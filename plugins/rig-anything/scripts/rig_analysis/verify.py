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


_ROTATION_CHANNELS = {"rotation_quaternion": "QUATERNION", "rotation_euler": "EULER",
                      "rotation_axis_angle": "AXIS_ANGLE"}


def keyed_rotation_channels(action):
    """{bone: {"QUATERNION" | "EULER" | "AXIS_ANGLE"}} - which rotation property
    each bone's curves in `action` write."""
    from . import motion
    out = {}
    for fc in motion._fcurves(action):
        path = fc.data_path
        if not path.startswith("pose.bones[") or '"' not in path:
            continue
        kind = _ROTATION_CHANNELS.get(path.rsplit(".", 1)[-1])
        if kind:
            out.setdefault(path.split('"')[1], set()).add(kind)
    return out


def _mode_kind(mode):
    return mode if mode in ("QUATERNION", "AXIS_ANGLE") else "EULER"


def adopt_rotation_modes(rig, action):
    """Put every bone `action` keys into the rotation mode its keys use.

    A bone reads only the rotation property its mode names. MPFB rigs rotate in
    Euler XYZ, and restoring a snapshot after baking put them back there - so
    Blender ignored every quaternion key, the legs stood still, and every check
    run before the restore had passed. Authoring ends with this, never with the
    mode the bone happened to be in before. Returns the bones it changed.
    """
    changed = []
    for name, kinds in keyed_rotation_channels(action).items():
        pb = rig.pose.bones.get(name)
        if pb is None or len(kinds) != 1:
            continue
        kind = next(iter(kinds))
        if _mode_kind(pb.rotation_mode) == kind:
            continue
        pb.rotation_mode = "XYZ" if kind == "EULER" else kind
        changed.append(name)
    return changed


def rotation_mode_mismatches(rig_name, action_name):
    """Bones `action` keys on a rotation property their rotation mode ignores.

    A quaternion key on an Euler bone - or an Euler key on a quaternion bone -
    plays as nothing at all. Every measurement then reads the rest pose, and the
    rest pose passes everything: floor, seam, even stride, which is merely zero.
    """
    rig = bpy.data.objects.get(rig_name)
    action = bpy.data.actions.get(action_name)
    if rig is None or rig.type != "ARMATURE":
        return {"error": "no armature named " + repr(rig_name)}
    if action is None:
        return {"error": "no action " + repr(action_name)}
    bad = []
    for name, kinds in sorted(keyed_rotation_channels(action).items()):
        pb = rig.pose.bones.get(name)
        if pb is None:
            continue
        mode = _mode_kind(pb.rotation_mode)
        if mode not in kinds:
            bad.append({"bone": name, "keys": sorted(kinds), "mode": pb.rotation_mode})
    note = ("" if not bad else
            "%d bones keyed on a rotation their mode ignores (e.g. %s keys %s but is in %s) - "
            "those keys do not play" % (len(bad), bad[0]["bone"], "/".join(bad[0]["keys"]),
                                        bad[0]["mode"]))
    return {"rig": rig_name, "action": action_name, "mismatches": bad, "note": note,
            "passed": not bad}


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


def action_channels(action, slot=None):
    """Bone names an action actually drives.

    Blender 4.4 moved an action's curves behind layers, strips and channelbags;
    before that they hung off `action.fcurves`. Both are read here, so the same
    code works on 4.x and 5.x.
    """
    names = set()
    layers = getattr(action, "layers", None)
    if layers:
        for layer in layers:
            for strip in layer.strips:
                for cb in getattr(strip, "channelbags", []):
                    if slot is not None and getattr(cb, "slot_handle", None) not in (
                            None, slot.handle):
                        continue
                    for fc in cb.fcurves:
                        if '"' in fc.data_path:
                            names.add(fc.data_path.split('"')[1])
    else:
        for fc in getattr(action, "fcurves", []):
            if '"' in fc.data_path:
                names.add(fc.data_path.split('"')[1])
    return names


def bind_action(rig, action):
    """Assign an action to a rig *and* bind its slot.

    A third way for a rig to read as a clean zero, and the most deceptive yet.
    Blender 4.4 put an action's curves in named slots, and a slot remembers
    which ID it was authored for. Assigning the action alone leaves nothing
    bound when those names no longer agree, so the rig sits in its rest pose
    while every frame is dutifully stepped through - stride 0.0000, loop seam
    0.000000, a table of results that looks not merely plausible but excellent.

    This happens in ordinary use: two rigs in one file, an action name reused,
    and the slot now points at the other skeleton. So the binding is checked
    against the rig's own bones and reported, never assumed to have worked.
    """
    ad = rig.animation_data or rig.animation_data_create()
    ad.action = action

    slots = list(getattr(action, "slots", []) or [])
    chosen = None
    if slots:
        # Prefer the slot authored for this object; fall back to the only one.
        chosen = next((s for s in slots if s.identifier == "OB" + rig.name), None)
        if chosen is None and len(slots) == 1:
            chosen = slots[0]
        if chosen is not None:
            try:
                ad.action_slot = chosen
            except (AttributeError, TypeError):
                chosen = None

    bones = {b.name for b in rig.data.bones}
    channels = action_channels(action, slot=chosen)
    drives = sorted(channels & bones)
    foreign = sorted(channels - bones)

    # Partial application is its own trap, and this skill's own naming invites
    # it. Every generically-built rig calls its limbs leg1_upper.L and so on,
    # so a hexapod's Tripod lands 8 of its 12 channels on a quadruped: the legs
    # it shares move, the two it does not are dropped, and what plays is a
    # confident half-animation of the wrong creature. A clip authored for
    # another skeleton is not this skeleton's clip, whatever the overlap.
    coverage = (len(drives) / float(len(drives) + len(foreign))
                if (drives or foreign) else 0.0)

    if drives and not foreign:
        note = "drives %d of this rig's bones" % len(drives)
    elif drives:
        note = ("only %d of its %d channels exist on %s (%s missing) - it was "
                "authored for another skeleton and would play as a partial "
                "animation" % (len(drives), len(drives) + len(foreign), rig.name,
                               ", ".join(foreign[:3])
                               + ("..." if len(foreign) > 3 else "")))
    else:
        whose = (", ".join(foreign[:3]) + ("..." if len(foreign) > 3 else "")
                 if foreign else "no bones at all")
        note = ("animates nothing on %s - its channels are for %s. Every "
                "measurement would read zero." % (rig.name, whose))

    return {
        "action": action.name,
        "slot": chosen.identifier if chosen is not None else None,
        "slots_available": [s.identifier for s in slots],
        "drives": drives,
        "foreign_channels": foreign,
        "coverage": round(coverage, 3),
        "bound": bool(drives) and not foreign,
        "note": note,
    }


def check_clip(rig_name, action_name, foot_bones, floor=0.0, up="Z",
               loop=True, forward="-Y", tolerance=0.0):
    """Assert the things that silently ruin a generated clip.

    - floor penetration: the lowest a foot ever reaches
    - loop seam: distance between the first and last frame's pose
    - stride and the speed the clip implies, so an engine can time-scale it
      honestly instead of letting the feet skate
    - rotation modes: a bone keyed on a rotation its mode ignores plays the rest
      pose, which passes everything above
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
        binding = bind_action(rig, action)
        if not binding["bound"]:
            # Refuse rather than measure a rest pose. The numbers that come back
            # from an unbound action are not merely wrong, they are immaculate.
            return {"error": "%s %s" % (repr(action_name), binding["note"]),
                    "binding": binding}
        lo, hi = _frames(action)
        # A body with no feet - a worm, a whale - still has a loop seam and a
        # lowest point; it has no stride. Track every bone for those, and
        # nothing for speed. With an empty list this used to raise.
        feetless = not foot_bones
        stance_bones = list(foot_bones)
        if feetless:
            foot_bones = [b.name for b in rig.data.bones]

        lowest = float("inf")
        lowest_at = None
        per_foot = {b: {"fwd": float("inf"), "back": -float("inf")} for b in foot_bones}
        tracks = {b: [] for b in foot_bones}      # (height, backward position)
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
                tracks[b].append((p[uidx], -fwd))
                if f == lo:
                    first[b] = p.copy()
                if f == hi:
                    last[b] = p.copy()

        seam = max((last[b] - first[b]).length for b in foot_bones) if loop else None
        stride = 0.0 if feetless else max(per_foot[b]["back"] - per_foot[b]["fwd"] for b in foot_bones)
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
        stride_implied = implied
        duty = None
        speed_source = "stride (2 x foot travel per cycle - exact only at duty 0.5)"

        # Measure the stance feet instead, where they can be seen. "Two strides
        # of foot travel per cycle" is only true when each foot is down exactly
        # half the time; a gallop's feet are down a third of it and swing past
        # their touchdown point, and the stride formula read that clip 60% off.
        # A foot is in stance while it sits at its lowest; the body's speed is
        # how fast it sweeps backward there.
        band = max(tolerance, 1e-4)
        speeds, down_frames, spans = [], 0, 0
        for b in stance_bones:
            track = tracks[b]
            low = min(h for h, _ in track)
            down = [h <= low + band for h, _ in track]
            down_frames += sum(down[:-1])
            for i in range(len(track) - 1):
                if down[i] and down[i + 1] and abs(track[i + 1][1] - track[i][1]) > 1e-7:
                    speeds.append((track[i + 1][1] - track[i][1]) * fps)
                    spans += 1
        if loop and cycle_duration > 0 and spans >= 2 * len(foot_bones):
            speeds.sort()
            v = speeds[len(speeds) // 2]
            # a planted foot moves at one steady speed; if they disagree this
            # was not a plant but a slide or a roll, and the stride stands
            steady = sum(1 for s in speeds if abs(s - v) <= 0.1 * abs(v)) >= 0.6 * len(speeds)
            if v > 0 and steady:
                implied = v
                duty = down_frames / float(len(foot_bones) * (hi - lo))
                speed_source = "stance feet (median backward speed while planted)"
        implied_playback = implied * cycle_duration / playback_duration \
            if playback_duration > 0 else 0.0
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
        modes = rotation_mode_mismatches(rig_name, action_name)
        if modes.get("mismatches"):
            failures.append("rotation mode: " + modes["note"])

        return {
            "action": action_name,
            "binding": binding,
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
            "speed_source": speed_source,
            "stride_implied_speed_mps": round(stride_implied, 4),
            "duty_factor": round(duty, 3) if duty is not None else None,
            "playback_duration_s": round(playback_duration, 4),
            "speed_note": (
                "implied_speed_mps assumes the true cycle (" + str(hi - lo)
                + " frames). An engine that imports all " + str(hi - lo + 1)
                + " keyed frames loops over the longer period - use "
                "implied_speed_playback_mps to time-scale playback there."
            ),
            "rotation_mode_mismatches": len(modes.get("mismatches", [])),
            "failures": failures,
            "passed": not failures,
        }
    finally:
        scene.frame_set(prev_frame)
        if rig.animation_data:
            rig.animation_data.action = prev_action
        _restore(rig, snap)


# --------------------------------------------------------------------------
# re-checking a finished clip
# --------------------------------------------------------------------------

# The authoring checks' tolerances, as fractions of the body map's size (or
# height), so a clip re-checked after layering is held to what it was authored
# to - never to something looser.
PLANT_TOL = 0.005       # planted drift and bone floor (`actions._check_common`)
SLIP_TOL = 0.004        # a stance contact leaving its line (`locomotion.cycle`)
SKIN_TOL = 0.015        # skin through the floor, of height (`_check_common` step 7)
SEAM_TOL = 1e-4         # loop seam, absolute
STANCE_BAND = 0.01      # in contact within this of its lowest, of height (`locomotion.detect`)


def _bound_meshes(rig):
    return [o for o in bpy.data.objects if o.type == "MESH" and any(
        m.type == "ARMATURE" and m.object == rig for m in o.modifiers)]


def _play(rig, action, frames, meshes=(), upw=None, mesh_frames=None):
    """{frame: pose matrices} and {frame: lowest evaluated skin height} over
    `frames`, with the action bound; the rig is left as it was found."""
    scene = bpy.context.scene
    snap = _snapshot(rig)
    ad = rig.animation_data or rig.animation_data_create()
    prev_action, prev_frame = ad.action, scene.frame_current
    prev_slot = getattr(ad, "action_slot", None)
    mats, skin = {}, {}
    try:
        binding = bind_action(rig, action)
        if not binding["bound"]:
            return None, None, binding
        for f in frames:
            scene.frame_set(f)
            bpy.context.view_layer.update()
            mats[f] = {pb.name: pb.matrix.copy() for pb in rig.pose.bones}
            if meshes and (mesh_frames is None or f in mesh_frames):
                dg = bpy.context.evaluated_depsgraph_get()
                low = float("inf")
                for o in meshes:
                    ev = o.evaluated_get(dg)
                    me = ev.to_mesh()
                    mw = o.matrix_world
                    low = min(low, min((mw @ v.co).dot(upw) for v in me.vertices))
                    ev.to_mesh_clear()
                skin[f] = low
        return mats, skin, binding
    finally:
        scene.frame_set(prev_frame)
        ad.action = prev_action
        if prev_slot is not None:
            try:
                ad.action_slot = prev_slot
            except (AttributeError, TypeError):
                pass
        _restore(rig, snap)


def _stance_spans(down, loop):
    """Contiguous runs of True as (start, length) over frame indices; in a loop a
    run crossing the end continues from the start."""
    n = len(down)
    if all(down):
        return [(0, n)]
    spans, i = [], 0
    while i < n:
        if down[i] and (i == 0 or not down[i - 1]):
            j = i
            while j < n and down[j]:
                j += 1
            spans.append([i, j - i])
            i = j
        else:
            i += 1
    if loop and len(spans) >= 2 and spans[0][0] == 0 and spans[-1][0] + spans[-1][1] == n:
        spans[-1][1] += spans[0][1]
        spans.pop(0)
    return [tuple(s) for s in spans]


def _line_fit(points):
    """(start, per-frame step, largest distance off that line) for a least-
    squares straight line at constant speed through consecutive frames."""
    n = len(points)
    tm = (n - 1) / 2.0
    mean = sum(points, Vector()) / n
    den = sum((i - tm) ** 2 for i in range(n)) or 1.0
    step = sum(((p - mean) * (i - tm) for i, p in enumerate(points)), Vector()) / den
    start = mean - step * tm
    off = max((p - (start + step * i)).length for i, p in enumerate(points))
    return start, step, off


def limb_clearance(rig_name, action_name, mesh_name=None, every=2, roles=("arm",),
                   forward="-Y", up="Z", floor=0.0, bm=None, stride=3):
    """Closest the skin of each free limb's forearm and hand comes to the body.

    Body is the skin of the torso - the axial bones below the neck and anything
    hung off them that is not a limb, jiggle bones included - and the legs'
    upper segments. Which bones those are comes from the body map, not names.
    Each limb vertex is tested against the nearest body triangle: negative
    distance (by that triangle's normal) is through the skin. A graze reads as
    a few millimetres; a hand in the hip reads centimetres negative.
    """
    from mathutils.bvhtree import BVHTree
    from . import bodymap
    rig = bpy.data.objects.get(rig_name)
    action = bpy.data.actions.get(action_name)
    if rig is None or action is None:
        return {"error": "missing rig or action"}
    bm = bm or bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return {"error": bm["error"]}
    meshes = ([bpy.data.objects[mesh_name]] if mesh_name and bpy.data.objects.get(mesh_name)
              else _bound_meshes(rig))
    if not meshes:
        return {"error": "no skinned mesh on " + rig_name}
    bones = rig.data.bones
    limbs = [l for l in bm["limbs"] if l["role"] in roles]
    if not limbs:
        return {"skipped": "no %s limbs" % "/".join(roles)}
    limb_bones = set()
    for l in bm["limbs"]:
        limb_bones.update(n for n in (l["girdle"], l["upper"], l["lower"], l["end"]) if n)
        limb_bones.update(l["digits"])
    # the forearm and everything it carries - a hand's other fingers too
    reach = set()
    for l in limbs:
        reach.add(l["lower"])
        reach.update(c.name for c in bones[l["lower"]].children_recursive)
    trunk = set(bm["torso"]) | set(bm.get("rear", []))
    stop = limb_bones | set(bm["neck"]) | set(bm["tail"]) | ({bm["head"]} if bm["head"] else set())
    body = {l["upper"] for l in bm["limbs"] if l["role"] == "leg"}
    for b in bones:
        # hung off the trunk without passing through a limb, the neck or a tail
        cur = b
        while cur is not None and cur.name not in trunk and cur.name not in stop:
            cur = cur.parent
        if cur is not None and cur.name in trunk:
            body.add(b.name)

    out = {"limbs": [l["name"] for l in limbs], "closest_m": None, "at_frame": None,
           "samples_inside": 0}
    worst = (float("inf"), None)
    for ob in meshes:
        names = {g.index: g.name for g in ob.vertex_groups}
        limb_v, body_v = [], set()
        for v in ob.data.vertices:
            ws = [(names.get(g.group), g.weight) for g in v.groups if g.weight > 0.0]
            tot = sum(w for _, w in ws)
            if tot <= 0.0:
                continue
            n, w = max(ws, key=lambda nw: nw[1])
            if n in reach and w / tot > 0.6:
                limb_v.append(v.index)
            elif n in body and w / tot > 0.5:
                body_v.add(v.index)
        tris = [tuple(p.vertices) for p in ob.data.polygons
                if all(i in body_v for i in p.vertices)]
        if not limb_v or not tris:
            continue
        lo, hi = _frames(action)
        frames = list(range(lo, hi + 1))[::max(1, every)]
        scene = bpy.context.scene
        snap = _snapshot(rig)
        ad = rig.animation_data or rig.animation_data_create()
        prev_action, prev_frame = ad.action, scene.frame_current
        try:
            if not bind_action(rig, action)["bound"]:
                return {"error": "could not bind " + action_name}
            for f in frames:
                scene.frame_set(f)
                dg = bpy.context.evaluated_depsgraph_get()
                ev = ob.evaluated_get(dg)
                me = ev.to_mesh()
                verts = [ob.matrix_world @ v.co for v in me.vertices]
                ev.to_mesh_clear()
                bvh = BVHTree.FromPolygons(verts, tris)
                for i in limb_v[::max(1, stride)]:
                    hit = bvh.find_nearest(verts[i])
                    if hit[0] is None:
                        continue
                    d = hit[3]
                    if (verts[i] - hit[0]).dot(hit[1]) < 0:
                        d = -d
                        out["samples_inside"] += 1
                    if d < worst[0]:
                        worst = (d, f)
        finally:
            scene.frame_set(prev_frame)
            ad.action = prev_action
            _restore(rig, snap)
    if worst[1] is not None:
        out["closest_m"], out["at_frame"] = round(worst[0], 4), worst[1]
    return out


def recheck(rig_name, action_name, forward="-Y", up="Z", floor=0.0, loop=True,
            clearance=False, mesh_name=None):
    """Play back a FINISHED clip and hold it to the checks it was authored under.

    Authoring checks run once, on the clip as generated. Anything layered on
    afterwards - a hunch, an upper body, feet brought in - is keyed straight
    over it and nothing measures it again; a 15 degree pelvis pitch across a
    walk leaves every authoring report still reading PASSED. This measures
    only Blender's playback, so it works on any clip from any source:

    - rotation modes: keys the bones' modes would ignore
    - bone floor: bones that carry skin, below the floor by more than
      PLANT_TOL of size (below their rest height, for a body built into it)
    - skin through the floor, by more than SKIN_TOL of height
    - loop seam (`loop=True`): first and last frame, every bone
    - foot slide: each leg's contact (`locomotion.contact_pivot`) is in stance
      while within STANCE_BAND of its lowest. A planted contact must move in a
      straight line at one speed (an in-place clip sweeps it backward) with no
      sideways or vertical drift, and every leg at the same speed - otherwise
      it skates. Held to SLIP_TOL of size.
    - balance, where it means something: when every leg stays planted and
      still for the whole clip (an idle, a held crouch), the skinned centre of
      mass must stay over the feet.
    - `clearance=True`: `limb_clearance`, failing below -PLANT_TOL of size.

    Returns a report with `failures` and `passed`, like every check here.
    """
    from . import bodymap, locomotion, motion
    rig = bpy.data.objects.get(rig_name)
    action = bpy.data.actions.get(action_name)
    if rig is None or rig.type != "ARMATURE":
        return {"error": "no armature named " + repr(rig_name)}
    if action is None:
        return {"error": "no action " + repr(action_name)}
    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return {"error": bm["error"]}
    body = motion.Body(rig, bm)
    size, height = bm["size"], bm["height"]
    mw = rig.matrix_world
    upw = bodymap.axis_vector(up)
    scale = sum(mw.to_scale()) / 3.0
    fwd, lat, up_a = bm["fwd"], bm["lat"], bm["up_vec"]
    lo, hi = _frames(action)
    frames = list(range(lo, hi + 1))
    meshes = _bound_meshes(rig)
    mats, skin, binding = _play(rig, action, frames, meshes, upw)
    if mats is None:
        return {"error": "%s %s" % (repr(action_name), binding["note"]), "binding": binding}

    failures, out = [], {"rig": rig_name, "action": action_name, "frames": [lo, hi],
                         "loop": loop}

    def h(p):
        return (mw @ p).dot(upw) - floor

    def tail(m, name):
        return m[name] @ Vector((0.0, rig.data.bones[name].length, 0.0))

    modes = rotation_mode_mismatches(rig_name, action_name)
    out["rotation_mode_mismatches"] = modes["mismatches"]
    if modes["mismatches"]:
        failures.append("rotation mode: " + modes["note"])

    # bone floor, skinned bones only
    tol = PLANT_TOL * size
    skinned = body.skinned_bones()
    bones = [b for b in rig.data.bones if skinned is None or b.name in skinned] or list(rig.data.bones)
    lowest, lowest_at = float("inf"), None
    for f in frames:
        for b in bones:
            for p in (mats[f][b.name].translation, tail(mats[f], b.name)):
                if h(p) < lowest:
                    lowest, lowest_at = h(p), (f, b.name)
    rest_lowest = min(h(p) for b in bones for p in (b.head_local, b.tail_local))
    out["lowest_bone"] = {"height": round(lowest, 4), "frame": lowest_at[0], "bone": lowest_at[1]}
    if lowest < min(0.0, rest_lowest) - tol:
        failures.append("%s reaches %.4f, below the floor, at frame %d"
                        % (lowest_at[1], lowest, lowest_at[0]))

    # skin through the floor, against the rest skin (as `_check_common`)
    if skin:
        skin_low = min(skin.values())
        skin_rest = body.skin_lowest(body.fk(), upw)
        if skin_rest is None:
            skin_rest = skin[lo]
        at = min(skin, key=skin.get)
        out["skin_lowest"] = {"height": round(skin_low - floor, 4), "frame": at}
        if skin_low < min(0.0, skin_rest) - floor - SKIN_TOL * height:
            failures.append("skin reaches %.4f, through the floor, at frame %d"
                            % (skin_low - floor, at))

    # loop seam
    if loop:
        seam, seam_bone = 0.0, None
        for b in rig.data.bones:
            e = max((mats[lo][b.name].translation - mats[hi][b.name].translation).length,
                    (tail(mats[lo], b.name) - tail(mats[hi], b.name)).length)
            if e > seam:
                seam, seam_bone = e, b.name
        out["loop_seam"] = round(seam, 6)
        if seam > SEAM_TOL:
            failures.append("loop seam %.5f on %s" % (seam, seam_bone))

    # foot slide during stance
    legs = [l for l in bm["limbs"] if l["role"] == "leg" and l["axial_index"] is not None]
    cyc = frames[:-1] if loop and len(frames) > 2 else frames
    n = len(cyc)
    slip_tol = SLIP_TOL * size
    contacts, stance_steps, all_still = {}, {}, bool(legs)
    for l in legs:
        carrier = l["end"] or l["lower"]
        pivot = locomotion.contact_pivot(rig, l)
        pts = [body.carried(mats[f], carrier, pivot) for f in cyc]
        hs = [h(p) for p in pts]
        low = min(hs)
        down = [x <= low + STANCE_BAND * height for x in hs]
        spans = _stance_spans(down, loop)
        worst = {"sideways": 0.0, "vertical": 0.0, "uneven": 0.0}
        steps = []
        for start, length in spans:
            # The band is wide enough to take in a foot one frame from touching
            # down or just lifted - Belle's toe lands inside it, still 2 cm from
            # where it plants - so an end frame hovering more than the slip
            # tolerance over the rest of its span is swing, not stance. One frame
            # at each end only: trimming further would eat a planted foot that
            # really does sink, which is what this is here to catch.
            if length >= 4:
                span_low = min(hs[(start + k) % n] for k in range(1, length - 1))
                if hs[start % n] > span_low + slip_tol * scale:
                    start, length = start + 1, length - 1
                if hs[(start + length - 1) % n] > span_low + slip_tol * scale:
                    length -= 1
            seq = [pts[(start + k) % n] for k in range(length)]
            if length < 3:
                continue
            _, step, off = _line_fit(seq)
            travel = length - 1
            worst["sideways"] = max(worst["sideways"], abs(step.dot(lat)) * travel)
            worst["vertical"] = max(worst["vertical"], abs(step.dot(up_a)) * travel)
            worst["uneven"] = max(worst["uneven"], off)
            steps.append((step.dot(fwd), travel))
        stance_steps[l["name"]] = steps
        if sum(down) < n:
            all_still = False
        contacts[l["name"]] = {
            "duty_factor": round(sum(down) / float(n), 3),
            "stance": [[round(s / float(n), 4), round((s + k) / float(n), 4)] for s, k in spans],
            **{k: round(v * scale, 5) for k, v in worst.items()},
        }
        for kind, v in worst.items():
            if v > slip_tol:
                failures.append("%s %s while planted by %.4f - the foot would skate"
                                % (l["name"], {"sideways": "drifts sideways",
                                               "vertical": "sinks or rises",
                                               "uneven": "moves unevenly"}[kind], v))
    # every stance contact sweeps back at the body's one speed
    all_steps = sorted(s for steps in stance_steps.values() for s, _ in steps)
    if all_steps:
        v = all_steps[len(all_steps) // 2]
        fps = bpy.context.scene.render.fps or 24
        out["stance_speed_mps"] = round(-v * scale * fps, 4)
        for name, steps in stance_steps.items():
            miss = max((abs(s - v) * t for s, t in steps), default=0.0)
            contacts[name]["speed_mismatch"] = round(miss * scale, 5)
            if miss > slip_tol:
                failures.append("%s is planted at a different speed from the other feet - "
                                "it slides %.4f over its stance" % (name, miss))
            if any(abs(s) * t > slip_tol for s, t in steps):
                all_still = False
    out["contacts"] = contacts

    # balance, for a clip standing still on every foot
    if legs and all_still:
        pts2 = []
        for l in legs:
            for nm in [l["end"]] + l["digits"] if l["end"] else [l["lower"]]:
                pts2 += [mats[lo][nm].translation, tail(mats[lo], nm)]
        normal = up_a
        origin = sum(pts2, Vector()) / len(pts2)
        hull = locomotion.support_polygon(pts2, origin, normal, fwd)
        f2 = (fwd - normal * fwd.dot(normal)).normalized()
        s2 = normal.cross(f2).normalized()
        worst_m, worst_f = float("inf"), None
        for f in frames:
            c = body.com(mats[f])
            m = locomotion.stability_margin(((c - origin).dot(f2), (c - origin).dot(s2)), hull)
            if m < worst_m:
                worst_m, worst_f = m, f
        out["balance"] = {"margin_m": round(worst_m * scale, 4), "frame": worst_f,
                          "com_source": body.com_source}
        if worst_m < 0.0:
            failures.append("centre of mass is %.4f outside the feet at frame %d - it "
                            "would fall" % (-worst_m, worst_f))

    if clearance:
        c = limb_clearance(rig_name, action_name, mesh_name=mesh_name, bm=bm,
                           forward=forward, up=up, floor=floor)
        out["clearance"] = c
        if c.get("closest_m") is not None and c["closest_m"] < -tol * scale:
            failures.append("a hand or forearm goes %.4f into the body at frame %d"
                            % (-c["closest_m"], c["at_frame"]))

    out["tolerances"] = {"plant": round(tol, 5), "slip": round(slip_tol, 5),
                         "skin": round(SKIN_TOL * height, 5)}
    out["failures"] = failures
    out["passed"] = not failures
    return out


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
        binding = bind_action(rig, action)
        if not binding["bound"]:
            return {"error": "%s %s" % (repr(action_name), binding["note"]),
                    "binding": binding}
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


def check_export_origin(rig_name, mesh_name=None, tolerance=0.01,
                        centroid_ratio=0.25):
    """Whether the exported transforms sit on the origin.

    What makes a character orbit is a *transform* on the exported root: rotate
    a node that carries a lateral translation and it swings around a point off
    to one side instead of turning in place. So the transforms are what get
    checked - the rig's and the mesh's, in world space, so a compensating
    parent does not hide one.

    The mesh's vertex centroid is deliberately NOT the test. It was, and it
    failed every animal it was shown: a rat's mass sits 3 cm behind its origin
    because it has a tail, a quadruped's 2 cm because it has a head, and none
    of that makes anything orbit. Anatomy is not an offset. The centroid is
    kept as a warning, at a threshold scaled to the creature, where it means
    something different - that the mesh really was modelled off to one side.
    """
    rig = bpy.data.objects.get(rig_name)
    if rig is None:
        return {"error": "no armature " + repr(rig_name)}

    def lateral(v):
        return math.hypot(v.x, v.y)

    rig_off = lateral(rig.matrix_world.translation)
    out = {
        "rig": rig_name,
        "rig_world": [round(v, 5) for v in rig.matrix_world.translation],
        "offset": round(rig_off, 5),
    }
    worst, culprit = rig_off, rig_name

    mesh = bpy.data.objects.get(mesh_name) if mesh_name else None
    if mesh:
        mesh_off = lateral(mesh.matrix_world.translation)
        out["mesh_world"] = [round(v, 5) for v in mesh.matrix_world.translation]
        out["mesh_offset"] = round(mesh_off, 5)
        if mesh_off > worst:
            worst, culprit = mesh_off, mesh_name

        pts = [mesh.matrix_world @ v.co for v in mesh.data.vertices]
        cx = sum(p.x for p in pts) / len(pts)
        cy = sum(p.y for p in pts) / len(pts)
        span = max(mesh.dimensions.x, mesh.dimensions.y) or 1.0
        out["mesh_mean_xy"] = [round(cx, 5), round(cy, 5)]
        out["centroid_offset"] = round(math.hypot(cx, cy), 5)
        out["centroid_fraction"] = round(out["centroid_offset"] / span, 3)
        if out["centroid_fraction"] > centroid_ratio:
            out["warning"] = ("mesh centroid is %.0f%% of its span off centre - "
                              "modelled to one side?"
                              % (out["centroid_fraction"] * 100))

    out["offset_worst"] = round(worst, 5)
    out["passed"] = worst <= tolerance
    out["note"] = ("centred" if out["passed"] else
                   culprit + " is off origin by " + format(worst, ".4f")
                   + " - export from the origin or the model will orbit")
    return out
