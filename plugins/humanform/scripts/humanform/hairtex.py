"""How a hair shell's texture will sample in Godot: texel shape on the skin and holes that survive the mips.

    from humanform import hairtex
    rep = hairtex.mip_check(ob)          # a hair shell object with a lookdev hair material
    rep["ok"], rep["problems"]           # False and the reasons when Godot will draw holes as patches

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
