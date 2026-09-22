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
build started later than body still refuses (the stage's own check). Moves is there too for a dressed body: it
refuses while garments are bound, so a whole build whose `[moves]` changed on a dressed file restarts from body.
A whole build whose flesh must rerun on a dressed file takes the garments off instead (`stages.undress`,
`UNDRESS_FOR_FLESH`) and the garments stage cuts them again; it restarts from body only if something of
wardrobe's could not be taken off.

The cascade stops where an output did not change: a stage that reads an earlier one only through what it left
in the file (`inputs.READS_OUTPUT`: moves of flesh) keeps a view hash with the digest of that output
(`inputs.outputs`) in place of the earlier stage's input hash (`view_hash`), and is skipped when its input
hash moved but its view did not.
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
    return _hash(ch, name, needs, sections, done, versions, quality_mod.for_hash(q, name, ch), reads), versions, reads


def view_hash(ch, name, needs, sections, done, outs, q, versions, reads, drop=()):
    """The stage's hash with, for each stage it needs whose output it reads (`inputs.READS_OUTPUT`), the digest of
    that output (`outs[need]`, as `inputs.outputs` took it) in place of the need's input hash - or None when the
    stage reads no earlier output, or an output it reads was never digested (a record from before 0.10.0). A stage
    whose input hash moved but whose view hash did not reads exactly what it read when it last ran. `drop` leaves
    output labels out of the digests: the hash test's control only."""
    reads_out = [n for n in inputs.READS_OUTPUT.get(name, ()) if n in needs]
    if not reads_out:
        return None
    seen = {n: done.get(n) for n in needs}
    for n in reads_out:
        out = outs.get(n)
        if not out:
            return None
        seen[n] = "output:" + inputs.data({k: v for k, v in out.items() if k not in drop})
    parts = {"stage": name, "spec": ch.digest(*sections), "needs": seen, "versions": versions, "view": True,
             "quality": quality_mod.for_hash(q, name)}
    if reads:
        parts["reads"] = reads
    return hashlib.sha1(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def _same_view(ch, name, rec, view):
    """Whether a stage whose input hash moved can be skipped: its record's view hash is the one it has now, and
    what it made is still in the file (the moves stage's stored clips)."""
    if view is None or rec is None or rec.get("view") != view:
        return False
    if name == "moves":
        return list(stages.moves_stored(ch)) == list(ch.moves.roles)
    return False


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
    godot = spec_mod.godot_project_of(path)
    if godot and not spec_mod.project_config(ch.project).get("blend", {}).get("inside_godot"):
        raise BuildRefused(
            f"[{ch.id}] refusing to save {path}: it is inside the Godot project {godot}, which would import it "
            "with its Blender importer (with no Blender path set, a headless --import fails there and the glbs "
            f"are not imported). Set [blend] dir in {os.path.join(ch.project or godot, spec_mod.PROJECT_CONFIG)} "
            "(or BLEND_DIR) to a folder outside it, put a .gdignore in the folder the blend goes to, or set "
            "[blend] inside_godot = true there if Godot is meant to import it")
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


class StageFailed(RuntimeError):
    """A stage raised while it ran. The message names the stage, how long it ran and the cause, and - raised out
    of `build` - where the file was left: `saved_after` is the last stage whose checkpoint was saved in this
    build (None when none was). The original exception is its `__cause__`."""

    def __init__(self, message, stage=None, saved_after=None, seconds=None):
        super().__init__(message)
        self.stage, self.saved_after, self.seconds = stage, saved_after, seconds


# Save the .blend after every stage that runs (when the build saves at all), so a failing stage costs only
# itself on the next build. A save of a character's file is well under a second against stages of 1-70 s.
CHECKPOINT = True


# A whole build whose flesh must rerun on a dressed body takes the garments off (`stages.undress`) instead of
# restarting from body. False restores the restart (the control in pipeline_woman's dressed flesh edit).
UNDRESS_FOR_FLESH = True


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
    for w in ch.warnings:
        log(f"[{ch.id}] WARNING {w}")
    t_build = time.time()
    # after every stage that runs, the file is saved (when this build saves at all), so a stage that fails
    # leaves the file as the last good stage left it: the next build resumes there instead of from body
    checkpoint = (lambda: _save(ch, blend, save_outside)) if blend and CHECKPOINT else None
    try:
        try:
            report = _build(ch, from_stage, to_stage, force, log, q, forced=(), checkpoint=checkpoint)
            restarted = None
        except _Restart as why:
            restarted = str(why)
            log(f"[{ch.id}] {restarted}")
            report = _build(ch, from_stage, to_stage, force, log, q, forced=("body",), checkpoint=checkpoint)
    except StageFailed as failed:
        saved = failed.saved_after
        if saved and blend:
            where = f"{blend} holds the build as {saved} left it; fix the cause and build again to resume at {failed.stage}"
        elif blend and os.path.isfile(blend):
            where = f"{blend} is as it was before this build; build again to resume at {failed.stage}"
        else:
            where = "no .blend was saved"
        raise StageFailed(f"{failed} - {where}", stage=failed.stage, saved_after=saved,
                          seconds=failed.seconds) from failed.__cause__
    ran = {k: v["seconds"] for k, v in report.items() if v.get("status") == "ran"}
    summary = {"quality": q, "stage_seconds": ran,
               "skipped": sorted(k for k, v in report.items() if v.get("status") != "ran"),
               "total_seconds": round(time.time() - t_build, 1)}
    if restarted:
        summary["restarted"] = restarted
    if ch.warnings:
        summary["warnings"] = list(ch.warnings)
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


def _build(ch, from_stage, to_stage, force, log, q, forced, checkpoint=None):
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
    outs = {}                                   # stage -> digest of its output a later stage reads (inputs.outputs)
    report = {}
    saved_after = None                          # the last stage checkpointed in this build
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
        view = view_hash(ch, name, needs, sections, done, outs, q, stage_versions, reads)
        if i < start:
            rec = stored.get(name)
            if rec is None:
                raise BuildRefused(f"from_stage={from_stage!r}, but {name} has not run in this file - "
                                   f"open the .blend saved after it, or start from {name}")
            same_view = rec.get("hash") != h and _same_view(ch, name, rec, view)
            if rec.get("hash") != h and not force and not same_view:
                raise BuildRefused(f"{name} in this file was built from a different spec or plugin versions "
                                   f"(stored {rec.get('hash')}, now {h}) - rebuild from {name}")
            done[name] = h if same_view else rec.get("hash")
            if rec.get("output") is not None:
                outs[name] = rec["output"]
            report[name] = {"status": "in file"}
            continue
        if i >= stop:
            break
        rec = stored.get(name)
        # preconditions guard running a stage, not skipping one: once garments are on, flesh's "no
        # garments bound" can never hold again, and a finished build must still rerun as unchanged
        if not force and name not in forced and rec is not None and rec.get("hash") == h:
            done[name] = h
            if rec.get("output") is not None:
                outs[name] = rec["output"]
            report[name] = {"status": "unchanged", "report": rec.get("report")}
            log(f"[{ch.id}] {name}: unchanged")
            continue
        # the cascade stops here: an earlier stage reran, but what this one reads of it came out the same. Its
        # record takes the new input hash, so every stage after it still sees the change upstream and reruns
        if not force and name not in forced and _same_view(ch, name, rec, view):
            done[name] = h
            _store(ch, name, dict(rec, hash=h, versions=stage_versions, inputs=reads, view=view))
            stored = records(ch)
            what = ", ".join(inputs.READS_OUTPUT[name])
            report[name] = {"status": "unchanged", "report": rec.get("report"),
                            "why": f"what it reads of {what} came out the same"}
            log(f"[{ch.id}] {name}: unchanged (its input hash moved, but what it reads of {what} came out the same)")
            continue
        if rec is not None and view is not None and rec.get("view") and not force and name not in forced:
            log(f"[{ch.id}] {name}: what it reads of {', '.join(inputs.READS_OUTPUT[name])} changed")
        if rec is not None and not force and name not in forced:
            moved = inputs.changed(rec.get("inputs"), reads)
            if moved and "inputs" in rec:
                log(f"[{ch.id}] {name}: what it reads changed: {', '.join(moved)}")
        again = stages.RESTARTS_FROM_BODY.get(name)
        if name == "flesh" and restartable and UNDRESS_FOR_FLESH and stages.garments_bound(ch):
            # a dressed body's flesh: the garments come off (they are cut again from the new flesh by the garments
            # stage) rather than the whole build starting over from body; if anything of wardrobe's is left, restart
            took_off = stages.undress(ch)
            log(f"[{ch.id}] flesh changed on a dressed body: took off {', '.join(took_off['garments'])} "
                f"({took_off['hem_bones']} hem bones, {len(took_off['body_groups'])} cover groups on the body)")
            if took_off["left"]:
                raise _Restart(f"flesh changed and garments could not all be taken off ({took_off['left']}): "
                               "rebuilding from body")
            ctx["undressed"] = took_off
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
        try:
            out = run(ch, ctx)
        except (BuildRefused, stages.StageRefused, _Restart):
            raise
        except Exception as exc:
            took = round(time.time() - t0, 1)
            log(f"[{ch.id}] {name}: FAILED after {took}s: {exc}")
            raise StageFailed(f"[{ch.id}] {name} failed after {took}s: {type(exc).__name__}: {exc}",
                              stage=name, saved_after=saved_after, seconds=took) from exc
        took = round(time.time() - t0, 1)
        done[name] = h
        # what came after this stage was built on what it just replaced - except a stage that reads this one only
        # through its output (inputs.READS_OUTPUT): its record stays, and its view hash says whether it still holds
        _forget(ch, [n for n in names[i + 1:] if name not in inputs.READS_OUTPUT.get(n, ())])
        entry = {"hash": h, "report": _small(out), "versions": stage_versions, "inputs": reads, "seconds": took}
        if view is not None:
            entry["view"] = view
        output = inputs.outputs(ch, name)
        if output is not None:
            entry["output"] = output
            outs[name] = output
            before = (rec or {}).get("output")
            if before:
                moved = inputs.output_changed(before, output)
                log(f"[{ch.id}] {name}: what later stages read of it "
                    + (f"changed: {', '.join(moved)}" if moved else "came out the same"))
        _store(ch, name, entry)
        stored = records(ch)
        report[name] = {"status": "ran", "seconds": took, "report": out}
        log(f"[{ch.id}] {name}: done in {took}s")
        if checkpoint is not None and i + 1 < stop:     # the last stage's file is saved by `build` itself
            t1 = time.time()
            checkpoint()
            saved_after = name
            log(f"[{ch.id}] {name}: checkpoint saved in {time.time() - t1:.1f}s")
    return report


def _small(value, limit=4000):
    """What goes on the rig: the report, cut down if it is large - the full one is returned."""
    text = json.dumps(value, default=str)
    if len(text) <= limit:
        return json.loads(text)
    return {"truncated": True, "keys": sorted(value)[:40] if isinstance(value, dict) else None}
