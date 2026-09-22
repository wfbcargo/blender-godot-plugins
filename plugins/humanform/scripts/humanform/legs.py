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
KEYS = {"plan", "stand", "metatarsal", "toe", "girth", "knee", "fold"}
FOLD_KEYS = {"knee", "hock"}
# A dog's cannon stands at 0.85-0.95 and its toes are about as long as it again [folklore, animal anatomy];
# the defaults are a canine biped's, and a satyr's shorter cannon is `metatarsal` down.
DEFAULTS = {"stand": 0.90, "metatarsal": 1.9, "toe": 1.7, "girth": 0.85, "knee": 130.0}
LIMITS = {"stand": (0.50, 0.98), "metatarsal": (0.8, 3.2), "toe": (0.8, 3.2),
          "girth": (0.5, 1.4), "knee": (100.0, 160.0)}
# only this fold is built; a bird's backward stifle is a different leg and says so
FOLD = {"knee": ("forward",), "hock": ("back",)}
DEFAULT_FOLD = {"knee": "forward", "hock": "back"}

# What the solved leg must land inside, before a vertex moves. Each is measured on the leg itself, so a plan
# that cannot be built on THIS body is refused with the number it reached.
SHANK = (0.55, 1.15)        # femur+tibia scaled by this to put the hip back at its height
HOCK_H = (0.10, 0.45)       # the hock's height as a share of hip height (a dog's is about 0.3)
META_SHARE = (0.10, 0.60)   # metatarsus over femur+tibia, after the solve
TOE_SHARE = (0.10, 0.85)    # toes over metatarsus
KNEE_SPARE = 0.02           # the solve may not ask the shank to reach past this share of dead straight


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
    for k in ("stand", "metatarsal", "toe", "girth", "knee"):
        if k in spec:
            lo, hi = LIMITS[k]
            v = spec[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                out.append(f"legs.{k} = {v!r}: a number in {lo}..{hi}"
                           + (" (the share of the metatarsus that stands vertical; a person's foot reads 0.43)"
                              if k == "stand" else
                              " (the included angle the stifle stands at, degrees)" if k == "knee" else ""))
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


def solve(joints, spec, floor=0.0, forward=(0.0, -1.0, 0.0)):
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

    m = M * float(p["metatarsal"])
    d = D * float(p["toe"])
    stand = float(p["stand"])

    # 1. the ball stands where it stood; the toes lie flat on the ground from it
    ball1 = ball.copy()
    toe_dir = _unit(np.array([tip[0] - ball[0], tip[1] - ball[1], 0.0]))
    if float(np.linalg.norm(toe_dir)) < 1e-9:
        toe_dir = fwd.copy()
    tip1 = ball1 + toe_dir * d

    # 2. the metatarsus stands: `stand` of it vertical, the rest back along the way the foot already leant
    back = np.array([ankle[0] - ball[0], ankle[1] - ball[1], 0.0])
    back = _unit(back) if float(np.linalg.norm(back)) > 1e-9 else -fwd
    hock = ball1 + up * (m * stand) + back * (m * math.sqrt(max(1.0 - stand * stand, 0.0)))

    # 3. the shank folds to `knee` degrees and puts the hip back where it was
    span = hip - hock
    dist = float(np.linalg.norm(span))
    ang = math.radians(float(p["knee"]))
    reach = math.sqrt(max(F * F + T * T - 2.0 * F * T * math.cos(ang), 1e-12))
    s = dist / reach
    f, t = F * s, T * s
    out["scale"] = {"femur": round(s, 4), "tibia": round(s, 4),
                    "metatarsal": round(float(p["metatarsal"]), 4), "toe": round(float(p["toe"]), 4),
                    "girth": round(float(p["girth"]), 4)}
    # the knee, in the plane of the hip-hock line and the body's forward axis, bent forward
    e = _unit(span * -1.0)                                  # hip -> hock
    n = fwd - e * float(np.dot(fwd, e))
    n = _unit(n) if float(np.linalg.norm(n)) > 1e-9 else _unit(np.cross(e, np.array([1.0, 0.0, 0.0])))
    x = (f * f - t * t + dist * dist) / (2.0 * dist)
    y = math.sqrt(max(f * f - x * x, 0.0))
    knee1 = hip + e * x + n * y

    hock_h = float(hock[2]) - floor
    shank = f + t
    meas = {"shank_scale": round(s, 3), "hock_height": round(hock_h, 4),
            "hock_over_hip": round(hock_h / max(hip_h, 1e-9), 3),
            "metatarsus_over_shank": round(m / max(shank, 1e-9), 3),
            "toe_over_metatarsus": round(d / max(m, 1e-9), 3),
            "knee_deg": round(float(p["knee"]), 1),
            "hock_deg": round(_angle(knee1, hock, ball1), 1),
            "effective_leg": round(shank + m, 4),
            "effective_over_hip": round((shank + m) / max(hip_h, 1e-9), 3)}
    out["measures"] = meas
    probs = out["problems"]
    for key, (lo, hi), what in (
            ("shank_scale", SHANK, "the femur and tibia must scale by this to stand the hip at its height; "
                                   "raise `knee` (a straighter stifle) or lower `stand`/`metatarsal`"),
            ("hock_over_hip", HOCK_H, "the hock's height over the hip's; `stand` and `metatarsal` set it"),
            ("metatarsus_over_shank", META_SHARE, "the standing foot against the shank above it (`metatarsal`)"),
            ("toe_over_metatarsus", TOE_SHARE, "the toes against the standing foot (`toe`)")):
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


def apply(human, spec, report=None, verbose=False):
    """Reshape a rigged body's legs to a leg plan, in place: the rest bones, every skinned mesh and every shape
    key. Returns the report - the plan, the solve per side and the measures it was checked on. Raises
    ValueError, with the range in the message, when the plan cannot be built on this leg."""
    import bpy
    from . import body as _body
    from . import species

    p = normalise(spec)
    rep = {} if report is None else report
    rep.update({"plan": p["plan"], "parameters": {k: p[k] for k in ("stand", "metatarsal", "toe", "girth",
                                                                    "knee", "fold")}})
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
    solved, scale, rot = {}, {}, {}
    fails = []
    for side, chain in sorted(rigd.legs.items()):
        if len(chain) < 4 or not all(chain[:4]):
            fails.append(f"leg {side} has {len(chain)} segments, not the four (thigh, shin, foot, toe) a "
                         f"leg plan reshapes")
            continue
        j = _joints(rigd, chain)
        s = solve(j, p, floor=floor)
        solved[side] = s
        fails += [f"{side}: {m}" for m in s["problems"]]
        if not s.get("changed"):
            continue
        pos = {k: np.asarray(v, float) for k, v in s["positions"].items()}
        g = float(p["girth"])
        for bone, (a0, b0, a1, b1, sc) in (
                (chain[0], (j["hip"], j["knee"], pos["hip"], pos["knee"], (1.0, s["scale"]["femur"], 1.0))),
                (chain[1], (j["knee"], j["ankle"], pos["knee"], pos["ankle"], (1.0, s["scale"]["tibia"], 1.0))),
                (chain[2], (j["ankle"], j["ball"], pos["ankle"], pos["ball"],
                            (g, float(p["metatarsal"]), g))),
                (chain[3], (j["ball"], j["tip"], pos["ball"], pos["tip"], (g, float(p["toe"]), g)))):
            rot[bone] = _rot_between(np.asarray(b0, float) - a0, b1 - a1)
            scale[bone] = sc
        # anything hanging off the toes (nails, a claw) rides the toe bone
        for extra in chain[4:]:
            rot[extra] = rot[chain[3]]
    if fails:
        raise ValueError("; ".join(fails))

    meshes = [species._Mesh(o, rig, rigd, smooth=species.WEIGHT_SMOOTH if o is human else 0)
              for o in species._skinned(rig)]
    body = next(m for m in meshes if m.ob is human)
    mask = species._body_mask(human)
    species._apply(meshes, body, mask, rigd, rig, _transforms(rigd, scale, rot))
    bpy.context.view_layer.update()

    after = species._Rig(rig)
    rep.update({
        "changed": True,
        "sides": {side: {k: s[k] for k in ("measures", "scale", "rest") if k in s} for side, s in solved.items()},
        "measures": solved[sorted(solved)[0]]["measures"] if solved else {},
        "hock_height_m": round(float(after.head[after.ix[after.legs[sorted(after.legs)[0]][2]], 2]), 4),
        "bones": {side: list(ch) for side, ch in sorted(rigd.legs.items())},
    })
    rig[PROP] = {"plan": p["plan"], "stand": float(p["stand"]), "metatarsal": float(p["metatarsal"]),
                 "toe": float(p["toe"]), "knee": float(p["knee"])}
    human[PROP] = rig[PROP]
    if verbose:
        print("legs", p["plan"], rep["measures"])
    return rep


def read(obj):
    """The plan left on a rig or a body by `apply`, or None."""
    v = obj.get(PROP) if obj is not None else None
    return dict(v) if v else None
