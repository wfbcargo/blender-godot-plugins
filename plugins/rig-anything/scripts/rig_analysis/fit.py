"""Fit Rigify's Basic/basic_human metarig to a measured biped.

Not Pinocchio. That embeds a skeleton into a medial-surface graph by optimising
a penalty function, which is the right answer when nothing is known about the
shape. Here the archetype is already known - phase 1 established that this is a
biped, which way is up and forward, and where the feet, hands, crotch and
shoulders are - so the remaining problem is much smaller: anchor a known
topology to known landmarks.

Landmarks are used wherever they were measured. The reference metarig's own
proportions are used only to place joints that cannot be measured from the
outside, chiefly knees and elbows, which sit inside the limb and leave no
signature on the silhouette.

Read-only with respect to the target mesh: the mesh is never modified, and the
armature is created alongside it.
"""

from __future__ import annotations

import importlib.util
import math
import os

import bpy
from mathutils import Vector

from . import measure

AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}

LEG_BONES = ("thigh", "shin", "foot", "toe", "heel.02")
ARM_BONES = ("shoulder", "upper_arm", "forearm", "hand")


# --------------------------------------------------------------------------
# the reference metarig
# --------------------------------------------------------------------------

def add_basic_human(name="metarig"):
    """Instantiate Rigify's Basic/basic_human, returning the armature object."""
    try:
        import rigify
    except ImportError:
        bpy.ops.preferences.addon_enable(module="rigify")
        import rigify

    path = os.path.join(os.path.dirname(rigify.__file__),
                        "metarigs", "Basic", "basic_human.py")
    if not os.path.exists(path):
        raise RuntimeError("basic_human metarig not found at " + path)

    spec = importlib.util.spec_from_file_location("_basic_human", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    mod.create(ob)
    return ob


def reference_layout(ob):
    """Rest head/tail of every bone, read live rather than hard-coded.

    Reading it from whatever Blender ships keeps this correct if the shipped
    metarig changes, instead of silently fitting to a stale table.
    """
    return {b.name: (b.head_local.copy(), b.tail_local.copy()) for b in ob.data.bones}


# --------------------------------------------------------------------------
# landmarks
# --------------------------------------------------------------------------

def biped_landmarks(obj, analysis=None, topo=None, forward_sign=-1):
    """Reduce the phase-1 analysis to the anchors a biped fit needs.

    `forward_sign` is the one thing geometry cannot settle and the renders can:
    -1 means the character faces the negative forward axis.
    """
    analysis = analysis or measure.analyze(obj.name)
    axes = analysis["axes"]
    up, lat = axes["up_axis"], axes["lateral_axis"]
    fwd = axes["forward_axis"]
    ui, li, fi = AXIS_INDEX[up], AXIS_INDEX[lat], AXIS_INDEX[fwd]

    topo = topo or measure.slab_topology(obj, axis=up, lateral=lat)
    bb = analysis["bbox"]
    ground = bb["min"][ui]
    top = bb["max"][ui]
    height = top - ground
    mid_lat = bb["centre"][li]

    contacts = analysis["ground_contacts"]["clusters"]
    if len(contacts) != 2:
        return {"error": "expected 2 ground contacts for a biped, got %d"
                         % len(contacts)}

    feet = sorted(contacts, key=lambda c: c["position"][li])
    foot_neg = Vector(feet[0]["position"])
    foot_pos = Vector(feet[1]["position"])

    # Hands: the extremities that are far out laterally and below the shoulder,
    # excluding anything near the feet.
    shoulder_z = topo.get("shoulder")
    hands = []
    for p in analysis["extremities"]["points"]:
        v = Vector(p["position"])
        if v[ui] < ground + 0.15 * height:
            continue
        if shoulder_z is not None and v[ui] > shoulder_z:
            continue
        hands.append(v)
    hands.sort(key=lambda v: -abs(v[li] - mid_lat))
    hand_neg = hand_pos = None
    for v in hands:
        if v[li] < mid_lat and hand_neg is None:
            hand_neg = v
        elif v[li] > mid_lat and hand_pos is None:
            hand_pos = v
        if hand_neg is not None and hand_pos is not None:
            break

    head_top = Vector(bb["centre"])
    head_top[ui] = top

    return {
        "up": up, "lateral": lat, "forward": fwd, "forward_sign": forward_sign,
        "ground": ground, "top": top, "height": height, "mid_lateral": mid_lat,
        "crotch": topo.get("crotch"),
        "shoulder": shoulder_z,
        "foot_neg": list(foot_neg), "foot_pos": list(foot_pos),
        "hand_neg": list(hand_neg) if hand_neg else None,
        "hand_pos": list(hand_pos) if hand_pos else None,
        "head_top": list(head_top),
        "complete": all(x is not None for x in
                        (topo.get("crotch"), topo.get("shoulder"), hand_neg, hand_pos)),
    }


# --------------------------------------------------------------------------
# medial snapping
# --------------------------------------------------------------------------

def _medial(obj, point, ui, li, mid_lat, side, band):
    """Pull a joint to the centre of the limb it sits in.

    A joint interpolated along a straight line between two anchors drifts
    outside a limb that curves. Re-centring it on the mesh cross-section at
    that height keeps the bone inside the geometry it has to deform.
    """
    verts = measure.world_verts(obj)
    sel = []
    for p in verts:
        if abs(p[ui] - point[ui]) > band:
            continue
        if side < 0 and p[li] >= mid_lat:
            continue
        if side > 0 and p[li] <= mid_lat:
            continue
        sel.append(p)
    if len(sel) < 4:
        return point
    out = point.copy()
    for i in (0, 1, 2):
        if i == ui:
            continue
        out[i] = sum(p[i] for p in sel) / len(sel)
    return out


# --------------------------------------------------------------------------
# the fit
# --------------------------------------------------------------------------

def fit_basic_human(obj_name, forward_sign=-1, name=None, snap_medial=True):
    """Build a basic_human metarig fitted to `obj_name`. Returns a report."""
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH":
        return {"error": "no mesh named " + repr(obj_name)}

    analysis = measure.analyze(obj_name)
    if analysis["ground_contacts"]["count"] != 2:
        return {"error": "not a biped: %d ground contacts (%s). Fit gated - "
                         "crotch and shoulder are meaningless for this shape."
                         % (analysis["ground_contacts"]["count"],
                            analysis["ground_contacts"]["hint"])}

    lm = biped_landmarks(obj, analysis=analysis, forward_sign=forward_sign)
    if "error" in lm:
        return lm
    if not lm["complete"]:
        return {"error": "incomplete landmarks", "landmarks": lm}

    ui, li, fi = AXIS_INDEX[lm["up"]], AXIS_INDEX[lm["lateral"]], AXIS_INDEX[lm["forward"]]

    rig = add_basic_human(name or (obj_name + "_metarig"))
    ref = reference_layout(rig)

    # --- correspondences between reference heights and measured ones
    ref_ground = min(min(h[ui], t[ui]) for h, t in ref.values())
    ref_top = max(max(h[ui], t[ui]) for h, t in ref.values())
    ref_hip = ref["thigh.L"][0][ui]
    ref_shoulder = ref["shoulder.L"][0][ui]

    # The crotch is deliberately NOT an anchor.
    #
    # It is a real measurement, but it is not the hip joint: the femoral head
    # sits inside the pelvis, above where the legs visibly meet. Anchoring the
    # hip to it dragged the whole leg chain ~7 cm low on a 1.69 m test figure
    # (hip 0.855 against a true 0.920, knee 0.445 against 0.520). Anchoring only
    # on ground, shoulder and top and letting the reference's proportions place
    # the hip predicts 0.949 - about 3 cm out instead of 7. The crotch is used
    # below as a lower bound instead, which still catches a shape whose legs
    # really do start somewhere unusual.
    anchors = sorted([
        (ref_ground, lm["ground"]),
        (ref_shoulder, lm["shoulder"]),
        (ref_top, lm["top"]),
    ])

    def warp_up(z):
        """Piecewise-linear height mapping through the measured anchors."""
        if z <= anchors[0][0]:
            return anchors[0][1] + (z - anchors[0][0])
        for i in range(len(anchors) - 1):
            a, b = anchors[i], anchors[i + 1]
            if a[0] <= z <= b[0]:
                t = (z - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
                return a[1] + t * (b[1] - a[1])
        return anchors[-1][1] + (z - anchors[-1][0])

    ref_leg_x = abs(ref["thigh.L"][0][li])
    tgt_leg_x = abs(Vector(lm["foot_pos"])[li] - lm["mid_lateral"])
    leg_scale = (tgt_leg_x / ref_leg_x) if ref_leg_x > 1e-6 else 1.0

    ref_depth = max(max(h[fi], t[fi]) for h, t in ref.values()) - \
                min(min(h[fi], t[fi]) for h, t in ref.values())
    tgt_depth = analysis["bbox"]["size"][fi]
    depth_scale = (tgt_depth / ref_depth) if ref_depth > 1e-6 else 1.0

    def place(v, lateral_scale):
        out = Vector((0.0, 0.0, 0.0))
        out[ui] = warp_up(v[ui])
        out[li] = lm["mid_lateral"] + (v[li]) * lateral_scale
        out[fi] = analysis["bbox"]["centre"][fi] + v[fi] * depth_scale
        return out

    # --- compute every bone's target, then write them in one edit pass
    targets = {}
    for bname, (h, t) in ref.items():
        base = bname.split(".")[0]
        scale = leg_scale if base in LEG_BONES or base == "heel" else 1.0
        if base in ARM_BONES:
            scale = 1.0
        targets[bname] = [place(h, scale), place(t, scale)]

    # --- snap the chains that WERE measured directly
    for side, foot_key, hand_key in ((-1, "foot_neg", "hand_neg"),
                                     (+1, "foot_pos", "hand_pos")):
        suffix = ".L" if (side > 0) else ".R"
        # Rigify's .L is +lateral in its own space; match by sign, not by label,
        # so a mesh built facing the other way still lands correctly.
        if ref["thigh.L"][0][li] < 0:
            suffix = ".R" if (side > 0) else ".L"

        foot = Vector(lm[foot_key])
        hand = Vector(lm[hand_key])

        # leg: hip at the crotch height on the leg's own axis, ankle above the
        # contact patch, knee at the reference's fraction between them
        # Hip: proportionally placed height, laterally on the leg's own axis,
        # floored at the crotch so it can never end up between the legs.
        hip = targets["thigh" + suffix][0].copy()
        hip[li] = foot[li]
        if hip[ui] < lm["crotch"]:
            hip[ui] = lm["crotch"]

        ankle = targets["foot" + suffix][0].copy()
        ankle[li] = foot[li]

        rh, rt = ref["thigh" + suffix][0], ref["foot" + suffix][0]
        span = (rh[ui] - rt[ui]) or 1.0
        knee_t = (rh[ui] - ref["shin" + suffix][0][ui]) / span
        knee = hip.lerp(ankle, knee_t)
        if snap_medial:
            knee = _medial(obj, knee, ui, li, lm["mid_lateral"], side,
                           0.04 * lm["height"])

        targets["thigh" + suffix] = [hip, knee]
        targets["shin" + suffix] = [knee, ankle]
        toe = targets["toe" + suffix][1].copy()
        toe[li] = foot[li]
        targets["foot" + suffix] = [ankle, Vector(lm[foot_key])]
        targets["toe" + suffix] = [Vector(lm[foot_key]), toe]

        # arm: shoulder at the measured shoulder height, wrist at the measured
        # hand, elbow at the reference's fraction along
        sh_head = targets["shoulder" + suffix][0].copy()
        sh_head[ui] = lm["shoulder"]
        sh_tail = targets["upper_arm" + suffix][0].copy()
        sh_tail[ui] = lm["shoulder"]

        ra, rb, rc = (ref["upper_arm" + suffix][0], ref["forearm" + suffix][0],
                      ref["hand" + suffix][0])
        upper_len = (rb - ra).length
        fore_len = (rc - rb).length
        elbow_t = upper_len / ((upper_len + fore_len) or 1.0)
        elbow = sh_tail.lerp(hand, elbow_t)
        if snap_medial:
            elbow = _medial(obj, elbow, ui, li, lm["mid_lateral"], side,
                            0.03 * lm["height"])

        hand_tail = hand + (hand - elbow).normalized() * (0.06 * lm["height"])
        targets["shoulder" + suffix] = [sh_head, sh_tail]
        targets["upper_arm" + suffix] = [sh_tail, elbow]
        targets["forearm" + suffix] = [elbow, hand]
        targets["hand" + suffix] = [hand, hand_tail]

    _write_edit_bones(rig, targets)

    return {
        "rig": rig.name,
        "target": obj_name,
        "landmarks": lm,
        "bones_placed": len(targets),
        "leg_scale": round(leg_scale, 4),
        "depth_scale": round(depth_scale, 4),
        "height_anchors": [[round(a, 4), round(b, 4)] for a, b in anchors],
    }


def _write_edit_bones(rig, targets):
    prev_mode = bpy.context.object.mode if bpy.context.object else "OBJECT"
    prev_active = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for name, (head, tail) in targets.items():
            eb = rig.data.edit_bones.get(name)
            if eb is None:
                continue
            # Connected bones share a point; setting the parent's tail moves the
            # child's head with it, so write heads last to win ties.
            eb.tail = tail
            eb.head = head
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.objects.active = prev_active
        if prev_active and prev_mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode=prev_mode)
            except Exception:
                pass
