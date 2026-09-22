"""A tail on a body that keeps its legs (08 fantasy species, layer 5: the body plan).

    tail.validate({"length": 0.6, "thickness": 0.14})      # standard library only
    rep = tail.apply(human, {"length": 0.6})               # on the rigged, warped body, after the leg plan

`graft.py` turns a pair of legs INTO a tail: it cuts the body at the hips and lofts a merfolk's tail where
the legs were. A gnoll or a satyr keeps its legs and grows a tail as well, so this is an addition, not a
replacement - but it is the same piece of work below the surface, and it uses graft's machinery: the boundary
loop left by removed faces (`graft._loops`), the free rectangle of the UV atlas (`graft._free_rect`), the
ring-by-ring loft and the shape-key flatten.

- **Where it leaves the body**: a patch of skin at the sacrum, `base` above the hip joints on the midline at
  the back. Its faces go, its boundary loop is the seam, and every vertex stays (hm08's vertex order is what
  the skin regions and the brow fits index, so nothing is ever renumbered - the exporter drops loose vertices).
- **The tail** is lofted along an arc: it leaves the body at `droop` degrees below horizontal and falls another
  `curve` degrees over its length, so it hangs behind and below the hips and clear of the legs. Its radius runs
  from `thickness` at the seam to `thickness * taper` at the tip (`PROFILE`), and its section morphs from the
  seam's own into a circle over the first third.
- **The rig**: `bones` bones down the arc, hung off the pelvis and named `tail.000`... - which is what
  `rig_analysis.bodymap` reads as a tail, so `motion.Body.pose_tail` curls and sways it and every gait swings
  it without another line of code. Each tail vertex is weighted to the two bones nearest it along the arc; the
  seam ring is shared half and half with the pelvis.
- **The check**: how near the tail comes to a leg at rest (`clearance`), reported in hip heights and refused
  when the tail starts inside a thigh. In motion the same question is rig-anything's
  (`verify.tail_clearance`), which measures it on every frame of every clip.

`follow-through` gives it its sway: the chain is an ordinary bone chain with skin on it, so its strand route
(hanging, 1D) takes it as it takes a ponytail.
"""

from __future__ import annotations

import json
import math

try:                     # validate() is standard library only: species_design and the spec check call it
    import numpy as np
except ImportError:      # pragma: no cover
    np = None

GROUP = "hf_tail"
ATTR = "hf_tail_surface"
PROP = "hf_tail"
KEYS = {"length", "thickness", "taper", "base", "droop", "curve", "bones", "rings", "tuft"}
# every length is a fraction of hip height, so a 1 m gnome's tail and a 2.6 m troll's are the same tail
DEFAULTS = {"length": 0.55, "thickness": 0.11, "taper": 0.12, "base": 0.12,
            "droop": 35.0, "curve": 30.0, "bones": 7, "rings": 18}
LIMITS = {"length": (0.15, 1.20), "thickness": (0.04, 0.35), "taper": (0.02, 0.60),
          "base": (-0.05, 0.25), "droop": (-20.0, 80.0), "curve": (-30.0, 90.0),
          "bones": (3, 16), "rings": (6, 40)}
# the radius along the tail, 0 at the seam to 1 at the tip, as a share of the run from `thickness` to
# `thickness * taper`: full at the root, then a steady draw down [folklore, animal tails]
PROFILE = [(0.0, 0.0), (0.12, 0.10), (0.35, 0.36), (0.7, 0.75), (1.0, 1.0)]
CLEAR_MIN = 0.02          # the tail's surface keeps this much of hip height off a leg's, at rest
CAP_RINGS = 3             # rings of the dome over the last one, so the tip is not a chisel


def normalise(spec):
    if spec is True:
        spec = {}
    out = dict(DEFAULTS)
    out.update(spec or {})
    return out


def validate(spec):
    """[] or the problems with a `tail` block, each naming its range. Standard library only."""
    if spec in (None, False):
        return []
    if spec is True:
        return []
    if not isinstance(spec, dict):
        return [f"tail must be a table ({', '.join(sorted(KEYS))}) or true, not {type(spec).__name__}"]
    out = [f"tail: unknown key {k!r} - it takes {', '.join(sorted(KEYS))}" for k in sorted(set(spec) - KEYS)]
    for k in ("length", "thickness", "taper", "base", "droop", "curve", "bones", "rings"):
        if k in spec:
            lo, hi = LIMITS[k]
            v = spec[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                unit = ("degrees below horizontal at the seam" if k == "droop" else
                        "degrees more over its length" if k == "curve" else
                        "bones in the chain" if k == "bones" else "rings down the loft" if k == "rings" else
                        "of hip height" if k in ("length", "thickness", "base") else "of its own base")
                out.append(f"tail.{k} = {v!r}: a number in {lo}..{hi} ({unit})")
    if "bones" in spec and isinstance(spec["bones"], (int, float)) and spec["bones"] != int(spec["bones"]):
        out.append(f"tail.bones = {spec['bones']!r}: a whole number of bones")
    return out


def _profile(t):
    ts = np.array([p[0] for p in PROFILE], float)
    vs = np.array([p[1] for p in PROFILE], float)
    return np.interp(t, ts, vs)


def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _arc(root, back, up, length, droop, curve, n):
    """`n` + 1 points down the tail's arc from `root`: it leaves at `droop` degrees below horizontal and falls
    another `curve` over its length."""
    pts = [np.asarray(root, float)]
    step = length / n
    for i in range(n):
        t = (i + 0.5) / n
        a = math.radians(droop + curve * t)
        d = back * math.cos(a) - up * math.sin(a)
        pts.append(pts[-1] + d / max(float(np.linalg.norm(d)), 1e-9) * step)
    return pts


def apply(human, spec, verbose=False):
    """Grow a tail on a rigged body, in place. Returns a report. Raises ValueError, with the range or the
    measurement in the message, when it cannot be built."""
    import bmesh
    import bpy
    from mathutils import Vector
    from . import body as _body, delta, graft
    from .species import _Rig

    problems = validate(spec)
    if problems:
        raise ValueError("; ".join(problems))
    g = normalise(spec)
    human = _body.obj(human)
    rig = _body.rig_of(human)
    if rig is None:
        raise ValueError(f"tail: {human.name} has no rig - a tail is grown after the rig (and the warp)")
    rep = {"flattened_keys": graft._flatten_keys(human)}
    rigd = _Rig(rig)
    if not rigd.legs:
        raise ValueError("tail: the rig has no legs off its pelvis - a tail in PLACE of the legs is graft.py")
    pelvis = rigd.spine[0]
    hip_z = float(np.mean([rig.data.bones[ch[0]].head_local.z for ch in rigd.legs.values()]))
    leg_bones = {n for ch in rigd.legs.values() for n in ch if n}

    me = human.data
    n_all = len(me.vertices)
    body_n = delta.BODY_VERTS
    co = np.empty(n_all * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)

    # ------------------------------------------------------------------ where it leaves the body
    root_z = hip_z * (1.0 + float(g["base"]))
    band = 0.05 * hip_z
    near = np.flatnonzero((np.abs(co[:body_n, 2] - root_z) < band) & (np.abs(co[:body_n, 0]) < 0.35 * hip_z))
    if not len(near):
        raise ValueError(f"tail: no skin at the sacrum ({root_z:.3f} m) - check `base`")
    back = int(near[np.argmax(co[near, 1])])                     # forward is -Y: the rearmost is the back
    root = co[back].copy()
    root[0] = 0.0
    radius = float(g["thickness"]) * hip_z
    up = np.array([0.0, 0.0, 1.0])
    backv = np.array([0.0, 1.0, 0.0])

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    drop = []
    for f in bm.faces:
        if not all(v.index < body_n for v in f.verts):
            continue
        c = np.array(f.calc_center_median())
        if c[1] <= root[1] - radius:                             # only the back of the body
            continue
        if float(np.linalg.norm(c - root)) < radius:
            drop.append(f)
    if not drop:
        bm.free()
        raise ValueError(f"tail: no face within {radius:.3f} m of the sacrum - raise `thickness`")
    dropped = set(drop)
    edges = []
    for f in drop:
        for e in f.edges:
            if any(ff not in dropped for ff in e.link_faces):
                edges.append((e.verts[0].index, e.verts[1].index))
    loops = graft._loops(edges)
    loops.sort(key=len, reverse=True)
    if not loops or len(loops[0]) < 6:
        bm.free()
        raise ValueError("tail: the patch at the sacrum left no ring to loft from - raise `thickness`")
    seam = loops[0]
    rep["seam_loops"] = [len(l) for l in loops]
    bmesh.ops.delete(bm, geom=drop, context="FACES_ONLY")
    loose = [e for e in bm.edges if not e.link_faces and all(v.index < body_n for v in e.verts)]
    bmesh.ops.delete(bm, geom=loose, context="EDGES_FACES")
    bm.verts.ensure_lookup_table()
    rep["faces_removed"] = len(drop)

    # ------------------------------------------------------------------ the seam ring, in the tail's frame
    sv = [bm.verts[i] for i in seam]
    P0 = np.array([tuple(v.co) for v in sv])
    centre0 = P0.mean(axis=0)
    a0 = math.radians(float(g["droop"]))
    axis = backv * math.cos(a0) - up * math.sin(a0)
    axis = axis / float(np.linalg.norm(axis))
    e1 = np.cross(axis, up)
    e1 = e1 / max(float(np.linalg.norm(e1)), 1e-9)
    e2 = np.cross(e1, axis)
    rel = P0 - centre0
    a = rel @ e1
    b = rel @ e2
    theta = np.arctan2(b, a)
    order = np.argsort(theta)
    sv = [sv[i] for i in order]
    a, b, theta = a[order], b[order], theta[order]
    r0 = np.hypot(a, b)
    r_base = float(np.mean(r0))
    M = len(sv)

    length = float(g["length"]) * hip_z
    K = int(g["rings"])
    joints = _arc(centre0, backv, up, length, float(g["droop"]), float(g["curve"]), K)
    r_tip = radius * float(g["taper"])
    rings = [sv]
    for k in range(1, K + 1):
        t = k / K
        c = joints[k]
        d = joints[k] - joints[k - 1]
        d = d / max(float(np.linalg.norm(d)), 1e-9)
        f1 = np.cross(d, up)
        f1 = f1 / max(float(np.linalg.norm(f1)), 1e-9)
        f2 = np.cross(f1, d)
        r = r_base + (r_tip - r_base) * float(_profile(t))
        e = float(_smooth(t / 0.35))
        pa = (1 - e) * a * (r / max(r_base, 1e-9)) + e * r * np.cos(theta)
        pb = (1 - e) * b * (r / max(r_base, 1e-9)) + e * r * np.sin(theta)
        pts = c[None, :] + pa[:, None] * f1[None, :] + pb[:, None] * f2[None, :]
        rings.append([bm.verts.new(tuple(p)) for p in pts])
    # A rounded tip. One apex a radius past the last ring leaves a chisel: a blunt polygonal stub, which is
    # what showed on the first tail from three metres. These are the rings of a hemisphere over the last one.
    d_end = joints[K] - joints[K - 1]
    d_end = d_end / max(float(np.linalg.norm(d_end)), 1e-9)
    f1 = np.cross(d_end, up)
    f1 = f1 / max(float(np.linalg.norm(f1)), 1e-9)
    f2 = np.cross(f1, d_end)
    for i in range(1, CAP_RINGS + 1):
        ang = (i / (CAP_RINGS + 1.0)) * (math.pi / 2)
        r = r_tip * math.cos(ang)
        c = joints[K] + d_end * (r_tip * math.sin(ang))
        pts = c[None, :] + (r * np.cos(theta))[:, None] * f1[None, :] + (r * np.sin(theta))[:, None] * f2[None, :]
        rings.append([bm.verts.new(tuple(p)) for p in pts])
    tip_v = bm.verts.new(tuple(joints[K] + d_end * r_tip))

    faces_new = []
    for r_a, r_b in zip(rings[:-1], rings[1:]):
        for j in range(M):
            jj = (j + 1) % M
            faces_new.append(bm.faces.new((r_a[j], r_a[jj], r_b[jj], r_b[j])))
    cap = []
    last = rings[-1]
    for j in range(M):
        cap.append(bm.faces.new((last[j], last[(j + 1) % M], tip_v)))
    faces_new.extend(cap)
    for f in faces_new:
        f.smooth = True
    bm.normal_update()
    probe = faces_new[M * (K // 2)]
    pc = np.array(probe.calc_center_median())
    ax = np.array(probe.normal)
    along = joints[K // 2 + 1] - joints[K // 2]
    radial = pc - joints[min(K // 2 + 1, K)]
    radial = radial - along * float(np.dot(radial, along)) / max(float(np.dot(along, along)), 1e-12)
    if float(np.dot(ax, radial)) < 0.0:
        for f in faces_new:
            f.normal_flip()
    bm.verts.index_update()

    # ------------------------------------------------------------------ UVs, in the atlas's free rectangle
    uvl = bm.loops.layers.uv.active
    rect = None
    if uvl is not None:
        new_faces = set(faces_new)
        uv_faces = [[tuple(l[uvl].uv) for l in f.loops] for f in bm.faces
                    if f not in new_faces and all(v.index < body_n for v in f.verts)]
        rect = graft._free_rect(uv_faces) or (0.0, 0.0, 0.05, 0.05)
        u0, v0, u1, v1 = rect
        for ri in range(len(rings) - 1):
            for j in range(M):
                f = faces_new[ri * M + j]
                for l in f.loops:
                    vi = l.vert
                    col = j if vi in (rings[ri][j], rings[ri + 1][j]) else j + 1
                    row = ri if vi in (rings[ri][j], rings[ri][(j + 1) % M]) else ri + 1
                    l[uvl].uv = (u0 + (u1 - u0) * col / M, v1 - (v1 - v0) * row / (len(rings) - 1))
        for cf in cap:
            for l in cf.loops:
                l[uvl].uv = (u0 + (u1 - u0) * 0.5, v0)
    rep["uv_rect"] = [round(float(x), 4) for x in rect] if rect else None
    seam_idx = [v.index for v in sv]                             # before the bmesh goes

    bm.to_mesh(me)
    bm.free()
    me.update()
    n_new = len(me.vertices)
    rep.update(root=[round(float(x), 4) for x in root], seam_verts=M, rings=K,
               tail_verts=n_new - n_all, length_m=round(length, 4),
               thickness_m=round(radius, 4), hip_height_m=round(hip_z, 4))

    # ------------------------------------------------------------------ the rig
    bpy.context.view_layer.objects.active = rig
    for o in bpy.context.selected_objects:
        o.select_set(False)
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    B = int(g["bones"])
    bj = _arc(centre0, backv, up, length, float(g["droop"]), float(g["curve"]), B)
    eb = rig.data.edit_bones
    names = []
    parent = eb[pelvis]
    for i in range(B):
        b = eb.new(f"tail.{i:03d}")
        b.head = Vector(tuple(bj[i]))
        b.tail = Vector(tuple(bj[i + 1]))
        b.roll = 0.0
        b.parent = parent
        b.use_connect = i > 0
        b.use_deform = True
        parent = b
        names.append(b.name)
    bpy.ops.object.mode_set(mode="OBJECT")
    rep["bones"] = names

    # ------------------------------------------------------------------ weights
    co2 = np.empty(n_new * 3)
    me.vertices.foreach_get("co", co2)
    co2 = co2.reshape(-1, 3)
    for nm in names:
        if nm not in human.vertex_groups:
            human.vertex_groups.new(name=nm)
    vg = {nm: human.vertex_groups[nm] for nm in names}
    gr = human.vertex_groups.get(GROUP) or human.vertex_groups.new(name=GROUP)
    J = np.array(bj)
    seg = J[1:] - J[:-1]
    seg_len = np.linalg.norm(seg, axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg_len)])
    total = float(cum[-1])

    def along(p):
        """Distance along the chain of the nearest point on it, 0 at the seam."""
        best, bs = 0.0, 1e30
        for i in range(len(seg)):
            d = seg[i]
            u = float(np.clip(np.dot(p - J[i], d) / max(np.dot(d, d), 1e-12), 0.0, 1.0))
            q = J[i] + d * u
            dist = float(np.linalg.norm(p - q))
            if dist < bs:
                bs, best = dist, float(cum[i] + u * seg_len[i])
        return best

    new_idx = list(range(n_all, n_new))
    for i in new_idx:
        v = me.vertices[i]
        for e in list(v.groups):
            gname = human.vertex_groups[e.group].name
            if gname != GROUP and gname in rig.data.bones:
                human.vertex_groups[e.group].remove([int(i)])
        s = along(co2[i]) / max(total, 1e-9) * B                 # 0 at the seam, B at the tip
        mid = float(np.clip(s - 0.5, 0.0, B - 1))
        i0 = int(math.floor(mid))
        f = mid - i0
        i1 = min(i0 + 1, B - 1)
        vg[names[i0]].add([int(i)], float(1 - f), "REPLACE")
        if i1 != i0:
            vg[names[i1]].add([int(i)], float(f), "REPLACE")
    # the seam ring carries the pelvis and the first tail bone half and half
    for i in seam_idx:
        vg[names[0]].add([int(i)], 0.5, "ADD")
    gr.add(new_idx, 1.0, "REPLACE")
    mark = np.zeros(n_new, np.float32)
    mark[n_all:] = 1.0
    if ATTR in me.attributes:
        me.attributes.remove(me.attributes[ATTR])
    me.attributes.new(ATTR, "FLOAT", "POINT").data.foreach_set("value", mark)
    for m in human.modifiers:
        if m.type == "MASK" and m.vertex_group and not m.invert_vertex_group:
            keepg = human.vertex_groups.get(m.vertex_group)
            if keepg is not None:
                keepg.add(new_idx, 1.0, "REPLACE")

    # ------------------------------------------------------------------ the check: clear of the legs at rest
    leg_v = []
    names_by_index = {v.index: v.name for v in human.vertex_groups}
    for v in me.vertices:
        # the body's own skin only: MPFB's helper geometry (past `body_n`) is masked out of every render
        # and every bake, and a helper sitting inside a thigh would read as a leg surface it is not
        if v.index >= body_n:
            continue
        for e in v.groups:
            if names_by_index.get(e.group) in leg_bones and e.weight > 0.5:
                leg_v.append(v.index)
                break
    gap = None
    if leg_v:
        L = co2[np.array(leg_v)]
        T = co2[n_all:]
        # the nearest leg vertex to each tail vertex, in blocks so a 20k x 3k distance matrix is never built
        best = 1e30
        for i in range(0, len(T), 256):
            blk = T[i:i + 256]
            d = np.linalg.norm(blk[:, None, :] - L[None, :, :], axis=2)
            best = min(best, float(d.min()))
        gap = best
    rep["leg_clearance"] = round(gap, 4) if gap is not None else None
    rep["leg_clearance_frac"] = round(gap / hip_z, 4) if gap is not None else None
    if gap is not None and gap < CLEAR_MIN * hip_z:
        raise ValueError(f"tail: it starts {gap * 1000:.0f} mm from a thigh ({gap / hip_z:.3f} of hip height, "
                         f"under {CLEAR_MIN}) - raise `base`, or lower `thickness` or `droop`")

    info = {"bones": names, "pelvis": pelvis, "root": rep["root"], "length_m": rep["length_m"],
            "thickness_m": rep["thickness_m"], "uv_rect": rep["uv_rect"], "first_new_vertex": n_all,
            "parameters": {k: g[k] for k in sorted(KEYS) if k in g}}
    human[PROP] = json.dumps(info)
    rig[PROP] = json.dumps({"tail": names, "pelvis": pelvis})
    if verbose:
        print("tail", len(names), "bones,", rep["tail_verts"], "verts, clearance", rep["leg_clearance"])
    return rep


def read(obj):
    """What `apply` left on a rig or a body, or None."""
    v = obj.get(PROP) if obj is not None else None
    return json.loads(v) if v else None
