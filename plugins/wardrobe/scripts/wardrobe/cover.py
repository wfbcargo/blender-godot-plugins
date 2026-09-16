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


def compute(garment, body, max_gap=0.1, margin=0.03, agree=0.7, groups=True):
    """`agree`: the least share of skinning the skin and the cloth over it must have in common
    for that skin to be hidden. Skin on a thigh under a hem hung from the torso, or on an arm
    under a cuff hung from cuff bones, moves out from under the cloth: it stays drawn."""
    g = rigmap._obj(garment)
    b = rigmap._obj(body)
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
        n = v.normal
        hit = bvh.ray_cast(v.co + n * 0.0005, n, max_gap)
        if hit[0] is None:
            continue
        # the cloth over this skin faces the way the skin does; cloth on the other leg, reached
        # across the gap from an inner thigh, faces back at it - hidden, that skin was a hole
        if hit[1].dot(n) < 0.3:
            continue
        covered[v.index] = True
        gap[v.index] = hit[3]
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
        if not cov or not agrees[i]:
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
            "max_gap": max_gap, "margin": margin,
            "_hidden": [i for i, f in enumerate(hidden) if f], "_edge": [i for i, f in enumerate(edge) if f]}


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
