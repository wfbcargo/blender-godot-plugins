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
    # control_before is planned before the change, as for the skin row: planned after it, both control plans see
    # the same quality and agree whether or not quality:close is dropped (critic round 1)
    close_drop = {"review": ["quality:close"]}
    control_before = plan("full", drop=close_drop)
    saved = quality.LEVELS["final"]["close"]
    quality.LEVELS["final"]["close"] = dict(saved, views=quality.CLOSE_DRAFT)
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

    # what moves reads of flesh's output: each flip must move its labels of the digest and moves' view hash; its
    # control leaves those labels out, and the flip must then go unseen; what flesh writes that moves never reads
    # (the jiggle block's swing limits) and what moves writes itself (the body's rotation modes, the pose, the
    # action on the rig) must move nothing
    output_drop = [label[len("output:"):] for label in judged_drop.get("flesh", []) if label.startswith("output:")]
    outputs = _output_flips(runner, ch, base, output_drop)
    failed += [f"output: {t}" for t, row in outputs.items() if not row["ok"] or row.get("control_unseen") is False]
    if failed:
        raise AssertionError(f"pipeline_hashes: flips not caught or unrelated edits that moved a stage: {failed}; "
                             + json.dumps({k: (out.get(k) or outputs.get(k[len("output: "):])) for k in failed}))
    report = {"stages": names, "flips": out, "outputs": outputs, "reads": reads, "failed": failed,
              "quality_skin": {q: quality.settings(q, "skin") for q in quality.QUALITIES},
              "final_hash_part_bake": quality.for_hash("final", "bake")}
    if failed:
        raise AssertionError(f"pipeline_hashes: flips not caught or unrelated edits that moved a stage: {failed}; "
                             + json.dumps({k: out[k] for k in failed if k in out}))
    return report


def _output_scene(ch):
    """A rig with a hip, a spine and a follow-through jiggle bone, and a cube skinned to it under the spec's names,
    as the flesh stage leaves a body: built the same way every time, so each flip starts from the same file."""
    import bmesh
    import bpy
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.actions):
        for block in list(coll):
            coll.remove(block)
    arm = bpy.data.armatures.new(ch.rig)
    rig = bpy.data.objects.new(ch.rig, arm)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, head, tail, parent in (("hips", (0, 0, 1.0), (0, 0, 1.2), None),
                                     ("spine", (0, 0, 1.2), (0, 0, 1.5), "hips"),
                                     ("ft_jiggle_belly", (0, -0.1, 1.1), (0, -0.25, 1.1), "hips")):
        b = arm.edit_bones.new(name)
        b.head, b.tail = head, tail
        if parent:
            b.parent = arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.bones["ft_jiggle_belly"]["ft_role"] = "jiggle"
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION" if pb.name.startswith("ft_") else "XYZ"
    me = bpy.data.meshes.new(ch.mesh)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.4)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(ch.mesh, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (0, 0, 1.2)
    groups = {g: ob.vertex_groups.new(name=g) for g in ("hips", "spine", "ft_jiggle_belly")}
    for v in me.vertices:
        groups["hips" if v.co.z < 0 else "spine"].add([v.index], 0.75, "REPLACE")
        groups["ft_jiggle_belly"].add([v.index], 0.25, "REPLACE")
    ob.modifiers.new("Armature", "ARMATURE").object = rig
    ob["follow_through"] = {"route": "jiggle_bones", "jiggle": {"regions": [{"name": "belly", "max_offset_m": 0.06}]}}
    me.materials.append(bpy.data.materials.new(f"{ch.name}_skin"))
    bpy.context.view_layer.update()
    return rig, ob


def _edit_bone(rig, name, **what):
    import bpy
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    b = rig.data.edit_bones[name]
    for k, v in what.items():
        if k == "parent":
            v = rig.data.edit_bones[v]
        setattr(b, k, v)
    bpy.ops.object.mode_set(mode="OBJECT")


def _output_flips(runner, ch, done, judged_drop):
    """What the moves stage reads of the flesh stage's output (`inputs.outputs(ch, "flesh")`), and moves' view hash
    (`runner.view_hash`), judged on a small file (`_output_scene`, rebuilt for each flip) with one thing flipped at
    a time. `judged_drop` leaves output labels out of every digest the flips are judged on
    (`PIPELINE_HASHES_DROP=flesh:output:<label>`): the fixture must then fail."""
    import bpy
    from character_pipeline import inputs, plugins, quality, stages
    q = quality.check(ch.build.quality)
    names = [s[0] for s in stages.STAGES if s[5](ch)]
    _name, needs, sections = next(s for s in stages.STAGES if s[0] == "moves")[:3]
    needs = [n for n in needs if n in names]
    versions = plugins.stage_versions(ch, "moves")

    def view(out, drop=()):
        return runner.view_hash(ch, "moves", needs, sections, done, {"flesh": out}, q, versions,
                                inputs.stage_inputs(ch, "moves"), drop=drop)

    def second_mesh(rig, ob):
        other = bpy.data.objects.new(f"{ch.name}_extra", ob.data.copy())
        bpy.context.scene.collection.objects.link(other)
        other.modifiers.new("Armature", "ARMATURE").object = rig

    def constraint(rig, ob):
        c = rig.pose.bones["spine"].constraints.new("COPY_ROTATION")
        c.target = rig
        c.subtarget = "hips"

    def weight(rig, ob):
        ob.vertex_groups["spine"].add([len(ob.data.vertices) - 1], 0.5, "REPLACE")

    def vertex(rig, ob):
        ob.data.vertices[0].co.x += 0.001

    def spec_edit(key, value):
        def edit(rig, ob):
            s = ob["follow_through"].to_dict()
            if key == "route":
                s["route"] = value
            else:
                s["jiggle"]["regions"][0][key] = value
            ob["follow_through"] = s
        return edit

    def action(rig, ob):
        rig.animation_data_create().action = bpy.data.actions.new(f"{ch.name}_Idle")

    def pose(rig, ob):
        rig.pose.bones["spine"].rotation_euler.x = 0.3

    mesh_labels = [label for label in inputs.OUTPUT_LABELS if label.startswith("mesh:")]
    # (title, edit, the labels it must move - None: it must move nothing)
    flips = [
        ("a bone's tail", lambda rig, ob: _edit_bone(rig, "spine", tail=(0, 0.01, 1.5)), ["rig:bones"]),
        ("a bone's parent", lambda rig, ob: _edit_bone(rig, "ft_jiggle_belly", parent="spine"), ["rig:bones"]),
        ("a bone's follow-through tag", lambda rig, ob: rig.data.bones["spine"].__setitem__("ft_role", "strand"),
         ["rig:bones", "rig:pose"]),
        ("a pose constraint", constraint, ["rig:pose"]),
        ("the rotation mode of a jiggle bone",
         lambda rig, ob: setattr(rig.pose.bones["ft_jiggle_belly"], "rotation_mode", "XYZ"), ["rig:pose"]),
        ("the rig's place", lambda rig, ob: setattr(rig, "location", (0.0, 0.0, 0.01)), ["rig:object"]),
        ("a second mesh bound to the rig", second_mesh, ["meshes:bound"] + mesh_labels),
        ("a vertex", vertex, ["mesh:geometry"]),
        ("a weight", weight, ["mesh:weights"]),
        ("an empty vertex group", lambda rig, ob: ob.vertex_groups.new(name="extra"), ["mesh:groups"]),
        ("a modifier", lambda rig, ob: ob.modifiers.new("Sub", "SUBSURF"), ["mesh:modifiers"]),
        ("the follow-through route", spec_edit("route", "soft_body"), ["mesh:marks"]),
        ("a wardrobe mark", lambda rig, ob: ob.__setitem__("wardrobe_cut", 1), ["mesh:marks"]),
        ("a material", lambda rig, ob: ob.data.materials.append(bpy.data.materials.new("extra")), ["mesh:materials"]),
        ("a shape key", lambda rig, ob: ob.shape_key_add(name="Basis"), ["mesh:shape_keys"]),
        # what flesh writes that moves never reads, and what moves writes itself
        ("unrelated: a jiggle swing limit", spec_edit("max_offset_m", 0.05), None),
        ("unrelated: the rotation mode of a body bone (moves sets it)",
         lambda rig, ob: setattr(rig.pose.bones["spine"], "rotation_mode", "QUATERNION"), None),
        ("unrelated: a pose (the stages rest the rig first)", pose, None),
        ("unrelated: an action on the rig", action, None),
    ]
    out = {}
    for title, edit, labels in flips:
        _output_scene(ch)
        before = inputs.outputs(ch, "flesh", drop=judged_drop)
        rig, ob = _output_scene(ch)
        edit(rig, ob)
        bpy.context.view_layer.update()
        after = inputs.outputs(ch, "flesh", drop=judged_drop)
        moved = inputs.output_changed(before, after)
        row = {"moved": moved, "view_moved": view(before) != view(after), "expect": labels}
        if labels is None:
            row["ok"] = not moved and not row["view_moved"]
        else:
            row["ok"] = sorted(moved) == sorted(labels) and row["view_moved"]
            # control: with those labels left out of the digest, moves' view no longer sees the flip
            row["control_unseen"] = view(before, drop=labels) == view(after, drop=labels)
        out[title] = row
    # a flesh record with no output digested (built before 0.10.0) gives moves no view: moves never skips on it
    out["no output recorded"] = {"ok": runner.view_hash(ch, "moves", needs, sections, done, {}, q, versions, {}) is None}
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    return out


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
