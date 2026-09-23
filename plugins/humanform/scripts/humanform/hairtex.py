"""How a hair part will read in Godot: its texture's texels and mips, and its outline at a distance.

    from humanform import hairtex
    rep = hairtex.mip_check(ob)          # a hair shell object with a lookdev hair material
    rep["ok"], rep["problems"]           # False and the reasons when Godot will draw holes as patches
    rep = hairtex.silhouette_check(ob)   # ... and when its outline is a curve, not the ends of hairs

Why this exists. The first beards were a shell whose V repeated every 12 mm (a strand's length) while U repeated
every 40 mm, on a 256 x 512 texture: a texel was 0.16 mm across the strands and 0.023 mm along them, 7:1. Godot
picks a mip from the larger footprint, so at 0.6 m the level it sampled was 5 mm wide across the strands. The
texture had 35% holes (the gaps between strands and a thinned root and tip band every 12 mm), lookdev's
coverage-kept mips held that share at every level, and alpha scissor cut each level's holes out whole: a grid
of square patches of skin, tiled every 40 x 12 mm, on the chin. Blender's review samples level 0, so its tiles
showed fine strands; the patches were only visible in the game (four rebuilds in the likeness round).

The check simulates what Godot's sampler does, face by face: each triangle's texel size on the skin along U and
V (from its UVs and the image's size), the mip level a camera at `distances_m` picks (trilinear, with
`anisotropic` x filtering when the material asks for it), how wide that level's texel is on screen, and the
share of that level's texels under the alpha cutoff (with the per-corner vertex alpha the fade multiplies in,
where the shell has one). A face is *patchy* when a hole there is at least `patch_px` screen pixels wide across the strands and at
least `hole_share` of the level's texels it shows are holes: holes that large read as patches, not as hairs. The shell
fails when more than `max_patchy` of its interior area (vertex alpha 1) is patchy at any distance.

Pure numpy apart from `arrays` (which reads a Blender object), so tests can feed it synthetic meshes.
"""

from __future__ import annotations

import math

import numpy as np

VFOV_DEG = 30.0             # a close-shot's field of view is 27-40 degrees
IMAGE_PX = 1080             # screen height the footprint is measured against
DISTANCES_M = (0.6, 4.0)    # the close-up and a conversation across a room
PATCH_PX = 1.5              # a hole this many screen pixels wide or wider reads as a patch
HOLE_SHARE = 0.05           # ... when this share of the sampled level's texels are holes
MAX_PATCHY = 0.05           # a shell fails when more than this share of its interior area is patchy
MAX_ANISOTROPY = 2.5        # the area-weighted 90th percentile texel aspect a strand shell may have


def mip_alpha(alpha, levels=10, coverage_cutoff=None):
    """[level 0, 1, ...] box-filtered alpha, as Godot's mips are made. `coverage_cutoff`: scale each level's alpha
    so the share at or over it is level 0's (lookdev's `coverage_mips`)."""
    out = [np.asarray(alpha, np.float64)]
    target = float((out[0] >= coverage_cutoff).mean()) if coverage_cutoff is not None else None
    for _ in range(levels):
        a = out[-1]
        H, W = a.shape
        if H < 2 or W < 2:
            break
        a = a[:H // 2 * 2, :W // 2 * 2].reshape(H // 2, 2, W // 2, 2).mean(axis=(1, 3))
        if target is not None and target > 0:
            q = float(np.quantile(a, 1.0 - target))
            if q > 0 and q < coverage_cutoff:
                a = np.minimum(1.0, a * (coverage_cutoff / q))
        out.append(a)
    return out


def texel_sizes(P, UV, W, H):
    """(s_u, s_v, area) per triangle: metres per texel along U and V, and the triangle's area. P (T, 3, 3) corner
    positions, UV (T, 3, 2) corner UVs in texture repeats, W x H the image."""
    E1, E2 = P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
    D1, D2 = UV[:, 1] - UV[:, 0], UV[:, 2] - UV[:, 0]
    det = D1[:, 0] * D2[:, 1] - D1[:, 1] * D2[:, 0]
    ok = np.abs(det) > 1e-12
    det = np.where(ok, det, 1.0)
    # J = [E1 E2] inv([D1 D2]): dP/du and dP/dv
    dPdu = (E1 * D2[:, 1:2] - E2 * D1[:, 1:2]) / det[:, None]
    dPdv = (E2 * D1[:, 0:1] - E1 * D2[:, 0:1]) / det[:, None]
    s_u = np.linalg.norm(dPdu, axis=1) / W
    s_v = np.linalg.norm(dPdv, axis=1) / H
    area = 0.5 * np.linalg.norm(np.cross(E1, E2), axis=1)
    area = np.where(ok & (s_u > 0) & (s_v > 0), area, 0.0)
    return np.where(ok, s_u, 1.0), np.where(ok, s_v, 1.0), area


def mip_check(ob=None, *, material=None, P=None, UV=None, A=None, alpha=None, cutoff=0.5, coverage_mips=False, anisotropic=0,
              distances_m=DISTANCES_M, vfov_deg=VFOV_DEG, image_px=IMAGE_PX, patch_px=PATCH_PX,
              hole_share=HOLE_SHARE, max_patchy=MAX_PATCHY, max_anisotropy=MAX_ANISOTROPY):
    """The report described in the module docstring. Pass a Blender object `ob` and the name of its hair `material`
    (None: its first; the triangles using it are checked, and its lookdev extras say whether coverage mips and
    anisotropic filtering are on - an exported body carries its beard as one of its materials), or the arrays: P (T, 3, 3), UV (T, 3, 2),
    A (T, 3) vertex alpha or None, alpha (H, W) the texture's alpha."""
    if ob is not None:
        P, UV, A, alpha, look = arrays(ob, material)
        coverage_mips = bool(look.get("coverage_mips", coverage_mips))
        anisotropic = int(look.get("anisotropic", anisotropic))
    H, W = alpha.shape
    s_u, s_v, area = texel_sizes(P, UV, W, H)
    tri_a = np.ones(len(P)) if A is None else A.min(axis=1)
    interior = (area > 0) & (tri_a >= 0.999)
    # across the strands (U) against along them (V): a texel coarser across than along is what hurts, because the
    # mip is then picked by V and U's strands and gaps blur into blocks; coarser along V only softens the strands
    across = s_u / np.maximum(s_v, 1e-12)
    levels = mip_alpha(alpha, coverage_cutoff=cutoff if coverage_mips else None)
    rep = {"texture_px": [W, H], "triangles": int(len(P)), "interior_area_m2": round(float(area[interior].sum()), 6),
           "texel_mm": {"u_median": round(float(np.median(s_u[area > 0]) * 1000), 4),
                        "v_median": round(float(np.median(s_v[area > 0]) * 1000), 4)},
           "across_to_along_p90": round(_wquantile(across, area, 0.9), 2),
           "holes_by_level": [round(float((a < cutoff).mean()), 3) for a in levels], "coverage_mips": coverage_mips,
           "anisotropic": anisotropic, "views": {}}
    problems = []
    if rep["across_to_along_p90"] > max_anisotropy:
        problems.append(f"texels are {rep['across_to_along_p90']}x coarser across the strands than along them on the "
                        f"skin (90th percentile; U {rep['texel_mm']['u_median']} mm, V {rep['texel_mm']['v_median']} "
                        f"mm): Godot picks the mip by V and blurs U's strands and gaps into blocks - make a texel as "
                        f"long along V as across U (texture_px against tile_m and the V repeat)")
    wsum = max(float(area[interior].sum()), 1e-12)
    for d in distances_m:
        f = d * 2.0 * math.tan(math.radians(vfov_deg) / 2.0) / image_px        # metres per screen pixel
        major = f / np.minimum(s_u, s_v)
        minor = f / np.maximum(s_u, s_v)
        n = max(1, anisotropic)
        foot = np.maximum(major / n, minor) if n > 1 else major
        L = np.clip(np.log2(np.maximum(foot, 1e-9)), 0, len(levels) - 1)
        Li = np.round(L).astype(int)
        # a hole's width across the strands on screen: a gap long along a strand but narrower than a pixel across
        # it reads as the gap between two hairs (a scalp's thinning hairline); one wider than that is a patch
        hole_px = (2.0 ** Li) * s_u / f
        holes = _holes_under(UV, Li, levels, cutoff)
        patchy = interior & (hole_px >= patch_px) & (holes >= hole_share)
        share = float(area[patchy].sum()) / wsum
        rep["views"][f"{d:g}m"] = {"mip_median": round(float(np.median(L[interior])) if interior.any() else 0.0, 2),
                                   "hole_px_median": round(float(np.median(hole_px[interior])) if interior.any() else 0.0, 2),
                                   "patchy_share": round(share, 3)}
        if share > max_patchy:
            li = int(np.median(Li[patchy]))
            problems.append(f"at {d:g} m, {share:.0%} of the shell draws holes as patches: mip {li} is "
                            f"{float(np.median(hole_px[patchy])):.1f} screen px a texel across and "
                            f"{float(np.median(holes[patchy])):.0%} of the texels those faces show are under the "
                            f"{cutoff} cutoff - give the interior "
                            f"an opaque under-layer (alpha over the cutoff between the strands) or square texels")
    rep["ok"] = not problems
    rep["problems"] = problems
    return rep


# barycentric sample points inside a triangle: its centre, points toward each corner and along each edge
_BARY = np.array([[1, 1, 1], [4, 1, 1], [1, 4, 1], [1, 1, 4], [2, 2, 1], [2, 1, 2], [1, 2, 2], [6, 1, 1], [1, 6, 1],
                  [1, 1, 6], [3, 3, 1], [3, 1, 3], [1, 3, 3]], np.float64)
_BARY /= _BARY.sum(axis=1, keepdims=True)


def _holes_under(UV, Li, levels, cutoff):
    """Per triangle, the share of sample points inside it (in UV, wrapped: the texture repeats) where its mip
    level's alpha is under `cutoff` - the holes that triangle actually shows, not the whole texture's."""
    pts = np.einsum("sk,tkc->tsc", _BARY, UV)                           # (T, S, 2)
    out = np.zeros(len(UV))
    for li in np.unique(Li):
        sel = Li == li
        a = levels[int(li)]
        h, w = a.shape
        x = np.floor(np.mod(pts[sel, :, 0], 1.0) * w).astype(int) % w
        y = np.floor(np.mod(pts[sel, :, 1], 1.0) * h).astype(int) % h
        out[sel] = (a[y, x] < cutoff).mean(axis=1)
    return out


def _wquantile(x, w, q):
    keep = w > 0
    if not keep.any():
        return 0.0
    x, w = x[keep], w[keep]
    o = np.argsort(x)
    c = np.cumsum(w[o])
    return float(x[o][min(len(x) - 1, int(np.searchsorted(c, q * c[-1])))])


def arrays(ob, material=None):
    """(P, UV, A, alpha, look) of a hair shell (the triangles of `ob` using `material`, None: its first): world corner positions, UVs of the material's UV map, the vertex
    alpha of its colour attribute (None without one), the base colour texture's alpha (rows bottom-up, as V runs)
    and {coverage_mips, anisotropic} from its lookdev extras."""
    me = ob.data
    names = [m.name if m is not None else None for m in me.materials]
    slot = names.index(material) if material is not None else 0
    mat = me.materials[slot] if len(me.materials) else None
    img, uv_name, attr_name = None, None, None
    if mat is not None and mat.use_nodes:
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None and img is None \
                    and node.outputs["Alpha"].is_linked:
                img = node.image
            elif node.type == "UVMAP" and node.uv_map:
                uv_name = node.uv_map
            elif node.type == "VERTEX_COLOR" and node.layer_name:
                attr_name = node.layer_name
    if img is None:
        raise ValueError(f"{ob.name}: no image drives its material's alpha")
    W, H = img.size
    px = np.empty(W * H * 4, np.float32)
    img.pixels.foreach_get(px)
    alpha = px.reshape(H, W, 4)[:, :, 3].astype(np.float64)
    me.calc_loop_triangles()
    tris = me.loop_triangles
    loops = np.empty(len(tris) * 3, np.int64)
    tris.foreach_get("loops", loops)
    verts = np.empty(len(tris) * 3, np.int64)
    tris.foreach_get("vertices", verts)
    mi = np.empty(len(tris), np.int64)
    tris.foreach_get("material_index", mi)
    mine = np.repeat(mi == slot, 3)
    loops, verts = loops[mine], verts[mine]
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    m = np.array(ob.matrix_world, np.float64)
    co = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
    uvl = me.uv_layers.get(uv_name) if uv_name else me.uv_layers.active
    uv = np.empty(len(me.loops) * 2, np.float64)
    uvl.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    A = None
    ca = me.color_attributes.get(attr_name) if attr_name else None
    if ca is not None:
        c = np.empty(len(ca.data) * 4, np.float64)
        ca.data.foreach_get("color", c)
        c = c.reshape(-1, 4)[:, 3]
        A = (c[loops] if ca.domain == "CORNER" else c[verts]).reshape(-1, 3)
    look = {}
    ld = mat.get("lookdev") if mat is not None else None
    if ld is not None:
        ld = ld.to_dict() if hasattr(ld, "to_dict") else dict(ld)
        al = ld.get("alpha") or {}
        look["coverage_mips"] = "coverage_mips" in al
        tf = (ld.get("godot") or {}).get("texture_filter")
        look["anisotropic"] = 4 if tf in (4, 5) else 0     # *_WITH_MIPMAPS_ANISOTROPIC; Godot's default is 4x
    return co[verts].reshape(-1, 3, 3), uv[loops].reshape(-1, 3, 2), A, alpha, look


# --------------------------------------------------------------------------- the silhouette at a distance

# Why this exists. A beard grown as layered shells over the skin has a smooth outline: every edge of it is
# the fade's zero line on the face, a curve. Hair does not - its outline is the ends of thousands of hairs,
# so the edge wanders by a few millimetres from column to column. That is most of what tells the eye "hair"
# from "a brown decal", and it is the one thing the mip check cannot see (it only looks at the texture).
# `silhouette_check` rasterises the part's own geometry, with the fade's vertex alpha, at the screen
# resolution a camera has at `distances_m`, and measures how far the outline wanders from a smoothed copy
# of itself. A shell measures near zero at every distance; strand cards measure several pixels close up and
# still a fraction of one across a room. It also measures how much of the part survives to 4 m, because a
# beard made only of thin cards can dissolve into nothing at a distance.
SIL_DISTANCES_M = (0.6, 4.0)
SIL_ROUGH_MIN_PX = {0.6: 1.5, 4.0: 0.35}    # the outline must wander at least this far from its own smoothing
SIL_FLAT_PX = 0.6           # a boundary column this near its own smoothing is a straight edge there
SIL_FLAT_MAX_MM = 22.0      # ... and a straight run longer than this reads as a cut edge, not as hair ends
SIL_STEP_TOP = 0.05         # the share of an edge's columns the biggest steps are counted over ...
SIL_STEP_MAX = 0.45         # ... and how much of its whole movement they may hold: a polygon staircase does
                            # all its moving in a handful of risers with flat treads between, so nearly all of
                            # it lands in that 5%; hair moves a little in every column and lands near 0.1
SIL_WINDOW_M = 0.012        # the outline is smoothed over this much of the subject, not a fixed number of
                            # pixels: at 0.6 m that is 40 screen pixels and at 4 m it is 6, so the measure asks
                            # the same question at both - do the ends of the hairs still break the edge up?
SIL_ALPHA_CUTOFF = 0.5      # vertex alpha (the fade) below which a triangle does not draw
SIL_KEEP_MIN = 0.6          # the area left at the far distance, as a share of the near one's
SIL_MAX_SAMPLES = 1500000
SIL_DIRECTIONS = (("front", (0.0, -1.0, 0.0)), ("side", (-1.0, 0.0, 0.0)))


def _rasterise(P, A, eye, forward, up, f, cutoff=SIL_ALPHA_CUTOFF, max_samples=SIL_MAX_SAMPLES):
    """A boolean coverage mask of triangles P (T, 3, 3) with corner alpha A (T, 3), seen from `eye` along
    `forward`, at `f` metres a pixel on the subject. Points are scattered inside each triangle at about one
    per pixel (at least three), so a card narrower than a pixel still marks the pixels it crosses."""
    right = np.cross(forward, up)
    right = right / max(np.linalg.norm(right), 1e-12)
    up = np.cross(right, forward)
    E1, E2 = P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
    area = 0.5 * np.linalg.norm(np.cross(E1, E2), axis=1)
    per = np.clip(np.ceil(area / (f * f)).astype(np.int64) * 2, 3, 400)
    if per.sum() > max_samples:
        per = np.maximum(3, (per * (max_samples / per.sum())).astype(np.int64))
    idx = np.repeat(np.arange(len(P)), per)
    rng = np.random.RandomState(5)
    u = rng.uniform(size=len(idx))
    v = rng.uniform(size=len(idx))
    flip = u + v > 1.0
    u, v = np.where(flip, 1.0 - u, u), np.where(flip, 1.0 - v, v)
    pts = P[idx, 0] + E1[idx] * u[:, None] + E2[idx] * v[:, None]
    al = A[idx, 0] * (1 - u - v) + A[idx, 1] * u + A[idx, 2] * v
    pts = pts[al >= cutoff]
    if not len(pts):
        return np.zeros((1, 1), bool)
    d = pts - eye
    depth = d @ forward
    depth = np.where(depth > 1e-6, depth, 1e-6)
    # a perspective camera whose pixel is `f` metres at the subject's own depth
    scale = float(np.median(depth))
    x = (d @ right) / depth * scale / f
    y = (d @ up) / depth * scale / f
    xi = np.round(x - x.min()).astype(np.int64)
    yi = np.round(y - y.min()).astype(np.int64)
    W, H = int(xi.max()) + 1, int(yi.max()) + 1
    if W * H > 40000000:
        return np.zeros((1, 1), bool)
    mask = np.zeros((H, W), bool)
    mask[yi, xi] = True
    return mask


def _edge(mask, window, top=False):
    """One outline of the silhouette - the bottom (`top` False: where the hair ends) or the top (`top` True:
    where it leaves the skin) - measured three ways.

    (wander, columns, flat_run, step_share): how far it strays from its own `window`-wide moving average in
    pixels (near zero for a smooth curve, several pixels for tips); the longest unbroken run of columns
    sitting on that average (a mass cut off on a line has one, hair tips do not); and how much of its whole
    movement happens in its biggest `SIL_STEP_TOP` of columns - a polygon staircase does all its moving in a
    few risers with flat treads between, which is what the root mat's own boundary looked like along the
    cheek."""
    window = max(3, int(window) | 1)
    cols = np.nonzero(mask.any(axis=0))[0]
    if len(cols) < window + 2:
        return 0.0, len(cols), 0, 0.0
    rows = np.arange(mask.shape[0])[:, None]
    # the image's rows run up with z: the hair's ends are the smallest row of a column, the hairline the largest
    line = (np.where(mask, rows, -1).max(axis=0) if top
            else np.where(mask, rows, mask.shape[0]).min(axis=0))[cols].astype(np.float64)
    pad = np.concatenate([np.full(window // 2, line[0]), line, np.full(window // 2, line[-1])])
    smooth = np.convolve(pad, np.ones(window) / window, mode="valid")
    dev = np.abs(line - smooth)
    run = best = 0
    for flat in dev <= SIL_FLAT_PX:
        run = run + 1 if flat else 0
        best = max(best, run)
    d = np.abs(np.diff(line))
    big = max(1, int(round(SIL_STEP_TOP * len(d))))
    step = float(np.sort(d)[-big:].sum() / max(d.sum(), 1e-9)) if len(d) else 0.0
    return float(dev.mean()), len(cols), int(best), step


def silhouette_check(ob=None, *, obs=None, P=None, A=None, distances_m=SIL_DISTANCES_M, vfov_deg=VFOV_DEG,
                     image_px=IMAGE_PX, rough_min_px=None, keep_min=SIL_KEEP_MIN,
                     directions=SIL_DIRECTIONS, name=None, flat_max_mm=SIL_FLAT_MAX_MM,
                     step_max=SIL_STEP_MAX):
    """Whether a hair part's outline reads as hair at each of `distances_m`. Pass a Blender object `ob`,
    several with `obs` (they are measured as one thing, which is what the eye sees: a beard's root mat, the
    cards over it and the locks hanging off it have no outline of their own), or the arrays P (T, 3, 3) and
    A (T, 3). World space, z up, the face toward -y.

    {ok, problems, views: {"<dir> <d>m": {wander_px, wander_mm, flat_run_mm, columns, area_m2}}}. A view
    fails when its outline wanders less than `rough_min_px` (SIL_ROUGH_MIN_PX): it is then a curve, not hair.
    It fails too when the *bottom* edge runs straight for more than `flat_max_mm` at the near distance -
    a mass that ends on a line is a bib, whatever the rest of its outline does, and that is what a long beard
    read as on a chest - and when either edge does more than `step_max` of its moving in its biggest few
    columns, which is a staircase of whole faces (the root mat's own boundary along the cheek). The far distance also fails when less than `keep_min` of the near distance's area is
    left - a beard of cards so thin it dissolves across a room."""
    rough_min_px = dict(SIL_ROUGH_MIN_PX if rough_min_px is None else rough_min_px)
    if obs:
        name = name or "+".join(o.name for o in obs)
        parts = [_tri_alpha(o) for o in obs]
        P = np.concatenate([x[0] for x in parts]) if parts else np.zeros((0, 3, 3))
        A = np.concatenate([x[1] for x in parts]) if parts else np.zeros((0, 3))
    elif ob is not None:
        name = name or ob.name
        P, A = _tri_alpha(ob)
    rep = {"name": name, "triangles": int(len(P)), "views": {}, "warnings": []}
    problems = []
    centre = P.reshape(-1, 3).mean(axis=0)
    for dname, fwd in directions:
        fwd = np.asarray(fwd, np.float64)
        fwd = fwd / np.linalg.norm(fwd)
        areas = {}
        for d in distances_m:
            f = d * 2.0 * math.tan(math.radians(vfov_deg) / 2.0) / image_px
            mask = _rasterise(P, A, centre - fwd * d, fwd, np.array([0.0, 0.0, 1.0]), f)
            win = round(SIL_WINDOW_M / f)
            wander, cols, flat, step = _edge(mask, win)
            t_wander, _c, t_flat, t_step = _edge(mask, win, top=True)
            areas[d] = float(mask.sum()) * f * f
            rep["views"][f"{dname} {d:g}m"] = {"wander_px": round(wander, 2),
                                               "wander_mm": round(wander * f * 1000, 2),
                                               "flat_run_mm": round(flat * f * 1000, 1),
                                               "step_share": round(step, 2),
                                               "top_wander_px": round(t_wander, 2),
                                               "top_flat_run_mm": round(t_flat * f * 1000, 1),
                                               "top_step_share": round(t_step, 2),
                                               "columns": cols, "area_m2": round(areas[d], 6)}
            lo = rough_min_px.get(d)
            if lo is not None and cols >= SIL_WINDOW_M / f + 2 and wander < lo:
                problems.append(f"{dname} at {d:g} m: the outline wanders {wander:.2f} px from its own smoothing "
                                f"(at least {lo} wanted) - a smooth curve reads as a decal, not as hair; grow it "
                                "as strand cards with ragged lengths, or fade their tips further")
            if lo is not None and d == min(distances_m) and flat * f * 1000 > flat_max_mm:
                problems.append(f"{dname} at {d:g} m: {flat * f * 1000:.0f} mm of its bottom edge runs straight "
                                f"(at most {flat_max_mm:.0f} mm) - hair does not end on a line; break the mass "
                                "into locks of unequal length, or scatter the tips")
            # The TOP edge - where the hair leaves the skin. A staircase there is the shell's own polygon
            # boundary, and this is where it shows; but a *warning*, not a refusal, because the same number
            # rises on anatomy a part is entitled to: a goatee's top edge steps by a centimetre at each corner
            # of the mouth, where the moustache sits above the chin patch, and read 53-68% with no staircase
            # in it at all. What refuses a stepped mat is `brows`' own `mat_edge` - the alpha ramp measured in
            # faces, on the mesh, where it is local and unambiguous. The bottom edge is allowed its big jumps
            # too: that is one lock ending above the next, and `flat_run_mm` is its test.
            if lo is not None and d == min(distances_m) and t_step > step_max:
                rep["warnings"].append(f"{dname} at {d:g} m: {t_step:.0%} of the TOP edge's movement is in its "
                                       f"biggest {SIL_STEP_TOP:.0%} of columns (over {step_max:.0%}) - look for "
                                       "a staircase of whole faces where the hair leaves the skin")
        near, far = min(distances_m), max(distances_m)
        if areas.get(near, 0) > 0 and areas.get(far, 0) / areas[near] < keep_min:
            problems.append(f"{dname}: {areas[far] / areas[near]:.0%} of its area is left at {far:g} m "
                            f"(at least {keep_min:.0%} wanted) - the cards are too thin or too few to hold "
                            "the shape across a room")
    rep["ok"] = not problems
    rep["problems"] = problems
    return rep


def _tri_alpha(ob):
    """(P (T, 3, 3) world corner positions, A (T, 3) corner alpha) of every triangle of `ob`; alpha comes
    from its first colour attribute (the fade), 1 without one."""
    me = ob.data
    me.calc_loop_triangles()
    tris = me.loop_triangles
    loops = np.empty(len(tris) * 3, np.int64)
    tris.foreach_get("loops", loops)
    verts = np.empty(len(tris) * 3, np.int64)
    tris.foreach_get("vertices", verts)
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    m = np.array(ob.matrix_world, np.float64)
    co = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
    A = np.ones((len(tris), 3))
    ca = me.color_attributes[0] if len(me.color_attributes) else None
    if ca is not None:
        c = np.empty(len(ca.data) * 4, np.float64)
        ca.data.foreach_get("color", c)
        c = c.reshape(-1, 4)[:, 3]
        A = (c[loops] if ca.domain == "CORNER" else c[verts]).reshape(-1, 3)
    return co[verts].reshape(-1, 3, 3), A
