"""Locomotion from ground contacts: walk to sprint, for any number of legs.

`actions.gait_cycle` lays a stride over a pose: every foot steps a fixed
fraction of its leg length about its REST spot, on the ground exactly half the
cycle. That serves a walk. Played faster it does not become a sprint, and on a
body that stands nearly straight-legged it cannot even step - the quadruped's
"run" came out as a 0.16 m shuffle, feet lifted 3.5 cm, legs never reaching.
The legs have to reach further as speed rises, and how much further is not a
per-creature constant. It follows from a handful of rules, all of which only
need what the body map already knows.

THE RULES
---------

1. Contacts define the motion, not limb types. Which rig points meet the
   ground is MEASURED - the skin at the bottom of each leg at rest - and the
   plane fitted through them is the frame everything is expressed in: hip
   height is height above that plane, strides lie in it, feet land on it. A
   leg is simply a chain whose skin touches that plane.

2. Speed is dimensionless. Animals of any size move alike at the same Froude
   number Fr = v^2 / (g h), h the hip height above the support plane
   (Alexander & Jayes 1983, the dynamic similarity hypothesis). So a rat and a
   dog "sprinting" means the same Fr, not the same m/s, and one number drives
   every creature.

3. Stride grows with speed: stride / h = 2.3 Fr^0.3 (Alexander 1976, fitted
   across mammals from walking to galloping).

4. Time on the ground shrinks with speed. The duty factor - the fraction of a
   cycle each foot is down - runs from ~0.75 at a slow walk through 0.5 at the
   walk-run change to ~0.25 in a fast gallop (Alexander & Jayes 1983). Under
   0.5 there are moments with no foot down: flight. A cockroach's tripod gets
   aerial phases above ~1 m/s the same way (Full & Tu 1991).

5. The stroke - how far a foot travels while planted - is duty x stride. It is
   what the legs actually have to reach, and it is where a fast gait's
   extension comes from: a sprinting quadruped's stroke is ~90% of its leg
   length, where the walk-derived run used 45%.

6. Reach is measured on the plane. A foot can sit where a sphere of the leg's
   extended length about the hip meets the support plane - a disc whose chord
   along the travel direction is the stroke the leg can make. When the stroke
   will not fit, in this order:
     a. roll the foot over its toe - the contact point is the pivot, so the
        distal segment adds its length to the leg (heel lift at push-off, which
        every digitigrade animal does);
     b. lower the hips - running animals do compress;
     c. shorten ground time toward a floor of 0.2 (more flight);
     d. and only then shorten the stride, which lowers the speed, reported.

7. Gait follows Froude, as gait transitions do in animals: walk below
   Fr ~0.5, then trot (quadrupeds) or run (bipeds), gallop above Fr ~2.5.
   A hexapod stays on alternating tripods and gets faster by the duty factor
   alone.

8. The body rides the load. A walk vaults over a stiff leg: hips highest at
   mid-stance. A run bounces on a spring: hips LOWEST at mid-stance, highest
   in flight. The height signal is the summed mid-stance load of every leg, so
   it is right for any footfall pattern without being written per gait. A
   galloping horizontal body also flexes and extends its spine once a stride
   (Hildebrand), gathered after the forefeet leave and stretched after the
   hind feet push off.

9. Swing reaches. A fast foot lifts high and early (the leg tucks), swings past
   its touchdown point, and draws back onto it - swing-leg retraction, which
   also lowers the speed difference at impact.

What this module does NOT do is pick a creature's top speed: that is a design
choice, made by asking for a Froude number (`GAITS` has names for the usual
ones). Everything after that is derived.

Sources: Alexander, R.McN. (1976) Estimates of speeds of dinosaurs. Nature 261;
Alexander & Jayes (1983) A dynamic similarity hypothesis for the gaits of
quadrupedal mammals. J. Zool. 201; Full & Tu (1991) Mechanics of a rapid running
insect. J. exp. Biol. 156; Hildebrand, M. (1977) Analysis of asymmetrical gaits.
J. Mammal. 58.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from . import bodymap, gait, motion, stored, verify

G = 9.81

# Froude numbers for gaits worth naming. Walk and trot sit well inside their
# ranges; "sprint" is a fast gallop, dog at full stretch ~Fr 3-4.
GAITS = {"walk": 0.20, "amble": 0.35, "trot": 1.0, "run": 1.5, "canter": 2.0,
         "gallop": 3.0, "sprint": 3.0}

# (dimensionless speed sqrt(Fr), duty factor), read off the quadruped and biped
# data in Alexander & Jayes 1983. Interpolated linearly between rows.
DUTY = ((0.0, 0.75), (0.45, 0.65), (0.7, 0.55), (1.0, 0.45), (1.6, 0.35),
        (2.5, 0.27), (4.0, 0.22))

MIN_DUTY = 0.2

# Ways of walking. Speed alone makes every body of a kind move alike; a style
# says how this one differs at the same Froude number. Each is a dict of
# `cycle` / `plan` arguments - duty, stride_scale, lift_scale, bounce_scale,
# sway, min_knee, extension, max_drop, stance_width, posture - and `upper`
# parameters, with "walk" and "run" sections laid over the common part by the
# gait asked for (Fr under 0.5 walks), and an "idle" section `actions.idle`
# reads. An explicit argument always beats the style; an `upper` dict is laid
# over the style's rather than replacing it.
GAIT_STYLES = {
    # an adult with nothing more said about them: the walk and run as the speed says, the hip drop
    # capped (grungist-creek's crowd and Belle were built on this before it had a name)
    "adult": {
        "walk": {"max_drop": 0.035},
        "run": {"max_drop": 0.07},
    },
    # short steps, feet low, long double support, soft knees, arms hanging
    # with little swing a little behind vertical, so a stooped body's hands
    # fall at the front of the thighs rather than out past the knees, a slight
    # stoop (gait in older adults: Winter 1990;
    # step length -10-20%, double support 25-35% vs ~20%)
    "elderly_shuffle": {
        "posture": {"pelvis": 2.0, "flex": 12.0, "neck": -8.0},
        "walk": {"duty": 0.74, "stride_scale": 0.8, "lift_scale": 0.8, "bounce_scale": 0.5,
                 "sway": 0.012, "extension": 0.94, "max_drop": 0.06,
                 "upper": {"arm_swing": 5.0, "arm_forward": -8.0, "elbow": 20.0, "elbow_swing": 3.0,
                           "hand_in": 3.0, "pelvis_turn": 1.5, "thorax_turn": 2.0, "side_bend": 2.0,
                           "lean": 0.0, "lean_bob": 0.5, "head_hold": 0.9}},
        "run": {"stride_scale": 0.8, "lift_scale": 0.7, "max_drop": 0.07},
        "idle": {"upper": {"arm_forward": -8.0, "elbow": 18.0}},
    },
    # feet apart (the thighs meet), a slower cadence on a longer step, the
    # body rocking over each stance leg, arms held out from the hips
    "heavy": {
        "stance_width": 1.4,
        "walk": {"stride_scale": 1.08, "lift_scale": 0.8, "bounce_scale": 0.6, "sway": 0.03,
                 "max_drop": 0.045,
                 "upper": {"arm_swing": 12.0, "side_bend": 4.0, "pelvis_list": 2.5, "lean": 1.0,
                           "hand_clearance": 0.04}},
        "run": {"stride_scale": 1.05, "lift_scale": 0.85, "bounce_scale": 0.8, "max_drop": 0.07,
                "upper": {"side_bend": 3.0, "hand_clearance": 0.04}},
        "idle": {"upper": {"hand_clearance": 0.035}},
    },
    # quicker, shorter steps and a bouncier body, big arm swing
    "child": {
        "walk": {"stride_scale": 0.88, "lift_scale": 1.15, "bounce_scale": 1.5, "sway": 0.012,
                 "max_drop": 0.035,
                 "upper": {"arm_swing": 24.0, "elbow": 18.0, "elbow_swing": 10.0, "lean": 2.0}},
        "run": {"stride_scale": 0.9, "lift_scale": 1.1, "bounce_scale": 1.4, "max_drop": 0.07,
                "upper": {"arm_swing": 25.0, "elbow_swing": 0.0}},
    },
    # purposeful: a longer step, arms driving with the elbows bent, a lean
    "brisk": {
        "walk": {"stride_scale": 1.05, "lift_scale": 1.05, "max_drop": 0.035,
                 "upper": {"arm_swing": 24.0, "elbow": 35.0, "elbow_swing": 12.0, "lean": 4.0,
                           "thorax_turn": 6.0}},
        "run": {"max_drop": 0.07, "upper": {"lean": 10.0}},
    },
    # unhurried: a slightly shorter, lower step, loose arms, a head that
    # rides the body more
    "relaxed": {
        "walk": {"stride_scale": 0.95, "lift_scale": 0.85, "bounce_scale": 0.9, "max_drop": 0.035,
                 "upper": {"arm_swing": 13.0, "elbow": 12.0, "elbow_swing": 6.0, "lean": 1.0,
                           "head_hold": 0.75}},
        "run": {"max_drop": 0.07, "upper": {"lean": 6.0}},
    },
}

STYLE_KEYS = ("duty", "stride_scale", "lift_scale", "bounce_scale", "sway", "min_knee",
              "extension", "max_drop", "centre_weight", "stance_width", "posture", "upper")


def style_args(style, section, explicit):
    """The arguments a style gives one clip, with `explicit` (the caller's
    non-None arguments) over them. `style` is a name from `GAIT_STYLES` or a
    dict of the same shape; `section` "walk", "run" or "idle"."""
    if style is None:
        return dict(explicit)
    if isinstance(style, str):
        if style not in GAIT_STYLES:
            raise ValueError("unknown gait style %r - styles are %s"
                             % (style, ", ".join(sorted(GAIT_STYLES))))
        style = GAIT_STYLES[style]
    out = {k: v for k, v in style.items() if k not in ("walk", "run", "idle")}
    sect = style.get(section) or {}
    for k, v in sect.items():
        if k == "upper" and isinstance(out.get("upper"), dict) and isinstance(v, dict):
            out["upper"] = dict(out["upper"], **v)
        else:
            out[k] = v
    unknown = set(out) - set(STYLE_KEYS)
    if unknown:
        raise ValueError("a style cannot set %s - it takes %s"
                         % (", ".join(sorted(unknown)), ", ".join(STYLE_KEYS)))
    for k, v in explicit.items():
        if k == "upper" and isinstance(v, dict) and isinstance(out.get("upper"), dict):
            out["upper"] = dict(out["upper"], **v)
        else:
            out[k] = v
    return out


def duty_factor(froude):
    u = math.sqrt(max(froude, 0.0))
    for (u0, b0), (u1, b1) in zip(DUTY, DUTY[1:]):
        if u <= u1:
            return b0 + (b1 - b0) * (u - u0) / (u1 - u0)
    return DUTY[-1][1]


def relative_stride(froude):
    """Stride length over hip height (Alexander 1976)."""
    return 2.3 * max(froude, 1e-6) ** 0.3


def choose_gait(n_legs, froude):
    if n_legs <= 2:
        return "walk" if froude < 0.5 else "run"
    if n_legs == 4:
        if froude < 0.5:
            return "walk"
        return "trot" if froude < 2.5 else "gallop"
    return "tripod"


# --------------------------------------------------------------------------
# contacts and the support plane
# --------------------------------------------------------------------------

def contact_pivot(rig, limb):
    """The point a planted foot rolls over: the far end of its end bone (the
    toe, or a generic rig's `_tip`), else the far end of the lower segment."""
    return rig.data.bones[limb["end"] or limb["lower"]].tail_local.copy()


def rest_contacts(poser, band=0.015):
    """Which rig points meet the ground at rest, measured on the skin.

    For each leg: the skin its distal bones dominate, the lowest band of it
    (within `band` of body height), its centroid, and which bones carry it.
    `pivot` is the joint the foot rolls over. A limb whose skin never comes
    near the ground is reported `grounded: False` - a leg by the body map's
    rule but not a contact, which is worth knowing before animating it.
    """
    body, bm, rig = poser.body, poser.bm, poser.rig
    body.skin_lowest(body.fk(), poser._upw)          # builds the vertex cache
    out = {}
    for l in poser.legs:
        names = {n for n in [l["lower"], l["end"]] + l["digits"] if n}
        pivot = contact_pivot(rig, l)
        verts = []
        for co, ws in getattr(body, "_skin", []) or []:
            top = max(ws, key=lambda nw: nw[1])[0]
            if top in names:
                verts.append((co, top, poser.height(co)))
        if verts:
            lo = min(h for _, _, h in verts)
            sel = [(co, n) for co, n, h in verts if h <= lo + band * bm["height"]]
            point = sum((co for co, _ in sel), Vector()) / len(sel)
            bones = sorted({n for _, n in sel})
            source = "skin"
        else:
            point, lo = pivot.copy(), poser.height(pivot)
            bones, source = [l["end"] or l["lower"]], "bones (no skin)"
        out[l["name"]] = {"point": point, "height": lo, "bones": bones,
                          "pivot": pivot, "source": source}
    if out:
        ground = min(c["height"] for c in out.values())
        for c in out.values():
            c["grounded"] = c["height"] <= ground + 0.03 * bm["height"]
    return out


def fit_plane(points, up):
    """(origin, normal) of the plane through contact points, normal toward `up`.

    Least squares for three or more; two points (a biped) give a line, and the
    plane is the one through that line nearest to level."""
    up = up.normalized()
    c = sum(points, Vector()) / max(len(points), 1)
    if len(points) >= 3:
        import numpy as np
        a = np.array([list(p - c) for p in points])
        w, v = np.linalg.eigh(a.T @ a)
        if w[1] > 1e-10 * max(w[2], 1e-12):
            n = Vector(v[:, 0].tolist()).normalized()
            return c, (n if n.dot(up) >= 0.0 else -n)
    if len(points) >= 2:
        line = (points[1] - points[0])
        if line.length > 1e-9:
            line.normalize()
            n = up - line * up.dot(line)
            if n.length > 1e-9:
                return c, n.normalized()
    return c, up


def support_polygon(points, origin, normal, fwd):
    """Contacts projected into the plane as 2D (fwd, lat) coordinates, convex hull
    in order. Fewer than three points is a segment or a point."""
    f = (fwd - normal * fwd.dot(normal)).normalized()
    s = normal.cross(f).normalized()
    pts = sorted({(round((p - origin).dot(f), 9), round((p - origin).dot(s), 9))
                  for p in points})
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def stability_margin(point2d, hull):
    """Signed distance from a projected point to the support polygon's edge:
    positive inside (statically stable), negative outside or with <3 contacts."""
    if len(hull) < 3:
        if not hull:
            return -float("inf")
        if len(hull) == 1:
            return -math.dist(point2d, hull[0])
        (ax, ay), (bx, by) = hull
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((point2d[0] - ax) * dx + (point2d[1] - ay) * dy)
                         / max(dx * dx + dy * dy, 1e-18)))
        return -math.dist(point2d, (ax + dx * t, ay + dy * t))
    margin = float("inf")
    for i in range(len(hull)):
        (ax, ay), (bx, by) = hull[i], hull[(i + 1) % len(hull)]
        ex, ey = bx - ax, by - ay
        ln = math.hypot(ex, ey) or 1e-12
        margin = min(margin, (ex * (point2d[1] - ay) - ey * (point2d[0] - ax)) / ln)
    return margin


# --------------------------------------------------------------------------
# reach on the plane
# --------------------------------------------------------------------------

class Reach:
    """Where one leg can put its contact point, and how the foot must roll."""

    def __init__(self, poser, limb, extension=0.97, min_knee=50.0,
                 heel_lift_max=60.0, toe_lift_max=25.0):
        self.P, self.limb = poser, limb
        a, b = limb["a"], limb["b"]
        # Never less than the leg already stands at: these rigs rest at 96-99.5%
        # of full length, and a cap below that left several legs unable to reach
        # the spot under their own hip.
        self.r_max = max(extension * (a + b),
                         min((limb["rest_eff"] - limb["rest_root"]).length, (a + b) * 0.995))
        # Nor more folded than it already stands: a cricket rests its hind knee
        # at 35 degrees, and a 50 degree floor gave that leg no stroke at all -
        # the planner divided by a zero stride.
        rest_d = (limb["rest_eff"] - limb["rest_root"]).length
        c = math.cos(math.radians(min_knee))
        self.r_min = min(math.sqrt(max(a * a + b * b - 2.0 * a * b * c, 0.0)), 0.98 * rest_d)
        self.pivot = contact_pivot(poser.rig, limb)
        # toe -> ankle at rest; the effector is the ankle, the contact the toe
        self.v = limb["rest_eff"] - self.pivot
        self.lims = (heel_lift_max, toe_lift_max) if limb["end"] else (0.0, 0.0)

    def ankle(self, contact, tilt):
        rot, _ = self.P.tilt_rotation(self.limb, tilt)
        return contact + rot @ self.v

    def fits(self, hip, contact, tilt):
        d = (self.ankle(contact, tilt) - hip).length
        return self.r_min <= d <= self.r_max

    def tilt(self, hip, contact, step=2.5):
        """(degrees, reachable): the smallest roll over the toe that brings the
        ankle within reach of the hip. Continuous in its inputs, so a foot
        rolling through a stride does not pop."""
        if self.fits(hip, contact, 0.0):
            return 0.0, True

        def err(t):
            d = (self.ankle(contact, t) - hip).length
            return max(d - self.r_max, self.r_min - d, 0.0)
        # candidates in order of size, heel lift before toe lift at each size
        cands = []
        k = 1
        while k * step <= max(self.lims) + step:
            for sgn, lim in ((1.0, self.lims[0]), (-1.0, self.lims[1])):
                if lim > 0.0 and (k - 1) * step < lim:
                    cands.append(sgn * min(k * step, lim))
            k += 1
        best = (err(0.0), 0.0)
        for t in cands:
            e = err(t)
            if e < best[0]:
                best = (e, t)
            if e == 0.0:
                # the previous size of the same sign did not fit: refine between
                lo, hi = math.copysign(max(abs(t) - step, 0.0), t), t
                for _ in range(12):
                    mid = 0.5 * (lo + hi)
                    if err(mid) == 0.0:
                        hi = mid
                    else:
                        lo = mid
                return hi, True
        return best[1], False

    def half_stroke(self, hip, centre, direction):
        """How far along `direction` from `centre` (a point on the plane) the
        contact can go with this hip before nothing fits."""
        L = self.limb["a"] + self.limb["b"]
        if not self.tilt(hip, centre)[1]:
            return 0.0
        lo, hi = 0.0, 2.0 * L
        for _ in range(18):
            mid = 0.5 * (lo + hi)
            if self.tilt(hip, centre + direction * mid, step=5.0)[1]:
                lo = mid
            else:
                hi = mid
        return lo


# --------------------------------------------------------------------------
# the plan
# --------------------------------------------------------------------------

def plan(poser, froude=None, speed=None, gait_name=None, extension=0.97,
         max_drop=None, centre_weight=None, stance_width=None, posture=None,
         duty=None, stride_scale=None, lift_scale=None, bounce_scale=None, min_knee=None):
    """Everything a cycle needs, derived from the contacts and one speed.

    Give `froude` (or a name from `GAITS`) or `speed` in m/s. Returns a dict:
    gait, froude, duty, stride and stroke (armature units and metres), natural
    speed and stride frequency, the drop the hips needed, per-leg stroke
    centres on the plane, the plane itself, and `limited_by` - what, if
    anything, the body could not do that was asked of it.

    max_drop       largest hip drop, as a share of the lowest hip height; None
                   grows it with speed, 0.10 + 0.08 sqrt(Fr) (to 0.22)
    centre_weight  0 centres each stroke on the rest foot, 1 under the hip;
                   None moves from one to the other with speed
    stance_width   each stroke line's distance from the midline as a multiple
                   of its hip's (`keyposes.stance_shift`): 1.0 walks with the
                   feet under the hips; None keeps the rest stance
    posture        a held `keyposes.posture_angles` dict; the hips are placed
                   where it carries them before reach is measured

    How a body walks at a speed, over what speed alone gives (a style):
    duty           ground time as a share of the cycle instead of the DUTY
                   table's - 0.75 an elderly shuffle's long double support
    stride_scale   stride times this; below 1 quicker, shorter steps at the
                   same speed (a child), above 1 slower cadence (a heavy body)
    lift_scale     swing foot height times this
    bounce_scale   hip rise and fall times this
    min_knee       smallest included knee angle a stance leg may fold to,
                   degrees (`Reach`, default 50)
    """
    from . import keyposes as kp
    bm, rig = poser.bm, poser.rig
    if isinstance(froude, str):
        # The name picks the speed; the footfalls come from the body. A hexapod
        # asked to "trot" runs alternating tripods at a trot's Froude number.
        froude = GAITS[froude]
    scale = sum(rig.matrix_world.to_scale()) / 3.0
    contacts = rest_contacts(poser)
    grounded = [l for l in poser.legs if contacts[l["name"]]["grounded"]]
    legs = grounded if len(grounded) >= 2 else poser.legs
    origin, normal = fit_plane([contacts[l["name"]]["point"] for l in legs], poser.up)
    fwd = (poser.fwd - normal * poser.fwd.dot(normal)).normalized()
    lat = normal.cross(fwd).normalized()

    # Where the hips are before any drop: at rest, or where a posture's pelvis
    # tilt carries them.
    root = {l["name"]: l["rest_root"].copy() for l in legs}
    if posture:
        body = poser.body
        posed = body.fk(body.bend_axial(Vector((0.0, 0.0, 0.0)),
                                        kp.posture_angles(bm, posture)))
        root = {l["name"]: posed[l["upper"]].translation.copy() for l in legs}
    hips = {l["name"]: (root[l["name"]] - origin).dot(normal) for l in legs}
    h_arm = sum(hips.values()) / len(hips)
    h = h_arm * scale
    if speed is not None:
        froude = speed * speed / (G * h)
    if froude is None:
        froude = GAITS["walk"]
    froude_asked = froude
    gait_name = gait_name or choose_gait(len(legs), froude)
    duty = duty_factor(froude) if duty is None else float(duty)
    speed = math.sqrt(froude * G * h)
    stride = relative_stride(froude) * h_arm * (1.0 if stride_scale is None else stride_scale)
    period = stride * scale / speed

    # Where each stroke is centred. A walk steps about where the foot stood; a
    # run puts its feet under the hip (Raibert's neutral point), which is also
    # the centre of the reach disc and so the longest stroke available.
    w = (motion.smoothstep((froude - 0.15) / 0.85) if centre_weight is None
         else centre_weight)
    # Sideways, a stance width moves the whole line - the foot, not its roll
    # over the toe, so the reach below is measured from where it now stands.
    centres, shifts = {}, {}
    for l in legs:
        piv = contact_pivot(rig, l)
        x_rest = (piv - origin).dot(fwd)
        x_hip = (root[l["name"]] - origin).dot(fwd)
        side = kp.stance_shift(poser, l, stance_width)
        side = lat * side.dot(lat)
        shifts[l["name"]] = side
        centres[l["name"]] = piv + fwd * ((x_hip - x_rest) * w) + side

    reach = {l["name"]: Reach(poser, l, extension=extension,
                              min_knee=50.0 if min_knee is None else min_knee) for l in legs}
    bounce = (body_bounce(froude, duty) * h_arm          # peak to peak
              * (1.0 if bounce_scale is None else bounce_scale))

    def available(drop):
        # the hip at its highest in the bounce is the hardest to reach from
        out = {}
        for l in legs:
            hip = root[l["name"]] - normal * (drop - 0.5 * bounce)
            r = reach[l["name"]]
            c = centres[l["name"]]
            out[l["name"]] = min(r.half_stroke(hip, c, fwd), r.half_stroke(hip, c, -fwd))
        return out

    limited = []
    stroke = duty * stride
    # A walk stays tall and a sprint compresses: allowed hip drop grows with
    # speed. Past it the gait gives up ground time, then stride - never height,
    # or a fast walk on stiff legs turns into a crouch walk.
    drop_given = max_drop is not None
    if max_drop is None:
        max_drop = 0.10 + 0.08 * min(math.sqrt(froude), 1.5)
    min_duty = 0.55 if duty >= 0.5 else MIN_DUTY
    drop_max = max_drop * min(hips.values())
    drop, avail = 0.0, available(0.0)
    steps = 12
    for k in range(steps + 1):
        drop = drop_max * k / steps
        avail = available(drop)
        if min(avail.values()) * 2.0 >= stroke:
            break
    fit = min(avail.values()) * 2.0
    if fit < stroke:
        limited.append("hips dropped to the limit (%.1f%% of hip height)" % (100 * max_drop))
        drop = drop_max
        new_duty = max(min_duty, fit / stride)
        if new_duty < duty:
            limited.append("ground time cut from %.2f to %.2f" % (duty, new_duty))
            duty = new_duty
        stroke = min(stroke, duty * stride)
        if fit < stroke:
            ratio = fit / stroke
            limited.append("stride shortened to %.0f%%, and the speed with it" % (100 * ratio))
            stroke, stride, speed = fit, stride * ratio, speed * ratio
            froude = speed * speed / (G * h)

    return {
        "gait": gait_name, "froude": froude, "froude_requested": froude_asked,
        "duty": duty,
        "speed_mps": speed, "period_s": period, "frequency_hz": 1.0 / period,
        "stride": stride, "stroke": stroke,
        "stride_m": stride * scale, "stroke_m": stroke * scale,
        "hip_height_m": h, "drop": drop, "drop_m": drop * scale,
        "max_drop": max_drop, "max_drop_given": drop_given, "drop_max": drop_max,
        "hip_min": min(hips.values()),
        "bounce": bounce, "centres": centres, "reach": reach, "roots": root,
        "stance_shift": shifts,
        "legs": legs, "contacts": contacts,
        "origin": origin, "normal": normal, "fwd": fwd, "lat": lat,
        "scale": scale, "limited_by": limited,
        "lift": (swing_lift(froude) * (sum(l["a"] + l["b"] for l in legs) / len(legs))
                 * (1.0 if lift_scale is None else lift_scale)),
        "flex": spine_flex(froude, gait_name, bm),
    }


def body_bounce(froude, duty):
    """Peak-to-peak body height change, as a fraction of hip height. Dynamic
    similarity makes it a function of Fr; the numbers are modest on purpose."""
    if duty >= 0.5:
        return 0.015
    return 0.02 + 0.012 * min(math.sqrt(froude), 3.0)


def swing_lift(froude):
    """Swing foot height as a fraction of leg length."""
    return 0.08 + 0.10 * min(math.sqrt(froude), 2.0)


def spine_flex(froude, gait_name, bm):
    """Degrees of spine arch at the gathered moment of a gallop, 0 otherwise."""
    if bm["upright"] or gait_name not in ("gallop", "bound"):
        return 0.0
    return 9.0 * max(0.0, min(1.0, (froude - 1.5) / 1.5))


# --------------------------------------------------------------------------
# the cycle
# --------------------------------------------------------------------------

def _swing_x(u, stroke, over):
    """Fore/aft of a swinging contact, 0..1 through swing: from the back of the
    stroke, past the front by `over`, and back onto it."""
    reach_at = 0.82
    if u < reach_at:
        return -0.5 * stroke + (stroke + over) * motion.smoothstep(u / reach_at)
    return 0.5 * stroke + over * (1.0 - motion.smoothstep((u - reach_at) / (1.0 - reach_at)))


def _swing_y(u, lift):
    """Lift through swing, peaking early - the foot comes up as the leg leaves
    behind and travels forward low, extending to land."""
    return lift * math.sin(math.pi * (u ** 0.7))


SWING_HOLD = 0.7
SWING_CLEARANCE = 0.02   # of body height: twice the band `verify` counts a contact planted in


def _clear_fold(p, limb, reach, contact, solved, fold):
    """The largest part of `fold` that keeps the swinging contact clear of the floor.

    The fold turns the foot about the ankle, so the contact moves with it. A paw folds
    its toe back and up; a cricket's 5 mm hind tarsus, pointing back and down, swung
    its tip into the floor for the last third of every swing, where the floor drape
    held it while the stride carried the leg on - a 0.4 mm drag per frame, inside the
    band the export's re-check counts as planted. The contact may go no lower than its
    planned swing height, or than SWING_CLEARANCE over where it stands, whichever is
    lower."""
    if not fold:
        return 0.0
    ankle = reach.ankle(contact, solved)

    def contact_h(f):
        return p.height(ankle - (reach.ankle(contact, solved + f) - contact))

    want = min(p.height(contact), p.height(reach.pivot) + SWING_CLEARANCE * p.bm["height"])
    if contact_h(fold) >= want:
        return fold
    if contact_h(0.0) < want:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(12):
        mid = 0.5 * (lo + hi)
        if contact_h(fold * mid) >= want:
            lo = mid
        else:
            hi = mid
    return fold * lo


def foot_state(phase, duty, stroke, lift, over, hold=SWING_HOLD):
    """(fore/aft, lift, plant weight, in stance, swing progress) at a leg's
    phase, 0 = touchdown.

    The plant weight never drops below SWING_HOLD in swing. At 0 the foot
    follows the shin, and a shin swung out straight carries the paw with it -
    the galloping quadruped's paws stuck out level like a swimmer's."""
    if phase < duty:
        return 0.5 * stroke - stroke * phase / duty, 0.0, 1.0, True, 0.0
    u = (phase - duty) / (1.0 - duty)
    plant = max(1.0 - (1.0 - hold) * u / 0.15, hold + (1.0 - hold) * (u - 0.9) / 0.1, hold)
    return _swing_x(u, stroke, over), _swing_y(u, lift), min(plant, 1.0), False, u


def cycle(rig_name, froude="walk", speed=None, gait_name=None, frames=None,
          forward="-Y", up="Z", floor=0.0, action_name="Locomotion", fps=None,
          extension=None, tail_lift=None, tail_swing=None, attempts=6, paw_fold=1.0,
          swing_hold=SWING_HOLD, max_drop=None, centre_weight=None, stance_width=None,
          posture=None, upper=None, duty=None, stride_scale=None, lift_scale=None,
          bounce_scale=None, sway=None, min_knee=None, style=None):
    """Author a looping gait from `plan`, verified on Blender's playback.

    froude         a number, or a name from `GAITS` ("walk", "trot", "sprint"...)
    speed          m/s instead of a Froude number
    max_drop       largest hip drop as a share of hip height. Given, it is a
                   hard cap: the hips never go lower, a stroke that still does
                   not fit is shortened, and a leg that still cannot reach is
                   reported as a failure naming max_drop. None lets the plan
                   choose (10-22% by speed) and the retries go past it.
    centre_weight  0 steps about the rest foot, 1 under the hip; None by speed
    stance_width   ankle distance from the midline as a multiple of the hip's:
                   1.0 feet under the hips, None the rest stance
    posture        held {"pelvis", "flex", "neck"} degrees, positive toward
                   `fwd` (`keyposes.posture_angles`). Posed inside every key,
                   so the legs are solved under the posed body and every check
                   sees it.
    upper          the upper body (`upper.py`): None moves it on an upright
                   two-legged body - pelvis and thorax turning and listing,
                   the head held, arms swinging opposite their legs - with
                   `upper.defaults` for this speed; a dict overrides those
                   parameters (degrees, metres); False leaves it at rest.
                   Bodies with other leg counts are untouched unless asked.
    duty, stride_scale, lift_scale, bounce_scale, min_knee
                   as `plan`: how this body walks at the speed, over what
                   the speed alone gives
    sway           side-to-side hip sway, amplitude as a share of leg length;
                   None is 0.01 on an upright walk, 0 otherwise
    style          a `GAIT_STYLES` name ("elderly_shuffle", "heavy", "child",
                   "brisk", "relaxed") or a dict of the same shape: defaults
                   for all of the above, and `upper` and `posture` and
                   `stance_width`, its "walk" or "run" section chosen by the
                   Froude number asked (a speed in m/s over 2 runs). Every
                   argument given here beats the style.

    The clip is in place. Its implied speed (stance feet sweeping back at the
    body's speed) is what the engine time-scales against; `natural_speed_mps`
    is the real-world speed of this gait at this body's size - what the engine
    should move the body at to look like the same animal.
    """
    given = {k: v for k, v in dict(
        duty=duty, stride_scale=stride_scale, lift_scale=lift_scale, bounce_scale=bounce_scale,
        sway=sway, min_knee=min_knee, extension=extension, max_drop=max_drop,
        centre_weight=centre_weight, stance_width=stance_width, posture=posture,
        upper=upper).items() if v is not None}
    asked = GAITS[froude] if isinstance(froude, str) else froude
    running_asked = (speed > 2.0) if speed is not None else (asked is not None and asked >= 0.5)
    try:
        a = style_args(style, "run" if running_asked else "walk", given)
    except ValueError as e:
        return {"error": str(e)}
    duty, stride_scale, lift_scale = a.get("duty"), a.get("stride_scale"), a.get("lift_scale")
    bounce_scale, sway, min_knee = a.get("bounce_scale"), a.get("sway"), a.get("min_knee")
    extension = a.get("extension", 0.97)
    max_drop, centre_weight = a.get("max_drop"), a.get("centre_weight")
    stance_width, posture, upper = a.get("stance_width"), a.get("posture"), a.get("upper")

    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return bm
    rig = bpy.data.objects[rig_name]
    body = motion.Body(rig, bm)
    from . import keyposes as kp
    P = kp.Poser(body)
    if len(P.legs) < 2:
        return {"error": "%s has %d legs - nothing to walk on" % (rig_name, len(P.legs))}

    pl = plan(P, froude=froude, speed=speed, gait_name=gait_name, extension=extension,
              max_drop=max_drop, centre_weight=centre_weight, stance_width=stance_width,
              posture=posture, duty=duty, stride_scale=stride_scale, lift_scale=lift_scale,
              bounce_scale=bounce_scale, min_knee=min_knee)
    legs = pl["legs"]
    offsets = gait.phase_offsets(
        [{"name": l["name"], "side": l["side"], "forward": l["forward_pos"]} for l in legs],
        gait=pl["gait"])
    duty = pl["duty"]
    frames = int(frames or (32 if duty >= 0.5 else 24))
    fwd, normal = pl["fwd"], pl["normal"]
    fr = pl["froude"]
    running = duty < 0.5
    tail_lift = (8.0 + 12.0 * min(1.0, fr)) if tail_lift is None else tail_lift
    tail_swing = (8.0 if not running else 4.0) if tail_swing is None else tail_swing
    if sway is None:
        sway = 0.01 if not running and bm["upright"] else 0.0
    sway_amp = sway * P.leg_len

    # Load: how much of the body's weight is mid-stance, summed over legs. The
    # hips ride it - up for a vaulting walk, down for a bouncing run.
    def load(p0):
        tot = 0.0
        for l in legs:
            p = (p0 - offsets[l["name"]]) % 1.0
            if p < duty:
                tot += math.sin(math.pi * p / duty)
        return tot
    samples_load = [load(i / 96.0) for i in range(96)]
    lo_l, hi_l = min(samples_load), max(samples_load)
    mean_l = sum(samples_load) / len(samples_load)

    def height_signal(p0):
        if hi_l - lo_l < 1e-6:
            return 0.0
        return (load(p0) - mean_l) / (hi_l - lo_l)

    # Spine: extended half-way between the last hind foot leaving and the first
    # forefoot landing, flexed half a cycle later.
    zone = {l["name"]: kp.leg_zone(P, l) for l in legs}
    hind = [l for l in legs if zone[l["name"]] < -0.33]
    fore = [l for l in legs if zone[l["name"]] > 0.33]
    ext_phase = 0.0
    if hind and fore:
        off_h = max((offsets[l["name"]] + duty) % 1.0 for l in hind)
        on_f = min(offsets[l["name"]] for l in fore)
        if on_f < off_h:
            on_f += 1.0
        ext_phase = 0.5 * (off_h + on_f)

    from . import upper as upper_mod
    upper_params = upper_mod.resolve(P, upper, upper_mod.defaults(fr, duty))
    U = None
    if upper_params is not None:
        stance = {l["name"]: {"target": (lambda p, limb, posed, s=pl["stance_shift"][l["name"]]:
                                         limb["rest_eff"] + s)} for l in legs}
        U = upper_mod.Upper(P, upper_params, posture=posture, stance=stance)

    state = {"drop": pl["drop"], "stroke": pl["stroke"], "lift": pl["lift"],
             "flex": pl["flex"], "bounce": 1.0, "over": 1.0}
    first_leg = legs[0]
    fold_amp = (0.25 + 0.35 * min(1.0, fr / 2.0)) * paw_fold

    def key_at(p0):
        S, H = state["stroke"], state["lift"]
        over = 0.1 * S * min(math.sqrt(fr), 2.0) / 2.0 * state["over"]
        limbs = {}
        for l in legs:
            ph = (p0 - offsets[l["name"]]) % 1.0
            x, y, plant, _, u = foot_state(ph, duty, S, H, over, swing_hold)
            contact = pl["centres"][l["name"]] + fwd * x + normal * y
            r = pl["reach"][l["name"]]
            # mid-swing the paw folds back under the leg, more the faster it goes
            fold = fold_amp * r.lims[0] * math.sin(math.pi * u)

            def folded(p, limb, posed, c=contact, r=r, fold=fold):
                solved = r.tilt(posed[limb["upper"]].translation, c)[0]
                return solved, _clear_fold(p, limb, r, c, solved, fold)

            def target(p, limb, posed, folded=folded, c=contact, r=r):
                solved, f = folded(p, limb, posed)
                if not f:
                    return c + r.v
                # The fold turns the paw, it does not move the ankle: the poser
                # adds the roll's ankle offset for the whole tilt, so take back
                # the part that belongs to the fold.
                return (c + r.v + p.tilt_rotation(limb, solved)[1]
                        - p.tilt_rotation(limb, solved + f)[1])
            limbs[l["name"]] = {
                "target": target,
                "planted": plant,
                "tilt": (lambda p, limb, posed, t, folded=folded: sum(folded(p, limb, posed))),
            }
        bounce = pl["bounce"] * state["bounce"] * height_signal(p0) * (1.0 if running else -1.0)
        flex = state["flex"] * math.cos(2.0 * math.pi * (p0 - ext_phase)) * -1.0
        side = 1.0 if (first_leg["rest_root"] - P.centre).dot(P.lat) > 0 else -1.0
        # The upper body rides the same phases: pelvis and thorax turn and
        # list, the head holds, the arms swing against their own side's leg.
        trunk, list_drop = None, 0.0
        if U is not None:
            trunk, arm_limbs, list_drop = U.cycle_key(p0, offsets, duty, legs)
            limbs.update(arm_limbs)
        return kp.Key(drop=state["drop"] + bounce + list_drop, limbs=limbs, flex=flex,
                      sway=sway_amp * math.sin(2.0 * math.pi * p0) * side,
                      tail_lift=tail_lift + 0.8 * flex,
                      tail_sway=-tail_swing * math.sin(2.0 * math.pi * p0),
                      posture=posture, trunk=trunk)

    skin_rest = body.skin_lowest(body.fk(), P._upw)
    skin_allowed = (min(0.0, skin_rest - floor) - 0.012 * bm["height"]
                    if skin_rest is not None else None)
    adjustments = []
    drop_ceiling = None
    # A max_drop the caller gave is a promise about the look of the gait (an
    # upright walk, not a crouch), so the retries may not break it.
    drop_limit = pl["drop_max"] if pl["max_drop_given"] else 0.3 * P.leg_len
    for attempt in range(max(1, attempts) * 3):
        samples = [P.pose(key_at((f - 1) / float(frames))) for f in range(1, frames + 2)]
        clamped = sorted({n for _, infos in samples for n, i in infos.items() if i["clamped"]})
        if clamped:
            if state["flex"] > 1.0:
                state["flex"] = state["flex"] * 0.5 if state["flex"] > 3.0 else 0.0
                adjustments.append("spine flex eased (%s out of reach)" % ", ".join(clamped))
            elif drop_ceiling is None and state["drop"] < drop_limit - 1e-9:
                state["drop"] = min(state["drop"] + 0.03 * P.leg_len, drop_limit)
                adjustments.append("hips lowered (%s out of reach)" % ", ".join(clamped))
            elif state["stroke"] > 0.4 * pl["stroke"]:
                state["stroke"] *= 0.9
                adjustments.append("stroke shortened (%s out of reach)" % ", ".join(clamped))
            else:
                # A leg standing at full stretch misses by its bounce and its
                # swing overshoot however short the stroke, so those go next.
                state["bounce"] *= 0.5
                state["over"] *= 0.5
                state["stroke"] *= 0.95
                adjustments.append("bounce and overshoot halved (%s out of reach)"
                                   % ", ".join(clamped))
            continue
        if skin_allowed is not None:
            low = min(body.skin_lowest(posed, P._upw) for posed, _ in samples[::2])
            if low - floor < skin_allowed:
                # Skin, not reach, is what limits this body. Dropping the hips
                # lowers the chest and folds the wrists - the rat's forearm skin
                # is weighted to its breast bones and went 2 cm into the floor -
                # so give back height first and never take it again; if the legs
                # then cannot reach, the stroke pays.
                if state["stroke"] < 0.5 * pl["stroke"] and state["drop"] > 1e-6:
                    state["drop"] = max(0.0, state["drop"] - max(floor - low, 0.0)
                                        - 0.004 * bm["height"])
                    drop_ceiling = state["drop"]
                    adjustments.append("skin %.3f under the floor: hips raised" % (floor - low))
                else:
                    state["stroke"] *= 0.85
                    adjustments.append("skin %.3f under the floor: stroke shortened"
                                       % (floor - low))
                continue
        break

    rest_pivots = {l["name"]: pl["reach"][l["name"]].pivot for l in legs}

    def check(keyed, ev, infos_by_frame):
        from .actions import _check_common, _pose_gap
        def in_stance(name, f):
            if name not in offsets:
                return False
            return foot_state(((f - 1) / float(frames) - offsets[name]) % 1.0, duty,
                              state["stroke"], state["lift"], 0.0)[3]
        r = _check_common(body, bm, keyed, ev, infos_by_frame, planted=[],
                          posed_limbs=P.legs, rest_floor=floor, starts_at_rest=False,
                          skid=in_stance)  # stance is held to the skate test below
        if clamped and pl["max_drop_given"] and state["drop"] >= drop_limit - 1e-9:
            r["failures"].append(
                "%s out of reach with the hips at max_drop %.3f (%.0f%% of hip height, "
                "%.3f m) - raise max_drop or ask for a slower gait"
                % (", ".join(clamped), pl["max_drop"], 100 * pl["max_drop"],
                   pl["drop_max"] * pl["scale"]))
        evaluated = ev["evaluated"]
        seam, seam_bone = _pose_gap(rig, evaluated[1], evaluated[frames + 1])
        if seam > 1e-4:
            r["failures"].append("loop seam %.5f on %s" % (seam, seam_bone))
        # The skate test, on the CONTACT: while planted, the toe must follow its
        # line on the plane exactly, however much the foot rolls over it.
        slip, peak = {}, {}
        tol = 0.004 * bm["size"]
        S = state["stroke"]
        for l in legs:
            carrier = l["end"] or l["lower"]
            worst = 0.0
            for f in range(1, frames + 2):
                ph = ((f - 1) / float(frames) - offsets[l["name"]]) % 1.0
                x, _, _, stance, _ = foot_state(ph, duty, S, state["lift"], 0.0)
                if not stance:
                    continue
                want = pl["centres"][l["name"]] + fwd * x
                got = body.carried(evaluated[f], carrier, rest_pivots[l["name"]])
                worst = max(worst, (got - want).length)
            slip[l["name"]] = round(worst, 5)
            if worst > tol:
                r["failures"].append("%s contact leaves its line by %.4f - it would "
                                     "skate" % (l["name"], worst))
            peak[l["name"]] = round(max(i[l["name"]]["reach"]
                                        for i in infos_by_frame.values()), 3)
        r["contact_slip"] = slip
        r["peak_reach"] = peak
        r["loop_seam"] = round(seam, 6)
        return r

    from .actions import _author_samples
    first_samples = samples
    keyed, infos, action, report = upper_mod.author_clear(
        U, rig_name, bm,
        lambda s: _author_samples(body, rig, action_name, s, fps, check),
        lambda: (first_samples if not U or not getattr(U, "clearance", None) else
                 [P.pose(key_at((f - 1) / float(frames))) for f in range(1, frames + 2)]))
    if "error" in report:
        return report

    fps_now = bpy.context.scene.render.fps
    S = state["stroke"]
    if pl["stroke"] <= 0.0:
        return {"error": "%s: no leg has any stroke to walk with (%s)" % (rig_name, "; ".join(pl["limited_by"]))}
    ratio = S / pl["stroke"]
    stance_s = duty * frames / fps_now
    natural = pl["speed_mps"] * ratio
    h = pl["hip_height_m"]
    report.update({
        "rig": rig_name, "action": action.name, "frames": [1, frames + 1], "fps": fps_now,
        "gait": pl["gait"],
        "froude": round(natural * natural / (G * h), 3),
        "froude_requested": round(pl["froude_requested"], 3),
        "duty_factor": round(duty, 3),
        "hip_height_m": round(h, 4),
        "stride_m": round(pl["stride_m"] * ratio, 4),
        "stroke_m": round(S * pl["scale"], 4),
        "stroke_over_leg": round(S / P.leg_len, 3),
        "lift_m": round(state["lift"] * pl["scale"], 4),
        "drop_m": round(state["drop"] * pl["scale"], 4),
        "max_drop": round(pl["max_drop"], 4),
        "drop_share": round(state["drop"] / pl["hip_min"], 4),
        "stance_width": stance_width,
        "stance_shift_m": {k: round(v.dot(pl["lat"]) * pl["scale"], 4)
                           for k, v in pl["stance_shift"].items()},
        "posture": dict(posture) if posture else None,
        "style": style if isinstance(style, str) or style is None else "custom",
        "stride_scale": stride_scale, "lift_scale": lift_scale, "bounce_scale": bounce_scale,
        "duty_asked": duty, "sway_share": round(sway, 4), "min_knee": min_knee,
        "upper": U.report() if U is not None else None,
        "spine_flex_deg": round(state["flex"], 2),
        "natural_speed_mps": round(natural, 4),
        "stride_frequency_hz": round(natural / (pl["stride_m"] * ratio), 3),
        "implied_speed_cycle_mps": round(S * pl["scale"] / stance_s, 4),
        "implied_speed_playback_mps": round(S * pl["scale"] / stance_s
                                            * frames / (frames + 1.0), 4),
        "phase_offsets": {k: round(v, 3) for k, v in offsets.items()},
        "contacts": {k: {"bones": c["bones"], "grounded": c["grounded"],
                         "source": c["source"]} for k, c in pl["contacts"].items()},
        "support_normal": [round(x, 4) for x in pl["normal"]],
        "limited_by": pl["limited_by"], "adjustments": adjustments,
        "attempts": attempt + 1,
    })
    return report


# --------------------------------------------------------------------------
# reading contacts back out of a clip
# --------------------------------------------------------------------------

def detect(rig_name, action_name, forward="-Y", up="Z", floor=0.0, tolerance=None):
    """Which contact points are on the ground, frame by frame, in ANY clip.

    Works on hand-authored clips as well as generated ones: each leg's contact
    pivot is carried by its bone through Blender's playback, and it is in
    contact while it sits within `tolerance` of the lowest it gets in the clip.
    Returns per leg the duty factor, stance intervals as cycle phases, the
    speed the stance contact sweeps back at, and per frame the support
    polygon's stability margin for the skinned centre of mass - the plane of
    grounded contacts, measured rather than assumed.
    """
    from . import keyposes as kp
    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return bm
    rig = bpy.data.objects[rig_name]
    action = bpy.data.actions.get(action_name)
    if action is None:
        return {"error": "no action " + repr(action_name)}
    body = motion.Body(rig, bm)
    P = kp.Poser(body)
    tol = 0.01 * bm["height"] if tolerance is None else tolerance
    pivots = {l["name"]: (l["end"] or l["lower"], contact_pivot(rig, l)) for l in P.legs}

    scene = bpy.context.scene
    ad = rig.animation_data or rig.animation_data_create()
    prev, prev_frame = ad.action, scene.frame_current
    snap = verify._snapshot(rig)
    per_frame = {}
    try:
        if not verify.bind_action(rig, action)["bound"]:
            return {"error": "could not bind " + action_name}
        lo, hi = verify._frames(action)
        for f in range(lo, hi + 1):
            scene.frame_set(f)
            bpy.context.view_layer.update()
            mats = {pb.name: pb.matrix.copy() for pb in rig.pose.bones}
            pts = {n: body.carried(mats, b, p) for n, (b, p) in pivots.items()}
            per_frame[f] = (pts, body.com(mats))
    finally:
        scene.frame_set(prev_frame)
        if prev is not None:
            verify.bind_action(rig, prev)
        else:
            ad.action = None
        verify._restore(rig, snap)

    frames = sorted(per_frame)
    n = len(frames) - 1 or 1          # last key repeats the first in a loop
    fps = scene.render.fps
    scale = sum(rig.matrix_world.to_scale()) / 3.0
    legs = {}
    for name in pivots:
        hs = [P.height(per_frame[f][0][name]) for f in frames]
        low = min(hs)
        down = [h <= low + tol for h in hs]
        speeds = []
        for i in range(len(frames) - 1):
            if down[i] and down[i + 1]:
                a, b = per_frame[frames[i]][0][name], per_frame[frames[i + 1]][0][name]
                speeds.append(-(b - a).dot(P.fwd) * scale * fps)
        spans, start = [], None
        for i, d in enumerate(down[:-1]):
            if d and start is None:
                start = i
            if not d and start is not None:
                spans.append([round(start / n, 4), round(i / n, 4)])
                start = None
        if start is not None:
            spans.append([round(start / n, 4), 1.0])
        speeds.sort()
        legs[name] = {
            "bone": pivots[name][0],
            "duty_factor": round(sum(down[:-1]) / float(n), 3),
            "stance": spans,
            "stance_speed_mps": round(speeds[len(speeds) // 2], 4) if speeds else None,
            "lowest_m": round(low * scale, 4),
        }

    margins, flight = [], 0
    for i, f in enumerate(frames[:-1]):
        pts, com = per_frame[f]
        grounded = [pts[nm] for nm in pivots if P.height(pts[nm]) <= legs[nm]["lowest_m"] / scale + tol]
        if not grounded:
            flight += 1
            margins.append(None)
            continue
        origin, normal = fit_plane(grounded, P.up) if len(grounded) >= 3 else \
            (sum(grounded, Vector()) / len(grounded), P.up)
        hull = support_polygon(grounded, origin, normal, P.fwd)
        f2 = (P.fwd - normal * P.fwd.dot(normal)).normalized()
        s2 = normal.cross(f2).normalized()
        c2 = ((com - origin).dot(f2), (com - origin).dot(s2))
        margins.append(stability_margin(c2, hull) * scale)
    stable = [m for m in margins if m is not None and m >= 0.0]
    speeds = [l["stance_speed_mps"] for l in legs.values() if l["stance_speed_mps"]]
    speeds.sort()
    return {
        "rig": rig_name, "action": action_name, "frames": [frames[0], frames[-1]],
        "legs": legs,
        "flight_fraction": round(flight / float(n), 3),
        "statically_stable_fraction": round(len(stable) / float(n), 3),
        "worst_margin_m": round(min((m for m in margins if m is not None), default=0.0), 4),
        "stance_speed_mps": speeds[len(speeds) // 2] if speeds else None,
    }


def summarize(r):
    if "error" in r:
        return "ERROR: " + r["error"]
    lines = ["%s  %s  %s  %s  frames %d-%d" % (
        r["rig"], r["action"], r["gait"], "PASSED" if r["passed"] else "FAILED",
        r["frames"][0], r["frames"][1])]
    lines.append("  Fr %.2f (asked %.2f)  duty %.2f  hip h %.3f m  natural %.3f m/s  %.2f Hz"
                 % (r["froude"], r["froude_requested"], r["duty_factor"], r["hip_height_m"],
                    r["natural_speed_mps"], r["stride_frequency_hz"]))
    lines.append("  stride %.3f m  stroke %.3f m (%.2f leg)  lift %.3f  drop %.3f  flex %.1f deg"
                 % (r["stride_m"], r["stroke_m"], r["stroke_over_leg"], r["lift_m"],
                    r["drop_m"], r["spine_flex_deg"]))
    if r.get("stance_width") is not None or r.get("posture"):
        lines.append("  stance width %s (shift %s)  posture %s  drop %.1f%% of hip (cap %.1f%%)"
                     % (r["stance_width"], r["stance_shift_m"], r["posture"],
                        100 * r["drop_share"], 100 * r["max_drop"]))
    lines.append("  clip implied %.4f m/s   peak reach %s" % (
        r["implied_speed_playback_mps"], r["peak_reach"]))
    lines.append("  slip %s  seam %s  skin %s  tightest %s" % (
        r["contact_slip"], r["loop_seam"], r["skin_lowest"], r["tightest_joint_degrees"]))
    for x in r["limited_by"] + r["adjustments"]:
        lines.append("  note " + x)
    lines += ["  FAIL " + f for f in r["failures"]]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# handing it to an engine
# --------------------------------------------------------------------------

GAIT_KEYS = ("gait", "froude", "duty_factor", "natural_speed_mps", "stride_m",
             "stroke_m", "stride_frequency_hz", "hip_height_m", "spine_flex_deg")


def engine_manifest(rig_name, reports=None, forward="-Y", up="Z", floor=0.0, mesh_name=None):
    """The `gaits` and `contacts` entries an engine controller reads, and with
    `mesh_name` the `collider` ({radius, height}, `export.collider`).

    `reports` is {role: report} from `cycle` (or `actions.move_set`); roles
    whose report did not come from `cycle` are skipped; None reads the reports a
    set function stored on the rig's actions (`stored.load`). Contacts are read back
    from Blender's playback of each clip with `detect`, not copied from the plan,
    and each foot carries its end bone's length, because an engine skeleton
    knows a bone's head but not where it ends - and the tail is the contact.

        gaits:    {role: {gait, froude, duty_factor, natural_speed_mps, ...}}
        contacts: {role: {feet: [{leg, bone, length, stance: [[from, to]...],
                   duty_factor}], flight_fraction, statically_stable_fraction}}
    """
    rig = bpy.data.objects.get(rig_name)
    if rig is None or rig.type != "ARMATURE":
        return {"error": "no armature named " + repr(rig_name)}
    reports = stored.resolve(reports, rig_name)
    scale = sum(rig.matrix_world.to_scale()) / 3.0
    gaits, contacts, problems = {}, {}, []
    for role, r in reports.items():
        if not isinstance(r, dict) or "natural_speed_mps" not in r:
            continue
        if not r.get("passed"):
            problems.append("%s did not pass its checks: %s" % (role, "; ".join(r.get("failures", []))))
        gaits[role] = {k: r[k] for k in GAIT_KEYS}
        d = detect(rig_name, r["action"], forward=forward, up=up, floor=floor)
        if "error" in d:
            problems.append("%s: %s" % (role, d["error"]))
            continue
        contacts[role] = {
            "feet": [{"leg": n, "bone": v["bone"],
                      "length": round(rig.data.bones[v["bone"]].length * scale, 5),
                      "stance": v["stance"], "duty_factor": v["duty_factor"]}
                     for n, v in d["legs"].items()],
            "flight_fraction": d["flight_fraction"],
            "statically_stable_fraction": d["statically_stable_fraction"],
        }
    out = {"gaits": gaits, "contacts": contacts, "problems": problems}
    if mesh_name:
        from . import export
        c = export.collider(mesh_name, rig_name, forward=forward, up=up, floor=floor)
        if "error" in c:
            problems.append("collider: " + c["error"])
        else:
            out["collider"] = c
    return out
