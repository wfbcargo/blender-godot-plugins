"""A leg plan: which segments of a leg stand, and which carries the ground (08 fantasy species, layer 5).

    legs.validate({"plan": "digitigrade", "stand": 0.9})     # standard library only: species_design calls it
    rep = legs.apply(human, "digitigrade")                   # on the rigged, warped MPFB body

A human is **plantigrade**: the foot lies on the ground from heel to toe, the ankle is the lowest joint and
the leg is two links with a plate on the end. A dog, a cat, a gnoll or a satyr is **digitigrade**: the
metatarsals stand up, so what was the ankle is carried well clear of the ground as a hock, and the toes alone
take the weight. The bones are the same bones. What changes is where each one points and how long it is, so
this is a reshape of a leg, not a replacement of one - `graft.py` (which cuts the legs off and lofts a tail in
their place) is the wrong machinery for it, and its own module is the right one. It borrows the warp's
(`species.py`): the rest skeleton as arrays, linear blend skinning of every mesh and every shape key with the
body's own weights, and one re-stand on the floor at the end. Nothing is cut, so every UV, every vertex index,
the toes and their nails come through untouched.

The plan is solved before anything moves, from the leg the body already has:

- **`stand`** is how much of the foot stands up: the share of the metatarsus that is vertical (sin of its angle
  above the ground). A person's foot already reads 0.43; a dog's cannon stands at 0.85-0.95.
- **`metatarsal`** and **`toe`** lengthen those two segments (a digitigrade foot is a long cannon on long
  toes), **`girth`** thins them.
- The ball of the foot stays where it stood and the toes are laid flat on the ground from it, so the creature
  keeps its stance and its contact patch. The hock lands `stand * metatarsus` above the ball.
- **`knee`** is the included angle the stifle is to stand at. The femur and the tibia are then scaled by the
  one factor that puts the hip back at the height it had - so stature, hip height and everything above the
  pelvis are untouched, and the leg folds up under the body the way a digitigrade leg does. The knee still
  points forward and the hock back (`fold`); nothing else is built yet, and a plan that asks for it is refused.

What comes out is checked before the mesh moves (`solve`): the shank scale, the hock's height as a share of
hip height, the metatarsus against the shank and the toes against the metatarsus. Each refusal names its range.

rig-anything reads the result off the geometry, not off a name: a leg whose end bone stands along the leg
rather than lying on the ground counts that bone into the effective leg, so `locomotion` scales by hip-to-toe
and the gait needs no new maths (`rig_analysis.bodymap`, `stand_share`).
"""

from __future__ import annotations

import math

try:                     # validate() is standard library only: species_design and the spec check call it
    import numpy as np
except ImportError:      # pragma: no cover
    np = None

PROP = "hf_legs"                  # the solved plan, left on the rig and on the body
PLANS = ("plantigrade", "digitigrade")
KEYS = {"plan", "stand", "metatarsal", "toe", "shank", "girth", "knee", "fold", "ratios", "stance"}
FOLD_KEYS = {"knee", "hock"}
# A dog's cannon stands at 0.85-0.95 and its toes are about as long as it again [folklore, animal anatomy];
# the defaults are a canine biped's, and a satyr's shorter cannon is `metatarsal` down.
DEFAULTS = {"stand": 0.90, "girth": 0.85, "knee": 130.0, "ratios": "canine",
            "metatarsal": None, "toe": None, "shank": None, "stance": None}
LIMITS = {"stand": (0.50, 0.98), "metatarsal": (0.5, 3.2), "toe": (0.3, 3.2), "shank": (0.4, 1.6),
          "girth": (0.3, 1.6), "knee": (100.0, 175.0), "stance": (-0.20, 0.30)}

# THE SILHOUETTE. A leg reads as an animal's or a person's from its segment ratios, not from what is on the end
# of it: the first digitigrade body had a hock, pads and claws and still read at four metres as a person
# walking on their toes, because its femur, tibia, metatarsus and digits were still a human's. So the plan's
# input is the ratios - femur : tibia : metatarsus : digits as fractions of the straightened limb - and the
# per-segment scales are SOLVED to reach them at the hip height the body already stands at.
#
# `metatarsus` here is the rig's foot bone, hock joint to the ball, which is the tarsus AND the metatarsals
# together (Fischer & Blickhan's third functional segment); the osteometric Mt:F indices below count the
# metatarsal bone alone, about 0.75 of it.
#
#   [measured, review] Fischer & Blickhan 2006, "The tri-segmented limbs of therian mammals": the three
#     functional segments of a therian hind limb - femur, shank, tarsus+metatarsus - are near-equal (1:1:1)
#     in the crouched limbs of small mammals, which is what makes a crouched leg self-stabilising.
#   [measured] Croft & Lorente 2021, PLoS ONE 16(8):e0256371 (metatarsal-femur ratio, the pes length index):
#     extant cursorial carnivorans sit at Mt:F 0.38-0.65; extant cursorial ungulates - camelids, pecoran
#     ruminants (Caprinae among them) and equids - at Mt:F >= 0.65.
#   [measured, comparative anatomy] a cursor lengthens the distal limb and stands on SHORT digits; an
#     unguligrade ungulate stands on the last phalanx alone, so its digits are shorter again.
#   The crural indices (tibia over femur, ~1.08 canine and ~1.18 caprine) are the conventional values for a
#   carnivoran and a pecoran; they are the least-supported number here and the most forgiving.
RATIOS = {
    # femur : tibia : metatarsus : digits, as fractions of the straightened limb (they are normalised), and
    # the rest of the silhouette that goes with them: how deep the stifle stands, how far the metatarsus
    # stands up, and how the leg TAPERS - a person's leg is nearly one girth from hip to ankle and an
    # animal's is a heavy thigh over a thin shank over a thinner cannon, which at four metres is as much of
    # the read as the joints are.
    "human":  {"femur": 0.394, "tibia": 0.398, "metatarsus": 0.137, "digits": 0.070,
               "knee": 175.0, "stand": 0.43,
               "girth": {"thigh": 1.0, "shank": 1.0, "metatarsus": 1.0, "digits": 1.0},
               "why": "measured on humanform's own fitted body: a plantigrade leg, the foot a plate"},
    "canine": {"femur": 0.317, "tibia": 0.343, "metatarsus": 0.270, "digits": 0.070,
               "knee": 116.0, "stand": 0.90,
               "girth": {"thigh": 1.20, "shank": 0.80, "metatarsus": 0.50, "digits": 0.85},
               "why": "f:t:m:d = 1 : 1.08 : 0.85 : 0.22; Mt:F 0.62 (top of the carnivoran band, a dog rather "
                      "than a bear) with the tarsus counted in, near Fischer & Blickhan's equal thirds; a "
                      "dog stands its stifle near 115 degrees and carries its muscle at the thigh"},
    "caprine": {"femur": 0.299, "tibia": 0.352, "metatarsus": 0.313, "digits": 0.036,
                "knee": 120.0, "stand": 0.95,
                "girth": {"thigh": 1.14, "shank": 0.68, "metatarsus": 0.38, "digits": 0.85},
                "why": "f:t:m:d = 1 : 1.18 : 1.05 : 0.12; Mt:F 0.80, inside the cursorial-ungulate band, on "
                       "the very short digits of an unguligrade foot; the cannon of a goat is a bare rod"},
}
GIRTH_KEYS = ("thigh", "shank", "metatarsus", "digits")
RATIO_KEYS = ("femur", "tibia", "metatarsus", "digits")
RATIO_TOL = 0.025         # how far a built share may sit from the plan's target before the silhouette fails
RATIO_RANGE = (0.02, 0.55)   # any one segment's share of the limb
# only this fold is built; a bird's backward stifle is a different leg and says so
FOLD = {"knee": ("forward",), "hock": ("back",)}
DEFAULT_FOLD = {"knee": "forward", "hock": "back"}

# What the solved leg must land inside, before a vertex moves. Each is measured on the leg itself, so a plan
# that cannot be built on THIS body is refused with the number it reached.
SHANK = (0.55, 1.15)        # femur+tibia scaled by this to put the hip back at its height
HOCK_H = (0.10, 0.45)       # the hock's height as a share of hip height (a dog's is about 0.3)
META_SHARE = (0.10, 0.60)   # metatarsus over femur+tibia, after the solve
TOE_SHARE = (0.10, 0.85)    # toes over metatarsus
PASSES = 4                 # at most this many stance solves; they settle in two or three
STANCE_SETTLED = 0.002     # metres the ball moves between passes before it is called settled
KNEE_SPARE = 0.02           # the solve may not ask the shank to reach past this share of dead straight


def ratios(spec):
    """The four segment shares a plan asks for, normalised, from a name in RATIOS or a table of its own."""
    r = (spec or {}).get("ratios") if isinstance(spec, dict) else None
    r = r if r is not None else DEFAULTS["ratios"]
    if isinstance(r, str):
        r = RATIOS[r] if r in RATIOS else RATIOS[DEFAULTS["ratios"]]
    vals = [float(r[k]) for k in RATIO_KEYS]
    tot = sum(vals)
    return {k: v / tot for k, v in zip(RATIO_KEYS, vals)}


def normalise(spec):
    """A plan as a dict with every key filled in. `"digitigrade"` (or None / `"plantigrade"`) is a shorthand."""
    if spec is None:
        spec = "plantigrade"
    if isinstance(spec, str):
        spec = {"plan": spec}
    out = dict(DEFAULTS)
    out["plan"] = "plantigrade"
    out["fold"] = dict(DEFAULT_FOLD)
    for k, v in (spec or {}).items():
        if k == "fold" and isinstance(v, dict):
            out["fold"] = dict(DEFAULT_FOLD, **v)
        else:
            out[k] = v
    out["ratio_name"] = out["ratios"] if isinstance(out["ratios"], str) else "custom"
    src = RATIOS.get(out["ratio_name"]) or (out["ratios"] if isinstance(out["ratios"], dict) else {})
    out["ratios"] = ratios({"ratios": out["ratios"]})
    # a ratio set is a whole silhouette: its stifle, its stand and its taper come with its lengths, and the
    # spec overrides any of them
    for k in ("knee", "stand", "stance"):
        if k not in (spec or {}) and src.get(k) is not None:
            out[k] = float(src[k])
    g = (spec or {}).get("girth", src.get("girth"))
    if isinstance(g, dict):
        out["girth"] = {q: float(g.get(q, 1.0)) for q in GIRTH_KEYS}
    else:
        out["girth"] = {q: float(g if g is not None else 1.0) for q in GIRTH_KEYS}
    return out


def validate(spec):
    """[] or the problems with a `legs` block, each naming its range. Standard library only."""
    if spec is None or spec == "plantigrade":
        return []
    if not isinstance(spec, (str, dict)):
        return [f"legs must be {' or '.join(repr(p) for p in PLANS)}, or a table of them, "
                f"not {type(spec).__name__}"]
    if isinstance(spec, str):
        if spec not in PLANS:
            return [f"legs = {spec!r}: one of {', '.join(PLANS)}"]
        return []
    out = []
    plan = spec.get("plan", "digitigrade")
    if plan not in PLANS:
        out.append(f"legs.plan = {plan!r}: one of {', '.join(PLANS)}")
    out += [f"legs: unknown key {k!r} - it takes {', '.join(sorted(KEYS))}" for k in sorted(set(spec) - KEYS)]
    g = spec.get("girth")
    if isinstance(g, dict):
        out += [f"legs.girth: unknown segment {k!r} - it takes {', '.join(GIRTH_KEYS)}"
                for k in sorted(set(g) - set(GIRTH_KEYS))]
        for k in GIRTH_KEYS:
            v = g.get(k)
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))
                                  or not LIMITS["girth"][0] <= v <= LIMITS["girth"][1]):
                out.append(f"legs.girth.{k} = {v!r}: a number in "
                           f"{LIMITS['girth'][0]}..{LIMITS['girth'][1]} (how thick that segment is against "
                           f"the body's own)")
    for k in ("stand", "metatarsal", "toe", "shank", "knee", "stance") + (() if isinstance(g, dict) else ("girth",)):
        if k in spec and spec[k] is not None:
            lo, hi = LIMITS[k]
            v = spec[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                out.append(f"legs.{k} = {v!r}: a number in {lo}..{hi}"
                           + (" (the share of the metatarsus that stands vertical; a person's foot reads 0.43)"
                              if k == "stand" else
                              " (the included angle the stifle stands at, degrees)" if k == "knee" else
                              " (a multiplier ON TOP of the ratios' own solve, which normally sets it)"
                              if k in ("metatarsal", "toe", "shank") else ""))
    r = spec.get("ratios")
    if r is not None:
        if isinstance(r, str):
            if r not in RATIOS:
                out.append(f"legs.ratios = {r!r}: one of {', '.join(RATIOS)}, or a table of "
                           f"{', '.join(RATIO_KEYS)}")
        elif not isinstance(r, dict):
            out.append(f"legs.ratios must be a name ({', '.join(RATIOS)}) or a table of "
                       f"{', '.join(RATIO_KEYS)}, not {type(r).__name__}")
        else:
            miss = [k for k in RATIO_KEYS if k not in r]
            if miss:
                out.append(f"legs.ratios: missing {', '.join(miss)} - it takes all four of "
                           f"{', '.join(RATIO_KEYS)}, as fractions of the straightened limb")
            out += [f"legs.ratios: unknown key {k!r}" for k in sorted(set(r) - set(RATIO_KEYS) - {"why"})]
            tot = sum(float(v) for k, v in r.items() if k in RATIO_KEYS and isinstance(v, (int, float)))
            for k in RATIO_KEYS:
                v = r.get(k)
                if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0 or tot <= 0:
                    out.append(f"legs.ratios.{k} = {v!r}: a positive fraction of the straightened limb")
                elif not RATIO_RANGE[0] <= v / tot <= RATIO_RANGE[1]:
                    out.append(f"legs.ratios.{k} = {v!r} is {v / tot:.3f} of the limb, outside "
                               f"{RATIO_RANGE[0]}..{RATIO_RANGE[1]}")
    fold = spec.get("fold")
    if fold is not None:
        if not isinstance(fold, dict):
            out.append(f"legs.fold must be a table ({', '.join(sorted(FOLD_KEYS))})")
        else:
            out += [f"legs.fold: unknown joint {k!r} - it takes {', '.join(sorted(FOLD_KEYS))}"
                    for k in sorted(set(fold) - FOLD_KEYS)]
            for k, allowed in FOLD.items():
                if k in fold and fold[k] not in allowed:
                    out.append(f"legs.fold.{k} = {fold[k]!r}: only {', '.join(allowed)} is built "
                               f"(a leg that folds the other way is a different plan, not a parameter)")
    if plan == "plantigrade" and set(spec) - {"plan"}:
        out.append("legs.plan = 'plantigrade' takes no other key: a plantigrade leg is the body's own")
    return out


# ---------------------------------------------------------------------------- the solve


def _unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else v * 0.0


def _rot_between(a, b):
    """The smallest 3x3 rotation taking unit `a` onto unit `b`."""
    a, b = _unit(np.asarray(a, float)), _unit(np.asarray(b, float))
    c = float(np.dot(a, b))
    v = np.cross(a, b)
    s = float(np.linalg.norm(v))
    if s < 1e-12:
        if c > 0.0:
            return np.eye(3)
        # opposed: any perpendicular axis
        p = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        v = _unit(np.cross(a, p))
        K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]], float)
        return np.eye(3) + 2.0 * K @ K
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]], float)
    return np.eye(3) + K + K @ K * ((1.0 - c) / (s * s))


# Where the contact patch lies once a foot plan has run, as fractions of the DIGIT length forward of the ball:
# the pad under the standing ball at 0, the toe pads at 0.75 of each toe (`feet.PATCH`, which is where its own
# pad anchors sit). A plantigrade foot stands on its whole sole and is never solved this way.
DEFAULT_PATCH = (0.0, 0.75)


def solve(joints, spec, floor=0.0, forward=(0.0, -1.0, 0.0), com=None, patch=None):
    """Where one leg's joints go under a plan, and whether it can be built.

    `joints`: {"hip", "knee", "ankle", "ball", "tip"} rest positions (armature space, +Z up). Returns a dict
    with the new positions, the scale each segment takes, the angles, the measures the plan is checked on and
    `problems` - empty when the plan is buildable on this leg.
    """
    p = normalise(spec)
    hip, knee, ankle = (np.asarray(joints[k], float) for k in ("hip", "knee", "ankle"))
    ball, tip = (np.asarray(joints[k], float) for k in ("ball", "tip"))
    up = np.array([0.0, 0.0, 1.0])
    fwd = _unit(np.asarray(forward, float) - up * float(np.dot(forward, up)))

    F = float(np.linalg.norm(knee - hip))          # femur
    T = float(np.linalg.norm(ankle - knee))        # tibia
    M = float(np.linalg.norm(ball - ankle))        # metatarsus
    D = float(np.linalg.norm(tip - ball))          # toes
    hip_h = float(hip[2]) - floor
    out = {"plan": p["plan"], "problems": [], "rest": {
        "femur": round(F, 4), "tibia": round(T, 4), "metatarsus": round(M, 4), "toe": round(D, 4),
        "hip_height": round(hip_h, 4), "ankle_height": round(float(ankle[2]) - floor, 4),
        "stand": round(float(ankle[2] - ball[2]) / max(M, 1e-9), 3)}}
    if p["plan"] != "digitigrade":
        out.update({"changed": False, "positions": {k: list(map(float, np.asarray(joints[k], float)))
                                                    for k in ("hip", "knee", "ankle", "ball", "tip")},
                    "scale": {"femur": 1.0, "tibia": 1.0, "metatarsus": 1.0, "toe": 1.0}})
        return out

    stand = float(p["stand"])
    r = p["ratios"]
    ang = math.radians(float(p["knee"]))
    k_reach = math.sqrt(max(r["femur"] ** 2 + r["tibia"] ** 2
                            - 2.0 * r["femur"] * r["tibia"] * math.cos(ang), 1e-12))

    # WHERE THE FOOT STANDS. A plantigrade foot stands on its whole sole, so its ball sits well forward of the
    # hip (16 cm on a person) with the ankle under it. A digitigrade one stands on its TOES, and they take the
    # sole's place under the body - which is what puts the hock behind the hip and deepens the leg's zig-zag.
    # Left at the human's ball, the leg came out a shallow S and read at four metres as a person on tiptoe.
    # `stance` is how far forward of the hip the ball stands, in hip heights; None leaves it where it was. Its
    # floor is set by BALANCE, not by anatomy: a biped's centre of mass is in front of its hips, and at 0.02
    # the paw body's crouch put its centre 3.6 mm outside its feet and rig-anything refused the clip.
    ball1 = ball.copy()
    toe_dir = _unit(np.array([tip[0] - ball[0], tip[1] - ball[1], 0.0]))
    if float(np.linalg.norm(toe_dir)) < 1e-9:
        toe_dir = fwd.copy()
    back = np.array([ankle[0] - ball[0], ankle[1] - ball[1], 0.0])
    back = _unit(back) if float(np.linalg.norm(back)) > 1e-9 else -fwd
    lean = math.sqrt(max(1.0 - stand * stand, 0.0))

    def hock_at(L, b0):
        """Where the hock lands for a straightened limb of length L: the metatarsus is r_m of it, standing."""
        return b0 + up * (r["metatarsus"] * L * stand) + back * (r["metatarsus"] * L * lean)

    def solve_L(b0):
        """The straightened limb length that makes the folded shank exactly reach the hock from this ball.

        ONE unknown: the ratios fix every segment as a share of it, the hip is where the body already stands,
        and the hock's height comes out of the metatarsus. `gap` rises with L (the reach grows, and a higher
        hock is nearer the hip), so a bisection is enough."""
        def gap(L):
            return k_reach * L - float(np.linalg.norm(hip - hock_at(L, b0)))
        base = F + T + M + D
        lo_L, hi_L = 0.30 * base, 3.0 * base
        if gap(lo_L) > 0 or gap(hi_L) < 0:
            return None
        for _ in range(60):
            mid = 0.5 * (lo_L + hi_L)
            if gap(mid) < 0:
                lo_L = mid
            else:
                hi_L = mid
        return 0.5 * (lo_L + hi_L)

    def place(stance_v, b0):
        return b0 + fwd * (float(stance_v) * hip_h - float(np.dot(b0 - hip, fwd)))

    # WHERE THE FOOT STANDS. A plantigrade foot stands on its whole sole, so its ball sits well forward of the
    # hip (16 cm on a person) with the ankle under it. A digitigrade one stands on its TOES, and they take the
    # sole's place under the body - which is what puts the hock behind the hip and deepens the leg's zig-zag.
    # Left at the human's ball, the leg came out a shallow S and read at four metres as a person on tiptoe.
    #
    # `stance` is how far forward of the hip the ball stands, in hip heights, and it is SOLVED rather than
    # chosen whenever a body is there to measure. The warp balances a body over its PLANTIGRADE foot; a leg
    # plan then moves the contact patch out from under it and a foot plan moves it again, and the first gnoll
    # stood with its centre of mass 50 mm outside its paws - Crouch and MouthOpen refused at export - until
    # its spec carried a hand-tuned stance. So the stance is whatever puts the body's centre over the middle
    # of the patch it will really stand on: the pads the foot plan nominates, `patch` fractions of the digit
    # length forward of the ball. A ratio set's own `stance` is only the fallback for a call with no `com`.
    stance, stance_from = p.get("stance"), "the plan"
    L = solve_L(ball1)
    if L is None:
        out["problems"].append(
            f"legs: no limb length reaches the hip at {hip_h:.3f} m with ratios "
            f"{'/'.join(f'{r[q]:.2f}' for q in RATIO_KEYS)} and a {p['knee']:.0f} degree stifle - "
            f"straighten the stifle or shorten the metatarsus's share")
        out.update({"changed": False})
        return out
    if com is not None and stance is None:
        # the patch's centre needs the digit length, which needs the limb length, which needs the ball: three
        # passes settle it (the ball moves centimetres, the limb length millimetres)
        pb, pf = patch if patch is not None else DEFAULT_PATCH
        for _ in range(3):
            centre = 0.5 * (float(pb) + float(pf)) * (r["digits"] * L * float(p["toe"] or 1.0))
            stance = float(np.clip((float(com) - float(np.dot(hip, fwd)) - centre) / max(hip_h, 1e-9),
                                   *LIMITS["stance"]))
            ball1 = place(stance, ball)
            got = solve_L(ball1)
            if got is None:
                break
            L = got
        stance_from = "the body's centre over its contact patch"
    elif stance is not None:
        ball1 = place(stance, ball1)
        L = solve_L(ball1) or L

    f, t = r["femur"] * L, r["tibia"] * L
    m, d = r["metatarsus"] * L, r["digits"] * L
    # The knobs are still free: each is a multiplier ON the solved segment, so a plan can push one away from
    # its ratio and the silhouette check will say by how much.
    if p.get("shank") is not None:
        f, t = f * float(p["shank"]), t * float(p["shank"])
    if p.get("metatarsal") is not None:
        m *= float(p["metatarsal"])
    if p.get("toe") is not None:
        d *= float(p["toe"])

    hock = ball1 + up * (m * stand) + back * (m * lean)
    tip1 = ball1 + toe_dir * d
    span = hip - hock
    dist = float(np.linalg.norm(span))

    out["scale"] = {"femur": round(f / max(F, 1e-9), 4), "tibia": round(t / max(T, 1e-9), 4),
                    "metatarsal": round(m / max(M, 1e-9), 4), "toe": round(d / max(D, 1e-9), 4),
                    "girth": {q: round(float(p["girth"][q]), 3) for q in GIRTH_KEYS}}
    # the knee, in the plane of the hip-hock line and the body's forward axis, bent forward
    e = _unit(span * -1.0)                                  # hip -> hock
    n = fwd - e * float(np.dot(fwd, e))
    n = _unit(n) if float(np.linalg.norm(n)) > 1e-9 else _unit(np.cross(e, np.array([1.0, 0.0, 0.0])))
    x = (f * f - t * t + dist * dist) / (2.0 * dist)
    y = math.sqrt(max(f * f - x * x, 0.0))
    knee1 = hip + e * x + n * y

    hock_h = float(hock[2]) - floor
    shank = f + t
    limb = f + t + m + d
    built = {q: v / max(limb, 1e-9) for q, v in
             (("femur", f), ("tibia", t), ("metatarsus", m), ("digits", d))}
    meas = {"shank_scale": round(f / max(F, 1e-9), 3), "hock_height": round(hock_h, 4),
            "hock_over_hip": round(hock_h / max(hip_h, 1e-9), 3),
            "metatarsus_over_shank": round(m / max(shank, 1e-9), 3),
            "toe_over_metatarsus": round(d / max(m, 1e-9), 3),
            "knee_deg": round(float(p["knee"]), 1),
            "hock_deg": round(_angle(knee1, hock, ball1), 1),
            "limb": round(limb, 4),
            "effective_leg": round(shank + m, 4),
            "effective_over_hip": round((shank + m) / max(hip_h, 1e-9), 3),
            "mt_over_femur": round(m / max(f, 1e-9), 3),
            "crural": round(t / max(f, 1e-9), 3),
            "ball_forward_of_hip": round(float(np.dot(ball1 - hip, fwd)) / max(hip_h, 1e-9), 3),
            "stance": None if stance is None else round(float(stance), 4),
            "stance_from": stance_from}
    out["measures"] = meas
    out["ratios"] = {"name": p.get("ratio_name", "custom"),
                     "target": {q: round(r[q], 4) for q in RATIO_KEYS},
                     "built": {q: round(built[q], 4) for q in RATIO_KEYS},
                     "off": {q: round(built[q] - r[q], 4) for q in RATIO_KEYS}}
    probs = out["problems"]
    # THE SILHOUETTE CHECK. Everything else here is about whether the leg can be built; this is about whether
    # it reads as the animal it is meant to be, which is the one thing looking at the parts never told us.
    bad = [f"{q} {built[q]:.3f} against {r[q]:.3f}" for q in RATIO_KEYS
           if abs(built[q] - r[q]) > RATIO_TOL]
    if bad:
        probs.append(f"legs: the leg's silhouette misses its {p.get('ratio_name', 'custom')} ratios by more "
                     f"than {RATIO_TOL} of the limb - {'; '.join(bad)} (shares of femur+tibia+metatarsus+"
                     f"digits). A `metatarsal`, `toe` or `shank` multiplier is what pushes one off its ratio")
    for key, (lo, hi), what in (
            ("shank_scale", SHANK, "the femur must scale by this to stand the hip at its height with these "
                                   "ratios; raise `knee` (a straighter stifle) or give the metatarsus less"),
            ("hock_over_hip", HOCK_H, "the hock's height over the hip's; `stand` and the metatarsus's share "
                                      "set it"),
            ("metatarsus_over_shank", META_SHARE, "the standing foot against the shank above it"),
            ("toe_over_metatarsus", TOE_SHARE, "the toes against the standing foot")):
        v = meas[key]
        if not lo <= v <= hi:
            probs.append(f"legs: {key} {v} is outside {lo}..{hi} - {what}")
    if dist > (f + t) * (1.0 - KNEE_SPARE):
        probs.append(f"legs: the shank would stand dead straight to reach the hock "
                     f"({dist:.3f} m of {f + t:.3f} m) - lower `knee`")
    out.update({"changed": True, "positions": {
        "hip": list(map(float, hip)), "knee": list(map(float, knee1)), "ankle": list(map(float, hock)),
        "ball": list(map(float, ball1)), "tip": list(map(float, tip1))}})
    return out


def _angle(a, b, c):
    """The included angle at b, degrees."""
    u, v = _unit(np.asarray(a, float) - b), _unit(np.asarray(c, float) - b)
    return math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(u, v))))))


# ---------------------------------------------------------------------------- applying it


def _com_forward(rig):
    """The forward coordinate of the mean of every skinned vertex, in armature space - the same centre of mass
    `rig_analysis.motion.Body.com` takes, and the same one the clip balance check holds over the feet."""
    from . import species
    tot, n = 0.0, 0
    for ob in species._skinned(rig):
        me = ob.data
        k = len(me.vertices)
        if not k:
            continue
        co = np.empty(k * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        mw = np.array(rig.matrix_world.inverted() @ ob.matrix_world, float)
        co = co @ mw[:3, :3].T + mw[:3, 3]
        tot += float(co[:, 1].sum())
        n += k
    return (tot / n) * -1.0 if n else None


def _joints(rigd, chain):
    """{"hip", "knee", "ankle", "ball", "tip"} for one leg chain (thigh, shin, foot, toe)."""
    ix = rigd.ix
    hip, knee, ankle, ball = (rigd.head[ix[n]] for n in chain[:4]) if len(chain) >= 4 else (None,) * 4
    if hip is None:
        return None
    tip = rigd.tail[ix[chain[3]]]
    return {"hip": hip, "knee": knee, "ankle": ankle, "ball": ball, "tip": tip}


def _transforms(rigd, scale, rot, shift=0.0):
    """The same shape of transform the warp builds (`species._Warp.transforms`), from an ABSOLUTE rotation and a
    scale per bone instead of a spine bend: T = (A, t, head, R, S, along)."""
    from . import species
    n = len(rigd.names)
    A = np.zeros((n + 1, 3, 3))
    t = np.zeros((n + 1, 3))
    H = np.zeros((n, 3))
    R = np.zeros((n, 3, 3))
    Q = np.zeros((n, 3, 3))
    S = {nm: tuple(scale.get(nm, (1.0, 1.0, 1.0))) for nm in rigd.names}
    for i, name in enumerate(rigd.names):
        p = rigd.parent[i]
        if p < 0:
            h, q = rigd.head[i].copy(), np.eye(3)
        else:
            h, q = A[p] @ rigd.head[i] + t[p], Q[p]
        if name in rot:
            q = np.asarray(rot[name], float)
        Q[i] = q
        R[i] = q @ rigd.R[i]
        A[i] = R[i] @ np.diag(S[name]) @ rigd.R[i].T
        t[i] = h - A[i] @ rigd.head[i]
        H[i] = h
    A[n] = np.eye(3)
    h0 = np.vstack([rigd.head, np.zeros((1, 3))])
    y0 = np.vstack([rigd.R[:, :, 1], np.array([[0.0, 0.0, 1.0]])])
    Ln = np.append(np.maximum(rigd.length, 1e-6), 1.0)
    uni = [S[nm][0] == S[nm][1] == S[nm][2] for nm in rigd.names]
    ln = np.array([1.0 if u else S[nm][1] for nm, u in zip(rigd.names, uni)] + [1.0])

    def along_scale(j, axis):
        return float(np.linalg.norm(np.array(S[rigd.names[j]]) * (rigd.R[j].T @ axis)))

    kn, mn = np.ones(n + 1), np.ones(n + 1)
    for i, nm in enumerate(rigd.names):
        if uni[i]:
            continue
        p = rigd.parent[i]
        kp = along_scale(p, rigd.R[i][:, 1]) if p >= 0 and rigd.kind.get(rigd.names[p]) else ln[i]
        kids = [j for j in rigd.children[i] if rigd.kind.get(rigd.names[j])]
        if kids:
            c = min(kids, key=lambda j: np.linalg.norm(rigd.head[j] - rigd.tail[i]))
            mc = along_scale(c, rigd.R[i][:, 1])
        else:
            mc = ln[i]
        kn[i] = float(np.clip(0.5 * (kp + ln[i]), *species.LIMITS["head"]))
        mn[i] = float(np.clip(0.5 * (mc + ln[i]), *species.LIMITS["head"]))
    Y = np.vstack([R[:, :, 1], np.array([[0.0, 0.0, 1.0]])])
    T = [A, t, H, R, S, (h0, y0, Ln, ln, kn, mn, Y)]
    species._shift(T, rigd, shift)
    return tuple(T)


def apply(human, spec, report=None, verbose=False, patch=None):
    """Reshape a rigged body's legs to a leg plan, in place: the rest bones, every skinned mesh and every shape
    key. Returns the report - the plan, the solve per side and the measures it was checked on. Raises
    ValueError, with the range in the message, when the plan cannot be built on this leg."""
    import bpy
    from . import body as _body
    from . import species

    p = normalise(spec)
    rep = {} if report is None else report
    rep.update({"plan": p["plan"], "ratios": p.get("ratio_name", "custom"),
                "parameters": {k: p[k] for k in ("stand", "metatarsal", "toe", "shank", "girth", "knee",
                                                 "fold")}})
    problems = validate(spec)
    if problems:
        raise ValueError("; ".join(problems))
    if p["plan"] != "digitigrade":
        rep["changed"] = False
        return rep

    human = _body.obj(human)
    rig = _body.rig_of(human)
    if rig is None:
        raise ValueError(f"{human.name} has no rig: legs.apply runs after scaffold.finish")
    rigd = species._Rig(rig)
    if not rigd.legs:
        raise ValueError(f"{rig.name}: no legs to reshape (the body map found no leg chain off the pelvis)")

    floor = 0.0
    # THE STANCE CONVERGES. The stance is solved to stand the body's centre over the contact patch, but the
    # legs are a third of the body: moving them forward carries that centre with them, so one pass
    # under-corrects (the satyr's hooves landed 14 mm behind its centre). The leg solve's targets are
    # ABSOLUTE - the ratios against the hip height and the ball's own place - so applying it again from its own
    # output lands exactly where a single pass with the final stance would have. Two or three passes settle it.
    passes = []
    for _ in range(PASSES if (p["plan"] == "digitigrade" and p.get("stance") is None) else 1):
        rigd = species._Rig(rig)
        com = _com_forward(rig)
        solved, scale, rot, fails = _pass(rigd, p, floor, com, patch)
        if fails:
            raise ValueError("; ".join(fails))
        _carry(human, rig, rigd, scale, rot, species, bpy)
        got = solved[sorted(solved)[0]]["measures"].get("stance")
        passes.append(None if got is None else round(float(got), 4))
        if com is None or (len(passes) > 1 and passes[-1] is not None and passes[-2] is not None
                           and abs(passes[-1] - passes[-2]) * (solved[sorted(solved)[0]]["rest"]["hip_height"]
                                                               or 1.0) < STANCE_SETTLED):
            break
    rep["stance_passes"] = passes
    rigd = species._Rig(rig)

    after = species._Rig(rig)
    rep.update({
        "changed": True,
        "sides": {side: {k: s[k] for k in ("measures", "scale", "rest", "ratios") if k in s}
                  for side, s in solved.items()},
        "silhouette": solved[sorted(solved)[0]].get("ratios") if solved else None,
        "measures": solved[sorted(solved)[0]]["measures"] if solved else {},
        "hock_height_m": round(float(after.head[after.ix[after.legs[sorted(after.legs)[0]][2]], 2]), 4),
        "bones": {side: list(ch) for side, ch in sorted(rigd.legs.items())},
    })
    rig[PROP] = {"plan": p["plan"], "stand": float(p["stand"]), "knee": float(p["knee"]),
                 "ratios": p.get("ratio_name", "custom"),
                 "shares": {q: float(v) for q, v in (rep.get("silhouette") or {}).get("built", {}).items()}}
    human[PROP] = rig[PROP]
    if verbose:
        print("legs", p["plan"], rep["measures"], "stance passes", passes)
    return rep


def _carry(human, rig, rigd, scale, rot, species, bpy):
    """Every skinned mesh and every shape key through one pass's transforms, then the rest bones."""
    meshes = [species._Mesh(o, rig, rigd, smooth=species.WEIGHT_SMOOTH if o is human else 0)
              for o in species._skinned(rig)]
    body = next(m for m in meshes if m.ob is human)
    mask = species._body_mask(human)
    species._apply(meshes, body, mask, rigd, rig, _transforms(rigd, scale, rot))
    bpy.context.view_layer.update()


def _pass(rigd, p, floor, com, patch):
    """One solve of every leg: (solved, scale, rot, problems)."""
    solved, scale, rot, fails = {}, {}, {}, []
    for side, chain in sorted(rigd.legs.items()):
        if len(chain) < 4 or not all(chain[:4]):
            fails.append(f"leg {side} has {len(chain)} segments, not the four (thigh, shin, foot, toe) a "
                         f"leg plan reshapes")
            continue
        j = _joints(rigd, chain)
        s = solve(j, p, floor=floor, com=com, patch=patch)
        solved[side] = s
        fails += [f"{side}: {m}" for m in s["problems"]]
        if not s.get("changed"):
            continue
        pos = {k: np.asarray(v, float) for k, v in s["positions"].items()}
        gi = p["girth"]
        for bone, (a0, b0, a1, b1, sc) in (
                (chain[0], (j["hip"], j["knee"], pos["hip"], pos["knee"],
                            (gi["thigh"], s["scale"]["femur"], gi["thigh"]))),
                (chain[1], (j["knee"], j["ankle"], pos["knee"], pos["ankle"],
                            (gi["shank"], s["scale"]["tibia"], gi["shank"]))),
                (chain[2], (j["ankle"], j["ball"], pos["ankle"], pos["ball"],
                            (gi["metatarsus"], s["scale"]["metatarsal"], gi["metatarsus"]))),
                (chain[3], (j["ball"], j["tip"], pos["ball"], pos["tip"],
                            (gi["digits"], s["scale"]["toe"], gi["digits"])))):
            rot[bone] = _rot_between(np.asarray(b0, float) - a0, b1 - a1)
            scale[bone] = sc
        # anything hanging off the toes (nails, a claw) rides the toe bone
        for extra in chain[4:]:
            rot[extra] = rot[chain[3]]
    return solved, scale, rot, fails


def read(obj):
    """The plan left on a rig or a body by `apply`, or None."""
    v = obj.get(PROP) if obj is not None else None
    return dict(v) if v else None
