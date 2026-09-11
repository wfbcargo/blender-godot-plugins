"""Bind a mesh to a fitted armature with Blender's bone-heat weights.

Bone heat is Baran & Popovic's heat-diffusion skinning, already shipped as
`parent_set(type='ARMATURE_AUTO')`, so it is used rather than reimplemented.

What it does not do is fail clearly. It reports "Bone Heat Weighting: failed to
find solution for one or more bones" without saying which bone or why, and it
silently ignores mesh islands no bone can see - producing a bind that looks
successful and leaves geometry unweighted. Everything here exists to turn those
into answers before and after binding.
"""

from __future__ import annotations

import bmesh
import bpy

from . import measure


def preflight(obj_name):
    """Predict whether bone heat will bind, and say what to fix if not."""
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH":
        return {"error": "no mesh named " + repr(obj_name)}

    health = measure.mesh_health(obj)
    fixes = []
    if health["loose_vertices"]:
        fixes.append("delete %d loose vertices" % health["loose_vertices"])
    if health["components"] > 1:
        fixes.append("join or remove %d disconnected surfaces" % health["components"])
    if health["non_manifold_edges"]:
        fixes.append("repair %d non-manifold edges" % health["non_manifold_edges"])
    if max(health["dimensions"]) < 0.1:
        fixes.append("scale the mesh up; bone heat is unreliable below ~0.1 units")

    return {
        "object": obj_name,
        "verdict": health["verdict"],
        "will_likely_bind": health["verdict"] != "blocked",
        "problems": health["problems"],
        "warnings": health["warnings"],
        "suggested_fixes": fixes,
    }


def clean_for_binding(obj_name, remove_loose=True, keep_largest=False):
    """Apply the repairs bone heat needs. Mutates the mesh - copy first."""
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH":
        return {"error": "no mesh named " + repr(obj_name)}

    before = measure.mesh_health(obj)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()

    removed_loose = 0
    if remove_loose:
        loose = [v for v in bm.verts if not v.link_edges]
        removed_loose = len(loose)
        for v in loose:
            bm.verts.remove(v)

    removed_islands = 0
    if keep_largest:
        bm.verts.ensure_lookup_table()
        parent = {v.index: v.index for v in bm.verts}

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for e in bm.edges:
            ra, rb = find(e.verts[0].index), find(e.verts[1].index)
            if ra != rb:
                parent[ra] = rb
        groups = {}
        for v in bm.verts:
            groups.setdefault(find(v.index), []).append(v)
        if len(groups) > 1:
            biggest = max(groups.values(), key=len)
            keep = {v.index for v in biggest}
            doomed = [v for v in bm.verts if v.index not in keep]
            removed_islands = len(doomed)
            for v in doomed:
                bm.verts.remove(v)

    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

    after = measure.mesh_health(obj)
    return {
        "object": obj_name,
        "removed_loose_vertices": removed_loose,
        "removed_island_vertices": removed_islands,
        "verdict_before": before["verdict"],
        "verdict_after": after["verdict"],
        "problems_after": after["problems"],
    }


def bind(mesh_name, rig_name, check=True):
    """Parent mesh to armature with automatic (bone heat) weights.

    Verifies afterwards that every vertex actually received weight. A bind that
    leaves geometry at zero weight still 'succeeds' and then tears apart the
    moment the rig moves.
    """
    obj = bpy.data.objects.get(mesh_name)
    rig = bpy.data.objects.get(rig_name)
    if obj is None or obj.type != "MESH":
        return {"error": "no mesh named " + repr(mesh_name)}
    if rig is None or rig.type != "ARMATURE":
        return {"error": "no armature named " + repr(rig_name)}

    if check:
        pre = preflight(mesh_name)
        if not pre["will_likely_bind"]:
            return {"error": "mesh is not in a bindable state",
                    "preflight": pre}

    view = bpy.context.view_layer
    prev_active = view.objects.active

    # Deselect through the API rather than bpy.ops.object.select_all, whose
    # poll fails outright when there is no valid active object - which is the
    # state a preceding edit-mode pass can leave behind.
    if view.objects.active is None and view.objects:
        view.objects.active = obj
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in view.objects:
        o.select_set(False)

    obj.select_set(True)
    rig.select_set(True)
    view.objects.active = rig

    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        failed = None
    except Exception as e:
        failed = str(e)
    finally:
        view.objects.active = prev_active

    if failed:
        return {"error": "bone heat failed: " + failed,
                "hint": "run clean_for_binding, or scale the mesh up"}

    groups = {g.name for g in obj.vertex_groups}
    deform = {b.name for b in rig.data.bones if b.use_deform}
    weighted = 0
    unweighted = []
    for v in obj.data.vertices:
        total = sum(g.weight for g in v.groups)
        if total > 1e-6:
            weighted += 1
        elif len(unweighted) < 20:
            unweighted.append(v.index)

    total_verts = len(obj.data.vertices)
    coverage = weighted / total_verts if total_verts else 0.0

    return {
        "mesh": mesh_name,
        "rig": rig_name,
        "vertex_groups": len(groups),
        "deform_bones": len(deform),
        "bones_without_group": sorted(deform - groups)[:12],
        "weighted_vertices": weighted,
        "total_vertices": total_verts,
        "coverage": round(coverage, 4),
        "unweighted_sample": unweighted,
        "passed": coverage > 0.999,
        "note": ("every vertex is weighted" if coverage > 0.999 else
                 "%d vertices carry no weight and will not follow the rig"
                 % (total_verts - weighted)),
    }
