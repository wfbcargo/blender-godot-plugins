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
- every preset's cap stays off the ears: `cap.ear_covered_verts` (ear vertices the cap lies over) is 0, and a
  control with the ear cut off (`ear_cut=False`, the cap as it was before) shows what it catches;
- `brows=True, lashes=True, body_hair=True` on the same body (humanform.brows): the brow and lash cards'
  counts and weights, the body hair's regions, their face order, and in the exported glTF their materials -
  alpha MASK, textures, the lookdev extras (scissor in Godot), lashes double-sided; `[hair] brows / lashes /
  body_hair` parse, a bad value is refused, and a spec without them hashes its hair section as before;
- the man's hairline, the lashes and the brow shape (hair-hairline-lashes): `hairline_feather` measures the
  cap texture near the hairline - its 10-90% coverage ramp and how far (mm on the cap, p10..p90 across U) the
  line where the hair turns dense wanders - for short_crop, bob, and short_crop with its `look` overrides
  dropped (the control, a hard hairline, which must fail the 1 mm floor); its `fringe_ratio` (alpha's change
  along the strands against across them in the thinning band: a comb of parallel spikes changes almost only
  across) against the round-1 look without edge hairs (the control, which must fail the floor); `edge_wobble`
  (how far `edge_wobble_m` moves the cap's V, against it off); `line_u` (how square U and V meet near the line
  at the temples and sides, against `line_u_m` 0, which must fail);
  `lash_root` is the upper lid's lash coverage in the band at the root (the lash line), against the Step 0 lash
  counts (the control, which must fail the floor); `brow_shapes` moves each brow card to each shape and
  reports its height profile and how far it moved, `natural` must leave every brow vertex where the default
  puts it (0.0 mm), `arched` must lift the outer third at least 1 mm, and the control (arched with its keys
  removed) must fail that; `[hair] brow_shape` parses, a bad one is refused, and "natural" hashes as a spec
  without the field;
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
                                            "eye_source", "ear_vertices")},
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

    face = _face(ch, root)
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
    brief += sheet.validate(sheet.new(sex="female", hair={"preset": "bun", "brow_shape": "bushy"}))
    # a bad colour and a bad brow shape together: both are reported, not only the first
    brief += sheet.validate(sheet.new(sex="female", hair={"preset": "bun", "colour": [2, 0, 0], "brow_shape": "bushy"}))
    return {
        "presets": presets,
        "gltf": H.stable(glb),
        "stage": stage,
        "spec": {"gaps": sorted(spec.GAPS), "deprecated": sorted(spec.DEPRECATED), "refusals": refusals,
                 "shell_bun_kind": old.hair.kind, "shell_bun_params": old.hair.params},
        "brief_refusal": [p for p in brief if "hair" in p],
        "stage_names": [s[0] for s in stages.STAGES],
        "rebuild_refused": rebuild,
        "face": face,
        "face_spec": _face_spec(spec, base),
        "optional_lookdev": optional,
    }


def _face(ch, root):
    """Brows, lashes and body hair (humanform.brows) on the built body, and the ears every cap stays off."""
    import bpy
    from humanform import hair
    out = {}
    # the control: the short crop's cap as it was before it knew where the ears are
    rep = hair.add(ch.mesh, preset="short_crop", colour=(0.35, 0.22, 0.12), name=ch.name, ear_cut=False)
    out["ear_covered_verts_without_ear_cut"] = rep["cap"]["ear_covered_verts"]
    for n in rep["objects"].values():
        bpy.data.objects.remove(bpy.data.objects[n], do_unlink=True)
    rep = hair.add(ch.mesh, preset="short_crop", colour=(0.35, 0.22, 0.12), name=ch.name, brows=True, lashes=True,
                   body_hair=True, sex="female")
    made = [bpy.data.objects[n] for n in rep["objects"].values()]
    out["objects"] = sorted(rep["objects"])
    out["ear_covered_verts"] = rep["cap"]["ear_covered_verts"]
    parts = {}
    for name, part in rep["face"]["parts"].items():
        parts[name] = {k: part[k] for k in ("faces", "verts", "weights", "regions", "colour", "lid_cards") if k in part}
        tex = (part.get("material") or {}).get("texture")
        if tex:
            # the card texture: share of texels a hair covers (skin between the hairs, no opaque band)
            parts[name]["texture"] = tex
        mat = bpy.data.materials.get(f"{ch.name}_{name}")
        if mat is not None and name in ("brows", "lashes"):
            parts[name]["transparent_shadow"] = bool(getattr(mat, "use_transparent_shadow", False))
    out["parts"] = H.stable(parts)
    out["skipped"] = rep["face"]["skipped"]
    out["face_order"] = {o.name: H.face_order(o) for o in made if o.name != f"{ch.name}_hair"}
    # the lash roots sit on the lids and the brows on the ridge: every card vertex's distance to the skin
    from mathutils.bvhtree import BVHTree
    from humanform import hair as _h
    lm = _h.landmarks(ch.mesh)
    bvh = _h._bvh(lm["_co"], bpy.data.objects[ch.mesh], lm["_eye_vertices"])
    lift = {}
    for o in made:
        if o.name.endswith(("_brows", "_lashes")):
            d = [bvh.find_nearest(o.matrix_world @ v.co)[3] for v in o.data.vertices]
            lift[o.name.rsplit("_", 1)[-1]] = [round(min(d) * 1000, 2), round(max(d) * 1000, 2)]
    out["skin_distance_mm"] = lift
    from rig_analysis import export as ra_export
    path = os.path.join(root, "face_cards.glb")
    w = ra_export.export_glb(path, [ch.mesh, ch.rig] + [o.name for o in made], actions=[], rig_name=ch.rig)
    j = _glb_json(w["file"])
    mats = {}
    for m in j["materials"]:
        part = m["name"][len(ch.name) + 1:]
        if part in ("brows", "lashes", "body_hair"):
            mats[part] = {"alphaMode": m.get("alphaMode"), "doubleSided": m.get("doubleSided", False),
                          "base_colour_texture": "baseColorTexture" in m.get("pbrMetallicRoughness", {}),
                          "normal_texture": "normalTexture" in m,
                          "godot_transparency": ((m.get("extras") or {}).get("lookdev") or {}).get("godot", {}).get("transparency"),
                          "lookdev_preset": ((m.get("extras") or {}).get("lookdev") or {}).get("preset")}
            g = ((m.get("extras") or {}).get("lookdev") or {}).get("godot", {})
            mats[part]["godot_sheen"] = {k: g.get(k) for k in ("rim_enabled", "backlight_enabled", "anisotropy_enabled")}
            mats[part]["texture_hash"] = _pixels_hash(f"{ch.name}_{part}_strands")
    out["gltf"] = H.stable(mats)
    for o in made:
        bpy.data.objects.remove(o, do_unlink=True)
    out["hairline_feather"] = _hairline_feather(ch)
    out["lash_root"] = _lash_root()
    out["brow_shapes"] = _brow_shapes(ch)
    return out


WANDER_MIN_MM = 1.0         # where the short crop's hair turns dense must wander at least this far (p10..p90)
LASH_ROOT_MIN = 0.65        # share of the upper lid's root band (V 0.02..0.1) that lashes cover at alpha >= 0.5
ARCH_MIN_MM = 1.0           # "arched" must lift the brow's outer third at least this far
WOBBLE_MIN_MM = 1.0         # short_crop's edge_wobble_m must move the cap's V near the line at least this far
SHEAR_MIN_DEG = 50.0        # near the hairline at the temples and sides, U and V must meet at least this square (median)
FRINGE_MIN = 0.1            # in the thinning band, alpha's change along the strands against across them (per mm):
                            # a comb of parallel spikes changes almost only across U; scattered leaning hairs both


def _fringe_ratio(a, span, tile):
    """Mean |d alpha / d mm| along V over mean |d alpha / d mm| across U, in the rows where the mean alpha across
    U is between 5% and 85% of its value at V 0.3 (the thinning band in front of the dense hair)."""
    import numpy as np
    Hh, W = a.shape
    v = (np.arange(Hh) + 0.5) / Hh
    mean = a.mean(axis=1)
    full = float(mean[np.searchsorted(v, 0.3)])
    rows = np.nonzero((mean >= 0.05 * full) & (mean <= 0.85 * full) & (v < 0.3))[0]
    if len(rows) < 2:
        return 0.0, 0
    band = a[rows.min():rows.max() + 1]
    gu = np.abs(np.diff(band, axis=1)).mean() / (tile / W * 1000)
    gv = np.abs(np.diff(band, axis=0)).mean() / (span / Hh * 1000)
    return round(float(gv / max(gu, 1e-9)), 4), int(len(rows))


def _uv_v(ch, preset, **overrides):
    """The hair object's UV V per loop, and the report's objects removed after."""
    import bpy
    import numpy as np
    from humanform import hair
    rep = hair.add(ch.mesh, preset=preset, colour=(0.35, 0.22, 0.12), name=ch.name, **overrides)
    me = bpy.data.objects[rep["objects"]["hair"]].data
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    for n in rep["objects"].values():
        bpy.data.objects.remove(bpy.data.objects[n], do_unlink=True)
    return uv[1::2]


def _uv_shear(ch, **overrides):
    """The angle (degrees) between the cap's U and V directions on the skin, per face, over the faces near the
    hairline (their V within 8 mm of the line's) at the temples and sides (|x| > 4 cm): the median and the share
    under 45 degrees. U and V square to each other there only if U runs along the line."""
    import bpy
    import math
    import numpy as np
    from humanform import hair
    pr = hair.params("short_crop", **overrides)
    rep = hair.add(ch.mesh, preset="short_crop", colour=(0.35, 0.22, 0.12), name=ch.name, **overrides)
    ob = bpy.data.objects[rep["objects"]["hair"]]
    me, M = ob.data, ob.matrix_world
    uvl = me.uv_layers.active.data
    co = np.array([tuple(M @ v.co) for v in me.vertices])
    v_hi = pr["cap_v_hairline"] + 0.008 / pr["cap_v_span_m"]
    angles = []
    for f in me.polygons:
        li = list(f.loop_indices)[:3]
        P = [co[me.loops[i].vertex_index] for i in li]
        T = [np.array(uvl[i].uv) for i in li]
        if np.mean([t[1] for t in T]) > v_hi or abs(np.mean([q[0] for q in P])) < 0.04:
            continue
        e1, e2, d1, d2 = P[1] - P[0], P[2] - P[0], T[1] - T[0], T[2] - T[0]
        det = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(det) < 1e-12:
            continue
        du, dv = (e1 * d2[1] - e2 * d1[1]) / det, (e2 * d1[0] - e1 * d2[0]) / det
        c = abs(float(du @ dv)) / (np.linalg.norm(du) * np.linalg.norm(dv) + 1e-12)
        angles.append(math.degrees(math.acos(min(c, 1.0))))
    line = (rep.get("cap") or {}).get("line_u")
    for n in rep["objects"].values():
        bpy.data.objects.remove(bpy.data.objects[n], do_unlink=True)
    a = np.array(angles) if angles else np.zeros(1)
    return {"faces": len(angles), "median_deg": round(float(np.median(a)), 2),
            "share_under_45": round(float((a < 45).mean()), 4), "line_u": line}


def _line_u(ch):
    """short_crop's `line_u_m` (U carried off the hairline) against the same cap with it 0 (the control)."""
    on, off = _uv_shear(ch), _uv_shear(ch, line_u_m=0.0)
    return {"on": on, "control_line_u_off": off, "ok": on["median_deg"] >= SHEAR_MIN_DEG,
            "control_fails": not off["median_deg"] >= SHEAR_MIN_DEG, "min_median_deg": SHEAR_MIN_DEG}


def _edge_wobble(ch):
    """How far short_crop's `edge_wobble_m` moves the cap's V near the hairline (mm on the cap, the largest
    change against the same cap with it 0), and the control: the same comparison with it 0 on both sides
    (must fail the floor)."""
    import numpy as np
    from humanform import hair
    span = hair.params("short_crop")["cap_v_span_m"]
    on, off = _uv_v(ch, "short_crop"), _uv_v(ch, "short_crop", edge_wobble_m=0.0)
    off2 = _uv_v(ch, "short_crop", edge_wobble_m=0.0)
    if len(on) != len(off):
        return {"error": f"loop counts differ: {len(on)} and {len(off)}", "ok": False, "control_fails": False}
    moved = float(np.abs(on - off).max()) * span * 1000
    control = float(np.abs(off2 - off).max()) * span * 1000
    return {"edge_wobble_m": hair.params("short_crop").get("edge_wobble_m"), "moved_max_mm": round(moved, 3),
            "loops_moved": int((np.abs(on - off) > 1e-6).sum()), "loops": int(len(on)),
            "ok": moved >= WOBBLE_MIN_MM, "control_wobble_off_mm": round(control, 3),
            "control_fails": not control >= WOBBLE_MIN_MM, "min_mm": WOBBLE_MIN_MM}


def _feather_mm(ch, preset, **overrides):
    """(feather mm, [V at 10%, 90%], edge wander mm) of the cap texture near the hairline, as distance on the cap
    (V runs 1 / cap_v_span_m per metre near the line). Feather: the V over which the mean alpha across U rises
    from 10% to 90% of its value at V 0.3. Edge wander: across U, in windows of 16 texels (about three strands),
    the V where the window's mean alpha first reaches 0.9 - where the hair turns dense - its p90 less its p10.
    A hard hairline starts dense on one line of V (0 mm), whatever its strand tips do."""
    import bpy
    import numpy as np
    from humanform import hair
    rep = hair.add(ch.mesh, preset=preset, colour=(0.35, 0.22, 0.12), name=ch.name, **overrides)
    img = bpy.data.images[f"{ch.name}_hair_strands"]
    W, Hh = img.size
    px = np.empty(W * Hh * 4, np.float32)
    img.pixels.foreach_get(px)
    alpha = px.reshape(Hh, W, 4)[:, :, 3].mean(axis=1)          # rows bottom-up: row 0 is V = 0
    v = (np.arange(Hh) + 0.5) / Hh
    full = float(alpha[np.searchsorted(v, 0.3)])
    lo = float(v[np.argmax(alpha >= 0.1 * full)])
    hi = float(v[np.argmax(alpha >= 0.9 * full)])
    span = hair.params(preset, **overrides)["cap_v_span_m"]
    a = px.reshape(Hh, W, 4)[:, :, 3]
    win = 16
    starts = []
    for x0 in range(0, W, 4):
        cols = (np.arange(win) + x0) % W
        m = a[:, cols].mean(axis=1)
        k = int(np.argmax(m >= 0.9))
        starts.append(float(v[k]))
    wander = float(np.percentile(starts, 90) - np.percentile(starts, 10))
    fringe, fringe_rows = _fringe_ratio(a, span, hair.params(preset, **overrides).get("tile_m", 0.04))
    for n in rep["objects"].values():
        bpy.data.objects.remove(bpy.data.objects[n], do_unlink=True)
    return (round((hi - lo) * span * 1000, 2), [round(lo, 4), round(hi, 4)], round(wander * span * 1000, 2),
            fringe, fringe_rows)


def _hairline_feather(ch):
    out = {}
    from humanform import hair
    # the round-1 look (a ragged dense start, strands rooted in front of it, no edge hairs): the comb
    comb = {k: v for k, v in hair.params("short_crop")["look"].items() if not k.startswith("edge_")}
    comb.update(root_power=0.8, root_fade=[0.0, 0.1])
    for label, preset, over in (("short_crop", "short_crop", {}), ("bob", "bob", {}),
                                ("control_short_crop_without_look", "short_crop", {"look": {}, "edge_wobble_m": 0.0}),
                                ("control_short_crop_comb", "short_crop", {"look": comb})):
        mm, v, wander, fringe, rows = _feather_mm(ch, preset, **over)
        out[label] = {"feather_mm": mm, "v_10_90": v, "edge_wander_mm": wander, "ok": wander >= WANDER_MIN_MM,
                      "fringe_ratio": fringe, "fringe_rows": rows, "fringe_ok": fringe >= FRINGE_MIN}
    out["min_wander_mm"] = WANDER_MIN_MM
    out["control_fails"] = not out["control_short_crop_without_look"]["ok"]
    out["min_fringe_ratio"] = FRINGE_MIN
    out["fringe_control_fails"] = not out["control_short_crop_comb"]["fringe_ok"]
    out["edge_wobble"] = _edge_wobble(ch)
    out["line_u"] = _line_u(ch)
    return out


def _lash_root():
    """Upper-lid lash coverage in the root band of the lash card texture, now and with the Step 0 counts."""
    import numpy as np
    from humanform import brows
    def share(lashes):
        saved = brows.LASHES
        brows.LASHES = lashes
        try:
            px, _n, _r = brows.card_pixels("lashes", (0.1, 0.07, 0.05), 1024, 256)
        finally:
            brows.LASHES = saved
        a, b = brows.LASH_U["upper"]
        band = px[int(0.02 * 256):int(0.1 * 256), int(a * 1024):int(b * 1024), 3]
        return round(float((band >= 0.5).mean()), 4)
    step0 = {"upper": dict(brows.LASHES["upper"], n=170, width=(1.6, 2.3), gather=0.6, short=0),
             "lower": brows.LASHES["lower"]}
    now, before = share(brows.LASHES), share(step0)
    return {"upper_root_share": now, "ok": now >= LASH_ROOT_MIN, "control_step0_share": before,
            "control_fails": before < LASH_ROOT_MIN, "min": LASH_ROOT_MIN}


def _brow_shapes(ch):
    import bpy
    import numpy as np
    from humanform import brows, hair

    def brow_points(**kw):
        rep = hair.add(ch.mesh, preset="short_crop", colour=(0.35, 0.22, 0.12), name=ch.name, brows=True, **kw)
        ob = bpy.data.objects[rep["objects"]["brows"]]
        pts = np.array([tuple(ob.matrix_world @ v.co) for v in ob.data.vertices])
        shape = rep["face"]["parts"]["brows"].get("shape")
        for n in rep["objects"].values():
            bpy.data.objects.remove(bpy.data.objects[n], do_unlink=True)
        return pts, shape

    default, _ = brow_points()
    out = {}
    for name in brows.BROW_SHAPES:
        pts, shape = brow_points(brow_shape=name)
        out[name] = dict(shape["L"], moved_max_mm=round(float(np.linalg.norm(pts - default, axis=1).max()) * 1000, 3))
    arch = out["arched"]["moved_mm"][3]           # t = 0.7, the outer third
    saved = brows.BROW_SHAPES["arched"]
    brows.BROW_SHAPES["arched"] = [[0.0, 0.0], [1.0, 0.0]]
    try:
        _pts, shape = brow_points(brow_shape="arched")
    finally:
        brows.BROW_SHAPES["arched"] = saved
    control = shape["L"]["moved_mm"][3]
    return {"shapes": out, "natural_unchanged": out["natural"]["moved_max_mm"] == 0.0,
            "arched_outer_lift_mm": arch, "ok": arch >= ARCH_MIN_MM and out["natural"]["moved_max_mm"] == 0.0,
            "control_arched_flat_lift_mm": control, "control_fails": not control >= ARCH_MIN_MM,
            "min_mm": ARCH_MIN_MM}


def _face_spec(spec, base):
    out = {}
    ok = spec.parse(dict(base, hair={"preset": "bun", "brows": True, "lashes": True}))
    out["parsed"] = {"brows": ok.hair.brows, "lashes": ok.hair.lashes, "body_hair": ok.hair.body_hair,
                     "face": ok.hair.face()}
    try:
        spec.parse(dict(base, hair={"preset": "bun", "brows": "yes"}))
        out["bad_value"] = None
    except spec.SpecError as exc:
        out["bad_value"] = str(exc)
    shaped = spec.parse(dict(base, hair={"preset": "bun", "brows": True, "brow_shape": "arched"}))
    out["brow_shape"] = {"parsed": shaped.hair.brow_shape, "face": shaped.hair.face()}
    try:
        spec.parse(dict(base, hair={"preset": "bun", "brows": True, "brow_shape": "bushy"}))
        out["brow_shape"]["bad_value"] = None
    except spec.SpecError as exc:
        out["brow_shape"]["bad_value"] = str(exc)
    plain = spec.parse(dict(base, hair={"preset": "bun", "colour": [0.1, 0.1, 0.1]}))
    out["brow_shape"]["natural_same_digest"] = spec.parse(dict(base, hair={
        "preset": "bun", "colour": [0.1, 0.1, 0.1], "brow_shape": "natural"})).digest("hair") == plain.digest("hair")
    # the section a spec without the switches hashes: exactly the fields it had before they existed
    out["plain_section"] = plain.section("hair")
    out["switch_off_same_digest"] = spec.parse(dict(base, hair={"preset": "bun", "colour": [0.1, 0.1, 0.1],
                                                               "brows": False})).digest("hair") == plain.digest("hair")
    return out


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
