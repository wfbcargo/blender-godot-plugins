"""Skirts and dresses: a tube hung from the waist (or a bodice) to a hem ring.

    sk = tailor.skirt("Nadia_body", waist=0.16, length=0.85, flare=1.3)            # just above the knee
    dr = tailor.dress("Nadia_body", neck=(-0.10, 0.08), sleeve=-0.1, length=0.85, flare=1.3)

A skirt cannot be cut from the skin the way trousers are: between the legs there is none, and a
skirt does not cling to one leg. So it is built. Around a vertical axis through the pelvis, rays
from outside find the body's surface (arms left out) at every angle and height; the cloth takes that
radius plus its ease and hangs straight down from the widest point above it, never tucking back in
under the seat or the belly. Below the widest hip level the tube opens toward the hem, whose ring is
`flare` times the widest hip girth (1.0 a pencil skirt, 1.3 an A-line), and never comes closer to
the legs at rest than `clearance`. The rings are blurred round and down so no ridge is left, then
pushed back out wherever blurring brought them inside what they must clear.

Weights: cloth lying on the body (within 2.5 cm of it - the waistband, the hips, the fronts of the
thighs) takes the weights of the skin under it, so it turns as that skin does; cloth hanging free
(beyond 6 cm - between the legs, below the seat) is weighted by distance: the pelvis above the hip
joints, the thighs below them, split between the two thighs by 1/d^6. Smoothed a little over the tube,
so a lifted thigh carries the front of the skirt in a crouch and a stride shares the cloth between the
legs. `weights` has the numbers that led there. Measurements are fractions of the body, as tailor's:

  waist    height of the waistband above the hip joints, in torso lengths
  length   along the leg: 0 at the hip joint, 1 at the knee, 2 at the ankle
  flare    hem girth over the widest hip girth
"""

from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import fit, rigmap

KINDS = ("skirt", "dress")


def _mean(xs):
    xs = list(xs)
    return sum(xs) / max(1, len(xs))


def levels(body):
    """Heights (body object space) of hips, knees, ankles, shoulders and the crotch, and the torso length."""
    body = rigmap._obj(body)
    hm = rigmap.humanoid(body)
    H, T = hm["heads"], hm["tails"]
    legs = list(hm["legs"].values())
    hip_z = _mean(H[l["thigh"]].z for l in legs)
    knee_z = _mean(H[l["shin"]].z for l in legs)
    ankle_z = _mean(T[l["shin"]].z for l in legs)
    shoulder_z = _mean(H[a["upper"]].z for a in hm["arms"].values())
    crotch_z = min((v.co.z for v in body.data.vertices if abs(v.co.x) < 0.004 and v.co.z < hip_z + 0.1),
                   default=hip_z - 0.07)
    return {"hm": hm, "hip_z": hip_z, "knee_z": knee_z, "ankle_z": ankle_z, "shoulder_z": shoulder_z,
            "torso": shoulder_z - hip_z, "crotch_z": crotch_z}


def hem_height(lv, length):
    if length <= 1.0:
        return lv["hip_z"] + (lv["knee_z"] - lv["hip_z"]) * length
    return lv["knee_z"] + (lv["ankle_z"] - lv["knee_z"]) * (length - 1.0)


def _arm_names(body, hm):
    """Every bone of the arms, fingers included: a hand hanging at the hips is not the hips."""
    names = {n for a in hm["arms"].values() for n in a.values() if n}
    names |= {vg.name for vg in body.vertex_groups if vg.name.startswith("ft_jiggle_arm")}
    rig = rigmap.rig_of(body)
    roots = [rig.data.bones.get(n) for n in list(names)]
    for b in roots:
        if b is not None:
            names |= {c.name for c in b.children_recursive}
    return names


def torso_legs(body, hm):
    """BVH of the body without its arms and hands (a hand hangs beside the hips), its vertices and
    triangles, in a canonical order."""
    armw = rigmap.chain_weights(body, _arm_names(body, hm))
    verts = [v.co.copy() for v in body.data.vertices]
    tris = [t for t in fit.canonical_tris(body.data) if max(armw[i] for i in t) < 0.4]
    return BVHTree.FromPolygons(verts, tris, all_triangles=True), verts, tris


def _axis(verts, tris, lo_z, hi_z, hm):
    """The vertical axis the tube hangs round: the midline of the hips, halfway front to back."""
    used = {i for t in tris for i in t}
    ys = [verts[i].y for i in used if lo_z <= verts[i].z <= hi_z]
    x = _mean(hm["heads"][l["thigh"]].x for l in hm["legs"].values())
    y = (min(ys) + max(ys)) * 0.5 if ys else _mean(hm["heads"][l["thigh"]].y for l in hm["legs"].values())
    return Vector((round(x, 6), round(y, 6)))


def _envelope(bvh, axis, z, segs, far=1.0):
    """Distance from the axis to the body's outer surface at each of `segs` angles, at height z:
    rays from `far` outside toward the axis. 0 where a ray reaches the axis (between the legs)."""
    out = []
    for j in range(segs):
        th = 2 * math.pi * j / segs
        d = Vector((math.cos(th), math.sin(th), 0.0))
        o = Vector((axis.x, axis.y, z)) + d * far
        hit = bvh.ray_cast(o, -d, far)
        out.append(far - hit[3] if hit[0] is not None else 0.0)
    return out


def _girth(radii):
    n = len(radii)
    pts = [(r * math.cos(2 * math.pi * j / n), r * math.sin(2 * math.pi * j / n)) for j, r in enumerate(radii)]
    return sum(math.dist(pts[j], pts[(j + 1) % n]) for j in range(n))


def profile(body, top_z, hem_z, flare, segs=64, ring_m=0.025, ease=0.008, clearance=0.02, blur=4,
            floor=None, lv=None, waist_ease=None):
    """Ring radii of a tube from `top_z` down to `hem_z`: [(z, [r per angle])], plus what was measured.
    `floor`: radii (per angle) the top may not come inside - a bodice's hem."""
    body = rigmap._obj(body)
    lv = lv or levels(body)
    hm = lv["hm"]
    bvh, verts, tris = torso_legs(body, hm)
    axis = _axis(verts, tris, lv["crotch_z"], top_z, hm)
    step = 0.01
    nfine = max(2, int(math.ceil((top_z - hem_z) / step)) + 1)
    fine_z = [top_z - (top_z - hem_z) * k / (nfine - 1) for k in range(nfine)]
    env = [_envelope(bvh, axis, z, segs) for z in fine_z]
    # hang: cloth falls straight from the widest point above it
    hang = []
    run = list(floor) if floor is not None else [0.0] * segs
    for e in env:
        run = [max(a, b) for a, b in zip(run, e)]
        hang.append(run)
    above = [k for k, z in enumerate(fine_z) if z >= lv["crotch_z"] + 0.02]
    wide_k = max(above, key=lambda k: (_girth(env[k]), -k)) if above else 0
    wide_z = fine_z[wide_k]
    wide = hang[wide_k]
    nr = max(2, int(round((top_z - hem_z) / ring_m)) + 1)
    rings_z = [top_z - (top_z - hem_z) * i / (nr - 1) for i in range(nr)]
    need, want = [], []
    for z in rings_z:
        k = min(range(nfine), key=lambda k: abs(fine_z[k] - z))
        # a waistband is snug - with a skirt's ease at the top a crouch looked down between it and the belly -
        # and loosens to the full ease by the widest hip level
        gap = ease if z >= lv["crotch_z"] else max(ease, clearance)
        if waist_ease is not None and z > wide_z:
            gap = waist_ease + (ease - waist_ease) * _smoothstep((top_z - z) / max(top_z - wide_z, 1e-6))
        n = [r + gap for r in hang[k]]
        if z >= wide_z:
            w = n
        else:
            t = (wide_z - z) / max(wide_z - hem_z, 1e-6)
            w = [max(a, ((1 - t) * (b + ease) + t * flare * b)) for a, b in zip(n, wide)]
        need.append(n)
        want.append(w)
    r = [list(w) for w in want]
    for _ in range(blur):
        nxt = []
        for i in range(nr):
            row = []
            for j in range(segs):
                s = wsum = 0.0
                for di in (-1, 0, 1):
                    ii = i + di
                    # the waistband stays snug: above the widest level only round the ring, not down it
                    if not 0 <= ii < nr or (di and rings_z[i] >= wide_z):
                        continue
                    for dj in (-3, -2, -1, 0, 1, 2, 3):
                        wgt = 1.0 / (1 + abs(di) * 2 + abs(dj))
                        s += r[ii][(j + dj) % segs] * wgt
                        wsum += wgt
                row.append(max(s / wsum, need[i][j]))
            nxt.append(row)
        r = nxt
    girth_wide = _girth(env[wide_k])
    return {"axis": axis, "rings": list(zip(rings_z, r)), "wide_z": wide_z, "girth_wide_m": girth_wide,
            "girth_hem_m": _girth(r[-1]), "levels": lv, "bvh": bvh, "verts": verts, "tris": tris}


def _ring_verts(bm, axis, z, radii):
    n = len(radii)
    return [bm.verts.new((axis.x + r * math.cos(2 * math.pi * j / n), axis.y + r * math.sin(2 * math.pi * j / n), z))
            for j, r in enumerate(radii)]


def _bridge(bm, upper, lower):
    """Quads between two rings of the same count, facing out (both run counter-clockwise from above)."""
    n = len(upper)
    for j in range(n):
        bm.faces.new((upper[j], lower[j], lower[(j + 1) % n], upper[(j + 1) % n]))


def _angle(axis, co):
    return math.atan2(co.y - axis.y, co.x - axis.x) % (2 * math.pi)


def _zip(bm, axis, upper, lower):
    """Triangles between two rings of different counts, walking round both by angle."""
    U = sorted(upper, key=lambda v: _angle(axis, v.co))
    L = sorted(lower, key=lambda v: _angle(axis, v.co))
    au = [_angle(axis, v.co) for v in U]
    al = [_angle(axis, v.co) for v in L]
    nu, nl = len(U), len(L)

    def ang(a, n, k):
        return a[k % n] + 2 * math.pi * (k // n)

    i = j = 0
    made = 0
    while i < nu or j < nl:
        cu, cl = U[i % nu], L[j % nl]
        if j >= nl or (i < nu and ang(au, nu, i + 1) <= ang(al, nl, j + 1)):
            nxt = U[(i + 1) % nu]
            tri = (cu, cl, nxt)
            i += 1
        else:
            nxt = L[(j + 1) % nl]
            tri = (cu, cl, nxt)
            j += 1
        if len({id(v) for v in tri}) == 3:
            try:
                bm.faces.new(tri)
                made += 1
            except ValueError:
                pass
    return made


def _segment_distance(p, a, b):
    ab = b - a
    t = 0.0 if ab.length_squared < 1e-12 else min(max((p - a).dot(ab) / ab.length_squared, 0.0), 1.0)
    return (p - (a + ab * t)).length


def _smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def weights(body, bm, fixed, prof, smooth=4, power=6.0, band=0.025, near_gap=0.025, far_gap=0.06, thigh=1.0,
            thigh_fade=0.10, thigh_lift=0.08, thigh_back=0.0, deform=None):
    """Per-vertex {bone: weight} for the tube's vertices; `fixed` {vert index: weights} are kept (a bodice).

    Cloth lying on the body takes the weights of the skin under it (the nearest point): the top `band` metres
    always, and below it wherever the skin is within `near_gap`, so it turns exactly as that skin does. Cloth
    hanging free - further than `far_gap` from any skin, between the legs, below the seat - is weighted by
    distance: from the pelvis to the thighs over `thigh_fade` metres down from `thigh_lift` above the hip
    joints, with up to `thigh` on the thighs, shared between the two by 1/distance^`power` to each thigh
    bone, and toward the back reduced by up to `thigh_back`. Then smoothed `smooth` times over the tube.

    Measured on Nadia's knee skirt in Godot: weighted by distance alone, the cloth over the front of the
    thighs at the hip crease carried 0.95 of a thigh where the skin under it carries 0.8, turned further than
    that skin in a crouch and was left inside the thigh (13 vertices); a crowd of L/R weights smoothed 24
    times at 1/d^2 let the forward thigh through the front in a run (86)."""
    body = rigmap._obj(body)
    lv = prof["levels"]
    hm = lv["hm"]
    H, T = hm["heads"], hm["tails"]
    deform = deform or rigmap.deform_names(body)
    arm = _arm_names(body, hm)
    names = {vg.index: vg.name for vg in body.vertex_groups}
    bw = [{names[x.group]: x.weight for x in v.groups
           if x.weight > 0 and names[x.group] in deform and names[x.group] not in arm} for v in body.data.vertices]
    bvh, bverts, btris = prof["bvh"], prof["verts"], prof["tris"]
    pelvis = hm["spine"][0]
    thighs = [(l["thigh"], H[l["thigh"]], T[l["thigh"]]) for l in hm["legs"].values()]
    top_z = prof["rings"][0][0]
    hip_z = lv["hip_z"]
    axis = prof["axis"]
    fwd = hm["forward"]
    bm.verts.ensure_lookup_table()
    w = []
    free = []
    for v in bm.verts:
        if v.index in fixed:
            w.append(dict(fixed[v.index]))
            free.append(False)
            continue
        hit = bvh.find_nearest(v.co)
        near = {}
        gap = 1.0
        if hit[0] is not None:
            gap = hit[3]
            t = btris[hit[2]]
            u, vv, ww = fit._barycentric(hit[0], bverts[t[0]], bverts[t[1]], bverts[t[2]])
            for i, f in zip(t, (u, vv, ww)):
                for k, x in bw[i].items():
                    near[k] = near.get(k, 0.0) + x * f
        inv = {name: 1.0 / max(_segment_distance(v.co, a, b), 0.03) ** power for name, a, b in thighs}
        s = sum(inv.values())
        share = thigh * _smoothstep((hip_z + thigh_lift - v.co.z) / thigh_fade)
        out = Vector((v.co.x - axis.x, v.co.y - axis.y, 0.0))
        if out.length > 1e-6:
            share *= 1.0 - thigh_back * max(0.0, -out.normalized().dot(fwd))
        built = {pelvis: 1.0 - share}
        for k, x in inv.items():
            built[k] = built.get(k, 0.0) + share * x / s
        f = _smoothstep((top_z - band - v.co.z) / band) * _smoothstep((gap - near_gap) / max(far_gap - near_gap, 1e-6))
        acc = {k: x * (1 - f) for k, x in near.items()}
        for k, x in built.items():
            acc[k] = acc.get(k, 0.0) + x * f
        w.append(acc)
        free.append(v.co.z < top_z - band)
    nb = [[e.other_vert(v).index for e in v.link_edges] for v in bm.verts]
    for _ in range(smooth):
        nxt = []
        for i, own in enumerate(w):
            if not free[i] or not nb[i]:
                nxt.append(own)
                continue
            acc = {k: x * 0.5 for k, x in own.items()}
            share = 0.5 / len(nb[i])
            for j in nb[i]:
                for k, x in w[j].items():
                    acc[k] = acc.get(k, 0.0) + x * share
            nxt.append(acc)
        w = nxt
    out = []
    for acc in w:
        top = sorted(((k, x) for k, x in acc.items() if x > 1e-4), key=lambda kv: (-kv[1], kv[0]))[:4]
        s = sum(x for _, x in top)
        out.append({k: x / s for k, x in top} if s > 0 else {pelvis: 1.0})
    return out


def _new_object(body, name, bm, vw):
    body = rigmap._obj(body)
    rig = rigmap.rig_of(body)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for p in mesh.polygons:
        p.use_smooth = True
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    obj = bpy.data.objects.new(name, mesh)
    for c in body.users_collection:
        c.objects.link(obj)
    keep = rigmap.deform_names(body)
    for g in body.vertex_groups:
        if g.name in keep:
            obj.vertex_groups.new(name=g.name)
    for i, acc in enumerate(vw):
        for k, x in acc.items():
            obj.vertex_groups[k].add([i], x, "REPLACE")
    obj.parent = body.parent
    obj.matrix_parent_inverse = body.matrix_parent_inverse.copy()
    obj.matrix_basis = body.matrix_basis.copy()
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    return obj


def _outward_share(obj, axis):
    me = obj.data
    good = 0
    for p in me.polygons:
        c = p.center
        radial = Vector((c.x - axis.x, c.y - axis.y, 0.0))
        good += 1 if radial.dot(p.normal) > 0 else 0
    return round(good / max(1, len(me.polygons)), 4)


def skirt(body, name="Skirt", waist=0.16, length=1.0, flare=1.25, segments=64, ring_m=0.025, ease=0.015,
          waist_ease=0.005, clearance=0.02, smooth=4, thigh=1.0, thigh_fade=0.10, thigh_lift=0.08, thigh_back=0.0):
    from . import tailor
    body = rigmap._obj(body)
    lv = levels(body)
    top_z = lv["hip_z"] + waist * lv["torso"]
    hem_z = hem_height(lv, length)
    if hem_z >= top_z - 0.05:
        raise ValueError(f"skirt: hem at {hem_z:.3f} m is not below the waist at {top_z:.3f} m")
    prof = profile(body, top_z, hem_z, flare, segs=segments, ring_m=ring_m, ease=ease, clearance=clearance, lv=lv,
                   waist_ease=waist_ease)
    bm = bmesh.new()
    rings = [_ring_verts(bm, prof["axis"], z, r) for z, r in prof["rings"]]
    for a, b in zip(rings, rings[1:]):
        _bridge(bm, a, b)
    bm.verts.index_update()
    vw = weights(body, bm, {}, prof, smooth=smooth, thigh=thigh, thigh_fade=thigh_fade, thigh_lift=thigh_lift,
                 thigh_back=thigh_back)
    obj = _new_object(body, name, bm, vw)
    obj["wardrobe_cut"] = _cut_record("skirt", body, prof, lv, top_z, hem_z, waist=waist, length=length,
                                      flare=flare, ease=ease, waist_ease=waist_ease, clearance=clearance, thigh=thigh,
                                      thigh_fade=thigh_fade, thigh_lift=thigh_lift, thigh_back=thigh_back)
    report = _report(obj, prof)
    tailor._warn(obj, report, tailor.flesh_order_warnings(body))
    obj["wardrobe_cut_report"] = report
    return obj


def dress(body, name="Dress", neck=(-0.10, 0.08), sleeve=-0.10, length=1.0, flare=1.25, waist=0.30,
          bodice_ease=0.008, segments=64, ring_m=0.025, ease=0.010, clearance=0.02, smooth=4, thigh=1.0,
          thigh_fade=0.10, thigh_lift=0.08, thigh_back=0.0):
    """A bodice cut from the body down to the natural waist (`waist` torso lengths above the hips),
    eased, and a skirt hung from its hem. `sleeve` and `neck` are tailor.shirt's."""
    from . import tailor
    body = rigmap._obj(body)
    lv = levels(body)
    join_z = lv["hip_z"] + waist * lv["torso"]
    hem_z = hem_height(lv, length)
    tmp = tailor.shirt(body, name=name + "__bodice", sleeve=sleeve, hem=waist, neck=neck)
    try:
        bodice_rep = fit.ease(tmp, body, base=bodice_ease, loose=0.0, hang=1.0)
        bm = bmesh.new()
        bm.from_mesh(tmp.data)
        gnames = {vg.index: vg.name for vg in tmp.vertex_groups}
        deform = rigmap.deform_names(body)
        fixed = {v.index: {gnames[x.group]: x.weight for x in v.groups if gnames[x.group] in deform and x.weight > 0}
                 for v in tmp.data.vertices}
    finally:
        me = tmp.data
        bpy.data.objects.remove(tmp, do_unlink=True)
        bpy.data.meshes.remove(me)
    loops = fit.tag_loops(fit.boundary_loops(bm), "shirt")
    hem_loop = loops["hem"]
    probe = profile(body, join_z, hem_z, flare, segs=8, ring_m=0.2, lv=lv, blur=0)
    axis = probe["axis"]
    # the skirt may not start inside the eased bodice: its hem radius, by angle, is a floor
    floor = [0.0] * segments
    for v in hem_loop:
        j = int(round(_angle(axis, v.co) / (2 * math.pi) * segments)) % segments
        r = (Vector((v.co.x - axis.x, v.co.y - axis.y))).length - ease
        for dj in (-1, 0, 1):
            floor[(j + dj) % segments] = max(floor[(j + dj) % segments], r)
    top_z = min(v.co.z for v in hem_loop) - ring_m
    prof = profile(body, top_z, hem_z, flare, segs=segments, ring_m=ring_m, ease=ease, clearance=clearance,
                   floor=floor, lv=lv)
    rings = [_ring_verts(bm, prof["axis"], z, r) for z, r in prof["rings"]]
    zipped = _zip(bm, prof["axis"], hem_loop, rings[0])
    for a, b in zip(rings, rings[1:]):
        _bridge(bm, a, b)
    bm.verts.index_update()
    vw = weights(body, bm, fixed, prof, smooth=smooth, thigh=thigh, thigh_fade=thigh_fade, thigh_lift=thigh_lift,
                 thigh_back=thigh_back)
    obj = _new_object(body, name, bm, vw)
    obj["wardrobe_cut"] = _cut_record("dress", body, prof, lv, join_z, hem_z, waist=waist, length=length,
                                      flare=flare, ease=ease, clearance=clearance, sleeve=sleeve, neck=list(neck),
                                      bodice_ease=bodice_ease, thigh=thigh, thigh_fade=thigh_fade,
                                      thigh_lift=thigh_lift, thigh_back=thigh_back)
    report = _report(obj, prof)
    report.update(bodice_verts=len(fixed), zip_triangles=zipped, bodice_gap_median_m=bodice_rep["gap_median_m"])
    tailor._warn(obj, report, tailor.flesh_order_warnings(body))
    obj["wardrobe_cut_report"] = report
    return obj


def _cut_record(kind, body, prof, lv, top_z, hem_z, **params):
    rec = {"kind": kind, "body": body.name, "top_z": round(top_z, 5), "hem_z": round(hem_z, 5),
           "wide_z": round(prof["wide_z"], 5), "hip_z": round(lv["hip_z"], 5), "crotch_z": round(lv["crotch_z"], 5),
           "torso_m": round(lv["torso"], 5), "axis": [prof["axis"].x, prof["axis"].y],
           # cover hides no skin below the hip joints: below them the thighs swing and fold out from under a
           # skirt, and hidden crease skin showed through its front in a crouch
           "cover_floor_z": round(lv["hip_z"], 5),
           # nor any facing forward: the belly comes away from the waistband when the body folds in a crouch
           # (Mei's, Nadia's and Rosa's front belly showed there, open to 12 of 48 views)
           "cover_max_front": 0.5, "cover_front_top_z": round(top_z, 5)}
    for k, v in params.items():
        rec[k] = v
    return rec


def _report(obj, prof):
    return {"rings": len(prof["rings"]), "segments": len(prof["rings"][0][1]),
            "wide_z": round(prof["wide_z"], 4), "girth_wide_m": round(prof["girth_wide_m"], 4),
            "girth_hem_m": round(prof["girth_hem_m"], 4),
            "flare_measured": round(prof["girth_hem_m"] / max(prof["girth_wide_m"], 1e-6), 3),
            "outward_faces": _outward_share(obj, prof["axis"])}


def soft_body(garment, body, fabric="cotton", pin_below=0.02):
    """Route a skirt or dress to follow-through cloth (a SoftBody3D in Godot) instead of hem bones: every
    vertex from `pin_below` under the widest hip level up is pinned to its strongest bone, the rest hangs.
    Needs follow-through's scripts importable. Returns cloth.prepare's report."""
    try:
        from follow_through import cloth
    except ImportError as exc:
        raise ImportError("wardrobe's soft-body route needs follow-through's scripts on sys.path "
                          "(FT_SCRIPTS)") from exc
    g = rigmap._obj(garment)
    cut = g.get("wardrobe_cut")
    if cut is None or cut.get("kind") not in KINDS:
        raise ValueError(f"{g.name} is not a skirt or a dress from tailor")
    floor = float(cut["wide_z"]) - pin_below
    pins = [v.index for v in g.data.vertices if v.co.z >= floor]
    return cloth.prepare(g.name, fabric=fabric, cls="draped_tube", pins=pins, anchor="bone")
