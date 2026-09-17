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
  is left alone and reported, unless the link is an earlier bake of the same image: a re-bake reuses the
  image datablock and re-points those nodes (so a rebuild never leaves the material an empty texture).
- The scene's render engine and Cycles device, samples and denoising are put back afterwards.
- `material`: bake only the faces using that material. Characters join their eyes (with their own UVs,
  overlapping the skin's) into the body; baking every face would paint the eyes over the skin texels.
- `method`: when `high` has `low`'s own topology (a `delta` shape key's high copy of the body it is baked
  onto), "matched" - chosen by "auto" - bakes no rays: each corner gets high's vertex normal expressed in
  low's MikkTSpace frame, an EMIT bake of that corner colour fills the map. Rays cast from one body part
  find another where they are close (the armpit and hip UV borders came out as hot spots, and the clean
  pass below left hard-edged flat patches that rendered as dark streaks on the arms and flanks); matched
  has neither. The map is as smooth as the mesh's vertices - which is all a per-vertex delta has.
- "rays": the usual selected-to-active bake, `extrusion` out from the low surface, `max_ray` long. Both
  meshes must be in the same place (a rigged low mesh is baked in its rig's rest pose).
- `clean` (on, rays only): the same bake is run against an exact copy of `low`, and wherever that comes out bent the
  rays found a neighbouring surface, not detail (between fingers, the nails, eyelids, ears) - those texels
  are set flat. On an MPFB body without it, the nails and eyelid rims baked as garbage (up to 166 degrees).
- `max_deg` (60): texels bent more than that are flattened as well - on an MPFB body the armpit and hip
  UV borders, where rays from the torso found the high copy's arm, came out as saturated hot spots.
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


def _only_material(low, material, prepare=None):
    """A temporary copy of `low` holding only the faces that use `material` (every face when None), and
    that material (None). `prepare(mesh)` runs on the copy before any face is removed."""
    import bmesh
    idx = None
    if material is not None:
        idx = next((i for i, s in enumerate(low.material_slots) if s.material and s.material.name == material), None)
        if idx is None:
            raise ValueError(f"{low.name} has no material {material!r}")
    me = low.data.copy()
    if prepare is not None:
        prepare(me)
    if idx is not None:
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
    if not tmp.users_collection:
        bpy.context.scene.collection.objects.link(tmp)
    return tmp, (me.materials[idx] if idx is not None else None)


ATTR = "lookdev_detail_tn"


def matched(low, high):
    """True when `high` is `low`'s own topology (same vertices and faces, in order): a delta shape key's
    high copy of the body it was baked off."""
    a, b = low.data, high.data
    if len(a.vertices) != len(b.vertices) or len(a.polygons) != len(b.polygons):
        return False
    n = min(len(a.polygons), 64)
    return all(tuple(a.polygons[i].vertices) == tuple(b.polygons[i].vertices) for i in range(n))


def _tangent_normals(low, high):
    """`prepare` for the matched bake: `high`'s vertex normal at each corner of the mesh, in the corner's
    MikkTSpace frame from the active UV map (OpenGL +Y), as a corner colour attribute."""
    hn = np.empty(len(high.data.vertices) * 3, np.float64)
    high.data.vertices.foreach_get("normal", hn)
    hn = hn.reshape(-1, 3)
    rot = np.array((low.matrix_world.inverted() @ high.matrix_world).to_3x3().inverted().transposed())
    hn = hn @ rot.T
    hn /= np.maximum(np.linalg.norm(hn, axis=1), 1e-12)[:, None]

    def prepare(me):
        me.calc_tangents(uvmap=me.uv_layers.active.name)
        nl = len(me.loops)
        t, n, sg = np.empty(nl * 3), np.empty(nl * 3), np.empty(nl)
        vi = np.empty(nl, np.int64)
        me.loops.foreach_get("tangent", t)
        me.loops.foreach_get("normal", n)
        me.loops.foreach_get("bitangent_sign", sg)
        me.loops.foreach_get("vertex_index", vi)
        t, n = t.reshape(-1, 3), n.reshape(-1, 3)
        b = sg[:, None] * np.cross(n, t)
        h = hn[vi]
        tn = np.stack([np.einsum("ij,ij->i", h, t), np.einsum("ij,ij->i", h, b), np.einsum("ij,ij->i", h, n)], axis=1)
        tn /= np.maximum(np.linalg.norm(tn, axis=1), 1e-12)[:, None]
        col = np.ones((nl, 4), np.float32)
        col[:, :3] = tn * 0.5 + 0.5
        me.free_tangents()
        attr = me.color_attributes.get(ATTR) or me.color_attributes.new(ATTR, "FLOAT_COLOR", "CORNER")
        attr.data.foreach_set("color", col.ravel())
    return prepare


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
# Sculpted detail at body scale (humanform's heights, 2 cm over several cm) bends a normal 30-45 degrees at most.
# Steeper texels are rays that found another surface only the high copy has there - where the arm's
# definition pushes its surface toward the torso at the armpit and hip UV borders - and are flattened.
MAX_DEG = 60.0


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


def _flatten_steep(img, deg):
    """Flatten texels bent more than `deg` from the surface normal; returns how many."""
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(-1, 4)
    n = a[:, :3] * 2.0 - 1.0
    z = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-6)
    bad = z < np.cos(np.radians(deg))
    a[bad, :3] = (0.5, 0.5, 1.0)
    img.pixels.foreach_set(a.ravel())
    img.update()
    return int(bad.sum())


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


def _bake_once(low, high, target, mats, name, size, extrusion, max_ray, margin, samples, device, emit=False):
    """One Cycles bake into a new image `name`: a selected-to-active NORMAL bake from `high` onto `target`,
    or with `emit` an EMIT bake of `target`'s own ATTR corner colours (the matched method, no rays)."""
    scene = bpy.context.scene
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False, is_data=True)
    img.generated_color = (0.5, 0.5, 1.0, 1.0)
    img.colorspace_settings.name = "Non-Color"

    rigs = [m.object for m in target.modifiers if m.type == "ARMATURE" and m.object is not None]
    cy = scene.cycles
    state = {"engine": scene.render.engine, "active": bpy.context.view_layer.objects.active,
             "cycles": (cy.device, cy.samples, cy.use_denoising),
             "selected": [o for o in scene.objects if o.select_get()],
             "pose": [(r, r.data.pose_position) for r in rigs]}
    added, unlinked, restore_out = [], [], []
    try:
        # a normal bake takes the source's shading normal: a map an earlier bake wired into the materials
        # (the high copy and the twin share the low mesh's) would be baked in again - into the twin too, which
        # then flattened the whole map. Their Principled Normal inputs are unlinked for the bake.
        for ob in ((target,) if emit else (high, target)):
            for slot in ob.material_slots:
                bsdf = _principled(slot.material)
                if bsdf is not None and bsdf.inputs["Normal"].is_linked:
                    lk = bsdf.inputs["Normal"].links[0]
                    unlinked.append((slot.material.node_tree, lk.from_socket, lk.to_socket))
                    slot.material.node_tree.links.remove(lk)
        scene.render.engine = "CYCLES"
        scene.cycles.device = device
        scene.cycles.samples = samples
        scene.cycles.use_denoising = False
        for r in rigs:
            r.data.pose_position = "REST"
        for m in mats:
            tree = m.node_tree
            if emit:
                out_was = [nd for nd in tree.nodes if nd.type == "OUTPUT_MATERIAL" and nd.is_active_output]
                at = tree.nodes.new("ShaderNodeAttribute")
                at.attribute_type = "GEOMETRY"
                at.attribute_name = ATTR
                em = tree.nodes.new("ShaderNodeEmission")
                out = tree.nodes.new("ShaderNodeOutputMaterial")
                tree.links.new(at.outputs["Color"], em.inputs["Color"])
                tree.links.new(em.outputs["Emission"], out.inputs["Surface"])
                out.is_active_output = True
                added += [(tree, at), (tree, em), (tree, out)]
                restore_out.append(out_was)
            for nd in tree.nodes:
                nd.select = False
            node = tree.nodes.new("ShaderNodeTexImage")
            node.image = img
            node.select = True
            tree.nodes.active = node
            added.append((tree, node))
        for o in scene.objects:
            o.select_set(False)
        if not emit:
            high.select_set(True)
        target.select_set(True)
        bpy.context.view_layer.objects.active = target
        bpy.context.view_layer.update()
        if emit:
            bpy.ops.object.bake(type="EMIT", use_selected_to_active=False, margin=margin, margin_type="EXTEND",
                                use_clear=False, target="IMAGE_TEXTURES")
        else:
            bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", normal_r="POS_X", normal_g="POS_Y",
                                normal_b="POS_Z", use_selected_to_active=True, cage_extrusion=extrusion,
                                max_ray_distance=max_ray, margin=margin, margin_type="EXTEND", use_clear=True,
                                target="IMAGE_TEXTURES")
    finally:
        for tree, node in added:
            tree.nodes.remove(node)
        for outs in restore_out:
            for nd in outs:
                nd.is_active_output = True
        for tree, a, b in unlinked:
            tree.links.new(a, b)
        scene.render.engine = state["engine"]
        cy.device, cy.samples, cy.use_denoising = state["cycles"]
        for r, pos in state["pose"]:
            r.data.pose_position = pos
        for o in scene.objects:
            o.select_set(o in state["selected"])
        bpy.context.view_layer.objects.active = state["active"]

    return img


def _our_texture(bsdf, img):
    """The Image Texture feeding `bsdf`'s Normal through a tangent Normal Map, when an earlier bake of this
    image (same name, or emptied) made it; else None."""
    link = bsdf.inputs["Normal"].links[0]
    nm = link.from_node
    if nm.type != "NORMAL_MAP" or not nm.inputs["Color"].is_linked:
        return None
    tex = nm.inputs["Color"].links[0].from_node
    if tex.type != "TEX_IMAGE":
        return None
    if tex.image is None or tex.image == img or tex.image.name == img.name:
        return tex
    return None


def bake_normal_from_high(low, high, out_dir, size=2048, material=None, extrusion=0.012, max_ray=0.03,
                          attach=True, name=None, samples=1, margin=None, device="CPU", strength=1.0, clean=True,
                          max_deg=MAX_DEG, method="auto"):
    """Bake `high`'s surface into a tangent normal map on `low`'s UVs and (with `attach`) wire it into
    `low`'s materials. `method`: "matched" (high is low's topology: its normals in low's tangent frames, no
    rays), "rays" (selected-to-active), "auto" (matched when `matched(low, high)`). Returns {"image", "file",
    "materials", "skipped", "stats", "seconds", "warnings", "method"}."""
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
    if method == "auto":
        method = "matched" if matched(low, high) else "rays"
    if method == "matched" and not matched(low, high):
        return {"error": f"{high.name} is not {low.name}'s topology: use method='rays'"}
    target, tmp = low, None
    mats = [s.material for s in low.material_slots if s.material]
    if material is not None or method == "matched":
        tmp, mat = _only_material(low, material, _tangent_normals(low, high) if method == "matched" else None)
        target = tmp
        if mat is not None:
            mats = [mat]
    if not mats:
        return {"error": f"{low.name} has no materials to bake into"}

    cleaned = 0
    try:
        img = _bake_once(low, high, target, mats, name + "_bake", size, extrusion, max_ray, margin, samples, device,
                         emit=method == "matched")
        if clean and method == "rays":
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
        if max_deg:
            cleaned += _flatten_steep(img, max_deg)
    finally:
        if tmp is not None:
            me = tmp.data
            bpy.data.objects.remove(tmp, do_unlink=True)
            bpy.data.meshes.remove(me)

    # takes the place of an earlier bake's image of that name: every user of that one (the material's
    # texture node) is remapped to this, so a re-bake never leaves the material an empty texture
    old = bpy.data.images.get(name)
    if old is not None:
        old.user_remap(img)
        bpy.data.images.remove(old)
    img.name = name
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
            tree = mat.node_tree
            if bsdf.inputs["Normal"].is_linked:
                tex = _our_texture(bsdf, img)
                if tex is None:
                    skipped.append(f"{mname}: its Normal input is already linked")
                    continue
                # an earlier bake's nodes: point them at this bake
                tex.image = img
                bsdf.inputs["Normal"].links[0].from_node.inputs["Strength"].default_value = strength
                attached.append(mname)
                continue
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
            "stats": dict(stats, cleaned_texels=cleaned), "method": method, "seconds": round(time.time() - t0, 1), "warnings": warnings}


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
