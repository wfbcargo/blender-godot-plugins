"""Test bodies with known answers, for scoring recognition.

Built in their own scene, `FollowThroughSamples`, so the user's scene is never
touched. Each body carries its truth in `obj["ft_truth"]`: the class it should
be recognised as and, for cloth, which vertices a person would pin.

    samples.build_all()                  # (re)build the scene, returns its name
    samples.score(results)               # compare classify results with truth

Units are metres; Blender Z up.
"""

from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

SCENE = "FollowThroughSamples"


def _scene():
    sc = bpy.data.scenes.get(SCENE)
    if sc is not None:
        for o in list(sc.objects):
            data = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if data is not None and data.users == 0:
                if isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Armature):
                    bpy.data.armatures.remove(data)
    else:
        sc = bpy.data.scenes.new(SCENE)
    return sc


def _link(sc, name, bm, location=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = location
    sc.collection.objects.link(ob)
    return ob


def _grid(size_x, size_y, cuts_x, cuts_y, matrix=None):
    """A subdivided rectangle in the XY plane, centred, optionally transformed."""
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=cuts_x, y_segments=cuts_y, size=0.5)
    bmesh.ops.scale(bm, vec=(size_x, size_y, 1.0), verts=bm.verts)
    if matrix is not None:
        bmesh.ops.transform(bm, matrix=matrix, verts=bm.verts)
    return bm


def _cylinder(radius, depth, segments=24, caps=True, radius_bottom=None, rings=1):
    bm = bmesh.new()
    rb = radius if radius_bottom is None else radius_bottom
    rows = []
    for r in range(rings + 1):
        t = r / rings
        z = depth * 0.5 - depth * t
        rad = radius + (rb - radius) * t
        rows.append([bm.verts.new((rad * math.cos(2 * math.pi * i / segments),
                                   rad * math.sin(2 * math.pi * i / segments), z))
                     for i in range(segments)])
    for a, b in zip(rows, rows[1:]):
        for i in range(segments):
            j = (i + 1) % segments
            bm.faces.new((a[i], a[j], b[j], b[i]))
    if caps:
        bm.faces.new(list(reversed(rows[0])))
        bm.faces.new(rows[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def _top_row(ob, axis=2, tol=1e-4):
    zs = [v.co[axis] for v in ob.data.vertices]
    top = max(zs)
    return sorted(v.index for v in ob.data.vertices if v.co[axis] > top - tol)


def _armature(sc, name, bones, location=(0, 0, 0)):
    """bones: [(name, head, tail, parent or None)]"""
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    ob.location = location
    sc.collection.objects.link(ob)
    # edit bones need the object active in a view layer
    win = bpy.context.window
    prev_scene = win.scene
    win.scene = sc
    try:
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode="EDIT")
        made = {}
        for bname, head, tail, parent in bones:
            eb = arm.edit_bones.new(bname)
            eb.head = head
            eb.tail = tail
            if parent:
                eb.parent = made[parent]
            made[bname] = eb
        bpy.ops.object.mode_set(mode="OBJECT")
    finally:
        win.scene = prev_scene
    return ob


def _skin_by_height(ob, rig, bands):
    """Weight every vertex fully to the bone whose z band holds it (world z)."""
    ob.users_scene[0].view_layers[0].update()      # matrix_world is stale until evaluated
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    groups = {b: ob.vertex_groups.new(name=b) for b, _lo, _hi in bands}
    for v in ob.data.vertices:
        z = (ob.matrix_world @ v.co).z
        for b, lo, hi in bands:
            if lo <= z < hi:
                groups[b].add([v.index], 1.0, "REPLACE")
                break
        else:
            groups[bands[-1][0]].add([v.index], 1.0, "REPLACE")


def build_all():
    sc = _scene()
    rot_x90 = Matrix.Rotation(math.radians(90), 4, "X")   # XY grid -> XZ (vertical, facing -Y)

    # 1. A banner on a pole: vertical sheet, one edge along the pole.
    pole = _link(sc, "FlagPole", _cylinder(0.03, 2.6, 16), (0, 0, 1.3))
    pole["ft_truth"] = {"class": "rigid"}
    m = Matrix.Translation((0.4, 0, 1.8)) @ rot_x90
    banner = _link(sc, "Banner", _grid(0.8, 1.0, 16, 20, m))
    left = min(v.co.x for v in banner.data.vertices)
    banner["ft_truth"] = {"class": "hanging_sheet",
                          "pins": sorted(v.index for v in banner.data.vertices if v.co.x < left + 1e-4)}

    # 2. A curtain threaded on a rod.
    rod = _link(sc, "CurtainRod", _cylinder(0.02, 1.8, 12), (3.0, 0, 2.2))
    rod.rotation_euler = (0, math.radians(90), 0)
    m = Matrix.Translation((3.0, 0, 1.3)) @ rot_x90
    curtain = _link(sc, "Curtain", _grid(1.4, 1.8, 20, 24, m))
    curtain["ft_truth"] = {"class": "hanging_sheet", "pins": _top_row(curtain)}

    # 3. A pennant hanging from nothing - the name and a vertical face are all there is.
    m = Matrix.Translation((5.5, 0, 1.5)) @ rot_x90
    pennant = _link(sc, "Pennant", _grid(0.4, 0.9, 8, 18, m))
    pennant["ft_truth"] = {"class": "hanging_sheet", "pins": _top_row(pennant)}

    # 4. A tablecloth lying on a table.
    table = _link(sc, "Table", _cylinder(0.5, 0.75, 32), (8.0, 0, 0.375))
    table["ft_truth"] = {"class": "rigid"}
    tc = _link(sc, "Tablecloth", _grid(1.6, 1.6, 24, 24, Matrix.Translation((8.0, 0, 0.755))))
    tc["ft_truth"] = {"class": "loose_sheet", "pins": []}

    # 5. A cape worn by a body with a spine: skinned, top row on the shoulders.
    body = _link(sc, "Body", _cylinder(0.18, 1.6, 24, rings=8), (11.0, 0, 0.8))
    rig = _armature(sc, "BodyRig", [
        ("hips", (0, 0, 0.0), (0, 0, 0.9), None),
        ("chest", (0, 0, 0.9), (0, 0, 1.4), "hips"),
        ("neck", (0, 0, 1.4), (0, 0, 1.6), "chest"),
    ], location=(11.0, 0, 0))
    _skin_by_height(body, rig, [("hips", -1, 0.9), ("chest", 0.9, 1.4), ("neck", 1.4, 9)])
    body["ft_truth"] = {"class": "body"}
    bm = _grid(0.5, 0.9, 10, 18)
    for v in bm.verts:                     # hang down the back, flaring away from it
        t = (0.45 - v.co.y) / 0.9          # 0 at the top row, 1 at the hem
        v.co = Vector((v.co.x, 0.182 + 0.17 * t * t, 1.45 - 0.9 * t))
    cape = _link(sc, "Cape", bm)
    cape.parent = rig                      # at the origin, so the parent puts it on the body
    _skin_by_height(cape, rig, [("chest", -1, 9)])
    cape["ft_truth"] = {"class": "draped_sheet", "pins": _top_row(cape)}

    # 6. A skirt: an open tube round the same kind of body, waist on the hips.
    body2 = _link(sc, "Legs", _cylinder(0.16, 1.0, 24), (14.0, 0, 0.5))
    body2["ft_truth"] = {"class": "body"}
    skirt = _link(sc, "Skirt", _cylinder(0.165, 0.55, 32, caps=False, radius_bottom=0.34, rings=12),
                  (14.0, 0, 0.72))
    skirt["ft_truth"] = {"class": "draped_tube", "pins": _top_row(skirt)}

    # 7. A scarf: a long narrow strip.
    m = Matrix.Translation((17.0, 0, 1.2)) @ rot_x90
    scarf = _link(sc, "Scarf", _grid(0.14, 1.3, 3, 26, m))
    scarf["ft_truth"] = {"class": "strap", "pins": _top_row(scarf)}

    # 8. A solidified sheet: cloth modelled with thickness - closed, but thin.
    bm = _grid(0.9, 0.9, 12, 12, Matrix.Translation((19.5, 0, 1.0)) @ rot_x90)
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.006)
    thick = _link(sc, "ThickBlanket", bm)
    thick["ft_truth"] = {"class": "solid_sheet", "pins": []}

    # 9. Jello: a closed, compact body. Not cloth.
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.3)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=4, use_grid_fill=True)
    jello = _link(sc, "Jello", bm, (22.0, 0, 0.15))
    jello["ft_truth"] = {"class": "volume"}

    # 10. A rock: closed and compact, and nothing about it should move.
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.25)
    rock = _link(sc, "Rock", bm, (24.0, 0, 0.25))
    rock["ft_truth"] = {"class": "volume"}

    sc.view_layers[0].update()          # evaluate matrix_world, or everything sits at the origin
    return sc.name


def score(results):
    """results: {object name: classify() result}. Class hits and pin overlap (IoU)."""
    out = {}
    hits = 0
    total = 0
    for name, res in results.items():
        ob = bpy.data.objects.get(name)
        truth = ob.get("ft_truth") if ob else None
        if not truth:
            continue
        truth = truth.to_dict() if hasattr(truth, "to_dict") else dict(truth)
        got = res.get("class")
        want = truth["class"]
        ok = got == want or (want in ("rigid", "body", "volume") and got in ("volume", "not_cloth"))
        total += 1
        hits += ok
        row = {"want": want, "got": got, "ok": ok}
        if "pins" in truth:
            want_p = set(truth["pins"])
            got_p = set(res.get("pins", {}).get("vertices", []))
            union = want_p | got_p
            row["pin_iou"] = 1.0 if not union else round(len(want_p & got_p) / len(union), 3)
        out[name] = row
    return {"accuracy": f"{hits}/{total}", "rows": out}
