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
}
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
    over["godot"] = godot
    mat, rep = ld_hair.material(name, colour, uv_map=uv_name, pixels=pixels, **over)
    if card_rep is not None:
        rep = dict(rep, texture=card_rep)
    if hasattr(mat, "use_transparent_shadow"):
        mat.use_transparent_shadow = True       # a card's shadow is its strands', not the whole card's
    if double_sided:
        mat.use_backface_culling = False
    tile = 1.0 if part in ("brows", "lashes") else rep["tile_m"]
    return mat, dict(rep, source="lookdev", double_sided=double_sided), tile


# ------------------------------------------------------------------------------------------ card textures

def _srgb_to_linear(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _strand(cover, tone, rng, x0, v0, v1, w0, w1, lean, bright):
    """Draw one hair into `cover` (H, W) as an antialiased tapering line from (x0 px, v0) to (x0 + lean px, v1),
    keeping the brightness of whichever hair is on top in `tone`."""
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


def _shape_brow(p, uv, shape, bvh):
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
    delta = np.interp(t, k[:, 0], k[:, 1])
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


def _cards(ob, co, part, base, rig, colour, uv_name, head, brow_shape="natural"):
    d = regions()[part]
    shaped = {}
    bvh = _body_bvh(ob, co) if part == "brows" and BROW_SHAPES[brow_shape] is not None else None
    mat, mat_rep, tile = _material(f"{base}_{part}", colour, uv_name, part, double_sided=(part == "lashes"))
    pts, faces, uvs, tris, bary = [], [], [], ([], [], []), []
    lids = {}
    for side in ("L", "R"):
        card = d[side]
        p, (ia, ib, ic), w = _rebuild(co, card["fit"])
        off = len(pts)
        if tile == 1.0:
            uv, side_lids = _card_uv(part, p, card["faces"], card["uv"])
            for k, n in side_lids.items():
                lids[k] = lids.get(k, 0) + n
        else:
            uv = card["uv"]
        if part == "brows" and tile == 1.0:
            p, shaped[side] = _shape_brow(p, uv, brow_shape, bvh)
        pts.extend(p.tolist())
        faces.extend([[off + i for i in q] for q in card["faces"]])
        uvs.extend(uv)
        tris[0].extend(ia.tolist())
        tris[1].extend(ib.tolist())
        tris[2].extend(ic.tolist())
        bary.extend(w.tolist())
    tris = tuple(np.array(t) for t in tris)
    weights = _interp_weights(ob, tris, np.array(bary), head)
    card = _card_object(f"{base}_{part}", ob, rig, pts, faces, uvs, weights, uv_name, tile)
    card.data.materials.append(mat)
    card["humanform_hair"] = {"part": part}
    # the lash roots and the brow must lie on the skin: the distance of each card's root row from the body
    return card, {"faces": len(faces), "verts": len(pts), "weights": sorted(weights),
                  "material": {k: mat_rep.get(k) for k in ("material", "source", "gltf", "double_sided", "texture")},
                  "colour": [round(c, 4) for c in colour], **({"lid_cards": lids} if lids else {}),
                  **({"shape": shaped} if shaped else {})}


# ------------------------------------------------------------------------------------------ body hair

def _sparse(px, npx, seed=3):
    """Thin the body hair's strand pixels (lookdev's, as `strand_texture` returns them) before they become the
    material's images: keep BODY_HAIR_KEEP of its strand bands, each rolled along V at random so the kept
    strands do not start on one row. Returns (colour, normal)."""
    px, npx = np.array(px, np.float64), np.array(npx, np.float64)
    H, W = px.shape[:2]
    rng = np.random.RandomState(seed)
    band = max(2, W // LOOK["body_hair"]["strands_per_tile"])
    for x0 in range(0, W, band):
        cols = slice(x0, min(W, x0 + band))
        if rng.uniform() > BODY_HAIR_KEEP:
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


# ------------------------------------------------------------------------------------------ entry

def add(body, lm, colour, base, rig=None, uv_name="UVMap", brows=True, lashes=True, body_hair=False, sex=None,
        brow_shape=None):
    """Brows, lashes and (optionally) body hair on a baked MPFB body. `lm` is `hair.landmarks(body)`;
    `colour` the scalp hair's screen (sRGB) colour; `brow_shape` one of `BROW_SHAPES` (None: "natural").
    Returns {objects, parts, skipped}."""
    brow_shape = brow_shape or "natural"
    if brow_shape not in BROW_SHAPES:
        raise ValueError(f"brow_shape {brow_shape!r} is not one of {tuple(BROW_SHAPES)}")
    from . import body as _body
    ob = _body.obj(body)
    out = {"objects": {}, "parts": {}, "skipped": None}
    if not (brows or lashes or body_hair):
        return out
    if not is_mpfb(ob):
        out["skipped"] = f"{ob.name} has {len(ob.data.vertices)} vertices, fewer than an MPFB body's " \
                         f"{regions()['n_body']}: no brows, lashes or body hair"
        return out
    co = lm["_co"]
    head = lm["head_bone"]
    for part, on, k in (("brows", brows, BROW_DARKEN), ("lashes", lashes, LASH_DARKEN)):
        if not on:
            continue
        card, rep = _cards(ob, co, part, base, rig, _darken(colour, k), uv_name, head, brow_shape=brow_shape)
        out["objects"][part] = card.name
        out["parts"][part] = rep
    if body_hair:
        hob, rep = _body_hair(ob, co, base, rig, _darken(colour, BODY_HAIR_DARKEN), uv_name, sex)
        out["objects"]["body_hair"] = hob.name
        out["parts"]["body_hair"] = rep
    return out
