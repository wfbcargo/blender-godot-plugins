"""Build an armature from discovered parts, for any combination of limbs.

`fit.py` anchors a known template to measured landmarks and is the better
answer whenever a template matches - it inherits proportions for joints that
cannot be measured from outside. This builds a skeleton with no template at
all, from whatever `decompose.classify` found, so a worm, a hexapod or a
six-armed statue gets a rig without one existing first.

The vocabulary is the whole design: a spine chain, an optional head and tail
continuing it, and N limbs branching off. A limb is one structure in two roles -
grounded and weight-bearing is a leg, free is an arm - so one code path emits
both, and a wing or a fin comes out correct for nothing extra.

Bone rolls are set deliberately rather than left to Blender's default, so that
every limb in the rig shares a rotation convention. They are still worth
probing with `verify.probe_chain` before authoring motion; that is a rule about
rigs in general, not a doubt about this one.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from . import decompose, measure

AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


def _resample(points, segments):
    """Evenly re-space a polyline by arc length into `segments` bones."""
    pts = [Vector(p) for p in points]
    if len(pts) < 2 or segments < 1:
        return pts[:2] if len(pts) >= 2 else pts

    cum = [0.0]
    for i in range(len(pts) - 1):
        cum.append(cum[-1] + (pts[i + 1] - pts[i]).length)
    total = cum[-1]
    if total <= 1e-9:
        return [pts[0], pts[-1]]

    out = []
    for s in range(segments + 1):
        target = total * s / segments
        j = 0
        while j < len(cum) - 2 and cum[j + 1] < target:
            j += 1
        seg = cum[j + 1] - cum[j]
        t = 0.0 if seg <= 1e-9 else (target - cum[j]) / seg
        out.append(pts[j].lerp(pts[j + 1], t))
    return out


def _segments_for(length, span, lo=1, hi=8, per=0.16):
    if span <= 0:
        return lo
    return max(lo, min(hi, int(round(length / (per * span)))))


def _nearest_index(points, target):
    best, bestd = 0, float("inf")
    for i, p in enumerate(points):
        d = (p - target).length
        if d < bestd:
            best, bestd = i, d
    return best


def build_from_parts(obj_name, parts=None, bands=18, head_at=None,
                     limb_segments=3, name=None, roll_axis=None):
    """Create a deform armature for `obj_name` from its discovered parts."""
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH":
        return {"error": "no mesh named " + repr(obj_name)}

    analysis = measure.analyze(obj_name)
    parts = parts or decompose.classify(obj, analysis=analysis, bands=bands,
                                        head_at=head_at)
    if "error" in parts:
        return parts

    axes = analysis["axes"]
    ui, li, fi = (AXIS_INDEX[axes["up_axis"]], AXIS_INDEX[axes["lateral_axis"]],
                  AXIS_INDEX[axes["forward_axis"]])
    span = parts["graph"]["geodesic_span"] or 1.0
    mid_lat = analysis["bbox"]["centre"][li]

    spine_pts = [Vector(p) for p in parts["spine"]["points"]]
    if len(spine_pts) < 2:
        return {"error": "no usable spine"}

    # Orient the spine so it runs tail -> head, which makes the bone chain read
    # in the same direction as every other rig.
    head_tip = Vector(parts["head"]["tip"]) if parts["head"] else None
    if head_tip is not None and (spine_pts[0] - head_tip).length < (spine_pts[-1] - head_tip).length:
        spine_pts.reverse()

    spine_len = sum((spine_pts[i + 1] - spine_pts[i]).length
                    for i in range(len(spine_pts) - 1))
    n_spine = _segments_for(spine_len, span, lo=2, hi=8)
    spine_nodes = _resample(spine_pts, n_spine)

    bones = []          # (name, head, tail, parent_name, roll_hint)
    for i in range(len(spine_nodes) - 1):
        bones.append((
            "spine" if i == 0 else "spine.%03d" % i,
            spine_nodes[i], spine_nodes[i + 1],
            None if i == 0 else ("spine" if i == 1 else "spine.%03d" % (i - 1)),
            "spine",
        ))
    spine_bone_names = [b[0] for b in bones]

    # head and tail continue the spine at its two ends
    if head_tip is not None and (head_tip - spine_nodes[-1]).length > 1e-4:
        bones.append(("head", spine_nodes[-1], head_tip, spine_bone_names[-1], "spine"))
    tail_tip = Vector(parts["tail"]["tip"]) if parts["tail"] else None
    if tail_tip is not None and (tail_tip - spine_nodes[0]).length > 1e-4:
        tail_pts = _resample([spine_nodes[0], tail_tip],
                             _segments_for((tail_tip - spine_nodes[0]).length, span,
                                           lo=1, hi=4))
        for i in range(len(tail_pts) - 1):
            bones.append((
                "tail" if i == 0 else "tail.%03d" % i,
                tail_pts[i], tail_pts[i + 1],
                spine_bone_names[0] if i == 0 else ("tail" if i == 1 else "tail.%03d" % (i - 1)),
                "spine",
            ))

    # limbs: one code path, role only decides the name
    limbs = [("leg", p) for p in parts["legs"]] + [("arm", p) for p in parts["arms"]]
    # index front-to-back along the spine so names are stable between runs
    limbs.sort(key=lambda kp: (kp[0], -kp[1]["tip"][fi]))

    counters = {}
    limb_report = []
    for role, p in limbs:
        chain_pts = [Vector(parts["spine"]["points"][0])]  # placeholder, replaced below
        pts = _limb_points(parts, p)
        if len(pts) < 2:
            continue
        # make sure the chain ends at the measured tip
        tip = Vector(p["tip"])
        if (pts[-1] - tip).length > 1e-6:
            pts = pts + [tip]

        segs = max(1, min(limb_segments, len(pts) - 1 if len(pts) > 2 else limb_segments))
        joints = _resample(pts, segs)

        side = "L" if (joints[-1][li] - mid_lat) >= 0 else "R"
        counters[(role, side)] = counters.get((role, side), 0) + 1
        idx = counters[(role, side)]
        base = "%s%d" % (role, idx)

        attach = _nearest_index(spine_nodes, joints[0])
        parent = spine_bone_names[min(attach, len(spine_bone_names) - 1)]

        seg_names = _limb_segment_names(base, side, segs)
        for i in range(segs):
            bones.append((seg_names[i], joints[i], joints[i + 1],
                          parent if i == 0 else seg_names[i - 1], "limb"))
        limb_report.append({
            "role": role, "name": base + "." + side, "segments": segs,
            "attached_to": parent, "tip": [round(v, 4) for v in joints[-1]],
            "length": round(sum((joints[i + 1] - joints[i]).length
                                for i in range(segs)), 4),
        })

    rig = _write(obj, bones, name or (obj_name + "_rig"), ui, li, roll_axis)
    rig["body_profile"] = "rig_anything_generic"        # bodymap.load_profile

    return {
        "rig": rig.name,
        "target": obj_name,
        "bones": len(bones),
        "spine_bones": len(spine_bone_names),
        "has_head": head_tip is not None,
        "has_tail": tail_tip is not None,
        "limbs": limb_report,
        "counts": {"legs": len(parts["legs"]), "arms": len(parts["arms"]),
                   "spine": len(spine_bone_names)},
        "summary": parts["summary"],
    }


def _limb_points(parts, p):
    """World positions along one limb chain, root first."""
    pts = p.get("_points")
    if pts:
        return [Vector(x) for x in pts]
    return [Vector(p["root"]), Vector(p["tip"])]


def _limb_segment_names(base, side, segs):
    if segs >= 3:
        names = ["%s_upper.%s" % (base, side), "%s_lower.%s" % (base, side),
                 "%s_tip.%s" % (base, side)]
        names += ["%s_seg%d.%s" % (base, i, side) for i in range(3, segs)]
        return names[:segs]
    if segs == 2:
        return ["%s_upper.%s" % (base, side), "%s_lower.%s" % (base, side)]
    return ["%s.%s" % (base, side)]


def _write(obj, bones, rig_name, ui, li, roll_axis):
    old = bpy.data.objects.get(rig_name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)

    arm = bpy.data.armatures.new(rig_name)
    rig = bpy.data.objects.new(rig_name, arm)
    bpy.context.collection.objects.link(rig)

    view = bpy.context.view_layer
    prev = view.objects.active
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in view.objects:
        o.select_set(False)
    view.objects.active = rig
    rig.select_set(True)

    up = Vector((0.0, 0.0, 0.0))
    up[ui] = 1.0
    lateral = Vector((0.0, 0.0, 0.0))
    lateral[li] = 1.0

    try:
        bpy.ops.object.mode_set(mode="EDIT")
        made = {}
        for name, head, tail, parent, kind in bones:
            if (tail - head).length < 1e-5:
                continue
            eb = arm.edit_bones.new(name)
            eb.head = head
            eb.tail = tail
            made[name] = eb
        for name, head, tail, parent, kind in bones:
            eb = made.get(name)
            if eb is None or parent is None:
                continue
            pb = made.get(parent)
            if pb is None:
                continue
            eb.parent = pb
            eb.use_connect = (pb.tail - eb.head).length < 1e-5
        # A shared roll reference keeps every limb on the same convention
        # instead of whatever Blender picks per bone.
        ref = roll_axis if roll_axis is not None else lateral
        for name, eb in made.items():
            try:
                eb.align_roll(up if name.startswith(("spine", "head", "tail")) else ref)
            except Exception:
                pass
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        view.objects.active = prev

    return rig
