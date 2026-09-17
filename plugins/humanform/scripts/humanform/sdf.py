"""Signed distance primitives and smooth blends, evaluated at points in plain numpy.

The sculpting half of grungist-creek's `assets/wardrobe/sdf_sculpt.py` (which also extracts a
surface); here the field is only ever evaluated at a body's own vertices, so there is no meshing.
Distances are negative inside.

    s = sdf.Sculpt()
    s.add(sdf.ellipsoid((0.08, -0.1, 1.23), (0.09, 0.07, 0.04), rot=m), k=0.01)
    s.cut(sdf.capsule((0, -0.1, 1.15), (0, -0.1, 1.33), 0.01), k=0.006)
    d = s.field(points)                                # (N,) signed distances

A primitive is `(fn, (lo, hi))`: `fn(points Nx3) -> distances N` and its bounding box, outside of
which (grown by its blend radius and MARGIN) it is not evaluated.
"""

from __future__ import annotations

import numpy as np

MARGIN = 0.03
FAR = 1e3


def _v(a):
    return np.asarray(a, dtype=np.float64)


def sphere(c, r):
    c = _v(c)
    return (lambda p: np.linalg.norm(p - c, axis=1) - r), (c - r, c + r)


def ellipsoid(c, radii, rot=None):
    """Quilez's bound: exact on the surface and near it. `rot` is a 3x3 whose columns are the
    ellipsoid's axes in world space (radii[i] along column i)."""
    c, r = _v(c), _v(radii)
    m = None if rot is None else _v(rot)

    def fn(p):
        q = p - c
        if m is not None:
            q = q @ m                      # components along each column
        k0 = np.linalg.norm(q / r, axis=1)
        k1 = np.linalg.norm(q / (r * r), axis=1)
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)
    ext = r.max()
    return fn, (c - ext, c + ext)


def capsule(a, b, ra, rb=None):
    """A round cone from a (radius ra) to b (radius rb): exact."""
    a, b = _v(a), _v(b)
    rb = ra if rb is None else rb
    ba = b - a
    l2 = float(ba @ ba)
    rr = ra - rb
    a2 = l2 - rr * rr
    il2 = 1.0 / l2

    def fn(p):
        pa = p - a
        y = pa @ ba
        z = y - l2
        x = pa * l2 - np.outer(y, ba)
        x2 = np.einsum("ij,ij->i", x, x)
        y2 = y * y * l2
        z2 = z * z * l2
        k = np.sign(rr) * rr * rr * x2
        out = np.empty(len(p))
        c1 = np.sign(z) * a2 * z2 > k
        c2 = np.sign(y) * a2 * y2 < k
        c3 = ~(c1 | c2)
        out[c1] = np.sqrt(x2[c1] + z2[c1]) * il2 - rb
        out[c2] = np.sqrt(x2[c2] + y2[c2]) * il2 - ra
        out[c3] = (np.sqrt(x2[c3] * a2 * il2) + y[c3] * rr) * il2 - ra
        return out
    r = max(ra, rb)
    return fn, (np.minimum(a, b) - r, np.maximum(a, b) + r)


def mirrored_x(prim):
    """The primitive and its mirror across X = 0, as one: evaluated at |x| (a body's left and right)."""
    fn, (lo, hi) = prim

    def mfn(p):
        q = p.copy()
        q[:, 0] = np.abs(q[:, 0])
        return fn(q)
    ext = max(abs(lo[0]), abs(hi[0]))
    lo2, hi2 = lo.copy(), hi.copy()
    lo2[0], hi2[0] = (-hi[0] if lo[0] >= 0 else -ext), ext
    return mfn, (lo2, hi2)


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


class Sculpt:
    """Adds (smooth union) and cuts (smooth subtraction), applied in order."""

    def __init__(self):
        self.ops = []                     # (kind, fn, lo, hi, k)

    def add(self, prim, k=0.01):
        for fn, (lo, hi) in (prim if isinstance(prim, list) else [prim]):
            self.ops.append(("add", fn, _v(lo), _v(hi), k))
        return self

    def cut(self, prim, k=0.005):
        for fn, (lo, hi) in (prim if isinstance(prim, list) else [prim]):
            self.ops.append(("cut", fn, _v(lo), _v(hi), k))
        return self

    def field(self, p):
        p = _v(p)
        d = np.full(len(p), FAR)
        for kind, fn, lo, hi, k in self.ops:
            g = max(k, MARGIN)
            m = np.all((p >= lo - g) & (p <= hi + g), axis=1)
            if not m.any():
                continue
            idx = np.nonzero(m)[0]
            dp = fn(p[idx])
            cur = d[idx]
            d[idx] = smin(cur, dp, k) if kind == "add" else smax(cur, -dp, k)
        return d
