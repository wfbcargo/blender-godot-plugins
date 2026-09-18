"""Build a character from its spec, stage by stage, resuming where the file already is.

    from character_pipeline import runner
    report = runner.build("C:/.../characters/belle.toml")                   # everything
    report = runner.build(spec, from_stage="garments")                         # in a .blend saved after moves
    report = runner.build(spec, to_stage="moves", save=False)
    report = runner.build(spec, quality="draft")                               # over the spec's [build] quality

Each stage that runs stores an input hash and its report in the file (a Text datablock,
`character_pipeline:<id>`, so nothing of it reaches an exported glb). The hash covers the spec sections the stage reads, the hashes of the stages it needs and the
plugin versions, and the data and code files the stage reads (`inputs.py`: garment presets, the hair
preset and hair code, follow-through's registry, the skin bake's code), so:

- a stage whose inputs have not changed since it last ran in this file is skipped ("unchanged"),
  unless `force`;
- `from_stage` in a fresh Blender session - the .blend opened, nothing else - picks up from what the
  file holds, and refuses if an earlier stage is missing or was built from a different spec;
- a stage whose preconditions do not hold refuses and names the order (`stages.StageRefused`).

With `save` (default) the .blend goes to the spec's `export.blend` after the last stage (resolved by
`spec.resolve_blend`: a relative path lands under $BLEND_DIR, else the project), refusing to overwrite a file
holding a scene this session does not have, and refusing - before any stage runs - a path outside the project
and $BLEND_DIR unless `save_outside=True` (06 rank 2: a copied spec cannot save over the real blends).

Where the minutes went: every stage that runs records its wall time, and the build's own record - the
quality, `stage_seconds` for the stages this build ran, what it skipped, and `total_seconds` - goes into the
returned report (`report["build"]`), the .blend (Text `character_pipeline:<id>:build`) and, when the export
stage ran, the manifest's `build` block (rewritten once review has run, so it is the whole build's).

Stages that put something on the body nothing takes off (hair, muscle: `stages.RESTARTS_FROM_BODY`) are not
run a second time on a body that has it: a whole build (no `from_stage`, or `from_stage="body"`) whose
`[hair]` or `[muscle]` changed rebuilds from body, forced, and says so in `report["build"]["restarted"]`; a
build started later than body still refuses (the stage's own check). Flesh and moves are there too for a
dressed body: they refuse while garments are bound, so a whole build whose `[flesh]` or `[moves]` changed on
a dressed file restarts from body.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time

import bpy

from . import inputs, plugins, quality as quality_mod, spec as spec_mod, stages

KEY = "character_pipeline"


class BuildRefused(RuntimeError):
    pass


def _text_name(ch):
    return f"{KEY}:{ch.id}"


def records(ch):
    """{stage: {hash, report, versions, seconds}} for this character, as the open file holds them.

    Kept in a Text datablock, `character_pipeline:<id>`, not on the rig: a custom property on the rig
    goes into every glb it is exported with as node extras, and build bookkeeping has no place in the
    engine. A text saves with the .blend and is never exported. The records only count while the rig
    they describe exists."""
    text = bpy.data.texts.get(_text_name(ch))
    if text is None or bpy.data.objects.get(ch.rig) is None:
        return {}
    try:
        data = json.loads(text.as_string())
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _store(ch, name, entry):
    if bpy.data.objects.get(ch.rig) is None:
        return
    data = records(ch)
    data[name] = entry
    text = bpy.data.texts.get(_text_name(ch)) or bpy.data.texts.new(_text_name(ch))
    text.clear()
    text.write(json.dumps(data, indent=1, default=str))


def _forget(ch, stage_names):
    text = bpy.data.texts.get(_text_name(ch))
    data = records(ch)
    if text is None or not any(n in data for n in stage_names):
        return
    for n in stage_names:
        data.pop(n, None)
    text.clear()
    text.write(json.dumps(data, indent=1, default=str))


def _hash(ch, name, needs, sections, done, versions, quality=None, reads=None):
    parts = {"stage": name, "spec": ch.digest(*sections), "needs": {n: done.get(n) for n in needs},
             "versions": versions}
    if quality is not None:                     # a "final" build hashes as it did before quality existed
        parts["quality"] = quality
    if reads:                                   # the data and code the stage reads (inputs.py)
        parts["reads"] = reads
    return hashlib.sha1(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def stage_hash(ch, name, needs, sections, done, q, drop=()):
    """(input hash, plugin versions, reads) of one stage: the spec sections it reads, the hashes of the stages
    it needs (`done`), the plugin versions it builds with, the quality settings it reads, and the data and code
    files it reads (`inputs.stage_inputs`)."""
    versions = plugins.stage_versions(ch, name)
    reads = inputs.stage_inputs(ch, name, drop=drop)
    return _hash(ch, name, needs, sections, done, versions, quality_mod.for_hash(q, name), reads), versions, reads


def plan(spec, quality=None, drop=None):
    """{stage: input hash} this spec builds with now, from the spec and the plugins alone - nothing is run and
    the open file is not read. A stage whose hash differs from its record in a file reruns there.
    `drop` ({stage: [labels]}) leaves inputs out of a stage's hash: the hash test's control only."""
    ch = spec_mod.load(spec) if isinstance(spec, (str, os.PathLike)) else spec
    q = quality_mod.check(quality or ch.build.quality)
    plugins.use()
    wanted = [s for s in stages.STAGES if s[5](ch)]
    names = [s[0] for s in wanted]
    done = {}
    for name, needs, sections, _check, _run, _applies in wanted:
        needs = [n for n in needs if n in names]
        done[name] = stage_hash(ch, name, needs, sections, done, q, drop=(drop or {}).get(name, ()))[0]
    return done


def open_saved(spec, log=print):
    """Open the spec's saved `[export] blend` when it exists and no other file is open, so its stage records
    are used: a `[flesh]` edit then reruns flesh to review, not the whole build from body.

    - nothing opened yet (Blender started with no file, `bpy.data.filepath` empty): the saved file is opened;
    - the saved file is already the open one: nothing to do;
    - another file is open: left open - the caller chose it (a `body.source = "blend"` spec's source file).

    Returns the path opened, or None. Opening replaces everything in this session, so a build script calls
    this before anything else touches the scene."""
    ch = spec_mod.load(spec) if isinstance(spec, (str, os.PathLike)) else spec
    path = ch.blend_path()
    if not path or not os.path.isfile(path):
        return None
    current = bpy.data.filepath or ""
    if current:
        if os.path.normcase(os.path.abspath(current)) != os.path.normcase(os.path.abspath(path)):
            log(f"[{ch.id}] {current} is open, so the saved {path} is not: its stage records are not used")
        return None
    bpy.ops.wm.open_mainfile(filepath=path)
    log(f"[{ch.id}] opened the saved {path}: stages whose inputs have not changed are skipped")
    return path


def check_save_path(ch, path, save_outside=False):
    """Refuse (BuildRefused) a .blend path outside the project and $BLEND_DIR unless `save_outside`: a spec
    copied into a scratch project with an absolute `[export] blend`, or a stray $BLEND_DIR, must not save over
    the real file. Returns the path."""
    roots = ch.save_roots()
    if not save_outside and not spec_mod.inside(path, roots):
        raise BuildRefused(f"[{ch.id}] refusing to save {path}: it is outside the project and $BLEND_DIR "
                           f"({', '.join(roots) or 'none known'}) - make [export] blend relative, set BLEND_DIR, "
                           "or pass save_outside=True")
    return path


def _save(ch, path, save_outside=False):
    """save_as_mainfile, refusing a path outside the project and $BLEND_DIR (`check_save_path`) and a file on
    disk that has a scene this session lacks."""
    check_save_path(ch, path, save_outside)
    if os.path.isfile(path) and os.path.normcase(os.path.abspath(bpy.data.filepath or "")) != os.path.normcase(os.path.abspath(path)):
        before = set(bpy.data.libraries)
        with bpy.data.libraries.load(path) as (src, _dst):
            on_disk = list(src.scenes)
        for lib in set(bpy.data.libraries) - before:
            bpy.data.libraries.remove(lib)
        lost = sorted(set(on_disk) - {s.name for s in bpy.data.scenes})
        if lost:
            raise BuildRefused(f"refusing to save over {path}: it holds scene(s) {lost} this session does not")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)     # a fresh BLEND_DIR may not exist yet
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    return path


class _Restart(Exception):
    pass


def build(spec, from_stage=None, to_stage=None, force=False, save=True, log=print, quality=None, resume=False,
          save_outside=False):
    """Run the spec's stages. `spec` is a path or a `spec.Character`. `quality` overrides the spec's
    `[build] quality` ("draft", "preview", "final"). `resume` first opens the spec's saved .blend when no
    file is open (`open_saved`), which is what a build script run from the command line wants.
    `save_outside` lets the .blend be saved outside the project and $BLEND_DIR (refused otherwise, before
    anything runs). Returns {stage: {status, report}, "build": {...}}."""
    ch = spec_mod.load(spec) if isinstance(spec, (str, os.PathLike)) else spec
    blend = ch.blend_path() if save else None
    if blend:
        check_save_path(ch, blend, save_outside)
    if resume:
        open_saved(ch, log=log)
    q = quality_mod.check(quality or ch.build.quality)
    t_build = time.time()
    try:
        report = _build(ch, from_stage, to_stage, force, log, q, forced=())
        restarted = None
    except _Restart as why:
        restarted = str(why)
        log(f"[{ch.id}] {restarted}")
        report = _build(ch, from_stage, to_stage, force, log, q, forced=("body",))
    ran = {k: v["seconds"] for k, v in report.items() if v.get("status") == "ran"}
    summary = {"quality": q, "stage_seconds": ran,
               "skipped": sorted(k for k, v in report.items() if v.get("status") != "ran"),
               "total_seconds": round(time.time() - t_build, 1)}
    if restarted:
        summary["restarted"] = restarted
    if ran:
        _store_build(ch, summary)
        if "export" in ran:
            _manifest_build(ch, summary)
    report["build"] = summary
    log(f"[{ch.id}] {q} build: {summary['total_seconds']}s ({', '.join(f'{k} {v}' for k, v in ran.items()) or 'nothing ran'})")
    if blend and any(v.get("status") for v in report.values() if isinstance(v, dict)):
        report["saved"] = _save(ch, blend, save_outside)
    return report


def build_record(ch):
    """The last build's record in the open file: {quality, stage_seconds, skipped, total_seconds}, or None."""
    text = bpy.data.texts.get(_text_name(ch) + ":build")
    try:
        return json.loads(text.as_string()) if text is not None else None
    except ValueError:
        return None


def _store_build(ch, summary):
    name = _text_name(ch) + ":build"
    text = bpy.data.texts.get(name) or bpy.data.texts.new(name)
    text.clear()
    text.write(json.dumps(summary, indent=1))


def _manifest_build(ch, summary):
    """The build block of the manifest export wrote: where this build's minutes went."""
    path = os.path.join(ch.out_dir(), f"{ch.id}.moves.json")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    manifest["build"] = summary
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)


def _build(ch, from_stage, to_stage, force, log, q, forced):
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
    ctx = {"scratch": tempfile.mkdtemp(prefix=f"pipeline_{ch.id}_"), "versions": versions, "quality": q}
    # a whole build of a brief body can start over from body; one started later cannot
    restartable = not forced and ch.body.source == "brief" and start <= names.index("body")
    if restartable:
        for gone, again in stages.CARRIED.items():
            if gone not in names and again(ch):
                raise _Restart(f"the spec has no [{gone}] now but the body carries it: rebuilding from body")
    for i, (name, needs, sections, check, run, _applies) in enumerate(wanted):
        needs = [n for n in needs if n in names]
        # the four plugins every stage builds with, an optional one (lookdev) only where the stage reads it,
        # and the data and code files it reads
        h, stage_versions, reads = stage_hash(ch, name, needs, sections, done, q)
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
        # preconditions guard running a stage, not skipping one: once garments are on, flesh's "no
        # garments bound" can never hold again, and a finished build must still rerun as unchanged
        if not force and name not in forced and rec is not None and rec.get("hash") == h:
            done[name] = h
            report[name] = {"status": "unchanged", "report": rec.get("report")}
            log(f"[{ch.id}] {name}: unchanged")
            continue
        if rec is not None and not force and name not in forced:
            moved = inputs.changed(rec.get("inputs"), reads)
            if moved and "inputs" in rec:
                log(f"[{ch.id}] {name}: what it reads changed: {', '.join(moved)}")
        again = stages.RESTARTS_FROM_BODY.get(name)
        if again is not None and restartable and again(ch):
            if name in ("flesh", "moves"):
                raise _Restart(f"{name} changed and garments are bound to the rig ({', '.join(stages.garments_bound(ch))}): "
                               "rebuilding from body")
            raise _Restart(f"{name} changed and the body already carries it (it cannot be taken off): "
                           "rebuilding from body")
        problem = check(ch)
        if problem:
            raise stages.StageRefused(f"[{ch.id}] {problem}")
        t0 = time.time()
        log(f"[{ch.id}] {name} ...")
        out = run(ch, ctx)
        took = round(time.time() - t0, 1)
        done[name] = h
        # what came after this stage was built on what it just replaced
        _forget(ch, names[i + 1:])
        _store(ch, name, {"hash": h, "report": _small(out), "versions": stage_versions, "inputs": reads,
                          "seconds": took})
        stored = records(ch)
        report[name] = {"status": "ran", "seconds": took, "report": out}
        log(f"[{ch.id}] {name}: done in {took}s")
    return report


def _small(value, limit=4000):
    """What goes on the rig: the report, cut down if it is large - the full one is returned."""
    text = json.dumps(value, default=str)
    if len(text) <= limit:
        return json.loads(text)
    return {"truncated": True, "keys": sorted(value)[:40] if isinstance(value, dict) else None}
