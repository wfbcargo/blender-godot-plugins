"""humanform's hair layer (improvements 05 5.2): every preset on one body, and the pipeline's hair stage.

A curvy MPFB woman from a spec is built through character-pipeline's body and bake stages. Then:

- each of `short_crop`, `bob`, `bun`, `ponytail` and `long_loose` is put on her with `hair.add` and taken off
  again, reporting what a person would check: the cap's feathered edge (the thickness and texture V at its
  geometric boundary - the edge lies on the skin in the transparent root zone, so there is no wall), the
  parts' sizes and their clearance from the skin, the follow-through strand contract where there is a
  strand, and the face order of every object made;
- the lookdev hair material is exported to a glb with the body (rig-anything's `export_glb`) and the glTF
  JSON read back: alpha MASK, a base colour and a normal texture, the `lookdev` extras Godot re-applies,
  and a hash of the strand texture's pixels;
- the spec's `[hair] preset = "ponytail"` runs the hair stage, which joins the hair and its strand into
  the body: the stage report, and the joined body's `ft_strand` group;
- `spec.GAPS` no longer lists hair, the deprecated `kind = "shell_bun"` still parses, and a bad preset or
  colour in a spec or a brief is refused.
"""
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS")
for _var in ("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS"):
    os.environ[_var] = H.scripts(_var)
# lookdev's Blender package is its `blender` folder, not `scripts`; the pipeline reads LD_SCRIPTS
os.environ.setdefault("LD_SCRIPTS", os.path.join(H.REPO, "plugins", "lookdev", "blender"))
sys.path.insert(0, os.environ["LD_SCRIPTS"])

SPEC = '''
[character]
id = "hairwoman"
name = "HairWoman"

[body]
sex = "female"
age = 30
stature = 1.68
build = "curvy"
seed = 11
style = "realistic"
skin = [0.62, 0.45, 0.36]

[moves]
gaits = { Walk = 0.2 }

[hair]
preset = "ponytail"
colour = [0.35, 0.22, 0.12]

[export]
dir = "assets/hairwoman"
res_dir = "res://assets/hairwoman"
'''

PRESETS = ("short_crop", "bob", "bun", "ponytail", "long_loose")


def _glb_json(path):
    with open(path, "rb") as fh:
        data = fh.read()
    n = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20:20 + n])


def _pixels_hash(name):
    import bpy
    import numpy as np
    img = bpy.data.images[name]
    px = np.empty(len(img.pixels), np.float32)
    img.pixels.foreach_get(px)
    return hashlib.sha1(np.round(px * 255).astype(np.uint8).tobytes()).hexdigest()[:12]


def _stable_rep(rep):
    lm = rep["landmarks"]
    out = {"landmarks": {k: lm[k] for k in ("head_bone", "top", "eye", "h", "cy", "ear_L", "ear_half_m", "chin",
                                            "eye_source")},
           "cap": rep["cap"], "parts": rep["parts"], "hair": rep["hair"], "objects": sorted(rep["objects"]),
           "material_source": rep["material"].get("source")}
    if "contract" in rep:
        out["contract"] = rep["contract"]
    return H.stable(out)


def build():
    import bpy
    import tomllib
    H.clear_scene()
    from character_pipeline import runner, spec, stages
    from humanform import hair, sheet

    root = os.path.join(H.out_dir(), "hair_presets")
    os.makedirs(os.path.join(root, "characters"), exist_ok=True)
    spec_path = os.path.join(root, "characters", "hairwoman.toml")
    with open(spec_path, "w", encoding="utf-8") as fh:
        fh.write(SPEC)
    ch = spec.load(spec_path)
    runner.build(ch, to_stage="bake", save=False, log=lambda m: None)
    body = bpy.data.objects[ch.mesh]

    presets = {}
    glb = {}
    for preset in PRESETS:
        rep = hair.add(ch.mesh, preset=preset, colour=(0.35, 0.22, 0.12), name=ch.name)
        made = [bpy.data.objects[n] for n in rep["objects"].values()]
        entry = _stable_rep(rep)
        entry["face_order"] = {o.name: H.face_order(o) for o in made}
        presets[preset] = entry
        if preset == "ponytail":
            from rig_analysis import export as ra_export
            path = os.path.join(root, "hair_material.glb")
            w = ra_export.export_glb(path, [ch.mesh, ch.rig] + [o.name for o in made], actions=[], rig_name=ch.rig)
            j = _glb_json(w["file"])
            mat = next(m for m in j["materials"] if m["name"] == f"{ch.name}_hair")
            glb = {"alphaMode": mat.get("alphaMode"), "alphaCutoff": mat.get("alphaCutoff", 0.5),
                   "base_colour_texture": "baseColorTexture" in mat.get("pbrMetallicRoughness", {}),
                   "normal_texture": "normalTexture" in mat, "extras": mat.get("extras"),
                   "extensions": sorted(mat.get("extensions", {})), "images": len(j.get("images", [])),
                   "strand_nodes": sorted(n.get("name") for n in j["nodes"] if (n.get("extras") or {}).get("ft_type")),
                   "strand_extras_keys": sorted(next((n["extras"] for n in j["nodes"]
                                                      if (n.get("extras") or {}).get("ft_type")), {}))}
            glb["texture_hash"] = _pixels_hash(f"{ch.name}_hair_strands")
            glb["normal_hash"] = _pixels_hash(f"{ch.name}_hair_strands_normal")
        for o in made:
            bpy.data.objects.remove(o, do_unlink=True)

    staged = runner.build(ch, from_stage="hair", to_stage="hair", save=False, log=lambda m: None)
    hr = staged["hair"]["report"]
    body = bpy.data.objects[ch.mesh]
    g = body.vertex_groups.get("ft_strand")
    in_group = sum(1 for v in body.data.vertices if g is not None and any(e.group == g.index for e in v.groups))
    stage = H.stable({"status": staged["hair"]["status"], "joined": hr["joined"], "strand_contract": hr["strand_contract"],
                      "body_verts": len(body.data.vertices), "ft_strand_verts": in_group,
                      "materials": [m.name for m in body.data.materials if m],
                      "leftover_hair_objects": sorted(o.name for o in bpy.data.objects if o.name.startswith(ch.name + "_hair"))})

    base = tomllib.loads(SPEC)
    refusals = {}
    for label, table in (("bad_preset", {"preset": "mohawk"}), ("bad_colour", {"preset": "bun", "colour": [2, 0, 0]}),
                         ("unknown_field", {"preset": "bun", "front": 0.07}), ("no_preset", {"colour": [0.1, 0.1, 0.1]})):
        try:
            spec.parse(dict(base, hair=table))
            refusals[label] = None
        except spec.SpecError as exc:
            refusals[label] = str(exc)
    old = spec.parse(dict(base, hair={"kind": "shell_bun", "back": 0.185}))
    brief = sheet.validate(sheet.new(sex="female", hair={"preset": "dreadlocks"}))
    return {
        "presets": presets,
        "gltf": H.stable(glb),
        "stage": stage,
        "spec": {"gaps": sorted(spec.GAPS), "deprecated": sorted(spec.DEPRECATED), "refusals": refusals,
                 "shell_bun_kind": old.hair.kind, "shell_bun_params": old.hair.params},
        "brief_refusal": [p for p in brief if "hair" in p],
        "stage_names": [s[0] for s in stages.STAGES],
    }


H.run("hair_presets", build)
