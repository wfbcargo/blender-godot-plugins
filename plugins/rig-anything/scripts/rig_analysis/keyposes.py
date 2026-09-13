"""Key poses: whole-body poses in body terms, and blends between them.

`actions.crouch` and `actions.slide` each hand-wrote a path from rest to one
pose. The next actions are not like that - a slide recovery runs slide pose ->
deep crouch -> stand, a crouch walk is a crouch with a gait laid over it - so
the pose itself becomes a value:

    Key(drop, shift, sway, lean, head_level, limbs={name: spec})

and `Poser.blend(a, b, w)` produces the body part way between two of them.
Axial numbers blend directly. A limb's target is computed from EACH key against
the current blended body and the two points are blended, so a key can say
"foot along the floor at full reach from wherever the hip is now" and still mix
with a key that says "foot back where it stood". Poles and planted feet blend
with the same weight, so nothing snaps.

A limb a key does not mention is at rest: legs stand where they stood, arms
ride their shoulder.

A limb spec:
    target   fn(poser, limb, posed) -> armature-space point, or None for rest
    pole     armature-space direction for the mid-joint, or None for natural
    planted  hold the end bone at its rest orientation (a flat foot)
"""

from __future__ import annotations

import math

from mathutils import Matrix, Vector

from . import motion


def lerp(a, b, w):
    return a + (b - a) * w


def lean_angles(bm, lean, head_level):
    """Total pitch per axial bone for a torso leaning `lean` degrees.

    The pelvis takes half, the torso ramps to the full lean by its top, and the
    neck and head hand `head_level` of it back so the creature keeps looking
    where it was looking. Positive leans forward, negative back.
    """
    n = len(bm["axial"])
    a = [0.0] * n
    if lean == 0.0 or n == 0:
        return a
    p = bm["pelvis_index"]
    torso_idx = [bm["axial"].index(x) for x in bm["torso"]]
    neck_idx = [bm["axial"].index(x) for x in bm["neck"]]
    head_idx = bm["axial"].index(bm["head"]) if bm["head"] else None
    pelvis = 0.5 * lean
    for i in range(n):
        a[i] = pelvis
    if torso_idx:
        last = max(torso_idx)
        for i in torso_idx:
            f = (i - p) / max(last - p, 1)
            a[i] = pelvis + (lean - pelvis) * f
        for i in range(last + 1, n):
            a[i] = lean
    tail_end = sorted(neck_idx + ([head_idx] if head_idx is not None else []))
    for k, i in enumerate(tail_end):
        f = (k + 1) / float(len(tail_end))
        a[i] = lean * (1.0 - head_level * f)
    return a


class Key:
    def __init__(self, drop=0.0, shift=0.0, sway=0.0, lean=0.0, head_level=0.8,
                 limbs=None, name=""):
        self.drop, self.shift, self.sway = drop, shift, sway
        self.lean, self.head_level = lean, head_level
        self.limbs = dict(limbs or {})
        self.name = name

    def copy(self, **changes):
        k = Key(self.drop, self.shift, self.sway, self.lean, self.head_level,
                self.limbs, self.name)
        for a, v in changes.items():
            setattr(k, a, v)
        return k


class Poser:
    """A body plus the measurements every key is written against."""

    def __init__(self, body):
        self.body = body
        bm = self.bm = body.bm
        self.rig = body.rig
        self.fwd, self.up, self.lat = bm["fwd"], bm["up_vec"], bm["lat"]
        self.legs = [l for l in bm["limbs"] if l["role"] == "leg"
                     and l["axial_index"] is not None]
        self.arms = [l for l in bm["limbs"] if l["role"] == "arm"
                     and l["axial_index"] is not None]
        self.leg_len = (sum(l["a"] + l["b"] for l in self.legs) / len(self.legs)
                        if self.legs else 0.0)
        self.centre = (sum((l["rest_root"] for l in self.legs), Vector())
                       / len(self.legs) if self.legs else Vector())
        mw = self.rig.matrix_world
        self._mw = mw
        from . import bodymap
        self._upw = bodymap.axis_vector(bm["up"])

    def height(self, p):
        return (self._mw @ p).dot(self._upw) - self.bm["floor"]

    def outward(self, limb):
        return self.lat if (limb["rest_root"] - self.centre).dot(self.lat) > 0.0 \
            else -self.lat

    def rest_target(self, limb, posed):
        if limb["role"] == "leg":
            return limb["rest_eff"].copy()
        return self.body.carried(posed, limb["attach"], limb["rest_eff"])

    def _spec(self, key, limb):
        s = key.limbs.get(limb["name"], {})
        return (s.get("target"), s.get("pole"),
                s.get("planted", limb["role"] == "leg"))

    def blend(self, a, b, w, w_legs=None, w_arms=None, w_lean=None):
        """The body `w` of the way from key `a` to key `b`.

        Legs, arms and the torso lean may run on their own curves - feet
        usually lead the hips, and getting up from the ground leads with the
        chest. Returns (posed matrices, per-limb solver info).
        """
        wl = w if w_legs is None else w_legs
        wa = w if w_arms is None else w_arms
        wt = w if w_lean is None else w_lean
        body = self.body
        axial = body.bend_axial(
            -self.up * lerp(a.drop, b.drop, w) + self.fwd * lerp(a.shift, b.shift, w)
            + self.lat * lerp(a.sway, b.sway, w),
            lean_angles(self.bm, lerp(a.lean, b.lean, wt),
                        lerp(a.head_level, b.head_level, wt)))
        posed = body.fk(axial)
        overrides = dict(axial)
        infos = {}
        for limb in self.legs + self.arms:
            lw = wl if limb["role"] == "leg" else wa
            ta_fn, pa, planted_a = self._spec(a, limb)
            tb_fn, pb, planted_b = self._spec(b, limb)
            ta = ta_fn(self, limb, posed) if ta_fn else self.rest_target(limb, posed)
            tb = tb_fn(self, limb, posed) if tb_fn else self.rest_target(limb, posed)
            target = ta.lerp(tb, lw)

            pole, pole_w = None, 1.0
            if pa is not None and pb is not None:
                pole = pa.normalized().lerp(pb.normalized(), lw)
                if pole.length < 1e-6:
                    pole = pb
            elif pb is not None:
                pole, pole_w = pb, lw
            elif pa is not None:
                pole, pole_w = pa, 1.0 - lw

            plant_w = lerp(1.0 if planted_a else 0.0, 1.0 if planted_b else 0.0, lw)
            ov, info = body.solve_limb(
                posed, limb, target,
                end_rotation=Matrix.Identity(3) if plant_w > 0.0 else None,
                end_weight=plant_w, pole=pole, pole_weight=pole_w)
            overrides.update(ov)
            infos[limb["name"]] = info
        return body.fk(overrides), infos

    def pose(self, key):
        return self.blend(key, key, 1.0)


# --------------------------------------------------------------------------
# the keys this package knows
# --------------------------------------------------------------------------

def rest_key():
    return Key(name="rest")


def _leg_drop_room(bm, leg, fold_limit):
    up = bm["up_vec"]
    span = leg["rest_root"] - leg["rest_eff"]
    vert = span.dot(up)
    horiz2 = max(span.length_squared - vert * vert, 0.0)
    shortest = max(abs(leg["a"] - leg["b"]), fold_limit * (leg["a"] + leg["b"]))
    return vert - math.sqrt(max(shortest * shortest - horiz2, 0.0))


def support(poser):
    """Forward extent of what the rest-planted legs stand on."""
    rig, fwd = poser.rig, poser.fwd
    coords = []
    for l in poser.legs:
        for n in ([l["end"]] + l["digits"]) if l["end"] else [l["lower"]]:
            b = rig.data.bones[n]
            coords += [b.head_local.dot(fwd), b.tail_local.dot(fwd)]
    return min(coords), max(coords)


def crouch_key(poser, depth=0.6, lean_degrees=None, head_level=0.8,
               arms_forward=True, fold_limit=0.45):
    """The held pose at the end of `actions.crouch` with the same arguments.

    Returns (key, info). Same maths as the crouch clip, so a clip that starts
    or ends here meets that clip without a seam - and `slide_recover` checks
    that it does, against Blender's playback of the real Crouch.
    """
    bm, rig = poser.bm, poser.rig
    upright = bm["upright"]
    lean = (45.0 if upright else 0.0) if lean_degrees is None else lean_degrees
    room = min(_leg_drop_room(bm, l, fold_limit) for l in poser.legs)
    lowest_axial = min(poser.height(pt) for n in bm["axial"]
                       for pt in (rig.data.bones[n].head_local,
                                  rig.data.bones[n].tail_local))
    belly = lowest_axial - 0.08 * bm["height"]
    max_drop = max(0.0, min(room, belly))
    drop = depth * max_drop

    limbs = {}
    if upright and arms_forward:
        def arm_goal(p, l, posed):
            shoulder = posed[l["upper"]].translation
            reach = l["a"] + l["b"]
            rest_eff = p.body.carried(posed, l["attach"], l["rest_eff"])
            lateral = (rest_eff - shoulder).dot(p.lat)
            return (shoulder + p.fwd * (0.6 * reach) - p.up * (0.55 * reach)
                    + p.lat * lateral)
        for l in poser.arms:
            limbs[l["name"]] = {"target": arm_goal, "planted": False}

    key = Key(drop=drop, lean=lean, head_level=head_level, limbs=limbs,
              name="crouch %.2f" % depth)

    # balance: slide the hips until the centre of mass is over the feet
    lo, hi = support(poser)
    centre, half = (lo + hi) * 0.5, (hi - lo) * 0.5
    band = (centre - 0.3 * half, centre + 0.3 * half)

    def com_fwd(shift):
        return poser.body.com(poser.pose(key.copy(shift=shift))[0]).dot(poser.fwd)

    shift = 0.0
    c0 = com_fwd(0.0)
    if not band[0] <= c0 <= band[1]:
        goal = band[0] if c0 < band[0] else band[1]
        x0, f0 = 0.0, c0 - goal
        x1 = -f0
        f1 = com_fwd(x1) - goal
        for _ in range(6):
            if abs(f1) < 1e-5 or abs(f1 - f0) < 1e-12:
                break
            x0, x1, f0 = x1, x1 - f1 * (x1 - x0) / (f1 - f0), f1
            f1 = com_fwd(x1) - goal
        shift = x1
    key.shift = shift
    return key, {"drop": drop, "max_drop": max_drop, "shift": shift, "lean": lean,
                 "limited_by": "legs" if room <= belly else "belly clearance",
                 "support": (lo, hi)}


def slide_key(poser, lead="L", hip_height=0.36, lean_degrees=-35.0, head_level=0.85):
    """The held pose at the end of `actions.slide` with the same arguments."""
    legs = poser.legs
    lead_leg = next(l for l in legs if l["side"] == lead)
    trail_leg = next(l for l in legs if l is not lead_leg)
    L = poser.leg_len
    hip_rest = sum(poser.height(l["rest_root"]) for l in legs) / 2.0
    ankle_rest = sum(poser.height(l["rest_eff"]) for l in legs) / 2.0
    lead_reach = 0.96 * L

    def hip_now(p, posed):
        return sum(p.height(posed[l["upper"]].translation) for l in p.legs) / 2.0

    def lateral(p, l):
        return p.lat * (l["rest_eff"] - l["rest_root"]).dot(p.lat)

    def lead_target(p, l, posed):
        hip = posed[l["upper"]].translation
        dz = ankle_rest - hip_now(p, posed)
        f = math.sqrt(max(lead_reach ** 2 - dz ** 2, 0.0))
        return hip + p.fwd * f + p.up * dz + lateral(p, l)

    def trail_target(p, l, posed):
        hip = posed[l["upper"]].translation
        dz = ankle_rest - hip_now(p, posed)
        return hip + p.fwd * (0.32 * L) + p.up * dz + lateral(p, l)

    up, fwd = poser.up, poser.fwd
    limbs = {
        lead_leg["name"]: {"target": lead_target, "planted": False,
                           "pole": (up + fwd * 0.2).normalized()},
        trail_leg["name"]: {"target": trail_target, "planted": False,
                            "pole": (poser.outward(trail_leg) + fwd * 0.35
                                     - up * 0.15).normalized()},
    }
    arm_side = {l["side"]: l for l in poser.arms}
    for arm, (f, u, o) in ((arm_side.get(trail_leg["side"]), (-0.35, -0.75, 0.3)),
                           (arm_side.get(lead_leg["side"]), (0.55, 0.15, 0.3))):
        if arm is None:
            continue

        def goal(p, l, posed, f=f, u=u, o=o):
            reach = l["a"] + l["b"]
            return posed[l["upper"]].translation + (
                p.fwd * f + p.up * u + p.outward(l) * o) * reach
        limbs[arm["name"]] = {"target": goal, "planted": False}

    return Key(drop=hip_rest - hip_height * L, lean=lean_degrees,
               head_level=head_level, limbs=limbs, name="slide")
