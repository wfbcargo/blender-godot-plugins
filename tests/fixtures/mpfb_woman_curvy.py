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
    from rig_analysis import actions as ra_actions, export as ra_export, locomotion as ra_loco
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
    roles = ("Idle",) + tuple(GAITS) + ("Crouch", "CrouchWalk", "Jump")
    moves = ra_actions.move_set(rig, prefix=NAME, roles=roles, options=options)
    if "error" in moves:
        raise RuntimeError("move_set: " + moves["error"])

    out = os.path.join(H.out_dir(), "mpfb_woman_curvy")
    os.makedirs(out, exist_ok=True)
    clips = [moves[r]["action"] for r in roles]
    held = ("Crouch", "Jump")                        # these hold their last pose, they do not loop
    loops = [moves[r]["action"] for r in roles if r not in held]
    exported = ra_export.export(body, rig, os.path.join(out, NAME.lower() + ".glb"),
                                foot_bones=["foot.L", "foot.R"], actions=clips, loop_clips=loops,
                                gaits=[moves[r]["action"] for r in GAITS], forward="-Y")
    loco = ra_loco.engine_manifest(rig, {r: moves[r] for r in GAITS}, forward="-Y", mesh_name=body)

    eyes = bpy.data.objects.get(NAME + "_eyes")
    return {
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
        "export": H.stable(exported),
        "engine": {"collider": H.stable(loco.get("collider")), "gaits": H.stable(loco.get("gaits")),
                   "problems": loco.get("problems")},
    }


H.run("mpfb_woman_curvy", build)
