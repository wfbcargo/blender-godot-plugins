"""A rabbit built, detected, rigged, skinned, hopped and exported - no MPFB, no .blend.

Exercises the hopper path end to end: `hopper_samples.rabbit` makes the mesh, `hoppers.detect`
finds the legs and their joints (scored against the sample's known joints, which is the one
check here that knows the right answer), `hoppers.build`/`skin` rig it, `hop.move_set` writes
Idle, Hop, Bound and the three jump clips, and `hop.export_creature` writes the glb and reads
its durations back.

Then the fresh session: the scene is saved to `rabbit.blend` and a second Blender opens it and
runs `_export_only.py`, which exports with no reports in hand - only what `move_set` stored on the
actions. `fresh_session.manifest_equal` says whether its `.moves.json` matches this session's.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS")


def _flat(value, prefix=""):
    """{dotted key: value}, leaving out path-like values - they name different files."""
    out = {}
    if isinstance(value, dict):
        for k, v in value.items():
            out.update(_flat(v, "%s.%s" % (prefix, k) if prefix else str(k)))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.update(_flat(v, "%s[%d]" % (prefix, i)))
    elif not (isinstance(value, str) and (os.path.isabs(value) or value.startswith("res://"))):
        out[prefix] = value
    return out


def fresh_session(mesh, rig, out, manifest_path):
    """Save the scene, export it again from a second Blender that never saw the reports, and
    compare the two manifests."""
    import bpy
    blend = os.path.join(out, "rabbit.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, copy=True)
    again = os.path.join(out, "fresh_session", "rabbit.glb")
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_export_only.py")
    proc = subprocess.run([bpy.app.binary_path, "-b", blend, "--factory-startup", "--python", helper,
                           "--", "kind=hop", "mesh=" + mesh, "rig=" + rig, "glb=" + again,
                           "creature=rabbit"],
                          capture_output=True, text=True, env=dict(os.environ))
    again_manifest = os.path.splitext(again)[0] + ".moves.json"
    if proc.returncode != 0 or not os.path.isfile(again_manifest):
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-8:]
        return {"manifest_equal": False, "error": "exit %d: %s" % (proc.returncode, " | ".join(tail))}
    with open(manifest_path, encoding="utf-8") as fh:
        first = _flat(json.load(fh))
    with open(again_manifest, encoding="utf-8") as fh:
        second = _flat(json.load(fh))
    differs = sorted(k for k in set(first) | set(second) if first.get(k, KeyError) != second.get(k, KeyError))
    result = {"manifest_equal": not differs}
    if differs:
        result["differs"] = differs[:10]
    return result


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
        "roles": H.roles(rig),
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
        "review": H.review_sheet(exported.get("review")),
        "manifest": H.stable(manifest),
        "fresh_session": (fresh_session(ob.name, rig, out, manifest_path) if os.path.isfile(manifest_path)
                          else {"manifest_equal": False, "error": "the first export wrote no manifest"}),
    }


H.run("rabbit", build)
