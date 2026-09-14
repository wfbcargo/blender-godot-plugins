"""Test hoppers: a cricket and a rabbit, built procedurally so `hoppers` has
shapes whose joints are known.

Both are one connected skin, sitting as the animal sits, forward -Y, up Z, on
the floor at z = 0:

- the CRICKET (a Gryllus-sized 30 mm body) stands on six legs. Its hind femur is
  swollen with the extensor muscle and angles up and back along the flank; the
  tibia is folded down under it, the tarsus lies along the floor. Every segment
  is visible, so detection can find every joint on the skin.
- the RABBIT (a 0.40 m Oryctolagus) sits on flat hind feet, heel down. Its femur
  is buried in the haunch - no silhouette shows the knee - so detection has to
  infer that joint from proportions, which is the honest case.

They are unions of spheres, voxel-remeshed. The first versions were metaballs,
and a metaball's field reaches 1.75 radii: the rabbit's belly balls pulled webs
of skin down onto its shins and feet across gaps of centimetres, which read as
a rig tearing its skin at 70x whenever a leg moved. A union joins only what
touches.

`truth(name)` gives each leg's joints root -> tip, so a detection is scored in
metres rather than judged by eye.
"""

from __future__ import annotations

import json
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

TRUTH = {}


def _chain(points, radii, spacing=0.3):
    """Spheres along a polyline, radius interpolated per point, spaced at
    `spacing` of the local radius so the union is a smooth tube."""
    out = []
    for (a, ra), (b, rb) in zip(zip(points, radii), zip(points[1:], radii[1:])):
        a, b = Vector(a), Vector(b)
        L = (b - a).length
        s = 0.0
        while s < L:
            t = s / L
            r = ra + (rb - ra) * t
            out.append((a.lerp(b, t), r))
            s += max(spacing * r, 1e-6)
    out.append((Vector(points[-1]), radii[-1]))
    return out


def _mirror(p):
    return Vector((-p[0], p[1], p[2]))


def _union_mesh(name, spheres, voxel, collection=None, smooth=3):
    """One closed skin around a set of (centre, radius) spheres."""
    old = bpy.data.objects.get(name)
    if old is not None:
        me_old = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        if me_old is not None and me_old.users == 0:
            bpy.data.meshes.remove(me_old)
    bm = bmesh.new()
    for c, r in spheres:
        seg = int(max(8, min(24, 2.0 * math.pi * r / (1.5 * voxel))))
        bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(6, seg // 2), radius=r,
                                  matrix=Matrix.Translation(c))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(obj)
    rm = obj.modifiers.new("remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = voxel
    if smooth:
        sm = obj.modifiers.new("smooth", "SMOOTH")
        sm.factor, sm.iterations = 0.5, smooth
    dg = bpy.context.evaluated_depsgraph_get()
    final = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    obj.modifiers.clear()
    obj.data = final
    bpy.data.meshes.remove(me)
    final.name = name
    for p in final.polygons:
        p.use_smooth = True
    low = min(v.co.z for v in final.vertices)
    for v in final.vertices:
        v.co.z -= low
    obj["floor_shift"] = -low
    return obj


def _record(obj, truth):
    """Move the known joints with the skin as it was set on the floor, and keep
    them on the object, so they survive a module reload."""
    dz = obj.get("floor_shift", 0.0)
    for k, pts in truth.items():
        truth[k] = [p + Vector((0.0, 0.0, dz)) for p in pts]
    TRUTH[obj.name] = truth
    obj["hopper_truth"] = json.dumps({k: [list(p) for p in v] for k, v in truth.items()})
    return obj


def truth(name):
    obj = bpy.data.objects[name]
    return {k: [Vector(p) for p in v] for k, v in json.loads(obj["hopper_truth"]).items()}


def cricket(name="CricketTest", collection=None, voxel=0.00022):
    """A field cricket. Hind leg femur 13.2 mm (swollen to 3.5 mm deep), tibia
    11.9, tarsus 4.9; fore and mid legs a quarter of that."""
    mm = 0.001
    truth, spheres = {}, []
    z0 = 4.2 * mm
    # head, pronotum, abdomen: (y, z above the belly line, radius) in mm
    for y, z, r in [(-12.5, 1.2, 2.4), (-9.5, 1.0, 2.7), (-6.0, 0.8, 3.0), (-2.5, 0.6, 3.2), (1.0, 0.6, 3.3),
                    (4.5, 0.7, 3.0), (8.0, 0.9, 2.7), (11.0, 1.1, 2.4), (13.5, 1.2, 1.7)]:
        spheres += _chain([Vector((0.0, y * mm, z0 + z * mm)), Vector((0.0, y * mm + 1.8 * mm, z0 + z * mm))],
                          [r * mm, r * mm])
    small = [0.62 * mm, 0.52 * mm, 0.42 * mm, 0.34 * mm]
    rest = {
        "fore": [(2.0, -8.0, z0 / mm - 0.8), (4.2, -10.5, 4.4), (5.4, -11.0, 0.9), (6.0, -13.5, 0.45)],
        "mid": [(2.4, -2.5, z0 / mm - 1.0), (5.2, -2.0, 4.6), (7.2, -1.0, 0.9), (8.8, 1.0, 0.45)],
    }
    for rank, js in rest.items():
        for side, f in (("L", lambda p: p), ("R", _mirror)):
            pts = [f(Vector(p) * mm) for p in js]
            spheres += _chain(pts, small)
            truth["%s.%s" % (rank, side)] = pts
    # hind: along the flank, splayed ~29 degrees in plan, knee level with the back
    hip = Vector((3.4, 3.0, z0 / mm - 0.6)) * mm
    knee = hip + Vector((6.0, 11.0, 4.2)) * mm                    # 13.2 mm
    ankle = Vector((9.8, 4.2, 0.9)) * mm                          # 11.9 mm from the knee
    toe = ankle + Vector((0.4, 4.9, -0.45)) * mm
    for side, f in (("L", lambda p: p), ("R", _mirror)):
        pts = [f(p) for p in (hip, knee, ankle, toe)]
        # the femur swells a third of the way out, then tapers to the knee
        fem = [pts[0].lerp(pts[1], t) for t in (0.0, 0.3, 0.75, 1.0)]
        spheres += _chain(fem, [1.35 * mm, 1.75 * mm, 1.15 * mm, 0.6 * mm])
        spheres += _chain(pts[1:], [0.42 * mm, 0.36 * mm, 0.3 * mm])
        truth["hind.%s" % side] = pts
    return _record(_union_mesh(name, spheres, voxel, collection), truth)


def rabbit(name="RabbitTest", collection=None, voxel=0.0035):
    """A sitting rabbit, 0.40 m nose to tail. Hind leg femur 0.082 (NZ White,
    82.3 mm), tibia 0.095, metatarsus 0.048, toes 0.028 - the foot flat, heel on
    the floor, the shin rising 45 degrees off it. Forelegs humerus 0.054, forearm
    0.054, paw 0.029, standing near vertical."""
    truth, spheres = {}, []
    body = [((0, 0.175, 0.105), 0.050), ((0, 0.135, 0.120), 0.078), ((0, 0.085, 0.140), 0.085),
            ((0, 0.030, 0.150), 0.080), ((0, -0.025, 0.145), 0.072), ((0, -0.070, 0.135), 0.066),
            ((0, -0.110, 0.140), 0.050), ((0, -0.150, 0.165), 0.052), ((0, -0.190, 0.170), 0.048),
            ((0, -0.222, 0.158), 0.030)]
    spheres += _chain([Vector(c) for c, _ in body], [r for _, r in body], spacing=0.15)
    for sx in (1, -1):
        spheres.append((Vector((sx * 0.038, 0.112, 0.128)), 0.050))      # haunch
        spheres.append((Vector((sx * 0.044, 0.072, 0.108)), 0.030))
        spheres += _chain([Vector((sx * 0.016, -0.170, 0.205)), Vector((sx * 0.024, -0.150, 0.265)),
                           Vector((sx * 0.028, -0.132, 0.310))], [0.013, 0.014, 0.008])   # ears
    spheres.append((Vector((0.0, 0.205, 0.120)), 0.020))                 # tail
    ball = Vector((0.045, 0.085, 0.0075))
    tip = ball + Vector((0.0, -0.028, -0.0005))                          # toes 0.028
    hock = ball + Vector((0.0, 0.048, 0.004))                            # metatarsus 0.048
    knee = hock + Vector((0.004, -0.067, 0.067))                         # tibia 0.095
    hip = knee + Vector((-0.007, 0.050, 0.064))                          # femur 0.082
    for side, f in (("L", lambda p: p), ("R", _mirror)):
        pts = [f(p) for p in (hip, knee, hock, ball, tip)]
        # the femur is inside the haunch; shank and foot show
        spheres += _chain(pts[1:], [0.018, 0.011, 0.010, 0.008])
        truth["hind.%s" % side] = pts
    fore = [Vector(p) for p in ((0.030, -0.068, 0.120), (0.030, -0.074, 0.066), (0.028, -0.080, 0.012),
                                (0.028, -0.108, 0.007), (0.028, -0.122, 0.006))]
    for side, f in (("L", lambda p: p), ("R", _mirror)):
        pts = [f(p) for p in fore]
        spheres += _chain(pts, [0.017, 0.012, 0.009, 0.0085, 0.007])
        truth["fore.%s" % side] = pts
    return _record(_union_mesh(name, spheres, voxel, collection), truth)


def build_all(collection_name="HopperTests"):
    coll = bpy.data.collections.get(collection_name)
    if coll is None:
        coll = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(coll)
    made = [cricket(collection=coll), rabbit(collection=coll)]
    return {o.name: {"vertices": len(o.data.vertices), "dimensions": [round(x, 4) for x in o.dimensions]}
            for o in made}
