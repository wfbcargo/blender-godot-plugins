"""Radial bodies: things with no front or back - a jellyfish, a starfish, a
brittle star, an anemone.

Every other archetype in this package is a spine with limbs off it, read front
to back. A radial body is a HUB with a ring of APPENDAGES round an axis - the
oral-aboral axis, mouth at one end - and it has as many "fronts" as it has
arms. `measure.rotational_symmetry` finds that axis and how many times the body
repeats round it; this module finds the hub and the appendages on the skin,
rigs them, weights them and poses them.

RECOGNITION
-----------

Geodesic distance from the hub's centre, in bands. Near the centre every band is
a ring round the axis. Where an arm leaves the body the band breaks into pieces,
and each piece covers only the arm's own sliver of angle. So:

    hub        a band piece that wraps round the axis, or touches it
    appendage  a band piece confined to a narrow angle; linked band to band
               they form a chain from the hub to a tip

Appendages modelled as separate loose parts - how most jellyfish arrive, and
exactly what bone heat refuses - are chains in their own right, rooted at the
nearest point of the body. Small compact loose parts (eyes, gonads, statocysts)
are rigid and ride the skin under them.

The oral side is where the appendages point: a jellyfish's hang down, an
anemone's reach up; a starfish's lie flat and its mouth is on the floor. The
KIND is suggested from the shape and settled from the renders, as a maw's is:

    medusa     a bell (dome) with tentacles and oral arms hanging orally
    polyp      a column with a crown of tentacles at its oral end
    asteroid   a disc with stout arms in its plane - a sea star
    ophiuroid  a small disc with slender arms in its plane - a brittle star

RIGGING
-------

`build` adds, on a mesh with no rig:

    hub            one bone on the axis, the root
    rib_NN_k       medusa: a chain down each bell meridian from near the apex to
                   the margin - the bell contracts by bending them in
    <role>NN_k     a chain along each appendage: arm, tentacle, oral_arm

Names carry no .L/.R: nothing here has a side. Every bone is tagged
`radial_role`, so `bodymap` leaves them alone.

`skin` weights without bone heat. Bone heat solves over a surface the bell's
thin shell and a tentacle's loose tube do not give it; here every vertex already
knows what it belongs to and where along it, so its weights are written directly:
bell skin between the two ribs either side of it by angle and along them by
radius, an appendage between the two bones either side of it along its length,
fading into whatever its root is attached to. Coverage is 1.0 by construction.
"""

from __future__ import annotations

import heapq
import json
import math

import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

from . import measure

PROP = "rig_anything_radial"
ROLE = "radial_role"
PARTS = "rig_anything_radial_parts:"
KINDS = ("medusa", "polyp", "asteroid", "ophiuroid")
TAU = 2.0 * math.pi


def _wrap(a):
    return (a + math.pi) % TAU - math.pi


def _v(x):
    return [round(float(c), 6) for c in x]


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------

def _adjacency(me, ids=None):
    """Weighted neighbour lists, optionally restricted to a vertex subset."""
    keep = None if ids is None else set(ids)
    nbr = {}
    cos = [v.co for v in me.vertices]
    for e in me.edges:
        a, b = e.vertices
        if keep is not None and (a not in keep or b not in keep):
            continue
        w = (cos[a] - cos[b]).length
        nbr.setdefault(a, []).append((b, w))
        nbr.setdefault(b, []).append((a, w))
    return nbr


def _dijkstra(nbr, sources):
    dist = {s: 0.0 for s in sources}
    pq = [(0.0, s) for s in sources]
    heapq.heapify(pq)
    while pq:
        d, v = heapq.heappop(pq)
        if d > dist.get(v, float("inf")):
            continue
        for n, w in nbr.get(v, ()):
            nd = d + w
            if nd < dist.get(n, float("inf")):
                dist[n] = nd
                heapq.heappush(pq, (nd, n))
    return dist


def _coverage(thetas):
    """How much of the circle a set of angles spans: 2 pi less the largest gap."""
    if len(thetas) < 2:
        return 0.0
    s = sorted(thetas)
    gap = max(b - a for a, b in zip(s, s[1:]))
    gap = max(gap, s[0] + TAU - s[-1])
    return TAU - gap


def _seg_param(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.dot(ab), 1e-18)))
    return t, (p - (a + ab * t)).length


def _resample(points, count):
    from .fins import _resample as rs
    return rs(points, count)


def _arc(points):
    return sum((b - a).length for a, b in zip(points, points[1:]))


def _pca(points):
    from .fins import _pca as p
    return p(points)


# --------------------------------------------------------------------------
# detection
# --------------------------------------------------------------------------

class _Frame:
    """The body's own cylindrical frame: `a` the symmetry axis, pointing ABORAL
    once the oral side is known; `e1` the reference angle, the rig's forward
    projected into the plane, so appendage 01 is the one facing forward."""

    def __init__(self, axis, centre, forward):
        from .bodymap import axis_vector
        self.a = Vector(axis).normalized()
        self.c = Vector(centre)
        f = axis_vector(forward)
        f = f - self.a * f.dot(self.a)
        if f.length < 1e-6:
            f = Vector((1.0, 0.0, 0.0)) - self.a * self.a.x
        self.e1 = f.normalized()
        self.e2 = self.a.cross(self.e1).normalized()

    def flip(self):
        """Point the axis the other way, keeping angles measured the same way
        round when seen from the aboral end."""
        self.a = -self.a
        self.e2 = self.a.cross(self.e1).normalized()

    def cyl(self, p):
        d = p - self.c
        h = d.dot(self.a)
        x, y = d.dot(self.e1), d.dot(self.e2)
        return math.hypot(x, y), math.atan2(y, x), h

    def radial(self, theta):
        return (self.e1 * math.cos(theta) + self.e2 * math.sin(theta)).normalized()

    def point(self, r, theta, h):
        return self.c + self.radial(theta) * r + self.a * h


def detect(mesh_name, kind=None, oral=None, forward="-Y", symmetry=None, min_share=0.002):
    """Find the hub and appendages of a radial body. World space: the rig
    `build` makes sits at the world origin.

    `kind` - medusa, polyp, asteroid, ophiuroid - comes from the renders; left
    out it is suggested from shape and flagged `kind_guessed`. `oral` ("+Z",
    "-Z", ...) overrides the side the mouth is on."""
    obj = bpy.data.objects.get(mesh_name)
    if obj is None or obj.type != "MESH":
        return {"error": "no mesh named %r" % mesh_name}
    sym = symmetry or measure.rotational_symmetry(obj)
    if not sym.get("radial"):
        return {"error": "%s repeats round no axis (rotational_symmetry: %s) - not a radial body; "
                         "pass symmetry= to force one" % (mesh_name, sym.get("notes") or "no order passed"),
                "symmetry": sym}
    me = obj.data
    mw = obj.matrix_world
    cos = [mw @ v.co for v in me.vertices]
    n = len(cos)
    fr = _Frame(sym["axis_vector"], sym["centre"], forward)
    order = sym["order"]
    warnings = list(sym.get("notes", []))

    from .maw import _components
    comp, sizes = _components(me)
    main = max(sizes, key=sizes.get)
    main_ids = [i for i in range(n) if comp[i] == main]
    world_me = _WorldMesh(me, cos)
    nbr = world_me.adjacency(main_ids)
    cyl = [fr.cyl(p) for p in cos]
    R_main = max(cyl[i][0] for i in main_ids) or 1.0

    # ---- the seed: the hub's centre on the skin. The vertex that minimises its
    # largest geodesic distance to the appendage tips; tips found by farthest-
    # point sampling and kept only when they lie out from the axis, so the far
    # side of a disc or the foot of a column is not taken for an arm.
    start = min(main_ids, key=lambda i: (cos[i] - fr.c).length)
    d0 = _dijkstra(nbr, [start])
    span0 = max(d0.values()) or 1.0
    cur = dict(d0)
    tips, tip_d = [], []
    for _ in range(min(2 * (order if isinstance(order, int) else 8) + 2, 26)):
        best = max(cur, key=cur.get)
        if cur[best] < 0.2 * span0:
            break
        dist = _dijkstra(nbr, [best])
        for k, v in dist.items():
            if v < cur.get(k, float("inf")):
                cur[k] = v
        if cyl[best][0] >= 0.5 * R_main:
            tips.append(best)
            tip_d.append(dist)
    if tips:
        seed = min(main_ids, key=lambda i: max(td.get(i, float("inf")) for td in tip_d))
    else:
        seed = start
    geo = _dijkstra(nbr, [seed])
    span = max(geo.values()) or 1.0

    # ---- bands and their pieces
    lens = sorted((cos[a] - cos[b]).length for a in main_ids for b, _ in nbr.get(a, ())[:1])
    p90 = lens[int(0.9 * (len(lens) - 1))] if lens else span / 40.0
    nb = int(max(12, min(80, span / max(1.5 * p90, 1e-9))))
    band = {i: min(nb - 1, int(geo[i] / span * nb)) for i in main_ids if i in geo}
    parent = {i: i for i in band}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i in band:
        for j, _ in nbr.get(i, ()):
            if j in band and band[j] == band[i]:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    pieces = {}
    for i in band:
        pieces.setdefault(find(i), []).append(i)
    piece_of = {i: find(i) for i in band}
    info = {}
    for pid, ids in pieces.items():
        rmin = min(cyl[i][0] for i in ids)
        cov = _coverage([cyl[i][1] for i in ids])
        info[pid] = {"ids": ids, "band": band[ids[0]], "hub": cov >= 0.6 * TAU or rmin <= 0.12 * R_main,
                     "centroid": sum((cos[i] for i in ids), Vector()) / len(ids)}
    # A ring broken into arcs is still body. The geodesic front runs further
    # over each tentacle's root than between them, so it comes down an
    # anemone's column in a ten-fold wave and every band cut the column into
    # arcs that each wrapped only part of the axis - eight of them read as arms.
    # So pieces of one band at the same radius and height are judged together,
    # by how much of the circle they OCCUPY: column arcs fill nearly all of it,
    # ten tentacles a third, thirty-two thin ones a sixth. Occupied bins, not
    # coverage - thirty-two tentacles leave no gap wider than 11 degrees.
    BINS = 72
    for pid, inf in info.items():
        ids = inf["ids"]
        inf["r"] = (min(cyl[i][0] for i in ids), max(cyl[i][0] for i in ids))
        inf["h"] = (min(cyl[i][2] for i in ids), max(cyl[i][2] for i in ids))
    tol = 0.05 * R_main
    by_band = {}
    for pid in pieces:
        by_band.setdefault(info[pid]["band"], []).append(pid)
    for b, pids in by_band.items():
        cand = [p for p in pids if not info[p]["hub"]]
        if len(cand) < 2:
            continue
        up = {p: p for p in cand}

        def f2(x):
            while up[x] != x:
                up[x] = up[up[x]]
                x = up[x]
            return x
        for i_, p in enumerate(cand):
            for q in cand[i_ + 1:]:
                A, B = info[p], info[q]
                if (A["r"][0] - tol <= B["r"][1] and B["r"][0] - tol <= A["r"][1]
                        and A["h"][0] - tol <= B["h"][1] and B["h"][0] - tol <= A["h"][1]):
                    up[f2(p)] = f2(q)
        clusters = {}
        for p in cand:
            clusters.setdefault(f2(p), []).append(p)
        for ps in clusters.values():
            occupied = {int((cyl[i][1] + math.pi) / TAU * BINS) % BINS for p in ps for i in info[p]["ids"]}
            if len(occupied) >= 0.55 * BINS:
                for p in ps:
                    info[p]["hub"] = True

    links = {pid: set() for pid in pieces}
    for i in band:
        for j, _ in nbr.get(i, ()):
            if j in band and band[j] != band[i]:
                links[piece_of[i]].add(piece_of[j])
                links[piece_of[j]].add(piece_of[i])

    # ---- appendages: connected groups of non-hub pieces
    app_pieces = {p for p in pieces if not info[p]["hub"]}
    seen, groups = set(), []
    for p in app_pieces:
        if p in seen:
            continue
        stack, g = [p], []
        seen.add(p)
        while stack:
            q = stack.pop()
            g.append(q)
            for r in links[q]:
                if r in app_pieces and r not in seen:
                    seen.add(r)
                    stack.append(r)
        groups.append(g)

    labels = [-1] * n              # -1 hub, -2 rigid loose part, k >= 0 appendage k
    appendages = []
    def back_path(leaf, gset):
        """Leaf to root through ever lower bands, the heaviest piece each step."""
        path, cur = [leaf], leaf
        while True:
            lower = [q for q in links[cur] if q in gset and info[q]["band"] < info[cur]["band"]]
            if not lower:
                break
            cur = max(lower, key=lambda q: len(info[q]["ids"]))
            path.append(cur)
        return list(reversed(path))

    branches = []              # (pieces, path)
    for g in groups:
        gset = set(g)
        if not any(info[q]["hub"] for p in g for q in links[p]):
            continue
        root_band = min(info[p]["band"] for p in g)
        leaves = [p for p in g if info[p]["band"] >= root_band + 3
                  and not any(q in gset and info[q]["band"] > info[p]["band"] for q in links[p])]
        if not leaves:
            leaves = [max(g, key=lambda p: info[p]["band"])]
        paths = [back_path(lf, gset) for lf in leaves]
        if len(paths) == 1:
            branches.append((g, paths[0]))
            continue
        shared = set(paths[0]).intersection(*map(set, paths[1:]))
        shortest = min(len(pth) for pth in paths)
        if len(shared) <= 0.3 * shortest:
            # Webbing, not a branch. An anemone's crown is fused between
            # neighbouring tentacles, and two of them came out as one appendage
            # with two tips: the second tentacle's skin projected onto the first
            # one's bones and stretched 11x when they curled. Split at the fork:
            # each tip is its own appendage, the shared stub is body.
            on_path = {}
            for k, pth in enumerate(paths):
                for p in pth:
                    if p not in shared:
                        on_path[p] = k
            owned = {k: [] for k in range(len(paths))}
            for p in g:
                if p in shared:
                    info[p]["hub"] = True
                    continue
                k = on_path.get(p)
                if k is None:
                    near = [on_path[q] for q in links[p] if q in on_path]
                    k = near[0] if near else None
                if k is not None:
                    owned[k].append(p)
            for k, pth in enumerate(paths):
                branches.append((owned[k], [p for p in pth if p not in shared]))
        else:
            warnings.append("an appendage branches (%d tips on a %d-band trunk): rigged along its "
                            "longest branch, the others follow it" % (len(leaves), len(shared)))
            branches.append((g, max(paths, key=len)))

    for g, path in branches:
        if not path:
            continue
        ids = [i for p in g for i in info[p]["ids"]]
        if len(ids) < max(12, min_share * n):
            continue                       # stays hub: a bump, not an arm
        root = path[0]
        rootset = set(info[root]["ids"])
        gset = set(g)
        touching = [j for i in rootset for j, _ in nbr.get(i, ()) if j in piece_of
                    and piece_of[j] not in gset]
        attach = (sum((cos[j] for j in touching), Vector()) / len(touching)) if touching \
            else info[root]["centroid"]
        tip = max(ids, key=lambda i: geo[i])
        # An appendage ENDS. Its tip is as far from the centre as the skin goes
        # there; a patch of body the bands happened to isolate carries on into
        # more body beyond its furthest vertex.
        if any(geo.get(j, 0.0) > geo[tip] + 1e-9 for j, _ in nbr.get(tip, ())):
            continue
        poly = [attach] + [info[p]["centroid"] for p in path] + [cos[tip]]
        widths = []
        for p in path:
            c = info[p]["centroid"]
            widths.append(2.0 * sum((cos[i] - c).length for i in info[p]["ids"]) / len(info[p]["ids"]))
        widths.sort()
        width = widths[len(widths) // 2] if widths else 0.0
        if _arc(poly) < 1.5 * width:
            continue                       # a stub wider than it is long is a bump
        appendages.append({"ids": ids, "poly": _dedupe(poly), "loose": False, "width": width})

    # ---- loose parts
    tree = KDTree(len(main_ids))
    for k, i in enumerate(main_ids):
        tree.insert(cos[i], k)
    tree.balance()
    rigid = []
    for cid, size in sizes.items():
        if cid == main:
            continue
        ids = [i for i in range(n) if comp[i] == cid]
        pts = [cos[i] for i in ids]
        centre, lam, vecs = _pca(pts) if len(pts) >= 4 else (pts[0], [0, 0, 0], None)
        near = [(tree.find(cos[i])[2], i) for i in ids]
        dmin, root_v = min(near)
        extent = 2.0 * math.sqrt(max(lam[2], 0.0)) * 1.7 if lam else 0.0
        elong = math.sqrt(lam[2] / max(lam[1], 1e-18)) if lam else 0.0
        if elong < 3.0 or extent < 0.08 * R_main:
            rigid.append({"ids": ids, "centre": centre})
            continue
        if dmin > 0.15 * R_main:
            warnings.append("a loose part of %d vertices floats %.3f from the body - attached "
                            "to the nearest skin anyway" % (len(ids), dmin))
        inbr = world_me.adjacency(ids)
        dg = _dijkstra(inbr, [root_v])
        far = max(dg.values()) or 1.0
        k = max(6, min(40, int(far / max(extent / 30.0, 1e-9))))
        rows = {}
        for i in ids:
            if i in dg:
                rows.setdefault(min(k - 1, int(dg[i] / far * k)), []).append(i)
        chain = [cos[main_ids[tree.find(cos[root_v])[1]]]]
        widths = []
        for b in sorted(rows):
            c = sum((cos[i] for i in rows[b]), Vector()) / len(rows[b])
            chain.append(c)
            widths.append(2.0 * sum((cos[i] - c).length for i in rows[b]) / len(rows[b]))
        chain.append(cos[max(dg, key=dg.get)])
        widths.sort()
        appendages.append({"ids": ids, "poly": _dedupe(chain), "loose": True,
                           "width": widths[len(widths) // 2]})

    # appendages too short to animate stay body
    keep = []
    for ap in appendages:
        if _arc(ap["poly"]) < 0.1 * R_main and not ap["loose"]:
            continue
        keep.append(ap)
    appendages = keep

    on_arm = {i for ap in appendages if not ap["loose"] for i in ap["ids"]}
    hub_ids = [i for i in main_ids if i not in on_arm]
    # ---- the oral side: where the appendages point
    if oral:
        from .bodymap import axis_vector
        if axis_vector(oral).dot(fr.a) > 0.0:
            fr.flip()
        oral_source = "given"
    else:
        tot, wsum = 0.0, 0.0
        for ap in appendages:
            d = ap["poly"][-1] - ap["poly"][0]
            tot += d.dot(fr.a)
            wsum += d.length
        if wsum > 0 and abs(tot) > 0.35 * wsum:
            if tot > 0.0:
                fr.flip()                 # appendages point along +a: a must be aboral
            oral_source = "appendages point to it"
        else:
            if fr.a.dot(Vector((0.0, 0.0, 1.0))) < 0.0:
                fr.flip()
            oral_source = "appendages lie in the plane - oral side taken as the floor side (a sea star's mouth is underneath)"
    cyl = [fr.cyl(p) for p in cos]

    # ---- the hub's shape
    hub_r = sorted(cyl[i][0] for i in hub_ids)
    R_hub = hub_r[int(0.97 * (len(hub_r) - 1))] if hub_r else R_main
    hs = [cyl[i][2] for i in hub_ids]
    h_lo, h_hi = min(hs), max(hs)
    height = h_hi - h_lo
    rim = [i for i in hub_ids if cyl[i][0] >= 0.92 * R_hub]
    rim_h = sum(cyl[i][2] for i in rim) / len(rim) if rim else h_lo
    fineness = height / max(2.0 * R_hub, 1e-9)

    for ap in appendages:
        r0, th0, h0 = fr.cyl(ap["poly"][0])
        d = ap["poly"][-1] - ap["poly"][0]
        ap.update({"theta": th0, "root_r": r0 / max(R_hub, 1e-9), "root_h": h0,
                   "length": _arc(ap["poly"]),
                   "axial": d.dot(-fr.a) / max(d.length, 1e-9)})     # + toward oral
    # ---- kind
    notes = []
    arms = appendages
    if not arms:
        guess = "medusa" if (rim_h - h_lo) < 0.35 * height and fineness < 1.2 else "polyp"
        notes.append("no appendages - a bare bell or column")
    else:
        planar = sum(abs(ap["axial"]) for ap in arms) / len(arms) < 0.5
        if planar:
            L_arm = sorted(ap["length"] for ap in arms)[len(arms) // 2]
            W_arm = sorted(ap["width"] for ap in arms)[len(arms) // 2]
            guess = "ophiuroid" if (W_arm < 0.12 * L_arm and R_hub < 0.4 * L_arm) else "asteroid"
        else:
            guess = "polyp" if fineness >= 0.8 else "medusa"
    kind_final = kind or guess
    if kind and kind not in KINDS:
        return {"error": "kind %r - expected one of %s" % (kind, ", ".join(KINDS))}

    # ---- roles and names: appendage 01 is the one nearest forward
    for ap in appendages:
        if kind_final == "medusa":
            ap["role"] = "tentacle" if ap["root_r"] >= 0.55 else "oral_arm"
        elif kind_final == "polyp":
            ap["role"] = "tentacle"
        else:
            ap["role"] = "arm"
    by_role = {}
    for ap in appendages:
        by_role.setdefault(ap["role"], []).append(ap)
    for role, aps in by_role.items():
        half = math.pi / max(len(aps), 1)
        aps.sort(key=lambda ap: (ap["theta"] + half) % TAU)
        for k, ap in enumerate(aps):
            ap["name"] = "%s%02d" % (role, k + 1)
    if by_role.get("arm") and isinstance(order, int) and len(by_role["arm"]) != order:
        warnings.append("%d arms found on a %d-fold body - check the renders"
                        % (len(by_role["arm"]), order))

    for k, ap in enumerate(appendages):
        for i in ap["ids"]:
            labels[i] = k
    for rg in rigid:
        for i in rg["ids"]:
            labels[i] = -2

    return {"mesh": mesh_name, "forward": forward, "frame": fr, "order": order,
            "symmetry_score": sym.get("score"), "kind": kind_final, "kind_guessed": kind is None,
            "kind_suggested": guess, "oral_source": oral_source,
            "R_hub": R_hub, "hub_height": height, "fineness": fineness, "h_lo": h_lo, "h_hi": h_hi,
            "rim_h": rim_h, "hub_ids": hub_ids, "appendages": appendages, "rigid": rigid,
            "labels": labels, "seed": seed, "bands": nb, "notes": notes, "warnings": warnings}


class _WorldMesh:
    def __init__(self, me, cos):
        self.me, self.cos = me, cos

    def adjacency(self, ids):
        keep = set(ids)
        nbr = {}
        cos = self.cos
        for e in self.me.edges:
            a, b = e.vertices
            if a in keep and b in keep:
                w = (cos[a] - cos[b]).length
                nbr.setdefault(a, []).append((b, w))
                nbr.setdefault(b, []).append((a, w))
        return nbr


def _dedupe(poly):
    out = [poly[0]]
    for p in poly[1:]:
        if (p - out[-1]).length > 1e-7:
            out.append(p)
    return out


def summary(d):
    if "error" in d:
        return "ERROR: " + d["error"]
    fr = d["frame"]
    lines = ["%s: %s radial body, %s-fold about %s, %s%s" % (
        d["mesh"], d["kind"], d["order"], _v(fr.a), "kind guessed from shape" if d["kind_guessed"] else "kind given",
        "" if d["kind"] == d["kind_suggested"] else " (shape suggests %s)" % d["kind_suggested"])]
    lines.append("  hub radius %.3f, height %.3f, fineness %.2f; oral side: %s"
                 % (d["R_hub"], d["hub_height"], d["fineness"], d["oral_source"]))
    for ap in d["appendages"]:
        lines.append("  %-11s %s %4d verts  %.3f long  %.4f wide  root at %4.0f deg, %3.0f%% of hub radius, "
                     "points %s" % (ap["name"], "loose" if ap["loose"] else "     ", len(ap["ids"]), ap["length"],
                                    ap["width"], math.degrees(ap["theta"]), 100 * ap["root_r"],
                                    "oral" if ap["axial"] > 0.5 else ("aboral" if ap["axial"] < -0.5 else "outward")))
    if d["rigid"]:
        lines.append("  %d rigid loose parts ride the skin under them" % len(d["rigid"]))
    lines += ["  NOTE " + x for x in d["notes"]] + ["  WARN " + w for w in d["warnings"]]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# building
# --------------------------------------------------------------------------

def _rib_count(order, tentacles):
    if isinstance(order, int) and order >= 6:
        m = order
    elif isinstance(order, int) and order >= 3:
        m = 2 * order
    else:
        m = 8
    if tentacles and tentacles % m != 0 and m % max(tentacles, 1) != 0 and 6 <= tentacles <= 16:
        m = tentacles
    return max(6, min(16, m))


def _rib_profile(d, theta, count):
    """Mid-shell points down the bell meridian at `theta`: (r, h) at radii
    through the bell to its margin."""
    fr = d["frame"]
    cos = [bpy.data.objects[d["mesh"]].matrix_world @ v.co for v in bpy.data.objects[d["mesh"]].data.vertices]
    half = math.pi / count
    wedge = []
    for i in d["hub_ids"]:
        r, th, h = fr.cyl(cos[i])
        if abs(_wrap(th - theta)) <= half:
            wedge.append((r, h))
    if len(wedge) < 8:
        wedge = [fr.cyl(cos[i])[::2] for i in d["hub_ids"]]
        wedge = [(r, h) for r, h in wedge]
    R = max(r for r, _ in wedge)
    bins = 16
    rows = [[] for _ in range(bins)]
    for r, h in wedge:
        rows[min(bins - 1, int(r / max(R, 1e-9) * bins))].append(h)
    mids = []
    for k, hs in enumerate(rows):
        if hs:
            mids.append(((k + 0.5) / bins * R, 0.5 * (min(hs) + max(hs))))
    # the margin itself: mean height of the outermost skin
    outer = [h for r, h in wedge if r >= 0.95 * R]
    mids.append((R, sum(outer) / len(outer)))

    def h_at(r):
        best = min(mids, key=lambda m: abs(m[0] - r))
        return best[1]
    return R, h_at


def build(mesh_name, detection=None, rig_name=None, kind=None, forward="-Y", rib_segments=3):
    """An armature for a radial mesh with no rig. Not weighted - call `skin`."""
    d = detection or detect(mesh_name, kind=kind, forward=forward)
    if "error" in d:
        return d
    obj = bpy.data.objects[mesh_name]
    fr = d["frame"]
    rig_name = rig_name or mesh_name + "_rig"
    old = bpy.data.objects.get(rig_name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    arm = bpy.data.armatures.new(rig_name)
    rig = bpy.data.objects.new(rig_name, arm)
    coll = obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection
    coll.objects.link(rig)
    rig.matrix_world = Matrix.Identity(4)

    from .maw import _edit
    _edit(rig)
    eb = arm.edit_bones
    R, H = d["R_hub"], d["hub_height"]
    roles = {}

    hub = eb.new("hub")
    h_mid = 0.5 * (d["h_lo"] + d["h_hi"])
    hub.head = fr.point(0.0, 0.0, h_mid)
    hub.tail = hub.head + fr.a * max(0.5 * H, 0.3 * R)
    hub.align_roll(fr.e1)
    roles["hub"] = "hub"

    ribs = []
    tentacles = [ap for ap in d["appendages"] if ap["role"] == "tentacle"]
    if d["kind"] == "medusa":
        count = _rib_count(d["order"], len(tentacles))
        theta0 = min((ap["theta"] for ap in tentacles), key=lambda t: abs(_wrap(t)), default=0.0) \
            if tentacles and (len(tentacles) % count == 0 or count % len(tentacles) == 0) else 0.0
        fracs = [0.25 + 0.75 * k / rib_segments for k in range(rib_segments + 1)]
        for j in range(count):
            th = theta0 + TAU * j / count
            Rw, h_at = _rib_profile(d, th, count)
            joints = [fr.point(f * Rw, th, h_at(f * Rw)) for f in fracs]
            names = []
            for k in range(rib_segments):
                nm = "rib%02d_%d" % (j + 1, k + 1)
                b = eb.new(nm)
                b.head, b.tail = joints[k], joints[k + 1]
                b.parent = eb[names[-1]] if names else hub
                b.use_connect = bool(names)
                b.align_roll(fr.a)
                names.append(nm)
                roles[nm] = "rib"
            ribs.append({"name": "rib%02d" % (j + 1), "theta": th, "bones": names,
                         "radii": [f * Rw for f in fracs]})

    # One bone count per appendage kind: the median arm's length over 1.2 widths. Counted per arm,
    # a symmetric sea star whose metaball arms differ ~10% in width got 3 bones on one arm (3.49)
    # and 4 on the rest (3.63-3.89).
    ratios = {}
    for ap in d["appendages"]:
        ratios.setdefault(ap["role"], []).append(ap["length"] / (1.2 * max(ap["width"], 1e-6)))
    seg_count = {}
    for role, rs in ratios.items():
        rs = sorted(rs)
        mid = len(rs) // 2
        med = rs[mid] if len(rs) % 2 else 0.5 * (rs[mid - 1] + rs[mid])
        cap = {"tentacle": 12, "oral_arm": 6, "arm": 8}[role]
        seg_count[role] = int(max(3, min(cap, round(med))))

    apps = []
    for ap in d["appendages"]:
        L, W = ap["length"], max(ap["width"], 1e-6)
        segs = seg_count[ap["role"]]
        joints = _resample(ap["poly"], segs)
        if ap["role"] == "oral_arm" or not ribs:
            parent = "hub"
        else:
            rib = min(ribs, key=lambda rb: abs(_wrap(rb["theta"] - ap["theta"])))
            parent = rib["bones"][-1]
        names = []
        for k in range(segs):
            nm = "%s_%d" % (ap["name"], k + 1)
            b = eb.new(nm)
            b.head, b.tail = joints[k], joints[k + 1]
            b.parent = eb[names[-1]] if names else eb[parent]
            b.use_connect = bool(names)
            b.align_roll(fr.a)
            names.append(nm)
            roles[nm] = ap["role"]
        apps.append({"name": ap["name"], "role": ap["role"], "theta": ap["theta"], "bones": names,
                     "parent": parent, "loose": ap["loose"], "length": L, "width": W,
                     "root_r": ap["root_r"], "attach": _v(joints[0])})

    bpy.ops.object.mode_set(mode="OBJECT")
    for nm, role in roles.items():
        arm.bones[nm][ROLE] = role
    stored = {"version": 1, "mesh": mesh_name, "kind": d["kind"], "kind_guessed": d["kind_guessed"],
              "order": d["order"], "forward": forward, "axis": _v(fr.a), "centre": _v(fr.c),
              "e1": _v(fr.e1), "e2": _v(fr.e2), "R_hub": R, "hub_height": H, "fineness": d["fineness"],
              "h_lo": d["h_lo"], "h_hi": d["h_hi"], "rim_h": d["rim_h"],
              "ribs": ribs, "appendages": apps}
    rig.data[PROP] = json.dumps(stored)
    txt = bpy.data.texts.get(PARTS + mesh_name) or bpy.data.texts.new(PARTS + mesh_name)
    txt.clear()
    txt.write(json.dumps({"n": len(obj.data.vertices), "labels": d["labels"]}))
    return {"rig": rig_name, "kind": d["kind"], "bones": len(arm.bones), "ribs": len(ribs),
            "appendages": {a["name"]: len(a["bones"]) for a in apps}}


def read(rig):
    raw = rig.data.get(PROP) if rig is not None else None
    if not raw:
        return None
    st = json.loads(raw)
    names = {b.name for b in rig.data.bones}
    for a in st["appendages"] + st["ribs"]:
        if any(b not in names for b in a["bones"]):
            return None
    return st


# --------------------------------------------------------------------------
# skinning
# --------------------------------------------------------------------------

def skin(rig_name):
    """Write every vertex's weights directly - no bone heat. Idempotent."""
    rig = bpy.data.objects.get(rig_name)
    st = read(rig)
    if st is None:
        return {"error": "%s has no radial rig - run radial.build" % rig_name}
    obj = bpy.data.objects[st["mesh"]]
    txt = bpy.data.texts.get(PARTS + st["mesh"])
    if txt is None:
        return {"error": "vertex labels for %s are missing - rebuild" % st["mesh"]}
    parts = json.loads(txt.as_string())
    if parts["n"] != len(obj.data.vertices):
        return {"error": "%s has changed since it was measured - rebuild" % st["mesh"]}
    labels = parts["labels"]
    bones = rig.data.bones
    a, c = Vector(st["axis"]), Vector(st["centre"])
    e1, e2 = Vector(st["e1"]), Vector(st["e2"])
    to_rig = rig.matrix_world.inverted() @ obj.matrix_world
    cos = [to_rig @ v.co for v in obj.data.vertices]

    def cyl(p):
        dd = p - c
        return math.hypot(dd.dot(e1), dd.dot(e2)), math.atan2(dd.dot(e2), dd.dot(e1))

    ribs = sorted(st["ribs"], key=lambda rb: rb["theta"] % TAU)

    def hat(s, centres, names):
        """Linear blend between the two centres either side of s."""
        if s <= centres[0]:
            return {names[0]: 1.0}
        if s >= centres[-1]:
            return {names[-1]: 1.0}
        for k in range(len(centres) - 1):
            if centres[k] <= s <= centres[k + 1]:
                t = (s - centres[k]) / max(centres[k + 1] - centres[k], 1e-12)
                out = {names[k]: 1.0 - t}
                out[names[k + 1]] = out.get(names[k + 1], 0.0) + t
                return out
        return {names[-1]: 1.0}

    def hub_weights(p):
        if not ribs:
            return {"hub": 1.0}
        r, th = cyl(p)
        # the two ribs either side, by angle
        m = len(ribs)
        k = max(range(m), key=lambda j: -abs(_wrap(th - ribs[j]["theta"])))
        dk = _wrap(th - ribs[k]["theta"])
        k2 = (k + 1) % m if dk >= 0 else (k - 1) % m
        gap = abs(_wrap(ribs[k2]["theta"] - ribs[k]["theta"])) or TAU / m
        t = min(1.0, abs(dk) / gap)
        out = {}
        for rb, share in ((ribs[k], 1.0 - t), (ribs[k2], t)):
            rr = rb["radii"]
            centres = [0.0] + [0.5 * (rr[i] + rr[i + 1]) for i in range(len(rr) - 1)]
            for nm, w in hat(r, centres, ["hub"] + rb["bones"]).items():
                out[nm] = out.get(nm, 0.0) + w * share
        return out

    chains = []
    for ap in st["appendages"]:
        pts = [bones[ap["bones"][0]].head_local.copy()] + [bones[b].tail_local.copy() for b in ap["bones"]]
        seg = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
        cum = [0.0]
        for s_ in seg:
            cum.append(cum[-1] + s_)
        centres = [0.0] + [0.5 * (cum[i] + cum[i + 1]) for i in range(len(seg))]
        root = hub_weights(pts[0]) if ap["parent"] in ("hub",) or ap["parent"].startswith("rib") \
            else {ap["parent"]: 1.0}
        chains.append({"pts": pts, "cum": cum, "centres": centres, "bones": ap["bones"], "root": root})

    def chain_weights(p, ch):
        best = (float("inf"), 0.0)
        pts, cum = ch["pts"], ch["cum"]
        for i in range(len(pts) - 1):
            t, dist = _seg_param(p, pts[i], pts[i + 1])
            if dist < best[0]:
                best = (dist, cum[i] + t * (cum[i + 1] - cum[i]))
        out = {}
        for nm, w in hat(best[1], ch["centres"], ["__root__"] + ch["bones"]).items():
            if nm == "__root__":
                for rn, rw in ch["root"].items():
                    out[rn] = out.get(rn, 0.0) + w * rw
            else:
                out[nm] = out.get(nm, 0.0) + w
        return out

    weights = [None] * len(cos)
    for i, p in enumerate(cos):
        lab = labels[i]
        if lab >= 0:
            weights[i] = chain_weights(p, chains[lab])
        elif lab == -1:
            weights[i] = hub_weights(p)
    # rigid loose parts copy the weights of the skin nearest them
    body = [i for i in range(len(cos)) if labels[i] != -2]
    tree = KDTree(len(body))
    for k, i in enumerate(body):
        tree.insert(cos[i], k)
    tree.balance()
    for i in range(len(cos)):
        if weights[i] is None:
            weights[i] = dict(weights[body[tree.find(cos[i])[1]]])

    ours = {b.name for b in bones}
    for g in list(obj.vertex_groups):
        if g.name in ours:
            obj.vertex_groups.remove(g)
    groups = {nm: obj.vertex_groups.new(name=nm) for nm in sorted(ours) if bones[nm].use_deform}
    buckets = {}
    for i, w in enumerate(weights):
        tot = sum(w.values()) or 1.0
        for nm, x in w.items():
            if x / tot > 1e-4:
                buckets.setdefault((nm, round(x / tot, 4)), []).append(i)
    for (nm, x), ids in buckets.items():
        groups[nm].add(ids, x, "REPLACE")

    if obj.parent is not rig:
        mwo = obj.matrix_world.copy()
        obj.parent = rig
        obj.matrix_world = mwo
    mod = next((m for m in obj.modifiers if m.type == "ARMATURE"), None) or obj.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    mod.use_vertex_groups = True
    # Coverage is read back from the mesh, not assumed: a vertex counts when a deform bone of this
    # rig holds some of its weight, and a bone counts when it holds some vertex.
    by_index = {g.index: nm for nm, g in groups.items()}
    used, uncovered = set(), 0
    for v in obj.data.vertices:
        held = {by_index[g.group] for g in v.groups if g.group in by_index and g.weight > 0.0}
        used |= held
        uncovered += not held
    covered = 1.0 - uncovered / float(max(1, len(obj.data.vertices)))
    return {"mesh": obj.name, "rig": rig_name, "coverage": round(covered, 4), "vertices": len(cos),
            "vertices_unweighted": uncovered,
            "bones_weighted": len(used), "bones_without_skin": sorted(ours - used),
            "passed": uncovered == 0 and not (ours - used) - {"hub"},
            "note": "weights written from the body's own parts; bone heat is not used"}


# --------------------------------------------------------------------------
# posing
# --------------------------------------------------------------------------

def body_map(rig, st=None):
    """The subset of a `bodymap.build` result the motion and check machinery
    reads, for a body that has no spine for `bodymap` to find."""
    st = st or read(rig)
    pts = [p for b in rig.data.bones for p in (b.head_local, b.tail_local)]
    mw = rig.matrix_world
    zs = [(mw @ p).z for p in pts]
    size = max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))
    from .bodymap import axis_vector
    fwd = axis_vector(st["forward"])
    up = Vector((0.0, 0.0, 1.0))
    return {"rig": rig.name, "forward": st["forward"], "up": "Z", "floor": 0.0, "fwd": fwd,
            "up_vec": up, "lat": up.cross(fwd).normalized(), "height": max(zs), "size": size,
            "limbs": [], "tail": [], "wings": [], "axial": [], "maw": None, "radial": st}


class RadialRig:
    """Rest measurements and the pose maths for a radial rig.

    Every rotation is given in the armature's REST frame about the bone's own
    head and carried down the chain by forward kinematics, so bending the first
    bone of a rib swings the whole rib and each child adds its own bend on top.

        q(theta)  axis radial x aboral: + turns a radial bone toward aboral and
                  an oral-pointing one outward - lift, splay
        a         the symmetry axis: + sweeps round the body, increasing angle
    """

    def __init__(self, rig_name):
        from . import motion
        self.rig = bpy.data.objects[rig_name]
        st = read(self.rig)
        if st is None:
            raise ValueError("%s has no radial rig - run radial.build" % rig_name)
        self.st = st
        self.bm = body_map(self.rig, st)
        self.body = motion.Body(self.rig, self.bm)
        self.a, self.c = Vector(st["axis"]), Vector(st["centre"])
        self.e1, self.e2 = Vector(st["e1"]), Vector(st["e2"])
        self.ribs = sorted(st["ribs"], key=lambda rb: rb["theta"] % TAU)
        self.apps = st["appendages"]
        self.kind, self.order = st["kind"], st["order"]

    def radial(self, theta):
        return (self.e1 * math.cos(theta) + self.e2 * math.sin(theta)).normalized()

    def q(self, theta):
        return self.radial(theta).cross(self.a).normalized()

    def by_role(self, role):
        return [ap for ap in self.apps if ap["role"] == role]

    def fk(self, rots, root=None):
        body = self.body
        posed = {}
        for b in body.bones:
            R = rots.get(b.name)
            L = None
            if R is not None:
                rb = body.rest[b.name].to_3x3()
                L = (rb.inverted() @ R @ rb).to_4x4()
            if b.parent is None:
                m = body.rest[b.name] if root is None else root @ body.rest[b.name]
            else:
                m = posed[b.parent.name] @ body.rest_local[b.name]
            posed[b.name] = m @ L if L is not None else m
        return posed

    def radius(self, mats, bone):
        """Distance of a bone's tail from the axis, in a posed frame."""
        from .motion import tail_of
        d = tail_of(self.body, mats, bone) - self.c
        return (d - self.a * d.dot(self.a)).length

    def rim_radii(self, mats):
        return [self.radius(mats, rb["bones"][-1]) for rb in self.ribs]

    # ---------------------------------------------------------------- bell
    def rib_rots(self, rib, bend_deg, rots):
        """Bend a rib by `bend_deg` in total, spread toward the margin: + closes
        the bell (see `bell_sign`)."""
        n = len(rib["bones"])
        w = [(k + 1) for k in range(n)]
        tot = float(sum(w))
        axis = self.q(rib["theta"])
        for k, nm in enumerate(rib["bones"]):
            rots[nm] = Matrix.Rotation(math.radians(bend_deg * self.bell_sign * w[k] / tot), 3, axis)
        return rots

    @property
    def bell_sign(self):
        if not hasattr(self, "_bell_sign"):
            self._bell_sign = 1.0
            if self.ribs:
                rib = self.ribs[0]
                r0 = self.radius(self.body.fk(), rib["bones"][-1])
                r1 = self.radius(self.fk(self.rib_rots(rib, 10.0, {})), rib["bones"][-1])
                self._bell_sign = 1.0 if r1 < r0 else -1.0
        return self._bell_sign

    def bend_for_contraction(self, fraction):
        """Total rib bend that pulls the margin in by `fraction` of its radius."""
        if not self.ribs:
            return 0.0
        rib = self.ribs[0]
        r0 = self.radius(self.body.fk(), rib["bones"][-1])
        want = (1.0 - fraction) * r0
        lo, hi = 0.0, 120.0
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            if self.radius(self.fk(self.rib_rots(rib, mid, {})), rib["bones"][-1]) > want:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    # ----------------------------------------------------------- appendages
    def chain_rots(self, ap, lift_deg=0.0, sweep_deg=0.0, rots=None, profile=None):
        """Spread `lift_deg` about q and `sweep_deg` about the axis along a
        chain, by `profile` (weights per bone; default even)."""
        rots = rots if rots is not None else {}
        n = len(ap["bones"])
        prof = profile or [1.0] * n
        tot = float(sum(prof)) or 1.0
        qa = self.q(ap["theta"])
        for k, nm in enumerate(ap["bones"]):
            lift = math.radians(lift_deg * prof[k] / tot)
            sweep = math.radians(sweep_deg * prof[k] / tot)
            R = Matrix.Rotation(lift, 3, qa) @ Matrix.Rotation(sweep, 3, self.a)
            rots[nm] = R @ rots[nm] if nm in rots else R
        return rots

    def wave_rots(self, ap, phase, amp_deg, wavelength=1.0, rots=None, axis="q"):
        """A bend travelling root to tip: bone k turns amp * s * sin(2 pi (phase
        - s / wavelength)), s its position along the chain, so the tip lags."""
        rots = rots if rots is not None else {}
        n = len(ap["bones"])
        ax = self.q(ap["theta"]) if axis == "q" else self.a
        for k, nm in enumerate(ap["bones"]):
            s = (k + 0.5) / n
            ang = math.radians(amp_deg * (0.3 + 0.7 * s) / n * 2.0) * math.sin(TAU * (phase - s / wavelength))
            R = Matrix.Rotation(ang, 3, ax)
            rots[nm] = R @ rots[nm] if nm in rots else R
        return rots
