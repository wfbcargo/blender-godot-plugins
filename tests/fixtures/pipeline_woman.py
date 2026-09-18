"""A character built from a spec alone: character-pipeline end to end (improvements 01).

The spec is `mpfb_woman_curvy`'s woman given flesh and Belle's two garment presets. `runner.build`
takes it through body, bake, flesh, moves, garments and export, and saves the .blend. Then:

- a second `build` in the same session skips every stage as unchanged;
- a garment bound to the rig makes the moves stage refuse, naming the order;
- a spec that still names the removed `export.height` is rejected;
- a second Blender opens the saved .blend and runs the export stage alone (`from_stage="export"`,
  forced): the manifest it writes must equal the first one - the fresh-session resume 01 asks for;
- last, a `[flesh]` edit on the dressed file restarts the whole build from body (flesh refuses while
  garments are bound), and with flesh taken out of `RESTARTS_FROM_BODY` (the control) it refuses.

The golden holds the stage statuses, what each stage reports that a person would check (the body's
stature, moves passed, flesh regions, garments passed and what they hide), the flesh stage's found
and missed types, a type it cannot find failing the stage unless `[flesh] may_miss` lists it (judged on
this body's own measure with `bloater_belly` added, which it has no mass for), the manifest's `flesh`
block, the manifest as
`moves_manifest` holds it, and the Idle clip's standing height, which `height_m.stand` must equal.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS")
# the pipeline finds its plugins through these variables (else the installed copies); point them at
# the checkout under test, for this process and the second Blender alike
for _var in ("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS"):
    os.environ[_var] = H.scripts(_var)

SPEC = '''
[character]
id = "fixwoman"
name = "FixWoman"

[body]
sex = "female"
age = 28
stature = 1.70
build = "curvy"
seed = 7
style = "realistic"
firmness = 0.4
skin = [0.62, 0.45, 0.36]

[moves]
gaits = { Walk = 0.2, Run = 2.0 }
style = "adult"
stance_width = 1.0

[flesh]
types = ["breast", "butt"]

[[outfit]]
preset = "sports_top"

[[outfit]]
preset = "shorts_mid_thigh"

[export]
dir = "assets/fixwoman"
res_dir = "res://assets/fixwoman"
blend = "fixwoman.blend"
'''


def _statuses(report):
    return {k: v["status"] for k, v in report.items() if isinstance(v, dict) and "status" in v}


def _idle_stand(ch):
    from rig_analysis import stored
    return (stored.load(ch.rig, roles=["Idle"]).get("Idle") or {}).get("standing_height_m")


def _second_blender(blend, spec_path, out_json):
    code = (
        "import sys, json; sys.path[:0] = %r\n"
        "from character_pipeline import runner\n"
        "r = runner.build(%r, from_stage='export', force=True, save=False, log=lambda m: None)\n"
        "json.dump({k: v['status'] for k, v in r.items() if isinstance(v, dict) and 'status' in v}, open(%r, 'w'))\n"
    ) % ([H.scripts(v) for v in ("CP_SCRIPTS",)], spec_path, out_json)
    import bpy
    proc = subprocess.run([bpy.app.binary_path, "-b", blend, "--factory-startup", "--python-exit-code", "1",
                           "--python-expr", code], capture_output=True, text=True, env=dict(os.environ))
    return proc.returncode, "\n".join((proc.stdout or "").splitlines()[-8:])


def _skin(ch, glb):
    """humanform's realistic skin through the pipeline: the glb's skin material carries base colour, roughness
    and normal maps and the lookdev extras Godot needs; the baked albedo's mean is the spec's tone; lips and
    areolae sample darker and redder than the body."""
    import struct
    import bpy
    import numpy as np
    from humanform import skin
    with open(glb, "rb") as fh:
        b = fh.read()
    g = json.loads(b[20:20 + struct.unpack_from("<I", b, 12)[0]])
    m = next(x for x in g["materials"] if x["name"] == f"{ch.name}_skin")
    pbr = m.get("pbrMetallicRoughness", {})
    look = (m.get("extras") or {}).get("lookdev", {})
    mat = bpy.data.materials[f"{ch.name}_skin"]
    rep = mat["humanform_skin"].to_dict()
    ob = bpy.data.objects[ch.mesh]
    img = bpy.data.images[f"{ch.name}_skin_base_color"]
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    me = ob.data
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers["UVMap"].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    lv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)

    def tone(idx):
        sel = np.isin(lv, idx)
        xy = np.clip((uv[sel] * [w, h]).astype(int), 0, [w - 1, h - 1])
        return [round(float(v), 2) for v in px[xy[:, 1], xy[:, 0], :3].mean(axis=0)]
    n = min(len(me.vertices), 13380)
    return {"textures": {"base_color": "baseColorTexture" in pbr, "roughness": "metallicRoughnessTexture" in pbr,
                         "normal": "normalTexture" in m},
            "uv_sets": sorted({k for mm in g["meshes"] for p in mm["primitives"] for k in p["attributes"]
                               if k.startswith("TEXCOORD")}),
            "lookdev_preset": look.get("preset"), "godot_sss": (look.get("godot") or {}).get("subsurf_scatter_enabled"),
            "detail": (look.get("detail") or {}).get("normal"),
            "stage": rep.get("stage"), "size": rep.get("size"), "tone_ok": rep.get("tone_ok"),
            "tone_target": rep.get("tone_target"), "tone_baked": [round(v, 2) for v in rep.get("baked", [])],
            "body_tone": tone(np.arange(n)),
            "lips_tone": tone(skin._mpfb_group_indices(ob, "lips", n)),
            "nipple_tone": tone(skin._mpfb_group_indices(ob, "nipple", n))}


def build():
    import bpy
    H.clear_scene()
    from character_pipeline import runner, spec, stages

    root = os.path.join(H.out_dir(), "pipeline_woman")
    os.makedirs(os.path.join(root, "characters"), exist_ok=True)
    spec_path = os.path.join(root, "characters", "fixwoman.toml")
    with open(spec_path, "w", encoding="utf-8") as fh:
        fh.write(SPEC)
    ch = spec.load(spec_path)
    ch.export.blend = os.path.join(root, "fixwoman.blend")

    first = runner.build(ch, save=True, log=lambda m: None)
    again = runner.build(ch, save=False, log=lambda m: None)

    # moves after garments: refused, with the order
    refused = None
    try:
        runner.build(ch, from_stage="moves", to_stage="moves", force=True, save=False, log=lambda m: None)
    except stages.StageRefused as exc:
        refused = str(exc)

    # export.height was removed (one convention: the Idle clip's standing height)
    height_field = None
    try:
        import tomllib
        spec.parse(tomllib.loads(SPEC.replace("[export]", '[export]\nheight = "mesh"')))
    except spec.SpecError as exc:
        height_field = str(exc)

    # [flesh] may_miss may only name a type the spec asks for
    may_miss_stray = None
    try:
        import tomllib
        spec.parse(tomllib.loads(SPEC.replace('types = ["breast", "butt"]',
                                              'types = ["breast", "butt"]\nmay_miss = ["belly"]')))
    except spec.SpecError as exc:
        may_miss_stray = str(exc)

    # a type the spec asks for that the body has no mass for: the stage's judgment on this body's own
    # measure, failing without may_miss and passing with it. find_regions only reads the body.
    import dataclasses
    from follow_through import flesh as ft_flesh
    asked = ["breast", "butt", "bloater_belly"]
    stages._rest(ch)
    looked = ft_flesh.find_regions(ch.mesh, ch.rig, types=asked)
    strict = dataclasses.replace(ch, flesh=dataclasses.replace(ch.flesh, types=asked))
    lenient = dataclasses.replace(ch, flesh=dataclasses.replace(ch.flesh, types=asked, may_miss=["bloater_belly"]))
    miss = {"missed": [{k: m[k] for k in ("type", "reason", "seeds", "min_size", "zone_vertices", "claimed")}
                       for m in looked["missed"]]}
    try:
        stages.judge_flesh(strict, looked)
        miss["without_may_miss"] = "passed"
    except RuntimeError as exc:
        miss["without_may_miss"] = "failed: names bloater_belly %s, gives numbers %s" % (
            "bloater_belly" in str(exc), " m out (a seed needs " in str(exc))
    miss["with_may_miss"] = stages.judge_flesh(lenient, looked)["found"]

    manifest_path = first["export"]["report"]["moves"]
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    # the `build` block is where this build's minutes went (runner.build rewrites it after every build that
    # exported), so the second Blender's export-only run writes its own: the rest must be equal
    before = json.dumps(dict(manifest, build=None), sort_keys=True)

    statuses_path = os.path.join(root, "second_blender.json")
    code, tail = _second_blender(ch.export.blend, spec_path, statuses_path)
    fresh = {"exit": code}
    if code == 0 and os.path.isfile(statuses_path):
        with open(statuses_path, encoding="utf-8") as fh:
            fresh["statuses"] = json.load(fh)
        with open(manifest_path, encoding="utf-8") as fh:
            again_manifest = json.load(fh)
            fresh["manifest_equal"] = json.dumps(dict(again_manifest, build=None), sort_keys=True) == before
            fresh["build_block"] = {"quality": again_manifest.get("build", {}).get("quality"),
                                    "stages_timed": sorted(again_manifest.get("build", {}).get("stage_seconds", {}))}
    else:
        fresh["tail"] = tail

    moves = first["moves"]["report"]
    garments = first["garments"]["report"]["garments"]
    flesh = first["flesh"]["report"]
    result = {
        "stages": _statuses(first),
        "rerun": _statuses(again),
        "refused": refused,
        "height_field": height_field,
        "body_stature": first["body"]["report"].get("stature"),
        "idle_standing_height_m": _idle_stand(ch),
        "moves": {role: {"passed": r["passed"], "failures": r["failures"], "drop_m": r.get("drop_m")}
                  for role, r in moves.items()},
        "flesh_regions": sorted("%s %s" % (g["name"], g["type"])
                                for g in bpy.data.objects[ch.mesh]["follow_through"]["jiggle"]["regions"]),
        "flesh_limits_m": flesh.get("limits_m"),
        "flesh_found": flesh.get("found"),
        "flesh_missed": [{k: m.get(k) for k in ("type", "reason")} for m in flesh.get("missed") or []],
        "flesh_miss_judged": miss,
        "may_miss_stray": may_miss_stray,
        "manifest_flesh": H.stable({"types": manifest.get("flesh", {}).get("types"),
                                    "missed": manifest.get("flesh", {}).get("missed"),
                                    "regions": [{k: r.get(k) for k in ("name", "type", "bone", "parent", "material",
                                                                       "frequency_hz", "damping_ratio", "peak_m",
                                                                       "max_offset_m")}
                                                for r in manifest.get("flesh", {}).get("regions", [])]}),
        "garments": {name: {"passed": g.get("passed"), "verts": g.get("verts"),
                            "jiggle_groups": g.get("jiggle_groups")} for name, g in garments.items()},
        "manifest": H.moves_manifest({"manifest": manifest, "problems": first["export"]["report"].get("problems")}),
        "fresh_session": fresh,
        "review": H.review_sheet(first["review"]["report"]),
        "review_meshes": first["review"]["report"]["meshes"],
        "skin": _skin(ch, first["export"]["report"]["glb"]),
    }
    # last, as it rebuilds the body: a [flesh] edit on this dressed file (what a resumed build of Belle meets)
    result["dressed_flesh_edit"] = _dressed_flesh_edit(ch)
    return result


def _dressed_flesh_edit(ch):
    """A whole build whose [flesh] changed on a file with the garments bound restarts from body (flesh refuses
    while garments are bound). Control first, while the file is still dressed: without flesh in
    `RESTARTS_FROM_BODY` the same build must refuse. to_stage=flesh and save=False, so nothing this fixture
    exported or saved is rewritten."""
    import dataclasses
    from character_pipeline import runner, stages
    edited = dataclasses.replace(ch, flesh=dataclasses.replace(ch.flesh, limit_share={"butt": 0.85}))
    out = {"bound_before": stages.garments_bound(edited)}
    kept = stages.RESTARTS_FROM_BODY.pop("flesh")
    try:
        runner.build(edited, to_stage="flesh", save=False, log=lambda m: None)
        out["control"] = "built (it must refuse)"
    except stages.StageRefused as exc:
        out["control"] = "refused: names garments %s, names fresh=1 %s" % ("garments are bound" in str(exc),
                                                                           "fresh=1" in str(exc))
    finally:
        stages.RESTARTS_FROM_BODY["flesh"] = kept
    try:
        r = runner.build(edited, to_stage="flesh", save=False, log=lambda m: None)
        out["statuses"] = _statuses(r)
        out["restarted"] = r["build"].get("restarted")
    except stages.StageRefused as exc:
        out["refused"] = str(exc)
    out["bound_after"] = stages.garments_bound(edited)
    return out


H.run("pipeline_woman", build)
