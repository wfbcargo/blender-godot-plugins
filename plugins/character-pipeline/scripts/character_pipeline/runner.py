"""Build a character from its spec, stage by stage, resuming where the file already is.

    from character_pipeline import runner
    report = runner.build("C:/.../characters/belle.toml")                   # everything
    report = runner.build(spec, from_stage="garments")                         # in a .blend saved after moves
    report = runner.build(spec, to_stage="moves", save=False)

Each stage that runs stores an input hash and its report on the rig (`rig["character_pipeline"]`,
JSON). The hash covers the spec sections the stage reads, the hashes of the stages it needs and the
plugin versions, so:

- a stage whose inputs have not changed since it last ran in this file is skipped ("unchanged"),
  unless `force`;
- `from_stage` in a fresh Blender session - the .blend opened, nothing else - picks up from what the
  file holds, and refuses if an earlier stage is missing or was built from a different spec;
- a stage whose preconditions do not hold refuses and names the order (`stages.StageRefused`).

With `save` (default) the .blend goes to the spec's `export.blend` after the last stage, refusing to
overwrite a file holding a scene this session does not have.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time

import bpy

from . import plugins, spec as spec_mod, stages

KEY = "character_pipeline"


class BuildRefused(RuntimeError):
    pass


def records(ch):
    rig = bpy.data.objects.get(ch.rig)
    raw = rig.get(KEY) if rig is not None else None
    try:
        return json.loads(raw) if isinstance(raw, str) else {}
    except ValueError:
        return {}


def _store(ch, name, entry):
    rig = bpy.data.objects.get(ch.rig)
    if rig is None:
        return
    data = records(ch)
    data[name] = entry
    rig[KEY] = json.dumps(data, default=str)


def _hash(ch, name, needs, sections, done, versions):
    parts = {"stage": name, "spec": ch.digest(*sections), "needs": {n: done.get(n) for n in needs},
             "versions": versions}
    return hashlib.sha1(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def _save(ch, path):
    """save_as_mainfile, refusing if the file on disk has a scene this session lacks."""
    if os.path.isfile(path) and os.path.normcase(os.path.abspath(bpy.data.filepath or "")) != os.path.normcase(os.path.abspath(path)):
        before = set(bpy.data.libraries)
        with bpy.data.libraries.load(path) as (src, _dst):
            on_disk = list(src.scenes)
        for lib in set(bpy.data.libraries) - before:
            bpy.data.libraries.remove(lib)
        lost = sorted(set(on_disk) - {s.name for s in bpy.data.scenes})
        if lost:
            raise BuildRefused(f"refusing to save over {path}: it holds scene(s) {lost} this session does not")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    return path


def build(spec, from_stage=None, to_stage=None, force=False, save=True, log=print):
    """Run the spec's stages. `spec` is a path or a `spec.Character`. Returns {stage: {status, report}}."""
    ch = spec_mod.load(spec) if isinstance(spec, (str, os.PathLike)) else spec
    plugins.use()
    versions = plugins.versions()
    wanted = [s for s in stages.STAGES if s[5](ch)]
    names = [s[0] for s in wanted]
    for label, value in (("from_stage", from_stage), ("to_stage", to_stage)):
        if value is not None and value not in names:
            raise BuildRefused(f"{label} {value!r} is not a stage of this spec (its stages: {', '.join(names)})")
    start = names.index(from_stage) if from_stage else 0
    stop = names.index(to_stage) + 1 if to_stage else len(names)

    stored = records(ch)
    done = {}                                   # stage -> input hash, as the file holds it or this run made it
    report = {}
    ctx = {"scratch": tempfile.mkdtemp(prefix=f"pipeline_{ch.id}_"), "versions": versions}
    for i, (name, needs, sections, check, run, _applies) in enumerate(wanted):
        needs = [n for n in needs if n in names]
        h = _hash(ch, name, needs, sections, done, versions)
        if i < start:
            rec = stored.get(name)
            if rec is None:
                raise BuildRefused(f"from_stage={from_stage!r}, but {name} has not run in this file - "
                                   f"open the .blend saved after it, or start from {name}")
            if rec.get("hash") != h and not force:
                raise BuildRefused(f"{name} in this file was built from a different spec or plugin versions "
                                   f"(stored {rec.get('hash')}, now {h}) - rebuild from {name}")
            done[name] = rec.get("hash")
            report[name] = {"status": "in file"}
            continue
        if i >= stop:
            break
        rec = stored.get(name)
        if not force and rec is not None and rec.get("hash") == h and check(ch) is None:
            done[name] = h
            report[name] = {"status": "unchanged", "report": rec.get("report")}
            log(f"[{ch.id}] {name}: unchanged")
            continue
        problem = check(ch)
        if problem:
            raise stages.StageRefused(f"[{ch.id}] {problem}")
        t0 = time.time()
        log(f"[{ch.id}] {name} ...")
        out = run(ch, ctx)
        took = round(time.time() - t0, 1)
        done[name] = h
        _store(ch, name, {"hash": h, "report": _small(out), "versions": versions, "seconds": took})
        stored = records(ch)
        report[name] = {"status": "ran", "seconds": took, "report": out}
        log(f"[{ch.id}] {name}: done in {took}s")
    if save and ch.export.blend and report:
        report["saved"] = _save(ch, ch.export.blend)
    return report


def _small(value, limit=4000):
    """What goes on the rig: the report, cut down if it is large - the full one is returned."""
    text = json.dumps(value, default=str)
    if len(text) <= limit:
        return json.loads(text)
    return {"truncated": True, "keys": sorted(value)[:40] if isinstance(value, dict) else None}
