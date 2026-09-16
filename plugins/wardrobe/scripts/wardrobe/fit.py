"""Fit a garment over a body: ease it off the skin, bridge the hollows, and skin it.

    fit.paint_ease(shirt)                      # how loose each part is: hem and cuffs flare
    rep = fit.ease(shirt, "Figure")            # push off the body, bridge cleavage and spine
    rep = fit.skin(shirt, "Figure")            # weights: the body's, smoothed, 4 a vertex

**Ease** is the gap between garment and skin. Every vertex gets a minimum: `base` everywhere
plus `loose` times its `wd_ease` weight (a vertex group, 0..1, paintable). The garment is
pushed out along its normals to that gap, then relaxed and pushed out again, repeatedly:
relaxing pulls it across hollows - between breasts, down the spine - like fabric under
tension, and pushing out keeps it off the skin. It never moves a vertex inward past its gap.

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
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import rigmap

EASE_GROUP = "wd_ease"


def canonical_tris(me):
    """A mesh's triangles in an order that does not depend on how its faces happen to be stored.

    `bpy.ops.object.join` - joining the eyes and the hair into a body - writes the same faces in
    a different order on every run: same vertices, same triangles, shuffled. A BVH built in that
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


def ease(garment, body, base=0.006, loose=0.025, iterations=16, relax=0.5, inflate=True,
         hang=1.0, hang_window=0.15, hang_bins=64, over=(), over_gap=0.003):
    """Push the garment off the body to its ease, bridging hollows, and let it hang. `over`:
    garments worn under this one - it is kept `over_gap` outside each of them too.
    Returns gap statistics."""
    g = rigmap._obj(garment)
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

    gaps = []
    for v in bm.verts:
        hit = bvh.find_nearest(v.co)
        if hit[0] is not None:
            gaps.append((v.co - hit[0]).dot(hit[1]))
    bm.to_mesh(g.data)
    bm.free()
    g.data.update()
    gaps.sort()
    return {"verts": len(gaps), "gap_min_m": round(gaps[0], 4), "gap_median_m": round(gaps[len(gaps) // 2], 4),
            "gap_p95_m": round(gaps[int(len(gaps) * 0.95)], 4), "gap_max_m": round(gaps[-1], 4)}


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
