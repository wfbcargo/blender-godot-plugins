"""Cut a garment out of the body it will be worn on.

The fastest garment that fits is the body's own skin: copy it, cut it where the garment
ends, and ease it off the body (`fit`). It inherits the body's topology, so its skin
weights are the body's own and it bends exactly where the body bends.

    shirt = tailor.shirt("Figure")                                   # a T-shirt
    tank  = tailor.shirt("Figure", sleeve=0.0, name="Tank")          # sleeves cut at the shoulder joint
    long  = tailor.shirt("Figure", sleeve=1.9, hem=-0.25, name="LongShirt")

Cuts are planes, and every plane only cuts the part of the body it is meant for: a sleeve
plane tilted with an A-posed arm also crosses the hips, so it is applied only to faces
skinned to that arm. Each cut is followed by keeping the piece that holds the chest.

Measurements are fractions of the body, so the same call fits any humanoid:
  sleeve   along the arm from the shoulder joint: 0 at it, 1 at the elbow, 2 at the wrist
  hem      height from the hip joints, in torso lengths (hip joints to shoulder joints);
           negative is below the hips
  neck     (front, back) heights of the neckline from the base of the neck, in torso lengths
"""

from __future__ import annotations

import bmesh
import bpy
from mathutils import Vector

from . import rigmap

FLESH_FIRST = ("flesh after garments loses the jiggle weights - run follow_through.flesh.prepare "
               "before cutting")


def flesh_order_warnings(body):
    """Warnings when `body` is meant to carry follow-through flesh but its jiggle weights are not
    there yet: a garment cut now copies skin weights with no jiggle bones in them, and its breasts,
    belly and buttocks stay rigid while the body's jiggle. A body with no follow-through spec is
    simply not fleshed, and gets no warning."""
    ft = body.get("follow_through")
    jiggle = ft.get("jiggle") if ft is not None else None
    regions = list(jiggle.get("regions") or []) if jiggle is not None else []
    if not regions:
        return []
    groups = {g.name for g in body.vertex_groups}
    missing = sorted(str(r.get("bone")) for r in regions if r.get("bone") not in groups)
    if not missing:
        return []
    if not any(n.startswith("ft_jiggle_") for n in groups):
        what = "%s has a follow-through jiggle spec (%d regions) but no ft_jiggle_* vertex groups" % (
            body.name, len(regions))
    else:
        what = "%s's follow-through jiggle regions have no vertex groups: %s" % (body.name, ", ".join(missing))
    return [what + ": " + FLESH_FIRST]


def _warn(obj, cuts, warnings):
    """Warnings go in the cut report (only when there are any) and are printed, as wardrobe's
    summaries are."""
    if warnings:
        cuts["warnings"] = warnings
        for w in warnings:
            print("wardrobe.tailor WARNING %s: %s" % (obj.name, w))


def _weight_of(dl, v, idx):
    d = v[dl]
    return sum(d.get(i, 0.0) for i in idx)


def _face_weight(dl, f, idx):
    return sum(_weight_of(dl, v, idx) for v in f.verts) / len(f.verts)


def _cut(bm, dl, idx, min_weight, co, no):
    """Bisect the faces skinned to `idx` by a plane and delete what lies on the normal's side."""
    faces = [f for f in bm.faces if _face_weight(dl, f, idx) >= min_weight]
    if not faces:
        return 0
    edges = {e for f in faces for e in f.edges}
    verts = {v for f in faces for v in f.verts}
    bmesh.ops.bisect_plane(bm, geom=list(verts) + list(edges) + faces, dist=1e-6,
                           plane_co=co, plane_no=no, clear_outer=False, clear_inner=False)
    # faces changed identity when split: select again, by weight and by side
    doomed = [f for f in bm.faces
              if _face_weight(dl, f, idx) >= min_weight and (f.calc_center_median() - co).dot(no) > 1e-6]
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    return len(doomed)


def _keep_piece(bm, near):
    """Delete every face not connected to the face nearest `near`."""
    bm.faces.ensure_lookup_table()
    start = min(bm.faces, key=lambda f: (f.calc_center_median() - near).length_squared)
    seen = {start}
    stack = [start]
    while stack:
        f = stack.pop()
        for e in f.edges:
            for g in e.link_faces:
                if g not in seen:
                    seen.add(g)
                    stack.append(g)
    rest = [f for f in bm.faces if f not in seen]
    bmesh.ops.delete(bm, geom=rest, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    return len(rest)


def shirt(body, name="Shirt", sleeve=0.45, hem=-0.08, neck=(-0.04, 0.12)):
    """A shirt cut from `body`: returns the new object, skinned like the body, not yet eased."""
    body = rigmap._obj(body)
    hm = rigmap.humanoid(body)
    rig = bpy.data.objects[hm["rig"]]
    H, T = hm["heads"], hm["tails"]
    up = Vector((0, 0, 1))
    fwd = hm["forward"]

    hip_z = sum(H[l["thigh"]].z for l in hm["legs"].values()) / max(1, len(hm["legs"]))
    shoulder_z = sum(H[a["upper"]].z for a in hm["arms"].values()) / max(1, len(hm["arms"]))
    torso = shoulder_z - hip_z

    bm = bmesh.new()
    bm.from_mesh(body.data)
    dl = bm.verts.layers.deform.verify()
    group = {g.name: g.index for g in body.vertex_groups}

    def idx(names):
        return {group[n] for n in names if n in group}

    cuts = {}
    for side, a in hm["arms"].items():
        arm_bones = [b for b in (a["upper"], a["fore"], a["hand"]) if b]
        arm_bones += [g for g in group if g.startswith("ft_jiggle_arm") and g.endswith("." + side)]
        if sleeve <= 1.0:
            s, e = H[a["upper"]], T[a["upper"]]
            t = sleeve
        else:
            s, e = H[a["fore"]], T[a["fore"]]
            t = sleeve - 1.0
        co = s.lerp(e, t)
        no = (e - s).normalized()
        cuts["sleeve." + side] = _cut(bm, dl, idx(arm_bones), 0.25, co, no)

    neck_bones = hm["neck"]
    if neck_bones:
        base = H[neck_bones[0]]
        r = 0.25 * torso
        front = base + fwd * r + up * (neck[0] * torso)
        back = base - fwd * r + up * (neck[1] * torso)
        left = up.cross(fwd).normalized()                 # up x forward = left (+X on a -Y facing body)
        no = (front - back).cross(left).normalized()
        if no.z < 0:
            no = -no
        cuts["neck"] = _cut(bm, dl, idx(neck_bones), 0.2, (front + back) * 0.5, no)

    hem_z = hip_z + hem * torso
    leg_bones = [b for l in hm["legs"].values() for b in l.values() if b]
    torso_bones = hm["torso"] + [g for g in group if g.startswith(("pelvis", "ft_jiggle_butt", "ft_jiggle_belly",
                                                                     "ft_jiggle_love"))]
    cuts["hem"] = _cut(bm, dl, idx(leg_bones + torso_bones), 0.0, Vector((0, 0, hem_z)), -up)

    chest = H[hm["torso"][-1]] + fwd * (0.1 * rigmap.torso_scale(torso))
    cuts["pieces_dropped"] = _keep_piece(bm, chest)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    obj = bpy.data.objects.new(name, mesh)
    for c in body.users_collection:
        c.objects.link(obj)
    for g in body.vertex_groups:
        obj.vertex_groups.new(name=g.name)      # same order: the bmesh deform layer is by index
    keep = rigmap.deform_names(body)
    for g in [g for g in obj.vertex_groups if g.name not in keep]:
        # a wd_hide_ group left on the body by an earlier cover.compute was copied into a second
        # shirt as a weight of 1 and normalised its real weights away
        obj.vertex_groups.remove(g)
    obj.parent = body.parent
    obj.matrix_parent_inverse = body.matrix_parent_inverse.copy()
    obj.matrix_basis = body.matrix_basis.copy()
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    obj["wardrobe_cut"] = {"kind": "shirt", "body": body.name, "sleeve": sleeve, "hem": hem, "neck": list(neck),
                           "hem_z": hem_z, "torso_m": torso, "hip_z": hip_z, "shoulder_z": shoulder_z}
    _warn(obj, cuts, flesh_order_warnings(body))
    obj["wardrobe_cut_report"] = cuts
    return obj


def _object(body, name, bm):
    rig = rigmap.rig_of(body)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    obj = bpy.data.objects.new(name, mesh)
    for c in body.users_collection:
        c.objects.link(obj)
    for g in body.vertex_groups:
        obj.vertex_groups.new(name=g.name)
    keep = rigmap.deform_names(body)
    for g in [g for g in obj.vertex_groups if g.name not in keep]:
        obj.vertex_groups.remove(g)
    obj.parent = body.parent
    obj.matrix_parent_inverse = body.matrix_parent_inverse.copy()
    obj.matrix_basis = body.matrix_basis.copy()
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    return obj


def pants(body, name="Trousers", waist=0.30, leg=1.9, leg_angle=0.0):
    """Trousers, shorts or briefs cut from `body`.

      waist      height of the waistband above the hip joints, in torso lengths
      leg        along the leg: 0 at the hip joint, 1 at the knee, 2 at the ankle
      leg_angle  degrees the leg opening rises toward the outside of the hip (briefs ~35)

    A leg's cut only takes faces skinned to that leg and lying out from the midline, so the crotch
    stays whole whatever height the opening is at."""
    body = rigmap._obj(body)
    hm = rigmap.humanoid(body)
    H, T = hm["heads"], hm["tails"]
    up = Vector((0, 0, 1))
    hip_z = sum(H[l["thigh"]].z for l in hm["legs"].values()) / max(1, len(hm["legs"]))
    shoulder_z = sum(H[a["upper"]].z for a in hm["arms"].values()) / max(1, len(hm["arms"]))
    torso = shoulder_z - hip_z

    bm = bmesh.new()
    bm.from_mesh(body.data)
    dl = bm.verts.layers.deform.verify()
    group = {g.name: g.index for g in body.vertex_groups}
    cuts = {}
    waist_z = hip_z + waist * torso
    cuts["waist"] = _cut(bm, dl, set(group.values()), 0.0, Vector((0, 0, waist_z)), up)
    import math
    # the crotch: the lowest point of the body on its midline - below it the legs are apart
    sc = rigmap.torso_scale(torso)   # the offsets below were set on human hips (rigmap.HUMAN_TORSO_M)
    crotch_z = min((v.co.z for v in body.data.vertices if abs(v.co.x) < 0.004 and v.co.z < hip_z + 0.1 * sc),
                   default=hip_z - 0.07 * sc)
    for side, l in hm["legs"].items():
        sx = 1 if side == "L" else -1
        bones = [b for b in l.values() if b] + [g for g in group if g.startswith("ft_jiggle_thigh") and g.endswith("." + side)]
        if leg <= 1.0:
            s, e = H[l["thigh"]], T[l["thigh"]]
            t = leg
        else:
            s, e = H[l["shin"]], T[l["shin"]]
            t = leg - 1.0
        co = s.lerp(e, t)
        no = (e - s).normalized()
        if leg_angle:
            a = math.radians(leg_angle)
            no = (no * math.cos(a) + Vector((sx, 0, 0)) * math.sin(a)).normalized()
        idx = {group[n] for n in bones if n in group}
        # only this leg's side, and near the crotch only faces out from the midline: the crotch stays
        # whole, and the inner thigh below it is still cut (a 3 cm midline band left a strip of
        # briefs hanging to the knee)
        mid = 0.35 * abs(H[l["thigh"]].x)
        cuts["leg." + side] = _cut_side(bm, dl, idx, 0.25, co, no, sx, mid, crotch_z - 0.015 * sc)
    front = hm["forward"]
    cuts["pieces_dropped"] = _keep_piece(bm, Vector((0, 0, hip_z + 0.04 * sc)) + front * (0.12 * sc))
    obj = _object(body, name, bm)
    obj["wardrobe_cut"] = {"kind": "pants", "body": body.name, "waist": waist, "leg": leg, "leg_angle": leg_angle,
                           "crotch_z": crotch_z,
                           "waist_z": waist_z, "hip_z": hip_z, "torso_m": torso, "hang_below": hip_z - 0.06 * sc}
    _warn(obj, cuts, flesh_order_warnings(body))
    obj["wardrobe_cut_report"] = cuts
    return obj


def skirt(body, name="Skirt", waist=0.16, length=1.0, flare=1.25, **kw):
    """A skirt built round `body`, not cut from it: a tube from the waistband (`waist` torso lengths above the
    hip joints) to a hem at `length` along the leg (1 the knee), whose girth is `flare` times the widest hip
    girth. Weighted to the body at the hips and to pelvis and thighs by distance below. See `skirts`."""
    from . import skirts
    return skirts.skirt(body, name=name, waist=waist, length=length, flare=flare, **kw)


def dress(body, name="Dress", neck=(-0.10, 0.08), sleeve=-0.10, length=1.0, flare=1.25, **kw):
    """A dress: a bodice cut from `body` (`neck` and `sleeve` as `shirt`'s) down to the natural waist, and a
    skirt hung from its hem to `length` along the leg with `flare`. See `skirts`."""
    from . import skirts
    return skirts.dress(body, name=name, neck=neck, sleeve=sleeve, length=length, flare=flare, **kw)


def _cut_side(bm, dl, idx, min_weight, co, no, sx, mid, below=-1e9):
    """_cut limited to faces whose centre lies beyond `mid` on the `sx` side of the midline."""
    def ok(f):
        c = f.calc_center_median()
        if c.z < below and c.x * sx > 0:
            return True                  # below the crotch, this side is this leg whatever its weights
        return c.x * sx > mid and _face_weight(dl, f, idx) >= min_weight
    faces = [f for f in bm.faces if ok(f)]
    if not faces:
        return 0
    edges = {e for f in faces for e in f.edges}
    verts = {v for f in faces for v in f.verts}
    bmesh.ops.bisect_plane(bm, geom=list(verts) + list(edges) + faces, dist=1e-6,
                           plane_co=co, plane_no=no, clear_outer=False, clear_inner=False)
    doomed = [f for f in bm.faces if ok(f) and (f.calc_center_median() - co).dot(no) > 1e-6]
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    return len(doomed)
