"""L6 part: eyebrows, eyelashes and light body hair on a baked MPFB body, and where its ears are.

    rep = brows.add(body, lm, colour=(0.12, 0.08, 0.05), base="StudyMan", brows=True, lashes=True)
    rep["objects"]      # {"brows": "StudyMan_brows", "lashes": "StudyMan_lashes"}
    brows.add(..., body_hair=True, sex="male")    # + "StudyMan_body_hair": forearms, shins, pubic; chest,
                                                  #   belly and thighs on a man
    brows.ear_vertices(body)                      # {"L": [...], "R": [...]} body vertex indices, or None

`hair.add(..., brows=True, lashes=True, body_hair=False)` calls this; the pipeline's `[hair]` section passes
the three switches through.

**Where things go.** A baked humanform body keeps MPFB's body vertices 0..13379 in base-mesh order (the
bake deletes only the helpers after them). `data/face_regions.json`, written by
`scripts/derive_face_regions.py` from MPFB's `base.obj`, stores by base index:
- the ears (the vertices MPFB's ear flap, wing and lobe targets bend), which `hair` keeps its cap off;
- MPFB's eyelash helper cards (`helper-{l,r}-eyelashes-{1,2}`, upper and lower lid, 92 quads a side), which
  the bake deletes, as proxy fits: each card vertex is a triangle of body vertices, barycentric weights and
  an offset along the triangle's normal in units of the triangle's size, so the cards follow the lids
  through every target and the fit;
- a brow card on each brow ridge (16 x 4), laid on the neutral face from the eye and stored the same way.

**Materials.** lookdev's hair material (`lookdev_blender.hair.material`) with its own strand settings per
part, so glTF carries alphaMode MASK, the strand texture and the `lookdev` extras that
`LookdevMaterials.apply` re-applies in Godot. Brows take the `[hair]` colour darkened by `BROW_DARKEN`,
lashes by `LASH_DARKEN`; lashes are two-sided (glTF doubleSided). Brow strands lean along the brow: V runs
across it from the lower edge (roots) to the upper edge (tips), U is sheared so a strand runs up and
toward the temple, upright at the brow's head and nearly along it by its tail.

Brows and lashes draw their own pixels (`card_pixels`) and hand them to lookdev's material (`pixels=`, card
mode) rather than overwriting the images lookdev made: separate hairs two or three texels wide tapering to under
one, skin between them (the hair texture's opaque middle band made the brow an ink stroke and the lashes an
eyeliner ring). U runs once along each brow and along each lid's card (upper lid
in the texture's left half, lower in its right), so the brow feathers in at its head and thins into its tail
and the lower lashes are fewer and finer. In Godot the cards are alpha-blended with no rim, backlight or
anisotropy (`CARD_GODOT`: at a grazing angle they lit a brow's tail into a grey sliver), and their alpha extras
(`CARD_ALPHA`) have lookdev rebuild the mips to keep each level's coverage and ramp alpha over 0.5 +- 0.25:
scissor drew them as hard, pixelated black cut-outs, twice as dark in their darkest pixels as Blender's close
set. In Blender their shadows are transparent (an opaque lash card shadowed a streak onto the cheek).

**Body hair** (off unless asked): a shell 0.3 mm off the skin over the regions, cut from the body's faces
by bone weight (and facing, for the torso), with a sparse strand texture - the hair texture with most of
its strands removed in bands and the rest staggered - repeating in V every `BODY_HAIR_STRAND_M` along the
limb (down the torso), so it reads as short hairs with skin between them.

Everything is skinned like the body under it (weights interpolated from the triangle each vertex rides,
the head for brows and lashes). A body that is not an MPFB body (fewer than 13380 vertices) gets none of
it, and the report says so.
"""

from __future__ import annotations

import json
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector

BROW_DARKEN = 0.8           # brow colour: the hair colour's sRGB channels times this
LASH_DARKEN = 0.4
BODY_HAIR_DARKEN = 0.8
BODY_HAIR_STRAND_M = 0.014  # one strand's length on the skin; V repeats every this far
BODY_HAIR_KEEP = 0.22       # share of the texture's strand bands kept
BODY_HAIR_LIFT_M = 0.0003
TILE_M = 0.04
GODOT_SCISSOR = 2           # BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
GODOT_BLEND = 1             # BaseMaterial3D.TRANSPARENCY_ALPHA
GODOT_FILTER_ANISOTROPIC = 5    # BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC

# lookdev hair preset overrides per part (keys of lookdev's `hair` material preset). Brows and lashes then
# get their own pixels (`card_pixels`): U runs once along each brow / lid (0..1, not tiled), so the strands
# can thin toward the brow's tail and the lid's corners, and every strand is a hair's width with skin between.
LOOK = {
    "brows": {"texture_px": [1024, 256], "mode": "card"},
    "lashes": {"texture_px": [1024, 256], "mode": "card"},
    "body_hair": {"texture_px": [256, 512], "strands_per_tile": 48, "root_zone": [0.05, 0.4], "tip_zone": [0.6, 0.95],
                  "root_fade": [0.0, 0.2], "tip_mult": 1.15, "gap_mult": 0.5, "wave_px": 1.2},
    "beard": {"texture_px": [512, 512]},     # its own pixels (`beard_pixels`)
    # the strand cards' own sheet: the same hairs at the same size, but no under-layer between them - a card
    # has to show skin (or the shell) through its gaps or it is a brown strip
    "beard_cards": {"texture_px": [512, 512]},
}

# Facial hair (`add(beard=...)`): a shell over the lower face with strand cards grown out of it and, for a long
# beard, a hanging part that sways, placed from the face's own features (data/face_features.json: the mouth's slit and corners, the nose's
# base) and the head bone's weights. Where it grows is a signed distance on the face (`beard_field`), so its edge
# is a smooth curve faded over `feather_m` (vertex alpha, interpolated across faces), not a line of whole faces.
# Each style: the regions it covers, `lift_m` off the skin, a hair's length in the texture (`strand_m`), the share
# of the texture its hairs cover (`cover`), whether an opaque under-layer fills between them (`under`: a full
# beard hides the skin the way a scalp's cap does; stubble shows it), the fade (`feather_m`), and its `length_m`
# at the chin and `volume` (0..1): `beard_spec` turns those into the cards' count and length and, past
# BEARD_HANG_MIN_M, a hanging part of its own. A spec can set `hair.beard_length` / `beard_volume` / `beard_braids`.
#
# The texture (`beard_pixels`) is square on the skin: BEARD_PX texels over TILE_M both ways, and every part's UVs
# are arc lengths in those units, so a texel is as long along the hairs as across them. The first beards
# repeated V every strand (12 mm over 512 rows against 40 mm over 256 across): Godot picked the mip by V and
# sampled U seven times too coarse, and the texture's 35% holes - kept at every level by the coverage mips - came
# out as a grid of square patches of skin in the game (Blender's review samples level 0). `hairtex.mip_check`
# fails a beard like that before it is exported.
#
# **Cards.** A beard is hair, so everything longer than a few millimetres grows as strand cards - the same
# thing scalp hair's fall and strands are - and the shell is only the root mat under them (a style's `cards`;
# `_beard_cards`). Layered shells were what made a beard read as a brown decal: a layer is the face's own
# surface offset along its normal, so its outline is the fade's zero line, a smooth curve, and no texture makes
# a curve look like the ends of hairs. `hairtex.silhouette_check` is the check that says so, in pixels.
# **Stubble keeps the shell and grows no cards**, because a shell is right there: a 2.5 mm hair is a third of a
# screen pixel long at 4 m and eight at 0.6 m, so a card could not show its length, only cost its geometry -
# what reads as stubble is the texture's dots on the skin, which is exactly what a shell draws.
BEARD_STYLES = {
    "stubble": {"regions": ("moustache", "corners", "chin", "jaw"), "lift_m": 0.0003, "strand_m": 0.0025,
                "cover": 0.4, "under": False, "feather_m": 0.005, "length_m": 0.0025, "volume": 0.0,
                "cards": None},
    "short": {"regions": ("moustache", "corners", "chin", "jaw"), "lift_m": 0.0025, "strand_m": 0.012,
              "cover": 0.85, "under": True, "feather_m": 0.005, "length_m": 0.014, "volume": 0.25,
              "cards": {"density": 40000, "width_m": 0.0055, "clump": 0.45, "cover": 0.5, "strand_m": 0.012,
                        "jitter": 0.3, "sweep": 0.15, "droop": 0.18, "taper": 0.45, "shade": 0.1}},
    "goatee": {"regions": ("moustache", "corners", "chin"), "lift_m": 0.0025, "strand_m": 0.012, "cover": 0.85,
               "under": True, "feather_m": 0.005, "length_m": 0.014, "volume": 0.25,
               "cards": {"density": 40000, "width_m": 0.0055, "clump": 0.45, "cover": 0.5, "strand_m": 0.012,
                         "jitter": 0.3, "sweep": 0.15, "droop": 0.18, "taper": 0.45, "shade": 0.1}},
    "moustache": {"regions": ("moustache",), "lift_m": 0.002, "strand_m": 0.010, "cover": 0.85, "under": True,
                  "feather_m": 0.003, "length_m": 0.012, "volume": 0.2,
                  "cards": {"density": 70000, "width_m": 0.005, "clump": 0.5, "cover": 0.5, "strand_m": 0.010,
                            "jitter": 0.3, "sweep": 0.45, "droop": 0.12, "taper": 0.4, "shade": 0.1}},
    "full": {"regions": ("moustache", "corners", "chin", "jaw"), "lift_m": 0.003, "strand_m": 0.02, "cover": 0.85,
             "under": True, "feather_m": 0.007, "length_m": 0.055, "volume": 0.6,
             "cards": {"density": 26000, "width_m": 0.0085, "clump": 0.55, "cover": 0.5, "strand_m": 0.02,
                       "jitter": 0.35, "sweep": 0.2, "droop": 0.3, "taper": 0.35,
                       "layers": 2, "layer_gap_m": 0.006, "layer_taper": 0.35, "shade": 0.14}},
    # the long beard is a mass, not a curtain: three layers deep with the outer ones shorter, three locks of
    # unequal length gathering as they fall, drawn in toward the midline by its tip, and a tone per clump
    "long": {"regions": ("moustache", "corners", "chin", "jaw"), "lift_m": 0.003, "strand_m": 0.03, "cover": 0.85,
             "under": True, "feather_m": 0.007, "length_m": 0.24, "volume": 0.7,
             "cards": {"density": 24000, "width_m": 0.011, "clump": 0.7, "cover": 0.5, "strand_m": 0.03,
                       "jitter": 0.45, "sweep": 0.2, "droop": 0.5, "taper": 0.28,
                       "layers": 3, "layer_gap_m": 0.011, "layer_taper": 0.45, "shade": 0.17, "plumb": 0.92,
                       "locks": 3, "lock_spread": 0.3, "gather": 0.5, "narrow": 0.42}},
}
BEARD_PX = 512              # texels per TILE_M, both ways (0.08 mm: a beard hair is 0.1-0.15 mm)
BEARD_UNDER_ALPHA = 0.51    # a full beard's alpha between its hairs: over the 0.5 cutoff at every mip ...
BEARD_UNDER_MAX = 1.0       # ... and up to this, varied over a few millimetres, so the fade takes it away
                            # gradually instead of all at once (see `beard_pixels`). The span has to cover the
                            # WHOLE fade ramp: a texel at alpha a is cut once the fade drops under 0.5/a, so
                            # 0.55..0.92 all went between fade 0.9 and 0.55 - a third of the ramp, which on
                            # hm08's 8-10 mm quads is still about one face. Stubble, which has no under-layer
                            # at all, dissolves perfectly; this is what makes a full beard's mat do the same.
BEARD_GAP = 0.45            # the under-layer's brightness against a hair's: the shadow between hairs
BEARD_FADE = "hf_beard_fade"    # the colour attribute whose alpha thins the hairs toward the beard's edge
BEARD_LIP_CLEAR_M = 0.0015  # the beard's edge along the lips: this far off the lips' red and the mouth's slit
BEARD_LIP_RIM_M = 0.008    # the lip set's outer ring further than this from the slit is skin, not lip
BEARD_FACING_M = 0.03       # a facing condition (a normal's component) counts this many metres a unit
BEARD_STAND_MAX_M = 0.025   # the layers stand off at most volume x this (a longer beard hangs instead)
BEARD_OUTER_THIN = 0.4      # the outermost layer's fade is this much lower: fewer, longer-looking hairs
BEARD_HANG_MIN_M = 0.06     # a beard longer than this at the chin hangs below it
BEARD_HAIR_ATTR = "hf_hair"     # point attribute set on the beard: hair, not skin (follow-through flesh.HAIR_ATTR)
BEARD_HANG_CLEAR_M = 0.055  # a hanging beard's back stays this far in front of the BARE body, and past the chin
                            # it hangs plumb from where it left the jaw rather than following the chest in
                            # (`cards` `plumb`). Clearance alone could not do this: a jersey shirt hung from the
                            # apex of a stocky chest stands up to 9 cm off the skin, so at 20, 38 and 75 mm the
                            # dwarf's beard was still under his t-shirt. `stages.hair_clearance` measures what
                            # is actually left once the clothes are on.
BEARD_DARKEN = 0.95
BEARD_AXIS_M = 0.07         # the beard's UVs run round and down about a centre this far behind the mouth
# the strand cards `humanform.cards` grows out of the beard field (everything else about a card - its shape,
# its clumping, its sheet, the cut where it starts to hang, its checks - is that module's, shared with fur's
# mane, ruff and tail brush)
BEARD_MAT_FEATHER_M = 0.024 # the root mat's ALPHA ramps from cut to solid over this much of the field,
                            # several faces wide, not over `feather_m`. The mat is whole body faces, so a ramp
                            # narrower than one face steps from face to face: the cheek line came out a
                            # staircase (`hairtex.silhouette_check`'s top edge measures it now). The geometry
                            # is still cut at the field; only the alpha reaches further in.
BEARD_CARD_OVERHANG_M = 0.016   # how far past the root mat's rim the cards still take roots
BEARD_MAT_SPAN_MAX = 0.30   # the most of that ramp one face may hold: 0.3 is two faces across it
BEARD_CARD_CLEAR_M = 0.0018     # a card never comes nearer the skin than this
BEARD_MOUSTACHE_MAX_M = 0.02    # a moustache card is never longer: a long beard's would bury the mouth
BEARD_HANG_SPLIT_M = 0.055  # a card whose tip falls this far below the chin hangs, and is cut there: the
                            # strand mesh starts clear of the hollow under the jaw, which the head's own
                            # surface calls solid (at 30 mm the chain's first bone still swung its top rows
                            # into it and `verify_strands` read 6 mm; at 55 mm it reads under 2)
# Godot: no rim, backlight or anisotropic sheen on hairs this fine - at a grazing angle (a brow's tail round
# the temple) they light a whole card's strands into a grey sliver
CARD_GODOT = {"transparency": GODOT_BLEND, "rim_enabled": False, "backlight_enabled": False,
              "anisotropy_enabled": False, "roughness": 0.75, "metallic_specular": 0.2,
              "texture_filter": GODOT_FILTER_ANISOTROPIC}
# blended cards: mips that keep level 0's coverage (lashes lost 60% of it by the fifth mip, and a blended
# card's mean alpha is its coverage) and alpha ramped over 0.5 +- 0.25, so a hair is dark in its core and soft
# at its sides - what Blender's supersampled alpha test looks like. edge 0.5 left brows a grey haze, 0.15 too dark.
CARD_ALPHA = {"coverage_mips": 0.5, "edge": 0.25}
# the lash texture's two halves: upper lid in U 0.02..0.48, lower lid in 0.52..0.98 (outer corner at 0.02 / 0.98)
LASH_U = {"upper": (0.02, 0.48), "lower": (0.52, 0.98)}
# per lid: `n` lashes `lengths` of the card long (before the corner's reach), `width` texels at the root, leaning
# `gather` of the way to their clump's centre; then `short` lashes `short_lengths` long packed at the root. Seen
# from the front the upper card is steep to the eye (its tips rise only about 16 deg), so a lash is a few
# screen pixels long: 170 lashes gathered 0.6 read as a few dark streaks on the lid; the lash line needs
# density at the root.
LASHES = {"upper": {"n": 260, "lengths": (0.55, 0.97), "width": (1.3, 1.9), "gather": 0.25,
                    "short": 160, "short_lengths": (0.1, 0.3)},
          "lower": {"n": 45, "lengths": (0.35, 0.7), "width": (1.1, 1.6), "gather": 0.6,
                    "short": 0, "short_lengths": (0.1, 0.2)}}

# brow shapes (`add(brow_shape=)`, a brief's `hair.brow_shape`): how far each brow card is moved along the skin,
# up (+) or down, in metres, against t = 0 at the brow's head (by the nose) .. 1 at its tail, as [t, metres]
# keys. "natural" is MPFB's card as fitted, untouched - the default, so a spec that does not ask is unchanged.
# "straight" takes most of the natural rise out and lifts the tail, "arched" lifts the peak over the outer third
# and drops the tail, "soft" is a low, round arch peaking mid-brow. The report's `shape_profile_mm` measures it.
BROW_SHAPES = {
    "natural": None,
    "straight": [[0.0, 0.0], [0.25, -0.0008], [0.55, -0.0018], [0.75, -0.0015], [1.0, 0.0008]],
    "arched": [[0.0, 0.0], [0.3, 0.0008], [0.62, 0.0026], [0.8, 0.0014], [1.0, -0.0014]],
    "soft": [[0.0, 0.0], [0.3, 0.0006], [0.5, 0.0009], [0.75, 0.0], [1.0, -0.0006]],
}
BROW_SHAPE_T = (0.1, 0.3, 0.5, 0.7, 0.9)     # where `shape_profile_mm` reports the brow's height

_DATA = None


def regions():
    global _DATA
    if _DATA is None:
        import humanform as pkg
        with open(os.path.join(pkg.DATA, "face_regions.json"), encoding="utf-8") as fh:
            _DATA = json.load(fh)
    return _DATA


def is_mpfb(ob):
    return len(ob.data.vertices) >= regions()["n_body"]


def ear_vertices(ob):
    """{"L": [indices], "R": [indices]} of the body's ear vertices, or None for a body that is not MPFB's."""
    if not is_mpfb(ob):
        return None
    d = regions()["ears"]
    return {"L": list(d["L"]), "R": list(d["R"])}


def _rebuild(co, fits):
    f = np.asarray(fits, np.float64)
    ia, ib, ic = f[:, 0].astype(int), f[:, 1].astype(int), f[:, 2].astype(int)
    a, b, c = co[ia], co[ib], co[ic]
    n = np.cross(b - a, c - a)
    area2 = np.linalg.norm(n, axis=1)
    n = n / area2[:, None]
    return (f[:, 3:4] * a + f[:, 4:5] * b + f[:, 5:6] * c + (f[:, 6] * np.sqrt(area2 / 2))[:, None] * n,
            (ia, ib, ic), f[:, 3:6])


def _vertex_weights(ob, indices):
    """{vertex: {group name: weight}} for the given body vertices."""
    names = {g.index: g.name for g in ob.vertex_groups}
    out = {}
    for i in set(int(x) for x in indices):
        out[i] = {names[e.group]: e.weight for e in ob.data.vertices[i].groups if e.weight > 1e-4 and e.group in names}
    return out


def _darken(colour, k):
    return tuple(max(0.0, min(1.0, c * k)) for c in colour)


def _material(name, colour, uv_name, part, double_sided=False):
    try:
        from lookdev_blender import hair as ld_hair
    except ImportError:
        ld_hair = None
    if ld_hair is None:
        from . import look
        mat = look.material(name, srgb=colour, roughness=0.5)
        return mat, {"material": mat.name, "source": "flat (lookdev_blender not importable)"},             (1.0 if part in ("brows", "lashes") else TILE_M)
    over = dict(LOOK[part])
    # in Godot, not the hair preset's depth pre-pass: a card this fine and this close to the skin blended its
    # many sub-cutoff strand fringes into a grey haze (eyeshadow round the lashes, a smudge under the brow).
    # Body hair takes scissor at the 0.5 the exporter writes; brows and lashes blend with CARD_ALPHA's ramp,
    # which is what removed the haze (coverage-kept mips, alpha 0 below 0.25).
    godot = dict(ld_hair.preset("hair")["godot"], transparency=GODOT_SCISSOR)
    pixels, card_rep = None, None
    if part in ("brows", "lashes"):
        godot.update(CARD_GODOT)
        godot.pop("backlight_share", None)
        over["alpha"] = dict(CARD_ALPHA)
        W, H = over["texture_px"]
        *pixels, card_rep = card_pixels(part, colour, W, H)
    elif part == "body_hair":
        p = ld_hair.preset("hair", **over)
        lin = _srgb_to_linear(np.asarray(colour[:3], np.float64))
        pixels = _sparse(*ld_hair.strand_texture(lin, p, seed=0))
    elif part in ("beard", "beard_cards"):
        style = over.pop("style")
        # `humanform.cards` asks for a sheet by its numbers rather than by a beard style, so it passes them
        spec = over.pop("_spec", None) or dict(BEARD_STYLES[style])
        # square texels, the fade's vertex alpha multiplied in, and no coverage-kept mips for a full beard (its
        # under-layer keeps every level over the cutoff); stubble and the cards keep their hairs' share at a distance
        godot.update(texture_filter=GODOT_FILTER_ANISOTROPIC, vertex_color_use_as_albedo=True)
        over["alpha"] = None if spec["under"] else {"coverage_mips": 0.5, "edge": 0.5}
        *pixels, beard_rep = beard_pixels(style, colour, BEARD_PX, TILE_M, spec=spec)
        card_rep = beard_rep
    over["godot"] = godot
    mat, rep = ld_hair.material(name, colour, uv_map=uv_name, pixels=pixels, **over)
    if card_rep is not None:
        rep = dict(rep, texture=card_rep)
    if hasattr(mat, "use_transparent_shadow"):
        mat.use_transparent_shadow = True       # a card's shadow is its strands', not the whole card's
    if double_sided:
        mat.use_backface_culling = False
    if part in ("beard", "beard_cards"):
        _fade_nodes(mat)
    tile = 1.0 if part in ("brows", "lashes") else rep["tile_m"]
    return mat, dict(rep, source="lookdev", double_sided=double_sided), tile


def _fade_nodes(mat):
    """Multiply the strand texture's colour and alpha by the `BEARD_FADE` colour attribute (white, its alpha the
    fade), ahead of the alpha's Round: glTF then carries it as COLOR_0, which multiplies base colour and alpha
    in Godot (`vertex_color_use_as_albedo`, set from the lookdev extras) as it does in Blender."""
    nt = mat.node_tree
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE" and n.outputs["Alpha"].is_linked)
    rnd = next(n for n in nt.nodes if n.type == "MATH" and n.operation == "ROUND")
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = BEARD_FADE
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    nt.links.new(tex.outputs["Alpha"], mul.inputs[0])
    nt.links.new(attr.outputs["Alpha"], mul.inputs[1])
    nt.links.new(mul.outputs[0], rnd.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], mix.inputs[6])
    nt.links.new(attr.outputs["Color"], mix.inputs[7])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    attr.location, mul.location, mix.location = (-900, 250), (-400, 150), (-400, 350)


# ------------------------------------------------------------------------------------------ card textures

def _srgb_to_linear(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _strand(cover, tone, rng, x0, v0, v1, w0, w1, lean, bright, mark=None):
    """Draw one hair into `cover` (H, W) as an antialiased tapering line from (x0 px, v0) to (x0 + lean px, v1),
    keeping the brightness of whichever hair is on top in `tone` (and, with `mark` = (array, value), that hair's
    value in the array)."""
    H, W = cover.shape
    r0, r1 = int(max(0, math.floor(v0 * H))), int(min(H, math.ceil(v1 * H)))
    if r1 - r0 < 2:
        return
    v = (np.arange(r0, r1) + 0.5) / H
    t = (v - v0) / max(v1 - v0, 1e-6)
    cx = x0 + lean * t * t                                  # a hair curves as it leaves the skin
    half = 0.5 * (w0 + (w1 - w0) * t)
    lo = int(math.floor(min(x0, x0 + lean) - w0 - 2))
    hi = int(math.ceil(max(x0, x0 + lean) + w0 + 2))
    cols = np.arange(lo, hi)
    inside = (cols >= 0) & (cols < W)
    cols = cols[inside]
    if not len(cols):
        return
    dx = np.abs((cols + 0.5)[None, :] - cx[:, None])
    c = np.clip(half[:, None] + 0.5 - dx, 0.0, 1.0) * np.clip(half[:, None] * 2.0, 0.0, 1.0) ** 0.5
    blk = cover[r0:r1, cols]
    better = c > blk
    cover[r0:r1, cols] = np.maximum(blk, c)
    tone[r0:r1, cols] = np.where(better, (bright * (0.85 + 0.25 * t))[:, None], tone[r0:r1, cols])
    if mark is not None:
        mark[0][r0:r1, cols] = np.where(better, mark[1], mark[0][r0:r1, cols])


def _brow_hairs(W, H, rng):
    """(cover, tone) for both brows: U 0 at the brow's head (nose), 1 at its tail; V 0 lower edge, 1 upper."""
    cover, tone = np.zeros((H, W)), np.ones((H, W))
    n = 850
    # how many hairs along the brow: feathered in at the head, full over the body, thinning into the tail
    us = rng.uniform(0.0, 1.0, n * 3)
    dens = np.interp(us, [0.0, 0.07, 0.2, 0.6, 0.85, 1.0], [0.15, 0.6, 1.0, 0.9, 0.45, 0.12])
    us = us[rng.uniform(0, 1, len(us)) < dens][:n]
    for u in us:
        # roots over the lower two thirds, hairs a third to a half of the card long; at the tail they are
        # confined to the middle, so the brow narrows to a point rather than a cut
        mid = 0.45
        spread = float(np.interp(u, [0.0, 0.6, 1.0], [0.42, 0.38, 0.18]))
        v0 = float(np.clip(rng.normal(mid - 0.12, spread * 0.5), 0.0, 0.8))
        length = rng.uniform(0.28, 0.55)
        v1 = min(0.99, v0 + length)
        _strand(cover, tone, rng, u * W, v0, v1, rng.uniform(1.9, 2.8), rng.uniform(0.5, 0.9),
                rng.normal(0.0, 3.0) + 4.0, float(np.clip(rng.normal(1.0, 0.13), 0.7, 1.35)))
    return cover, tone


def _lash_hairs(W, H, rng):
    """(cover, tone): upper lid in U LASH_U["upper"], lower lid in LASH_U["lower"], both with the outer corner at
    their outer ends (0.02 and 0.98); V 0 at the lid, 1 at the card's far edge. Per lid, `LASHES`: long lashes,
    then short ones packed at the root, which make the dark lash line a lid reads by from the front."""
    cover, tone = np.zeros((H, W)), np.ones((H, W))
    for lid in ("upper", "lower"):
        spec = LASHES[lid]
        a, b = LASH_U[lid]
        for n, lengths, width, gather_k in ((spec["n"], spec["lengths"], spec["width"], spec["gather"]),
                                            (spec["short"], spec["short_lengths"], spec["width"], 0.0)):
            if not n:
                continue
            # s: 0 at the outer corner, 1 at the inner; lashes are longest and densest over the outer middle
            ss = rng.uniform(0.0, 1.0, n * 3)
            dens = np.interp(ss, [0.0, 0.08, 0.3, 0.7, 0.9, 1.0], [0.3, 0.9, 1.0, 0.8, 0.35, 0.1])
            ss = ss[rng.uniform(0, 1, len(ss)) < dens][:n]
            # lashes gather in small clumps whose tips meet: each lash leans toward its clump's centre
            clumps = np.sort(rng.uniform(0.0, 1.0, max(3, n // 4)))
            for s_ in ss:
                u = a + (b - a) * (s_ if lid == "upper" else 1.0 - s_)
                reach = float(np.interp(s_, [0.0, 0.35, 0.75, 1.0], [0.75, 1.0, 0.85, 0.5]))
                v1 = 0.03 + reach * rng.uniform(*lengths)
                # outer lashes sweep out toward the corner, inner ones toward the nose
                out = (0.5 - s_) * 2.0 * (1 if lid == "upper" else -1)
                c = clumps[np.argmin(np.abs(clumps - s_))]
                gather = (c - s_) * (b - a) * W * (1 if lid == "upper" else -1) * gather_k
                _strand(cover, tone, rng, u * W, 0.02, min(0.99, v1), rng.uniform(*width), 0.35,
                        -out * rng.uniform(8.0, 18.0) * v1 + gather + rng.normal(0.0, 2.5) * v1,
                        float(np.clip(rng.normal(1.0, 0.12), 0.7, 1.35)))
    return cover, tone


def card_pixels(part, colour, W, H, seed=5):
    """(colour, normal, report) for a brow or lash card, for lookdev's `hair.material(pixels=...)`: separate
    hairs two or three texels wide at the root tapering to under one, skin (alpha 0) between them, colour the
    part's colour with a little per-hair variation and lighter toward the tip. Arrays are (H, W, 4), rows
    bottom-up (row 0 is V = 0), colour sRGB with straight alpha, normal a tangent-space map."""
    rng = np.random.RandomState(seed)
    cover, tone = (_brow_hairs if part == "brows" else _lash_hairs)(W, H, rng)
    lin = _srgb_to_linear(np.asarray(colour[:3], np.float64))
    rgb = np.clip(lin[None, None, :] * tone[:, :, None], 0.0, 1.0)
    px = np.empty((H, W, 4), np.float32)
    px[:, :, :3] = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
    px[:, :, 3] = np.clip(cover * 1.15, 0.0, 1.0)
    # each hair a rounded ridge across U
    slope = (np.roll(cover, -1, axis=1) - np.roll(cover, 1, axis=1)) * 0.5
    nrm = np.stack([-slope, np.zeros_like(slope), np.ones_like(slope)], axis=2)
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    npx = np.ones((H, W, 4), np.float32)
    npx[:, :, :3] = nrm * 0.5 + 0.5
    return px, npx, {"texture_px": [W, H], "coverage": round(float((px[:, :, 3] >= 0.5).mean()), 4), "seed": seed}


def _periodic(u, v, rng, terms=4, max_k=3):
    """A smooth field on the unit torus (so it tiles with the texture), about -1..1: a few low sine waves."""
    out = np.zeros(np.broadcast(u, v).shape)
    for _ in range(terms):
        k, l = rng.randint(-max_k, max_k + 1, 2)
        if k == 0 and l == 0:
            k = 1
        out = out + np.sin(2 * math.pi * (k * u + l * v) + rng.uniform(0, 2 * math.pi))
    return out / math.sqrt(terms / 2.0)


def beard_pixels(style, colour, px=BEARD_PX, tile_m=TILE_M, seed=11, spec=None):
    """(colour, normal, report) for a beard shell in `style` (BEARD_STYLES), for lookdev's
    `hair.material(pixels=...)`: `px` x `px` texels over `tile_m` x `tile_m` on the skin, tiling both ways, V down
    the face. Separate hairs `strand_m` long (about 0.12 mm wide at the root, tapering), rooted anywhere in the
    tile - never in rows, so no band of roots or tips repeats down the chin - leaning with a slowly turning flow
    and gathered into loose clumps, until they cover `cover` of it. A full beard (`under`) fills between them
    with a darker under-layer at alpha BEARD_UNDER_ALPHA, over the 0.5 cutoff, so no mip level has a hole;
    stubble has none (skin between its hairs). Arrays are (H, W, 4), rows bottom-up (row 0 is V = 0), colour
    sRGB with straight alpha, normal a tangent-space map (each hair a ridge across U). `spec` overrides the
    style's own (the cards' sheet passes `under` off and their own `cover` and `strand_m`)."""
    spec = BEARD_STYLES[style] if spec is None else spec
    rng = np.random.RandomState(seed)
    N = int(px)
    texel = tile_m / N
    length = spec["strand_m"] / texel                   # a hair's length, texels
    w0, w1 = 0.12e-3 / texel, 0.05e-3 / texel           # root and tip width, texels
    # drawn once into a 3x3 canvas and folded back, so a hair crossing the tile's edge carries on over the seam
    big = np.zeros((3 * N, 3 * N))
    tone = np.ones((3 * N, 3 * N))
    rank = np.zeros((3 * N, 3 * N))
    lean_f = np.random.RandomState(seed + 1)
    flow_ph = [lean_f.uniform(0, 2 * math.pi, 2) for _ in range(3)]
    clump = np.random.RandomState(seed + 2)
    clump_ph = [(clump.randint(1, 4), clump.randint(-3, 4), clump.uniform(0, 2 * math.pi)) for _ in range(4)]

    def flow(u, v):                                     # radians off straight down, a slowly turning field
        return 0.28 * sum(math.sin(2 * math.pi * ((k + 1) * u + (k % 2) * v) + ph[0]) / (k + 1)
                          for k, ph in enumerate(flow_ph))

    def clumped(u, v):                                  # 0..1: where hairs gather
        return 0.5 + 0.5 * sum(math.sin(2 * math.pi * (k * u + l * v) + ph) for k, l, ph in clump_ph) / 4.0

    mean_w = 0.5 * (w0 + w1) * 0.8
    n_target = int(-math.log(max(1e-3, 1.0 - spec["cover"])) * N * N / max(length * mean_w, 1.0))
    drawn = tries = 0
    while drawn < n_target and tries < n_target * 4:
        tries += 1
        u, v = rng.uniform(), rng.uniform()
        if rng.uniform() > 0.45 + 0.55 * clumped(u, v):
            continue
        L = length * rng.uniform(0.6, 1.15)
        ang = flow(u, v) + rng.normal(0.0, 0.12)
        lean = math.tan(ang) * L
        # the canvas's rows run up (row 0 is V = 0) and V runs down the face: a hair's root is at its smaller V
        x0 = (N + u * N)
        v0 = (N + v * N) / (3 * N)
        v1 = v0 + L / (3 * N)
        bright = float(np.clip(rng.normal(1.0, 0.14), 0.7, 1.4)) * (1.3 if rng.uniform() < 0.06 else 1.0)
        _strand(big, tone, rng, x0, v0, v1, rng.uniform(0.85, 1.15) * w0, w1, lean, bright,
                mark=(rank, rng.uniform(0.02, 1.0)))
        drawn += 1
    cover = np.zeros((N, N))
    ton = np.ones((N, N))
    rk = np.zeros((N, N))
    for by in range(3):
        for bx in range(3):
            blk = (slice(by * N, (by + 1) * N), slice(bx * N, (bx + 1) * N))
            better = big[blk] > cover
            cover = np.where(better, big[blk], cover)
            ton = np.where(better, tone[blk], ton)
            rk = np.where(better, rank[blk], rk)
    uu, vv = np.meshgrid((np.arange(N) + 0.5) / N, (np.arange(N) + 0.5) / N)
    lock = 1.0 + 0.12 * _periodic(uu, vv, np.random.RandomState(seed + 3))
    lin = _srgb_to_linear(np.asarray(colour[:3], np.float64))
    shade = (BEARD_GAP + (ton - BEARD_GAP) * cover) if spec["under"] else ton
    rgb = np.clip(lin[None, None, :] * (shade * lock)[:, :, None], 0.0, 1.0)
    out = np.empty((N, N, 4), np.float32)
    out[:, :, :3] = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
    # alpha: a hair's own rank (uniform per hair) over the cutoff, so the fade's vertex alpha (1 inside, 0.5 at the
    # edge, multiplied in) drops hairs one by one toward the edge - the under-layer first (at a fade under
    # 0.5 / BEARD_UNDER_ALPHA), then the hairs in rank order - rather than the whole shell at one line
    hair = cover >= 0.5
    # The under-layer's alpha is NOT one number. Scissored, a constant 0.55 times the fade crosses 0.5 within
    # a fade span of 0.02 - about a millimetre of the field - so the whole mat switched from solid to gone
    # inside one body face and its edge came out a staircase of quads along the cheek. Varied over a few
    # millimetres, its texels cross at different fades and the mat thins out over two or three faces.
    floor = 0.0
    if spec["under"]:
        blot = 0.5 + 0.5 * np.clip(_periodic(uu, vv, np.random.RandomState(seed + 4), terms=6, max_k=14), -1, 1)
        floor = BEARD_UNDER_ALPHA + (BEARD_UNDER_MAX - BEARD_UNDER_ALPHA) * blot
    out[:, :, 3] = np.where(hair, np.maximum(floor, 0.5 + 0.5 * rk),
                            np.maximum(floor, np.clip(cover, 0.0, 0.499)))
    slope = (np.roll(cover, -1, axis=1) - np.roll(cover, 1, axis=1)) * 0.5
    nrm = np.stack([-slope, np.zeros_like(slope), np.ones_like(slope)], axis=2)
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    npx = np.ones((N, N, 4), np.float32)
    npx[:, :, :3] = nrm * 0.5 + 0.5
    return out, npx, {"texture_px": [N, N], "tile_m": tile_m, "texel_mm": round(texel * 1000, 4),
                      "hairs": drawn, "hair_cover": round(float((cover >= 0.5).mean()), 3),
                      "under": spec["under"], "min_alpha": round(float(out[:, :, 3].min()), 3), "seed": seed}


def _components(n, faces):
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for q in faces:
        for i in q[1:]:
            parent[find(i)] = find(q[0])
    return [find(i) for i in range(n)]


def _card_uv(part, pts, faces, uv):
    """Per-vertex UVs for one side's card in the card texture's layout (see LOOK): U once along the brow
    (0 head .. 1 tail, keeping the stored lean of the strands), or along each lid's card from its outer
    corner (lashes: upper lid 0.02..0.48, lower 0.52..0.98). V as stored. Returns (uvs, {lid: cards})."""
    uv = np.asarray(uv, np.float64)
    out = uv.copy()
    if part == "brows":
        lo, hi = float(uv[:, 0].min()), float(uv[:, 0].max())
        out[:, 0] = 0.01 + 0.98 * (uv[:, 0] - lo) / max(hi - lo, 1e-9)
        return out.tolist(), {}
    # lashes: each lid's card is its own piece; which lid by where its roots are (V near 0) against the other
    # piece's, and the outer corner is the end furthest from the face's middle
    comp = np.array(_components(len(pts), faces))
    keys = sorted(set(comp.tolist()))
    root_z = {k: float(pts[(comp == k) & (uv[:, 1] < 0.2), 2].mean()) if ((comp == k) & (uv[:, 1] < 0.2)).any()
              else float(pts[comp == k, 2].mean()) for k in keys}
    mid_z = float(np.median(list(root_z.values())))
    lat = np.abs(pts[:, 0])
    counts = {}
    for k in keys:
        m = comp == k
        lid = "upper" if root_z[k] >= mid_z and len(keys) > 1 else ("lower" if len(keys) > 1 else "upper")
        counts[lid] = counts.get(lid, 0) + 1
        a, b = LASH_U[lid]
        lo, hi = float(lat[m].min()), float(lat[m].max())
        s_ = (hi - lat[m]) / max(hi - lo, 1e-9)                # 0 at the outer corner, 1 at the inner
        out[m, 0] = a + (b - a) * (s_ if lid == "upper" else 1.0 - s_)
    return out.tolist(), counts


def _brow_heights(p, t):
    """Mean height (z, metres) of a brow card's vertices near each `BROW_SHAPE_T` along it (t 0 head .. 1 tail)."""
    out = []
    for tt in BROW_SHAPE_T:
        near = np.abs(t - tt) < 0.08
        out.append(float(p[near, 2].mean()) if near.any() else float("nan"))
    return np.array(out)


def _shape_brow(p, uv, shape, bvh, scale=1.0):
    """Move one brow card along the skin to `shape` (a `BROW_SHAPES` name): each vertex goes up the skin (world +Z
    turned into the skin's tangent plane) by the shape's offset at its t, then back onto the skin at the height
    over it it had. Returns (points, report); the report's `shape_profile_mm` is the card's height at
    `BROW_SHAPE_T` relative to its first point, and `moved_mm` how far each moved from the natural brow, so a
    shape is measured, not assumed."""
    p = np.array(p, np.float64)
    u = np.asarray(uv, np.float64)[:, 0]
    t = np.clip((u - 0.01) / 0.98, 0.0, 1.0)
    before = _brow_heights(p, t)
    keys = BROW_SHAPES[shape]
    if keys is None:
        return p, {"shape": shape, "shape_profile_mm": [round(float(x), 2) for x in (before - before[0]) * 1000]}
    k = np.array(keys, np.float64)
    delta = np.interp(t, k[:, 0], k[:, 1]) * scale      # a larger head's brow moves as far in proportion
    q = p.copy()
    up = np.array([0.0, 0.0, 1.0])
    for i in range(len(p)):
        loc, nrm, _f, _d = bvh.find_nearest(Vector(p[i]))
        if loc is None:
            continue
        n = np.array(nrm)
        height = float(np.dot(p[i] - np.array(loc), n))
        tang = up - n * np.dot(up, n)
        tang /= max(np.linalg.norm(tang), 1e-9)
        moved = p[i] + tang * delta[i]
        loc2, nrm2, _f, _d = bvh.find_nearest(Vector(moved))
        q[i] = np.array(loc2) + np.array(nrm2) * height if loc2 is not None else moved
    after = _brow_heights(q, t)
    return q, {"shape": shape,
               "shape_profile_mm": [round(float(x), 2) for x in (after - after[0]) * 1000],
               "natural_profile_mm": [round(float(x), 2) for x in (before - before[0]) * 1000],
               "moved_mm": [round(float((a - b) * 1000), 2) for a, b in zip(after, before)]}


def _body_bvh(ob, co):
    """The body's surface in world space: the faces of its first n_body vertices (MPFB's body, no helpers)."""
    from mathutils.bvhtree import BVHTree
    n = regions()["n_body"]
    polys = [tuple(p.vertices) for p in ob.data.polygons if max(p.vertices) < n]
    return BVHTree.FromPolygons([Vector(c) for c in co[:n]], polys)


def _card_object(name, body, rig, pts_world, faces, uvs, weights, uv_name, tile):
    """A mesh from world points, quads and per-vertex UVs (U in metres, divided by `tile`)."""
    from .hair import _object
    bm = bmesh.new()
    verts = [bm.verts.new(Vector(p)) for p in pts_world]
    bm.verts.index_update()                     # a new BMVert's index is not its place until this
    uv = bm.loops.layers.uv.new(uv_name)
    for q in faces:
        f = bm.faces.new([verts[i] for i in q])
        f.smooth = True
        for loop in f.loops:
            u, v = uvs[loop.vert.index]
            loop[uv].uv = (u / tile, v)
    ob = _object(name, bm, body, rig, weights)
    bm.free()
    return ob


def _interp_weights(ob, tris, bary, fallback):
    """Per-card-vertex weights interpolated from the triangle each vertex rides: {group: array}."""
    ia, ib, ic = tris
    table = _vertex_weights(ob, np.concatenate([ia, ib, ic]))
    groups = sorted({g for w in table.values() for g in w})
    out = {g: np.zeros(len(ia)) for g in groups}
    for k in range(len(ia)):
        for idx, w in ((ia[k], bary[k, 0]), (ib[k], bary[k, 1]), (ic[k], bary[k, 2])):
            for g, x in table[int(idx)].items():
                out[g][k] += w * x
    if not groups:
        return {fallback: np.ones(len(ia))}
    total = sum(out.values())
    total = np.where(total > 1e-6, total, 1.0)
    return {g: np.clip(w / total, 0.0, 1.0) for g, w in out.items() if w.max() > 1e-3}


HEAD_SHARE_MIN = 0.6      # brow and lash cards: the least head weight their triangles may carry


def _side_cards(ob, part, d):
    """[(name, card)] a part is laid from: the human pair, or on a head whose eyes humanform.eye_layout arranged (its
    PROP on the body), the human cards of the eyes it kept and one set per eye it placed - lashes on its lids, and a
    brow arch over it (one continuous arch across the midline over a median eye). A human body has no PROP and takes
    exactly the human pair."""
    lay = ob.get("hf_eye_layout") if part in ("lashes", "brows") else None
    if not lay:
        return [("L", d["L"]), ("R", d["R"])]
    lay = json.loads(lay)
    if part == "brows" and "brows" not in lay:
        return [("L", d["L"]), ("R", d["R"])]              # a layout from before brows followed the eyes
    out = [(side, d[side]) for side in ("L", "R") if side not in lay.get(f"hide_{part}", [])]
    return out + [(f"e{i}", c) for i, c in enumerate(lay.get(part, []))]


def _cards(ob, co, part, base, rig, colour, uv_name, head, brow_shape="natural", scale=1.0):
    d = regions()[part]
    shaped = {}
    bvh = _body_bvh(ob, co) if part == "brows" and BROW_SHAPES[brow_shape] is not None else None
    mat, mat_rep, tile = _material(f"{base}_{part}", colour, uv_name, part, double_sided=(part == "lashes"))
    pts, faces, uvs, tris, bary = [], [], [], ([], [], []), []
    lids = {}
    for side, card in _side_cards(ob, part, d):
        p, (ia, ib, ic), w = _rebuild(co, card["fit"])
        off = len(pts)
        if tile == 1.0:
            uv, side_lids = _card_uv(part, p, card["faces"], card["uv"])
            for k, n in side_lids.items():
                lids[k] = lids.get(k, 0) + n
        else:
            uv = card["uv"]
        if part == "brows" and tile == 1.0:
            p, shaped[side] = _shape_brow(p, uv, brow_shape, bvh, scale)
        pts.extend(p.tolist())
        faces.extend([[off + i for i in q] for q in card["faces"]])
        uvs.extend(uv)
        tris[0].extend(ia.tolist())
        tris[1].extend(ib.tolist())
        tris[2].extend(ic.tolist())
        bary.extend(w.tolist())
    tris = tuple(np.array(t) for t in tris)
    weights = _interp_weights(ob, tris, np.array(bary), head)
    on_head = float(np.mean(weights.get(head, np.zeros(1))))
    if part in ("brows", "lashes") and on_head < HEAD_SHARE_MIN:
        # the cards ride hm08 triangles by index: off the head means the body's vertex order moved (a graft's
        # loose vertices dropped by the bake put a mermaid's brows on her chest) - never ship that
        raise ValueError(f"{part}: the cards' triangles carry {on_head:.0%} head weight (under "
                         f"{HEAD_SHARE_MIN:.0%}): {ob.name}'s hm08 vertex order is not the base mesh's")
    card = _card_object(f"{base}_{part}", ob, rig, pts, faces, uvs, weights, uv_name, tile)
    card.data.materials.append(mat)
    card["humanform_hair"] = {"part": part}
    # the lash roots and the brow must lie on the skin: the distance of each card's root row from the body
    return card, {"faces": len(faces), "verts": len(pts), "weights": sorted(weights),
                  "material": {k: mat_rep.get(k) for k in ("material", "source", "gltf", "double_sided", "texture")},
                  "colour": [round(c, 4) for c in colour], **({"lid_cards": lids} if lids else {}),
                  **({"shape": shaped} if shaped else {})}


# ------------------------------------------------------------------------------------------ body hair

def _sparse(px, npx, seed=3, keep=None, per_tile=None):
    """Thin the body hair's strand pixels (lookdev's, as `strand_texture` returns them) before they become the
    material's images: keep BODY_HAIR_KEEP (or `keep`) of its strand bands, each rolled along V at random so the
    kept strands do not start on one row. Returns (colour, normal)."""
    keep = BODY_HAIR_KEEP if keep is None else keep
    px, npx = np.array(px, np.float64), np.array(npx, np.float64)
    H, W = px.shape[:2]
    rng = np.random.RandomState(seed)
    band = max(2, W // (per_tile or LOOK["body_hair"]["strands_per_tile"]))
    for x0 in range(0, W, band):
        cols = slice(x0, min(W, x0 + band))
        if rng.uniform() > keep:
            px[:, cols, 3] = 0.0
            continue
        shift = int(rng.randint(0, H))
        px[:, cols] = np.roll(px[:, cols], shift, axis=0)
        npx[:, cols] = np.roll(npx[:, cols], shift, axis=0)
    return px, npx


def _weights_array(ob, name):
    g = ob.vertex_groups.get(name)
    w = np.zeros(len(ob.data.vertices))
    if g is None:
        return w
    for v in ob.data.vertices:
        for e in v.groups:
            if e.group == g.index:
                w[v.index] = e.weight
    return w


def body_hair_regions(ob, co, normals, sex):
    """{region: boolean vertex mask} over the body's first n_body vertices."""
    n = regions()["n_body"]
    co, normals = co[:n], normals[:n]
    W = {name: _weights_array(ob, name)[:n] for name in
         ("forearm.L", "forearm.R", "shin.L", "shin.R", "thigh.L", "thigh.R", "spine", "spine.001", "spine.002",
          "spine.003")}
    front = -normals[:, 1]
    out = {"forearms": (W["forearm.L"] + W["forearm.R"]) > 0.6,
           "shins": (W["shin.L"] + W["shin.R"]) > 0.6}
    # the crotch: the lowest point of the body's middle above the knees
    mid = co[(np.abs(co[:, 0]) < 0.01) & (co[:, 2] > 0.5)]
    crotch = float(mid[:, 2].min()) if len(mid) else 0.8
    out["pubic"] = ((co[:, 2] > crotch + 0.02) & (co[:, 2] < crotch + 0.1) & (np.abs(co[:, 0]) < 0.055 + 0.3 *
                    np.maximum(co[:, 2] - crotch - 0.02, 0.0)) & (front > 0.25))
    if sex == "male":
        out["thighs"] = ((W["thigh.L"] + W["thigh.R"]) > 0.6) & (co[:, 2] < crotch - 0.03)
        chest = W["spine.002"] + W["spine.003"]
        out["chest"] = (chest > 0.5) & (front > 0.55) & (np.abs(co[:, 0]) < 0.11)
        belly = W["spine.001"] + W["spine"]
        out["belly"] = (belly > 0.5) & (front > 0.5) & (np.abs(co[:, 0]) < 0.03 + 0.25 * np.maximum(
            crotch + 0.16 - co[:, 2], 0.0)) & (co[:, 2] > crotch + 0.08)
    return {k: v for k, v in out.items() if v.any()}


def _body_hair(ob, co, base, rig, colour, uv_name, sex):
    me = ob.data
    nrm = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("normal", nrm)
    m3 = np.array(ob.matrix_world.to_3x3(), np.float64)
    nrm = nrm.reshape(-1, 3).astype(np.float64) @ m3.T
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-9)[:, None]
    masks = body_hair_regions(ob, co, nrm, sex)
    mat, mat_rep, tile = _material(f"{base}_body_hair", colour, uv_name, "body_hair")
    region_of = np.full(len(co), -1)
    names = sorted(masks)
    for k, name in enumerate(names):
        region_of[np.nonzero(masks[name])[0]] = k
    bones = rig.data.bones if rig is not None else None
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    src_layer = bm.verts.layers.int.new("hf_src")
    for v in bm.verts:
        v[src_layer] = v.index
    keep = [f for f in bm.faces if all(region_of[v.index] >= 0 for v in f.verts)
            and len({region_of[v.index] for v in f.verts}) == 1]
    counts = {name: 0 for name in names}
    for f in keep:
        counts[names[region_of[f.verts[0].index]]] += 1
    region_face = {f: names[region_of[f.verts[0].index]] for f in keep}
    keep_set = set(keep)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f not in keep_set], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    for layer in list(bm.loops.layers.uv.values()):
        bm.loops.layers.uv.remove(layer)
    for layer in list(bm.loops.layers.color.values()):
        bm.loops.layers.color.remove(layer)
    dl = bm.verts.layers.deform.active
    src = [v[src_layer] for v in bm.verts]      # the body vertex each shell vertex was cut from
    mw = ob.matrix_world
    for v, i in zip(bm.verts, src):
        v.co = mw @ v.co + Vector(nrm[i]) * BODY_HAIR_LIFT_M
    bm.verts.layers.int.remove(src_layer)
    uv = bm.loops.layers.uv.new(uv_name)
    # V along the limb's bone (down the torso) every BODY_HAIR_STRAND_M, U around it in tiles
    axis_of = {"forearms": ("forearm.L", "forearm.R"), "shins": ("shin.L", "shin.R"), "thighs": ("thigh.L", "thigh.R")}
    for f, name in region_face.items():
        for loop in f.loops:
            p = loop.vert.co
            bone_names = axis_of.get(name)
            if bone_names and bones is not None and all(b in bones for b in bone_names):
                b = bones[bone_names[0] if p.x > 0 else bone_names[1]]
                h = rig.matrix_world @ b.head_local
                t = rig.matrix_world @ b.tail_local
                ax = (t - h).normalized()
                rel = p - h
                along = rel.dot(ax)
                radial = rel - ax * along
                ref = Vector((0.0, -1.0, 0.0))
                r0 = (ref - ax * ref.dot(ax)).normalized()
                ang = math.atan2(radial.dot(ax.cross(r0)), radial.dot(r0))
                loop[uv].uv = (ang * 0.04 / tile, along / BODY_HAIR_STRAND_M)
            else:
                loop[uv].uv = (p.x / tile, -p.z / BODY_HAIR_STRAND_M)
    for f in bm.faces:
        f.smooth = True
    weights = {}
    if dl is not None:
        names_g = {g.index: g.name for g in ob.vertex_groups}
        per = {}
        for k, v in enumerate(bm.verts):
            for gi, w in v[dl].items():
                if gi in names_g and w > 1e-4:
                    per.setdefault(names_g[gi], np.zeros(len(bm.verts)))[k] = w
            v[dl].clear()
        weights = per
    bm.verts.index_update()
    from .hair import _object
    hob = _object(f"{base}_body_hair", bm, ob, rig, weights)
    bm.free()
    hob.data.materials.append(mat)
    hob["humanform_hair"] = {"part": "body_hair"}
    return hob, {"faces": len(hob.data.polygons), "verts": len(hob.data.vertices), "regions": counts,
                 "sex": sex, "material": {k: mat_rep.get(k) for k in ("material", "source", "gltf")},
                 "source_vertices": len(src)}


def beard_field(ob, co, normals, head_bone, neck_bone=None, scale=1.0, also=()):
    """Where a beard grows, as signed distances on the face (metres, + inside) rather than vertex masks: a
    region's edge is then a smooth curve that the fade interpolates across faces, not a staircase of whole faces.
    Returns ({region: margin per body vertex}, face margin per body vertex, marks). Regions: `moustache` (between
    the nose's base and the upper lip, out to just past the mouth's corners), `corners` (round the mouth's corners,
    joining the moustache to the chin, as a full beard and a goatee grow), `chin` (under the lower lip - the soul
    patch - over the chin and a little under it) and `jaw` (along the jaw from the chin back to in front of the
    ears, below a line from the nose's base at the mouth's corner down to the mouth's height at the side of the
    face). The face margin keeps every region off the lips' red and the mouth's slit (BEARD_LIP_CLEAR_M) and off
    the neck (the weight of the head bone, the neck's, and `also`'s - every bone hung under the head, because
    a jaw bone takes the mandible's skin off the head and without it the chin is not head skin at all: the chin
    region came out empty and `chin_z` landed a millimetre under the mouth).
    A condition on a normal (facing forward, down) counts BEARD_FACING_M a
    unit. World space: z up, the face towards -y. Every distance was tuned on a human face; `scale`
    (hair.head_scale) scales them."""
    k = float(scale)
    from mathutils.kdtree import KDTree
    from . import measure as _measure
    feats = _measure.face_features()
    n = regions()["n_body"]
    co, normals = co[:n], normals[:n]
    W = _weights_array(ob, head_bone)[:n]
    for extra in ([neck_bone] if neck_bone else []) + list(also or ()):
        W = W + _weights_array(ob, extra)[:n]
    mouth, nose, lips = co[feats["mouth"]], co[feats["nose"]], co[feats["lips"]]
    z_m, y_m = float(mouth[:, 2].mean()), float(mouth[:, 1].mean())
    x_c = float(np.abs(mouth[:, 0]).max())
    z_n = float(nose[:, 2].min())
    front = -normals[:, 1]
    down = -normals[:, 2]
    z = co[:, 2]
    ax = np.abs(co[:, 0])
    behind = co[:, 1] - y_m                     # depth behind the mouth
    mid = (ax < 0.006 * k) & (W > 0.5) & (behind < 0.03 * k)
    chin_z = float(co[mid, 2].min()) if mid.any() else z_m - 0.05 * k
    # the lips' red: face_features' lip set without the part of its outer ring more than BEARD_LIP_RIM_M from
    # the mouth's slit, which is the skin under the lower lip (it reached 14 mm under the mouth's middle, and the
    # beard left a bald notch there); the ring nearer the slit is the lip's own edge and stays
    lip_idx = np.asarray(feats["lips"], np.int64)
    in_set = np.zeros(n, bool)
    in_set[lip_idx] = True
    ev = np.empty(len(ob.data.edges) * 2, np.int64)
    ob.data.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    ev = ev[(ev < n).all(axis=1)]
    rim = np.zeros(n, bool)
    cross = in_set[ev[:, 0]] != in_set[ev[:, 1]]
    rim[ev[cross].ravel()] = True
    mkd = KDTree(len(mouth))
    for i, p in enumerate(mouth):
        mkd.insert(p, i)
    mkd.balance()
    far = np.array([mkd.find(co[i])[2] > BEARD_LIP_RIM_M * k for i in lip_idx], bool)
    inner = lip_idx[~(rim[lip_idx] & far)]
    red = np.vstack([co[inner] if len(inner) else lips, mouth])
    kd = KDTree(len(red))
    for i, p in enumerate(red):
        kd.insert(p, i)
    kd.balance()
    near = np.full(len(co), 1.0)
    for i in np.nonzero((np.abs(z - z_m) < 0.04 * k) & (ax < x_c + 0.02 * k))[0]:
        near[i] = kd.find(co[i])[2]
    L = BEARD_FACING_M * k

    def AND(*a):
        return np.minimum.reduce(a)

    def OR(*a):
        return np.maximum.reduce(a)

    # off the lips' red by BEARD_LIP_CLEAR_M, counted double so the hair is dense within a few mm of the lip
    face = AND((W - 0.5) * L, (near - BEARD_LIP_CLEAR_M * k) * 2.0)
    out = {
        "moustache": AND(z - (z_m + 0.003 * k), (z_n - 0.0015 * k) - z, (x_c + 0.006 * k) - ax, (front - 0.3) * L),
        "corners": AND((x_c + 0.01 * k) - ax, z - (z_m - 0.016 * k), (z_m + 0.008 * k) - z, (front - 0.1) * L),
        "chin": AND((z_m - 0.001 * k) - z, (x_c + 0.004 * k) - ax, 0.05 * k - behind,
                    OR(AND(z - chin_z, OR((front + 0.2) * L, (down - 0.3) * L)),
                       AND(chin_z - z, z - (chin_z - 0.012 * k), (down - 0.45) * L))),
    }
    # the jaw: below the cheek line (the nose's base at the corner, falling to the mouth's height by 7 cm out).
    # Under the chin only the jaw's underside, which faces down: the neck's front faces forward, and taking
    # forward-facing skin there ran the first beard down the throat to the collar.
    t = np.clip((ax - (x_c + 0.006 * k)) / max(0.07 * k - (x_c + 0.006 * k), 1e-6), 0.0, 1.0)
    cheek_line = z_n - 0.0015 * k + t * ((z_m - 0.005 * k) - (z_n - 0.0015 * k))
    out["jaw"] = AND(cheek_line - z, 0.085 * k - ax, 0.085 * k - behind,
                     OR(AND(z - chin_z, OR((front + 0.1) * L, (down - 0.3) * L)),
                        AND(chin_z - z, z - (chin_z - 0.025 * k), (down - 0.45) * L)))
    marks = {"mouth_z": round(z_m, 4), "mouth_y": round(y_m, 4), "nose_base_z": round(z_n, 4),
             "chin_z": round(chin_z, 4), "mouth_half_width": round(x_c, 4)}
    return out, face, marks


def beard_regions(ob, co, normals, head_bone, neck_bone=None, scale=1.0, also=()):
    """({region: boolean vertex mask} over the body's first n_body vertices, marks): `beard_field`'s regions,
    where their signed distance (and the face's) is positive."""
    out, face, marks = beard_field(ob, co, normals, head_bone, neck_bone, scale, also)
    masks = {r: (m > 0) & (face > 0) for r, m in out.items()}
    return {r: m for r, m in masks.items() if m.any()}, marks


def beard_spec(style, length_m=None, volume=None, scale=1.0, braids=None):
    """BEARD_STYLES[style] with a `length_m` / `volume` override, every length times `scale`, and what follows
    from them: `shells` (layers of the root mat - one whenever cards grow over it), `stand_m` (how far the
    outer layer stands off the inner at the chin), `hang_m` (a hanging part's length below the chin; 0 for a
    beard shorter than BEARD_HANG_MIN_M) and, for a carded style, its `cards` block with the lengths scaled,
    a card count per square metre raised with the volume, and `braids` (0: loose locks)."""
    spec = dict(BEARD_STYLES[style])
    if length_m is not None:
        spec["length_m"] = float(length_m)
    if volume is not None:
        spec["volume"] = float(volume)
    k = float(scale)
    for key in ("lift_m", "strand_m", "feather_m", "length_m"):
        spec[key] = spec[key] * k
    cards = spec.get("cards")
    if cards is not None:
        cards = dict(cards)
        for key in [x for x in cards if x.endswith("_m")]:
            cards[key] = cards[key] * k
        # more cards on a fuller beard, and fewer per square metre on a bigger head (a card is wider there too)
        cards["density"] = cards["density"] * (0.4 + 0.6 * spec["volume"] / max(BEARD_STYLES[style]["volume"], 1e-6)) \
            / max(k * k, 1e-6)
        cards["braids"] = int(braids or 0)
        spec["cards"] = cards
    # with cards the shell is only the root mat under them: one layer. Layers were the old volume, and layers
    # are what read as a decal.
    spec["shells"] = 1 if cards is not None else 1 + int(round(spec["volume"] * 5))
    spec["stand_m"] = spec["volume"] * min(spec["length_m"], BEARD_STAND_MAX_M * k)
    spec["hang_m"] = spec["length_m"] if spec["length_m"] > BEARD_HANG_MIN_M * k else 0.0
    return spec


def _smooth_np(t):
    return t * t * (3 - 2 * t)


def _named_weights(ob, indices):
    """[{group name: weight}] for body vertices `indices`."""
    names = {g.index: g.name for g in ob.vertex_groups}
    return [{names[e.group]: e.weight for e in ob.data.vertices[i].groups if e.group in names and e.weight > 1e-4}
            for i in indices]


def _smooth1(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def _beard(ob, co, base, rig, colour, uv_name, style, head_bone, scale=1.0, length_m=None, volume=None,
           braids=None):
    """A beard in `style` (BEARD_STYLES; `length_m`, `volume` and `braids` override its own).

    Two pieces:

    - the **root mat**, one shell of the body's own faces round `beard_field`'s regions, `lift_m` off the skin,
      with the under-layer texture that hides the skin the way a scalp's cap does, its UVs arc lengths on a
      sphere of one radius round a centre behind the mouth. For `stubble` that is the whole beard: at 2.5 mm a
      hair is shorter than a card could show.
    - the **strand cards**, grown by `humanform.cards` out of the field - the same growth a mane, a ruff or a
      tail brush uses, given the beard's own numbers: the field as a weight, a length ramp from the moustache
      down to the chin, a cap over the mouth, and the chin as the line past which a card is cut and its lower
      part hangs in a strand mesh of its own.

    Returns ({"beard": ob, "beard_cards": ob?, "beard_strand": ob?}, report)."""
    k = float(scale)
    spec = beard_spec(style, length_m, volume, k, braids=braids)
    me = ob.data
    nrm = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("normal", nrm)
    m3 = np.array(ob.matrix_world.to_3x3(), np.float64)
    nrm = nrm.reshape(-1, 3).astype(np.float64) @ m3.T
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-9)[:, None]
    neck, under_head = None, []
    if rig is not None and head_bone in rig.data.bones:
        hb = rig.data.bones[head_bone]
        if hb.parent is not None:
            neck = hb.parent.name
        under_head = [b.name for b in hb.children_recursive]     # the jaw, and whatever a species hangs there
    field, face, marks = beard_field(ob, co, nrm, head_bone, neck, scale=k, also=under_head)
    n = regions()["n_body"]
    sd = np.full(len(me.vertices), -1.0)
    sd[:n] = np.minimum(face, np.maximum.reduce([field[r] for r in spec["regions"]]))
    fo, fi = 0.4 * spec["feather_m"], 0.6 * spec["feather_m"]
    saved = LOOK["beard"]
    LOOK["beard"] = dict(saved, style=style)
    try:
        mat, mat_rep, tile = _material(f"{base}_beard", colour, uv_name, "beard")
    finally:
        LOOK["beard"] = saved
    tile = tile * k
    # The mat reaches BEARD_MAT_FEATHER_M/2 past the field's zero line, not `feather_m`/2.5, so its alpha has
    # two or three rings of faces to fade over. Cut at the narrow band, the ramp from solid to gone happened
    # inside one face and the cheek line came out a staircase of whole faces - the same fault the shell's own
    # outline had before the field was a signed distance.
    out_m = fo + 0.5 * BEARD_MAT_FEATHER_M * k
    polys = [tuple(p.vertices) for p in me.polygons if max(p.vertices) < n
             and max(sd[i] for i in p.vertices) > -out_m and min(sd[i] for i in p.vertices) > -(out_m + 0.02 * k)]
    used = sorted({i for p in polys for i in p})
    local = {i: j for j, i in enumerate(used)}
    mw = np.array(ob.matrix_world, np.float64)
    base_co = np.array([tuple(me.vertices[i].co) for i in used]) @ mw[:3, :3].T + mw[:3, 3]
    vn = nrm[used]
    fade0 = 0.4 + 0.6 * np.clip((sd[used] + out_m) / (out_m + BEARD_MAT_FEATHER_M * k), 0.0, 1.0)
    z_m, chin_z = marks["mouth_z"], marks["chin_z"]
    g = 0.35 + 0.65 * _smooth_np(np.clip((z_m - base_co[:, 2]) / max(z_m - chin_z, 1e-6), 0.0, 1.0))
    wts = _named_weights(ob, used)
    c = Vector((0.0, marks["mouth_y"] + BEARD_AXIS_M * k, marks["mouth_z"]))
    # the root mat's UVs are arc lengths on a sphere of ONE radius round that centre, not of each point's own:
    # with the point's own radius the map is not affine across a face, and the faces where it changes fastest
    # (the moustache's, the underside of the chin) came out with texels 2.8x longer one way than the other and
    # a millimetre across - `hairtex.mip_check` refused a moustache-only beard and a stubble outright. At one
    # radius a texel is the texture's own size where the skin is at R and finer toward the chin, never coarser.
    beard_r = float(np.median(np.linalg.norm(base_co - np.array(tuple(c)), axis=1))) or 0.05 * k
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new(uv_name)
    col = bm.verts.layers.float_color.new(BEARD_FADE)
    vweights = []
    ns = spec["shells"]
    for sh in range(ns):
        f = sh / (ns - 1) if ns > 1 else 0.0
        off = spec["lift_m"] + f * spec["stand_m"] * g
        dens = 1.0 - BEARD_OUTER_THIN * f
        pos = base_co + vn * off[:, None]
        verts = []
        for j, p in enumerate(pos):
            v = bm.verts.new(Vector(p))
            v[col] = (1.0, 1.0, 1.0, float(fade0[j] * dens))
            verts.append(v)
            vweights.append(wts[j])
        du, dv = (0.37 * sh) % 1.0, (0.61 * sh) % 1.0      # each layer's texture shifted
        for p in polys:
            fc = bm.faces.new([verts[local[i]] for i in p])
            fc.smooth = True
            for loop in fc.loops:
                d = loop.vert.co - c
                rho = math.hypot(d.x, d.y)
                loop[uv].uv = (math.atan2(d.x, -d.y) * beard_r / tile + du,
                               -math.atan2(d.z, rho) * beard_r / tile + dv)
    weights = {}
    for i, w in enumerate(vweights):
        for name, x in w.items():
            weights.setdefault(name, np.zeros(len(vweights)))[i] = x
    bm.verts.index_update()
    from .hair import _object
    hob = _object(f"{base}_beard", bm, ob, rig, weights)
    bm.free()
    hob.data.materials.append(mat)
    hob["humanform_hair"] = {"part": "beard", "style": style}
    # marked as hair for whatever reads the body after the join (follow-through's flesh leaves it out)
    at = hob.data.attributes.new(BEARD_HAIR_ATTR, "FLOAT", "POINT")
    at.data.foreach_set("value", np.ones(len(hob.data.vertices), np.float32))
    objects = {"beard": hob}
    rep = {"style": style, "faces": len(hob.data.polygons), "verts": len(hob.data.vertices),
           "regions": {r: int(((field[r] > 0) & (face > 0)).sum()) for r in spec["regions"]},
           "marks": marks, "shells": ns, "length_m": round(spec["length_m"], 4), "volume": spec["volume"],
           "stand_m": round(spec["stand_m"], 4), "lift_m": spec["lift_m"], "feather_m": spec["feather_m"],
           "braids": (spec["cards"] or {}).get("braids", 0), "cards": None,
           "material": {x: mat_rep.get(x) for x in ("material", "source", "gltf", "texture")}}

    if spec["cards"] is not None:
        from . import cards as _cards
        cp = spec["cards"]
        # the beard's numbers, in the shapes `cards.grow` asks for: the field as a 0..1 weight per body
        # vertex, a length ramp longest at the chin, and a cap over the mouth so a long beard does not
        # bury it. Every length here is already scaled by the head, so grow() is handed scale 1.
        # the field `cards` grows from is the same ramp across the fade as the mat's alpha: the roots thin
        # over the feather band instead of stopping at it, so the cards overhang the mat's own polygon edge
        # rather than leaving it as a sawtooth line across the cheek. `density` is per square metre of field
        # weighted by that ramp, which is why a beard's numbers are large.
        # The cards root BEARD_CARD_OVERHANG_M further out than the mat, thinning to nothing there, so their
        # bodies fall across the mat's rim and break it. The mat is whole body faces and its alpha alone could
        # not soften that rim enough: the cheek line still stepped from quad to quad (which is what
        # `hairtex.silhouette_check`'s top edge refuses).
        card_out = out_m + BEARD_CARD_OVERHANG_M * k
        weight = np.zeros(len(me.vertices))
        weight[:n] = np.clip((sd[:n] + card_out) / (card_out + fi), 0.0, 1.0)
        fade_v = 0.4 + 0.6 * weight
        z = np.zeros(len(me.vertices))
        z[:n] = (np.array([tuple(me.vertices[i].co) for i in range(n)]) @ mw[:3, :3].T + mw[:3, 3])[:, 2]
        ramp = 0.35 + 0.65 * _smooth_np(np.clip((z_m - z) / max(z_m - chin_z, 1e-6), 0.0, 1.0))
        cap = np.where(z > z_m, BEARD_MOUSTACHE_MAX_M * k, 1e9)
        inside = {r: ((field[r] > fi) & (face > 0)).astype(float) for r in spec["regions"]}
        crep = _cards.grow(ob, weight[:n], spec["length_m"], colour, name=f"{base}_beard", uv_name=uv_name,
                           rig=rig, root_bone=head_bone, scale=1.0, length_scale=ramp[:n],
                           max_length_m=cap[:n], fade=fade_v[:n], what="beard",
                           hang_below_z=(chin_z - BEARD_HANG_SPLIT_M * k) if spec["hang_m"] > 0 else None,
                           hang_m=spec["hang_m"], regions=inside,
                           clear_m=BEARD_CARD_CLEAR_M * k, hang_clear_m=BEARD_HANG_CLEAR_M * k, tile=tile,
                           **{x: cp[x] for x in cp if x in _cards.PARAMS})
        for part, o in crep.pop("made").items():
            o["humanform_hair"] = {"part": f"beard_{part}", "style": style}
            objects[f"beard_{part}"] = o
        rep["cards"] = crep
        if "beard_strand" in objects:
            rep["cards"]["contract"] = _cards.contract(objects["beard_strand"])
            if not rep["cards"]["contract"]["passed"]:
                raise RuntimeError("the hanging beard does not meet follow-through's strand contract: "
                                   f"{rep['cards']['contract']['problems']}")

    # How many faces the mat's alpha takes to go from solid to gone. A ramp narrower than a face steps from
    # face to face, and that is a staircase along the cheek - an INTERIOR boundary, which no silhouette can
    # see, so it is measured here on the mesh instead.
    edge = [q for q in polys if max(fade0[local[i]] for i in q) > 0.5 and min(fade0[local[i]] for i in q) < 0.95]
    spread = sorted(max(fade0[local[i]] for i in q) - min(fade0[local[i]] for i in q) for q in edge) or [0.0]
    span = float(spread[len(spread) // 2])
    rep["mat_edge"] = {"faces": len(edge), "median_fade_span": round(span, 3),
                       "ramp_faces": round(0.6 / max(span, 1e-6), 2), "feather_m": BEARD_MAT_FEATHER_M * k}
    if edge and span > BEARD_MAT_SPAN_MAX:
        raise RuntimeError(f"{base}_beard: the root mat's alpha crosses from solid to gone in {0.6 / span:.1f} "
                           f"faces (at least {0.6 / BEARD_MAT_SPAN_MAX:.0f} wanted) - its edge will read as a "
                           "staircase of whole faces along the cheek; widen BEARD_MAT_FEATHER_M")

    from . import hairtex
    rep["godot_sampling"], rep["silhouette"] = {}, {}
    bad = []
    for part, o in objects.items():
        if mat_rep.get("source") == "lookdev":
            # how it will sample in Godot: a beard whose holes survive the mips as patches is refused here,
            # before it is exported (the first beards' square patches cost four rebuilds to find by eye)
            check = hairtex.mip_check(o)
            rep["godot_sampling"][o.name] = {x: check[x] for x in ("ok", "across_to_along_p90", "texel_mm",
                                                                   "views")}
            if not check["ok"]:
                raise RuntimeError(f"{o.name}: the beard would draw as patches in Godot - "
                                   + "; ".join(check["problems"]))
    # How its outline reads: a shell's is a smooth curve (a decal), hair's is the ends of its hairs - measured
    # over the mat, the cards and the hanging locks together, because that is what the eye sees and each
    # piece's own edge is a cut through it (the mat's is the field's zero line, the cards' is the chin where
    # the locks take over). Stubble is the mat alone and is exempt: a shell is right there.
    sil = hairtex.silhouette_check(obs=list(objects.values()), name=f"{base}_beard",
                                   rough_min_px=(None if spec["cards"] is not None else {}))
    rep["silhouette"]["beard"] = {"ok": sil["ok"], "views": sil["views"], "problems": sil["problems"],
                                  "warnings": sil.get("warnings", [])}
    bad += sil["problems"]
    for w in sil.get("warnings", []):
        print(f"[beard] WARN {base}: {w}", flush=True)
    for part, o in objects.items():
        if part != "beard":
            rep["silhouette"][part] = {"views": hairtex.silhouette_check(o, rough_min_px={},
                                                                         name=o.name)["views"]}
    c_ = rep["cards"] or {}
    print(f"[beard] {style}: {c_.get('roots', 0)} cards in {c_.get('clumps', 0)} clumps "
          f"({c_.get('rooted', 0)} on the face, {c_.get('hanging', 0)} hanging, "
          f"{c_.get('cut_at_hang', 0)} cut at the chin, {c_.get('braided', 0)} braided), "
          f"{sum(len(o.data.vertices) for o in objects.values())} verts, "
          f"clearance {(c_.get('min_clearance_m') or 0) * 1000:.1f} mm; gaps "
          + ", ".join(f"{b} {v['gap_p99_mm']}/{v['nominal_mm']} mm ({v['roots']} roots)"
                      for b, v in (c_.get("coverage", {}).get("regions") or {}).items())
          + "; outline " + " ".join(f"{x.split()[0]}@{x.split()[1]} {y['wander_px']}px"
                                    for x, y in rep["silhouette"]["beard"]["views"].items())
          + " (" + ", ".join(f"{part} {s['views']['front 0.6m']['wander_px']}px"
                             for part, s in rep["silhouette"].items() if part != "beard") + ")", flush=True)
    if bad:
        raise RuntimeError(f"{hob.name}: the beard's outline does not read as hair - " + "; ".join(bad))
    return objects, rep


def beard_strand_contract(ob):
    """`cards.contract` on a hanging beard: follow-through's strand contract, checked."""
    from . import cards as _cards
    return _cards.contract(ob)


# ------------------------------------------------------------------------------------------ entry

def add(body, lm, colour, base, rig=None, uv_name="UVMap", brows=True, lashes=True, body_hair=False, sex=None,
        brow_shape=None, beard=None, beard_colour=None, beard_length=None, beard_volume=None, beard_braids=None):
    """Brows, lashes and (optionally) body hair and a beard on a baked MPFB body. `lm` is `hair.landmarks(body)`;
    `colour` the scalp hair's screen (sRGB) colour; `brow_shape` one of `BROW_SHAPES` (None: "natural");
    `beard` one of `BEARD_STYLES` (None: none), in `beard_colour` (None: the hair colour darkened by BEARD_DARKEN),
    with `beard_braids` ropes wound out of its hanging part (a dwarf's plaited beard; 0 or None: loose locks).
    A beard long enough to hang leaves a second object, `<base>_beard_strand`, which carries follow-through's
    strand contract and must not be joined into the body.
    Returns {objects, parts, skipped}."""
    if beard is not None and beard not in BEARD_STYLES:
        raise ValueError(f"beard {beard!r} is not one of {tuple(BEARD_STYLES)}")
    brow_shape = brow_shape or "natural"
    if brow_shape not in BROW_SHAPES:
        raise ValueError(f"brow_shape {brow_shape!r} is not one of {tuple(BROW_SHAPES)}")
    from . import body as _body
    ob = _body.obj(body)
    out = {"objects": {}, "parts": {}, "skipped": None}
    if not (brows or lashes or body_hair or beard):
        return out
    if not is_mpfb(ob):
        out["skipped"] = f"{ob.name} has {len(ob.data.vertices)} vertices, fewer than an MPFB body's " \
                         f"{regions()['n_body']}: no brows, lashes, body hair or beard"
        return out
    co = lm["_co"]
    head = lm["head_bone"]
    for part, on, k in (("brows", brows, BROW_DARKEN), ("lashes", lashes, LASH_DARKEN)):
        if not on:
            continue
        card, rep = _cards(ob, co, part, base, rig, _darken(colour, k), uv_name, head, brow_shape=brow_shape,
                           scale=lm.get("scale", 1.0))
        out["objects"][part] = card.name
        out["parts"][part] = rep
    if body_hair:
        hob, rep = _body_hair(ob, co, base, rig, _darken(colour, BODY_HAIR_DARKEN), uv_name, sex)
        out["objects"]["body_hair"] = hob.name
        out["parts"]["body_hair"] = rep
    if beard:
        bcol = tuple(beard_colour) if beard_colour is not None else _darken(colour, BEARD_DARKEN)
        made, rep = _beard(ob, co, base, rig, bcol, uv_name, beard, head, scale=lm.get("scale", 1.0),
                           length_m=beard_length, volume=beard_volume, braids=beard_braids)
        for part, o in made.items():
            out["objects"][part] = o.name
        out["parts"]["beard"] = rep
    return out
