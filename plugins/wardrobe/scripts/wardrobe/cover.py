"""Which parts of the body a garment covers - and so which the engine should stop drawing.

    rep = cover.compute(shirt, "Figure")         # writes wd_hide / wd_edge groups on the body copy
    print(cover.summarize(rep))

Hiding covered skin is the fix every engine uses for skin showing through clothes (Bethesda's
biped slots, MetaHuman's body masks, Character Creator's hide-inner-mesh). Skin that is not
drawn cannot poke through.

A body vertex is **covered** when a ray from it along its normal meets the garment within
`max_gap`. Covered skin is hidden only where the cloth over it is skinned like it (`agree`, the
share of weight they have in common): a thigh under a hem hung from the torso, or an arm under a
cuff on cuff bones, swings out from under the cloth, and hidden it opens holes into the body: on
the sample shirt, hiding all covered skin left 38 thigh vertices uncovered in the worst frame
of a walk (0.72%); with `agree` 0.7, 1. Covered, agreeing skin is **hidden** unless it is
within `margin` (along the surface) of skin that is uncovered or disagrees: that band, the **edge**, stays drawn so a neckline, cuff or hem
never opens a hole when the garment slides a little. The hidden set is carried to Godot by
position (Godot's importer reorders vertices), and Godot drops every triangle whose three
vertices are hidden.
"""

from __future__ import annotations

import base64
import heapq
import struct

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import fit, rigmap


def garment_bvh(garment):
    g = rigmap._obj(garment)
    me = g.data
    verts = [v.co.copy() for v in me.vertices]
    tris = fit.canonical_tris(me)
    return BVHTree.FromPolygons(verts, tris, all_triangles=True)


def _weights(obj):
    names = {vg.index: vg.name for vg in obj.vertex_groups}
    bones = {b.name for b in rigmap.rig_of(obj).data.bones if b.use_deform}
    return [{names[x.group]: x.weight for x in v.groups if x.weight > 0 and names[x.group] in bones}
            for v in obj.data.vertices]


def compute(garment, body, max_gap=0.1, margin=0.03, agree=0.7, groups=True, floor_z=None, max_front=None,
            behind=0.0):
    """`agree`: the least share of skinning the skin and the cloth over it must have in common
    for that skin to be hidden. Skin on a thigh under a hem hung from the torso, or on an arm
    under a cuff hung from cuff bones, moves out from under the cloth: it stays drawn.

    `floor_z` (body object space): no skin below it counts as covered. None takes the cut's
    `cover_floor_z` - a skirt's hem hinge: below it the cloth is the hem bones' and they move it, so
    nothing under it is hidden. `max_front`: skin facing forward more than this (its normal on the
    body's forward axis) is not covered, below the cut's `cover_front_top_z` when it has one; None
    takes the cut's `cover_max_front` - the belly comes away from a skirt's waistband when the body
    folds in a crouch.

    `behind`: how far under the skin cloth may lie and still cover it - a compression garment
    (`fit.ease(..., flatten=...)`) is pressed into the flesh it squeezes. The line is then also
    followed inward that far, skin neither line reaches is covered by the nearest cloth within
    that distance when it lies over that cloth's face, and the report adds `inside` (covered skin with the cloth under it)
    and `drawn_over_cloth` (corners of triangles still drawn that lie over the cloth: skin showing
    through it - see `drawn_over_cloth`, which `wardrobe.dress` lifts the cloth over)."""
    g = rigmap._obj(garment)
    b = rigmap._obj(body)
    if floor_z is None:
        cut = g.get("wardrobe_cut")
        floor_z = cut.get("cover_floor_z") if cut is not None else None
    if max_front is None:
        cut = g.get("wardrobe_cut")
        max_front = cut.get("cover_max_front") if cut is not None else None
    fwd = rigmap.humanoid(b)["forward"] if max_front is not None else None
    cut = g.get("wardrobe_cut")
    front_top = cut.get("cover_front_top_z", 1e9) if cut is not None else 1e9
    to_body = b.matrix_world.inverted() @ g.matrix_world
    me = g.data
    gv = [to_body @ v.co for v in me.vertices]
    gtris = fit.canonical_tris(me)
    bvh = BVHTree.FromPolygons(gv, gtris, all_triangles=True)
    gw = _weights(g)
    bw = _weights(b)

    bme = b.data
    covered = [False] * len(bme.vertices)
    agrees = [False] * len(bme.vertices)
    gap = [0.0] * len(bme.vertices)
    for v in bme.vertices:
        if floor_z is not None and v.co.z < floor_z:
            continue
        if fwd is not None and v.co.z < front_top and v.normal.dot(fwd) > max_front:
            continue
        n = v.normal
        hit = bvh.ray_cast(v.co + n * 0.0005, n, max_gap)
        depth = hit[3] if hit[0] is not None else None
        # the cloth over this skin faces the way the skin does; cloth on the other leg, reached
        # across the gap from an inner thigh, faces back at it - hidden, that skin was a hole
        if hit[0] is not None and hit[1].dot(n) < 0.3:
            hit = (None,)
        if hit[0] is None and behind > 0:
            hit = bvh.ray_cast(v.co + n * 0.0005, -n, behind + 0.0005)
            # under the skin it only has to face out: compressed across a crease (a crotch, the
            # fold under a buttock) the cloth turns away from the skin it passes under
            if hit[0] is not None and hit[1].dot(n) < 0.0:
                hit = (None,)
            depth = -(hit[3] - 0.0005) if hit[0] is not None else None
        if hit[0] is None and behind > 0:
            # in a cleft (a crotch) the skin's normal runs along the compressed cloth and both
            # lines miss it: the nearest cloth, over its face and not turned against the skin
            near = bvh.find_nearest(v.co, behind)
            if near[0] is not None and near[3] > 1e-9:
                side = (v.co - near[0]).dot(near[1])
                if abs(side) > 0.7 * near[3] and near[1].dot(n) > -0.2:
                    hit, depth = near, -side
        if hit[0] is None:
            continue
        covered[v.index] = True
        gap[v.index] = depth
        t = gtris[hit[2]]
        u, vv, w = _bary(hit[0], gv[t[0]], gv[t[1]], gv[t[2]])
        cloth = {}
        for i, f in zip(t, (u, vv, w)):
            for k, x in gw[i].items():
                cloth[k] = cloth.get(k, 0.0) + x * f
        skin = bw[v.index]
        common = sum(min(x, cloth.get(k, 0.0)) for k, x in skin.items())
        agrees[v.index] = common >= agree

    # distance along the body's surface from uncovered skin
    adj = [[] for _ in bme.vertices]
    for e in bme.edges:
        a, c = e.vertices
        d = (bme.vertices[a].co - bme.vertices[c].co).length
        adj[a].append((c, d))
        adj[c].append((a, d))
    dist = [1e9] * len(bme.vertices)
    heap = []
    for i, cov in enumerate(covered):
        # skin under the floor is not an edge of the cloth: the margin runs from cloth edges only
        if (not cov or not agrees[i]) and (floor_z is None or bme.vertices[i].co.z >= floor_z) \
                and (fwd is None or bme.vertices[i].co.z >= front_top or bme.vertices[i].normal.dot(fwd) <= max_front):
            dist[i] = 0.0
            heap.append((0.0, i))
    heapq.heapify(heap)
    while heap:
        d, i = heapq.heappop(heap)
        if d > dist[i] or d > margin:
            continue
        for j, w in adj[i]:
            nd = d + w
            if nd < dist[j] and nd <= margin:
                dist[j] = nd
                heapq.heappush(heap, (nd, j))
    hidden = [covered[i] and agrees[i] and dist[i] > margin for i in range(len(covered))]
    edge = [covered[i] and not hidden[i] for i in range(len(covered))]
    disagree = [i for i in range(len(covered)) if covered[i] and not agrees[i]]

    if groups and b.type == "MESH" and "wardrobe_cut" not in b.keys():
        for name, flags in (("wd_hide_" + g.name, hidden), ("wd_edge_" + g.name, edge)):
            vg = b.vertex_groups.get(name) or b.vertex_groups.new(name=name)
            vg.remove(list(range(len(flags))))
            vg.add([i for i, f in enumerate(flags) if f], 1.0, "REPLACE")
            vg.lock_weight = True

    # triangles that disappear: all three corners hidden
    bme.calc_loop_triangles()
    tris_hidden = sum(1 for t in bme.loop_triangles if all(hidden[i] for i in t.vertices))
    gaps = sorted(gap[i] for i in range(len(gap)) if hidden[i])
    return {"garment": g.name, "body": b.name, "body_verts": len(bme.vertices),
            "covered": sum(covered), "disagree": sum(1 for i in range(len(covered)) if covered[i] and not agrees[i]),
            "hidden": sum(hidden), "edge": sum(edge),
            "tris_total": len(bme.loop_triangles), "tris_hidden": tris_hidden,
            "hidden_gap_median_m": round(gaps[len(gaps) // 2], 4) if gaps else None,
            "hidden_gap_max_m": round(gaps[-1], 4) if gaps else None,
            "max_gap": max_gap, "margin": margin, **({"floor_z": floor_z} if floor_z is not None else {}),
            **({"max_front": max_front} if max_front is not None else {}),
            **({"behind": behind, "inside": sum(1 for i in range(len(gap)) if covered[i] and gap[i] < 0),
                "drawn_over_cloth": len(drawn_over_cloth(g, b, {"_hidden": [i for i, f in enumerate(hidden) if f],
                                                                  "_edge": [i for i, f in enumerate(edge) if f],
                                                                  "_disagree": disagree},
                                                         reach=behind))}
               if behind > 0 else {}),
            "_hidden": [i for i, f in enumerate(hidden) if f], "_edge": [i for i, f in enumerate(edge) if f],
            "_disagree": disagree}


def drawn_over_cloth(garment, body, rep, reach=0.03, tol=0.0005):
    """Body triangles the engine still draws (not every corner hidden) with a covered or hidden
    corner lying over the garment's face within `reach` - skin that shows through it. `rep`: this
    garment's `compute` report. A compression garment is eased inside the skin it squeezes, and a
    triangle between a hidden and a drawn vertex is drawn whole: at the edge of the hidden skin, and
    in a crotch where it stays drawn, the hidden corner stood through the cloth. Skin the garment
    does not cover - an arm beside a top - lies over the cloth by right and is not counted."""
    g = rigmap._obj(garment)
    b = rigmap._obj(body)
    hid = set(rep["_hidden"])
    # skinned unlike the cloth over it is skin beside the garment, not under it: an inner arm
    # against a top lay over its face by right, and lifting the top over it ran away
    under = hid | (set(rep["_edge"]) - set(rep.get("_disagree", ())))
    bvh = garment_bvh(g)
    bme = b.data
    bme.calc_loop_triangles()
    over = {}
    out = []
    for t in bme.loop_triangles:
        vs = tuple(t.vertices)
        if all(i in hid for i in vs):
            continue
        bad = False
        for i in vs:
            if i not in under:
                continue
            if i not in over:
                co = bme.vertices[i].co
                h = bvh.find_nearest(co, reach)
                over[i] = False
                if h[0] is not None and h[3] > 1e-9:
                    side = (co - h[0]).dot(h[1])
                    over[i] = side > tol and side > 0.7 * h[3]
            bad = bad or over[i]
        if bad:
            out.append(vs)
    return sorted(out)


def _bary(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11, d20, d21 = v0.dot(v0), v0.dot(v1), v1.dot(v1), v2.dot(v0), v2.dot(v1)
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-18:
        return 1.0, 0.0, 0.0
    y = (d11 * d20 - d01 * d21) / den
    z = (d00 * d21 - d01 * d20) / den
    return 1.0 - y - z, y, z


def gltf_positions(body, indices):
    """Body vertex positions in the glTF mesh space (Y up: x, z, -y), float32 little-endian,
    base64 - the form the Godot runtime matches against the imported mesh."""
    b = rigmap._obj(body)
    buf = bytearray()
    for i in indices:
        co = b.data.vertices[i].co
        buf += struct.pack("<fff", co.x, co.z, -co.y)
    return base64.b64encode(bytes(buf)).decode("ascii")


def summarize(rep):
    return (f"{rep['garment']} over {rep['body']}: {rep['covered']} of {rep['body_verts']} body verts covered, "
            f"{rep['disagree']} skinned unlike the cloth over them, "
            f"{rep['hidden']} hidden, {rep['edge']} kept as edge ({rep['margin'] * 100:.0f} cm); "
            f"{rep['tris_hidden']} of {rep['tris_total']} triangles not drawn; "
            f"gap under hidden skin median {rep['hidden_gap_median_m']} m, max {rep['hidden_gap_max_m']} m")
