"""L4 part: adult external genitals on an MPFB body, as neutral figure-study anatomy (relaxed, at rest).

    rep = genitals.add(human, "male")                          # keep MPFB's shell, targets at neutral
    rep = genitals.add(human, "male", shape={"length": 0.4})    # MPFB's penis-length target, 0..1 (0.5 neutral;
                                                                # 0..1 is an adult's range, SHAPE_SPAN_M)
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
   faceted in a lit close-up; then its flat rim is dropped (`_trim_flush`: the flap MPFB spreads over the
   crotch ~1 mm off the skin, out into both groin folds), so it joins the body where it stands out of it and
   the body keeps its own crotch skin - with the flap on the pelvis, a thigh went 23 mm into it in a crouch;
2. the body faces under the shell's footprint (its open loop's plane, +-4 cm) are cut out;
3. the hole's rim and the shell's loop are zipped with triangles merged by angle about the footprint's
   centre (the two loops differ in count, 20 vs 68 on the study man, so bmesh's `bridge_loops` leaves
   holes), paired into quads where they can be, wound to match their neighbours, and the seam relaxed;
4. each thigh's share of a shell vertex is held to `THIGH_SHARE`, fading in over `BLEND_M` from the join,
   the rest going to the pelvis, so the part rides the pelvis, not a leg.

The body stays one closed piece: the open-edge count after is the count before less the shell's loop. The cut's
inner body vertices stay behind as loose points (glTF exports none of them), so every hm08 index still holds on
the fused mesh: skin regions, brows, lashes and landmarks read MPFB's index lists after the bake.

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
from mathutils import Matrix, Vector

from . import delta

HELPER = "helper-genital"
MASK_GROUP = "body"             # MPFB's "Hide helpers" mask keeps this group
KEY_PREFIX = "hfg:"
SHAPES = ("length", "circ", "testicles")
# What 0 and 1 of a `shape` value mean, each side of 0.5 (MPFB's neutral): at most this far, in metres, of the
# furthest vertex's move. MPFB's own targets at full weight are far past an adult's range - penis-length-incr
# moves the tip 16.2 cm (a 9 cm shaft to 25 cm), -decr 3.6 cm; -circ 9 / 6 mm; -testicles 4.3 / 2.9 cm - and
# 1.0 used to be the whole target. Now 0..1 spans a flaccid adult's range round the neutral (length ~6-12 cm).
SHAPE_SPAN_M = {"length": 0.03, "circ": 0.0025, "testicles": 0.012}
MPFB_UNIT_M = 0.1               # MakeHuman's targets are in decimetres
THIGH_SHARE = 0.06              # most a thigh may hold of a shell vertex away from the join
BLEND_M = 0.02                  # the join's own weights fade to the capped ones over this far from the loop
CLEAR_M = 0.006                 # the shell is moved to stand at least this far off a thigh's swept skin
MAX_PUSH_M = 0.015              # the most the sweep moves a shell vertex
# The bake-time clearance is taken at rest only. Sweeping each thigh through 126 poses (flexion to 100 deg)
# and adding both thighs' pushes pinched the scrotum from both sides to half MPFB's width (width/height 0.23
# at 10% of its height against the helper's 0.54) and still left the walk 15 mm inside a thigh: static
# geometry cannot clear a thigh that moves. The moving thighs are cleared per clip frame instead
# (`clear_thighs`, corrective bones keyed in the clips).
SWEEP_FLEX_DEG = (0,)
SWEEP_ABD_DEG = (0,)
SWEEP_TWIST_DEG = (0,)
SIDE_BONE = "hf_genital"        # hf_genital.L / .R: the shell's halves, keyed per clip frame off the thighs
SIDE_ROLE = "genital_clearance"  # tagged ft_role so rig-anything's body map skips them like jiggle bones
SIDE_SHARE = 0.9                # the most the two side bones hold of a shell vertex, away from the join
SIDE_FADE_M = (0.006, 0.026)    # side weight fades in from 0 at this far from the join to full at that far
SIDE_SPLIT_M = 0.012            # the halves cross over the midline across +-this (the shaft rides both)
KEY_CLEAR_M = 0.0015            # each keyed frame stands the scrotum this far off the thigh skin
KEY_MAX_M = 0.05                # most a side bone moves (0.03 held the study man's run 15 mm inside, on the cap)
SWING_DEG = (0, 8, 16, 24, 32)   # the common escape searched: a forward swing of both halves about their roots ...
ESCAPE_M = (0.0, 0.01, 0.02, 0.03, 0.04)  # ... and forward (and the first two, down) travel
ESCAPE_COST = 0.5               # shortfall (m summed over vertices) one metre of escape travel is worth
ESCAPE_AFTER_M = 0.01           # the escape is searched only when moving apart leaves this much shortfall
ROT_ARM_M = 0.04                # a turn of 1 rad costs what this much travel does (about the scrotum's length)
SQUASH_MAX_M = 0.03             # most the two halves close on each other (the scrotum's ~5 cm to ~2 cm)
CLEAR_LIMIT_MM = 15.0           # the gate: the deepest a thigh may go into the part in any clip (verify.crotch_clearance
                                # part_mm). At 0.4 m in Godot a thigh 1.5 cm into a ~5 cm scrotum reads as soft contact,
                                # a thigh pressing it aside; past that the part is seen passing through the leg
UV_SAME_ISLAND = 0.03          # seam UVs further apart than this (0..1 atlas) are on different islands
FLUSH_M = 0.003                 # shell faces this close to the body from the open loop inward are its flap (`_trim_flush`)
JOIN_KEEP_M = 0.015             # shell vertices this close to the join keep their place and the join's weights
REGION = "genital"
RELIEF_KEY = delta.KEY_PREFIX + REGION
ATTR = "hf_genital"             # point attribute marking the shell; survives the bake's mask and a subdivision
ATTR_SCROTUM = "hf_genital_scrotum"  # 0 shaft .. 1 scrotum, from which of MPFB's targets moves the vertex


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
    """MPFB's genital targets at `shape` ({length|circ|testicles: 0..1}, 0.5 neutral): above 0.5 the `incr`
    target, below it the `decr` one, weighted so 0 and 1 move the furthest vertex SHAPE_SPAN_M (a weight of
    at most 1: a `decr` target shorter than its span stops there)."""
    from . import scaffold
    _, TargetService, _, _ = scaffold.services()
    out = {}
    for k, v in (shape or {}).items():
        if k not in SHAPES:
            raise ValueError(f"genital shape {k!r}: one of {SHAPES}")
        v = float(v)
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"genital shape {k} = {v}: 0..1, 0.5 neutral")
        for suffix, t in (("incr", max(0.0, (v - 0.5) * 2)), ("decr", max(0.0, (0.5 - v) * 2))):
            stem = f"penis-{k}-{suffix}"
            reach = max(_target_deltas(stem).values(), default=0.0) * MPFB_UNIT_M
            w = min(1.0, t * SHAPE_SPAN_M[k] / reach) if reach > 0 else 0.0
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


def _target_deltas(stem):
    import gzip
    path = _target_path(stem)
    out = {}
    if path is None:
        return out
    with gzip.open(path, "rt") as fh:
        for line in fh:
            f = line.split()
            if len(f) == 4 and not line.startswith("#"):
                out[int(f[0])] = float(np.linalg.norm([float(x) for x in f[1:]]))
    return out


def _scrotum_score(human, idx):
    """Per body vertex, 0 on the shaft .. 1 on the scrotum: MPFB's `penis-testicles` target moves only the
    scrotum and `penis-length` / `penis-circ` only the shaft, so the share of a vertex's movement that is the
    testicles target's says which it is; vertices none of them move take their neighbours' (diffused over
    the shell), and the result is smoothed twice."""
    n = len(human.data.vertices)
    t = _target_deltas("penis-testicles-incr")
    s = {k: v for stem in ("penis-length-incr", "penis-circ-incr") for k, v in _target_deltas(stem).items()}
    score = np.zeros(n, np.float32)
    known = np.zeros(n, bool)
    for i in idx:
        a, b = t.get(i, 0.0), s.get(i, 0.0)
        if a + b > 1e-6:
            score[i], known[i] = a / (a + b), True
    sset = set(idx)
    nb = {i: [] for i in idx}
    for e in human.data.edges:
        a, b = e.vertices
        if a in sset and b in sset:
            nb[a].append(b)
            nb[b].append(a)
    for _ in range(40):
        todo = [i for i in idx if not known[i] and any(known[j] for j in nb[i])]
        if not todo:
            break
        for i in todo:
            ks = [j for j in nb[i] if known[j]]
            score[i] = float(np.mean(score[ks]))
        known[todo] = True
    for _ in range(2):
        new = score.copy()
        for i in idx:
            if nb[i]:
                new[i] = 0.5 * score[i] + 0.5 * float(np.mean(score[nb[i]]))
        score = new
    return score


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
    sa = human.data.attributes.get(ATTR_SCROTUM) or human.data.attributes.new(ATTR_SCROTUM, "FLOAT", "POINT")
    sa.data.foreach_set("value", _scrotum_score(human, idx))
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


def _scrotum(me, shell):
    """The `ATTR_SCROTUM` score per vertex (1 on the whole shell of a body kept before the score existed)."""
    at = me.attributes.get(ATTR_SCROTUM)
    if at is None or at.domain != "POINT":
        return shell.astype(np.float32)
    v = np.empty(len(me.vertices), np.float32)
    at.data.foreach_get("value", v)
    return v


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


def _trim_flush(bm, shell, co, flush_m):
    """Drop the shell's flat rim: the band of shell faces reached from its open loop through faces lying within
    `flush_m` of the body (every vertex), so the shell joins the body where it stands out of it.

    MPFB's helper does not rise from the body at its open loop: it spreads over it as a flap about 1 mm off the
    skin, out into both groin folds (the study man's reaches 37 mm off the midline; 262 of its 763 subdivided
    vertices lie within 3 mm of the body). Cut out and zipped, the flap replaced that skin with vertices on the
    pelvis, while the skin round it moved with the thighs: in a crouch with the knees out the join creased into
    a collar, and given the skin's own weights instead it tore into wings. Without the flap the body's own
    crotch skin stays and deforms as it does on a body without the part.

    Works on `bm` (the shell's faces subdivided, the body still whole); returns the faces removed, 0 when the
    band would not leave one simple open loop (the flap is then kept)."""
    from mathutils.bvhtree import BVHTree
    faces = list(bm.faces)
    fshell = {f for f in faces if all(shell[v.index] for v in f.verts)}
    body = [tuple(v.index for v in f.verts) for f in faces if not any(shell[v.index] for v in f.verts)]
    bvh = BVHTree.FromPolygons([Vector(c) for c in co], body)
    flush = {}
    for f in fshell:
        for v in f.verts:
            if v not in flush:
                hit = bvh.find_nearest(Vector(co[v.index]), flush_m * 4)
                flush[v] = hit[0] is not None and hit[3] < flush_m
    open_e = [e for e in bm.edges if len(e.link_faces) == 1 and all(shell[v.index] for v in e.verts)]
    seeds = {f for e in open_e for f in e.link_faces if f in fshell and all(flush[v] for v in f.verts)}
    gone, todo = set(seeds), list(seeds)
    while todo:
        f = todo.pop()
        for e in f.edges:
            for g in e.link_faces:
                if g not in gone and g in fshell and all(flush[v] for v in g.verts):
                    gone.add(g)
                    todo.append(g)

    def islands(kept):
        # kept faces cut off from the main body of the shell by the band (a bump on the flap): part of the flap
        comps, seen = [], set()
        for f in kept:
            if f in seen:
                continue
            comp, stack = {f}, [f]
            seen.add(f)
            while stack:
                g = stack.pop()
                for e in g.edges:
                    for h in e.link_faces:
                        if h in kept and h not in seen:
                            seen.add(h)
                            comp.add(h)
                            stack.append(h)
            comps.append(comp)
        comps.sort(key=len, reverse=True)
        return set().union(*comps[1:]) if len(comps) > 1 else set()
    gone |= islands(fshell - gone)

    def rim(kept):
        return [e for e in bm.edges if sum(1 for g in e.link_faces if g in kept) == 1
                and all(shell[v.index] for v in e.verts)]
    for _ in range(20):
        kept = fshell - gone
        deg = {}
        for e in rim(kept):
            for v in e.verts:
                deg[v] = deg.get(v, 0) + 1
        pinched = [v for v, k in deg.items() if k != 2]
        if not pinched:
            break
        # a vertex where two removed patches meet: its faces go back, so the rim passes it once
        for v in pinched:
            gone -= set(v.link_faces)
        gone |= islands(fshell - gone)
    if not gone:
        return 0
    edges = rim(fshell - gone)
    try:
        loop = _walk(edges)
    except RuntimeError:
        return 0
    if len(loop) != len({v for e in edges for v in e.verts}):
        return 0
    verts = {v for f in gone for v in f.verts}
    bmesh.ops.delete(bm, geom=list(gone), context="FACES_ONLY")
    for e in [e for e in bm.edges if not e.link_faces]:
        bm.edges.remove(e)
    for v in verts:
        if v.is_valid and not v.link_edges:
            bm.verts.remove(v)
    return len(gone)


def _body_uvs(bm, shell, co, verts):
    """{BMVert: UV} for `verts` (the shell's open loop): the active UV of the body surface nearest each, by
    inverse distance over the nearest body face's corners. Taken before the cut, while the body is whole."""
    from mathutils.bvhtree import BVHTree
    uv = bm.loops.layers.uv.active
    if uv is None:
        return {}
    body = [f for f in bm.faces if not any(shell[v.index] for v in f.verts)]
    bvh = BVHTree.FromPolygons([Vector(c) for c in co], [tuple(v.index for v in f.verts) for f in body])
    out = {}
    for v in verts:
        loc, _, fi, _ = bvh.find_nearest(Vector(co[v.index]))
        if loc is None:
            continue
        f = body[fi]
        ws = [1.0 / max((Vector(co[lo.vert.index]) - loc).length, 1e-6) for lo in f.loops]
        t = sum(ws)
        out[v] = sum((lo[uv].uv * (w / t) for lo, w in zip(f.loops, ws)), Vector((0.0, 0.0)))
    return out


def fuse(ob, levels=1, smooth=2, flush_m=None):
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
    trimmed = _trim_flush(bm, shell, co, FLUSH_M if flush_m is None else flush_m) if (flush_m is None or flush_m > 0) else 0
    if trimmed:
        # the shell's own vertices go last on the mesh, so dropping them moves no body vertex's index
        bm.to_mesh(me)
        bm.free()
        me.update()
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

    body_uv = _body_uvs(bm, shell, co, sloop)
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
    # the cut's inner vertices are kept, loose (no edge, no face: glTF leaves them out), so every hm08 body vertex
    # keeps its index on the fused mesh. Deleting them shifted every index after the crotch, and what reads MPFB's
    # index lists after the bake (skin's regions, the brows and lashes, landmarks) landed on the wrong vertices:
    # the study man's brows and lashes came out 692 vertices short.
    for e in [e for e in bm.edges if not e.link_faces]:
        bm.edges.remove(e)
    n_gone = len(dead)
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
            # One UV island per seam face. The shell's side takes the body's UV under it: with the shell's own
            # (MPFB's helper island) a seam face spanned two islands, and the skin bake drew it as a wedge
            # across the atlas - a hard-edged pink band over the groin in Godot. The body's side takes, of its
            # vertex's UVs (two where the body's own islands meet on the midline), the one nearest the shell
            # side's: an arbitrary one striped a heavy man's thighs the same way.
            ref = [body_uv[lo.vert] for lo in f.loops if lo.vert in body_uv]
            ref = sum(ref, Vector((0.0, 0.0))) / len(ref) if ref else None
            for lo in f.loops:
                if lo.vert in body_uv:
                    lo[uv].uv = body_uv[lo.vert]
                    continue
                cands = [x[uv].uv.copy() for x in lo.vert.link_loops if x.face not in newset]
                if cands:
                    best = min(cands, key=lambda c: (c - ref).length) if ref is not None else cands[0]
                    # a rim vertex on none of the island the shell side lies in (a heavy man's footprint crosses
                    # where the legs' islands meet the torso's): the face takes the shell side's UV, a patch of
                    # the skin it stands on, rather than a stripe across the atlas
                    lo[uv].uv = best if ref is None or (best - ref).length < UV_SAME_ISLAND else ref
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
    return {"shell_loop": loop_n, "rim": rim_n, "shell_faces": shell_faces_n, "flap_faces_trimmed": trimmed,
            "cut_faces": n_cut,
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
    ob["hf_genital_pelvis"] = pelvis
    ob["hf_genital_thighs"] = list(thighs)
    return {"bone": pelvis, "shares": {k: round(v / s, 3) for k, v in sorted(out.items())},
            "clearance": clearance}


SRC_ATTR = "hf_src"             # int point attribute: the vertex's index before `fuse` (-1 on the shell)


def mark_source(ob):
    """Before `fuse`: number each vertex with its index (the shell -1), so a mesh that shared the unfused
    topology can be carried over (`refit_high`). Returns the unfused coordinates."""
    ob = _obj(ob)
    me = ob.data
    src = np.arange(len(me.vertices), dtype=np.int32)
    src[_shell_mask(me)] = -1
    at = me.attributes.get(SRC_ATTR) or me.attributes.new(SRC_ATTR, "INT", "POINT")
    at.data.foreach_set("value", src)
    return _mesh_co(me)


def refit_high(ob, high, pre_co):
    """After `fuse`: rebuild `high` (a normal map's high copy with the UNFUSED topology, e.g. the muscle stage's
    `delta.high_copy`) on the fused mesh - the fused mesh's own vertices moved by high's offset from the unfused
    body at the vertex each came from (none on the shell and the seam, which the high copy has no offset for) -
    so lookdev's matched bake still lines up face for face. Without it the fused body's face count differs and
    the whole body's bake falls back to rays (a faceted collar at the join, streaks down the groin). Returns
    the face counts."""
    ob, high = _obj(ob), _obj(high)
    me = ob.data
    at = me.attributes.get(SRC_ATTR)
    if at is None:
        raise ValueError(f"{ob.name}: no {SRC_ATTR} - call mark_source before fuse")
    src = np.empty(len(me.vertices), np.int32)
    at.data.foreach_get("value", src)
    hco = _mesh_co(high.data)
    if len(hco) != len(pre_co):
        raise ValueError(f"{high.name} has {len(hco)} vertices, the unfused body {len(pre_co)}")
    rel = np.array(ob.matrix_world.inverted() @ high.matrix_world)
    hco = hco @ rel[:3, :3].T + rel[:3, 3]
    off = np.zeros((len(src), 3))
    ok = (src >= 0) & (src < len(hco))
    off[ok] = hco[src[ok]] - pre_co[src[ok]]
    new = me.copy()
    new.attributes.remove(new.attributes[SRC_ATTR])
    new.vertices.foreach_set("co", (_mesh_co(me) + off).ravel())
    new.update()
    old = high.data
    before = len(old.polygons)
    high.data = new
    high.matrix_world = ob.matrix_world.copy()
    bpy.data.meshes.remove(old)
    me.attributes.remove(at)
    return {"faces_before": before, "faces_after": len(new.polygons), "moved": int(ok.sum())}


# ------------------------------------------------------------------ male: clear of the moving thighs

def _join_d(me, shell):
    """Per shell vertex, how far it lies from the join (the shell vertices with a neighbour off the shell)."""
    co = _mesh_co(me)
    ev = np.empty(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    cross = shell[ev[:, 0]] != shell[ev[:, 1]]
    join = np.unique(np.where(shell[ev[cross, 0]], ev[cross, 0], ev[cross, 1]))
    out = np.full(len(co), np.inf)
    if len(join):
        from mathutils.kdtree import KDTree
        kd = KDTree(len(join))
        for k, i in enumerate(join):
            kd.insert(Vector(co[i]), k)
        kd.balance()
        for i in np.nonzero(shell)[0]:
            out[i] = kd.find(Vector(co[i]))[2]
    return out


def _smooth01(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _limit4(ob, idx, bones):
    """Keep the four strongest bone weights of each vertex in `idx` (glTF's four joints), renormalised."""
    for i in idx:
        v = ob.data.vertices[int(i)]
        d = sorted((x for x in v.groups if ob.vertex_groups[x.group].name in bones and x.weight > 0.0),
                   key=lambda x: (-x.weight, x.group))
        if len(d) <= 4:
            continue
        tot, kept = sum(x.weight for x in d), sum(x.weight for x in d[:4]) or 1.0
        for x in d[4:]:
            ob.vertex_groups[x.group].remove([int(i)])
        for x in d[:4]:
            x.weight = x.weight / kept * tot


def side_rig(ob, rig):
    """The corrective bones `hf_genital.L/.R` and their weights (idempotent): each holds one half of the shell,
    the halves crossing over the midline across +-SIDE_SPLIT_M (so the shaft rides both and moves whole when
    they move together), up to SIDE_SHARE of a vertex, fading to nothing at the join so the seam never moves
    against the body. Parented to follow-through's `ft_jiggle_genital` when there is one (the part still
    swings as a whole), else to the pelvis. Returns the bone names."""
    ob, rig = _obj(ob), _obj(rig)
    names = (SIDE_BONE + ".L", SIDE_BONE + ".R")
    me = ob.data
    shell = _shell_mask(me)
    if not shell.any():
        raise ValueError(f"{ob.name} carries no genital shell")
    if all(n in rig.data.bones for n in names) and all(n in ob.vertex_groups for n in names):
        return list(names)
    pelvis = ob.get("hf_genital_pelvis") or "spine"
    parent = "ft_jiggle_genital" if "ft_jiggle_genital" in rig.data.bones else pelvis
    mw = np.array(ob.matrix_world)
    co = _mesh_co(me) @ mw[:3, :3].T + mw[:3, 3]
    sc = co[shell]
    cx = float(np.median(sc[:, 0]))
    jd = _join_d(me, shell)
    scr = _scrotum(me, shell)
    rootm = shell & (jd < 0.004)
    root = co[rootm & (scr > 0.5)] if (rootm & (scr > 0.5)).any() else co[rootm]
    inv = rig.matrix_world.inverted()
    win = bpy.context.window
    prev_active = bpy.context.view_layer.objects.active
    try:
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        bpy.context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        eb = rig.data.edit_bones
        for n, s in zip(names, (1, -1)):
            b = eb.get(n) or eb.new(n)
            # the head at the half's root: the bone turns the half about where it hangs from
            half = root[(root[:, 0] - cx) * s > 0]
            h = half.mean(axis=0) if len(half) else root.mean(axis=0)
            b.head = inv @ Vector(h)
            b.tail = inv @ Vector(h + np.array((0.0, 0.0, -0.03)))
            b.parent = eb.get(parent)
            b.use_deform = True
            b.use_connect = False
            b["ft_role"] = SIDE_ROLE
        bpy.ops.object.mode_set(mode="OBJECT")
    finally:
        if bpy.context.view_layer.objects.active is not None and \
                bpy.context.view_layer.objects.active.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if prev_active is not None and prev_active.name in bpy.context.view_layer.objects:
            bpy.context.view_layer.objects.active = prev_active
    for n in names:
        g = ob.vertex_groups.get(n)
        if g is not None:
            ob.vertex_groups.remove(g)
    gl, gr = (ob.vertex_groups.new(name=n) for n in names)
    idx = np.nonzero(shell)[0]
    # the scrotum only: the shaft hangs in front, where the thighs leave room, and stays on the pelvis (or
    # the jiggle bone) - swung with the scrotum it pointed up
    fade = _smooth01(jd[idx], *SIDE_FADE_M) * SIDE_SHARE * _smooth01(scr[idx], 0.25, 0.75)
    sl = np.clip(0.5 + (co[idx, 0] - cx) / (2 * SIDE_SPLIT_M), 0.0, 1.0)
    for i, f, s in zip(idx, fade, sl):
        w = float(f)
        if w <= 1e-3:
            continue
        v = me.vertices[int(i)]
        for x in v.groups:
            x.weight *= (1.0 - w)
        if w * s > 1e-4:
            gl.add([int(i)], w * s, "REPLACE")
        if w * (1 - s) > 1e-4:
            gr.add([int(i)], w * (1 - s), "REPLACE")
    _limit4(ob, idx, {b.name for b in rig.data.bones})
    return list(names)


def _group_weights(ob, name):
    g = ob.vertex_groups.get(name)
    w = np.zeros(len(ob.data.vertices))
    if g is None:
        return w
    for v in ob.data.vertices:
        for x in v.groups:
            if x.group == g.index:
                w[v.index] = x.weight
    return w


def _thigh_faces(ob, thighs):
    me = ob.data
    shell = _shell_mask(me)
    gi = {g.index: g.name for g in ob.vertex_groups}
    dom = [None] * len(me.vertices)
    for v in me.vertices:
        best = max(((gi[x.group], x.weight) for x in v.groups), key=lambda t: t[1], default=(None, 0))
        dom[v.index] = best[0]
    return {t: [p.vertices[:] for p in me.polygons if not any(shell[i] for i in p.vertices)
                and all(dom[i] == t for i in p.vertices)] for t in thighs}


def _bvhs(pco, faces_by_thigh):
    from mathutils.bvhtree import BVHTree
    verts = [Vector(c) for c in pco]
    return [BVHTree.FromPolygons(verts, f) for f in faces_by_thigh.values() if f]


def _contacts(bvhs, pts, idx, reach=0.05):
    """{vertex: (signed distance, normal)} of each vertex in `idx` (at `pts[k]`) against the nearest thigh skin
    within reach."""
    out = {}
    for k, i in enumerate(idx):
        p = Vector(pts[k])
        for bvh in bvhs:
            loc, nrm, _, _ = bvh.find_nearest(p, reach)
            if loc is None:
                continue
            s = (p - loc).dot(nrm)
            if i not in out or s < out[i][0]:
                out[i] = (s, np.asarray(nrm))
    return out


def _rot(axis, ang):
    axis = axis / (np.linalg.norm(axis) or 1.0)
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(ang) * k + (1 - np.cos(ang)) * (k @ k)


def _moved(p, wl, wr, heads, moves):
    """Where points `p` go under the side bones' moves [(t, R)] about their heads (linear blend skinning)."""
    out = p.copy()
    for w, h, (t, r) in zip((wl, wr), heads, moves):
        out += w[:, None] * ((p - h) @ r.T + h + t - p)
    return out


def _shortfall(bvhs, pts, clear, reach=0.05):
    tot = 0.0
    for q in pts:
        v = Vector(q)
        s = min((((v - loc).dot(n)) for loc, n, _, _ in (b.find_nearest(v, reach) for b in bvhs) if loc is not None),
                default=clear)
        if s < clear:
            tot += clear - s
    return tot


def _apart(bvhs, pts, idx, wl, wr, lat, clear):
    """Per-half translations moving the halves off what they touch (least moved, closing on each other by at
    most SQUASH_MAX_M): cyclic projection onto the violated half-spaces of the contacts at `pts`."""
    con = _contacts(bvhs, pts, idx)
    x = np.zeros(6)
    rows = [(np.concatenate([wl[i] * n, wr[i] * n]), clear - s_) for i, (s_, n) in con.items()
            if s_ < clear and wl[i] + wr[i] > 0.2]
    if rows:
        sq = np.zeros(6)
        sq[:3], sq[3:] = lat, -lat
        rows.append((sq, -SQUASH_MAX_M))
        A = np.array([r_[0] for r_ in rows])
        b = np.array([r_[1] for r_ in rows])
        nn = np.einsum("ij,ij->i", A, A)
        for _ in range(100):
            worst = 0.0
            for k in range(len(b)):
                v = b[k] - A[k] @ x
                if v > 1e-5:
                    x += A[k] * v / nn[k]
                    worst = max(worst, v)
            if worst < 2e-4:
                break
    return x[:3], x[3:]


def _cap(moves):
    out = []
    for t, r in moves:
        m = np.linalg.norm(t)
        out.append((t * KEY_MAX_M / m if m > KEY_MAX_M else t, r))
    return out


def _solve(bvhs, pco, idx, wl, wr, heads, frame_axes, clear):
    """The side bones' moves [(t, R)] for one frame. First the halves are only moved apart from what they
    touch (`_apart`). Where the thighs collapse into the crotch (linear blend skinning crosses the two inner
    thighs' skin behind the scrotum in a walk or run) that leaves it inside: there is no room between them,
    only in front. Then a common escape is searched - both halves swung forward about their roots (SWING_DEG)
    and carried forward and down (ESCAPE_M), scored by the summed shortfall of `clear` plus ESCAPE_COST per
    metre - and the halves moved apart from what still touches."""
    # only what the side bones can move is solved for (the shaft and the root are the pelvis's)
    idx = [i for i in idx if wl[i] + wr[i] > 0.2]
    if not idx:
        return [(np.zeros(3), np.eye(3))] * 2
    ii = np.array(idx)
    p = pco[ii]
    wli, wri = wl[ii], wr[ii]
    fwd, down, lat = frame_axes
    eye = np.eye(3)
    tl, tr = _apart(bvhs, p, idx, wl, wr, lat, clear)
    first = _cap([(tl, eye), (tr, eye)])
    left = _shortfall(bvhs, _moved(p, wli, wri, heads, first), clear)
    if left < ESCAPE_AFTER_M:
        return first
    axis = np.cross(down, fwd)
    best = (_shortfall(bvhs, p, clear), [(np.zeros(3), eye)] * 2)
    for deg in SWING_DEG:
        r = _rot(axis, np.radians(deg))
        for f in ESCAPE_M:
            for d in ESCAPE_M[:2]:
                if not deg and not f and not d:
                    continue
                t = fwd * f + down * d
                mv = [(t, r), (t, r)]
                sc = _shortfall(bvhs, _moved(p, wli, wri, heads, mv), clear)
                cost = sc + ESCAPE_COST * (np.radians(deg) * ROT_ARM_M + f + d)
                if cost < best[0] - 1e-9:
                    best = (cost, mv)
    moves = best[1]
    dl, dr = _apart(bvhs, _moved(p, wli, wri, heads, moves), idx, wl, wr, lat, clear)
    second = _cap([(moves[0][0] + dl, moves[0][1]), (moves[1][0] + dr, moves[1][1])])
    if _shortfall(bvhs, _moved(p, wli, wri, heads, second), clear) < left:
        return second
    return first


def _eval_co(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    em = ev.to_mesh()
    pco = _mesh_co(em)
    ev.to_mesh_clear()
    mw = np.array(ob.matrix_world)
    return pco @ mw[:3, :3].T + mw[:3, 3]


def clear_thighs(ob, rig, actions, measure=True):
    """Key the corrective bones in each clip so the shell stands KEY_CLEAR_M off the thighs' skin at every frame
    (the thigh sweeps through the scrotum's side in a walk, run or crouch; linear blend skinning with the pelvis
    holding the part cannot keep it out, and moving the rest shape out of every pose the thigh can take pinched
    it). Each frame the body is evaluated with the side bones at rest, the shell's contacts with each thigh's
    skin found, and the two translations solved (least move; the halves close on each other at most
    SQUASH_MAX_M). With `measure`, each clip is evaluated again afterwards. Returns per clip the worst frame
    (shell vertices more than 1 mm inside a thigh, deepest mm) before and after, and the largest key."""
    ob, rig = _obj(ob), _obj(rig)
    names = side_rig(ob, rig)
    thighs = list(ob.get("hf_genital_thighs") or [b.name for b in rig.data.bones if "thigh" in b.name.lower()
                                                   and b.parent is not None and b.parent.name == "spine"])
    me = ob.data
    shell = _shell_mask(me)
    jd = _join_d(me, shell)
    wl, wr = _group_weights(ob, names[0]), _group_weights(ob, names[1])
    idx = [int(i) for i in np.nonzero(shell)[0]]
    far = [i for i in idx if jd[i] >= 0.01]
    faces = _thigh_faces(ob, thighs)
    ad = rig.animation_data or rig.animation_data_create()
    was_action = ad.action
    sc = bpy.context.scene
    was_frame = sc.frame_current
    pbs = [rig.pose.bones[n] for n in names]
    rinv = np.array(rig.matrix_world.inverted().to_3x3())
    pelvis_pb = rig.pose.bones[ob.get("hf_genital_pelvis") or "spine"]
    pelvis_rest_inv = np.linalg.inv(np.array((rig.matrix_world @ pelvis_pb.bone.matrix_local).to_3x3()))
    report = {}

    def worst_of(contacts):
        d = [-s for i, (s, _) in contacts.items() if s < -0.001 and i in far_set]
        return (len(d), round(max(d) * 1000, 1) if d else 0.0)
    far_set = set(far)
    try:
        for act in actions:
            act = bpy.data.actions[act] if isinstance(act, str) else act
            ad.action = act
            if getattr(act, "slots", None) and len(act.slots):
                ad.action_slot = act.slots[0]
            _drop_keys(act, names)
            for pb in pbs:
                pb.rotation_mode = "QUATERNION"
                pb.location = (0.0, 0.0, 0.0)
                pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            f0, f1 = (int(round(x)) for x in act.frame_range)
            keys, before, peak, peak_deg = {}, (0, 0.0, None), 0.0, 0.0
            for f in range(f0, f1 + 1):
                sc.frame_set(f)
                pco = _eval_co(ob)
                bvhs = _bvhs(pco, faces)
                con = _contacts(bvhs, pco[idx], idx)
                w = worst_of(con)
                if w > before[:2]:
                    before = w + (f,)
                heads = [np.array(rig.matrix_world @ pb.head) for pb in pbs]
                pm = np.array((rig.matrix_world @ pelvis_pb.matrix).to_3x3()) @ pelvis_rest_inv
                axes = (pm @ np.array((0.0, -1.0, 0.0)), pm @ np.array((0.0, 0.0, -1.0)), pm @ np.array((1.0, 0, 0)))
                near = [i for i in idx if i in con and con[i][0] < 0.03]
                moves = [(np.zeros(3), np.eye(3))] * 2
                if near:
                    moves = _solve(bvhs, pco, near, wl, wr, heads, axes, KEY_CLEAR_M)
                loc = []
                for pb, (t, r) in zip(pbs, moves):
                    rb = np.array(pb.matrix.to_3x3())
                    rl = np.linalg.solve(rb, rinv @ t)
                    ql = Matrix((np.linalg.solve(rb, rinv @ r @ np.linalg.inv(rinv)) @ rb).tolist()).to_quaternion()
                    loc.append((rl, ql))
                    peak = max(peak, float(np.linalg.norm(t)))
                    peak_deg = max(peak_deg, float(np.degrees(np.arccos(np.clip((np.trace(r) - 1) / 2, -1, 1)))))
                keys[f] = loc
            for f, loc in keys.items():
                for pb, (lv, q) in zip(pbs, loc):
                    pb.location = Vector(lv)
                    pb.rotation_quaternion = q
                    pb.keyframe_insert("location", frame=f, group=pb.name)
                    pb.keyframe_insert("rotation_quaternion", frame=f, group=pb.name)
            after = None
            if measure:
                after = (0, 0.0, None)
                for f in range(f0, f1 + 1):
                    sc.frame_set(f)
                    pco = _eval_co(ob)
                    w = worst_of(_contacts(_bvhs(pco, faces), pco[far], far))
                    if w > after[:2]:
                        after = w + (f,)
            report[act.name] = {"before": list(before), "after": list(after) if after else None,
                                "key_max_mm": round(peak * 1000, 1), "key_max_deg": round(peak_deg, 1)}
    finally:
        ad.action = was_action
        for pb in pbs:
            pb.location = (0.0, 0.0, 0.0)
            pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        sc.frame_set(was_frame)
    return {"bones": names, "clips": report}


def _drop_keys(act, names):
    """Remove `act`'s location curves of the bones `names` (a rerun keys them afresh)."""
    paths = {f'pose.bones["{n}"].{p}' for n in names for p in ("location", "rotation_quaternion")}
    curves = []
    if hasattr(act, "fcurves"):
        curves = [(act.fcurves, fc) for fc in act.fcurves if fc.data_path in paths]
    else:
        for layer in act.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves += [(bag.fcurves, fc) for fc in bag.fcurves if fc.data_path in paths]
    for coll, fc in curves:
        coll.remove(fc)


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
    mons = 0.0065 * k * _gauss(co, mons_c, (0.045 * k, 0.04 * k, 0.03 * k)) * front_side
    lab = 0.0055 * k * (_gauss(co, lab_c(1), (0.011 * k, 0.03 * k, 0.03 * k)) +
                        _gauss(co, lab_c(-1), (0.011 * k, 0.03 * k, 0.03 * k))) * front_side
    cleft = -0.0025 * k * _gauss(co, (0.0, float(y(lab_z)), lab_z), (0.005 * k, 0.03 * k, 0.03 * k)) * front_side
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
