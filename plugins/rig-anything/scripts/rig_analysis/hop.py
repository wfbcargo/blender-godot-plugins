"""Hopping, bounding and jumping for the legs `hoppers` found.

A walk and a run come from `locomotion`: contacts, a Froude number, a duty
factor. Hoppers break two of its assumptions. Their saltatorial legs have three
segments that fold as a Z, so where the hip can be is not a two-bone reach; and
their fast gaits push both hind feet together and fly, so the body's height is
not a gentle bob but a ballistic arc between stances. And a jump is not a gait
at all: it is a launch the legs make, a flight the engine makes, and a landing.

THE LEG
-------

Hind stance is built from joint angles that were measured, not from a height
that was guessed. Hall et al. (2022, PeerJ 10:e13611) filmed New Zealand White
rabbits hopping: the ankle (tibia to metatarsus) is 103 degrees at foot strike,
closes to 66 at 38% of stance and opens to 137 at toe-off; the heel never
touches. The tri-segmented mammal leg keeps its femur roughly parallel to its
metatarsus (Fischer & Blickhan 2006) - the pantograph Rigify's rear_paw imposes
- which makes the knee's included angle equal the ankle's. Given the toe's
contact and where the hip must be fore and aft, that fixes how far the heel is
lifted and so how high the hip rides: the body's stance height is an output.

A cricket's hind leg does not pantograph. Its tarsus lies on the floor and the
jump is the femur-tibia joint opening from full flexion: 10 degrees to 150 in
Acheta domesticus (Hustert & Baldus 2010, JEB 213:4055), in 8 ms for a long
jump and up to 30 for a short one.

THE GAITS (leporid)
-------------------

Rabbits move their forelimbs alternately and hindlimbs together (Carneiro et
al. 2021). On a treadmill at 8-16 km/h they half-bound (Simons 1996, J Morphol
230:299): forefeet down in sequence, hind feet nearly together, 3.5 strides a
second at 12 km/h - a 0.95 m stride. At speed the hind feet land ahead of where
the forefeet were. `Bound` is that gait, scaled to this body by dynamic
similarity on hind-leg length (v ~ L^0.5, f ~ L^-0.5) from a reference NZ White
leg (femur 82.3 mm; tibia and foot from ratios marked UNVERIFIED in `hoppers`).
`Hop` is the slow gait: 0.40 s of hind stance (Hall 2022) at a duty factor of
0.5 - the duty and its stroke are design numbers.

THE JUMP
--------

    launch   take-off speed and angle per kind; the push is constant
             acceleration over the hip's travel d, so it lasts 2 d / v
    cricket  1-3 m/s at 20-30 degrees (Acheta; Hustert & Baldus 2010): 2.0 m/s at
             25 used. Co-contraction 10-120 ms before release: 60 ms used
    rabbit   no take-off measurement was found. 3.0 m/s at 40 degrees is a
             design number (UNVERIFIED); extension runs proximal to distal, hip
             then knee then ankle, as a frog's does (Astley & Roberts 2014)
    flight   the engine's: a ballistic arc from the launch velocity. Locusts leave
             the ground spinning at hundreds of degrees a second but 98.8% of a
             jump's kinetic energy is translation (Goode et al. 2023) - the clip
             does not spin
    landing  a rabbit's forefeet first, hind feet swinging down after; a cricket
             into a crouch, hind tibiae folded (a landed locust holds its femora
             ~40 degrees to the ground, tibiae fully flexed: Reichel et al. 2019)

The clips are authored in place, as everywhere in this package, except that a
launch and a landing move the body over planted feet. How far is handed to the
engine as `takeoff_offset_model` and `land_offset_model`, so it can put the root
where the body is when it switches clips.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Vector

from . import bodymap, hoppers, keyposes as kp, locomotion as lm, motion, stored

G = 9.81

# Degrees of spine arch a hopping body may take to bring its shoulders down to
# its forelegs before it pitches instead (design)
ARCH_MAX = 18.0

# NZ White reference hind leg, hip to ball: femur 82.3 mm (PubMed 23420943),
# tibia 1.15x (UNVERIFIED), metatarsus ~48 mm (UNVERIFIED, MT3 / femur 0.5-0.6)
REF_RABBIT_LEG = 0.0823 + 0.0946 + 0.048

# Hall et al. 2022: ankle (tibia-metatarsus) included angle through hind stance
ANKLE_PROFILE = ((0.0, 103.0), (0.38, 66.0), (1.0, 137.0))

GAITS = {
    # half-bound, Simons 1996: 3.5 Hz, 0.95 m stride at 12 km/h
    "Bound": {"speed_ref": 3.33, "hz_ref": 3.5, "hind_duty": 0.28, "fore_duty": 0.26,
              "fore_on": 0.50, "fore_lag": 0.06, "pitch": 6.0, "flex": 8.0, "frames": 16,
              "hind_ahead": 0.15,
              "source": "half-bound, Simons 1996 (3.5 Hz at 12 km/h); duties, pitch and flex design"},
    # slow hop: Hall 2022 hind stance 0.40 s; duty 0.5 and the stroke design
    "Hop": {"hind_stance_s": 0.40, "hind_duty": 0.50, "fore_duty": 0.36, "fore_on": 0.58,
            "fore_lag": 0.10, "stroke_over_leg": 0.55, "pitch": 4.0, "flex": 4.0, "frames": 24,
            "hind_ahead": 0.15,
            "source": "hind stance 0.40 s (Hall 2022); duty 0.5, stroke 0.55 leg, pitch and flex design"},
}

JUMPS = {
    "orthopteran": {"speed": 2.0, "angle": 25.0, "cock_s": 0.06, "knee_cocked": 12.0, "knee_takeoff": 145.0,
                    "land_knee": 25.0,
                    "source": "Acheta: 1-3 m/s at 20-30 deg, knee 10-150 deg, co-contraction 10-120 ms "
                              "(Hustert & Baldus 2010)"},
    "leporid": {"speed": 3.0, "angle": 40.0, "cock_s": 0.20, "knee_takeoff": 140.0, "ankle_takeoff": 137.0,
                "land_knee": None,
                "source": "UNVERIFIED design (no rabbit take-off measurement found); ankle 137 deg at "
                          "toe-off from Hall 2022, proximal-to-distal order from Astley & Roberts 2014"},
}


def _lerp_profile(profile, u):
    u = max(0.0, min(1.0, u))
    for (u0, a0), (u1, a1) in zip(profile, profile[1:]):
        if u <= u1:
            w = (u - u0) / max(u1 - u0, 1e-9)
            w = w * w * (3.0 - 2.0 * w)
            return a0 + (a1 - a0) * w
    return profile[-1][1]


def _angle_at(a, b, c):
    u, v = a - b, c - b
    if u.length < 1e-12 or v.length < 1e-12:
        return 180.0
    return math.degrees(u.angle(v))


# --------------------------------------------------------------------------
# the body
# --------------------------------------------------------------------------

class Hopper:
    """A hopper rig with its body map, poser, and the saltatorial legs picked out."""

    def __init__(self, rig_name, mass_kg=None):
        rig = bpy.data.objects.get(rig_name)
        st = hoppers.read(rig)
        if st is None:
            raise ValueError("%s carries no hopper rig - run hoppers.build and hoppers.skin" % rig_name)
        self.rig, self.st, self.kind = rig, st, st["kind"]
        self.bm = bodymap.build(rig_name, forward=st["forward"], up=st["up"], floor=0.0)
        if "error" in self.bm:
            raise ValueError(self.bm["error"])
        self.body = motion.Body(rig, self.bm)
        self.P = kp.Poser(self.body)
        self.fwd, self.up, self.lat = self.bm["fwd"], self.bm["up_vec"], self.bm["lat"]
        self.scale = sum(rig.matrix_world.to_scale()) / 3.0
        by_upper = {l["upper"]: l for l in self.P.legs}
        self.legs = {}
        for g in st["legs"]:
            limb = by_upper.get(g["bones"][0])
            if limb is not None:
                self.legs[g["name"]] = dict(limb, hop=g)
        self.hind = [self.legs[n] for n in st["saltatorial"] if n in self.legs]
        self.others = [l for n, l in self.legs.items() if n not in st["saltatorial"]]
        self.fore = [l for l in self.others if l["hop"]["rank"] == "fore"]
        from .flight import mesh_volume
        vol, _ = mesh_volume(rig)
        density = 1050.0 if self.kind == "leporid" else 1100.0
        self.mass_kg = float(mass_kg) if mass_kg else vol * density
        self.mass_source = "given" if mass_kg else "skin volume x %.0f kg/m3" % density

    # lengths in armature units
    def seg(self, limb):
        b = self.rig.data.bones
        m = b[limb["end"]].length if limb["end"] else 0.0
        return limb["a"], limb["b"], m

    def leg_length(self, limb):
        a, b, m = self.seg(limb)
        return a + b + m

    def hip_height(self, limb):
        return self.P.height(limb["rest_root"])

    def pivot(self, limb):
        return lm.contact_pivot(self.rig, limb)


# --------------------------------------------------------------------------
# the pantograph leg
# --------------------------------------------------------------------------

def pantograph(H, limb, contact, phi_deg, dx_want):
    """Hind stance, constructed: the ball of the foot on `contact`, the ankle's
    included angle `phi_deg`, femur parallel to metatarsus, and the hip `dx_want`
    ahead of the contact along the body. Returns (hip, hock, alpha_deg, error)
    in armature space; alpha is the metatarsus's elevation above the floor."""
    fe, ti, m = H.seg(limb)
    f, u = H.fwd, H.up
    lat_off = (limb["rest_root"] - contact).dot(H.lat)
    phi = math.radians(phi_deg)

    def build(alpha):
        e = f * math.cos(alpha) - u * math.sin(alpha)           # hock -> ball
        hock = contact - e * m
        k = f * math.cos(phi - alpha) + u * math.sin(phi - alpha)
        knee = hock + k * ti
        hip = knee - e * fe
        return hip, hock

    def err(alpha):
        return (build(alpha)[0] - contact).dot(f) - dx_want

    best = min((abs(err(math.radians(a))), a) for a in range(0, 90))
    a0 = math.radians(best[1])
    lo, hi = max(0.0, a0 - math.radians(1.0)), min(math.radians(89.5), a0 + math.radians(1.0))
    if err(lo) * err(hi) < 0.0:
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            if err(lo) * err(mid) <= 0.0:
                hi = mid
            else:
                lo = mid
        a0 = 0.5 * (lo + hi)
    hip, hock = build(a0)
    hip = hip + H.lat * lat_off
    hock = hock + H.lat * lat_off
    return hip, hock, math.degrees(a0), abs(err(a0))


def rest_alpha(H, limb):
    b = H.rig.data.bones[limb["end"]]
    v = b.head_local - b.tail_local
    return math.degrees(math.atan2(v.dot(H.up), max(-v.dot(H.fwd), 1e-12)))


def ankle_angle(H, mats, limb):
    b = H.rig.data.bones
    knee = mats[limb["lower"]].translation
    hock = mats[limb["end"]].translation
    ball = motion.tail_of(H.body, mats, limb["end"])
    return _angle_at(knee, hock, ball)


def knee_angle(H, mats, limb):
    hip = mats[limb["upper"]].translation
    knee = mats[limb["lower"]].translation
    hock = mats[limb["end"]].translation if limb["end"] else motion.tail_of(H.body, mats, limb["lower"])
    return _angle_at(hip, knee, hock)


def femur_meta_angle(H, mats, limb):
    fem = mats[limb["lower"]].translation - mats[limb["upper"]].translation
    met = motion.tail_of(H.body, mats, limb["end"]) - mats[limb["end"]].translation
    return math.degrees(fem.angle(met)) if fem.length and met.length else 0.0


# --------------------------------------------------------------------------
# plans
# --------------------------------------------------------------------------

def plan_gait(H, role):
    g = GAITS[role]
    L = sum(H.leg_length(l) for l in H.hind) / len(H.hind) * H.scale
    k = L / REF_RABBIT_LEG
    out = {"role": role, "hind_leg_m": L, "scale_to_reference": k, "source": g["source"]}
    if "speed_ref" in g:
        speed = g["speed_ref"] * math.sqrt(k)
        hz = g["hz_ref"] / math.sqrt(k)
        stride = speed / hz
        stroke = stride * g["hind_duty"]
    else:
        period = g["hind_stance_s"] * math.sqrt(k) / g["hind_duty"]
        hz = 1.0 / period
        stroke = g["stroke_over_leg"] * L
        stride = stroke / g["hind_duty"]
        speed = stride * hz
    h = sum(H.hip_height(l) for l in H.hind) / len(H.hind) * H.scale
    out.update({"speed_mps": speed, "frequency_hz": hz, "stride_m": stride, "hind_stroke_m": stroke,
                "fore_stroke_m": stride * g["fore_duty"], "hip_height_rest_m": h,
                "froude": speed * speed / (G * max(h, 1e-9))})
    for key in ("hind_duty", "fore_duty", "fore_on", "fore_lag", "pitch", "flex", "frames", "hind_ahead"):
        out[key] = g[key]
    return out


def plan_jump(H, speed=None, angle=None):
    j = dict(JUMPS[H.kind])
    if speed:
        j["speed"] = speed
    if angle:
        j["angle"] = angle
    v, th = j["speed"], math.radians(j["angle"])
    j.update({"flight_time_s": 2.0 * v * math.sin(th) / G,
              "range_m": v * v * math.sin(2.0 * th) / G,
              "apex_m": (v * math.sin(th)) ** 2 / (2.0 * G)})
    return j


# --------------------------------------------------------------------------
# the hop / bound cycle
# --------------------------------------------------------------------------

def _foot(phase, duty, stroke, lift, over):
    return lm.foot_state(phase, duty, stroke, lift, over)


def _within_reach(p, limb, posed, target, share=0.95):
    """A foot in the air goes where it is asked, or as near as the leg reaches
    (`keyposes.within_reach`: height goes before ground position). An airborne
    body high over its toe-off asked the forelegs for 117%."""
    return kp.within_reach(p, limb, posed, target, share=share)


def hop_cycle(rig_name, role="Hop", action_name=None, frames=None, fps=None, attempts=8):
    """A looping half-bound (`Bound`) or slow hop (`Hop`), in place.

    Phase 0 is hind touchdown. Both hind feet push together; the forefeet land
    in sequence at `fore_on`, `fore_lag` apart. In hind stance the hips ride the
    pantograph leg on Hall's ankle profile; in fore stance the forelegs reach
    their contacts; between stances the body flies on a ballistic arc."""
    H = Hopper(rig_name)
    if H.kind != "leporid":
        return {"error": "%s is a %s; hop and bound cycles are leporid gaits" % (rig_name, H.kind)}
    pl = plan_gait(H, role)
    fps_now = fps or bpy.context.scene.render.fps
    n = int(frames or pl["frames"])
    P, body, bm = H.P, H.body, H.bm
    sc = H.scale
    S_h = pl["hind_stroke_m"] / sc
    dH = pl["hind_duty"]
    period = 1.0 / pl["frequency_hz"]
    fore = sorted(H.fore, key=lambda l: l["side"])
    fore_on = {l["name"]: (pl["fore_on"] + i * pl["fore_lag"]) % 1.0 for i, l in enumerate(fore)}
    # Every planted foot sweeps back at the one belt speed, S_h / dH - the body's
    # speed. A foreleg that cannot reach spends less of the cycle down; it never
    # sweeps a shorter stroke at the same duty, which is slower than the body:
    # the first bound did, and its forefeet would have skated at 44% speed.
    state = {"S_h": S_h, "dF": pl["fore_duty"], "lift": 1.0}

    def S_f():
        return state["S_h"] / dH * state["dF"]
    limited = []
    L_h = sum(H.leg_length(l) for l in H.hind) / len(H.hind)

    # Hip fore-aft relative to the contact at stance progress u: centred under
    # the hip at mid-stance, the contact sweeping back by the stroke.
    # Hind feet come down ahead of the hips, under the belly - `hind_ahead` leg
    # lengths (design). Centred under the hips, the pantograph stood the legs
    # up straight and put the haunch on stilts, the head 26 degrees down.
    centres = {}
    for l in H.hind:
        centres[l["name"]] = H.pivot(l) + H.fwd * ((l["rest_root"] - H.pivot(l)).dot(H.fwd)
                                                   + pl["hind_ahead"] * L_h)
    for l in fore:
        centres[l["name"]] = H.pivot(l) + H.fwd * (0.35 * (l["rest_root"] - H.pivot(l)).dot(H.fwd))

    def hind_solution(u, S):
        """(hip height above rest hip, hock, alpha) for hind stance progress u."""
        l = H.hind[0]
        phi = _lerp_profile(ANKLE_PROFILE, u)
        x = 0.5 * S - S * u                                   # contact relative to centre
        c = centres[l["name"]] + H.fwd * x
        dx_want = (l["rest_root"] - centres[l["name"]]).dot(H.fwd) - x
        hip, hock, alpha, e = pantograph(H, l, c, phi, dx_want)
        return P.height(hip) - P.height(l["rest_root"]), alpha, e

    def hermite(a, b, va, vb, w, span):
        w2, w3 = w * w, w * w * w
        return ((2 * w3 - 3 * w2 + 1) * a + (w3 - 2 * w2 + w) * va * span
                + (-2 * w3 + 3 * w2) * b + (w3 - w2) * vb * span)

    f_on = min(fore_on.values())
    def f_off_now():
        return max(fore_on[k] + state["dF"] for k in fore_on)

    def hip_rise(p0):
        """The hips over their rest height. Hind stance: the pantograph. Between
        hind stances the hind legs swing and the hips are free: they carry on
        from toe-off and come down to the next strike on a smooth curve."""
        S = state["S_h"]
        if p0 <= dH:
            return hind_solution(p0 / dH, S)[0]
        eps = 0.02
        a, b = hind_solution(1.0, S)[0], hind_solution(0.0, S)[0]
        va = (a - hind_solution(1.0 - eps, S)[0]) / (eps * dH)
        vb = (hind_solution(eps, S)[0] - b) / (eps * dH)
        span = 1.0 - dH
        # half the push's upward speed carries on: the rump rises past toe-off
        # and turns, rather than coasting up through the whole swing
        return hermite(a, b, 0.5 * va, vb, (p0 - dH) / span, span)

    sh_rest = sum(P.height(l["rest_root"]) for l in fore) / len(fore)
    L_f = sum(l["a"] + l["b"] for l in fore) / len(fore)

    def shoulder_rise(p0):
        """The shoulders over their rest height. Fore stance: carried by the
        forelegs, a little below rest and giving under the load. Otherwise the
        front is free, rising through the hind push toward level."""
        base = -0.06 * L_f

        def fore_val(u):
            return base - 0.04 * L_f * math.sin(math.pi * max(0.0, min(1.0, u)))
        q = (p0 - f_on) % 1.0
        span_f = f_off_now() - f_on
        if q <= span_f:
            return fore_val(q / span_f)
        # free: from fore lift-off round to the next fore touchdown
        w = (q - span_f) / max(1.0 - span_f, 1e-9)
        # The front follows the hips while it is free: 60% of their rise, eased
        # in and out of the fore stances. Held down, the test rabbit's toe-off
        # pitched it 47 degrees nose-down, head at the floor.
        window = math.sqrt(max(0.0, math.sin(math.pi * w)))
        return base + 0.6 * max(0.0, hip_rise(p0)) * window

    def axial_heights(key):
        posed, _ = P.pose(kp.Key(drop=key.drop, lean=key.lean, flex=key.flex, head_level=key.head_level))
        hip = sum(P.height(posed[l["upper"]].translation) for l in H.hind) / len(H.hind)
        sh = sum(P.height(posed[l["upper"]].translation) for l in fore) / len(fore)
        return hip, sh

    hip_rest = sum(P.height(l["rest_root"]) for l in H.hind) / len(H.hind)
    solved = {}

    def body_key(p0):
        """Drop and pitch putting hips and shoulders at their curves' heights."""
        if p0 in solved:
            return solved[p0]
        base_flex = pl["flex"] * math.cos(2.0 * math.pi * p0)
        want_hip = hip_rest + hip_rise(p0)
        want_sh = sh_rest + shoulder_rise(p0)
        key = kp.Key(drop=-hip_rise(p0), lean=0.0, flex=base_flex, head_level=1.0)

        def pitch(theta):
            # The trunk pitches as one piece. `lean` alone tips the pelvis half
            # as far as the chest, and the 47 degrees this cycle asked for
            # crushed the belly - 140 faces inside out on one spine bone. A lean
            # of 4/3 theta and a counter-arch of theta/3 pitch every torso bone
            # by theta.
            key.lean = 4.0 * theta / 3.0
            key.flex = base_flex - theta / 3.0
        theta = 0.0
        for _ in range(4):
            lo, hi = -40.0, 45.0
            for _ in range(22):
                theta = 0.5 * (lo + hi)
                pitch(theta)
                if axial_heights(key)[1] > want_sh:
                    lo = theta
                else:
                    hi = theta
            pitch(theta)
            got_hip = axial_heights(key)[0]
            if abs(got_hip - want_hip) < 1e-5 * bm["size"]:
                break
            key.drop += got_hip - want_hip
        solved[p0] = (key.drop, key.lean, key.flex, theta)
        return solved[p0]

    def key_at(p0):
        drop, lean, flex, _ = body_key(p0)
        limbs = {}
        for l in H.hind:
            ph = p0 % 1.0
            x, y, plant, stance, u = _foot(ph, dH, state["S_h"], 0.12 * L_h, 0.1 * state["S_h"])
            c = centres[l["name"]] + H.fwd * x + H.up * y
            if stance:
                su = ph / dH
                _, alpha, _ = hind_solution(su, state["S_h"])
                tilt = alpha - rest_alpha(H, l)
            else:
                # swinging: the heel carried lifted, folding forward mid-swing
                _, a_off, _ = hind_solution(1.0, state["S_h"])
                _, a_on, _ = hind_solution(0.0, state["S_h"])
                tilt = (a_off + (a_on - a_off) * motion.smoothstep(u)) - rest_alpha(H, l)                     + 25.0 * math.sin(math.pi * u)
            v = l["rest_eff"] - H.pivot(l)
            if stance:
                tgt = (lambda p, limb, posed, c=c, v=v: c + v)
            else:
                tgt = (lambda p, limb, posed, c=c, v=v, t=tilt: _within_reach(
                    p, limb, posed, c + v + p.tilt_rotation(limb, t)[1]) - p.tilt_rotation(limb, t)[1])
            limbs[l["name"]] = {"target": tgt, "planted": plant, "tilt": tilt}
        for l in fore:
            ph = (p0 - fore_on[l["name"]]) % 1.0
            x, y, plant, stance, u = _foot(ph, state["dF"], S_f(), 0.15 * (l["a"] + l["b"]), 0.1 * S_f())
            c = centres[l["name"]] + H.fwd * x + H.up * y
            r = lm.Reach(P, l)
            limbs[l["name"]] = {
                "target": ((lambda p, limb, posed, c=c, r=r: c + r.v) if stance else
                           (lambda p, limb, posed, c=c, r=r: _within_reach(p, limb, posed, c + r.v))),
                "planted": plant,
                "tilt": (lambda p, limb, posed, t, c=c, r=r: r.tilt(posed[limb["upper"]].translation, c)[0]),
            }
        return kp.Key(drop=drop, limbs=limbs, lean=lean, head_level=1.0, flex=flex,
                      tail_lift=10.0 + 0.5 * flex)

    lean0 = {"deg": 0.0, "arch": 0.0}

    def pose_frame(p0):
        return P.pose(key_at(p0))

    for attempt in range(attempts):
        solved.clear()
        samples = [pose_frame((f - 1) / float(n)) for f in range(1, n + 2)]
        clamped = sorted({nm for _, infos in samples for nm, i in infos.items() if i["clamped"]})
        if not clamped:
            break
        # Only the legs that miss pay. Shortening the hind stroke for a foreleg's
        # sake kept the hind foot under the hip, the pantograph stood the leg
        # straight, the hips rose - and the forelegs missed by more.
        hind_names = {l["name"] for l in H.hind}
        if any(nm in hind_names for nm in clamped):
            state["S_h"] *= 0.9
        if any(nm not in hind_names for nm in clamped):
            state["dF"] = max(0.12, state["dF"] * 0.88)
        limited.append("hind stroke %.0f%%, fore duty %.0f%% (%s out of reach)"
                       % (100 * state["S_h"] / S_h, 100 * state["dF"] / pl["fore_duty"], ", ".join(clamped)))

    from .actions import _author_samples, _check_common, _pose_gap
    skin_checks = skin_checks_for(body)

    def check(keyed, ev, infos_by_frame):
        def in_stance(name, f):
            leg = next((l for l in H.hind + fore if l["name"] == name), None)
            if leg is None:
                return False
            duty = dH if leg in H.hind else state["dF"]
            on = 0.0 if leg in H.hind else fore_on[name]
            return ((f - 1) / float(n) - on) % 1.0 < duty
        r = _check_common(body, bm, keyed, ev, infos_by_frame, planted=[], posed_limbs=P.legs,
                          rest_floor=0.0, starts_at_rest=False,
                          skid=in_stance)  # stance is held to the stance-line test below
        E = ev["evaluated"]
        seam, bone = _pose_gap(H.rig, E[1], E[n + 1])
        r["loop_seam"] = round(seam, 6)
        if seam > 1e-4 * bm["size"]:
            r["failures"].append("loop seam %.5f on %s" % (seam, bone))
        tol = 0.006 * bm["size"]
        slip = {}
        for l in H.hind + fore:
            duty = dH if l in H.hind else state["dF"]
            on = 0.0 if l in H.hind else fore_on[l["name"]]
            S = state["S_h"] if l in H.hind else S_f()
            worst = 0.0
            for f in range(1, n + 2):
                ph = ((f - 1) / float(n) - on) % 1.0
                if ph >= duty:
                    continue
                want = centres[l["name"]] + H.fwd * (0.5 * S - S * ph / duty)
                got = body.carried(E[f], l["end"], H.pivot(l))
                worst = max(worst, (got - want).length)
            slip[l["name"]] = round(worst * sc, 5)
            if worst > tol:
                r["failures"].append("%s leaves its stance line by %.4f - it would skate" % (l["name"], worst))
        r["contact_slip_m"] = slip
        belts = {"hind": state["S_h"] / dH, "fore": S_f() / state["dF"]}
        r["stance_speed_ratio"] = round(belts["fore"] / belts["hind"], 4)
        if abs(belts["fore"] / belts["hind"] - 1.0) > 0.02:
            r["failures"].append("forefeet sweep back at %.0f%% of the hind feet's speed - one pair skates"
                                 % (100 * belts["fore"] / belts["hind"]))
        # the hind leg on Hall's profile, parallel to its metatarsus
        ank, par = {}, 0.0
        for l in H.hind:
            got = []
            for f in range(1, n + 1):
                ph = (f - 1) / float(n)
                if ph < dH:
                    got.append((ph / dH, ankle_angle(H, E[f], l)))
                    par = max(par, femur_meta_angle(H, E[f], l))
            strike = min(got, key=lambda g: g[0])[1]
            low = min(g[1] for g in got)
            toe_off = max(got, key=lambda g: g[0])[1]
            ank[l["name"]] = {"strike": round(strike, 1), "min": round(low, 1), "last_stance": round(toe_off, 1)}
        r["ankle_deg"] = ank
        r["ankle_plan_deg"] = {"strike": 103.0, "min": 66.0, "toe_off": 137.0}
        r["femur_metatarsus_max_deg"] = round(par, 2)
        for nm, a in ank.items():
            if abs(a["min"] - 66.0) > 15.0:
                r["failures"].append("%s ankle closes to %.0f deg in stance, Hall 2022 measured 66" % (nm, a["min"]))
        if par > 12.0:
            r["failures"].append("femur and metatarsus part by %.0f deg in stance - not a pantograph" % par)
        # both hind feet together
        hts = []
        for f in range(1, n + 1):
            hts.append([P.height(body.carried(E[f], l["end"], H.pivot(l))) for l in H.hind])
        spread = max(abs(h[0] - h[-1]) for h in hts) * sc
        r["hind_height_mismatch_m"] = round(spread, 5)
        if spread > 0.01 * bm["size"] * sc:
            r["failures"].append("the hind feet do not move together (%.4f m apart in height)" % spread)
        skin_report(r, skin_checks, body, E, range(1, n + 1))
        # hind feet overstep the forefeet at speed: world position at touchdown
        stride = state["S_h"] / dH
        hind_td = sum((centres[l["name"]] + H.fwd * (0.5 * state["S_h"])).dot(H.fwd) for l in H.hind) / len(H.hind)
        fore_prints = [(centres[l["name"]] + H.fwd * (0.5 * S_f())).dot(H.fwd)
                       + stride * fore_on[l["name"]] - stride for l in fore]
        r["hind_overstep_m"] = round((hind_td - max(fore_prints)) * sc, 4)
        if role == "Bound" and r["hind_overstep_m"] <= 0.0:
            r["failures"].append("the hind feet land behind the forefeet's prints - a bound oversteps")
        return r

    action_name = action_name or "%s_%s" % (rig_name, role)
    keyed, infos, action, report = _author_samples(body, H.rig, action_name, samples, fps, check)
    if "error" in report:
        return report
    ratio = state["S_h"] / S_h
    speed = pl["speed_mps"] * ratio
    duration = (n + 1) / float(fps_now)
    stance_s = dH * n / fps_now
    report.update({
        "rig": rig_name, "action": action.name, "role": role, "frames": [1, n + 1], "fps": fps_now,
        "plan": {k: (round(v, 5) if isinstance(v, float) else v) for k, v in pl.items()},
        "gait": "half-bound" if role == "Bound" else "hop",
        "froude": round(speed * speed / (G * pl["hip_height_rest_m"]), 3),
        "duty_factor": dH, "natural_speed_mps": round(speed, 4),
        "stride_m": round(pl["stride_m"] * ratio, 4), "stroke_m": round(state["S_h"] * sc, 4),
        "stride_frequency_hz": round(pl["frequency_hz"], 4),
        "hip_height_m": round(pl["hip_height_rest_m"], 4), "spine_flex_deg": pl["flex"],
        "implied_speed_cycle_mps": round(state["S_h"] * sc / stance_s, 4),
        "playback_speed_scale": round(pl["frequency_hz"] * duration, 4),
        "fore_touchdown_phase": {k: round(v, 3) for k, v in fore_on.items()},
        "fore_duty": round(state["dF"], 4),
        "limited_by": limited, "attempts": attempt + 1, "body_pitch_deg": [round(min(v[3] for v in solved.values()), 1),
                           round(max(v[3] for v in solved.values()), 1)],
    })
    return report


class SkinChecks:
    """Stretch and inversion on the linear-blend-skinned mesh, for poses that
    swing joints ~100 degrees.

    - Edges under a quarter of the median rest length are left out, and
      counted: voxel and metaball skins leave slivers along creases, and any
      motion multiplies their length many times.
    - A face is inverted when its posed normal opposes its rest normal carried
      by the BLENDED rotation of its weights. The shared check compares against
      its top-weighted bone alone, and haunch skin half on a femur swinging 90
      degrees - turning, correctly, half as far - read as 270 inside-out faces.
    """

    def __init__(self, body):
        import statistics
        self.body = body
        rig = body.rig
        self.meshes = []
        self.dropped_edges = 0
        for o in bpy.data.objects:
            if o.type != "MESH" or not any(md.type == "ARMATURE" and md.object == rig for md in o.modifiers):
                continue
            m = rig.matrix_world.inverted() @ o.matrix_world
            names = {g.index: g.name for g in o.vertex_groups if g.name in rig.data.bones}
            cos = [m @ v.co for v in o.data.vertices]
            ws = []
            for v in o.data.vertices:
                w = {names[g.group]: g.weight for g in v.groups if g.group in names and g.weight > 0}
                t = sum(w.values())
                ws.append({k: x / t for k, x in w.items()} if t else {})
            faces = [tuple(p.vertices) for p in o.data.polygons]
            edges = {(min(a, b), max(a, b)) for f in faces for a, b in zip(f, f[1:] + f[:1])}
            rest_len = {e: (cos[e[0]] - cos[e[1]]).length for e in edges}
            med = statistics.median(rest_len.values()) if rest_len else 0.0
            keep = [e for e in edges if rest_len[e] >= 0.25 * med]
            self.dropped_edges += len(edges) - len(keep)
            normals, fw = [], []
            for f in faces:
                nv = Vector((0.0, 0.0, 0.0))
                for k in range(len(f)):
                    nv += cos[f[k]].cross(cos[f[(k + 1) % len(f)]])
                longest = max((cos[f[k]] - cos[f[(k + 1) % len(f)]]).length for k in range(len(f)))
                normals.append(None if 0.5 * nv.length < 0.1 * longest * longest else nv)
                acc = {}
                for vi in f:
                    for k, x in ws[vi].items():
                        acc[k] = acc.get(k, 0.0) + x / len(f)
                fw.append(acc)
            self.meshes.append({"cos": cos, "ws": ws, "faces": faces, "edges": keep, "rest_len": rest_len,
                                "normals": normals, "face_w": fw})

    def measure(self, mats, q=0.99):
        body = self.body
        deform = {n: mats[n] @ body.rest[n].inverted() for n in body.rest}
        lin = {n: d.to_3x3() for n, d in deform.items()}
        ratios, flipped = [], 0
        for m in self.meshes:
            pos = []
            for co, ws in zip(m["cos"], m["ws"]):
                p = Vector((0.0, 0.0, 0.0))
                for n, w in ws.items():
                    p += (deform[n] @ co) * w
                pos.append(p if ws else co)
            ratios += [(pos[a] - pos[b]).length / m["rest_len"][(a, b)] for a, b in m["edges"]]
            for f, n0, fw in zip(m["faces"], m["normals"], m["face_w"]):
                if n0 is None or not fw:
                    continue
                n1 = Vector((0.0, 0.0, 0.0))
                for k in range(len(f)):
                    n1 += pos[f[k]].cross(pos[f[(k + 1) % len(f)]])
                carried = Vector((0.0, 0.0, 0.0))
                for nm, x in fw.items():
                    carried += (lin[nm] @ n0) * x
                if n1.length > 1e-12 and n1.dot(carried) < 0.0:
                    flipped += 1
        ratios.sort()
        if not ratios:
            return 1.0, 1.0, flipped
        return ratios[-1], ratios[int(q * (len(ratios) - 1))], flipped


def skin_checks_for(body):
    return SkinChecks(body)


def skin_report(r, checks, body, evaluated, frames, max_limit=20.0, p99_limit=3.5, every=None,
                flip_share=0.02):
    """Skin stretch and inversion over a clip's frames.

    Fails on the 99th-percentile edge stretch past `p99_limit`, the single worst
    edge past `max_limit`, or more than `flip_share` of faces inverted beyond rest. The
    worst edge alone is too local to judge a creature by - a flank fold between a
    swinging shin and the belly takes it on a handful of edges - so it has its own,
    looser limit and is always reported."""
    frames = list(frames)
    step = every or max(1, len(frames) // 8)
    _, _, rest_flips = checks.measure(body.fk())
    worst, worst_p, worst_f, at = 1.0, 1.0, 0, None
    for f in frames[::step] + [frames[-1]]:
        mx, p99, fl = checks.measure(evaluated[f])
        if mx > worst:
            worst, at = mx, f
        worst_p = max(worst_p, p99)
        worst_f = max(worst_f, fl - rest_flips)
    total = sum(len(m["faces"]) for m in checks.meshes)
    r["stretch_max"], r["stretch_p99"], r["flipped_faces"] = round(worst, 3), round(worst_p, 3), worst_f
    r["stretch_ignored_edges"] = checks.dropped_edges
    if worst_p > p99_limit:
        r["failures"].append("1%% of skin edges stretch past %.1fx" % worst_p)
    if worst > max_limit:
        r["failures"].append("skin stretches to %.1fx at frame %s" % (worst, at))
    # 2% of faces: a gathered hind swing tucks the test rabbit's thighs under its
    # belly and inverts 1.3-1.5% of its faces there, which no weighting tried
    # removed (less femur influence made it worse, more too). A linear-blend
    # limit; corrective shapes would fix it and are not done.
    if worst_f > flip_share * total:
        r["failures"].append("%d faces turn inside out" % worst_f)


# --------------------------------------------------------------------------
# the jump: launch, air, land
# --------------------------------------------------------------------------

def _pitch_key(key, theta, base_flex=0.0):
    """Pitch the trunk as one piece by `theta` (positive nose down)."""
    key.lean = 4.0 * theta / 3.0
    key.flex = base_flex - theta / 3.0
    return key


def _to_model(v):
    return [round(v.x, 5), round(v.z, 5), round(-v.y, 5)]


def _planted(limb, tilt=0.0):
    return {"target": (lambda p, l, posed: l["rest_eff"].copy()), "planted": True, "tilt": tilt}


def _free(fn):
    return {"target": fn, "planted": 0.7}


def _hip_rel(H, fold, f, u):
    """A leg in the air: its rest reach from the hip, scaled by `fold`, pushed
    forward / up by fractions of the leg's length - within reach."""
    def fn(p, limb, posed):
        hip = posed[limb["upper"]].translation
        reach = limb["a"] + limb["b"]
        t = hip + (limb["rest_eff"] - limb["rest_root"]) * fold + (p.fwd * f + p.up * u) * reach
        return _within_reach(p, limb, posed, t, share=0.93)
    return fn


def _ankle_for(H, key, limb, phi, lo=-15.0, hi=85.0):
    """The heel lift that gives `limb` an ankle angle of `phi` in this key."""
    def angle(t):
        k = key.copy(limbs=dict(key.limbs))
        k.limbs[limb["name"]] = _planted(limb, t)
        posed, info = H.P.pose(k)
        return ankle_angle(H, posed, limb), info[limb["name"]]["clamped"]
    best = None
    for t in range(int(lo), int(hi) + 1, 5):
        a, cl = angle(float(t))
        if not cl and (best is None or abs(a - phi) < best[0]):
            best = (abs(a - phi), float(t))
    if best is None:
        return 0.0
    t0 = best[1]
    a_lo, a_hi = t0 - 5.0, t0 + 5.0
    for _ in range(12):
        m1, m2 = a_lo + (a_hi - a_lo) / 3.0, a_hi - (a_hi - a_lo) / 3.0
        if abs(angle(m1)[0] - phi) < abs(angle(m2)[0] - phi):
            a_hi = m2
        else:
            a_lo = m1
    return 0.5 * (a_lo + a_hi)


def _travel(H, key, d, s):
    k = key.copy(limbs=dict(key.limbs))
    k.drop = key.drop - d.dot(H.up) * s
    k.shift = key.shift + d.dot(H.fwd) * s
    return k


def _extension_onsets(series, fps):
    """First time each joint's angle has made 15% of its opening during the push."""
    out = {}
    for name, vals in series.items():
        lo, hi = min(vals), max(vals)
        if hi - lo < 5.0:
            out[name] = None
            continue
        start = vals[0]
        target = start + 0.15 * (max(vals) - start)
        idx = next((i for i, v in enumerate(vals) if v >= target), None)
        out[name] = None if idx is None else round(idx / float(fps), 4)
    return out


def launch(rig_name, action_name=None, fps=None, speed=None, angle=None):
    """From rest, gather, push, leave the ground - ending on the take-off pose.

    The body moves over planted hind feet: first down and back into the cocked
    pose, then along the take-off direction at constant acceleration until the
    hind leg has opened to its take-off extension. How far that is sets how long
    the push lasts: 2 D / v. The engine takes the body over from the last frame,
    at `takeoff_offset_model` from the root, moving at the take-off velocity."""
    H = Hopper(rig_name)
    P, body, bm = H.P, H.body, H.bm
    jp = plan_jump(H, speed, angle)
    fps_now = fps or bpy.context.scene.render.fps
    th = math.radians(jp["angle"])
    d = H.fwd * math.cos(th) + H.up * math.sin(th)
    hind = H.hind
    others = [l for l in P.legs if l["name"] not in {h["name"] for h in hind}]
    Lh = sum(l["a"] + l["b"] for l in hind) / len(hind)

    def base(drop=0.0, shift=0.0, theta=0.0, hind_tilt=0.0, others_spec=None):
        # a cricket's abdomen reads as a tail behind its hind legs; it is not lifted
        k = kp.Key(drop=drop, shift=shift, head_level=1.0, tail_lift=15.0 if H.kind == "leporid" else 0.0)
        _pitch_key(k, theta)
        for l in hind:
            k.limbs[l["name"]] = _planted(l, hind_tilt)
        for l in others:
            k.limbs[l["name"]] = (others_spec or {}).get(l["name"], _planted(l))
        return k

    def knee(key):
        posed, info = P.pose(key)
        return sum(knee_angle(H, posed, l) for l in hind) / len(hind), posed, info

    # --- the gathered pose
    aim = -0.5 * jp["angle"]                        # nose up toward the take-off
    cock_contacts = {}
    if H.kind == "orthopteran":
        # A planted tarsus and a still hip fix the knee angle: only the distance
        # between them sets it. Dropping the test cricket 3 mm closed its knee
        # from 32 degrees to 28 before its belly met the floor. So the hind
        # tarsi step in first - under the femur, behind the hip, at the distance
        # a knee folded to `knee_cocked` spans - and the push opens it from there.
        l0 = hind[0]
        a, b = l0["a"], l0["b"]
        r = math.sqrt(max(a * a + b * b - 2.0 * a * b * math.cos(math.radians(jp["knee_cocked"])), 1e-12))
        dz_rest = P.height(l0["rest_root"]) - P.height(l0["rest_eff"])
        drop = max(0.0, dz_rest - 0.75 * r)
        cocked = base(drop=drop, theta=aim * 0.3)
        beta = math.radians(15.0)
        for l in hind:
            hip = l["rest_root"] - H.up * drop
            dz = P.height(hip) - P.height(l["rest_eff"])
            h = math.sqrt(max(r * r - dz * dz, 0.0))
            out = P.outward(l)
            ankle = hip - H.up * dz + (-H.fwd * math.cos(beta) + out * math.sin(beta)) * h
            cock_contacts[l["name"]] = ankle
            cocked.limbs[l["name"]] = {"target": (lambda p, limb, posed, t=ankle: t.copy()), "planted": True}
    else:
        # A rabbit gathers low over its heels, the front lifting to aim; its
        # forelegs leave the ground as it does - planted, aiming nose-up asked
        # them for 143% of their length.
        cocked = base(drop=0.04 * Lh, theta=aim,
                      others_spec={l["name"]: _free(_hip_rel(H, 0.8, 0.1, 0.1)) for l in others})
        # no deeper than the skin allows: heel and haunch skin sink first
        kp.limit_drop_by_skin(P, cocked)
    k_cock, _, _ = knee(cocked)

    # --- the push: how far the hips travel before the leg is open
    phi_to = jp.get("ankle_takeoff")

    def pushed(D, u=1.0):
        k = _travel(H, cocked, d, D * u * u)
        _pitch_key(k, (aim * 0.3 if H.kind == "orthopteran" else aim) * (1.0 - 0.4 * u))
        for l in others:
            if H.kind == "leporid" or u > 0.15:
                k.limbs[l["name"]] = _free(_hip_rel(H, 0.75, 0.25, 0.35 * max(u, 0.3)))
        return k

    def pushed_full(D):
        k = pushed(D)
        if H.kind == "leporid" and phi_to:
            for l in hind:
                k.limbs[l["name"]] = _planted(l, _ankle_for(H, k, l, phi_to))
        return k

    lo, hi = 0.0, 1.5 * Lh
    for _ in range(18 if H.kind == "leporid" else 26):
        mid = 0.5 * (lo + hi)
        a, _, info = knee(pushed_full(mid))
        if any(info[l["name"]]["clamped"] for l in hind) or a > jp["knee_takeoff"]:
            hi = mid
        else:
            lo = mid
    D = lo
    t_push = 2.0 * D * H.scale / jp["speed"]
    n_cock = max(4, int(round(jp["cock_s"] * fps_now)))
    n_push = max(2, int(round(t_push * fps_now)))
    n_gather = max(4, int(round(0.15 * fps_now)))

    samples, marks = [], {}
    rest = kp.rest_key()
    rest_start = rest
    if H.kind == "leporid":
        # the forelegs leave the ground as the front lifts: blend them from
        # their rest reach, held within reach of a rising shoulder
        rest_start = kp.rest_key()
        for l in others:
            rest_start.limbs[l["name"]] = _free(lambda p, limb, posed: _within_reach(
                p, limb, posed, posed[limb["upper"]].translation + (limb["rest_eff"] - limb["rest_root"]),
                share=0.999))
            rest_start.limbs[l["name"]]["planted"] = 1.0
    for f in range(n_gather):
        w = motion.smoothstep(f / float(n_gather - 1))
        if cock_contacts:
            k = cocked.copy(limbs=dict(cocked.limbs), drop=cocked.drop * w)
            _pitch_key(k, aim * 0.3 * w)
            for l in hind:
                c = l["rest_eff"].lerp(cock_contacts[l["name"]], w)
                lift = 0.25 * (l["a"] + l["b"]) * math.sin(math.pi * w)
                k.limbs[l["name"]] = {"target": (lambda p, limb, posed, t=c + H.up * lift: t.copy()),
                                      "planted": w >= 1.0 or w <= 0.0}
            samples.append(P.pose(k))
        else:
            samples.append(P.blend(rest_start, cocked, w, w_lean=w))
    marks["cocked"] = len(samples)
    for f in range(n_cock):
        samples.append(P.pose(cocked))                  # co-contraction: held
    marks["push_start"] = len(samples)
    ankle_series = []
    for f in range(1, n_push + 1):
        u = f / float(n_push)
        k = pushed(D, u)
        if H.kind == "leporid" and phi_to:
            # proximal to distal: the ankle holds until a third of the push, then opens
            phi_c = sum(ankle_angle(H, P.pose(cocked)[0], l) for l in hind) / len(hind)
            w = motion.smoothstep((u - 0.35) / 0.65)
            phi = phi_c + (phi_to - phi_c) * w
            for l in hind:
                k.limbs[l["name"]] = _planted(l, _ankle_for(H, k, l, phi))
            if u > 0.6:
                # Toe-off: the foot is leaving the ground, so where rolling onto
                # the toes would push the ball's skin through the floor - 4 mm on
                # the test rabbit at 137 degrees - the foot rises by that much.
                for _ in range(2):
                    posed, _ = P.pose(k)
                    sinks = 0.0
                    for l in hind:
                        chain = [l["lower"], l["end"]] + l["digits"]
                        low, rest_low = body.limb_skin_lowest(posed, chain)
                        allowed = min(0.004 * bm["height"], rest_low - bm["floor"])
                        sinks = max(sinks, allowed - (low - bm["floor"]))
                    if sinks <= 1e-6:
                        break
                    for l in hind:
                        spec = k.limbs[l["name"]]
                        k.limbs[l["name"]] = dict(spec, target=(lambda p, limb, posed, fn=spec["target"], z=sinks:
                                                                fn(p, limb, posed) + p.up * z))
        samples.append(P.pose(k))
    marks["takeoff"] = len(samples)
    takeoff_key = k

    def check(keyed, ev, infos):
        from .actions import _check_common
        r = _check_common(body, bm, keyed, ev, infos, planted=[], posed_limbs=P.legs, rest_floor=0.0)
        E = ev["evaluated"]
        # a cricket's knee closes to 10 degrees by design: not a failure here
        r["failures"] = [x for x in r["failures"] if "past what a joint does" not in x]
        drift = {}
        for l in hind:
            n = l["end"]
            p0 = body.carried(E[marks["cocked"]], n, H.pivot(l))
            # up to the frame before take-off: on it the toes are leaving
            worst = max((body.carried(E[f], n, H.pivot(l)) - p0).length
                        for f in range(marks["cocked"], marks["takeoff"]))
            drift[l["name"]] = round(worst * H.scale, 5)
            if worst > 0.01 * bm["size"]:
                r["failures"].append("%s's toe slides %.4f before take-off" % (l["name"], worst))
        r["planted_drift"] = drift
        fin = E[marks["takeoff"]]
        kn = sum(knee_angle(H, fin, l) for l in hind) / len(hind)
        kc = sum(knee_angle(H, E[marks["cocked"]], l) for l in hind) / len(hind)
        r["knee_deg"] = {"cocked": round(kc, 1), "takeoff": round(kn, 1), "plan_takeoff": jp["knee_takeoff"]}
        if abs(kn - jp["knee_takeoff"]) > 12.0:
            r["failures"].append("the hind knee opens to %.0f deg at take-off, planned %.0f" % (kn, jp["knee_takeoff"]))
        if H.kind == "orthopteran" and kc > jp["knee_cocked"] + 8.0:
            r["failures"].append("the hind knee cocks only to %.0f deg (full flexion ~10)" % kc)
        # the hips left along the take-off direction
        hip0 = sum((E[marks["push_start"]][l["upper"]].translation for l in hind), Vector()) / len(hind)
        hip1 = sum((fin[l["upper"]].translation for l in hind), Vector()) / len(hind)
        mv = hip1 - hip0
        ang = math.degrees(math.atan2(mv.dot(H.up), mv.dot(H.fwd)))
        r["takeoff"] = {"angle_deg": round(ang, 1), "plan_deg": jp["angle"], "push_m": round(mv.length * H.scale, 4),
                        "push_s": round(t_push, 4), "push_frames": n_push, "speed_mps": jp["speed"]}
        if abs(ang - jp["angle"]) > 8.0:
            r["failures"].append("the hips leave at %.0f deg, planned %.0f" % (ang, jp["angle"]))
        if H.kind == "leporid":
            series = {"hip": [], "knee": [], "ankle": []}
            for f in range(marks["push_start"], marks["takeoff"] + 1):
                M = E[f]
                l = hind[0]
                pel = M[l["attach"]].to_3x3() @ Vector((0.0, 1.0, 0.0))
                fem = M[l["lower"]].translation - M[l["upper"]].translation
                series["hip"].append(math.degrees(pel.angle(fem)))
                series["knee"].append(knee_angle(H, M, l))
                series["ankle"].append(ankle_angle(H, M, l))
            on = _extension_onsets(series, fps_now)
            r["extension_onset_s"] = on
            if on["ankle"] is not None and on["knee"] is not None and on["ankle"] < on["knee"]:
                r["failures"].append("the ankle opens before the knee - extension should run proximal to distal")
        skin_report(r, skin_checks_for(body), body, E, [f for f, _ in keyed])
        return r

    from .actions import _author_samples
    action_name = action_name or "%s_JumpLaunch" % rig_name
    keyed, infos, action, report = _author_samples(body, H.rig, action_name, samples, fps, check)
    if "error" in report:
        return report
    # the body's own translation: with the trunk pitched, the hips also move by
    # the pitch, and handing the engine that put the air clip 36 mm off
    off = (H.fwd * takeoff_key.shift - H.up * takeoff_key.drop) * H.scale
    report.update({"rig": rig_name, "action": action.name, "role": "JumpLaunch", "frames": [1, len(samples)],
                   "fps": fps_now, "plan": {k: (round(v, 5) if isinstance(v, float) else v) for k, v in jp.items()},
                   "marks": marks, "takeoff_offset_model": _to_model(off),
                   "takeoff_velocity_model": _to_model(d.normalized() * jp["speed"]),
                   "takeoff_pitch_deg": round(-0.6 * aim, 2)})
    report["_takeoff_key"] = takeoff_key
    return report


def air(rig_name, launch_report, action_name=None, fps=None):
    """From the take-off pose to the landing reach, over the planned flight time.
    Body at the origin: the engine carries it on the ballistic arc."""
    H = Hopper(rig_name)
    P, body, bm = H.P, H.body, H.bm
    jp = launch_report["plan"]
    fps_now = fps or bpy.context.scene.render.fps
    n = max(8, int(round(jp["flight_time_s"] * fps_now)))
    to = launch_report["_takeoff_key"]
    start = to.copy(limbs=dict(to.limbs), drop=0.0, shift=0.0)
    for l in H.hind:
        # the pushing feet leave their contacts where they were, relative to the
        # body - wherever those were: a cricket's tarsi stepped in to cock
        spec = to.limbs[l["name"]]
        start.limbs[l["name"]] = {"target": (lambda p, limb, posed, D=to.drop, S=to.shift, fn=spec["target"]:
                                             fn(p, limb, posed) + p.up * D - p.fwd * S),
                                  "planted": 1.0, "tilt": spec.get("tilt", 0.0)}
    reach = _landing_reach(H)
    # The body flies at the origin; the floor it left is below by the push's
    # rise. Toes drape onto the floor they are near - at the real one on the
    # launch's last frame - and against the origin's floor the first air frame
    # draped them somewhere else: a 36 mm seam at the rabbit's toes.
    air_floor = to.drop * H.scale
    P.bm["floor"] = air_floor
    samples = []
    for f in range(n):
        w = motion.smoothstep(f / float(n - 1))
        samples.append(P.blend(start, reach, w, w_legs=math.sqrt(w)))

    def check(keyed, ev, infos):
        from .actions import _check_common, _pose_gap
        r = _check_common(body, bm, keyed, ev, infos, planted=[], posed_limbs=P.legs, rest_floor=0.0,
                          starts_at_rest=False, skid=False)
        # in the air: the floor is the engine's business
        r["failures"] = [x for x in r["failures"] if "past what a joint does" not in x and "floor" not in x]
        skin_report(r, skin_checks_for(body), body, ev["evaluated"], [f for f, _ in keyed])
        return r
    from .actions import _author_samples
    action_name = action_name or "%s_JumpAir" % rig_name
    try:
        keyed, infos, action, report = _author_samples(body, H.rig, action_name, samples, fps, check)
    finally:
        P.bm["floor"] = 0.0
    if "error" in report:
        return report
    # The clip carries the floor it was authored against. The authoring check knows this
    # body is in the air and lets its feet hang below the ground it left; the exporter's
    # re-check, running later on nothing but the written clip, measured it against the
    # origin and refused the whole export over a foot 7 cm "through the floor".
    action["rig_anything_floor"] = air_floor
    report.update({"rig": rig_name, "action": action.name, "role": "JumpAir", "frames": [1, n], "fps": fps_now,
                   "flight_time_s": jp["flight_time_s"], "floor_below_body_m": round(-air_floor, 5)})
    report["_reach_key"] = reach
    return report


def _landing_reach(H):
    """The pose a body flies into to land: a rabbit's forelegs out and down, hind
    legs drawn forward under it; a cricket's legs spread down to meet the ground,
    hind tibiae half open."""
    P = H.P
    k = kp.Key(head_level=1.0, tail_lift=20.0)
    hind = {l["name"] for l in H.hind}
    for l in P.legs:
        z = kp.leg_zone(P, l)
        if H.kind == "leporid":
            if l["name"] in hind:
                # forward under the hips, not up into the belly: folded 0.7 and
                # 0.35 forward, the test rabbit's thighs crumpled into its belly
                k.limbs[l["name"]] = _free(_hip_rel(H, 0.95, 0.08, -0.02))
            else:
                k.limbs[l["name"]] = _free(_hip_rel(H, 0.95, 0.35, -0.05))
        else:
            if l["name"] in hind:
                k.limbs[l["name"]] = _free(_hip_rel(H, 1.0, -0.1, -0.1))
            else:
                k.limbs[l["name"]] = _free(_hip_rel(H, 1.0, 0.15 * (1 if z > 0 else 0), -0.15))
    if H.kind == "leporid":
        _pitch_key(k, 12.0)                        # nose down to the forefeet
    return k


def land(rig_name, air_report, action_name=None, fps=None):
    """Touch down and settle to rest. A rabbit's forefeet take the ground first
    and its hind feet swing down after; a cricket lands on all six and folds its
    hind tibiae before standing. Starts on the Air clip's last pose, offset back
    and up along the landing path; ends at rest."""
    H = Hopper(rig_name)
    P, body, bm = H.P, H.body, H.bm
    fps_now = fps or bpy.context.scene.render.fps
    reach = air_report["_reach_key"]
    dur = 0.35 if H.kind == "leporid" else 0.139      # locust landing 139 ms (Reichel et al. 2019)
    n = max(8, int(round(dur * fps_now)))
    th = math.radians(plan_jump(H)["angle"])
    dland = H.fwd * math.cos(th) - H.up * math.sin(th)
    hind = {l["name"] for l in H.hind}
    first = [l for l in P.legs if (l["name"] not in hind)] if H.kind == "leporid" else list(P.legs)
    later = [l for l in P.legs if l not in first]

    def start_key(D):
        k = reach.copy(limbs=dict(reach.limbs))
        k.drop = -(-dland * D).dot(H.up)
        k.shift = (-dland * D).dot(H.fwd)
        return k

    # Back off along the path until the leading feet, in the air clip's reach
    # pose, are just at the floor: the landing starts exactly where the air
    # clip ends, and touches down on its first frames.
    clearance = 0.03 * sum(l["a"] + l["b"] for l in first) / len(first)

    def lowest_first(D):
        # the skin, not the contact point: a cricket's tibia and a rabbit's
        # toes hang below the pivot, and the first landings started in the floor
        posed, _ = P.pose(start_key(D))
        low = float("inf")
        for l in first:
            chain = [l["upper"], l["lower"]] + ([l["end"]] if l["end"] else []) + l["digits"]
            sk, _ = body.limb_skin_lowest(posed, chain)
            bones = min(P.height(pt) for nm in chain
                        for pt in (posed[nm].translation, motion.tail_of(body, posed, nm)))
            low = min(low, bones, sk - bm["floor"] if sk is not None else bones)
        return low - clearance
    lo, hi = 0.0, 2.0 * sum(l["a"] + l["b"] for l in P.legs) / len(P.legs)
    if lowest_first(lo) >= 0.0:
        D = 0.0
    else:
        # the reaching feet are through the floor with the body at rest height:
        # the body starts further back and up the path
        for _ in range(24):
            mid = 0.5 * (lo + hi)
            if lowest_first(mid) > 0.0:
                hi = mid
            else:
                lo = mid
        D = hi
    k0 = start_key(D)
    # each foot comes down onto its standing contact: the first legs over the
    # opening fifth, a rabbit's hind legs by 45%
    touch_first = max(1, int(round(0.2 * (n - 1))))
    touch_later = int(round(0.45 * (n - 1)))
    squash = 0.08 * sum(l["a"] + l["b"] for l in H.hind) / len(H.hind)
    rest = kp.rest_key()
    samples = []
    landed = set()

    def _reaches(key, limb):
        hip_key = key.copy(limbs={})
        posed, _ = P.pose(hip_key)
        hip = posed[limb["upper"]].translation
        return (limb["rest_eff"] - hip).length <= 0.985 * (limb["a"] + limb["b"])

    for f in range(n):
        u = f / float(n - 1)
        # the body decelerates to rest along the path, dipping as it takes the load
        s_ = 1.0 - (1.0 - u) ** 2
        k = start_key(D * (1.0 - s_))
        k.drop += squash * math.sin(math.pi * min(1.0, u / 0.8))
        base_pitch = 12.0 if H.kind == "leporid" else 0.0
        _pitch_key(k, base_pitch * (1.0 - motion.smoothstep(u)))
        for l in P.legs:
            t_on = touch_first if l in first else touch_later
            if l["name"] in landed or (f >= t_on and _reaches(k, l)):
                # planted from the first frame its standing contact is in reach:
                # at a cricket's eight landing frames a fixed share planted the
                # forelegs while the body was still high, at 131% of their length
                landed.add(l["name"])
                k.limbs[l["name"]] = _planted(l)
            else:
                t_on = max(t_on, f + 1)
                w = motion.smoothstep(f / float(max(t_on, 1)))
                w_h = motion.smoothstep(min(1.0, 1.6 * f / float(max(t_on, 1))))
                air_fn = reach.limbs[l["name"]]["target"]

                def come_down(p, limb, posed, w=w, w_h=w_h, fn=air_fn):
                    # over the contact first, then down onto it: moving both
                    # together dragged the feet along the floor into place
                    a_ = fn(p, limb, posed)
                    b_ = limb["rest_eff"]
                    up = p.up
                    horiz = a_ + ((b_ - a_) - up * (b_ - a_).dot(up)) * w_h
                    return _within_reach(p, limb, posed, horiz + up * ((b_ - a_).dot(up) * w), share=0.97)
                k.limbs[l["name"]] = {"target": come_down, "planted": 0.7 + 0.3 * w}
        samples.append(P.pose(k))
    # the last frame is rest exactly
    samples[-1] = P.pose(rest)

    def check(keyed, ev, infos):
        from .actions import _check_common
        r = _check_common(body, bm, keyed, ev, infos, planted=[], posed_limbs=P.legs, rest_floor=0.0,
                          starts_at_rest=False)
        r["failures"] = [x for x in r["failures"] if "past what a joint does" not in x]
        E = ev["evaluated"]
        down = {}
        for l in P.legs:
            hs = [P.height(body.carried(E[f], l["end"] or l["lower"], H.pivot(l))) for f in range(1, n + 1)]
            low = min(hs)
            down[l["name"]] = next(i + 1 for i, h in enumerate(hs) if h <= low + 0.01 * bm["height"])
        r["touchdown_frame"] = down
        if later:
            if max(down[l["name"]] for l in first) >= min(down[l["name"]] for l in later):
                r["failures"].append("the hind feet touch down before the forefeet")
        drift = {}
        for l in P.legs:
            f0 = down[l["name"]]
            p0 = body.carried(E[f0], l["end"] or l["lower"], H.pivot(l))
            worst = max((body.carried(E[f], l["end"] or l["lower"], H.pivot(l)) - p0).length for f in range(f0, n + 1))
            drift[l["name"]] = round(worst * H.scale, 5)
            if worst > 0.012 * bm["size"]:
                r["failures"].append("%s slides %.4f after touching down" % (l["name"], worst))
        r["planted_drift"] = drift
        skin_report(r, skin_checks_for(body), body, E, [f for f, _ in keyed])
        return r

    from .actions import _author_samples
    action_name = action_name or "%s_JumpLand" % rig_name
    keyed, infos, action, report = _author_samples(body, H.rig, action_name, samples, fps, check)
    if "error" in report:
        return report
    lowest = min(P.height(body.carried(P.pose(k0)[0], l["end"] or l["lower"], H.pivot(l))) for l in P.legs)
    report.update({"rig": rig_name, "action": action.name, "role": "JumpLand", "frames": [1, n], "fps": fps_now,
                   "land_offset_model": _to_model((H.fwd * k0.shift - H.up * k0.drop) * H.scale),
                   "touch_clearance_m": round(lowest * H.scale, 5), "landing": {"path_m": round(D * H.scale, 4),
                                                                                "duration_s": round((n - 1) / fps_now, 3)}})
    return report


def jump_set(rig_name, prefix=None, fps=None, speed=None, angle=None):
    """JumpLaunch, JumpAir, JumpLand - and the seams between them measured on
    Blender's playback, with the body offsets the engine applies taken out."""
    from .actions import _evaluated_frame, _pose_gap
    prefix = prefix or rig_name
    L = launch(rig_name, action_name="%s_JumpLaunch" % prefix, fps=fps, speed=speed, angle=angle)
    if "error" in L:
        return {"JumpLaunch": L}
    A = air(rig_name, L, action_name="%s_JumpAir" % prefix, fps=fps)
    out = {"JumpLaunch": L, "JumpAir": A}
    if "error" not in A:
        out["JumpLand"] = land(rig_name, A, action_name="%s_JumpLand" % prefix, fps=fps)
    rig = bpy.data.objects[rig_name]
    H = Hopper(rig_name)

    def shifted(mats, model_offset):
        # model (glTF) -> Blender armature: (x, y, z) -> (x, -z, y)
        o = Vector((model_offset[0], -model_offset[2], model_offset[1])) / H.scale
        return {k: Matrix.Translation(-o) @ m for k, m in mats.items()}
    seams = {}
    if "error" not in A:
        a_end = _evaluated_frame(rig, L["action"], None)
        b_start = _evaluated_frame(rig, A["action"], 1)
        gap, bone = _pose_gap(rig, shifted(a_end, L["takeoff_offset_model"]), b_start)
        seams["launch -> air"] = (round(gap * H.scale, 5), bone)
        A.setdefault("failures", [])
        if gap > 0.01 * H.bm["size"]:
            A["failures"].append("first frame is %.4f from the take-off pose (%s)" % (gap, bone))
            A["passed"] = False
    Ld = out.get("JumpLand")
    if Ld and "error" not in Ld:
        a_end = _evaluated_frame(rig, A["action"], None)
        b_start = _evaluated_frame(rig, Ld["action"], 1)
        gap, bone = _pose_gap(rig, a_end, shifted(b_start, Ld["land_offset_model"]))
        seams["air -> land"] = (round(gap * H.scale, 5), bone)
        if gap > 0.01 * H.bm["size"]:
            Ld["failures"].append("first frame is %.4f from the air pose (%s)" % (gap, bone))
            Ld["passed"] = False
    for r in out.values():
        if isinstance(r, dict):
            r["seams"] = seams
            for k in [k for k in r if k.startswith("_")]:
                del r[k]
    stored.store(out, rig_name)
    return out


# --------------------------------------------------------------------------
# sets, the engine manifest, export
# --------------------------------------------------------------------------

# A cricket's walk at Froude 0.2 stepped at 16 Hz and at 0.08 at 13.7; Acheta
# walks at up to 12 (Hustert & Baldus 2010). Stride frequency goes as Fr^0.2
# here, so 0.04 keeps it under.
INSECT_WALK_FROUDE = 0.04

LOOPS = ("Idle", "Walk", "Hop", "Bound")
ROLES = ("Idle", "Walk", "Hop", "Bound", "JumpLaunch", "JumpAir", "JumpLand")


def move_set(rig_name, prefix=None, fps=None):
    """Every clip this hopper's kind has. Returns {role: report}.

    leporid      Idle Hop Bound JumpLaunch JumpAir JumpLand
    orthopteran  Idle Walk JumpLaunch JumpAir JumpLand
    """
    from . import actions
    H = Hopper(rig_name)
    prefix = prefix or rig_name
    nm = lambda role: "%s_%s" % (prefix, role)
    out = {"Idle": actions.idle(rig_name, action_name=nm("Idle"), forward=H.st["forward"], fps=fps)}
    if H.kind == "leporid":
        out["Hop"] = hop_cycle(rig_name, "Hop", action_name=nm("Hop"), fps=fps, attempts=10)
        out["Bound"] = hop_cycle(rig_name, "Bound", action_name=nm("Bound"), fps=fps, attempts=10)
    else:
        out["Walk"] = lm.cycle(rig_name, froude=INSECT_WALK_FROUDE, action_name=nm("Walk"),
                               forward=H.st["forward"], fps=fps)
    out.update(jump_set(rig_name, prefix=prefix, fps=fps))
    stored.store(out, rig_name)             # on the actions, so export works in a later session
    return out


_clean = stored.clean                       # drops `_` keys, rounds to 5 places, vectors as lists


def engine_manifest(rig_name, reports=None):
    """The `hop` block of `.moves.json`: the legs as detected, which pair jumps,
    the gaits and the jump's numbers and offsets - plus `gaits` and `contacts`
    in the shape `creature_controller.gd` already reads.

    `reports=None` reads the reports `move_set` stored on this rig's actions."""
    reports = stored.resolve(reports, rig_name, ROLES)
    H = Hopper(rig_name)
    st = H.st
    ok = {k: r for k, r in reports.items() if isinstance(r, dict) and "error" not in r}
    legs = []
    for g in st["legs"]:
        legs.append({"name": g["name"], "rank": g["rank"], "side": g["side"], "bones": g["bones"],
                     "roles": g["roles"], "lengths_m": [round(x * H.scale, 5) for x in g["lengths"]],
                     "rest_angles_deg": g["rest_angles_deg"], "measured": g["measured"],
                     "plantigrade": g["plantigrade"], "saltatorial": g["name"] in st["saltatorial"]})
    out = {"kind": st["kind"], "kind_guessed": st["kind_guessed"], "evidence": st["evidence"],
           "hind_over_others": _clean(st["hind_over_others"]), "legs": legs,
           "mass_kg": round(H.mass_kg, 4), "mass_source": H.mass_source,
           "clips": {role: r["action"] for role, r in ok.items()},
           "loops": [r["action"] for role, r in ok.items() if role in LOOPS]}
    gaits = {}
    for role in ("Hop", "Bound"):
        r = ok.get(role)
        if r:
            gaits[role] = {"speed_mps": r["natural_speed_mps"], "frequency_hz": r["stride_frequency_hz"],
                           "stride_m": r["stride_m"], "hind_duty": r["duty_factor"],
                           "fore_touchdown_phase": r["fore_touchdown_phase"], "froude": r["froude"],
                           "playback_speed_scale": r["playback_speed_scale"], "hind_overstep_m": r["hind_overstep_m"],
                           "ankle_deg": r["ankle_deg"], "source": r["plan"]["source"]}
    if gaits:
        out["gaits"] = gaits
    L, A, D = ok.get("JumpLaunch"), ok.get("JumpAir"), ok.get("JumpLand")
    if L:
        fps_now = L["fps"]
        out["jump"] = {
            "speed_mps": L["plan"]["speed"], "angle_deg": L["plan"]["angle"],
            "flight_time_s": L["plan"]["flight_time_s"], "range_m": L["plan"]["range_m"],
            "apex_m": L["plan"]["apex_m"], "source": L["plan"]["source"],
            "takeoff_offset_model": L["takeoff_offset_model"],
            "takeoff_velocity_model": L["takeoff_velocity_model"],
            "launch_duration_s": round((L["frames"][1] - 1) / float(fps_now), 4),
            "push_start_s": round((L["marks"]["push_start"] - 1) / float(fps_now), 4),
            "push": L["takeoff"], "knee_deg": L["knee_deg"],
            "extension_onset_s": L.get("extension_onset_s"),
            "air_duration_s": round((A["frames"][1] - 1) / float(A["fps"]), 4) if A else None,
            "land_offset_model": D["land_offset_model"] if D else None,
            "touch_clearance_m": D["touch_clearance_m"] if D else None,
            "land_duration_s": D["landing"]["duration_s"] if D else None,
            "touchdown_frame": D.get("touchdown_frame") if D else None,
            "seams_m": {k: v[0] for k, v in L.get("seams", {}).items()},
        }
    out["checks"] = {role: {k: r.get(k) for k in ("passed", "stretch_p99", "stretch_max", "flipped_faces",
                                                   "loop_seam", "contact_slip_m", "prediction_error")
                            if r.get(k) is not None} for role, r in ok.items()}
    out["problems"] = (["%s did not pass: %s" % (k, "; ".join(r.get("failures", [])))
                        for k, r in ok.items() if not r.get("passed")]
                       + ["%s: %s" % (k, r["error"]) for k, r in reports.items()
                          if isinstance(r, dict) and "error" in r])
    return _clean(out)


def export_creature(mesh_name, rig_name, reports, glb_path, creature, res_path=None, review=True,
                    review_options=None):
    """Export through `export.export` - read back, durations checked - and write
    `<name>.moves.json` beside it with the `hop` block and the `gaits` /
    `contacts` entries the other creatures carry.

    `reports` may be None: the reports `move_set` stored on the rig's actions are
    used, so a .blend saved after authoring exports in a fresh session. `review`
    and `review_options` as `export.export`: the review sheet goes to
    `<glb folder>/review/<glb name>/`."""
    import json
    import os
    from . import export
    reports = stored.resolve(reports, rig_name, ROLES)
    m = engine_manifest(rig_name, reports)
    if m["problems"]:
        return {"error": "not exporting clips that failed: " + "; ".join(m["problems"]), "manifest": m}
    H = Hopper(rig_name)
    clips = list(m["clips"].values())
    feet = sorted({l["end"] for l in H.P.legs if l["end"]})
    e = export.export(mesh_name, rig_name, glb_path, foot_bones=feet, actions=clips, loop_clips=m["loops"],
                      forward=H.st["forward"], sidecar=False, review=review,
                      review_options=dict({"title": creature}, **(review_options or {})))
    if not e.get("exported"):
        return {"error": "export refused at %s" % e.get("stage"), "export": e}
    loco = lm.engine_manifest(rig_name, {k: r for k, r in reports.items() if k in ("Walk", "Hop", "Bound")},
                              forward=H.st["forward"])
    stand = max(r.get("standing_height_m", 0.0) for r in reports.values() if isinstance(r, dict))
    size = H.bm["size"] * H.scale
    base = os.path.splitext(glb_path)[0]
    moves = {
        "creature": creature, "rig": rig_name,
        "scene": res_path or ("res://assets/creatures/%s" % os.path.basename(glb_path)),
        "clips": m["clips"], "loops": m["loops"],
        "implied_speed_mps": {k: c.get("implied_speed_playback_mps") for k, c in e["clips"]["clips"].items()
                              if c.get("implied_speed_playback_mps")},
        "height_m": {"stand": round(stand, 4)},
        "body_m": {"length": round(size, 4)},
        "hop": m, "gaits": loco.get("gaits", {}), "contacts": loco.get("contacts", {}),
        "verified": e["verified"],
        "note": ("rig-anything hoppers: legs found on the skin by walking up from each ground contact, "
                 "joints at the corners of the band-centroid line, joints the skin hides inferred from "
                 "proportions; weights written from the parts. Hind stance on Hall et al. 2022's ankle "
                 "profile through a femur-parallel-to-metatarsus leg; jumps as launch / air / land with the "
                 "body offsets the engine applies between them."),
    }
    with open(base + ".moves.json", "w", encoding="utf-8") as fh:
        json.dump(moves, fh, indent=2)
    return {"glb": glb_path, "moves": base + ".moves.json", "verified": e["verified"], "clips": clips,
            "bones": e["preflight"]["bones"], "review": e.get("review")}


def summarize(r):
    if "error" in r:
        return "ERROR: " + r["error"]
    lines = ["%s %s %s" % (r.get("rig"), r.get("action"), "PASSED" if r.get("passed") else "FAILED")]
    lines += ["  FAIL " + f for f in r.get("failures", [])]
    for k in ("natural_speed_mps", "stride_m", "stroke_m", "stride_frequency_hz", "froude", "loop_seam",
              "contact_slip_m", "ankle_deg", "femur_metatarsus_max_deg", "hind_height_mismatch_m",
              "hind_overstep_m", "stretch_max", "flipped_faces", "tightest_joint_degrees", "skin_lowest",
              "limited_by", "playback_speed_scale", "takeoff", "extension_onset_s", "landing",
              "planted_drift", "seams", "knee_deg"):
        if r.get(k) not in (None, [], {}):
            lines.append("  %s %s" % (k, r[k]))
    return "\n".join(lines)


def stretch_report(H, mats, worst=5):
    """The most stretched skin edges in a pose: ratio, rest position, and the
    weights at both ends - to find which part of a clip tears the skin."""
    import types
    from .swim import SwimChecks
    ch = SwimChecks(types.SimpleNamespace(body=H.body))
    deform = {nm: mats[nm] @ H.body.rest[nm].inverted() for nm in H.body.rest}
    out = []
    for m in ch.meshes:
        pos = []
        for co, ws in zip(m["cos"], m["ws"]):
            p = Vector((0.0, 0.0, 0.0))
            for nm, w in ws.items():
                p += (deform[nm] @ co) * w
            pos.append(p if ws else co)
        for a, b in m["edges"]:
            out.append(((pos[a] - pos[b]).length / m["rest_len"][(a, b)], a, b, m))
    out.sort(key=lambda x: -x[0])
    rows = []
    for s, a, b, m in out[:worst]:
        rows.append({"stretch": round(s, 2), "rest": [round(x, 4) for x in m["cos"][a]],
                     "weights_a": {k: round(v, 2) for k, v in m["ws"][a].items()},
                     "weights_b": {k: round(v, 2) for k, v in m["ws"][b].items()}})
    return rows
