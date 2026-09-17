"""A character built from a spec alone: character-pipeline end to end (improvements 01).

The spec is `mpfb_woman_curvy`'s woman given flesh and Belle's two garment presets. `runner.build`
takes it through body, bake, flesh, moves, garments and export, and saves the .blend. Then:

- a second `build` in the same session skips every stage as unchanged;
- a garment bound to the rig makes the moves stage refuse, naming the order;
- a spec that still names the removed `export.height` is rejected;
- a second Blender opens the saved .blend and runs the export stage alone (`from_stage="export"`,
  forced): the manifest it writes must equal the first one - the fresh-session resume 01 asks for.

The golden holds the stage statuses, what each stage reports that a person would check (the body's
stature, moves passed, flesh regions, garments passed and what they hide), the manifest as
`moves_manifest` holds it, and the Idle clip's standing height, which `height_m.stand` must equal.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS")
# the pipeline finds its plugins through these variables (else the installed copies); point them at
# the checkout under test, for this process and the second Blender alike
for _var in ("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS"):
    os.environ[_var] = H.scripts(_var)

SPEC = '''
[character]
id = "fixwoman"
name = "FixWoman"

[body]
sex = "female"
age = 28
stature = 1.70
build = "curvy"
seed = 7
style = "realistic"
firmness = 0.4
skin = [0.62, 0.45, 0.36]

[moves]
gaits = { Walk = 0.2, Run = 2.0 }
style = "adult"
stance_width = 1.0

[flesh]
types = ["breast", "butt"]

[[outfit]]
preset = "sports_top"

[[outfit]]
preset = "shorts_mid_thigh"

[export]
dir = "assets/fixwoman"
res_dir = "res://assets/fixwoman"
blend = "fixwoman.blend"
'''


def _statuses(report):
    return {k: v["status"] for k, v in report.items() if isinstance(v, dict) and "status" in v}


def _idle_stand(ch):
    from rig_analysis import stored
    return (stored.load(ch.rig, roles=["Idle"]).get("Idle") or {}).get("standing_height_m")


def _second_blender(blend, spec_path, out_json):
    code = (
        "import sys, json; sys.path[:0] = %r\n"
        "from character_pipeline import runner\n"
        "r = runner.build(%r, from_stage='export', force=True, save=False, log=lambda m: None)\n"
        "json.dump({k: v['status'] for k, v in r.items()}, open(%r, 'w'))\n"
    ) % ([H.scripts(v) for v in ("CP_SCRIPTS",)], spec_path, out_json)
    import bpy
    proc = subprocess.run([bpy.app.binary_path, "-b", blend, "--factory-startup", "--python-exit-code", "1",
                           "--python-expr", code], capture_output=True, text=True, env=dict(os.environ))
    return proc.returncode, "\n".join((proc.stdout or "").splitlines()[-8:])


def build():
    import bpy
    H.clear_scene()
    from character_pipeline import runner, spec, stages

    root = os.path.join(H.out_dir(), "pipeline_woman")
    os.makedirs(os.path.join(root, "characters"), exist_ok=True)
    spec_path = os.path.join(root, "characters", "fixwoman.toml")
    with open(spec_path, "w", encoding="utf-8") as fh:
        fh.write(SPEC)
    ch = spec.load(spec_path)
    ch.export.blend = os.path.join(root, "fixwoman.blend")

    first = runner.build(ch, save=True, log=lambda m: None)
    again = runner.build(ch, save=False, log=lambda m: None)

    # moves after garments: refused, with the order
    refused = None
    try:
        runner.build(ch, from_stage="moves", to_stage="moves", force=True, save=False, log=lambda m: None)
    except stages.StageRefused as exc:
        refused = str(exc)

    # export.height was removed (one convention: the Idle clip's standing height)
    height_field = None
    try:
        import tomllib
        spec.parse(tomllib.loads(SPEC.replace("[export]", '[export]\nheight = "mesh"')))
    except spec.SpecError as exc:
        height_field = str(exc)

    manifest_path = first["export"]["report"]["moves"]
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    before = json.dumps(manifest, sort_keys=True)

    statuses_path = os.path.join(root, "second_blender.json")
    code, tail = _second_blender(ch.export.blend, spec_path, statuses_path)
    fresh = {"exit": code}
    if code == 0 and os.path.isfile(statuses_path):
        with open(statuses_path, encoding="utf-8") as fh:
            fresh["statuses"] = json.load(fh)
        with open(manifest_path, encoding="utf-8") as fh:
            fresh["manifest_equal"] = json.dumps(json.load(fh), sort_keys=True) == before
    else:
        fresh["tail"] = tail

    moves = first["moves"]["report"]
    garments = first["garments"]["report"]["garments"]
    flesh = first["flesh"]["report"]
    return {
        "stages": _statuses(first),
        "rerun": _statuses(again),
        "refused": refused,
        "height_field": height_field,
        "body_stature": first["body"]["report"].get("stature"),
        "idle_standing_height_m": _idle_stand(ch),
        "moves": {role: {"passed": r["passed"], "failures": r["failures"], "drop_m": r.get("drop_m")}
                  for role, r in moves.items()},
        "flesh_regions": sorted("%s %s" % (g["name"], g["type"])
                                for g in bpy.data.objects[ch.mesh]["follow_through"]["jiggle"]["regions"]),
        "flesh_limits_m": flesh.get("limits_m"),
        "garments": {name: {"passed": g.get("passed"), "verts": g.get("verts"),
                            "jiggle_groups": g.get("jiggle_groups")} for name, g in garments.items()},
        "manifest": H.moves_manifest({"manifest": manifest, "problems": first["export"]["report"].get("problems")}),
        "fresh_session": fresh,
    }


H.run("pipeline_woman", build)
