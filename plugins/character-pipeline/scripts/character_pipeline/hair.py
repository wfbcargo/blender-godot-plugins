"""DEPRECATED: the pipeline's old hair, kept only so a spec with `kind = "shell_bun"` still builds. New specs
name a humanform hair preset (`[hair] preset = "bun"`), which has a feathered hairline, strand material and
strand objects; see humanform's SKILL.md, Hair (improvements 05 5.2).

A shell cut from the scalp and pushed out, and a bun, joined into the body and skinned whole to the head
role. Moved from grungist-creek's build_belle.py, where it was Belle's `hair()`. Heights are measured down
from the top of the head.
"""

from __future__ import annotations

import bmesh
import bpy
from mathutils import Vector

DEFAULTS = dict(front=0.075, side=0.095, back=0.185, ear_x=0.066, thick=0.011, edge=0.003,
                bun=(0.0, 0.105, -0.13), bun_size=(0.052, 0.045, 0.048), colour=(0.17, 0.10, 0.06))


def _uvsphere(bm, **kw):
    """create_uvsphere with its faces in a stable order (Blender shuffles them per process; 05 5.7)."""
    before = set(bm.faces)
    res = bmesh.ops.create_uvsphere(bm, **kw)
    bm.verts.index_update()
    bm.faces.index_update()
    new = sorted((f for f in bm.faces if f not in before), key=lambda f: tuple(v.index for v in f.verts))
    rank = {f: len(before) + i for i, f in enumerate(new)}
    bm.faces.sort(key=lambda f: rank.get(f, f.index))
    bm.faces.index_update()
    return res


def shell_bun(ch, **params):
    from humanform import look
    from rig_analysis import bodymap
    h = dict(DEFAULTS, **params)
    ob = bpy.data.objects[ch.mesh]
    rig = bpy.data.objects[ch.rig]
    head = bodymap.build(ch.rig)["roles"]["head"]
    if head is None:
        raise RuntimeError(f"hair: rig-anything found no head bone on {ch.rig} to skin the hair to")
    head_bone = rig.data.bones[head]
    gi = ob.vertex_groups[head].index
    top = max(v.co.z for v in ob.data.vertices)
    cy = 0.5 * (head_bone.head_local.y + head_bone.tail_local.y)

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    dl = bm.verts.layers.deform.active

    def on_scalp(v):
        if v[dl].get(gi, 0.0) < 0.98:
            return False
        front = max(-1.0, min(1.0, (cy - v.co.y) / 0.09))        # +1 at the brow, -1 at the nape
        side = 1.0 - abs(front)
        line = top - (h["front"] * max(front, 0.0) + h["back"] * max(-front, 0.0) + h["side"] * side)
        if abs(v.co.x) > h["ear_x"] and v.co.z < top - h["front"]:
            return False                                            # the ears stay out
        return v.co.z > line

    keep = {f.index for f in bm.faces if all(on_scalp(v) for v in f.verts)}
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.normal_update()
    for v in bm.verts:
        v.co = v.co + v.normal * (h["edge"] if v.is_boundary else h["thick"])
    for _ in range(4):
        moved = [(v, sum((e.other_vert(v).co for e in v.link_edges), Vector()) / len(v.link_edges))
                 for v in bm.verts if not v.is_boundary and v.link_edges]
        for v, avg in moved:
            v.co = v.co.lerp(avg, 0.5)
    centre = Vector((0.0, cy, top)) + Vector(h["bun"])
    res = _uvsphere(bm, u_segments=20, v_segments=12, radius=1.0)
    for v in res["verts"]:
        v.co = centre + Vector((v.co.x * h["bun_size"][0], v.co.y * h["bun_size"][1], v.co.z * h["bun_size"][2]))
    for v in bm.verts:
        v[dl].clear()
        v[dl][gi] = 1.0
    me = bpy.data.meshes.new(ch.name + "_hair")
    bm.to_mesh(me)
    bm.free()
    hair = bpy.data.objects.new(ch.name + "_hair", me)
    for c in ob.users_collection:
        c.objects.link(hair)
    for g in ob.vertex_groups:
        hair.vertex_groups.new(name=g.name)
    hair.matrix_world = ob.matrix_world.copy()
    mat = bpy.data.materials.new(ch.name + "_hair")
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*look.srgb_to_linear(h["colour"]), 1.0)
    bsdf.inputs["Roughness"].default_value = 0.45
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    verts = len(me.vertices)
    with bpy.context.temp_override(active_object=ob, selected_editable_objects=[ob, hair], object=ob,
                                   selected_objects=[ob, hair]):
        bpy.ops.object.join()
    return {"verts": verts, "faces_from_scalp": len(keep), "head": head}
