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

**Transmittance in Godot** reads a thickness toward the sun from the directional shadow map, whose texels are
millimetres wide at 1 m: on a finger, at the web between two and on an ear the thickness it reads is noise of
the size of the depth itself (and about zero just past the terminator, where the surface is its own occluder).
Skin mode's profile is pure red from about 0.1 depth on and ignores the colour's RGB (it uses only the alpha), so
at full strength and a 1 cm depth that noise drew thin saturated orange-red lines at the finger edges and the
thumb web, and red specks on the ears (lookdev `edges` measures them). The strength (the colour's alpha) is
0.2, so a mark the noise draws never outshines the skin under it, and the depth 3 cm, so real thin parts - finger
edges and webs, ears - still glow warm with the sun behind them while a whole palm (2-3 cm, 7+ in the profile's
units) does not. Skin mode stays: turning it off changes the screen-space scatter, and faces go grey.
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
# Measured on study_man's bake before humanform 0.14.0 (notebooks/realism-step2/skin-regions.md): knees, elbows,
# knuckles and cheeks sat at CIELAB dE 2.6-3.2 from plain skin - one just-noticeable difference, lost under light
# and mottle - and palms and soles were *redder* than skin. Now the red regions shift red against green (R/G of the
# multiplier 1.25-1.6) and the pale ones lift green and blue over red (paler, less red, a little yellow).
# Roughness: Weyrich et al. 2006 (measured faces, Torrance-Sparrow m 0.25-0.45 by region) and d'Eon & Luebke 2007
# (m 0.3 for skin) put skin's perceptual roughness (sqrt of the microfacet slope) near 0.5-0.6; the oily T-zone is
# the low end, not lacquer. Forehead/nose/chin 0.46 and lips 0.45 (was 0.38 and 0.36, which drew a white plateau).
REGIONS = {
    "lips":      {"tint": (0.84, 0.46, 0.50), "rough": 0.45},
    "nipple":    {"tint": (0.70, 0.50, 0.46), "rough": 0.48},
    "genital":   {"tint": (0.74, 0.46, 0.43), "rough": 0.50},
    "knee":      {"tint": (0.80, 0.52, 0.48), "rough": 0.58},
    "elbow":     {"tint": (0.78, 0.52, 0.48), "rough": 0.60},
    "knuckle":   {"tint": (0.76, 0.47, 0.44), "rough": 0.55},
    "palm":      {"tint": (1.35, 1.35, 1.24), "rough": 0.60},
    "sole":      {"tint": (1.32, 1.32, 1.14), "rough": 0.64},
    "flush":     {"tint": (1.00, 0.70, 0.70), "rough": 0.48},     # cheeks, nose tip, ears
    # nail 0.55 (humanform 0.15.0; was 0.30): MPFB's nail plate ends in a rim the overcast sky catches at grazing, and
    # at 1 m a glossy plate drew a pale crescent at every fingertip (notebooks/realism-step2/skin-finger-edges.md: the
    # crescent's added light fell 33 -> 21 -> 17 -> 14 -> 13 with the nail at 0.30/0.40/0.45/0.50/0.55). Keeping the
    # gloss on the plate and fading it at the free edge or roughening the fingertip pad left it as it was.
    "nail":      {"tint": (1.10, 0.92, 0.92), "rough": 0.55},
}
BASE_ROUGH = 0.50
T_ZONE_ROUGH = 0.46            # forehead, nose, chin: oilier than the rest, still skin
LIMB_ROUGH = 0.57              # forearms, shins: drier
MOTTLE = ((4.0, 0.08), (24.0, 0.035))    # (noise scale per metre, value share) - blotches ~25 cm, then ~4 cm
REDNESS = 0.07                 # the low octave also shifts red against green/blue by this share
# palms and soles by the brief's tone (humanform 0.14.0, critic round 1): palmar and plantar skin carries a fraction of
# the melanin of the rest (Yamaguchi et al. 2006; palmoplantar melanocyte density ~1/5 of the trunk's), so how much
# paler a palm is grows with how dark the body is - barely on pale skin, a lot on deep skin. The lift is a CIELAB
# lightness step dL = clip(PALE_SLOPE * (PALE_L0 - L*_tone), PALE_DL) turned into one linear gain, times a hue that
# takes a little red and more blue out (paler, a touch yellow, never green over red - that read olive in Godot).
# The table's palm/sole tints are what a body marked without a tone gets.
PALE_L0 = 80.0
PALE_SLOPE = 0.5
PALE_DL = (8.5, 16.0)
PALE_HUE = {"palm": (1.0, 0.985, 0.95), "sole": (1.0, 0.99, 0.90)}
# the regional contrast each bake must reach: CIELAB dE76 of the region's baked tone from plain skin, and which way
# (redder: region R/G over skin R/G at least RED_MIN; paler: lighter by PALE_DL_MIN and no redder than skin)
CONTRAST_FLOOR = {"lips": ("red", 8.0), "knee": ("red", 5.0), "elbow": ("red", 5.0), "knuckle": ("red", 5.0),
                  # set under the weakest body the fixtures build, not the strongest: study_woman reads
                  # genital 14.9 and nipple 15.3, but skin_detail's reads 8.3 and 9.3, and a floor that a
                  # legitimate body misses is a failure recorded as normal rather than a check
                  "genital": ("red", 7.0), "nipple": ("red", 8.0),
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
    # skin mode uses only the alpha (the strength); the RGB is what a non-skin mode would tint with
    "subsurf_scatter_transmittance_color": [0.92, 0.42, 0.30, 0.2],
    "subsurf_scatter_transmittance_depth": 0.03,   # m: finger edges, webs and ears glow; a whole palm must not
    "subsurf_scatter_transmittance_boost": 0.0,
    "metallic_specular": 0.42,
}
# The tiling detail lookdev draws on UV2 in Godot (lookdev_materials.gd set_detail). Pores alone (`cells` per tile,
# 0.3 mm on the face) are under a pixel at 1 m and mip away to a flat normal, so a coarser octave rides with them:
# `coarse_cells` per tile of larger pits of random depth with shallow furrows between (2.3 mm on the face, 3.7 mm
# on the body), in the normal (`coarse_weight` of the height, at `bump`) and as an albedo cavity (`cavity`, the
# darkening at the deepest point; the base colour is lifted back by its mean, `keep_base`, which also gives the
# baked normal map back what the detail mix takes). Its mips fade to flat where a cell is under 3 texels, so at full
# body it adds no shimmer. A 512 px tile 40 times across UV2 keeps the pores the size they were at 256 px / 80.
# `shared`: every body draws the same tile (the seed is left out), so a crowd pays for it once (2.3 MB, ~0.1 s).
DETAIL = {"normal": "pores", "tile_px": 512, "cells": 96, "uv2_scale": 40.0, "strength": 0.35, "bump": 5.5,
          "coarse_cells": 12, "coarse_px": 128, "coarse_weight": 0.7, "pit": 0.4, "furrow": 0.2, "furrow_depth": 0.4,
          "cavity": 0.26, "keep_base": True, "shared": True}
MPFB_GROUPS = {"lips": "lips", "nipple": "nipple", "nippleTip": "nipple", "ears": "flush",
               "fingernails": "nail", "toenails": "nail"}

# --- Creature skin (improvements 08, layer 3: surface): any tone, any pattern. Everything below is used only when
# a caller passes `species_skin`; with None every function above and below takes exactly the human path it always
# did. Nothing here knows a species: every default comes from the tone by the rules below, and the parameters are
# the only way to ask for more. `references/skin.md` says how to get from a description to the parameters.
#
#     look.skin(ob, (0.45, 0.52, 0.42), species_skin={
#         "regions_off": ["genital"],                        # REGIONS names left plain (and unchecked)
#         "pattern": {"kind": "blotches",                    # spots | stripes | blotches | mottle
#                     "colour": [0.33, 0.38, 0.30],          # sRGB, multiplied in as colour / tone
#                     "scale": 0.18,                         # m: spot spacing, stripe period, blotch size
#                     "amount": 0.6,                         # 0..1, the mask's strength
#                     "regions": ["back", "arms", "legs"]},  # optional, PATTERN_AREAS, their union; default all
#         "subsurface_tint": [0.5, 0.4, 0.3]})               # optional sRGB the scatter follows (default the tone)
#
# `{}` is a valid species_skin: the tone-relative rules with no pattern. (A species file's whole `skin` block may be
# passed: its `palette` is ignored here, since choosing the tone is the caller's job.) The rules, for a tone t in
# linear RGB with chroma c = t / geomean(t) (1, 1, 1 for a grey; its log is the direction of the tone's hue):
# - **Darker regions** (lips, areolae, genital skin, knees, elbows, knuckles, the flush) go darker and more
#   saturated ALONG THE TONE's own hue, never towards a human red: tint = d * c^s, normalised so it scales the
#   tone's luminance by d (the human table's factor) while s > 0 pushes the chroma further the way it already
#   points (SPECIES_DEEP). A green tone's lips are a deeper green, a tawny one's still come out warm.
# - **Nails** lighten and desaturate towards grey (SPECIES_NAIL) instead of the human pink.
# - **Palms and soles** keep `pale_tint`'s CIELAB lightness step from the tone's own L* (already tone-relative), but
#   not its hue: they lose a little saturation along the tone (SPECIES_PALE_SAT) instead.
# - **The contrast check**: a "red" floor becomes "deep" - the same dE floor, darker by DEEP_DL_MIN, and a CIELAB
#   hue within DEEP_HUE_MAX of plain skin's; a "pale" floor keeps its lightness step and swaps "no redder than
#   skin" for the same hue test; `regions_off` are not checked. The human tints on a green tone turn its lips
#   brown (hue 25 degrees off), which fails.
# - **Mottle** is stronger (SPECIES_MOTTLE) and its colour shift follows log c (darker patches more saturated in
#   the tone's own hue) instead of adding red.
# - **Subsurface**: the Blender radii are the human ones blended in log (SSS_TONE_SHARE) with radii proportional to
#   c^SSS_EXP of the scatter colour (`subsurface_tint`, else the tone), at the human radii's geometric mean: blood
#   still reddens the scatter, the tone decides which way it leans. Godot's skin-mode transmittance is a red
#   profile whatever the colour's RGB, so where the scatter is not red-dominant (radius R/G under
#   TRANSMIT_RG_MIN; the human radii are 2.7) transmittance is turned off rather than let a green ear glow red.
PATTERN = "hf_skin_pattern"    # float per vertex: where a pattern may show (written by mark)
PATTERN_KINDS = ("spots", "stripes", "blotches", "mottle", "scales")
# `graft`: the surface humanform.graft grew (a tail), fading up over its seam by the graft's own `fade`
PATTERN_AREAS = ("head", "torso", "arms", "legs", "back", "front", "graft")
PATTERN_SKIP = ("palm", "sole", "lips", "nail")     # never patterned
SPECIES_KEYS = ("regions_off", "pattern", "subsurface_tint", "palette")
# (d, s): the luminance factors are the human table's; s is set so a low-chroma (greyish) tone still shows its
# regions by hue as well as by value, and a saturated one's lips stay skin (at s 1.4 a saturated green's lips were a
# toy's green, chroma 45 against the skin's 30)
SPECIES_DEEP = {"lips": (0.52, 1.0), "nipple": (0.55, 0.8), "genital": (0.55, 0.7), "knee": (0.62, 0.6),
                "elbow": (0.62, 0.6), "knuckle": (0.58, 0.6), "flush": (0.85, 0.6)}
# stronger than a human's mottle (whose regional flush and vascular red already break the tone up), because along a
# green or grey tone nothing else does
SPECIES_MOTTLE = ((4.0, 0.11), (24.0, 0.05))
SPECIES_REDNESS = 0.10         # the low octave's colour shift, along log c
SPECIES_NAIL = (1.10, -0.4)    # luminance factor, saturation exponent (negative: towards grey)
SPECIES_PALE_SAT = -0.25       # palms and soles: `pale_tint`'s lift, a little less saturated along the tone
DEEP_DL_MIN = 1.0              # CIELAB L*: a deep region is darker than plain skin by at least this
# degrees of CIELAB hue from plain skin's. The tone-relative tints move hue 0-2 degrees on green and grey tones and
# up to 10 on a saturated warm one (its lips); the human tints on an olive tone move the lips 25
DEEP_HUE_MAX = 15.0
DEEP_CHROMA_MIN = 5.0          # below this chroma (on either) hue is not judged
SSS_TONE_SHARE = 0.5           # at 0.75 a saturated green's ear glowed chartreuse under a back light
SSS_EXP = 1.25                 # radius ~ chroma^1.25 fits the human radii against a human tone
TRANSMIT_RG_MIN = 1.8          # human 2.7, a tawny tone 2.3; grey-greens and olives 1.3-1.5


def _chroma(lin):
    lin = np.maximum(np.asarray(lin, np.float64)[:3], 1e-4)
    return lin / np.exp(np.log(lin).mean())


def _luma(lin):
    return float(np.dot([0.2126, 0.7152, 0.0722], lin))


def _along(lin, d, s):
    """A linear multiplier that scales the tone's luminance by `d` and its chroma by the power `s`."""
    c = _chroma(lin) ** s
    t = np.asarray(lin, np.float64)[:3]
    return tuple(round(float(v), 4) for v in d * c * _luma(t) / max(_luma(t * c), 1e-6))


def _rgb(v, what):
    try:
        v = [float(x) for x in v]
    except (TypeError, ValueError):
        raise ValueError(f"species_skin {what}: expected [r, g, b] sRGB 0..1, got {v!r}") from None
    if len(v) != 3 or not all(0.0 <= x <= 1.0 for x in v):
        raise ValueError(f"species_skin {what}: expected [r, g, b] sRGB 0..1, got {v!r}")
    return v


def species_check(sp):
    """`species_skin` validated and filled in (a plain dict, JSON-able), or None for None. Raises ValueError naming
    the key and the allowed values."""
    if sp is None:
        return None
    if not isinstance(sp, dict):
        raise ValueError(f"species_skin must be a dict, got {type(sp).__name__}")
    bad = sorted(set(sp) - set(SPECIES_KEYS))
    if bad:
        raise ValueError(f"species_skin: unknown key(s) {bad}; allowed {list(SPECIES_KEYS)}")
    off = list(sp.get("regions_off") or [])
    if any(k not in REGIONS for k in off):
        raise ValueError(f"species_skin regions_off {off}: each must be one of {list(REGIONS)}")
    out = {"regions_off": sorted(set(off))}
    if sp.get("subsurface_tint") is not None:
        out["subsurface_tint"] = _rgb(sp["subsurface_tint"], "subsurface_tint")
    pat = sp.get("pattern")
    if pat:
        bad = sorted(set(pat) - {"kind", "colour", "scale", "amount", "regions"})
        if bad:
            raise ValueError(f"species_skin pattern: unknown key(s) {bad}")
        if pat.get("kind") not in PATTERN_KINDS:
            raise ValueError(f"species_skin pattern kind {pat.get('kind')!r}: one of {list(PATTERN_KINDS)}")
        scale = float(pat.get("scale", 0.1))
        amount = float(pat.get("amount", 0.5))
        if not 0.005 <= scale <= 2.0:
            raise ValueError(f"species_skin pattern scale {scale} m: 0.005..2.0")
        if not 0.0 <= amount <= 1.0:
            raise ValueError(f"species_skin pattern amount {amount}: 0..1")
        areas = list(pat.get("regions") or [])
        if any(a not in PATTERN_AREAS for a in areas):
            raise ValueError(f"species_skin pattern regions {areas}: each one of {list(PATTERN_AREAS)}")
        if "colour" not in pat:
            raise ValueError("species_skin pattern: needs a colour [r, g, b] sRGB")
        out["pattern"] = {"kind": pat["kind"], "colour": _rgb(pat["colour"], "pattern colour"), "scale": scale,
                          "amount": amount, "regions": areas}
    return out


def species_tints(tone, sp):
    """The region tints a species skin uses for tone `tone` (sRGB): SPECIES_DEEP along the tone, the nail
    lightened, palms and soles as `pale_tint`. Regions off are left out."""
    lin = np.asarray(look.srgb_to_linear(tone)[:3], np.float64)
    out = {k: _along(lin, d, s) for k, (d, s) in SPECIES_DEEP.items()}
    out["nail"] = _along(lin, *SPECIES_NAIL)
    for k in ("palm", "sole"):
        # pale_tint's gain (its hue's red is 1) without its hue, which took green out and so read redder on a green body
        out[k] = _along(lin, pale_tint(tone, k)[0][0] / PALE_HUE[k][0], SPECIES_PALE_SAT)
    return {k: v for k, v in out.items() if k not in sp["regions_off"]}


def species_scatter(tone, sp):
    """(Blender subsurface radii in mm, Godot transmittance colour RGBA, transmittance on) for a species skin."""
    src = sp.get("subsurface_tint") or list(tone)[:3]
    c = _chroma(look.srgb_to_linear(src)[:3]) ** SSS_EXP
    human = np.asarray(SUBSURFACE["radius"], np.float64)
    gm = np.exp(np.log(human).mean())
    r = np.exp((1 - SSS_TONE_SHARE) * np.log(human) + SSS_TONE_SHARE * np.log(c * gm))
    col = r / r.max()
    on = bool(r[0] / r[1] >= TRANSMIT_RG_MIN)
    return (tuple(round(float(v), 4) for v in r), [round(float(v), 3) for v in col] + [0.2], on)


def species_godot(tone, sp):
    """GODOT for a species skin: transmittance tinted by the scatter colour, and off where skin mode would draw
    red on a body that does not scatter red."""
    _, col, on = species_scatter(tone, sp)
    g = dict(GODOT, subsurf_scatter_transmittance_color=col)
    if not on:
        g["subsurf_scatter_transmittance_enabled"] = False
    return g


def _species_of(held):
    import json
    s = held.get("species")
    return json.loads(s) if s else None


def pattern_areas(ob, sp):
    """Per-vertex weight (0..1) of where a species pattern shows on an MPFB human: the union of the pattern's
    `regions` (PATTERN_AREAS; all of the body if none), never on palms, soles, lips or nails."""
    from . import muscle
    n = min(len(ob.data.vertices), delta.BODY_VERTS)
    co = delta.mixed_coords(ob)
    faces = delta.body_faces(ob)
    p = co[:n]
    nrm = delta.vertex_normals(co, faces)[:n]
    areas = sp["pattern"]["regions"]
    j = muscle._joints(ob, co)
    need = ("joint-neck", "joint-pelvis", "joint-l-upper-leg", "joint-l-shoulder", "joint-l-elbow", "joint-l-hand")
    if not areas:
        m = np.ones(n)
    elif any(k not in j for k in need):
        m = np.ones(n)
    else:
        s = float((j["joint-neck"][2] - j["joint-pelvis"][2]) / 0.60)
        head = _smooth(j["joint-neck"][2] - 0.01 * s, j["joint-neck"][2] + 0.04 * s, p[:, 2])
        legs = 1.0 - _smooth(j["joint-l-upper-leg"][2] - 0.06 * s, j["joint-l-upper-leg"][2] + 0.02 * s, p[:, 2])
        arm = np.zeros(n)
        for side in (1.0, -1.0):
            pts = [np.array(j[k], np.float64) * np.array([side, 1, 1])
                   for k in ("joint-l-shoulder", "joint-l-elbow", "joint-l-hand")]
            pts.append(pts[2] + (pts[2] - pts[1]) * 0.6)                 # past the wrist: the hand
            d = np.full(n, 9.0)
            for a, b in zip(pts[:-1], pts[1:]):
                ab = b - a
                t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-9), 0, 1)
                d = np.minimum(d, np.linalg.norm(p - (a + np.outer(t, ab)), axis=1))
            outward = _smooth(0.5, 1.0, np.abs(p[:, 0]) / max(abs(j["joint-l-shoulder"][0]), 1e-6))
            arm = np.maximum(arm, (1.0 - _smooth(0.06 * s, 0.12 * s, d)) * outward)
        arm = arm * (1 - head)
        pick = {"head": head, "legs": legs * (1 - arm), "arms": arm, "graft": graft_area(ob, p),
                "torso": np.clip(1 - np.maximum(np.maximum(head, legs), arm), 0, 1),
                "back": _smooth(0.0, 0.45, nrm[:, 1]), "front": _smooth(0.0, 0.45, -nrm[:, 1])}   # MPFB faces -Y
        m = np.zeros(n)
        for a in areas:
            m = np.maximum(m, pick[a])
    w, _, _ = regions(ob)
    for k in PATTERN_SKIP:
        m = m * (1.0 - w[k])
    # soft borders (a pattern fading out, not cut off at a seam between areas)
    return np.clip(delta.smooth(m, faces, iterations=6, share=0.5)[:n], 0, 1)


def graft_area(ob, p):
    """0..1 over the body's own vertices `p`: 1 below a graft's seam (humanform.graft's PROP on the body), fading to 0
    over its `fade` above it; 0 everywhere on a body with no graft. The graft's own vertices are marked in `mark`."""
    import json
    info = ob.get("hf_graft")
    if not info:
        return np.zeros(len(p))
    info = json.loads(info)
    z0, fade = float(info["seam_z"]), max(float(info.get("fade", 0.08)), 1e-4)
    return 1.0 - _smooth(z0, z0 + fade, p[:, 2])


def graft_vertices(ob):
    """Indices of the vertices a graft added (its vertex group), or an empty array."""
    g = ob.vertex_groups.get("hf_graft")
    if g is None:
        return np.zeros(0, np.int64)
    return np.array([v.index for v in ob.data.vertices if any(e.group == g.index and e.weight > 0.5 for e in v.groups)],
                    np.int64)


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


def _sheet_sex(ob):
    """The brief's sex off the body's stored sheet, or None when it is not there (then the genital
    band keeps the sex-blind shape it had before humanform 0.17.0)."""
    try:
        return __import__("json").loads(ob["humanform_sheet"]).get("sex")
    except Exception:
        return None


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
    # the joint): scaled so its core reaches 1 (humanform 0.14.0; the knee's core was 0.86 before)
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
                        w["knuckle"] = np.maximum(w["knuckle"], hand * _gauss(p, J(nm), (0.011 if old else 0.0125) * s)
                                                  * _smooth(0.1, 0.5, -facing))
        else:
            notes.append("no finger joints: no palms or knuckles")
        # soles: below the ankle, facing down
        foot = on * (1.0 - _smooth(J("joint-l-ankle")[2] - 0.01 * s, J("joint-l-ankle")[2] + 0.02 * s, p[:, 2]))
        w["sole"] = np.maximum(w["sole"], foot * _smooth(-0.35, -0.75, nrm[:, 2]))
        # flush: the cheek below and outside each eye, facing forwards
        eye = J("joint-l-eye")
        cheek = eye + np.array([0.012 * side * xs * s, -0.005 * s, -0.035 * s])
        # (0.14.0: wider and fuller - at 1.8 cm and 0.8 the flush was a coin on the cheekbone)
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
    # A woman's tinted skin is the mons pubis and the labia, which reach higher than the hip-joint line
    # and wider than a man's midline strip. One sex-blind band gave 63 vertices on the study man and 60
    # on the study woman, while the anatomy there covers about 258 (humanform's own genital delta:
    # mons 148, labia 87, cleft 23), so most of a woman's was left plain.
    top, sigma = (0.03, 0.03) if _sheet_sex(ob) != "female" else (0.115, 0.070)
    band = _smooth(hip[2] + top * s, hip[2] - 0.02 * s, p[:, 2]) * _smooth(hip[2] - 0.16 * s, hip[2] - 0.10 * s, p[:, 2])
    mid_x = np.exp(-(p[:, 0] ** 2) / (2 * (sigma * s) ** 2))
    w["genital"] = band * mid_x * _smooth(-0.2, 0.3, front - nrm[:, 2] * 0.5) * (p[:, 1] < hip[1] + 0.02 * s)
    # T-zone: forehead, the nose and the chin, facing forwards
    face = _smooth(0.2, 0.6, front) * (p[:, 2] > eye_z - 0.12 * s)
    forehead = _smooth(eye_z + 0.01 * s, eye_z + 0.03 * s, p[:, 2]) * (1 - _smooth(eye_z + 0.07 * s, eye_z + 0.10 * s, p[:, 2]))
    strip = np.exp(-(p[:, 0] ** 2) / (2 * (0.012 * s) ** 2))
    extra["t_zone"] = face * np.maximum(forehead * (np.abs(p[:, 0]) < 0.06 * s), strip * (p[:, 2] < eye_z + 0.03 * s))
    for k in w:
        w[k] = np.clip(w[k], 0, 1) if k == "lips" else delta.smooth(np.clip(w[k], 0, 1), faces, iterations=1, share=0.5)[:n]
    return w, extra, notes


def pale_tint(srgb, region):
    """The palm or sole tint for a body of tone `srgb`: a linear gain that lifts CIELAB L* by PALE_SLOPE * (PALE_L0 -
    L*), clipped to PALE_DL, times PALE_HUE[region]. Returns (tint, dL)."""
    L = float(_lab(np.asarray(srgb, np.float64)[:3])[0])
    dl = float(np.clip(PALE_SLOPE * (PALE_L0 - L), *PALE_DL))

    def Y(l):
        f = (l + 16.0) / 116.0
        return f ** 3 if f > 6.0 / 29.0 else (l / 903.3)
    g = Y(min(L + dl, 100.0)) / max(Y(L), 1e-6)
    return tuple(round(g * h, 4) for h in PALE_HUE[region]), round(dl, 2)


def mark(ob, tone=None, species_skin=None):
    """Write `hf_skin_tint` and `hf_skin_oil` on an MPFB human (see `regions`). `tone` (the brief's sRGB) sets the
    palm and sole lift (`pale_tint`); without it they take REGIONS' fixed tints. `species_skin` (see PATTERN; it
    needs `tone`) takes its region tints along the tone, leaves `regions_off` plain and writes `hf_skin_pattern`.
    Returns a report."""
    ob = bpy.data.objects[ob] if isinstance(ob, str) else ob
    w, extra, notes = regions(ob)
    prm = params()
    pale = {}
    sp = species_check(species_skin)
    if sp is not None:
        if tone is None:
            raise ValueError("skin.mark: species_skin needs the tone")
        tints = species_tints(tone, sp)
        prm = dict(prm, REGIONS={k: dict(v, tint=tints.get(k, v["tint"])) for k, v in prm["REGIONS"].items()})
        for k in sp["regions_off"]:
            w[k] = np.zeros_like(w[k])
        for k in ("palm", "sole"):
            if k in tints:
                pale[k] = {"tint": list(tints[k]), "dL": pale_tint(tone, k)[1]}
        if "pattern" in sp:
            pm = pattern_areas(ob, sp)
            full = np.zeros(len(ob.data.vertices), np.float32)
            full[:len(pm)] = pm
            areas = sp["pattern"]["regions"]
            if not areas or "graft" in areas:
                full[graft_vertices(ob)] = 1.0          # a graft's own surface is all pattern
            if PATTERN in ob.data.attributes:
                ob.data.attributes.remove(ob.data.attributes[PATTERN])
            ob.data.attributes.new(PATTERN, "FLOAT", "POINT").data.foreach_set("value", full)
    elif tone is not None and not legacy():
        prm = dict(prm, REGIONS=dict(prm["REGIONS"]))
        for k in ("palm", "sole"):
            t, dl = pale_tint(tone, k)
            prm["REGIONS"][k] = dict(prm["REGIONS"][k], tint=t)
            pale[k] = {"tint": list(t), "dL": dl}
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
    rep = {"regions": {k: round(float((v > 0.5).sum()), 0) for k, v in w.items()},
           "t_zone": int((extra["t_zone"] > 0.5).sum()), "limb": int((extra["limb"] > 0.5).sum()), "notes": notes,
           "pale": pale}
    if sp is not None:
        rep["species"] = {"regions_off": sp["regions_off"], "pattern_verts": 0}
        if "pattern" in sp:
            pv = np.empty(len(me.vertices), np.float32)
            me.attributes[PATTERN].data.foreach_get("value", pv)
            rep["species"]["pattern_verts"] = int((pv > 0.5).sum())
    return rep


def seed_of(name):
    return zlib.crc32(name.encode("utf-8")) % 997


def _principled_skin(bsdf, lin, roughness, radius=None):
    """What every skin material has, flat or procedural: the tone, a roughness, subsurface and skin's F0."""
    bsdf.inputs["Base Color"].default_value = (*lin, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.subsurface_method = "RANDOM_WALK"
    bsdf.inputs["Subsurface Weight"].default_value = SUBSURFACE["weight"]
    bsdf.inputs["Subsurface Radius"].default_value = SUBSURFACE["radius"] if radius is None else radius
    bsdf.inputs["Subsurface Scale"].default_value = SUBSURFACE["scale"]
    if "Subsurface IOR" in bsdf.inputs:
        bsdf.inputs["Subsurface IOR"].default_value = SUBSURFACE["ior"]
    bsdf.inputs["Specular IOR Level"].default_value = SPECULAR_IOR_LEVEL
    bsdf.inputs["IOR"].default_value = SUBSURFACE["ior"]


def material(name, srgb, seed=None, roughness=BASE_ROUGH, procedural=False, species_skin=None):
    """The skin material, reused by name and rebuilt every call.

    By default it is FLAT: the brief's tone as an unlinked Base Color, one roughness, subsurface - what the glTF
    exporter can read (a linked Base Color it cannot trace to an image is exported as nothing, which Godot draws
    white) and it references no mesh attribute (so `hf_skin_*` are never exported as COLOR_n). A body exported
    without a bake gets this. `procedural=True` is what `bake` bakes and then replaces: the tone (linear) times
    `hf_skin_tint` times mottling, roughness from `hf_skin_oil`, a fine bump. `species_skin` (see PATTERN) gives
    the subsurface and Godot's transmittance the tone's scatter colour, mottles along the tone and adds the
    pattern; it is stored on the material (`humanform_skin["species"]`, JSON), so `bake` rebuilds the same."""
    seed = seed_of(name) if seed is None else seed
    sp = species_check(species_skin)
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
    _principled_skin(bsdf, lin, roughness, radius=None if sp is None else species_scatter(srgb, sp)[0])
    mat.diffuse_color = (*lin, 1.0)
    mat["lookdev"] = {"preset": "skin", "godot": dict(GODOT) if sp is None else species_godot(srgb, sp),
                      "detail": dict(DETAIL, seed=int(seed)),
                      "tone_srgb": [round(float(c), 4) for c in tuple(srgb)[:3]]}
    mat["humanform_skin"] = {"seed": int(seed), "tone_srgb": [round(float(c), 4) for c in tuple(srgb)[:3]],
                             "stage": "flat"}
    if sp is not None:
        mat["humanform_skin"] = dict(mat["humanform_skin"], species=__import__("json").dumps(sp))
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
    if sp is not None:
        prm = dict(prm, MOTTLE=SPECIES_MOTTLE, REDNESS=SPECIES_REDNESS)
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
        if i == 0 and sp is not None:
            # a species mottles along its own tone: channel c gets gain * (1 + k_c (inv - 1)), k the tone's
            # log-chroma scaled to 1 on its strongest channel (a human tone's k is red +1, blue about -1)
            lc = np.log(_chroma(lin))
            k = lc / max(float(np.abs(lc).max()), 1e-6)
            inv = N("ShaderNodeMath")
            inv.operation = "MULTIPLY_ADD"
            L(gain.outputs["Result"], inv.inputs[0])
            inv.inputs[1].default_value = -prm["REDNESS"] / share
            inv.inputs[2].default_value = 1.0 + prm["REDNESS"] / share
            for c, kc in zip(("Red", "Green", "Blue"), k):
                f = N("ShaderNodeMath")
                f.operation = "MULTIPLY_ADD"
                L(inv.outputs["Value"], f.inputs[0])
                f.inputs[1].default_value = float(kc)
                f.inputs[2].default_value = 1.0 - float(kc)
                both = N("ShaderNodeMath")
                both.operation = "MULTIPLY"
                L(f.outputs["Value"], both.inputs[0])
                L(gain.outputs["Result"], both.inputs[1])
                L(both.outputs["Value"], red.inputs[c])
        elif i == 0:
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
    if sp is not None and "pattern" in sp:
        col = _pattern_nodes(tree, coord, col, lin, sp["pattern"], seed)
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


def _pattern_nodes(tree, coord, col, lin, pat, seed):
    """A species pattern on the procedural skin: a mask (0..1) in object space, times `amount` and the
    `hf_skin_pattern` attribute, multiplying the colour by pattern colour / tone where it is 1. Returns the colour
    socket. Object space is metres on a body, so `scale` is the pattern's size in metres."""
    N, L = tree.nodes.new, tree.links.new
    size = pat["scale"]
    # the seed moves the pattern (wave has no W), and a low noise warps it so nothing is a perfect circle or line
    off = N("ShaderNodeVectorMath")
    off.operation = "ADD"
    L(coord.outputs["Object"], off.inputs[0])
    off.inputs[1].default_value = (seed * 0.371 % 17.0, seed * 0.613 % 13.0, seed * 0.137 % 11.0)
    warp = N("ShaderNodeTexNoise")
    warp.noise_dimensions = "3D"
    warp.inputs["Scale"].default_value = 1.2 / size
    warp.inputs["Detail"].default_value = 3.0
    L(off.outputs["Vector"], warp.inputs["Vector"])
    wc = N("ShaderNodeVectorMath")
    wc.operation = "SUBTRACT"
    L(warp.outputs["Color"], wc.inputs[0])
    wc.inputs[1].default_value = (0.5, 0.5, 0.5)
    ws = N("ShaderNodeVectorMath")
    ws.operation = "MULTIPLY_ADD"
    L(wc.outputs["Vector"], ws.inputs[0])
    ws.inputs[1].default_value = (0.45 * size,) * 3
    L(off.outputs["Vector"], ws.inputs[2])
    p = ws.outputs["Vector"]

    def ramp(value, lo, hi, invert=False):
        m = N("ShaderNodeMapRange")
        m.interpolation_type = "SMOOTHSTEP"
        L(value, m.inputs["Value"])
        m.inputs["From Min"].default_value = lo
        m.inputs["From Max"].default_value = hi
        m.inputs["To Min"].default_value = 1.0 if invert else 0.0
        m.inputs["To Max"].default_value = 0.0 if invert else 1.0
        return m

    kind = pat["kind"]
    if kind == "spots":
        vor = N("ShaderNodeTexVoronoi")
        vor.voronoi_dimensions = "3D"
        vor.feature = "F1"
        vor.inputs["Scale"].default_value = 1.0 / size
        vor.inputs["Randomness"].default_value = 1.0
        L(p, vor.inputs["Vector"])
        sep = N("ShaderNodeSeparateColor")
        L(vor.outputs["Color"], sep.inputs["Color"])
        # a radius per spot, 0.16-0.32 of the spacing, from the cell's random colour
        r0 = N("ShaderNodeMath")
        r0.operation = "MULTIPLY_ADD"
        L(sep.outputs["Green"], r0.inputs[0])
        r0.inputs[1].default_value = 0.16
        r0.inputs[2].default_value = 0.16 + 0.11          # the edge noise adds 0.11 on average
        r1 = N("ShaderNodeMath")
        r1.operation = "ADD"
        L(r0.outputs["Value"], r1.inputs[0])
        r1.inputs[1].default_value = 0.10
        # ragged edges: a fine noise added to the distance, so a spot is a blot, not a disc
        edge = N("ShaderNodeTexNoise")
        edge.noise_dimensions = "3D"
        edge.inputs["Scale"].default_value = 5.0 / size
        edge.inputs["Detail"].default_value = 4.0
        L(p, edge.inputs["Vector"])
        dist = N("ShaderNodeMath")
        dist.operation = "MULTIPLY_ADD"
        L(edge.outputs["Fac"], dist.inputs[0])
        dist.inputs[1].default_value = 0.22
        L(vor.outputs["Distance"], dist.inputs[2])
        m = ramp(dist.outputs["Value"], 0.0, 1.0, invert=True)
        L(r0.outputs["Value"], m.inputs["From Min"])
        L(r1.outputs["Value"], m.inputs["From Max"])
        keep = ramp(sep.outputs["Red"], 0.12, 0.22)          # about one cell in six has no spot
        dark = N("ShaderNodeMath")                            # and each is 0.6-1.0 as dark
        dark.operation = "MULTIPLY_ADD"
        L(sep.outputs["Blue"], dark.inputs[0])
        dark.inputs[1].default_value = 0.4
        dark.inputs[2].default_value = 0.6
        mask = N("ShaderNodeMath")
        mask.operation = "MULTIPLY"
        L(m.outputs["Result"], mask.inputs[0])
        L(keep.outputs["Result"], mask.inputs[1])
        mask2 = N("ShaderNodeMath")
        mask2.operation = "MULTIPLY"
        L(mask.outputs["Value"], mask2.inputs[0])
        L(dark.outputs["Value"], mask2.inputs[1])
        mask = mask2.outputs["Value"]
    elif kind == "stripes":
        wave = N("ShaderNodeTexWave")
        wave.wave_type = "BANDS"
        wave.bands_direction = "Z"
        wave.wave_profile = "SIN"
        wave.inputs["Scale"].default_value = 0.3183 / size      # Blender's bands: sin(20 * scale * z), period `size`
        wave.inputs["Distortion"].default_value = 4.0
        wave.inputs["Detail"].default_value = 2.0
        wave.inputs["Detail Scale"].default_value = 1.5
        L(p, wave.inputs["Vector"])
        mask = ramp(wave.outputs["Fac"], 0.62, 0.80).outputs["Result"]
    elif kind == "scales":
        # overlapping scales: a semi-regular cell per scale, stretched a little along the body (Z), each shaded
        # from its covered upper part (dark) to its free lower rim (light), with a dark outline. The mask is
        # full: the colour is the pattern's, and the shading multiplies it below
        sc = N("ShaderNodeVectorMath")
        sc.operation = "MULTIPLY"
        L(off.outputs["Vector"], sc.inputs[0])
        sc.inputs[1].default_value = (1.0 / size, 1.0 / size, 1.0 / (0.8 * size))
        vor = N("ShaderNodeTexVoronoi")
        vor.voronoi_dimensions = "3D"
        vor.feature = "F1"
        vor.inputs["Scale"].default_value = 1.0
        vor.inputs["Randomness"].default_value = 0.35
        L(sc.outputs["Vector"], vor.inputs["Vector"])
        loc = N("ShaderNodeVectorMath")
        loc.operation = "SUBTRACT"
        L(sc.outputs["Vector"], loc.inputs[0])
        L(vor.outputs["Position"], loc.inputs[1])
        sep = N("ShaderNodeSeparateXYZ")
        L(loc.outputs["Vector"], sep.inputs[0])
        shade = ramp(sep.outputs["Z"], -0.45, 0.45, invert=True)      # 1 at the free lower rim, 0 at the top
        edge = N("ShaderNodeTexVoronoi")
        edge.voronoi_dimensions = "3D"
        edge.feature = "DISTANCE_TO_EDGE"
        edge.inputs["Scale"].default_value = 1.0
        edge.inputs["Randomness"].default_value = 0.35
        L(sc.outputs["Vector"], edge.inputs["Vector"])
        line = ramp(edge.outputs["Distance"], 0.0, 0.09, invert=True)  # 1 on a scale's outline
        bright = N("ShaderNodeMath")
        bright.operation = "MULTIPLY_ADD"
        L(shade.outputs["Result"], bright.inputs[0])
        bright.inputs[1].default_value = 0.45
        bright.inputs[2].default_value = 0.6
        dark = N("ShaderNodeMath")
        dark.operation = "MULTIPLY_ADD"
        L(line.outputs["Result"], dark.inputs[0])
        dark.inputs[1].default_value = -0.45
        dark.inputs[2].default_value = 1.0
        shading = N("ShaderNodeMath")
        shading.operation = "MULTIPLY"
        L(bright.outputs["Value"], shading.inputs[0])
        L(dark.outputs["Value"], shading.inputs[1])
        one = N("ShaderNodeValue")
        one.outputs[0].default_value = 1.0
        mask = one.outputs[0]
        scale_shading = shading.outputs["Value"]
    else:
        nz = N("ShaderNodeTexNoise")
        nz.noise_dimensions = "3D"
        nz.inputs["Scale"].default_value = 1.0 / size
        nz.inputs["Detail"].default_value = 3.0 if kind == "blotches" else 4.0
        nz.inputs["Roughness"].default_value = 0.55
        L(p, nz.inputs["Vector"])
        lo, hi = (0.50, 0.58) if kind == "blotches" else (0.36, 0.64)
        mask = ramp(nz.outputs["Fac"], lo, hi).outputs["Result"]
    where = N("ShaderNodeAttribute")
    where.attribute_type = "GEOMETRY"
    where.attribute_name = PATTERN
    amt = N("ShaderNodeMath")
    amt.operation = "MULTIPLY"
    L(mask, amt.inputs[0])
    L(where.outputs["Fac"], amt.inputs[1])
    fac = N("ShaderNodeMath")
    fac.operation = "MULTIPLY"
    fac.use_clamp = True
    L(amt.outputs["Value"], fac.inputs[0])
    fac.inputs[1].default_value = pat["amount"]
    ratio = np.asarray(look.srgb_to_linear(pat["colour"])[:3]) / np.maximum(np.asarray(lin, np.float64), 1e-4)
    mix = N("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    L(fac.outputs["Value"], mix.inputs["Factor"])
    L(col, mix.inputs[6])
    mix.inputs[7].default_value = (*[float(v) for v in ratio], 1.0)
    if kind != "scales":
        return mix.outputs[2]
    # the scales' own shading, where the pattern is: colour x (1 - fac (1 - shading))
    inv = N("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    L(scale_shading, inv.inputs[1])
    k = N("ShaderNodeMath")
    k.operation = "MULTIPLY"
    L(inv.outputs["Value"], k.inputs[0])
    L(fac.outputs["Value"], k.inputs[1])
    g = N("ShaderNodeMath")
    g.operation = "SUBTRACT"
    g.inputs[0].default_value = 1.0
    L(k.outputs["Value"], g.inputs[1])
    mul = N("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    L(mix.outputs[2], mul.inputs[6])
    gc = N("ShaderNodeCombineColor")
    for ch in ("Red", "Green", "Blue"):
        L(g.outputs["Value"], gc.inputs[ch])
    L(gc.outputs["Color"], mul.inputs[7])
    return mul.outputs[2]


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
    sp = _species_of(held)

    def flat():
        # the bake failed: back to the flat material the exporter reads (never a procedural one it cannot)
        material(mat.name, target, seed=seed, species_skin=sp)
        mat["humanform_skin"] = dict(held, stage="flat")

    if TINT not in ob.data.attributes:
        unmarked(ob)
    if sp is not None and "pattern" in sp and PATTERN not in ob.data.attributes:
        # an unmarked mesh: the pattern everywhere
        ob.data.attributes.new(PATTERN, "FLOAT", "POINT").data.foreach_set(
            "value", np.ones(len(ob.data.vertices), np.float32))
    material(mat.name, target, seed=seed, procedural=True, species_skin=sp)
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
            if graft_rect is not None:
                # a graft's surface (a tail) has its own colour: the tone the brief gives is the skin's, so the
                # mean is held over the rest of the atlas
                side = int(round(np.sqrt(len(cov))))
                yy, xx = np.divmod(np.arange(len(cov)), side)
                u, v = (xx + 0.5) / side, (yy + 0.5) / side
                u0, v0, u1, v1 = graft_rect
                inside = (u >= u0) & (u <= u1) & (v >= v0) & (v <= v1)
                if (cov & ~inside).any():
                    cov = cov & ~inside
                means["graft_texels"] = int((self.coverage & inside).sum())
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
                ref = loop_region == 0
                if loop_plain is not None and (ref & loop_plain).sum() >= 0.05 * ref.sum():
                    ref = ref & loop_plain          # plain skin the pattern cannot reach, if there is enough of it
                plain = out[texel[ref], :3].astype(np.float64).mean(axis=0)
                means["regions"]["skin"] = [round(float(v), 3) for v in plain]
                means["contrast"] = contrast({k: out[texel[loop_region == i + 1], :3].astype(np.float64).mean(axis=0)
                                              for i, k in enumerate(REGIONS) if (loop_region == i + 1).any()}, plain,
                                             hue=sp is not None)
            return out.ravel()

    graft_rect = None
    if ob.get("hf_graft"):
        import json as _json
        graft_rect = (_json.loads(ob["hf_graft"]).get("uv_rect") or None)
    me = ob.data
    loop_uv = loop_region = loop_plain = None
    if REGION in me.attributes and me.uv_layers.active is not None:
        loop_uv = np.empty(len(me.loops) * 2, np.float32)
        me.uv_layers.active.data.foreach_get("uv", loop_uv)
        loop_uv = np.mod(loop_uv.reshape(-1, 2), 1.0)
        lv = np.empty(len(me.loops), np.int64)
        me.loops.foreach_get("vertex_index", lv)
        vr = np.empty(len(me.vertices), np.int32)
        me.attributes[REGION].data.foreach_get("value", vr)
        loop_region = vr[lv]
        if sp is not None and "pattern" in sp and PATTERN in me.attributes:
            # a pattern darkens plain skin's mean, and a region it does not reach (a face) would be judged against it
            pv = np.empty(len(me.vertices), np.float32)
            me.attributes[PATTERN].data.foreach_get("value", pv)
            loop_plain = pv[lv] < 0.1
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
        extra["contrast_fail"] = contrast_fails(means["contrast"], species=sp)
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


def _hue(lab):
    return float(np.degrees(np.arctan2(lab[2], lab[1]))), float(np.hypot(lab[1], lab[2]))


def contrast(tones, plain, hue=False):
    """Each region's baked tone against plain skin's (both sRGB): `dE` (CIELAB 1976), `dL` (lightness) and `rg`,
    the region's red/green ratio over skin's (above 1 is redder). `hue` (a species skin) adds `dh`, the CIELAB
    hue angle from plain skin's in degrees, and `C`, the region's chroma. The free values; `contrast_fails`
    judges them."""
    plain = np.asarray(plain, np.float64)
    lp = _lab(plain)
    out = {}
    for k, v in tones.items():
        v = np.asarray(v, np.float64)
        lv = _lab(v)
        out[k] = {"dE": round(float(np.linalg.norm(lv - lp)), 2), "dL": round(float(lv[0] - lp[0]), 2),
                  "rg": round(float((v[0] / max(v[1], 1e-6)) / max(plain[0] / max(plain[1], 1e-6), 1e-6)), 3)}
        if hue:
            (h, c), (hp, cp) = _hue(lv), _hue(lp)
            out[k]["dh"] = round(float((h - hp + 180.0) % 360.0 - 180.0), 1)
            out[k]["C"] = round(c, 2)
    if hue:
        out["skin"] = {"C": round(_hue(lp)[1], 2), "h": round(_hue(lp)[0], 1)}
    return out


def contrast_fails(c, species=None):
    """What in a `contrast` report is under CONTRAST_FLOOR: ["knee: dE 2.96 < 5.0", "palm: redder than skin
    (rg 1.04)", ...]. A floored region the body has no texels of fails too ("knee: no texels"): a mask that lost a
    region must not pass by being absent. (Only a body with region marks gets a `contrast` report at all.)

    With `species` (a checked species_skin) a "red" floor is "deep": the same dE, darker by DEEP_DL_MIN, and a hue
    within DEEP_HUE_MAX of plain skin's where both have chroma (so no human-red lip on a green body); the
    species' `regions_off` are not judged."""
    fails = []
    off = set(species["regions_off"]) if species else set()
    for k, (way, floor) in CONTRAST_FLOOR.items():
        if k in off:
            continue
        if species and way == "red":
            way = "deep"
        if k not in c:
            fails.append(f"{k}: no texels")
            continue
        r = c[k]
        if r["dE"] < floor:
            fails.append(f"{k}: dE {r['dE']} < {floor}")
        if way == "deep":
            if r["dL"] > -DEEP_DL_MIN:
                fails.append(f"{k}: not darker than skin (dL {r['dL']} > -{DEEP_DL_MIN})")
            cs = (c.get("skin") or {}).get("C", 0.0)
            if "dh" in r and min(cs, r.get("C", 0.0)) >= DEEP_CHROMA_MIN and abs(r["dh"]) > DEEP_HUE_MAX:
                fails.append(f"{k}: off the tone's hue (dh {r['dh']} deg, over {DEEP_HUE_MAX})")
        if way == "red" and r["rg"] < RED_MIN:
            fails.append(f"{k}: not redder than skin (rg {r['rg']} < {RED_MIN})")
        if way == "pale" and r["dL"] < PALE_DL_MIN:
            fails.append(f"{k}: not paler than skin (dL {r['dL']} < {PALE_DL_MIN})")
        if way == "pale" and species:
            cs = (c.get("skin") or {}).get("C", 0.0)
            if "dh" in r and min(cs, r.get("C", 0.0)) >= DEEP_CHROMA_MIN and abs(r["dh"]) > DEEP_HUE_MAX:
                fails.append(f"{k}: off the tone's hue (dh {r['dh']} deg, over {DEEP_HUE_MAX})")
        elif way == "pale" and r["rg"] > PALE_RG_MAX:
            fails.append(f"{k}: redder than skin (rg {r['rg']} > {PALE_RG_MAX})")
    return fails


def unmarked(ob):
    """A mesh with no region marks (not an MPFB body): a uniform tint and base roughness, so the bake still
    gets the tone, the mottling and the relief."""
    me = ob.data
    n = len(me.vertices)
    me.attributes.new(TINT, "FLOAT_VECTOR", "POINT").data.foreach_set("vector", np.ones(n * 3, np.float32))
    me.attributes.new(OIL, "FLOAT", "POINT").data.foreach_set("value", np.full(n, BASE_ROUGH, np.float32))
