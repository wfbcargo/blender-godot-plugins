"""One body, exported three times - asymmetric, symmetric and mirrored - for the Godot asymmetry meter.

rig-anything's fixed per-character left/right asymmetry (`variability.py`) is measured at bake time
by `variability.measure`, off Blender's playback of the baked clip. This fixture exports what that
instrument measured so the ENGINE can measure it again, independently, off the playing skeleton:
`regress --godot` plays each export through rig-anything's `verify_asymmetry.gd` (whose meter is
`asymmetry_meter.gd`) and compares the two, channel by channel, on Walk and Run (`GODOT_ASYM`).

follow-through's `Figure` (lofted, Rigify basic_human, no flesh) is fitted and bound once, then given
Idle, Walk and Run three times over, each set exported as its own character:

  asym     `[variability] asymmetry = variability.SENSIBLE` (0.35, the shipped dial) on the id
           `IDENTITY`, chosen because its draw is large on EVERY channel (|unit| > 0.6 on arm swing,
           step length, shoulder dip and lag), so no channel can pass for want of a draw
  zero     no `[variability]` at all - the identity; its indices are the body's own
  mirror   the same draw with `RA_ASYM_MIRROR=1`: applied to both sides, so drawn and non-zero and
           symmetric again - a control that must FAIL "is asymmetric"

and one more measurement that is not a build:

  swap     the asym clips measured with the body map's `lat` negated, so +lat is -lat: every
           ratio must invert and `stance_offset_m` flip sign. In Godot the same control is the
           meter's `swap_sides`; regress holds the two against each other, and against `asym`'s
           Blender numbers, which a swapped meter must NOT agree with.

Per case and clip the golden carries the free values (`variability.measure`: arm swing, step length,
stride, shoulder dip, arm lag, stance offset) and the verdicts they give against `FLOORS` - the same
floors `verify_asymmetry.gd` is handed by regress, so the bake and the engine judge on one number:

  stride_even   stride_m's index under STRIDE_INDEX - the no-skate invariant
  asymmetric    arm swing and shoulder dip indices over INDEX, and |lag +lat - lag -lat| over LAG.
                True for asym, and FALSE for zero and mirror: those two verdicts are the controls,
                recorded here so the day either one reads True the golden moves
  step_moved    step length's part, judged as the stance offset MOVING against zero's by more than
                STEP_M (the Figure's own feet plant 10 mm apart at asymmetry 0, so its step index is
                not zero on a symmetric build - rigify_human judges it the same way). False for
                mirror, which moves both feet the same way

regress reads these numbers back from THIS build's report, not from the golden, so the comparison is
always the same baked clip in both engines. The manifests carry the `variability` block a pipeline
build writes; the meter must not read it, and `verify_asymmetry.gd poison=1` proves it does not.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "FT_SCRIPTS")

BODY = "Figure"
ROLES = ("Idle", "Walk", "Run")
GAITS = ("Walk", "Run")
# unit draw on arm_swing, step_length, shoulder_dip, lag: +0.995, +0.654, -0.818, -0.880. Found by
# scanning `asym_meter_<k>` for the first ids whose draw clears 0.6 on all four channels.
IDENTITY = "asym_meter_169"
# (label, asymmetry, RA_ASYM_MIRROR)
CASES = (("asym", "SENSIBLE", False), ("zero", None, False), ("mirror", "SENSIBLE", True))
MEASURES = ("arm_swing_deg", "step_length_m", "stride_m", "shoulder_dip_m", "lag_cycles",
            "stance_offset_m", "frames")
# The verdicts' floors. What a symmetric Figure reads (zero and mirror, Walk and Run, Blender):
# arm swing index <= 0.0045, shoulder dip index <= 0.022 (the run's), |lag diff| <= 0.0061 cycles;
# at asymmetry 0.35 on IDENTITY: 0.20-0.25, 0.07-0.12 and 0.020-0.030. Each floor sits about twice
# the largest symmetric reading and well under the smallest asymmetric one. The symmetric lag is
# not zero because lag is taken over the clip as the engine plays it, whose duplicated last frame
# is held for one interval at phase 0 - where the two legs are half a cycle apart, so the hold
# bends their two Fourier phases differently (over the true cycle, lo..hi-1, a symmetric build
# reads 0.0012 at most; the engine never plays that cycle). STRIDE_INDEX: the
# Run's 14 keys put a foot's turnaround up to a key off its true extreme, and the asymmetric run
# reads 0.0099 in Blender for exactly that reason (walk: 0.0002-0.0013), so 0.02 - 1.9 cm on a
# 0.94 m stride, under a third of one key of swing-phase foot travel. STEP_M is rigify_human's.
FLOORS = {"INDEX": 0.04, "LAG": 0.012, "STRIDE_INDEX": 0.02, "STEP_M": 0.002}


def _verdicts(m, zero=None):
    arm, dip, lag, st = m["arm_swing_deg"], m["shoulder_dip_m"], m["lag_cycles"], m["stride_m"]
    out = {"stride_even": st["index"] < FLOORS["STRIDE_INDEX"],
           "lag_diff_cycles": round(lag["plus_lat"] - lag["minus_lat"], 5),
           "asymmetric": (arm["index"] > FLOORS["INDEX"] and dip["index"] > FLOORS["INDEX"]
                          and abs(lag["plus_lat"] - lag["minus_lat"]) > FLOORS["LAG"])}
    if zero is not None:
        out["stance_offset_moved_m"] = round(m["stance_offset_m"] - zero["stance_offset_m"], 5)
        out["step_moved"] = abs(out["stance_offset_moved_m"]) > FLOORS["STEP_M"]
    return out


def build():
    import bpy
    H.clear_scene()
    from follow_through import samples
    from rig_analysis import actions, bodymap, export, variability

    made = samples.build_bodies(rig=True, walk=False, rig_anything=H.scripts("RA_SCRIPTS"))
    rig = made["bodies"][BODY]["rig"]
    window = bpy.context.window
    previous, window.scene = window.scene, bpy.data.scenes[made["scene"]]
    cases, clips = {}, {}
    try:
        fps = bpy.context.scene.render.fps
        for label, dial, mirror in CASES:
            v = None
            if dial:
                v = variability.resolve({"asymmetry": getattr(variability, dial)}, IDENTITY)
            was = os.environ.get("RA_ASYM_MIRROR")
            if mirror:
                os.environ["RA_ASYM_MIRROR"] = "1"
            try:
                moves = actions.move_set(rig, prefix="%s_%s" % (BODY, label), roles=ROLES,
                                         variability=v)
            finally:
                if mirror:
                    os.environ.pop("RA_ASYM_MIRROR", None)
                    if was is not None:
                        os.environ["RA_ASYM_MIRROR"] = was
            if "error" in moves:
                raise RuntimeError("move_set %s: %s" % (label, moves["error"]))
            out = os.path.join(H.out_dir(), label)
            os.makedirs(out, exist_ok=True)
            char = export.export_character(BODY, rig, os.path.join(out, "asym_%s.glb" % label),
                                           name="%s %s" % (BODY, label), reports=moves, roles=ROLES,
                                           loops=ROLES, gaits=GAITS, forward="-Y", review=False,
                                           extra={"variability": v} if v else None)
            if "error" in char:
                raise RuntimeError("export %s: %s" % (label, char["error"]))
            measured = {}
            for role in GAITS:
                m = variability.measure(rig, moves[role]["action"])
                if "error" in m or "skipped" in m:
                    raise RuntimeError("measure %s %s: %s" % (label, role, m))
                clips[(label, role)] = moves[role]["action"]
                measured[role] = {"clip": moves[role]["action"],
                                  "passed": moves[role].get("passed"),
                                  "failures": moves[role].get("failures", [])[:3],
                                  "drawn": (moves[role].get("variability") or {}).get("plus_lat"),
                                  **{k: m.get(k) for k in MEASURES}}
            cases[label] = {"resolved": v, "measured": measured,
                            "moves_json": H.moves_manifest(char)}
        # the side-swap control: the asym clips, measured with +lat and -lat exchanged
        bm = bodymap.build(rig, forward="-Y", up="Z")
        bm = dict(bm, lat=-bm["lat"])
        cases["swap"] = {"measured": {}}
        for role in GAITS:
            m = variability.measure(rig, clips[("asym", role)], bm=bm)
            cases["swap"]["measured"][role] = {"clip": clips[("asym", role)],
                                               **{k: m.get(k) for k in MEASURES}}
    finally:
        window.scene = previous
    for label, c in cases.items():
        for role, m in c["measured"].items():
            m["verdicts"] = _verdicts(m, cases["zero"]["measured"][role] if label != "zero" else None)
    for role in GAITS:
        a, s = cases["asym"]["measured"][role], cases["swap"]["measured"][role]
        s["verdicts"]["ratios_inverted"] = all(
            abs(a[k]["ratio"] * s[k]["ratio"] - 1.0) < 1e-3
            for k in ("arm_swing_deg", "step_length_m", "stride_m", "shoulder_dip_m"))
        s["verdicts"]["stance_offset_flipped"] = (a["stance_offset_m"] * s["stance_offset_m"] < 0.0
                                                 and abs(a["stance_offset_m"] + s["stance_offset_m"]) < 1e-4)
    return {"identity": IDENTITY, "dial": variability.SENSIBLE, "fps": fps, "floors": FLOORS,
            "cases": H.stable(cases)}


H.run("asym_meter", build)
