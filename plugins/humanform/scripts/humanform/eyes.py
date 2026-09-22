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


SLOTS = ("sclera", "iris", "limbal", "pupil")   # material slot order on the eye mesh


def _slot_for_angle(deg):
    """The fallback split, used only when lookdev is not importable: no limbal ring."""
    return "pupil" if deg < PUPIL_HALF_ANGLE else "iris" if deg < IRIS_HALF_ANGLE else "sclera"


def _materials(name, iris):
    """The four eye materials and the angle split that goes with them.

    lookdev's `eye` preset owns both: it carries the cornea coat Godot needs (glTF has no clearcoat),
    the limbal ring, and the rule that keeps a dark iris above its pupil. Without lookdev the eye falls
    back to flat colours and no ring, the way brows and lashes do.

    Returns (materials by slot, slot_for_angle, report)."""
    names = {"sclera": "HF_sclera", "iris": f"HF_iris_{name}",
             "limbal": f"HF_limbal_{name}", "pupil": "HF_pupil"}
    try:
        from lookdev_blender import eyes as ld_eyes
    except ImportError:
        ld_eyes = None
    if ld_eyes is None:
        dark = tuple(c * 0.35 for c in (iris or IRIS))
        mats = {"sclera": look.material(names["sclera"], srgb=SCLERA, roughness=0.25),
                "iris": look.material(names["iris"], srgb=iris, roughness=0.35),
                "limbal": look.material(names["limbal"], srgb=dark, roughness=0.3),
                "pupil": look.material(names["pupil"], srgb=PUPIL, roughness=0.2)}
        return mats, _slot_for_angle, {"source": "flat (lookdev_blender not importable)"}
    mats, rep = ld_eyes.materials(iris_srgb=iris, names=names)
    return mats, (lambda deg: ld_eyes.slot_for_angle(deg)), dict(rep, source="lookdev")


def add(human, iris=None, segments=32, rings=32, places=None):
    """`iris`: a screen (sRGB) colour, as picked or written in a brief; None for a mid brown. `places`: eyes at
    [(centre, radius)] instead of in MPFB's two sockets (humanform.eye_layout: one eye, three, ...), each named
    `e<i>` in the report; None is the human pair from the helpers, exactly as before.

    `rings` was 16 until the eye preset: at that height the whole iris was 2 rings of faces and the
    pupil 1, which is what every benchmark critic saw as "a faceted iris polygon" and a pupil with
    "blocky edges", and the preset's 3.5 degree limbal band fell between two rings and got no faces at
    all (faces near the edge sat at 16.8, 28.0 and 39.2 degrees). 32 is the first count that resolves
    the band; past it the band still catches one ring, so it buys nothing. Measured on the
    pipeline_woman fixture the pair costs 1024 more vertices (17241 -> 18265), about 2048 triangles,
    against a 30000 budget."""
    human = _body.obj(human)
    iris = IRIS if iris is None else tuple(iris)
    rig = _body.rig_of(human)
    name = f"{human.name}_eyes"
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)

    eye_mats, slot_for, mat_report = _materials(name, iris)

    bm = bmesh.new()
    report = {"materials": mat_report}
    forward = Vector((0, -1, 0))
    if places is None:
        where = []
        for side in ("l", "r"):
            pts = _helper_points(human, side)
            centre = pts.mean(axis=0)
            where.append((side, centre, float(np.linalg.norm(pts - centre, axis=1).mean())))
    else:
        where = [(f"e{i}", np.asarray(c, np.float64), float(r)) for i, (c, r) in enumerate(places)]
    for side, centre, radius in where:
        report[side] = {"centre": [round(float(c), 4) for c in centre], "radius": round(radius, 4)}
        before = set(bm.verts)
        _uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius,
                  matrix=Matrix.Translation(Vector(centre)) @ Matrix.Rotation(math.radians(90), 4, "X"))
        new_faces = [f for f in bm.faces if all(v not in before for v in f.verts)]
        for f in new_faces:
            d = (f.calc_center_median() - Vector(centre)).normalized()
            angle = math.degrees(d.angle(forward))
            f.material_index = SLOTS.index(slot_for(angle))
            f.smooth = True
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for slot in SLOTS:
        me.materials.append(eye_mats[slot])
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
