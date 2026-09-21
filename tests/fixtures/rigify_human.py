"""A Rigify basic_human biped, given every biped move and exported - no MPFB, no flesh.

follow-through's `Figure` (a lofted body with no helper geometry and no ground root bone) is fitted
with rig-anything's `fit_basic_human` and bound by `samples.build_bodies`, then `actions.move_set`
authors its whole default set - Idle, Walk, Trot, Run, Crouch, CrouchWalk, Jump, Slide, SlideRecover
and SlideToCrouch - and `export.export` re-checks every clip on playback and reads the written
durations back. The export runs with `skip_bad_clips=True`: the slides failed their floor checks on
this body before improvements 5.8 (a toe 0.16 m through the floor at the bottom of the Slide), and
a refused export would leave nothing verified. What is dropped and why is in the golden - nothing,
now - so a regression shows as clips going missing.

This is the Rigify counterpart of `mpfb_woman_curvy`: the same move code on a rig whose root is an
ordinary pelvis, so a change aimed at one kind of rig shows here if it moves the other. It also runs
with Rigify off, as `--factory-startup` leaves it, and so proves rig-anything turns it on itself.
What a person checks after a change is per role: passed and its failures, the hip drop and what
limited it, balance, stride and implied speed, planted-foot drift and stance slip.

It also drives `verify.arm_swing` over carry angles taken from real clips (`ARM_SWING_CASES`), so
the branch that fails an arm carried out in front is exercised without needing a body built wrong,
and it walks the same body at two speeds a decade apart to say whether the last rung of the axial
lag ladder moves with speed (`HEAD_RUNG_CASES`), with the locked head it replaces as the control
that must read a flat line.

And it is where the fixed per-character left/right asymmetry is judged (`ASYM_IDS`, `_asymmetry`):
four more walks on the same body, each MEASURED off its baked clip, at the default (which must
change nothing and report nothing), at the shipped dial on two different character ids, and once
with `RA_ASYM_MIRROR=1` - the control that must fail, whose verdicts are False in the golden.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "FT_SCRIPTS")

BODY = "Figure"
ROLES = ("Idle", "Walk", "Trot", "Run", "Crouch", "CrouchWalk", "Jump",
         "Slide", "SlideRecover", "SlideToCrouch")
GAITS = ("Walk", "Trot", "Run")
LOOPS = ("Idle", "Walk", "Trot", "Run", "CrouchWalk")     # the rest are one-shots
# The numbers worth a line of their own, beside the full report each role carries.
HEADLINE = ("passed", "failures", "hip_drop_m", "max_drop_m", "drop_limited_by", "balance",
            "stride_m", "implied_speed_playback_mps", "planted_drift", "stance_slip", "loop_seam",
            "lowest_point", "skin_lowest", "tightest_joint_degrees")

# The last rung of the lag ladder, and the control that must fail it. Every rung
# of the axial chain lags the one below it by a phase that DEPENDS ON SPEED, so
# the tell of a rung that is not really there is a relative phase that reads the
# same number at every speed - the thorax was caught at a flat -179.3 that way,
# and the head at a flat -0.6. Two clips a decade of Froude apart say whether the
# rung moves. `head_lag` forced to 0 is the locked head that `upper.trunk` gave
# before it took the head's own signal: it MUST come out flat and so MUST fail
# the test the derived lag passes. `thorax_head_phase_deg` is measured off the
# BAKED clip, never off the prediction.
HEAD_RUNG_FROUDE = (0.05, 1.2)
HEAD_RUNG_SWEEP_DEG = 20.0
HEAD_RUNG_CASES = (("derived", None), ("control_locked_head", {"head_lag": 0.0}))

# The mass model is a property of the BODY, not of the clip, but every role
# builds its own `motion.Body`, so before the cache a seven-role set solved the
# same unchanged skin four separate times - 7.32 s of an 18.42 s move set on
# Belle, and the whole of the `moves` regression the benchmark caught.
#
# A cache is only ever as good as the thing that invalidates it, so invalidation
# is what is checked here, not the speed. Move one vertex and the model must be
# taken again. `control_pinned_key` is the control that MUST fail: it holds the
# fingerprint still - exactly the bug a careless key would have - and so serves
# the STALE mass for a body that has changed. Its verdicts are False in the
# golden, so this check fails if invalidation ever breaks AND if the control ever
# stops working.
MASS_CACHE_LIFT_M = 0.05
MASS_CACHE_CASES = (("keyed_on_the_body", False), ("control_pinned_key", True))

# Walks in a style, and what each style must keep of its own (`locomotion.GAIT_STYLES`).
STYLED_WALKS = ("child", "elderly_shuffle", "heavy")
STYLED_HEADLINE = ("passed", "failures", "stance_knee_flex_deg", "vault", "vault_drop_m", "drop_m",
                   "duty_factor", "stride_m")

# The fixed per-character left/right asymmetry (rig-anything's `variability.py`), measured off
# the BAKED clip and never from the parameter that was set. Four walks on one body:
#
#   zero     the default. Its indices are the body's own - a Rigify Figure is not exactly
#            symmetric and the solver is not exact - and every other case is judged against them.
#   ship_a   `variability.SENSIBLE` on one character id: each index must clear zero's by MARGIN.
#   ship_b   the same dial on a DIFFERENT id: also asymmetric, and its draw differs from ship_a's,
#            which is what "two characters differ" means.
#   mirror   the control that must fail. `RA_ASYM_MIRROR=1` gives both sides one side's draw, so
#            the asymmetry is still drawn and still applied (the arms swing less than zero's) and
#            the clip comes out symmetric again. Its verdicts are False in the golden, so this
#            check fails if the side plumbing is lost AND if the control ever stops working.
ASYM_IDS = ("rigify_human_a", "rigify_human_b")
ASYM_MEASURES = ("arm_swing_deg", "shoulder_dip_m")
# how far past the body's own asymmetry a symmetry index must get to count as asymmetric. The
# shoulder dip is the quiet one (a 2.5 degree clavicle at a walk), so it sets this floor.
ASYM_MARGIN = 0.004
# Step length is judged on `stance_offset_m` instead of on its index, in metres, because the
# index is not monotone in the asymmetry: this body's own feet already plant 6.5 mm apart along
# the travel direction, so a draw that happens to shift the other way makes the walk MORE
# symmetric than the default while still being just as asymmetric a change. The offset is the
# quantity the bake moves one for one, and it is signed.
ASYM_STEP_MARGIN_M = 0.002

# `verify.arm_swing` decides whether a clip's arms swing through hanging or are carried out in
# front (04 d). Its branches cannot all be reached by a body that is built right, so they are
# driven here from carry angles measured on real clips, the way `flesh_figure` drives the limit
# ladder. Each case is (name, [carry per frame], running); only the extremes matter, since the
# check reads the range and the minimum.
ARM_SWING_CASES = (
    # a walk that swings through hanging: Tomas, grungist-creek ed654b0
    ("walk_through_hanging", [-8.9, 10.7, 30.3, 10.7], False),
    # the tightest shipped pass - Margaret's elderly shuffle, 13.6 degrees of swing
    ("elderly_shuffle", [-3.9, 2.9, 9.7, 2.9], False),
    # the pre-fix Walter walk the review strips caught: both arms held out in front, bobbing
    ("walk_held_in_front", [8.8, 17.2, 25.5, 17.2], False),
    # a run keeps both arms in front by design and is guarded by hand_rise instead
    ("run_in_front", [1.2, 28.0, 54.8, 28.0], True),
    # an idle does not swing, so it is never checked - the pre-fix Walter idle, still unguarded
    ("idle_held_in_front", [13.8, 14.8, 15.8, 14.8], False),
    # the limit itself, either side
    ("on_the_limit", [2.0, 12.0, 22.0, 12.0], False),
    ("just_over_the_limit", [2.1, 12.1, 22.1, 12.1], False),
)


def build():
    import bpy
    H.clear_scene()
    from follow_through import samples
    from rig_analysis import actions, export, verify

    made = samples.build_bodies(rig=True, walk=False, rig_anything=H.scripts("RA_SCRIPTS"))
    rig = made["bodies"][BODY]["rig"]
    # The samples build in a scene of their own; move_set and the exporter work on the active one.
    window = bpy.context.window
    previous, window.scene = window.scene, bpy.data.scenes[made["scene"]]
    try:
        moves = actions.move_set(rig, prefix=BODY, roles=ROLES)
        if "error" in moves:
            raise RuntimeError("move_set: " + moves["error"])
        out = os.path.join(H.out_dir(), "rigify_human")
        os.makedirs(out, exist_ok=True)
        # export_character writes figure.moves.json for `--godot`, with the dropped slides left out
        char = export.export_character(BODY, rig, os.path.join(out, "figure.glb"), name=BODY,
                                       reports=moves, roles=ROLES, loops=LOOPS, gaits=GAITS,
                                       forward="-Y", skip_bad_clips=True)
        exported = char.get("export", {})
        # A styled walk on the same body, after the export so its clips stay out of the glb: the
        # vault must keep each style's character - a child's hips rise and fall bounce_scale
        # times its own need, an elderly shuffle and a heavy walk do not vault and keep soft
        # knees at mid-stance (rig-anything 0.24.x lost all three to the vault).
        from rig_analysis import locomotion
        styled = {}
        for style in STYLED_WALKS:
            r = locomotion.cycle(rig, froude=0.2, style=style, action_name=BODY + "_Style_" + style)
            styled[style] = H.stable({k: r.get(k) for k in STYLED_HEADLINE} if "error" not in r else r)
        # The head rung and its control, after the export so these clips stay out
        # of the glb as the styled walks do.
        head_rung = {}
        for label, upper in HEAD_RUNG_CASES:
            got = {}
            for froude in HEAD_RUNG_FROUDE:
                r = locomotion.cycle(rig, froude=froude, upper=upper,
                                     action_name="%s_HeadRung_%s_%s" % (BODY, label, froude))
                u = r.get("upper") or {}
                got[str(froude)] = H.stable({
                    "speed_mps": r.get("implied_speed_playback_mps"),
                    "stride_hz": u.get("stride_hz"), "head_hz": u.get("head_hz"),
                    "head_lag_deg": u.get("head_lag_deg"),
                    "pelvis_thorax_phase_deg": r.get("pelvis_thorax_phase_deg"),
                    "thorax_head_phase_deg": r.get("thorax_head_phase_deg"),
                    "passed": r.get("passed"), "failures": r.get("failures")})
            ends = [got[str(f)].get("thorax_head_phase_deg") for f in HEAD_RUNG_FROUDE]
            # the free value, not a clamped verdict: how far the rung moved over
            # the sweep, beside the threshold it is read against
            got["sweep_deg"] = None if None in ends else round(abs(ends[1] - ends[0]), 1)
            got["needs_deg"] = HEAD_RUNG_SWEEP_DEG
            got["moves_with_speed"] = bool(got["sweep_deg"] is not None
                                           and got["sweep_deg"] >= HEAD_RUNG_SWEEP_DEG)
            head_rung[label] = got
        asymmetry = H.stable(_asymmetry(rig))
        mass_cache = H.stable(_mass_cache(rig))
    finally:
        window.scene = previous

    return {
        "roles": H.roles(rig),
        "mesh": {"vertices": len(bpy.data.objects[BODY].data.vertices)},
        "rig": {"bones": len(bpy.data.objects[rig].data.bones)},
        "bind_coverage": made["bodies"][BODY].get("coverage"),
        "headline": {role: H.stable({k: moves[role].get(k) for k in HEADLINE if k in moves[role]})
                     for role in ROLES},
        "moves": {role: H.stable(moves[role]) for role in ROLES},
        "styled_walks": styled,
        "head_rung": head_rung,
        "asymmetry": asymmetry,
        "mass_cache": mass_cache,
        "export": {"exported": exported.get("exported"), "stage": exported.get("stage"),
                   "note": exported.get("note"), "dropped_clips": H.stable(exported.get("dropped_clips")),
                   "verified": H.stable(exported.get("verified")),
                   "clips": H.stable({n: {k: c.get(k) for k in ("passed", "failures", "loops",
                                                                "locomotion", "engine_duration_s",
                                                                "implied_speed_playback_mps")}
                                      for n, c in (exported.get("clips") or {}).get("clips", {}).items()}),
                   "failing": H.stable((exported.get("clips") or {}).get("failing")),
                   "preflight": H.stable(exported.get("preflight"))},
        "arm_swing": {name: H.stable(verify.arm_swing(carry, running))
                      for name, carry, running in ARM_SWING_CASES},
        "moves_json": H.moves_manifest(char),
        "review": H.review_sheet(char.get("review")),
    }


def _mass_cache(rig):
    """Does the body-mass cache reuse an unchanged body, and drop a changed one?

    Both cases move the SAME vertex by the same amount; they differ only in
    whether the key is allowed to notice. `measure` is counted rather than timed,
    because a count is the same number on every machine.
    """
    import bpy
    from rig_analysis import bodymap, mass, motion

    bm = bodymap.build(rig, forward="-Y", up="Z")
    rig_object = bpy.data.objects[rig]          # `rig` is a NAME here, as move_set takes one
    real_measure, real_fingerprint = mass.measure, mass._fingerprint
    calls = {"n": 0}

    def counted(*a, **k):
        calls["n"] += 1
        return real_measure(*a, **k)

    def fresh():
        """A new Body, as every role's maker makes one - no per-Body cache to hit."""
        return motion.Body(rig_object, bm)

    out = {}
    mesh = bpy.data.objects[BODY].data
    home = tuple(mesh.vertices[0].co)
    try:
        mass.measure = counted
        for label, pinned in MASS_CACHE_CASES:
            mass._MEASURED.clear()
            mesh.vertices[0].co = home
            if pinned:
                mass._fingerprint = lambda name: "pinned"
            else:
                mass._fingerprint = real_fingerprint
            calls["n"] = 0
            first = mass.body_mass(fresh())
            again = mass.body_mass(fresh())          # unchanged: must NOT measure again
            reused = calls["n"]
            mesh.vertices[0].co = (home[0], home[1], home[2] + MASS_CACHE_LIFT_M)
            after = mass.body_mass(fresh())          # changed: MUST measure again
            out[label] = {
                "measures_once_when_unchanged": bool(reused == 1),
                "measure_calls_for_two_bodies": reused,
                "total_kg": None if not first else round(first.get("total_mass", 0.0), 4),
                "total_kg_after_edit": None if not after else round(after.get("total_mass", 0.0), 4),
                # the free values above, the verdict below
                "noticed_the_edit": bool(first and after
                                         and first.get("total_mass") != after.get("total_mass")),
            }
            assert again is not None or first is None
    finally:
        mass.measure, mass._fingerprint = real_measure, real_fingerprint
        mass._MEASURED.clear()
        mesh.vertices[0].co = home
    return out


def _asymmetry(rig):
    """Bake the four walks above, measure each off its clip, and judge them against `zero`."""
    from rig_analysis import locomotion, variability

    def walk(label, identity, asymmetry, mirror=False):
        v = None
        if asymmetry is not None:
            v = variability.resolve({"asymmetry": asymmetry}, identity)
        was = os.environ.get("RA_ASYM_MIRROR")
        if mirror:
            os.environ["RA_ASYM_MIRROR"] = "1"
        try:
            r = locomotion.cycle(rig, froude=0.2, style="adult", variability=v,
                                 action_name=BODY + "_Asym_" + label)
        finally:
            if mirror:
                os.environ.pop("RA_ASYM_MIRROR", None)
                if was is not None:
                    os.environ["RA_ASYM_MIRROR"] = was
        if "error" in r:
            return {"error": r["error"]}
        m = variability.measure(rig, r["action"])
        return {"resolved": v, "drawn": (r.get("variability") or {}).get("plus_lat"),
                "report_has_variability": "variability" in r,
                "passed": r.get("passed"), "failures": r.get("failures", [])[:3],
                "stroke_m": r.get("stroke_m"),
                "measured": {k: m.get(k) for k in
                             ASYM_MEASURES + ("step_length_m", "stride_m", "stance_offset_m")}}

    cases = {"zero": walk("zero", ASYM_IDS[0], None),
             "ship_a": walk("ship_a", ASYM_IDS[0], variability.SENSIBLE),
             "ship_b": walk("ship_b", ASYM_IDS[1], variability.SENSIBLE),
             "mirror_control": walk("mirror", ASYM_IDS[0], variability.SENSIBLE, mirror=True)}
    base = cases["zero"]["measured"]
    for name, c in cases.items():
        if "error" in c or name == "zero":
            continue
        # the free values, not just the verdicts: an index that drifts toward its floor is
        # visible in the golden long before the verdict flips
        c["index_over_zero"] = {k: round(c["measured"][k]["index"] - base[k]["index"], 5)
                                for k in ASYM_MEASURES}
        c["asymmetric"] = {k: c["index_over_zero"][k] > ASYM_MARGIN for k in ASYM_MEASURES}
        c["stance_offset_moved_m"] = round(c["measured"]["stance_offset_m"]
                                           - base["stance_offset_m"], 5)
        c["asymmetric"]["step_length_m"] = (abs(c["stance_offset_moved_m"])
                                            > ASYM_STEP_MARGIN_M)
        # the no-skate invariant: each foot still travels one stride at the body's speed, or
        # one of them would slide over its stance and the exporter would refuse the clip
        c["stride_stays_even"] = c["measured"]["stride_m"]["index"] < 0.01
    a, b = cases["ship_a"], cases["ship_b"]
    return {
        "margin": ASYM_MARGIN,
        "dial": variability.SENSIBLE,
        "cases": cases,
        # the whole claim in four booleans, so a golden diff reads as a verdict and not as noise
        # at the default the clip reports no variability block at all, which is what keeps every
        # existing character's report - and so its golden - byte for byte what it was
        "zero_reports_nothing": cases["zero"]["report_has_variability"] is False,
        "asym_reports_block": all(cases[k]["report_has_variability"] is True
                                  for k in ("ship_a", "ship_b", "mirror_control")),
        "ship_a_asymmetric": all(a["asymmetric"].values()),
        "ship_b_asymmetric": all(b["asymmetric"].values()),
        "strides_stay_even": all(c.get("stride_stays_even") for c in cases.values()
                                 if "stride_stays_even" in c),
        "two_ids_differ": a["drawn"] != b["drawn"] and any(
            a["measured"][k]["ratio"] != b["measured"][k]["ratio"] for k in ASYM_MEASURES),
        # the control: drawn and applied, but symmetric - every verdict False
        "mirror_control_symmetric": not any(cases["mirror_control"]["asymmetric"].values()),
        "mirror_control_did_apply": (cases["mirror_control"]["measured"]["arm_swing_deg"]["plus_lat"]
                                     != base["arm_swing_deg"]["plus_lat"]),
        # determinism, with no Blender in it: the same seed twice, two ids apart, and the
        # control that breaks exactly that
        "determinism": _determinism(),
    }


def _determinism():
    from rig_analysis import variability
    seed = variability.seed_from(ASYM_IDS[0])
    same = (variability.draw(seed, variability.SENSIBLE).values
            == variability.draw(variability.seed_from(ASYM_IDS[0]), variability.SENSIBLE).values)
    other = variability.draw(variability.seed_from(ASYM_IDS[1]), variability.SENSIBLE).values
    was = os.environ.get("RA_ASYM_NONDETERMINISTIC")
    os.environ["RA_ASYM_NONDETERMINISTIC"] = "1"
    try:
        loose = variability.seed_from(ASYM_IDS[0]) == variability.seed_from(ASYM_IDS[0])
    finally:
        os.environ.pop("RA_ASYM_NONDETERMINISTIC", None)
        if was is not None:
            os.environ["RA_ASYM_NONDETERMINISTIC"] = was
    return {
        # the seed is the id's, byte for byte, in this process and in every other one
        "seed": seed,
        "same_id_same_draw": same,
        "two_ids_differ": variability.draw(seed, variability.SENSIBLE).values != other,
        # a zero dial is the identity exactly, not nearly: 1.0 and 0.0, not 0.9999999
        "zero_is_exact": all(variability.draw(seed, 0.0).gain(c, s) == 1.0
                             and variability.draw(seed, 0.0).offset(c, s) == 0.0
                             for c in variability.CHANNELS for s in (1, -1)),
        # the control that must fail: a seed off the process agrees with nothing, not even itself
        "control_nondeterministic_agrees": loose,
    }


H.run("rigify_human", build)
