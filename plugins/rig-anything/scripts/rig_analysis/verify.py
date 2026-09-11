"""Verification harness for generated rigs and clips.

This exists because generated animation fails *quietly*. A clip with a wrong
rotation sign still plays; a foot 6 mm through the floor still renders; a
skeleton offset from its own origin still animates, and simply orbits. Every
check here turns one of those into a number you can assert on.

Nothing in this module writes keyframes. `probe_bone_axis` temporarily poses the
rig to take a measurement and always restores the pose it found.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Euler, Vector

AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


# --------------------------------------------------------------------------
# pose helpers
# --------------------------------------------------------------------------

def _snapshot(rig):
    return {
        pb.name: (tuple(pb.rotation_quaternion), tuple(pb.location),
                  tuple(pb.rotation_euler), pb.rotation_mode)
        for pb in rig.pose.bones
    }


def _restore(rig, snap):
    for pb in rig.pose.bones:
        q, loc, eul, mode = snap[pb.name]
        pb.rotation_mode = mode
        pb.rotation_quaternion = q
        pb.location = loc
        pb.rotation_euler = eul
    bpy.context.view_layer.update()


def clear_pose(rig):
    for pb in rig.pose.bones:
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()


def repair_evaluation(rig):
    """Force the depsgraph to rebuild this armature's pose evaluation.

    An armature can get into a state where assigning rotation_quaternion
    updates matrix_basis but the posed tail never moves - view_layer.update(),
    update_tag, an explicit depsgraph update and frame_set all return stale
    values.

    Entering and leaving POSE mode is the step that actually rebuilds it.
    Bouncing pose_position REST/POSE looks like it should be equivalent and is
    not: measured on a freshly fitted rig, the pose_position bounce left the
    observed tip moving 0.0000 while the mode bounce moved it 0.2942. Both are
    attempted, cheapest first.
    """
    view = bpy.context.view_layer
    prev_active = view.objects.active
    prev_selected = [o for o in view.objects if o.select_get()]
    try:
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        view.objects.active = rig
        rig.data.pose_position = "POSE"
        rig.update_tag()
        view.update()

        for o in view.objects:
            o.select_set(False)
        rig.select_set(True)
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass
    finally:
        try:
            for o in view.objects:
                o.select_set(False)
            for o in prev_selected:
                o.select_set(True)
            view.objects.active = prev_active
        except Exception:
            pass


def poses_respond(rig, bone_name, watch, degrees=45.0):
    """Does posing `bone_name` actually move `watch`?

    Guards against the silent failure above, where every measurement comes back
    as zero and the caller happily derives a complete, confident and totally
    fictional axis table from it.
    """
    snap = _snapshot(rig)
    try:
        clear_pose(rig)
        base = bone_tip(rig, watch).copy()
        pb = rig.pose.bones[bone_name]
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = Euler(
            (math.radians(degrees), 0.0, 0.0), "XYZ").to_quaternion()
        bpy.context.view_layer.update()
        moved = (bone_tip(rig, watch) - base).length
        if moved <= 1e-6:
            # try the other two axes before declaring it dead: the test axis
            # might genuinely be the bone's roll axis for a tip-only chain
            for idx in (1, 2):
                clear_pose(rig)
                e = [0.0, 0.0, 0.0]
                e[idx] = math.radians(degrees)
                pb.rotation_quaternion = Euler(e, "XYZ").to_quaternion()
                bpy.context.view_layer.update()
                moved = max(moved, (bone_tip(rig, watch) - base).length)
        return moved > 1e-6
    finally:
        _restore(rig, snap)


def bone_tip(rig, bone_name):
    return rig.matrix_world @ rig.pose.bones[bone_name].tail


def bone_head(rig, bone_name):
    return rig.matrix_world @ rig.pose.bones[bone_name].head


# --------------------------------------------------------------------------
# THE axis probe
# --------------------------------------------------------------------------

def probe_bone_axis(rig_name, bone_name, degrees=30.0, forward="-Y", up="Z",
                    observe=None):
    """Rotate one bone about each local axis and report where its tip actually goes.

    Bone roll varies per rig, per limb and per asset, so the mapping from a
    local rotation to a visible motion cannot be assumed - not even between two
    bones in the same chain. A knee bends backward and an elbow bends forward;
    assuming the elbow followed the knee is exactly the bug this function
    exists to prevent.

    `observe` is the bone whose tip is watched, defaulting to `bone_name`. For a
    chain, watch the end effector (e.g. rotate "Thigh.L", observe "Foot.L").
    """
    rig = bpy.data.objects.get(rig_name)
    if rig is None or rig.type != "ARMATURE":
        return {"error": "no armature named " + repr(rig_name)}
    if bone_name not in rig.pose.bones:
        return {"error": "no bone " + repr(bone_name)}
    watch = observe or bone_name
    if watch not in rig.pose.bones:
        return {"error": "no observed bone " + repr(watch)}

    fsign = -1.0 if forward.startswith("-") else 1.0
    fidx = AXIS_INDEX[forward[-1].upper()]
    uidx = AXIS_INDEX[up[-1].upper()]

    snap = _snapshot(rig)
    prev_modes = {pb.name: pb.rotation_mode for pb in rig.pose.bones}
    try:
        # Never measure a rig that is not responding. A stale pose evaluation
        # yields zero for every axis, from which a caller would derive a
        # complete and entirely fictional table of rotation signs.
        if not poses_respond(rig, bone_name, watch):
            repair_evaluation(rig)
            if not poses_respond(rig, bone_name, watch):
                return {
                    "error": "pose evaluation is stale for " + rig_name
                    + ": rotating " + bone_name + " does not move " + watch
                    + " on any axis, even after a depsgraph repair. Measurements "
                    "would all read zero, so no axes are reported.",
                    "rig": rig_name,
                    "bone": bone_name,
                    "observed": watch,
                }

        clear_pose(rig)
        base = bone_tip(rig, watch).copy()

        results = {}
        for axis, idx in AXIS_INDEX.items():
            clear_pose(rig)
            pb = rig.pose.bones[bone_name]
            e = [0.0, 0.0, 0.0]
            e[idx] = math.radians(degrees)
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = Euler(e, "XYZ").to_quaternion()
            bpy.context.view_layer.update()

            d = bone_tip(rig, watch) - base
            forward_component = d[fidx] * fsign
            up_component = d[uidx]
            # Thresholds are relative to how far the tip actually travelled, so
            # the same rule works on a 2 cm prop and a 20 m creature.
            mag = d.length
            cut = 0.3 * mag
            if mag < 1e-5:
                verdict = "no movement"
            elif abs(forward_component) >= cut and abs(forward_component) >= abs(up_component):
                verdict = "forward" if forward_component > 0 else "backward"
            elif abs(up_component) >= cut:
                verdict = "up" if up_component > 0 else "down"
            else:
                verdict = "sideways (roll/twist)"

            results[axis] = {
                "delta": [round(v, 4) for v in d],
                "magnitude": round(mag, 4),
                "forward_component": round(forward_component, 4),
                "up_component": round(up_component, 4),
                "moves": verdict,
            }

        swing = max(results, key=lambda a: abs(results[a]["forward_component"]))
        fc = results[swing]["forward_component"]
        return {
            "rig": rig_name,
            "bone": bone_name,
            "observed": watch,
            "degrees": degrees,
            "forward": forward,
            "axes": results,
            "swing_axis": swing,
            "forward_sign": ("+" if fc > 0 else "-") + swing,
            "summary": (
                "rotating " + bone_name + " by +" + str(degrees) + " about local "
                + swing + " moves " + watch + " "
                + results[swing]["moves"]
                + " => use " + ("positive" if fc > 0 else "negative")
                + " " + swing + " for forward"
            ),
        }
    finally:
        _restore(rig, snap)
        for pb in rig.pose.bones:
            pb.rotation_mode = prev_modes[pb.name]
        bpy.context.view_layer.update()


def probe_chain(rig_name, bones, forward="-Y", up="Z", degrees=30.0):
    """Probe several bones at once and return a table.

    Run this once per rig before authoring anything. Every sign used by a
    generator should be read out of this table, never assumed.
    """
    rows = []
    for spec in bones:
        if isinstance(spec, (list, tuple)):
            bone, observe = spec
        else:
            bone, observe = spec, None
        r = probe_bone_axis(rig_name, bone, degrees=degrees, forward=forward,
                            up=up, observe=observe)
        if "error" in r:
            rows.append({"bone": bone, "error": r["error"]})
        else:
            rows.append({
                "bone": bone,
                "observed": r["observed"],
                "swing_axis": r["swing_axis"],
                "forward_sign": r["forward_sign"],
                "moves_on_plus": r["axes"][r["swing_axis"]]["moves"],
            })
    return {"rig": rig_name, "forward": forward, "probes": rows}


# --------------------------------------------------------------------------
# clip checks
# --------------------------------------------------------------------------

def _frames(action):
    lo, hi = action.frame_range
    return int(lo), int(hi)


def check_clip(rig_name, action_name, foot_bones, floor=0.0, up="Z",
               loop=True, forward="-Y", tolerance=0.0):
    """Assert the things that silently ruin a generated clip.

    - floor penetration: the lowest a foot ever reaches
    - loop seam: distance between the first and last frame's pose
    - stride and the speed the clip implies, so an engine can time-scale it
      honestly instead of letting the feet skate
    """
    rig = bpy.data.objects.get(rig_name)
    action = bpy.data.actions.get(action_name)
    if rig is None:
        return {"error": "no armature " + repr(rig_name)}
    if action is None:
        return {"error": "no action " + repr(action_name)}

    uidx = AXIS_INDEX[up[-1].upper()]
    fsign = -1.0 if forward.startswith("-") else 1.0
    fidx = AXIS_INDEX[forward[-1].upper()]

    scene = bpy.context.scene
    snap = _snapshot(rig)
    prev_action = rig.animation_data.action if rig.animation_data else None
    prev_frame = scene.frame_current

    try:
        if rig.animation_data is None:
            rig.animation_data_create()
        rig.animation_data.action = action
        lo, hi = _frames(action)

        lowest = float("inf")
        lowest_at = None
        per_foot = {b: {"fwd": float("inf"), "back": -float("inf")} for b in foot_bones}
        first = {}
        last = {}

        for f in range(lo, hi + 1):
            scene.frame_set(f)
            bpy.context.view_layer.update()
            for b in foot_bones:
                p = bone_tip(rig, b)
                if p[uidx] < lowest:
                    lowest, lowest_at = p[uidx], f
                fwd = p[fidx] * fsign
                per_foot[b]["fwd"] = min(per_foot[b]["fwd"], -fwd)
                per_foot[b]["back"] = max(per_foot[b]["back"], -fwd)
                if f == lo:
                    first[b] = p.copy()
                if f == hi:
                    last[b] = p.copy()

        seam = max((last[b] - first[b]).length for b in foot_bones) if loop else None
        stride = max(per_foot[b]["back"] - per_foot[b]["fwd"] for b in foot_bones)
        fps = scene.render.fps

        # Two different periods, and using the wrong one makes the feet slide.
        #
        # A seamless loop authored with a duplicated final frame (33 == 1) has a
        # true cycle of hi-lo frames. But glTF exports every keyed frame, so an
        # engine importing it sees a clip of hi frames and loops over all of
        # them - holding the duplicate for one frame-interval each cycle.
        # Author against `cycle`; time-scale playback against `playback`.
        cycle_duration = (hi - lo) / float(fps) if fps else 0.0
        playback_duration = (hi - lo + 1) / float(fps) if fps else 0.0
        implied = (2.0 * stride / cycle_duration) if cycle_duration > 0 else 0.0
        implied_playback = (
            (2.0 * stride / playback_duration) if playback_duration > 0 else 0.0
        )
        duration = cycle_duration

        failures = []
        # A tolerance is not laxity. Without IK foot-planting, a limb swung as a
        # pendulum must dip its tip slightly below the rest height, and a rig
        # fitted to a real animal puts its toes ON the ground - a rat's rested
        # at +0.00003. Demanding exactly zero penetration is unsatisfiable at
        # any amplitude; what matters is that the dip stays negligible against
        # the creature's size.
        if lowest < floor - tolerance - 1e-6:
            failures.append(
                "foot reaches " + format(lowest, ".4f") + " at frame " + str(lowest_at)
                + ", below the floor at " + format(floor, ".4f")
                + " by more than the " + format(tolerance, ".4f") + " tolerance"
            )
        if loop and seam is not None and seam > 1e-4:
            failures.append("loop seam " + format(seam, ".6f") + " - first and last frame differ")

        return {
            "action": action_name,
            "frames": [lo, hi],
            "fps": fps,
            "duration_s": round(duration, 4),
            "lowest_foot": round(lowest, 4),
            "lowest_at_frame": lowest_at,
            "floor": floor,
            "tolerance": round(tolerance, 5),
            "loop_seam": round(seam, 6) if seam is not None else None,
            "stride_m": round(stride, 4),
            "implied_speed_mps": round(implied, 4),
            "implied_speed_playback_mps": round(implied_playback, 4),
            "playback_duration_s": round(playback_duration, 4),
            "speed_note": (
                "implied_speed_mps assumes the true cycle (" + str(hi - lo)
                + " frames). An engine that imports all " + str(hi - lo + 1)
                + " keyed frames loops over the longer period - use "
                "implied_speed_playback_mps to time-scale playback there."
            ),
            "failures": failures,
            "passed": not failures,
        }
    finally:
        scene.frame_set(prev_frame)
        if rig.animation_data:
            rig.animation_data.action = prev_action
        _restore(rig, snap)


def contralateral(rig_name, action_name, limb_a, limb_b, forward="-Y"):
    """Correlate two limbs' swing, each about its own mean.

    Opposite limbs should correlate near -1 and same-side limbs near +1.

    Comparing raw positions instead of deviations from the mean gives a wrong
    answer whenever a joint's neutral pose is off-centre - a bent elbow leaves
    the hand permanently in front of the body, so its absolute sign never flips
    even while it swings perfectly well.
    """
    rig = bpy.data.objects.get(rig_name)
    action = bpy.data.actions.get(action_name)
    if rig is None or action is None:
        return {"error": "missing rig or action"}

    fidx = AXIS_INDEX[forward[-1].upper()]
    scene = bpy.context.scene
    snap = _snapshot(rig)
    prev_action = rig.animation_data.action if rig.animation_data else None
    prev_frame = scene.frame_current

    try:
        if rig.animation_data is None:
            rig.animation_data_create()
        rig.animation_data.action = action
        lo, hi = _frames(action)

        a, b = [], []
        for f in range(lo, hi):  # exclude the duplicated loop frame
            scene.frame_set(f)
            bpy.context.view_layer.update()
            a.append(bone_tip(rig, limb_a)[fidx])
            b.append(bone_tip(rig, limb_b)[fidx])

        n = len(a)
        if n < 3:
            return {"error": "too few frames"}
        ma, mb = sum(a) / n, sum(b) / n
        da = [x - ma for x in a]
        db = [x - mb for x in b]
        num = sum(x * y for x, y in zip(da, db))
        den = math.sqrt(sum(x * x for x in da) * sum(y * y for y in db))
        r = (num / den) if den else 0.0

        return {
            "action": action_name,
            "limb_a": limb_a,
            "limb_b": limb_b,
            "correlation": round(r, 4),
            "amplitude_a": round(max(a) - min(a), 4),
            "amplitude_b": round(max(b) - min(b), 4),
            "reading": ("contralateral (opposite limbs)" if r < -0.7 else
                        "same-side (moves together)" if r > 0.7 else
                        "uncorrelated - suspicious"),
        }
    finally:
        scene.frame_set(prev_frame)
        if rig.animation_data:
            rig.animation_data.action = prev_action
        _restore(rig, snap)


def check_export_origin(rig_name, mesh_name=None, tolerance=0.01):
    """Whether the rig sits on its own origin.

    An exported root carrying a translation makes the character orbit a point
    off to one side when the node is rotated, rather than turning in place.
    """
    rig = bpy.data.objects.get(rig_name)
    if rig is None:
        return {"error": "no armature " + repr(rig_name)}

    out = {
        "rig": rig_name,
        "rig_location": [round(v, 5) for v in rig.location],
        "offset": round(Vector(rig.location).length, 5),
    }
    if mesh_name:
        mesh = bpy.data.objects.get(mesh_name)
        if mesh:
            pts = [mesh.matrix_world @ v.co for v in mesh.data.vertices]
            cx = sum(p.x for p in pts) / len(pts)
            cy = sum(p.y for p in pts) / len(pts)
            out["mesh_mean_xy"] = [round(cx, 5), round(cy, 5)]
            out["lateral_offset"] = round(math.hypot(cx, cy), 5)

    off = out.get("lateral_offset", out["offset"])
    out["passed"] = off <= tolerance
    out["note"] = ("centred" if out["passed"] else
                   "off origin by " + format(off, ".4f")
                   + " - export from the origin or the model will orbit")
    return out
