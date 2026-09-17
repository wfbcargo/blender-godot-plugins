"""Moves for radial bodies: a jellyfish pulses, a sea star glides on its tube
feet, a brittle star rows, an anemone sways and closes.

A walk comes from a Froude number, a swim from body length; these come from the
published kinematics of the animals themselves, scaled by the size `radial`
measured. Every number carries its source, and the ones that are design choices
say so.

MEDUSA - pulse (rowing or jetting)
----------------------------------

The bell's fineness f = height / diameter sorts the swimmers (Colin & Costello
2002): oblate bells (f < 0.5) ROW, shedding vortices at the margin; prolate bells
(f >~ 0.9) JET; between them jet-paddlers like Catostylus (f ~ 0.6).

    pulse rate        0.41 (D / 0.1 m)^-0.62 Hz - a fit through Aurelia ephyrae
                      (0.3 cm, 3.8 Hz), a 6 cm semaeostome (0.6 Hz), adult
                      Aurelia (13 cm, 0.24 Hz) and Cyanea (50 cm, 0.19 Hz)
    contraction       37% of the cycle rowing (32-42%), 34% Catostylus, 35% jetting
    coast             15% of a rowing cycle, held contracted (Cyanea: 2.0 s
                      contraction, 1.0 s coast, 2.4 s relaxation)
    margin in by      18% of its radius rowing (Aurelia ~12% from its 1.3x area
                      change, Catostylus 23%); 25% jetting - design
    distance / pulse  0.42 D rowing (6 cm semaeostome 1.5 cm/s at 0.6 Hz), 0.47 D
                      jet-paddling (Catostylus), 1.0 D jetting (design; Sarsia is
                      reported near 2 - one study)
    surge             51% of a cycle's distance in contraction, 37% relaxation,
                      11% coast (Catostylus) - handed to the engine as a curve
    turn              41 degrees per asymmetric pulse (Aurelia model - one study)

A bell swims ABORAL end first, along its axis. It steers by contracting one
side harder; which side is a free choice for a body with no front, so the Turn
clip is authored toward rib 01 and the engine spins the body about its own axis
to put that side where it wants - by a multiple of 360/order, which is invisible.

ASTEROID - tube feet
--------------------

A sea star crawls on ~1000 tube feet at ~1 mm/s (Asterias rubens, 0.98 mm/s on
glass, 1.12 on slate) with no leading arm: a direction is broadcast and every
foot steps toward it (Heydari et al. 2020). Faster, it BOUNCES: the disc rises
and falls at 0.14-0.40 Hz, frequency ~ mass^-0.14, feet never leaving the floor.
So Crawl is a bounce that goes nowhere in particular, and the engine slides the
body any way at all without turning it.

OPHIUROID - rowing
------------------

A brittle star picks an arm to lead; the two next to it row together, like a
breaststroke; the rest trail. A movement sequence takes ~2 s. It turns by
handing the lead to another arm - the disc does not rotate - and a quarter of
the time rows in reverse, one arm trailing (Astley 2012). So `Row` is authored
with arm01 leading and `RowBack` with arm01 trailing; to go any way the engine
picks whichever arm, forward or reversed, is nearest - never more than 180/2n
degrees off (18 for five arms) - and spins the body to it.

POLYP - sessile
---------------

An anemone does not travel. `Sway` is its tentacles moving in the water;
`Retract` folds them in over the mouth and `Extend` opens them again. Periods are
design numbers.
"""

from __future__ import annotations

import math
import types

import bpy
from mathutils import Matrix, Vector

from . import radial as rad
from . import stored

TAU = 2.0 * math.pi
FLESH = 1030.0          # kg/m3 - cnidarian and echinoderm tissue sits near seawater


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _ease(t):
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def _to_model(v):
    """Blender vector -> glTF / Godot model space (Y up, forward +Z for -Y)."""
    return [round(v.x, 5), round(v.z, 5), round(-v.y, 5)]


def _mass(rr, mass_kg):
    from .flight import mesh_volume
    vol, closed = mesh_volume(rr.rig)
    if mass_kg:
        return float(mass_kg), "given"
    return vol * FLESH, "skin volume x %.0f kg/m3%s" % (FLESH, "" if closed else " (mesh not closed)")


# --------------------------------------------------------------------------
# numbers
# --------------------------------------------------------------------------

def plan(rr, mass_kg=None):
    st = rr.st
    D = 2.0 * st["R_hub"]
    mass, mass_src = _mass(rr, mass_kg)
    out = {"kind": rr.kind, "order": rr.order, "diameter_m": D, "height_m": st["hub_height"],
           "fineness": st["fineness"], "mass_kg": mass, "mass_source": mass_src, "notes": []}
    if rr.kind == "medusa":
        f = st["fineness"]
        mode = "rowing" if f < 0.5 else ("jet-paddling" if f < 0.9 else "jetting")
        hz = 0.41 * (D / 0.1) ** -0.62
        if not (0.003 <= D <= 0.6):
            out["notes"].append("pulse-rate fit spans 0.3-50 cm bells; %.2f m is extrapolated" % D)
        share = {"rowing": 0.37, "jet-paddling": 0.34, "jetting": 0.35}[mode]
        coast = 0.15 if mode == "rowing" else 0.0
        contraction = {"rowing": 0.18, "jet-paddling": 0.23, "jetting": 0.25}[mode]
        per_pulse = {"rowing": 0.42, "jet-paddling": 0.47, "jetting": 1.0}[mode]
        stride = per_pulse * D
        relax = 1.0 - share - coast
        # distance shares -> speed multiplier per phase, normalised to mean 1
        dist = {"contraction": 0.51, "coast": 0.11 if coast else 0.0, "relaxation": 0.37}
        tot = sum(dist.values())
        surge = []
        for k in range(24):
            t = (k + 0.5) / 24.0
            if t < share:
                v = dist["contraction"] / tot / share
            elif t < share + coast:
                v = dist["coast"] / tot / coast
            else:
                v = dist["relaxation"] / tot / relax
            surge.append(round(v, 4))
        m = sum(surge) / len(surge)
        surge = [round(s / m, 4) for s in surge]
        out.update({"mode": mode, "pulse_hz": hz, "pulse_fast_hz": 2.0 * hz,
                    "contraction_share": share, "coast_share": coast, "relaxation_share": relax,
                    "margin_contraction": contraction, "stride_m": stride,
                    "cruise_speed_mps": stride * hz, "fast_speed_mps": stride * 2.0 * hz,
                    "surge": surge, "turn_deg_per_pulse": 41.0,
                    "sink_speed_mps": 0.05 * D,
                    "rib_bend_deg": rr.bend_for_contraction(contraction)})
        out["notes"].append("fast pulsing at 2x the rate and the sinking speed (0.05 D/s) are design numbers")
    elif rr.kind == "asteroid":
        # bounce 0.14-0.40 Hz ~ M^-0.14 over 54 animals (Heydari 2021); the mass
        # it is anchored at is an assumption: 0.27 Hz, mid-range, at 50 g
        hz = 0.27 * (max(mass, 1e-4) / 0.05) ** -0.14
        speed = 1.0e-3
        out.update({"mode": "tube_feet", "speed_mps": speed, "bounce_hz": hz,
                    "stride_m": speed / hz, "bounce_share_of_height": 0.12,
                    "heading_free": True})
        out["notes"].append("1 mm/s is Asterias rubens (one study); the bounce is anchored at 0.27 Hz for "
                            "50 g (assumed) and its height is a design number")
    elif rr.kind == "ophiuroid":
        hz = 0.5                   # a movement sequence ~2 s (Astley 2012)
        out.update({"mode": "rowing", "stroke_hz": hz, "power_share": 0.6, "sweep_deg": 28.0,
                    "recovery_lift_deg": 22.0, "reverse_share": 0.25})
        out["notes"].append("2 s per stroke is Ophiocoma echinata; sweep, lift and power share are design")
    else:
        out.update({"mode": "sessile", "sway_period_s": 4.0, "retract_s": 1.2})
        out["notes"].append("sway and retraction timings are design numbers")
    if rr.kind in ("asteroid", "ophiuroid") and isinstance(rr.order, int):
        out["heading_error_deg"] = 180.0 / (2 * rr.order) if rr.kind == "ophiuroid" else 0.0
    return out


def summarize_plan(p):
    lines = ["%s, %s-fold, %.3f m across, %.3f m tall (fineness %.2f), %.3f kg (%s)"
             % (p["kind"], p["order"], p["diameter_m"], p["height_m"], p["fineness"], p["mass_kg"],
                p["mass_source"])]
    if p["kind"] == "medusa":
        lines.append("%s: %.3f Hz pulse, %.0f%% contracting, %.0f%% coast; margin in %.0f%% (ribs bend %.1f deg)"
                     % (p["mode"], p["pulse_hz"], 100 * p["contraction_share"], 100 * p["coast_share"],
                        100 * p["margin_contraction"], p["rib_bend_deg"]))
        lines.append("%.3f m a pulse, cruise %.4f m/s (%.2f D/s), turn %.0f deg a pulse"
                     % (p["stride_m"], p["cruise_speed_mps"], p["cruise_speed_mps"] / p["diameter_m"],
                        p["turn_deg_per_pulse"]))
    elif p["kind"] == "asteroid":
        lines.append("tube feet: %.4f m/s, bounce %.3f Hz, any heading without turning"
                     % (p["speed_mps"], p["bounce_hz"]))
    elif p["kind"] == "ophiuroid":
        lines.append("rowing at %.2f Hz, sweep %.0f deg, heading error at most %.0f deg"
                     % (p["stroke_hz"], p["sweep_deg"], p.get("heading_error_deg", 0)))
    return "\n".join(lines + ["NOTE " + n for n in p["notes"]])


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def _skin_checks(rr):
    from .swim import SwimChecks
    return SwimChecks(types.SimpleNamespace(body=rr.body))


def _fourier_phase(values):
    n = len(values)
    mean = sum(values) / n
    re = sum((v - mean) * math.cos(TAU * k / n) for k, v in enumerate(values))
    im = sum((v - mean) * math.sin(TAU * k / n) for k, v in enumerate(values))
    return math.atan2(im, re)


def _check(rr, checks, keyed, ev, infos, loop, floats, stretch_limit=3.0):
    from .actions import _check_common, _pose_gap
    body, bm = rr.body, rr.bm
    r = _check_common(body, bm, keyed, ev, infos, planted=[], posed_limbs=[],
                      rest_floor=0.0, starts_at_rest=False)
    if floats:
        r["failures"] = [f for f in r["failures"] if "the floor" not in f]
    evaluated = ev["evaluated"]
    frames = [f for f, _ in keyed]
    use = frames[:-1] if loop else frames
    if loop:
        seam, bone = _pose_gap(body.rig, evaluated[frames[0]], evaluated[frames[-1]])
        r["loop_seam"] = round(seam, 6)
        if seam > 1e-4 * bm["size"]:
            r["failures"].append("loop seam %.5f on %s" % (seam, bone))
    _, rest_flips = checks.skin(body.fk())
    worst_s, worst_f, at = 1.0, 0, None
    for f in use[::max(1, len(use) // 12)]:
        s, fl = checks.skin(evaluated[f])
        worst_s = max(worst_s, s)
        if fl - rest_flips > worst_f:
            worst_f, at = fl - rest_flips, f
    r["stretch_max"] = round(worst_s, 3)
    r["flipped_faces"] = worst_f
    if worst_s > stretch_limit:
        r["failures"].append("skin stretches to %.1fx" % worst_s)
    if worst_f:
        r["failures"].append("%d faces turn inside out at frame %d" % (worst_f, at))
    return r, use, evaluated


def _author(rr, name, samples, fps, check):
    from .actions import _author_samples
    return _author_samples(rr.body, rr.rig, name, samples, fps, check)


def _finish(r, rr, action, frames, extra):
    if "error" in r:
        return r
    r.update({"rig": rr.rig.name, "action": action.name, "frames": [1, frames],
              "fps": bpy.context.scene.render.fps, "kind": rr.kind})
    r.update(extra)
    return r


# --------------------------------------------------------------------------
# medusa
# --------------------------------------------------------------------------

def _contraction(p, t):
    """Bell closure over one pulse, 0 relaxed to 1 contracted."""
    cs, co = p["contraction_share"], p["coast_share"]
    t = t % 1.0
    if t < cs:
        return _ease(t / cs)
    if t < cs + co:
        return 1.0
    return 1.0 - _ease((t - cs - co) / max(1.0 - cs - co, 1e-9))


def bell_pose(rr, p, t, tilt=0.0, psi=0.0, amp=1.0, fling=1.0):
    """The bell at phase t of a pulse: ribs bent by the contraction - harder on
    the side facing `psi` by `tilt` - tentacles drawn in behind the margin with a
    lag and a wave running down them, oral arms likewise, gentler."""
    rots = {}
    rib_of_tip, bend_of = {}, {}

    def rib_bend(rib, when):
        return p["rib_bend_deg"] * amp * _contraction(p, when) * max(0.0, 1.0 + tilt * math.cos(rib["theta"] - psi))
    for rib in rr.ribs:
        rr.rib_rots(rib, rib_bend(rib, t), rots)
        rib_of_tip[rib["bones"][-1]] = rib
    for ap in rr.apps:
        gentle = 0.5 if ap["role"] == "oral_arm" else 1.0
        lag = 0.12 if ap["role"] == "tentacle" else 0.2
        c = amp * _contraction(p, t - lag)
        n = len(ap["bones"])
        rib = rib_of_tip.get(ap["parent"])
        if rib is not None:
            # A tentacle HANGS from the margin; it is not a stiff extension of
            # the rib. Carried rigidly, an 18 degree rib bend swung a 0.43 m
            # tentacle's tip 13 cm in - its whole resting radius - and all eight
            # met under the bell. So the carried bend is undone at its root and
            # 15% of it given back LATE: undone at 85% in step with the rib, the
            # tips swung in ahead of the margin and led the pulse by 8 degrees.
            net = -rib_bend(rib, t) + 0.15 * rib_bend(rib, t - lag)
            undo = Matrix.Rotation(math.radians(net * rr.bell_sign), 3, rr.q(rib["theta"]))
            first = ap["bones"][0]
            rots[first] = undo @ rots[first] if first in rots else undo
        # drawn in toward the axis as the bell drives forward: - about q. At 14
        # degrees a 1.4 D tentacle met its opposite number under the bell and
        # they passed through each other, every number still passing.
        rr.chain_rots(ap, lift_deg=-5.0 * gentle * c * fling, rots=rots,
                      profile=[1.0 + 0.5 * k / max(n - 1, 1) for k in range(n)])
        rr.wave_rots(ap, t, 10.0 * gentle * amp * fling, wavelength=1.2, rots=rots)
    return rr.fk(rots)


def _margin(rr, mats):
    return rr.rim_radii(mats)


def _check_bell(rr, p, checks, keyed, ev, infos, loop, symmetric, tilt_psi=None):
    r, use, evaluated = _check(rr, checks, keyed, ev, infos, loop, floats=True)
    # Hanging appendages must not meet under the bell. Found in a render, not
    # a number: the first pulse drew its tentacles in until they crossed.
    hanging = [ap for ap in rr.apps if ap["role"] == "tentacle"]
    if hanging:
        rest_m = rr.body.fk()
        closest = min(rr.radius(evaluated[f], ap["bones"][-1]) / max(rr.radius(rest_m, ap["bones"][-1]), 1e-9)
                      for f in use for ap in hanging)
        r["tentacle_tip_radius_min"] = round(closest, 3)
        # 25%: the crossing pulse read 1.5%; a turn's hard side, with tips still
        # 7 cm apart across a 30 cm bell, reads 45%
        if closest < 0.25:
            r["failures"].append("tentacle tips close to %.0f%% of their resting radius - they meet "
                                 "under the bell" % (100 * closest))
    series = [_margin(rr, evaluated[f]) for f in use]
    means = [sum(x) / len(x) for x in series]
    rest = sum(_margin(rr, rr.body.fk())) / len(rr.ribs)
    frac = 1.0 - min(means) / rest
    r["margin_contraction"] = round(frac, 4)
    if symmetric:
        r["margin_contraction_plan"] = round(p["margin_contraction"], 4)
        if abs(frac - p["margin_contraction"]) > 0.15 * p["margin_contraction"]:
            r["failures"].append("the margin closes %.1f%%, planned %.1f%%"
                                 % (100 * frac, 100 * p["margin_contraction"]))
        spread = max((max(x) - min(x)) / rest for x in series)
        r["asymmetry"] = round(spread, 4)
        if spread > 0.02:
            r["failures"].append("the pulse is lopsided by %.1f%% of the radius - it would steer"
                                 % (100 * spread))
        k_min = min(range(len(means)), key=lambda k: means[k])
        duty = k_min / float(len(use))
        r["contraction_share"] = round(duty, 3)
        want = p["contraction_share"]
        if abs(duty - want) > max(1.5 / len(use), 0.1 * want) and abs(duty - (want + p["coast_share"])) > \
                max(1.5 / len(use), 0.1 * want) and not (want <= duty <= want + p["coast_share"]):
            r["failures"].append("the bell is fully closed at %.0f%% of the pulse, planned %.0f%%"
                                 % (100 * duty, 100 * want))
        # tentacles lag the margin: their tips reach furthest in after it does
        tents = rr.by_role("tentacle")
        if tents and loop:
            ph_m = _fourier_phase(means)
            tips = [sum(rr.radius(evaluated[f], ap["bones"][-1]) for ap in tents) / len(tents) for f in use]
            lag = math.degrees((_fourier_phase(tips) - ph_m + math.pi) % TAU - math.pi)
            r["tentacle_lag_deg"] = round(lag, 1)
            if lag <= 0.0:
                r["failures"].append("the tentacles lead the bell (%.0f deg) - they would pull it" % lag)
    if tilt_psi is not None:
        near = min(rr.ribs, key=lambda rb: abs(rad._wrap(rb["theta"] - tilt_psi)))
        far = min(rr.ribs, key=lambda rb: abs(rad._wrap(rb["theta"] - tilt_psi - math.pi)))
        i_n, i_f = rr.ribs.index(near), rr.ribs.index(far)
        cn = 1.0 - min(x[i_n] for x in series) / (rest or 1.0)
        cf = 1.0 - min(x[i_f] for x in series) / (rest or 1.0)
        r["turn_side_closes"], r["far_side_closes"] = round(cn, 4), round(cf, 4)
        if cn <= cf + 0.03:
            r["failures"].append("the turning side closes %.1f%%, the far side %.1f%% - no turn"
                                 % (100 * cn, 100 * cf))
    return r


def pulse(rig_name, frames=48, action_name="Pulse", fps=None, mass_kg=None):
    """One looping pulse. Authored over `frames` and played by the engine at
    `playback_speed_scale` to beat at the planned rate."""
    rr = rad.RadialRig(rig_name)
    if rr.kind != "medusa":
        return {"error": "%s is a %s, not a bell" % (rig_name, rr.kind)}
    p = plan(rr, mass_kg)
    fps_now = fps or bpy.context.scene.render.fps
    n = int(frames)
    samples = [(bell_pose(rr, p, (k - 1) / float(n)), {}) for k in range(1, n + 2)]
    checks = _skin_checks(rr)
    _, _, action, r = _author(rr, action_name, samples, fps,
                              lambda keyed, ev, infos: _check_bell(rr, p, checks, keyed, ev, infos,
                                                                   loop=True, symmetric=True))
    duration = (n + 1) / float(fps_now)
    return _finish(r, rr, action, n + 1, {
        "role": "Pulse", "plan": _round(p), "pulse_hz": round(p["pulse_hz"], 4),
        "playback_speed_scale": round(p["pulse_hz"] * duration, 4)})


def drift(rig_name, frames=72, action_name="Drift", fps=None):
    """Hanging in the water between pulses: the bell barely breathing, the
    tentacles swaying."""
    rr = rad.RadialRig(rig_name)
    if rr.kind != "medusa":
        return {"error": "%s is a %s, not a bell" % (rig_name, rr.kind)}
    p = plan(rr)
    soft = dict(p, contraction_share=0.5, coast_share=0.0)
    n = int(frames)
    samples = [(bell_pose(rr, soft, (k - 1) / float(n), amp=0.2, fling=0.5), {}) for k in range(1, n + 2)]
    checks = _skin_checks(rr)
    _, _, action, r = _author(rr, action_name, samples, fps,
                              lambda keyed, ev, infos: _check_bell(rr, p, checks, keyed, ev, infos,
                                                                   loop=True, symmetric=False))
    return _finish(r, rr, action, n + 1, {"role": "Drift"})


def turn_pulse(rig_name, frames=48, action_name="Turn", fps=None, tilt=0.7):
    """One pulse closing harder on the side toward rib 01 (angle 0). The engine
    spins the body to face that side where it wants to go, then turns its axis
    by `turn_deg` over the clip."""
    rr = rad.RadialRig(rig_name)
    if rr.kind != "medusa":
        return {"error": "%s is a %s, not a bell" % (rig_name, rr.kind)}
    p = plan(rr)
    fps_now = fps or bpy.context.scene.render.fps
    psi = rr.ribs[0]["theta"]
    n = int(frames)
    # capped so the hard side stays within 1.35x a plain pulse's bend
    k_tilt = min(tilt, 0.35)
    samples = [(bell_pose(rr, p, (k - 1) / float(n), tilt=k_tilt, psi=psi), {}) for k in range(1, n + 1)]
    checks = _skin_checks(rr)
    _, _, action, r = _author(rr, action_name, samples, fps,
                              lambda keyed, ev, infos: _check_bell(rr, p, checks, keyed, ev, infos,
                                                                   loop=False, symmetric=False, tilt_psi=psi))
    duration = (n - 1) / float(fps_now)
    return _finish(r, rr, action, n, {"role": "Turn", "turn_deg": p["turn_deg_per_pulse"],
                                      "toward_theta_deg": round(math.degrees(psi), 3),
                                      "playback_speed_scale": round(p["pulse_hz"] * duration, 4)})


# --------------------------------------------------------------------------
# asteroid
# --------------------------------------------------------------------------

def _arm_reach(rr, ap):
    b0 = rr.rig.data.bones[ap["bones"][0]]
    b1 = rr.rig.data.bones[ap["bones"][-1]]
    d = b1.tail_local - b0.head_local
    return (d - rr.a * d.dot(rr.a)).length


def crawl(rig_name, frames=None, action_name="Crawl", fps=None, mass_kg=None):
    """One bounce of a sea star's tube-foot crawl: the disc rises and settles,
    the arms stay down and bend at the root to keep their tips on the floor."""
    rr = rad.RadialRig(rig_name)
    if rr.kind != "asteroid":
        return {"error": "%s is a %s, not a sea star" % (rig_name, rr.kind)}
    p = plan(rr, mass_kg)
    fps_now = fps or bpy.context.scene.render.fps
    n = int(frames or 48)
    bob_h = p["bounce_share_of_height"] * rr.st["hub_height"]
    from .motion import tail_of
    rest = rr.body.fk()
    tip_rest = {ap["name"]: tail_of(rr.body, rest, ap["bones"][-1]).dot(rr.a) for ap in rr.apps}

    def arm_rots(ap, ang, rots):
        # pressed down at the root, easing back along the arm so the tip lies flat
        nb = len(ap["bones"])
        rr.chain_rots(ap, lift_deg=-ang, rots=rots, profile=[1.0] + [0.0] * (nb - 1))
        if nb > 1:
            rr.chain_rots(ap, lift_deg=0.5 * ang, rots=rots, profile=[0.0] + [1.0] * (nb - 1))
        return rots

    samples = []
    solved = {}
    for k in range(1, n + 2):
        t = (k - 1) / float(n)
        bob = bob_h * (0.5 - 0.5 * math.cos(TAU * t))
        root = Matrix.Translation(rr.a * bob)
        rots = {}
        for ap in rr.apps:
            # Solved, not estimated: asin(bob / reach) with a fixed counter-bend
            # left the tips 1.2 mm up on a 3.8 mm bounce.
            key = (ap["name"], round(bob, 9))
            if key not in solved:
                lo, hi = 0.0, 40.0
                for _ in range(22):
                    mid = 0.5 * (lo + hi)
                    m = rr.fk(arm_rots(ap, mid, {}), root=root)
                    if tail_of(rr.body, m, ap["bones"][-1]).dot(rr.a) > tip_rest[ap["name"]]:
                        lo = mid
                    else:
                        hi = mid
                solved[key] = 0.5 * (lo + hi)
            arm_rots(ap, solved[key], rots)
        samples.append((rr.fk(rots, root=root), {}))
    checks = _skin_checks(rr)

    def check(keyed, ev, infos):
        r, use, evaluated = _check(rr, checks, keyed, ev, infos, loop=True, floats=False)
        from .motion import tail_of
        drift = 0.0
        for ap in rr.apps:
            z0 = tail_of(rr.body, rr.body.fk(), ap["bones"][-1]).dot(rr.a)
            for f in use:
                drift = max(drift, abs(tail_of(rr.body, evaluated[f], ap["bones"][-1]).dot(rr.a) - z0))
        r["arm_tip_lift_m"] = round(drift, 5)
        if drift > 0.25 * bob_h + 1e-4:
            r["failures"].append("arm tips leave the floor by %.4f while the disc bounces %.4f" % (drift, bob_h))
        r["bounce_m"] = round(bob_h, 5)
        return r
    _, _, action, r = _author(rr, action_name, samples, fps, check)
    duration = (n + 1) / float(fps_now)
    return _finish(r, rr, action, n + 1, {"role": "Crawl", "plan": _round(p),
                                          "playback_speed_scale": round(p["bounce_hz"] * duration, 4)})


def star_idle(rig_name, frames=96, action_name="Idle", fps=None):
    """Arm tips lifting and settling in turn round the body."""
    rr = rad.RadialRig(rig_name)
    if rr.kind not in ("asteroid", "ophiuroid"):
        return {"error": "%s is a %s, not a star" % (rig_name, rr.kind)}
    n = int(frames)
    samples = []
    arms = sorted(rr.apps, key=lambda ap: ap["theta"] % TAU)
    for k in range(1, n + 2):
        t = (k - 1) / float(n)
        rots = {}
        for j, ap in enumerate(arms):
            nb = len(ap["bones"])
            lift = 9.0 * (0.5 - 0.5 * math.cos(TAU * (t - j / float(len(arms)))))
            rr.chain_rots(ap, lift_deg=lift, rots=rots,
                          profile=[0.0] * (nb // 2) + [1.0] * (nb - nb // 2))
        samples.append((rr.fk(rots), {}))
    checks = _skin_checks(rr)
    _, _, action, r = _author(rr, action_name, samples, fps,
                              lambda keyed, ev, infos: _check(rr, checks, keyed, ev, infos, loop=True,
                                                              floats=False)[0])
    return _finish(r, rr, action, n + 1, {"role": "Idle"})


# --------------------------------------------------------------------------
# ophiuroid
# --------------------------------------------------------------------------

def _row_roles(rr, heading, reverse):
    """Assign each arm its part for a heading: forward rowing has a lead arm
    and the pair either side of it rows; reversed, the pair nearest the heading
    rows and the arm opposite trails."""
    arms = sorted(rr.apps, key=lambda ap: abs(rad._wrap(ap["theta"] - heading)))
    roles = {}
    if reverse:
        for ap in arms[:2]:
            roles[ap["name"]] = "row"
        roles[arms[-1]["name"]] = "trail"
    else:
        roles[arms[0]["name"]] = "lead"
        for ap in arms[1:3]:
            roles[ap["name"]] = "row"
    for ap in arms:
        roles.setdefault(ap["name"], "follow")
    return roles


def row_pose(rr, p, t, heading, reverse=False):
    roles = _row_roles(rr, heading, reverse)
    rots = {}
    ps = p["power_share"]
    sweep, lift_max = p["sweep_deg"], p["recovery_lift_deg"]
    for ap in rr.apps:
        role = roles[ap["name"]]
        nb = len(ap["bones"])
        # rowing: root-heavy, the arm bending into an arc as it pulls
        prof = [2.0 * (nb - k) / nb for k in range(nb)]
        off = rad._wrap(ap["theta"] - heading)
        side = 1.0 if off >= 0.0 else -1.0     # + sweeps toward the rear
        if role == "row":
            # An arm swept round the body moves its tip along the circle, and
            # only sin(angle from the heading) of that is backward. Rowing from
            # 36 degrees off the heading - the front pair when rowing reversed -
            # pushed 1.6x as far sideways as back, so a rower near the heading
            # swings out to 75 degrees first and rows from there.
            splay = side * max(0.0, math.radians(75.0) - abs(off))
            base = math.degrees(splay)
            if t < ps:
                u = _ease(t / ps)
                s, lift = base + side * sweep * (2.0 * u - 1.0), 0.0
            else:
                u = _ease((t - ps) / (1.0 - ps))
                s, lift = base + side * sweep * (1.0 - 2.0 * u), lift_max * math.sin(math.pi * u)
            rr.chain_rots(ap, lift_deg=lift, sweep_deg=s, rots=rots, profile=prof)
        elif role == "lead":
            # probing: the tip lifts and swings a little
            rr.chain_rots(ap, lift_deg=6.0 + 4.0 * math.sin(TAU * t), rots=rots,
                          profile=[0.0] * (nb // 2) + [1.0] * (nb - nb // 2))
            rr.wave_rots(ap, t, 6.0, rots=rots, axis="a")
        else:
            # trailing arms are dragged: bent back a little, following the stroke
            s = side * 6.0 * math.sin(TAU * t)
            rr.chain_rots(ap, sweep_deg=s, rots=rots, profile=prof)
    return rr.fk(rots), roles


def _row(rig_name, reverse, frames, action_name, fps, mass_kg):
    rr = rad.RadialRig(rig_name)
    if rr.kind != "ophiuroid":
        return {"error": "%s is a %s, not a brittle star" % (rig_name, rr.kind)}
    p = plan(rr, mass_kg)
    fps_now = fps or bpy.context.scene.render.fps
    n = int(frames or 48)
    arm01 = min(rr.apps, key=lambda ap: ap["name"])
    heading = arm01["theta"] + (math.pi if reverse else 0.0)
    samples, roles = [], None
    for k in range(1, n + 2):
        mats, roles = row_pose(rr, p, (k - 1) / float(n), heading, reverse)
        samples.append((mats, {}))
    checks = _skin_checks(rr)
    hvec = rr.radial(heading)

    def check(keyed, ev, infos):
        from .motion import tail_of
        r, use, evaluated = _check(rr, checks, keyed, ev, infos, loop=True, floats=False)
        rowers = [ap for ap in rr.apps if roles[ap["name"]] == "row"]
        ps = p["power_share"]
        stance = [f for i, f in enumerate(use) if (i / float(len(use))) < ps]
        strokes, slips, lifts = [], [], []
        for ap in rowers:
            pts = [tail_of(rr.body, evaluated[f], ap["bones"][-1]) for f in stance]
            back = -(pts[-1] - pts[0]).dot(hvec)
            lat = hvec.cross(rr.a)
            side = abs((pts[-1] - pts[0]).dot(lat))
            strokes.append(back)
            slips.append(side / max(abs(back), 1e-9))
            z0 = tail_of(rr.body, rr.body.fk(), ap["bones"][-1]).dot(rr.a)
            lifts.append(max(abs(q.dot(rr.a) - z0) for q in pts))
        stride = sum(strokes) / len(strokes) if strokes else 0.0
        r["stride_m"] = round(stride, 5)
        r["stroke_slip"] = round(max(slips), 3) if slips else None
        r["stance_tip_lift_m"] = round(max(lifts), 5) if lifts else None
        if stride <= 0.0:
            r["failures"].append("the rowing arms sweep forward in their power stroke - it would row backward")
        # a sweep round the body moves the tip on an arc, so some sideways travel
        # is expected; the two rowers' cancels, but each must still push mostly back
        if slips and max(slips) > 1.2:
            r["failures"].append("a rowing arm's tip moves %.1fx as far sideways as back" % max(slips))
        tol = 0.02 * rr.bm["size"]
        if lifts and max(lifts) > tol:
            r["failures"].append("a rowing arm lifts %.4f off the floor during its power stroke" % max(lifts))
        return r
    _, _, action, r = _author(rr, action_name, samples, fps, check)
    if "error" in r:
        return r
    duration = (n + 1) / float(fps_now)
    stride = r.get("stride_m", 0.0)
    return _finish(r, rr, action, n + 1, {
        "role": "RowBack" if reverse else "Row", "plan": _round(p),
        "heading_theta_deg": round(math.degrees(heading), 3), "roles": roles,
        "speed_mps": round(stride * p["stroke_hz"], 5),
        "playback_speed_scale": round(p["stroke_hz"] * duration, 4)})


def row(rig_name, frames=None, action_name="Row", fps=None, mass_kg=None):
    return _row(rig_name, False, frames, action_name, fps, mass_kg)


def row_back(rig_name, frames=None, action_name="RowBack", fps=None, mass_kg=None):
    return _row(rig_name, True, frames, action_name, fps, mass_kg)


# --------------------------------------------------------------------------
# polyp
# --------------------------------------------------------------------------

def sway(rig_name, frames=96, action_name="Sway", fps=None):
    rr = rad.RadialRig(rig_name)
    if rr.kind != "polyp":
        return {"error": "%s is a %s, not a polyp" % (rig_name, rr.kind)}
    p = plan(rr)
    fps_now = fps or bpy.context.scene.render.fps
    n = int(frames)
    tents = sorted(rr.apps, key=lambda ap: ap["theta"] % TAU)
    samples = []
    for k in range(1, n + 2):
        t = (k - 1) / float(n)
        rots = {}
        for j, ap in enumerate(tents):
            ph = t + 0.5 * j / len(tents)
            rr.wave_rots(ap, ph, 14.0, wavelength=1.5, rots=rots, axis="q")
            rr.wave_rots(ap, ph + 0.25, 8.0, wavelength=1.5, rots=rots, axis="a")
        samples.append((rr.fk(rots), {}))
    checks = _skin_checks(rr)
    _, _, action, r = _author(rr, action_name, samples, fps,
                              lambda keyed, ev, infos: _check(rr, checks, keyed, ev, infos, loop=True,
                                                              floats=False)[0])
    duration = (n + 1) / float(fps_now)
    return _finish(r, rr, action, n + 1, {"role": "Sway",
                                          "playback_speed_scale": round(duration / p["sway_period_s"], 4)})


def _curl(rr, share):
    rots = {}
    for ap in rr.apps:
        nb = len(ap["bones"])
        # tip-heavy curl in over the mouth: toward the axis is - about q for a
        # tentacle pointing oral and out
        rr.chain_rots(ap, lift_deg=-95.0 * share, rots=rots,
                      profile=[0.4 + 1.2 * k / max(nb - 1, 1) for k in range(nb)])
    return rots


def measure_curl_limit(rig_name, stretch_limit=3.0, steps=8):
    """How far the tentacles curl in before a face turns inside out or an edge
    passes `stretch_limit` - bisected on predicted poses and stored on the rig,
    as `swim.measure_fin_limits` does for fins. The test anemone's crown folded
    two faces at a full curl."""
    import json
    rr = rad.RadialRig(rig_name)
    checks = _skin_checks(rr)
    _, rest_flips = checks.skin(rr.body.fk())

    def ok(share):
        s, fl = checks.skin(rr.fk(_curl(rr, share)))
        return s <= stretch_limit and fl <= rest_flips
    if ok(1.0):
        best = 1.0
    else:
        lo, hi = 0.0, 1.0
        for _ in range(steps):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if ok(mid) else (lo, mid)
        best = lo
    st = json.loads(rr.rig.data[rad.PROP])
    st["curl_clean"] = round(best, 3)
    rr.rig.data[rad.PROP] = json.dumps(st)
    return {"curl_clean": st["curl_clean"]}


def retract(rig_name, frames=None, action_name="Retract", fps=None, extend=False):
    rr = rad.RadialRig(rig_name)
    if rr.kind != "polyp":
        return {"error": "%s is a %s, not a polyp" % (rig_name, rr.kind)}
    if "curl_clean" not in rr.st:
        measure_curl_limit(rig_name)
        rr = rad.RadialRig(rig_name)
    p = plan(rr)
    fps_now = fps or bpy.context.scene.render.fps
    n = int(frames or max(8, round(p["retract_s"] * fps_now)))
    limit = rr.st["curl_clean"]
    samples = []
    for k in range(1, n + 1):
        u = _smooth((k - 1) / float(n - 1))
        samples.append((rr.fk(_curl(rr, limit * (1.0 - u if extend else u))), {}))
    checks = _skin_checks(rr)

    def check(keyed, ev, infos):
        r, use, evaluated = _check(rr, checks, keyed, ev, infos, loop=False, floats=False)
        end = evaluated[use[-1] if not extend else use[0]]
        rest = rr.body.fk()
        closer = sum(rr.radius(end, ap["bones"][-1]) < 0.8 * rr.radius(rest, ap["bones"][-1]) for ap in rr.apps)
        r["tentacles_closed"] = closer
        if closer < len(rr.apps):
            r["failures"].append("only %d of %d tentacles fold in toward the mouth" % (closer, len(rr.apps)))
        return r
    _, _, action, r = _author(rr, action_name, samples, fps, check)
    return _finish(r, rr, action, n, {"role": "Extend" if extend else "Retract", "curl_share": limit})


# --------------------------------------------------------------------------
# sets and the engine manifest
# --------------------------------------------------------------------------

def _round(p):
    return {k: (round(v, 5) if isinstance(v, float) else v) for k, v in p.items()}


def move_set(rig_name, prefix=None, fps=None, mass_kg=None):
    """Author every clip this body's kind has. Returns {role: report}."""
    rr = rad.RadialRig(rig_name)
    prefix = prefix or rig_name
    nm = lambda role: "%s_%s" % (prefix, role)
    if rr.kind == "medusa":
        makers = {"Pulse": lambda: pulse(rig_name, action_name=nm("Pulse"), fps=fps, mass_kg=mass_kg),
                  "Drift": lambda: drift(rig_name, action_name=nm("Drift"), fps=fps),
                  "Turn": lambda: turn_pulse(rig_name, action_name=nm("Turn"), fps=fps)}
    elif rr.kind == "asteroid":
        makers = {"Crawl": lambda: crawl(rig_name, action_name=nm("Crawl"), fps=fps, mass_kg=mass_kg),
                  "Idle": lambda: star_idle(rig_name, action_name=nm("Idle"), fps=fps)}
    elif rr.kind == "ophiuroid":
        makers = {"Row": lambda: row(rig_name, action_name=nm("Row"), fps=fps, mass_kg=mass_kg),
                  "RowBack": lambda: row_back(rig_name, action_name=nm("RowBack"), fps=fps, mass_kg=mass_kg),
                  "Idle": lambda: star_idle(rig_name, action_name=nm("Idle"), fps=fps)}
    else:
        makers = {"Sway": lambda: sway(rig_name, action_name=nm("Sway"), fps=fps),
                  "Retract": lambda: retract(rig_name, action_name=nm("Retract"), fps=fps),
                  "Extend": lambda: retract(rig_name, action_name=nm("Extend"), fps=fps, extend=True)}
    out = {role: make() for role, make in makers.items()}
    stored.store(out, rig_name)             # on the actions, so export works in a later session
    return out


LOOPS = ("Pulse", "Drift", "Crawl", "Idle", "Row", "RowBack", "Sway")
ROLES = ("Pulse", "Drift", "Turn", "Crawl", "Idle", "Row", "RowBack", "Sway", "Retract", "Extend")


def _stored_mass(reports):
    """The mass `move_set` was given, as its reports' plans recorded it - so a manifest built
    from stored reports in a later session plans with the same mass."""
    for r in reports.values():
        p = r.get("plan") if isinstance(r, dict) else None
        if isinstance(p, dict) and p.get("mass_source") == "given" and p.get("mass_kg"):
            return p["mass_kg"]
    return None


def engine_manifest(reports=None, rig_name=None, mass_kg=None):
    """The `radial` entry of `.moves.json`: the body, its appendages with their
    angles in model space, the clips and the numbers that play them.

    `reports=None` reads the reports `move_set` stored on the rig's actions, and
    the mass it was given unless `mass_kg` says otherwise."""
    if reports is None:
        reports = stored.resolve(None, rig_name, ROLES)
        mass_kg = mass_kg or _stored_mass(reports)
    rr = rad.RadialRig(rig_name)
    st = rr.st
    ok = {k: r for k, r in reports.items() if isinstance(r, dict) and "error" not in r}
    p = plan(rr, mass_kg)
    bones = rr.rig.data.bones
    lengths = lambda names: [round(bones[b].length, 5) for b in names]
    apps = []
    for ap in st["appendages"]:
        apps.append({"name": ap["name"], "role": ap["role"], "theta_deg": round(math.degrees(ap["theta"]), 3),
                     "direction_model": _to_model(rr.radial(ap["theta"])), "bones": ap["bones"],
                     "bone_lengths_m": lengths(ap["bones"]),
                     "parent": ap["parent"], "length_m": round(ap["length"], 4), "loose": ap["loose"]})
    out = {"kind": rr.kind, "order": rr.order,
           "heading_quantum_deg": (360.0 / rr.order) if isinstance(rr.order, int) else None,
           "axis_aboral_model": _to_model(rr.a), "reference_model": _to_model(rr.e1),
           "body": {k: round(p[k], 5) if isinstance(p[k], float) else p[k]
                    for k in ("diameter_m", "height_m", "fineness", "mass_kg")},
           "appendages": apps,
           "ribs": [{"name": rb["name"], "theta_deg": round(math.degrees(rb["theta"]), 3), "bones": rb["bones"],
                     "bone_lengths_m": lengths(rb["bones"])} for rb in rr.ribs],
           "plan": _round({k: v for k, v in p.items() if k not in ("diameter_m", "height_m", "fineness", "mass_kg")}),
           "clips": {role: r["action"] for role, r in ok.items()},
           "loops": [r["action"] for role, r in ok.items() if role in LOOPS]}
    out["playback_speed_scale"] = {role: r["playback_speed_scale"] for role, r in ok.items()
                                   if "playback_speed_scale" in r}
    if rr.kind == "medusa" and "Pulse" in ok:
        out["measured"] = {"margin_contraction": ok["Pulse"].get("margin_contraction"),
                           "tentacle_lag_deg": ok["Pulse"].get("tentacle_lag_deg")}
        if "Turn" in ok:
            out["turn"] = {"turn_deg": ok["Turn"]["turn_deg"],
                           "toward_model": _to_model(rr.radial(math.radians(ok["Turn"]["toward_theta_deg"])))}
    if rr.kind == "ophiuroid":
        out["row"] = {role: {"heading_model": _to_model(rr.radial(math.radians(ok[role]["heading_theta_deg"]))),
                             "heading_theta_deg": ok[role]["heading_theta_deg"],
                             "stride_m": ok[role]["stride_m"], "speed_mps": ok[role]["speed_mps"]}
                      for role in ("Row", "RowBack") if role in ok}
    out["problems"] = (["%s did not pass: %s" % (k, "; ".join(r.get("failures", [])))
                        for k, r in ok.items() if not r.get("passed")]
                       + ["%s: %s" % (k, r["error"]) for k, r in reports.items()
                          if isinstance(r, dict) and "error" in r])
    return out


def export_creature(mesh_name, rig_name, reports, glb_path, creature, res_path=None, mass_kg=None,
                    review=True, review_options=None):
    """Export the glb through `export.export` - read back and duration-checked -
    and write `<name>.moves.json` beside it with the `radial` block, in the shape
    the other creatures' manifests have. `reports=None` exports what `move_set`
    stored on the rig's actions. `review` and `review_options` as `export.export`."""
    import json
    import os
    from . import export
    m = engine_manifest(reports, rig_name, mass_kg)
    if m["problems"]:
        return {"error": "not exporting clips that failed: " + "; ".join(m["problems"]), "manifest": m}
    clips = list(m["clips"].values())
    # No feet: check_clip then seams every bone and reports no stride. A radial
    # body's travel is not a stride of planted feet - it is the plan's pulse
    # distance or the stroke `row` measured - and is carried in the manifest.
    forward = rad.read(bpy.data.objects[rig_name])["forward"]
    e = export.export(mesh_name, rig_name, glb_path, foot_bones=[], actions=clips,
                      loop_clips=m["loops"], forward=forward, sidecar=False, review=review,
                      review_options=dict({"title": creature}, **(review_options or {})))
    if not e.get("exported"):
        return {"error": "export refused at %s" % e.get("stage"), "export": e}
    base = os.path.splitext(glb_path)[0]
    moves = {
        "creature": creature, "rig": rig_name,
        "scene": res_path or ("res://assets/creatures/%s" % os.path.basename(glb_path)),
        "clips": m["clips"], "loops": m["loops"],
        "body_m": {"diameter": m["body"]["diameter_m"], "height": m["body"]["height_m"]},
        "radial": m,
        "verified": e["verified"],
        "note": ("rig-anything radial: a hub and a ring of appendages found on the skin, weighted "
                 "without bone heat; no front or back, so headings are chosen per move - a bell "
                 "swims aboral end first and steers by a lopsided pulse, a sea star glides any way "
                 "on its tube feet, a brittle star rows behind whichever arm is nearest."),
    }
    with open(base + ".moves.json", "w", encoding="utf-8") as fh:
        json.dump(moves, fh, indent=2)
    return {"glb": glb_path, "moves": base + ".moves.json", "verified": e["verified"],
            "clips": clips, "bones": e["preflight"]["bones"], "review": e.get("review")}


def summarize(r):
    if "error" in r:
        return "ERROR: " + r["error"]
    lines = ["%s %s %s" % (r.get("rig"), r.get("action"), "PASSED" if r.get("passed") else "FAILED")]
    lines += ["  FAIL " + f for f in r.get("failures", [])]
    for k in ("prediction_error", "loop_seam", "stretch_max", "flipped_faces", "margin_contraction",
              "margin_contraction_plan", "asymmetry", "contraction_share", "tentacle_lag_deg",
              "tentacle_tip_radius_min",
              "turn_side_closes", "far_side_closes", "arm_tip_lift_m", "bounce_m", "stride_m",
              "stroke_slip", "stance_tip_lift_m", "speed_mps", "tentacles_closed", "curl_share",
              "playback_speed_scale"):
        if r.get(k) is not None:
            lines.append("  %s %s" % (k, r[k]))
    return "\n".join(lines)
