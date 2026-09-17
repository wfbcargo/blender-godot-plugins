"""Bake surface detail from a high copy into a tangent-space normal map on the game mesh.

For detail that exists as geometry on one mesh and should show on another without it - muscle
definition sculpted as a shape key (humanform's `delta` parts), a scar, seams - the usual
selected-to-active normal bake, wired back into the low mesh's own materials so the glTF exporter
writes it as the material's normalTexture:

    res = detail.bake_normal_from_high("Dante_body", "Dante_high", r"C:/proj/assets/dante_tex",
                                       size=2048, material="Dante_skin")
    print(detail.summarize(res))

- `low` keeps its materials: a Normal Map node (tangent space, the mesh's UV map) is added in front of
  each target material's Principled BSDF Normal input. A material whose Normal input is already linked
  is left alone and reported.
- `material`: bake only the faces using that material. Characters join their eyes (with their own UVs,
  overlapping the skin's) into the body; baking every face would paint the eyes over the skin texels.
- The rays: `extrusion` out from the low surface, `max_ray` long. Both meshes must be in the same place
  (a rigged low mesh is baked in its rig's rest pose).
- `clean` (on): the same bake is run against an exact copy of `low`, and wherever that comes out bent the
  rays found a neighbouring surface, not detail (between fingers, the nails, eyelids, ears) - those texels
  are set flat. On an MPFB body without it, the nails and eyelid rims baked as garbage (up to 166 degrees).
- Tangent space is OpenGL (+Y), MikkTSpace from the low mesh's UVs: what glTF and Godot expect.

`stats` in the result: how much of the map is detail rather than flat (texels bent more than 1 and
5 degrees from the surface normal, and the 99.9th-percentile bend), so a bake that found nothing -
misplaced meshes, too short a ray - is visible without opening the image.
"""

from __future__ import annotations

import os
import time

import bpy
import numpy as np


def _obj(o):
    return bpy.data.objects[o] if isinstance(o, str) else o


def _principled(mat):
    if mat is None or mat.node_tree is None:
        return None
    return next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def _only_material(low, material):
    """A temporary copy of `low` holding only the faces that use `material`."""
    import bmesh
    idx = next((i for i, s in enumerate(low.material_slots) if s.material and s.material.name == material), None)
    if idx is None:
        raise ValueError(f"{low.name} has no material {material!r}")
    me = low.data.copy()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != idx], context="FACES")
    bm.to_mesh(me)
    bm.free()
    tmp = bpy.data.objects.new(low.name + "_bake_tmp", me)
    tmp.matrix_world = low.matrix_world.copy()
    for m in low.modifiers:
        if m.type == "ARMATURE":
            mod = tmp.modifiers.new(m.name, "ARMATURE")
            mod.object = m.object
    for g in low.vertex_groups:
        tmp.vertex_groups.new(name=g.name)
    for c in low.users_collection:
        c.objects.link(tmp)
    return tmp, me.materials[idx]


def _stats(img):
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    n = px.reshape(-1, 4)[:, :3] * 2.0 - 1.0
    ln = np.linalg.norm(n, axis=1)
    ok = ln > 0.5
    z = np.clip(n[ok, 2] / ln[ok], -1.0, 1.0)
    ang = np.degrees(np.arccos(z))
    return {"texels": int(ok.sum()), "over_1deg": round(float((ang > 1.0).mean()), 5),
            "over_5deg": round(float((ang > 5.0).mean()), 5),
            "p999_deg": round(float(np.percentile(ang, 99.9)), 2) if len(ang) else 0.0}


CLEAN_DEG = 1.0


def _static_twin(low):
    """A static copy of `low` as it is drawn in its rig's rest pose."""
    rigs = [m.object for m in low.modifiers if m.type == "ARMATURE" and m.object is not None]
    pose = [(r, r.data.pose_position) for r in rigs]
    try:
        for r in rigs:
            r.data.pose_position = "REST"
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(low.evaluated_get(dg), depsgraph=dg)
    finally:
        for r, p in pose:
            r.data.pose_position = p
        bpy.context.view_layer.update()
    twin = bpy.data.objects.new(low.name + "_twin", me)
    twin.matrix_world = low.matrix_world.copy()
    bpy.context.scene.collection.objects.link(twin)
    return twin


def _flatten_where_bent(img, ref, deg):
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    r = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    ref.pixels.foreach_get(r)
    a, r = a.reshape(-1, 4), r.reshape(-1, 4)
    n = r[:, :3] * 2.0 - 1.0
    z = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-6)
    bad = z < np.cos(np.radians(deg))
    a[bad, :3] = (0.5, 0.5, 1.0)
    img.pixels.foreach_set(a.ravel())
    img.update()
    return int(bad.sum())


def _bake_once(low, high, target, mats, name, size, extrusion, max_ray, margin, samples, device):
    scene = bpy.context.scene
    img = bpy.data.images.get(name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False, is_data=True)
    img.colorspace_settings.name = "Non-Color"
    img.generated_color = (0.5, 0.5, 1.0, 1.0)

    rigs = [m.object for m in target.modifiers if m.type == "ARMATURE" and m.object is not None]
    state = {"engine": scene.render.engine, "active": bpy.context.view_layer.objects.active,
             "selected": [o for o in scene.objects if o.select_get()],
             "pose": [(r, r.data.pose_position) for r in rigs]}
    added = []
    try:
        scene.render.engine = "CYCLES"
        scene.cycles.device = device
        scene.cycles.samples = samples
        scene.cycles.use_denoising = False
        for r in rigs:
            r.data.pose_position = "REST"
        for m in mats:
            tree = m.node_tree
            for nd in tree.nodes:
                nd.select = False
            node = tree.nodes.new("ShaderNodeTexImage")
            node.image = img
            node.select = True
            tree.nodes.active = node
            added.append((tree, node))
        for o in scene.objects:
            o.select_set(False)
        high.select_set(True)
        target.select_set(True)
        bpy.context.view_layer.objects.active = target
        bpy.context.view_layer.update()
        bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", normal_r="POS_X", normal_g="POS_Y",
                            normal_b="POS_Z", use_selected_to_active=True, cage_extrusion=extrusion,
                            max_ray_distance=max_ray, margin=margin, margin_type="EXTEND", use_clear=True,
                            target="IMAGE_TEXTURES")
    finally:
        for tree, node in added:
            tree.nodes.remove(node)
        scene.render.engine = state["engine"]
        for r, pos in state["pose"]:
            r.data.pose_position = pos
        for o in scene.objects:
            o.select_set(o in state["selected"])
        bpy.context.view_layer.objects.active = state["active"]

    return img


def bake_normal_from_high(low, high, out_dir, size=2048, material=None, extrusion=0.012, max_ray=0.03,
                          attach=True, name=None, samples=1, margin=None, device="CPU", strength=1.0, clean=True):
    """Bake `high`'s surface into a tangent normal map on `low`'s UVs and (with `attach`) wire it into
    `low`'s materials. Returns {"image", "file", "materials", "skipped", "stats", "seconds", "warnings"}."""
    low, high = _obj(low), _obj(high)
    if low.type != "MESH" or high.type != "MESH":
        return {"error": "low and high must both be meshes"}
    if not low.data.uv_layers:
        return {"error": f"{low.name} has no UV map"}
    os.makedirs(out_dir, exist_ok=True)
    name = name or f"{bpy.path.clean_name(low.name)}_detail_normal"
    margin = margin if margin is not None else max(4, size // 128)
    warnings = []
    t0 = time.time()
    scene = bpy.context.scene
    for ob in (low, high):
        if scene.objects.get(ob.name) is None:
            scene.collection.objects.link(ob)
    target, tmp = low, None
    mats = [s.material for s in low.material_slots if s.material]
    if material is not None:
        tmp, mat = _only_material(low, material)
        target, mats = tmp, [mat]
    if not mats:
        return {"error": f"{low.name} has no materials to bake into"}

    cleaned = 0
    try:
        img = _bake_once(low, high, target, mats, name, size, extrusion, max_ray, margin, samples, device)
        if clean:
            # The same bake against an exact copy of the low mesh: wherever that is not flat, the rays found
            # a neighbouring surface (between fingers, nails, eyelids, ears), not detail - flatten it there.
            twin = _static_twin(low)
            try:
                ref = _bake_once(low, twin, target, mats, name + "_twin", size, extrusion, max_ray, margin,
                                 samples, device)
            finally:
                me = twin.data
                bpy.data.objects.remove(twin, do_unlink=True)
                bpy.data.meshes.remove(me)
            cleaned = _flatten_where_bent(img, ref, CLEAN_DEG)
            bpy.data.images.remove(ref)
    finally:
        if tmp is not None:
            me = tmp.data
            bpy.data.objects.remove(tmp, do_unlink=True)
            bpy.data.meshes.remove(me)

    path = os.path.join(out_dir, name + ".png")
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    stats = _stats(img)
    if stats["over_1deg"] == 0.0:
        warnings.append("the map is flat: nothing of the high mesh was found within the rays "
                        f"(extrusion {extrusion} m, max_ray {max_ray} m) - are the meshes in the same place?")

    attached, skipped = [], []
    if attach:
        uv = low.data.uv_layers.active.name
        names = [material] if material else [m.name for m in mats]
        for mname in names:
            mat = bpy.data.materials[mname]
            bsdf = _principled(mat)
            if bsdf is None:
                skipped.append(f"{mname}: no Principled BSDF")
                continue
            if bsdf.inputs["Normal"].is_linked:
                skipped.append(f"{mname}: its Normal input is already linked")
                continue
            tree = mat.node_tree
            tex = tree.nodes.new("ShaderNodeTexImage")
            tex.image = img
            tex.location = (bsdf.location.x - 600, bsdf.location.y - 400)
            nm = tree.nodes.new("ShaderNodeNormalMap")
            nm.space = "TANGENT"
            nm.uv_map = uv
            nm.inputs["Strength"].default_value = strength
            nm.location = (bsdf.location.x - 300, bsdf.location.y - 400)
            tree.links.new(tex.outputs["Color"], nm.inputs["Color"])
            tree.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
            attached.append(mname)
    return {"image": img.name, "file": path, "size": size, "materials": attached, "skipped": skipped,
            "stats": dict(stats, cleaned_texels=cleaned), "seconds": round(time.time() - t0, 1), "warnings": warnings}


def summarize(res):
    if "error" in res:
        return "ERROR: " + res["error"]
    s = res["stats"]
    lines = [f"detail normal {res['file']} ({res['size']} px, {res['seconds']} s): "
             f"{100 * s['over_1deg']:.2f}% of texels bent >1 deg, {100 * s['over_5deg']:.2f}% >5 deg, "
             f"99.9th percentile {s['p999_deg']} deg",
             "  attached to " + (", ".join(res["materials"]) or "nothing")]
    lines += ["  skipped " + x for x in res["skipped"]]
    lines += ["  WARN " + w for w in res["warnings"]]
    return "\n".join(lines)
