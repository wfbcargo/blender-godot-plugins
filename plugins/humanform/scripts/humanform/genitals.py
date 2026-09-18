"""L4 part: adult external genitals on an MPFB body, as neutral figure-study anatomy (relaxed, at rest).

    rep = genitals.add(human, "male")                          # keep MPFB's shell, targets at neutral
    rep = genitals.add(human, "male", shape={"length": 0.4})    # MPFB's penis-length target, 0..1 (0.5 neutral)
    rep = genitals.add(human, "female")                         # a delta part: mons and labia majora relief
    rep = genitals.fuse(baked)                                  # male: after bake_for_game, one surface

**Male.** MPFB2's base mesh carries a shaft and scrotum shell, vertex group `helper-genital` (200 vertices,
182 quads, ~6 x 9 x 9 cm), open only where it sits on the crotch: one boundary loop of 34 vertices lying
within ~3 mm of the body's surface, weighted by MPFB ~91% to the pelvis. Its six targets
`genitals/penis-{length,circ,testicles}-{incr,decr}` move only those vertices. MPFB hides every helper behind
its "Hide helpers" Mask (group `body`) and rig-anything's `bake_for_game` applies that mask, so without this
module the shell is deleted.

`keep` (via `add`, on the unbaked body after the fit) loads the targets a `shape` asks for (as `hfg:` keys,
so `library.capture` never stores them), puts the shell into the mask's group so the bake keeps it, and marks
it with the point attribute `hf_genital`, which the bake carries. `fuse` then works on the baked mesh - no
shape keys, plain skin weights - before anything else (eyes, hair) is joined into it:

1. the shell is subdivided once (Catmull-Clark, weights, UVs and the mark interpolated): 11 mm quads read
   faceted in a lit close-up;
2. the body faces under the shell's footprint (its open loop's plane, +-4 cm) are cut out;
3. the hole's rim and the shell's loop are zipped with triangles merged by angle about the footprint's
   centre (the two loops differ in count, 20 vs 68 on the study man, so bmesh's `bridge_loops` leaves
   holes), paired into quads where they can be, wound to match their neighbours, and the seam relaxed;
4. each thigh's share of a shell vertex is held to `THIGH_SHARE`, fading in over `BLEND_M` from the join,
   the rest going to the pelvis, so the part rides the pelvis, not a leg.

The body stays one closed piece: the open-edge count after is the count before less the shell's loop. The cut
deletes a few hm08 body vertices, so hm08 indices do not hold on a fused mesh - which is baked, and nothing
reads them there (`delta` and `muscle` run before the bake).

**Female.** hm08's female crotch is a shallow mons cleft. `relief` adds a delta part (`delta`, the muscle
mechanism): a mons pubis pad and two labia majora pads either side of the midline cleft, heights along the
body's normals in groups `mons`, `labia`, `cleft`, authored from the body's own landmarks and scaled by
`strength`. It is a shape key `hfd:genital` the bake folds in. The body's resolution there (~2 cm edges)
carries soft forms, not detail - by design.
"""

from __future__ import annotations

import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from . import delta

HELPER = "helper-genital"
MASK_GROUP = "body"             # MPFB's "Hide helpers" mask keeps this group
KEY_PREFIX = "hfg:"
SHAPES = ("length", "circ", "testicles")
THIGH_SHARE = 0.06              # most a thigh may hold of a shell vertex away from the join
BLEND_M = 0.02                  # the join's own weights fade to the capped ones over this far from the loop
CLEAR_M = 0.006                 # the shell is moved to stand at least this far off a thigh's swept skin
MAX_PUSH_M = 0.015              # the most the sweep moves a shell vertex
SWEEP_FLEX_DEG = (-30, -10, 10, 30, 50, 75, 100)   # each thigh swung through these (forward positive) ...
SWEEP_ABD_DEG = (-10, 0, 12)                       # ... at these abductions (in negative) ...
SWEEP_TWIST_DEG = (-15, 0, 15)                     # ... and twists, the pelvis still
JOIN_KEEP_M = 0.015             # shell vertices this close to the join keep their place and the join's weights
REGION = "genital"
RELIEF_KEY = delta.KEY_PREFIX + REGION
ATTR = "hf_genital"             # point attribute marking the shell; survives the bake's mask and a subdivision


def _obj(o):
    return bpy.data.objects[o] if isinstance(o, str) else o


def helper_indices(human):
    g = human.vertex_groups.get(HELPER)
    if g is None:
        return []
    gi = g.index
    return [v.index for v in human.data.vertices if any(e.group == gi and e.weight > 0 for e in v.groups)]


# ------------------------------------------------------------------ male: keep the shell

def _target_path(stem):
    from . import scaffold
    _, _, _, LocationService = scaffold.services()
    path = os.path.join(LocationService.get_mpfb_data("targets"), "genitals", stem + ".target.gz")
    return path if os.path.exists(path) else None


def _shape(human, shape):
    """MPFB's genital targets at `shape` ({length|circ|testicles: 0..1}, 0.5 neutral): above 0.5 the
    `incr` target at (v - 0.5) * 2, below it the `decr` target at (0.5 - v) * 2."""
    from . import scaffold
    _, TargetService, _, _ = scaffold.services()
    out = {}
    for k, v in (shape or {}).items():
        if k not in SHAPES:
            raise ValueError(f"genital shape {k!r}: one of {SHAPES}")
        v = float(v)
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"genital shape {k} = {v}: 0..1, 0.5 neutral")
        for suffix, w in (("incr", max(0.0, (v - 0.5) * 2)), ("decr", max(0.0, (0.5 - v) * 2))):
            stem = f"penis-{k}-{suffix}"
            kb = human.data.shape_keys.key_blocks if human.data.shape_keys else None
            key = kb.get(KEY_PREFIX + stem) if kb else None
            if key is None and w > 0:
                path = _target_path(stem)
                if path is None:
                    raise FileNotFoundError(f"no MPFB target genitals/{stem}")
                key = TargetService.load_target(human, path, weight=0.0, name=KEY_PREFIX + stem)
            if key is not None:
                key.value = w
                out[stem] = round(w, 3)
    return out


def keep(human, shape=None):
    """Put the shell into the mask's kept group (and its targets on). Returns a report."""
    human = _obj(human)
    idx = helper_indices(human)
    if not idx:
        raise ValueError(f"{human.name} has no {HELPER} group (not an MPFB2 body?)")
    g = human.vertex_groups.get(MASK_GROUP)
    if g is None:
        raise ValueError(f"{human.name} has no {MASK_GROUP!r} group for MPFB's helper mask")
    g.add(idx, 1.0, "REPLACE")
    at = human.data.attributes.get(ATTR) or human.data.attributes.new(ATTR, "FLOAT", "POINT")
    mark = np.zeros(len(human.data.vertices), np.float32)
    mark[idx] = 1.0
    at.data.foreach_set("value", mark)
    targets = _shape(human, shape)
    human.data.update()
    human["hf_genitals"] = "male"
    return {"sex": "male", "shell_vertices": len(idx), "targets": targets}


# ------------------------------------------------------------------ male: one surface

def _loops(edges):
    """Closed vertex loops from a list of (a, b) boundary edges."""
    adj = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    seen, loops = set(), []
    for s in sorted(adj):
        if s in seen:
            continue
        loop, cur = [s], s
        seen.add(s)
        while True:
            nxt = [x for x in adj[cur] if x not in seen]
            if not nxt:
                break
            cur = nxt[0]
            seen.add(cur)
            loop.append(cur)
        loops.append(loop)
    return loops


def _inside_2d(pts, poly):
    """Even-odd point-in-polygon for (N, 2) points against an (M, 2) polygon."""
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        cross = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi)
        inside ^= cross
        j = i
    return inside


def _walk(edges):
    """One closed loop of BMVerts, in order, from its BMEdges."""
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    if not adj or any(len(x) != 2 for x in adj.values()):
        raise RuntimeError("genitals: the cut's rim is not one simple loop")
    start = min(adj, key=lambda v: v.index)
    loop, prev, cur = [start], None, start
    while True:
        nxt = adj[cur][0] if adj[cur][0] is not prev else adj[cur][1]
        if nxt is start:
            break
        loop.append(nxt)
        prev, cur = cur, nxt
    if len(loop) != len(adj):
        raise RuntimeError(f"genitals: the cut left more than one rim ({len(loop)} of {len(adj)} vertices)")
    return loop


def _zipper(bm, a, b, c, u, w, pos):
    """Triangles joining two closed loops of BMVerts (the shell's `a` inside the rim `b`): both turned the same
    way round in the footprint plane (c, u, w) and merged by their angle about the footprint's centre, so the
    fan follows the loops round instead of cutting across. Returns the new faces."""
    cv, uv_, wv = Vector(c), Vector(u), Vector(w)

    def ang(v):
        d = pos[v] - cv
        return float(np.arctan2(d.dot(wv), d.dot(uv_)))

    def area(loop):
        p = np.array([[(pos[v] - cv).dot(uv_), (pos[v] - cv).dot(wv)] for v in loop])
        return 0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))
    if area(a) < 0:
        a = a[::-1]
    if area(b) < 0:
        b = b[::-1]
    two_pi = 2 * np.pi
    t0 = ang(a[0])
    k = min(range(len(b)), key=lambda j: abs((ang(b[j]) - t0 + np.pi) % two_pi - np.pi))
    b = b[k:] + b[:k]
    ta = [(ang(v) - t0) % two_pi for v in a] + [two_pi]
    ta[0] = 0.0
    d0 = (ang(b[0]) - t0 + np.pi) % two_pi - np.pi
    tb = [d0 + (ang(v) - ang(b[0])) % two_pi for v in b] + [d0 + two_pi]
    tb[0] = d0
    m, n = len(a), len(b)
    i = j = 0
    faces = []
    while i < m or j < n:
        ai, bj = a[i % m], b[j % n]
        adv_a = j >= n or (i < m and ta[i + 1] <= tb[j + 1])
        tri = (ai, a[(i + 1) % m], bj) if adv_a else (ai, b[(j + 1) % n], bj)
        if adv_a:
            i += 1
        else:
            j += 1
        faces.append(bm.faces.new(tri))
    return faces


def _deform_groups(human):
    rig = human.parent if human.parent is not None and human.parent.type == "ARMATURE" else None
    if rig is None:
        for m in human.modifiers:
            if m.type == "ARMATURE" and m.object is not None:
                rig = m.object
    return rig, ({b.name for b in rig.data.bones if b.use_deform} if rig is not None else set())


def _shell_mask(me):
    """Per-vertex bool: the vertex is the shell's (the `ATTR` point attribute `keep` wrote, which the bake's mask
    and a subdivision carry)."""
    at = me.attributes.get(ATTR)
    if at is None or at.domain != "POINT":
        return np.zeros(len(me.vertices), bool)
    v = np.empty(len(me.vertices), np.float32)
    at.data.foreach_get("value", v)
    return v > 0.5


def _mesh_co(me):
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def _subdivide_shell(ob, levels):
    """Replace the shell's faces with a Catmull-Clark subdivision of them (weights, UVs and the attribute
    interpolated by the modifier): the shell split off into a temporary object, subdivided, joined back."""
    me = ob.data
    shell = _shell_mask(me)
    tmp_me = me.copy()
    bm = bmesh.new()
    bm.from_mesh(tmp_me)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not shell[v.index]], context="VERTS")
    bm.to_mesh(tmp_me)
    bm.free()
    tmp = bpy.data.objects.new(ob.name + "_hfg_tmp", tmp_me)
    for g in ob.vertex_groups:
        tmp.vertex_groups.new(name=g.name)
    for coll in ob.users_collection:
        coll.objects.link(tmp)
    tmp.matrix_world = ob.matrix_world
    sub = tmp.modifiers.new("sub", "SUBSURF")
    sub.levels = sub.render_levels = levels
    sub.boundary_smooth = "PRESERVE_CORNERS"
    sub.uv_smooth = "PRESERVE_BOUNDARIES"
    dg = bpy.context.evaluated_depsgraph_get()
    out = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    tmp.modifiers.remove(sub)
    old = tmp.data
    tmp.data = out
    bpy.data.meshes.remove(old)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if shell[v.index]], context="VERTS")
    bm.to_mesh(me)
    bm.free()
    with bpy.context.temp_override(active_object=ob, selected_editable_objects=[ob, tmp], object=ob,
                                   selected_objects=[ob, tmp]):
        bpy.ops.object.join()
    return len(out.polygons)


def _orient(new_faces):
    """Wind each new face so every edge it shares with a settled face runs the other way round in it."""
    new = set(new_faces)
    settled = set()
    todo = list(new_faces)
    for _ in range(len(todo) + 1):
        left = []
        for f in todo:
            ref = None
            for lo in f.loops:
                for g_lo in lo.edge.link_loops:
                    if g_lo.face is not f and (g_lo.face not in new or g_lo.face in settled):
                        ref = (lo, g_lo)
                        break
                if ref:
                    break
            if ref is None:
                left.append(f)
                continue
            lo, g_lo = ref
            if lo.vert is g_lo.vert:            # both run the edge the same way: f is wound backwards
                f.normal_flip()
            settled.add(f)
        if not left or len(left) == len(todo):
            break
        todo = left


def fuse(ob, levels=1, smooth=2):
    """On the baked body (after `bake_for_game`, before anything else joins it): subdivide the shell `levels`
    times, cut its footprint out of the body and zip the hole's rim to the shell's open loop, then relax the
    seam `smooth` times. Returns a report (loops, faces cut and made, open edges on the body before and after,
    the shell's bone shares)."""
    ob = _obj(ob)
    if ob.get("hf_genitals_fused"):
        return {"note": "already fused"}
    if not _shell_mask(ob.data).any():
        raise ValueError(f"{ob.name} carries no genital shell (run genitals.keep on the unbaked body)")

    def open_edges(bm):
        return sum(1 for e in bm.edges if len(e.link_faces) == 1)

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    before = open_edges(bm)
    bm.free()
    shell_faces_n = _subdivide_shell(ob, levels) if levels else None
    me = ob.data
    co = _mesh_co(me)
    shell = _shell_mask(me)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    sedges = [e for e in bm.edges if len(e.link_faces) == 1 and all(shell[v.index] for v in e.verts)]
    sloop = _walk(sedges)
    lp = co[[v.index for v in sloop]]
    c = lp.mean(axis=0)
    _, _, vt = np.linalg.svd(lp - c)
    n, u, w = vt[2], vt[0], vt[1]
    poly = np.stack([(lp - c) @ u, (lp - c) @ w], axis=1)

    def inside(p):
        r = p - c
        return (np.abs(r @ n) < 0.04) & _inside_2d(np.stack([r @ u, r @ w], axis=1), poly)

    body_ins = ~shell & inside(co)
    fc = np.array([co[[v.index for v in f.verts]].mean(axis=0) for f in bm.faces])
    fshell = np.array([all(shell[v.index] for v in f.verts) for f in bm.faces])
    fin = inside(fc) & ~fshell
    cut_faces = {f for f in bm.faces if not fshell[f.index] and
                 (fin[f.index] or any(body_ins[v.index] for v in f.verts))}
    if not cut_faces:
        bm.free()
        raise RuntimeError("genitals: no body faces under the shell's footprint")
    rim = {e for f in cut_faces for e in f.edges if any(g not in cut_faces for g in e.link_faces)}
    pos = {v: Vector(co[v.index]) for v in bm.verts}
    n_cut = len(cut_faces)
    dead = {v for f in cut_faces for v in f.verts if all(g in cut_faces for g in v.link_faces)}
    bmesh.ops.delete(bm, geom=list(cut_faces), context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[e for e in bm.edges if not e.link_faces], context="EDGES")
    gone = [v for v in dead if v.is_valid and not v.link_faces]
    n_gone = len(dead)
    bmesh.ops.delete(bm, geom=gone, context="VERTS")
    bm.verts.index_update()
    rim_loop = _walk(sorted((e for e in rim if e.is_valid and len(e.link_faces) == 1),
                            key=lambda e: (e.verts[0].index, e.verts[1].index)))
    new_faces = _zipper(bm, sloop, rim_loop, c, u, w, pos)
    _orient(new_faces)
    join = bmesh.ops.join_triangles(bm, faces=new_faces, cmp_seam=False, cmp_sharp=False, cmp_uvs=False,
                                    cmp_vcols=False, cmp_materials=False, angle_face_threshold=3.14159,
                                    angle_shape_threshold=3.14159)
    keep_new = set(join["faces"]) | set(new_faces)
    new_faces = [f for f in bm.faces if f in keep_new]
    uv = bm.loops.layers.uv.active
    newset = set(new_faces)
    for f in new_faces:
        f.smooth = True
        mats = [g.material_index for e in f.edges for g in e.link_faces if g not in newset]
        if mats:
            f.material_index = max(set(mats), key=mats.count)
        if uv is not None:
            for lo in f.loops:
                other = next((x for x in lo.vert.link_loops if x.face not in newset), None)
                if other is not None:
                    lo[uv].uv = other[uv].uv
    # relax the seam: the zipped strip's vertices and one ring either side
    seam = {v for f in new_faces for v in f.verts}
    ring = {x for v in seam for e in v.link_edges for x in e.verts}
    for _ in range(smooth):
        bmesh.ops.smooth_vert(bm, verts=sorted(ring, key=lambda v: v.index), factor=0.5,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)
    after = open_edges(bm)
    n_new, n_quads = len(new_faces), sum(1 for f in new_faces if len(f.verts) == 4)
    rim_n, loop_n = len(rim_loop), len(sloop)
    bm.to_mesh(me)
    bm.free()
    me.update()
    weights = _pelvis_weights(ob)
    ob["hf_genitals_fused"] = True
    return {"shell_loop": loop_n, "rim": rim_n, "shell_faces": shell_faces_n, "cut_faces": n_cut,
            "cut_vertices": n_gone, "seam_faces": n_new, "seam_quads": n_quads,
            "open_edges_before": before, "open_edges_after": after, "weights": weights}


def _dominant(me, names):
    """Per vertex, the deform group (by name) holding most of it, or None."""
    out = [None] * len(me.vertices)
    for v in me.vertices:
        best = max((e for e in v.groups if e.group in names), key=lambda e: e.weight, default=None)
        if best is not None:
            out[v.index] = names[best.group]
    return out


def _sweep_push(ob, rig, shell, join_d, pelvis, thighs, names):
    """How far each shell vertex must move (a vector in the body's rest frame) to stand CLEAR_M off every
    thigh's skin as the thighs swing through SWEEP poses with the pelvis still: each thigh posed in turn (the
    other at rest), the body evaluated through its Armature, the thigh-dominated skin taken back into the
    pelvis's rest frame, and each shell vertex measured against it. Moves are capped at MAX_PUSH_M: past that
    the thighs meet the shell only in a deep crouch, where a real one is squeezed too."""
    from mathutils.bvhtree import BVHTree
    me = ob.data
    co = _mesh_co(me)
    idx = [int(i) for i in np.nonzero(shell)[0] if join_d[i] >= JOIN_KEEP_M]
    dom = _dominant(me, names)
    push = np.zeros((len(co), 3))
    pb_p = rig.pose.bones.get(pelvis)
    saved = {}
    for t in thighs:
        pb = rig.pose.bones.get(t)
        if pb is not None:
            saved[t] = (pb.rotation_mode, tuple(pb.rotation_euler), tuple(pb.rotation_quaternion))
    prev_pos = rig.data.pose_position
    rig.data.pose_position = "POSE"
    poses = 0
    try:
        for t in thighs:
            pb = rig.pose.bones.get(t)
            if pb is None:
                continue
            faces = [p.vertices[:] for p in me.polygons
                     if not any(shell[i] for i in p.vertices) and all(dom[i] == t for i in p.vertices)]
            if not faces:
                continue
            knee_rest = rig.matrix_world @ pb.bone.tail_local
            side_push = np.zeros((len(co), 3))
            for flex, abd, twist in ((f, a, w) for f in SWEEP_FLEX_DEG for a in SWEEP_ABD_DEG
                                     for w in SWEEP_TWIST_DEG):
                pb.rotation_mode = "XYZ"
                rx, rz = np.radians(flex), np.radians(abd)
                # forward is whichever sign carries the knee to -y; out is whichever carries it off the midline
                pb.rotation_euler = (rx, np.radians(twist), rz)
                bpy.context.view_layer.update()
                knee = rig.matrix_world @ pb.tail
                if flex and (knee.y > knee_rest.y) == (flex > 0):
                    rx = -rx
                if abd and (abs(knee.x) < abs(knee_rest.x)) == (abd > 0):
                    rz = -rz
                pb.rotation_euler = (rx, np.radians(twist), rz)
                bpy.context.view_layer.update()
                dg = bpy.context.evaluated_depsgraph_get()
                ev = ob.evaluated_get(dg)
                em = ev.to_mesh()
                pco = _mesh_co(em)
                ev.to_mesh_clear()
                if len(pco) != len(co):
                    continue
                # back into the pelvis's rest frame (the pelvis is at rest here, so this is the identity
                # unless a constraint moved it)
                if pb_p is not None:
                    m = np.array(pb_p.bone.matrix_local @ pb_p.matrix.inverted())
                    pco = pco @ m[:3, :3].T + m[:3, 3]
                bvh = BVHTree.FromPolygons([Vector(c) for c in pco], faces)
                poses += 1
                for i in idx:
                    p = Vector(co[i])
                    loc, nrm, _, _ = bvh.find_nearest(p)
                    if loc is None:
                        continue
                    s = (p - loc).dot(nrm)
                    if s < CLEAR_M:
                        need = np.asarray(nrm) * min(CLEAR_M - s, MAX_PUSH_M)
                        if np.linalg.norm(need) > np.linalg.norm(side_push[i]):
                            side_push[i] = need
            # each thigh's own largest move, the two added: a vertex both thighs reach (the scrotum's floor)
            # is moved away from both instead of towards whichever pushed hardest
            push += side_push
    finally:
        for t, (mode, eul, q) in saved.items():
            pb = rig.pose.bones[t]
            pb.rotation_mode = mode
            pb.rotation_euler = eul
            pb.rotation_quaternion = q
        rig.data.pose_position = prev_pos
        bpy.context.view_layer.update()
    return push, poses


def _apply_push(ob, shell, join_d, push, iterations=6):
    """Apply the clearance move, smoothed over the shell so no dent shows (each pass averages the move with the
    shell neighbours' and keeps whichever is larger, so every contact is still cleared), fading to nothing at
    the join. Returns the largest move and how many vertices needed one."""
    me = ob.data
    co = _mesh_co(me)
    idx = np.nonzero(shell)[0]
    pushed = int(np.count_nonzero(np.linalg.norm(push, axis=1) > 1e-6))
    if not pushed:
        return {"pushed": 0, "max_mm": 0.0}
    need = push.copy()
    disp = push.copy()
    nb = {int(i): [] for i in idx}
    for e in me.edges:
        a, b = e.vertices
        if shell[a] and shell[b]:
            nb[a].append(b)
            nb[b].append(a)
    for _ in range(iterations):
        new = disp.copy()
        for i in idx:
            if join_d[i] < JOIN_KEEP_M or not nb[int(i)]:
                continue
            avg = disp[nb[int(i)]].mean(axis=0)
            new[i] = avg if np.linalg.norm(avg) > np.linalg.norm(need[i]) else need[i] + 0.5 * (avg - need[i])
        disp = new
    ramp = np.clip((join_d - JOIN_KEEP_M) / JOIN_KEEP_M, 0.0, 1.0)
    ramp[~np.isfinite(ramp)] = 0.0
    disp *= ramp[:, None]
    me.vertices.foreach_set("co", (co + disp).ravel())
    me.update()
    return {"pushed": pushed, "max_mm": round(float(np.linalg.norm(disp, axis=1).max()) * 1000, 1)}


def _pelvis_weights(ob):
    """The shell's skin and its clearance from the thighs. The pelvis carries it; each thigh's share is held to
    THIGH_SHARE away from the join (fading in over BLEND_M). Giving the thighs more where they touch it was
    tried (up to 0.8 by contact distance): it halved the walk's intersection but lifted the scrotum's sides
    with the thighs in a crouch into spikes at the join. So the shell is instead moved clear of where the
    thighs sweep (`_sweep_push`), with the pelvis still. Returns the shell's summed shares and the move."""
    rig, deform = _deform_groups(ob)
    me = ob.data
    shell_mask = _shell_mask(me)
    shell = np.nonzero(shell_mask)[0]
    if not deform or not len(shell):
        return None
    names = {g.index: g.name for g in ob.vertex_groups if g.name in deform}
    tot = {}
    for i in shell:
        for e in me.vertices[i].groups:
            if e.group in names:
                tot[names[e.group]] = tot.get(names[e.group], 0.0) + e.weight
    if not tot:
        return None
    pelvis = max(tot, key=tot.get)
    thighs = sorted(k for k in tot if k != pelvis)
    sset = set(int(i) for i in shell)
    co = _mesh_co(me)
    # the join: shell vertices with a neighbour off the shell
    join = sorted({a for e in me.edges for a, b in (tuple(e.vertices), tuple(e.vertices)[::-1])
                   if a in sset and b not in sset})
    lp = co[join] if join else co[shell[:1]]
    join_d = np.full(len(co), np.inf)
    for i in shell:
        join_d[i] = float(np.min(np.linalg.norm(lp - co[i], axis=1)))
    push, poses = _sweep_push(ob, rig, shell_mask, join_d, pelvis, thighs, names) if rig is not None else (None, 0)
    clearance = _apply_push(ob, shell_mask, join_d, push) if push is not None else {"pushed": 0, "max_mm": 0.0}
    clearance["poses"] = poses
    out = {}
    for i in shell:
        t = min(1.0, join_d[i] / BLEND_M)
        ws = {names[e.group]: e.weight for e in me.vertices[i].groups if e.group in names}
        s = sum(ws.values()) or 1.0
        ws = {k: v / s for k, v in ws.items()}
        capped = {k: (min(v, THIGH_SHARE) if k in thighs else v) for k, v in ws.items()}
        rest = 1.0 - sum(v for k, v in capped.items() if k != pelvis)
        capped[pelvis] = max(rest, 0.0)
        for k in set(ws) | set(capped):
            v = (1 - t) * ws.get(k, 0.0) + t * capped.get(k, 0.0)
            ob.vertex_groups[k].add([int(i)], v, "REPLACE")
            out[k] = out.get(k, 0.0) + v
    s = sum(out.values()) or 1.0
    return {"bone": pelvis, "shares": {k: round(v / s, 3) for k, v in sorted(out.items())},
            "clearance": clearance}


# ------------------------------------------------------------------ female: relief

def _gauss(p, centre, radii):
    d = (p - np.asarray(centre)) / np.asarray(radii)
    return np.exp(-0.5 * np.einsum("ij,ij->i", d, d))


def relief_card(human):
    """The female relief authored on this body's own landmarks: {group: heights (m, BODY_VERTS)} in an
    in-memory delta card (reference: this body's stature, so it applies at scale 1)."""
    human = _obj(human)
    co = delta.mixed_coords(human)[:delta.BODY_VERTS]
    st = delta.stature_of(co)
    z0 = co[:, 2].min()
    k = st / 1.67
    # the crotch: the lowest body point on the midline between the legs, at hip height's band
    mid = np.abs(co[:, 0]) < 0.006 * k
    band = mid & (co[:, 2] - z0 > 0.40 * st) & (co[:, 2] - z0 < 0.56 * st)
    crotch = co[band][np.argmin(co[band][:, 2])]
    # the front surface on the midline above it
    front = mid & (co[:, 2] > crotch[2]) & (co[:, 2] < crotch[2] + 0.12 * k) & (co[:, 1] < crotch[1])
    fy = float(co[front][:, 1].min()) if front.any() else crotch[1] - 0.05 * k
    y = lambda z: np.interp(z, co[front][:, 2][np.argsort(co[front][:, 2])],  # noqa: E731
                            co[front][:, 1][np.argsort(co[front][:, 2])]) if front.any() else fy
    zc = crotch[2]
    mons_c = (0.0, float(y(zc + 0.075 * k)), zc + 0.075 * k)
    lab_z = zc + 0.03 * k
    lab_c = lambda s: (s * 0.014 * k, float(y(lab_z)), lab_z)  # noqa: E731
    front_side = co[:, 1] < crotch[1] + 0.02 * k
    mons = 0.0045 * k * _gauss(co, mons_c, (0.045 * k, 0.04 * k, 0.03 * k)) * front_side
    lab = 0.0035 * k * (_gauss(co, lab_c(1), (0.011 * k, 0.03 * k, 0.03 * k)) +
                        _gauss(co, lab_c(-1), (0.011 * k, 0.03 * k, 0.03 * k))) * front_side
    cleft = -0.0015 * k * _gauss(co, (0.0, float(y(lab_z)), lab_z), (0.005 * k, 0.03 * k, 0.03 * k)) * front_side
    groups = {"mons": mons, "labia": lab, "cleft": cleft}
    faces = delta.body_faces(human)
    groups = {g: delta.smooth(h, faces, iterations=1, share=0.4) for g, h in groups.items()}
    payload = {"type": "delta", "frame": "normal", "unit": "um", "reference": {"stature_m": round(st, 4)},
               "groups": {g: delta.pack(h) for g, h in sorted(groups.items())}}
    return {"kind": "part", "region": REGION, "name": "relief-v1", "id": None, "payload": payload,
            "landmarks": {"crotch": [round(float(x), 4) for x in crotch], "mons": [round(x, 4) for x in mons_c]}}


def relief(human, strength=1.0):
    human = _obj(human)
    card = relief_card(human)
    w = {g: float(strength) for g in card["payload"]["groups"]}
    rep = delta.apply(human, card, weights=w, mode="key", value=1.0, key_name=RELIEF_KEY)
    human["hf_genitals"] = "female"
    return {"sex": "female", "key": RELIEF_KEY, "max_mm": rep["max_mm"], "groups": rep["groups"],
            "landmarks": card["landmarks"], "strength": float(strength)}


# ------------------------------------------------------------------ entry

def add(human, sex, shape=None, strength=1.0):
    """The part for `sex` on an unbaked MPFB body: male keeps the shell (then `fuse` before the bake), female
    adds the relief key. Returns a report."""
    if sex == "male":
        return keep(human, shape)
    if sex == "female":
        if shape:
            raise ValueError("genital shape targets are MPFB's male ones")
        return relief(human, strength)
    raise ValueError(f"sex must be 'male' or 'female', not {sex!r}")
