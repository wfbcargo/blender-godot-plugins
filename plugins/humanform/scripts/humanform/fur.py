"""Fur: one coverage map on the shared hm08 mesh, drawn in Godot as offset shells.

    from humanform import fur
    fur.validate(block)                  # problems, each with the range in the message (no bpy)
    rep = fur.apply(human, block)        # per-vertex map on the body + the `humanform_fur` property
    rep = fur.bake(human, out_dir)       # the three PNGs, the checks, the covered skin

**The coverage map is the shared object.** Everything a shell and a strand card both need is per
vertex of hm08's body (`delta.BODY_VERTS`), so it transfers between bodies the way `delta.py`'s parts
and `skin.py`'s region weights do - the same vertex is the same anatomical place on every MPFB body,
before or after the species warp:

    hf_fur_den    FLOAT          density 0..1: the share of the skin the fur hides there
    hf_fur_len    FLOAT          length in metres, at that vertex
    hf_fur_flow   FLOAT_VECTOR   unit direction the fur lies, in the body's object space
    hf_fur_col    FLOAT_VECTOR   the fur's own colour there, linear RGB
    hf_fur_pat    FLOAT          0..1: where the region's second colour may show

A fur block names regions by landmark areas (`AREAS`, the vocabulary `skin.pattern_areas` uses,
widened for the parts fur cares about: a face nap, forearms, a ruff round the neck), each with a
length, a density, a flow, a colour and a pattern colour. The areas are measured on the body's own
joints, so a dwarf's ruff sits on the dwarf's shoulders and a troll's on the troll's.

**Density, length and flow travel as a vertex colour, not as a texture.** hm08's shipping UV atlas
overlaps itself - about a fifth of its texels are claimed by two different parts of the body
(`atlas_overlap`) - so a coverage map rasterised into it depends on the order the triangles happen to be
drawn in, and the first one came back with furred hands, feet and scalp. The three quantities vary over
centimetres, which hm08's 8-15 mm quads carry with room to spare, so they go in the `hf_fur` colour
attribute (VCOL) and glTF carries them as COLOR_0.

**Two textures** carry what does need texel resolution:

    <base>_fur_colour.png   RGB, sRGB: the fur's colour, the region's pattern already mixed in
                            per texel (spots, stripes, blotches - `skin.PATTERN_KINDS`' words).
                            Colour survives the overlap: the furred triangles are drawn last, so a
                            contested texel can only tint fur slightly wrong, never open a hole.
    <base>_fur_strands.png  R8, tiled: per texel the height up the fur (0..1) the strand there
                            reaches, 0 for bare skin. A shell at height t keeps the texels over t, so
                            the strands taper by themselves and no shell repeats another's outline.
                            Being tiled, it never touches the atlas at all.

`TILE_M` on the skin at `MASK_PX` is chosen so `hairtex.mip_check` passes at 0.6 m and at 4 m: the
gaps between strands stay under a screen pixel wide at the mip Godot picks, instead of surviving into
a mip and cutting square patches of skin out (the beard's failure, `hairtex`'s docstring).

**The Godot side** is `humanform/godot/addons/humanform_fur/fur.gd`: N copies of the skin mesh, the
same skin and skeleton, pushed out along the normal by `t * length`, sheared along the flow, drawn
with the strand mask. `covered` lists the skin under fur dense enough to hide it, as positions in the
glTF mesh space, exactly as wardrobe lists the skin a garment covers - so that skin is not drawn.
"""

from __future__ import annotations

import json
import math
import os

try:                     # validate()/normalise() are standard library only: species_design (and
    import numpy as np   # character-pipeline's spec check) call them outside Blender, where numpy may be absent
except ImportError:      # pragma: no cover
    np = None


def _delta():
    """humanform.delta, imported late: it needs bpy, and the block checks above run outside Blender."""
    from . import delta
    return delta


SCHEMA = "humanform-fur/1"
PROP = "humanform_fur"

# per-vertex map (point attributes on the body, read by `bake`)
DEN = "hf_fur_den"
LEN = "hf_fur_len"
FLOW = "hf_fur_flow"
COL = "hf_fur_col"
PAT = "hf_fur_pat"
# 1 on every vertex the body had when the map was laid on it. A finished body carries more than skin - the
# hair cap, the brows and the lashes are joined into the same mesh, and their UVs are tiled in strand units,
# so one of their cards can span the whole atlas and paint its own (furless) values over the skin's. It did,
# the first time. Marking the skin when the map is written is the one test that cannot be fooled by a UV.
SKIN = "hf_fur_skin"
CARD_FIELD = "hf_fur_card_"    # + the region name: the field a `cards` region grows its strands from
# The map Godot reads, as a FLOAT_COLOR attribute: R density, G length / length_max_m, B and A the flow's
# (cos, sin) in the mesh's tangent frame, mapped to 0..1. It is a vertex attribute and not a texture
# because **hm08's UV atlas overlaps itself**: a fifth of its texels are claimed by two different parts of
# the body, and a coverage map rasterised into it came back with furred hands, feet and scalp (`atlas_overlap`
# measures it). Density, length and flow vary over centimetres, so hm08's 8-15 mm quads carry them with room
# to spare. glTF takes it as COLOR_0 (rig-anything's exporter names it; see its VERTEX_COLOUR_MAPS).
VCOL = "hf_fur"

# Landmark areas a region may name: `skin.PATTERN_AREAS`' words (one vocabulary for where something sits
# on a body), widened by the parts fur asks for and a skin pattern never did - a face, a ruff, forearms.
# `tail` and `graft` are the two areas that are NOT hm08: they are geometry a body plan added
# (humanform.tail lofts a tail off the sacrum, humanform.graft lofts one where the legs were), whose
# vertices sit past `delta.BODY_VERTS`. They are skin like any other - a hyena's tail is a brush - so
# `areas` reads them off their own vertex groups rather than off hm08's landmarks.
AREAS = ("body", "head", "face", "neck", "ruff", "shoulders", "back", "front", "torso", "chest",
         "belly", "arms", "upper_arms", "forearms", "hands", "legs", "thighs", "shins", "feet",
         "tail", "graft")
TAIL_GROUP = "hf_tail"         # humanform.tail.GROUP: the vertices it lofted
# never furred: the skin that has to stay skin (as `skin.PATTERN_SKIP`, plus the eyes and the mouth)
SKIP_REGIONS = ("palm", "sole", "lips", "nail")
EYE_RADII = 1.9                # eyeball radii round each eye kept bare
FLOWS = ("down", "back", "out", "along")

# Ranges. Past LENGTH_M shell fur stops being cheap or convincing: at 8 cm the shells are far enough
# apart to read as stacked sheets whatever their number, and hair that long hangs and swings, which is
# strand cards' job (humanform.hair), not a shell's.
LENGTH_M = (0.0008, 0.08)
# ... unless the region says `cards = true`, which is how hair PAST that goes on: strand cards
# (`humanform.cards`, reached through `hair.cards`), grown from this region's own mask. A mane, a ruff
# past 8 cm and a tail's brush are the same growth a beard is, and the coverage map is already the
# per-vertex field it takes. What the region leaves in the SHELL map is `CARD_MAT_M` of root mat at its
# own density - the thing that hides the skin, as a scalp's cap does - and the cards stand on that.
CARD_LENGTH_M = (0.02, 0.45)   # a card region's length: under 2 cm shells are cheaper and better
CARD_MAT_M = 0.004             # the mat a card region leaves in the shell map
CARD_DENSITY = 7000.0          # card roots a square metre of field: a beard's own is 26000, and a
                               # mane runs the whole neck and both shoulders. The mat hides the skin;
                               # the cards are there for the silhouette, so they are wider and sparser
CARD_WIDTH_M = 0.014           # ... and this wide at the root (a beard's is 0.008)
CARD_JITTER = 0.5              # ... and their length varies by this share, card to card: a beard's
                               # 0.35 over a field this size still ended a mane on one line
DENSITY = (0.05, 1.0)
SHELLS = (4, 24)
SHELLS_DEFAULT = 12
PATTERN_SCALE_M = (0.005, 0.5)
PATTERN_AMOUNT = (0.0, 1.0)
LAY = (0.0, 1.0)               # how far the fur lies over: 0 stands straight out, 1 lies flat
LAY_DEFAULT = 0.55
BLEND_SHARP = 3.0              # how sharply a region keeps its own length against its neighbours' (see `apply`)
BLEND_COLOUR = 1.0             # ... and how gently its colour crosses into theirs
EDGE_LENGTH = 0.25             # the share of its length fur keeps at the very edge of its coverage
RIM = (0.25, 0.60)             # an area weight is remapped through this: solid inside, feathered at the rim
# ... after the area is normalised by its own peak (see `apply`). Under this peak there is no region worth
# normalising - a couple of vertices clipping a landmark - and the build says so instead of scaling noise up.
PEAK_FLOOR = 0.12

COVER_DENSITY = 0.75           # skin under fur at least this dense is not drawn (the base coat covers it)
MIN_DENSITY = 0.02             # under this a vertex carries no fur at all

TILE_M = 0.040                 # the strand mask's tile on the skin
MASK_PX = 512
MAP_PX = 1024
# A coat, not a speckle. At 900 strands a square centimetre and 0.45 mm across, a texel was a strand and
# the pelt read at 2 m as dirt on skin rather than as fur: the eye was given per-texel noise, which is what
# dirt looks like. Fur reads as fur by its *clumps* - it parts, and each clump lies together - so the
# strands are fewer and wider, gathered into clumps a few millimetres apart, and each strand carries its
# own tone along its whole length instead of the mask varying texel to texel.
STRAND_MM = 0.95               # a strand's width on the skin
STRANDS_PER_CM2 = 230.0        # seeds per square centimetre of skin at density 1
CLUMP_MM = 4.2                 # how far apart the clumps sit
CLUMP_PULL = 0.45              # how far a strand is drawn toward its clump's centre
CLUMP_SHARE = 0.6              # how much of a strand's length its clump decides, the rest its own
STRAND_TONE = 0.55             # the spread of tone between strands (1 = black to white)
STRAND_PX_MIN = 1.0            # a strand narrower than this at 0.6 m is a wash, not hair
CONSERVATIVE_PX = 0.75         # how far past its edges a triangle may claim an unclaimed texel

# What the checks hold the fur to on the outline. A screen pixel is 0.30 mm on the skin at 0.6 m and 1.99 mm
# at 4 m (`hairtex.VFOV_DEG`, `IMAGE_PX`), so the two distances ask opposite questions:
#   at 4 m   is there any fur to see at all? Under SIL_MIN_PX it is a fuzz on the edge, and the shells cost
#            their draw calls for nothing - tint the skin instead.
#   at 0.6 m does the outline comb? On the silhouette a shell's gap is against the background, with nothing
#            behind it, so it is the one place layers read as separate. SIL_BAND_PX holds the gap at 4 m,
#            where fur should be seamless; SIL_NEAR_BAND_PX is the close-up's looser limit, and a failure
#            there is answered by more shells (the message says how many), not by shorter fur.
# Fur too long for shells at all is refused earlier, by LENGTH_M: past 8 cm hair hangs and swings, and only
# strand cards do that.
SIL_DISTANCES_M = (0.6, 4.0)
SIL_MIN_PX = 0.9
SIL_BAND_PX = 2.0
SIL_NEAR_BAND_PX = 12.0


# ------------------------------------------------------------------ the block


def _rgb(v, what):
    if not isinstance(v, (list, tuple)) or len(v) != 3 or not all(isinstance(c, (int, float)) for c in v):
        raise ValueError(f"{what} must be [r, g, b], screen (sRGB) channels 0..1")
    if not all(0.0 <= float(c) <= 1.0 for c in v):
        raise ValueError(f"{what} {list(v)}: every channel must be 0..1")
    return [round(float(c), 4) for c in v]


def _range(name, v, lo, hi, unit=""):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise ValueError(f"{name} must be a number, got {v!r}")
    if not lo <= float(v) <= hi:
        raise ValueError(f"{name} {v}{unit} is outside {lo}-{hi}{unit}")
    return float(v)


def normalise(block):
    """A fur block with its defaults filled in, or None for no fur. Raises ValueError with the range in
    the message. Stdlib and numpy only: it runs outside Blender (species_design validates with it)."""
    if block is None:
        return None
    if not isinstance(block, dict):
        raise ValueError("fur must be a table of regions (see humanform.fur.AREAS)")
    b = dict(block)
    unknown = sorted(set(b) - {"schema", "regions", "shells", "lay", "seed", "cover", "tile_m", "note"})
    if unknown:
        raise ValueError(f"fur keys {unknown}: only regions, shells, lay, seed, cover, tile_m, note")
    regions = b.get("regions")
    if not regions:
        raise ValueError("fur needs at least one region: {\"regions\": [{\"areas\": [...], \"length_m\": ...}]}, "
                         f"areas one of {', '.join(AREAS)}")
    if isinstance(regions, dict):          # {name: {...}} is as good as a list, and reads better in TOML
        regions = [dict(v, name=k) for k, v in regions.items()]
    out = []
    names = set()
    for i, r in enumerate(regions):
        if not isinstance(r, dict):
            raise ValueError(f"fur.regions[{i}] must be a table")
        bad = sorted(set(r) - {"name", "areas", "length_m", "density", "flow", "colour", "pattern_colour",
                               "pattern", "except_areas", "cards"})
        if bad:
            raise ValueError(f"fur.regions[{i}] keys {bad}: only name, areas, except_areas, length_m, density, "
                             "flow, colour, pattern_colour, pattern, cards")
        name = str(r.get("name") or f"fur{i + 1}")
        if name in names:
            raise ValueError(f"fur.regions: two regions named {name!r}")
        names.add(name)
        areas = r.get("areas") or ["body"]
        if isinstance(areas, str):
            areas = [areas]
        for a in areas:
            if a not in AREAS:
                raise ValueError(f"fur.regions[{name}].areas {a!r}: one of {', '.join(AREAS)}")
        skip = r.get("except_areas") or []
        if isinstance(skip, str):
            skip = [skip]
        for a in skip:
            if a not in AREAS:
                raise ValueError(f"fur.regions[{name}].except_areas {a!r}: one of {', '.join(AREAS)}")
        as_cards = r.get("cards", False)
        if not isinstance(as_cards, bool):
            raise ValueError(f"fur.regions[{name}].cards must be true or false (strand cards, or shells)")
        length = _range(f"fur.regions[{name}].length_m", r.get("length_m", 0.008),
                        *(CARD_LENGTH_M if as_cards else LENGTH_M), unit=" m")
        density = _range(f"fur.regions[{name}].density", r.get("density", 1.0), *DENSITY)
        flow = r.get("flow", "down")
        if flow not in FLOWS:
            raise ValueError(f"fur.regions[{name}].flow {flow!r}: one of {', '.join(FLOWS)}")
        ent = {"name": name, "areas": list(areas), "except_areas": list(skip),
               "length_m": round(length, 5), "density": round(density, 4), "flow": flow,
               "cards": bool(as_cards)}
        if r.get("colour") is not None:
            ent["colour"] = _rgb(r["colour"], f"fur.regions[{name}].colour")
        if r.get("pattern_colour") is not None:
            ent["pattern_colour"] = _rgb(r["pattern_colour"], f"fur.regions[{name}].pattern_colour")
        pat = r.get("pattern")
        if pat is not None:
            if isinstance(pat, str):
                pat = {"kind": pat}
            if not isinstance(pat, dict):
                raise ValueError(f"fur.regions[{name}].pattern must be a word or a table")
            kinds = ("spots", "stripes", "blotches", "mottle")
            kind = pat.get("kind", "spots")
            if kind not in kinds:
                raise ValueError(f"fur.regions[{name}].pattern.kind {kind!r}: one of {', '.join(kinds)}")
            ent["pattern"] = {
                "kind": kind,
                "scale": round(_range(f"fur.regions[{name}].pattern.scale", pat.get("scale", 0.05),
                                      *PATTERN_SCALE_M, unit=" m"), 4),
                "amount": round(_range(f"fur.regions[{name}].pattern.amount", pat.get("amount", 0.6),
                                       *PATTERN_AMOUNT), 3)}
            if ent.get("pattern_colour") is None:
                raise ValueError(f"fur.regions[{name}].pattern needs pattern_colour: the second colour it draws")
        out.append(ent)
    shells = int(_range("fur.shells", b.get("shells", SHELLS_DEFAULT), *SHELLS))
    lay = _range("fur.lay", b.get("lay", LAY_DEFAULT), *LAY)
    tile = _range("fur.tile_m", b.get("tile_m", TILE_M), 0.008, 0.2, unit=" m")
    cover = b.get("cover", True)
    if not isinstance(cover, bool):
        raise ValueError("fur.cover must be true or false (draw the skin under dense fur, or not)")
    doc = {"schema": SCHEMA, "regions": out, "shells": shells, "lay": round(lay, 3),
           "seed": int(b.get("seed", 0)), "cover": cover, "tile_m": round(tile, 4)}
    if b.get("note"):
        doc["note"] = str(b["note"])
    return doc


def validate(block):
    """Problems with a fur block, as strings with the range in the message (empty when it is buildable)."""
    try:
        normalise(block)
    except ValueError as exc:
        return [str(exc)]
    return []


def shell_heights(n):
    """The heights 0..1 of `n` strand shells, in the order a level of detail drops them: the outermost
    first (it carries the silhouette), then the middle, then between - a van der Corput order, so the
    first M of them always span the whole height and dropping the rest thins the fur without shortening
    it or moving its outline. That is what stops a distance change popping between shells."""
    t = [(i + 1) / n for i in range(n)]
    order = sorted(range(n), key=lambda i: (_vdc(n - 1 - i), i))
    return [t[i] for i in order]


def _vdc(i, base=2):
    v, d = 0.0, 1.0 / base
    while i:
        v += (i % base) * d
        i //= base
        d /= base
    return v


# ------------------------------------------------------------------ the areas, on the body's own joints


def _smooth(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / (e1 - e0 if e1 != e0 else 1e-9), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _rings(bare, faces, rings, n):
    """0 on a bare vertex, rising to 1 `rings` edges away from the nearest bare one - how far into the fur a
    vertex is, in rings of the mesh. The fur's colour and its length are feathered on this."""
    d = _delta()
    r, c = d.neighbours(faces)
    out = np.full(d.BODY_VERTS, float(rings))
    front = np.zeros(d.BODY_VERTS, bool)
    front[:n] = bare[:n]
    out[front] = 0.0
    for k in range(1, rings):
        grown = front.copy()
        grown[r[front[c]]] = True
        new = grown & ~front
        out[new] = float(k)
        front = grown
    return np.clip(out[:n] / float(rings), 0.0, 1.0)


def _seg_distance(p, pts):
    d = np.full(len(p), 9.0)
    for a, b in zip(pts[:-1], pts[1:]):
        ab = b - a
        t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-9), 0, 1)
        d = np.minimum(d, np.linalg.norm(p - (a + np.outer(t, ab)), axis=1))
    return d


def areas(ob):
    """({area: weight 0..1 over EVERY vertex the body has}, {"flow": (n_all, 3) unit vectors, "scale": s},
    notes) - every `AREAS` name measured on this body's own joints, the way `skin.regions` measures a skin
    region, so the same block lands in the same anatomical place on a dwarf and on a troll.

    The landmark areas are hm08's, so they are measured over its own vertices and are zero past them.
    Geometry a body plan ADDED - a tail off the sacrum, a graft where the legs were - is skin too, and it
    carries fur through its own area (`tail`, `graft`), read off the vertex group that made it. Before
    that, everything past `delta.BODY_VERTS` took density zero and a tail could not be given a brush."""
    from . import muscle, skin
    n_all = len(ob.data.vertices)
    n = min(n_all, _delta().BODY_VERTS)
    co = _delta().mixed_coords(ob)
    faces = _delta().body_faces(ob)
    p = co[:n]
    nrm = _delta().vertex_normals(co, faces)[:n]
    j = muscle._joints(ob, co)
    notes = []
    need = ("joint-neck", "joint-pelvis", "joint-l-upper-leg", "joint-l-shoulder", "joint-l-elbow",
            "joint-l-hand", "joint-l-knee", "joint-l-ankle", "joint-l-eye")
    missing = [k for k in need if k not in j]
    A = {a: np.zeros(n) for a in AREAS}
    A["body"] = np.ones(n)
    if missing:
        notes.append(f"no joints {missing}: fur covers the whole body evenly")
        A, ctx = _grow_to_mesh(ob, A, None, None, n, n_all, 1.0, j)
        return A, ctx, notes
    s = float((j["joint-neck"][2] - j["joint-pelvis"][2]) / 0.60)
    xs = 1.0 if j["joint-l-hand"][0] > 0 else -1.0
    neck_z, sh_z = float(j["joint-neck"][2]), float(j["joint-l-shoulder"][2])
    hip_z, knee_z, ank_z = (float(j["joint-l-upper-leg"][2]), float(j["joint-l-knee"][2]),
                            float(j["joint-l-ankle"][2]))
    front = -nrm[:, 1]                                     # MPFB faces -Y
    eye_z = float(j["joint-l-eye"][2])
    A["head"] = _smooth(neck_z - 0.01 * s, neck_z + 0.04 * s, p[:, 2])
    # The face is the front of the head *below the brow*. Taken as "the head, facing forward" it reached
    # over the crown - a crown vertex tilts forward a little, and the smoothing at the end of this function
    # carried the rest - and a 3 mm nap at density 0.7 drew a black skull cap over the hair in Godot.
    A["face"] = (A["head"] * _smooth(0.15, 0.55, front)
                 * (1.0 - _smooth(eye_z + 0.05 * s, eye_z + 0.12 * s, p[:, 2])))
    A["neck"] = _smooth(sh_z - 0.02 * s, sh_z + 0.05 * s, p[:, 2]) * (1 - A["head"])
    A["back"] = _smooth(0.0, 0.45, nrm[:, 1])
    A["front"] = _smooth(0.0, 0.45, -nrm[:, 1])
    arm = np.zeros(n)
    upper = np.zeros(n)
    fore = np.zeros(n)
    hand = np.zeros(n)
    along = np.zeros((n, 3))
    for side in (1.0, -1.0):
        sgn = np.array([side, 1.0, 1.0])
        sho, elb, wri = (np.array(j[k], np.float64) * sgn
                         for k in ("joint-l-shoulder", "joint-l-elbow", "joint-l-hand"))
        tip = wri + (wri - elb) * 0.6
        d = _seg_distance(p, [sho, elb, wri, tip])
        outward = _smooth(0.5, 1.0, np.abs(p[:, 0]) / max(abs(j["joint-l-shoulder"][0]), 1e-6))
        limb = (1.0 - _smooth(0.06 * s, 0.12 * s, d)) * outward
        arm = np.maximum(arm, limb)
        du = _seg_distance(p, [sho, elb])
        df = _seg_distance(p, [elb, wri])
        dh = _seg_distance(p, [wri, tip])
        upper = np.maximum(upper, limb * (du <= np.minimum(df, dh) + 1e-9))
        fore = np.maximum(fore, limb * (df < np.minimum(du, dh)))
        hand = np.maximum(hand, limb * (dh < np.minimum(du, df)))
        for a, b in ((sho, elb), (elb, wri)):
            seg = b - a
            L = max(float(np.linalg.norm(seg)), 1e-9)
            t = np.clip(((p - a) @ seg) / (L * L), 0, 1)
            near = np.linalg.norm(p - (a + np.outer(t, seg)), axis=1) < 0.12 * s
            along[near] = seg / L
        hipj = np.array(j["joint-l-upper-leg"], np.float64) * sgn
        kne = np.array(j["joint-l-knee"], np.float64) * sgn
        ank = np.array(j["joint-l-ankle"], np.float64) * sgn
        for a, b in ((hipj, kne), (kne, ank)):
            seg = b - a
            L = max(float(np.linalg.norm(seg)), 1e-9)
            t = np.clip(((p - a) @ seg) / (L * L), 0, 1)
            near = (np.linalg.norm(p - (a + np.outer(t, seg)), axis=1) < 0.13 * s) & (p[:, 2] < hip_z)
            along[near] = seg / L
    A["arms"], A["upper_arms"], A["forearms"], A["hands"] = arm, upper * arm, fore * arm, hand * arm
    A["shoulders"] = np.clip(np.zeros(n), 0, 1)
    for side in (1.0, -1.0):
        c = np.array(j["joint-l-shoulder"], np.float64) * np.array([side, 1.0, 1.0])
        A["shoulders"] = np.maximum(A["shoulders"],
                                    1.0 - _smooth(0.05 * s, 0.13 * s, np.linalg.norm(p - c, axis=1)))
    A["ruff"] = np.clip(np.maximum(A["neck"], A["shoulders"] * (1 - arm)) +
                        _smooth(sh_z - 0.12 * s, sh_z - 0.02 * s, p[:, 2]) * (1 - arm) *
                        (1 - _smooth(neck_z - 0.02 * s, neck_z + 0.03 * s, p[:, 2])) * 0.9, 0, 1)
    legs = 1.0 - _smooth(hip_z - 0.06 * s, hip_z + 0.02 * s, p[:, 2])
    A["legs"] = legs * (1 - arm)
    A["feet"] = A["legs"] * (1.0 - _smooth(ank_z - 0.01 * s, ank_z + 0.03 * s, p[:, 2]))
    A["shins"] = A["legs"] * _smooth(ank_z, ank_z + 0.03 * s, p[:, 2]) * (
        1.0 - _smooth(knee_z - 0.01 * s, knee_z + 0.05 * s, p[:, 2]))
    A["thighs"] = A["legs"] * _smooth(knee_z, knee_z + 0.05 * s, p[:, 2])
    A["torso"] = np.clip(1 - np.maximum(np.maximum(A["head"], A["legs"]), arm), 0, 1)
    mid_z = 0.5 * (sh_z + hip_z)
    A["chest"] = A["torso"] * _smooth(mid_z - 0.05 * s, mid_z + 0.05 * s, p[:, 2])
    A["belly"] = A["torso"] * (1.0 - _smooth(mid_z - 0.05 * s, mid_z + 0.05 * s, p[:, 2]))
    A["graft"] = skin.graft_area(ob, p)
    # never furred: the skin that has to stay skin, and the eyes
    w, _, _ = skin.regions(ob)
    bare = np.zeros(n)
    for k in SKIP_REGIONS:
        bare = np.maximum(bare, w[k])
    r_eye = 0.012 * s
    for side in (1.0, -1.0):
        c = np.array(j["joint-l-eye"], np.float64) * np.array([side * xs, 1.0, 1.0])
        bare = np.maximum(bare, 1.0 - _smooth(EYE_RADII * r_eye * 0.7, EYE_RADII * r_eye,
                                              np.linalg.norm(p - c, axis=1)))
    keep = 1.0 - np.clip(bare, 0, 1)
    for a in AREAS:
        raw = np.clip(A[a], 0, 1) * keep
        # smoothed for a soft rim, then held to where the area actually reached: diffusion alone carried the
        # face over the crown (a 3 mm nap drew a skull cap over the hair), and a region should feather at
        # its edge, not grow past it
        A[a] = np.clip(_delta().smooth(raw, faces, iterations=2, share=0.5)[:n], 0, 1) * (raw > 1e-3)
    # flows, each projected off the surface so the fur lies on the skin rather than into it
    def _tangential(v):
        v = np.asarray(v, np.float64)
        v = v - nrm * (v * nrm).sum(axis=1)[:, None]
        L = np.linalg.norm(v, axis=1)
        bad = L < 1e-6
        if bad.any():                      # straight down a horizontal face: fall back to backwards
            alt = np.array([0.0, 1.0, 0.0]) - nrm * (nrm @ np.array([0.0, 1.0, 0.0]))[:, None]
            v[bad] = alt[bad]
            L = np.linalg.norm(v, axis=1)
        return v / np.maximum(L, 1e-9)[:, None]

    flat = np.linalg.norm(along, axis=1) < 0.5
    along[flat] = np.array([0.0, 0.0, -1.0])
    flows = {"flow_down": _tangential(np.tile([0.0, 0.0, -1.0], (n, 1))),
             "flow_back": _tangential(np.tile([0.0, 1.0, 0.0], (n, 1))),
             "flow_out": _tangential(np.stack([np.sign(p[:, 0] + 1e-12), np.zeros(n), np.zeros(n)], axis=1)),
             "flow_along": _tangential(-along)}
    A, ctx = _grow_to_mesh(ob, A, flows, nrm, n, n_all, s, j)
    ctx["faces"] = faces
    return A, ctx, notes


def _mesh_normals(ob, n_all):
    """The mesh's own vertex normals, for the vertices hm08's landmark maths does not reach."""
    v = np.empty(n_all * 3, np.float32)
    try:
        ob.data.vertex_normals.foreach_get("vector", v)
    except (AttributeError, RuntimeError, ValueError):
        return np.tile(np.array([0.0, -1.0, 0.0]), (n_all, 1))
    v = v.reshape(n_all, 3).astype(np.float64)
    L = np.linalg.norm(v, axis=1)
    v[L < 1e-6] = np.array([0.0, -1.0, 0.0])
    return v / np.maximum(np.linalg.norm(v, axis=1), 1e-9)[:, None]


def _grow_to_mesh(ob, A, flows, nrm, n, n_all, s, j):
    """Widen the hm08-sized areas and flows to every vertex the body has, and fill in the areas that are
    not hm08 at all: `tail` (humanform.tail's vertex group) and the new half of `graft`."""
    from . import skin as skin_mod
    nrm_all = _mesh_normals(ob, n_all)
    if nrm is not None and n:
        nrm_all[:n] = nrm
    co_all = _delta().mixed_coords(ob)[:n_all]

    def grow(v, fill=0.0):
        out = np.full((n_all,) + np.shape(v)[1:], fill, np.float64)
        out[:n] = v
        return out
    tail_w = np.zeros(n_all)
    g = ob.vertex_groups.get(TAIL_GROUP)
    if g is not None:
        for v in ob.data.vertices:
            for e in v.groups:
                if e.group == g.index:
                    tail_w[v.index] = max(tail_w[v.index], min(1.0, float(e.weight)))
    out = {a: grow(A[a]) for a in AREAS}
    # a body is everything the body IS, whatever a plan added to it
    out["body"] = np.ones(n_all)
    out["tail"] = np.clip(tail_w, 0, 1)
    gv = skin_mod.graft_vertices(ob)
    if len(gv):
        out["graft"] = out["graft"].copy()
        out["graft"][np.asarray(gv, np.int64)] = 1.0

    def tangential(v):
        v = np.asarray(v, np.float64)
        v = v - nrm_all * (v * nrm_all).sum(axis=1)[:, None]
        L = np.linalg.norm(v, axis=1)
        bad = L < 1e-6
        if bad.any():
            alt = np.array([0.0, 1.0, 0.0]) - nrm_all * (nrm_all @ np.array([0.0, 1.0, 0.0]))[:, None]
            v[bad] = alt[bad]
        return v / np.maximum(np.linalg.norm(v, axis=1), 1e-9)[:, None]
    # past hm08 there are no limb axes to lie along, so every flow falls back to the one that is defined
    # everywhere: straight down the surface. A tail's brush lies down its own length, which IS down it.
    down = tangential(np.tile([0.0, 0.0, -1.0], (n_all, 1)))
    ctx = {"scale": s, "joints": j, "normals": nrm_all, "co": co_all,
           "faces": _delta().body_faces(ob), "body_verts": n}
    for k in ("flow_down", "flow_back", "flow_out", "flow_along"):
        ctx[k] = down.copy()
        if flows is not None and k in flows:
            ctx[k][:n] = flows[k]
    return out, ctx


# ------------------------------------------------------------------ the map on the body


def _linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(c):
    c = np.clip(np.asarray(c, np.float64), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def apply(ob, block, base_colour=None):
    """Write the coverage map on a body and the `humanform_fur` property. `base_colour` (screen sRGB) is
    what a region with no colour of its own takes. Returns a report; raises ValueError on a bad block."""
    import bpy
    ob = bpy.data.objects[ob] if isinstance(ob, str) else ob
    b = normalise(block)
    if b is None:
        return {"fur": None}
    A, ctx, notes = areas(ob)
    n = len(next(iter(A.values())))
    n_all = len(ob.data.vertices)
    den = np.zeros(n)
    default = _linear(base_colour if base_colour is not None else (0.35, 0.26, 0.18))
    per = []
    # Every region's own weight, then a weighted blend. The first cut took the densest region's values
    # outright, and a 45 mm ruff beside a 12 mm pelt then stood off the neck as a collar of separate
    # sheets: where the length steps, the shells splay, because nothing closes the side of the step.
    # Blending over each region's own feathered mask (raised to BLEND_SHARP, so a region's core keeps its
    # own length) makes the ruff taper into the pelt instead.
    ws = []
    for r in b["regions"]:
        m = np.zeros(n)
        for a in r["areas"]:
            m = np.maximum(m, A[a])
        for a in r["except_areas"]:
            m = m * (1.0 - A[a])
        # A region is judged against ITS OWN peak, not against 1. The landmark areas are smoothed fields
        # and several of them never reach 1 anywhere (`ruff` peaks near 0.55 on these bodies, and an
        # `except_areas` multiplies whatever is left down again), so read raw, such a region had no core
        # at all: the blend below gave the gnoll's 72 mm mane about an eighth of its own length and it came
        # out as 28 mm of pelt - no mane on the body at all, and the same for its paler chest (2026-09-22).
        # Normalising cannot GROW an area - a vertex the area never reached is still 0, and the round's own
        # rule holds - it only says where that area's inside is.
        peak = float(m.max()) if m.size else 0.0
        if peak > PEAK_FLOOR:
            m = m / peak
        # solid inside the region, feathered only at its rim. Taken raw, an area weight that peaks at 0.5
        # (a ruff is the overlap of a neck, the shoulders and the chest, each already smoothed) put half
        # the upper body in the band where the skin is still drawn under the fur, and the stochastic edge
        # showed there as a wide speckled sash across the chest.
        m = _smooth(RIM[0], RIM[1], np.clip(m, 0, 1)) * r["density"]
        den = np.maximum(den, m)
        ws.append(m)
        per.append({"name": r["name"], "vertices": int((m > MIN_DENSITY).sum()), "area_peak": round(peak, 3),
                    "length_m": r["length_m"], "density": r["density"], "flow": r["flow"]})
        if peak <= PEAK_FLOOR:
            notes.append(f"fur region {r['name']!r}: its areas {r['areas']} reach only {peak:.2f} on this "
                         f"body (floor {PEAK_FLOOR}), so it has no solid inside and its length and colour "
                         "are blended away into its neighbours - name a wider area, or drop an except_areas")
    # Two blends, because length and colour want opposite things. Length wants a region to keep its own
    # (BLEND_SHARP), or a 45 mm ruff averages into a 12 mm pelt and stops being a ruff. Colour wants the
    # gentlest blend there is: a ruff's tone against a pelt's stepped by 0.065 in luma across one edge of
    # the mesh where they met, which is a seam the eye reads as a line (`edge_tone`).
    def _norm(p_):
        W_ = np.stack([w ** p_ for w in ws])
        t_ = W_.sum(axis=0)
        k_ = t_ > 1e-9
        W_[:, k_] /= t_[k_]
        return W_, k_

    W, on = _norm(BLEND_SHARP)
    W_col, _ = _norm(BLEND_COLOUR)
    length = np.zeros(n)
    flow = np.zeros((n, 3))
    col = np.tile(default, (n, 1))
    pat = np.zeros(n)
    for i, r in enumerate(b["regions"]):
        w = W[i]
        # a cards region leaves only its root mat in the shell map: the shells are what hides the skin
        # under the cards, and drawing them at the card's own length would be the collar of sheets the
        # shell path is capped at 8 cm to avoid
        length += w * (CARD_MAT_M if r.get("cards") else r["length_m"])
        flow += w[:, None] * ctx["flow_" + r["flow"]]
        c = np.asarray(_linear(r["colour"]) if r.get("colour") is not None else default)
        col += W_col[i][:, None] * (c - default)   # the weights sum to 1 where any region reaches
        pat += w * (r["pattern"]["amount"] if r.get("pattern") else 0.0)
    L = np.linalg.norm(flow, axis=1)
    flow[L < 1e-6] = ctx["flow_down"][L < 1e-6]
    flow /= np.maximum(np.linalg.norm(flow, axis=1), 1e-9)[:, None]
    # The Laplacian runs over hm08's own face graph, so it only reaches hm08's own vertices; a tail or a
    # graft is smooth already (it is a loft) and is left as its area laid it.
    nb = int(ctx.get("body_verts") or min(n, _delta().BODY_VERTS))
    den[:nb] = np.clip(_delta().smooth(den[:nb], ctx["faces"], iterations=2, share=0.5)[:nb], 0, 1)
    length[:nb] = _delta().smooth(length[:nb], ctx["faces"], iterations=4, share=0.5)[:nb]
    den = np.clip(den, 0, 1)
    # Where the fur ends it must end into the skin, not against it. Drawn at full length and full colour up
    # to the last furred vertex, a pelt left a dark ring at every wrist and ankle and a dark band at the
    # hairline: a step in tone across a boundary, which `edge_tone` measures. So over the band where the
    # skin is still drawn under the fur, the fur shortens to nothing and its colour goes to the skin's. The
    # feather follows distance from bare skin (COVER_DENSITY), not density, and like the Laplacian it walks
    # hm08's faces: a tail or a graft has none of them, so it keeps its own length and colour.
    reach = np.ones(n)
    reach[:nb] = _rings(den[:nb] < COVER_DENSITY, ctx["faces"], EDGE_RINGS, nb)
    reach[:nb] = np.clip(_delta().smooth(reach[:nb], ctx["faces"], iterations=2, share=0.5)[:nb], 0, 1)
    col = default * (1.0 - reach[:, None]) + col * reach[:, None]
    length = length * (EDGE_LENGTH + (1.0 - EDGE_LENGTH) * reach)
    den[den < MIN_DENSITY] = 0.0
    length[den <= 0.0] = 0.0
    me = ob.data
    for name in (DEN, LEN, FLOW, COL, PAT, SKIN, VCOL):
        if name in me.attributes:
            me.attributes.remove(me.attributes[name])

    def _f(name, v):
        a = np.zeros(n_all, np.float32)
        a[:n] = v
        me.attributes.new(name, "FLOAT", "POINT").data.foreach_set("value", a)

    def _v(name, v):
        a = np.zeros((n_all, 3), np.float32)
        a[:n] = v
        me.attributes.new(name, "FLOAT_VECTOR", "POINT").data.foreach_set("vector", a.ravel())

    _f(DEN, den)
    _f(LEN, length)
    # Each cards region's own mask, kept per vertex so the growth can happen LATER - the cards are grown on
    # the baked body, where `areas` has no MPFB joints left to measure landmarks from. It is the field
    # `hair.cards` takes, unchanged.
    for name in [a.name for a in me.attributes if a.name.startswith(CARD_FIELD)]:
        me.attributes.remove(me.attributes[name])
    for i, r in enumerate(b["regions"]):
        if r.get("cards"):
            _f(CARD_FIELD + r["name"], np.clip(ws[i] / max(float(r["density"]), 1e-6), 0, 1))
    _f(PAT, pat)
    _vcol(ob, den, length, flow, n, n_all)
    # every vertex the body has NOW is skin; hair, brows and lashes are joined in after this
    me.attributes.new(SKIN, "FLOAT", "POINT").data.foreach_set("value", np.ones(n_all, np.float32))
    _v(FLOW, flow)
    _v(COL, col)
    spec = dict(b)
    # the skin the fur ends into, kept here because a species body's stored sheet has no skin: the tone is
    # drawn from the species palette and put on after the warp (`pipeline._make_species`)
    spec["skin_tone"] = [round(float(c), 4) for c in (base_colour if base_colour is not None
                                                      else (0.35, 0.26, 0.18))]
    spec["length_max_m"] = round(float(length.max()) if len(length) else 0.0, 5)
    spec["vertices"] = int((den > 0).sum())
    spec["covered_vertices"] = int((den >= COVER_DENSITY).sum())
    ob[PROP] = json.loads(json.dumps(spec))
    return {"fur": spec, "regions": per, "notes": notes,
            "density_mean": round(float(den[den > 0].mean()) if (den > 0).any() else 0.0, 3),
            "length_mm": {"max": round(float(length.max()) * 1000, 2),
                          "mean": round(float(length[den > 0].mean()) * 1000, 2) if (den > 0).any() else 0.0}}


def refresh_vcol(ob):
    """Write the `hf_fur` colour attribute again from the per-vertex map, over the body as it is now.

    It has to run after every stage that adds geometry, because **Blender's join fills a colour attribute's
    missing values with white**, not with zero: the hair cap, the brows and the lashes joined into the body
    after the map was laid down came out at density 1 and full length, and seventeen shells drew a black
    skull cap over the hair. `hf_fur_skin` marks what was the body when the map was written, and the FLOAT
    attributes beside it are filled with zero by the same join, so both say the same thing - fur belongs
    only where the skin was."""
    ob = _obj_of(ob)
    den, length, flow = _attr(ob, DEN), _attr(ob, LEN), _attr(ob, FLOW, 3)
    if den is None or length is None or flow is None:
        return None
    skin = _attr(ob, SKIN)
    if skin is not None:
        keep = skin > 0.5
        den = den * keep
        length = length * keep
    n_all = len(ob.data.vertices)
    if VCOL in ob.data.color_attributes:
        ob.data.color_attributes.remove(ob.data.color_attributes[VCOL])
    return _vcol(ob, den, length, flow, n_all, n_all)


def _obj_of(ob):
    import bpy
    return bpy.data.objects[ob] if isinstance(ob, str) else ob


def flow_frame(nrm):
    """(T, B) per vertex: an orthonormal frame on the surface that depends on the NORMAL alone.

    T is the body's own down projected onto the tangent plane (world +Y, the back, where the surface faces
    straight up or down), B is `normal x T`. The flow's angle is written against this frame and the shader
    rebuilds exactly it, so neither side needs the UVs.

    It used to be written against the mesh's UV TANGENT, the frame Godot builds TANGENT and BINORMAL on -
    and a tangent flips sign across a UV seam. hm08's atlas has a seam straight down the midline of the back
    of the head and the neck, so the shells either side of it sheared in OPPOSITE directions and opened a
    wedge: a bald, skin-coloured stripe from the crown to the middle of the back, in every Godot shot of the
    gnoll, while the coverage map measured a uniform 0.95 either side of it (2026-09-22). A normal is
    continuous across a UV seam; a tangent is not."""
    nrm = np.asarray(nrm, np.float64)
    down = np.tile(np.array([0.0, 0.0, -1.0]), (len(nrm), 1))          # Blender object space: z is up
    t = down - nrm * (down * nrm).sum(axis=1)[:, None]
    L = np.linalg.norm(t, axis=1)
    bad = L < 1e-6
    if bad.any():
        alt = np.array([0.0, 1.0, 0.0])                                 # the body's back
        t[bad] = (alt - nrm * (nrm @ alt)[:, None])[bad]
    t /= np.maximum(np.linalg.norm(t, axis=1), 1e-9)[:, None]
    return t, np.cross(nrm, t)


def _vcol(ob, den, length, flow, n, n_all):
    """The map Godot reads, as the `hf_fur` colour attribute (see VCOL). The flow is written in the frame
    `flow_frame` builds off the surface normal, which the shader rebuilds from NORMAL alone."""
    me = ob.data
    T, B = flow_frame(_mesh_normals(ob, n_all))
    lmax = max(float(length.max()) if len(length) else 0.0, 1e-6)
    cs = (flow * T[:n]).sum(axis=1)
    sn = (flow * B[:n]).sum(axis=1)
    L = np.hypot(cs, sn)
    cs, sn = cs / np.maximum(L, 1e-9), sn / np.maximum(L, 1e-9)
    v = np.zeros((n_all, 4), np.float32)
    v[:n, 0] = den
    v[:n, 1] = length / lmax
    v[:n, 2] = 0.5 + 0.5 * cs
    v[:n, 3] = 0.5 + 0.5 * sn
    a = me.color_attributes.new(VCOL, "FLOAT_COLOR", "POINT")
    a.data.foreach_set("color", v.ravel())
    # not made active: a beard's fade (`brows.BEARD_FADE`) is a colour attribute too, and its material
    # names the layer it wants. The exporter names this one as well (rig_analysis.export.VERTEX_COLOUR_MAPS)
    return lmax


def atlas_overlap(ob, px=512):
    """How much of the body's UV atlas two different triangles claim - the measure that sent fur's coverage
    map out of the atlas and into a vertex colour. hm08's own UV overlaps itself (23% of its texels here),
    so anything rasterised into it depends on the order the triangles are drawn in. Returns the share of
    covered texels whose value changes when the triangles are drawn in the opposite order."""
    den = _attr(ob, DEN)
    tri, uv, pos = _triangles(ob)
    sk = np.flatnonzero(skin_tris(ob, tri, uv))
    if not len(sk):
        return {"texels": 0, "share": 0.0}
    v = (den[tri[sk]] if den is not None else np.ones((len(sk), 3)))[:, :, None]
    a, ca = _rasterise(uv[sk], v, px)
    b, cb = _rasterise(uv[sk][::-1], v[::-1], px)
    both = ca & cb
    diff = (np.abs(a[..., 0] - b[..., 0]) > 0.25) & both
    return {"texels": int(both.sum()), "order_dependent": int(diff.sum()),
            "share": round(float(diff.sum() / max(both.sum(), 1)), 4),
            "note": "a map rasterised into this atlas would be wrong here; fur's is a vertex colour"}


def read(ob):
    """The fur block a body carries, or None."""
    import bpy
    ob = bpy.data.objects[ob] if isinstance(ob, str) else ob
    v = ob.get(PROP)
    if v is None:
        return None
    if hasattr(v, "to_dict"):
        v = v.to_dict()
    return json.loads(json.dumps(v, default=float))


def carried(ob):
    """True when the body has the coverage map on it (the attributes, not only the property)."""
    import bpy
    ob = bpy.data.objects[ob] if isinstance(ob, str) else ob
    return DEN in ob.data.attributes and read(ob) is not None


def _attr(ob, name, dim=1):
    a = ob.data.attributes.get(name)
    if a is None:
        return None
    n = len(ob.data.vertices)
    if dim == 1:
        v = np.empty(n, np.float32)
        a.data.foreach_get("value", v)
        return v.astype(np.float64)
    v = np.empty(n * 3, np.float32)
    a.data.foreach_get("vector", v)
    return v.reshape(n, 3).astype(np.float64)


# ------------------------------------------------------------------ the textures


def _triangles(ob):
    """(tri (T, 3) vertex indices, uv (T, 3, 2), pos (T, 3, 3)) over every face of the mesh, in the
    active UV layer. Every face, not only hm08's body quads: a graft's tail is furred too."""
    me = ob.data
    uvl = me.uv_layers.active
    if uvl is None:
        raise ValueError("fur: the body has no UV map to write its coverage map into")
    nl = len(me.loops)
    lv = np.empty(nl, np.int64)
    me.loops.foreach_get("vertex_index", lv)
    uv = np.empty(nl * 2, np.float32)
    uvl.data.foreach_get("uv", uv)
    uv = uv.reshape(nl, 2).astype(np.float64)
    lt = np.empty(len(me.polygons), np.int64)
    ls = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", lt)
    me.polygons.foreach_get("loop_start", ls)
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    tri_l = []
    for k in (3, 4):
        sel = lt == k
        if not sel.any():
            continue
        idx = ls[sel][:, None] + np.arange(k)[None, :]
        fans = [(0, 1, 2)] if k == 3 else [(0, 1, 2), (0, 2, 3)]
        for f in fans:
            tri_l.append(idx[:, list(f)])
    if not tri_l:
        raise ValueError("fur: the body has no triangles or quads")
    L = np.concatenate(tri_l)
    return lv[L], uv[L], co[lv[L]]


def in_atlas(uv, margin=1e-3):
    """Which triangles lie inside the UV unit square - the fallback test when a body has no `hf_fur_skin`."""
    return np.all((uv >= -margin) & (uv <= 1.0 + margin), axis=(1, 2))


def skin_tris(ob, tri, uv):
    """Which triangles are the body's own skin: every corner marked `hf_fur_skin` when the map was laid on
    it, before hair, brows and lashes were joined in. Without the mark (an older build), the UV square."""
    m = _attr(ob, SKIN)
    if m is None:
        return in_atlas(uv)
    return (m[tri] > 0.5).all(axis=1) & in_atlas(uv)


def _rasterise(uv, values, px, fill=0.0):
    """Barycentric rasterisation of per-corner `values` (T, 3, C) into a (px, px, C) image over the UV
    unit square, plus a coverage mask (see the two passes below). What neither pass reaches is filled by
    `_dilate`, so a bilinear sample just off an island's edge still reads fur."""
    T = len(uv)
    C = values.shape[2]
    img = np.full((px, px, C), fill, np.float64)
    cov = np.zeros((px, px), bool)
    P = uv * px
    lo = np.floor(P.min(axis=1)).astype(np.int64)
    hi = np.ceil(P.max(axis=1)).astype(np.int64)
    lo = np.clip(lo, 0, px - 1)
    hi = np.clip(hi, 1, px)
    # Two passes. First every texel whose centre a triangle covers, which decides ownership where islands
    # meet; then, only into texels still unwritten, a pass conservative by three quarters of a texel, which
    # is what gives a thin island (a finger, a toe) its texels instead of leaving them to `_dilate` and the
    # island packed beside it. The hands and feet came back furred without it.
    for conservative in (False, True):
        _pass(img, cov, P, values, lo, hi, T, conservative)
    return img, cov


def _pass(img, cov, P, values, lo, hi, T, conservative):
    for t in range(T):
        x0, y0 = lo[t]
        x1, y1 = hi[t]
        if x1 <= x0 or y1 <= y0:
            continue
        xs = np.arange(x0, x1) + 0.5
        ys = np.arange(y0, y1) + 0.5
        gx, gy = np.meshgrid(xs, ys)
        a, b, c = P[t]
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            continue
        w0 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / d
        w1 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / d
        w2 = 1.0 - w0 - w1
        # the conservative tolerance is a distance in texels turned into barycentric units, so a big
        # triangle gets a tiny one and cannot claim the atlas
        if conservative:
            ad = abs(d)
            m = ((w0 >= -CONSERVATIVE_PX * math.hypot(b[0] - c[0], b[1] - c[1]) / ad)
                 & (w1 >= -CONSERVATIVE_PX * math.hypot(c[0] - a[0], c[1] - a[1]) / ad)
                 & (w2 >= -CONSERVATIVE_PX * math.hypot(a[0] - b[0], a[1] - b[1]) / ad))
            m = m & ~cov[y0:y1, x0:x1]
        else:
            m = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not m.any():
            continue
        ww = np.stack([np.clip(w0, 0, 1), np.clip(w1, 0, 1), np.clip(w2, 0, 1)], axis=-1)
        ww = ww / np.maximum(ww.sum(axis=-1, keepdims=True), 1e-9)
        val = ww[..., None] * values[t][None, None, :, :]
        val = val.sum(axis=2)
        yy, xx = np.nonzero(m)
        img[y0 + yy, x0 + xx] = val[m]
        cov[y0 + yy, x0 + xx] = True


def _dilate(img, cov, passes=2):
    """Grow the covered texels outwards, so a bilinear sample just off an island edge reads fur, not black.
    Returns (image, the texels it now has), so a caller can fill the rest with something of its own."""
    out = img.copy()
    have = cov.copy()
    for _ in range(passes):
        if have.all():
            break
        acc = np.zeros_like(out)
        cnt = np.zeros(have.shape, np.float64)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            s = np.roll(np.roll(out, dy, 0), dx, 1)
            h = np.roll(np.roll(have, dy, 0), dx, 1)
            acc += s * h[..., None]
            cnt += h
        new = (~have) & (cnt > 0)
        out[new] = acc[new] / cnt[new][..., None]
        have |= new
    return out, have


def strand_mask(px=MASK_PX, tile_m=TILE_M, seed=0, density=STRANDS_PER_CM2, width_mm=STRAND_MM,
                clump_mm=CLUMP_MM):
    """The tiled strand mask, (px, px, 2): R the height up the fur (0..1) the strand at that texel reaches,
    0 for bare skin; G that strand's own tone, the same the whole way along it. It wraps in both
    directions, so the tile repeats without a seam. A shell at height t keeps the texels over t, so the
    strands taper by themselves and no two shells share an outline (which is what banding is).

    The strands are gathered into **clumps** `clump_mm` apart: each is drawn `CLUMP_PULL` of the way to its
    clump's centre, and `CLUMP_SHARE` of its length is its clump's. Real fur parts into clumps and each
    clump lies together; without that a shell stack reads as felt up close and as speckled dirt at 2 m."""
    rng = np.random.default_rng(seed + 104729)
    cm2 = (tile_m * 100.0) ** 2
    k = max(8, int(round(density * cm2)))
    nc = max(1, int(round(cm2 / (clump_mm * 0.1) ** 2)))
    clump_xy = rng.random((nc, 2))
    clump_h = rng.random(nc)
    clump_tone = rng.random(nc)
    seeds = rng.random((k, 2))
    mine = rng.integers(0, nc, k)
    # toward the clump's centre, by the shortest way round the wrap
    dxy = clump_xy[mine] - seeds
    dxy -= np.round(dxy)
    seeds = (seeds + CLUMP_PULL * dxy) % 1.0
    heights = 0.42 + 0.58 * (CLUMP_SHARE * clump_h[mine] + (1 - CLUMP_SHARE) * rng.random(k))
    tone = np.clip(0.5 + STRAND_TONE * (CLUMP_SHARE * (clump_tone[mine] - 0.5)
                                        + (1 - CLUMP_SHARE) * (rng.random(k) - 0.5)), 0.0, 1.0)
    r = (width_mm * 1e-3 / tile_m) * 0.5        # the strand's radius in tile units
    g = (np.arange(px) + 0.5) / px
    gx, gy = np.meshgrid(g, g)
    out = np.zeros((px, px, 2), np.float64)
    # wrap by testing the nine offsets: a strand near an edge reaches over it
    for ox in (-1.0, 0.0, 1.0):
        for oy in (-1.0, 0.0, 1.0):
            for (sx, sy), h, tn in zip(seeds, heights, tone):
                cx, cy = sx + ox, sy + oy
                if cx < -2 * r or cx > 1 + 2 * r or cy < -2 * r or cy > 1 + 2 * r:
                    continue
                x0 = max(0, int((cx - r) * px))
                x1 = min(px, int(math.ceil((cx + r) * px)) + 1)
                y0 = max(0, int((cy - r) * px))
                y1 = min(px, int(math.ceil((cy + r) * px)) + 1)
                if x1 <= x0 or y1 <= y0:
                    continue
                d = np.hypot(gx[y0:y1, x0:x1] - cx, gy[y0:y1, x0:x1] - cy) / max(r, 1e-9)
                # a round strand, its own height at the core and tapering to nothing at the rim: the
                # taper is what gives a soft edge instead of a disc
                v = h * np.clip(3.0 * (1.0 - d), 0.0, 1.0)
                win = out[y0:y1, x0:x1]
                take = v > win[..., 0]
                win[..., 0] = np.where(take, v, win[..., 0])
                win[..., 1] = np.where(take, tn, win[..., 1])   # the tone follows the strand, not the texel
    out[..., 1] = np.where(out[..., 0] > 0, out[..., 1], 0.5)
    return out


def _pattern(pos, pat, seed):
    """0..1 per point: where a region's second colour shows. `pos` (N, 3) in metres."""
    kind, scale, amount = pat["kind"], max(pat["scale"], 1e-4), pat["amount"]
    rng = np.random.default_rng(seed + 7907)
    off = rng.random(3) * 100.0
    q = pos / scale + off
    if kind == "stripes":
        v = 0.5 + 0.5 * np.sin(2 * math.pi * q[:, 2] + 2.0 * np.sin(2 * math.pi * 0.21 * q[:, 1]))
        m = _smooth(0.45, 0.62, v)
    elif kind == "spots":
        cell = np.floor(q)
        f = q - cell
        h = _hash3(cell + off)
        d = np.linalg.norm(f - (0.25 + 0.5 * h), axis=1)
        m = 1.0 - _smooth(0.22, 0.34, d)
    elif kind == "blotches":
        m = _smooth(0.48, 0.70, _fbm(q, 3))
    else:                                        # mottle
        m = _smooth(0.35, 0.75, _fbm(q * 2.2, 2))
    return np.clip(m * amount, 0, 1)


def _hash3(v):
    x = np.sin(v @ np.array([127.1, 311.7, 74.7])) * 43758.5453
    y = np.sin(v @ np.array([269.5, 183.3, 246.1])) * 43758.5453
    z = np.sin(v @ np.array([113.5, 271.9, 124.6])) * 43758.5453
    return np.stack([x - np.floor(x), y - np.floor(y), z - np.floor(z)], axis=1)


def _fbm(q, octaves):
    v = np.zeros(len(q))
    amp, f = 0.5, 1.0
    for _ in range(octaves):
        s = np.sin(q[:, 0] * f * 1.7 + 1.3) * np.sin(q[:, 1] * f * 1.1 + 2.7) * np.sin(q[:, 2] * f * 1.9 + 0.7)
        v += amp * (0.5 + 0.5 * s)
        amp *= 0.5
        f *= 2.03
    return v / (1.0 - 0.5 ** octaves) * 0.5


def _tangent_frames(tri, uv, pos, n_verts):
    """Per-vertex (T, B) from the mesh's UVs, the frame Godot's TANGENT/BINORMAL is built on, so an angle
    written here is the angle the shader reads."""
    e1 = pos[:, 1] - pos[:, 0]
    e2 = pos[:, 2] - pos[:, 0]
    d1 = uv[:, 1] - uv[:, 0]
    d2 = uv[:, 2] - uv[:, 0]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    ok = np.abs(det) > 1e-12
    r = np.zeros(len(tri))
    r[ok] = 1.0 / det[ok]
    T = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r[:, None]
    B = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r[:, None]
    accT = np.zeros((n_verts, 3))
    accB = np.zeros((n_verts, 3))
    for k in range(3):
        np.add.at(accT, tri[:, k], T)
        np.add.at(accB, tri[:, k], B)
    accT /= np.maximum(np.linalg.norm(accT, axis=1), 1e-12)[:, None]
    accB /= np.maximum(np.linalg.norm(accB, axis=1), 1e-12)[:, None]
    return accT, accB


def maps(ob, size=MAP_PX):
    """((px, px, 3) sRGB colour map, report): the fur's own colour in the body's UV layout, each region's
    pattern mixed in per texel (a per-vertex pattern would be as coarse as the mesh, and hm08's quads are
    8-15 mm - bigger than a spot).

    Colour is the one part of the map that can live in hm08's overlapping atlas (`atlas_overlap`): where
    two parts of the body claim a texel the furred one is drawn last and wins, and the worst a contested
    texel can do is tint fur slightly wrong - never open a hole, which is what the overlap did to density."""
    spec = read(ob)
    if spec is None:
        raise ValueError("fur.maps: the body carries no fur (call fur.apply first)")
    den = _attr(ob, DEN)
    col = _attr(ob, COL, 3)
    pat = _attr(ob, PAT)
    if den is None or col is None:
        raise ValueError("fur.maps: the body has no hf_fur_den attribute (call fur.apply first)")
    tri, uv, pos = _triangles(ob)
    sk = np.flatnonzero(skin_tris(ob, tri, uv))
    colour = col.copy()
    for r in spec["regions"]:
        if not r.get("pattern"):
            continue
        m = _pattern(pos.reshape(-1, 3), r["pattern"], spec.get("seed", 0)).reshape(len(tri), 3)
        want = _linear(r["pattern_colour"])
        amt = (pat[tri] > 0.5 * r["pattern"]["amount"]) * m
        for k in range(3):
            colour[tri[:, k]] = colour[tri[:, k]] * (1 - amt[:, k, None]) + want * amt[:, k, None]
    # furred triangles last, so a contested texel carries the fur's colour and not the bare skin's
    order = sk[np.argsort(den[tri[sk]].min(axis=1), kind="stable")]
    # Filled with the body's own skin tone, not with black, and grown far enough that a mip cannot reach
    # past it. Left black and dilated two texels, the unwritten space around the small islands - the hands,
    # the wrists, the feet - was pulled into the coat by the mips at 2 m and drew black gloves and socks.
    skin_lin = _linear(spec.get("skin_tone") or (0.35, 0.26, 0.18))
    col_img, cov = _rasterise(uv[order], colour[tri[order]], size, fill=0.0)
    # Both halves of the same question. DILATION keeps a bilinear sample just off an island edge honest; the
    # MIP CHAIN is the other half, because Godot picks a coarse mip at a few metres and each level averages
    # an island with the gap beside it. With the gap at zero the gnoll's chest, forearms, hands and one foot
    # came out SOLID BLACK at 4 m while the same fur was tawny at 0.6 m (2026-09-22). So the space between
    # the islands takes the coat's own mean - never black, and never the skin either, which is a different
    # tone again - and every level of the chain then lies between the coat's own colours: the worst a mip
    # can do is flatten the pattern, which is what distance should do anyway.
    mean = col_img[cov].mean(axis=0) if cov.any() else np.asarray(skin_lin, float)
    col_img[~cov] = mean
    col_img, filled = _dilate(col_img, cov, passes=DILATE_PASSES)
    col_img[~filled] = mean
    rep = {"size": size, "covered_texels": int(cov.sum()), "texels": size * size,
           "background": [round(float(c), 4) for c in mean],
           "skin_triangles": int(len(sk)), "triangles": int(len(tri)),
           "length_max_m": round(float(spec.get("length_max_m") or 0.0), 5)}
    return np.clip(_srgb(col_img), 0, 1), rep


# ------------------------------------------------------------------ the checks


def uv_scale(ob):
    """(scale, metres per UV unit): how far the strand mask is tiled so a tile is `tile_m` on the skin.
    The median over the body's triangles, so one number serves the whole atlas; how square that leaves a
    texel is what `mip_check` measures."""
    spec = read(ob) or {}
    tile = float(spec.get("tile_m") or TILE_M)
    tri, uv, pos = _triangles(ob)
    den = _attr(ob, DEN)
    on = skin_tris(ob, tri, uv) & ((den[tri] > MIN_DENSITY).all(axis=1) if den is not None else True)
    if not np.any(on):
        on = skin_tris(ob, tri, uv)
    a_uv = 0.5 * np.abs(np.cross(uv[on, 1] - uv[on, 0], uv[on, 2] - uv[on, 0]))
    a_m = 0.5 * np.linalg.norm(np.cross(pos[on, 1] - pos[on, 0], pos[on, 2] - pos[on, 0]), axis=1)
    ok = (a_uv > 1e-12) & (a_m > 1e-12)
    m_per_uv = float(np.sqrt(np.median(a_m[ok] / a_uv[ok])))
    return round(m_per_uv / tile, 4), round(m_per_uv, 4)


def mip_check(ob, mask=None, heights=(0.25, 0.5, 0.75), **kw):
    """How the fur mask samples in Godot, through `hairtex.mip_check`: the body's furred triangles, their UVs
    tiled by `uv_scale`, and the mask thresholded at each shell height (a shell keeps the texels over its
    height, so that *is* its alpha). The worst height is the report.

    **What it fails on, and what it deliberately does not.** hairtex's patch test asks whether a hole that
    survives into the mip Godot picks cuts a square patch of *skin* out - the beard's failure - and its own
    remedy is "give the interior an opaque under-layer (alpha over the cutoff between the strands)". Shell
    fur has one by construction: the base coat is shell 0 at height 0, drawn with alpha forced to 1 wherever
    the density map is over `MIN_DENSITY`, in the fur's own colour. A hole in any strand shell therefore
    shows the shell under it, down to that coat - never skin and never the background, except on the outline,
    which is `silhouette_check`'s job. So the patchy shares are reported as free numbers and are not a
    failure here. What remains, and is a failure:
      - **anisotropy** (hairtex's own): texels coarser across the strands than along them, so Godot picks the
        mip by V and blurs the strands and their gaps into blocks. Fur has no excuse for it - the mask is
        tiled square on the skin - so a failure means the body's UVs are stretched where the fur sits.
      - **a strand narrower than a screen pixel at the close distance** (STRAND_PX_MIN): then even up close
        no hair is ever resolved and the whole shell stack is an expensive flat wash. Widen the strand or
        shrink the tile."""
    from . import hairtex
    spec = read(ob) or {}
    tile = float(spec.get("tile_m") or TILE_M)
    if mask is None:
        mask = strand_mask(MASK_PX, tile, int(spec.get("seed", 0)))
    den = _attr(ob, DEN)
    tri, uv, pos = _triangles(ob)
    on = skin_tris(ob, tri, uv) & (den[tri] > MIN_DENSITY).all(axis=1)
    if not on.any():
        return {"ok": False, "problems": ["fur.mip_check: no furred triangle on the body"]}
    scale, m_per_uv = uv_scale(ob)
    P = pos[on]
    UV = uv[on] * scale
    kw.setdefault("max_patchy", 1.0)             # see the docstring: the base coat is the opaque under-layer
    worst = None
    hm = mask[..., 0] if mask.ndim == 3 else mask
    for t in heights:
        alpha = (hm >= t).astype(np.float64)
        if alpha.mean() < 1e-4:
            continue
        rep = hairtex.mip_check(P=P, UV=UV, A=None, alpha=alpha, cutoff=0.5, **kw)
        rep["height"] = t
        rep["coverage"] = round(float(alpha.mean()), 3)
        if worst is None or rep["views"][f"{min(hairtex.DISTANCES_M):g}m"]["patchy_share"] >                 worst["views"][f"{min(hairtex.DISTANCES_M):g}m"]["patchy_share"]:
            worst = rep
    if worst is None:
        return {"ok": False, "problems": ["fur.mip_check: the strand mask is empty at every shell height"]}
    near = min(kw.get("distances_m") or hairtex.DISTANCES_M)
    mm_per_px = near * 2.0 * math.tan(math.radians(hairtex.VFOV_DEG) / 2.0) / hairtex.IMAGE_PX * 1000
    strand_px = STRAND_MM / mm_per_px
    worst["strand_px_near"] = round(float(strand_px), 2)
    worst["base_coat"] = "shell 0, opaque where density > MIN_DENSITY: no hole ever shows skin"
    if strand_px < STRAND_PX_MIN:
        worst["problems"] = list(worst["problems"]) + [
            f"a strand is {strand_px:.2f} screen px across at {near:g} m, under {STRAND_PX_MIN}: no hair is ever "
            f"resolved and the shells are an expensive flat wash - widen fur.STRAND_MM past "
            f"{STRAND_PX_MIN * mm_per_px:.2f} mm, or shrink tile_m (it is {tile * 1000:.0f} mm)"]
    worst["ok"] = not worst["problems"]
    worst["uv_scale"] = scale
    worst["m_per_uv"] = m_per_uv
    worst["tile_m"] = tile
    return worst


def silhouette_check(ob, distances_m=SIL_DISTANCES_M, vfov_deg=None, image_px=None):
    """Does the fur read on the outline? At each distance, the fur's length and the gap between two
    shells, in screen pixels, over the vertices that fall on the silhouette (their normal across the
    view). Fur under `SIL_MIN_PX` at 4 m is a fuzz nobody sees; shells over `SIL_BAND_PX` apart draw as
    stacked sheets, which is banding; fur over `SIL_MAX_PX` at 0.6 m is hair and wants strand cards."""
    from . import hairtex
    vfov_deg = hairtex.VFOV_DEG if vfov_deg is None else vfov_deg
    image_px = hairtex.IMAGE_PX if image_px is None else image_px
    spec = read(ob) or {}
    den = _attr(ob, DEN)
    length = _attr(ob, LEN)
    if den is None:
        return {"ok": False, "problems": ["fur.silhouette_check: the body carries no fur map"]}
    n = min(len(den), _delta().BODY_VERTS)
    co = _delta().mixed_coords(ob)
    faces = _delta().body_faces(ob)
    nrm = _delta().vertex_normals(co, faces)[:n]
    d, L = den[:n], length[:n]
    shells = int(spec.get("shells") or SHELLS_DEFAULT)
    out = {"shells": shells, "views": {}}
    problems = []
    # the silhouette: vertices whose normal lies across the view, over the two horizontal views a demo
    # actually shows (from the front and from the side)
    sil = np.zeros(n, bool)
    for view in (np.array([0.0, -1.0, 0.0]), np.array([1.0, 0.0, 0.0])):
        sil |= (np.abs(nrm @ view) < 0.25) & (d > MIN_DENSITY)
    if not sil.any():
        return {"ok": False, "problems": ["fur.silhouette_check: no furred vertex on the silhouette"]}
    Ls = L[sil]
    near, far = min(distances_m), max(distances_m)
    for dist in distances_m:
        f = dist * 2.0 * math.tan(math.radians(vfov_deg) / 2.0) / image_px      # metres per screen pixel
        px = Ls / f
        gap = px / shells
        fur_p90 = float(np.quantile(px, 0.9))
        # banding shows where the fur is longest (the ruff), which a percentile over the whole body hides
        gap_max = float(px.max()) / shells
        out["views"][f"{dist:g}m"] = {"mm_per_px": round(f * 1000, 3),
                                      "fur_px_median": round(float(np.median(px)), 2),
                                      "fur_px_p90": round(fur_p90, 2),
                                      "fur_px_max": round(float(px.max()), 2),
                                      "shell_gap_px_max": round(gap_max, 3)}
        if dist == far and fur_p90 < SIL_MIN_PX:
            problems.append(f"at {dist:g} m the fur is {fur_p90:.2f} screen px long on the outline (90th "
                            f"percentile), under {SIL_MIN_PX}: it reads as a fuzz on the edge, not as fur - "
                            f"lengthen it past {SIL_MIN_PX * f * 1000:.1f} mm, or drop the fur and tint the skin "
                            "(the shells cost their draw calls for nothing)")
        limit = SIL_NEAR_BAND_PX if dist == near else SIL_BAND_PX
        if gap_max > limit:
            need = min(SHELLS[1], int(math.ceil(float(px.max()) / limit)))
            more = (f"{need} shells or more" if need > shells else "shorter fur")
            problems.append(f"at {dist:g} m two shells are {gap_max:.2f} screen px apart where the fur is "
                            f"longest on the outline, over {limit}: there a gap has the background behind it, so "
                            f"the layers comb - {more} (it has {shells}, up to {SHELLS[1]})")
    out["silhouette_vertices"] = int(sil.sum())
    out["ok"] = not problems
    out["problems"] = problems
    return out


EDGE_TOL = 0.04                # sRGB luma: the biggest step in the fur's tone across one edge of the mesh
DILATE_PASSES = 16             # how far a map is grown past its islands, so a mip cannot sample past it
DARK_TOL = 0.05                # sRGB luma a patch of coat may sit below the coat's own mean
DARK_SHARE = 0.01              # ... over this share of the furred area, it is a patch and not a shading
FLOW_TOL_DEG = 2.0             # how far a decoded flow may sit from the one that was written
EDGE_RINGS = 5                 # how far from the edge of the fur its colour and length are feathered


def edge_tone(ob, tone=None):
    """The step in the fur's tone across the mesh's own edges, near where the fur ends - `skin.seam_tone`'s
    question asked of a fur boundary instead of a graft's seam. A wrist, an ankle and a hairline are all the
    same boundary: fur on one side, skin on the other, and the eye reads a step in tone there as a dark ring
    however good the fur is.

    Measured locally, between neighbouring vertices, not by binning the whole body: binned, the bands mix
    regions - a face nap at density 0.7 with its own paler colour sat in the middle band and read as a step
    that was not there. hm08's vertices are 8-15 mm apart, so a colour that changes over a few centimetres
    passes and a ring does not. Returns free numbers plus a `fail` sentence, never an exception."""
    import json as _json
    den, col = _attr(ob, DEN), _attr(ob, COL, 3)
    if den is None or col is None:
        return {"fail": "edge_tone: the body carries no fur map"}
    if tone is None:
        tone = (read(ob) or {}).get("skin_tone")
    if tone is None:
        sheet = ob.get("humanform_sheet")
        if sheet:
            try:
                tone = (_json.loads(sheet) if isinstance(sheet, str) else dict(sheet)).get("skin")
            except Exception:
                tone = None
    d = _delta()
    n = min(len(den), d.BODY_VERTS)
    faces = d.body_faces(ob)
    r, c = d.neighbours(faces)
    # the skin's own colour stands in for a bare vertex, so the last step - fur to skin - is measured too
    lin = col[:n].copy()
    bare = den[:n] < MIN_DENSITY
    if tone is not None:
        lin[bare] = _linear(tone)
    luma = _srgb(np.clip(lin, 0, 1)) @ np.array([0.2126, 0.7152, 0.0722])
    near = bare.copy()
    for _ in range(EDGE_RINGS):
        grown = near.copy()
        grown[r[near[c]]] = True
        near = grown
    keep = (r < n) & (c < n)
    r, c = r[keep], c[keep]
    at_edge = near[r] & near[c] & ~(bare[r] & bare[c])
    if not at_edge.any():
        return {"edges": 0, "step": 0.0, "tol": EDGE_TOL, "note": "no fur boundary on this body"}
    step = np.abs(luma[r[at_edge]] - luma[c[at_edge]])
    out = {"edges": int(at_edge.sum()), "tol": EDGE_TOL,
           "step": round(float(np.quantile(step, 0.99)), 4),
           "step_max": round(float(step.max()), 4),
           "step_median": round(float(np.median(step)), 4),
           "skin": round(float(_luma_srgb(_linear(tone))), 4) if tone is not None else None}
    if out["step"] > EDGE_TOL:
        i = int(np.argmax(step))
        out["fail"] = (f"the fur's tone steps by {out['step']:.3f} across one edge of the mesh where the fur "
                       f"ends (99th percentile of {out['edges']} edges, worst {out['step_max']:.3f}), over "
                       f"{EDGE_TOL}: that draws as a dark ring at a wrist, an ankle or a hairline - feather "
                       "the colour into the skin's over the band where the skin is still drawn "
                       "(fur.EDGE_LENGTH and the `edge` blend in fur.apply)")
    return out


def dark_patches(ob, col_img, distances_m=SIL_DISTANCES_M):
    """Any patch of furred body markedly darker than the surface it sits on - the failure a tone *step*
    across the fur's edge does not catch. It measures the colour map as Godot samples it, **through its mips**:
    a small UV island surrounded by unwritten space reads its own colour at mip 0 and whatever is beyond it
    a few levels up, and that is how the hands, the wrists and the feet came out as black gloves and socks
    at 2 m while every per-texel measure said the map was right. Returns free numbers and a `fail`."""
    from . import hairtex
    den = _attr(ob, DEN)
    tri, uv, pos = _triangles(ob)
    sk = skin_tris(ob, tri, uv)
    furred = sk & (den[tri].mean(axis=1) > 0.3)
    if not furred.any():
        return {"area_m2": 0.0, "share": 0.0, "tol": DARK_TOL}
    px = col_img.shape[0]
    lum = np.asarray(col_img, float) @ np.array([0.2126, 0.7152, 0.0722])     # the map is already sRGB
    levels = [lum]
    while levels[-1].shape[0] > 1:
        a = levels[-1]
        n = a.shape[0] // 2
        levels.append(a[:2 * n:2, :2 * n:2] * 0.25 + a[1:2 * n:2, :2 * n:2] * 0.25
                      + a[:2 * n:2, 1:2 * n:2] * 0.25 + a[1:2 * n:2, 1:2 * n:2] * 0.25)
    mid = uv[furred].mean(axis=1)
    # the surface's own colour: mip 0 averaged over the triangle (four points), which carries the pattern.
    # Compared against a *global* coat mean instead, the spots a pattern is meant to draw fail the check.
    ref_uv = [mid] + [mid * 0.4 + uv[furred][:, k] * 0.6 for k in range(3)]
    ref = np.zeros(len(mid))
    for q in ref_uv:
        u = np.clip((q * px).astype(np.int64), 0, px - 1)
        ref += lum[u[:, 1], u[:, 0]] / len(ref_uv)
    P = pos[furred]
    area = 0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1)
    s_u, s_v, _ = hairtex.texel_sizes(P, uv[furred], px, px)
    tot = max(float(area.sum()), 1e-12)
    out = {"tol": DARK_TOL, "share_limit": DARK_SHARE, "views": {}}
    worst, worst_d = 0.0, None
    for dist in distances_m:
        f = dist * 2.0 * math.tan(math.radians(hairtex.VFOV_DEG) / 2.0) / hairtex.IMAGE_PX
        L = np.clip(np.round(np.log2(np.maximum(f / np.maximum(np.minimum(s_u, s_v), 1e-12), 1e-9))),
                    0, len(levels) - 1).astype(int)
        got = np.empty(len(mid))
        for li in np.unique(L):
            a = levels[li]
            m = L == li
            u = np.clip((mid[m] * a.shape[0]).astype(np.int64), 0, a.shape[0] - 1)
            got[m] = a[u[:, 1], u[:, 0]]
        mean = float((got * area).sum() / tot)
        dark = got < ref - DARK_TOL
        share = float(area[dark].sum() / tot)
        out["views"][f"{dist:g}m"] = {"mip_median": int(np.median(L)), "coat_luma": round(mean, 4),
                                      "dark_share": round(share, 4),
                                      "darkest": round(float(got.min()), 4),
                                      "worst_drop": round(float((ref - got).max()), 4)}
        if share > worst:
            worst, worst_d = share, (dist, mean, got, dark, area)
    out["share"] = round(worst, 4)
    if worst > DARK_SHARE:
        dist, mean, got, dark, area = worst_d
        z = pos[furred][dark].mean(axis=1)[:, 2]
        out["fail"] = (f"at {dist:g} m, {worst:.1%} of the furred body draws more than {DARK_TOL} in luma "
                       f"below its own surface colour (the coat's mean is {mean:.3f}, the darkest patch "
                       f"{float(got[dark].min()):.3f}, between z {float(z.min()):.2f} and "
                       f"{float(z.max()):.2f} m): that reads as a dark patch - a black glove, a sock, a "
                       "band - and a pattern's own spots do not, because the surface colour it is measured "
                       "against carries them. The usual cause is the colour map's unwritten space being "
                       "pulled in by a mip; grow it further (fur.DILATE_PASSES) and fill it with the skin's "
                       "tone, not with black")
    return out


def _luma_srgb(lin):
    lin = np.asarray(lin, float)
    return float(_srgb(np.array([float(lin[0]), float(lin[1]), float(lin[2])])) @ [0.2126, 0.7152, 0.0722])


def card_fields(ob):
    """[{name, field, length_m, colour, flow, density}] for every region the block marked `cards = true`.

    `field` is one 0..1 weight per vertex of this body - exactly what `hair.cards` takes - and `flow` the
    unit direction per vertex the shells lie along, which is the direction the cards should set off in.
    Empty on a body with no fur or no cards region. The fields were written by `apply` before the bake,
    because that is the only time `areas` can measure hm08's landmarks; growing them is a later job, after
    the body is baked and its rig is final.
    """
    spec = read(ob) or {}
    out = []
    for r in spec.get("regions", []):
        if not r.get("cards"):
            continue
        field = _attr(ob, CARD_FIELD + r["name"])
        if field is None:
            continue
        skin = _attr(ob, SKIN)
        if skin is not None:
            field = field * (skin > 0.5)      # never on hair, brows or lashes joined in after the map
        out.append({"name": r["name"], "field": np.clip(field, 0, 1), "length_m": float(r["length_m"]),
                    "colour": tuple(r.get("colour") or (0.3, 0.22, 0.14)), "density": float(r["density"]),
                    "flow": _attr(ob, FLOW, 3)})
    return out


def covered(ob):
    """The body vertex indices under fur dense enough to hide the skin (`COVER_DENSITY`), the way
    wardrobe lists the skin a garment covers. Empty when the block turns cover off."""
    spec = read(ob) or {}
    if not spec.get("cover", True):
        return np.zeros(0, np.int64)
    den = _attr(ob, DEN)
    if den is None:
        return np.zeros(0, np.int64)
    return np.flatnonzero(den >= COVER_DENSITY)


def gltf_positions(ob, indices):
    """Those vertices' positions in the glTF mesh space (Y up: x, z, -y), float32 little-endian, base64 -
    the form wardrobe's runtime matches against the imported mesh, and fur's does too, because Godot's
    importer reorders vertices and splits them at UV seams."""
    import base64
    import struct
    me = ob.data
    buf = bytearray()
    for i in indices:
        co = me.vertices[int(i)].co
        buf += struct.pack("<fff", co.x, co.z, -co.y)
    return base64.b64encode(bytes(buf)).decode("ascii")


# ------------------------------------------------------------------ the whole pass


def _png(path, arr, greyscale=False):
    """Write a (H, W, C) float 0..1 array as an 8-bit PNG, row 0 at the top (what Godot samples with
    UV.y down), through Blender's image writer so nothing else is needed."""
    import bpy
    h, w = arr.shape[:2]
    if greyscale:
        rgba = np.stack([arr, arr, arr, np.ones_like(arr)], axis=-1)
    elif arr.shape[2] == 3:
        rgba = np.concatenate([arr, np.ones((h, w, 1))], axis=2)
    else:
        rgba = arr
    name = os.path.basename(path)
    img = bpy.data.images.get(name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, width=w, height=h, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    # Blender's pixel buffer runs bottom-up; the PNG we want has row 0 at the top
    img.pixels.foreach_set(np.ascontiguousarray(rgba[::-1], np.float32).ravel())
    img.file_format = "PNG"
    img.filepath_raw = path
    img.save()
    img.pack()
    return img


def bake(ob, out_dir, base=None, size=MAP_PX, mask_px=MASK_PX, checks=True):
    """The whole fur pass on a baked body: the three PNGs into `out_dir`, the checks, the covered skin,
    and the finished `humanform_fur` property the glb carries as node extras. Returns a report; a failed
    check is `report["fail"]` (a sentence), never an exception - the caller decides."""
    import bpy
    ob = bpy.data.objects[ob] if isinstance(ob, str) else ob
    spec = read(ob)
    if spec is None:
        return {"fur": None}
    base = base or (ob.name[:-5] if ob.name.endswith("_body") else ob.name)
    os.makedirs(out_dir, exist_ok=True)
    lmax = refresh_vcol(ob)          # see refresh_vcol: a join fills a colour attribute with white
    if lmax is not None:
        spec = dict(spec)
        spec["length_max_m"] = round(float(lmax), 5)
        ob[PROP] = json.loads(json.dumps(spec))
    col_img, m_rep = maps(ob, size=size)
    mask = strand_mask(mask_px, float(spec.get("tile_m") or TILE_M), int(spec.get("seed", 0)))
    names = {"colour": f"{base}_fur_colour.png", "strands": f"{base}_fur_strands.png"}
    _png(os.path.join(out_dir, names["colour"]), col_img)
    _png(os.path.join(out_dir, names["strands"]),
         np.stack([mask[..., 0], mask[..., 1], np.zeros_like(mask[..., 0])], axis=-1))
    scale, m_per_uv = uv_scale(ob)
    idx = covered(ob)
    spec = dict(spec)
    spec["textures"] = names
    spec["uv_scale"] = scale
    spec["m_per_uv"] = m_per_uv
    spec["length_max_m"] = m_rep["length_max_m"]
    spec["heights"] = [round(t, 5) for t in shell_heights(int(spec.get("shells") or SHELLS_DEFAULT))]
    spec["min_density"] = MIN_DENSITY
    spec["cover_density"] = COVER_DENSITY
    spec["hide"] = {"space": "gltf_mesh", "count": int(len(idx)),
                    "positions_f32": gltf_positions(ob, idx), "tolerance_m": 0.0005}
    rep = {"fur": spec, "maps": m_rep, "textures": names,
           "mask": {"px": mask_px, "tile_m": spec.get("tile_m", TILE_M),
                    "strand_mm": STRAND_MM, "clump_mm": CLUMP_MM,
                    "coverage_at_half": round(float((mask[..., 0] >= 0.5).mean()), 3),
                    "coverage_at_root": round(float((mask[..., 0] > 0).mean()), 3)},
           "covered": int(len(idx))}
    if checks:
        rep["atlas"] = atlas_overlap(ob)
        rep["mip"] = mip_check(ob, mask=mask)
        rep["silhouette"] = silhouette_check(ob)
        rep["edge"] = edge_tone(ob)
        rep["dark"] = dark_patches(ob, col_img)
        rep["flow"] = flow_roundtrip(ob)
        bad = (list(rep["mip"].get("problems") or []) + list(rep["silhouette"].get("problems") or [])
               + ([rep["edge"]["fail"]] if rep["edge"].get("fail") else [])
               + ([rep["dark"]["fail"]] if rep["dark"].get("fail") else [])
               + ([rep["flow"]["fail"]] if rep["flow"].get("fail") else []))
        if bad:
            rep["fail"] = "; ".join(([rep["fail"]] if rep.get("fail") else []) + bad)
    ob[PROP] = json.loads(json.dumps(spec))
    return rep


def flow_roundtrip(ob):
    """Decode the flow back out of the colour attribute the way the SHADER will, and compare it with the
    direction humanform meant. {worst_deg, p99_deg, vertices, ok, fail}.

    The flow travels as an angle, which means it travels in a FRAME, and the writer and the shader have to
    agree on that frame down to its sign. They did not: humanform wrote against the mesh's UV tangent and
    the shader read TANGENT/BINORMAL, which flip across a UV seam - hm08 has one down the midline of the
    back of the head and neck - so the shells either side sheared apart and opened a bald stripe there. The
    map itself measured perfectly uniform across it, which is why nothing caught it; this decodes instead.
    A frame that disagrees shows up here as a large angle at the vertices along the seam."""
    den, flow = _attr(ob, DEN), _attr(ob, FLOW, 3)
    if den is None or flow is None or VCOL not in ob.data.color_attributes:
        return {"ok": True, "skipped": "no fur map"}
    n_all = len(ob.data.vertices)
    v = np.zeros(n_all * 4, np.float32)
    ob.data.color_attributes[VCOL].data.foreach_get("color", v)
    v = v.reshape(n_all, 4)
    T, B = flow_frame(_mesh_normals(ob, n_all))
    cs, sn = v[:, 2] * 2.0 - 1.0, v[:, 3] * 2.0 - 1.0
    L = np.hypot(cs, sn)
    got = (T * (cs / np.maximum(L, 1e-9))[:, None] + B * (sn / np.maximum(L, 1e-9))[:, None])
    # the stored flow laid back into THIS frame's plane: the map was written before the bake and the
    # normals have moved a little since, and that tilt is not what this check is about - the frame's
    # agreement is, so both sides are compared in the plane the shader will shear in
    want = T * (flow * T).sum(axis=1)[:, None] + B * (flow * B).sum(axis=1)[:, None]
    want = want / np.maximum(np.linalg.norm(want, axis=1), 1e-9)[:, None]
    on = (den > MIN_DENSITY) & (np.linalg.norm(flow, axis=1) > 1e-6) & (L > 1e-3)
    if not on.any():
        return {"ok": True, "skipped": "no furred vertex carries a flow"}
    ang = np.degrees(np.arccos(np.clip((got[on] * want[on]).sum(axis=1), -1.0, 1.0)))
    rep = {"vertices": int(on.sum()), "worst_deg": round(float(ang.max()), 2),
           "p99_deg": round(float(np.percentile(ang, 99)), 2), "tol_deg": FLOW_TOL_DEG}
    rep["ok"] = rep["p99_deg"] <= FLOW_TOL_DEG
    if not rep["ok"]:
        rep["fail"] = (f"the flow decodes {rep['p99_deg']:.1f} deg from where it was written over its worst "
                       f"hundredth ({rep['worst_deg']:.1f} at worst, limit {FLOW_TOL_DEG}) - the shader's "
                       "frame and humanform's disagree, and where they disagree the shells shear apart and "
                       "open a bald stripe (see fur.flow_frame)")
    return rep


def export_maps(ob, out_dir, base=None):
    """Write the packed fur PNGs out again beside a glb, without redoing the pass (a resumed build)."""
    import bpy
    ob = bpy.data.objects[ob] if isinstance(ob, str) else ob
    spec = read(ob)
    if spec is None or not spec.get("textures"):
        return {}
    base = base or (ob.name[:-5] if ob.name.endswith("_body") else ob.name)
    os.makedirs(out_dir, exist_ok=True)
    done = {}
    for key, name in spec["textures"].items():
        img = bpy.data.images.get(name)
        path = os.path.join(out_dir, name)
        if img is None:
            continue
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        done[key] = name
    return done
