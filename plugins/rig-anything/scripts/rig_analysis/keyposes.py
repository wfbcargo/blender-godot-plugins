"""Key poses: whole-body poses in body terms, and blends between them.

`actions.crouch` and `actions.slide` each hand-wrote a path from rest to one
pose. The next actions are not like that - a slide recovery runs slide pose ->
deep crouch -> stand, a crouch walk is a crouch with a gait laid over it - so
the pose itself becomes a value:

    Key(drop, shift, sway, lean, head_level, limbs={name: spec}, posture={...})

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
    planted  hold the end bone at its rest orientation (a flat foot). A number
             0..1 blends between following the shin and holding it - a foot
             lifting off or coming down
    tilt     degrees the planted end rolls over its toe, or
             fn(poser, limb, posed, target) -> degrees, solved against the body
             as it is posed this frame
"""

from __future__ import annotations

import math

from mathutils import Matrix, Vector

from . import motion

# A foot stepping from one spot on the floor to another (`Poser._step`): the share
# of the blend spent lifting it at the start and setting it down at the end, and
# how high it goes, as a share of the leg.
STEP_SHARE = 0.15
STEP_LIFT = 0.1

# A relaxed hand: degrees each finger joint curls toward the palm, by its place
# along the finger from the hand (knuckle, middle joint, end joint, further).
# Most of it at the knuckles, least at the tips: a curl held at the tips reads
# as a claw (the first pass, 14/22/16, did). The fingers cascade - the index
# curls least, each finger further from the thumb FINGER_CASCADE more - and
# close toward the middle of the hand by FINGER_CLOSE of the angle between
# them (at most FINGER_CLOSE_MAX_DEG each), since a hanging hand's fingers
# touch. The thumb does not oppose: its base swings in toward the side of the
# index finger's middle joint by THUMB_IN of the way (at most
# THUMB_IN_MAX_DEG), its end joints curl a little. A hand at rest hangs this
# way; MPFB's rest pose holds the fingers straight and apart, which reads as a
# hand held up flat. `Key.hands` scales it per arm.
FINGER_CURL_DEG = (22.0, 20.0, 12.0, 8.0)
FINGER_CASCADE = 0.1
FINGER_CLOSE = 0.85
FINGER_CLOSE_MAX_DEG = 14.0
THUMB_CURL_DEG = (0.0, 10.0, 8.0, 6.0)
THUMB_IN = 0.7
THUMB_IN_MAX_DEG = 30.0


def hand_digits(rig, limb):
    """The finger bones of an arm's hand, found by the skeleton's shape.

    Returns [(bone name, curl axis in armature rest space, degrees)] with
    parents before children, or [] when the hand has fewer than three digits.
    A digit is a path from the hand (the arm's end bone) to a leaf; the thumb
    is the path pointing furthest from the others. The palm is the plane
    through the wrist and the fingers' first joints, and its palm side is where
    the thumb and the fingers' own rest bend lie. A bone several digits share
    (a Rigify palm bone carrying both index and thumb) is left alone.
    """
    if not limb.get("end"):
        return []
    hand = rig.data.bones[limb["end"]]
    leaves = [b for b in hand.children_recursive if not b.children]
    if len(leaves) < 3:
        return []
    paths = []
    for lf in leaves:
        path, c = [], lf
        while c is not None and c != hand:
            path.insert(0, c)
            c = c.parent
        paths.append(path)
    wrist = hand.head_local
    dirs = [(p[-1].tail_local - wrist).normalized() for p in paths]
    mean = sum(dirs, Vector()).normalized()
    thumb = min(range(len(paths)), key=lambda i: dirs[i].dot(mean))
    fingers = [p for i, p in enumerate(paths) if i != thumb]
    pts = [p[0].tail_local for p in fingers] + [wrist]
    centre = sum(pts, Vector()) / len(pts)
    # plane normal: the smallest principal axis of the points
    cov = Matrix(((0.0,) * 3,) * 3)
    for q in pts:
        d = q - centre
        for i in range(3):
            for j in range(3):
                cov[i][j] += d[i] * d[j]
    import numpy as np
    w, v = np.linalg.eigh(np.array([list(r) for r in cov]))
    n = Vector(v[:, 0].tolist()).normalized()
    side = (paths[thumb][-1].tail_local - centre).dot(n)
    for p in fingers:
        a = p[0].tail_local - p[0].head_local
        a.normalize()
        t = p[-1].tail_local - p[0].head_local
        side += (t - a * t.dot(a)).dot(n)
    palm = n if side > 0.0 else -n
    count = {}
    for p in paths:
        for b in p:
            count[b.name] = count.get(b.name, 0) + 1
    # fingers ranked from the thumb: the index is the one whose root lies nearest it
    t_root = paths[thumb][0].head_local
    order = sorted(range(len(paths)), key=lambda i: (paths[i][0].head_local - t_root).length)
    rank = {i: r for r, i in enumerate(j for j in order if j != thumb)}
    index = next(j for j in order if j != thumb)

    def flat(v):
        return (v - palm * v.dot(palm)).normalized()
    mid_dir = flat(sum((dirs[i] for i in rank), Vector()))
    # where the thumb tip rests: beside the index finger's middle joint, a
    # finger's width toward the thumb and half one toward the palm
    ip = paths[index]
    width = min(((paths[j][0].head_local - ip[0].head_local).length for j in rank if j != index),
                default=0.02)
    joint = ip[1].head_local if len(ip) > 1 else ip[0].tail_local
    toward = flat(t_root - ip[0].head_local)
    rest_spot = joint + toward * width + palm * 0.5 * width
    out, seen = [], set()
    for i, p in enumerate(paths):
        is_thumb = i == thumb
        table = THUMB_CURL_DEG if is_thumb else FINGER_CURL_DEG
        scale = 1.0 if is_thumb else 1.0 + FINGER_CASCADE * (rank[i] - 1)
        k = 0
        for b in p:
            if count[b.name] > 1:
                continue
            d = (b.tail_local - b.head_local).normalized()
            axis = d.cross(palm)
            if b.name in seen or axis.length < 1e-6:
                k += 1
                continue
            seen.add(b.name)
            rot = Matrix.Rotation(math.radians(table[min(k, len(table) - 1)] * scale), 3,
                                  axis.normalized())
            if k == 0 and is_thumb:
                # swing the thumb in toward the index's side instead of across the palm
                tip = p[-1].tail_local - b.head_local
                want = rest_spot - b.head_local
                sw = tip.cross(want)
                if sw.length > 1e-9:
                    ang = min(THUMB_IN * tip.angle(want), math.radians(THUMB_IN_MAX_DEG))
                    rot = Matrix.Rotation(ang, 3, sw.normalized()) @ rot
            elif k == 0:
                # close the finger toward the middle of the hand, in the palm's plane
                f = flat(d)
                ang = math.atan2(f.cross(mid_dir).dot(palm), f.dot(mid_dir))
                cap = math.radians(FINGER_CLOSE_MAX_DEG)
                ang = max(-cap, min(cap, FINGER_CLOSE * ang))
                rot = Matrix.Rotation(ang, 3, palm) @ rot
            q = rot.to_quaternion()
            ax, ang = q.to_axis_angle()
            if ang > 1e-6:
                out.append((b.name, ax.normalized(), round(math.degrees(ang), 2)))
            k += 1
    depth = {b.name: len(b.parent_recursive) for b in hand.children_recursive}
    out.sort(key=lambda e: depth[e[0]])
    return out


def on_floor(fn):
    """Mark a leg target as a spot on the floor, so a blend to or from another
    floor spot steps between them (`Poser._step`). Returns `fn`."""
    fn.on_floor = True
    return fn


def _means_floor(fn):
    # no target is the leg at rest, standing where it stood
    return fn is None or getattr(fn, "on_floor", False)


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


def flex_angles(bm, flex):
    """Total pitch per axial bone for a spine arched by `flex` degrees.

    Horizontal bodies only. The torso between the rear and front limb girdles
    bends as a bow: its rear end pitches up by `flex`, its front end down, so the
    middle rises (flexed, positive) or sags (extended, negative). A galloping
    dog does this every stride - flexing brings the hind feet up under it,
    extending throws the forefeet out - and it is a large part of how the
    stride gets longer than the legs alone allow. Neck and head keep their
    level; bones behind the pelvis ride it.
    """
    n = len(bm["axial"])
    a = [0.0] * n
    if not flex or n == 0 or bm["upright"]:
        return a
    p = bm["pelvis_index"]
    idx = [bm["axial"].index(x) for x in bm["torso"]]
    if len(idx) < 2:
        return a
    first, last = min(idx), max(idx)
    for i in range(n):
        if i < first:
            a[i] = -flex
        elif i <= last:
            a[i] = -flex + 2.0 * flex * (i - first) / float(max(last - first, 1))
    return a


# The movements a `posture` names, in degrees. All are pitches about the body
# map's lateral axis, and positive always moves the head end toward `fwd` (down,
# on a horizontal body) - the same sense as `lean`, so no rotation sign is read.
POSTURE = ("pelvis", "flex", "neck")


def posture_angles(bm, posture):
    """Total pitch per axial bone for a held posture: {"pelvis", "flex", "neck"}.

    pelvis  anterior tilt of the pelvis bone; everything above it rides along
    flex    the trunk above the pelvis bends forward by this much in total,
            ramped so the upper bones take more (a thoracic hunch, not a hinge
            at the waist). A torso of one bone takes it all on that bone.
    neck    the neck and head bend forward by this much relative to the top of
            the trunk, shared equally; negative craned back up. A body with no
            neck bones bends the head alone.

    Walter's hunch, which kept his gaze ahead, is {"pelvis": 4, "flex": 30,
    "neck": -22}. Unlike `lean`, nothing is handed back automatically: a
    posture says exactly where every segment points.
    """
    names = bm["axial"]
    n = len(names)
    a = [0.0] * n
    if not posture or n == 0:
        return a
    unknown = set(posture) - set(POSTURE)
    if unknown:
        raise ValueError("unknown posture movement %s - posture takes %s"
                         % (", ".join(sorted(unknown)), ", ".join(POSTURE)))
    p = bm["pelvis_index"]
    inc = [0.0] * n
    inc[p] += float(posture.get("pelvis", 0.0))
    flex = float(posture.get("flex", 0.0))
    torso = sorted(names.index(x) for x in bm["torso"])
    above = [i for i in torso if i > p] or ([p] if p in torso else [])
    if flex and above:
        ramp = [max(i - p, 1) for i in above]
        for i, r in zip(above, ramp):
            inc[i] += flex * r / float(sum(ramp))
    neck = float(posture.get("neck", 0.0))
    top = sorted(names.index(x) for x in bm["neck"])
    if bm["head"]:
        top.append(names.index(bm["head"]))
    if neck and top:
        for i in top:
            inc[i] += neck / len(top)
    total = 0.0
    for i in range(p, n):
        total += inc[i]
        a[i] = total
    for i in range(p):
        a[i] = a[p]                       # bones behind the pelvis ride it
    return a


def stance_shift(poser, limb, width):
    """Sideways move, armature space, putting a leg's rest effector (the ankle)
    `width` times its hip's offset from the body's midline: 1.0 stands the
    ankle under the hip, below 1 narrower, None or the rest ratio changes
    nothing. The midline is the mean of the leg roots."""
    if width is None:
        return Vector((0.0, 0.0, 0.0))
    lat = poser.lat
    hip = (limb["rest_root"] - poser.centre).dot(lat)
    ankle = (limb["rest_eff"] - poser.centre).dot(lat)
    return lat * (width * hip - ankle)


class Key:
    def __init__(self, drop=0.0, shift=0.0, sway=0.0, lean=0.0, head_level=0.8,
                 limbs=None, name="", tail_lift=0.0, tail_sway=0.0, flex=0.0,
                 wings=None, maw=None, posture=None, trunk=None, hands=None):
        self.drop, self.shift, self.sway = drop, shift, sway
        self.lean, self.head_level = lean, head_level
        self.limbs = dict(limbs or {})
        self.name = name
        # degrees, summed along the tail: lift raises the tip, sway swings it
        self.tail_lift, self.tail_sway = tail_lift, tail_sway
        # degrees of spine arch, see `flex_angles`
        self.flex = flex
        # a `wings.state` (both sides) or {"L": state, "R": state}; None is the
        # Poser's ground pose for wings - folded
        self.wings = wings
        # a `maw.state`; None is the mouth at rest - closed
        self.maw = maw
        # a held posture, see `posture_angles`; None is the rest shape
        self.posture = dict(posture) if posture else None
        # per axial bone degrees added on top of everything else, from
        # `upper.trunk`: {"pitch": [...], "yaw": [...], "roll": [...]} - a
        # pelvis turning and listing under a counter-rotating chest
        self.trunk = trunk
        # {arm name: share of the relaxed finger curl}; an arm not named is
        # relaxed (1.0) - see FINGER_CURL_DEG
        self.hands = dict(hands) if hands else None

    def copy(self, **changes):
        k = Key(self.drop, self.shift, self.sway, self.lean, self.head_level,
                self.limbs, self.name, self.tail_lift, self.tail_sway, self.flex,
                self.wings, self.maw, self.posture, self.trunk, self.hands)
        for a, v in changes.items():
            setattr(k, a, v)
        return k


class Poser:
    """A body plus the measurements every key is written against."""

    def __init__(self, body, wings_folded=1.0):
        self.body = body
        bm = self.bm = body.bm
        self.rig = body.rig
        self.fwd, self.up, self.lat = bm["fwd"], bm["up_vec"], bm["lat"]
        self.legs = [l for l in bm["limbs"] if l["role"] == "leg"
                     and l["axial_index"] is not None]
        self.arms = [l for l in bm["limbs"] if l["role"] == "arm"
                     and l["axial_index"] is not None]
        # Wings are not arms: nothing that reaches or counter-swings moves
        # them. On the ground they are carried folded - a creature walking with
        # its wings out as modelled is not walking - so a key that says nothing
        # about wings means `wings_folded`, and the body's GROUND REST is that
        # pose. `body.ground_rest` is what "frame one is rest" is measured against.
        self.wing_rig = None
        self.wing_default = None
        # A mouth is closed unless a key opens it, so every clip authored
        # before a maw was built plays the same after.
        self.maw_rig = None
        if bm.get("maw"):
            from . import maw as maw_mod
            self.maw_rig = maw_mod.MawRig(body)
        self.leg_len = (sum(l["a"] + l["b"] for l in self.legs) / len(self.legs)
                        if self.legs else 0.0)
        self.centre = (sum((l["rest_root"] for l in self.legs), Vector())
                       / len(self.legs) if self.legs else Vector())
        mw = self.rig.matrix_world
        self._mw = mw
        from . import bodymap
        self._upw = bodymap.axis_vector(bm["up"])
        # An upright body's hands hang relaxed, fingers curled (`hand_digits`).
        # Like folded wings, that is its ground rest: frame one of a crouch
        # starts from it, not from MPFB's flat splayed hand.
        self.hands = {}
        if bm.get("upright"):
            for arm in self.arms:
                digits = hand_digits(self.rig, arm)
                if digits:
                    self.hands[arm["name"]] = [
                        (n, body.rest[n].to_3x3().inverted() @ axis, deg) for n, axis, deg in digits]
        if bm.get("wings"):
            from . import wings as wing_mod
            self.wing_rig = wing_mod.WingRig(body)
            self.wing_default = wing_mod.state(fold=wings_folded, tuck=1.0)
        if bm.get("wings") or self.hands:
            body.ground_rest = self.pose(Key(name="ground rest"))[0]

    def height(self, p):
        return (self._mw @ p).dot(self._upw) - self.bm["floor"]

    def outward(self, limb):
        return self.lat if (limb["rest_root"] - self.centre).dot(self.lat) > 0.0 \
            else -self.lat

    def foot_lift(self, limb):
        """How far this foot's end sits above the lowest skin under it, at rest.

        The height its target may not go below, so the sole lands on the floor rather than
        through it. Measured as a distance rather than as a rest height above the floor,
        because a clip the engine has thrown into the air lowers the poser's floor by the
        jump's height - and a foot hanging under an airborne body is meant to be below where
        it stands, just not below the ground the engine has put beneath it.
        """
        cache = self.__dict__.setdefault("_foot_lifts", {})
        if limb["name"] in cache:
            return cache[limb["name"]]
        bones = [n for n in [limb["end"] or limb["lower"]] + list(limb.get("digits") or []) if n]
        entries = [(n, self.rig.data.bones[n].head_local.copy(),
                    self.rig.data.bones[n].tail_local.copy()) for n in bones]
        bottoms = [self.height(p) for _, head, tail in entries for p in (head, tail)]
        for measured in self.body.chain_skin(entries).values():
            if measured["rest_bottom"] is not None:      # skin, where the bone is not the lowest
                bottoms.append(measured["rest_bottom"] - self.bm["floor"])
        cache[limb["name"]] = self.height(limb["rest_eff"]) - min(bottoms)
        return cache[limb["name"]]

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

    def _step(self, limb, ta_fn, tb_fn, ta, tb, w, target):
        """A foot moving between two spots on the floor steps there: it lifts,
        crosses over the floor and comes straight down, rather than dragging.

        Both keys of a slide recovery stand the foot on the floor - Slide's far out
        along it, the squat's under the hips - and the straight blend between them
        drew a Rigify biped's feet in along the ground as the body rose onto them:
        the lead heel reached the floor 0.41 m short of its spot and skidded in, the
        trail foot 0.14 m (`floor_skid`, tolerance 0.009), and a Rigify dog's
        forefeet 0.29 m. Here the first and last `STEP_SHARE` of the blend lift and
        lower the foot in place and the travel happens between, `STEP_LIFT` of the
        leg high, or the distance if that is shorter.

        Only between two keys that both mean the floor (`on_floor`): a leg at rest,
        or a target marked as lying on it. Judged by the targets' heights instead, a
        jump's tuck - asked for under the floor while the hips are still low - read
        as on it, and an MPFB woman's feet were lifted 10.5 cm a frame before her
        take-off. A foot standing on one spot in both keys (a crouch, a gait's
        key blended with itself) never moves."""
        if not (_means_floor(ta_fn) and _means_floor(tb_fn)):
            return target
        d = tb - ta
        across = d - self.up * d.dot(self.up)
        lift_max = STEP_LIFT * (limb["a"] + limb["b"])
        amount = min(1.0, across.length / lift_max)
        if amount <= 0.0:
            return target
        r = STEP_SHARE
        over = motion.smoothstep((w - r) / (1.0 - 2.0 * r))
        raised = min(motion.smoothstep(w / r), motion.smoothstep((1.0 - w) / r))
        moved = ta + across * lerp(w, over, amount) + self.up * (d.dot(self.up) * w)
        return moved + self.up * (raised * min(lift_max, across.length))

    def blend(self, a, b, w, w_legs=None, w_arms=None, w_lean=None, w_wings=None,
              w_maw=None):
        """The body `w` of the way from key `a` to key `b`.

        Legs, arms, wings and the torso lean may run on their own curves - feet
        usually lead the hips, and getting up from the ground leads with the
        chest. Returns (posed matrices, per-limb solver info).
        """
        wl = w if w_legs is None else w_legs
        wa = w if w_arms is None else w_arms
        wt = w if w_lean is None else w_lean
        ww = w if w_wings is None else w_wings
        body = self.body
        angles = lean_angles(self.bm, lerp(a.lean, b.lean, wt),
                             lerp(a.head_level, b.head_level, wt))
        flex = lerp(getattr(a, "flex", 0.0), getattr(b, "flex", 0.0), w)
        if flex:
            angles = [x + y for x, y in zip(angles, flex_angles(self.bm, flex))]
        post_a, post_b = getattr(a, "posture", None) or {}, getattr(b, "posture", None) or {}
        if post_a or post_b:
            held = {k: lerp(post_a.get(k, 0.0), post_b.get(k, 0.0), wt)
                    for k in set(post_a) | set(post_b)}
            angles = [x + y for x, y in zip(angles, posture_angles(self.bm, held))]
        yaw = roll = None
        tr_a, tr_b = getattr(a, "trunk", None) or {}, getattr(b, "trunk", None) or {}
        if tr_a or tr_b:
            n = len(angles)

            def term(k):
                va, vb = tr_a.get(k) or [0.0] * n, tr_b.get(k) or [0.0] * n
                return [lerp(x, y, wt) for x, y in zip(va, vb)]
            angles = [x + y for x, y in zip(angles, term("pitch"))]
            yaw, roll = term("yaw"), term("roll")
        axial = body.bend_axial(
            -self.up * lerp(a.drop, b.drop, w) + self.fwd * lerp(a.shift, b.shift, w)
            + self.lat * lerp(a.sway, b.sway, w), angles, yaw, roll)
        posed = body.fk(axial)
        overrides = dict(axial)
        if self.bm.get("tail"):
            overrides.update(body.pose_tail(
                posed, lift_deg=lerp(a.tail_lift, b.tail_lift, wt),
                sway_deg=lerp(a.tail_sway, b.tail_sway, wt), floor=self.bm["floor"],
                clearance=0.004 * self.bm["height"]))
            posed = body.fk(overrides)
        a_maw, b_maw = getattr(a, "maw", None), getattr(b, "maw", None)
        if self.maw_rig is not None and (a_maw is not None or b_maw is not None):
            from . import maw as maw_mod
            overrides.update(self.maw_rig.pose(
                posed, maw_mod.blend_states(a_maw, b_maw, w if w_maw is None else w_maw)))
            posed = body.fk(overrides)
        if self.wing_rig is not None:
            from . import wings as wing_mod
            states = wing_mod.blend_states(
                a.wings if a.wings is not None else self.wing_default,
                b.wings if b.wings is not None else self.wing_default, ww)
            overrides.update(self.wing_rig.pose(posed, states))
            posed = body.fk(overrides)
        infos, plant_ws = {}, {}
        for limb in self.legs + self.arms:
            lw = wl if limb["role"] == "leg" else wa
            ta_fn, pa, planted_a = self._spec(a, limb)
            tb_fn, pb, planted_b = self._spec(b, limb)
            # a pole may depend on the body as posed this frame, like a target
            pa = pa(self, limb, posed) if callable(pa) else pa
            pb = pb(self, limb, posed) if callable(pb) else pb
            ta = ta_fn(self, limb, posed) if ta_fn else self.rest_target(limb, posed)
            tb = tb_fn(self, limb, posed) if tb_fn else self.rest_target(limb, posed)
            target = ta.lerp(tb, lw)
            if limb["role"] == "leg" and 0.0 < lw < 1.0:
                target = self._step(limb, ta_fn, tb_fn, ta, tb, lw, target)

            pole, pole_w = None, 1.0
            if pa is not None and pb is not None:
                pole = pa.normalized().lerp(pb.normalized(), lw)
                if pole.length < 1e-6:
                    pole = pb
            elif pb is not None:
                pole, pole_w = pb, lw
            elif pa is not None:
                pole, pole_w = pa, 1.0 - lw

            plant_w = lerp(float(planted_a), float(planted_b), lw)

            def tilt_of(key, t):
                v = key.limbs.get(limb["name"], {}).get("tilt", 0.0)
                return v(self, limb, posed, t) if callable(v) else v
            tilt = lerp(tilt_of(a, ta), tilt_of(b, tb), lw)
            end_rot, lift = self.tilt_rotation(limb, tilt)
            if limb["role"] == "leg":
                # No foot is asked to stand below the floor. Both keys' targets are evaluated
                # against *this* frame's body, so a key meaning "hang the leg 80% of its
                # length under the hips" resolves, while the hips are still down in a crouch,
                # to a point under the ground: the one frame between a jump's load and its
                # launch put an MPFB woman's toe 1.5 cm through the floor and her skin 2.5 cm.
                # Held so the sole rests on the floor, the leg stays down until the hips have
                # risen enough for the target to clear it - which is what a take-off looks
                # like. A planted foot and a slide's floor targets already sit exactly there.
                # A foot the plan has in the air is tested on the ankle the solve is given -
                # the target plus the roll's lift. A gait that folds a swinging foot takes the
                # fold's lift off the target, and tested without it a cricket's hind foot read
                # as under the floor for the last third of every swing: held planted at floor
                # height while the stride carried it on, its toe dragged 1 mm. A planted foot
                # rolling over its toe keeps the test without the lift: that is what holds its
                # toe on the floor as the heel rises (with it, a dog's toe sank 3.4 mm).
                swinging = plant_w < 1.0
                if self.height(target + lift if swinging else target) < self.foot_lift(limb):
                    # It has not left the ground yet, so it stays where it was planted -
                    # whole, not just at that height: clamping the height alone let the foot
                    # slide 1.1 cm sideways towards the launch's outward target while it was
                    # still down, and the export's re-check called it skating. Still planted,
                    # too: released early, the sole pitches into the floor even with the
                    # ankle where it rests.
                    target = ta.copy()
                    under = self.foot_lift(limb) - self.height(target + lift if swinging else target)
                    if under > 0.0:                       # in case it was already down there
                        target = target + self.up * under
                    plant_w = 1.0
            plant_ws[limb["name"]] = plant_w
            ov, info = body.solve_limb(
                posed, limb, target + lift,
                end_rotation=end_rot if plant_w > 0.0 else None,
                end_weight=plant_w, pole=pole, pole_weight=pole_w)
            overrides.update(ov)
            infos[limb["name"]] = info
        posed = body.fk(overrides)
        drapes = {}
        for limb in self.legs:
            # Only a foot in the air: a planted one is already held where its
            # contact is solved, and draping it slid a walking bird's toes 1-2 cm.
            if limb["end"] and plant_ws.get(limb["name"], 1.0) < 1.0:
                # Unplanted, a foot follows the shin, and a shin pitched forward tips
                # the sole into the floor: a dragon pushing off or drawing its legs in
                # from a skid put its toes 2.5 cm into it. Toe bones did not save the
                # foot above them - only the toes were laid down, from wherever the
                # foot ended - so a Rigify biped's tucked trail foot in a slide stayed
                # 2.7 cm under the floor at the ball (skin -2.7 cm) with its toe
                # resting neatly on top. The foot turns up onto the floor first, by its
                # own skin (`lay_on_floor`), then its toes lie down from there.
                laid = body.lay_on_floor(posed, limb["end"], floor=self.bm["floor"],
                                         clearance=0.004 * self.bm["height"])
                if laid:
                    overrides.update(laid)
                    posed = body.fk(overrides)
            # toes lie on the floor rather than pointing into it
            drapes.update(body.drape_digits(posed, limb, floor=self.bm["floor"],
                                            clearance=0.004 * self.bm["height"]))
        if drapes:
            overrides.update(drapes)
            posed = body.fk(overrides)
        if self.hands:
            for arm_name, digits in self.hands.items():
                share = lerp((a.hands or {}).get(arm_name, 1.0), (b.hands or {}).get(arm_name, 1.0), wa)
                if not share:
                    continue
                for n, axis_local, deg in digits:
                    parent = body.rig.data.bones[n].parent.name
                    posed[n] = (posed[parent] @ body.rest_local[n]
                                @ Matrix.Rotation(math.radians(deg * share), 4, axis_local))
                    overrides[n] = posed[n]
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
    # A ground root - MPFB's, Mixamo's, any game rig's motion bone lying at the
    # floor under the whole skeleton - is on the axial chain but carries no
    # trunk: counted, it put the "belly" under the floor and allowed an MPFB
    # woman no drop at all, so her crouch was a 33 cm hip shift on straight
    # legs. That bone is `roles["root"]`. It used to be "axial bones wholly
    # below the lowest ankle", which picks the same bone on every fixture (MPFB's
    # `root`; none on Rigify or the dog). The two would part on an unskinned
    # motion bone at hip height (the role drops it: it carries no trunk) or a
    # skinned axial bone under the ankles (the role keeps it: it is body).
    root = (bm.get("roles") or {}).get("root")
    trunk = [n for n in bm["axial"] if n != root] or bm["axial"]
    lowest_axial = min(poser.height(pt) for n in trunk
                       for pt in (rig.data.bones[n].head_local,
                                  rig.data.bones[n].tail_local))
    belly = lowest_axial - 0.08 * bm["height"]
    max_drop = max(0.0, min(room, belly))
    drop = depth * max_drop

    limbs = {}
    if upright and arms_forward:
        # Hanging forward against gravity, out from the thighs, elbows bent -
        # `upper.arm_spec`. The old goal kept the rest hand's sideways offset,
        # and from an A-pose one arm reached far out to the side.
        from . import upper as upper_mod
        for l in poser.arms:
            limbs[l["name"]] = upper_mod.arm_spec(poser, l, forward=28.0, out=20.0,
                                                  elbow=35.0, hand_in=3.0)

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
        lead_leg["name"]: {"target": on_floor(lead_target), "planted": False,
                           "pole": (up + fwd * 0.2).normalized()},
        trail_leg["name"]: {"target": on_floor(trail_target), "planted": False,
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


def within_reach(p, limb, posed, target, share=0.95):
    """A foot goes where it is asked, or as near as the leg reaches - giving up
    height before its place on the ground.

    Pulled straight back toward the hip, a foot out of reach loses its ground
    position with its height, so it meets the floor short of its spot and skids
    the rest of the way once the body comes within reach: a cricket's forefeet
    landed and slid 0.5 mm, 1.7% of the body. Kept over the spot, it waits in
    the air and comes straight down. Only when the spot itself is out of reach
    across the ground does the foot fall short, as close as the leg goes."""
    hip = posed[limb["upper"]].translation
    d = target - hip
    top = share * (limb["a"] + limb["b"])
    if d.length <= top:
        return target
    up = p.up
    vert = d.dot(up)
    across = d - up * vert
    if across.length >= top:
        return hip + across.normalized() * top
    return hip + across + up * math.copysign(math.sqrt(top * top - across.length_squared), vert)


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
    return on_floor(fn)


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
    if poser.bm["upright"] and poser.arms:
        # arms back on the load, thrown forward and up through the launch,
        # settling for the landing: (forward, out, elbow) degrees
        from . import upper as upper_mod
        for key, (f, o, e) in ((load, (-35.0, 20.0, 25.0)), (launch, (70.0, 22.0, 40.0)),
                               (tuck, (45.0, 24.0, 55.0)), (reach, (20.0, 22.0, 30.0))):
            for l in poser.arms:
                key.limbs[l["name"]] = upper_mod.arm_spec(poser, l, f, o, e, 4.0)
    return [load, launch, tuck, reach]
