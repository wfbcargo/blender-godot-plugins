"""A cricket built, detected, rigged, skinned, walked, jumped and exported - no .blend.

The rabbit fixture's pipeline on `hopper_samples.cricket`, which takes the other branch of the
hopper path: `hoppers.detect` has to find six legs and call the body `orthopteran`, every joint is
visible on the skin (scored against the sample's known joints), and `hop.move_set` writes Idle,
Walk and the three jump clips instead of Hop and Bound. `hop.export_creature` writes the glb, or
refuses and reports every clip's checks.

The sample's own voxel (0.00022) is kept: the remesh is most of the run (about 105 s of 125 s
alone, 190 s beside another build under `--jobs 2`), which is not far past the rabbit's 140 s, so
there was no reason to coarsen it and move what detection sees. At that voxel every joint lands
within 1.2 mm of the truth on a 30 mm body.

When it was recorded the export was refused: `JumpLand` fails because the fore feet slide 0.5 mm
after touching down (the limit is 1.2% of body size), so the golden holds the refusal and every
clip's checks. A fix that lets the cricket export moves `export` and fills `manifest`.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS")


def build():
    import bpy
    H.clear_scene()
    from rig_analysis import hop, hopper_samples, hoppers

    ob = hopper_samples.cricket()
    detection = hoppers.detect(ob.name)
    if "error" in detection:
        raise RuntimeError(detection["error"])
    scored = hoppers.score(detection, hopper_samples.truth(ob.name))

    built = hoppers.build(ob.name, detection=detection)
    rig = built["rig"] if isinstance(built, dict) and "rig" in built else ob.name + "_rig"
    skinned = hoppers.skin(rig)
    moves = hop.move_set(rig)

    out = os.path.join(H.out_dir(), "cricket")
    os.makedirs(out, exist_ok=True)
    exported = hop.export_creature(ob.name, rig, moves, os.path.join(out, "cricket.glb"), "cricket")
    # A refused export reports every clip's checks; a successful one reports the file it wrote
    # and puts the checks in the manifest beside it. The golden wants them either way.
    manifest_path = os.path.join(out, "cricket.moves.json")
    manifest = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            written = json.load(fh)
        manifest = {k: written.get(k) for k in ("clips", "loops", "implied_speed_mps", "height_m",
                                                "body_m", "gaits", "contacts", "hop", "verified")}

    return {
        "roles": H.roles(rig),
        "mesh": {"vertices": len(ob.data.vertices),
                 "dimensions": [round(x, 5) for x in ob.dimensions]},
        "detection": {"kind": detection["kind"], "kind_guessed": detection["kind_guessed"],
                      "hind_over_others": detection.get("hind_over_others"),
                      "legs": {l["name"]: {"joints": len(l["joints"]),
                                           "segments": [[s["role"], s["length"]] for s in l["segments"]]}
                               for l in detection["legs"]},
                      "warnings": detection.get("warnings")},
        "joint_error_vs_truth": H.stable(scored),
        "rig": {"bones": len(bpy.data.objects[rig].data.bones)},
        "skin": H.stable(skinned),
        "moves": {role: H.stable(report) for role, report in moves.items()},
        "export": H.stable(exported),
        "manifest": H.stable(manifest),
    }


H.run("cricket", build)
