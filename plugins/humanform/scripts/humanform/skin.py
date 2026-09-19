"""Realistic skin for an MPFB body: tone that varies by region, mottling, oil and pores, subsurface - baked so
glTF carries it and marked so lookdev puts back in Godot what glTF drops.

    skin.mark(human)                        # on the MPFB human (its region groups): per-vertex tint and oil
    mat = skin.material("Nora_skin", (0.62, 0.44, 0.33), seed=11)   # procedural Principled + subsurface
    skin.bake(game_mesh, mat, size=1024)    # lookdev's bake: albedo, ORM (roughness), tangent normal
    look.skin(ob, srgb)                     # all three, as each fits the object (see look.skin)

**Regions.** A body's skin is not one colour. Lips, areolae and nipples, genital skin, knees, elbows and
knuckles are darker and redder; palms and soles are paler and yellower; cheeks, the nose tip and the ears
flush. MPFB's own region groups (`nipple`, `nippleTip`, `lips`, `ears`, `fingernails`, `toenails`, made by
MPFB for its skin materials) give the first set; the rest come from MPFB's joint groups and the surface
normal (a palm faces away from the back of the hand, found from the thumb; a sole faces down; a knee cap
forwards, an elbow back). Each region is a soft per-vertex weight, and they are written once, on the MPFB
human, as two point attributes: `hf_skin_tint` (a linear RGB multiplier of the brief's tone, stored as a
vector because the glTF exporter writes every colour attribute out as COLOR_n) and
`hf_skin_oil` (a roughness). rig-anything's `bake_for_game` keeps every data layer, so they reach the
game mesh even though the groups do not.

**Tone.** The brief's `skin` colour stays the mean: after baking, the albedo map's mean over the texels the
body covers is pulled back to it (a per-channel gain in linear light), so the regions and the mottling
move tone around the body without moving its average. `TONE_TOLERANCE` is what the bake checks. The bake also
measures each region against plain skin in the finished map (`contrast`: CIELAB dE, lightness, red/green) and
judges it against `CONTRAST_FLOOR` (`contrast_ok`, the misses in `contrast_fail`), and reports the baked roughness
over each region and the T-zone (`roughness`).

**Mottling and pores.** Two octaves of 4D noise in object space (seeded, so a rebuild bakes the same map)
vary tone and redness; a finer noise bumps the baked normal map. Real pores (0.05-0.2 mm) are finer than any
texel a 1-2k map spends on a whole body, so they come in Godot as a tiling detail normal (the material's
`lookdev.detail`), on a second UV map `hf_detail` (a copy of the body's) because Godot's detail layer can
only tile on UV2.

**Subsurface.** Principled subsurface, random walk, weight 1, with Jensen et al. 2001's skin mean free paths
(red 3.67 mm, green 1.37 mm, blue 0.68 mm) at scale 0.001 (the body is in metres). glTF has no subsurface, so
the material's `lookdev` custom property (glTF extras) asks Godot for `subsurf_scatter` in skin mode with
transmittance; `LookdevMaterials.apply` sets them.
"""

from __future__ import annotations

import os
import tempfile
import zlib

import bpy
import numpy as np

from . import delta, look

TINT = "hf_skin_tint"
OIL = "hf_skin_oil"
REGION = "hf_skin_region"      # int per vertex: 1 + index in REGIONS of the region it is mostly in, 0 for plain skin
DETAIL_UV = "hf_detail"
TONE_TOLERANCE = 0.03          # sRGB, per channel: the baked mean against the brief's colour

# linear RGB multipliers of the mean tone, and roughness, per region (weights blend them; unmarked skin is 1, BASE).
# Measured on study_man's bake before humanform 0.13.0 (notebooks/realism-step2/skin-regions.md): knees, elbows,
# knuckles and cheeks sat at CIELAB dE 2.6-3.2 from plain skin - one just-noticeable difference, lost under light
# and mottle - and palms and soles were *redder* than skin. Now the red regions shift red against green (R/G of the
# multiplier 1.25-1.6) and the pale ones lift green and blue over red (paler, less red, a little yellow).
# Roughness: Weyrich et al. 2006 (measured faces, Torrance-Sparrow m 0.25-0.45 by region) and d'Eon & Luebke 2007
# (m 0.3 for skin) put skin's perceptual roughness (sqrt of the microfacet slope) near 0.5-0.6; the oily T-zone is
# the low end, not lacquer. Forehead/nose/chin 0.46 and lips 0.45 (was 0.38 and 0.36, which drew a white plateau).
REGIONS = {
    "lips":      {"tint": (0.84, 0.46, 0.50), "rough": 0.45},
    "nipple":    {"tint": (0.70, 0.50, 0.46), "rough": 0.48},
    "genital":   {"tint": (0.70, 0.54, 0.50), "rough": 0.50},
    "knee":      {"tint": (0.80, 0.52, 0.48), "rough": 0.58},
    "elbow":     {"tint": (0.78, 0.52, 0.48), "rough": 0.60},
    "knuckle":   {"tint": (0.80, 0.52, 0.48), "rough": 0.55},
    "palm":      {"tint": (1.35, 1.35, 1.24), "rough": 0.60},
    "sole":      {"tint": (1.32, 1.32, 1.14), "rough": 0.64},
    "flush":     {"tint": (1.00, 0.70, 0.70), "rough": 0.48},     # cheeks, nose tip, ears
    "nail":      {"tint": (1.10, 0.92, 0.92), "rough": 0.30},
}
BASE_ROUGH = 0.50
T_ZONE_ROUGH = 0.46            # forehead, nose, chin: oilier than the rest, still skin
LIMB_ROUGH = 0.57              # forearms, shins: drier
MOTTLE = ((4.0, 0.08), (24.0, 0.035))    # (noise scale per metre, value share) - blotches ~25 cm, then ~4 cm
REDNESS = 0.07                 # the low octave also shifts red against green/blue by this share
# the regional contrast each bake must reach: CIELAB dE76 of the region's baked tone from plain skin, and which way
# (redder: region R/G over skin R/G at least RED_MIN; paler: lighter by PALE_DL_MIN and no redder than skin)
CONTRAST_FLOOR = {"lips": ("red", 8.0), "knee": ("red", 5.0), "elbow": ("red", 5.0), "knuckle": ("red", 5.0),
                  "flush": ("red", 4.0), "palm": ("pale", 5.0), "sole": ("pale", 5.0)}
RED_MIN = 1.03
PALE_DL_MIN = 3.0
PALE_RG_MAX = 1.02
# HF_SKIN_LEGACY_REGIONS=1 puts back the values and the unbounded palm mask of humanform 0.12.0 - the must-fail
# control of the contrast check (skin_detail)
LEGACY = {"REGIONS": {"lips": {"tint": (0.90, 0.62, 0.64), "rough": 0.36},
                      "knee": {"tint": (0.88, 0.76, 0.72), "rough": 0.58},
                      "elbow": {"tint": (0.86, 0.74, 0.70), "rough": 0.60},
                      "knuckle": {"tint": (0.88, 0.76, 0.72), "rough": 0.55},
                      "palm": {"tint": (1.16, 1.04, 0.98), "rough": 0.60},
                      "sole": {"tint": (1.14, 1.05, 0.92), "rough": 0.64},
                      "flush": {"tint": (1.02, 0.88, 0.88), "rough": 0.46}},
          "T_ZONE_ROUGH": 0.38, "MOTTLE": ((5.0, 0.07), (28.0, 0.035)), "REDNESS": 0.05}
ZONES = ("t_zone",)            # REGION ids after REGIONS' for skin in no region: the oily T-zone, for the bake's report
BUMP = {"scale": 180.0, "strength": 0.12, "distance": 0.0006}   # fine relief the map can hold at 1-2k
SUBSURFACE = {"weight": 1.0, "radius": (3.67, 1.37, 0.68), "scale": 0.001, "ior": 1.4}
SPECULAR_IOR_LEVEL = 0.45      # skin F0 ~2.8% (IOR 1.4) against Principled's 4% at 0.5
GODOT = {                      # StandardMaterial3D properties glTF drops (lookdev_materials.gd sets them)
    "subsurf_scatter_enabled": True,
    "subsurf_scatter_strength": 0.45,
    "subsurf_scatter_skin_mode": True,
    "subsurf_scatter_transmittance_enabled": True,
    "subsurf_scatter_transmittance_color": [0.92, 0.42, 0.30, 1.0],
    "subsurf_scatter_transmittance_depth": 0.01,   # m: ears, finger edges glow; a whole palm (2-3 cm) must not
    "subsurf_scatter_transmittance_boost": 0.0,
    "metallic_specular": 0.42,
}
DETAIL = {"normal": "pores", "tile_px": 256, "cells": 48, "uv2_scale": 80.0, "strength": 0.35, "bump": 3.0}
MPFB_GROUPS = {"lips": "lips", "nipple": "nipple", "nippleTip": "nipple", "ears": "flush",
               "fingernails": "nail", "toenails": "nail"}


def legacy():
    return os.environ.get("HF_SKIN_LEGACY_REGIONS") == "1"


def params():
    """The region tints and roughness, T-zone roughness, mottle and redness in force (LEGACY's under the control)."""
    if not legacy():
        return {"REGIONS": REGIONS, "T_ZONE_ROUGH": T_ZONE_ROUGH, "MOTTLE": MOTTLE, "REDNESS": REDNESS}
    return {"REGIONS": {k: LEGACY["REGIONS"].get(k, v) for k, v in REGIONS.items()},
            "T_ZONE_ROUGH": LEGACY["T_ZONE_ROUGH"], "MOTTLE": LEGACY["MOTTLE"], "REDNESS": LEGACY["REDNESS"]}


def _smooth(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _gauss(p, c, r):
    d2 = ((p - np.asarray(c)) ** 2).sum(axis=1)
    return np.exp(-d2 / (2.0 * r * r))


def _unit(v):
    v = np.asarray(v, np.float64)
    return v / max(np.linalg.norm(v), 1e-12)


def _mpfb_group_indices(ob, name, n):
    """Vertex indices of `name`: the object's group if it has one, else MPFB's own list for the base mesh."""
    g = ob.vertex_groups.get(name)
    if g is not None:
        gi = g.index
        return np.array([v.index for v in ob.data.vertices[:n] if any(e.group == gi and e.weight > 0.1 for e in v.groups)],
                        dtype=np.int64)
    try:
        from bl_ext.user_default.mpfb.entities.socketobject._extra_vertex_groups import vertex_group_information
        idx = vertex_group_information["basemesh"].get(name) or []
    except ImportError:
        idx = []
    return np.array([i for i in idx if i < n], dtype=np.int64)


def regions(ob):
    """Per-vertex weights (0..1) of each region on an MPFB human, from its region and joint groups and the
    mixed (shape-keyed) surface. Returns ({region: array over the body vertices}, {"t_zone":, "limb":}, notes)."""
    from . import muscle
    n = min(len(ob.data.vertices), delta.BODY_VERTS)
    co = delta.mixed_coords(ob)
    faces = delta.body_faces(ob)
    p = co[:n]
    nrm = delta.vertex_normals(co, faces)[:n]
    j = muscle._joints(ob, co)
    w = {k: np.zeros(n) for k in REGIONS}
    notes = []
    for g, region in MPFB_GROUPS.items():
        idx = _mpfb_group_indices(ob, g, n)
        if len(idx):
            m = np.zeros(n)
            m[idx] = 1.0
            if g == "lips":
                # MPFB's lips group reaches past the vermilion into the skin round the mouth and the corners (a
                # soft clown's oval when tinted): keep its core, the vertices still well inside after the
                # membership is smoothed, and taper it to nothing at the mouth corners. It is not smoothed
                # again below: the vermilion border is a sharp edge on a real mouth.
                core = delta.smooth(m, faces, iterations=3, share=0.5)[:n]
                hw = float(np.abs(p[idx, 0]).max())
                m = _smooth(0.70, 0.95, core) * m * (1.0 - _smooth(0.78 * hw, 0.97 * hw, np.abs(p[:, 0])))
            w[region] = np.maximum(w[region], m)
        else:
            notes.append(f"no {g} group")
    need = ("joint-neck", "joint-pelvis", "joint-l-knee", "joint-l-elbow", "joint-l-hand", "joint-l-ankle",
            "joint-l-eye", "joint-l-upper-leg")
    missing = [k for k in need if k not in j]
    extra = {"t_zone": np.zeros(n), "limb": np.zeros(n)}
    if missing:
        notes.append(f"no joints {missing}: only MPFB's region groups")
        return w, extra, notes
    s = float((j["joint-neck"][2] - j["joint-pelvis"][2]) / 0.60)      # ~1 for a 1.75 m adult
    xs = 1.0 if j["joint-l-hand"][0] > 0 else -1.0                    # which way is the left side
    fwd = np.array([0.0, -1.0, 0.0])                                   # MPFB faces -Y
    front = nrm @ fwd
    old = legacy()
    # a joint mark's Gaussian peaks under 1 where its centre sits off the surface (a knee cap 4 cm in front of
    # the joint): scaled so its core reaches 1 (humanform 0.13.0; the knee's core was 0.86 before)
    peak = 1.0 if old else 1.25
    for side in (1.0, -1.0):
        def J(name):
            c = np.array(j[name], np.float64)
            if side < 0:
                c[0] = -c[0]
            return c
        on = np.sign(p[:, 0]) == side * xs
        # knees (cap, forwards) and elbows (olecranon, backwards)
        w["knee"] = np.maximum(w["knee"], on * np.minimum(1.0, peak * _gauss(p, J("joint-l-knee") + fwd * 0.04 * s,
                                                                           0.045 * s)) * _smooth(0.1, 0.5, front))
        w["elbow"] = np.maximum(w["elbow"], on * np.minimum(1.0, peak * _gauss(p, J("joint-l-elbow") - fwd * 0.03 * s,
                                                                             0.04 * s)) * _smooth(0.1, 0.5, -front))
        # hand: past the wrist along the forearm; palm is the side the thumb curls towards
        wr, el = J("joint-l-hand"), J("joint-l-elbow")
        ax = _unit(wr - el)
        along = (p - wr) @ ax
        hand = on * _smooth(0.0, 0.02 * s, along)
        if not old:
            # the hand ends past the fingertips and within a hand's breadth of the forearm's line: unbounded, the
            # half-space past the wrist took in the undersides of the feet (917 of study_man's 2093 palm
            # vertices were below the wrist by over 15 cm, 0.12.0)
            radial = np.linalg.norm((p - wr) - np.outer(along, ax), axis=1)
            hand = hand * (1.0 - _smooth(0.24 * s, 0.28 * s, along)) * (1.0 - _smooth(0.09 * s, 0.11 * s, radial))
        thumb = J("joint-l-finger-1-1") if "joint-l-finger-1-1" in j else None
        mid = J("joint-l-finger-3-1") if "joint-l-finger-3-1" in j else None
        if thumb is not None and mid is not None:
            a = _unit(mid - wr)
            t = thumb - wr
            t = _unit(t - a * (t @ a))
            palm_n = _unit(np.cross(a, t)) * (side * xs)
            facing = nrm @ palm_n
            w["palm"] = np.maximum(w["palm"], hand * _smooth(0.05, 0.45, facing))
            for k in range(2, 6):
                for seg in (1, 2, 3):
                    nm = f"joint-l-finger-{k}-{seg}"
                    if nm in j:
                        w["knuckle"] = np.maximum(w["knuckle"], hand * _gauss(p, J(nm), 0.011 * s)
                                                  * _smooth(0.1, 0.5, -facing))
        else:
            notes.append("no finger joints: no palms or knuckles")
        # soles: below the ankle, facing down
        foot = on * (1.0 - _smooth(J("joint-l-ankle")[2] - 0.01 * s, J("joint-l-ankle")[2] + 0.02 * s, p[:, 2]))
        w["sole"] = np.maximum(w["sole"], foot * _smooth(-0.35, -0.75, nrm[:, 2]))
        # flush: the cheek below and outside each eye, facing forwards
        eye = J("joint-l-eye")
        cheek = eye + np.array([0.012 * side * xs * s, -0.005 * s, -0.035 * s])
        # (0.13.0: wider and fuller - at 1.8 cm and 0.8 the flush was a coin on the cheekbone)
        w["flush"] = np.maximum(w["flush"], (0.8 if old else 0.9) * _gauss(p, cheek, (0.018 if old else 0.024) * s)
                                * _smooth(0.0, 0.4, front))
        # limbs are drier: forearms and shins
        extra["limb"] = np.maximum(extra["limb"], on * _smooth(0.0, 0.05 * s, (p - el) @ ax) * (1 - hand))
        extra["limb"] = np.maximum(extra["limb"], on * _smooth(J("joint-l-knee")[2], J("joint-l-knee")[2] - 0.08 * s,
                                                               p[:, 2]) * (1 - foot))
    # nose tip: the most forward head vertex between the mouth and the eyes
    eye_z = j["joint-l-eye"][2]
    head = (p[:, 2] > eye_z - 0.08 * s) & (p[:, 2] < eye_z) & (np.abs(p[:, 0]) < 0.02 * s)
    if head.any():
        tip = p[np.where(head)[0][np.argmin(p[head] @ -fwd)]]
        w["flush"] = np.maximum(w["flush"], 0.8 * _gauss(p, tip, 0.012 * s))
    # genital skin: the midline between the hip joints, from the pubis down, front and under
    hip = 0.5 * (np.array(j["joint-l-upper-leg"]) + np.array(j["joint-l-upper-leg"]) * np.array([-1, 1, 1]))
    band = _smooth(hip[2] + 0.03 * s, hip[2] - 0.02 * s, p[:, 2]) * _smooth(hip[2] - 0.16 * s, hip[2] - 0.10 * s, p[:, 2])
    mid_x = np.exp(-(p[:, 0] ** 2) / (2 * (0.03 * s) ** 2))
    w["genital"] = band * mid_x * _smooth(-0.2, 0.3, front - nrm[:, 2] * 0.5) * (p[:, 1] < hip[1] + 0.02 * s)
    # T-zone: forehead, the nose and the chin, facing forwards
    face = _smooth(0.2, 0.6, front) * (p[:, 2] > eye_z - 0.12 * s)
    forehead = _smooth(eye_z + 0.01 * s, eye_z + 0.03 * s, p[:, 2]) * (1 - _smooth(eye_z + 0.07 * s, eye_z + 0.10 * s, p[:, 2]))
    strip = np.exp(-(p[:, 0] ** 2) / (2 * (0.012 * s) ** 2))
    extra["t_zone"] = face * np.maximum(forehead * (np.abs(p[:, 0]) < 0.06 * s), strip * (p[:, 2] < eye_z + 0.03 * s))
    for k in w:
        w[k] = np.clip(w[k], 0, 1) if k == "lips" else delta.smooth(np.clip(w[k], 0, 1), faces, iterations=1, share=0.5)[:n]
    return w, extra, notes


def mark(ob):
    """Write `hf_skin_tint` and `hf_skin_oil` on an MPFB human (see `regions`). Returns a report."""
    ob = bpy.data.objects[ob] if isinstance(ob, str) else ob
    w, extra, notes = regions(ob)
    prm = params()
    n_all = len(ob.data.vertices)
    n = len(next(iter(w.values())))
    tint = np.ones((n_all, 4))
    rough = np.full(n_all, BASE_ROUGH)
    rough[:n] = (BASE_ROUGH + (prm["T_ZONE_ROUGH"] - BASE_ROUGH) * extra["t_zone"]
                 + (LIMB_ROUGH - BASE_ROUGH) * extra["limb"])
    for k, spec in prm["REGIONS"].items():
        a = w[k][:, None]
        tint[:n, :3] = tint[:n, :3] * (1 - a) + np.asarray(spec["tint"]) * a
        rough[:n] = rough[:n] * (1 - w[k]) + spec["rough"] * w[k]
    me = ob.data
    for name in (TINT, OIL, REGION):
        if name in me.attributes:
            me.attributes.remove(me.attributes[name])
    rid = np.zeros(n_all, np.int32)
    for i, z in enumerate(ZONES):
        # a zone's id only where no region claims the vertex (they are written first, so a region overwrites)
        rid[:n][extra[z] > 0.5] = len(REGIONS) + i + 1
    for i, k in enumerate(REGIONS):
        rid[:n][w[k] > 0.5] = i + 1
    me.attributes.new(REGION, "INT", "POINT").data.foreach_set("value", rid)
    # a vector, not a colour attribute: the glTF exporter writes every colour attribute as COLOR_n
    me.attributes.new(TINT, "FLOAT_VECTOR", "POINT").data.foreach_set("vector", tint[:, :3].astype(np.float32).ravel())
    me.attributes.new(OIL, "FLOAT", "POINT").data.foreach_set("value", rough.astype(np.float32))
    return {"regions": {k: round(float((v > 0.5).sum()), 0) for k, v in w.items()},
            "t_zone": int((extra["t_zone"] > 0.5).sum()), "limb": int((extra["limb"] > 0.5).sum()), "notes": notes}


def seed_of(name):
    return zlib.crc32(name.encode("utf-8")) % 997


def _principled_skin(bsdf, lin, roughness):
    """What every skin material has, flat or procedural: the tone, a roughness, subsurface and skin's F0."""
    bsdf.inputs["Base Color"].default_value = (*lin, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.subsurface_method = "RANDOM_WALK"
    bsdf.inputs["Subsurface Weight"].default_value = SUBSURFACE["weight"]
    bsdf.inputs["Subsurface Radius"].default_value = SUBSURFACE["radius"]
    bsdf.inputs["Subsurface Scale"].default_value = SUBSURFACE["scale"]
    if "Subsurface IOR" in bsdf.inputs:
        bsdf.inputs["Subsurface IOR"].default_value = SUBSURFACE["ior"]
    bsdf.inputs["Specular IOR Level"].default_value = SPECULAR_IOR_LEVEL
    bsdf.inputs["IOR"].default_value = SUBSURFACE["ior"]


def material(name, srgb, seed=None, roughness=BASE_ROUGH, procedural=False):
    """The skin material, reused by name and rebuilt every call.

    By default it is FLAT: the brief's tone as an unlinked Base Color, one roughness, subsurface - what the glTF
    exporter can read (a linked Base Color it cannot trace to an image is exported as nothing, which Godot draws
    white) and it references no mesh attribute (so `hf_skin_*` are never exported as COLOR_n). A body exported
    without a bake gets this. `procedural=True` is what `bake` bakes and then replaces: the tone (linear) times
    `hf_skin_tint` times mottling, roughness from `hf_skin_oil`, a fine bump."""
    seed = seed_of(name) if seed is None else seed
    lin = look.srgb_to_linear(srgb)[:3]
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    if mat.node_tree is None and hasattr(mat, "use_nodes"):
        mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    N, L = tree.nodes.new, tree.links.new
    out = N("ShaderNodeOutputMaterial")
    bsdf = N("ShaderNodeBsdfPrincipled")
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])
    _principled_skin(bsdf, lin, roughness)
    mat.diffuse_color = (*lin, 1.0)
    mat["lookdev"] = {"preset": "skin", "godot": dict(GODOT), "detail": dict(DETAIL, seed=int(seed)),
                      "tone_srgb": [round(float(c), 4) for c in tuple(srgb)[:3]]}
    mat["humanform_skin"] = {"seed": int(seed), "tone_srgb": [round(float(c), 4) for c in tuple(srgb)[:3]],
                             "stage": "flat"}
    if not procedural:
        return mat
    mat["humanform_skin"] = dict(mat["humanform_skin"], stage="procedural")
    coord = N("ShaderNodeTexCoord")
    tint = N("ShaderNodeAttribute")
    tint.attribute_type = "GEOMETRY"
    tint.attribute_name = TINT
    oil = N("ShaderNodeAttribute")
    oil.attribute_type = "GEOMETRY"
    oil.attribute_name = OIL
    tone = N("ShaderNodeMix")
    tone.data_type = "RGBA"
    tone.blend_type = "MULTIPLY"
    tone.inputs["Factor"].default_value = 1.0
    tone.inputs[6].default_value = (*lin, 1.0)
    L(tint.outputs["Color"], tone.inputs[7])
    col = tone.outputs[2]
    prm = params()
    for i, (scale, share) in enumerate(prm["MOTTLE"]):
        nz = N("ShaderNodeTexNoise")
        nz.noise_dimensions = "4D"
        nz.inputs["Scale"].default_value = scale
        nz.inputs["Detail"].default_value = 2.0
        nz.inputs["W"].default_value = seed * 1.618 + i * 7.3
        L(coord.outputs["Object"], nz.inputs["Vector"])
        # (noise - 0.5) * 2 * share, per channel: value, and on the first octave redness too
        gain = N("ShaderNodeMapRange")
        gain.inputs["From Min"].default_value = 0.3
        gain.inputs["From Max"].default_value = 0.7
        gain.inputs["To Min"].default_value = 1.0 - share
        gain.inputs["To Max"].default_value = 1.0 + share
        L(nz.outputs["Fac"], gain.inputs["Value"])
        red = N("ShaderNodeCombineColor")
        if i == 0:
            # more red where it is darker: blotchy vascular colour, not just lightness
            inv = N("ShaderNodeMath")
            inv.operation = "MULTIPLY_ADD"
            L(gain.outputs["Result"], inv.inputs[0])
            inv.inputs[1].default_value = -prm["REDNESS"] / share
            inv.inputs[2].default_value = 1.0 + prm["REDNESS"] / share
            L(inv.outputs["Value"], red.inputs["Red"])
            L(gain.outputs["Result"], red.inputs["Green"])
            L(gain.outputs["Result"], red.inputs["Blue"])
            # the red channel keeps the value term as well
            both = N("ShaderNodeMath")
            both.operation = "MULTIPLY"
            L(inv.outputs["Value"], both.inputs[0])
            L(gain.outputs["Result"], both.inputs[1])
            L(both.outputs["Value"], red.inputs["Red"])
        else:
            for c in ("Red", "Green", "Blue"):
                L(gain.outputs["Result"], red.inputs[c])
        mul = N("ShaderNodeMix")
        mul.data_type = "RGBA"
        mul.blend_type = "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        L(col, mul.inputs[6])
        L(red.outputs["Color"], mul.inputs[7])
        col = mul.outputs[2]
    L(col, bsdf.inputs["Base Color"])
    L(oil.outputs["Fac"], bsdf.inputs["Roughness"])
    bump_tex = N("ShaderNodeTexNoise")
    bump_tex.noise_dimensions = "4D"
    bump_tex.inputs["Scale"].default_value = BUMP["scale"]
    bump_tex.inputs["Detail"].default_value = 3.0
    bump_tex.inputs["W"].default_value = seed * 0.73 + 3.1
    L(coord.outputs["Object"], bump_tex.inputs["Vector"])
    bump = N("ShaderNodeBump")
    bump.inputs["Strength"].default_value = BUMP["strength"]
    bump.inputs["Distance"].default_value = BUMP["distance"]
    L(bump_tex.outputs["Fac"], bump.inputs["Height"])
    L(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _lookdev():
    """lookdev's bake module with `bake_material`: an already imported one if it has it, else from LD_SCRIPTS or
    the lookdev plugin next to this one (a checkout's or the installed skills'), replacing an older import."""
    import importlib
    import sys
    mod = sys.modules.get("lookdev_blender.bake")
    if mod is not None and hasattr(mod, "bake_material"):
        return mod
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.environ.get("LD_SCRIPTS"), os.path.join(here, "..", "..", "..", "lookdev", "blender"),
                 os.path.join(here, "..", "..", "lookdev", "blender")):
        if not cand or not os.path.isdir(os.path.join(cand, "lookdev_blender")):
            continue
        cand = os.path.normpath(cand)
        if cand in sys.path:
            sys.path.remove(cand)
        sys.path.insert(0, cand)
        for name in [k for k in sys.modules if k == "lookdev_blender" or k.startswith("lookdev_blender.")]:
            del sys.modules[name]
        importlib.invalidate_caches()
        mod = importlib.import_module("lookdev_blender.bake")
        if hasattr(mod, "bake_material"):
            return mod
    return None


def _srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def _linear(x):
    x = np.clip(np.asarray(x, np.float64), 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def bake(ob, mat, size=1024, out_dir=None):
    """Bake the procedural skin into albedo, ORM and normal maps on `ob`'s UVs (lookdev's `bake_material`),
    hold the albedo's covered mean to the brief's tone, pack the images, and add the `hf_detail` UV map.
    Returns a report with the baked and target means (sRGB)."""
    ob = bpy.data.objects[ob] if isinstance(ob, str) else ob
    ld = _lookdev()
    if ld is None:
        return {"error": "lookdev_blender is not importable (set LD_SCRIPTS or install lookdev): skin left flat"}
    # copies, not views: np.asarray of an ID property array shares its memory, and rebuilding the material
    # below replaces that property (the view then reads freed memory - a black albedo "held" to 0,0,0)
    held = mat["humanform_skin"].to_dict()
    target = np.array([float(v) for v in held["tone_srgb"]], np.float64)
    seed = int(held.get("seed", seed_of(mat.name)))

    def flat():
        # the bake failed: back to the flat material the exporter reads (never a procedural one it cannot)
        material(mat.name, target, seed=seed)
        mat["humanform_skin"] = dict(held, stage="flat")

    if TINT not in ob.data.attributes:
        unmarked(ob)
    material(mat.name, target, seed=seed, procedural=True)
    mat["humanform_skin"] = dict(held, stage="procedural")
    means = {}

    class Adjust:
        coverage = None

        def __call__(self, key, px):
            if key == "roughness" and loop_region is not None:
                # the baked roughness over each region's and zone's texels (the map's first channel)
                side = int(round(np.sqrt(len(px) // 4)))
                xy = np.clip((loop_uv * side).astype(np.int64), 0, side - 1)
                r = px.reshape(-1, 4)[xy[:, 1] * side + xy[:, 0], 0].astype(np.float64)
                names = list(REGIONS) + list(ZONES)
                means["roughness"] = {k: round(float(r[loop_region == i + 1].mean()), 3)
                                      for i, k in enumerate(names) if (loop_region == i + 1).any()}
                if (loop_region == 0).any():
                    means["roughness"]["skin"] = round(float(r[loop_region == 0].mean()), 3)
                return None
            # a byte sRGB image's pixels are its stored (sRGB-encoded) values, not linear light
            if key != "base_color" or self.coverage is None or not self.coverage.any():
                return None
            srgb = px.reshape(-1, 4)[:, :3].astype(np.float64)
            lin = _linear(srgb)
            cov = self.coverage
            means["baked_raw"] = [round(float(v), 4) for v in srgb[cov].mean(axis=0)]
            gain = np.ones(3)
            lin_t = _linear(target)
            for _ in range(8):                      # the sRGB mean of a scaled linear map: a few fixed-point steps
                m = _srgb(lin[cov] * gain).mean(axis=0)
                gain *= lin_t / np.maximum(_linear(m), 1e-6)
            out = px.reshape(-1, 4).copy()
            out[:, :3] = _srgb(lin * gain)
            means["gain"] = [round(float(g), 4) for g in gain]
            means["baked"] = [round(float(v), 4) for v in out[cov, :3].astype(np.float64).mean(axis=0)]
            means["p05_p95"] = [[round(float(v), 3) for v in np.percentile(out[cov, :3], q, axis=0)] for q in (5, 95)]
            if loop_region is not None:
                # each region's tone in the map (sRGB), sampled at its vertices' UVs
                side = int(round(np.sqrt(len(out))))
                xy = np.clip((loop_uv * side).astype(np.int64), 0, side - 1)
                texel = xy[:, 1] * side + xy[:, 0]
                means["regions"] = {k: [round(float(v), 3) for v in out[texel[loop_region == i + 1], :3].mean(axis=0)]
                                    for i, k in enumerate(REGIONS) if (loop_region == i + 1).any()}
                plain = out[texel[loop_region == 0], :3].astype(np.float64).mean(axis=0)
                means["regions"]["skin"] = [round(float(v), 3) for v in plain]
                means["contrast"] = contrast({k: out[texel[loop_region == i + 1], :3].astype(np.float64).mean(axis=0)
                                              for i, k in enumerate(REGIONS) if (loop_region == i + 1).any()}, plain)
            return out.ravel()

    me = ob.data
    loop_uv = loop_region = None
    if REGION in me.attributes and me.uv_layers.active is not None:
        loop_uv = np.empty(len(me.loops) * 2, np.float32)
        me.uv_layers.active.data.foreach_get("uv", loop_uv)
        loop_uv = np.mod(loop_uv.reshape(-1, 2), 1.0)
        lv = np.empty(len(me.loops), np.int64)
        me.loops.foreach_get("vertex_index", lv)
        vr = np.empty(len(me.vertices), np.int32)
        me.attributes[REGION].data.foreach_get("value", vr)
        loop_region = vr[lv]
    out_dir = out_dir or tempfile.mkdtemp(prefix="hf_skin_")
    try:
        res = ld.bake_material(ob, mat, out_dir, size=size, maps=("base_color", "roughness", "normal"),
                               adjust=Adjust())
    except Exception as e:                          # noqa: BLE001 - any failure must still leave a readable material
        res = {"error": f"bake_material raised {type(e).__name__}: {e}"}
    if "error" in res:
        flat()
        return dict(res, error=res["error"] + ": skin left flat")
    me = ob.data
    if DETAIL_UV not in me.uv_layers:
        active = me.uv_layers.active
        src = active.name
        uv = me.uv_layers.new(name=DETAIL_UV)
        data = np.empty(len(me.loops) * 2, np.float32)
        me.uv_layers[src].data.foreach_get("uv", data)
        uv.data.foreach_set("uv", data)
        me.uv_layers.active = me.uv_layers[src]
        me.uv_layers[src].active_render = True
    # the marks stay (a rebake from this file needs them); none is a colour attribute, so the exporter skips them
    err = float(np.abs(np.asarray(means.get("baked", [9, 9, 9])) - target).max())
    extra = {}
    if "contrast" in means:
        extra["contrast_fail"] = contrast_fails(means["contrast"])
        extra["contrast_ok"] = not extra["contrast_fail"]
    return {"size": size, "maps": res["maps"], "images": res["images"], "timings_s": res["timings_s"],
            "tone_target": [round(float(v), 4) for v in target], **means,
            "tone_error": round(err, 4), "tone_ok": err <= TONE_TOLERANCE, **extra, "detail_uv": DETAIL_UV}


def _lab(srgb):
    """CIELAB (D65) of an sRGB colour."""
    lin = _linear(srgb)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    x = (m @ lin) / np.array([0.95047, 1.0, 1.08883])
    f = np.where(x > 0.008856, np.cbrt(x), 7.787 * x + 16.0 / 116.0)
    return np.array([116.0 * f[1] - 16.0, 500.0 * (f[0] - f[1]), 200.0 * (f[1] - f[2])])


def contrast(tones, plain):
    """Each region's baked tone against plain skin's (both sRGB): `dE` (CIELAB 1976), `dL` (lightness) and `rg`,
    the region's red/green ratio over skin's (above 1 is redder). The free values; `contrast_fails` judges them."""
    plain = np.asarray(plain, np.float64)
    lp = _lab(plain)
    out = {}
    for k, v in tones.items():
        v = np.asarray(v, np.float64)
        lv = _lab(v)
        out[k] = {"dE": round(float(np.linalg.norm(lv - lp)), 2), "dL": round(float(lv[0] - lp[0]), 2),
                  "rg": round(float((v[0] / max(v[1], 1e-6)) / max(plain[0] / max(plain[1], 1e-6), 1e-6)), 3)}
    return out


def contrast_fails(c):
    """What in a `contrast` report is under CONTRAST_FLOOR: ["knee: dE 2.96 < 5.0", "palm: redder than skin
    (rg 1.04)", ...]. A floored region the body has no texels of is not judged."""
    fails = []
    for k, (way, floor) in CONTRAST_FLOOR.items():
        if k not in c:
            continue
        r = c[k]
        if r["dE"] < floor:
            fails.append(f"{k}: dE {r['dE']} < {floor}")
        if way == "red" and r["rg"] < RED_MIN:
            fails.append(f"{k}: not redder than skin (rg {r['rg']} < {RED_MIN})")
        if way == "pale" and r["dL"] < PALE_DL_MIN:
            fails.append(f"{k}: not paler than skin (dL {r['dL']} < {PALE_DL_MIN})")
        if way == "pale" and r["rg"] > PALE_RG_MAX:
            fails.append(f"{k}: redder than skin (rg {r['rg']} > {PALE_RG_MAX})")
    return fails


def unmarked(ob):
    """A mesh with no region marks (not an MPFB body): a uniform tint and base roughness, so the bake still
    gets the tone, the mottling and the relief."""
    me = ob.data
    n = len(me.vertices)
    me.attributes.new(TINT, "FLOAT_VECTOR", "POINT").data.foreach_set("vector", np.ones(n * 3, np.float32))
    me.attributes.new(OIL, "FLOAT", "POINT").data.foreach_set("value", np.full(n, BASE_ROUGH, np.float32))
