"""Muscle definition, build quality and build timing through character-pipeline, and rebuilding a changed
`[hair]` or `[muscle]` without stacking it.

A lean muscular man (Dante's brief with no forced muscle macro) is built from a spec with `[muscle] output =
"geometry"`, `[hair] preset = "bun"` and `[build] quality = "draft"`. Then, in the same session, as a person
editing the spec would:

- the muscle stage's report: per-group weights from the brief, the body-fat estimate, the fitted macro, the
  composite spike humanform's facet guard holds down, and the `hfd:muscle` keys `bake_for_game` baked;
- the build record: `stage_seconds` names every stage that ran, and the same record is in the manifest's
  `build` block and the .blend's `character_pipeline:<id>:build` text (the seconds themselves are volatile);
- `[hair]` changed to `short_crop` and the whole spec rebuilt: the runner restarts from body instead of
  refusing, and the body carries one hair layer (the vertex count equals a fresh short_crop build's);
- `[muscle] output = "normal"`: restarted again, the bake stage bakes the high copy into the skin's normal
  map (matched, at the draft's 512 px) and removes the high copy;
- `[muscle]` dropped: restarted, and the body no longer carries definition;
- a hair-only rebuild started at the hair stage still refuses (the documented order);
- spec refusals for the new fields, and the quality table.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS", "LD_SCRIPTS")
for _var in ("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS", "LD_SCRIPTS"):
    os.environ[_var] = H.scripts(_var)

SPEC = '''
[character]
id = "fixdante"
name = "FixDante"

[body]
sex = "male"
age = 27
stature = 1.91
build = "muscular"
seed = 3
firmness = 0.9
skin = [0.3, 0.18, 0.11]

[muscle]
output = "geometry"

[hair]
preset = "bun"
colour = [0.1, 0.07, 0.05]

[moves]
gaits = { Walk = 0.2 }
style = "brisk"
stance_width = 1.13

[build]
quality = "draft"

[review]
enabled = false

[export]
dir = "assets/fixdante"
res_dir = "res://assets/fixdante"
'''


def _statuses(report):
    return {k: v["status"] for k, v in report.items() if isinstance(v, dict) and "status" in v}


def _body(ch):
    import bpy
    from character_pipeline import stages
    ob = bpy.data.objects[ch.mesh]
    return {"verts": len(ob.data.vertices), "haired": stages.haired(ch), "muscled": stages.muscled(ch),
            "cp_muscle": ob.get("cp_muscle"),
            "hair_materials": sorted(m.name for m in ob.data.materials if m and "hair" in m.name.lower()),
            "images": sorted(i.name for i in bpy.data.images if "muscle" in i.name.lower()),
            "high_left": bpy.data.objects.get(ch.name + "_muscle_high") is not None,
            "skin_textures": sorted(n.image.name for m in ob.data.materials if m and m.node_tree
                                    for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image)}


def build():
    import bpy
    import tomllib
    H.clear_scene()
    from character_pipeline import quality, runner, spec, stages

    root = os.path.join(H.out_dir(), "pipeline_muscle")
    os.makedirs(os.path.join(root, "characters"), exist_ok=True)
    spec_path = os.path.join(root, "characters", "fixdante.toml")
    with open(spec_path, "w", encoding="utf-8") as fh:
        fh.write(SPEC)
    base = tomllib.loads(SPEC)

    def variant(**sections):
        d = dict(base, **sections)
        for k in [k for k, v in d.items() if v is None]:
            del d[k]
        return spec.parse(d, spec_path)

    quiet = dict(save=False, log=lambda m: None)
    ch = spec.load(spec_path)
    first = runner.build(ch, **quiet)
    mu = first["muscle"]["report"]
    muscle = {k: mu[k] for k in ("output", "groups", "weights", "body_fat_pct", "muscle_term", "definition_total",
                                 "fitted_muscle", "spike_um", "spike_limit_um", "max_mm")}
    with open(os.path.join(ch.out_dir(), "fixdante.moves.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    rec = runner.build_record(ch)
    timing = {"stages_timed": sorted(first["build"]["stage_seconds"]), "quality": first["build"]["quality"],
              "manifest_quality": manifest.get("build", {}).get("quality"),
              "manifest_stages_timed": sorted(manifest.get("build", {}).get("stage_seconds", {})),
              "manifest_has_total": "total_seconds" in manifest.get("build", {}),
              "blend_record_same": rec == first["build"],
              "all_positive": all(v >= 0 for v in first["build"]["stage_seconds"].values())}
    built = _body(ch)
    again = runner.build(ch, **quiet)

    # [hair] changed: a whole build restarts from body, and the body carries one layer
    crop = variant(hair={"preset": "short_crop", "colour": [0.1, 0.07, 0.05]})
    r = runner.build(crop, **quiet)
    hair_change = {"statuses": _statuses(r), "restarted": r["build"].get("restarted"), **_body(crop)}
    # from the hair stage the documented order still holds: no restart, a refusal
    bun = variant()
    try:
        runner.build(bun, from_stage="hair", to_stage="hair", **quiet)
        hair_change["from_hair_stage"] = None
    except stages.StageRefused as exc:
        hair_change["from_hair_stage"] = str(exc)

    # [muscle] output = "normal": restarted, baked into the skin's normal map
    normal = variant(hair={"preset": "short_crop", "colour": [0.1, 0.07, 0.05]}, muscle={"output": "normal"})
    r = runner.build(normal, **quiet)
    nm = r["bake"]["report"].get("muscle_normal") or {}
    muscle_normal = {"statuses": _statuses(r), "restarted": r["build"].get("restarted"),
                     "bake": {k: nm.get(k) for k in ("size", "method", "materials", "warnings")},
                     "output": r["muscle"]["report"]["output"], **_body(normal)}

    # [muscle] dropped: restarted, nothing carried
    plain = variant(hair={"preset": "short_crop", "colour": [0.1, 0.07, 0.05]}, muscle=None)
    r = runner.build(plain, **quiet)
    dropped = {"statuses": _statuses(r), "restarted": r["build"].get("restarted"), **_body(plain)}

    # a fresh short_crop body in its own file, to compare vertex counts with the rebuilt one
    H.clear_scene()
    for t in list(bpy.data.texts):
        bpy.data.texts.remove(t)
    fresh = runner.build(variant(hair={"preset": "short_crop", "colour": [0.1, 0.07, 0.05]}, muscle=None), **quiet)
    fresh_verts = len(bpy.data.objects[ch.mesh].data.vertices)
    hair_change["verts_equal_fresh_build"] = dropped["verts"] == fresh_verts
    dropped["fresh_statuses"] = _statuses(fresh)

    refusals = {}
    for label, patch in (("bad_output", {"muscle": {"output": "texture"}}),
                         ("bad_group", {"muscle": {"groups": ["glutes"]}}),
                         ("size_without_normal", {"muscle": {"normal_size": 1024}}),
                         ("size_not_pow2", {"muscle": {"output": "normal", "normal_size": 1000}}),
                         ("strength_range", {"muscle": {"strength": 3.0}}),
                         ("unknown_field", {"muscle": {"output": "geometry", "tone": 1}}),
                         ("blend_source", {"body": {"source": "blend", "object": "X"}}),
                         ("bad_quality", {"build": {"quality": "ultra"}})):
        try:
            spec.parse(dict(base, **patch))
            refusals[label] = None
        except spec.SpecError as exc:
            refusals[label] = str(exc)

    return {
        "stages": _statuses(first),
        "rerun": _statuses(again),
        "stage_names": [s[0] for s in stages.STAGES],
        "muscle": H.stable(muscle),
        "build_record": timing,
        "built": built,
        "hair_change": H.stable(hair_change),
        "muscle_normal": H.stable(muscle_normal),
        "muscle_dropped": H.stable(dropped),
        "refusals": refusals,
        "quality": {q: {p: quality.settings(q, p) for p in ("body", "review", "muscle", "hair")}
                    for q in quality.QUALITIES},
        "final_hash_part": {s: quality.for_hash("final", s) for s in ("body", "review", "moves")},
        "draft_hash_part_moves": quality.for_hash("draft", "moves"),
    }


H.run("pipeline_muscle", build)
