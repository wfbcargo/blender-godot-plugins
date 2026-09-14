"""Deterministic mesh measurement for auto-rigging.

Read-only: nothing here mutates the scene. Everything returns plain
JSON-serialisable dicts so results can be read back through the MCP bridge.

Measurements work on the BASE mesh (obj.data) under the object's world matrix,
not the evaluated mesh. An evaluated mesh is posed by any armature modifier and
would describe the current pose rather than the authored shape. Unapplied
modifiers are reported as a warning instead.
"""

from __future__ import annotations

import heapq
import math
from collections import defaultdict

import bmesh
import bpy
from mathutils import Matrix, Vector

AXES = ("X", "Y", "Z")
AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}
INDEX_AXIS = {0: "X", 1: "Y", 2: "Z"}


# --------------------------------------------------------------------------
# geometry access
# --------------------------------------------------------------------------

def world_verts(obj):
    mw = obj.matrix_world
    return [mw @ v.co for v in obj.data.vertices]


def edge_list(obj):
    return [tuple(e.vertices) for e in obj.data.edges]


def bbox(points):
    lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return {
        "min": [round(v, 5) for v in lo],
        "max": [round(v, 5) for v in hi],
        "size": [round(v, 5) for v in (hi - lo)],
        "centre": [round(v, 5) for v in ((hi + lo) / 2.0)],
    }


# --------------------------------------------------------------------------
# 1. mesh health - the bone-heat pre-flight
# --------------------------------------------------------------------------

def mesh_health(obj):
    """Whether Blender's automatic (bone heat) weighting is likely to succeed.

    Bone heat fails on non-manifold geometry, on meshes whose vertices are very
    densely packed in scene units, and it silently ignores loose parts that no
    bone can see. Each is checked here rather than discovered later as an opaque
    "failed to find solution for one or more bones".
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    non_manifold_edges = sum(1 for e in bm.edges if not e.is_manifold)
    boundary_edges = sum(1 for e in bm.edges if e.is_boundary)
    loose_verts = sum(1 for v in bm.verts if not v.link_edges)
    degenerate_faces = sum(1 for f in bm.faces if f.calc_area() < 1e-9)

    parent = list(range(len(bm.verts)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for e in bm.edges:
        ra, rb = find(e.verts[0].index), find(e.verts[1].index)
        if ra != rb:
            parent[ra] = rb
    # Count surfaces only. A loose vertex is its own component, so including
    # them here would double-report the same defect as both "disconnected
    # parts" and "loose vertices".
    connected = [v.index for v in bm.verts if v.link_edges]
    components = len({find(i) for i in connected}) if connected else 0
    bm.free()

    dims = obj.dimensions
    largest = max(dims) if max(dims) > 0 else 0.0
    unapplied = [m.type for m in obj.modifiers if m.type != "ARMATURE"]

    problems = []
    warnings = []
    # Graded, not absolute. A real asset almost always carries some
    # non-manifold geometry - a downloaded rat had 223 edges out of ~70k, at
    # eye and mouth openings - and bone heat binds through that perfectly well.
    # Blocking on any at all would refuse every real model; the failures it
    # actually causes come from widespread non-manifold structure.
    total_edges = len(obj.data.edges) or 1
    nm_ratio = non_manifold_edges / float(total_edges)
    if non_manifold_edges and nm_ratio > 0.02:
        problems.append("%d non-manifold edges (%.1f%% of the mesh)"
                        % (non_manifold_edges, 100.0 * nm_ratio))
    elif non_manifold_edges:
        warnings.append("%d non-manifold edges (%.1f%%) - usually survivable"
                        % (non_manifold_edges, 100.0 * nm_ratio))
    if components > 1:
        problems.append(
            str(components) + " disconnected parts - bone heat ignores islands no bone can see"
        )
    if loose_verts:
        problems.append(str(loose_verts) + " loose vertices")
    if largest < 0.1:
        problems.append(
            "largest dimension " + format(largest, ".4f")
            + " - very dense in scene units, bone heat often fails; scale up before binding"
        )
    if degenerate_faces:
        warnings.append(str(degenerate_faces) + " zero-area faces")
    if boundary_edges:
        warnings.append(str(boundary_edges) + " boundary edges (open mesh)")
    if unapplied:
        warnings.append("unapplied modifiers: " + ", ".join(unapplied))
    if len(obj.data.vertices) < 50:
        warnings.append(str(len(obj.data.vertices)) + " vertices only - very coarse for skinning")

    return {
        "vertices": len(obj.data.vertices),
        "polygons": len(obj.data.polygons),
        "components": components,
        "non_manifold_edges": non_manifold_edges,
        "boundary_edges": boundary_edges,
        "loose_vertices": loose_verts,
        "degenerate_faces": degenerate_faces,
        "dimensions": [round(v, 5) for v in dims],
        "scale": [round(v, 5) for v in obj.scale],
        "unapplied_modifiers": unapplied,
        "problems": problems,
        "warnings": warnings,
        "verdict": "blocked" if problems else ("caution" if warnings else "ok"),
    }


# --------------------------------------------------------------------------
# 2. symmetry - finds the mirror plane, which names the left/right axis
# --------------------------------------------------------------------------

def symmetry(obj, samples=3000):
    """Score mirror symmetry about each axis through the bbox centre.

    The best-scoring axis is the lateral (left/right) one for almost any
    creature, which constrains which axis can be forward.
    """
    from mathutils.kdtree import KDTree

    pts = world_verts(obj)
    if not pts:
        return {"scores": {}, "lateral_axis": None, "lateral_confident": False}

    step = max(1, len(pts) // samples)
    pts = pts[::step]

    bb = bbox(pts)
    centre = Vector(bb["centre"])
    diag = Vector(bb["size"]).length or 1.0

    tree = KDTree(len(pts))
    for i, p in enumerate(pts):
        tree.insert(p, i)
    tree.balance()

    scores = {}
    for axis, idx in AXIS_INDEX.items():
        total = 0.0
        for p in pts:
            m = p.copy()
            m[idx] = 2.0 * centre[idx] - m[idx]
            _, _, dist = tree.find(m)
            total += dist
        mean_err = total / len(pts)
        scores[axis] = round(max(0.0, 1.0 - (mean_err / (diag * 0.02))), 4)

    ordered = sorted(scores.values())
    lateral = max(scores, key=scores.get)
    return {
        "scores": scores,
        "lateral_axis": lateral,
        "lateral_confident": bool(scores[lateral] > 0.75 and (ordered[-1] - ordered[-2]) > 0.1),
        "note": "highest score = mirror plane normal = the left/right axis",
    }


# --------------------------------------------------------------------------
# 2b. rotational symmetry - a body with no front or back
# --------------------------------------------------------------------------

def _perp_basis(a):
    ref = Vector((0.0, -1.0, 0.0)) if abs(a.dot(Vector((0.0, -1.0, 0.0)))) < 0.9 else Vector((1.0, 0.0, 0.0))
    e1 = (ref - a * ref.dot(a)).normalized()
    return e1, a.cross(e1).normalized()


def rotational_symmetry(obj, samples=2500, max_order=24, pass_score=0.6):
    """Find an axis the body repeats around, and how many times.

    A mirror plane names left and right; a jellyfish, a starfish or an anemone
    has as many mirror planes as it has arms, so `symmetry` scores two axes
    alike and settles nothing. What such a body has instead is an axis it can be
    turned about - by 72 degrees for a starfish - and still land on itself.

    Tested honestly, the way `symmetry` tests a mirror: rotate every point by
    360/k degrees about a candidate axis and measure how far it lands from the
    surface. k passes when that is small. A 4-fold body also passes k = 2 and an
    8-fold one 2 and 4, so the ORDER is the largest k that passes; a body of
    revolution passes every k and is reported as `continuous`.

    Candidates are the world axes and the principal axes, each through the
    bounding-box centre in its own plane - a symmetric body's centre is on its
    axis however long its tentacles hang.
    """
    from mathutils.kdtree import KDTree

    pts = world_verts(obj)
    if len(pts) < 8:
        return {"radial": False, "note": "too few vertices"}
    step = max(1, len(pts) // samples)
    pts = pts[::step]
    diag = Vector(bbox(pts)["size"]).length or 1.0
    tree = KDTree(len(pts))
    for i, p in enumerate(pts):
        tree.insert(p, i)
    tree.balance()

    import numpy as np
    arr = np.array([tuple(p) for p in pts])
    mean = arr.mean(axis=0)
    _, vecs = np.linalg.eigh(np.cov((arr - mean).T))
    cands = [("X", Vector((1, 0, 0))), ("Y", Vector((0, 1, 0))), ("Z", Vector((0, 0, 1)))]
    for i in range(3):
        v = Vector(tuple(vecs[:, i])).normalized()
        if all(abs(v.dot(c)) < 0.985 for _, c in cands):
            cands.append(("PCA%d" % i, v))

    def score_k(a, centre, k):
        """Two tests, both must hold. Absolute: points land within 2% of the
        body's diagonal, as the mirror test asks. Relative: they land far closer
        than the turn moved them. Without the second, a 15 degree turn about a
        whale's long axis moves its flank so little that it passes on size alone
        (0.51 before this test)."""
        R = Matrix.Rotation(2.0 * math.pi / k, 3, a)
        total, moved = 0.0, 0.0
        for p in pts:
            q = centre + R @ (p - centre)
            total += tree.find(q)[2]
            moved += (q - p).length
        absolute = 1.0 - (total / len(pts)) / (diag * 0.02)
        relative = 1.0 - (total / max(moved, 1e-12)) / 0.25
        return max(0.0, min(absolute, relative))

    # The centre is the skin's area-weighted centroid, not the bounding box's.
    # A box is centred on a body of even order only: a five-armed star has one
    # arm up and two down, its box sits 6 mm off its axis, and every turn about
    # that point missed - a starfish scored as no symmetry at all. Weighted by
    # area rather than counted by vertex, so tessellation does not pull it.
    mw = obj.matrix_world
    area_c, area = Vector((0.0, 0.0, 0.0)), 0.0
    for poly in obj.data.polygons:
        a_ = poly.area * max(mw.median_scale, 1e-12) ** 2
        area_c += (mw @ poly.center) * a_
        area += a_
    centroid = area_c / area if area > 0 else Vector(tuple(mean))

    results = []
    for label, a in cands:
        h = [p.dot(a) for p in pts]
        centre = centroid - a * centroid.dot(a) + a * 0.5 * (min(h) + max(h))
        scores = {}
        for k in range(2, max_order + 1):
            scores[k] = round(score_k(a, centre, k), 4)
        passing = [k for k, s in scores.items() if s >= pass_score]
        if not passing:
            order = None
        elif len(passing) >= max_order - 2:
            order = "continuous"
        else:
            # The largest k that passes CLEARLY. A jellyfish with 8 tentacles and
            # 4 oral arms is 4-fold, but its oral arms are a small share of the
            # skin and a 45 degree turn still scored 0.72 against 0.9 for 90 -
            # a pass on points, and the wrong answer about the animal.
            top = max(scores[k] for k in passing)
            order = max(k for k in passing if scores[k] >= 0.85 * top)
        results.append({"axis": label, "vector": [round(c, 5) for c in a],
                        "centre": [round(c, 5) for c in centre], "order": order,
                        "score": (scores[order] if isinstance(order, int) else
                                  min(scores.values()) if order else max(scores.values())),
                        "scores": scores})

    def rank(r):
        o = r["order"]
        # a real order beats none; any beats 2 (a half-turn is a bilateral box);
        # continuous ranks with a high order; ties by score
        n = 0 if o is None else (100 if o == "continuous" else o)
        return (n >= 3, r["score"], n)

    best = max(results, key=rank)
    radial_axes = [r for r in results if r["order"] is not None and
                   (r["order"] == "continuous" or r["order"] >= 3)]
    radial = bool(radial_axes)
    notes = []
    if len({r["axis"] for r in radial_axes if not r["axis"].startswith("PCA")}) >= 2:
        notes.append("more than one axis turns onto itself - a sphere, a cube or a "
                     "rock, not an animal with an oral-aboral axis")
    if best["order"] == "continuous":
        notes.append("a body of revolution: no arms to count. A bell with no tentacles, "
                     "a vase or a column - the renders say which")
    if best["order"] == 2:
        notes.append("only a half-turn repeats: bilateral, or a box")
    return {
        "radial": radial,
        "axis": best["axis"] if radial else None,
        "axis_vector": best["vector"] if radial else None,
        "centre": best["centre"] if radial else None,
        "order": best["order"] if radial else None,
        "score": best["score"] if radial else None,
        "candidates": [{k: r[k] for k in ("axis", "order", "score")} for r in results],
        "notes": notes,
        "note": "order = the largest k for which a 360/k degree turn lands the body on "
                "itself; 5 a starfish, 4 or 8 most jellyfish, continuous a body of revolution",
    }


# --------------------------------------------------------------------------
# 3. ground contacts - limb tips, and therefore a leg-count hint
# --------------------------------------------------------------------------

def mid_lat_of(bb, axis_index):
    return bb["centre"][axis_index]


def _contact_link_radius(contacts, plane, size):
    """Link distance for single-linkage clustering of contact points.

    Derived from the actual sampling density (median nearest-neighbour distance
    among the contact points) rather than from model size, so it adapts to both
    dense and coarse meshes. Clamped so a pathological mesh cannot produce a
    radius that merges the whole footprint into one blob.
    """
    from mathutils.kdtree import KDTree

    n = len(contacts)
    tree = KDTree(n)
    for i, p in enumerate(contacts):
        tree.insert(Vector((p[plane[0]], p[plane[1]], 0.0)), i)
    tree.balance()

    step = max(1, n // 400)
    nn = []
    for i in range(0, n, step):
        p = contacts[i]
        found = tree.find_n(Vector((p[plane[0]], p[plane[1]], 0.0)), 2)
        if len(found) > 1:
            nn.append(found[1][2])
    if not nn:
        return 0.05 * max(size[plane[0]], size[plane[1]], 1e-6)
    nn.sort()
    median = nn[len(nn) // 2]
    extent = max(size[plane[0]], size[plane[1]], 1e-6)
    return max(min(median * 3.0, 0.25 * extent), 1e-5)


def _euclid_groups(verts, idxs, plane, link):
    """Single-linkage grouping of contact points in the ground plane.

    Only a first pass: it reliably splits things that are far apart, and
    over-splits a rounded sole into strips. The geodesic pass repairs that.
    """
    from mathutils.kdtree import KDTree

    tree = KDTree(len(idxs))
    for k, i in enumerate(idxs):
        p = verts[i]
        tree.insert(Vector((p[plane[0]], p[plane[1]], 0.0)), k)
    tree.balance()

    parent = list(range(len(idxs)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for k, i in enumerate(idxs):
        p = verts[i]
        for (_, j, _) in tree.find_range(Vector((p[plane[0]], p[plane[1]], 0.0)), link):
            ra, rb = find(k), find(j)
            if ra != rb:
                parent[ra] = rb

    buckets = {}
    for k, i in enumerate(idxs):
        buckets.setdefault(find(k), []).append(i)
    return list(buckets.values())


def _merge_by_geodesic(verts, edges, groups):
    """Merge contact groups that are close ALONG THE SURFACE.

    The cut-off is taken from the data rather than hard-coded: pairwise
    geodesic distances between groups fall into two populations - small ones
    within a single limb and large ones between limbs - so the threshold is
    placed at the widest ratio gap between consecutive sorted distances. A
    hard-coded distance would have to be retuned for every model scale.
    """
    reps = []
    for members in groups:
        cx = sum(verts[i].x for i in members) / len(members)
        cy = sum(verts[i].y for i in members) / len(members)
        cz = sum(verts[i].z for i in members) / len(members)
        c = Vector((cx, cy, cz))
        reps.append(min(members, key=lambda i: (verts[i] - c).length))

    n = len(groups)
    INF = float("inf")
    dmat = [[0.0] * n for _ in range(n)]
    for a in range(n):
        dist = _geodesic(verts, edges, [reps[a]])
        for b in range(n):
            dmat[a][b] = dist[reps[b]]

    pairs = sorted(
        dmat[a][b] for a in range(n) for b in range(a + 1, n) if dmat[a][b] != INF
    )
    if not pairs:
        return groups, {"merged": False, "reason": "groups are disconnected on the mesh"}

    # The threshold is an absolute ceiling, a small fraction of the model's own
    # geodesic span.
    #
    # An earlier version cut at the widest ratio gap between sorted distances.
    # That works when fragments of one sole sit ~2% of the span apart and real
    # limbs sit 100%+ apart, but it assumes a gap exists. On a quadruped the
    # four feet are all far from each other - 1.18 to 1.72 on a span of 0.97,
    # with no gap at all - so it cut inside that band and merged the front pair
    # and the rear pair into two "feet", turning a quadruped into a biped.
    #
    # This step only ever repairs over-splitting WITHIN one limb, so anything
    # further than a small fraction of the span apart must stay separate,
    # whether or not the distances happen to form a gap.
    span = max(d for row in dmat for d in row if d != INF) or 1.0
    threshold = 0.12 * span

    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a in range(n):
        for b in range(a + 1, n):
            if dmat[a][b] <= threshold:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb

    merged = {}
    for a in range(n):
        merged.setdefault(find(a), []).extend(groups[a])

    return list(merged.values()), {
        "merged": True,
        "groups_before": n,
        "groups_after": len(merged),
        "threshold": round(threshold, 5),
        "pairwise_geodesic": [round(p, 4) for p in pairs[:12]],
    }


def ground_contacts(obj, up="Z", band=0.06):
    """Cluster vertices sitting near the model's lowest point.

    For a creature in a standing rest pose each cluster is a foot, so the count
    is the strongest single archetype hint: 2 biped, 4 quadruped, 6 hexapod,
    0 not a standing creature (fish, floating, or lying down).
    """
    ui = AXIS_INDEX[up]
    verts = world_verts(obj)
    edges = edge_list(obj)
    if not verts:
        return {"clusters": [], "count": 0, "contact_vertices": 0, "hint": "empty"}

    bb = bbox(verts)
    size = Vector(bb["size"])
    lo = bb["min"][ui]
    height = size[ui] or 1.0
    thresh = lo + band * height

    idxs = [i for i, p in enumerate(verts) if p[ui] <= thresh]
    contacts = [verts[i] for i in idxs]
    if not contacts:
        return {"clusters": [], "count": 0, "contact_vertices": 0, "hint": "no ground contact"}

    plane = [i for i in (0, 1, 2) if i != ui]

    # Cluster along the SURFACE, not through space.
    #
    # Euclidean clustering cannot do this job at any radius. A sole is usually
    # slightly rounded, so its contact patch breaks into separate strips: a
    # radius tight enough to keep two feet apart splits one foot into three,
    # and a radius loose enough to join them merges the feet. Geodesic distance
    # has no such conflict - two strips of one sole are centimetres apart
    # across the mesh, while the opposite foot is a metre away up and over the
    # hips.
    link = _contact_link_radius([verts[i] for i in idxs], plane, size)
    groups_idx = _euclid_groups(verts, idxs, plane, link)

    if len(groups_idx) > 1:
        groups_idx, merge_info = _merge_by_geodesic(verts, edges, groups_idx)
    else:
        merge_info = {"merged": False, "reason": "single group"}

    groups = {k: [verts[i] for i in members] for k, members in enumerate(groups_idx)}

    floor = max(3, int(len(contacts) * 0.04))
    out = []
    for members in sorted(groups.values(), key=lambda m: -len(m)):
        if len(members) < floor:
            continue
        pos = [0.0, 0.0, 0.0]
        pos[plane[0]] = round(sum(p[plane[0]] for p in members) / len(members), 5)
        pos[plane[1]] = round(sum(p[plane[1]] for p in members) / len(members), 5)
        pos[ui] = round(min(p[ui] for p in members), 5)
        span0 = max(p[plane[0]] for p in members) - min(p[plane[0]] for p in members)
        span1 = max(p[plane[1]] for p in members) - min(p[plane[1]] for p in members)
        out.append({
            "position": pos,
            "vertices": len(members),
            "patch_size": [round(span0, 4), round(span1, 4)],
        })

    # Not every ground contact is a foot.
    #
    # A real rat rests its TAIL on the floor, which read as a fifth "leg" and
    # turned a quadruped into "unusual - 5 contacts". Limbs come in mirrored
    # lateral pairs; a tail, belly or chin touches down on the centreline
    # alone. Pairing separates them without needing to know the creature.
    lat_extent = size[li] if (li := plane[0]) is not None else 1.0
    half = 0.5 * (size[plane[0]] or 1.0)
    for c in out:
        c["lateral_offset"] = round(c["position"][plane[0]] - mid_lat_of(bb, plane[0]), 5)
    for c in out:
        c["paired"] = False
    for i, a in enumerate(out):
        if a["paired"]:
            continue
        for b in out[i + 1:]:
            if b["paired"]:
                continue
            mirrored = abs(a["lateral_offset"] + b["lateral_offset"]) <= 0.25 * half
            aligned = abs(a["position"][plane[1]] - b["position"][plane[1]]) <= 0.30 * (size[plane[1]] or 1.0)
            apart = abs(a["lateral_offset"] - b["lateral_offset"]) > 0.12 * half
            if mirrored and aligned and apart:
                a["paired"] = b["paired"] = True
                break
    for c in out:
        c["kind"] = "limb" if c["paired"] else (
            "midline" if abs(c["lateral_offset"]) <= 0.25 * half else "unpaired")

    legs = [c for c in out if c["kind"] == "limb"]
    midline = [c for c in out if c["kind"] == "midline"]

    hints = {0: "no ground contact", 1: "single base/pedestal", 2: "biped",
             3: "tripod", 4: "quadruped", 6: "hexapod", 8: "octoped"}
    return {
        "clusters": out,
        "count": len(legs),
        "raw_contacts": len(out),
        "midline_contacts": len(midline),
        "contact_vertices": len(contacts),
        "link_radius": round(link, 5),
        "merge": merge_info,
        "hint": hints.get(len(legs), "unusual - " + str(len(legs)) + " paired contacts"),
    }


# --------------------------------------------------------------------------
# 4. extremities - geodesic farthest points give limb tips, head, tail
# --------------------------------------------------------------------------

def _geodesic(verts, edges, sources):
    adj = defaultdict(list)
    for a, b in edges:
        w = (verts[a] - verts[b]).length
        adj[a].append((b, w))
        adj[b].append((a, w))
    INF = float("inf")
    dist = [INF] * len(verts)
    pq = []
    for s in sources:
        dist[s] = 0.0
        heapq.heappush(pq, (0.0, s))
    while pq:
        d, v = heapq.heappop(pq)
        if d > dist[v]:
            continue
        for n, w in adj[v]:
            nd = d + w
            if nd < dist[n]:
                dist[n] = nd
                heapq.heappush(pq, (nd, n))
    return dist


def extremities(obj, count=8):
    """Farthest-point sampling over the mesh edge graph.

    Extremities are where limb chains must terminate, so they anchor a template
    fit. Geodesic (along-surface) distance is used rather than Euclidean so a
    hand resting near the hip is still far from the spine.
    """
    verts = world_verts(obj)
    edges = edge_list(obj)
    if not verts or not edges:
        return {"points": [], "note": "no edge graph"}

    bb = bbox(verts)
    centre = Vector(bb["centre"])
    start = min(range(len(verts)), key=lambda i: (verts[i] - centre).length)

    dist = _geodesic(verts, edges, [start])
    finite = [d for d in dist if d != float("inf")]
    if not finite:
        return {"points": [], "note": "disconnected mesh"}

    picks = []
    cur = list(dist)
    for _ in range(count):
        best, bestd = -1, -1.0
        for k in range(len(verts)):
            d = cur[k]
            if d != float("inf") and d > bestd:
                best, bestd = k, d
        if best < 0 or bestd <= 0.0:
            break
        picks.append(best)
        d2 = _geodesic(verts, edges, [best])
        cur = [min(a, b) for a, b in zip(cur, d2)]

    span = max(finite) or 1.0
    return {
        "points": [
            {
                "position": [round(v, 5) for v in verts[i]],
                "geodesic_from_centre": round(dist[i], 5),
                "fraction_of_span": round(dist[i] / span, 3),
            }
            for i in picks
        ],
        "geodesic_span": round(span, 5),
        "unreachable_vertices": len(verts) - len(finite),
        "note": "candidate limb tips / head / tail, ordered by coverage",
    }


# --------------------------------------------------------------------------
# 5. cross-sections - torso vs limbs, and neck/waist pinch points
# --------------------------------------------------------------------------

def cross_sections(obj, axis="Z", bins=24):
    idx = AXIS_INDEX[axis]
    pts = world_verts(obj)
    if not pts:
        return {"bins": []}
    bb = bbox(pts)
    lo, hi = bb["min"][idx], bb["max"][idx]
    span = (hi - lo) or 1.0
    buckets = [[] for _ in range(bins)]
    for p in pts:
        b = min(bins - 1, int((p[idx] - lo) / span * bins))
        buckets[b].append(p)
    other = [i for i in (0, 1, 2) if i != idx]
    out = []
    for i, bucket in enumerate(buckets):
        at = round(lo + span * (i + 0.5) / bins, 4)
        if not bucket:
            out.append({"at": at, "verts": 0, "extent": [0.0, 0.0]})
            continue
        e0 = max(p[other[0]] for p in bucket) - min(p[other[0]] for p in bucket)
        e1 = max(p[other[1]] for p in bucket) - min(p[other[1]] for p in bucket)
        out.append({"at": at, "verts": len(bucket), "extent": [round(e0, 4), round(e1, 4)]})
    return {
        "axis": axis,
        "bins": out,
        "note": "narrow extents between wide ones are neck/waist pinch points",
    }


# --------------------------------------------------------------------------
# 6. axis inference
# --------------------------------------------------------------------------

def slab_topology(obj, axis="Z", lateral="X", bins=40):
    """Locate the crotch and shoulders from per-slab surface topology.

    No width profile can find these. Slicing a standing biped and counting
    components does not work either, because hands and legs both produce two
    components at different heights.

    What separates them is whether a component *crosses the lateral midline*.
    Limbs never do; the torso always does. So:

        crotch   = the lowest slab containing a midline-crossing component
                   (below it there are only two separate legs)
        shoulder = the highest slab that still has two off-midline components
                   beside the torso (above it the arms have merged into it)

    Connectivity is taken over the mesh edge graph restricted to the slab, so
    two limbs that touch without being joined still read as separate.
    """
    idx = AXIS_INDEX[axis]
    lat = AXIS_INDEX[lateral]
    verts = world_verts(obj)
    edges = edge_list(obj)
    if not verts or not edges:
        return {"slabs": [], "note": "no edge graph"}

    bb = bbox(verts)
    lo, hi = bb["min"][idx], bb["max"][idx]
    span = (hi - lo) or 1.0

    membership = [min(bins - 1, int((p[idx] - lo) / span * bins)) for p in verts]
    by_slab = defaultdict(list)
    for vi, b in enumerate(membership):
        by_slab[b].append(vi)

    mid = bb["centre"][lat]
    half_width = (bb["size"][lat] or 1.0) * 0.5

    # Gaps between sorted lateral coordinates, not bin occupancy.
    #
    # A slab through a hollow limb gives a ring of surface points, so each limb
    # occupies two arcs with an empty middle. Bin occupancy therefore reports a
    # single leg as two runs and misses a torso whose ring has no vertex exactly
    # on the midline - both are sampling artefacts, not anatomy. Sorting the
    # coordinates and looking at the gaps between them measures the empty space
    # that actually exists, using extremes rather than whether a bin got lucky.
    width = bb["size"][lat] or 1.0
    tol = 0.02 * width

    slabs = []
    for b in range(bins):
        members = by_slab.get(b, [])
        at = lo + span * (b + 0.5) / bins
        if len(members) < 4:
            slabs.append({"at": round(at, 4), "verts": len(members),
                          "midline_gap": None, "outer_gaps": 0, "extent": None})
            continue

        xs = sorted(verts[vi][lat] for vi in members)
        gaps = []
        for i in range(len(xs) - 1):
            g = xs[i + 1] - xs[i]
            if g > tol:
                gaps.append((xs[i], xs[i + 1], g))

        # the gap straddling the midline, if the midline is empty
        midline_gap = 0.0
        for a, bnd, g in gaps:
            if a < mid < bnd:
                midline_gap = g
                break

        outer = [g for a, bnd, g in gaps if not (a < mid < bnd) and g > 0.05 * width]

        slabs.append({
            "at": round(at, 4),
            "verts": len(members),
            "midline_gap": round(midline_gap, 4),
            "outer_gaps": len(outer),
            "extent": [round(xs[0] - mid, 4), round(xs[-1] - mid, 4)],
        })

    real = [s for s in slabs if s["midline_gap"] is not None]

    # Crotch: where the gap between the legs is narrowest.
    #
    # Not "where the gap closes" - above the crotch the midline runs through the
    # hollow inside of the torso ring, so a nonzero gap reappears and is pure
    # sampling noise. The gap instead falls smoothly while the legs converge and
    # is minimal exactly where they meet. Only the lower part of the body is
    # considered, and only if the legs were meaningfully apart to begin with, so
    # a robe or a single-legged form reports nothing rather than a fiction.
    lower = [s for s in real if s["at"] <= lo + 0.65 * span]
    crotch = None
    if lower:
        widest = max(s["midline_gap"] for s in lower)
        if widest >= 0.05 * width:
            crotch = min(lower, key=lambda s: s["midline_gap"])["at"]
        legs_separate = widest >= 0.05 * width
    else:
        legs_separate = False

    # Shoulder: the highest slab above the crotch with a gap on each side
    # separating an outer cluster (an arm) from the torso. Above it the arms
    # have merged into the shoulders.
    shoulder = None
    for s in real:
        if crotch is not None and s["at"] <= crotch:
            continue
        if s["outer_gaps"] >= 2:
            shoulder = s["at"]

    return {
        "axis": axis,
        "lateral": lateral,
        "slabs": slabs,
        "crotch": crotch,
        "shoulder": shoulder,
        "legs_separate": legs_separate,
        "note": "crotch = narrowest midline gap in the lower body; shoulder = "
                "highest slab above it still showing an arm clear of the torso "
                "on each side",
    }


def torso_axis(obj, at_forward, up="Z", lateral="X", forward="Y", band=0.05):
    """Height of the body's central axis at one position along its length.

    A quadruped's spine is horizontal, so it cannot be read off a vertical
    profile the way a biped's can. Taking the centroid of a cross-section does
    not work either: the legs are in the same slab and drag it downward.

    The body is roughly circular in section, so its centre lies about one radius
    below its top, and the radius shows in the lateral width measured near the
    top - high enough that the legs, which hang below, contribute nothing.
    """
    ui, li, fi = AXIS_INDEX[up], AXIS_INDEX[lateral], AXIS_INDEX[forward]
    verts = world_verts(obj)
    if not verts:
        return None

    size = Vector(bbox(verts)["size"])
    half = band * size[fi]
    slab = [p for p in verts if abs(p[fi] - at_forward) <= half]
    if len(slab) < 8:
        return None

    ground = bbox(verts)["min"][ui]
    height = size[ui] or 1.0

    top = max(p[ui] for p in slab)
    bottom = min(p[ui] for p in slab)

    # A slab clear of the ground contains no legs, so its vertical extent IS the
    # body's diameter and the midpoint is the axis exactly - no width estimate
    # needed. Where limbs do reach into the slab, fall back to measuring near
    # the top, correcting for the fact that a chord taken across the upper fifth
    # of a circular section is about 0.8 of its diameter, and flag it as the
    # weaker reading it is.
    limb_free = bottom > ground + 0.25 * height
    if limb_free:
        axis = 0.5 * (top + bottom)
        width = top - bottom
        confident = True
    else:
        upper = [p for p in slab if p[ui] >= top - 0.2 * (top - bottom)]
        if len(upper) < 4:
            upper = slab
        chord = max(p[li] for p in upper) - min(p[li] for p in upper)
        width = chord / 0.8
        axis = top - 0.5 * width
        confident = False

    return {
        "at_forward": round(at_forward, 4),
        "top": round(top, 4),
        "bottom": round(bottom, 4),
        "width": round(width, 4),
        "axis_height": round(axis, 4),
        "limb_free": limb_free,
        "confident": confident,
        "lateral_centre": round(
            (max(p[li] for p in slab) + min(p[li] for p in slab)) * 0.5, 4),
        "samples": len(slab),
    }


def spine_line(obj, front_forward, rear_forward, up="Z", lateral="X",
               forward="Y", samples=9):
    """Height of the spine between the shoulders and the hips.

    Sampled only where the cross-section is limb-free, then averaged. Readings
    taken at the limb attachments are unreliable - the shoulder and hip bulge
    widens the section right where the measurement is wanted - and a quadruped's
    spine is close enough to level between those points that the clean
    mid-torso samples describe it better than the contaminated ones do.
    """
    lo, hi = sorted((front_forward, rear_forward))
    readings = []
    for i in range(samples):
        t = (i + 0.5) / samples
        at = lo + t * (hi - lo)
        r = torso_axis(obj, at, up=up, lateral=lateral, forward=forward)
        if r:
            readings.append(r)

    good = [r for r in readings if r["confident"]]
    use = good or readings
    if not use:
        return None
    heights = sorted(r["axis_height"] for r in use)
    median = heights[len(heights) // 2]
    return {
        "height": round(median, 4),
        "samples_used": len(use),
        "limb_free_samples": len(good),
        "spread": round(heights[-1] - heights[0], 4),
        "readings": [(r["at_forward"], r["axis_height"], r["confident"]) for r in readings],
    }


def infer_axes(obj, up=None):
    """Determine up / lateral / forward, with the evidence that produced them.

    Up defaults to Z, Blender's world convention, rather than being derived.
    An earlier version picked the axis with the MOST ground-contact clusters,
    which is backwards - more clusters is not better, and it happily chose the
    body's front as "down" for a standing figure. Evidence for all three axes is
    returned so the choice can be overridden when an asset really is authored
    on its side.

    Lateral comes from the mirror plane, which is reliable. Forward is then the
    remaining axis; its SIGN is the genuinely unreliable part and is what the
    render pass exists to settle.
    """
    size = Vector(bbox(world_verts(obj))["size"])
    sym = symmetry(obj)
    lateral = sym["lateral_axis"]

    evidence = {}
    for axis in AXES:
        gc = ground_contacts(obj, up=axis)
        evidence[axis] = {
            "clusters": gc["count"],
            "hint": gc["hint"],
            "contact_vertices": gc["contact_vertices"],
            "balanced": _balanced(gc["clusters"]),
        }

    chosen = (up or "Z").upper()
    plausible = evidence[chosen]["clusters"] in (1, 2, 4, 6, 8)

    remaining = [a for a in AXES if a != chosen and a != lateral]
    forward = remaining[0] if remaining else None

    alternatives = [
        a for a in AXES
        if a != chosen and evidence[a]["clusters"] in (2, 4, 6) and evidence[a]["balanced"]
    ]

    return {
        "up_axis": chosen,
        "up_source": "explicit" if up else "Blender Z-up convention",
        "lateral_axis": lateral,
        "forward_axis": forward,
        "forward_sign": "unknown - confirm from renders",
        "per_axis_evidence": evidence,
        "plausible_limb_count_on_up": plausible,
        "alternative_up_axes": alternatives,
        "symmetry_scores": sym["scores"],
        "confidence": "high" if (sym["lateral_confident"] and plausible) else "low",
    }


def _balanced(clusters, tol=0.35):
    """Whether contact clusters are of comparable size.

    Real limbs of one creature put roughly equal area on the ground; a spurious
    grouping usually does not.
    """
    if len(clusters) < 2:
        return False
    counts = [c["vertices"] for c in clusters]
    return (max(counts) - min(counts)) <= tol * max(counts)


# --------------------------------------------------------------------------
# top level
# --------------------------------------------------------------------------

def make_proxy(obj, target_verts=6000, suffix="__rig_proxy"):
    """A decimated stand-in for analysis of a dense mesh.

    Everything measured here is structural and reported in world space, so a
    lower-poly copy gives the same answers. A real asset is often dense enough
    that the pure-Python geodesic passes stop being merely slow and start
    blocking: a 32k-vertex rat ran past the MCP timeout entirely. The proxy
    shares the original's world transform, so results transfer with no mapping.
    """
    import bpy as _bpy

    name = obj.name + suffix
    old = _bpy.data.objects.get(name)
    if old:
        _bpy.data.objects.remove(old, do_unlink=True)

    cp = obj.copy()
    cp.data = obj.data.copy()
    cp.name = name
    cp.data.name = name
    _bpy.context.collection.objects.link(cp)
    for m in list(cp.modifiers):
        cp.modifiers.remove(m)

    n = len(cp.data.vertices)
    if n > target_verts:
        dec = cp.modifiers.new("Decimate", "DECIMATE")
        dec.ratio = max(0.02, float(target_verts) / float(n))
        view = _bpy.context.view_layer
        prev = view.objects.active
        for o in view.objects:
            o.select_set(False)
        view.objects.active = cp
        cp.select_set(True)
        try:
            _bpy.ops.object.modifier_apply(modifier=dec.name)
        except Exception:
            pass
        view.objects.active = prev
    return cp


def analyze(obj_name, up=None, max_verts=6000):
    real = bpy.data.objects.get(obj_name)
    if real is None:
        return {"error": "no object named " + repr(obj_name)}
    if real.type != "MESH":
        return {"error": repr(obj_name) + " is " + real.type + ", not MESH"}

    dense = len(real.data.vertices) > max_verts
    obj = make_proxy(real, max_verts) if dense else real
    try:
        result = _analyze_obj(obj, obj_name, up)
    finally:
        if dense:
            bpy.data.objects.remove(obj, do_unlink=True)
    result["proxy_used"] = dense
    result["source_vertices"] = len(real.data.vertices)
    # health is about the REAL mesh, not the decimated stand-in
    result["health"] = mesh_health(real)
    return result


def _analyze_obj(obj, obj_name, up):
    axes = infer_axes(obj, up=up)
    rot = rotational_symmetry(obj)
    if rot["radial"]:
        # Nothing here has a forward. Saying "Y, sign unknown" invites a fitter
        # to pick one, and every choice is arbitrary for a body with five fronts.
        axes["body_plan"] = "radial"
        axes["forward_axis"] = None
        axes["forward_sign"] = ("none - a %s-fold radial body; any arm can lead"
                                % rot["order"])
        axes["symmetry_axis"] = rot["axis"]
    else:
        axes["body_plan"] = "bilateral"
    return {
        "rotational_symmetry": rot,
        "object": obj_name,
        "bbox": bbox(world_verts(obj)),
        "health": mesh_health(obj),
        "axes": axes,
        "symmetry": symmetry(obj),
        "ground_contacts": ground_contacts(obj, up=axes["up_axis"]),
        "extremities": extremities(obj),
        "cross_sections": cross_sections(obj, axis=axes["up_axis"]),
    }


def candidates():
    """Mesh objects in the scene worth analysing, largest first."""
    out = []
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        out.append({
            "name": o.name,
            "vertices": len(o.data.vertices),
            "dimensions": [round(v, 4) for v in o.dimensions],
            "parent": o.parent.name if o.parent else None,
            "has_armature": any(m.type == "ARMATURE" for m in o.modifiers),
        })
    return sorted(out, key=lambda d: -d["vertices"])
