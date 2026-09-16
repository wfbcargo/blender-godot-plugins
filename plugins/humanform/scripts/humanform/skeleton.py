"""L1 -> rig: a deform skeleton placed exactly on a landmark set, named the way the other plugins read.

    rig = skeleton.build(lm, "Mara")      # armature object "Mara_rig", linked to the scene
    skeleton.BONES                        # (name, head landmark, tail landmark, parent)

The names are rig-anything's (spine .. spine.005, shoulder / upper_arm / forearm / hand,
thigh / shin / foot / toe, .L and .R) - the layout Nora's rig proved with wardrobe,
follow-through and animate-anything. Joints are placed from landmarks, never fitted to a mesh:
the fitter put Belle's shoulders 19 cm low. Fingers come with the base mesh's rig (Phase 3).
The landmark set is stored on the rig as the custom property `humanform_landmarks` (JSON).
"""

from __future__ import annotations

import json

import bpy
from mathutils import Vector

BONES = [
    ("spine", "pelvis", "iliac_crest", None),
    ("spine.001", "iliac_crest", "tenth_rib", "spine"),
    ("spine.002", "tenth_rib", "chest", "spine.001"),
    ("spine.003", "chest", "neck_base", "spine.002"),
    ("spine.004", "neck_base", "head_base", "spine.003"),
    ("spine.005", "head_base", "vertex", "spine.004"),
]
for _s in ("L", "R"):
    BONES += [
        (f"shoulder.{_s}", f"clavicle.{_s}", f"shoulder.{_s}", "spine.003"),
        (f"upper_arm.{_s}", f"shoulder.{_s}", f"elbow.{_s}", f"shoulder.{_s}"),
        (f"forearm.{_s}", f"elbow.{_s}", f"wrist.{_s}", f"upper_arm.{_s}"),
        (f"hand.{_s}", f"wrist.{_s}", f"fingertip.{_s}", f"forearm.{_s}"),
        (f"thigh.{_s}", f"hip.{_s}", f"knee.{_s}", "spine"),
        (f"shin.{_s}", f"knee.{_s}", f"ankle.{_s}", f"thigh.{_s}"),
        (f"foot.{_s}", f"ankle.{_s}", f"ball.{_s}", f"shin.{_s}"),
        (f"toe.{_s}", f"ball.{_s}", f"toe.{_s}", f"foot.{_s}"),
    ]


def build(lm, name, collection=None):
    rig_name = f"{name}_rig"
    old = bpy.data.objects.get(rig_name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    arm = bpy.data.armatures.new(rig_name)
    ob = bpy.data.objects.new(rig_name, arm)
    (collection or bpy.context.scene.collection).objects.link(ob)
    P = {k: Vector(p) for k, p in lm["points"].items()}

    vl = bpy.context.view_layer
    prev_active = vl.objects.active
    vl.update()
    vl.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for bname, head, tail, parent in BONES:
            eb = arm.edit_bones.new(bname)
            eb.head, eb.tail = P[head], P[tail]
            eb.roll = 0.0
            if parent:
                eb.parent = arm.edit_bones[parent]
                eb.use_connect = (eb.head - arm.edit_bones[parent].tail).length < 1e-5
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        if prev_active is not None:
            vl.objects.active = prev_active
    for pb in ob.pose.bones:
        pb.rotation_mode = "QUATERNION"
    ob["humanform_landmarks"] = json.dumps(lm)
    return ob


def read_landmarks(rig):
    raw = rig.get("humanform_landmarks")
    return json.loads(raw) if raw else None
