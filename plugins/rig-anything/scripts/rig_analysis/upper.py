"""The upper body of a walking biped: trunk rotation, arm swing, a steady head.

`locomotion.cycle` places the feet and the hips. Everything above them used to
be left at rest - arms held out in the rig's A-pose, the chest locked to the
pelvis - or was keyed over the finished clip by per-project scripts that fitted
a sine to the feet and rotated bones by name. This module is the same motion
written the way the rest of the package is: as terms of each key, from the
gait's own phases, posed in the body map's frame, with every clip still played
back and checked.

WHAT MOVES (all sign-free: senses come from the body map's axes and which side
each leg sits on, never from a bone's roll)

- pelvis turn: the hip over the forward foot goes forward (about `up`)
- pelvis list: the hip over the loaded leg rises, the swing side drops (about
  `fwd`); the pelvis pivots on the loaded hip, so the stance leg reaches no
  further than it did
- thorax turn: the chest turns against the pelvis, and the shoulders against
  the hips
- side bend: the trunk leans over the stance leg (a waddle, when large),
  against the pelvis, which lifts that hip
- lean and lean_bob: a held forward trunk lean, and a pitch twice a stride
  timed off each footstrike (`footstrike`, `lean_lag`)
- head nod: the head keeps a little of the held lean, none of the bob, and
  pitches to hold its gaze on a point `gaze_m` ahead as the body rises and falls
- head hold: the neck and head take back that share of the trunk's turn and
  roll, so the head keeps its orientation toward the world - and
  they take it back LATE, reading the same drive `head_lag` of a cycle behind
  the thorax as the thorax reads it behind the pelvis. That is the last rung
  of the lag ladder, and `head_frequency` measures the segment it belongs to
- arm swing: each arm swings opposite its own side's leg, the forward swing
  the larger, and the elbow bends further as the arm comes forward
- shoulder girdle: each shoulder DROPS as its own side takes the body's weight,
  and swings forward with its own arm. The girdle hangs off the axial chain
  rather than sitting on it, so `Key.trunk` cannot reach it - it is posed by
  `motion.Body.turn_bone` through `Key.girdle`, before the arms are solved, so
  each arm rides its shoulder instead of being left behind by it

ARMS are positions, like legs. Each arm's direction is built against GRAVITY
and the body's heading - hanging `arm_out` degrees out from vertical, swung
forward about the lateral axis - not in the chest's frame, so a hunched body's
arms hang in front of it instead of swinging behind. The hand is placed from
the shoulder along that direction and a forearm bent `elbow` degrees in the
arm's own bend plane (measured from its rest shape, so a rig whose forearm
rests bent and one whose arm rests straight both bend forward), and the IK is
given the elbow that geometry implies as its pole. `arm_out` left as None is
measured: the least abduction that keeps the forearm and hand skin
`hand_clearance` off the hips and thighs through the swing.

Parameters are degrees and metres; `defaults(froude, duty)` scales them with
speed - a walk subtle, a run with bent elbows and a big swing.
"""

from __future__ import annotations

import math

from mathutils import Vector

# Every parameter `cycle(upper=...)` and `idle(upper=...)` take.
PARAMS = ("arm_swing", "arm_forward", "arm_out", "elbow", "elbow_swing", "hand_in",
          "pelvis_turn", "pelvis_list", "thorax_turn", "side_bend", "lean", "lean_bob",
          "lean_lag", "head_hold", "gaze_m", "hand_clearance", "breath",
          "girdle_drop", "girdle_forward", "girdle_lag",
          "trunk_hz", "trunk_damping", "arm_lag", "hand_lag", "head_lag", "limb_damping")


# The relaxed finger curl rides the arm swing (`Upper.cycle_key`): its share
# goes 1 -+ HAND_SWING, HAND_LAG of a cycle behind the arm.
HAND_LAG = 0.08
HAND_SWING = 0.25

# The share of the held trunk lean the head keeps - 1 - the 0.85 `head_hold`
# every axis used to share. The lean is a posture, not a motion, so it keeps
# its old number while the turn's share moves with speed.
HEAD_LEAN_KEEP = 0.15


def response(drive_hz, natural_hz, damping):
    """(gain, lag as a fraction of a cycle) of a damped second-order system
    driven at `drive_hz`.

    The standard driven-oscillator transfer function, and the reason it is here
    rather than a tuned constant: a segment hung on the one below it does not
    copy its parent, it CHASES it, and how far behind it runs depends on how
    fast it is being driven relative to its own natural frequency.

        r = drive / natural
        lag  = atan2(2 z r, 1 - r^2)      0 at r << 1, pi/2 at r = 1, pi at r >> 1
        gain = 1 / sqrt((1 - r^2)^2 + (2 z r)^2)

    That one expression is why a walking body's thorax and pelvis are near
    IN-phase at a slow walk and move toward ANTI-phase as speed rises (van
    Emmerik et al.): nothing changes about the body, only how fast it is being
    driven. Written as `-k x pelvis` it cannot do that at either end, and
    measured off our own clips it came out -179.3 degrees at every speed from
    0.92 to 4.59 m/s - a flat line where the real thing sweeps.

    A lag in TIME is a speed-dependent offset in PHASE, and the cycle is
    already evaluated per phase, so spending it costs nothing: evaluate the
    driver at `p0 - lag` instead of at `p0`.
    """
    if natural_hz <= 0.0 or drive_hz <= 0.0:
        # Nothing known about the drive: fall back to the hard anti-phase this
        # replaces, which is the r >> 1 limit of the same expression.
        return 1.0, 0.5
    r = drive_hz / float(natural_hz)
    denom = 1.0 - r * r
    num = 2.0 * damping * r
    lag = math.atan2(num, denom)          # num >= 0, so this lands in 0..pi
    gain = 1.0 / math.sqrt(denom * denom + num * num)
    return gain, lag / (2.0 * math.pi)


def _twist(m, rest, axis):
    """Signed angle of `m` about `axis` relative to `rest` (swing-twist)."""
    q = (m.to_3x3() @ rest.to_3x3().inverted()).to_quaternion()
    p = Vector((q.x, q.y, q.z)).dot(axis)
    w = q.w
    if w < 0.0:
        p, w = -p, -w
    return 2.0 * math.atan2(p, w)


def _fundamental(xs):
    """(amplitude, phase in degrees) of the once-per-cycle component."""
    n = len(xs)
    if n < 2:
        return 0.0, 0.0
    re = sum(x * math.cos(-2.0 * math.pi * i / n) for i, x in enumerate(xs)) * (2.0 / n)
    im = sum(x * math.sin(-2.0 * math.pi * i / n) for i, x in enumerate(xs)) * (2.0 / n)
    return math.hypot(re, im), math.degrees(math.atan2(im, re))


def _segment_twists(body, bm, evaluated, frames, name):
    """The once-per-cycle (amplitude, phase) of one bone's rotation about `up`,
    read off the BAKED clip, or None."""
    rest = body.rest
    if not name or name not in rest:
        return None
    up = bm["up_vec"]
    xs = []
    for f in range(1, frames + 1):
        ev = evaluated.get(f)
        if not ev or name not in ev:
            return None
        xs.append(_twist(ev[name], rest[name], up))
    amp, ph = _fundamental(xs)
    return None if amp < 1e-6 else (amp, ph)


def _lead(a, b):
    """b's phase relative to a's, wrapped to +-180."""
    return round(((b - a + 180.0) % 360.0) - 180.0, 1)


def relative_phase(body, bm, evaluated, frames):
    """The axial chain's relative phases in the transverse plane, in degrees,
    read off the BAKED clip - Blender's own matrices, never the prediction.

    Returns {"pelvis_thorax_phase_deg", "thorax_head_phase_deg"}, each present
    only when both of its segments turn: the relative Fourier phase the gait
    literature reports, the once-per-stride component of each segment's
    rotation about `up`, the later segment minus its driver, wrapped to +-180.
    0 is the two turning together, +-180 is dead against each other.

    The chain is a LADDER: the legs drive the pelvis, the pelvis drives the
    thorax, the thorax drives the head, and each rung is a mass hung on the one
    below it that arrives late. Healthy walking runs from near in-phase at a
    slow walk toward anti-phase as speed rises, so a clip set that reports the
    SAME number at every speed is the thing this measures against - it is what
    caught the thorax at a flat -179.3, and the head rung was found the same
    way.

    {} when the body map names none of the pairs.
    """
    roles = bm.get("roles") or {}
    pelvis, chest = roles.get("pelvis"), roles.get("chest")
    head = bm.get("head") or (bm.get("neck") or [None])[-1]
    got = {}
    p = _segment_twists(body, bm, evaluated, frames, pelvis) if pelvis else None
    t = (_segment_twists(body, bm, evaluated, frames, chest)
         if chest and chest != pelvis else None)
    h = (_segment_twists(body, bm, evaluated, frames, head)
         if head and head not in (pelvis, chest) else None)
    if p and t:
        got["pelvis_thorax_phase_deg"] = _lead(p[1], t[1])
    if t and h:
        got["thorax_head_phase_deg"] = _lead(t[1], h[1])
    return got


def limb_frequencies(poser):
    """{arm: {"arm": Hz, "hand": Hz}} from the body's own measured mass.

    The arm swinging about its shoulder and the hand about its wrist, both
    about the body's lateral axis, both under gravity. Measured once and cached
    on the body, because a character builds several clips and the answer is a
    property of the body, not of the clip.

    {} when the body carries no skinned mass to measure - a rig with no mesh
    bound, say - and every caller then falls back to the constants that were
    set by hand.
    """
    body = poser.body
    cached = body.__dict__.get("_limb_hz")
    if cached is not None:
        return cached
    out = {}
    try:
        from . import mass as mass_mod
        data = mass_mod.body_mass(body)
        if data and "error" not in data:
            bones = body.rig.data.bones
            lat = poser.lat

            def carried(root):
                got, stack = [], [bones[root]]
                while stack:
                    b = stack.pop()
                    got.append(b.name)
                    stack.extend(b.children)
                return got

            for arm in poser.arms:
                entry = {}
                upper_bone = arm["upper"]
                if upper_bone in bones:
                    entry["arm"] = mass_mod.pendulum(
                        data, body.rig, carried(upper_bone),
                        bones[upper_bone].head_local, lat)
                end = arm.get("end")
                if end and end in bones:
                    entry["hand"] = mass_mod.pendulum(
                        data, body.rig, carried(end), bones[end].head_local, lat)
                out[arm["name"]] = {k: v for k, v in entry.items() if v}
    except Exception:
        out = {}
    body.__dict__["_limb_hz"] = out
    return out


def head_frequency(poser):
    """The natural frequency, in Hz, of what the axial chain carries at its top
    - the neck and everything above it - swinging about the body's lateral axis
    through the base of the neck. `mass.pendulum` on measured mass, cached on
    the body; None when nothing up there carries any.

    WHAT THE NUMBER IS, AND WHAT IT IS NOT. `mass.pendulum` returns
    sqrt(m g d / I) / 2pi, and it reads `d` as a distance, unsigned. For
    something that HANGS - everything `limb_frequencies` measures - the centre
    of mass is below its pivot, gravity restores, and that is a resonance. What
    the top of an upright chain carries sits ABOVE its pivot (measured: 0.19 m
    on the lofted study body, 0.14 m on an MPFB one), so gravity there
    destabilises instead, and the same expression is a divergence rate rather
    than a free oscillation. The restoring stiffness is the neck's, and nobody
    has that number - the same gap that leaves `trunk_hz` fitted.

    It is still the right number to reach for, and the reason is that it is the
    only one here that is MEASURED. Its size lands where the real thing does -
    0.91 Hz on a 9.2 kg lofted top, 1.09 Hz on a 4.1 kg MPFB one, two bodies
    that share no geometry - and a stride runs at 0.8 to 2 Hz, so the ratio
    `response` needs sits in the interesting part of the curve instead of
    pinned at either limit. Set `head_lag` to override it with a number, and
    `head_lag=0.0` is the locked top this replaces.
    """
    body = poser.body
    cached = body.__dict__.get("_head_hz")
    if cached is not None:
        return cached or None
    hz = None
    try:
        from . import mass as mass_mod
        bm = poser.bm
        chain = list(bm.get("neck") or [])
        root = chain[0] if chain else bm.get("head")
        data = mass_mod.body_mass(body)
        bones = body.rig.data.bones
        if root and root in bones and data and "error" not in data:
            carried, stack = [], [bones[root]]
            while stack:
                b = stack.pop()
                carried.append(b.name)
                stack.extend(b.children)
            hz = mass_mod.pendulum(data, body.rig, carried,
                                   bones[root].head_local, poser.lat)
    except Exception:
        hz = None
    body.__dict__["_head_hz"] = hz or 0.0
    return hz


def _smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def defaults(froude, duty):
    """Upper-body parameters for a gait at this Froude number.

    From walking and running kinematics: the shoulders swing about 15-20
    degrees each way walking and about 25 running; a running arm swings about
    a line 15 degrees behind hanging - 40 back, 14 forward - with the elbow
    held near 85 degrees the whole way, so the forearm never rises past level
    and the hand travels from beside the hip to the lower chest. With the swing
    centred the forward upper arm reached 30 degrees, the forearm pointed above
    level and read as a straight arm thrown out with the hand at the neck, and
    the back hand stayed in front of the body; the pelvis turns ~4 degrees each way walking and ~9 running,
    the thorax less and against it; the pelvis lists ~4 walking; the trunk
    leans 2-3 degrees walking and ~8 running."""
    u = math.sqrt(max(froude, 0.0))
    running = duty < 0.5
    run = _smooth((froude - 0.3) / 0.9)       # 0 walking .. 1 running
    return {
        "arm_swing": max(4.0, min(25.0, 6.0 + 22.0 * u)),
        "arm_forward": 2.0 - 17.0 * run,
        "arm_out": None,
        "elbow": 15.0 + 70.0 * run,
        "elbow_swing": 8.0 * (1.0 - run),
        "hand_in": 5.0 * _smooth((froude - 0.5) / 1.0),
        "pelvis_turn": 2.0 + 5.0 * min(u, 1.4),
        # The frontal plane RISES with speed. Pelvic obliquity is ~9.5 deg peak-to-
        # peak walking at 5 km/h and 14.5 / 22.4 running at 10 / 15 km/h (Ruiz-
        # Malagon et al. 2023, Table 1), 8-16 running (Perpina-Martinez et al.
        # 2023); the lab-frame trunk tilts over the STANCE leg, 3 deg slow to 10
        # running (Thorstensson et al. 1984). These were 4 walking falling to 3
        # running, and a flat 1.5 toward the swing side. Taken at the low end of
        # the running range: the spread is wide and skin markers read spines large.
        "pelvis_list": 4.5 + 1.5 * run,
        "thorax_turn": 1.5 + 4.0 * min(u, 1.4),
        "side_bend": 2.0 + 2.0 * run,
        "lean": 1.0 + 5.0 * min(u, 1.5),
        # The trunk's twice-a-stride pitch, timed off footstrike: ~2-3 deg peak-to-
        # peak walking with the forward peak at the start of support, ~5 running
        # with the BACKWARD peak at footstrike (Thorstensson et al. 1984). `lean_lag`
        # is where the forward peak sits after each footstrike, in cycles: 0 at a
        # walk, a quarter (the next trough past the strike) at a run.
        "lean_bob": 1.25 + 1.25 * run,
        "lean_lag": 0.25 * run,
        # How much of the thorax's turn and roll the head takes back, so the gaze
        # holds. The head keeps ~64% of the shoulders' yaw walking (5.2 of 8.1 deg)
        # and ~26% running (6.1 of 23.8), world frame (Pontzer et al. 2009): it
        # holds more the faster the trunk turns. This was a flat 0.85 - 15% kept at
        # every speed, a head read as locked.
        "head_hold": 0.35 + 0.4 * run,
        # The head's nod is not a share of the trunk's: it holds the eyes on a point
        # about a metre ahead while the body rises and falls, so it pitches up as
        # the head drops (Hirasaki et al. 1999; ~1 m at 1.67 m/s, Moore et al. 1999).
        # Metres to that point; None is no nod, the head riding the held lean alone.
        "gaze_m": 1.0,
        "hand_clearance": 0.015,
        "breath": 0.0,
        # The shoulder girdle. Tied to `arm_swing` rather than given its own
        # speed curve, so a style that damps the arms damps the shoulders with
        # them: the shoulder carries roughly a fifth of the arm's fore-aft
        # excursion. The drop is what reads as "shoulders drop when you walk" -
        # a couple of degrees on a clavicle is about a centimetre at the
        # shoulder, which is the size of the real thing. PROVISIONAL numbers:
        # they are the right shape and an eye, not a measurement, set them - the
        # motion critic (04) is what should settle them.
        "girdle_drop": 2.5 + 3.5 * run,
        "girdle_forward": 0.22 * max(4.0, min(25.0, 6.0 + 22.0 * u)),
        # Fraction of a cycle the girdle trails its driver. A shoulder is a mass
        # hung on the ribcage, so it arrives late; HAND_LAG is the same idea one
        # joint further out, and is larger because it is further out. Also
        # PROVISIONAL: 07's L1 derives every lag on the chain from segment
        # inertia instead, and should take this with it.
        "girdle_lag": 0.05,
        # The trunk as a mass on the pelvis. FITTED, not measured: chosen so the
        # pelvis-thorax relative phase sweeps the way van Emmerik et al. report
        # it - near in-phase at a slow walk, close to anti-phase by running -
        # given the stride frequencies this package produces. The damping sets
        # how sharply it turns over. A real derivation would be trunk inertia
        # (0.28.0's mass model has it) on the spine's torsional stiffness, which
        # is the number nobody has.
        "trunk_hz": 0.82,
        "trunk_damping": 0.35,
        # The HAND's lag is derived from the body's own mass, as a gravity
        # pendulum about the wrist (`mass.pendulum` -> `response`); None asks
        # for that. It lands near 0.10 of a cycle against the 0.08 that used to
        # be written here by hand, which is the physics agreeing with the eye.
        #
        # The ARM's is NOT derived, and the reason is measured rather than
        # argued. Treating the arm as a pendulum driven by its own leg's signal
        # gives 0.33 of a cycle at a walk, and swept against whole-body angular
        # momentum - `mass.angular_momentum`, the thing arms are FOR - it comes
        # out worse than the half cycle it would replace on both measures
        # (mean |L| 0.0118 against 0.0095; the range is flat within 2% across
        # 0.30..0.50). Half a cycle sits at the optimum, which is what the
        # biomechanics says: the arms are there to cancel the legs. The real
        # speed dependence is not a phase lag inside 1:1 anyway - it is a
        # transition from 2:1 to 1:1 between arm and leg near the arm's own
        # resonance (Wagenaar & van Emmerik 2004), which is a different and
        # much larger change. Set a number here to explore it.
        "arm_lag": 0.5,
        "hand_lag": None,
        # The top of the axial chain's lag, as a fraction of a cycle. None
        # derives it - `head_frequency` measures the segment, `response` turns
        # that into a phase - which is what makes the last rung of the ladder
        # move with speed instead of reading the same number at every one. A
        # number here overrides it; 0.0 is the locked top this replaces, and is
        # the control.
        "head_lag": None,
        "limb_damping": 0.30,
    }


def idle_defaults():
    """Arms relaxed down by the sides: a little forward, elbows soft."""
    return {
        "arm_swing": 0.0, "arm_forward": 4.0, "arm_out": None, "elbow": 12.0,
        "elbow_swing": 0.0, "hand_in": 0.0, "pelvis_turn": 0.0, "pelvis_list": 0.0,
        "thorax_turn": 0.0, "side_bend": 0.0, "lean": 0.0, "lean_bob": 0.0, "lean_lag": 0.0,
        "head_hold": 0.85, "gaze_m": None, "hand_clearance": 0.015,
        # degrees the arms drift with each breath
        "breath": 1.0,
        # nothing is carrying weight and no arm is swinging, so the shoulders
        # sit where the rig put them
        "girdle_drop": 0.0, "girdle_forward": 0.0, "girdle_lag": 0.0,
        # an idle has no stride to be driven at, so no coupling runs
        "trunk_hz": 0.82, "trunk_damping": 0.35,
        "arm_lag": 0.5, "hand_lag": None, "head_lag": None, "limb_damping": 0.30,
    }


def resolve(poser, upper, base):
    """The parameter dict to use, or None for no upper body.

    upper None   on for an upright two-legged body; its arms move if it has any
    upper False  off
    upper True   on, with `base`
    upper dict   on, `base` with these laid over it
    """
    if upper is False:
        return None
    if upper is None:
        if not (poser.bm["upright"] and len(poser.legs) == 2):
            return None
        upper = {}
    if upper is True:
        upper = {}
    unknown = set(upper) - set(PARAMS)
    if unknown:
        raise ValueError("unknown upper-body parameter %s - upper takes %s"
                         % (", ".join(sorted(unknown)), ", ".join(PARAMS)))
    out = dict(base)
    out.update(upper)
    return out


# --------------------------------------------------------------------------
# signals from the gait
# --------------------------------------------------------------------------

def _side(poser, limb):
    """+1 or -1: which side of the midline a limb hangs, along `lat`."""
    return 1.0 if (limb["rest_root"] - poser.centre).dot(poser.lat) > 0.0 else -1.0


def leg_forward(ph, duty):
    """+1 with the foot furthest forward, -1 furthest back, at a leg's phase
    (0 = touchdown). Crosses zero moving back at mid-stance, where the foot
    passes under its hip - the moment an arm passes its shoulder."""
    return -math.sin(2.0 * math.pi * (ph - 0.5 * duty))


def leg_load(ph, duty):
    """0..1 share of the body a leg carries, peaking at mid-stance."""
    return math.sin(math.pi * ph / duty) if ph < duty else 0.0


def strike_pulse(ph, lag, width):
    """0..1: one leg's footstrike, a raised cosine peaking `lag` of a cycle
    after its touchdown (ph = 0) and `width` of a cycle either side of that.

    This is the signal the trunk's flexion and the head's nod share, so they
    are timed off the same event rather than each off a phase of its own."""
    x = (ph - lag + 0.5) % 1.0 - 0.5
    return 0.5 * (1.0 + math.cos(math.pi * x / width)) if abs(x) < width else 0.0


def footstrike(at, offsets, legs, lag, width=0.25):
    """The body's footstrike signal at cycle phase `at`: every leg's
    `strike_pulse` summed, its mean taken out, scaled so a biped reads -1..+1.

    Zero-mean, so a held lean stays the lean it was asked for. For two legs half
    a cycle apart and `width` 0.25 the pulses tile the cycle and the sum is
    exactly cos(4 pi (at - lag)) - the twice-a-stride curve `lean_bob` used to
    be written as, now placed after each footstrike instead of on it. With `lag`
    0 it is that curve to the last digit, which is the control."""
    if not legs:
        return 0.0
    s = sum(strike_pulse((at - offsets[l["name"]]) % 1.0, lag, width) for l in legs)
    mean = width * len(legs)                  # a raised cosine's mean over the cycle
    return 2.0 * (s - mean) * (2.0 / len(legs))


# --------------------------------------------------------------------------
# the trunk
# --------------------------------------------------------------------------

def trunk(poser, pelvis_yaw, pelvis_roll, thorax_yaw, thorax_roll, pitch, head_hold,
          head=None):
    """Per axial bone totals {"pitch", "yaw", "roll"} for `Key.trunk`.

    The pelvis (and anything behind it) takes the pelvis values, the torso
    ramps to the thorax values by its top, and the neck and head hand back
    `head_hold` of it by the head. `pitch` is carried by the torso only, ramped
    the same way.

    `head` is the TOP of the chain's own drive - {"yaw", "roll", "pitch"} read
    wherever its own phase puts it - and it is the reason this takes a signal
    instead of a scalar. Handing the top back a share of its driver's VALUE, as
    this did, can only ever put it in phase with that driver: a value carries an
    amplitude and nothing else, and the measured head phase came out flat at
    every speed because of it. Given its own values, the top can read the same
    drive one rung later, and one `response` call then supplies the lag.

    None keeps the old behaviour exactly - the top reads its driver's value -
    which is what every caller with nothing to say about phase (the idle) wants,
    and is the control this change is measured against."""
    bm = poser.bm
    names = bm["axial"]
    n = len(names)
    out = {"pitch": [0.0] * n, "yaw": [0.0] * n, "roll": [0.0] * n}
    if n == 0:
        return out
    p = bm["pelvis_index"]
    torso = sorted(names.index(x) for x in bm["torso"])
    top_i = sorted(names.index(x) for x in bm["neck"])
    if bm["head"]:
        top_i.append(names.index(bm["head"]))
    last = max([i for i in torso if i >= p] or [p])
    ends = {"yaw": (pelvis_yaw, thorax_yaw), "roll": (pelvis_roll, thorax_roll),
            "pitch": (0.0, pitch)}
    for i in range(n):
        if i <= p:
            f = 0.0
        elif i <= last:
            f = (i - p) / float(max(last - p, 1))
        else:
            f = 1.0
        for k, (a, b) in ends.items():
            out[k][i] = a + (b - a) * f
    top = ends if head is None else {k: (0.0, head.get(k, ends[k][1])) for k in ends}
    # one share for every axis, or {"yaw", "roll", "pitch"}: the gaze holds the
    # turn and the roll, while the pitch is a nod of the head's own
    hold = head_hold if isinstance(head_hold, dict) else dict.fromkeys(out, head_hold)
    for j, i in enumerate(top_i):
        w = (j + 1) / float(len(top_i))
        for k in out:
            # from the driver's own value at the base of the neck to the head's
            # own, held back by `head_hold`, at the top
            far = top[k][1] * (1.0 - hold[k])
            out[k][i] = ends[k][1] + (far - ends[k][1]) * w
    return out


# --------------------------------------------------------------------------
# arms
# --------------------------------------------------------------------------

def _bend_plane(poser, limb):
    """(forward share, outward share) of the direction a forearm folds, read
    from the arm's rest shape in a frame of (arm, heading, outward). A straight
    rest arm folds straight forward."""
    fwd = poser.fwd
    out = poser.outward(limb)
    u = (limb["rest_eff"] - limb["rest_root"]).normalized()
    if limb["pole_source"] != "rest shape" or limb["rest_dev"].length < 1e-9:
        return 1.0, 0.0
    hand_side = -limb["rest_dev"].normalized()
    f = fwd - u * fwd.dot(u)
    if f.length < 0.3:
        return 1.0, 0.0
    f.normalize()
    o = out - u * out.dot(u) - f * out.dot(f)
    cf = hand_side.dot(f)
    co = hand_side.dot(o.normalized()) if o.length > 0.5 else 0.0
    if cf < 0.5:
        # a rest bend that folds sideways or back is not an elbow's; the rig's
        # rest pose says nothing useful about walking, so fold forward
        return 1.0, 0.0
    ln = math.hypot(cf, co)
    return cf / ln, co / ln


def arm_geometry(poser, limb, forward, out, elbow, hand_in=0.0):
    """(upper-arm direction, forearm direction, elbow pole) in armature space.

    forward  degrees the upper arm is swung forward of hanging, about `lat`
    out      degrees it hangs out from vertical, away from the midline
    elbow    degrees of elbow flexion, 0 straight
    hand_in  degrees the forearm turns toward the midline"""
    up, fwd = poser.up, poser.fwd
    outward = poser.outward(limb)
    ab, fl = math.radians(out), math.radians(forward)
    down = -up
    d = (down * (math.cos(ab) * math.cos(fl)) + fwd * (math.cos(ab) * math.sin(fl))
         + outward * math.sin(ab)).normalized()
    cf, co = _bend_plane(poser, limb)
    f = fwd - d * fwd.dot(d)
    if f.length < 1e-6:
        f = up - d * up.dot(d)
    f.normalize()
    o = outward - d * outward.dot(d) - f * outward.dot(f)
    o = o.normalized() if o.length > 1e-6 else d.cross(f).normalized()
    hi = math.radians(hand_in)
    fold = (f * cf + o * co)
    fold = (fold * math.cos(hi) - o * math.sin(hi)).normalized()
    el = math.radians(max(elbow, 2.0))
    e = (d * math.cos(el) + fold * math.sin(el)).normalized()
    a, b = limb["a"], limb["b"]
    w = (d * a + e * b)
    wn = w.normalized()
    mid = d * a
    pole = mid - wn * mid.dot(wn)
    return d, e, pole.normalized()


def arm_spec(poser, limb, forward, out, elbow, hand_in=0.0):
    """A `Key` limb spec putting the hand where `arm_geometry` says, from
    wherever the shoulder is this frame."""
    d, e, pole = arm_geometry(poser, limb, forward, out, elbow, hand_in)
    offset = d * limb["a"] + e * limb["b"]

    def target(p, l, posed, offset=offset):
        return posed[l["upper"]].translation + offset
    return {"target": target, "pole": pole, "planted": False,
            "arm": (forward, out, elbow, hand_in)}


# --------------------------------------------------------------------------
# keeping hands off the body
# --------------------------------------------------------------------------

def _clearance_setup(poser):
    """Body triangles and vertices, and the forearm/hand vertices, each with
    their weights (armature space), cached on the body."""
    body = poser.body
    cache = body.__dict__.get("_upper_clearance")
    if cache is not None:
        return cache
    import bpy
    from mathutils.bvhtree import BVHTree
    from . import verify
    rig, bm = poser.rig, poser.bm
    reach, trunk_bones = verify.clearance_bones(rig, bm, poser.arms)
    to_arm = rig.matrix_world.inverted()
    body_pts, tris, limb_v = [], [], []
    for ob in verify.clearance_meshes(rig):      # the skin, not a garment over it
        m = to_arm @ ob.matrix_world
        names = {g.index: g.name for g in ob.vertex_groups}
        index = {}
        for v in ob.data.vertices:
            co = m @ v.co
            ws = [(names.get(g.group), g.weight) for g in v.groups
                  if g.weight > 0.0 and names.get(g.group) in body.rest]
            tot = sum(w for _, w in ws)
            if tot <= 0.0:
                continue
            n, w = max(ws, key=lambda nw: nw[1])
            if n in reach and w / tot > 0.6:
                limb_v.append((co, [(k, x / tot) for k, x in ws], n))
            elif n in trunk_bones and w / tot > 0.5:
                index[v.index] = len(body_pts)
                body_pts.append((co, [(k, x / tot) for k, x in ws]))
        for poly in ob.data.polygons:
            if all(i in index for i in poly.vertices):
                tris.append(tuple(index[i] for i in poly.vertices))
    cache = None
    if tris and limb_v:
        cache = {"body": body_pts, "tris": tris, "limb": limb_v[::2], "BVHTree": BVHTree}
    body._upper_clearance = cache
    return cache


def _skinned(body, posed, pts, deform):
    out = []
    for co, ws in pts:
        p = Vector((0.0, 0.0, 0.0))
        for n, w in ws:
            if n not in deform:
                deform[n] = posed[n] @ body.rest[n].inverted()
            p += (deform[n] @ co) * w
        out.append(p)
    return out


def arm_clearance(poser, posed, limbs=None):
    """Closest (signed, armature units) that the forearm and hand skin of
    `limbs` comes to the trunk and thighs, both skinned as `posed` - the
    same linear blend Blender does. Negative is inside. None when there is no
    skin to measure."""
    cache = _clearance_setup(poser)
    if cache is None:
        return None
    from . import verify
    names = None
    if limbs is not None:
        names = verify.clearance_bones(poser.rig, poser.bm, limbs)[0]
    body = poser.body
    deform = {}
    bvh = cache["BVHTree"].FromPolygons(_skinned(body, posed, cache["body"], deform),
                                        cache["tris"])
    worst = float("inf")
    for co, ws, top in cache["limb"]:
        if names is not None and top not in names:
            continue
        p = _skinned(body, posed, [(co, ws)], deform)[0]
        hit = bvh.find_nearest(p)
        if hit[0] is None:
            continue
        worst = min(worst, verify.signed_gap(p, hit))
    return None if worst == float("inf") else worst


def clear_out(poser, limb, poses, margin, posture=None, stance=None, limit=45.0):
    """The least `out` (degrees from vertical) that keeps this arm's forearm
    and hand `margin` (metres) off the body in every one of `poses`, a list of
    (forward, elbow, hand_in). Measured with the trunk held in `posture` and
    the legs in `stance` ({leg name: spec}); None if there is no skin."""
    from . import keyposes as kp
    scale = sum(poser.rig.matrix_world.to_scale()) / 3.0
    want = margin / scale
    if _clearance_setup(poser) is None:
        return None
    memo = {}

    def gap(out):
        if out not in memo:
            worst = float("inf")
            for forward, elbow, hand_in in poses:
                limbs = dict(stance or {})
                limbs[limb["name"]] = arm_spec(poser, limb, forward, out, elbow, hand_in)
                posed, _ = poser.pose(kp.Key(limbs=limbs, posture=posture))
                g = arm_clearance(poser, posed, [limb])
                if g is not None:
                    worst = min(worst, g)
            memo[out] = worst
        return memo[out]

    if gap(0.0) >= want:
        return 0.0
    lo, hi = 0.0, limit
    if gap(hi) < want:
        return limit
    for _ in range(7):
        mid = 0.5 * (lo + hi)
        if gap(mid) >= want:
            hi = mid
        else:
            lo = mid
    return round(hi, 1)


# --------------------------------------------------------------------------
# what cycle and idle call
# --------------------------------------------------------------------------

class Upper:
    """Resolved parameters for one clip, and the per-key terms they give."""

    def __init__(self, poser, params, posture=None, stance=None, running=False,
                 stride_hz=0.0, asym=None):
        self.P = poser
        self.params = dict(params)
        # This character's fixed left/right asymmetry (`variability.Asym`). None is the
        # identity: every gain exactly 1.0, every offset exactly 0.0, so a body that asks
        # for nothing is posed by the same arithmetic to the same numbers it always was.
        from . import variability as var_mod
        self.asym = asym if asym is not None else var_mod.IDENTITY
        # How fast the trunk is being driven: once per stride. With it, the
        # thorax's lag behind the pelvis comes from `response`; without it (an
        # idle, a one-shot action) the lag is the half-cycle that hard anti-
        # phase always was, and nothing changes.
        self.stride_hz = float(stride_hz or 0.0)
        self.trunk_gain, self.trunk_lag = response(
            self.stride_hz, self.params.get("trunk_hz", 0.0),
            self.params.get("trunk_damping", 0.35))
        # The arm and the hand are gravity pendulums, and the body has been
        # measured, so their natural frequencies are not parameters: the mass
        # model gives m, the lever arm and the inertia, and `mass.pendulum`
        # turns those into the frequency. A human arm lands near 0.9 Hz and a
        # hand near 1.6 Hz; at a walk's stride the hand's lag then comes out
        # about 0.10 of a cycle, against the 0.08 that was set here by eye -
        # which is the physics agreeing with whoever tuned it.
        self.limb_hz = limb_frequencies(poser)
        d = self.params.get("limb_damping", 0.30)
        # The last rung of the same ladder. The pelvis is driven by the legs,
        # the thorax chases the pelvis, and what the chain carries at its top
        # chases the thorax - measured the same way, by `head_frequency` on the
        # mass model rather than by a number set here. `head_lag` given wins;
        # 0.0 is the locked top this replaces, and is the control.
        # A body with nothing skinned has no frequency to measure, and
        # `response`'s own fallback is half a cycle - which is the right guess
        # for something hung BELOW its driver and the wrong one here, where what
        # is replaced is a locked top. Unmeasured keeps the locked top instead.
        self.head_hz = head_frequency(poser) or 0.0
        given = self.params.get("head_lag")
        self.head_lag = (given if given is not None
                         else (response(self.stride_hz, self.head_hz, d)[1]
                               if self.head_hz else 0.0))
        self.arm_lag, self.hand_lag = {}, {}
        for arm in poser.arms:
            hz = self.limb_hz.get(arm["name"]) or {}
            given = self.params.get("arm_lag")
            self.arm_lag[arm["name"]] = (
                given if given is not None else response(self.stride_hz, hz.get("arm", 0.0), d)[1])
            given = self.params.get("hand_lag")
            self.hand_lag[arm["name"]] = (
                given if given is not None
                else (response(self.stride_hz, hz.get("hand", 0.0), d)[1] if hz.get("hand")
                      else HAND_LAG))
        # Whether this clip is a run (duty < 0.5), for the arm checks: a run keeps both
        # arms in front and is judged on hand rise and elbow instead of the swing-through
        # -hanging a walk must show. Only the gait path knows it; idles and turns are False.
        self.running = bool(running)
        side_legs = {}
        for l in poser.legs:
            side_legs.setdefault(_side(poser, l), []).append(l)
        self.side_legs = side_legs
        self.outs = {}
        prm = self.params
        # how much the hips are apart, for pivoting the list on the loaded hip
        self.hip_half = (sum(abs((l["rest_root"] - poser.centre).dot(poser.lat))
                             for l in poser.legs) / max(len(poser.legs), 1))
        body = poser.body
        self.s_yaw = body.axis_turns(poser.up, poser.lat, poser.fwd)
        self.s_roll = body.axis_turns(poser.fwd, poser.lat, poser.up)
        for arm in poser.arms:
            if prm["arm_out"] is not None:
                self.outs[arm["name"]] = float(prm["arm_out"])
                continue
            sw = prm["arm_swing"] * self.asym.gain("arm_swing", _side(poser, arm))
            fw = prm["arm_forward"]
            el, es = prm["elbow"], prm["elbow_swing"]
            poses = [(fw, el, prm["hand_in"])]
            if sw:
                poses += [(fw - sw, el - es, 0.3 * prm["hand_in"]),
                          (fw + 1.25 * sw, el + es, prm["hand_in"])]
            got = clear_out(poser, arm, poses, prm["hand_clearance"], posture=posture,
                            stance=stance)
            self.outs[arm["name"]] = 10.0 if got is None else got
        self.params["arm_out_measured"] = {k: v for k, v in self.outs.items()}

    def arm_terms(self, arm, swing, breath=0.0):
        """Limb spec for one arm at a swing of -1 (back) .. +1 (forward)."""
        prm = self.params
        # This arm's own swing: the parameter times this side's fixed asymmetry gain (1.0
        # exactly when the character asked for none). Nobody swings both arms the same.
        arm_swing = prm["arm_swing"] * self.asym.gain("arm_swing", _side(self.P, arm))
        forward = prm["arm_forward"] + arm_swing * swing
        if swing > 0.0:
            forward += 0.15 * arm_swing * swing           # the forward swing is the larger
        forward += breath
        elbow = prm["elbow"] + prm["elbow_swing"] * swing
        hand_in = prm["hand_in"] * (0.3 + 0.7 * max(swing, 0.0))
        out = self.outs[arm["name"]] + 0.8 * breath
        return arm_spec(self.P, arm, forward, out, elbow, hand_in)

    def cycle_key(self, p0, offsets, duty, legs, height=None):
        """(trunk, limbs, extra drop) at cycle phase p0 of a gait.

        `height(q)` is how high the body rides at cycle phase q, metres, + up;
        the head nods against it. None (or no `gaze_m`) is no nod."""
        P, prm = self.P, self.params
        n = float(max(len(legs), 1))

        def drive(at):
            """(per-leg forward, per-leg load, turn, list) at cycle phase `at`."""
            fs = {l["name"]: leg_forward((at - offsets[l["name"]]) % 1.0, duty) for l in legs}
            ld = {l["name"]: leg_load((at - offsets[l["name"]]) % 1.0, duty) for l in legs}
            # +1: the +lat side's foot forward, and its hip with it
            t = sum(_side(P, l) * fs[l["name"]] for l in legs) / n
            # +1: the +lat side carrying the body
            ls = max(-1.0, min(1.0, sum(_side(P, l) * ld[l["name"]] for l in legs)))
            return fs, ld, t, ls

        fwd_sig, load, turn, lst = drive(p0)
        # The pelvis is driven directly by the legs. The thorax is a mass hung
        # on it, so it CHASES the pelvis by `trunk_lag` of a cycle rather than
        # mirroring it instantly - and the sign is no longer written down. At a
        # lag of half a cycle this is exactly the `-k x pelvis` it replaces,
        # which is the fast limit; slower, the two come closer to moving
        # together, which is what a walking body does.
        _f2, _l2, turn_t, lst_t = (drive((p0 - self.trunk_lag) % 1.0)
                                   if self.trunk_lag else (fwd_sig, load, turn, lst))
        pelvis_yaw = prm["pelvis_turn"] * turn * self.s_yaw
        thorax_yaw = prm["thorax_turn"] * turn_t * self.s_yaw
        pelvis_roll = prm["pelvis_list"] * lst * self.s_roll
        # The trunk leans over the STANCE leg in the lab frame, against the
        # pelvis, which lifts that hip (Thorstensson et al. 1984). It is not
        # lagged: `trunk_lag` is the thorax chasing the pelvis's TURN, and reused
        # here it put the roll ~120 deg behind the pelvis on every body - neither
        # over the stance leg nor away from it.
        thorax_roll = -prm["side_bend"] * lst * self.s_roll
        # Forward and back twice a stride, off each footstrike (`footstrike`):
        # the forward peak `lean_lag` of a cycle after it.
        pitch = prm["lean"] + prm["lean_bob"] * footstrike(p0, offsets, legs,
                                                           prm.get("lean_lag", 0.0))
        # The top of the chain is one rung further out: a mass carried on the
        # thorax, so it reads the SAME drive one more lag back rather than
        # copying the thorax's value. Its own signal is what `trunk` needs to
        # place it at a phase of its own.
        _f3, _l3, turn_h, _lh = (drive((p0 - self.trunk_lag - self.head_lag) % 1.0)
                                 if self.head_lag else (fwd_sig, load, turn_t, lst_t))
        lst_h = drive((p0 - self.head_lag) % 1.0)[3] if self.head_lag else lst
        # The head's pitch is its own, not a share of the trunk's: it keeps a
        # little of the held lean (as it always did) and none of the bob - the
        # head-on-trunk pitch cancels the trunk's at a walk (Hirasaki et al.
        # 1999) - and it nods to hold the eyes on a point `gaze_m` ahead as the
        # body rises and falls: up as the head drops.
        nod = self.nod(p0, height)
        lo, hi = getattr(self, "nod_range", (nod, nod))
        self.nod_range = (min(lo, nod), max(hi, nod))
        head_pitch = HEAD_LEAN_KEEP * prm["lean"] + nod
        head_sig = {"yaw": prm["thorax_turn"] * turn_h * self.s_yaw,
                    "roll": -prm["side_bend"] * lst_h * self.s_roll,
                    "pitch": head_pitch}
        hold = prm["head_hold"]
        tr = trunk(P, pelvis_yaw, pelvis_roll, thorax_yaw, thorax_roll, pitch,
                   {"yaw": hold, "roll": hold, "pitch": 0.0}, head=head_sig)
        drop = self.hip_half * math.sin(math.radians(abs(prm["pelvis_list"] * lst)))
        limbs, hands, girdle = {}, {}, {}
        g_lag = prm.get("girdle_lag", 0.0)
        g_drop, g_fwd = prm.get("girdle_drop", 0.0), prm.get("girdle_forward", 0.0)
        for arm in P.arms:
            side = _side(P, arm)
            same = [l for l in self.side_legs.get(side, []) if l["name"] in fwd_sig]
            if not same:
                continue
            # the leg on that side nearest the arm along the body
            leg = min(same, key=lambda l: abs(l["forward_pos"] - arm["forward_pos"]))
            # The arm is a pendulum hung at the shoulder, so it does not mirror
            # its leg instantly, it chases the body's swing. As with the trunk
            # the sign is not written down: a lag of half a cycle IS the exact
            # negation this replaces, and it is what `response` returns when
            # nothing is known about the drive.
            al = self.arm_lag.get(arm["name"], 0.5) + self.asym.offset("lag", side)
            hl = self.hand_lag.get(arm["name"], HAND_LAG)
            swing = leg_forward((p0 - al - offsets[leg["name"]]) % 1.0, duty)
            limbs[arm["name"]] = self.arm_terms(arm, swing)
            # the fingers trail the arm by their own pendulum's lag, opening a
            # little as the hand comes back and closing as it goes forward
            lagged = leg_forward((p0 - al - hl - offsets[leg["name"]]) % 1.0, duty)
            hands[arm["name"]] = 1.0 + HAND_SWING * lagged
            # The shoulder. It drops as ITS OWN SIDE takes the weight - which is
            # why a walk has two shoulder dips a stride, one per leg, and why
            # they are half a cycle apart rather than together - and it swings
            # forward with its own arm. Both trail their driver by `girdle_lag`,
            # because a shoulder is a mass hung on a ribcage and arrives late.
            g_bone = arm.get("girdle")
            if not g_bone or not (g_drop or g_fwd):
                continue
            ph = (p0 - g_lag - offsets[leg["name"]]) % 1.0
            # one shoulder drops a little deeper than the other, always the same one
            drop_here = (-g_drop * self.asym.gain("shoulder_dip", side)
                         * leg_load(ph, duty) * side * self.s_roll)
            fwd_here = g_fwd * -leg_forward(ph, duty) * side * self.s_yaw
            girdle[g_bone] = (0.0, drop_here, fwd_here)
        self.hands = hands
        self.girdle = girdle
        return tr, limbs, drop

    def nod(self, p0, height, samples=48):
        """Degrees the head pitches at cycle phase p0 to hold its gaze on a point
        `gaze_m` ahead while the body rides `height`: + forward (down), so a head
        below its mean height pitches up. 0 with no height or no gaze."""
        gaze = self.params.get("gaze_m")
        if height is None or not gaze:
            return 0.0
        mean = sum(height(i / float(samples)) for i in range(samples)) / samples
        dz = height(p0 % 1.0) - mean
        return math.degrees(math.atan2(dz, float(gaze)))

    def idle_key(self, t):
        """(limbs) at idle time t in 0..1: relaxed arms, a breath of drift."""
        b = self.params.get("breath", 0.0) * math.sin(2.0 * math.pi * t)
        # nothing is loaded and no arm is swinging: clear any girdle a gait key
        # left on this Upper, rather than holding the last frame of a walk
        self.girdle = {}
        return {arm["name"]: self.arm_terms(arm, 0.0, breath=b) for arm in self.P.arms}

    def widen(self, need_m):
        """Hang every arm further out by enough to gain `need_m` metres at the
        hand."""
        scale = sum(self.P.rig.matrix_world.to_scale()) / 3.0
        for arm in self.P.arms:
            reach = (arm["a"] + arm["b"]) * scale
            self.outs[arm["name"]] += math.degrees(1.3 * need_m / max(reach, 1e-6)) + 0.5

    def report(self):
        out = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in self.params.items()
               if k != "arm_out_measured"}
        out["arm_out"] = {k: round(v, 1) for k, v in self.outs.items()}
        # what the trunk coupling actually resolved to for this clip
        out["stride_hz"] = round(self.stride_hz, 3)
        out["trunk_lag_cycles"] = round(self.trunk_lag, 4)
        out["trunk_lag_deg"] = round(self.trunk_lag * 360.0, 1)
        out["trunk_gain"] = round(self.trunk_gain, 4)
        # the last rung: the measured frequency of what the chain carries at its
        # top, and the lag that frequency gives at this stride
        out["head_hz"] = round(self.head_hz, 3)
        out["head_lag_cycles"] = round(self.head_lag, 4)
        out["head_lag_deg"] = round(self.head_lag * 360.0, 1)
        # the gaze's nod as keyed: peak-to-peak degrees over the keys this clip asked for
        rng = getattr(self, "nod_range", None)
        out["head_nod_deg_pp"] = round(rng[1] - rng[0], 2) if rng else 0.0
        out["limb_hz"] = {k: {kk: round(vv, 3) for kk, vv in v.items()}
                          for k, v in getattr(self, "limb_hz", {}).items()}
        out["arm_lag_cycles"] = {k: round(v, 4) for k, v in getattr(self, "arm_lag", {}).items()}
        out["hand_lag_cycles"] = {k: round(v, 4) for k, v in getattr(self, "hand_lag", {}).items()}
        out["arm_out_measured"] = {k: round(v, 1) for k, v in self.params["arm_out_measured"].items()}
        if self.asym:
            out["asymmetry"] = self.asym.report()
        if getattr(self, "clearance", None) is not None:
            out["clearance_m"] = self.clearance.get("closest_m")
            # [closest m, mean arm_out] per playback, when the hang had to widen
            out["clearance_tries"] = getattr(self, "tries", [])
        return out


def author_clear(U, rig_name, bm, author, resample, tries=3):
    """Author a clip, play it back, and hang the arms further out while the
    forearm or hand skin comes nearer the body than `hand_clearance`.

    The hang is first measured against the body at rest; a walking body turns
    its pelvis and swings its thighs under the arms, and Blender's playback of
    the finished clip is the only measure of that which is not an opinion.
    `author(samples)` returns `_author_samples`' tuple, `resample()` new
    samples with the arms as they now are. A hand still inside the body after
    the retries is a failure in the clip's report."""
    from . import verify
    samples = resample()
    for attempt in range(tries + 1):
        keyed, infos, action, report = author(samples)
        if "error" in report or U is None or not U.P.arms:
            return keyed, infos, action, report
        c = verify.limb_clearance(rig_name, action.name, bm=bm, every=2)
        U.clearance = c
        closest = c.get("closest_m")
        U.__dict__.setdefault("tries", []).append(
            [closest, round(sum(U.outs.values()) / max(len(U.outs), 1), 1)])
        if closest is None or closest >= U.params["hand_clearance"] or attempt == tries:
            break
        U.widen(U.params["hand_clearance"] - closest)
        samples = resample()
    closest = (U.clearance or {}).get("closest_m")
    scale = sum(U.P.rig.matrix_world.to_scale()) / 3.0
    if closest is not None and closest < -verify.PLANT_TOL * bm["size"] * scale:
        report["failures"].append("a hand or forearm goes %.4f into the body at frame %d"
                                  % (-closest, U.clearance["at_frame"]))
        report["passed"] = False
    report["arm_clearance_m"] = closest
    # how the arms are carried: a walk's hand below the chest, a run's elbow bent
    ap = verify.arm_pose(rig_name, action.name, running=U.running, bm=bm)
    if "error" not in ap and "skipped" not in ap:
        report["arm_pose"] = ap["arms"]
        report["arm_running"] = ap["running"]
        if ap["failures"]:
            report["failures"].extend(ap["failures"])
            report["passed"] = False
    return keyed, infos, action, report
