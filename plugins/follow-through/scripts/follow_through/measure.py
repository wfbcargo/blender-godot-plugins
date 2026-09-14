"""Measure a mesh for secondary-motion recognition.

Everything here is deterministic geometry. It does not decide what a thing *is*;
it produces the evidence `classify` argues from, and the renders settle what the
evidence cannot. A flag and a tablecloth are the same open sheet - which one it
is depends on what it touches and which way it faces.

The measures, and what each is for:

  boundary loops     an open sheet has one, a tube (skirt, sleeve) has two or more,
                     a closed body has none. The single strongest cloth cue.
  thickness          a closed mesh can still be cloth: a sheet given a Solidify and
                     applied. Rays cast inward from each face land a few mm away.
  curvature          total absolute angle defect over 4*pi. A sphere scores 1, a flat
                     or folded sheet near 0 - cloth is made from flat panels.
  extents            principal extents from area-weighted PCA. A strip much longer
                     than wide behaves as a strand (scarf, ribbon), not a sheet.
  contacts           which other objects each vertex touches: a pole, a body, a
                     table. Pins come from here.
  skin               armature and deform groups: a cloth skinned to a rig is worn.

World space and metres throughout, Blender Z up.
"""

from __future__ import annotations

import math
import re

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

# Modifiers that change the vertex set glTF would write. A cloth object carrying
# one would pin vertices that do not exist in the exported file.
TOPOLOGY_MODIFIERS = {"SUBSURF", "MIRROR", "ARRAY", "SOLIDIFY", "BEVEL", "DECIMATE",
                      "REMESH", "TRIANGULATE", "WELD", "SCREW", "SKIN", "BOOLEAN",
                      "NODES", "MULTIRES", "WIREFRAME", "EDGE_SPLIT", "MASK", "BUILD"}
# Modifiers follow-through owns or that deform without changing topology.
HARMLESS_MODIFIERS = {"ARMATURE", "CLOTH", "COLLISION", "SOFT_BODY", "SMOOTH",
                      "CORRECTIVE_SMOOTH", "LAPLACIANSMOOTH", "DATA_TRANSFER",
                      "SHRINKWRAP", "SURFACE_DEFORM", "MESH_DEFORM", "LATTICE",
                      "DISPLACE", "WAVE", "HOOK", "SIMPLE_DEFORM", "CAST", "WARP"}


def _world_bmesh(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return bm


def _components(bm):
    """Connected vertex islands, as lists of vertex indices."""
    seen = set()
    out = []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack = [v]
        seen.add(v.index)
        comp = []
        while stack:
            cur = stack.pop()
            comp.append(cur.index)
            for e in cur.link_edges:
                o = e.other_vert(cur)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
        out.append(comp)
    return out


def boundary_loops(bm):
    """Chain boundary edges into loops. Returns lists of vertex indices in order.

    A boundary vertex normally has exactly two boundary edges. A bow-tie vertex
    (two sheets meeting at a point) has four; the walk takes any unused edge, so
    such a mesh yields loops that may be split differently than a human would
    draw them - the count stays right, which is what classification uses."""
    unused = {e.index for e in bm.edges if e.is_boundary}
    loops = []
    while unused:
        start = bm.edges[unused.pop()]
        loop = [start.verts[0].index, start.verts[1].index]
        cur = start.verts[1]
        guard = 0
        while guard < len(bm.edges) + 2:
            guard += 1
            nxt = None
            for e in cur.link_edges:
                if e.index in unused:
                    nxt = e
                    break
            if nxt is None:
                break
            unused.discard(nxt.index)
            cur = nxt.other_vert(cur)
            if cur.index == loop[0]:
                break
            loop.append(cur.index)
        loops.append(loop)
    return loops


def _pca(points, weights=None):
    """Principal axes and extents of a point set. Axes sorted longest first."""
    import numpy as np
    P = np.array([tuple(p) for p in points], dtype=float)
    if len(P) == 0:
        return {"centre": [0, 0, 0], "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "extents": [0, 0, 0]}
    W = np.ones(len(P)) if weights is None else np.array(weights, dtype=float)
    W = W / max(W.sum(), 1e-12)
    c = (P * W[:, None]).sum(axis=0)
    Q = P - c
    cov = (Q * W[:, None]).T @ Q
    vals, vecs = np.linalg.eigh(cov)
    order = np.argsort(vals)[::-1]
    axes = [vecs[:, i] for i in order]
    extents = [float(np.ptp(Q @ a)) for a in axes]
    return {"centre": c.tolist(), "axes": [a.tolist() for a in axes], "extents": extents}


def _angle_defect_ratio(bm):
    """Total absolute Gaussian curvature (angle defect) over interior vertices / 4 pi.

    Boundary vertices are skipped: their defect measures the outline's turning,
    not the surface's curvature."""
    total = 0.0
    for v in bm.verts:
        if v.is_boundary or not v.link_faces:
            continue
        s = 0.0
        for loop in v.link_loops:
            s += loop.calc_angle()
        total += abs(2.0 * math.pi - s)
    return total / (4.0 * math.pi)


def _thickness(bm, samples=400):
    """Median distance a ray cast inward from a face travels before hitting the mesh.

    For a closed body it is the body's depth; for a solidified sheet, the
    solidify thickness. Returns None for meshes with no faces."""
    if not bm.faces:
        return None
    tree = BVHTree.FromBMesh(bm)
    step = max(1, len(bm.faces) // samples)
    hits = []
    # BMesh sequences refuse stepped slices; every cloth sample had under 800 faces, so
    # step was 1 and this only failed on the first dense body
    bm.faces.ensure_lookup_table()
    for fi in range(0, len(bm.faces), step):
        f = bm.faces[fi]
        n = f.normal
        if n.length < 1e-9:
            continue
        origin = f.calc_center_median() - n * 1e-5
        loc, _normal, _idx, dist = tree.ray_cast(origin, -n)
        if loc is not None and dist is not None:
            hits.append(dist)
    if not hits:
        return None
    hits.sort()
    return hits[len(hits) // 2]


def _home(obj):
    """The scene and view layer `obj` lives in - not necessarily the active one."""
    scene = obj.users_scene[0] if obj.users_scene else bpy.context.scene
    return scene, scene.view_layers[0]


def _other_mesh_trees(obj, radius):
    """BVH trees, in world space, of every other visible mesh near `obj` in its scene."""
    scene, layer = _home(obj)
    depsgraph = layer.depsgraph
    lo, hi = _world_bounds(obj)
    lo = lo - Vector((radius,) * 3)
    hi = hi + Vector((radius,) * 3)
    trees = []
    for other in scene.objects:
        if other is obj or other.type != "MESH" or not other.visible_get(view_layer=layer):
            continue
        olo, ohi = _world_bounds(other)
        if any(olo[i] > hi[i] or ohi[i] < lo[i] for i in range(3)):
            continue
        ev = other.evaluated_get(depsgraph)
        me = ev.to_mesh()
        try:
            mw = other.matrix_world
            verts = [mw @ v.co for v in me.vertices]
            polys = [tuple(p.vertices) for p in me.polygons]
            if polys:
                # closed: every edge shared by exactly two faces, so "inside" means something
                counts = {}
                for p in me.polygons:
                    for ek in p.edge_keys:
                        counts[ek] = counts.get(ek, 0) + 1
                closed = all(c == 2 for c in counts.values())
                trees.append((other.name, BVHTree.FromPolygons(verts, polys), closed))
        finally:
            ev.to_mesh_clear()
    return trees


def _inside(tree, p):
    """Ray-parity inside test against a closed mesh. Casts along a skewed axis so a
    ray grazing an edge or running along a face is not the common case."""
    d = Vector((0.5773, 0.5774, 0.5773)).normalized()
    origin = p.copy()
    hits = 0
    for _ in range(64):
        loc, _n, _i, _dist = tree.ray_cast(origin, d)
        if loc is None:
            break
        hits += 1
        origin = loc + d * 1e-5
    return hits % 2 == 1


def _world_bounds(obj):
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def contacts(obj, bm=None, tolerance=None):
    """Which other objects each vertex touches.

    A vertex touches an object when it lies inside it or within `tolerance` of
    its surface. Default tolerance is 1 cm or 1% of the object's size, whichever
    is larger - a banner's edge wraps a pole a few mm off its surface, and a
    tolerance fixed in metres would miss that on a large sail and catch the floor
    under a small handkerchief."""
    own = bm is None
    if own:
        bm = _world_bmesh(obj)
    try:
        lo, hi = _world_bounds(obj)
        size = (hi - lo).length
        tol = tolerance if tolerance is not None else max(0.01, 0.01 * size)
        trees = _other_mesh_trees(obj, tol)
        by_object = {}
        for name, tree, closed in trees:
            touching = []
            for v in bm.verts:
                hit = tree.find_nearest(v.co)
                if hit[0] is None:
                    continue
                dist = hit[3]
                if dist <= tol or (closed and _inside(tree, v.co)):
                    touching.append(v.index)
            if touching:
                by_object[name] = touching
        return {"tolerance": tol, "by_object": by_object}
    finally:
        if own:
            bm.free()


def skin(obj):
    """Armature, deform bones and each vertex's strongest bone."""
    arm = None
    for m in obj.modifiers:
        if m.type == "ARMATURE" and m.object is not None:
            arm = m.object
            break
    if arm is None and obj.parent is not None and obj.parent.type == "ARMATURE" \
            and obj.parent_type == "ARMATURE":
        arm = obj.parent
    if arm is None:
        return {"armature": None}
    bone_names = {b.name for b in arm.data.bones}
    groups = {g.index: g.name for g in obj.vertex_groups if g.name in bone_names}
    strongest = {}
    for v in obj.data.vertices:
        best = None
        for g in v.groups:
            if g.group in groups and g.weight > 0.0 and (best is None or g.weight > best[1]):
                best = (groups[g.group], g.weight)
        if best:
            strongest[v.index] = best[0]
    return {"armature": arm.name, "deform_groups": sorted(groups.values()),
            "weighted_vertices": len(strongest), "strongest_bone": strongest}


NAME_HINTS = {
    "hanging_sheet": ("flag", "banner", "curtain", "drape", "pennant", "standard", "tapestry"),
    "draped_sheet": ("cape", "cloak", "tabard", "mantle", "shawl", "poncho", "apron"),
    "draped_tube": ("skirt", "robe", "dress", "kilt", "gown", "sleeve", "tunic", "shirt"),
    "loose_sheet": ("tablecloth", "towel", "tarp", "sheet", "blanket", "rug", "cloth", "napkin"),
    "strap": ("scarf", "ribbon", "sash", "strap", "belt", "tassel", "streamer", "bandana"),
    "tensioned": ("sail", "tent", "awning", "canopy", "hammock", "kite"),
}


def name_hints(name):
    tokens = [t for t in re.split(r"[^a-z]+", name.lower()) if t]
    found = []
    for cls, words in NAME_HINTS.items():
        for t in tokens:
            if any(t == w or t == w + "s" for w in words):
                found.append(cls)
                break
    return found


def analyze(obj_name, contact_tolerance=None):
    """Every measure recognition needs, for one mesh object."""
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        return {"error": "no object named " + repr(obj_name)}
    if obj.type != "MESH":
        return {"error": f"{obj_name} is a {obj.type}, not a mesh"}
    # A scene that is not the active one is not evaluated on its own: objects
    # created or moved in it keep a stale matrix_world - identity, for new ones -
    # and every world-space measure then reads them piled up at the origin.
    _home(obj)[1].update()

    bm = _world_bmesh(obj)
    try:
        comps = _components(bm)
        loops = boundary_loops(bm)
        area = sum(f.calc_area() for f in bm.faces)
        non_manifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
        wire = sum(1 for e in bm.edges if not e.link_faces)
        closed = not loops and bm.faces
        volume = abs(bm.calc_volume(signed=True)) if closed else 0.0
        thickness = _thickness(bm)
        pca = _pca([v.co for v in bm.verts])
        edge_lengths = sorted(e.calc_length() for e in bm.edges)
        mean_edge = sum(edge_lengths) / len(edge_lengths) if edge_lengths else 0.0
        lo, hi = _world_bounds(obj)

        loop_info = []
        for lp in loops:
            pts = [bm.verts[i].co for i in lp]
            length = sum((pts[i] - pts[(i + 1) % len(pts)]).length for i in range(len(pts)))
            c = sum(pts, Vector()) / len(pts)
            lp_pca = _pca(pts)
            loop_info.append({
                "vertices": lp,
                "count": len(lp),
                "length": round(length, 4),
                "centre": [round(x, 4) for x in c],
                "height": round(c.z, 4),
                # normal of the loop's best-fit plane: smallest principal axis
                "plane_normal": [round(x, 4) for x in lp_pca["axes"][2]],
                "flatness": round(lp_pca["extents"][2] / max(lp_pca["extents"][0], 1e-9), 4),
            })

        # Face normals, area-weighted: a vertical sheet's normal is horizontal.
        n_sum = Vector()
        n_abs_z = 0.0
        for f in bm.faces:
            a = f.calc_area()
            n_sum += f.normal * a
            n_abs_z += abs(f.normal.z) * a
        verticality = 1.0 - (n_abs_z / area if area > 0 else 0.0)

        cont = contacts(obj, bm, contact_tolerance)
        # where on the sheet each contact sits, as a fraction of its height
        height_span = max(hi.z - lo.z, 1e-9)
        for name, idx in list(cont["by_object"].items()):
            zs = [bm.verts[i].co.z for i in idx]
            cont["by_object"][name] = {
                "vertices": idx,
                "count": len(idx),
                "fraction_of_vertices": round(len(idx) / max(len(bm.verts), 1), 4),
                "mean_height_fraction": round((sum(zs) / len(zs) - lo.z) / height_span, 4),
            }
        sk = skin(obj)
        size = max(pca["extents"][0], 1e-9)

        modifiers = [(m.name, m.type) for m in obj.modifiers]
        blocking = [n for n, t in modifiers if t in TOPOLOGY_MODIFIERS]

        # Euler characteristic of each island: a disc (one open sheet) is 1,
        # an annulus (a tube open at both ends) is 0, a closed sphere-like body 2.
        euler = len(bm.verts) - len(bm.edges) + len(bm.faces)

        return {
            "object": obj.name,
            "vertices": len(bm.verts),
            "edges": len(bm.edges),
            "faces": len(bm.faces),
            "components": len(comps),
            "euler_characteristic": euler,
            "boundary_loops": loop_info,
            "closed": bool(closed),
            "non_manifold_edges": non_manifold,
            "wire_edges": wire,
            "area_m2": round(area, 5),
            "volume_m3": round(volume, 6),
            # 0.094 for a sphere, near 0 for anything sheet-like
            "compactness": round(volume / (area ** 1.5), 5) if area > 0 else 0.0,
            "thickness_m": None if thickness is None else round(thickness, 5),
            "thickness_over_size": None if thickness is None else round(thickness / size, 5),
            "curvature_over_sphere": round(_angle_defect_ratio(bm), 4),
            "extents_m": [round(e, 4) for e in pca["extents"]],
            "principal_axes": [[round(x, 4) for x in a] for a in pca["axes"]],
            "aspect_long_over_mid": round(pca["extents"][0] / max(pca["extents"][1], 1e-9), 3),
            "flatness_min_over_long": round(pca["extents"][2] / size, 4),
            "verticality": round(verticality, 3),
            "mean_edge_m": round(mean_edge, 5),
            "bounds": {"min": [round(x, 4) for x in lo], "max": [round(x, 4) for x in hi]},
            "contacts": cont,
            "skin": {k: v for k, v in sk.items() if k != "strongest_bone"},
            "name_hints": name_hints(obj.name),
            "modifiers": modifiers,
            "blocking_modifiers": blocking,
            "existing_cloth": [m.name for m in obj.modifiers if m.type == "CLOTH"],
            "vertex_groups": [g.name for g in obj.vertex_groups],
            "uv_layers": len(obj.data.uv_layers),
            "shape_keys": 0 if obj.data.shape_keys is None else len(obj.data.shape_keys.key_blocks),
        }
    finally:
        bm.free()
