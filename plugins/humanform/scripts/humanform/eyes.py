"""L4 part: eyeballs in an MPFB body's sockets.

    eyes = eyes.add("Mara")                 # "Mara_eyes": two spheres, sclera / iris / pupil, on the head bone
    eyes.add("Mara", iris=(0.46, 0.57, 0.63))    # a screen (sRGB) colour: grey-blue

MPFB2 hides a 72-vertex proxy ball in each socket (vertex groups `helper-l-eye`, `helper-r-eye`)
behind its "Hide helpers" mask. Its centre and radius, read from the evaluated mesh after every
target and the fit, place a clean sphere exactly where the eyelids expect the eye. The iris faces
the body's forward direction; the pupil is a smaller cap inside it. Materials are plain Principled
BSDF from `look` - colours given as sRGB, converted to linear (L6 look development replaces them). The eyes are skinned 100% to the head bone
(`head_bone`: the rig's body profile's head, `spine.005` on the rig humanform builds), or parented to
the body when there is no rig yet.
"""

from __future__ import annotations

import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import body as _body
from . import look

HEAD_BONE = "spine.005"    # scaffold.RENAME["head"], used when no body profile can be read
IRIS_HALF_ANGLE = 32.0     # degrees from the gaze axis: ~11-12 mm across on the ~32 mm MPFB eye proxy
PUPIL_HALF_ANGLE = 14.0


def head_bone(rig):
    """The bone the eyes ride: the head its body profile claims, else `HEAD_BONE`.

    The profile is rig-anything's (`rig["body_profile"]`, set by `scaffold.rig`). humanform does not
    depend on rig-anything, so it is read only when `rig_analysis` is already importable - as it is
    wherever the body goes on to be animated or exported - and nothing else about rig-anything's
    install is assumed. Without it the answer is the same bone, from humanform's own rename table."""
    if rig is not None and rig.get("body_profile"):
        try:
            from rig_analysis import bodymap
        except ImportError:
            bodymap = None
        if bodymap is not None:
            head = ((bodymap.load_profile(rig) or {}).get("roles") or {}).get("head")
            if head:
                return head
    return HEAD_BONE


def _helper_points(human, side):
    g = human.vertex_groups.get(f"helper-{side}-eye")
    if g is None:
        raise ValueError(f"{human.name} has no helper-{side}-eye group (not an MPFB2 body?)")
    b = _body.Body(human)
    idx = [v.index for v in human.data.vertices if any(e.group == g.index for e in v.groups)]
    return b.co_unmasked[idx]


# screen (sRGB) colours, converted by look.material. The iris default is a mid brown; sclera and pupil
# were written as linear values before 0.6 and are kept at the same linear colour.
IRIS = (0.537, 0.437, 0.313)
SCLERA = (0.936, 0.926, 0.906)
PUPIL = (0.100, 0.100, 0.100)


def _uvsphere(bm, **kw):
    """`bmesh.ops.create_uvsphere`, with the sphere's faces in a stable order.

    Blender 5.2's create_uvsphere writes the same vertices in the same order on every run, but its
    faces in a different order in every process, and a body that joins these eyes inherits the shuffle
    (improvements 5.7). The new faces are sorted by their vertex indices; faces already in `bm` keep
    their places."""
    before = set(bm.faces)
    res = bmesh.ops.create_uvsphere(bm, **kw)
    bm.verts.index_update()
    bm.faces.index_update()
    new = sorted((f for f in bm.faces if f not in before), key=lambda f: tuple(v.index for v in f.verts))
    rank = {f: len(before) + i for i, f in enumerate(new)}
    bm.faces.sort(key=lambda f: rank.get(f, f.index))
    bm.faces.index_update()
    return res


def add(human, iris=None, segments=32, rings=16):
    """`iris`: a screen (sRGB) colour, as picked or written in a brief; None for a mid brown."""
    human = _body.obj(human)
    iris = IRIS if iris is None else tuple(iris)
    rig = _body.rig_of(human)
    name = f"{human.name}_eyes"
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)

    bm = bmesh.new()
    report = {}
    forward = Vector((0, -1, 0))
    for side in ("l", "r"):
        pts = _helper_points(human, side)
        centre = pts.mean(axis=0)
        radius = float(np.linalg.norm(pts - centre, axis=1).mean())
        report[side] = {"centre": [round(float(c), 4) for c in centre], "radius": round(radius, 4)}
        before = set(bm.verts)
        _uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius,
                  matrix=Matrix.Translation(Vector(centre)) @ Matrix.Rotation(math.radians(90), 4, "X"))
        new_faces = [f for f in bm.faces if all(v not in before for v in f.verts)]
        for f in new_faces:
            d = (f.calc_center_median() - Vector(centre)).normalized()
            angle = math.degrees(d.angle(forward))
            f.material_index = 2 if angle < PUPIL_HALF_ANGLE else 1 if angle < IRIS_HALF_ANGLE else 0
            f.smooth = True
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for mat in (look.material("HF_sclera", srgb=SCLERA, roughness=0.25),
                look.material(f"HF_iris_{name}", srgb=iris, roughness=0.35),
                look.material("HF_pupil", srgb=PUPIL, roughness=0.2)):
        me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    for coll in human.users_collection:
        coll.objects.link(ob)
    head = head_bone(rig)
    if rig is not None and head in rig.data.bones:
        ob.parent = rig
        vg = ob.vertex_groups.new(name=head)
        vg.add(list(range(len(me.vertices))), 1.0, "REPLACE")
        mod = ob.modifiers.new("Armature", "ARMATURE")
        mod.object = rig
    else:
        ob.parent = human
    report["object"] = name
    return ob, report
