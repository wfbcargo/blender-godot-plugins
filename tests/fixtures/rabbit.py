"""A rabbit built, detected, rigged, skinned, hopped and exported - no MPFB, no .blend.

Exercises the hopper path end to end: `hopper_samples.rabbit` makes the mesh, `hoppers.detect`
finds the legs and their joints (scored against the sample's known joints, which is the one
check here that knows the right answer), `hoppers.build`/`skin` rig it, `hop.move_set` writes
Idle, Hop, Bound and the three jump clips, and `hop.export_creature` writes the glb and reads
its durations back.
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

    ob = hopper_samples.rabbit()
    detection = hoppers.detect(ob.name)
    if "error" in detection:
        raise RuntimeError(detection["error"])
    scored = hoppers.score(detection, hopper_samples.truth(ob.name))

    built = hoppers.build(ob.name, detection=detection)
    rig = built["rig"] if isinstance(built, dict) and "rig" in built else ob.name + "_rig"
    skinned = hoppers.skin(rig)
    moves = hop.move_set(rig)

    out = os.path.join(H.out_dir(), "rabbit")
    os.makedirs(out, exist_ok=True)
    exported = hop.export_creature(ob.name, rig, moves, os.path.join(out, "rabbit.glb"), "rabbit")
    # A refused export reports every clip's checks; a successful one reports the file it wrote
    # and puts the checks in the manifest beside it. The golden wants them either way.
    manifest_path = os.path.join(out, "rabbit.moves.json")
    manifest = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            written = json.load(fh)
        manifest = {k: written.get(k) for k in ("clips", "loops", "implied_speed_mps", "height_m",
                                                "body_m", "gaits", "contacts", "hop", "verified")}

    return {
        "mesh": {"vertices": len(ob.data.vertices),
                 "dimensions": [round(x, 4) for x in ob.dimensions]},
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


H.run("rabbit", build)
