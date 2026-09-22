"""Style from the build: how a body's proportions change the way it walks.

`locomotion.cycle` already scales every gait to the body by the Froude number, so a 1.3 m dwarf and
a 2 m elf walk at their own speeds and cadences with nothing said. What the Froude number does not
give is the STYLE a body's build implies at that same dimensionless speed: a long trunk on short legs
rolls, a stocky body stays on the ground longer, a very heavy one never leaves it. `derive_style`
measures those on the rig and returns a `locomotion.STYLE_KEYS` style dict, which `actions.move_set`
lays UNDER the spec's own style (`merge_styles`: the user's words win, key by key).

A body of human proportions and an ordinary build returns {} - not a small style, nothing - so its clips
are exactly the ones it had before this existed. Every term is continuous in its measure and clamped,
and each starts at the edge of the human band, not at the human mean. Stockiness is the exception that
humans reach too: a heavy or a short, heavy human (grungist-creek's smoke_heavy 27 kg/m^3, smoke_elderly
24, smoke_petite 21) derives its stockiness terms - what the "heavy" style does by hand - which is why
character-pipeline derives only for a non-human species unless a spec asks (`[moves] derive = true`).

WHAT IS MEASURED (`measure`)
----------------------------
trunk_to_leg   neck base (where the neck leaves the chest) to the hip joints, over hip-joint height.
               Read on eight MPFB bodies built by the pipeline (1.12-2.02 m, both sexes, BMI to 38):
               0.58-0.68, mean 0.63 (HUMAN_TRUNK_TO_LEG); the heaviest is the highest. Achondroplasia's sitting-height ratio is ~0.66 of
               stature against ~0.52 (Hoover-Fong et al. 2008 growth curves), a trunk-to-leg ratio
               near 1.0-1.1; the species preset "dwarf" softens that (legs 0.62/0.78 femur/tibia).
stockiness     mass / stature^3 (Rohrer's ponderal index, kg/m^3). A BMI 22 adult of 1.75 m is 12.6;
               BMI 30 at 1.75 m is 17; a BMI 29 dwarf of 1.30 m is 22.
mass_kg        rig-anything's voxel mass (`mass.body_mass`, 1010 kg/m^3), or a BMI 22 estimate when
               the rig has no closed skin.
arm_to_hip     shoulder-to-fingertip over hip height. Reported only: arm swing's amplitude and its
               lag already come from the arm's measured pendulum (`upper.limb_frequencies`).

THE MAPPING
-----------
t = trunk excess, 0 at the top of the human band (0.70) .. 1 at an achondroplastic 1.0 (clamped 0..1.25)
s = stockiness excess, 0 at 17 kg/m^3 .. 1 at 23 (clamped 0..1.25)
m = mass excess, 0 at 300 kg .. 1 at 600 (clamped 0..1)
a = arm shortness, arm (shoulder to fingertip) over trunk: 0 at 1.15 .. 1 at 0.9 (clamped 0..1.25);
    the same eight humans read 1.24-1.40

  drives                          per unit          research
  pelvis_list (frontal, deg)      +3.0 t            achondroplasia: pelvic obliquity and hip abduction up,
  side_bend (trunk roll, deg)     +2.0 t              the "waddle" (Inan et al. 2006 gait analysis, and
  stance_width (x rest, gaits)    +0.1 t +0.08 s      Sims et al. 2019 J Pediatr Orthop, both measured)
                                  (at most +20%)
  pelvis_turn (lumbar yaw, deg)   +2.0 t            transverse pelvic rotation up (same)
  posture.pelvis (anterior, deg)  +5.0 t            anterior pelvic tilt / lumbar lordosis up (same)
  run max_drop (knee flexion)     x (1 - 0.3 t)     less stance knee flexion (same) - a walk already
                                                    vaults over a straight leg, so the run is where it shows
  walk duty                       +0.04 s           heavier bodies prolong double support (Browning &
  bounce_scale                    x (1 - 0.25 s)      Kram 2007, obese adults: wider steps, longer stance,
                                                      less vertical excursion)
  run duty / flight               duty >= 0.5 above 300 kg: no aerial phase - elephants never leave
                                                    the ground at any speed (Hutchinson et al. 2003,
                                                    Nature 422); the run becomes a fast walk
  run bounce / max_drop           x (1 - 0.4 m)     straighter, columnar limbs with mass (Biewener 1989,
                                                    Science 245: effective mechanical advantage rises)
  run elbow / arm_swing (deg)     -25 a / -8 a      short arms on a long trunk: the bent running arm
                                                    would lift the hand past the chest (rig-anything's
                                                    own arm check); swing timing stays the pendulum's

Numbers are the shape of each change and its direction from the research, sized so a full dwarf
reads clearly without any clip leaving its checks; they are not fitted to a dataset.
"""

from __future__ import annotations


# trunk_to_leg on MPFB bodies from the pipeline (measured, see the docstring): the band a human sits in
HUMAN_TRUNK_TO_LEG = 0.63
TRUNK_BAND_HI = 0.70            # the top of the human band (0.682 measured, BMI 38): no trunk term below it
TRUNK_FULL = 1.0                # an achondroplastic trunk-to-leg ratio: the full term
STOCKY_HI = 17.0                # kg/m^3, BMI ~30 at 1.75 m: no stockiness term below it
STOCKY_FULL = 23.0
HEAVY_KG = 300.0                # above it, no flight phase and straightening limbs
HEAVY_FULL_KG = 600.0
ARM_BAND_LO = 1.15              # arm over trunk: the bottom of the human band (1.33 measured)
ARM_FULL = 0.9

# The checks (`checks`): a walk's Froude number outside this band reads as a stroll or a power walk
# at best, and as a different gait at worst (human preferred walking is Fr 0.25, the walk-run change
# 0.5, Alexander 1989; 0.18 is the slow end of an unhurried walk).
WALK_FROUDE = (0.18, 0.35)
# a hand reaches the top of the head when the arm to the palm is this much longer than the straight
# line from the shoulder joint: the elbow has to come round the side of the head
HEAD_REACH = 1.2


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _heights(bm, rig):
    """A function giving a point's height above the floor, armature point in, metres out."""
    from .bodymap import axis_vector
    mw = rig.matrix_world
    up = axis_vector(bm["up"]).normalized()
    return lambda p: (mw @ p).dot(up) - bm["floor"]


def _skin_top(rig, bm, h):
    """The highest skin point over the head (world metres) and its armature-space point, or None."""
    from . import mass as mass_mod
    best = None
    for o in mass_mod._meshes_for(rig):
        to_arm = rig.matrix_world.inverted() @ o.matrix_world
        for v in o.data.vertices:
            p = to_arm @ v.co
            z = h(p)
            if best is None or z > best[0]:
                best = (z, p)
    return best


def measure(bm, rig=None, mass=None, with_mass=True):
    """The build measures `derive_style` maps, off a rig's rest skeleton and skin.

    `mass` is a `mass.measure` dict, a number in kg, or None to measure it (`mass.body_mass`);
    `with_mass=False` skips it (the reach checks need none), leaving mass_kg and stockiness out.
    Returns {} for a body with no upright pair of legs (nothing here applies to a quadruped)."""
    import bpy
    rig = rig or bpy.data.objects[bm["rig"]]
    legs = [l for l in bm["limbs"] if l["role"] == "leg"]
    arms = [l for l in bm["limbs"] if l["role"] == "arm"]
    if len(legs) != 2 or not bm.get("upright"):
        return {}
    h = _heights(bm, rig)
    scale = sum(rig.matrix_world.to_scale()) / 3.0
    hip = sum(h(l["rest_root"]) for l in legs) / 2.0
    axial = bm["axial"]
    joints = bm["axial_joints"]
    if bm.get("neck"):
        neck_base = h(joints[axial.index(bm["neck"][0])])
    elif bm.get("head"):
        neck_base = h(joints[axial.index(bm["head"])])
    else:
        return {}
    top = _skin_top(rig, bm, h)
    stature = top[0] if top else bm["height"] * scale
    out = {"stature_m": round(stature, 4), "hip_height_m": round(hip, 4),
           "neck_base_m": round(neck_base, 4), "trunk_m": round(neck_base - hip, 4),
           "trunk_to_leg": round((neck_base - hip) / max(hip, 1e-6), 4)}

    kg, source = None, None
    if not with_mass:
        source = "skipped"
    elif isinstance(mass, (int, float)):
        kg, source = float(mass), "given"
    elif isinstance(mass, dict) and mass.get("total_mass"):
        kg, source = float(mass["total_mass"]), "voxel"
    else:
        from . import mass as mass_mod, motion
        try:
            md = mass_mod.body_mass(motion.Body(rig, bm))
        except Exception:                                       # pragma: no cover
            md = None
        if md and md.get("total_mass"):
            kg, source = float(md["total_mass"]), "voxel"
    if kg is None and with_mass:
        kg, source = 22.0 * stature * stature, "estimated (BMI 22)"
    if kg is not None:
        out.update(mass_kg=round(kg, 2), mass_source=source,
                   stockiness=round(kg / max(stature, 1e-6) ** 3, 3))

    if arms:
        bones = rig.data.bones
        reach, palm, shoulder_h, shoulder = [], [], [], []
        for a in arms:
            # the wrist to the farthest fingertip along the limb's own chain (the longest finger, which
            # bodymap follows), else the hand bone's tail; the palm half way along it
            far = a["digits"][-1] if a["digits"] else (a["end"] or a["lower"])
            tip = (bones[far].tail_local - a["rest_eff"]).length if a["end"] else 0.0
            reach.append((a["a"] + a["b"] + tip) * scale)
            palm.append((a["a"] + a["b"] + 0.5 * tip) * scale)
            shoulder_h.append(h(a["rest_root"]))
            shoulder.append(a["rest_root"])
        arm = sum(reach) / len(reach)
        out["arm_m"] = round(arm, 4)
        out["arm_to_hip"] = round(arm / max(hip, 1e-6), 4)
        # hanging straight down, where the fingertips come to
        out["fingertip_hang_m"] = round(min(sh - r for sh, r in zip(shoulder_h, reach)), 4)
        if top:
            d = min((rig.matrix_world @ top[1] - rig.matrix_world @ s).length for s in shoulder)
            out["head_reach_ratio"] = round(min(palm) / max(d, 1e-6), 3)
    return out


def terms(m):
    """(t, s, mass excess) for a `measure` dict: 0 inside the human band, clamped above it."""
    if not m:
        return 0.0, 0.0, 0.0
    t = _clamp((m["trunk_to_leg"] - TRUNK_BAND_HI) / (TRUNK_FULL - TRUNK_BAND_HI), 0.0, 1.25)
    s = _clamp((m.get("stockiness", 0.0) - STOCKY_HI) / (STOCKY_FULL - STOCKY_HI), 0.0, 1.25)
    w = _clamp((m.get("mass_kg", 0.0) - HEAVY_KG) / (HEAVY_FULL_KG - HEAVY_KG), 0.0, 1.0)
    return t, s, w


def arm_term(m):
    """0 for arms in the human band, up to 1.25 for arms short against the trunk (shoulder to
    fingertip over neck-base-to-hip: 1.24-1.40 on MPFB humans, 0.93 with the arm segments at 0.6)."""
    if not m or not m.get("arm_m") or not m.get("trunk_m"):
        return 0.0
    return _clamp((ARM_BAND_LO - m["arm_m"] / m["trunk_m"]) / (ARM_BAND_LO - ARM_FULL), 0.0, 1.25)


def _rest_stance(bm):
    """The rest ankle-to-midline over hip-to-midline ratio (`keyposes.stance_shift`'s 1.0 is under the hip)."""
    legs = [l for l in bm["limbs"] if l["role"] == "leg"]
    lat = bm["lat"]
    centre = sum((l["rest_root"] for l in legs), legs[0]["rest_root"] * 0.0) / len(legs)
    ratios = []
    for l in legs:
        hip = (l["rest_root"] - centre).dot(lat)
        if abs(hip) > 1e-6:
            ratios.append((l["rest_eff"] - centre).dot(lat) / hip)
    return sum(ratios) / len(ratios) if ratios else 1.0


def derive_style(bm, mass=None, rig=None, measured=None):
    """A `locomotion.STYLE_KEYS` style for this build, or {} for a body of human proportions and build.

    `bm` is `bodymap.build`'s map; `mass` as `measure`. Sections "walk", "run" and "idle" only,
    so `merge_styles` can lay the spec's style over it key by key. See the module docstring for the
    mapping and its sources."""
    from . import locomotion
    m = measured if measured is not None else measure(bm, rig=rig, mass=mass)
    t, s, w = terms(m)
    if t == 0.0 and s == 0.0 and w == 0.0 and arm_term(m) == 0.0:
        return {}
    walk, run, idle = {}, {}, {}
    wu, ru = {}, {}
    if t > 0.0 or s > 0.0:
        # the gaits only: a standing idle on straight legs cannot widen without the legs lengthening
        # (a dwarf's idle at +36% needed 102% of its legs), and the stance is the one it stood in
        width = round(_rest_stance(bm) * (1.0 + min(0.2, 0.1 * t + 0.08 * s)), 3)
        for sect in (walk, run):
            sect["stance_width"] = width
    if t > 0.0:
        base_w = locomotion_upper_defaults(0.2)
        base_r = locomotion_upper_defaults(2.0)
        wu.update(pelvis_list=round(base_w["pelvis_list"] + 3.0 * t, 2),
                  side_bend=round(base_w["side_bend"] + 2.0 * t, 2),
                  pelvis_turn=round(base_w["pelvis_turn"] + 2.0 * t, 2))
        ru.update(pelvis_list=round(base_r["pelvis_list"] + 3.0 * t, 2),
                  side_bend=round(base_r["side_bend"] + 2.0 * t, 2))
        posture = {"pelvis": round(5.0 * t, 2)}
        for sect in (walk, run, idle):
            sect["posture"] = dict(posture)
    run_drop = locomotion.GAIT_STYLES["adult"]["run"]["max_drop"]
    run_drop *= (1.0 - 0.3 * t) * (1.0 - 0.4 * w)
    if t > 0.0 or w > 0.0:
        run["max_drop"] = round(run_drop, 4)
    if s > 0.0:
        walk["duty"] = round(locomotion.duty_factor(locomotion.GAITS["walk"]) + 0.04 * s, 3)
        walk["bounce_scale"] = round(1.0 - 0.25 * s, 3)
        run["bounce_scale"] = round(1.0 - 0.25 * s, 3)
    if w > 0.0:
        run["duty"] = 0.5
        run["bounce_scale"] = round(run.get("bounce_scale", 1.0) * (1.0 - 0.4 * w), 3)
    a = arm_term(m)
    if a > 0.0:
        # Short arms on a long trunk: a running arm's bent elbow brings the hand up past the chest
        # (the plain dwarf's run put it at 69% of hip-to-shoulder, over the arm check's 65%), so the
        # run's elbow opens and its swing shortens. The arm's pendulum timing is already its own
        # (`upper.limb_frequencies`); this is its amplitude.
        base_r = locomotion_upper_defaults(2.0)
        ru.update(elbow=round(base_r["elbow"] - 25.0 * a, 1),
                  arm_swing=round(base_r["arm_swing"] - 8.0 * a, 1))
    if wu:
        walk["upper"] = wu
    if ru:
        run["upper"] = ru
    return {k: v for k, v in (("walk", walk), ("run", run), ("idle", idle)) if v}


def locomotion_upper_defaults(froude):
    """`upper.defaults` at a Froude number with its own duty, so a derived value is the default plus
    the build's term rather than a number that goes stale when the default moves."""
    from . import locomotion, upper
    return upper.defaults(froude, locomotion.duty_factor(froude))


def merge_styles(under, over):
    """One style dict: `over` (a `GAIT_STYLES` name, a dict, or None) laid on `under` key by key, per
    section, with `upper` and `posture` merged within. Each is flattened per section first
    (`locomotion.style_args`), so a key the spec sets in its common part still beats a derived key
    in a section. `under` empty returns `over` unchanged - a name stays a name."""
    from .locomotion import style_args
    if not under:
        return over
    out = {}
    for sect in ("walk", "run", "idle"):
        a = style_args(under, sect, {})
        b = style_args(over, sect, {})
        merged = dict(a)
        for k, v in b.items():
            if k in ("upper", "posture") and isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = dict(merged[k], **v)
            else:
                merged[k] = v
        out[sect] = merged
    return out


def checks(reports=None, measured=None):
    """Warnings, each with its fix: a baked walk's Froude number outside WALK_FROUDE, and arms that
    cannot reach the hips hanging or the top of the head. `reports` is {role: report} (`move_set`),
    `measured` a `measure` dict. [] when all is well."""
    out = []
    lo, hi = WALK_FROUDE
    for role, r in sorted((reports or {}).items()):
        if not isinstance(r, dict) or "natural_speed_mps" not in r or r.get("gait") != "walk":
            continue
        fr = r.get("froude")
        if fr is None:
            continue
        if fr < lo:
            why = ("; ".join(r.get("limited_by") or []) or "asked for %.3f" % r.get("froude_requested", fr))
            out.append("%s walks at Froude %.3f, under %.2f - it reads as a shuffle (%s): ask for "
                       "gaits.%s >= %.2f, or if the stride was cut, raise max_drop in "
                       "[moves.per_gait.%s] or lengthen the legs" % (role, fr, lo, why, role, lo, role))
        elif fr > hi:
            out.append("%s walks at Froude %.3f, over %.2f - a power walk at the edge of running: ask "
                       "for gaits.%s <= %.2f (0.2-0.25 is an unhurried walk)" % (role, fr, hi, role, hi))
    m = measured or {}
    if m.get("fingertip_hang_m") is not None and m["fingertip_hang_m"] > m["hip_height_m"]:
        out.append("the hands hang %.3f m above the hip joints (fingertips at %.3f m, hips at %.3f m) - "
                   "the arms cannot reach a belt or a pocket: lengthen the upper arm and forearm "
                   "(the species preset's humerus / forearm segments)"
                   % (m["fingertip_hang_m"] - m["hip_height_m"], m["fingertip_hang_m"], m["hip_height_m"]))
    if m.get("head_reach_ratio") is not None and m["head_reach_ratio"] < HEAD_REACH:
        out.append("the hands cannot reach the top of the head (arm to palm %.2f of the shoulder-to-crown "
                   "distance, needs %.2f) - no helmet on, no drinking from a raised cup: lengthen the "
                   "upper arm and forearm, or lower the head (shorter neck)" % (m["head_reach_ratio"], HEAD_REACH))
    return out
