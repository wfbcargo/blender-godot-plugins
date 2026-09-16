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
        # the cloth set's props and bodies only have to be recognised as not cloth; which
        # volume class they are is scored by score_volumes and score_flesh
        ok = got == want or (want in ("rigid", "body", "volume") and
                             got in ("volume", "not_cloth", "loose_volume", "mounted_volume", "flesh"))
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


# ------------------------------------------------------------------ bodies with flesh

BODY_SCENE = "FollowThroughBodies"

# torso cross-sections, bottom to top: (z, half width, front depth, back depth)
FIGURE_TORSO = [(0.80, 0.150, 0.085, 0.095), (0.93, 0.170, 0.100, 0.115), (1.08, 0.130, 0.085, 0.090),
                (1.26, 0.155, 0.095, 0.100), (1.38, 0.185, 0.080, 0.085), (1.46, 0.080, 0.060, 0.060)]
BLOATER_TORSO = [(0.80, 0.175, 0.105, 0.110), (0.93, 0.205, 0.125, 0.125), (1.08, 0.215, 0.125, 0.115),
                 (1.26, 0.215, 0.115, 0.110), (1.38, 0.215, 0.090, 0.095), (1.46, 0.090, 0.065, 0.065)]

# bumps: (type, name, z, degrees from front toward the body's left, height m, radius m)
FIGURE_BUMPS = [("breast", "breast.L", 1.25, 26, 0.060, 0.055), ("breast", "breast.R", 1.25, -26, 0.060, 0.055),
                ("butt", "butt.L", 0.89, 150, 0.055, 0.075), ("butt", "butt.R", 0.89, -150, 0.055, 0.075),
                ("belly", "belly", 1.03, 0, 0.035, 0.085)]
BLOATER_BUMPS = [("bloater_belly", "bloater_belly", 1.04, 0, 0.170, 0.260),
                 ("breast", "breast.L", 1.28, 30, 0.045, 0.065), ("breast", "breast.R", 1.28, -30, 0.045, 0.065),
                 ("love_handle", "love_handle.L", 0.99, 95, 0.040, 0.070),
                 ("love_handle", "love_handle.R", 0.99, -95, 0.040, 0.070),
                 ("butt", "butt.L", 0.88, 150, 0.040, 0.075), ("butt", "butt.R", 0.88, -150, 0.040, 0.075)]


def _interp_torso(profile, z):
    if z <= profile[0][0]:
        return profile[0][1:]
    for (z0, *a), (z1, *b) in zip(profile, profile[1:]):
        if z <= z1:
            t = (z - z0) / (z1 - z0)
            t = t * t * (3 - 2 * t)
            return tuple(x + (y - x) * t for x, y in zip(a, b))
    return profile[-1][1:]


def _torso_bm(profile, bumps, rows=72, around=72, power=2.4):
    """A lofted torso: super-ellipse sections, front toward -Y, with Gaussian bumps added
    along the surface normal. Capped at both ends."""
    bm = bmesh.new()
    z_lo, z_hi = profile[0][0], profile[-1][0]
    grid = []
    for i in range(rows + 1):
        z = z_lo + (z_hi - z_lo) * i / rows
        a, bf, bb = _interp_torso(profile, z)
        ring = []
        for j in range(around):
            th = 2 * math.pi * j / around            # 0 = front (-Y), +90 deg = body's left (+X)
            s, c = math.sin(th), math.cos(th)
            b = bf if c >= 0 else bb
            r = 1.0 / ((abs(s) / a) ** power + (abs(c) / b) ** power) ** (1.0 / power)
            p = Vector((s * r, -c * r, z))
            n = Vector((s, -c, 0.0))
            for _kind, _name, bz, deg, h, rad in bumps:
                bth = math.radians(deg)
                bs, bc = math.sin(bth), math.cos(bth)
                bbv = bf if bc >= 0 else bb
                br = 1.0 / ((abs(bs) / a) ** power + (abs(bc) / bbv) ** power) ** (1.0 / power)
                centre = Vector((bs * br, -bc * br, bz))
                d2 = (p - centre).length_squared
                p = p + n * h * math.exp(-d2 / (2 * (rad * 0.55) ** 2))
            ring.append(bm.verts.new(p))
        grid.append(ring)
    for i in range(rows):
        for j in range(around):
            k = (j + 1) % around
            bm.faces.new((grid[i][j], grid[i][k], grid[i + 1][k], grid[i + 1][j]))
    bm.faces.new(list(reversed(grid[0])))
    bm.faces.new(grid[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def _uvsphere(bm, **kw):
    """`bmesh.ops.create_uvsphere`, with the sphere's faces in a stable order.

    Blender 5.2's create_uvsphere writes its faces in a different order in every process (same
    vertices, same face set; improvements 5.7). A sample stored straight from it would differ between
    builds; the new faces are sorted by vertex index, and faces already in `bm` keep their places. A
    body that is voxel remeshed afterwards (`_body`) gets its order from the remesh instead."""
    before = set(bm.faces)
    res = bmesh.ops.create_uvsphere(bm, **kw)
    bm.verts.index_update()
    bm.faces.index_update()
    new = sorted((f for f in bm.faces if f not in before), key=lambda f: tuple(v.index for v in f.verts))
    rank = {f: len(before) + i for i, f in enumerate(new)}
    bm.faces.sort(key=lambda f: rank.get(f, f.index))
    bm.faces.index_update()
    return res


def _capsule_into(bm, a, b, r, segs=20):
    a, b = Vector(a), Vector(b)
    d = b - a
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    m = Matrix.Translation((a + b) / 2) @ rot
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r, depth=d.length, matrix=m)
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=12, radius=r, matrix=Matrix.Translation(a))
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=12, radius=r, matrix=Matrix.Translation(b))


def _ellipsoid_into(bm, c, r):
    m = Matrix.Translation(c) @ Matrix.Diagonal((r[0], r[1], r[2], 1.0))
    bmesh.ops.create_uvsphere(bm, u_segments=28, v_segments=16, radius=1.0, matrix=m)


def _body(sc, name, torso, bumps, limb_scale=1.0, voxel=0.012, location=(0, 0, 0)):
    """A whole body fused into one closed mesh: the lofted torso, then neck, head and limbs
    as capsules, voxel remeshed so they join, and smoothed so the joins blend."""
    bm = _torso_bm(torso, bumps)
    k = limb_scale
    top = torso[-1][0]
    _capsule_into(bm, (0, 0, top - 0.04), (0, 0, top + 0.07), 0.055 * k)
    _ellipsoid_into(bm, (0, -0.01, top + 0.19), (0.09, 0.105, 0.12))
    shoulder_z = torso[-2][0]
    half = torso[-2][1]
    for s in (1, -1):
        hip = (s * 0.085 * k, 0.0, torso[0][0] + 0.07)
        knee = (s * 0.105 * k, -0.005, 0.47)
        ankle = (s * 0.115 * k, 0.0, 0.08)
        _capsule_into(bm, hip, knee, 0.078 * k)
        _capsule_into(bm, knee, ankle, 0.05 * k)
        _capsule_into(bm, (ankle[0], 0.02, 0.04), (ankle[0], -0.14, 0.035), 0.036 * k)
        sh = (s * (half - 0.02), 0.0, shoulder_z)
        elbow = (s * (half + 0.2), 0.0, shoulder_z - 0.18)
        wrist = (s * (half + 0.36), 0.0, shoulder_z - 0.36)
        _capsule_into(bm, sh, elbow, 0.048 * k)
        _capsule_into(bm, elbow, wrist, 0.038 * k)
        _ellipsoid_into(bm, (wrist[0] + s * 0.04, 0.0, wrist[2] - 0.05), (0.03, 0.045, 0.06))
    me = bpy.data.meshes.new(name + "_parts")
    bm.to_mesh(me)
    bm.free()
    tmp = bpy.data.objects.new(name + "_parts", me)
    sc.collection.objects.link(tmp)
    rm = tmp.modifiers.new("remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = voxel
    sm = tmp.modifiers.new("smooth", "SMOOTH")
    sm.factor = 0.8
    sm.iterations = 6
    sc.view_layers[0].update()
    out = bpy.data.meshes.new_from_object(tmp.evaluated_get(sc.view_layers[0].depsgraph))
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.meshes.remove(me)
    for p in out.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, out)
    ob.location = location
    sc.collection.objects.link(ob)
    sc.view_layers[0].update()
    truth = []
    for kind, bname, z, deg, h, rad in bumps:
        a, bf, bb = _interp_torso(torso, z)
        th = math.radians(deg)
        s, c = math.sin(th), math.cos(th)
        b = bf if c >= 0 else bb
        r = 1.0 / ((abs(s) / a) ** 2.4 + (abs(c) / b) ** 2.4) ** (1.0 / 2.4) + h
        truth.append({"type": kind, "name": bname, "radius": rad,
                      "centre": [s * r + location[0], -c * r + location[1], z + location[2]]})
    ob["ft_truth"] = {"class": "flesh", "regions": truth}
    return ob


def build_bodies(rig=True, walk=True, rig_anything=None):
    """Two bodies with known soft masses: `Figure` (breasts, buttocks, a small belly) and
    `Bloater` (a swollen belly, moobs, love handles). With `rig`, each is rigged with
    rig-anything's basic_human fitter and bound; with `walk`, given rig-anything's
    contact-locomotion walk. Returns the scene name and what was made.

    rig-anything is found at `rig_anything` (its scripts folder) or beside this plugin."""
    sc = bpy.data.scenes.get(BODY_SCENE)
    if sc is not None:
        _clear(sc)
    else:
        sc = bpy.data.scenes.new(BODY_SCENE)
    made = {"scene": sc.name, "bodies": {}}
    # both at the origin, overlapping: rig-anything refuses to export a rig off origin,
    # because in Godot the model would orbit the node instead of walking with it
    for name, torso, bumps, k, x in (("Figure", FIGURE_TORSO, FIGURE_BUMPS, 1.0, 0.0),
                                     ("Bloater", BLOATER_TORSO, BLOATER_BUMPS, 1.2, 0.0)):
        ob = _body(sc, name, torso, bumps, limb_scale=k, location=(x, 0, 0))
        made["bodies"][name] = {"vertices": len(ob.data.vertices)}
    if not rig:
        return made
    ra = _rig_anything(rig_anything)
    win = bpy.context.window
    prev = win.scene
    win.scene = sc
    try:
        for name in made["bodies"]:
            res = ra.fit.fit_basic_human(name, forward_sign=-1)
            bind = ra.skin.bind(name, res["rig"])
            made["bodies"][name].update(rig=res["rig"], coverage=bind.get("coverage"))
            if walk:
                from rig_analysis import locomotion as lm
                r = lm.cycle(res["rig"], froude="walk", action_name=name + "Walk")
                made["bodies"][name]["walk"] = {k: r[k] for k in ("action", "speed_mps", "frames") if k in r}
                # the whole report, for rig-anything's export_character (its gaits and contacts)
                made["bodies"][name]["walk_report"] = r
    finally:
        win.scene = prev
    return made


def export_bodies(out_dir, rig_anything=None):
    """Build, rig, walk, flesh and export both sample bodies - the demo's assets, from scratch.

    Each body goes out through rig-anything's export (which verifies the walk's duration
    and writes <name>.rig.json with its speed), then is read back by export.verify, which
    checks every jiggle bone is in the skin where the spec puts it."""
    import os
    from . import export, flesh
    made = build_bodies(rig=True, walk=True, rig_anything=rig_anything)
    ra = _rig_anything(rig_anything)
    from rig_analysis import export as rx
    win = bpy.context.window
    prev = win.scene
    win.scene = bpy.data.scenes[made["scene"]]
    out = {}
    try:
        for name in made["bodies"]:
            rep = flesh.prepare(name)
            path = os.path.join(out_dir, name.lower() + ".glb")
            m = rx.export(name, name + "_metarig", path, foot_bones=["foot.L", "foot.R"],
                          actions=[name + "Walk"], loop_clips=[name + "Walk"], forward="-Y")
            out[name] = {"regions": len(rep.get("regions", [])), "exported": m.get("exported"),
                         "durations_match": m.get("verified", {}).get("durations_match"),
                         "read_back": export.verify(path, expect_meshes=[name])["passed"] if m.get("exported") else False}
    finally:
        win.scene = prev
    return out


def _clear(sc):
    for o in list(sc.objects):
        data = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Armature):
                bpy.data.armatures.remove(data)


def _rig_anything(path=None):
    import importlib
    import os
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [path] if path else []
    candidates += [os.path.normpath(os.path.join(here, "..", "..", "..", "rig-anything", "scripts")),
                   os.path.join(os.path.expanduser("~"), ".claude", "skills", "rig-anything", "scripts")]
    for c in candidates:
        if c and os.path.isdir(os.path.join(c, "rig_analysis")):
            if c not in sys.path:
                sys.path.insert(0, c)
            import rig_analysis
            importlib.reload(rig_analysis)
            rig_analysis.reload_all()
            from rig_analysis import fit, skin
            rig_analysis.fit, rig_analysis.skin = fit, skin
            return rig_analysis
    raise RuntimeError("rig-anything not found: pass rig_anything=<its scripts folder>")


def score_flesh(found, obj_name=None, tolerance=0.12):
    """Compare flesh.find_regions output with a sample body's truth: each true mass should be
    found as a region of its type whose jiggle bone tail lies within `tolerance` m of the
    mass's peak, or 60% of the mass's radius if that is larger. Returns hits, misses,
    extras and the distance for each."""
    ob = bpy.data.objects[obj_name or found["object"]]
    truth = ob["ft_truth"].to_dict() if hasattr(ob["ft_truth"], "to_dict") else dict(ob["ft_truth"])
    rows = []
    used = set()
    for t in truth["regions"]:
        want = Vector(t["centre"])
        best = None
        for r in found["regions"]:
            if r["name"] in used:
                continue
            d = (Vector(tuple(r["tail"])) - want).length
            if best is None or d < best[0]:
                best = (d, r)
        limit = max(tolerance, 0.6 * t.get("radius", 0.0))
        ok = best is not None and best[0] <= limit and best[1]["type"] == t["type"]
        if ok:
            used.add(best[1]["name"])
        rows.append({"want": t["name"], "type": t["type"], "got": best[1]["name"] if best else None,
                     "got_type": best[1]["type"] if best else None,
                     "distance_m": round(best[0], 3) if best else None, "ok": ok})
    extras = [r["name"] for r in found["regions"] if r["name"] not in used]
    hits = sum(r["ok"] for r in rows)
    return {"object": ob.name, "found": f"{hits}/{len(rows)}", "rows": rows, "extras": extras}


# ------------------------------------------------------------------ volumes

VOLUME_SCENE = "FollowThroughVolumes"


def _mold(radius, height, flutes=8, depth=0.12, segments=48, rings=10):
    """A turned-out jelly mould: a fluted, tapering drum with a rounded top."""
    bm = bmesh.new()
    rows = []
    for r in range(rings + 1):
        t = r / rings
        z = height * t
        taper = 1.0 - 0.35 * t * t
        row = []
        for j in range(segments):
            th = 2 * math.pi * j / segments
            rad = radius * taper * (1.0 + depth * 0.5 * math.cos(flutes * th))
            row.append(bm.verts.new((rad * math.cos(th), rad * math.sin(th), z)))
        rows.append(row)
    for a, b in zip(rows, rows[1:]):
        for j in range(segments):
            k = (j + 1) % segments
            bm.faces.new((a[j], a[k], b[k], b[j]))
    bottom = bm.verts.new((0, 0, 0))
    top = bm.verts.new((0, 0, height * 1.05))
    for j in range(segments):
        k = (j + 1) % segments
        bm.faces.new((rows[0][k], rows[0][j], bottom))
        bm.faces.new((rows[-1][j], rows[-1][k], top))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def _blob(radius, squash_z=0.55, seed=3, detail=3):
    import random
    rnd = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=detail, radius=radius)
    bumps = [(Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))).normalized(), rnd.uniform(0.05, 0.15))
             for _ in range(5)]
    for v in bm.verts:
        n = v.co.normalized()
        k = 1.0 + sum(a * max(0.0, n.dot(d)) ** 3 for d, a in bumps)
        v.co = Vector((v.co.x * k, v.co.y * k, v.co.z * k * squash_z))
    lo = min(v.co.z for v in bm.verts)
    for v in bm.verts:
        v.co.z -= lo
    return bm


def build_volumes(variant=0, scene_name=None):
    """Volumes with known classes and types, in their own scene.

    variant 0 is the named set. variant 1 is a second set - each thing scaled and shaped a
    little differently, and named Thing01.. so no name can help - for testing whether
    teaching from the first set lets the second be typed."""
    sc_name = scene_name or (VOLUME_SCENE if variant == 0 else f"{VOLUME_SCENE}{variant}")
    sc = bpy.data.scenes.get(sc_name)
    if sc is not None:
        _clear(sc)
    else:
        sc = bpy.data.scenes.new(sc_name)
    k = 1.0 if variant == 0 else 1.15
    names = iter(f"Thing{i:02d}" for i in range(1, 50))

    def nm(name):
        return name if variant == 0 else next(names)

    def put(name, bm, loc, truth):
        ob = _link(sc, name, bm, loc)
        for p in ob.data.polygons:
            p.use_smooth = True
        if truth:
            ob["ft_truth"] = truth
        return ob

    floor = bmesh.new()
    bmesh.ops.create_cube(floor, size=1.0)
    bmesh.ops.scale(floor, vec=(5.6, 2.0, 0.1), verts=floor.verts)
    put("Floor", floor, (2.3, 0, -0.05), {"class": "rigid"})

    plate = _cylinder(0.2 * k, 0.02, 32)
    put(nm("Plate"), plate, (0.0, 0, 0.01), {"class": "rigid"})
    put(nm("Jello"), _mold(0.1 * k, 0.12 * k, flutes=8 if variant == 0 else 6), (0.0, 0, 0.02),
        {"class": "mounted_volume", "type": "jello"})

    cube = bmesh.new()
    bmesh.ops.create_cube(cube, size=0.12 * k)
    bmesh.ops.subdivide_edges(cube, edges=cube.edges[:], cuts=5, use_grid_fill=True)
    put(nm("JelloCube"), cube, (0.6, 0, 0.45), {"class": "loose_volume", "type": "jello"})

    ramp = bmesh.new()
    bmesh.ops.create_cube(ramp, size=1.0)
    bmesh.ops.scale(ramp, vec=(1.2, 0.5, 0.01), verts=ramp.verts)   # thin: a thick ramp's end is a step a rolling ball wedges against
    rob = put("Ramp", ramp, (1.3, 0, 0.2), {"class": "rigid"})
    rob.rotation_euler = (0, math.radians(15), 0)
    ball = bmesh.new()
    _uvsphere(ball, u_segments=32, v_segments=16, radius=0.08 * k)
    sc.view_layers[0].update()
    top = rob.matrix_world @ Vector((-0.5, 0, 0.5))
    put(nm("ClayBall"), ball, (top.x + 0.08, 0, top.z + 0.08 * k + 0.004), {"class": "loose_volume", "type": "clay_ball"})

    put(nm("SlimeBlob"), _blob(0.14 * k, seed=3 + variant), (2.3, 0, 0.0), {"class": "loose_volume", "type": "slime"})

    balloon = bmesh.new()
    _uvsphere(balloon, u_segments=32, v_segments=16, radius=0.11 * k)
    for v in balloon.verts:
        v.co.z = v.co.z * (1.15 if v.co.z > 0 else 0.9) + 0.11 * k * 0.9
    put(nm("WaterBalloon"), balloon, (2.9, 0, 0.0), {"class": "loose_volume", "type": "water_balloon"})

    plate2 = _cylinder(0.16 * k, 0.02, 32)
    put(nm("Saucer"), plate2, (3.9, 0, 0.01), {"class": "rigid"})
    flan = _cylinder(0.1 * k, 0.09 * k, 32, radius_bottom=0.12 * k, rings=4)
    put(nm("Pudding"), flan, (3.9, 0, 0.02 + 0.045 * k), {"class": "mounted_volume", "type": "pudding"})

    rock = _blob(0.12 * k, squash_z=0.8, seed=11 + variant, detail=2)
    for v in rock.verts:       # facets: rocks are angular
        v.co = Vector((round(v.co.x / 0.03) * 0.03, round(v.co.y / 0.03) * 0.03, round(v.co.z / 0.03) * 0.03)) * 0.5 + v.co * 0.5
    put(nm("Rock"), rock, (4.7, 0, 0.0), {"class": "loose_volume", "type": "rock"})

    sc.view_layers[0].update()
    return sc.name


def score_volumes(scene_name=VOLUME_SCENE):
    """Classify every volume sample in a scene; class and type accuracy against truth."""
    from . import classify
    sc = bpy.data.scenes[scene_name]
    rows = {}
    cls_ok = type_ok = total = 0
    for ob in sc.objects:
        truth = ob.get("ft_truth")
        if ob.type != "MESH" or not truth or truth.get("class") == "rigid":
            continue
        truth = truth.to_dict() if hasattr(truth, "to_dict") else dict(truth)
        r = classify.classify(ob.name)
        c = r["class"] == truth["class"]
        t = r.get("type") == truth.get("type")
        rows[ob.name] = {"want": f"{truth['class']}/{truth.get('type')}", "got": f"{r['class']}/{r.get('type')}",
                         "class_ok": c, "type_ok": t, "type_evidence": r.get("type_evidence", [])}
        cls_ok += c
        type_ok += t
        total += 1
    return {"scene": scene_name, "class": f"{cls_ok}/{total}", "type": f"{type_ok}/{total}", "rows": rows}
