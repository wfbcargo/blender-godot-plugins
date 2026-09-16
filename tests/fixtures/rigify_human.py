"""A Rigify basic_human biped, given every biped move and exported - no MPFB, no flesh.

follow-through's `Figure` (a lofted body with no helper geometry and no ground root bone) is fitted
with rig-anything's `fit_basic_human` and bound by `samples.build_bodies`, then `actions.move_set`
authors its whole default set - Idle, Walk, Trot, Run, Crouch, CrouchWalk, Jump, Slide, SlideRecover
and SlideToCrouch - and `export.export` re-checks every clip on playback and reads the written
durations back. The export runs with `skip_bad_clips=True`: the slides fail their floor checks on
this body (rig-anything 0.14.2 - a toe 0.16 m through the floor at the bottom of the Slide), and a
refused export would leave nothing verified. What was dropped and why is in the golden, so a fix
shows as those clips coming back.

This is the Rigify counterpart of `mpfb_woman_curvy`: the same move code on a rig whose root is an
ordinary pelvis, so a change aimed at one kind of rig shows here if it moves the other. It also runs
with Rigify off, as `--factory-startup` leaves it, and so proves rig-anything turns it on itself.
What a person checks after a change is per role: passed and its failures, the hip drop and what
limited it, balance, stride and implied speed, planted-foot drift and stance slip.
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


def build():
    import bpy
    H.clear_scene()
    from follow_through import samples
    from rig_analysis import actions, export

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
        "export": {"exported": exported.get("exported"), "stage": exported.get("stage"),
                   "note": exported.get("note"), "dropped_clips": H.stable(exported.get("dropped_clips")),
                   "verified": H.stable(exported.get("verified")),
                   "clips": H.stable({n: {k: c.get(k) for k in ("passed", "failures", "loops",
                                                                "locomotion", "engine_duration_s",
                                                                "implied_speed_playback_mps")}
                                      for n, c in (exported.get("clips") or {}).get("clips", {}).items()}),
                   "failing": H.stable((exported.get("clips") or {}).get("failing")),
                   "preflight": H.stable(exported.get("preflight"))},
        "moves_json": H.moves_manifest(char),
    }


H.run("rigify_human", build)
