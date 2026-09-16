"""A test quadruped: a dog, built procedurally so `fit.fit_basic_quadruped` has a
shape whose joints are known.

One connected skin, standing as a dog stands, forward -Y, up Z, on the floor at
z = 0: a Labrador-sized body, 0.57 m at the withers and about 1.1 m from nose to
tail tip, on four legs whose paws sit flat on the floor. The legs bend the way a
dog's do and the way Rigify's basic_quadruped models them - the front elbow sits
behind the shoulder and the wrist under it, the rear stifle forward of the hip
and the hock well behind it - so a fitter that bends all four legs alike puts a
joint outside the skin.

Like `hopper_samples`, it is a union of spheres voxel-remeshed
(`hopper_samples._union_mesh`), not metaballs: a union joins only what touches,
so the belly never webs onto the elbows. The voxel is coarse (0.015 m, a leg
about five voxels across) because this body is a fixture's input, and a dense
one only makes bone heat and the playback checks slower without changing where
a joint is.

The tail hangs clear of the floor on purpose. A tail that touched down would be a
midline contact, which `measure.ground_contacts` already discounts, but the
point of this sample is exactly four paired contacts and nothing to argue about.

`truth(name)` gives each leg's joints root -> tip - shoulder or hip, elbow or
stifle, wrist or hock, and the paw's contact on the floor - so a fit is scored in
metres rather than judged by eye. The keys are `front.L`, `front.R`, `rear.L`,
`rear.R`, with L on +X, which is Rigify's .L for a body facing -Y.
"""

from __future__ import annotations

import json

import bpy
from mathutils import Vector

from .hopper_samples import _chain, _mirror, _union_mesh

TRUTH = {}


def _record(obj, truth):
    """Move the known joints with the skin as it was set on the floor, and keep
    them on the object, so they survive a module reload."""
    dz = obj.get("floor_shift", 0.0)
    for k, pts in truth.items():
        truth[k] = [p + Vector((0.0, 0.0, dz)) for p in pts]
    TRUTH[obj.name] = truth
    obj["quadruped_truth"] = json.dumps({k: [list(p) for p in v] for k, v in truth.items()})
    return obj


def truth(name):
    obj = bpy.data.objects[name]
    return {k: [Vector(p) for p in v] for k, v in json.loads(obj["quadruped_truth"]).items()}


def dog(name="DogTest", collection=None, voxel=0.015):
    """A standing dog. Front leg: humerus 0.15, forearm 0.20, metacarpus and paw
    0.08; rear leg: femur 0.17, tibia 0.20, metatarsus 0.12 - in the ratios of a
    medium breed, the hock about a fifth of the way up the leg."""
    truth, spheres = {}, []
    # trunk, rump to chest: (y, z, radius). The chest is deep, the loin narrower.
    trunk = [((0.0, 0.30, 0.47), 0.110), ((0.0, 0.18, 0.46), 0.115), ((0.0, 0.04, 0.46), 0.120),
             ((0.0, -0.10, 0.45), 0.140), ((0.0, -0.22, 0.46), 0.140), ((0.0, -0.30, 0.49), 0.115)]
    spheres += _chain([Vector(c) for c, _ in trunk], [r for _, r in trunk], spacing=0.25)
    # neck up and forward to the skull, then the muzzle
    head = [((0.0, -0.34, 0.54), 0.085), ((0.0, -0.42, 0.64), 0.070), ((0.0, -0.46, 0.68), 0.080),
            ((0.0, -0.55, 0.66), 0.050), ((0.0, -0.63, 0.64), 0.035)]
    spheres += _chain([Vector(c) for c, _ in head], [r for _, r in head], spacing=0.25)
    for sx in (1, -1):                                                   # ears
        spheres += _chain([Vector((sx * 0.050, -0.44, 0.74)), Vector((sx * 0.070, -0.42, 0.66))],
                          [0.025, 0.018])
    # the tail rises off the rump and hangs, its tip 0.28 m above the floor
    tail = [((0.0, 0.40, 0.52), 0.035), ((0.0, 0.52, 0.48), 0.028), ((0.0, 0.60, 0.38), 0.020),
            ((0.0, 0.62, 0.30), 0.014)]
    spheres += _chain([Vector(c) for c, _ in tail], [r for _, r in tail], spacing=0.3)

    # joints root -> tip; the last is the paw's contact point, its sphere resting on z = 0
    fore = [Vector((0.090, -0.26, 0.40)),       # shoulder joint, at the front of the chest
            Vector((0.085, -0.19, 0.265)),      # elbow, behind and below it
            Vector((0.080, -0.21, 0.065)),      # wrist, under the elbow
            Vector((0.080, -0.27, 0.0))]        # paw on the floor, ahead of the wrist
    hind = [Vector((0.090, 0.26, 0.42)),        # hip
            Vector((0.100, 0.16, 0.285)),       # stifle, forward of the hip
            Vector((0.090, 0.30, 0.120)),       # hock, well behind it
            Vector((0.090, 0.27, 0.0))]         # paw
    for rank, pts, radii in (("front", fore, [0.055, 0.042, 0.032, 0.030]),
                             ("rear", hind, [0.070, 0.050, 0.030, 0.030])):
        for side, f in (("L", lambda p: p), ("R", _mirror)):
            joints = [f(p) for p in pts]
            # the paw's sphere sits on the floor: its centre one radius up, the contact under it
            centres = joints[:-1] + [joints[-1] + Vector((0.0, 0.0, radii[-1]))]
            spheres += _chain(centres, radii)
            truth["%s.%s" % (rank, side)] = joints
    return _record(_union_mesh(name, spheres, voxel, collection), truth)


def build_all(collection_name="QuadrupedTests"):
    coll = bpy.data.collections.get(collection_name)
    if coll is None:
        coll = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(coll)
    made = [dog(collection=coll)]
    return {o.name: {"vertices": len(o.data.vertices), "dimensions": [round(x, 4) for x in o.dimensions]}
            for o in made}
