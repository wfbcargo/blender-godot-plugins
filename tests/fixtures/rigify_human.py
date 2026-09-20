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

# Walks in a style, and what each style must keep of its own (`locomotion.GAIT_STYLES`).
STYLED_WALKS = ("child", "elderly_shuffle", "heavy")
STYLED_HEADLINE = ("passed", "failures", "stance_knee_flex_deg", "vault", "vault_drop_m", "drop_m",
                   "duty_factor", "stride_m")

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


H.run("rigify_human", build)
