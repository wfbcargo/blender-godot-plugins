"""Decompose an arbitrary mesh into chains: spine, head, tail, limbs.

Template fitting only works for shapes a template exists for. Anything else -
a worm, a hexapod, a six-armed statue, a fish - has no `basic_worm` to anchor
to. But every one of them is the same thing underneath: chains of joints,
joined at branch points.

So the structure is discovered rather than assumed, by building a Reeb graph.
Geodesic distance is measured outward from the centre of the mesh, vertices are
grouped into bands of that distance, and the connected components within each
band become nodes. A tube produces one component per band; where the shape
branches, one component becomes two, and that is a junction. The result is a
graph whose topology is the creature's topology, with no shape class assumed.

Roles are then assigned from geometry:

    spine   what remains once every limb is pruned away
    limb    a chain branching off the spine and reaching away from it
    head    the spine's own end, or a chain continuing the spine's line
    tail    the other such end

and each limb's terminus is grounded (a leg, bearing weight) or free (an arm,
a wing, a fin). Arm and leg are the same structure in different roles, which is
why one code path builds both.

ACCURACY, measured on four shapes with known structure - a worm, a quadruped, a
biped and a hexapod:

    legs, spine, head and tail   exact at every band count tried (14-30)
    free limbs (arms)            resolution-sensitive

Leg counts came back 0/4/2/6 at every setting. Arms did not: a worm read 0, 2,
13 and 2 arms at 14, 18, 24 and 30 bands. Grounding is a hard, external test, so
legs are safe; a free limb is only distinguishable from a surface feature by
prominence and reach, and finer bands turn body detail into topology. Default
18. Treat a nonzero arm count as a hypothesis to confirm from the renders, and
sweep `bands` if a result looks wrong.
"""

from __future__ import annotations

import heapq
import math
from collections import defaultdict, deque

import bpy
from mathutils import Vector

from . import measure

AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


# --------------------------------------------------------------------------
# Reeb graph
# --------------------------------------------------------------------------

def _adjacency(edges):
    adj = defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    return adj


def _geodesic_from(verts, adj, sources):
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
        for n in adj[v]:
            nd = d + (verts[v] - verts[n]).length
            if nd < dist[n]:
                dist[n] = nd
                heapq.heappush(pq, (nd, n))
    return dist


def _graph_centre(verts, adj):
    """A vertex near the middle of the shape, used as the distance origin.

    Taken as the vertex minimising the maximum geodesic distance to a set of
    extremities, rather than the vertex nearest the bounding-box centre. For an
    L-shaped or curled body the bbox centre can fall outside the mesh entirely,
    which would put the origin of the whole field in the wrong place.
    """
    start = 0
    d0 = _geodesic_from(verts, adj, [start])
    finite = [(d, i) for i, d in enumerate(d0) if d != float("inf")]
    if not finite:
        return start
    far_a = max(finite)[1]
    da = _geodesic_from(verts, adj, [far_a])
    far_b = max((d, i) for i, d in enumerate(da) if d != float("inf"))[1]
    db = _geodesic_from(verts, adj, [far_b])
    best, best_score = start, float("inf")
    for i in range(len(verts)):
        if da[i] == float("inf") or db[i] == float("inf"):
            continue
        score = abs(da[i] - db[i]) + 0.001 * max(da[i], db[i])
        if score < best_score:
            best, best_score = i, score
    return best


def reeb_graph(obj, bands=18):
    """Build a Reeb graph of the mesh over geodesic distance from its centre."""
    verts = measure.world_verts(obj)
    edges = measure.edge_list(obj)
    if not verts or not edges:
        return {"error": "mesh has no edge graph"}

    adj = _adjacency(edges)
    centre = _graph_centre(verts, adj)
    dist = _geodesic_from(verts, adj, [centre])
    finite = [d for d in dist if d != float("inf")]
    if not finite:
        return {"error": "mesh is disconnected"}
    span = max(finite) or 1.0

    band_of = {}
    for i, d in enumerate(dist):
        if d == float("inf"):
            continue
        band_of[i] = min(bands - 1, int(d / span * bands))

    by_band = defaultdict(list)
    for i, b in band_of.items():
        by_band[b].append(i)

    nodes = []
    node_of_vert = {}
    for b in range(bands):
        members = by_band.get(b)
        if not members:
            continue
        inside = set(members)
        seen = set()
        for start in members:
            if start in seen:
                continue
            comp = []
            stack = [start]
            seen.add(start)
            while stack:
                v = stack.pop()
                comp.append(v)
                for n in adj[v]:
                    if n in inside and n not in seen:
                        seen.add(n)
                        stack.append(n)
            if len(comp) < 3:
                continue
            nid = len(nodes)
            pos = Vector((0.0, 0.0, 0.0))
            for v in comp:
                pos += verts[v]
            pos /= len(comp)
            radius = sum((verts[v] - pos).length for v in comp) / len(comp)
            nodes.append({
                "id": nid, "band": b, "verts": comp, "pos": pos,
                "radius": radius, "count": len(comp),
                "geodesic": sum(dist[v] for v in comp) / len(comp),
            })
            for v in comp:
                node_of_vert[v] = nid

    links = set()
    for a, b in edges:
        na, nb = node_of_vert.get(a), node_of_vert.get(b)
        if na is not None and nb is not None and na != nb:
            links.add((min(na, nb), max(na, nb)))

    degree = defaultdict(int)
    for a, b in links:
        degree[a] += 1
        degree[b] += 1

    return {
        "nodes": nodes,
        "links": sorted(links),
        "degree": dict(degree),
        "centre_vertex": centre,
        "geodesic_span": round(span, 5),
        "bands": bands,
    }


# --------------------------------------------------------------------------
# chains
# --------------------------------------------------------------------------

def chains(graph):
    """Collapse the graph into polylines that run between its branch points.

    Every degree-2 run is a chain; nodes of degree 1 are tips and degree 3+ are
    junctions. This is what turns a mesh into a limb count.
    """
    if "error" in graph:
        return graph

    adj = defaultdict(list)
    for a, b in graph["links"]:
        adj[a].append(b)
        adj[b].append(a)

    deg = {n["id"]: len(adj[n["id"]]) for n in graph["nodes"]}
    special = {i for i, d in deg.items() if d != 2}
    nodes = {n["id"]: n for n in graph["nodes"]}

    seen_edges = set()
    out = []
    starts = special or {graph["nodes"][0]["id"]}
    for s in starts:
        for first in adj[s]:
            if (s, first) in seen_edges:
                continue
            path = [s, first]
            seen_edges.add((s, first))
            seen_edges.add((first, s))
            prev, cur = s, first
            while deg.get(cur, 0) == 2:
                nxt = [x for x in adj[cur] if x != prev]
                if not nxt:
                    break
                prev, cur = cur, nxt[0]
                seen_edges.add((prev, cur))
                seen_edges.add((cur, prev))
                path.append(cur)
            length = sum((nodes[path[i]]["pos"] - nodes[path[i + 1]]["pos"]).length
                         for i in range(len(path) - 1))
            out.append({
                "nodes": path,
                "ends": (path[0], path[-1]),
                "end_degrees": (deg.get(path[0], 0), deg.get(path[-1], 0)),
                "length": round(length, 5),
                "mean_radius": round(
                    sum(nodes[p]["radius"] for p in path) / len(path), 5),
            })
    return {"chains": out, "degree": deg, "nodes": nodes, "adj": dict(adj)}


def _longest_path(ch):
    """The longest tip-to-tip route through the graph - the spine.

    Dijkstra, with predecessors recorded. An earlier version accumulated
    distance during a breadth-first walk, which is only correct on a tree; the
    Reeb graph has cycles wherever a band's components rejoin, so the distances
    came out wrong and the path reconstruction stopped after one node. That
    produced a "spine" of a single joint on a worm, which then orphaned the
    head and neck chains and reported them as limbs.
    """
    nodes, adj = ch["nodes"], ch["adj"]
    if not nodes:
        return []

    def dijkstra(seed):
        INF = float("inf")
        dist = {seed: 0.0}
        prev = {}
        pq = [(0.0, seed)]
        while pq:
            d, v = heapq.heappop(pq)
            if d > dist.get(v, INF):
                continue
            for n in adj.get(v, []):
                nd = d + (nodes[v]["pos"] - nodes[n]["pos"]).length
                if nd < dist.get(n, INF):
                    dist[n] = nd
                    prev[n] = v
                    heapq.heappush(pq, (nd, n))
        return dist, prev

    # Seed from the largest connected component, not from whatever node happens
    # to be first. Band components that touch nothing leave isolated nodes in
    # the graph, and Dijkstra from one of those returns only itself - which
    # reported a one-joint "spine" for a worm whose graph was a clean 32-node
    # chain.
    seen = set()
    best_comp = []
    for start in nodes:
        if start in seen:
            continue
        comp = []
        stack = [start]
        seen.add(start)
        while stack:
            v = stack.pop()
            comp.append(v)
            for n in adj.get(v, []):
                if n not in seen:
                    seen.add(n)
                    stack.append(n)
        if len(comp) > len(best_comp):
            best_comp = comp
    if not best_comp:
        return []
    seed = best_comp[0]

    dist, _ = dijkstra(seed)
    if not dist:
        return [seed]
    a = max(dist, key=dist.get)

    dist_a, prev_a = dijkstra(a)
    if not dist_a:
        return [a]
    b = max(dist_a, key=dist_a.get)

    path = [b]
    while path[-1] != a and path[-1] in prev_a:
        path.append(prev_a[path[-1]])
    path.reverse()
    return path


# --------------------------------------------------------------------------
# roles
# --------------------------------------------------------------------------

def _leaf_chains(ch):
    """Chains with a free end. Every limb, head and tail is one of these."""
    out = []
    for c in ch["chains"]:
        d0, d1 = c["end_degrees"]
        if d0 == 1 and d1 == 1:
            out.append((c, c["ends"][0], c["ends"][1]))   # whole shape is a chain
        elif d0 == 1:
            out.append((c, c["ends"][1], c["ends"][0]))   # (chain, root, tip)
        elif d1 == 1:
            out.append((c, c["ends"][0], c["ends"][1]))
    return out


def classify(obj, analysis=None, bands=18, head_at=None, min_prominence=0.06):
    """Decompose a mesh into roled parts.

    The spine is what remains once every limb is pruned away, not the longest
    path through the graph. On a quadruped the longest path runs from one foot
    to another straight through the body - it reported two feet as the head and
    the tail, and swallowed two of the four legs on the way.

    `head_at` is the forward coordinate of the head end and comes from the
    renders. Geometry cannot decide it - a tail can be longer than a muzzle -
    so when it is omitted the choice is made by bulk and flagged as a guess.
    """
    analysis = analysis or measure.analyze(obj.name)
    axes = analysis["axes"]
    ui = AXIS_INDEX[axes["up_axis"]]
    li = AXIS_INDEX[axes["lateral_axis"]]
    fi = AXIS_INDEX[axes["forward_axis"]]

    graph = reeb_graph(obj, bands=bands)
    if "error" in graph:
        return graph
    ch = chains(graph)
    nodes = ch["nodes"]
    span = graph["geodesic_span"] or 1.0

    bb = analysis["bbox"]
    ground = bb["min"][ui]
    height = bb["size"][ui] or 1.0

    leaves = _leaf_chains(ch)

    # Surface dimples and band-boundary slivers also appear as leaf chains. A
    # real appendage is long both in absolute terms and relative to its own
    # girth; a bump is neither.
    def prominent(c):
        return (c["length"] >= min_prominence * span
                and c["length"] >= 1.6 * max(c["mean_radius"], 1e-6))

    real = [(c, r, t) for (c, r, t) in leaves if prominent(c)]
    pruned = len(leaves) - len(real)

    # The core: everything not consumed by a leaf chain. Leaf chains are removed
    # whole rather than by repeatedly stripping degree-1 nodes, which on a tree
    # would eat the entire shape.
    consumed = set()
    for c, root, tip in real:
        for n in c["nodes"]:
            if n != root:
                consumed.add(n)
    core_nodes = [n for n in nodes if n not in consumed]

    # The spine must not descend into a leg.
    #
    # On an upright biped the legs are axially aligned with the spine, so the
    # longest path through the core happily runs from the head down one leg to
    # the floor. It then claimed the upper half of that leg, leaving the two
    # legs 0.345 and 0.810 long and attached to different spine bones. Limb
    # roots mark where the girdles are: nothing below the lowest of them is
    # spine. A quadruped is unaffected, since its limb roots already sit at
    # spine height, and a limbless worm has no constraint to apply.
    grounded_leaves = [(c, r, t) for (c, r, t) in real
                       if nodes[t]["pos"][ui] <= ground + 0.12 * height]
    if grounded_leaves:
        # The HIGHEST leg root, not the lowest. Using the lowest is circular:
        # when the spine has already eaten a leg's upper half, that leg's root
        # is spuriously low and licenses the very descent it should prevent.
        # Legs attach at a common height on a symmetric body, so the intact one
        # reports the true girdle.
        floor_up = max(nodes[r]["pos"][ui] for (c, r, t) in grounded_leaves) - 0.04 * height
        core_nodes = [n for n in core_nodes if nodes[n]["pos"][ui] >= floor_up]

    if len(core_nodes) >= 2:
        sub = {"nodes": {n: nodes[n] for n in core_nodes},
               "adj": {n: [m for m in ch["adj"].get(n, []) if m in set(core_nodes)]
                       for n in core_nodes}}
        spine_nodes = _longest_path(sub)
    else:
        spine_nodes = []

    if len(spine_nodes) < 2:
        # No branches at all: a worm, snake or tentacle. The whole shape is the
        # spine and its two ends are head and tail.
        spine_nodes = _longest_path(ch)
        real = []

    if len(spine_nodes) < 2:
        return {"error": "could not extract a spine", "object": obj.name}

    axis = (nodes[spine_nodes[-1]]["pos"] - nodes[spine_nodes[0]]["pos"])
    axis = axis.normalized() if axis.length > 1e-9 else Vector((0, 1, 0))

    # Extend the spine through whichever leaf chain continues it at each end.
    #
    # Pruning limbs to find the core also prunes the head and the tail, because
    # those are leaf chains too. On a worm that left only the middle third and
    # reported it as the whole spine. The most axially aligned chain at each end
    # is put back, so the spine runs nose to tail rather than stopping at the
    # first junction.
    # Repeat until neither end grows. A single pass per end is not enough: a
    # worm's core is its middle and both halves attach at the same junction, so
    # one pass folded in one half and left the other reported as a limb with
    # alignment 0.97 - which is to say, obviously part of the spine.
    consumed_by_spine = set()
    for _ in range(6):
        grew = False
        for at_start in (False, True):
            end = spine_nodes[0] if at_start else spine_nodes[-1]
            best, best_score = None, 0.55
            for c, root, tip in real:
                if id(c) in consumed_by_spine or root != end:
                    continue
                d = nodes[tip]["pos"] - nodes[root]["pos"]
                if d.length < 1e-9:
                    continue
                score = abs(d.normalized().dot(axis))
                if score > best_score:
                    best, best_score = (c, root, tip), score
            if best is None:
                continue
            c, root, tip = best
            seq = c["nodes"] if c["nodes"][0] == root else list(reversed(c["nodes"]))
            if at_start:
                spine_nodes = list(reversed(seq[1:])) + spine_nodes
            else:
                spine_nodes = spine_nodes + seq[1:]
            consumed_by_spine.add(id(c))
            grew = True
        if not grew:
            break

    real = [(c, r, t) for (c, r, t) in real if id(c) not in consumed_by_spine]
    spine_set = set(spine_nodes)
    axis = (nodes[spine_nodes[-1]]["pos"] - nodes[spine_nodes[0]]["pos"])
    axis = axis.normalized() if axis.length > 1e-9 else Vector((0, 1, 0))
    end_a, end_b = spine_nodes[0], spine_nodes[-1]

    # the spine's own terminal points are now the head and tail ends
    spine_tips = {
        0: {"tip": [round(v, 4) for v in nodes[end_a]["pos"]],
            "mean_radius": round(nodes[end_a]["radius"], 4), "length": 0.0,
            "from_spine_end": True},
        1: {"tip": [round(v, 4) for v in nodes[end_b]["pos"]],
            "mean_radius": round(nodes[end_b]["radius"], 4), "length": 0.0,
            "from_spine_end": True},
    }

    parts, axial = [], []
    for c, root, tip in real:
        tip_pos, root_pos = nodes[tip]["pos"], nodes[root]["pos"]
        direction = tip_pos - root_pos
        if direction.length < 1e-9:
            continue
        alignment = abs(direction.normalized().dot(axis))
        at_end = root in (end_a, end_b) or root not in spine_set
        seq = c["nodes"] if c["nodes"][0] == root else list(reversed(c["nodes"]))
        entry = {
            "chain": seq, "root_node": root,
            # the medial polyline, root first - the builder follows this rather
            # than a straight line, so a bent limb keeps its bend
            "_points": [[round(v, 5) for v in nodes[n]["pos"]] for n in seq],
            "tip": [round(v, 4) for v in tip_pos],
            "root": [round(v, 4) for v in root_pos],
            "length": c["length"], "mean_radius": c["mean_radius"],
            "alignment": round(alignment, 3),
            "grounded": tip_pos[ui] <= ground + 0.12 * height,
            "lateral_offset": round(tip_pos[li] - bb["centre"][li], 4),
            "forward": round(tip_pos[fi], 4), "up": round(tip_pos[ui], 4),
        }
        # A head or tail continues the spine's own direction; a limb leaves it.
        #
        # Judged on alignment alone, not on which node it attaches to. Requiring
        # it to root exactly at a spine end fails whenever the Reeb graph has
        # cycles - a worm's far half aligned at 0.97 and a quadruped's tail at
        # 0.93 both stayed classified as arms, which they visibly are not.
        # Alignment alone is not enough. A human's arms hang parallel to a
        # vertical spine and score 0.91, so an alignment-only rule classified
        # both of them as tails. What separates them is displacement: a head or
        # tail continues the spine's LINE, while an arm runs parallel to it but
        # off to one side.
        centred = abs(tip_pos[li] - bb["centre"][li]) <= 0.3 * (0.5 * (bb["size"][li] or 1.0))
        if alignment > 0.85 and centred and not entry["grounded"]:
            axial.append(entry)
        elif alignment > 0.6 and at_end and centred and not entry["grounded"]:
            axial.append(entry)
        else:
            # A limb reaches away from the spine. A dimple on the body's surface
            # can be long enough and slender enough to pass the prominence test
            # while still sitting right on top of the spine, so reach is checked
            # too: on a hexapod the real legs stood 0.37 from the spine and the
            # false one 0.12.
            reach = min((tip_pos - nodes[s]["pos"]).length for s in spine_set)
            if reach < 0.12 * span:
                entry["role"] = "bump"
                continue
            entry["role"] = "leg" if entry["grounded"] else "arm"
            parts.append(entry)

    # Head and tail are the spine's own two ends. Any axial leaf chain was
    # already folded into the spine above, so there is nothing left to guess at
    # except which end is which.
    # Candidates are the spine's own two ends plus any axial chain that was not
    # folded into it. Both describe the same thing - where the body terminates
    # along its own axis - so they compete on equal footing.
    candidates = [spine_tips[0], spine_tips[1]] + axial
    for c in candidates:
        c.setdefault("length", 0.0)
    guessed = False
    if head_at is not None:
        candidates.sort(key=lambda e: abs(e["tip"][fi] - head_at))
        head = candidates[0]
        rest = [e for e in candidates[1:]
                if (Vector(e["tip"]) - Vector(head["tip"])).length > 0.15 * span]
        tail = max(rest, key=lambda e: abs(e["tip"][fi] - head["tip"][fi])) if rest else None
    else:
        guessed = True
        ordered = sorted(candidates, key=lambda e: e["tip"][fi])
        head, tail = ordered[0], ordered[-1]
        if head["mean_radius"] < tail["mean_radius"]:
            head, tail = tail, head

    legs = [p for p in parts if p["role"] == "leg"]
    arms = [p for p in parts if p["role"] == "arm"]

    return {
        "object": obj.name,
        "graph": {"nodes": len(graph["nodes"]), "links": len(graph["links"]),
                  "geodesic_span": graph["geodesic_span"]},
        "spine": {
            "nodes": spine_nodes,
            "length": round(sum(
                (nodes[spine_nodes[i]]["pos"] - nodes[spine_nodes[i + 1]]["pos"]).length
                for i in range(len(spine_nodes) - 1)), 5) if len(spine_nodes) > 1 else 0.0,
            "points": [[round(v, 4) for v in nodes[n]["pos"]] for n in spine_nodes],
            "radii": [round(nodes[n]["radius"], 4) for n in spine_nodes],
        },
        "head": head, "tail": tail, "head_end_guessed": guessed,
        "legs": legs, "arms": arms,
        "pruned_bumps": pruned,
        "counts": {"legs": len(legs), "arms": len(arms),
                   "spine_joints": len(spine_nodes)},
        "summary": _summary(len(legs), len(arms), 0, len(spine_nodes)),
    }


def _summary(legs, arms, other, spine_len):
    if legs == 0 and arms == 0 and other == 0:
        return "a single chain - worm, snake, tentacle, or a limbless body"
    bits = []
    if legs:
        bits.append("%d leg%s" % (legs, "" if legs == 1 else "s"))
    if arms:
        bits.append("%d arm%s" % (arms, "" if arms == 1 else "s"))
    if other:
        bits.append("%d other limb%s" % (other, "" if other == 1 else "s"))
    return "spine of %d joints with " % spine_len + ", ".join(bits)
