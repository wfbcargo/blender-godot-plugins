"""humanform's realistic skin, from an MPFB human to the glb, and what happens when it is NOT baked.

One seeded brief with a deep skin tone (the darks are where an sRGB/linear slip shows):

1. `pipeline.make` -> look.skin on the MPFB human: the material is FLAT (tone as an unlinked Base Color,
   subsurface, the lookdev extras) and the region marks are written as non-colour attributes.
2. `bake_for_game` and a direct glTF export, no bake - the path mpfb_woman_curvy and any consumer without
   character-pipeline's bake stage takes: the skin must carry baseColorFactor = the brief's tone (linear), and
   no COLOR_n (a procedural material or a colour attribute here once made the body white in Godot).
3. The bake with lookdev made unavailable: look.skin must fall back to the same flat material, not leave the
   procedural one the exporter cannot read.
4. The real bake (512 px, draft is 1024): base colour, roughness and normal maps in the glb, the albedo's covered
   mean held to the brief's tone, lips and areolae darker and redder than the body, palms and soles paler, and
   the glb's embedded map the same pixels as the baked one.
"""
import json
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "HF_SCRIPTS", "LD_SCRIPTS")

NAME = "FixSkin"
TONE = (0.45, 0.31, 0.23)
BRIEF = dict(name=NAME, sex="male", age=35, stature=1.76, build="average", seed=23, style="realistic",
             skin=TONE)
SIZE = 512


def _glb(path):
    with open(path, "rb") as fh:
        b = fh.read()
    n = struct.unpack_from("<I", b, 12)[0]
    return json.loads(b[20:20 + n]), b, 20 + n + 8


def _export(objs, path):
    import bpy
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_animations=False,
                              export_extras=True)
    return _glb(path)


def _skin_entry(g, name):
    m = next(x for x in g["materials"] if x["name"] == name)
    pbr = m.get("pbrMetallicRoughness", {})
    look = (m.get("extras") or {}).get("lookdev", {})
    return m, pbr, look


def _r(v, p=3):
    return [round(float(x), p) for x in v]


def build():
    import bpy
    import numpy as np
    H.clear_scene()
    import rig_analysis  # noqa: F401
    from rig_analysis import export as ra_export
    import humanform  # noqa: F401
    from humanform import look, pipeline, sheet, skin

    lin = look.srgb_to_linear(TONE)[:3]
    pipeline.make(sheet.new(**BRIEF), use_library=False)
    human = bpy.data.objects[NAME]
    mat = bpy.data.materials[f"{NAME}_skin"]
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    rep = mat["humanform_skin"].to_dict()
    me = human.data
    marked = {"stage": rep.get("stage"),
              "base_color_linked": bsdf.inputs["Base Color"].is_linked,
              "base_color": _r(bsdf.inputs["Base Color"].default_value[:3], 4),
              "subsurface_weight": round(float(bsdf.inputs["Subsurface Weight"].default_value), 3),
              "regions": rep.get("marked"),
              "attributes": {a: (me.attributes[a].data_type, me.attributes[a].domain)
                             for a in (skin.TINT, skin.OIL, skin.REGION) if a in me.attributes},
              "colour_attributes": sorted(a.name for a in me.color_attributes)}

    rig = bpy.data.objects[NAME + "_rig"]
    body = NAME + "_body"
    b = ra_export.bake_for_game(NAME, rig.name, name=body)
    if "error" in b:
        raise RuntimeError("bake_for_game: " + b["error"])
    ob = bpy.data.objects[body]
    tmp = tempfile.mkdtemp(prefix="skin_detail_")

    # 2. unbaked, exported as it is
    g, _, _ = _export([ob, rig], os.path.join(tmp, "unbaked.glb"))
    m, pbr, lk = _skin_entry(g, mat.name)
    attrs = sorted({k for mm in g["meshes"] for p in mm["primitives"] for k in p["attributes"]})
    unbaked = {"baseColorFactor": _r(pbr.get("baseColorFactor", [1, 1, 1, 1])[:3], 4),
               "factor_is_tone": bool(np.allclose(pbr.get("baseColorFactor", [1, 1, 1])[:3], lin, atol=1e-3)),
               "baseColorTexture": "baseColorTexture" in pbr,
               "colour_sets": [a for a in attrs if a.startswith("COLOR_")],
               "lookdev_preset": lk.get("preset"), "godot_sss": (lk.get("godot") or {}).get("subsurf_scatter_enabled")}

    # 3. the bake cannot run: flat, not procedural
    real = skin._lookdev
    skin._lookdev = lambda: None
    try:
        look.skin(ob, TONE, name=mat.name, size=SIZE)
    finally:
        skin._lookdev = real
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    rep = mat["humanform_skin"].to_dict()
    fallback = {"stage": rep.get("stage"), "error": bool(rep.get("error")),
                "base_color_linked": bsdf.inputs["Base Color"].is_linked,
                "base_color_is_tone": bool(np.allclose(bsdf.inputs["Base Color"].default_value[:3], lin, atol=1e-4)),
                "marks_kept": skin.TINT in ob.data.attributes}

    # 4. the real bake
    look.skin(ob, TONE, name=mat.name, size=SIZE)
    rep = mat["humanform_skin"].to_dict()
    g, blob, binoff = _export([ob, rig], os.path.join(tmp, "baked.glb"))
    m, pbr, lk = _skin_entry(g, mat.name)
    img = bpy.data.images[f"{mat.name}_base_color"]
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)[..., :3]
    # the glb's embedded PNG, decoded
    gi = g["images"][g["textures"][pbr["baseColorTexture"]["index"]]["source"]]
    bv = g["bufferViews"][gi["bufferView"]]
    png = os.path.join(tmp, "glb_base_color.png")
    with open(png, "wb") as fh:
        fh.write(blob[binoff + bv.get("byteOffset", 0): binoff + bv.get("byteOffset", 0) + bv["byteLength"]])
    gim = bpy.data.images.load(png)
    gpx = np.empty(w * h * 4, np.float32)
    gim.pixels.foreach_get(gpx)
    gpx = gpx.reshape(h, w, 4)[..., :3]
    me = ob.data
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers["UVMap"].data.foreach_get("uv", uv)
    xy = np.clip((np.mod(uv.reshape(-1, 2), 1.0) * [w, h]).astype(int), 0, [w - 1, h - 1])
    regions = rep.get("regions", {})
    luma = {k: 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2] for k, v in regions.items()}
    redness = {k: v[0] / max(v[1], 1e-3) for k, v in regions.items()}
    attrs = sorted({k for mm in g["meshes"] for p in mm["primitives"] for k in p["attributes"]})
    baked = {"stage": rep.get("stage"), "size": rep.get("size"), "tone_ok": rep.get("tone_ok"),
             "tone_target": _r(rep.get("tone_target", []), 3), "tone_baked": _r(rep.get("baked", []), 2),
             "textures": {"base_color": "baseColorTexture" in pbr, "roughness": "metallicRoughnessTexture" in pbr,
                          "normal": "normalTexture" in m},
             "baseColorFactor": _r(pbr.get("baseColorFactor", [1, 1, 1, 1])[:3], 3),
             "uv_sets": [a for a in attrs if a.startswith("TEXCOORD")],
             "colour_sets": [a for a in attrs if a.startswith("COLOR_")],
             "lookdev_preset": lk.get("preset"), "godot_sss": (lk.get("godot") or {}).get("subsurf_scatter_enabled"),
             "godot_transmittance_depth": (lk.get("godot") or {}).get("subsurf_scatter_transmittance_depth"),
             "detail": (lk.get("detail") or {}).get("normal"),
             "glb_map_is_baked_map": bool(np.abs(gpx[xy[:, 1], xy[:, 0]] - px[xy[:, 1], xy[:, 0]]).max() < 1.5 / 255),
             "region_tones": {k: _r(v, 2) for k, v in sorted(regions.items())},
             "lips_redder_darker": bool(redness.get("lips", 0) > redness["skin"] and luma.get("lips", 9) < luma["skin"]),
             "nipple_darker": bool(luma.get("nipple", 9) < luma["skin"]),
             "palm_paler": bool(luma.get("palm", 0) > luma["skin"]),
             "sole_paler": bool(luma.get("sole", 0) > luma["skin"]),
             "genital_darker": bool(luma.get("genital", 9) < luma["skin"])}
    return {"marked": marked, "unbaked_export": unbaked, "no_lookdev": fallback, "baked": baked}


H.run("skin_detail", build)
