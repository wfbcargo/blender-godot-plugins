"""A character built from a spec alone: character-pipeline end to end (improvements 01).

The spec is `mpfb_woman_curvy`'s woman given flesh and Belle's two garment presets. `runner.build`
takes it through body, bake, flesh, moves, garments and export, and saves the .blend. Then:

- a second `build` in the same session skips every stage as unchanged;
- a garment bound to the rig makes the moves stage refuse, naming the order;
- a spec that still names the removed `export.height` is rejected;
- a second Blender opens the saved .blend and runs the export stage alone (`from_stage="export"`,
  forced): the manifest it writes must equal the first one - the fresh-session resume 01 asks for;
- last, a `[flesh]` edit on the dressed file takes the garments off and reruns flesh alone, and moves is skipped
  because what it reads of flesh came out the same; without the undress (the control) it restarts from body, and
  without the undress and with flesh taken out of `RESTARTS_FROM_BODY` it refuses.

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

    # where the breast bones land (follow-through check_placement). This body's chin stands out of the neck's
    # lean envelope inside the breast zone: before face vertices were kept out of regions its breast bones went
    # on it (about 1.45 m, most of their weight on the face, 0.05 at the bust). The control puts that back and must
    # fail the check, and the stage's judgment must fail on it.
    hangs = ("pivot_rise_m", "weight_at_apex", "weight_10cm_above", "weight_on_thigh")

    def placed(found, kinds=("breast",)):
        p = ft_flesh.check_placement(found["tissue"], [r for r in found["regions"] if r["type"] in kinds],
                                     found["coords"])
        return {"ok": p["ok"], "chin_z": p["chin_z"],
                "regions": {r["name"]: {"tail_z": r["tail_z"], "head_share": r["head_share"], "ok": r["ok"],
                                        **{k: r[k] for k in hangs if k in r}}
                            for r in p["regions"]}}
    placement = placed(looked)
    os.environ["FT_FLESH_LEGACY_PLACEMENT"] = "1"
    try:
        legacy = ft_flesh.find_regions(ch.mesh, ch.rig, types=["breast"])
        legacy["placement"] = ft_flesh.check_placement(legacy["tissue"], legacy["regions"], legacy["coords"])
    finally:
        os.environ.pop("FT_FLESH_LEGACY_PLACEMENT", None)
    placement["control_legacy"] = placed(legacy)
    legacy_ch = dataclasses.replace(ch, flesh=dataclasses.replace(ch.flesh, types=["breast"]))
    try:
        stages.judge_flesh(legacy_ch, legacy)
        placement["control_legacy"]["judged"] = "passed (it must fail)"
    except RuntimeError as exc:
        placement["control_legacy"]["judged"] = "failed: MISPLACED names the chin %s, the face %s" % (
            "above the chin" in str(exc), "head-skinned" in str(exc))

    # breasts and buttocks hang from above (follow-through 0.8.0): pivot over the apex, weight graded from the
    # attachment and off the thigh. The control puts the old bone (tail inside the surface, head level with it)
    # and the plateau weights back and must fail the check on both types.
    placement["hanging"] = placed(looked, ("breast", "butt"))
    os.environ["FT_FLESH_LEGACY_ATTACHMENT"] = "1"
    try:
        plateau = ft_flesh.find_regions(ch.mesh, ch.rig, types=["breast", "butt"])
    finally:
        os.environ.pop("FT_FLESH_LEGACY_ATTACHMENT", None)
    placement["control_attachment"] = placed(plateau, ("breast", "butt"))

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
        "flesh_placement": placement,
        "flesh_stage_placement": flesh.get("placement"),
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
        "close": _close(ch, first["review"]["report"]),
        "skin": _skin(ch, first["export"]["report"]["glb"]),
    }
    # last, as it rebuilds the body: a [flesh] edit on this dressed file (what a resumed build of Belle meets)
    result["dressed_flesh_edit"] = _dressed_flesh_edit(ch)
    return result


def _close(ch, review):
    """The review stage's close-up look set (rig-anything `closeups`, 06 rank 1): at final every view and, since
    she wears a sports top, the 0.42 m under-bust view, each tile on disk and passing its checks (coverage and
    how far the view's own bones sit from the tile's centre are kept to 2 places: the pose is exact, the pixels
    are EEVEE's; `subject_margin` is how far the worst of the view's points - each knuckle and fingertip, both
    eyes, each foot's heel, ankle and toe - sits inside the tile's edge). Then the controls, which must fail: a
    palm camera aimed from the other hand's bone (`off_centre`), a set of a speck under the floor instead of the
    body (`empty` on every tile), and the palm camera moved up the arm - 6 cm (the Step 0 critic's case, which
    passed with the fingertips cut off while only the centroid was checked) and 3 cm, where the centroid is
    still central and only the every-point check can see the fingertips at the edge (`cut`). Then the draft
    set, face and the left hand, and last `[review] close = false`, which must take the set away (`_close_off`).
    The set on disk is rewritten by these, so it is read first."""
    import bpy
    from rig_analysis import closeups
    from character_pipeline import quality, stages
    c = review.get("close") or {}
    d = stages.close_dir(ch)
    out = {"pngs": sorted(f for f in os.listdir(d) if f.endswith(".png")) if os.path.isdir(d) else [],
           "close_json": os.path.isfile(os.path.join(d, "close.json")),
           "gdignore": os.path.isfile(os.path.join(d, ".gdignore")),
           "count": c.get("count"), "pose": c.get("pose"), "views": c.get("views"), "failed": c.get("failed"),
           "wears_top": stages.wears_top(ch),
           "tiles": {v: {"ok": t["ok"], "coverage": round(t["coverage"], 2),
                         "subject_off": None if t["subject_off"] is None else round(t["subject_off"], 2),
                         "subject_margin": None if t.get("subject_margin") is None else round(t["subject_margin"], 2),
                         "on_body": t["on_body"], "distance_m": t["distance_m"]}
                     for v, t in (c.get("tiles") or {}).items()}}
    meshes = review["meshes"]
    try:
        stages.run_close(ch, {"quality": "final"}, meshes, aim_override={"hand_palm.L": "hand.R"})
        out["control_wrong_bone"] = "passed (it must fail)"
    except RuntimeError as exc:
        import re
        # each failed tile is "<view>: <reason> (...)[; <reason> (...)]", quoted either way by the list's repr
        out["control_wrong_bone"] = {"raised": sorted(set(re.findall(r"""["']([\w.]+): (\w+)""", str(exc))))}
    me = bpy.data.meshes.new("close_speck")
    me.from_pydata([(0, 0, -5.0), (0.001, 0, -5.0), (0, 0.001, -5.0)], [], [(0, 1, 2)])
    speck = bpy.data.objects.new("close_speck", me)
    bpy.context.scene.collection.objects.link(speck)
    try:
        r = closeups.look_set([speck.name], ch.rig, os.path.join(os.path.dirname(d), "close_control"),
                              views=("face", "hand_palm.L", "feet"), action=stages.close_pose(ch))
        out["control_empty"] = {v: [f.split(" ")[0] for f in t["fail"]] for v, t in r["tiles"].items()}
    finally:
        bpy.data.objects.remove(speck, do_unlink=True)
        bpy.data.meshes.remove(me)
    for cm in (6, 3):
        r = closeups.look_set(meshes, ch.rig, os.path.join(os.path.dirname(d), "close_control"),
                              views=("hand_palm.L",), action=stages.close_pose(ch),
                              aim_override={"hand_palm.L": (0.0, 0.0, cm / 100.0)})
        t = r["tiles"]["hand_palm.L"]
        out[f"control_palm_up_{cm}cm"] = {"fail": [f.split(" ")[0] for f in t["fail"]],
                                          "subject_off": round(t["subject_off"], 2),
                                          "subject_margin": round(t["subject_margin"], 2)}
    draft = stages.run_close(ch, {"quality": "draft"}, meshes)
    out["draft"] = {"views": draft["views"], "failed": draft["failed"],
                    "table": {q: quality.settings(q, "close") for q in quality.QUALITIES}}
    out["close_off"] = _close_off(ch)
    return out


def _close_off(ch):
    """`[review] close = false` on a file whose close/ folder an earlier review wrote: the review stage must
    remove it (and report the folder it removed) and render no set. Control: with `stages.clear_close` made a
    no-op, the same review leaves the stale folder, and the check must see it."""
    import dataclasses
    from character_pipeline import stages
    off = dataclasses.replace(ch, review=dataclasses.replace(ch.review, close=False))
    d = stages.close_dir(ch)
    out = {"had_folder": os.path.isdir(d)}
    real = stages.clear_close
    stages.clear_close = lambda _ch: None
    try:
        r = stages.run_review(off, {"quality": "final"})
    finally:
        stages.clear_close = real
    out["control_no_clear"] = {"folder_left": os.path.isdir(d), "close_in_report": "close" in r}
    r = stages.run_review(off, {"quality": "final"})
    out["folder_left"] = os.path.isdir(d)
    out["close_in_report"] = "close" in r
    out["reported_removed"] = bool(r.get("close_removed"))
    out["ok"] = (not out["folder_left"]) and out["reported_removed"] and not out["close_in_report"]
    out["control_seen"] = out["control_no_clear"]["folder_left"]
    return out


class _Stop(Exception):
    pass


def _dressed_flesh_edit(ch):
    """A whole build whose [flesh] changed on a file with the garments bound takes the garments off
    (`stages.undress`) and reruns flesh on the body, not the whole build from body; flesh is restored from the
    unfleshed copy, so what moves reads of it comes out the same and moves is skipped. Controls first, while the
    file is still dressed: without the undress (`runner.UNDRESS_FOR_FLESH = False`) the build restarts from body
    (stopped at the restart, before it rebuilds anything), and without the undress and without flesh in
    `RESTARTS_FROM_BODY` it refuses. to_stage=moves and save=False, so nothing this fixture exported or saved is
    rewritten."""
    import dataclasses
    from character_pipeline import runner, stages
    edited = dataclasses.replace(ch, flesh=dataclasses.replace(ch.flesh, limit_share={"butt": 0.85}))
    out = {"bound_before": stages.garments_bound(edited)}
    kept = stages.RESTARTS_FROM_BODY.pop("flesh")
    runner.UNDRESS_FOR_FLESH = False
    try:
        runner.build(edited, to_stage="flesh", save=False, log=lambda m: None)
        out["control"] = "built (it must refuse)"
    except stages.StageRefused as exc:
        out["control"] = "refused: names garments %s, names fresh=1 %s" % ("garments are bound" in str(exc),
                                                                           "fresh=1" in str(exc))
    finally:
        stages.RESTARTS_FROM_BODY["flesh"] = kept

    def stop_at_restart(message):
        if "rebuilding from body" in message:
            raise _Stop(message.split("] ", 1)[-1])
    try:
        runner.build(edited, to_stage="flesh", save=False, log=stop_at_restart)
        out["control_restart"] = "no restart (without the undress it must restart from body)"
    except _Stop as exc:
        out["control_restart"] = str(exc)
    finally:
        runner.UNDRESS_FOR_FLESH = True
    try:
        r = runner.build(edited, to_stage="moves", save=False, log=lambda m: None)
        out["statuses"] = _statuses(r)
        out["restarted"] = r["build"].get("restarted")
        flesh = (r.get("flesh") or {}).get("report") or {}
        out["undressed"] = flesh.get("undressed")
        out["unfleshed"] = flesh.get("unfleshed")
        out["moves_why"] = (r.get("moves") or {}).get("why")
    except stages.StageRefused as exc:
        out["refused"] = str(exc)
    out["bound_after"] = stages.garments_bound(edited)
    return out


H.run("pipeline_woman", build)
