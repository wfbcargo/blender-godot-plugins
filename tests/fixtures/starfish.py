"""A sea star built, detected, rigged, skinned, crawled and exported - no .blend.

Exercises the radial path end to end: `radial_samples.starfish` makes one connected metaball skin,
`radial.detect` finds the hub and its arms, `radial.build`/`skin` rig and weight it without bone
heat, `radial_moves.move_set` writes Crawl and Idle, and `radial_moves.export_creature` writes the
glb and the `.moves.json` with its `radial` block.

`kind="asteroid"` is passed: the kind normally comes from looking at renders, which a fixture cannot
do. What detection would have guessed on its own is reported beside it (`kind_suggested`).

The sample is built at the world origin, resting on the floor, which is where `radial.detect` and
`build` expect a body - so nothing is moved before export.

`radial.skin` reports `coverage` as a constant 1.0, so the fixture also counts the vertices that
actually carry weight (`skin.measured_coverage`).
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS")


def _measured_coverage(obj, rig):
    """Share of vertices with some weight on a bone of `rig`."""
    bones = {b.name for b in rig.data.bones}
    index = {g.index for g in obj.vertex_groups if g.name in bones}
    covered = sum(1 for v in obj.data.vertices if any(g.group in index and g.weight > 0.0 for g in v.groups))
    return round(covered / float(max(1, len(obj.data.vertices))), 5)


def build():
    import bpy
    H.clear_scene()
    from rig_analysis import radial, radial_moves, radial_samples

    ob = radial_samples.starfish()
    detection = radial.detect(ob.name, kind="asteroid")
    if "error" in detection:
        raise RuntimeError(detection["error"])

    built = radial.build(ob.name, detection=detection)
    if "error" in built:
        raise RuntimeError(built["error"])
    rig = built["rig"]
    skinned = radial.skin(rig)
    if isinstance(skinned, dict) and "error" not in skinned:
        skinned = dict(skinned, measured_coverage=_measured_coverage(ob, bpy.data.objects[rig]))
    moves = radial_moves.move_set(rig)

    out = os.path.join(H.out_dir(), "starfish")
    os.makedirs(out, exist_ok=True)
    exported = radial_moves.export_creature(ob.name, rig, moves, os.path.join(out, "starfish.glb"),
                                            "starfish")
    # A refused export carries the manifest it would have written; a successful one writes it
    # beside the glb. The golden wants it either way.
    manifest_path = os.path.join(out, "starfish.moves.json")
    manifest = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            written = json.load(fh)
        manifest = {k: written.get(k) for k in ("clips", "loops", "body_m", "radial", "verified")}

    arms = sorted(detection["appendages"], key=lambda ap: ap["theta"] % (2 * math.pi))
    thetas = [math.degrees(ap["theta"] % (2 * math.pi)) for ap in arms]
    gaps = [(thetas[(i + 1) % len(thetas)] - thetas[i]) % 360.0 for i in range(len(thetas))]
    return {
        "mesh": {"vertices": len(ob.data.vertices),
                 "dimensions": [round(x, 5) for x in ob.dimensions],
                 "location": [round(x, 6) for x in ob.location]},
        "detection": {"kind": detection["kind"], "kind_guessed": detection["kind_guessed"],
                      "kind_suggested": detection.get("kind_suggested"),
                      "order": detection["order"], "symmetry_score": detection.get("symmetry_score"),
                      "oral_source": detection.get("oral_source"),
                      "R_hub": detection["R_hub"], "hub_height": detection["hub_height"],
                      "fineness": detection["fineness"], "hub_vertices": len(detection["hub_ids"]),
                      "rigid": len(detection["rigid"]),
                      "arms": {ap["name"]: {"role": ap["role"], "theta_deg": math.degrees(ap["theta"]),
                                            "length": ap["length"], "width": ap["width"],
                                            "root_r": ap["root_r"], "loose": ap["loose"],
                                            "vertices": len(ap["ids"])}
                               for ap in arms},
                      "arm_gaps_deg": gaps,
                      "notes": detection.get("notes"), "warnings": detection.get("warnings")},
        "rig": built,
        "skin": H.stable(skinned),
        "moves": {role: H.stable(report) for role, report in moves.items()},
        "export": H.stable(exported),
        "manifest": H.stable(manifest),
    }


H.run("starfish", build)
