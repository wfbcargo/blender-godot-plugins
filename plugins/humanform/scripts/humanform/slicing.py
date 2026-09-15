"""Cut a body with a plane and get the loops a tape measure would wrap.

    loops = slicing.cut(b, point, normal)        # list of Loop, one per connected cross-section
    lp.points (N,3), lp.hull (M,2), lp.perimeter (convex hull = tape), lp.centre (3D),
    lp.radius (perimeter / 2 pi), lp.spans_x0 (crosses the midline)

A loop is a connected component of the segments the plane cuts through the faces, so two legs
are two loops and a torso with arms pressed against it is one.
"""

from __future__ import annotations

import math

import numpy as np
from mathutils import Vector


def _basis(normal):
    n = np.asarray(normal, dtype=np.float64)
    n = n / np.linalg.norm(n)
    helper = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(n, helper)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return n, u, v


def hull2d(p):
    """Monotone chain convex hull of (N,2) points, counter-clockwise."""
    pts = np.unique(np.round(p, 7), axis=0)
    if len(pts) < 3:
        return pts
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def half(seq):
        out = []
        for q in seq:
            while len(out) >= 2:
                a, b = out[-2], out[-1]
                if (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0]) <= 0:
                    out.pop()
                else:
                    break
            out.append(q)
        return out

    lower = half(pts)
    upper = half(pts[::-1])
    return np.array(lower[:-1] + upper[:-1])


class Loop:
    def __init__(self, points, origin, u, v, hull=True):
        self.points = points
        self.min = points.min(axis=0)
        self.max = points.max(axis=0)
        if not hull:
            # extents only: enough for "does it cross the midline" at a fraction of the cost
            self.hull, self.perimeter, self.area, self.radius = None, 0.0, 0.0, 0.0
            self.centre = Vector(points.mean(axis=0))
            return
        uv = np.stack([(points - origin) @ u, (points - origin) @ v], axis=1)
        self.hull = hull2d(uv)
        h = self.hull
        if len(h) >= 3:
            nxt = np.roll(h, -1, axis=0)
            self.perimeter = float(np.linalg.norm(nxt - h, axis=1).sum())
            cross = h[:, 0] * nxt[:, 1] - nxt[:, 0] * h[:, 1]
            area = cross.sum() / 2.0
            if abs(area) > 1e-12:
                cx = ((h[:, 0] + nxt[:, 0]) * cross).sum() / (6 * area)
                cy = ((h[:, 1] + nxt[:, 1]) * cross).sum() / (6 * area)
            else:
                cx, cy = h.mean(axis=0)
            self.area = float(abs(area))
        else:
            self.perimeter = 0.0
            self.area = 0.0
            cx, cy = uv.mean(axis=0) if len(uv) else (0.0, 0.0)
        self.centre = Vector(origin + u * cx + v * cy)
        self.radius = self.perimeter / (2 * math.pi)

    @property
    def spans_x0(self):
        return self.min[0] < 0.0 < self.max[0]

    @property
    def width_x(self):
        return float(self.max[0] - self.min[0])

    def __repr__(self):
        return f"Loop(perimeter={self.perimeter:.3f}, centre={tuple(round(c, 3) for c in self.centre)})"


def points(b, point, normal):
    """Just the cut points, unconnected - cheap, for profiles."""
    n = np.asarray(normal, dtype=np.float64)
    d = (b.co - np.asarray(point, dtype=np.float64)) @ n
    d[d == 0.0] = 1e-9
    e0, e1 = b.edges[:, 0], b.edges[:, 1]
    cross = (d[e0] > 0) != (d[e1] > 0)
    ce = np.nonzero(cross)[0]
    t = d[e0[ce]] / (d[e0[ce]] - d[e1[ce]])
    return b.co[e0[ce]] + (b.co[e1[ce]] - b.co[e0[ce]]) * t[:, None], ce, cross


def cut(b, point, normal, min_points=3, hull=True):
    n, u, v = _basis(normal)
    origin = np.asarray(point, dtype=np.float64)
    pts, ce, cross = points(b, origin, n)
    if len(ce) == 0:
        return []
    index = -np.ones(len(b.edges), np.int64)
    index[ce] = np.arange(len(ce))
    lc = cross[b.loop_edge]
    lf = b.loop_face[lc]
    le = index[b.loop_edge[lc]]
    order = np.argsort(lf, kind="stable")
    lf, le = lf[order], le[order]
    starts = np.flatnonzero(np.r_[True, lf[1:] != lf[:-1]])
    counts = np.diff(np.r_[starts, len(lf)])
    pairs = []
    for s, c in zip(starts.tolist(), counts.tolist()):
        for k in range(0, c - 1, 2):
            pairs.append((le[s + k], le[s + k + 1]))

    parent = list(range(len(ce)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, c in pairs:
        ra, rc = find(int(a)), find(int(c))
        if ra != rc:
            parent[ra] = rc
    roots = np.array([find(i) for i in range(len(ce))])
    loops = []
    for r in np.unique(roots):
        sel = pts[roots == r]
        if len(sel) >= min_points:
            loops.append(Loop(sel, origin, u, v, hull))
    loops.sort(key=lambda lp: -(lp.perimeter if hull else len(lp.points)))
    return loops


def horizontal(b, z, hull=True):
    return cut(b, (0.0, 0.0, z), (0.0, 0.0, 1.0), hull=hull)


def nearest(loops, p):
    p = Vector(p)
    return min(loops, key=lambda lp: (lp.centre - p).length) if loops else None
