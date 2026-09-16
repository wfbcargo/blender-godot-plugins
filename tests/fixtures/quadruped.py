"""A dog built, fitted with Rigify's basic_quadruped, bound, walked, trotted, run, crouched and
exported - no .blend.

`quadruped_samples.dog` makes the mesh, and `measure.analyze` has to see exactly four ground
contacts in it. `fit.fit_basic_quadruped` fits the metarig (Rigify off, as `--factory-startup`
leaves it - the fitter turns it on), and its leg joints are scored against the sample's known ones,
the one check here that knows the right answer. `skin.bind` binds it with bone heat, as SKILL.md's
quadruped path does, `actions.move_set` authors Idle, Walk, Trot, Run and Crouch, and
`export.export` re-checks every clip on playback and reads the written durations back.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS")

ROLES = ("Idle", "Walk", "Trot", "Run", "Crouch")
GAITS = ("Walk", "Trot", "Run")
LOOPS = ("Idle", "Walk", "Trot", "Run")
HEAD_AT = -0.6            # the muzzle's forward coordinate - a person reads it off the renders
# truth key -> the metarig bones whose heads are that leg's joints, root to tip
LEG_BONES = {"front": ("front_thigh", "front_shin", "front_foot", "front_toe"),
             "rear": ("thigh", "shin", "foot", "toe")}
FOOT_BONES = ["front_foot.L", "front_foot.R", "foot.L", "foot.R"]
HEADLINE = ("passed", "failures", "hip_drop_m", "max_drop_m", "drop_limited_by", "balance",
            "stride_m", "implied_speed_playback_mps", "planted_drift", "stance_slip", "loop_seam",
            "lowest_point", "skin_lowest", "tightest_joint_degrees")


def score(rig, truth):
    """Distance from each fitted joint to the sample's, per leg, root to tip."""
    out = {}
    for key, joints in sorted(truth.items()):
        rank, side = key.split(".")
        errs = []
        for bone, want in zip(LEG_BONES[rank], joints):
            b = rig.data.bones[bone + "." + side]
            errs.append(((rig.matrix_world @ b.head_local) - want).length)
        out[key] = {"per_joint": [round(e, 5) for e in errs], "mean": sum(errs) / len(errs),
                    "worst": max(errs)}
    every = [e for v in out.values() for e in v["per_joint"]]
    out["all"] = {"mean": sum(every) / len(every), "worst": max(every)}
    return out


def build():
    import bpy
    H.clear_scene()
    from rig_analysis import actions, export, fit, measure, quadruped_samples, skin

    ob = quadruped_samples.dog()
    # the rest mesh's extent - `ob.dimensions` would be the evaluated one, posed by whatever clip
    # is active when the report is written
    rest_size = [round(max(v.co[i] for v in ob.data.vertices) - min(v.co[i] for v in ob.data.vertices), 4)
                 for i in range(3)]
    analysis = measure.analyze(ob.name)
    contacts = analysis["ground_contacts"]
    if contacts["count"] != 4:
        raise RuntimeError("the dog has %d ground contacts, not 4 (%s)" % (contacts["count"], contacts["hint"]))

    fitted = fit.fit_basic_quadruped(ob.name, head_at=HEAD_AT)
    if "error" in fitted:
        raise RuntimeError("fit: " + fitted["error"])
    rig = bpy.data.objects[fitted["rig"]]
    joints = score(rig, quadruped_samples.truth(ob.name))

    bound = skin.bind(ob.name, rig.name)
    if "error" in bound:
        raise RuntimeError("bind: " + bound["error"])

    moves = actions.move_set(rig.name, prefix="Dog", roles=ROLES)
    if "error" in moves:
        raise RuntimeError("move_set: " + moves["error"])

    out = os.path.join(H.out_dir(), "quadruped")
    os.makedirs(out, exist_ok=True)
    exported = export.export(ob.name, rig.name, os.path.join(out, "dog.glb"), foot_bones=FOOT_BONES,
                             actions=[moves[r]["action"] for r in ROLES],
                             loop_clips=[moves[r]["action"] for r in LOOPS],
                             gaits=[moves[r]["action"] for r in GAITS], forward="-Y")

    return {
        "mesh": {"vertices": len(ob.data.vertices), "rest_size": rest_size},
        "ground_contacts": {"count": contacts["count"], "raw": contacts["raw_contacts"],
                            "midline": contacts["midline_contacts"],
                            "positions": sorted(H.stable([c["position"] for c in contacts["clusters"]]))},
        "fit": H.stable({k: v for k, v in fitted.items() if k != "rig"}),
        "joint_error_vs_truth": H.stable(joints),
        "bind": H.stable({k: bound.get(k) for k in ("coverage", "vertex_groups", "deform_bones",
                                                     "bones_without_group", "passed")}),
        "headline": {role: H.stable({k: moves[role].get(k) for k in HEADLINE if k in moves[role]})
                     for role in ROLES},
        "moves": {role: H.stable(moves[role]) for role in ROLES},
        "export": {"exported": exported.get("exported"), "stage": exported.get("stage"),
                   "note": exported.get("note"), "verified": H.stable(exported.get("verified")),
                   "clips": H.stable({n: {k: c.get(k) for k in ("passed", "failures", "loops",
                                                                "locomotion", "engine_duration_s",
                                                                "implied_speed_playback_mps")}
                                      for n, c in (exported.get("clips") or {}).get("clips", {}).items()}),
                   "failing": H.stable((exported.get("clips") or {}).get("failing")),
                   "preflight": H.stable(exported.get("preflight"))},
    }


H.run("quadruped", build)
