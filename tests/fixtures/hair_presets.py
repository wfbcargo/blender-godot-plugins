"""humanform's hair layer (improvements 05 5.2): every preset on one body, and the pipeline's hair stage.

A curvy MPFB woman from a spec is built through character-pipeline's body and bake stages. Then:

- each of `short_crop`, `bob`, `bun`, `ponytail` and `long_loose` is put on her with `hair.add` and taken off
  again, reporting what a person would check: the cap's feathered edge (the thickness and texture V at its
  geometric boundary - the edge lies on the skin in the transparent root zone, so there is no wall), the
  parts' sizes and their clearance from the skin, the follow-through strand contract where there is a
  strand, how faceted the across-strand direction is (the tangent Godot shades the anisotropy with), and
  the face order of every object made;
- the lookdev hair material is exported to a glb with the body (rig-anything's `export_glb`) and the glTF
  JSON read back: alpha MASK, a base colour and a normal texture, the `lookdev` extras Godot re-applies,
  and a hash of the strand texture's pixels;
- the spec's `[hair] preset = "ponytail"` runs the hair stage, which joins the cap and the tie into the
  body and leaves the tail its own object for the strand stage (`pipeline_ponytail`): the stage report,
  the body it joined into, and the `ft_strand` group on the object left behind;
- changing `[hair]` and rerunning the stage on the built body is refused rather than joining a second hair
  layer on top of the first, the body is left exactly as it was, and another character's hair object in the
  same file is not counted as hers;
- `spec.GAPS` no longer lists hair, the deprecated `kind = "shell_bun"` still parses, and a bad preset or
  colour in a spec or a brief is refused;
- lookdev is optional to the pipeline: with `LD_SCRIPTS` pointing at nothing, `plugins.use()` still imports
  the four it needs, lookdev's version is in the hash of the hair stage only (and not for a shell_bun spec),
  and a shell_bun spec's hair section hashes as it did before hair presets existed.
"""
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

# lookdev is routed with the rest. Its Blender package is `blender/`, not `scripts/` - the harness knows
# that, so `--plugins <checkout>` reaches it, and `use` records its version in the report. This fixture's
# glTF numbers are lookdev's own (the strand texture hashes, the material extras) and so is the cap's
# `strand_turns`, the crown's circumference over lookdev's `tile_m`.
H.use("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS", "LD_SCRIPTS")
for _var in ("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS", "LD_SCRIPTS"):
    os.environ[_var] = H.scripts(_var)

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


def _uv_tangent_turn(objs):
    """How faceted the across-strand direction is on the hair's own meshes.

    Per triangle, the direction of increasing U in its plane (what lookdev's `LookdevMaterials.apply`
    gives a hair surface as its tangent, and all the anisotropic highlight uses), against the mean of its
    edge neighbours', mod 180 degrees. Where this is large the per-face tangent is faceted and Godot draws
    the facets as dark polygons in the sheen, which `strand_tangents` averages away (lookdev
    `references/hair.md`); the count is what a change to the cap's U field would move.
    """
    import bmesh
    import numpy as np
    out = {}
    for ob in objs:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        uv = bm.loops.layers.uv.active
        tan = {}
        for f in bm.faces:
            ls = f.loops
            p0, p1, p2 = ls[0].vert.co, ls[1].vert.co, ls[2].vert.co
            e1, e2 = p1 - p0, p2 - p0
            fn = e1.cross(e2)
            a2 = fn.length
            if a2 < 1e-12:
                continue
            n = fn / a2
            g = ((ls[1][uv].uv.x - ls[0][uv].uv.x) * n.cross(-e2)
                 + (ls[2][uv].uv.x - ls[0][uv].uv.x) * n.cross(e1)) / a2
            if g.length < 1e-9:
                continue
            tan[f.index] = np.array(g.normalized()[:], dtype=float)
        turns = []
        for f in bm.faces:
            t = tan.get(f.index)
            if t is None:
                continue
            angs = [float(np.degrees(np.arccos(min(1.0, abs(float(np.dot(t, tan[g.index])))))))
                    for e in f.edges for g in e.link_faces if g.index != f.index and g.index in tan]
            if angs:
                turns.append(sum(angs) / len(angs))
        bm.free()
        arr = np.array(turns) if turns else np.zeros(1)
        out[ob.name.split("_", 1)[-1]] = {"tris": len(turns), "over_35_deg": int((arr > 35).sum()),
                                          "max_deg": round(float(arr.max()), 1)}
    return out


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
        entry["uv_tangent_turn"] = _uv_tangent_turn(made)
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
    tail = bpy.data.objects.get(hr.get("strand_object") or "")
    g = tail.vertex_groups.get("ft_strand") if tail else None
    in_group = sum(1 for v in tail.data.vertices if g is not None and any(e.group == g.index for e in v.groups)) if tail else 0
    stage = H.stable({"status": staged["hair"]["status"], "joined": hr["joined"], "strand_contract": hr["strand_contract"],
                      "body_verts": len(body.data.vertices), "strand_object": hr.get("strand_object"),
                      "strand_ft_strand_verts": in_group,
                      "body_has_ft_strand": body.vertex_groups.get("ft_strand") is not None,
                      "materials": [m.name for m in body.data.materials if m],
                      "leftover_hair_objects": sorted(o.name for o in bpy.data.objects if o.name.startswith(ch.name + "_hair"))})

    base = tomllib.loads(SPEC)
    rebuild = _rebuild_refused(ch, spec, base)
    optional = _optional_lookdev(ch, spec)

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
        "rebuild_refused": rebuild,
        "optional_lookdev": optional,
    }


def _rebuild_refused(ch, spec, base):
    """Changing `[hair]` on a body that already has hair must refuse, not stack a second layer on.

    The hair stage joins its hair into the body. On a rebuild where only `[hair]` changed, bake's hash is
    unchanged so bake is skipped and the stage ran on an already-haired body: the old bun stayed in the
    mesh, and `humanform.hair`'s landmarks read the previous cap (weighted 1.0 to the head bone) as scalp,
    so the crown rose 7.8 mm and the head unit `h` grew 6.8% - the whole hairline moved, silently. Here the
    spec's preset is changed from ponytail to bun and the hair stage rerun from the built file, which is the
    shape of that rebuild; `stages.check_hair` refuses it and the body is untouched."""
    import bpy
    from character_pipeline import runner, stages
    body = bpy.data.objects[ch.mesh]
    before = {"verts": len(body.data.vertices), "materials": [m.name for m in body.data.materials if m]}
    other = spec.parse(dict(base, hair={"preset": "bun", "colour": [0.35, 0.22, 0.12]}))
    out = {"found": stages.haired(ch), "refused": None}
    try:
        runner.build(other, from_stage="hair", to_stage="hair", save=False, log=lambda m: None)
    except stages.StageRefused as exc:
        out["refused"] = str(exc)
    body = bpy.data.objects[ch.mesh]
    after = {"verts": len(body.data.vertices), "materials": [m.name for m in body.data.materials if m]}
    out["body_unchanged"] = after == before
    out["verts"] = after["verts"]
    # a file can hold a crowd: another character's hair, not named for this one and not on its rig, is
    # not this one's, so it must not appear and must not refuse anybody's first hair stage
    decoy = bpy.data.objects.new("Crowd_hair", bpy.data.meshes.new("Crowd_hair"))
    decoy.data.materials.append(bpy.data.materials.new("Crowd_hair"))
    bpy.context.scene.collection.objects.link(decoy)
    out["with_another_character"] = stages.haired(ch)
    bpy.data.objects.remove(decoy, do_unlink=True)
    return H.stable(out)


def _optional_lookdev(ch, spec):
    import hashlib as _h
    from character_pipeline import plugins
    out = {"stage_version_keys": {name: sorted(plugins.stage_versions(ch, name))
                                  for name in ("body", "bake", "hair", "flesh", "moves", "garments", "export")}}
    old = spec.parse(dict(__import__("tomllib").loads(SPEC), hair={"kind": "shell_bun", "back": 0.185}))
    out["shell_bun_hair_keys"] = sorted(plugins.stage_versions(old, "hair"))
    # the section a shell_bun spec's hair hash covers, as it was before presets: {kind, params}
    section = old.section("hair")
    out["shell_bun_section"] = section
    out["shell_bun_digest_matches_pre_preset"] = old.digest("hair") == _h.sha1(json.dumps(
        {"hair": {"kind": "shell_bun", "params": {"back": 0.185}}}, sort_keys=True, default=str).encode()).hexdigest()[:16]
    saved = os.environ.get("LD_SCRIPTS")
    try:
        os.environ["LD_SCRIPTS"] = os.path.join(H.out_dir(), "hair_presets", "no_lookdev_here")
        mods = plugins.use()
        out["without_lookdev"] = {"imported": [m.__name__ for m in mods], "available": plugins.available("lookdev_blender"),
                                  "hair_versions": plugins.stage_versions(ch, "hair").get("lookdev")}
    finally:
        os.environ["LD_SCRIPTS"] = saved
    return out


H.run("hair_presets", build)
