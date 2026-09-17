"""Fit a garment over a body: ease it off the skin, bridge the hollows, and skin it.

    fit.paint_ease(shirt)                      # how loose each part is: hem and cuffs flare
    rep = fit.ease(shirt, "Figure")            # push off the body, bridge cleavage and spine
    rep = fit.ease(top, "Belle", smooth=1.0, flatten={"breast": 0.2})   # compression: smooth, not traced
    rep = fit.skin(shirt, "Figure")            # weights: the body's, smoothed, 4 a vertex

**Ease** is the gap between garment and skin. Every vertex gets a minimum: `base` everywhere
plus `loose` times its `wd_ease` weight (a vertex group, 0..1, paintable). The garment is
pushed out along its normals to that gap, then relaxed and pushed out again, repeatedly:
relaxing pulls it across hollows - between breasts, down the spine - like fabric under
tension, and pushing out keeps it off the skin. It never moves a vertex inward past its gap.

**Compression** (`smooth`, `flatten`): a sports top or leggings do not trace the body, they squeeze
it. The ease is then measured from a compressed copy of the skin under the garment (`compress`), and
`detail` says how many millimetres of the skin's own relief the cloth still carries.

**Skin** decides whether it stays over the body when the body moves. A garment cut from the
body already carries the body's weights vertex for vertex and keeps them exactly; anything
else gets them from the nearest point of the body's surface, interpolated across that
triangle, then smoothed a little over the garment (so a bridge across a cleavage is not torn
between two breast bones). Either way they are capped at four influences: glTF keeps four.
"""

from __future__ import annotations

import heapq

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import rigmap

EASE_GROUP = "wd_ease"
COMPRESS_FADE = 0.05       # m from the garment's edge over which compression fades back to the skin
SMOOTH_REACH = 0.2         # m: smooth=1 runs (SMOOTH_REACH / mean edge length)^2 Taubin passes
TAUBIN = (0.5, -0.53)      # shrink, then inflate: smooths detail without shrinking the torso
DETAIL_BAND = 0.03         # m of cloth next to an opening left out of the detail check
DETAIL_REACH = 0.03        # m: relief standing over this much surface is detail; anything broader is the body's own form


def canonical_tris(me):
    """A mesh's triangles in an order that does not depend on how its faces happen to be stored.

    A body can arrive with the same vertices and triangles in a different order on every run:
    Blender's `bmesh.ops.create_uvsphere` shuffles its faces per process, and humanform's eyes,
    joined into a body, carried that into it (improvements 5.7). A BVH built in that
    order breaks near-ties differently, so `find_nearest` answers a vertex on a seam with one
    triangle in one build and its neighbour in the next, the push-out lands fractions of a
    millimetre apart, and sixteen relax iterations turn that into millimetres of garment. Sorting
    the triangles makes a fit reproducible whatever order the mesh arrived in. Vertex order is
    stable across those joins, so sorting on vertex indices is canonical. (improvements 5.6)
    """
    me.calc_loop_triangles()
    return sorted(tuple(t.vertices) for t in me.loop_triangles)


def body_bvh(body):
    """BVH of the body's rest surface in its object space, and its triangles."""
    body = rigmap._obj(body)
    me = body.data
    verts = [v.co.copy() for v in me.vertices]
    tris = canonical_tris(me)
    return BVHTree.FromPolygons(verts, tris, all_triangles=True), verts, tris


def boundary_loops(bm):
    """Open boundary loops of a bmesh as lists of verts, each tagged by where it is."""
    edges = {e for e in bm.edges if e.is_boundary}
    loops = []
    while edges:
        e = edges.pop()
        loop = [e.verts[0], e.verts[1]]
        grow = True
        while grow:
            grow = False
            tip = loop[-1]
            for e2 in tip.link_edges:
                if e2 in edges:
                    edges.discard(e2)
                    other = e2.other_vert(tip)
                    if other is loop[0]:
                        break
                    loop.append(other)
                    grow = True
                    break
        loops.append(loop)
    return loops


def kind_of(garment):
    cut = garment.get("wardrobe_cut")
    return (cut.get("kind") if cut is not None else None) or "shirt"


def tag_loops(loops, kind="shirt"):
    """Name each boundary loop. A shirt: the lowest is the hem, the highest the neck, the
    widest-out the cuffs (L on +X). Trousers: the highest is the waist, the others the legs."""
    info = []
    for lp in loops:
        c = sum((v.co for v in lp), Vector()) / len(lp)
        info.append((lp, c))
    tags = {}
    if not info:
        return tags
    if kind == "pants":
        info.sort(key=lambda t: -t[1].z)
        tags["waist"] = info[0][0]
        for lp, c in info[1:]:
            key = "leg.L" if c.x > 0 else "leg.R"
            tags[key if key not in tags else key + ".1"] = lp
        return tags
    by_x = sorted(info, key=lambda t: t[1].x)
    rest = list(info)
    if len(info) >= 4:
        tags["cuff.R"] = by_x[0][0]
        tags["cuff.L"] = by_x[-1][0]
        rest = [t for t in info if t[0] is not by_x[0][0] and t[0] is not by_x[-1][0]]
    rest.sort(key=lambda t: t[1].z)
    tags["hem"] = rest[0][0]
    if len(rest) > 1:
        tags["neck"] = rest[-1][0]
    for i, t in enumerate(rest[1:-1]):
        tags[f"opening.{i}"] = t[0]
    return tags


def geodesic(bm, sources, limit):
    """Distance along edges from a set of verts, up to `limit` (vert index -> metres)."""
    dist = {v.index: 0.0 for v in sources}
    heap = [(0.0, v.index) for v in sources]
    bm.verts.ensure_lookup_table()
    while heap:
        d, i = heapq.heappop(heap)
        if d > dist.get(i, 1e9) or d > limit:
            continue
        v = bm.verts[i]
        for e in v.link_edges:
            o = e.other_vert(v)
            nd = d + e.calc_length()
            if nd < dist.get(o.index, 1e9) and nd <= limit:
                dist[o.index] = nd
                heapq.heappush(heap, (nd, o.index))
    return dist


def paint_ease(garment, hem_band=0.16, cuff_band=0.06, neck_band=0.0, hem=1.0, cuff=0.3, neck=0.0,
               leg_band=0.10, leg=0.5, waist_band=0.0, waist=0.0):
    """Paint `wd_ease`: each opening's amount at the opening, fading to 0 over its band. A shirt
    has a hem, cuffs and a neck; trousers a waist and legs."""
    g = rigmap._obj(garment)
    bm = bmesh.new()
    bm.from_mesh(g.data)
    tags = tag_loops(boundary_loops(bm), kind_of(g))
    w = [0.0] * len(bm.verts)
    table = {"hem": (hem_band, hem), "cuff": (cuff_band, cuff), "neck": (neck_band, neck),
             "leg": (leg_band, leg), "waist": (waist_band, waist)}
    for tag, lp in tags.items():
        band, amount = table.get(tag.split(".")[0], (0.0, 0.0))
        if band <= 0 or amount <= 0:
            continue
        for i, d in geodesic(bm, lp, band).items():
            w[i] = max(w[i], amount * (1.0 - d / band) ** 1.5)
    bm.free()
    vg = g.vertex_groups.get(EASE_GROUP) or g.vertex_groups.new(name=EASE_GROUP)
    vg.remove(list(range(len(w))))
    for i, x in enumerate(w):
        if x > 0:
            vg.add([i], x, "REPLACE")
    return {"loops": sorted(tags), "painted": sum(1 for x in w if x > 0)}


def _ease_weights(g):
    vg = g.vertex_groups.get(EASE_GROUP)
    w = [0.0] * len(g.data.vertices)
    if vg is None:
        return w
    for v in g.data.vertices:
        for ge in v.groups:
            if ge.group == vg.index:
                w[v.index] = ge.weight
    return w


def _hang_setup(g_bm, body, bvh, tris, window, bins, below=None):
    """Which garment verts hang (not on an arm or shoulder, below the armpits), and the axis they
    hang around: vertical, through the root of the spine."""
    b = rigmap._obj(body)
    hm = rigmap.humanoid(b)
    arm_names = {n for a in hm["arms"].values() for n in a.values() if n}
    arm_names |= {vg.name for vg in b.vertex_groups if vg.name.startswith("ft_jiggle_arm")}
    armw = rigmap.chain_weights(b, arm_names)
    root = hm["heads"][hm["spine"][0]]
    shoulder_z = sum(hm["heads"][a["upper"]].z for a in hm["arms"].values()) / max(1, len(hm["arms"]))
    hip_z = sum(hm["heads"][l["thigh"]].z for l in hm["legs"].values()) / max(1, len(hm["legs"]))
    top = shoulder_z - 0.3 * (shoulder_z - hip_z)
    mask = []
    for v in g_bm.verts:
        hit = bvh.find_nearest(v.co)
        w = max(armw[i] for i in tris[hit[2]]) if hit[0] is not None else 0.0
        # fade in below the armpits: a hard edge left a horizontal crease across the back
        fade = min(max((top - v.co.z) / (0.25 * (shoulder_z - hip_z)), 0.0), 1.0)
        if below is not None:
            # trousers hang over the seat, not down the legs: around the spine axis a leg's inner
            # and outer sides share a sector, and hanging pushed the inner thigh out to the outer
            fade *= min(max((v.co.z - below) / 0.05, 0.0), 1.0)
        mask.append(fade * min(max((0.4 - w) / 0.2, 0.0), 1.0))
    return {"mask": mask, "axis": Vector((root.x, root.y, 0.0)), "window": window, "bins": bins}


def _hang(bm, hs, amount, cell=0.01):
    """Cloth falls straight down from the widest point above it; it does not tuck back in under
    a buttock or a bust.

    A radius field R(angle, height) around the axis holds the widest hanging vert in each cell.
    Hanging makes it monotonic downward within `window` (a running max from above), then it is
    blurred across angle and height so neighbouring sectors agree - pushing each sector on its
    own crumpled the back of a shirt into ridges. Each hanging vert is pushed out to the field."""
    import math
    axis, window, nb = hs["axis"], hs["window"], hs["bins"]
    pts = []
    zs = []
    for v in bm.verts:
        m = hs["mask"][v.index]
        if m <= 0:
            continue
        d = Vector((v.co.x - axis.x, v.co.y - axis.y))
        a = (math.atan2(d.y, d.x) + math.pi) / (2 * math.pi) * nb
        pts.append((v, a, d.length, m))
        zs.append(v.co.z)
    if not pts:
        return 0
    z0, z1 = min(zs), max(zs)
    nz = int((z1 - z0) / cell) + 2
    raw = [[-1.0] * nz for _ in range(nb)]
    for (v, a, r, _m) in pts:
        i, j = int(a) % nb, int((v.co.z - z0) / cell)
        raw[i][j] = max(raw[i][j], r)
    span = max(1, int(round(window / cell)))
    hung = [[-1.0] * nz for _ in range(nb)]
    for i in range(nb):
        col = raw[i]
        for j in range(nz):
            hung[i][j] = max(col[j:min(nz, j + span + 1)])
    # blur: angle +-2 sectors, height +-2 cells, ignoring empty cells
    field = [[-1.0] * nz for _ in range(nb)]
    for i in range(nb):
        for j in range(nz):
            s = n = 0.0
            for di in (-2, -1, 0, 1, 2):
                for dj in (-2, -1, 0, 1, 2):
                    jj = j + dj
                    if 0 <= jj < nz:
                        x = hung[(i + di) % nb][jj]
                        if x >= 0:
                            wgt = 1.0 / (1 + abs(di) + abs(dj))
                            s += x * wgt
                            n += wgt
            field[i][j] = s / n if n else -1.0
    moved = 0
    for (v, a, r, m) in pts:
        fz = (v.co.z - z0) / cell - 0.5
        fi = a - 0.5
        i0, j0 = int(math.floor(fi)), int(math.floor(fz))
        ti, tj = fi - i0, fz - j0
        acc = wsum = 0.0
        for di, wi in ((0, 1 - ti), (1, ti)):
            for dj, wj in ((0, 1 - tj), (1, tj)):
                jj = min(max(j0 + dj, 0), nz - 1)
                x = field[(i0 + di) % nb][jj]
                if x >= 0:
                    acc += x * wi * wj
                    wsum += wi * wj
        if wsum <= 0:
            continue
        want = r + (acc / wsum - r) * amount * m
        if want > r + 1e-5:
            d = Vector((v.co.x - axis.x, v.co.y - axis.y, 0.0))
            if d.length > 1e-6:
                v.co = v.co + d.normalized() * (want - r)
                moved += 1
    return moved


# ------------------------------------------------------------------ compression and detail

def _np_mesh(obj):
    """Vertices (n, 3), canonical triangles (m, 3), edges (k, 2) and vertex normals of a mesh."""
    me = obj.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    no = np.empty(n * 3)
    me.vertices.foreach_get("normal", no)
    ed = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", ed)
    tris = np.array(canonical_tris(me), dtype=np.int64).reshape(-1, 3)
    return co.reshape(n, 3), tris, ed.reshape(-1, 2).astype(np.int64), no.reshape(n, 3)


def _umbrella(X, ed, deg):
    """Each vertex's mean neighbour position."""
    n = len(X)
    s = np.empty_like(X)
    for c in range(3):
        s[:, c] = (np.bincount(ed[:, 0], weights=X[ed[:, 1], c], minlength=n)
                   + np.bincount(ed[:, 1], weights=X[ed[:, 0], c], minlength=n))
    return s / np.maximum(deg, 1)[:, None]


def _geodesic_np(co, ed, sources, limit):
    """Distance along edges from the `sources` mask, up to `limit` (inf beyond)."""
    n = len(co)
    adj = [[] for _ in range(n)]
    lengths = np.linalg.norm(co[ed[:, 0]] - co[ed[:, 1]], axis=1)
    for (a, b), d in zip(ed.tolist(), lengths.tolist()):
        adj[a].append((b, d))
        adj[b].append((a, d))
    dist = np.full(n, np.inf)
    heap = [(0.0, int(i)) for i in np.flatnonzero(sources)]
    for _, i in heap:
        dist[i] = 0.0
    heapq.heapify(heap)
    while heap:
        d, i = heapq.heappop(heap)
        if d > dist[i]:
            continue
        for j, w in adj[i]:
            nd = d + w
            if nd < dist[j] and nd <= limit:
                dist[j] = nd
                heapq.heappush(heap, (nd, j))
    return dist


def region_groups(body, key):
    """The vertex groups a region name means on `body`: a follow-through flesh type or region
    name ("breast", "breast.L") -> its jiggle bones; else a rig-anything bone role ("chest",
    "pelvis") -> that bone; else a vertex group of that name."""
    b = rigmap._obj(body)
    names = []
    ft = b.get("follow_through")
    jiggle = ft.get("jiggle") if ft is not None else None
    for r in (jiggle.get("regions") or []) if jiggle is not None else []:
        if key in (r.get("type"), r.get("name")):
            names.append(r.get("bone") or "ft_jiggle_" + str(r.get("name")))
    if not names:
        try:
            from rig_analysis import bodymap
            roles = bodymap.build(rigmap.rig_of(b).name, meshes=[b]).get("roles") or {}
            if isinstance(roles.get(key), str):
                names = [roles[key]]
        except ImportError:
            pass
    if not names and key in b.vertex_groups:
        names = [key]
    return [n for n in names if n in b.vertex_groups]


def region_weights(obj, groups):
    """Per-vertex summed weight of `groups` on `obj`, capped at 1."""
    obj = rigmap._obj(obj)
    gi = {obj.vertex_groups[n].index for n in groups if n in obj.vertex_groups}
    w = np.zeros(len(obj.data.vertices))
    if not gi:
        return w
    for v in obj.data.vertices:
        s = 0.0
        for x in v.groups:
            if x.group in gi:
                s += x.weight
        w[v.index] = s
    return np.minimum(w, 1.0)


def _under(garment_bvh, co, no, ahead=0.1, behind=0.0, touch=0.002):
    """Mask of skin vertices the garment lies on: within `touch`, or met along the skin's normal
    within `ahead` (or `behind` it) by cloth facing the same way."""
    out = np.zeros(len(co), dtype=bool)
    hit_tri = np.full(len(co), -1, dtype=np.int64)
    for i in range(len(co)):
        p, n = Vector(co[i]), Vector(no[i])
        h = garment_bvh.find_nearest(p, touch)
        if h[0] is None:
            h = garment_bvh.ray_cast(p + n * 0.0005, n, ahead)
            if h[0] is not None and h[1].dot(n) < 0.3:
                h = (None,)
        if h[0] is None and behind > 0:
            h = garment_bvh.ray_cast(p - n * 0.0005, -n, behind)
            if h[0] is not None and h[1].dot(n) < 0.0:
                h = (None,)
            if h[0] is None:
                # a nipple's tilted normal runs past cloth pressed over it: the nearest cloth, over its face
                near = garment_bvh.find_nearest(p, behind)
                if near[0] is not None and near[3] > 1e-9 and abs((p - near[0]).dot(near[1])) > 0.7 * near[3]                         and near[1].dot(n) > -0.2:
                    h = near
        if h[0] is not None:
            out[i] = True
            hit_tri[i] = h[2]
    return out, hit_tri


def _membrane(X, ed, fill):
    """The harmonic surface over the `fill` vertices with every other vertex held: each filled
    vertex the mean of its neighbours. Solved directly - Jacobi passes crawl an edge a pass, and
    stopped on a small step they left the membrane in the breast."""
    idx = np.flatnonzero(fill)
    pos = -np.ones(len(X), dtype=np.int64)
    pos[idx] = np.arange(len(idx))
    m = len(idx)
    if m > 4000:
        raise ValueError("flatten: a region of %d vertices is too large to fill; name a smaller one" % m)
    K = np.zeros((m, m))
    rhs = np.zeros((m, 3))
    for a, b in ((ed[:, 0], ed[:, 1]), (ed[:, 1], ed[:, 0])):
        on = fill[a]
        ia, jb = pos[a[on]], b[on]
        np.add.at(K, (ia, ia), 1.0)
        inner = fill[jb]
        np.add.at(K, (ia[inner], pos[jb[inner]]), -1.0)
        np.add.at(rhs, ia[~inner], X[jb[~inner]])
    M = X.copy()
    M[idx] = np.linalg.solve(K, rhs)
    return M


def compress(garment, body, smooth=0.0, flatten=None, fade=COMPRESS_FADE):
    """The body as a compression garment squeezes it, to ease the cloth off (improvements 05 5.3).

    Only skin the garment lies on moves, and each vertex moves by its `fade` (0 at the edge of
    that skin, 1 from `fade` in along the surface), so at a neckline, hem or armhole - where
    cover keeps skin drawn - the surface is the skin and the cloth sits outside it.

      flatten   {region: share}: a region (see `region_groups`) is moved `share` of the way to
                the membrane stretched over its edge (a harmonic fill, the skin around it held),
                scaled by the region's own weights (normalised to 1) - the feathered jiggle
                weights make it fade out toward the chest.
      smooth    0..1: (smooth x `SMOOTH_REACH` / mean edge length)^2 Taubin passes (shrink then inflate, so the torso
                keeps its girth) over that skin, the rest held - after flatten, so what flatten
                leaves at a weight's peak is smoothed too. Nipples, ribs, a navel go.

    Returns positions as `_co`, a BVH of them as `_bvh` (canonical triangles `_tris`), and how far
    the surface moved."""
    g = rigmap._obj(garment)
    b = rigmap._obj(body)
    co, tris, ed, no = _np_mesh(b)
    deg = np.bincount(ed.ravel(), minlength=len(co)).astype(float)
    gm = g.data
    gbvh = BVHTree.FromPolygons([v.co.copy() for v in gm.vertices], canonical_tris(gm), all_triangles=True)
    region, _ = _under(gbvh, co, no)
    dist = _geodesic_np(co, ed, ~region, fade)
    t = np.clip(np.where(np.isinf(dist), 1.0, dist / max(fade, 1e-9)), 0.0, 1.0)
    f = np.where(region, t * t * (3 - 2 * t), 0.0)

    X = co.copy()
    rep = {"smooth": float(smooth), "fade_m": fade, "region_verts": int(region.sum())}
    # flatten first, smooth after: the lerp toward the membrane is only as smooth as the region's
    # weights, and a weight peaked at the nipple drew the nipple back out as a point
    flat = {}
    for key, share in sorted((flatten or {}).items()):
        groups = region_groups(b, key)
        w = region_weights(b, groups)
        w = np.where(region, w / max(float(w.max()), 1e-9), 0.0)   # share is of the whole region's projection
        fill = w > 0.01
        if not fill.any():
            flat[key] = {"share": share, "groups": sorted(groups), "verts": 0}
            continue
        M = _membrane(X, ed, fill)
        d = np.maximum(((X - M) * no).sum(axis=1), 0.0)
        # toward the membrane, not along the skin's normals: those turn sharply at a nipple, and
        # moved along them the surface folded there and the cloth eased off it tore open
        X = X + (share * w)[:, None] * (M - X)
        flat[key] = {"share": share, "groups": sorted(groups), "verts": int(fill.sum()),
                     "projection_max_m": round(float(d[fill].max()), 4),
                     "moved_max_m": round(float((share * w * d * f).max()), 4)}
    if flat:
        rep["flatten"] = flat
    # the same smoothing on a coarse body and a fine one: diffusion spreads about an edge a pass,
    # so the passes go with the square of reach over edge length (a 1.7 cm MPFB torso: 138 passes,
    # the 1.0 cm sample figure: 400)
    near = region[ed[:, 0]] & region[ed[:, 1]]
    edge = float(np.linalg.norm(co[ed[near, 0]] - co[ed[near, 1]], axis=1).mean()) if near.any() else 1.0
    passes = int(round((max(0.0, min(1.0, float(smooth))) * SMOOTH_REACH / max(edge, 1e-4)) ** 2))
    rep["edge_m"] = round(edge, 4)
    for _ in range(passes):
        for lam in TAUBIN:
            A = _umbrella(X, ed, deg)
            X[region] += lam * (A[region] - X[region])
    rep["passes"] = passes
    # Each skin vertex goes to the nearest point of the smoothed surface, not to where its own
    # vertex drifted: umbrella passes slide vertices along the surface toward even edges, and that
    # slide, faded out toward the garment's edge, folded the surface there (skin through compression
    # shorts at the leg openings). Moving only along normals instead - per pass or once at the end -
    # crossed the moves of a nipple's vertices and pinched the cloth over it.
    tris_l = [tuple(t) for t in tris.tolist()]
    smooth_bvh = BVHTree.FromPolygons([Vector(p) for p in X], tris_l, all_triangles=True)
    target = co.copy()
    for i in np.flatnonzero(region):
        h = smooth_bvh.find_nearest(Vector(co[i]))
        if h[0] is not None:
            target[i] = tuple(h[0])
    S = co + f[:, None] * (target - co)
    rep["_fade"] = f
    moved = np.linalg.norm(S - co, axis=1)
    rep["moved_max_m"] = round(float(moved.max()), 4)
    rep["moved_p95_m"] = round(float(np.percentile(moved[region], 95)), 4) if region.any() else 0.0
    rep["_co"] = S
    rep["_tris"] = [tuple(t) for t in tris.tolist()]
    rep["_bvh"] = BVHTree.FromPolygons([Vector(p) for p in S], rep["_tris"], all_triangles=True)
    return rep


def _areas(co, tris):
    """Each vertex's area: a third of the triangles it belongs to."""
    a, b, c = co[tris[:, 0]], co[tris[:, 1]], co[tris[:, 2]]
    dbl = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    return np.bincount(tris.ravel(), weights=np.repeat(dbl / 6.0, 3), minlength=len(co))


def relief(co, tris, ed, reach=DETAIL_REACH):
    """Each vertex's height (m, signed) over the same surface smoothed across `reach`.

    The reference is Taubin (shrink then inflate, `TAUBIN`), as many passes as spread diffusion
    that far - (reach / mean edge)^2, the count `compress` uses - so a breast's or a thigh's own
    curve survives it and only what stands on that curve is left: a nipple, a navel, the fold under
    a buttock, a rib. That is the detail a compression garment is meant to hide; the form under it
    is not, and a check that counted the form would call every fitted garment a tracer.

    Height is measured to the nearest point of the smoothed surface, not to where the vertex's own
    copy drifted: the passes slide vertices along the surface toward even edge lengths."""
    n = len(co)
    deg = np.bincount(ed.ravel(), minlength=n).astype(float)
    edge = float(np.linalg.norm(co[ed[:, 0]] - co[ed[:, 1]], axis=1).mean())
    passes = int(round((reach / max(edge, 1e-4)) ** 2))
    X = co.copy()
    for _ in range(passes):
        for lam in TAUBIN:
            X += lam * (_umbrella(X, ed, deg) - X)
    bvh = BVHTree.FromPolygons([Vector(p) for p in X], [tuple(t) for t in tris.tolist()], all_triangles=True)
    d = np.zeros(n)
    for i in range(n):
        h = bvh.find_nearest(Vector(co[i]))
        if h[0] is not None:
            d[i] = (Vector(co[i]) - h[0]).dot(h[1])
    return d, passes, edge


def _moments(a, x, y):
    """Area-weighted variance of `x`, of `y`, and their covariance."""
    s = a.sum()
    mx, my = (a * x).sum() / s, (a * y).sum() / s
    return ((a * (x - mx) ** 2).sum() / s, (a * (y - my) ** 2).sum() / s,
            (a * (x - mx) * (y - my)).sum() / s)


def detail(garment, body, regions=None, limit=None, band=DETAIL_BAND, min_verts=12, reach=DETAIL_REACH):
    """How much of the skin's own relief the cloth still carries (improvements 04 step 5).

    Per region: `skin_relief_mm`, how much relief (see `relief`) the skin under the cloth has to
    trace; `traced`, the share of it the cloth reproduces; and `relief_mm = traced x
    skin_relief_mm`, the millimetres of the body's relief the cloth carries - the number a
    `limit` holds. Cloth within `band` of an opening, and skin under it, is left out: an edge has
    no surface to compare.

    `traced` is a regression, the area-weighted slope of the cloth's relief on the skin's relief
    sampled under it, not a ratio of amplitudes. Cloth has relief of its own from the projection
    that laid it on the body - faceting, at the same scale and a few hundredths of a millimetre -
    and that is uncorrelated with the skin, so it leaves the slope alone where a ratio would count
    it as tracing. A ratio also divides by however much relief the body happens to have, so on a
    smooth body it reports the cloth's own noise against nothing; the millimetres do not.

    `regions`: names for `region_groups` (default: every follow-through flesh type the garment
    carries weights of), each measured where its weight is at least half its strongest on the body;
    "all" is always measured. `limit` {region: most mm}: `passed` and `problems`. A limited region
    that cannot be measured - too little cloth or skin in it - is a problem too, not a quiet pass:
    a limit nothing was measured against has not been met (as `verify` learned in 0.2.2)."""
    g = rigmap._obj(garment)
    b = rigmap._obj(body)
    gco, gtris, ged, _ = _np_mesh(g)
    bco, btris, bed, bno = _np_mesh(b)
    Ag, Ab = _areas(gco, gtris), _areas(bco, btris)
    Dg, g_passes, _ = relief(gco, gtris, ged, reach)
    Db, b_passes, _ = relief(bco, btris, bed, reach)

    bm = bmesh.new()
    bm.from_mesh(g.data)
    boundary = np.zeros(len(gco), dtype=bool)
    for v in bm.verts:
        if v.is_boundary:
            boundary[v.index] = True
    bm.free()
    interior = ~(_geodesic_np(gco, ged, boundary, band) <= band)
    gtris_l = [tuple(t) for t in gtris.tolist()]
    gbvh = BVHTree.FromPolygons([Vector(p) for p in gco], gtris_l, all_triangles=True)
    under, hit = _under(gbvh, bco, bno, ahead=0.1, behind=0.03, touch=0.0)
    tri_interior = interior[gtris].all(axis=1)
    skin = under & (hit >= 0) & tri_interior[np.maximum(hit, 0)]

    # the skin's relief where each piece of cloth lies, to regress the cloth's own against
    btris_l = [tuple(t) for t in btris.tolist()]
    bbvh = BVHTree.FromPolygons([Vector(p) for p in bco], btris_l, all_triangles=True)
    Ds = np.zeros(len(gco))
    found = np.zeros(len(gco), dtype=bool)
    for i in range(len(gco)):
        h = bbvh.find_nearest(Vector(gco[i]), 0.08)
        if h[0] is None:
            continue
        t = btris_l[h[2]]
        u, v, w = _barycentric(h[0], Vector(bco[t[0]]), Vector(bco[t[1]]), Vector(bco[t[2]]))
        Ds[i] = Db[t[0]] * u + Db[t[1]] * v + Db[t[2]] * w
        found[i] = True

    if regions is None:
        regions = []
        ft = b.get("follow_through")
        jiggle = ft.get("jiggle") if ft is not None else None
        for r in (jiggle.get("regions") or []) if jiggle is not None else []:
            if r.get("type") and r.get("type") not in regions and (r.get("bone") in g.vertex_groups):
                regions.append(r.get("type"))
        regions = sorted(regions)
    limit = dict(limit or {})
    names = ["all"] + [r for r in regions if r != "all"] + sorted(k for k in limit if k != "all" and k not in regions)
    out, problems, unmeasured = {}, [], []
    for name in names:
        if name == "all":
            wg, wb = np.ones(len(gco)), np.ones(len(bco))
        else:
            groups = region_groups(b, name)
            wg, wb = region_weights(g, groups), region_weights(b, groups)
        # half the region's strongest weight: jiggle weights share their vertices with the spine
        cm = interior & found & (wg >= 0.5 * wb.max()) & (wg > 0)
        sm = skin & (wb >= 0.5 * wb.max()) & (wb > 0)
        if cm.sum() < min_verts or sm.sum() < min_verts:
            if name in limit:
                # a body without that flesh, or flesh found elsewhere (follow-through put an MPFB
                # woman's breast weights on her face): the limit is still unmet, not waived
                unmeasured.append("%s: %d cloth, %d skin verts under the garment (least %d)"
                                  % (name, cm.sum(), sm.sum(), min_verts))
            continue
        # the skin's relief measured on the skin itself; sampling it at the cloth's vertices
        # interpolates a nipple's peak away across the body triangle it stands on
        skin_mm = 1000.0 * _moments(Ab[sm], Db[sm], Db[sm])[0] ** 0.5
        vs, vc, cov = _moments(Ag[cm], Ds[cm], Dg[cm])
        traced = cov / vs if vs > 0 else None
        carried = max(0.0, traced) * skin_mm if traced is not None else None
        out[name] = {"cloth_verts": int(cm.sum()), "skin_verts": int(sm.sum()),
                     "skin_relief_mm": round(skin_mm, 3), "cloth_relief_mm": round(1000.0 * vc ** 0.5, 3),
                     "traced": round(traced, 3) if traced is not None else None,
                     "relief_mm": round(carried, 3) if carried is not None else None}
        if name in limit and carried is not None and round(carried, 3) > limit[name]:
            problems.append("detail %s: the cloth carries %.3f mm of the skin's relief, limit %.3f mm"
                            % (name, carried, limit[name]))
    rep = {"band_m": band, "reach_m": reach, "passes": {"cloth": g_passes, "skin": b_passes}, "regions": out}
    if limit:
        problems = problems + ["detail %s: not measured, so the limit is unmet" % x for x in unmeasured]
        rep.update(limit=limit, passed=not problems, problems=problems)
        if unmeasured:
            rep["unmeasured"] = unmeasured
    return rep


def ease(garment, body, base=0.006, loose=0.025, iterations=16, relax=0.5, inflate=True,
         hang=1.0, hang_window=0.15, hang_bins=64, over=(), over_gap=0.003,
         smooth=0.0, flatten=None, fade=COMPRESS_FADE, detail_limit=None):
    """Push the garment off the body to its ease, bridging hollows, and let it hang. `over`:
    garments worn under this one - it is kept `over_gap` outside each of them too.

    Compression (`smooth` 0..1, `flatten` {region: share}): the ease is measured from a compressed
    copy of the body instead of the skin - smoothed over the garment's region and with the named
    regions' projection reduced - fading back to the skin over `fade` from the garment's edges
    (see `compress`). `detail_limit` {region: mm}: the most of the skin's own relief the cloth may
    carry over each region (see `detail`); the report says whether it held.

    Returns gap statistics (against the skin), `detail`, and `compression` when it was asked for."""
    g = rigmap._obj(garment)
    compressing = bool(smooth) or bool(flatten)
    comp = None
    if compressing:
        comp = compress(g, body, smooth=smooth, flatten=flatten, fade=fade)
        bvh, tris = comp["_bvh"], comp["_tris"]
    else:
        bvh, _, tris = body_bvh(body)
    ew = _ease_weights(g)
    bm = bmesh.new()
    bm.from_mesh(g.data)
    bm.verts.ensure_lookup_table()
    want = [base + loose * ew[v.index] for v in bm.verts]
    cut = g.get("wardrobe_cut")
    below = cut.get("hang_below") if cut is not None else None
    hs = _hang_setup(bm, body, bvh, tris, hang_window, hang_bins, below) if hang > 0 else None
    unders = [body_bvh(o)[0] for o in over]

    floor = None
    if compressing:
        # start on the compressed surface: eased from the skin, relaxing pulled a nipple's tip in
        # by a fraction of a millimetre a pass and push-out never moves cloth inward
        raw_bvh, raw_co, raw_tris = body_bvh(body)
        S, fade_w = comp["_co"], comp["_fade"]
        floor = [0.0] * len(bm.verts)
        for v in bm.verts:
            hit = raw_bvh.find_nearest(v.co)
            if hit[0] is None:
                continue
            t = raw_tris[hit[2]]
            u, vv, w = _barycentric(hit[0], raw_co[t[0]], raw_co[t[1]], raw_co[t[2]])
            p = S[t[0]] * u + S[t[1]] * vv + S[t[2]] * w
            v.co = v.co + (Vector(p) - hit[0])
            # where compression has faded out the cloth also keeps its ease off the skin itself:
            # there cover leaves the skin drawn, and cloth under it is skin showing
            floor[v.index] = 1.0 - float(fade_w[t[0]] * u + fade_w[t[1]] * vv + fade_w[t[2]] * w)
    if inflate:
        bm.normal_update()
        for v in bm.verts:
            v.co = v.co + v.normal * want[v.index]

    def push_out():
        worst_in = 0.0
        for v in bm.verts:
            hit = bvh.find_nearest(v.co)
            if hit[0] is None:
                continue
            p, n = hit[0], hit[1]
            s = (v.co - p).dot(n)
            if s < want[v.index]:
                worst_in = min(worst_in, s)
                v.co = v.co + n * (want[v.index] - s)
            if floor is not None and floor[v.index] > 0.0:
                hit = raw_bvh.find_nearest(v.co)
                if hit[0] is not None:
                    s = (v.co - hit[0]).dot(hit[1])
                    need = want[v.index] * floor[v.index]
                    if s < need:
                        v.co = v.co + hit[1] * (need - s)
        return worst_in

    push_out()
    for _ in range(iterations):
        new = []
        for v in bm.verts:
            if v.is_boundary:
                nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
            else:
                nb = [e.other_vert(v) for e in v.link_edges]
            if not nb:
                new.append(v.co.copy())
                continue
            avg = sum((o.co for o in nb), Vector()) / len(nb)
            new.append(v.co.lerp(avg, relax))
        for v, co in zip(bm.verts, new):
            v.co = co
        if hs is not None:
            _hang(bm, hs, hang)
        push_out()

    if unders:
        _clear_unders(bm, unders, over_gap)
        push_out()

    skin_bvh = body_bvh(body)[0] if compressing else bvh
    gaps, from_compressed = [], []
    for v in bm.verts:
        hit = skin_bvh.find_nearest(v.co)
        if hit[0] is not None:
            gaps.append((v.co - hit[0]).dot(hit[1]))
        if compressing:
            hit = bvh.find_nearest(v.co)
            if hit[0] is not None:
                from_compressed.append((v.co - hit[0]).dot(hit[1]))
    bm.to_mesh(g.data)
    bm.free()
    g.data.update()
    gaps.sort()
    out = {"verts": len(gaps), "gap_min_m": round(gaps[0], 4), "gap_median_m": round(gaps[len(gaps) // 2], 4),
           "gap_p95_m": round(gaps[int(len(gaps) * 0.95)], 4), "gap_max_m": round(gaps[-1], 4)}
    if compressing:
        from_compressed.sort()
        rep = {k: v for k, v in comp.items() if not k.startswith("_")}
        rep["gap_min_from_compressed_m"] = round(from_compressed[0], 4)
        rep["inside_skin_verts"] = sum(1 for x in gaps if x < 0.0)
        out["compression"] = rep
    out["detail"] = detail(g, body, limit=detail_limit)
    return out


def lift_over(garment, body, tris, gap, radius=0.02, spread=12, keep=0.8, reach=0.03):
    """Lift the garment over the corners of these body triangles (vertex index triples) that lie
    over its face - the skin `cover.drawn_over_cloth` found showing through a compression garment -
    until it is `gap` outside them. Each such corner asks the cloth within `radius` to rise by what
    it lacks, fading with distance; the lift is spread over neighbours as `_clear_unders` spreads
    its own, and applied along the garment's normals. Returns the number of garment vertices moved."""
    from mathutils.kdtree import KDTree
    g = rigmap._obj(garment)
    b = rigmap._obj(body)
    if not tris:
        return 0
    me = g.data
    gbvh = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], canonical_tris(me), all_triangles=True)
    kd = KDTree(len(me.vertices))
    for v in me.vertices:
        kd.insert(v.co, v.index)
    kd.balance()
    need = [0.0] * len(me.vertices)
    for i in sorted({i for t in tris for i in t}):
        co = b.data.vertices[i].co
        h = gbvh.find_nearest(co, reach)
        if h[0] is None or h[3] <= 1e-9:
            continue
        side = (co - h[0]).dot(h[1])
        if side <= 0.0 or side < 0.7 * h[3]:
            continue
        for _co, j, d in kd.find_range(h[0], radius):
            need[j] = max(need[j], (side + gap) * (1.0 - d / radius))
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.normal_update()
    nb = [[e.other_vert(v).index for e in v.link_edges] for v in bm.verts]
    for _ in range(spread):
        need = [max(need[k], keep * sum(need[j] for j in nb[k]) / len(nb[k])) if nb[k] else need[k]
                for k in range(len(need))]
    for v in bm.verts:
        if need[v.index] > 0:
            v.co = v.co + v.normal * need[v.index]
    bm.to_mesh(me)
    bm.free()
    me.update()
    return sum(1 for x in need if x > 0)


def _clear_unders(bm, unders, gap, spread=12, keep=0.8):
    """Lift the garment `gap` clear of the garments under it - smoothly. Pushed out only where it
    lay too close, a shirt took a step at every edge of the bra under it: lumps over the shoulders
    where the straps end. The lift each vertex needs is spread over its neighbours (each keeps the
    larger of its own need and `keep` of theirs), then applied along the garment's normals."""
    bm.verts.ensure_lookup_table()
    bm.normal_update()
    need = [0.0] * len(bm.verts)
    for v in bm.verts:
        for ub in unders:
            h = ub.find_nearest(v.co, 0.04)
            if h[0] is None:
                continue
            d = v.co - h[0]
            su = d.dot(h[1])
            # only cloth over the inner garment's surface, not beside its cut edge: past a strap's
            # edge the nearest point is on the edge, the distance along the face normal says
            # nothing, and it lifted the shirt into a 2 cm spike behind each shoulder
            if d.length > 1e-5 and abs(su) < 0.7 * d.length:
                continue
            if su < -0.004:
                continue         # more than 4 mm under the inner garment: its far side, or a fold of it
            if su < gap:
                need[v.index] = max(need[v.index], gap - su)
    nb = [[e.other_vert(v).index for e in v.link_edges] for v in bm.verts]
    for _ in range(spread):
        need = [max(need[i], keep * sum(need[j] for j in nb[i]) / len(nb[i])) if nb[i] else need[i]
                for i in range(len(need))]
    for v in bm.verts:
        if need[v.index] > 0:
            v.co = v.co + v.normal * need[v.index]
    return sum(1 for x in need if x > 0)


def _barycentric(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
    d20, d21 = v2.dot(v0), v2.dot(v1)
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-18:
        return 1.0, 0.0, 0.0
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    u = 1.0 - v - w
    # clamp onto the triangle, then renormalise
    u, v, w = max(u, 0.0), max(v, 0.0), max(w, 0.0)
    s = u + v + w or 1.0
    return u / s, v / s, w / s


def skin(garment, body, transfer=None, smooth=None, smooth_factor=0.5, limit=4):
    """Skin weights for the garment. `transfer` None: keep the weights of a garment cut from
    the body (tailor), take them from the body's surface otherwise. `smooth` None: 0 for a cut
    garment - it then moves exactly as the skin under it, jiggle included, and keeps the body's
    four influences (smoothed twice, 27% of one vertex's weight fell past the fourth) - and 2
    for a transferred one."""
    g = rigmap._obj(garment)
    b = rigmap._obj(body)
    if transfer is None:
        transfer = "wardrobe_cut" not in g.keys()
    if smooth is None:
        smooth = 2 if transfer else 0
    deform = rigmap.deform_names(b)
    body_groups = [vg.name for vg in b.vertex_groups if vg.name in deform]
    for n in body_groups:
        if n not in g.vertex_groups:
            g.vertex_groups.new(name=n)
    deform = set(body_groups)

    weights = []          # per garment vertex: {name: w}
    if transfer:
        bvh, bverts, btris = body_bvh(b)
        bw = []
        names = {vg.index: vg.name for vg in b.vertex_groups}
        for v in b.data.vertices:
            bw.append({names[x.group]: x.weight for x in v.groups if x.weight > 0 and names[x.group] in deform})
        for v in g.data.vertices:
            hit = bvh.find_nearest(v.co)
            t = btris[hit[2]]
            u, vv, w = _barycentric(hit[0], bverts[t[0]], bverts[t[1]], bverts[t[2]])
            acc = {}
            for i, f in zip(t, (u, vv, w)):
                for k, x in bw[i].items():
                    acc[k] = acc.get(k, 0.0) + x * f
            weights.append(acc)
    else:
        names = {vg.index: vg.name for vg in g.vertex_groups}
        for v in g.data.vertices:
            weights.append({names[x.group]: x.weight for x in v.groups if names[x.group] in deform and x.weight > 0})

    bm = bmesh.new()
    bm.from_mesh(g.data)
    bm.verts.ensure_lookup_table()
    neighbours = [[e.other_vert(v).index for e in v.link_edges] for v in bm.verts]
    bm.free()
    for _ in range(smooth):
        nxt = []
        for i, own in enumerate(weights):
            nb = neighbours[i]
            if not nb:
                nxt.append(own)
                continue
            acc = {k: x * (1 - smooth_factor) for k, x in own.items()}
            share = smooth_factor / len(nb)
            for j in nb:
                for k, x in weights[j].items():
                    acc[k] = acc.get(k, 0.0) + x * share
            nxt.append(acc)
        weights = nxt

    worst_dropped = 0.0
    for i, acc in enumerate(weights):
        top = sorted(acc.items(), key=lambda kv: -kv[1])
        kept = top[:limit]
        dropped = sum(x for _, x in top[limit:])
        total = sum(x for _, x in kept)
        worst_dropped = max(worst_dropped, dropped / (total + dropped) if total + dropped > 0 else 0.0)
        weights[i] = {k: x / total for k, x in kept} if total > 0 else {}

    for n in body_groups:
        g.vertex_groups[n].remove(list(range(len(g.data.vertices))))
    for i, acc in enumerate(weights):
        for k, x in acc.items():
            if x > 1e-4:
                g.vertex_groups[k].add([i], x, "REPLACE")
    unskinned = sum(1 for acc in weights if not acc)
    return {"transferred": transfer, "groups": len(body_groups), "unskinned_verts": unskinned,
            "worst_dropped_share": round(worst_dropped, 3)}
