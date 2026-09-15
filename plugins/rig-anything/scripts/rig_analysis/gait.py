"""Generate a looping locomotion cycle for any number of legs.

Rigging literature mostly stops at the skeleton; animation is assumed to come
from retargeting a library clip, which needs the skeleton to match a profile
that already exists. A hexapod has no clip to retarget. So the cycle is
generated instead, from two things the decomposition already knows: how many
legs there are, and where each one sits along the body.

A gait is just a set of phase offsets. Every leg runs the same stance/swing
curve, started at a different point in the cycle:

    biped         0.0, 0.5
    quadruped     lateral-sequence walk, or a diagonal trot
    hexapod       alternating tripods
    n legs        alternating by rank and side

Nothing here assumes four legs, or two, or that the creature is a vertebrate.

NOTHING here assumes a rotation convention either. Which local axis swings a
limb forward, and with which sign, is measured per bone with
`verify.probe_bone_axis`, and the direction a mid-joint bends is measured from
the limb's own rest shape. That is not caution for its own sake: a knee bends
backward and an elbow forward, a quadruped's front legs are arms, and two rigs
of the same character disagree about which axis is which.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Euler, Vector

from . import verify

AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


# --------------------------------------------------------------------------
# phase offsets
# --------------------------------------------------------------------------

def phase_offsets(legs, gait="walk"):
    """Assign each leg its offset in the cycle.

    `legs` are dicts with a `name`, a `side` ("L"/"R") and a `forward` position.
    Ranks are numbered front to back, so the same rule covers any leg count.
    """
    if not legs:
        return {}

    ordered = sorted(legs, key=lambda l: -l["forward"])
    ranks, rank_of = [], {}
    for l in ordered:
        placed = False
        for i, r in enumerate(ranks):
            if abs(r - l["forward"]) < 0.18 * (abs(r) + abs(l["forward"]) + 1e-6) or \
               abs(r - l["forward"]) < 1e-3:
                rank_of[l["name"]] = i
                placed = True
                break
        if not placed:
            ranks.append(l["forward"])
            rank_of[l["name"]] = len(ranks) - 1

    pairs = len(ranks)
    out = {}
    for l in ordered:
        r = rank_of[l["name"]]
        s = 0 if l["side"] == "L" else 1
        if gait == "bound":
            out[l["name"]] = (r % 2) * 0.5
        elif gait == "gallop" and pairs == 2:
            # Rotary gallop, the dog's and the cheetah's: the feet land in a
            # circle - LH, RH, RF, LF - each pair a tenth of a cycle apart, the
            # fore pair half a cycle after the hind. As TOUCHDOWN times; see
            # `locomotion`, which reads offsets that way round.
            out[l["name"]] = (0.5 if r == 0 else 0.0) + (0.1 * s if r == 1 else 0.1 * (1 - s))
        elif pairs == 1:
            out[l["name"]] = 0.5 * s
        elif pairs == 2 and gait == "walk":
            # lateral sequence: LH 0.0, LF 0.25, RH 0.5, RF 0.75
            out[l["name"]] = 0.5 * s + 0.25 * (1 - r if r < 2 else 0)
        else:
            # trot and tripod are the same rule: alternate by rank and side
            out[l["name"]] = 0.5 * ((r + s) % 2)
    return out


def _default_gait(n_legs):
    if n_legs <= 2:
        return "walk"
    if n_legs == 4:
        return "walk"
    return "tripod"


# --------------------------------------------------------------------------
# the cycle
# --------------------------------------------------------------------------

def _swing(p):
    """Fore/aft position of a limb over the cycle. +1 forward at p=0."""
    return math.cos(2.0 * math.pi * p)


def _lift(p):
    """How much the mid-joint folds. Peaks mid-swing, zero through stance."""
    return max(0.0, -math.sin(2.0 * math.pi * p))


def _limb_bend_sign(rig, upper, lower, tip, forward):
    """Which way this limb's mid-joint already bends, measured from rest.

    A knee bends backward and an elbow forward; a quadruped's front legs are
    arms and its rear legs are legs. Rather than encode that table, the limb is
    asked: the mid-joint's offset from the straight root-to-tip line says which
    way it is already folded, and folding further follows it.
    """
    fsign = -1.0 if forward.startswith("-") else 1.0
    fi = AXIS_INDEX[forward[-1].upper()]

    root = rig.matrix_world @ rig.data.bones[upper].head_local
    mid = rig.matrix_world @ rig.data.bones[lower].head_local
    end = rig.matrix_world @ rig.data.bones[tip].tail_local

    span = end - root
    if span.length < 1e-9:
        return 1.0
    t = max(0.0, min(1.0, (mid - root).dot(span) / span.dot(span)))
    straight = root + span * t
    dev = (mid - straight)[fi] * fsign
    # magnitude is returned too, so near-zero readings can be reconciled
    # against the mirrored limb instead of being trusted on their own
    return (1.0 if dev >= 0 else -1.0), abs(dev) / max(span.length, 1e-9)


def generate(rig_name, legs, forward="-Y", up="Z", gait=None, frames=32,
             action_name=None, swing_degrees=28.0, lift_degrees=45.0,
             spine_bones=None, sway_degrees=4.0, arms=None, fps=None,
             floor=0.0, auto_fit=True, attempts=5):
    """Author a looping gait cycle, verified against the floor.

    If a foot penetrates the floor the swing amplitude is reduced and the cycle
    re-authored, up to `attempts` times. A real rat failed its first pass by
    3.8 mm - small enough to look fine and large enough to put a paw through
    the ground every stride. Amplitude that suits one creature's proportions
    does not suit another's, so rather than ask the caller to guess, the clip
    is measured and retried.
    """
    swing = swing_degrees
    lift = lift_degrees
    last = None
    for attempt in range(max(1, attempts) if auto_fit else 1):
        last = _generate_once(rig_name, legs, forward=forward, up=up, gait=gait,
                              frames=frames, action_name=action_name,
                              swing_degrees=swing, lift_degrees=lift,
                              spine_bones=spine_bones, sway_degrees=sway_degrees,
                              arms=arms, fps=fps, floor=floor)
        if "error" in last:
            return last
        v = last["verification"]
        if v.get("passed") or not auto_fit:
            last["swing_degrees"] = round(swing, 2)
            last["lift_degrees"] = round(lift, 2)
            last["attempts"] = attempt + 1
            return last
        swing *= 0.78
        lift *= 0.88
    last["swing_degrees"] = round(swing, 2)
    last["lift_degrees"] = round(lift, 2)
    last["attempts"] = attempts
    return last


def _fresh_action(rig, name):
    """An empty action called `name`, without destroying someone else's.

    Taking the name blindly deletes whatever already holds it, and the default
    name here is just the gait - "Walk". Rig a quadruped in a file that already
    contains a hand-authored humanoid Walk and the humanoid's clip is gone:
    same name, different skeleton, no warning and no undo. It is only found
    later, when the humanoid is re-exported and arrives in the engine standing
    still.

    An existing action is replaced only when it belongs to this rig. Otherwise
    the new one is prefixed and both survive.
    """
    bones = {b.name for b in rig.data.bones}
    old = bpy.data.actions.get(name)
    if old is not None:
        if verify.action_channels(old) <= bones:
            bpy.data.actions.remove(old)        # ours, or empty - safe to take
        else:
            name = "%s_%s" % (rig.name, name)
            clash = bpy.data.actions.get(name)
            if clash is not None:
                bpy.data.actions.remove(clash)
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    return action


def _generate_once(rig_name, legs, forward="-Y", up="Z", gait=None, frames=32,
                   action_name=None, swing_degrees=28.0, lift_degrees=45.0,
                   spine_bones=None, sway_degrees=4.0, arms=None, fps=None,
                   floor=0.0):
    rig = bpy.data.objects.get(rig_name)
    if rig is None or rig.type != "ARMATURE":
        return {"error": "no armature named " + repr(rig_name)}
    if not legs:
        return {"error": "no legs to animate"}

    gait = gait or _default_gait(len(legs))
    offsets = phase_offsets(legs, gait=gait)
    action_name = action_name or gait.capitalize()

    # Probe every limb before touching anything. A stale rig reads as zero on
    # every axis and would yield a confident, fictional set of signs.
    probes, bend = {}, {}
    for l in legs:
        r = verify.probe_bone_axis(rig_name, l["upper"], observe=l["tip"],
                                   forward=forward, up=up)
        if "error" in r:
            return {"error": "axis probe failed for %s: %s" % (l["upper"], r["error"])}
        probes[l["name"]] = r
        bend[l["name"]] = _limb_bend_sign(rig, l["upper"], l["lower"], l["tip"], forward)

    # Reconcile mirrored limbs.
    #
    # A nearly straight limb has almost no rest deviation, so its measured bend
    # direction is decided by noise - a hexapod came back with leg1.L at +1 and
    # leg1.R at -1, which would fold one leg of a mirrored pair backwards. On a
    # bilaterally symmetric body the pair must agree, so the clearer reading
    # wins.
    by_base = {}
    for l in legs:
        base = l["name"].rsplit(".", 1)[0]
        by_base.setdefault(base, []).append(l["name"])
    for base, names in by_base.items():
        if len(names) < 2:
            continue
        best = max(names, key=lambda n: bend[n][1])
        for n in names:
            bend[n] = (bend[best][0], bend[n][1])
    bend = {k: v[0] for k, v in bend.items()}

    lower_probes = {}
    for l in legs:
        r = verify.probe_bone_axis(rig_name, l["lower"], observe=l["tip"],
                                   forward=forward, up=up)
        lower_probes[l["name"]] = None if "error" in r else r

    scene = bpy.context.scene
    if fps:
        scene.render.fps = fps

    if rig.animation_data is None:
        rig.animation_data_create()
    action = _fresh_action(rig, action_name)
    action_name = action.name
    rig.animation_data.action = action

    verify.clear_pose(rig)

    def axis_quat(axis, degrees):
        e = [0.0, 0.0, 0.0]
        e[AXIS_INDEX[axis]] = math.radians(degrees)
        return Euler(e, "XYZ").to_quaternion()

    keys = list(range(1, frames + 2))          # frame frames+1 repeats frame 1
    for f in keys:
        p0 = ((f - 1) % frames) / float(frames)

        for l in legs:
            p = (p0 + offsets[l["name"]]) % 1.0
            pr = probes[l["name"]]
            swing_axis = pr["swing_axis"]
            fwd_positive = pr["forward_sign"].startswith("+")

            amount = _swing(p) * swing_degrees
            deg = amount if fwd_positive else -amount
            pb = rig.pose.bones[l["upper"]]
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = axis_quat(swing_axis, deg)
            pb.keyframe_insert("rotation_quaternion", frame=f)

            lp = lower_probes[l["name"]]
            if lp:
                fold = _lift(p) * lift_degrees * bend[l["name"]]
                lb = rig.pose.bones[l["lower"]]
                lb.rotation_mode = "QUATERNION"
                lb.rotation_quaternion = axis_quat(lp["swing_axis"], fold)
                lb.keyframe_insert("rotation_quaternion", frame=f)

        # arms counter-swing against the same-side leg, half a cycle apart
        for a in (arms or []):
            pr = verify.probe_bone_axis(rig_name, a["upper"], observe=a["tip"],
                                        forward=forward, up=up)
            if "error" in pr:
                continue
            p = (p0 + a.get("phase", 0.5)) % 1.0
            amount = _swing(p) * swing_degrees * 0.7
            deg = amount if pr["forward_sign"].startswith("+") else -amount
            pb = rig.pose.bones[a["upper"]]
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = axis_quat(pr["swing_axis"], deg)
            pb.keyframe_insert("rotation_quaternion", frame=f)

        # a little body sway, twice per cycle
        for i, bn in enumerate(spine_bones or []):
            if bn not in rig.pose.bones:
                continue
            amp = sway_degrees * math.sin(2.0 * math.pi * p0 * 2.0 + i * 0.4)
            pb = rig.pose.bones[bn]
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = axis_quat(up[-1].upper(), amp)
            pb.keyframe_insert("rotation_quaternion", frame=f)

    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                for fc in cb.fcurves:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"

    feet = [l["tip"] for l in legs]
    # scaled to the creature: 0.5% of its height
    reach = max(rig.dimensions) or 1.0
    check = verify.check_clip(rig_name, action_name, feet, floor=floor,
                              up=up, loop=True, forward=forward,
                              tolerance=0.005 * reach)

    rig.animation_data.action = None
    verify.clear_pose(rig)
    # the probes restore each bone's previous mode; the keys need theirs
    verify.adopt_rotation_modes(rig, action)

    return {
        "rig": rig_name,
        "action": action_name,
        "gait": gait,
        "legs": len(legs),
        "frames": frames,
        "phase_offsets": {k: round(v, 3) for k, v in offsets.items()},
        "axes": {k: probes[k]["forward_sign"] for k in probes},
        "bend_signs": {k: bend[k] for k in bend},
        "verification": check,
    }


def limbs_from_rig(rig_name, forward="-Y", role="leg"):
    """Find limb chains in a rig built by `build.build_from_parts`.

    Bones are named `<role><n>_upper.<side>` / `_lower` / `_tip`, so the chains
    can be recovered from the rig alone - no need to carry the decomposition
    around, and a rig edited by hand still works as long as the names survive.
    """
    rig = bpy.data.objects.get(rig_name)
    if rig is None or rig.type != "ARMATURE":
        return []
    fi = AXIS_INDEX[forward[-1].upper()]

    groups = {}
    for b in rig.data.bones:
        if "_" not in b.name or not b.name.startswith(role):
            continue
        base, _, rest = b.name.partition("_")
        part, _, side = rest.partition(".")
        if not side:
            continue
        groups.setdefault((base, side), {})[part] = b.name

    out = []
    for (base, side), parts in sorted(groups.items()):
        if "upper" not in parts:
            continue
        upper = parts["upper"]
        lower = parts.get("lower", upper)
        tip = parts.get("tip", lower)
        tip_pos = rig.matrix_world @ rig.data.bones[tip].tail_local
        out.append({
            "name": base + "." + side,
            "side": side,
            "upper": upper, "lower": lower, "tip": tip,
            "forward": tip_pos[fi] * (-1.0 if forward.startswith("-") else 1.0),
        })
    return out


# ---------------------------------------------------------------------------
# legless locomotion
# ---------------------------------------------------------------------------

def spine_chain(rig_name, forward="-Y"):
    """Order a creature's bones from head to tail along its travel axis.

    Parenting cannot supply this order. The worm's chain branches at its middle
    bone and runs BOTH ways - spine.001..007 toward the head and tail.001..003
    toward the rear - so walking the hierarchy visits the body outward from the
    centre rather than end to end, and a wave built on that order travels out
    from the middle in both directions at once. Position along the forward axis
    gives the real order, and it does not care what the bones are called.
    """
    rig = bpy.data.objects.get(rig_name)
    if rig is None or rig.type != "ARMATURE":
        return []
    fsign = -1.0 if forward.startswith("-") else 1.0
    fidx = AXIS_INDEX[forward[-1].upper()]
    # Most forward first: "forwardness" is the head position projected onto the
    # travel direction.
    ranked = sorted(rig.data.bones,
                    key=lambda b: b.head_local[fidx] * fsign, reverse=True)
    return [b.name for b in ranked]


def _arc_positions(rig, chain, fidx, fsign):
    """Where each bone sits along the body, 0 at the head and 1 at the tail.

    Measured along the SKELETON, not through space. The obvious way - rank the
    bones by position on the travel axis - is wrong on a real generated rig,
    because the rig is not guaranteed to run monotonically. The worm's does not:
    `spine.001` sits behind its own parent and in front of its own child, so the
    spine doubles back, and ranking by position hands neighbouring phases to
    bones that are not neighbours. The wave comes out as noise.

    Walking the hierarchy instead makes the order structural. Distance is
    accumulated outward from the root along each branch and signed by the
    direction that branch travels, so a kinked chain still yields a monotonic
    parameter and the wave stays coherent.
    """
    names = set(chain)
    by_name = {b.name: b for b in rig.data.bones}

    # The root of this body: the highest ancestor still inside the chain.
    def root_of(bone):
        cur = bone
        while cur.parent is not None and cur.parent.name in names:
            cur = cur.parent
        return cur

    roots = {root_of(by_name[n]).name for n in chain}
    root = by_name[sorted(roots)[0]]

    # Distance from the root, accumulated down each branch.
    dist = {root.name: 0.0}
    branch = {root.name: None}
    stack = [root]
    while stack:
        bone = stack.pop()
        for child in bone.children:
            if child.name not in names:
                continue
            step = (Vector(child.head_local) - Vector(bone.head_local)).length
            if step < 1e-6:
                step = bone.length
            dist[child.name] = dist[bone.name] + step
            branch[child.name] = (branch[bone.name]
                                  if branch[bone.name] is not None else child.name)
            stack.append(child)

    # Which way each branch runs is decided ONCE, from the branch as a whole -
    # its farthest bone against the root. Deciding it per step re-introduces the
    # exact bug this function exists to dodge: one kinked link reverses the sign
    # mid-branch and the wave folds back on itself.
    root_fwd = Vector(root.head_local)[fidx] * fsign
    far = {}
    for n in chain:
        b = branch.get(n)
        if b is None:
            continue
        if b not in far or dist[n] > dist[far[b]]:
            far[b] = n
    heading = {}
    for b, tip_name in far.items():
        tip_fwd = Vector(by_name[tip_name].head_local)[fidx] * fsign
        heading[b] = -1.0 if tip_fwd > root_fwd else 1.0

    signed = {}
    for n in chain:
        b = branch.get(n)
        signed[n] = 0.0 if b is None else dist[n] * heading.get(b, 1.0)

    for n in chain:
        signed.setdefault(n, 0.0)
    lo = min(signed[n] for n in chain)
    hi = max(signed[n] for n in chain)
    span = (hi - lo) or 1.0
    return {n: (signed[n] - lo) / span for n in chain}


def _lateral_index(forward, up):
    used = {AXIS_INDEX[forward[-1].upper()], AXIS_INDEX[up[-1].upper()]}
    return ({0, 1, 2} - used).pop()


def _fcurves(action):
    """Every fcurve of an action, across Blender's old and slotted layouts."""
    out = []
    layers = getattr(action, "layers", None)
    if layers:
        for layer in layers:
            for strip in layer.strips:
                for cb in getattr(strip, "channelbags", []):
                    out.extend(cb.fcurves)
    else:
        out.extend(getattr(action, "fcurves", []))
    return out


def undulate(rig_name, bones=None, forward="-Y", up="Z", frames=32,
             action_name="Undulate", amplitude_degrees=16.0, wavelengths=1.25,
             head_damping=0.35, fps=None, floor=0.0, min_bones=4):
    """A travelling lateral wave along a legless body.

    The same shape as the legged gaits - one curve, phase-offset per element. A
    leg is offset by its rank and side; a spine bone is offset by how far along
    the body it sits, which turns the same machinery into serpentine motion.

    Two things here are measured rather than assumed, both for reasons this
    skill has already been bitten by:

    - Which local axis bends a bone sideways is PROBED per bone. The chain
      branches at the middle and its two halves run in opposite directions, so
      one half needs the opposite sign for the same world-space bend. This is
      the elbow-and-knee problem wearing a different hat.
    - The wave has to actually TRAVEL. A standing wave animates beautifully and
      moves the creature nowhere, which is precisely the kind of failure that
      looks like success.

    Speed comes from the serpentine model: a snake slides along its own track,
    so while the wave sweeps one wavelength backward along the body, the body
    advances by that wavelength's straight-line extent. That is a different
    derivation from the legged clips' stride, deliberately - a stride means
    nothing to something with no feet.
    """
    rig = bpy.data.objects.get(rig_name)
    if rig is None or rig.type != "ARMATURE":
        return {"error": "no armature named " + repr(rig_name)}

    chain = list(bones) if bones else spine_chain(rig_name, forward=forward)
    chain = [b for b in chain if b in rig.pose.bones]
    if len(chain) < min_bones:
        return {"error": "no spine to undulate: %d usable bones, need %d. A body "
                         "with neither legs nor a chain does not move."
                         % (len(chain), min_bones)}

    lat = _lateral_index(forward, up)
    fidx = AXIS_INDEX[forward[-1].upper()]
    fsign = -1.0 if forward.startswith("-") else 1.0

    # Arc position of each bone, 0 at the head and 1 at the tail. Measured along
    # the body rather than by index, so uneven bone lengths do not skew the wave.
    heads = [Vector(rig.data.bones[b].head_local) for b in chain]
    s_map = _arc_positions(rig, chain, fidx, fsign)
    s = [s_map[b] for b in chain]
    # Re-order by arc position so the wave is written along the body, not in
    # whatever order the bones happened to be ranked.
    order = sorted(range(len(chain)), key=lambda i: s[i])
    chain = [chain[i] for i in order]
    s = [s[i] for i in order]

    # Probe every bone for the axis that bends it sideways.
    axes = {}
    for b in chain:
        pr = verify.probe_bone_axis(rig_name, b, forward=forward, up=up)
        if "error" in pr:
            return {"error": "axis probe failed for %s: %s" % (b, pr["error"])}
        best = max(pr["axes"], key=lambda a: abs(pr["axes"][a]["delta"][lat]))
        d = pr["axes"][best]["delta"][lat]
        if abs(d) < 1e-6:
            return {"error": "bone %s does not bend laterally on any axis" % b}
        axes[b] = (best, 1.0 if d > 0 else -1.0)

    scene = bpy.context.scene
    if fps:
        scene.render.fps = fps
    if rig.animation_data is None:
        rig.animation_data_create()
    action = _fresh_action(rig, action_name)
    action_name = action.name
    rig.animation_data.action = action
    verify.clear_pose(rig)

    def axis_quat(axis, degrees):
        e = [0.0, 0.0, 0.0]
        e[AXIS_INDEX[axis]] = math.radians(degrees)
        return Euler(e, "XYZ").to_quaternion()

    keys = list(range(1, frames + 2))          # frame frames+1 repeats frame 1
    for f in keys:
        t = ((f - 1) % frames) / float(frames)
        for i, b in enumerate(chain):
            # Phase lags with distance along the body, so the wave is born at
            # the head and travels backward - which is what pushes forward.
            phase = 2.0 * math.pi * (t - wavelengths * s[i])
            # Amplitude grows from the head and then PLATEAUS. Letting it climb
            # all the way to the tail stacks the envelope on top of the
            # compounding every chain already has - each bone inherits its
            # parent's rotation - and the last bones crack like a whip, swinging
            # further than the body is wide. Real undulators build amplitude
            # over the front half and hold it.
            envelope = head_damping + (1.0 - head_damping) * min(1.0, s[i] / 0.6)
            axis, sign = axes[b]
            deg = math.sin(phase) * amplitude_degrees * envelope * sign
            pb = rig.pose.bones[b]
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = axis_quat(axis, deg)
            pb.keyframe_insert("rotation_quaternion", frame=f)

    for fc in _fcurves(action):
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
    verify.adopt_rotation_modes(rig, action)

    # Straight-line extent of the body while the wave is fully developed.
    scene.frame_set(1 + frames // 4)
    bpy.context.view_layer.update()
    pts = [rig.matrix_world @ rig.pose.bones[b].head for b in chain]
    extent = max(p[fidx] for p in pts) - min(p[fidx] for p in pts)
    rest_extent = (max(h[fidx] for h in heads) - min(h[fidx] for h in heads)) or 1.0

    fps_now = scene.render.fps
    cycle_s = frames / float(fps_now)
    playback_s = (frames + 1) / float(fps_now)
    speed_cycle = (extent / wavelengths) / cycle_s
    speed_playback = (extent / wavelengths) / playback_s

    check = verify.check_clip(rig_name, action_name, [chain[-1], chain[0]],
                             floor=floor, up=up, forward=forward,
                             tolerance=0.02 * max(rig.dimensions))
    scene.frame_set(1)

    return {
        "rig": rig_name,
        "action": action_name,
        "gait": "undulate",
        "mode": "lateral",
        "bones": len(chain),
        "chain": chain,
        "frames": frames,
        "wavelengths": wavelengths,
        "amplitude_degrees": amplitude_degrees,
        "axes": {b: ("+" if axes[b][1] > 0 else "-") + axes[b][0] for b in axes},
        "body_extent_m": round(extent, 4),
        "shortening": round(1.0 - extent / rest_extent, 4),
        "implied_speed_playback_mps": round(speed_playback, 4),
        "implied_speed_cycle_mps": round(speed_cycle, 4),
        "verification": check,
    }
