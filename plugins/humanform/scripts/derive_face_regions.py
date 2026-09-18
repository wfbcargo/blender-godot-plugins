"""Derive `data/face_regions.json` from MPFB2's base mesh: the ears, the eyelash cards and the brow cards.

    blender -b --factory-startup --python-exit-code 1 --python derive_face_regions.py -- [base=<base.obj>] [out=<json>]

A baked humanform body keeps MPFB's body vertices 0..13379 in base-mesh order (the bake deletes only the
helpers after them), so anything placed on the base mesh by vertex index can be put back on any body
after its targets, fit and bake. Three things are placed that way:

- **ears**: the base-mesh vertices of each ear - the ones standing out from the skull by more than
  `EAR_OUT_M` when the head is smoothed flat (a thin flap collapses onto the skull, the skull hardly
  moves), grown from the vertex that moved most beside and behind the eyes so nothing but the ear is taken. MPFB has no ear vertex group (its
  `mesh_metadata/basemesh_vertex_groups.json` lists only the helpers and sides), and its ear targets'
  displacements fall off into the scalp and jaw, so neither can say where an ear ends.
- **lashes**: MPFB's `helper-{l,r}-eyelashes-{1,2}` cards, the geometry MakeHuman's eyelash proxies ride.
  The bake deletes them, so each of their vertices is stored as a proxy fit: a triangle of body vertices,
  barycentric weights and an offset along the triangle's normal in units of the triangle's size.
- **brows**: a card on each brow ridge, laid on the skin from the eye (MPFB has eyebrow shape targets but
  no brow geometry), `BROW_COLS` along and `BROW_ROWS` across, stored the same way.

Each card vertex also carries its UV: V along the strands (0 at the root, 1 at the tip), U across them in
metres of the neutral base mesh (`humanform.brows` divides by the material's tile width).
"""

from __future__ import annotations

import json
import math
import os
import sys

import bpy  # noqa: F401  (run inside Blender: mathutils)
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "data", "face_regions.json"))
BASE = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender", "5.2", "extensions",
                    "user_default", "mpfb", "data", "3dobjs", "base.obj")
N_BODY = 13380
IPD_M = 0.064            # the neutral base mesh is scaled so its eye centres are this far apart
EAR_TARGETS = ("flap", "wing", "lobe")    # MPFB ear targets that bend the flap itself, not the ear as a whole
EAR_SHARE = 0.3                             # a vertex moved by more than this share of a target's most
BROW_COLS, BROW_ROWS = 16, 4
# the brow on the neutral face, from the eye centre (x lateral, z up), in eye radii R, and its height
# across in metres: head (medial), arch, tail
BROW_CURVE = [(-0.95, 1.30, 0.0105), (-0.3, 1.52, 0.0095), (0.55, 1.66, 0.0075), (1.35, 1.55, 0.0050),
              (1.95, 1.25, 0.0022)]
# the angle of the strands to the brow's line, degrees: nearly upright at the head, lying along it by the tail
BROW_ANGLE = [(0.0, 75.0), (0.25, 40.0), (0.6, 22.0), (1.0, 14.0)]
BROW_LIFT_M = 0.0004
LOWER_LASH = 0.45        # the lower lashes' length, as a share of MPFB's lower card


def parse(path):
    verts, faces, group = [], [], None
    groups = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("v "):
                x, y, z = (float(t) for t in line.split()[1:4])
                verts.append((x, -z, y))                   # MakeHuman: Y up, +Z forward -> Blender: Z up, -Y forward
            elif line.startswith("g "):
                group = line.split()[1]
            elif line.startswith("f "):
                f = tuple(int(t.split("/")[0]) - 1 for t in line.split()[1:])
                faces.append(f)
                groups.setdefault(group, []).append(f)
    return np.array(verts, np.float64), faces, groups


def proxy(bvh, co, body_faces, p):
    """(a, b, c, wa, wb, wc, off): p = sum w * corner + off * size * normal, the triangle nearest p."""
    loc, _n, fi, _d = bvh.find_nearest(Vector(p))
    f = body_faces[fi]
    best = None
    for tri in ((f[0], f[1], f[2]), (f[0], f[2], f[3])) if len(f) == 4 else ((f[0], f[1], f[2]),):
        a, b, c = (co[i] for i in tri)
        n = np.cross(b - a, c - a)
        area2 = float(np.linalg.norm(n))
        n = n / area2
        size = math.sqrt(area2 / 2)
        off = float(np.dot(p - a, n))
        q = p - off * n
        # barycentric of the projection
        v0, v1, v2 = b - a, c - a, q - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        d20, d21 = v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01
        wb = (d11 * d20 - d01 * d21) / den
        wc = (d00 * d21 - d01 * d20) / den
        wa = 1 - wb - wc
        worst = min(wa, wb, wc)
        if best is None or worst > best[0]:
            best = (worst, [int(tri[0]), int(tri[1]), int(tri[2]), round(float(wa), 6), round(float(wb), 6),
                            round(float(wc), 6), round(off / size, 6)])
    return best[1]


def rebuild(co, fit):
    a, b, c = co[fit[0]], co[fit[1]], co[fit[2]]
    n = np.cross(b - a, c - a)
    area2 = np.linalg.norm(n)
    return fit[3] * a + fit[4] * b + fit[5] * c + fit[6] * math.sqrt(area2 / 2) * n / area2


def ears(targets_dir):
    """{side: [base indices]}: the vertices MPFB's ear-shaping targets move (see the module docstring)."""
    import glob
    import gzip
    out = {}
    for side, mh in (("L", "l"), ("R", "r")):
        seen = set()
        for kind in EAR_TARGETS:
            for path in sorted(glob.glob(os.path.join(targets_dir, "ears", f"{mh}-ear-{kind}-*.target.gz"))):
                disp = {}
                with gzip.open(path, "rt") as fh:
                    for line in fh:
                        p = line.split()
                        if p and p[0].isdigit():
                            disp[int(p[0])] = math.sqrt(sum(float(x) ** 2 for x in p[1:4]))
                top = max(disp.values())
                seen.update(i for i, d in disp.items() if d > EAR_SHARE * top and i < N_BODY)
        out[side] = sorted(seen)
        print(f"ear {side}: {len(seen)} vertices")
    return out


def lash_cards(co, groups, bvh, body_faces, eyes, tile_u=1.0):
    cards = {}
    for side, mh in (("L", "l"), ("R", "r")):
        faces = []
        for k in (1, 2):
            faces += groups.get(f"helper-{mh}-eyelashes-{k}", [])
        faces = [tuple(f) for f in dict.fromkeys(faces)]
        verts = sorted({i for f in faces for i in f})
        local = {v: n for n, v in enumerate(verts)}
        pts = co[verts].copy()
        eye = eyes[side]
        # the lower lid's lashes are fine and short: MPFB's lower card is as long as the upper one, so it is
        # drawn in toward its roots on the skin
        lower = pts[:, 2] < eye[2]
        for k in np.nonzero(lower)[0]:
            root = np.array(tuple(bvh.find_nearest(Vector(pts[k]))[0]))
            pts[k] = root + (pts[k] - root) * LOWER_LASH
        # V: how far each vertex is from the skin (the lid), 0 at the root row, 1 at the tips, per lid
        dist = np.array([bvh.find_nearest(Vector(p))[3] for p in pts])
        # U: round the eye, in metres at the lash's own radius from the eye centre
        ang = np.arctan2(pts[:, 2] - eye[2], (pts[:, 0] - eye[0]) * (1 if side == "L" else -1))
        rad = np.hypot(pts[:, 0] - eye[0], pts[:, 2] - eye[2])
        u = ang * float(np.median(rad))
        v = np.zeros(len(pts))
        for lid in (lower, ~lower):
            lo, hi = float(dist[lid].min()), float(dist[lid].max())
            v[lid] = 0.03 + 0.94 * (dist[lid] - lo) / max(hi - lo, 1e-9)
        lo, hi = float(dist.min()), float(dist.max())
        fits = [proxy(bvh, co, body_faces, p) for p in pts]
        err = max(float(np.linalg.norm(rebuild(co, f) - p)) for f, p in zip(fits, pts))
        cards[side] = {"verts": [int(x) for x in verts], "fit": fits,
                       "faces": [[local[i] for i in f] for f in faces],
                       "uv": [[round(float(a), 6), round(float(b), 5)] for a, b in zip(u, v)]}
        print(f"lashes {side}: {len(verts)} vertices, {len(faces)} faces, lift {lo * 1000:.2f}..{hi * 1000:.2f} mm, "
              f"refit error {err * 1e6:.2f} um")
    return cards


def _interp(table, x):
    xs = [t[0] for t in table]
    return [float(np.interp(x, xs, [t[k] for t in table])) for k in range(1, len(table[0]))]


def brow_cards(co, bvh, body_faces, eyes, radius):
    cards = {}
    for side, sign in (("L", 1.0), ("R", -1.0)):
        e = eyes[side]
        s_knots = np.linspace(0.0, 1.0, len(BROW_CURVE))
        s = np.linspace(0.0, 1.0, BROW_COLS)
        xs = np.interp(s, s_knots, [c[0] for c in BROW_CURVE])
        zs = np.interp(s, s_knots, [c[1] for c in BROW_CURVE])
        hs = np.interp(s, s_knots, [c[2] for c in BROW_CURVE])
        # the centreline in the face's plane (x, z), smooth, then its normal in that plane
        cx = e[0] + sign * xs * radius
        cz = e[2] + zs * radius
        tx, tz = np.gradient(cx), np.gradient(cz)
        tl = np.hypot(tx, tz)
        tx, tz = tx / tl, tz / tl
        nx, nz = -tz * sign, tx * sign                 # up across the brow, on both sides
        grid = np.zeros((BROW_ROWS, BROW_COLS, 3))
        t = np.linspace(0.0, 1.0, BROW_ROWS)
        for i, ti in enumerate(t):
            for j in range(BROW_COLS):
                taper = 1.0
                x = cx[j] + nx[j] * (ti - 0.5) * hs[j] * taper
                z = cz[j] + nz[j] * (ti - 0.5) * hs[j] * taper
                loc, nrm, _fi, _d = bvh.ray_cast(Vector((x, e[1] - 0.3, z)), Vector((0, 1, 0)), 0.6)
                if loc is None:
                    raise RuntimeError(f"brow {side}: a ray at x={x:.4f} z={z:.4f} missed the face")
                grid[i, j] = np.array(tuple(loc)) + np.array(tuple(nrm)) * BROW_LIFT_M
        # arc length along the middle row, and U sheared so the strands lean along the brow
        mid = grid[BROW_ROWS // 2]
        arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(mid, axis=0), axis=1))])
        length = float(arc[-1])
        verts, uvs, fits = [], [], []
        for i, ti in enumerate(t):
            for j in range(BROW_COLS):
                ang = math.radians(_interp(BROW_ANGLE, s[j])[0])
                u = arc[j] - ti * hs[j] / math.tan(ang)
                verts.append(grid[i, j])
                uvs.append([round(float(u), 6), round(float(0.02 + 0.96 * ti), 5)])
                fits.append(proxy(bvh, co, body_faces, grid[i, j]))
        faces = []
        for i in range(BROW_ROWS - 1):
            for j in range(BROW_COLS - 1):
                q = [i * BROW_COLS + j, i * BROW_COLS + j + 1, (i + 1) * BROW_COLS + j + 1, (i + 1) * BROW_COLS + j]
                faces.append(q if sign > 0 else q[::-1])      # facing out of the face on both sides
        err = max(float(np.linalg.norm(rebuild(co, f) - p)) for f, p in zip(fits, verts))
        cards[side] = {"fit": fits, "faces": faces, "uv": uvs}
        print(f"brow {side}: {len(verts)} vertices, {len(faces)} faces, length {length * 1000:.1f} mm, "
              f"refit error {err * 1e6:.2f} um")
    return cards


def main():
    args = dict(a.split("=", 1) for a in sys.argv[sys.argv.index("--") + 1:]) if "--" in sys.argv else {}
    base = args.get("base", BASE)
    out = args.get("out", OUT)
    co, faces, groups = parse(base)
    body_faces = [f for f in faces if max(f) < N_BODY]
    eyes_raw = {s: co[sorted({i for f in groups[f"helper-{m}-eye"] for i in f})] for s, m in (("L", "l"), ("R", "r"))}
    ipd = float(np.linalg.norm(eyes_raw["L"].mean(axis=0) - eyes_raw["R"].mean(axis=0)))
    scale = IPD_M / ipd
    co = co * scale
    eyes = {s: v.mean(axis=0) * scale for s, v in eyes_raw.items()}
    if eyes["L"][0] < 0:
        raise RuntimeError("MPFB's left eye is not on +X")
    radius = float(np.mean([np.linalg.norm(eyes_raw[s] * scale - eyes[s], axis=1).mean() for s in eyes]))
    bvh = BVHTree.FromPolygons([Vector(c) for c in co[:N_BODY]], body_faces)
    top = float(co[:N_BODY, 2].max())
    head_mask = co[:N_BODY, 2] > float(np.mean([e[2] for e in eyes.values()])) - 0.12
    print(f"base: {len(co)} vertices, {len(body_faces)} body faces, scale {scale:.5f} m/unit, eye radius "
          f"{radius * 1000:.1f} mm, top {top:.3f} m")
    doc = {
        "_": "Generated by humanform/scripts/derive_face_regions.py from MPFB2's base.obj - do not edit. Vertex "
             "indices are base-mesh indices, which a baked humanform body keeps for its first 13380 vertices. "
             "A fit is [a, b, c, wa, wb, wc, off]: wa*A + wb*B + wc*C + off * sqrt(area ABC) * unit normal of ABC.",
        "n_body": N_BODY, "eye_radius_m": round(radius, 5),
        "ears": ears(os.path.join(os.path.dirname(os.path.dirname(base)), "targets")),
        "lashes": lash_cards(co, groups, bvh, body_faces, eyes),
        "brows": brow_cards(co, bvh, body_faces, eyes, radius),
    }
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, separators=(",", ":"))
        fh.write("\n")
    print("wrote", out, os.path.getsize(out), "bytes")


main()
