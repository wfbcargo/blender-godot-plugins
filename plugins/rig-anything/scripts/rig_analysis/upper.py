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
- side bend: the trunk leans over the stance leg (a waddle, when large)
- lean and lean_bob: a held forward trunk lean, and a dip twice a stride
- head hold: the neck and head take back that share of the trunk's turn,
  roll and pitch, so the head keeps its orientation toward the world
- arm swing: each arm swings opposite its own side's leg, the forward swing
  the larger, and the elbow bends further as the arm comes forward

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
          "head_hold", "hand_clearance", "breath")


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
        "pelvis_list": 3.0 if running else 4.0,
        "thorax_turn": 1.5 + 4.0 * min(u, 1.4),
        "side_bend": 1.5,
        "lean": 1.0 + 5.0 * min(u, 1.5),
        "lean_bob": 2.0 if running else 1.0,
        "head_hold": 0.85,
        "hand_clearance": 0.015,
        "breath": 0.0,
    }


def idle_defaults():
    """Arms relaxed down by the sides: a little forward, elbows soft."""
    return {
        "arm_swing": 0.0, "arm_forward": 4.0, "arm_out": None, "elbow": 12.0,
        "elbow_swing": 0.0, "hand_in": 0.0, "pelvis_turn": 0.0, "pelvis_list": 0.0,
        "thorax_turn": 0.0, "side_bend": 0.0, "lean": 0.0, "lean_bob": 0.0,
        "head_hold": 0.85, "hand_clearance": 0.015,
        # degrees the arms drift with each breath
        "breath": 1.0,
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


# --------------------------------------------------------------------------
# the trunk
# --------------------------------------------------------------------------

def trunk(poser, pelvis_yaw, pelvis_roll, thorax_yaw, thorax_roll, pitch, head_hold):
    """Per axial bone totals {"pitch", "yaw", "roll"} for `Key.trunk`.

    The pelvis (and anything behind it) takes the pelvis values, the torso
    ramps to the thorax values by its top, and the neck and head hand back
    `head_hold` of the thorax's by the head. `pitch` is carried by the torso
    only, ramped the same way."""
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
    for j, i in enumerate(top_i):
        keep = 1.0 - head_hold * (j + 1) / float(len(top_i))
        for k in out:
            out[k][i] = ends[k][1] * keep
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
    for ob in verify._bound_meshes(rig):
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

    def __init__(self, poser, params, posture=None, stance=None):
        self.P = poser
        self.params = dict(params)
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
            sw, fw = prm["arm_swing"], prm["arm_forward"]
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
        forward = prm["arm_forward"] + prm["arm_swing"] * swing
        if swing > 0.0:
            forward += 0.15 * prm["arm_swing"] * swing     # the forward swing is the larger
        forward += breath
        elbow = prm["elbow"] + prm["elbow_swing"] * swing
        hand_in = prm["hand_in"] * (0.3 + 0.7 * max(swing, 0.0))
        out = self.outs[arm["name"]] + 0.8 * breath
        return arm_spec(self.P, arm, forward, out, elbow, hand_in)

    def cycle_key(self, p0, offsets, duty, legs):
        """(trunk, limbs, extra drop) at cycle phase p0 of a gait."""
        P, prm = self.P, self.params
        fwd_sig = {l["name"]: leg_forward((p0 - offsets[l["name"]]) % 1.0, duty) for l in legs}
        load = {l["name"]: leg_load((p0 - offsets[l["name"]]) % 1.0, duty) for l in legs}
        n = float(max(len(legs), 1))
        # +1: the +lat side's foot forward, and its hip with it
        turn = sum(_side(P, l) * fwd_sig[l["name"]] for l in legs) / n
        # +1: the +lat side carrying the body
        lst = sum(_side(P, l) * load[l["name"]] for l in legs)
        lst = max(-1.0, min(1.0, lst))
        pelvis_yaw = prm["pelvis_turn"] * turn * self.s_yaw
        thorax_yaw = -prm["thorax_turn"] * turn * self.s_yaw
        pelvis_roll = prm["pelvis_list"] * lst * self.s_roll
        thorax_roll = -prm["side_bend"] * lst * self.s_roll
        pitch = prm["lean"] + prm["lean_bob"] * math.cos(4.0 * math.pi * p0)
        tr = trunk(P, pelvis_yaw, pelvis_roll, thorax_yaw, thorax_roll, pitch,
                   prm["head_hold"])
        drop = self.hip_half * math.sin(math.radians(abs(prm["pelvis_list"] * lst)))
        limbs = {}
        for arm in P.arms:
            same = [l for l in self.side_legs.get(_side(P, arm), []) if l["name"] in fwd_sig]
            if not same:
                continue
            # the leg on that side nearest the arm along the body
            leg = min(same, key=lambda l: abs(l["forward_pos"] - arm["forward_pos"]))
            limbs[arm["name"]] = self.arm_terms(arm, -fwd_sig[leg["name"]])
        return tr, limbs, drop

    def idle_key(self, t):
        """(limbs) at idle time t in 0..1: relaxed arms, a breath of drift."""
        b = self.params.get("breath", 0.0) * math.sin(2.0 * math.pi * t)
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
        out["arm_out_measured"] = {k: round(v, 1) for k, v in self.params["arm_out_measured"].items()}
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
    ap = verify.arm_pose(rig_name, action.name, running=getattr(U, "running", False), bm=bm)
    if "error" not in ap and "skipped" not in ap:
        report["arm_pose"] = ap["arms"]
        if ap["failures"]:
            report["failures"].extend(ap["failures"])
            report["passed"] = False
    return keyed, infos, action, report
