"""Hoppers: find the jumping legs on the skin, their joints, and rig them.

A walking leg and a jumping leg differ in exactly the things a two-bone limb
cannot express. A cricket's hind femur is swollen with the extensor muscle and
its tibia folds flat under it; a rabbit stands on a hind foot as long as its
shin, heel on the ground, and pushes off by lifting that heel. Both legs are
Z-shaped - three segments folded against each other - and the jump is the Z
opening. `decompose` sees neither: its Reeb graph read the test cricket as a
two-joint spine and the rabbit's ears as arms.

So hopper legs are found from what a standing body does have for certain -
its ground contacts - and walked up the skin:

1. SEED. Each paired contact from `measure.ground_contacts` is a foot. The seed
   is the vertex of that patch farthest (geodesically) from the body's centre:
   the toe tip, not the middle of a flat sole, so the foot itself is walked as
   a segment rather than swallowed by the first band.
2. WALK. Geodesic distance from the seed, in bands. On a tube each band is a
   ring and its centroid advances one band width per band. Where the tube
   enters the body the ring spreads over it and the centroid stalls - that is
   where the leg ends, whatever the leg's thickness does on the way (a cricket's
   femur is five times its tibia's radius and is still leg). A band that
   crosses the midline, or grows past half the body's half-width, is body too.
3. JOINTS. The band centroids are the leg's medial line. Joints are its
   corners: the optimal k-segment polyline through them by dynamic programming,
   with k the smallest that fits to a fraction of the leg's radius.
4. HIDDEN JOINTS. A rabbit's femur is buried in its haunch: no silhouette shows
   its knee, so walking stops mid-shin. When the walk ends well below the body's
   middle, the hip is placed at the centre of the flesh the leg entered, and the
   knee on the visible shank's own line, where femur / tibia comes out at the
   ratio `KINDS` carries for that animal. Both are reported as inferred.
5. KIND. The saltatorial pair is the longest by a margin (`SALTATORIAL_RATIO`);
   six legs with a swollen hind femur is an orthopteran, four with a long foot
   lying on the floor a leporid. The renders can overrule it with `kind=`.

Everything is in world space; `build` writes the rig in the same frame.
"""

from __future__ import annotations

import json
import math

import bpy
from mathutils import Vector

from . import measure

PROP = "hopper"
ROLE = "hop_role"

# Leg-length ratio (hind / mean of the others) above which a pair is saltatorial.
SALTATORIAL_RATIO = 1.35

# Per kind: the segment roles of each leg rank, root -> tip, and the proportion
# priors used where a joint cannot be seen. Filled in from the literature in
# `references/hoppers.md`; these defaults are the test bodies' own anatomy.
KINDS = {
    "orthopteran": {
        "ranks": {"fore": ["femur", "tibia", "tarsus"], "mid": ["femur", "tibia", "tarsus"],
                  "hind": ["femur", "tibia", "tarsus"]},
        "femur_over_tibia": {"hind": 1.1, "fore": 1.0, "mid": 1.0},
    },
    "leporid": {
        "ranks": {"fore": ["humerus", "forearm", "paw", "digits"],
                  "hind": ["femur", "tibia", "metatarsus", "toes"]},
        # NZ White femur 82.3 mm (osteomorphometry, PubMed 23420943); crural
        # index tibia / femur ~1.15 (UNVERIFIED - Young et al. 2014 rank it
        # pika < Sylvilagus < Lepus but print no means); humerus / forearm ~0.92
        # (UNVERIFIED)
        "femur_over_tibia": {"hind": 0.87, "fore": 0.92},
        # tibia over the whole flat foot, heel to toe tip: ~95 mm on ~76 mm
        # (UNVERIFIED, from MT3 / femur 0.5-0.6 plus toes)
        "tibia_over_foot": {"hind": 1.25},
        # share of the foot from ball to toe tip, used when the ball's bend is
        # too slight to see
        "toe_share": {"hind": 0.31, "fore": 0.33},
    },
}


# --------------------------------------------------------------------------
# mesh access
# --------------------------------------------------------------------------

class _Mesh:
    def __init__(self, obj):
        mw = obj.matrix_world
        self.obj = obj
        self.V = [mw @ v.co for v in obj.data.vertices]
        self.adj = [[] for _ in self.V]
        for e in obj.data.edges:
            a, b = e.vertices
            self.adj[a].append(b)
            self.adj[b].append(a)

    def geodesic(self, sources, limit=float("inf"), within=None):
        import heapq
        dist = {}
        pq = []
        for s in sources:
            dist[s] = 0.0
            pq.append((0.0, s))
        heapq.heapify(pq)
        V, adj = self.V, self.adj
        while pq:
            d, v = heapq.heappop(pq)
            if d > dist.get(v, float("inf")) or d > limit:
                continue
            for n in adj[v]:
                if within is not None and n not in within:
                    continue
                nd = d + (V[v] - V[n]).length
                if nd < dist.get(n, float("inf")):
                    dist[n] = nd
                    heapq.heappush(pq, (nd, n))
        return dist


def _components(verts, adj):
    """Connected pieces of a vertex subset."""
    inside = set(verts)
    seen, out = set(), []
    for v0 in verts:
        if v0 in seen:
            continue
        stack, comp = [v0], []
        seen.add(v0)
        while stack:
            v = stack.pop()
            comp.append(v)
            for n in adj[v]:
                if n in inside and n not in seen:
                    seen.add(n)
                    stack.append(n)
        out.append(comp)
    return out


def thickness(obj, V, smooth=2):
    """Shape diameter per vertex: how far a ray cast inward along the normal
    travels before leaving the skin (Shapira, Shamir & Cohen-Or 2008). A leg is
    thin and a body thick whatever either is called, and it is what stops a
    walk where a tube enters the body."""
    from mathutils.bvhtree import BVHTree
    me = obj.data
    polys = [tuple(p.vertices) for p in me.polygons]
    tree = BVHTree.FromPolygons(V, polys)
    n3 = obj.matrix_world.to_3x3().inverted().transposed()
    far = max((max(p[i] for p in V) - min(p[i] for p in V)) for i in range(3))
    out = []
    for v, p in zip(me.vertices, V):
        n = (n3 @ v.normal).normalized()
        hit = tree.ray_cast(p - n * 1e-4 * far, -n, far)
        out.append(hit[3] if hit[0] is not None else 0.0)
    if smooth:
        adj = [[] for _ in V]
        for e in me.edges:
            a, b = e.vertices
            adj[a].append(b)
            adj[b].append(a)
        for _ in range(smooth):
            out = [0.5 * t + 0.5 * (sum(out[j] for j in adj[i]) / len(adj[i]) if adj[i] else t)
                   for i, t in enumerate(out)]
    return out


# --------------------------------------------------------------------------
# walking a leg
# --------------------------------------------------------------------------

def walk(mesh, seed, side_sign, lat_axis, mid_lat, half_width, band, max_bands=400,
         stall=0.45, claimed=None, sdf=None, core=None, exclude=None):
    """Band centroids from `seed` up a tube until it enters the body.

    Windows two bands wide, one band apart, so every window shares skin with the
    one before: single bands on these meshes broke into up to twelve pieces, and
    keeping the largest made the centroid jump and lost the leg at the knee.
    Every piece connected to the previous window is kept.

    Returns a list of bands, tip first: {"centroid", "radius", "verts", "d"}, and
    the reason the walk stopped."""
    dist = mesh.geodesic([seed])
    by_band = {}
    for v, dv in dist.items():
        by_band.setdefault(int(dv / band), []).append(v)
    bands, prev, slow = [], None, 0
    reason = "ran out of mesh"
    claimed = claimed or set()
    for k in range(max_bands):
        members = by_band.get(k, []) + by_band.get(k + 1, [])
        if exclude:
            members = [v for v in members if v not in exclude]
        if not members:
            break
        pieces = _components(members, mesh.adj)
        if prev is None:
            keep = [max(pieces, key=len)]
        else:
            keep = [p for p in pieces if any(v in prev or any(n in prev for n in mesh.adj[v]) for v in p)]
            if not keep:
                reason = "the band lost contact with the leg"
                break
        piece = [v for p in keep for v in p]
        c = sum((mesh.V[v] for v in piece), Vector()) / len(piece)
        r = sum((mesh.V[v] - c).length for v in piece) / len(piece)
        lat = [(mesh.V[v][lat_axis] - mid_lat) * side_sign for v in piece]
        core_share = (sum(1 for v in piece if sdf[v] > core) / len(piece)) if sdf is not None else 0.0
        if bands and min(lat) < -0.02 * half_width:
            reason = "the band crossed the midline"
            break
        if bands and core_share > 0.35:
            reason = "the band reached the body's core thickness"
            break
        if bands and r > 0.5 * half_width:
            reason = "the band grew past half the body's half-width"
            break
        if bands and claimed and sum(1 for v in piece if v in claimed) > 0.3 * len(piece):
            reason = "the band ran into another leg"
            break
        if len(bands) >= 3:
            step = (c - bands[-1]["centroid"]).length / band
            slow = slow + 1 if step < stall else 0
            if slow >= 3:
                bands = bands[:-2]            # the bands that already stalled
                reason = "the band stalled - the leg entered the body"
                break
        # the new band alone is what the leg owns; the window is what is measured
        own = by_band.get(k, [])
        own_set = set(piece)
        bands.append({"centroid": c, "radius": r, "verts": [v for v in own if v in own_set], "d": (k + 1) * band,
                      "core": core_share, "pieces": len(pieces)})
        prev = own_set
    return bands, reason


def fit_polyline(points, max_segments=4, min_samples=2):
    """Optimal k-segment polyline through ordered `points` with vertices on
    samples, no segment spanning fewer than `min_samples` steps. Returns
    {k: (indices, rms)} for k = 1..max_segments."""
    n = len(points)
    cost = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 2, n):
            a, b = points[i], points[j]
            ab = b - a
            L2 = max(ab.dot(ab), 1e-24)
            s = 0.0
            for m in range(i + 1, j):
                t = max(0.0, min(1.0, (points[m] - a).dot(ab) / L2))
                s += (points[m] - (a + ab * t)).length_squared
            cost[i][j] = s
    INF = float("inf")
    best = {}
    # D[k][j]: best cost reaching sample j with k segments from sample 0
    D = [[INF] * n for _ in range(max_segments + 1)]
    back = [[-1] * n for _ in range(max_segments + 1)]
    D[0][0] = 0.0
    for k in range(1, max_segments + 1):
        for j in range(1, n):
            for i in range(0, j - min_samples + 1):
                if D[k - 1][i] == INF:
                    continue
                c = D[k - 1][i] + cost[i][j]
                if c < D[k][j]:
                    D[k][j], back[k][j] = c, i
        if D[k][n - 1] < INF:
            idx, j, kk = [n - 1], n - 1, k
            while kk > 0:
                j = back[kk][j]
                idx.append(j)
                kk -= 1
            best[k] = (list(reversed(idx)), math.sqrt(D[k][n - 1] / n))
    return best


def _angle(a, b, c):
    """Included angle at b, degrees - 180 is straight."""
    u, v = a - b, c - b
    if u.length < 1e-12 or v.length < 1e-12:
        return 180.0
    return math.degrees(u.angle(v))


# --------------------------------------------------------------------------
# detection
# --------------------------------------------------------------------------

def detect(mesh_name, kind=None, forward="-Y", up="Z", band_share=0.01, max_segments=4):
    """Find every leg, its joints, and which pair jumps.

    `kind` ("orthopteran" | "leporid") overrules the guess - take it from the
    renders when the guess is wrong. `forward` is the world axis the head points
    along, also from the renders."""
    obj = bpy.data.objects.get(mesh_name)
    if obj is None or obj.type != "MESH":
        return {"error": "no mesh named %r" % mesh_name}
    ui = "XYZ".index(up[-1].upper())
    fi = "XYZ".index(forward[-1].upper())
    fsign = -1.0 if forward.startswith("-") else 1.0
    li = 3 - ui - fi
    mesh = _Mesh(obj)
    V = mesh.V
    lo = [min(p[i] for p in V) for i in range(3)]
    hi = [max(p[i] for p in V) for i in range(3)]
    size = [hi[i] - lo[i] for i in range(3)]
    height = size[ui]
    half_width = 0.5 * size[li]
    mid_lat = 0.5 * (lo[li] + hi[li])
    floor = lo[ui]
    warnings = []

    gc = measure.ground_contacts(obj, up=up[-1].upper())
    feet = [c for c in gc["clusters"] if c["kind"] == "limb"]
    if len(feet) < 2:
        return {"error": "%s has %d paired ground contacts - a hopper stands on its legs"
                % (mesh_name, len(feet))}

    # the body's centre: the vertex nearest the centroid of skin well above the floor
    upper = [p for p in V if p[ui] > floor + 0.35 * height] or V
    centre_p = sum(upper, Vector()) / len(upper)
    centre = min(range(len(V)), key=lambda i: (V[i] - centre_p).length)
    from_centre = mesh.geodesic([centre])
    span = max(from_centre.values())
    edges = mesh.obj.data.edges
    mean_edge = sum((V[e.vertices[0]] - V[e.vertices[1]]).length for e in edges) / max(len(edges), 1)
    # Never thinner than the mesh: bands narrower than an edge come out empty or
    # in pieces that share no edge with the band before, and the walk loses the leg.
    band = max(band_share * span, 1.6 * mean_edge)
    sdf = thickness(obj, V)
    ranked = sorted(sdf)
    # the body's core: the thick end of the skin. 0.7 of the 90th percentile
    # passes a cricket's swollen femur (0.55 of its abdomen) and stops at the body
    core = 0.7 * ranked[int(0.9 * (len(ranked) - 1))]

    legs, claimed = [], set()
    thresh = floor + 0.06 * height
    low = [i for i, p in enumerate(V) if p[ui] <= thresh]
    from_high = mesh.geodesic([i for i, p in enumerate(V) if p[ui] >= floor + 0.3 * height])
    low_parts = _components(low, mesh.adj)
    for c in sorted(feet, key=lambda c: -c["position"][fi] * fsign):
        pos = Vector(c["position"])
        # the patch: low vertices near this contact
        # the patch: the connected run of low skin at this contact. A box round
        # the contact reached the opposite forefoot on the rabbit, and the seed
        # - the farthest vertex in it - was on the wrong leg.
        start = min(low, key=lambda i: (V[i] - pos).length, default=None)
        if start is None:
            continue
        patch = next(p for p in low_parts if start in p)
        # The distal tip is the end of the patch farthest over the skin from
        # anything high. "Farthest from the body's centre" took the rabbit's
        # heel: sitting, its knee is over its toes, so the toes are nearer the
        # centre by way of the shin. From HIGH skin the toes are reached only
        # back along the foot and up the shank.
        seed = max(patch, key=lambda i: from_high.get(i, -1.0))
        side_sign = 1.0 if pos[li] - mid_lat >= 0.0 else -1.0
        bands, reason = walk(mesh, seed, side_sign, li, mid_lat, half_width, band, claimed=claimed,
                             sdf=sdf, core=core)
        if len(bands) < 4:
            warnings.append("contact at %s walked only %d bands (%s)" % (tuple(round(x, 4) for x in pos),
                                                                          len(bands), reason))
            continue
        leg = {"side": "L" if side_sign > 0 else "R", "contact": pos, "seed": seed,
               "bands": bands, "stop": reason}
        # A foot lying on the floor has a second end: the heel. When the walk
        # never passed it, the shank rose from somewhere else - a sitting
        # rabbit's shin rests on its foot, their skins fuse, and the walk went
        # up the front of the shin from the ball of the foot. Walk again from
        # the heel, over skin the first walk did not take: that is the shank.
        patch_set = set(patch)
        along = mesh.geodesic([seed], within=patch_set)
        heel = max(along, key=along.get)
        r_foot = sorted(b["radius"] for b in bands[:5])[min(2, len(bands[:5]) - 1)]
        # Where the walk leaves the floor. Leaving far in front of the heel, the
        # shank rose from somewhere the walk never reached - a flat foot, heel
        # down. Leaving at the heel, it simply turned up the leg (a cricket's
        # tarsus, a rabbit's paw).
        foot_level = floor + 2.5 * r_foot
        leave = next((b for b in bands if b["centroid"][ui] > foot_level), bands[-1])
        gap = abs((leave["centroid"] - V[heel])[fi])
        leg["heel_check"] = {"leaves_floor_from_heel": gap, "foot_radius": r_foot,
                             "heel_along": along[heel]}
        # and the foot is a real share of the leg: a cricket's tarsus is 18% of
        # what the walk covers, a rabbit's hind foot half
        foot_share = along[heel] / max(bands[-1]["d"], 1e-12)
        leg["heel_check"]["foot_share"] = foot_share
        if gap > 2.5 * r_foot and along[heel] >= 3.0 * r_foot and foot_share >= 0.3:
            # only the floor-level skin is the foot's: shin skin both walks
            # cross is left for this one to climb
            taken = {v for b in bands if b["centroid"][ui] <= foot_level for v in b["verts"]}
            shank, why = walk(mesh, heel, side_sign, li, mid_lat, half_width, band, claimed=claimed,
                              sdf=sdf, core=core, exclude=taken)
            rises = len(shank) >= 3 and shank[-1]["centroid"][ui] - shank[0]["centroid"][ui] > 2.0 * r_foot
            if rises:
                # the first walk's climb up the shin is the same leg: keep only
                # its foot, so the fit sees toe -> heel and the shank separately
                bands = [b for b in bands if b["centroid"][ui] <= foot_level]
                leg.update({"bands": bands, "heel": heel, "shank_bands": shank, "shank_stop": why,
                            "foot_radius": r_foot})
                bands = bands + shank
            else:
                leg["heel_check"]["walk"] = why
        for b in bands:
            claimed.update(b["verts"])
        legs.append(leg)

    # pair and rank, front to back
    for l in legs:
        l["forward"] = l["contact"][fi] * fsign
    lefts = sorted([l for l in legs if l["side"] == "L"], key=lambda l: -l["forward"])
    rights = sorted([l for l in legs if l["side"] == "R"], key=lambda l: -l["forward"])
    if len(lefts) != len(rights):
        warnings.append("%d left legs and %d right - pairing by rank anyway" % (len(lefts), len(rights)))
    n_pairs = min(len(lefts), len(rights))
    rank_names = {2: ["fore", "hind"], 3: ["fore", "mid", "hind"]}.get(
        n_pairs, ["leg%d" % (i + 1) for i in range(n_pairs)])
    pairs = []
    for i in range(n_pairs):
        for l in (lefts[i], rights[i]):
            l["rank"] = rank_names[i]
            l["name"] = "%s.%s" % (rank_names[i], l["side"])
        pairs.append((lefts[i], rights[i]))
    legs = [l for p in pairs for l in p]

    # joints on each leg: corners of the band-centroid line. First by fit alone,
    # to guess the kind; refitted below at the count that kind's legs have.
    for l in legs:
        if l.get("shank_bands"):
            _fit_plantigrade(l, V, KINDS)
        else:
            _fit_joints(l, V, max_segments)

    # how high each leg's walk ended against the body at that station
    body_verts = [i for i in range(len(V)) if i not in claimed]
    for l in legs:
        root = l["joints"][0]
        near = [V[i] for i in body_verts if abs(V[i][fi] - root[fi]) <= 0.08 * size[fi]]
        mid_h = (sum(p[ui] for p in near) / len(near)) if near else root[ui]
        l["root_height_share"] = (root[ui] - floor) / max(mid_h - floor, 1e-9)
        l["body_mid_height"] = mid_h
        l["hidden_root"] = l["root_height_share"] < 0.6

    # guess the kind before inferring what cannot be seen - the priors depend on it
    def path_len(l):
        return sum((b - a).length for a, b in zip(l["joints"], l["joints"][1:]))
    pair_len = [0.5 * (path_len(a) + path_len(b)) for a, b in pairs]
    guess, evidence = None, []
    if n_pairs >= 2:
        hind = pair_len[-1]
        others = sum(pair_len[:-1]) / (n_pairs - 1)
        ratio = hind / max(others, 1e-12)
        evidence.append("hind pair %.1f%% longer than the others on the skin" % (100 * (ratio - 1)))
        hl = pairs[-1][0]
        if n_pairs == 3 and ratio >= SALTATORIAL_RATIO:
            prox = hl["segment_radii"][0] / max(pairs[1][0]["segment_radii"][0], 1e-12)
            evidence.append("hind femur %.1fx as thick as the mid femur" % prox)
            if prox >= 1.5:
                guess = "orthopteran"
        elif n_pairs == 2:
            foot = _floor_segment(hl["joints"], ui, floor, height)
            if foot is not None:
                evidence.append("hind foot segment %d lies on the floor (%.0f deg, %.3f long)"
                                % (foot["index"], foot["angle"], foot["length"]))
            if hl.get("plantigrade"):
                evidence.append("hind legs stand heel down on a flat foot, the shank rising from the heel")
            # A sitting leporid hides most of its hind leg in the haunch, so the
            # skin's own leg lengths can make the hind pair look SHORTER; the
            # flat foot, heel down, is the sign that survives.
            if foot is not None and (hl.get("plantigrade") or
                                     (ratio >= 1.1 and foot["length"] >= 0.2 * path_len(hl))):
                guess = "leporid"
    kind = kind or guess
    if kind is None:
        return {"error": "no saltatorial pair found on %s" % mesh_name, "evidence": evidence,
                "pairs": [round(x, 5) for x in pair_len], "warnings": warnings}
    spec = KINDS[kind]

    # refit at the expected count, put back what the skin hides, then name
    for l in legs:
        roles = spec["ranks"].get(l["rank"])
        if roles is None:
            warnings.append("%s has no segment roles for a %s" % (l["name"], kind))
            roles = ["seg%d" % i for i in range(len(l["joints"]) - 1)]
        # a hidden root means the first segment (femur, humerus) is in the body
        # and only part of the second shows
        visible = len(roles) - (1 if l["hidden_root"] else 0)
        if l.get("shank_bands"):
            _fit_plantigrade(l, V, KINDS, toe_share=spec.get("toe_share", {}).get(l["rank"]))
        else:
            _fit_joints(l, V, max_segments, k=visible, toe_share=spec.get("toe_share", {}).get(l["rank"]),
                        floor=floor, up_index=ui)
        if l["hidden_root"]:
            _infer_hidden(l, V, body_verts, spec, ui, li, fi, warnings, mid_lat, l["body_mid_height"])
        n_seg = len(l["joints"]) - 1
        if n_seg != len(roles):
            warnings.append("%s: %d segments found, a %s %s leg has %d - roles assigned from the tip"
                            % (l["name"], n_seg, kind, l["rank"], len(roles)))
            roles = (["seg%d" % i for i in range(max(0, n_seg - len(roles)))] + roles)[-n_seg:]
        l["roles"] = roles
        l["segments"] = [{"role": r, "length": (b - a).length}
                         for r, a, b in zip(roles, l["joints"], l["joints"][1:])]
        l["angles"] = [_angle(a, b, c) for a, b, c in zip(l["joints"], l["joints"][1:], l["joints"][2:])]

    full = [0.5 * (path_len(a) + path_len(b)) for a, b in pairs]
    hind_ratio = full[-1] / max(sum(full[:-1]) / max(n_pairs - 1, 1), 1e-12) if n_pairs >= 2 else None

    # the body without its legs: spine from slices along the forward axis
    spine = _spine(V, body_verts, fi, ui, fsign, size)
    return {
        "mesh": mesh_name, "kind": kind, "kind_guessed": kind == guess and guess is not None,
        "evidence": evidence, "forward": forward, "up": up,
        "size": size, "height": height, "floor": floor,
        "legs": [dict({k: v for k, v in l.items() if k not in ("bands", "shank_bands")},
                      trace=[(tuple(round(x, 5) for x in bd["centroid"]), round(bd["radius"], 5), len(bd["verts"]),
                              bd["core"], bd["pieces"]) for bd in l["bands"]],
                      shank_trace=[(tuple(round(x, 5) for x in bd["centroid"]), round(bd["radius"], 5), len(bd["verts"]),
                                    bd["core"], bd["pieces"]) for bd in l.get("shank_bands", [])]) for l in legs],
        "leg_vertices": {l["name"]: [(v, b["d"]) for b in l["bands"] for v in b["verts"]] for l in legs},
        "pair_lengths": {pairs[i][0]["rank"]: full[i] for i in range(n_pairs)},
        "hind_over_others": hind_ratio,
        "spine": spine,
        "warnings": warnings,
    }


def _floor_segment(joints, ui, floor, height):
    """The run of distal segments lying along the floor, if any: its first
    segment's index, steepest angle and total length."""
    run, steep = [], 0.0
    for i in range(len(joints) - 2, -1, -1):
        a, b = joints[i], joints[i + 1]
        d = b - a
        if d.length < 1e-12:
            continue
        ang = math.degrees(math.asin(min(1.0, abs(d[ui]) / d.length)))
        if ang > 25.0 or max(a[ui], b[ui]) - floor > 0.12 * height:
            break
        run.append(i)
        steep = max(steep, ang)
    if not run:
        return None
    return {"index": min(run), "angle": steep,
            "length": sum((joints[i + 1] - joints[i]).length for i in run)}


def _line(points):
    """(centroid, unit direction) of the least-squares line through points."""
    import numpy as np
    A = np.array([tuple(p) for p in points])
    c = A.mean(axis=0)
    _, _, vt = np.linalg.svd(A - c)
    d = Vector(vt[0].tolist())
    return Vector(c.tolist()), d.normalized()


def _meet(l1, l2):
    """Midpoint of closest approach of two lines, or None when near parallel."""
    (p, u), (q, v) = l1, l2
    w = p - q
    a, b, c = u.dot(u), u.dot(v), v.dot(v)
    d, e = u.dot(w), v.dot(w)
    den = a * c - b * b
    if den < 1e-6:
        return None
    s_ = (b * e - c * d) / den
    t_ = (a * e - b * d) / den
    return ((p + u * s_) + (q + v * t_)) * 0.5


def _sharpen(pts, idx, min_angle=15.0):
    """Joints where the lines through neighbouring segments meet.

    A fold's band centroids round its corner off: the cricket's knee sat 3.2 mm
    short on the samples. Each segment's line is fitted to its middle samples
    and the joint put where the lines come closest - unless they are nearly in
    line, where the meeting point runs away and the sample is kept."""
    lines = []
    for a, b in zip(idx, idx[1:]):
        lo_i, hi_i = min(a, b), max(a, b)
        n = hi_i - lo_i
        trim = max(0, int(0.2 * n))
        inner = pts[lo_i + trim:hi_i - trim + 1]
        lines.append(_line(inner) if len(inner) >= 3 else None)
    out = [pts[i].copy() for i in idx]
    for j in range(1, len(idx) - 1):
        l1, l2 = lines[j - 1], lines[j]
        if l1 is None or l2 is None:
            continue
        ang = math.degrees(math.acos(max(-1.0, min(1.0, abs(l1[1].dot(l2[1]))))))
        if ang < min_angle:
            continue
        m = _meet(l1, l2)
        if m is not None and (m - out[j]).length < 0.5 * min((out[j] - out[j - 1]).length,
                                                            (out[j + 1] - out[j]).length):
            out[j] = m
    return out


def _fit_joints(l, V, max_segments, k=None, toe_share=None, floor=None, up_index=2, straight=160.0):
    _fit_joints_k(l, V, max_segments, k)
    if k is None or toe_share is None or floor is None or len(l["joints"]) < 4:
        return
    # A corner nearly straight is not a corner the skin shows: a rabbit's paw
    # and digits bend ~7 degrees, and the fit spent that joint mid-forearm. When
    # the last segment lies on the floor, fit one fewer and split the foot by
    # the prior instead.
    js = l["joints"]
    bends = [_angle(a, b, c) for a, b, c in zip(js, js[1:], js[2:])]
    last = js[-1] - js[-2]
    on_floor = abs(last[up_index]) <= 0.45 * last.length
    if max(bends) > straight and on_floor:
        _fit_joints_k(l, V, max_segments, k - 1)
        js = l["joints"]
        ball = js[-1].lerp(js[-2], toe_share)
        l["joints"] = js[:-1] + [ball, js[-1]]
        l["measured"] = l["measured"] + [False]
        l["segment_radii"] = l["segment_radii"] + [l["segment_radii"][-1]]
        l["ball_source"] = "prior: digits %.0f%% of the foot (corner %.0f deg, too straight to see)" % (
            100 * toe_share, max(bends))


def _fit_joints_k(l, V, max_segments, k=None):
    pts = [b["centroid"] for b in l["bands"]]              # tip -> root
    radii = [b["radius"] for b in l["bands"]]
    med_r = sorted(radii)[len(radii) // 2]
    # no segment shorter than a tenth of the walk: a fold's bands, where femur
    # and tibia skin meet, put a spurious corner mid-tibia on the cricket
    fits = fit_polyline(pts, max_segments=max(max_segments, k or 0),
                        min_samples=max(2, len(pts) // 10))
    tol = 0.22 * med_r
    if k is None or k not in fits:
        k = max(fits)
        for kk in sorted(fits):
            if fits[kk][1] <= tol:
                k = kk
                break
    idx = fits[k][0]
    joints = list(reversed(_sharpen(pts, idx)))             # root -> tip
    joints[-1] = _tip_on_axis(V[l["seed"]], joints[-2], pts[:2])
    seg_r = []
    rev = list(reversed(idx))
    for a, b in zip(rev, rev[1:]):
        lo_i, hi_i = min(a, b), max(a, b)
        rs = radii[lo_i:hi_i + 1]
        seg_r.append(sum(rs) / len(rs))
    # the walk stops at the body's skin; the joint is under it, about a
    # segment's radius further along the segment's own line
    if len(joints) >= 2:
        d = (joints[0] - joints[1])
        if d.length > 1e-12:
            joints[0] = joints[0] + d.normalized() * seg_r[0]
    l.update({"joints": joints, "measured": [True] * len(joints), "segment_radii": seg_r,
              "fit_rms": fits[k][1], "fit_tolerance": tol, "median_radius": med_r,
              "segments_by_fit": {kk: round(v[1] / max(med_r, 1e-12), 3) for kk, v in fits.items()}})


def _fit_plantigrade(l, V, kinds, toe_share=None, min_bend=35.0):
    """Joints of a leg standing on a flat foot: toe tip, ball, heel (hock), and
    the shank rising from the heel, walked separately."""
    shank = l["shank_bands"]
    r_foot = l["foot_radius"]
    heel_cap = shank[0]["centroid"].copy()
    tip = _tip_on_axis(V[l["seed"]], heel_cap, [b["centroid"] for b in l["bands"][:2]])
    # the heel's first window sits in the rounded heel, about half a foot
    # radius behind the hock's axis
    hock = heel_cap + (tip - heel_cap).normalized() * (0.5 * r_foot)
    # the foot: first-walk bands lying along tip -> hock
    seg = hock - tip
    L2 = max(seg.dot(seg), 1e-24)
    foot = []
    for b in l["bands"]:
        t = max(0.0, min(1.0, (b["centroid"] - tip).dot(seg) / L2))
        if (b["centroid"] - (tip + seg * t)).length > 1.5 * r_foot:
            break
        foot.append(b["centroid"])
    ball, bend = None, 180.0
    if len(foot) >= 4:
        pts = [tip] + foot + [hock]
        fits = fit_polyline(pts, max_segments=2, min_samples=2)
        if 2 in fits:
            i = fits[2][0][1]
            bend = _angle(tip, pts[i], hock)
            if bend <= 180.0 - min_bend:
                ball = pts[i].copy()
    ball_source = "corner"
    if ball is None:
        share = toe_share if toe_share is not None else 0.3
        ball = tip.lerp(hock, share)
        ball_source = "prior: toes %.0f%% of the foot (bend %.0f deg, too slight to see)" % (100 * share, bend)
    # the shank: a line through the heel walk, from the hock up
    cs = [b["centroid"] for b in shank]
    c, d = _line(cs)
    if d.dot(cs[-1] - cs[0]) < 0.0:
        d = -d
    top = c + d * (cs[-1] - c).dot(d)
    radii = [b["radius"] for b in shank]
    l.update({"joints": [top, hock, ball, tip], "measured": [True, True, ball_source == "corner", True],
              "segment_radii": [sorted(radii)[len(radii) // 2], r_foot, r_foot],
              "fit_rms": 0.0, "fit_tolerance": 0.0, "median_radius": sorted(radii)[len(radii) // 2],
              "segments_by_fit": {}, "ball_source": ball_source, "plantigrade": True})


def _tip_on_axis(seed, prev, first_centroids):
    """The skin's tip vertex lies on the floor; the segment's axis runs a radius
    above it. Move the tip onto the axis through the joint before it."""
    c0 = sum(first_centroids, Vector()) / len(first_centroids)
    d = seed - prev
    axis = c0 - prev
    if axis.length < 1e-12:
        return seed.copy()
    axis.normalize()
    return prev + axis * d.dot(axis)


def _circles(c1, r1, c2, r2, e1, e2):
    """Intersections of two circles in the plane spanned by e1, e2 (through c1),
    as 3D points; [] when they miss."""
    d3 = c2 - c1
    x2, y2 = d3.dot(e1), d3.dot(e2)
    d = math.hypot(x2, y2)
    if d < 1e-12 or d > r1 + r2 or d < abs(r1 - r2):
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2.0 * d)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    mx, my = a * x2 / d, a * y2 / d
    out = []
    for sg in (1.0, -1.0):
        px, py = mx + sg * h * (-y2) / d, my + sg * h * x2 / d
        out.append(c1 + e1 * px + e2 * py)
    return out


def _infer_hidden(leg, V, body_verts, spec, ui, li, fi, warnings, mid_lat, mid_h):
    """Put back the joints the skin hides.

    The hip goes fore and aft at the centre of the flesh the leg entered, on the
    leg's own side. Then, by what shows:

    - a flat foot (a rabbit's hind leg): its length is measured, so the tibia is
      `tibia_over_foot` of it and the femur `femur_over_tibia` of that. The hip
      sits at the body's middle height; the knee is where a tibia circle about
      the hock meets a femur circle about the hip, in the leg's plane. Of the two
      meetings, the one along the shank that shows. A shank line alone, from the
      25 mm of shin the test rabbit's haunch leaves visible, missed the hip.
    - otherwise the walk stopped at the knee or partway up the shank: the knee is
      on that shank's line, no nearer than the shank that shows, and the hip
      height is where the femur comes out at `femur_over_tibia`.
    """
    rank = leg["rank"]
    ratio = spec["femur_over_tibia"].get(rank, 1.0)
    root, below = leg["joints"][0], leg["joints"][1]
    s = (root - below).normalized()                # up the shank
    r_blob = 3.0 * leg["median_radius"] + 0.5 * (root - below).length
    side = 1.0 if root[li] - mid_lat > 0 else -1.0
    flesh = [V[i] for i in body_verts if (V[i] - root).length <= r_blob and V[i][ui] >= root[ui]
             and (V[i][li] - mid_lat) * side >= 0.0]
    if len(flesh) < 8:
        warnings.append("%s: no flesh found above the leg's root to place a hip in" % leg["name"])
        return
    fc = sum(flesh, Vector()) / len(flesh)
    e_f = Vector((0.0, 0.0, 0.0))
    e_f[fi] = 1.0
    e_u = Vector((0.0, 0.0, 0.0))
    e_u[ui] = 1.0
    hip = below.copy()
    hip[fi] = fc[fi]
    t_over_foot = spec.get("tibia_over_foot", {}).get(rank)
    how = None
    if leg.get("plantigrade") and t_over_foot:
        foot = sum((b - a).length for a, b in zip(leg["joints"][1:], leg["joints"][2:]))
        T = t_over_foot * foot
        F = ratio * T
        hip[ui] = max(mid_h, root[ui])
        hits = _circles(below, T, hip, F, e_f, e_u)
        if not hits:
            # scale both to just reach: the prior and this body disagree
            dist = (hip - below).length
            k = dist / (T + F) * 1.001 if dist > T + F else max(abs(T - F), 1e-9) / max(dist, 1e-9) * 0.999
            warnings.append("%s: femur and tibia at the prior ratios %s the hip - scaled by %.2f"
                            % (leg["name"], "cannot reach" if dist > T + F else "overshoot", k))
            T, F = T * k, F * k
            hits = _circles(below, T, hip, F, e_f, e_u) or [below + s * T]
        knee = max(hits, key=lambda p: (p - below).normalized().dot(s))
        how = "circles: tibia %.4f (%.2f foot), femur %.4f" % (T, t_over_foot, F)
    else:
        # knee = below + u s; the hip's height then puts the femur at ratio * u
        shown = (root - below).length
        u = shown
        knee = below + s * u
        F = ratio * u
        dx = hip[fi] - knee[fi]
        if abs(dx) < F:
            hip[ui] = knee[ui] + math.sqrt(F * F - dx * dx)
            how = "knee at the visible root, hip height from femur %.4f" % F
        else:
            hip[ui] = max(mid_h, knee[ui])
            how = "knee at the visible root, hip at the body's middle height"
    leg["joints"] = [hip, knee] + leg["joints"][1:]
    leg["measured"] = [False, False] + leg["measured"][1:]
    leg["segment_radii"] = [leg["segment_radii"][0] * 2.0] + leg["segment_radii"]
    leg["inferred"] = how
    leg["hip_flesh_vertices"] = len(flesh)


def _spine(V, body_verts, fi, ui, fsign, size, slices=10):
    coords = [V[i][fi] for i in body_verts]
    lo, hi = min(coords), max(coords)
    pts = []
    for k in range(slices):
        a = lo + (hi - lo) * k / slices
        b = lo + (hi - lo) * (k + 1) / slices
        sel = [V[i] for i in body_verts if a <= V[i][fi] < b or (k == slices - 1 and V[i][fi] == hi)]
        if sel:
            pts.append(sum(sel, Vector()) / len(sel))
    # rear -> head
    pts.sort(key=lambda p: p[fi] * fsign)
    return {"points": pts}


def score(detection, truth):
    """Joint error against known joints, per leg: mean and worst, metres."""
    out = {}
    for l in detection["legs"]:
        t = truth.get(l["name"])
        if not t:
            continue
        errs = []
        # match by count from the tip: detection may lack or add proximal joints
        for a, b in zip(reversed(l["joints"]), reversed(t)):
            errs.append((a - b).length)
        out[l["name"]] = {"mean": sum(errs) / len(errs), "worst": max(errs), "joints": len(l["joints"]),
                          "truth_joints": len(t), "per_joint_tip_first": [round(e, 5) for e in errs]}
    return out


def summary(d):
    if "error" in d:
        return "ERROR: %s %s" % (d["error"], d.get("evidence", ""))
    lines = ["%s: %s%s, hind legs %.2fx the others" % (d["mesh"], d["kind"],
                                                       " (guessed)" if d["kind_guessed"] else "",
                                                       d["hind_over_others"] or 0.0)]
    lines += ["  evidence: " + e for e in d["evidence"]]
    for l in d["legs"]:
        segs = ", ".join("%s %.4f" % (s["role"], s["length"]) for s in l["segments"])
        inf = sum(1 for m in l["measured"] if not m)
        lines.append("  %-7s %s | angles %s | fit %.2f r%s | stop: %s" % (
            l["name"], segs, ", ".join("%.0f" % a for a in l["angles"]),
            l["fit_rms"] / max(l["median_radius"], 1e-12),
            (" | %d joints inferred" % inf) if inf else "", l["stop"]))
    lines += ["  WARN " + w for w in d["warnings"]]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# rigging
# --------------------------------------------------------------------------

PARTS = "hopper_parts_"


def _v(p):
    return [round(float(x), 6) for x in p]


def build(mesh_name, detection=None, rig_name=None, kind=None, forward="-Y", up="Z", spine_bones=None):
    """An armature for a hopper mesh with no rig. Not weighted - call `skin`.

    The axial chain runs rear to head through the body's slice centroids, its
    last bone `head`. Each leg gets one bone per segment the detection named -
    `hind_femur.L > hind_tibia.L > hind_metatarsus.L > hind_toes.L` - hung from
    the nearest axial bone, so `bodymap` reads the femur as upper, the tibia as
    lower, the metatarsus (or a cricket's tarsus) as the end and the toes as
    digits. Every leg bone carries `hop_role`; the detection is stored on the
    rig, so `skin`, `HopRig` and the manifest all read the same answer."""
    d = detection or detect(mesh_name, kind=kind, forward=forward, up=up)
    if "error" in d:
        return d
    from . import build as build_mod
    obj = bpy.data.objects[mesh_name]
    rig_name = rig_name or mesh_name + "_rig"
    ui = "XYZ".index(up[-1].upper())
    fi = "XYZ".index(forward[-1].upper())
    li = 3 - ui - fi

    pts = [Vector(p) for p in d["spine"]["points"]]
    if spine_bones:
        from .build import _resample
        pts = _resample(pts, spine_bones)
    names = ["spine" if i == 0 else "spine.%03d" % i for i in range(len(pts) - 2)] + ["head"]
    # Rooted at the pelvis - the axial bone the jumping legs hang from - with the
    # chain running forward to the head and BACK to the rear. Rooted at the rear
    # tip, a cricket's swaying abdomen was the root of every bone: Godot's
    # importer kept none of its sub-millimetre translation, and the whole body
    # slid 0.87 mm under planted feet.
    hips = [Vector(g["joints"][0]) for g in d["legs"] if g["rank"] == d["legs"][-1]["rank"]]
    hip_c = sum(hips, Vector()) / max(len(hips), 1)
    pelvis = min(range(len(names)), key=lambda i: ((pts[i] + pts[i + 1]) * 0.5 - hip_c).length)
    pelvis = min(pelvis, len(names) - 2) if len(names) > 1 else 0
    bones = []
    for i, nm in enumerate(names):
        if i >= pelvis:
            bones.append((nm, pts[i], pts[i + 1], names[i - 1] if i > pelvis else None, "spine"))
        else:
            # pointing rearward from its parent, one bone nearer the pelvis
            bones.append((nm, pts[i + 1], pts[i], names[i + 1], "spine"))

    def nearest_axial(p):
        best, bd = names[0], float("inf")
        for i, nm in enumerate(names):
            a, b = pts[i], pts[i + 1]
            ab = b - a
            t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.dot(ab), 1e-24)))
            dd = (p - (a + ab * t)).length
            if dd < bd:
                best, bd = nm, dd
        return best

    roles, legs = {}, []
    for l in d["legs"]:
        joints = [Vector(j) for j in l["joints"]]
        chain = []
        for r, a, b in zip(l["roles"], joints, joints[1:]):
            nm = "%s_%s.%s" % (l["rank"], r, l["side"])
            parent = chain[-1] if chain else nearest_axial(a)
            bones.append((nm, a, b, parent, "limb"))
            roles[nm] = r
            chain.append(nm)
        legs.append({"name": l["name"], "rank": l["rank"], "side": l["side"], "roles": l["roles"],
                     "bones": chain, "attach": bones[[x[0] for x in bones].index(chain[0])][3],
                     "joints": [_v(j) for j in joints], "measured": l["measured"],
                     "lengths": [round((b - a).length, 6) for a, b in zip(joints, joints[1:])],
                     "radii": [round(r, 6) for r in l["segment_radii"]],
                     "rest_angles_deg": [round(a, 2) for a in l["angles"]],
                     "plantigrade": bool(l.get("plantigrade")), "inferred": l.get("inferred"),
                     "contact": _v(l["contact"])})

    lateral = Vector((0.0, 0.0, 0.0))
    lateral[li] = 1.0
    rig = build_mod._write(obj, bones, rig_name, ui, li, lateral)
    coll = obj.users_collection[0] if obj.users_collection else None
    if coll is not None and rig.name not in coll.objects:
        for c in list(rig.users_collection):
            c.objects.unlink(rig)
        coll.objects.link(rig)
    for nm, r in roles.items():
        rig.data.bones[nm][ROLE] = r
    hind = [g for g in legs if g["rank"] == d["legs"][-1]["rank"]]
    stored = {"version": 1, "mesh": mesh_name, "kind": d["kind"], "kind_guessed": d["kind_guessed"],
              "evidence": d["evidence"], "forward": forward, "up": up,
              "size": list(d["size"]), "height": d["height"], "floor": d["floor"],
              "axial": names, "pelvis": names[pelvis], "legs": legs, "saltatorial": [g["name"] for g in hind],
              "hind_over_others": d["hind_over_others"], "warnings": d["warnings"]}
    rig.data[PROP] = json.dumps(stored)
    txt = bpy.data.texts.get(PARTS + mesh_name) or bpy.data.texts.new(PARTS + mesh_name)
    txt.clear()
    txt.write(json.dumps({"n": len(obj.data.vertices),
                          "legs": {k: [[v, round(dd, 6)] for v, dd in vs] for k, vs in d["leg_vertices"].items()}}))
    return {"rig": rig.name, "kind": d["kind"], "bones": len(rig.data.bones),
            "legs": {g["name"]: g["bones"] for g in legs}, "axial": names}


def read(rig):
    rig = bpy.data.objects.get(rig) if isinstance(rig, str) else rig
    raw = rig.data.get(PROP) if rig is not None and rig.type == "ARMATURE" else None
    if not raw:
        return None
    st = json.loads(raw)
    have = {b.name for b in rig.data.bones}
    if any(b not in have for g in st["legs"] for b in g["bones"]):
        return None
    return st


# --------------------------------------------------------------------------
# weights
# --------------------------------------------------------------------------

def _project(P, joints):
    """Every point onto a polyline: (arc parameter, distance, segment, t)."""
    import numpy as np
    J = np.array(joints, dtype=float)
    n = len(P)
    best_d = np.full(n, np.inf)
    best_s = np.zeros(n)
    best_k = np.zeros(n, dtype=int)
    best_t = np.zeros(n)
    acc = 0.0
    for k in range(len(J) - 1):
        a, b = J[k], J[k + 1]
        ab = b - a
        L = float(np.linalg.norm(ab))
        t = np.clip(((P - a) @ ab) / max(L * L, 1e-24), 0.0, 1.0)
        q = a + t[:, None] * ab
        dist = np.linalg.norm(P - q, axis=1)
        better = dist < best_d
        best_d = np.where(better, dist, best_d)
        best_s = np.where(better, acc + t * L, best_s)
        best_k = np.where(better, k, best_k)
        best_t = np.where(better, t, best_t)
        acc += L
    return best_s, best_d, best_k, best_t


def _project_facing(P, N, joints):
    """Like `_project`, but a vertex only counts as on a segment whose axis it
    faces away from. At a Z-fold's inner corner the skin on top of a rabbit's
    foot is as near the shin's axis above it as the foot's below; its normal
    points up - away from the foot, toward the shin - and that settles it. The
    same test keeps a cricket's tibia skin, folded under the femur, off it."""
    import numpy as np
    J = np.array(joints, dtype=float)
    n = len(P)
    best_e = np.full(n, np.inf)
    best_s = np.zeros(n)
    acc = 0.0
    for k in range(len(J) - 1):
        a, b = J[k], J[k + 1]
        ab = b - a
        L = float(np.linalg.norm(ab))
        t = np.clip(((P - a) @ ab) / max(L * L, 1e-24), 0.0, 1.0)
        q = a + t[:, None] * ab
        rad = P - q
        dist = np.linalg.norm(rad, axis=1)
        facing = np.einsum("ij,ij->i", rad, N) / np.maximum(dist, 1e-12)
        eff = np.where(facing > -0.2, dist, dist * 4.0)
        better = eff < best_e
        best_e = np.where(better, eff, best_e)
        best_s = np.where(better, acc + t * L, best_s)
        acc += L
    return best_s


def _chain_weights(s, joints, blend):
    """Weights along a chain from an arc parameter: 1 inside a segment, a linear
    hand-over across each joint `blend[j]` either side. Returns (bones, n)."""
    import numpy as np
    J = np.array(joints, dtype=float)
    L = np.linalg.norm(J[1:] - J[:-1], axis=1)
    ends = np.concatenate([[0.0], np.cumsum(L)])
    m = len(L)
    W = np.zeros((m, len(s)))
    for k in range(m):
        lo, hi = ends[k], ends[k + 1]
        w = np.ones(len(s))
        if k > 0:
            z = blend[k]
            w = np.minimum(w, np.clip((s - (lo - z)) / max(2 * z, 1e-12), 0.0, 1.0))
        else:
            w = np.where(s < lo, 1.0, w)
        if k < m - 1:
            z = blend[k + 1]
            w = np.minimum(w, np.clip(((hi + z) - s) / max(2 * z, 1e-12), 0.0, 1.0))
        W[k] = w
    tot = W.sum(axis=0)
    return W / np.where(tot > 0, tot, 1.0)


def js_len(js):
    return sum((Vector(b) - Vector(a)).length for a, b in zip(js, js[1:]))


def skin(rig_name, smooth_iterations=12, max_influences=4):
    """Write every vertex's weights from the parts - no bone heat.

    Leg skin the detection walked goes to that leg's bones by where it projects
    along the chain, handing over across each joint within about a segment's
    radius - a folded cricket knee keeps its tibia's skin off its femur, which
    bone heat, seeing the two a skin's width apart, would not. The rest is body:
    along the axial chain the same way, except where a leg's bones run inside it.
    A rabbit's femur is in its haunch, so haunch skin within reach of the femur
    follows it, fading out with distance. Then smoothed over the surface and cut
    to `max_influences`."""
    import numpy as np
    rig = bpy.data.objects.get(rig_name)
    st = read(rig) if rig else None
    if st is None:
        return {"error": "%s carries no hopper rig - run hoppers.build" % rig_name}
    obj = bpy.data.objects[st["mesh"]]
    txt = bpy.data.texts.get(PARTS + st["mesh"])
    parts = json.loads(txt.as_string()) if txt else None
    if parts is None or parts["n"] != len(obj.data.vertices):
        return {"error": "the stored parts do not match %s any more - rebuild" % st["mesh"]}
    mw = obj.matrix_world
    P = np.array([tuple(mw @ v.co) for v in obj.data.vertices])
    n3 = mw.to_3x3().inverted().transposed()
    N = np.array([tuple((n3 @ v.normal).normalized()) for v in obj.data.vertices])
    n = len(P)
    bones = rig.data.bones

    def joints_of(chain):
        js = [tuple(bones[b].head_local) for b in chain]
        js.append(tuple(bones[chain[-1]].tail_local))
        return js

    columns = {}

    def add(nm, w):
        columns[nm] = columns.get(nm, np.zeros(n)) + w

    leg_owner = np.full(n, -1)
    for i, g in enumerate(st["legs"]):
        for v, _ in parts["legs"].get(g["name"], []):
            leg_owner[v] = i

    axial = st["axial"]
    # the axial chain in body order, rear to head, whichever way its bones point
    aj = []
    for nm in axial:
        bb = bones[nm]
        h, t = tuple(bb.head_local), tuple(bb.tail_local)
        if aj and (Vector(h) - Vector(aj[-1])).length > (Vector(t) - Vector(aj[-1])).length:
            h, t = t, h
        if not aj:
            nxt = bones[axial[1]] if len(axial) > 1 else None
            if nxt is not None and min((Vector(h) - Vector(tuple(nxt.head_local))).length,
                                       (Vector(h) - Vector(tuple(nxt.tail_local))).length) <                     min((Vector(t) - Vector(tuple(nxt.head_local))).length,
                        (Vector(t) - Vector(tuple(nxt.tail_local))).length):
                h, t = t, h
            aj.append(h)
        aj.append(t)
    li = 3 - "XYZ".index(st["up"][-1].upper()) - "XYZ".index(st["forward"][-1].upper())
    mid_lat = float(np.mean([j[li] for j in aj]))
    s_ax, d_ax, _, _ = _project(P, aj)

    # The walks claim the bands they measured, not every vertex of the leg: the
    # inside of the test rabbit's foot was left out, weighted as body, and
    # stretched 70x when the foot moved. Grow each leg over adjacent skin that
    # lies nearer its own visible segments - within a couple of radii - than to
    # the spine.
    adj = [[] for _ in range(n)]
    for ed in obj.data.edges:
        a_, b_ = ed.vertices
        adj[a_].append(b_)
        adj[b_].append(a_)
    grown = {}
    for i, g in enumerate(st["legs"]):
        js = joints_of(g["bones"])
        # from the segment that ends at the first joint seen: a shin that shows
        # below a hidden knee is still shin
        first_seen = g["measured"].index(True) if True in g["measured"] else 0
        start = max(0, first_seen - 1)
        vis = js[start:]
        _, d_leg, k_leg, _ = _project(P, vis)
        rad = np.array(g["radii"][start:] or g["radii"])
        limit = 2.2 * rad[np.clip(k_leg, 0, len(rad) - 1)]
        ok = (d_leg < limit) & (d_leg < d_ax) & (((P[:, li] - mid_lat) * (1.0 if g["side"] == "L" else -1.0)) > 0.0)
        frontier = [v for v in range(n) if leg_owner[v] == i]
        added = 0
        while frontier:
            nxt = []
            for v in frontier:
                for w in adj[v]:
                    if leg_owner[w] < 0 and ok[w]:
                        leg_owner[w] = i
                        nxt.append(w)
                        added += 1
            frontier = nxt
        grown[g["name"]] = added
    ax_len = np.linalg.norm(np.diff(np.array(aj), axis=0), axis=1)
    W_ax = _chain_weights(s_ax, aj, [0.0] + [0.35 * min(a, b) for a, b in zip(ax_len, ax_len[1:])] + [0.0])

    body_share = np.ones(n)
    leg_cols = []
    for i, g in enumerate(st["legs"]):
        js = joints_of(g["bones"])
        s, dist, _, _ = _project(P, js)
        mine = leg_owner == i
        if mine.any():
            s = np.where(mine, _project_facing(P, N, js), s)
        radii = g["radii"]
        lens = g["lengths"]
        # A hopper's joints swing ~100 degrees from a sitting pose to a push-off.
        # Handed over within 1.2 radii, the rabbit's heel skin stretched 12x;
        # the hand-over spans nearly two radii each side, or 45% of the shorter
        # segment.
        blend = [0.0] + [max(1e-6, min(0.45 * min(lens[k - 1], lens[k]), 1.8 * max(radii[k - 1], radii[k])))
                         for k in range(1, len(lens))] + [0.0]
        W = _chain_weights(s, js, blend)
        # body skin follows only bones hidden inside the body - a buried femur,
        # not the shin the haunch happens to rest on
        n_hidden = sum(1 for m in g["measured"][:-1] if not m)
        hidden_end = sum(lens[:max(n_hidden - 1, 1)]) if n_hidden else 0.0
        # The leg's own skin: all leg, fading into the body over the root's
        # radius, so the junction is a blend, not a seam.
        root_fade = np.clip(s / max(2.0 * radii[0], 1e-9), 0.0, 1.0)
        # Body skin a hidden bone runs under: follows the leg, fading with
        # distance. A leg that shows all the way up reaches only a root's width.
        hidden = not g["measured"][0]
        reach = (0.55 * lens[0] + 1.0 * radii[0]) if hidden else 2.0 * radii[0]
        near = np.clip(1.0 - dist / max(reach, 1e-9), 0.0, 1.0)
        near = near * near * (3.0 - 2.0 * near)
        if hidden:
            near = near * np.clip(1.0 - (s - hidden_end) / max(radii[0], 1e-9), 0.0, 1.0)
        if not hidden:
            near = near * np.clip(1.0 - s / max(4.0 * radii[0], 1e-9), 0.0, 1.0)
        # never pull skin across the midline
        side = 1.0 if g["side"] == "L" else -1.0
        across = (P[:, li] - mid_lat) * side < 0.0
        share = np.where(mine, 0.5 + 0.5 * root_fade, np.where(across | (leg_owner >= 0), 0.0, 0.7 * near))
        leg_cols.append((g, W, share))
        body_share = body_share - share
    over = body_share < 0.0
    if over.any():
        # two legs claiming the same body skin: scale them down to fit
        tot = sum(sh for _, _, sh in leg_cols)
        scale = np.where(over, 1.0 / np.maximum(tot, 1e-12), 1.0)
        leg_cols = [(g, W, sh * scale) for g, W, sh in leg_cols]
        body_share = np.clip(1.0 - sum(sh for _, _, sh in leg_cols), 0.0, 1.0)
    for g, W, sh in leg_cols:
        for k, nm in enumerate(g["bones"]):
            add(nm, W[k] * sh)
    for k, nm in enumerate(axial):
        add(nm, W_ax[k] * body_share)

    names = list(columns)
    M = np.array([columns[k] for k in names])
    if smooth_iterations:
        e = np.array([tuple(ed.vertices) for ed in obj.data.edges])
        deg = np.bincount(e.ravel(), minlength=n).astype(float)
        for _ in range(smooth_iterations):
            acc = np.zeros_like(M)
            np.add.at(acc.T, e[:, 0], M.T[e[:, 1]])
            np.add.at(acc.T, e[:, 1], M.T[e[:, 0]])
            M = 0.5 * M + 0.5 * acc / np.maximum(deg, 1.0)
    if max_influences:
        order = np.argsort(-M, axis=0)
        keep = np.zeros_like(M, dtype=bool)
        for i in range(min(max_influences, len(names))):
            keep[order[i], np.arange(n)] = True
        M = np.where(keep, M, 0.0)
    tot = M.sum(axis=0)
    M = M / np.where(tot > 0, tot, 1.0)
    ours = {b.name for b in bones}
    for g in list(obj.vertex_groups):
        if g.name in ours:
            obj.vertex_groups.remove(g)
    for k, nm in enumerate(names):
        grp = obj.vertex_groups.new(name=nm)
        col = M[k]
        idx = np.nonzero(col > 1e-4)[0]
        vals = np.round(col[idx], 4)
        for w_val in np.unique(vals):
            grp.add([int(i) for i in idx[vals == w_val]], float(w_val), "REPLACE")
    if obj.parent is not rig:
        mwo = obj.matrix_world.copy()
        obj.parent = rig
        obj.matrix_world = mwo
    mod = next((m for m in obj.modifiers if m.type == "ARMATURE"), None) or obj.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    mod.use_vertex_groups = True
    covered = float((tot > 0).mean())
    unweighted = sorted(ours - {nm for k, nm in enumerate(names) if M[k].max() > 0.05})
    # Skin joining a leg's far segments straight to the body: a sitting pose
    # modelled with the foot fused under the haunch. It cannot be weighted
    # well - whatever it follows, the other side pulls away - and on the test
    # rabbit it stretched 70x when the leg extended.
    webs = {}
    E = np.array([tuple(ed.vertices) for ed in obj.data.edges])
    for i, g in enumerate(st["legs"]):
        js = joints_of(g["bones"])
        s_leg, _, _, _ = _project(P, js)
        first_seen = g["measured"].index(True) if True in g["measured"] else 0
        shown_from = js_len(js[:first_seen + 1]) if first_seen else 0.0
        # the distal half of what shows: its junction with the body is expected
        far = (leg_owner == i) & (s_leg > shown_from + 0.5 * (js_len(js) - shown_from))
        a_far = far[E[:, 0]] & (leg_owner[E[:, 1]] < 0)
        b_far = far[E[:, 1]] & (leg_owner[E[:, 0]] < 0)
        count = int(a_far.sum() + b_far.sum())
        if count:
            webs[g["name"]] = count
    # Skin of one segment lying on another's: a fold modelled closed, like a
    # sitting rabbit's shin fused onto its foot. It tears when the joint opens.
    folds = {}
    for i, g in enumerate(st["legs"]):
        js = [Vector(j) for j in joints_of(g["bones"])]
        mine = np.nonzero(leg_owner == i)[0]
        for k in range(len(js) - 2):
            # each segment against its own radius: a cricket's femur is five
            # times its tibia's, and the tibia's skin read as lying on it
            r1, r2 = 1.3 * g["radii"][k], 1.3 * g["radii"][k + 1]
            _, d1, _, _ = _project(P[mine], [tuple(js[k]), tuple(js[k + 1])])
            _, d2, _, _ = _project(P[mine], [tuple(js[k + 1]), tuple(js[k + 2])])
            dj = np.linalg.norm(P[mine] - np.array(tuple(js[k + 1])), axis=1)
            count = int(((d1 < r1) & (d2 < r2) & (dj > 2.5 * max(r1, r2))).sum())
            if count:
                folds["%s %s/%s" % (g["name"], g["roles"][k], g["roles"][k + 1])] = count
    warnings = ["%s: %d edges join its distal half straight to the body - skin fused under the body "
                "at rest will tear when the leg extends" % (k, v) for k, v in webs.items()]
    warnings += ["%s: %d vertices lie on both segments away from their joint - a fold modelled closed, "
                 "which tears when the joint opens" % (k, v) for k, v in folds.items()]
    return {"mesh": obj.name, "rig": rig_name, "coverage": round(covered, 4), "groups": len(names),
            "bones_without_skin": unweighted, "passed": covered == 1.0 and not unweighted,
            "fused_webs": webs, "closed_folds": folds, "warnings": warnings, "leg_skin_grown": grown,
            "note": "weights written from the detected parts; bone heat is not used"}
