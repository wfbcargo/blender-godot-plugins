"""Per-character variability: the part of a gait that is this body's and nobody else's.

A generated walk is mirror-symmetric to the last digit, and that is one of the tells that
nobody generated it by walking. Nobody is symmetric: one arm swings further than the other,
one step is a little longer, one shoulder drops a little deeper, and the whole pattern is the
same every day of that person's life. It is IDENTITY, not noise.

So this module draws a fixed left/right asymmetry ONCE from a seed and hands it to the bake.
It is not a jitter and it is not sampled per frame or per cycle: `draw(seed, asymmetry)`
returns four signed numbers, and every clip of that character is baked with the same four.
The runtime half of L4 - per-cycle phase and amplitude jitter - is a different mechanism and
lives on the engine side; this module only carries its resolved parameters through so the two
halves read one block (see `resolve` and the seam below).

THE SEAM (character-pipeline writes it, the engine reads it)

    [variability]            in characters/<who>.toml, all optional
    seed = 1234              absent: derived from the character's id (`seed_from`)
    asymmetry = 0.35         0..1, default 0
    jitter_phase = 0.0       0..1, default 0 - the runtime half
    jitter_amp = 0.0         0..1, default 0 - the runtime half

    "variability": {"seed": ..., "asymmetry": ..., "jitter_phase": ..., "jitter_amp": ...}
                             one top-level key in <who>.moves.json, the RESOLVED values used

**Every default is zero**, and zero is the identity: `draw(seed, 0.0)` gives a gain of exactly
1.0 and an offset of exactly 0.0 on every channel and every side, so a character that does not
ask for asymmetry bakes bit-for-bit the clip it baked before this module existed. Nothing here
is reached unless a spec opts in.

DETERMINISM is the whole point, and it is the failure mode to design against - improvements 5.7
was a round lost to a per-process face shuffle. So:

- the seed comes from the character's identity through SHA-256 of its id, never from `hash()`
  (salted per process), the clock, the process id or `os.urandom`;
- each channel's value is SHA-256 of `<seed>:<channel>`, drawn independently, so it does not
  depend on the order channels are asked for or on any dict's iteration order;
- nothing carries RNG state between draws, so drawing one channel cannot move another.

Two builds of one spec are therefore identical, and two different character ids differ.
`RA_ASYM_NONDETERMINISTIC=1` breaks exactly that (the control that must fail).

WHAT IT MOVES, and why these four

At bake, the asymmetry is a small signed per-side MULTIPLIER on what is mirrored today - it is
not added noise, so the gait keeps its shape and only its balance changes:

    arm_swing     how far that side's arm swings (the largest real asymmetry in walking)
    step_length   where that side's foot plants along the travel direction, so the step from
                  one foot to the other is not the step back (each foot still travels one full
                  stride at the body's speed - a planted foot that swept a different distance
                  in the same time would simply skate, and the exporter says so)
    shoulder_dip  how deep that shoulder drops as its own leg takes the weight
    lag           how far behind its leg that side's arm swings, in cycles

`SPREAD` is each channel's half-spread at `asymmetry = 1`, chosen from what is measured in
people rather than by eye: arm swing is the loosest (healthy adults commonly differ 10-20%
between sides and much more after a stroke), step length the tightest (a symmetry index of a
few percent is normal, and 10% is a limp). At the shipped default of 0.35 they land inside
those bands. `asymmetry = 1` is the dial's end, not a person.

`RA_ASYM_MIRROR=1` applies one side's draw to BOTH sides: the asymmetry is still drawn, still
deterministic, still non-zero, and the baked clip comes out symmetric again. That is the other
control that must fail - it tests the side plumbing directly rather than the draw.
"""

from __future__ import annotations

import hashlib
import math
import os

# The seam's keys, in the order they are written. `seed` resolves to an int, the rest to floats.
KEYS = ("seed", "asymmetry", "jitter_phase", "jitter_amp")
# Every default is zero, so a spec that says nothing changes nothing.
DEFAULTS = {"asymmetry": 0.0, "jitter_phase": 0.0, "jitter_amp": 0.0}

# What a fixed asymmetry moves, and each channel's half-spread at asymmetry = 1.
# A multiplier channel is 1 +- SPREAD * asymmetry; `lag` is an offset in cycles.
CHANNELS = ("arm_swing", "step_length", "shoulder_dip", "lag")
SPREAD = {
    "arm_swing": 0.35,      # +-35% at the dial's end; +-12% at the shipped 0.35
    "step_length": 0.03,    # of the stroke, each way, so the two steps differ by 4x that
    "shoulder_dip": 0.25,
    "lag": 0.04,            # cycles, added to the arm's lag behind its own leg
}
# What a real person is worth on the dial: inside every band above, visible in a side-by-side.
SENSIBLE = 0.35

_MASK = (1 << 64) - 1


class VariabilityError(ValueError):
    pass


def seed_from(identity):
    """A stable 64-bit seed from a character's id. SHA-256, never `hash()`: Python salts that
    per process, so a seed taken from it would differ between two builds of one spec."""
    if os.environ.get("RA_ASYM_NONDETERMINISTIC") == "1":
        # the control: a seed from the process, which two builds of one spec cannot agree on
        return int.from_bytes(os.urandom(8), "big") & _MASK
    text = "" if identity is None else str(identity)
    return int.from_bytes(hashlib.sha256(("rig-anything/variability/" + text).encode("utf-8")
                                         ).digest()[:8], "big") & _MASK


def _unit(seed, channel):
    """A signed value in (-1, 1) for one channel of one seed. Drawn from the seed and the
    channel's NAME, not from a stream, so asking for one channel cannot move another and the
    order they are asked in does not matter."""
    d = hashlib.sha256(("%d:%s" % (int(seed) & _MASK, channel)).encode("utf-8")).digest()
    return (int.from_bytes(d[:8], "big") / float(1 << 64)) * 2.0 - 1.0


def _number(table, key, where):
    v = table.get(key, DEFAULTS[key])
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise VariabilityError("%s%s must be a number 0..1, not %r" % (where, key, v))
    v = float(v)
    if not 0.0 <= v <= 1.0:
        raise VariabilityError("%s%s = %s must be 0..1" % (where, key, v))
    return v


def resolve(table=None, identity=None, where="[variability] "):
    """The seam block: the RESOLVED values a build actually used, ready to be written under
    `"variability"` in <who>.moves.json.

    table     the spec's `[variability]`, or None / {} for a character that asks for nothing
    identity  the character's id, which `seed` is derived from when the spec names none

    Returns {"seed": int, "asymmetry": float, "jitter_phase": float, "jitter_amp": float}.
    Raises `VariabilityError` naming the field it refuses."""
    table = dict(table or {})
    unknown = sorted(set(table) - set(KEYS))
    if unknown:
        raise VariabilityError("%sunknown field(s) %s - it takes %s"
                               % (where, ", ".join(unknown), ", ".join(KEYS)))
    seed = table.get("seed")
    if seed is None:
        seed = seed_from(identity)
    elif isinstance(seed, bool) or not isinstance(seed, int):
        raise VariabilityError("%sseed must be a whole number, not %r" % (where, seed))
    out = {"seed": int(seed) & _MASK}
    for k in KEYS[1:]:
        out[k] = _number(table, k, where)
    return out


class Asym:
    """One character's fixed left/right asymmetry: four signed numbers, drawn once.

    `gain(channel, side)` is the multiplier for that side (1.0 exactly when asymmetry is 0),
    `offset(channel, side)` the additive term (0.0 exactly when asymmetry is 0). `side` is the
    body map's +1 / -1 along `lat`, so nothing here knows the words "left" or "right" - a body
    plan with no sides never reaches it, and one with six legs gets the same two sides its
    bodymap already has."""

    __slots__ = ("seed", "asymmetry", "values", "mirrored")

    def __init__(self, seed, asymmetry, values, mirrored=False):
        self.seed = int(seed)
        self.asymmetry = float(asymmetry)
        self.values = dict(values)
        self.mirrored = bool(mirrored)

    def __bool__(self):
        return self.asymmetry != 0.0

    def _signed(self, channel, side):
        v = self.values.get(channel, 0.0)
        if self.mirrored:
            # the control: one side's draw on both sides - still asymmetric as a number,
            # symmetric as a body
            return v
        return v * (1.0 if side > 0 else -1.0)

    def gain(self, channel, side):
        """The multiplier on `channel` for the side `side` of the midline."""
        return 1.0 + self._signed(channel, side)

    def offset(self, channel, side):
        """The additive term on `channel` for the side `side` of the midline."""
        return self._signed(channel, side)

    def report(self):
        """What was drawn, for the clip report. Keyed by channel, +lat side's signed value."""
        return {"seed": self.seed, "asymmetry": round(self.asymmetry, 4),
                "plus_lat": {k: round(v, 5) for k, v in sorted(self.values.items())}}


IDENTITY = Asym(0, 0.0, {c: 0.0 for c in CHANNELS})


def draw(seed, asymmetry):
    """The fixed asymmetry for one character. `asymmetry` 0 gives the identity, where every
    gain is exactly 1.0 and every offset exactly 0.0."""
    a = float(asymmetry or 0.0)
    if a <= 0.0:
        return IDENTITY
    vals = {c: SPREAD[c] * a * _unit(seed, c) for c in CHANNELS}
    return Asym(seed, a, vals, mirrored=os.environ.get("RA_ASYM_MIRROR") == "1")


def for_clip(variability, identity=None):
    """The `Asym` a clip bakes with, from a spec's `[variability]` table (or an already
    resolved block, or None). None / {} / asymmetry 0 all give `IDENTITY`."""
    if isinstance(variability, Asym):
        return variability
    if not variability:
        return IDENTITY
    r = resolve(variability, identity)
    return draw(r["seed"], r["asymmetry"])


# --------------------------------------------------------------------------
# measuring it off the baked clip
# --------------------------------------------------------------------------

def measure(rig_name, action_name, forward="-Y", up="Z", floor=0.0, bm=None):
    """Left against right, measured on Blender's PLAYBACK of a baked clip - never from the
    parameter that was set.

    Per side (`+1` / `-1` along the body map's `lat`):
      arm_swing_deg     the arm's carry angle range, as `verify.arm_pose` measures it
      step_length_m     that side's STEP: how far ahead of the other foot it plants (the gait
                        lab's step length, not the stride - each foot's own travel is the same
                        on both sides in any walk that does not drift)
      shoulder_dip_m    that shoulder's vertical excursion over the mean hip height, so the
                        body's own bounce is taken out and this side's own drop is left
      stride_m          each foot's OWN travel, which must stay the same on both sides: the
                        no-skate invariant, reported so a reader sees it rather than trusts it

    and, not per side, `stance_offset_m`: the +lat foot's stance position along `fwd` minus the
    -lat foot's, both off the hips. That is the free value the asymmetry moves one for one, and
    the two step lengths are `stride/2 +- stance_offset`.

    and per measure a `ratio` (the +lat side over the -lat side) and `index`, the usual
    symmetry index 2|L-R|/(L+R). A perfectly mirrored clip reads ratio 1 and index 0.

    Returns {"sides": {...}, "arm_swing_deg": {...}, ...} or {"error": ...} / {"skipped": ...}.
    """
    import bpy
    from mathutils import Vector

    from . import bodymap, verify
    rig = bpy.data.objects.get(rig_name)
    action = bpy.data.actions.get(action_name)
    if rig is None or action is None:
        return {"error": "missing rig %r or action %r" % (rig_name, action_name)}
    bm = bm or bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return {"error": bm["error"]}
    arms = [l for l in bm["limbs"] if l["role"] == "arm" and l["end"]]
    legs = [l for l in bm["limbs"] if l["role"] == "leg" and l["end"]]
    if len(legs) < 2:
        return {"skipped": "fewer than two legs"}
    lo, hi = verify._frames(action)
    mats, _, binding = verify._play(rig, action, list(range(lo, hi + 1)))
    if mats is None:
        return {"error": binding["note"]}
    upv, fwd, lat = bm["up_vec"], bm["fwd"], bm["lat"]
    # the midline the sides are taken about: the mean of the legs' roots along `lat`, which is
    # `keyposes.Poser.centre` projected the only way this measurement cares about
    mid = sum(l["rest_root"].dot(lat) for l in legs) / len(legs)

    def side_of(limb):
        return 1 if limb["rest_root"].dot(lat) > mid else -1

    bones = rig.data.bones
    frames = sorted(mats)
    out = {"clip": action_name, "frames": len(frames)}

    # Step length, as a gait lab means it: the distance along `fwd` from one foot's plant to
    # the other's. NOT each foot's own travel - that is the STRIDE, and it is the same on both
    # sides in any walk that does not drift, because a planted foot that swept a different
    # distance in the same time would skate (rig-anything's exporter refuses exactly that).
    # A person with a short left step still carries each foot one stride a cycle; they plant it
    # somewhere else. So each foot's stance is summarised by where it sits along `fwd` relative
    # to the HIPS (a reference neither foot is part of, so two feet cannot cancel each other the
    # way two shoulders do), and the two steps follow exactly:
    #     step(+lat) = stride/2 + offset,  step(-lat) = stride/2 - offset
    # where `offset` is the +lat foot's stance position minus the -lat foot's. Read off the
    # planted frames, so it is continuous - a touchdown FRAME moves in whole frames and made
    # this measurement jump by 2-3 cm at a time when it was taken there.
    steps, strides = {}, {}
    stance_offset = None
    if len(legs) >= 2:
        hips = [sum(mats[f][g["upper"]].translation.dot(fwd) for g in legs) / len(legs)
                for f in frames]
        pos, travel = {}, {}
        for l in legs:
            xs = [mats[f][l["end"]].translation.dot(fwd) - hips[i] for i, f in enumerate(frames)]
            lo, hi = min(xs), max(xs)
            travel[l["name"]] = hi - lo
            # the planted half of the cycle is the forward half of the foot's travel; its mean
            # is this foot's stance position, and it moves one for one with where it plants
            planted = [x for x in xs if x >= 0.5 * (lo + hi)]
            pos[l["name"]] = sum(planted) / len(planted)
            strides.setdefault(side_of(l), []).append(travel[l["name"]])
        plus = [pos[l["name"]] for l in legs if side_of(l) > 0]
        minus = [pos[l["name"]] for l in legs if side_of(l) < 0]
        if plus and minus:
            stance_offset = sum(plus) / len(plus) - sum(minus) / len(minus)
            stride = sum(travel.values()) / len(travel)
            steps[1] = [0.5 * stride + stance_offset]
            steps[-1] = [0.5 * stride - stance_offset]

    # shoulder dip: each shoulder's height over the MEAN HIP height, so the body's own bounce
    # does not swamp it. Not over the mean of the two shoulders, which cannot work: with two of
    # them each one's deviation from their mean is exactly minus the other's, so the two ranges
    # come out equal whatever the shoulders do. (That version measured 1.0000 on a clip whose
    # arms were plainly 13% apart, which is how it was caught.)
    dips, swings = {}, {}
    if len(arms) >= 2:
        hips = [sum(mats[f][g["upper"]].translation.dot(upv) for g in legs) / len(legs)
                for f in frames]
        for l in arms:
            h = [mats[f][l["upper"]].translation.dot(upv) - hips[i] for i, f in enumerate(frames)]
            dips.setdefault(side_of(l), []).append(max(h) - min(h))
        # arm swing: the carry angle's range - the palm seen from its own shoulder, which is
        # the quantity `verify.arm_pose` reports as `arm_swing_deg`
        for l in arms:
            carry = []
            for f in frames:
                sh = mats[f][l["upper"]].translation
                palm = mats[f][l["end"]] @ Vector((0.0, 0.5 * bones[l["end"]].length, 0.0))
                v = palm - sh
                carry.append(math.degrees(math.atan2(v.dot(fwd), -v.dot(upv))))
            swings.setdefault(side_of(l), []).append(max(carry) - min(carry))

    def pair(per_side, digits):
        if len(per_side) < 2:
            return None
        p = sum(per_side.get(1, [])) / max(len(per_side.get(1, [])), 1)
        m = sum(per_side.get(-1, [])) / max(len(per_side.get(-1, [])), 1)
        tot = p + m
        return {"plus_lat": round(p, digits), "minus_lat": round(m, digits),
                "ratio": round(p / m, 5) if abs(m) > 1e-12 else None,
                "index": round(2.0 * abs(p - m) / tot, 5) if abs(tot) > 1e-12 else 0.0}

    out["step_length_m"] = pair(steps, 5)
    # the free values behind it: the offset the asymmetry moves directly, and each foot's own
    # travel, which must stay the same on both sides - the no-skate invariant, reported so a
    # reader can see it rather than take it on trust
    out["stance_offset_m"] = None if stance_offset is None else round(stance_offset, 5)
    out["stride_m"] = pair(strides, 5)
    out["shoulder_dip_m"] = pair(dips, 5)
    out["arm_swing_deg"] = pair(swings, 3)
    out["sides"] = {"legs": {l["name"]: side_of(l) for l in legs},
                    "arms": {l["name"]: side_of(l) for l in arms}}
    return out


def summarize(m):
    """One line per measure of a `measure` result."""
    if "error" in m or "skipped" in m:
        return m.get("error") or m.get("skipped")
    rows = []
    for key, unit in (("arm_swing_deg", "deg"), ("step_length_m", "m"), ("stride_m", "m"),
                      ("shoulder_dip_m", "m")):
        v = m.get(key)
        if not v:
            continue
        rows.append("%-15s +lat %.4f %s  -lat %.4f %s  ratio %s  index %s"
                    % (key, v["plus_lat"], unit, v["minus_lat"], unit,
                       "-" if v["ratio"] is None else "%.4f" % v["ratio"], "%.4f" % v["index"]))
    if m.get("stance_offset_m") is not None:
        rows.append("%-15s %+.5f m" % ("stance_offset", m["stance_offset_m"]))
    return "\n".join(rows)
