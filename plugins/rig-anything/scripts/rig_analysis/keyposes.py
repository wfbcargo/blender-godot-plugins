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
                 limbs=None, name="", tail_lift=0.0, tail_sway=0.0):
        self.drop, self.shift, self.sway = drop, shift, sway
        self.lean, self.head_level = lean, head_level
        self.limbs = dict(limbs or {})
        self.name = name
        # degrees, summed along the tail: lift raises the tip, sway swings it
        self.tail_lift, self.tail_sway = tail_lift, tail_sway

    def copy(self, **changes):
        k = Key(self.drop, self.shift, self.sway, self.lean, self.head_level,
                self.limbs, self.name, self.tail_lift, self.tail_sway)
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

    def tilt_rotation(self, limb, degrees):
        """(rotation, ankle offset) for a planted end pivoting on its toe.

        Positive raises the heel - or the wrist - off the floor while the toe
        stays put, which is how a crouching rat keeps its forearm skin out of
        the ground."""
        if not degrees or not limb["end"]:
            return Matrix.Identity(3), Vector((0.0, 0.0, 0.0))
        b = self.rig.data.bones[limb["end"]]
        v = b.head_local - b.tail_local                   # toe -> ankle, rest
        axis = self.lat if self.lat.cross(v).dot(self.up) > 0.0 else -self.lat
        rot = Matrix.Rotation(math.radians(degrees), 3, axis)
        return rot, rot @ v - v

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
        if self.bm.get("tail"):
            overrides.update(body.pose_tail(
                posed, lift_deg=lerp(a.tail_lift, b.tail_lift, wt),
                sway_deg=lerp(a.tail_sway, b.tail_sway, wt), floor=self.bm["floor"],
                clearance=0.004 * self.bm["height"]))
            posed = body.fk(overrides)
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
            tilt = lerp(a.limbs.get(limb["name"], {}).get("tilt", 0.0),
                        b.limbs.get(limb["name"], {}).get("tilt", 0.0), lw)
            end_rot, lift = self.tilt_rotation(limb, tilt)
            ov, info = body.solve_limb(
                posed, limb, target + lift,
                end_rotation=end_rot if plant_w > 0.0 else None,
                end_weight=plant_w, pole=pole, pole_weight=pole_w)
            overrides.update(ov)
            infos[limb["name"]] = info
        posed = body.fk(overrides)
        # toes lie on the floor rather than pointing into it
        drapes = {}
        for limb in self.legs:
            drapes.update(body.drape_digits(posed, limb, floor=self.bm["floor"],
                                            clearance=0.004 * self.bm["height"]))
        if drapes:
            overrides.update(drapes)
            posed = body.fk(overrides)
        return posed, infos

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
    tilts = solve_contact_tilts(poser, key)
    skin_limited = limit_drop_by_skin(poser, key)
    return key, {"drop": drop, "max_drop": max_drop, "shift": shift, "lean": lean,
                 "tilts": tilts, "skin_limited_drop": skin_limited,
                 "limited_by": "legs" if room <= belly else "belly clearance",
                 "support": (lo, hi)}


def limit_drop_by_skin(poser, key, clearance=0.004):
    """Raise `key.drop` until no skin passes below the floor. Returns the drop
    removed, or 0.0.

    Legs and belly are not the only things that reach the ground. A sharply
    folded joint near it bulges its skin downward - the rat's wrists sank 7-9
    mm into the floor in a crouch its bones allowed - so the crouch is also as
    deep as the skin permits. The allowance is the rest pose's own lowest skin,
    so a body authored touching the ground is not lifted off it.
    """
    body, bm = poser.body, poser.bm
    floor, height = bm["floor"], bm["height"]
    rest_low = body.skin_lowest(body.fk(), poser._upw)
    if rest_low is None:
        return 0.0
    allowed = min(clearance * height, rest_low - floor)

    def err(drop):
        return (body.skin_lowest(poser.pose(key.copy(drop=drop))[0], poser._upw)
                - floor) - allowed

    full = key.drop
    if err(full) >= -0.001 * height:
        return 0.0
    lo, hi = 0.0, full                     # lo is safe, hi goes through
    if err(0.0) < -0.001 * height:
        return 0.0                         # not the drop's doing; leave it
    for _ in range(12):
        mid = 0.5 * (lo + hi)
        if err(mid) >= -0.001 * height:
            lo = mid
        else:
            hi = mid
    key.drop = lo
    return full - lo


def solve_contact_tilts(poser, key, clearance=0.004, max_tilt=50.0):
    """Lift heels or wrists off the floor where a planted limb's own skin would
    go through it. Mutates `key`; returns {leg: degrees}.

    A rat crouching on flat forefeet sank its wrist skin 8.6 mm into the
    floor: the metacarpal held flat while the forearm folded down onto it. Real
    animals roll onto their toes instead, so each planted leg's end bone pivots
    on its toe until that leg's skin - the lower segment, the end and the
    digits - clears the floor or sits no lower than it rested. A body that does
    not need it gets 0 and an unchanged pose.
    """
    floor, height = poser.bm["floor"], poser.bm["height"]
    tilts = {}
    for l in poser.legs:
        spec = key.limbs.get(l["name"], {})
        if not spec.get("planted", True) or not l["end"]:
            continue
        bones = [l["lower"], l["end"]] + l["digits"]

        def low_at(t):
            trial = key.copy(limbs=dict(key.limbs))
            trial.limbs[l["name"]] = dict(spec, planted=True, tilt=t)
            low, rest_low = poser.body.limb_skin_lowest(poser.pose(trial)[0], bones)
            allowed = min(clearance * height, rest_low - floor)
            return (low - floor) - allowed

        base_err = low_at(0.0)
        if base_err >= -0.001 * height:
            continue
        # Only where rolling onto the toe actually lifts the skin. A foot that
        # already stands near vertical - the rat's forefoot, wrist 4.2 cm above
        # its toe - swings its wrist DOWN whichever way it pivots, and the first
        # version of this pushed it to the 50 degree limit and sank it deeper.
        if low_at(5.0) <= base_err:
            continue
        lo, hi = 0.0, max_tilt
        if low_at(hi) < 0.0:
            lo = hi                                         # best we can do
        else:
            for _ in range(10):
                mid = 0.5 * (lo + hi)
                if low_at(mid) < 0.0:
                    lo = mid
                else:
                    hi = mid
        t = hi if lo < max_tilt else max_tilt
        key.limbs[l["name"]] = dict(spec, planted=True, tilt=t)
        tilts[l["name"]] = round(t, 2)
    return tilts


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


# --------------------------------------------------------------------------
# limb targets for bodies that are not bipeds
# --------------------------------------------------------------------------

def leg_zone(poser, limb):
    """Where a leg sits along the body: +1 front rank, -1 rear, 0 middle."""
    pos = [l["forward_pos"] for l in poser.legs]
    centre = (max(pos) + min(pos)) * 0.5
    half = (max(pos) - min(pos)) * 0.5
    return 0.0 if half < 1e-9 else (limb["forward_pos"] - centre) / half


def hip_relative(fold=1.0, f=0.0, u=0.0, o=0.0):
    """Target: the leg's rest reach from its hip scaled by `fold`, then pushed
    forward / up / outward by fractions of the leg's length. Moves with the
    body, so it is the shape of a leg in the air."""
    def fn(p, l, posed):
        hip = posed[l["upper"]].translation
        reach = l["a"] + l["b"]
        return (hip + (l["rest_eff"] - l["rest_root"]) * fold
                + (p.fwd * f + p.up * u + p.outward(l) * o) * reach)
    return fn


def along_floor(direction, reach=0.9):
    """Target: on the floor, `reach` of the leg's length from wherever its hip
    is now, in `direction(poser, limb)` - a leg stretched out along the ground."""
    def fn(p, l, posed):
        hip = posed[l["upper"]].translation
        dz = p.height(l["rest_eff"]) - p.height(hip)
        span = reach * (l["a"] + l["b"])
        d = direction(p, l)
        # Keep the leg's rest splay only across the stretch direction, and pay
        # for it out of the reach. A hexapod's legs spend much of their length
        # sideways; ignoring that asked them for 104% of it.
        side = (l["rest_eff"] - l["rest_root"]).dot(p.lat) * (1.0 - abs(d.dot(p.lat)))
        h = math.sqrt(max(span * span - dz * dz - side * side, 0.0))
        return hip + d * h + p.up * dz + p.lat * side
    return fn


def _rise_room(poser, reach=0.95):
    """How far the body can rise with every foot still on its rest spot."""
    rooms = []
    for l in poser.legs:
        span = l["rest_root"] - l["rest_eff"]
        vert = span.dot(poser.up)
        horiz2 = max(span.length_squared - vert * vert, 0.0)
        top = reach * (l["a"] + l["b"])
        rooms.append(math.sqrt(max(top * top - horiz2, 0.0)) - vert)
    return max(0.0, min(rooms))


def belly_height(poser):
    """Height of the lowest rest vertex skinned mainly to the spine.

    Measured on the skin, not the bones: the hexapod's body hangs well below
    its spine chain, and a skid dropped by the bones put its belly 4.5 cm
    through the floor. Falls back to the lowest axial bone point."""
    import bpy
    rig, bm = poser.rig, poser.bm
    axial = set(bm["axial"]) | {n for t in bm["tails"] for n in t}
    low = None
    for o in bpy.data.objects:
        if o.type != "MESH" or not any(m.type == "ARMATURE" and m.object == rig
                                       for m in o.modifiers):
            continue
        names = {g.index: g.name for g in o.vertex_groups}
        mw = o.matrix_world
        for v in o.data.vertices:
            best = max(v.groups, key=lambda g: g.weight, default=None)
            if best is None or names.get(best.group) not in axial:
                continue
            h = (mw @ v.co).dot(poser._upw) - bm["floor"]
            low = h if low is None else min(low, h)
    if low is None:
        low = min(poser.height(pt) for n in bm["axial"]
                  for pt in (rig.data.bones[n].head_local, rig.data.bones[n].tail_local))
    return low


def skid_key(poser, belly_clearance=0.05):
    """A horizontal body's slide: belly low, front legs stretched forward along
    the floor, rear legs back, middle legs out to the sides.

    Returns (key, info). A biped slides on `slide_key` instead.
    """
    bm = poser.bm
    clearance = belly_clearance * bm["height"]
    drop = max(0.0, belly_height(poser) - clearance)

    def direction(p, l):
        z = leg_zone(p, l)
        if z > 0.33:
            return p.fwd
        if z < -0.33:
            return -p.fwd
        return p.outward(l)

    limbs = {l["name"]: {"target": along_floor(direction, 0.9), "planted": False}
             for l in poser.legs}
    # The belly estimate is a start, not an answer: skin weighted to the legs
    # and hips also hangs below the spine. Solve the drop against the skinned
    # mesh itself until its lowest point sits at the clearance.
    # The rear legs stretch back along the same floor the tail lies on, and on
    # the quadruped went straight through it; a skidding animal lifts its tail.
    key = Key(drop=drop, limbs=limbs, name="skid", tail_lift=30.0)
    floor = bm["floor"]
    low = None
    for _ in range(6):
        low = poser.body.skin_lowest(poser.pose(key)[0], poser._upw)
        if low is None:
            break
        err = (low - floor) - clearance
        if abs(err) < 0.002 * bm["height"]:
            break
        key.drop = max(0.0, key.drop + err)
    return key, {"drop": key.drop,
                 "skin_lowest": None if low is None else low - floor}


def jump_keys(poser):
    """load -> launch -> tuck -> reach, for any leg count, authored in place.

    The engine moves the body through the air; the clip only shapes it. Launch
    rises as far as the legs reach with every foot still down; tuck folds the
    legs under, front forward and rear back; reach puts the front feet out and
    down to meet the ground.
    """
    load, _ = crouch_key(poser, depth=0.7)

    def legs_by_zone(front, rear, middle):
        out = {}
        for l in poser.legs:
            z = leg_zone(poser, l)
            fold, f, o = front if z > 0.33 else rear if z < -0.33 else middle
            out[l["name"]] = {"target": hip_relative(fold, f, 0.0, o), "planted": False}
        return out

    # Launch is a stretch, not a rise: rear legs driven back, front legs lifting
    # forward. Rising on planted feet needs spare leg length, and a body that
    # stands on nearly straight legs has none - the quadruped's rise came out
    # 0.0 and its jump had no take-off at all.
    rise = max(_rise_room(poser), 0.05 * poser.leg_len)
    launch = Key(drop=-rise, limbs=legs_by_zone((0.65, 0.2, 0.0), (0.85, -0.35, 0.0),
                                                (0.8, -0.1, 0.1)), name="launch")

    tuck = Key(limbs=legs_by_zone((0.55, 0.15, 0.0), (0.55, -0.15, 0.0),
                                  (0.55, 0.0, 0.1)), name="tuck")
    reach = Key(limbs=legs_by_zone((0.95, 0.22, 0.0), (0.9, -0.05, 0.0),
                                   (0.9, 0.0, 0.05)), name="reach")
    # the tail streams up through the launch and balances through the air
    load.tail_lift, launch.tail_lift, tuck.tail_lift, reach.tail_lift = 0.0, 25.0, 15.0, 20.0
    return [load, launch, tuck, reach]
