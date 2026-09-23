"""Strand cards: hair grown out of a per-vertex field on a body, for anything a shell cannot show.

    from humanform import cards
    rep = cards.grow(body, field, length_m=0.012, colour=(0.2, 0.12, 0.07), name="Borin_beard")
    rep["objects"]          # {"cards": "Borin_beard_cards"}  (+ "strand" when part of it hangs)

`field` is one float per body vertex (hm08's `delta.BODY_VERTS`, the shape `brows.beard_field` and
`fur`'s `hf_fur_den` are in): 0 where nothing grows, 1 well inside, between at the edge. Everything
else is a number over it.

**What a card is.** A ribbon of `cols` columns bowed out of its own chord - a flat card vanishes
edge-on - grown from a root scattered on the field. It starts along the skin's own downhill direction
(world down projected onto the tangent plane; straight down where the skin faces down, as under a chin
or a belly), or along a `flow` the caller gives per vertex (fur has one); it turns toward gravity by
`droop` at every step and is held `clear_m` off the body the whole way, so it follows the surface
before it falls. Past `hang_below_z` the clearance opens to `hang_clear_m`, which is what keeps a
beard off the chest and a mane off the shoulder.

**Length** is `length_m` times the field's own weight ramp (`length_scale`, one per vertex, for a
beard longest at the chin or a mane longest at the withers), jittered per card by `jitter` and capped
per vertex by `max_length_m` (a moustache that must not bury the mouth). `clump` gathers them: each
clump grows a spine and its members bend into it over their second half, which is what makes locks
rather than a pelt; `braids` winds the hanging clumps round their spine instead.

**What hangs is its own mesh.** A card whose tip falls past `hang_below_z` is cut there: the part
above rides the skin rigidly, as the skin it grows out of does, and only the part below goes into
`<name>_strand` with follow-through's contract - `ft_centrelines`, one chain a lock, each starting at
the cut. A chain that starts at the roots swings the skin they sit on into the body (the dwarf's beard
read 3.8 cm inside his own jaw at every rate until the cut was put in), and one chain for a whole
sheet twists it, which is why `long_loose`'s curtain is not chained at all.

**Conventions a card must keep**, because Godot is where they show:
- UVs are arc length across and along the card over the sheet's tile, so a texel is square and
  `hairtex.mip_check` passes - the beard's square patches came from texels 7:1;
- the sheet has no opaque under-layer (a card must show its gaps, or it is a brown strip);
- the fade (a colour attribute, COLOR_0 in glTF) is the root's at the root and falls to `tip_fade`
  over the last of the card, which drops the sheet's hairs one by one by rank and leaves a scatter of
  tips instead of a cut across the texture. That is what `hairtex.silhouette_check` measures.

Checks, all before the export: `coverage` (a bald patch of the field, by region), the cards' least
clearance off the skin, and the caller's own `hairtex` checks on the objects returned.
"""

from __future__ import annotations

import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector

FADE_ATTR = "hf_card_fade"      # the colour attribute whose alpha thins the hairs (brows.BEARD_FADE is this)
HAIR_ATTR = "hf_hair"           # point attribute: hair, not skin (follow-through flesh.HAIR_ATTR)
TILE_M = 0.04
SHEET_PX = 512

SEG_M = 0.022               # a card gets a segment every this far along it ...
SEGS = (3, 10)              # ... within these bounds
COLS = 3                    # columns across it: a bowed ribbon, so it does not vanish edge-on
BOW = 0.35                  # the middle column stands this much of the half width out of the chord
TIP_AT = 0.45               # from this share of a card's length its fade falls ...
TIP_FADE = 0.42             # ... to this: the sheet's hairs drop out one by one by rank
TAPER_POW = 1.6             # how the width narrows toward the tip
CLUMP_SIZE = 4.0            # cards a clump gathers at clump 0, and twice that at clump 1
MEAN_SAMPLES = 11           # points a clump's, a rope's or a lock's mean path is measured at
LOCKS = 3                   # chains a hanging part is sprung on: one down each side, one in the middle
GAP_MAX = 3.0               # the widest gap between a root and the next, as a multiple of the nominal spacing
ROOTS_MIN = 8               # a region of the field with fewer roots than this is bald
SINK_MAX_M = 0.002          # a card's outer column may cut this far into the skin it lies on, no further
SEED = 23

# The most cards one growth may build. Each is a ribbon emitted vertex by vertex in Python, so the
# cost is linear and steep: the gnoll asked for a MANE at the beard's own density (26000 a square
# metre over the whole neck and both shoulders) and the build had not finished twelve minutes later,
# with nothing on screen to say why. Refused now, before a single card is grown.
ROOTS_MAX = 20000

PARAMS = {
    "density": 26000.0,     # roots per square metre of field
    "width_m": 0.008,       # a card's width at its root
    "taper": 0.35,          # its width at the tip, as a share of that
    "clump": 0.5,           # 0..1: how far a card bends into its clump's spine
    "braids": 0,            # ropes wound out of the hanging part (0: loose locks)
    "jitter": 0.35,         # length varies by this share, per card
    "droop": 0.3,           # how much of each step's direction gravity takes
    "sweep": 0.0,           # sideways flare from the midline (a moustache)
    "clear_m": 0.0018,      # a card never comes nearer the skin than this ...
    "hang_clear_m": 0.02,   # ... and this far past `hang_below_z`, clear of the chest and the shirt on it
    "cover": 0.5,           # the sheet's share of hairs
    "strand_m": 0.02,       # a hair's length in the sheet
    "tip_at": TIP_AT, "tip_fade": TIP_FADE, "bow": BOW, "cols": COLS, "seg_m": SEG_M,
    # a hanging mass is not a sheet: it has depth, it narrows as it falls, and it is made of locks
    "layers": 1,            # card layers out from the skin - 1 is a sheet, 3 reads as a volume
    "layer_gap_m": 0.007,   # how far apart they stand by the tip
    "layer_taper": 0.4,     # the outermost layer's length, as this much less than the innermost's
    "locks": 3,             # how many locks the hanging cards gather into, and spring chains they get
    "lock_spread": 0.0,     # 0..1: how unequal those locks are in length, so they do not end on a line
    "gather": 0.0,          # 0..1: how far a lock's hanging cards converge on its own spine as they fall
    "narrow": 0.0,          # 0..1: how far the hanging mass draws in toward the midline by its tip
    "shade": 0.0,           # 0..1: tone between clumps (the vertex colour Godot multiplies into albedo)
    "plumb": 0.0,           # 0..1: how far the hanging part keeps the forward position it had at the cut
                            # instead of following the body in behind it
}


def params(**over):
    """PARAMS with `over` on top, refusing a name that is not one of them."""
    bad = [k for k in over if k not in PARAMS]
    if bad:
        raise ValueError(f"card parameters {bad} are not any of {sorted(PARAMS)}")
    out = dict(PARAMS)
    out.update({k: v for k, v in over.items() if v is not None})
    return out


def scaled(p, k):
    """`p` with every length (a key ending `_m`) times `k`, and the density per square metre over k^2 -
    a card on a bigger head is wider and longer, so fewer of them cover the same share of it."""
    out = {key: (v * k if key.endswith("_m") else v) for key, v in p.items()}
    out["density"] = p["density"] / max(k * k, 1e-6)
    return out


def material(name, colour, uv_name, cover=0.5, strand_m=0.02, px=SHEET_PX, tile_m=TILE_M):
    """lookdev's hair material with a strand sheet of its own: `cover` of it hairs `strand_m` long, the rest
    transparent, square texels over `tile_m`, alpha-scissored with coverage-kept mips so the hair count holds
    at a distance, the fade multiplied in as COLOR_0, and two-sided (a card is seen from both sides).

    The same sheet `brows.beard_pixels` draws, with the under-layer off: an opaque fill between the hairs is
    what a shell needs to hide skin and exactly what a card must not have."""
    from . import brows
    spec = {"under": False, "cover": float(cover), "strand_m": float(strand_m)}
    saved = brows.LOOK.get("beard_cards")
    brows.LOOK["beard_cards"] = {"texture_px": [px, px], "style": "_cards", "_spec": spec}
    try:
        return brows._material(name, colour, uv_name, "beard_cards", double_sided=True)
    finally:
        if saved is None:
            brows.LOOK.pop("beard_cards", None)
        else:
            brows.LOOK["beard_cards"] = saved


# ------------------------------------------------------------------------------------------ growing

def grow(body, field, length_m, colour=None, *, name=None, uv_name=None, rig=None, root_bone=None,
         scale=1.0, flow=None, length_scale=None, max_length_m=None, fade=None, hang_below_z=None,
         hang_m=None, seed=SEED, material_=None, tile=None, regions=None, what="cards", **over):
    """Grow strand cards out of `field` (one 0..1 weight per body vertex) on `body`.

    length_m        a card's length where the field is 1 and `length_scale` is 1
    colour          the hairs' screen (sRGB) colour; ignored when `material_` is given
    name            the objects are `<name>_cards` and `<name>_strand` (default: the body's base name)
    root_bone       the bone a hanging part swings from (default: the body's strongest at the roots)
    scale           every length times this, the density over its square (`hair.head_scale`)
    flow            (n, 3) world directions the cards set off in, per body vertex; None: downhill on the skin
    length_scale    (n,) multiplier on `length_m` per body vertex; None: 1 everywhere
    max_length_m    (n,) cap per body vertex, or a float; None: no cap
    fade            (n,) vertex alpha at the root; None: 0.4 + 0.6 * field
    hang_below_z    world z past which a card is cut and its lower part swings; None: nothing hangs
    regions         {name: (n,) weight} the coverage check reports and refuses a bald one by
    **over          any of PARAMS

    Returns {objects: {cards, strand?}, roots, clumps, coverage, min_clearance_m, ...}."""
    from . import body as _body
    from .hair import _object, _push_out, _clearance
    ob = _body.obj(body)
    rig = rig if rig is not None else _body.rig_of(ob)
    uv_name = uv_name or (ob.data.uv_layers.active.name if ob.data.uv_layers.active else "UVMap")
    base = name or (ob.name[:-5] if ob.name.endswith("_body") else ob.name)
    k = float(scale)
    p = scaled(params(**over), k)
    me = ob.data
    n = len(np.asarray(field))
    field = np.clip(np.asarray(field, np.float64), 0.0, 1.0)
    fade0 = (0.4 + 0.6 * field) if fade is None else np.asarray(fade, np.float64)
    lscale = np.ones(n) if length_scale is None else np.asarray(length_scale, np.float64)
    cap = (np.full(n, float(max_length_m)) if np.isscalar(max_length_m) or isinstance(max_length_m, float)
           else (None if max_length_m is None else np.asarray(max_length_m, np.float64)))
    length_m = float(length_m) * k
    hang_m = float(hang_m) * k if hang_m is not None else length_m

    if material_ is None:
        material_, mat_rep, sheet_tile = material(f"{base}_cards", colour or (0.2, 0.14, 0.09), uv_name,
                                                  cover=p["cover"], strand_m=p["strand_m"] / max(k, 1e-6))
    else:
        mat_rep, sheet_tile = {"material": material_.name, "source": "caller"}, TILE_M
    tile = (tile if tile is not None else sheet_tile) * k

    # the faces the field touches, and their corners' world positions, normals and skin weights
    polys = [tuple(q.vertices) for q in me.polygons if max(q.vertices) < n and max(field[i] for i in q.vertices) > 0]
    if not polys:
        raise RuntimeError(f"{what}: the field is zero everywhere - nothing to grow")
    used = sorted({i for q in polys for i in q})
    local = {i: j for j, i in enumerate(used)}
    mw = np.array(ob.matrix_world, np.float64)
    base_co = np.array([tuple(me.vertices[i].co) for i in used]) @ mw[:3, :3].T + mw[:3, 3]
    nrm = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3).astype(np.float64) @ np.array(ob.matrix_world.to_3x3(), np.float64).T
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-9)[:, None]
    vn = nrm[used]
    dirs = None if flow is None else np.asarray(flow, np.float64)[used]
    wts = _named_weights(ob, used)
    bvh = _body_bvh(ob, np.array([tuple(v.co) for v in me.vertices]) @ mw[:3, :3].T + mw[:3, 3])

    hang_z = -1e9 if hang_below_z is None else float(hang_below_z)
    clear_near, clear_hang = p["clear_m"], p["hang_clear_m"]

    def clear_of(z, t=0.0, layer=0.0):
        """How far off the body a card spine is held at height `z`, `t` of the way along it: `clear_m` on the
        face, opening to `hang_clear_m` past the hang line - and further out for each card layer, which is
        what gives a hanging mass depth instead of laying every card on one sheet."""
        past = _smooth1(hang_z, hang_z - 0.04 * k, z)
        # the layers open only where the part hangs: a face card pushed a centimetre off the lip is not
        # depth, it is a card standing in front of the mouth
        return (clear_near + (clear_hang - clear_near) * past
                + layer * p["layer_gap_m"] * _smooth1(0.0, 0.6, t) * past)

    rng = np.random.RandomState(seed)
    roots, normals, rweights, lengths, starts = _roots(polys, local, base_co, vn, dirs, field[used],
                                                       fade0[used], lscale[used],
                                                       None if cap is None else cap[used], wts,
                                                       length_m, p, k, rng)
    if not roots:
        raise RuntimeError(f"{what}: the field grew no card roots - raise `density` or widen the field")
    if len(roots) > ROOTS_MAX:
        raise RuntimeError(
            f"{what}: {len(roots)} card roots at density {p['density']:.0f} a square metre, over "
            f"{ROOTS_MAX} - every card is built vertex by vertex, so this does not finish: lower `density`. "
            "A beard's field is a few hundredths of a square metre and a pelt's region is a hundred times "
            "that (fur.CARD_DENSITY is what fur passes for exactly this reason)")
    npos = np.array([tuple(q) for q in roots])
    ncl = max(1, int(round(len(roots) / (CLUMP_SIZE * (1.0 + p["clump"])))))
    centres = npos[rng.choice(len(roots), ncl, replace=False)] if ncl < len(roots) else npos
    owner = np.argmin(((npos[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2), axis=1)
    # Depth: every card takes a layer, the inner ones most populous and the outer ones shorter. A hanging
    # mass whose cards all sit at one offset is a sheet however many of them there are - the long beard read
    # as a flat bib laid on the shirt.
    n_layers = max(1, int(p["layers"]))
    layer = np.minimum(n_layers - 1, (n_layers * rng.uniform(size=len(roots)) ** 1.6).astype(int))
    # Locks: contiguous bands across the body, each with a length of its own, so the mass ends in several
    # tips at several heights instead of on one line.
    n_locks = max(1, int(p["locks"]))
    order = np.argsort(npos[:, 0])
    lock = np.zeros(len(roots), int)
    for j in range(n_locks):
        lock[order[j * len(order) // n_locks:(j + 1) * len(order) // n_locks]] = j
    lock_len = 1.0 - p["lock_spread"] * rng.uniform(size=n_locks)
    # tone per CARD with a bias toward its clump's: all of a clump at one tone drew the mass in blocks the
    # size of a clump, which is a different flatness from the one it was meant to cure
    shade = (1.0 + p["shade"] * (0.6 * (rng.uniform(size=ncl) * 2.0 - 1.0)[owner]
                                 + 0.4 * (rng.uniform(size=len(roots)) * 2.0 - 1.0)))
    # the lock's length and the layer's shortening are the hanging mass's shape, so they apply to the cards
    # that reach past the cut. A face card made shorter by them stopped overhanging the root mat and left its
    # polygon edge as a sawtooth across the cheek.
    def _shape(i, L):
        if hang_below_z is None or roots[i].z - L >= hang_z:
            return L
        return L * lock_len[lock[i]] * (1.0 - p["layer_taper"] * layer[i] / max(n_layers - 1, 1))
    lengths = [(_shape(i, L), f) for i, (L, f) in enumerate(lengths)]
    paths, outs = [], []
    for i, (root, nor) in enumerate(zip(roots, normals)):
        cl = (lambda z, tt=0.0, lay=float(layer[i]): clear_of(z, tt, lay))
        pts, outv = _grow_card(bvh, root + nor * clear_near, nor, starts[i], lengths[i][0], p["droop"], cl)
        paths.append(pts)
        outs.append(outv)
    paths = _clump(paths, owner, ncl, p["clump"])
    hanging = [hang_below_z is not None and q[-1].z < hang_z for q in paths]
    braided = _braid(paths, npos, hanging, p, hang_m) if p["braids"] else set()
    if not braided and (p["gather"] > 0 or p["narrow"] > 0):
        _gather(paths, hanging, lock, n_locks, p, hang_z, hang_m)
    if p["plumb"] > 0:
        # the torso's own front profile over the fall, not the skin nearest each point: a belly stands
        # further forward than the chest, and a beard held only off its nearest skin falls in behind it
        low = min((q[-1].z for i, q in enumerate(paths) if hanging[i]), default=hang_z)
        band = base_co[(base_co[:, 2] < hang_z) & (base_co[:, 2] > low - 0.02) & (np.abs(base_co[:, 0]) < 0.14)]
        co_all = np.array([tuple(v.co) for v in me.vertices]) @ mw[:3, :3].T + mw[:3, 3]
        torso = co_all[(co_all[:, 2] < hang_z) & (co_all[:, 2] > low - 0.02) & (np.abs(co_all[:, 0]) < 0.14)]
        front = float(torso[:, 1].min()) if len(torso) else (float(band[:, 1].min()) if len(band) else 0.0)
        _plumb(paths, hanging, hang_z, p["plumb"], front - clear_hang)
    for i, pts in enumerate(paths):
        for j in range(1, len(pts)):
            pts[j] = _push_out(bvh, pts[j], clear_of(pts[j].z, j / max(len(pts) - 1, 1), float(layer[i])))

    neck = chest = None
    head = root_bone or _strongest_bone(rweights)
    if rig is not None and head in rig.data.bones and rig.data.bones[head].parent is not None:
        nb = rig.data.bones[head].parent
        neck = nb.name
        chest = nb.parent.name if nb.parent is not None else None

    bm, sbm = bmesh.new(), bmesh.new()
    uv, col, vweights = bm.loops.layers.uv.new(uv_name), bm.verts.layers.float_color.new(FADE_ATTR), []
    suv, scol, svweights, sshare = sbm.loops.layers.uv.new(uv_name), \
        sbm.verts.layers.float_color.new(FADE_ATTR), [], []
    made = {"rooted": 0, "hanging": 0, "cut": 0}
    for i, pts in enumerate(paths):
        u0, v0 = rng.uniform() * tile, rng.uniform() * tile
        w_root = rweights[i]
        rigid = lambda q, w_root=w_root: w_root                             # noqa: E731
        tone = float(shade[i])
        if not hanging[i]:
            _emit_card(bm, uv, col, vweights, pts, outs[i], p, lengths[i][1], rigid, tile, u0, v0, tone=tone)
            made["rooted"] += 1
            continue

        def wfun(q, w_root=w_root):
            return _hang_weights(w_root, q.z, hang_z, hang_m, neck, chest)

        def sfun(q):
            return min(1.0, max(0.0, (hang_z - q.z) / max(hang_m, 1e-6)))
        upper, lower, cut_at = _cut_at_z(pts, outs[i], hang_z)
        if upper is not None:
            _emit_card(bm, uv, col, vweights, upper[0], upper[1], p, lengths[i][1], rigid, tile, u0, v0,
                       span=(0.0, cut_at), tone=tone)
            made["cut"] += 1
        _emit_card(sbm, suv, scol, svweights, lower[0], lower[1], p, lengths[i][1], wfun, tile, u0,
                   v0 + cut_at * _polyline_m(pts), share=sshare, sfun=sfun, span=(cut_at, 1.0), tone=tone)
        made["hanging"] += 1

    objects = {}
    if len(bm.faces):
        objects["cards"] = _make(f"{base}_cards", bm, ob, rig, vweights, material_, _object)
    bm.free()
    lines = []
    if len(sbm.faces):
        sob = _make(f"{base}_strand", sbm, ob, rig, svweights, material_, _object,
                    extra={"ft_strand": np.maximum(np.array(sshare), 1e-3)})
        inv = ob.matrix_world.inverted()
        lines = _locks(paths, hanging, npos, p["braids"] or p["locks"], hang_z)
        sob["ft_type"] = "strand"
        sob["ft_root_bone"] = head
        sob["ft_strand_type"] = what
        sob["ft_centrelines"] = [[round(float(x), 5) for q in ln for x in tuple(inv @ Vector(q))] for ln in lines]
        sob["ft_length_m"] = round(max(_polyline_m(ln) for ln in lines), 4) if lines else 0.0
        objects["strand"] = sob
    sbm.free()

    gaps = _coverage(npos, ({nm: np.asarray(v)[used] for nm, v in regions.items()} if regions else None),
                     field[used], base_co, p)
    clear = _clearance(bvh, [Vector(q) for pts in paths for q in pts[1:]])
    rep = {"objects": {a: o.name for a, o in objects.items()}, "made": objects, "roots": len(roots),
           "clumps": ncl, "rooted": made["rooted"], "hanging": made["hanging"], "cut_at_hang": made["cut"],
           "braided": len(braided), "locks": len(lines), "root_bone": head,
           "density_per_m2": round(p["density"], 1), "width_m": round(p["width_m"], 4), "clump": p["clump"],
           "length_m": [round(min(x[0] for x in lengths), 4), round(max(x[0] for x in lengths), 4)],
           "coverage": gaps, "min_clearance_m": clear, "material": mat_rep}
    if not gaps["ok"]:
        raise RuntimeError(f"{what}: the strand cards leave the field bald - " + "; ".join(gaps["problems"]))
    if clear is not None and clear < -SINK_MAX_M * k:
        raise RuntimeError(f"{what}: a strand card runs {-clear * 1000:.1f} mm inside the skin (at most "
                           f"{SINK_MAX_M * k * 1000:.1f} mm) - a card wider than the curve it lies on cuts "
                           "the chord; narrow `width_m` or raise `clear_m`")
    return rep


def _make(name, bm, ob, rig, vweights, mat, _object, extra=None):
    groups = dict(extra or {})
    for i, w in enumerate(vweights):
        for g, x in w.items():
            groups.setdefault(g, np.zeros(len(vweights)))[i] = x
    bm.verts.index_update()
    out = _object(name, bm, ob, rig, groups)
    out.data.materials.append(mat)
    at = out.data.attributes.new(HAIR_ATTR, "FLOAT", "POINT")
    at.data.foreach_set("value", np.ones(len(out.data.vertices), np.float32))
    return out


def _roots(polys, local, base_co, vn, dirs, w_used, fade_used, lscale, cap, wts, length_m, p, k, rng):
    """Roots over the field: per body face, `density` x its area x how far inside the field it is, at random
    points in it. Returns (positions, normals, skin weights, [(length, fade)], start directions)."""
    down = Vector((0.0, 0.0, -1.0))
    roots, normals, rweights, lengths, starts = [], [], [], [], []
    for q in polys:
        idx = [local[i] for i in q]
        inside = float(np.mean(w_used[idx]))
        if inside <= 0.0:
            continue
        tris = [(idx[0], idx[i], idx[i + 1]) for i in range(1, len(idx) - 1)]
        areas = [0.5 * float(np.linalg.norm(np.cross(base_co[b] - base_co[a], base_co[c] - base_co[a])))
                 for a, b, c in tris]
        want = p["density"] * sum(areas) * inside
        for _ in range(int(want) + (1 if rng.uniform() < want - int(want) else 0)):
            ti = int(np.searchsorted(np.cumsum(areas), rng.uniform() * max(sum(areas), 1e-12)))
            a, b, c = tris[min(ti, len(tris) - 1)]
            u1, u2 = rng.uniform(), rng.uniform()
            if u1 + u2 > 1.0:
                u1, u2 = 1.0 - u1, 1.0 - u2
            bw = (1.0 - u1 - u2, u1, u2)
            pos = bw[0] * base_co[a] + bw[1] * base_co[b] + bw[2] * base_co[c]
            nor = bw[0] * vn[a] + bw[1] * vn[b] + bw[2] * vn[c]
            nor = Vector(nor / max(np.linalg.norm(nor), 1e-9))
            w = {}
            for j, s in zip((a, b, c), bw):
                for nm, x in wts[j].items():
                    w[nm] = w.get(nm, 0.0) + s * x
            tot = sum(w.values()) or 1.0
            root = Vector(pos)
            roots.append(root)
            normals.append(nor)
            rweights.append({nm: x / tot for nm, x in w.items() if x / tot > 1e-4})
            L = length_m * float(bw[0] * lscale[a] + bw[1] * lscale[b] + bw[2] * lscale[c])
            L *= 1.0 + p["jitter"] * (rng.uniform() * 2.0 - 1.0)
            if cap is not None:
                # the cap is jittered too, or every capped hair would end on one line (a moustache's)
                L = min(L, float(bw[0] * cap[a] + bw[1] * cap[b] + bw[2] * cap[c]) * rng.uniform(0.55, 1.0))
            lengths.append((max(L, 0.004 * k), float(bw[0] * fade_used[a] + bw[1] * fade_used[b]
                                                     + bw[2] * fade_used[c])))
            if dirs is not None:
                d = Vector(bw[0] * dirs[a] + bw[1] * dirs[b] + bw[2] * dirs[c])
                starts.append((d.normalized() if d.length > 1e-6 else down.copy()))
                continue
            # downhill on the skin: world down in the tangent plane, or straight down where the skin faces down
            t = down - nor * down.dot(nor)
            t = t.normalized() if t.length > 0.25 else down.copy()
            side = Vector((math.copysign(1.0, root.x) if abs(root.x) > 1e-4 else 0.0, 0.0, 0.0))
            starts.append((t * 0.9 + nor * 0.3
                           + side * p["sweep"] * min(1.0, abs(root.x) / max(0.03 * k, 1e-6))).normalized())
    return roots, normals, rweights, lengths, starts


def _grow_card(bvh, root, normal, d0, length, droop, clear_of, segs=None):
    """One card's path: `segs` + 1 points from the root, following the body and falling into gravity, with the
    outward normal at each. Walked four times as finely as it is kept, so the push off the skin does not
    corner."""
    from .hair import _push_out
    segs = segs or int(min(SEGS[1], max(SEGS[0], round(length / SEG_M))))
    down = Vector((0.0, 0.0, -1.0))
    fine = 4 * segs
    ds = length / fine
    pts, outv = [root.copy()], [normal.copy()]
    d, out = d0.normalized(), normal.copy()
    for _i in range(fine):
        d = (d * (1.0 - droop) + down * droop).normalized()
        cand = _push_out(bvh, pts[-1] + d * ds, clear_of(pts[-1].z - ds))
        step = cand - pts[-1]
        cand = pts[-1] + (step.normalized() if step.length > 1e-9 else d) * ds
        d = (cand - pts[-1]).normalized()
        hit = bvh.find_nearest(cand)
        if hit[0] is not None:
            off = cand - hit[0]
            out = off.normalized() if off.length > 1e-6 and off.dot(hit[1]) > 0 else Vector(hit[1])
        pts.append(cand)
        outv.append(out.copy())
    return pts[::4], outv[::4]


def _sample(path, u):
    """The point a fraction `u` along a path by index (cards have different numbers of points: a long one
    gets a segment every SEG_M, a stubby one the minimum)."""
    x = max(0.0, min(1.0, u)) * (len(path) - 1)
    i = min(len(path) - 2, int(x))
    return path[i].lerp(path[i + 1], x - i)


def _mean_path(paths, members, r=MEAN_SAMPLES):
    return [Vector(tuple(np.mean([tuple(_sample(paths[i], j / (r - 1))) for i in members], axis=0)))
            for j in range(r)]


def _clump(paths, owner, ncl, clump):
    """Bend each card into its clump's mean path over its second half: locks, not a pelt."""
    if clump <= 0:
        return paths
    means = {}
    for ci in range(ncl):
        members = [i for i in range(len(paths)) if owner[i] == ci]
        if len(members) >= 2:
            means[ci] = _mean_path(paths, members)
    out = []
    for i, pts in enumerate(paths):
        mean = means.get(int(owner[i]))
        if mean is None:
            out.append(pts)
            continue
        n = len(pts)
        out.append([q.lerp(_sample(mean, j / (n - 1)), clump * _smooth1(0.25, 1.0, j / (n - 1)))
                    for j, q in enumerate(pts)])
    return out


def _braid(paths, npos, hanging, p, hang_m):
    """Wind the hanging cards round `braids` ropes instead of letting them hang in loose clumps: each rope is
    the mean path of a contiguous share of the cards across the body, and every card of it spirals round that
    path at its own phase, on a radius that pulses down the rope - which is what a plait's bulges are. Cheap,
    because the cards and their spines are already there: it only re-places the points."""
    idx = [i for i, h in enumerate(hanging) if h]
    if not idx or p["braids"] < 1:
        return set()
    order = sorted(idx, key=lambda i: npos[i][0])
    # contiguous across the body, so a rope is a rope: interleaving put every rope's cards across the whole
    # width and all the spines landed on top of one another
    B = int(p["braids"])
    ropes = [order[j * len(order) // B:(j + 1) * len(order) // B] for j in range(B)]
    done = set()
    for rope in ropes:
        if len(rope) < 3:
            continue
        spine = _mean_path(paths, rope)
        r0 = max(p["width_m"] * 1.2, float(np.std([npos[i][0] for i in rope])) * 1.3)
        turns = max(1.0, hang_m / max(6.0 * r0, 1e-4))
        for m, i in enumerate(rope):
            phi = 2 * math.pi * m / len(rope)
            n = len(paths[i])
            new = []
            for j in range(n):
                u = j / (n - 1)
                c0 = _sample(spine, u)
                d = _sample(spine, min(1.0, u + 0.05)) - _sample(spine, max(0.0, u - 0.05))
                d = d.normalized() if d.length > 1e-9 else Vector((0.0, 0.0, -1.0))
                b = Vector((1.0, 0.0, 0.0)) if abs(d.x) < 0.95 else Vector((0.0, 1.0, 0.0))
                b = (b - d * b.dot(d)).normalized()
                c2 = d.cross(b)
                ang = phi + 2 * math.pi * turns * u
                r = r0 * (1.0 - 0.6 * u) * (0.75 + 0.25 * math.cos(3.0 * ang))
                new.append(c0.lerp(c0 + b * (r * math.cos(ang)) + c2 * (r * math.sin(ang)),
                                   _smooth1(0.0, 0.25, u)))
            paths[i] = new
            done.add(i)
    return done


def _plumb(paths, hanging, cut_z, plumb, front_y):
    """Past the cut, a card hangs from where it left the jaw rather than following the body in behind it.

    Held only off the nearest skin, a long beard traced the chest and the belly - and a jersey shirt hung from
    the apex of a stocky chest stands up to 9 cm off that skin, so a third of the dwarf's beard was under his
    t-shirt however far the clearance was raised. Hair does not do that: it hangs. Each hanging point is kept
    at least as far forward (-y) as the greater of where its card passed the cut and `front_y`, the torso's own
    front profile over the fall less the hang clearance."""
    for i, pts in enumerate(paths):
        if not hanging[i]:
            continue
        y_cut = next((q.y for q in pts if q.z <= cut_z), None)
        if y_cut is None:
            continue
        want = min(y_cut, front_y)
        for j, q in enumerate(pts):
            if q.z <= cut_z and q.y > want:
                pts[j] = Vector((q.x, q.y + (want - q.y) * plumb, q.z))


def _gather(paths, hanging, lock, n_locks, p, cut_z, hang_m):
    """Shape the hanging mass: each lock's cards converge on that lock's own spine as they fall (`gather`),
    and the whole mass draws in toward the midline by its tip (`narrow`).

    Without this the hanging cards are a curtain as wide at the tip as the jaw is at the top - a flat brown
    bib on the chest, which is what the long beard read as. A beard is widest where it leaves the jaw and
    gathers into two or three locks below it."""
    idx = [i for i, h in enumerate(hanging) if h]
    if not idx:
        return
    for j in range(n_locks):
        members = [i for i in idx if lock[i] == j]
        if len(members) < 3:
            continue
        spine = _mean_path(paths, members)
        for i in members:
            n = len(paths[i])
            new = []
            for r, q in enumerate(paths[i]):
                s = _smooth1(cut_z, cut_z - max(hang_m, 1e-6), q.z)       # 0 at the cut, 1 at the tip
                g = q.lerp(_sample(spine, r / max(n - 1, 1)), p["gather"] * s)
                new.append(Vector((g.x * (1.0 - p["narrow"] * s), g.y, g.z)))
            paths[i] = new


def _locks(paths, hanging, npos, n_locks, z_start):
    """The hanging part's centrelines, one a lock: the cards split left to right into `n_locks` groups, each
    group's mean path **from `z_start` down** - the cut, not the roots. follow-through hangs one spring chain
    on each and every vertex joins its nearest; a vertex above the first joint projects to the chain's start
    and stays rigid on the root bone, which is what a card's root on the skin has to be."""
    idx = [i for i, h in enumerate(hanging) if h]
    if not idx:
        return []
    idx.sort(key=lambda i: npos[i][0])
    n_locks = max(1, min(int(n_locks), len(idx)))
    out = []
    for j in range(n_locks):
        group = idx[j * len(idx) // n_locks:(j + 1) * len(idx) // n_locks] or idx
        line = _mean_path(paths, group)
        k = next((i for i, q in enumerate(line) if q.z <= z_start), 0)
        if k > 0:
            a, b = line[k - 1], line[k]
            f = (a.z - z_start) / max(a.z - b.z, 1e-9)
            line = [a.lerp(b, min(1.0, max(0.0, f)))] + line[k:]
        out.append([tuple(q) for q in line])
    return [ln for ln in out if _polyline_m(ln) > 1e-3]


def _hang_weights(w_root, z, cut_z, hang_m, neck, chest):
    """A hanging card's rigid fallback weights at height `z`: the root's at the cut, blending into the next
    bone up the chain and then its parent toward the tip, so the part still moves sensibly before
    follow-through's chain takes over (and if the strand stage never runs)."""
    u = min(1.0, max(0.0, (cut_z - z) / max(hang_m, 1e-6)))
    a = _smooth1(0.1, 0.6, u)
    b = _smooth1(0.5, 1.0, u)
    w = {nm: x * (1.0 - a) for nm, x in w_root.items()}
    if neck:
        w[neck] = w.get(neck, 0.0) + (a * (1.0 - b) if chest else a)
    if chest:
        w[chest] = w.get(chest, 0.0) + a * b
    return {nm: x for nm, x in w.items() if x > 1e-4}


def _cut_at_z(pts, outv, z):
    """Split a card's path where it first falls past `z`: ((upper points, upper normals) or None,
    (lower points, lower normals), the cut's share of the whole card's length). Both pieces share the cut
    point, so the hair runs on across it."""
    k = next((j for j, q in enumerate(pts) if q.z <= z), None)
    if k is None or k == 0:
        return None, (pts, outv), 0.0
    a, b = pts[k - 1], pts[k]
    f = min(1.0, max(0.0, (a.z - z) / max(a.z - b.z, 1e-9)))
    cut = a.lerp(b, f)
    n_out = outv[k - 1].lerp(outv[k], f)
    upper = (pts[:k] + [cut], outv[:k] + [n_out])
    lower = ([cut] + pts[k:], [n_out] + outv[k:])
    whole = _polyline_m(pts)
    return upper, lower, (_polyline_m(upper[0]) / whole if whole > 1e-9 else 0.0)


def _emit_card(bm, uv, col, vweights, pts, outv, p, fade_root, wfun, tile, u0, v0,
               share=None, sfun=None, span=(0.0, 1.0), tone=1.0):
    """Write one card into `bm`: a bowed ribbon along `pts`, `width_m` across at the root narrowing to
    `taper` of it, UVs in metres over `tile` both ways (square texels) and the fade in `col`. `span` is this
    piece's share of the whole card, so a card cut at the hang line tapers and fades as one card across the
    two meshes."""
    cols = int(p["cols"])
    n = len(pts)
    arc = [0.0]
    for a, b in zip(pts[:-1], pts[1:]):
        arc.append(arc[-1] + (b - a).length)
    L = max(arc[-1], 1e-6)
    grid = []
    for i, q in enumerate(pts):
        t = span[0] + (span[1] - span[0]) * (arc[i] / L)
        d = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        d = d.normalized() if d.length > 1e-9 else Vector((0.0, 0.0, -1.0))
        o = outv[i] - d * outv[i].dot(d)
        o = o.normalized() if o.length > 1e-6 else Vector((0.0, -1.0, 0.0))
        sidev = d.cross(o).normalized()
        hw = 0.5 * p["width_m"] * (1.0 - (1.0 - p["taper"]) * t ** TAPER_POW)
        a = fade_root * (1.0 - (1.0 - p["tip_fade"]) * _smooth1(p["tip_at"], 1.0, t))
        row = []
        for j in range(cols):
            f = -1.0 + 2.0 * j / (cols - 1)
            pos = q + sidev * (hw * f) + o * (hw * p["bow"] * (1.0 - f * f))
            v = bm.verts.new(pos)
            v[col] = (tone, tone, tone, float(a))
            vweights.append(wfun(pos))
            if share is not None:
                share.append(sfun(pos))
            row.append((v, (u0 + hw * f) / tile, (v0 + arc[i]) / tile))
        grid.append(row)
    for i in range(n - 1):
        for j in range(cols - 1):
            quad = [grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]]
            fc = bm.faces.new([x[0] for x in quad])
            fc.smooth = True
            for loop, (_v, uu, vv) in zip(fc.loops, quad):
                loop[uv].uv = (uu, vv)
    return L


def _coverage(roots, regions, w_used, base_co, p):
    """Whether the cards cover the field: for every point well inside each named region, the distance to the
    nearest card root, against the spacing the density asks for (1 / sqrt(density)).

    This is what catches a bald patch before a build ships. The narrowest parts of a field - the notch of skin
    under a lower lip, the corners of a mouth, the far end of a mane - are the first places a sampler that only
    takes whole faces, or a density too low for a region, leaves bare; the beard's shell version of that was
    found by eye instead, four rebuilds in. A region with fewer than ROOTS_MIN roots is bald outright."""
    from mathutils.kdtree import KDTree
    kd = KDTree(len(roots))
    for i, q in enumerate(roots):
        kd.insert(Vector(q), i)
    kd.balance()
    body = KDTree(len(base_co))
    for i, q in enumerate(base_co):
        body.insert(Vector(q), i)
    body.balance()
    home = [body.find(Vector(q))[1] for q in roots]         # the body vertex each root sits on
    nominal = 1.0 / math.sqrt(max(p["density"], 1e-6))
    out, problems = {}, []
    for nm, m in (regions or {"field": w_used}).items():
        m = np.asarray(m, np.float64)
        sel = np.nonzero(m > 0.6)[0]
        if not len(sel):
            continue
        near = np.sort(np.array([kd.find(Vector(base_co[i]))[2] for i in sel]))
        p99 = float(near[min(len(near) - 1, int(0.99 * len(near)))])
        n_roots = int(sum(1 for j in home if m[j] > 0))
        out[nm] = {"points": int(len(sel)), "roots": n_roots, "nominal_mm": round(nominal * 1000, 2),
                   "gap_p99_mm": round(p99 * 1000, 2), "gap_max_mm": round(float(near[-1]) * 1000, 2)}
        if n_roots < ROOTS_MIN:
            problems.append(f"{nm}: {n_roots} card roots over {len(sel)} points of the region - it is bald")
        elif p99 > GAP_MAX * nominal:
            problems.append(f"{nm}: skin {p99 * 1000:.1f} mm from the nearest card root (99th percentile; the "
                            f"density asks for {nominal * 1000:.1f} mm, at most {GAP_MAX}x) - the region has "
                            "a gap the cards never reach")
    return {"ok": not problems, "problems": problems, "regions": out}


# ------------------------------------------------------------------------------------------ small helpers

def _smooth1(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def _polyline_m(pts):
    return float(sum((Vector(b) - Vector(a)).length for a, b in zip(pts[:-1], pts[1:])))


def _named_weights(ob, indices):
    """[{group name: weight}] for body vertices `indices`."""
    names = {g.index: g.name for g in ob.vertex_groups}
    return [{names[e.group]: e.weight for e in ob.data.vertices[i].groups if e.group in names and e.weight > 1e-4}
            for i in indices]


def _strongest_bone(rweights):
    """The group the roots carry most of: the bone a hanging part swings from when none is named."""
    total = {}
    for w in rweights:
        for nm, x in w.items():
            total[nm] = total.get(nm, 0.0) + x
    return max(total, key=total.get) if total else None


def _body_bvh(ob, co):
    """The body's surface in world space, as far as `co` reaches."""
    from mathutils.bvhtree import BVHTree
    n = len(co)
    polys = [tuple(q.vertices) for q in ob.data.polygons if max(q.vertices) < n]
    return BVHTree.FromPolygons([Vector(c) for c in co], polys)


CLEAR_MARGIN_M = 0.004      # a strand must keep this much air between itself and the cloth over the skin
CLEAR_STAND_MAX_M = 0.05    # cloth further off the skin than this is not cloth over that skin: the ray has
                            # left through an opening (a neck hole) and hit the garment's far side


def clearance(part, against, body=None, samples=1500):
    """Whether `part` falls in front of what the body is wearing, or is caught under it.

    For each of `part`'s points: the nearest point on the skin, the outward direction from it, and the first
    garment surface along that ray. A point nearer the skin than that surface is **under the cloth**; one
    further out is in front of it; one where the ray meets no garment has no cloth to be under.

    A plain signed distance cannot answer this - a garment is an open shell, so the side of a distant face's
    normal means nothing, and a beard 30 cm clear of the trousers read as "330 mm inside" them. This is how a
    hanging part is checked against a **dressed** body: it grows in the hair stage, long before the garments
    exist, so its `hang_clear_m` is measured off bare skin, and a jersey shirt hung from the apex of a stocky
    chest stands a long way off that skin. The dwarf's long beard hung 38 mm off his chest and was still
    inside his t-shirt.

    {under_share, under_depth_m, min_gap_m, nearest, covered, sampled}."""
    from mathutils.bvhtree import BVHTree
    from . import body as _body

    def tree(o, skin_only=False):
        o = _body.obj(o)
        me = o.data
        co = [o.matrix_world @ v.co for v in me.vertices]
        hair = np.zeros(len(me.vertices))
        at = me.attributes.get(HAIR_ATTR) if skin_only else None
        if at is not None:
            buf = np.empty(len(at.data), np.float32)
            at.data.foreach_get("value", buf)
            hair[:len(buf)] = buf
        # the body carries the cards joined into it, and a card is not skin: measured against the body as it
        # stands, a beard vertex's "nearest skin" is its own neighbour and the ray out of it leaves through
        # the far side of the shirt (494 mm)
        polys = [tuple(q.vertices) for q in me.polygons if not any(hair[i] > 0.5 for i in q.vertices)]
        return (o.name, BVHTree.FromPolygons(co, polys)) if co and polys else None

    part = _body.obj(part)
    against = [against] if not isinstance(against, (list, tuple)) else list(against)
    cloth = [x for x in (tree(o) for o in against) if x]
    if not cloth:
        return None
    skin = tree(body, skin_only=True) if body is not None else None
    verts = [part.matrix_world @ v.co for v in part.data.vertices]
    step = max(1, len(verts) // samples)
    under, covered, taken, deepest, gap, where = 0, 0, 0, 0.0, 1.0, None
    for v in verts[::step]:
        taken += 1
        for nm, tr in cloth:
            hit = tr.find_nearest(v)
            if hit[0] is not None and (v - hit[0]).length < gap:
                gap, where = (v - hit[0]).length, nm
        if skin is None:
            continue
        near = skin[1].find_nearest(v)
        if near[0] is None:
            continue
        out = v - near[0]
        if out.length < 1e-6:
            continue
        stand = None
        for _nm, tr in cloth:
            hit = tr.ray_cast(near[0] + out.normalized() * 1e-4, out.normalized(), 0.5)
            if hit[0] is not None:
                d = (hit[0] - near[0]).length
                stand = d if stand is None else min(stand, d)
        if stand is None or stand > CLEAR_STAND_MAX_M:
            continue            # no cloth over this patch of skin, or the ray left through the neck hole
        covered += 1
        if out.length < stand + CLEAR_MARGIN_M:
            under += 1
            deepest = max(deepest, stand + CLEAR_MARGIN_M - out.length)
    return {"under_share": round(under / max(covered, 1), 4), "under": under, "covered": covered,
            "under_depth_m": round(deepest, 4), "min_gap_m": round(gap, 5), "nearest": where,
            "sampled": taken, "against": [nm for nm, _ in cloth]}


def contract(strand):
    """follow-through's strand contract as a hanging card mesh carries it, checked (`ft_centrelines`: one
    chain a lock, since one chain through a sheet as wide as a jaw twists it). {passed, problems, ...}."""
    from . import body as _body
    from .hair import _weights
    ob = _body.obj(strand)
    problems = []
    if ob.get("ft_type") != "strand":
        problems.append(f"ft_type is {ob.get('ft_type')!r}, not 'strand'")
    if not ob.get("ft_root_bone"):
        problems.append("no ft_root_bone")
    lines = [list(x) for x in (ob.get("ft_centrelines") or [])]
    if not lines:
        problems.append("no ft_centrelines")
    for i, flat in enumerate(lines):
        if len(flat) < 6 or len(flat) % 3:
            problems.append(f"lock {i}: a centreline must be a flat [x, y, z, ...] of at least two points")
    g = ob.vertex_groups.get("ft_strand")
    if g is None:
        problems.append("no ft_strand vertex group")
    order = None
    if g is not None and lines and not problems:
        w = _weights(ob, "ft_strand")
        co = np.empty(len(ob.data.vertices) * 3, np.float32)
        ob.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        pts = np.array(lines[len(lines) // 2], np.float64).reshape(-1, 3)
        root, tip = w < 0.1, w > 0.9
        if root.any() and tip.any():
            order = {"root_group_z": round(float(co[root][:, 2].mean()), 4),
                     "tip_group_z": round(float(co[tip][:, 2].mean()), 4),
                     "first_point_z": round(float(pts[0][2]), 4), "last_point_z": round(float(pts[-1][2]), 4)}
            if order["tip_group_z"] > order["root_group_z"]:
                problems.append("ft_strand weights do not run down the cards: their tips are above their roots")
    return {"passed": not problems, "problems": problems, "locks": len(lines),
            "points": [len(x) // 3 for x in lines], "order": order}
