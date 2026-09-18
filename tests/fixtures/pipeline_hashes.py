"""Rebuilds that match what changed: every file a stage reads is in its input hash (06 rank 3).

Nothing is built. `runner.plan` computes each stage's input hash from the spec and the plugins as they are on
disk - the hash a build compares with the record in the saved .blend, so a stage whose planned hash moves is a
stage the next build reruns there. The fixture copies the plugins into its own folder, points the pipeline at
the copies, and then edits one file at a time (and puts it back):

- each **flip** edits a file some stage reads - a garment preset worn by the spec, the hair preset in use, the
  hair and brow code, lookdev's hair material and bake code, humanform's skin code, follow-through's built-in
  and user registries, a plugin version, the skin map size of a final build - and must move that stage's hash
  and leave every stage before it alone;
- each **unrelated** edit touches something no stage of the spec reads (a preset it does not wear, a hair
  preset it does not use, lookdev's thresholds, follow-through's cloth code) and must move nothing;
- each flip's **control** plans again with the flipped input left out of its stage's hash (`plan(drop=)`):
  the flip must then go unseen at that stage, so the check above is what catches a stage that stops hashing
  an input, and not something else in the hash.

Four flips reach a stage's hash through a part other than `inputs.py`: a plugin version (`version:<plugin>`,
from `plugins.stage_versions`), the skin map size and the close-up views of a final build (`quality:skin`,
`quality:close`, from `quality.for_hash`) and a spec section edit (`spec:<section>`, from the stage's sections
in `stages.STAGES`). `plan(drop=)` only leaves out `inputs.py` labels, so for these the fixture leaves the part
out itself, by wrapping that function or table for the length of one plan (`_left_out`); their controls then
work as every other flip's do.

`PIPELINE_HASHES_DROP=<stage>:<label>` leaves that input out of every plan the flips are judged on, as if
`inputs.py` no longer named it: the fixture must then fail (the harness's control, run by hand). It takes the
`_left_out` labels too: `body:version:wardrobe`, `bake:quality:skin`, `flesh:spec:flesh`, `review:quality:close`.

The golden holds, per flip, the stage expected, the first stage that moved and every stage that moved.
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

VARS = ("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS", "LD_SCRIPTS")
PACKAGES = ("rig_analysis", "humanform", "follow_through", "wardrobe", "character_pipeline", "lookdev_blender")
H.use(*VARS)

BODY = '''
[character]
id = "fixhash"
name = "FixHash"

[body]
sex = "female"
age = 28
stature = 1.70
build = "curvy"
seed = 7
style = "realistic"
skin = [0.62, 0.45, 0.36]

[moves]
gaits = { Walk = 0.2, Run = 2.0 }
style = "adult"

[export]
dir = "assets/fixhash"
res_dir = "res://assets/fixhash"
blend = "fixhash.blend"
'''

# the spec most flips are judged on: every stage with a file to read
FULL = BODY + '''
[muscle]
output = "geometry"

[hair]
preset = "bun"
brows = true
lashes = true

[flesh]
types = ["breast", "butt"]

[[outfit]]
preset = "sports_top"

[[outfit]]
preset = "shorts_mid_thigh"
'''

# the deprecated hair, which reads the pipeline's own hair.py
SHELL = BODY + '''
[hair]
kind = "shell_bun"
'''

# no close-up set: the review stage reads nothing of rig-anything's closeups.py
NOCLOSE = BODY + '''
[review]
close = false
'''

# a muscle normal map, which the bake stage bakes with lookdev's detail.py
NORMAL = BODY + '''
[muscle]
output = "normal"
'''


def _copy_plugins(root):
    """The plugins a build reads, copied: their scripts, data and plugin.json, not docs, Godot files or
    humanform's seed sheets."""
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "seed", "sources", "godot", "references", "skills",
                                    "bin", "*.md", "*.png")
    out = {}
    for var in VARS:
        scripts = H.scripts(var)
        plugin = os.path.dirname(scripts)
        dst = os.path.join(root, os.path.basename(plugin))
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(plugin, dst, ignore=ignore)
        out[var] = os.path.join(dst, os.path.basename(scripts))
    return out


def _use_copies(copies):
    """Point the pipeline at the copies: environment, sys.path and a fresh import of every package."""
    for var in VARS:
        orig = H.scripts(var)
        while orig in sys.path:
            sys.path.remove(orig)
        os.environ[var] = copies[var]
    for name in [k for k in sys.modules if k.split(".")[0] in PACKAGES]:
        del sys.modules[name]
    sys.path.insert(0, copies["CP_SCRIPTS"])
    import character_pipeline
    character_pipeline.reload_all()
    from character_pipeline import runner
    return runner


def _bump_number(value, path):
    """The first number found under `path` (a list of keys, depth-first below it), nudged: a real edit of the
    data rather than a key no plugin reads."""
    node = value
    for k in path:
        node = node[k]

    def walk(n):
        items = n.items() if isinstance(n, dict) else enumerate(n) if isinstance(n, list) else ()
        for k, v in items:
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                n[k] = v + (0.001 if isinstance(v, float) else 1)
                return True
            if isinstance(v, (dict, list)) and walk(v):
                return True
        return False
    if not walk(node):
        raise AssertionError(f"no number under {path}")


def _edit_json(path, keys):
    def edit():
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        _bump_number(data, keys)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
    return edit


def _edit_code(path):
    def edit():
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n# pipeline_hashes: an edit\n")
    return edit


def _edit_version(path):
    def edit():
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data["version"] = data["version"] + "-edit"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
    return edit


def _write(path, data):
    def edit():
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
    return edit


def build():
    root = os.path.join(H.out_dir(), "pipeline_hashes")
    os.makedirs(os.path.join(root, "characters"), exist_ok=True)
    copies = _copy_plugins(os.path.join(root, "plugins"))
    user_types = os.path.join(root, "user_types.json")
    if os.path.exists(user_types):
        os.remove(user_types)
    os.environ["FOLLOW_THROUGH_TYPES"] = user_types
    runner = _use_copies(copies)
    from character_pipeline import quality, spec

    specs = {}
    for name, text in (("full", FULL), ("shell", SHELL), ("normal", NORMAL), ("noclose", NOCLOSE)):
        path = os.path.join(root, "characters", f"fixhash_{name}.toml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        specs[name] = path

    def P(var, *rel):
        return os.path.join(os.path.dirname(copies[var]), *rel)

    hf = copies["HF_SCRIPTS"]
    ld = copies["LD_SCRIPTS"]
    # (name, spec, edit, stage expected to move first or None for "nothing moves", label a control drops)
    flips = [
        ("garments.json: a worn preset", "full", _edit_json(P("WD_SCRIPTS", "presets", "garments.json"),
                                                            ["garments", "sports_top"]), "garments", "preset:sports_top"),
        ("garments.json: the second worn preset", "full", _edit_json(P("WD_SCRIPTS", "presets", "garments.json"),
                                                                     ["garments", "shorts_mid_thigh"]),
         "garments", "preset:shorts_mid_thigh"),
        ("hair_presets.json: the preset in use", "full", _edit_json(P("HF_SCRIPTS", "data", "hair_presets.json"),
                                                                    ["presets", "bun"]), "hair", "preset:bun"),
        ("hair_presets.json: the defaults", "full", _edit_json(P("HF_SCRIPTS", "data", "hair_presets.json"),
                                                               ["defaults"]), "hair", "preset:bun"),
        ("hair_presets.json: the hairline", "full", _edit_json(P("HF_SCRIPTS", "data", "hair_presets.json"),
                                                               ["hairline"]), "hair", "preset:bun"),
        ("humanform hair.py", "full", _edit_code(os.path.join(hf, "humanform", "hair.py")), "hair",
         "code:humanform.hair"),
        ("humanform brows.py", "full", _edit_code(os.path.join(hf, "humanform", "brows.py")), "hair",
         "code:humanform.brows"),
        ("face_regions.json", "full", _edit_json(P("HF_SCRIPTS", "data", "face_regions.json"), []), "hair",
         "data:humanform.face_regions"),
        ("lookdev hair.py", "full", _edit_code(os.path.join(ld, "lookdev_blender", "hair.py")), "hair",
         "code:lookdev_blender.hair"),
        ("lookdev materials.json: hair", "full", _edit_json(P("LD_SCRIPTS", "presets", "materials.json"),
                                                            ["materials", "hair"]), "hair", "data:lookdev.hair"),
        ("pipeline hair.py (shell_bun)", "shell", _edit_code(os.path.join(copies["CP_SCRIPTS"], "character_pipeline",
                                                                          "hair.py")), "hair",
         "code:character_pipeline.hair"),
        ("humanform skin.py", "full", _edit_code(os.path.join(hf, "humanform", "skin.py")), "bake",
         "code:humanform.skin"),
        ("humanform look.py", "full", _edit_code(os.path.join(hf, "humanform", "look.py")), "bake",
         "code:humanform.look"),
        ("lookdev bake.py", "full", _edit_code(os.path.join(ld, "lookdev_blender", "bake.py")), "bake",
         "code:lookdev_blender.bake"),
        ("lookdev detail.py (muscle normal map)", "normal", _edit_code(os.path.join(ld, "lookdev_blender",
                                                                                    "detail.py")), "bake",
         "code:lookdev_blender.detail"),
        ("follow-through builtin.json: a type", "full", _edit_json(P("FT_SCRIPTS", "types", "builtin.json"),
                                                                   ["types", "butt"]), "flesh",
         "data:follow_through.registry"),
        ("follow-through flesh.py", "full", _edit_code(os.path.join(copies["FT_SCRIPTS"], "follow_through", "flesh.py")),
         "flesh", "code:follow_through.flesh"),
        ("follow-through user registry", "full", _write(user_types, {
            "schema": "follow-through-types/1", "materials": {}, "examples": [],
            "types": {"butt": {"limit_share": 0.5}}}), "flesh", "data:follow_through.registry"),
        ("rig-anything closeups.py", "full", _edit_code(os.path.join(copies["RA_SCRIPTS"], "rig_analysis",
                                                                     "closeups.py")), "review",
         "code:rig_analysis.closeups"),
        # a plugin version moves every stage (body first): the version of each plugin is in every stage's hash
        ("wardrobe version", "full", _edit_version(P("WD_SCRIPTS", ".claude-plugin", "plugin.json")), "body",
         "version:wardrobe"),
        # unrelated: nothing this spec reads
        ("unrelated: garments.json, a preset not worn", "full",
         _edit_json(P("WD_SCRIPTS", "presets", "garments.json"), ["garments", "leggings"]), None, None),
        ("unrelated: hair_presets.json, a preset not used", "full",
         _edit_json(P("HF_SCRIPTS", "data", "hair_presets.json"), ["presets", "long_loose"]), None, None),
        ("unrelated: lookdev thresholds.json", "full",
         _edit_json(P("LD_SCRIPTS", "presets", "thresholds.json"), []), None, None),
        ("unrelated: follow-through cloth.py", "full",
         _edit_code(os.path.join(copies["FT_SCRIPTS"], "follow_through", "cloth.py")), None, None),
        ("unrelated: face_regions.json without brows or lashes", "normal",
         _edit_json(P("HF_SCRIPTS", "data", "face_regions.json"), []), None, None),
        ("unrelated: closeups.py with [review] close = false", "noclose",
         _edit_code(os.path.join(copies["RA_SCRIPTS"], "rig_analysis", "closeups.py")), None, None),
    ]
    drop_env = os.environ.get("PIPELINE_HASHES_DROP")
    judged_drop = {}
    if drop_env:
        stage, label = drop_env.split(":", 1)
        judged_drop = {stage: [label]}

    def plan(which, drop=None):
        """`which` is a spec's name or a loaded spec; `drop` ({stage: [labels]}) as `runner.plan`'s, and also
        the three labels that are not `inputs.py`'s (`_left_out`)."""
        drop = drop if drop is not None else judged_drop
        target = specs[which] if isinstance(which, str) else which
        return _left_out(drop, lambda rest: runner.plan(target, drop=rest))

    names = {k: list(plan(k)) for k in specs}
    out, failed = {}, []
    for title, which, edit, stage, label in flips:
        touched = _snapshot(copies, user_types)
        before = plan(which)
        control_before = plan(which, drop={stage: [label]}) if label else None
        try:
            edit()
            after = plan(which)
            control = plan(which, drop={stage: [label]}) if label else None
        finally:
            _restore(touched, user_types)
        moved = [s for s in names[which] if before[s] != after[s]]
        want = stage
        row = {"spec": which, "expect": want, "first": moved[0] if moved else None, "moved": moved}
        row["ok"] = (not moved) if want is None else (bool(moved) and moved[0] == want)
        if label:
            # with the input left out, the stage the flip targets must not move: the flip is only seen through it
            row["control_unseen"] = control[stage] == control_before[stage]
            row["label"] = label
        if not row["ok"] or row.get("control_unseen") is False:
            failed.append(title)
        out[title] = row

    # the skin map size of a final build is in bake's hash (a final file baked at 1024 must rebake); control: with
    # the size left out of bake's hash, the same change goes unseen at bake
    skin_drop = {"bake": ["quality:skin"]}
    before = plan("full")
    control_before = plan("full", drop=skin_drop)
    saved = quality.LEVELS["final"]["skin"]["size"]
    quality.LEVELS["final"]["skin"]["size"] = 1024
    try:
        old = plan("full")
        control = plan("full", drop=skin_drop)
    finally:
        quality.LEVELS["final"]["skin"]["size"] = saved
    moved = [s for s in names["full"] if before[s] != old[s]]
    row = {"spec": "full", "expect": "bake", "first": moved[0] if moved else None, "moved": moved,
           "ok": bool(moved) and moved[0] == "bake", "label": "quality:skin",
           "control_unseen": control["bake"] == control_before["bake"]}
    out["final skin map size 2048 -> 1024"] = row
    if not row["ok"] or not row["control_unseen"]:
        failed.append("final skin map size 2048 -> 1024")

    # the close-up set of a final build is in review's hash (a final file reviewed before the set existed must
    # review again and write it): the final views changed to the draft's move review and nothing before it
    saved = quality.LEVELS["final"]["close"]
    quality.LEVELS["final"]["close"] = dict(saved, views=quality.CLOSE_DRAFT)
    close_drop = {"review": ["quality:close"]}
    control_before = plan("full", drop=close_drop)
    try:
        other = plan("full")
        control = plan("full", drop=close_drop)
    finally:
        quality.LEVELS["final"]["close"] = saved
    moved = [s for s in names["full"] if before[s] != other[s]]
    row = {"spec": "full", "expect": "review", "first": moved[0] if moved else None, "moved": moved,
           "ok": moved == ["review"], "label": "quality:close",
           "control_unseen": control["review"] == control_before["review"]}
    out["final close-up views"] = row
    if not row["ok"] or not row["control_unseen"]:
        failed.append("final close-up views")

    # a spec edit moves its own stage on: [flesh] reruns flesh and after, never body, muscle, bake or hair
    import dataclasses
    ch = spec.load(specs["full"])
    edited = dataclasses.replace(ch, flesh=dataclasses.replace(ch.flesh, limit_share={"butt": 0.5}))
    base, flesh_edit = plan(ch), plan(edited)
    # control: with [flesh] left out of flesh's spec digest, the edit goes unseen at flesh
    flesh_drop = {"flesh": ["spec:flesh"]}
    control_base, control_edit = plan(ch, drop=flesh_drop), plan(edited, drop=flesh_drop)
    moved = [s for s in names["full"] if base[s] != flesh_edit[s]]
    row = {"spec": "full", "expect": "flesh", "first": moved[0] if moved else None, "moved": moved,
           "ok": bool(moved) and moved[0] == "flesh", "label": "spec:flesh",
           "control_unseen": control_edit["flesh"] == control_base["flesh"]}
    out["spec [flesh] edit"] = row
    if not row["ok"] or not row["control_unseen"]:
        failed.append("spec [flesh] edit")

    # what each stage of the full spec reads, by label (the digests themselves move with every plugin edit)
    from character_pipeline import inputs
    reads = {s: sorted(inputs.stage_inputs(ch, s)) for s in names["full"]}
    report = {"stages": names, "flips": out, "reads": reads, "failed": failed,
              "quality_skin": {q: quality.settings(q, "skin") for q in quality.QUALITIES},
              "final_hash_part_bake": quality.for_hash("final", "bake")}
    if failed:
        raise AssertionError(f"pipeline_hashes: flips not caught or unrelated edits that moved a stage: {failed}; "
                             + json.dumps({k: out[k] for k in failed if k in out}))
    return report


LEFT_OUT = ("version:", "quality:", "spec:")


def _left_out(drop, run):
    """Run `run(rest)` with the labels of `drop` ({stage: [labels]}) that are not `inputs.py`'s left out of their
    stage's hash, and the rest passed on as `runner.plan`'s own `drop`:

    - `version:<plugin>`: that plugin's version, out of the versions `plugins.stage_versions` gives the stage;
    - `quality:<part>`: that quality part, out of what `quality.for_hash` gives the stage;
    - `spec:<section>`: that spec section, out of the sections the stage digests (`stages.STAGES`).

    Each is patched for the length of this one plan and put back, whatever happens."""
    from character_pipeline import plugins, quality, stages
    rest, own = {}, {}
    for stage, labels in (drop or {}).items():
        for label in labels:
            (own if label.startswith(LEFT_OUT) else rest).setdefault(stage, []).append(label)
    if not own:
        return run(rest)

    def gone(stage, kind):
        return [label.split(":", 1)[1] for label in own.get(stage, ()) if label.startswith(kind)]

    real_versions, real_for_hash, real_stages = plugins.stage_versions, quality.for_hash, stages.STAGES

    def stage_versions(ch, stage):
        out = dict(real_versions(ch, stage))
        for plugin in gone(stage, "version:"):
            out.pop(plugin, None)
        return out

    def for_hash(q, stage):
        out = real_for_hash(q, stage)
        if isinstance(out, dict):
            out = {k: v for k, v in out.items() if k not in gone(stage, "quality:")} or None
        return out

    table = [(name, needs, tuple(s for s in sections if s not in gone(name, "spec:")), *more)
             for name, needs, sections, *more in real_stages]
    plugins.stage_versions, quality.for_hash, stages.STAGES = stage_versions, for_hash, table
    try:
        return run(rest)
    finally:
        plugins.stage_versions, quality.for_hash, stages.STAGES = real_versions, real_for_hash, real_stages


def _snapshot(copies, user_types):
    """Every file under the copies, by content, so an edit can be put back exactly."""
    snap = {}
    for var in VARS:
        top = os.path.dirname(copies[var])
        for dirpath, _dirs, files in os.walk(top):
            if "__pycache__" in dirpath:
                continue
            for f in files:
                p = os.path.join(dirpath, f)
                with open(p, "rb") as fh:
                    snap[p] = fh.read()
    return snap


def _restore(snap, user_types):
    for p, data in snap.items():
        with open(p, "rb") as fh:
            now = fh.read()
        if now != data:
            with open(p, "wb") as fh:
                fh.write(data)
    if os.path.exists(user_types):
        os.remove(user_types)


H.run("pipeline_hashes", build)
