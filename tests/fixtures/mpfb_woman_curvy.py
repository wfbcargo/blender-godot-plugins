"""A woman from a brief, baked, walked, run and exported - humanform and rig-anything together.

The path every person in `grungist-creek/assets/humans` takes, on one seeded brief: ANSUR fit
through MPFB2 (`humanform.pipeline`), `bake_for_game` (shape keys and the helper mask down to one
skinned mesh with at most four weights a vertex), `actions.move_set` for Idle, Walk and Run with
the hip drop capped and an upper body solved inside each clip, then rig-anything's exporter, which
re-checks every clip on playback and reads the written durations back.

The library is not consulted: a fixture must build the same body on a machine that has never seen
it, so `use_library=False` and every fit is fresh.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "HF_SCRIPTS")

NAME = "FixWoman"
BRIEF = dict(name=NAME, sex="female", age=28, stature=1.70, build="curvy", seed=7, style="realistic",
             firmness=0.4, skin=(0.62, 0.45, 0.36))
# The hip drop cap and the Froude number per gait, as assets/humans/build_human.py passes them.
STYLE = {"walk": {"max_drop": 0.035}, "run": {"max_drop": 0.07}}
GAITS = {"Walk": 0.2, "Run": 2.0}
STANCE_WIDTH = 1.0


def build():
    import bpy
    H.clear_scene()
    import rig_analysis  # noqa: F401
    from rig_analysis import actions as ra_actions, export as ra_export
    import humanform  # noqa: F401
    from humanform import pipeline, sheet

    rig, body = NAME + "_rig", NAME + "_body"
    made = pipeline.make(sheet.new(**BRIEF), use_library=False)

    baked = ra_export.bake_for_game(NAME, rig, name=body)
    if "error" in baked:
        raise RuntimeError("bake: " + baked["error"])
    bpy.data.objects[rig].data.pose_position = "POSE"
    mesh = bpy.data.objects[body]
    unweighted = sum(1 for v in mesh.data.vertices if not any(g.weight > 1e-4 for g in v.groups))

    held = {"style": STYLE, "stance_width": STANCE_WIDTH, "posture": None}
    options = {"Idle": dict(held)}
    for role, froude in GAITS.items():
        options[role] = dict(held, froude=froude)
    # Crouch and CrouchWalk are here because they are where an MPFB body goes wrong: its ground
    # root bone lies on the floor and carries no skin, and a crouch that takes it for the belly
    # drops no hips at all. Jump is here because it used to put a toe through the floor at the
    # one frame between its load and its launch (05's 5.1), and exports unforced now.
    # TurnL and TurnR turn 90 degrees on the spot about a planted foot's ball (rig-anything 0.24.0):
    # the floor-skid check follows the pivot and the stepping foot through every frame.
    roles = ("Idle",) + tuple(GAITS) + ("Crouch", "CrouchWalk", "Jump", "TurnL", "TurnR")
    moves = ra_actions.move_set(rig, prefix=NAME, roles=roles, options=options)
    if "error" in moves:
        raise RuntimeError("move_set: " + moves["error"])

    out = os.path.join(H.out_dir(), "mpfb_woman_curvy")
    os.makedirs(out, exist_ok=True)
    # Through export_character, which writes fixwoman.moves.json for `--godot`. Its defaults are what
    # this fixture used to pass by hand: the feet are the legs' end bones, Crouch and Jump hold their
    # last pose (no loop seam) while the rest loop, and Walk and Run (the `cycle` reports) are the gaits.
    char = ra_export.export_character(body, rig, os.path.join(out, NAME.lower() + ".glb"), name=NAME,
                                      reports={r: moves[r] for r in roles}, forward="-Y")
    exported = char.get("export", {})
    loco = {"collider": char["manifest"]["collider"], "gaits": char["manifest"]["gaits"],
            "problems": char["problems"]} if "manifest" in char else {"problems": [char["error"]]}

    # the relaxed hand every clip poses (`keyposes.hand_digits`): which bones curl, by how much, found
    # from the skeleton's shape - a change in which bone reads as the thumb shows here
    from rig_analysis import bodymap as ra_bodymap, keyposes as ra_kp, motion as ra_motion
    poser = ra_kp.Poser(ra_motion.Body(bpy.data.objects[rig], ra_bodymap.build(rig, forward="-Y")))
    hands = {arm: [[n, deg] for n, _, deg in digits] for arm, digits in sorted(poser.hands.items())}

    eyes = bpy.data.objects.get(NAME + "_eyes")
    return {
        "roles": H.roles(rig),
        # The order faces are stored in, which no measurement sees: humanform's eyes came out
        # shuffled in every process until 5.7, and a body that joins them inherits it. Under
        # `--twice` a change here is NONDETERMINISTIC.
        "structure": {"eyes_faces": H.face_order(eyes) if eyes else None,
                      "body_faces": H.face_order(mesh)},
        "fit": {"ansur": H.stable(made.get("ansur")), "macros": H.stable(made.get("macros")),
                "notes": made.get("notes"), "check": H.stable(made.get("check"))},
        "bake": {"vertices": len(mesh.data.vertices), "groups": len(mesh.vertex_groups),
                 "unweighted": unweighted, "height_m": round(max((mesh.matrix_world @ v.co).z
                                                                 for v in mesh.data.vertices), 4),
                 "report": H.stable(baked)},
        "moves": {role: H.stable(moves[role]) for role in roles},
        "hands": hands,
        "export": H.stable(exported),
        "review": H.review_sheet(exported.get("review")),
        "engine": {"collider": H.stable(loco.get("collider")), "gaits": H.stable(loco.get("gaits")),
                   "problems": loco.get("problems")},
        "moves_json": H.moves_manifest(char),
        "skin_export": _skin_export(os.path.join(out, NAME.lower() + ".glb")),
    }


def _skin_export(glb):
    """The skin as the glb carries it. This body is exported without a bake, so its skin must still be the
    brief's tone as baseColorFactor, and no helper attribute may ride along as a vertex colour: a procedural
    material and a colour attribute once exported as a factorless material and COLOR_0/1, white in Godot."""
    import json as _json
    import struct
    if not os.path.exists(glb):
        return {"missing": True}
    with open(glb, "rb") as fh:
        b = fh.read()
    g = _json.loads(b[20:20 + struct.unpack_from("<I", b, 12)[0]])
    m = next((x for x in g.get("materials", []) if x["name"] == NAME + "_skin"), None)
    if m is None:
        return {"material": None}
    pbr = m.get("pbrMetallicRoughness", {})
    return {"baseColorFactor": [round(v, 4) for v in pbr.get("baseColorFactor", [1, 1, 1, 1])],
            "baseColorTexture": "baseColorTexture" in pbr,
            "colour_sets": sorted({k for me in g["meshes"] for p in me["primitives"] for k in p["attributes"]
                                   if k.startswith("COLOR_")})}


H.run("mpfb_woman_curvy", build)
