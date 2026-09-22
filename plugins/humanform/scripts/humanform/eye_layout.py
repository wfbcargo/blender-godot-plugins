"""How many eyes a head has, where they sit and how big they are - for any creature (08 fantasy species, layer 2).

    rep = eye_layout.apply(human, {"count": 1, "size": 1.5})          # one median eye, 1.5x a human's
    rep = eye_layout.apply(human, {"count": 3})                         # the pair, and a third on the forehead
    rep = eye_layout.apply(human, {"at": [{"x": 0.0, "rise": 0.0, "size": 1.4},   # any arrangement
                                          {"x": 1.2, "rise": 0.02, "size": 0.6}], "keep_pair": False})
    eye_layout.validate(spec)                                           # [] or the problems, each with the fix

A human is `{"count": 2}` (or no spec at all), and nothing is changed. Everything else is three general moves on the
unbaked MPFB body, before the proportion warp so the warp carries them like any other head part:

- **close** a socket that no eye takes: MPFB's lids and the pocket behind them are relaxed to the membrane their
  rim spans (a harmonic fill over the orbit with the rim held), with a slight dome, so skin runs over where the eye
  was. Its eyeball, eye helper and lash cards go.
- **carve** a socket where a new eye sits: the skin inside an almond aperture (`aperture`, in eyeball radii) is
  laid just inside the eyeball, a lid band just outside it, blended back to the face over `blend` radii. The
  eyeball's surface is where the skin passes through it: that line is the lid margin.
- **place** an eyeball in each socket (humanform.eyes, sclera / iris / pupil, on the head bone) and a lash card
  on each new eye: the human upper and lower lash cards of the nearest side, moved and scaled from their own eye
  to the new one and re-fitted to the new lids (humanform.brows reads them off the body, `PROP`).

Sizes are eyeball diameters against the human eye MPFB fits (`size` 1 is a person's). Positions are in the head's
frame: `x` is the fraction of the human eye's distance from the midline (0 on the midline, 1 where a person's eye
is, negative on the right), `rise` metres up from the human eyes' line on a reference head (features.REF_HEAD),
scaled with this head. The paired eyes are kept (`keep_pair`) only when the arrangement has two or more eyes and
none of the placed ones is where they are.

The displacement is the shape key `KEY` (delta.py's prefix, so the library never stores it and mixed_coords leaves
it out), on top of the features' keys. Call it after `features.apply` and before `species.warp`.

Checks (`apply`'s report): every new eye's aperture has skin inside it and its lid band around it
(`aperture_verts`, `lid_verts`: a socket too small for the mesh fails), the closed socket's skin is out of the
old eyeball (`closed_depth_mm`), and no face of the head crosses another (`features.head_intersections`).
"""

from __future__ import annotations

import json
import math

import bpy
import numpy as np
from mathutils import Vector

from . import delta, features

KEY = delta.KEY_PREFIX + "eyes-layout"
PROP = "hf_eye_layout"
BODY_VERTS = delta.BODY_VERTS
SPEC_KEYS = {"count", "size", "rise", "spacing", "at", "keep_pair", "aperture", "blend", "protrude"}
AT_KEYS = {"x", "rise", "size"}
LIMITS = {"count": (1, 6), "size": (0.4, 3.0), "rise": (-0.03, 0.08), "spacing": (0.0, 2.0), "x": (-2.5, 2.5)}
APERTURE = (0.95, 0.50)      # half width, half height of the lid opening in eyeball radii. A person's is ~1.25 x 0.42
                             # of the ball, but its corners run back round the ball into the orbit; carved into a face
                             # an opening wider than the ball bared the ball's side (a first cyclops, seen 3/4)
PROTRUDE = None              # the eyeball's front ahead of the face around it (RING), in radii: None is the person's
                             # own eye on this head, measured (flush: -0.01 on MPFB's). 0.35 ahead of the nose bridge
                             # made the first cyclops' eye bulge and stare (0.40 ahead of its face ring, half the ball
                             # bare from the front against a person's 0.19)
RING = 1.6                   # the face around an eye: the skin this many radii from its centre, seen from the front
EXPOSE_VIEWS = (0, 35, 60)   # the yaws (degrees, the worse side) a new eye's bare share is measured from
EXPOSE_TOL = 0.25            # ... and it may exceed the person's eye on the same head by this share (+0.02) at most
# a person's eye as the game shows it, measured with `exposure` on baked MPFB bodies (study_man 0.190 / 0.32,
# smoke_petite 0.186 / 0.33, the drow 0.191): the bare share of the ball from the front and the opening's height over
# its width. A new eye is held to the person's own eye or this, whichever is more open: the cyclops' pre-warp man
# (40, muscular) measured 0.15 / 0.24, and a 1.5x copy of that read as a slit
EYE_NORM = {"bare": 0.19, "ratio": 0.32}
RATIO_TOL = 0.2              # ... and its opening's height over width within this share of theirs
PROTRUDE_TOL = 0.15          # ... nor stand further out of its face than theirs by more than this many radii
BLEND = 2.3                 # the carve fades back to the face by this many radii (in aperture units)
LID = (1.05, 1.18)           # the lid band's distance from the eyeball's centre, at the margin and at its outer edge
INSIDE = 0.94                # skin inside the aperture is laid this far out: hidden inside the eyeball
FORE_RISE = 0.035            # a third (fourth...) eye's default height over the pair, on the reference head
CLOSE_RADIUS = 1.8           # the closed orbit: skin within this many eyeball radii of the old eye
DOME = 0.15                  # the closed skin's dome, in eyeball radii


def validate(spec):
    """[] or the problems with an eye arrangement, each naming the range or the keys it takes."""
    if spec is None:
        return []
    if not isinstance(spec, dict):
        return [f"head.eyes must be a table ({', '.join(sorted(SPEC_KEYS))}), not {type(spec).__name__}"]
    out = [f"head.eyes: unknown key {k!r} - it takes {', '.join(sorted(SPEC_KEYS))}" for k in sorted(set(spec) - SPEC_KEYS)]
    for k in ("count", "size", "rise", "spacing"):
        v = spec.get(k)
        if v is None:
            continue
        lo, hi = LIMITS[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
            out.append(f"head.eyes.{k} = {v!r}: a number in {lo}..{hi}")
    if "count" in spec and isinstance(spec["count"], float) and not float(spec["count"]).is_integer():
        out.append(f"head.eyes.count = {spec['count']!r}: a whole number")
    for i, a in enumerate(spec.get("at") or []):
        if not isinstance(a, dict):
            out.append(f"head.eyes.at[{i}] must be a table of x, rise, size")
            continue
        out += [f"head.eyes.at[{i}]: unknown key {k!r} - x, rise, size" for k in sorted(set(a) - AT_KEYS)]
        for k in AT_KEYS & set(a):
            lo, hi = LIMITS["rise" if k == "rise" else k]
            if not isinstance(a[k], (int, float)) or not lo <= a[k] <= hi:
                out.append(f"head.eyes.at[{i}].{k} = {a[k]!r}: a number in {lo}..{hi}")
    ap = spec.get("aperture")
    pr = spec.get("protrude")
    if pr is not None and (not isinstance(pr, (int, float)) or not -0.5 <= pr <= 0.9):
        out.append(f"head.eyes.protrude = {pr!r}: the eyeball's front ahead of the face around it, in its radii, "
                   "-0.5..0.9 (leave it out: a person's eye on this head is measured, about 0)")
    if ap is not None and (not isinstance(ap, (list, tuple)) or len(ap) != 2
                           or not all(isinstance(v, (int, float)) and 0.3 <= v <= 2.0 for v in ap)):
        out.append(f"head.eyes.aperture = {ap!r}: [half width, half height] in eyeball radii, each 0.3..2.0")
    return out


def is_human(spec):
    """True when the arrangement is a person's two eyes (nothing to do)."""
    if not spec:
        return True
    return (int(spec.get("count", 2)) == 2 and not spec.get("at") and float(spec.get("size", 1.0)) == 1.0
            and float(spec.get("spacing", 1.0)) == 1.0 and float(spec.get("rise", 0.0)) == 0.0)


def plan(spec):
    """The arrangement as {"keep_pair": bool, "eyes": [{"x", "rise", "size"}]} (the new eyes only)."""
    spec = dict(spec or {})
    size = float(spec.get("size", 1.0))
    if spec.get("at"):
        eyes = [{"x": float(a.get("x", 0.0)), "rise": float(a.get("rise", 0.0)), "size": float(a.get("size", size))}
                for a in spec["at"]]
        keep = bool(spec.get("keep_pair", False))
        return {"keep_pair": keep, "eyes": eyes}
    n = int(spec.get("count", 2))
    rise = float(spec.get("rise", 0.0))
    if n == 1:
        return {"keep_pair": False, "eyes": [{"x": 0.0, "rise": rise, "size": size}]}
    if n == 2:
        sp = float(spec.get("spacing", 1.0))
        return {"keep_pair": False, "eyes": [{"x": sgn * sp, "rise": rise, "size": size} for sgn in (1.0, -1.0)]}
    # the pair kept, the rest stacked up the forehead's midline
    extra = []
    for k in range(n - 2):
        extra.append({"x": 0.0, "rise": (spec.get("rise") if "rise" in spec else FORE_RISE) * (1 + 0.8 * k),
                      "size": size})
    return {"keep_pair": bool(spec.get("keep_pair", True)), "eyes": extra}


# ------------------------------------------------------------------------------------------------ the surface

def _full(ob, skip=()):
    """Every vertex as the body is drawn: the basis and every shape key at its value, hfd: keys included (keys whose
    names start with one of `skip` left out)."""
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    keys = me.shape_keys
    if keys is None:
        me.vertices.foreach_get("co", co)
        return co.reshape(n, 3)
    basis = keys.key_blocks[0]
    basis.data.foreach_get("co", co)
    co = co.reshape(n, 3)
    out = co.copy()
    tmp = np.empty(n * 3)
    cache = {basis.name: co}
    for kb in keys.key_blocks[1:]:
        if kb.mute or abs(kb.value) < 1e-9 or (skip and kb.name.startswith(tuple(skip))):
            continue
        kb.data.foreach_get("co", tmp)
        rel = kb.relative_key
        if rel.name not in cache:
            r = np.empty(n * 3)
            rel.data.foreach_get("co", r)
            cache[rel.name] = r.reshape(n, 3)
        d = tmp.reshape(n, 3) - cache[rel.name]
        if kb.vertex_group:
            vg = ob.vertex_groups.get(kb.vertex_group)
            if vg is not None:
                w = np.zeros(n)
                for v in me.vertices:
                    for e in v.groups:
                        if e.group == vg.index:
                            w[v.index] = e.weight
                d = d * w[:, None]
        out += kb.value * d
    return out


def _group(ob, name):
    g = ob.vertex_groups.get(name)
    if g is None:
        return np.zeros(0, int)
    return np.array([v.index for v in ob.data.vertices if any(e.group == g.index for e in v.groups)], int)


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _close(P, faces, c, r, sgn, report):
    """Relax one orbit to the skin its rim spans: harmonic over the region, the rim held, and a dome."""
    d = np.linalg.norm(P - c, axis=1)
    region = (d < CLOSE_RADIUS * r) & (np.sign(P[:, 0]) == sgn) & (np.abs(P[:, 0]) > 0.003)
    rows, cols = delta.neighbours(faces)
    inside = region.copy()
    # the rim: region vertices with a neighbour outside it
    outside_nb = np.bincount(rows, weights=(~region[cols]).astype(float), minlength=BODY_VERTS) > 0
    free = inside & ~outside_nb
    deg = np.bincount(rows, minlength=BODY_VERTS).astype(float)
    Q = P.copy()
    for _ in range(900):
        avg = np.stack([np.bincount(rows, weights=Q[cols, k], minlength=BODY_VERTS) for k in range(3)], axis=1)
        avg /= np.maximum(deg, 1)[:, None]
        Q[free] = avg[free]
    # dome: out along the rim's mean outward direction, most at the middle
    rim = inside & outside_nb
    out_dir = np.array([0.35 * sgn, -1.0, 0.0])
    out_dir /= np.linalg.norm(out_dir)
    rr = np.clip(np.linalg.norm(Q[free] - c, axis=1) / (CLOSE_RADIUS * r), 0, 1)
    Q[free] += out_dir * (DOME * r * (1 - rr ** 2))[:, None]
    # soften the rim: a few smoothing passes over a band either side of it, so the closed orbit has no crease
    band = (d < (CLOSE_RADIUS + 0.5) * r) & (np.sign(P[:, 0]) == sgn) & (np.abs(P[:, 0]) > 0.003)
    band_free = band & ~(np.bincount(rows, weights=(~band[cols]).astype(float), minlength=BODY_VERTS) > 0)
    for _ in range(10):
        avg = np.stack([np.bincount(rows, weights=Q[cols, k], minlength=BODY_VERTS) for k in range(3)], axis=1)
        avg /= np.maximum(deg, 1)[:, None]
        Q[band_free] = 0.5 * Q[band_free] + 0.5 * avg[band_free]
    # how far in front of the old eyeball's front the closed skin now lies (it must cover where the eye was)
    front = c[1] - r
    report["closed_depth_mm"] = round(float((front - Q[free, 1].max()) * 1000), 2) if free.any() else None
    report["closed_verts"] = int(free.sum())
    report["rim_verts"] = int(rim.sum())
    return Q


def _carve(P, c, R, ap, blend, report):
    """The socket for one new eye (centre c, radius R): inside the aperture skin just inside the ball, a lid band
    just outside, blended back to the face."""
    a, b = ap[0] * R, ap[1] * R
    dx, dz = P[:, 0] - c[0], P[:, 2] - c[2]
    bb = np.where(dz > 0, b * 1.1, b * 0.9)          # the upper lid arches higher than the lower
    q = np.sqrt((dx / a) ** 2 + (dz / bb) ** 2)
    front = (P[:, 1] - c[1]) < 0.6 * R                 # the face in front of the eye, not the head behind it
    near = front & (q < blend) & (np.linalg.norm(P - c, axis=1) < 3.2 * R)
    v = P - c
    dist = np.linalg.norm(v, axis=1)
    dirs = v / np.maximum(dist, 1e-9)[:, None]
    # the skin's distance from the ball's centre rises smoothly through the eyeball's radius at q = 1, so the line
    # where it passes through the ball (the lid margin) follows the aperture between vertices, not their jagged
    # edges (a step from inside to outside at q = 1 left a ragged corner)
    t_in = _smoothstep((q - 0.75) / 0.5)
    t_lid = _smoothstep((q - 1.0) / 0.45)
    target_r = R * (INSIDE + (LID[0] + (LID[1] - LID[0]) * t_lid - INSIDE) * t_in)
    target = c + dirs * target_r[:, None]
    w = np.where(q < 1.45, 1.0, 1.0 - _smoothstep((q - 1.45) / max(blend - 1.45, 1e-6)))
    w = w * near
    Q = P + (target - P) * w[:, None]
    report.setdefault("aperture_verts", []).append(int((near & (q < 1.0)).sum()))
    report.setdefault("lid_verts", []).append(int((near & (q >= 1.0) & (q < 1.45)).sum()))
    return Q


# ------------------------------------------------------------------------------------------------ lash cards

def _tris(faces):
    return np.concatenate([faces[:, [0, 1, 2]], faces[:, [0, 2, 3]]])


def _refit(points, co, tris):
    """Card points as brows' proxy fits on the body's triangles: [a, b, c, wa, wb, wc, offset]."""
    from mathutils.bvhtree import BVHTree
    tree = BVHTree.FromPolygons([Vector(p) for p in co[:BODY_VERTS]], [tuple(int(i) for i in t) for t in tris])
    rows = []
    for p in points:
        loc, _n, fi, _d = tree.find_nearest(Vector(p))
        ia, ib, ic = (int(i) for i in tris[fi])
        A, B, C = co[ia], co[ib], co[ic]
        n = np.cross(B - A, C - A)
        area2 = float(np.linalg.norm(n))
        n = n / max(area2, 1e-12)
        L = np.array(loc)
        # barycentric of the nearest point
        v0, v1, v2 = B - A, C - A, L - A
        d00, d01, d11, d20, d21 = v0 @ v0, v0 @ v1, v1 @ v1, v2 @ v0, v2 @ v1
        den = max(d00 * d11 - d01 * d01, 1e-18)
        wb = (d11 * d20 - d01 * d21) / den
        wc = (d00 * d21 - d01 * d20) / den
        wa = 1.0 - wb - wc
        off = float((np.asarray(p) - L) @ n) / max(math.sqrt(area2 / 2), 1e-9)
        rows.append([ia, ib, ic, round(wa, 6), round(wb, 6), round(wc, 6), round(off, 6)])
    return rows


def _lash_cards(co_before, co_after, faces, eyes_old, new, ap):
    """For each new eye, lash cards carried from the human eyes and fitted to its lids. Each card's roots are
    laid on this eye's lid margin - the aperture `ap`'s almond, nasal corner to outer corner - and every other
    point keeps its offset from its nearest root, scaled with the eye. An eye on the midline takes two cards, the
    left eye's on its left half and the right eye's on its right, nasal corners meeting in the middle, so it is
    symmetric. (Scaled whole, the human roots fell inside the larger opening and crossed the iris; scaled by the
    opening's stretch, the lashes stood up like a brush; one card alone was lopsided - the first cyclops.)"""
    from . import brows
    d = brows.regions().get("lashes")
    if not d:
        return []
    tris = _tris(faces)
    out = []
    for e in new:
        R = e["radius"]
        A, Bu, Bl = ap[0] * R, ap[1] * 1.1 * R, ap[1] * 0.9 * R
        median = abs(e["centre"][0]) < 0.25 * R
        if median:
            jobs = [("L", 0.0, A), ("R", 0.0, -A)]           # (source, nasal x, outer x) on the new eye
        else:
            sgn = 1.0 if e["centre"][0] >= 0 else -1.0
            jobs = [("L" if sgn > 0 else "R", -sgn * A, sgn * A)]
        for side, x_nasal, x_outer in jobs:
            card = d[side]
            p, _, _ = brows._rebuild(co_before, card["fit"])
            c0, r0 = eyes_old[side]
            rel = p - c0
            roots = np.asarray(card["uv"], float)[:, 1] < 0.2
            ri = np.flatnonzero(roots)
            rr = rel[ri]
            lat = rr[:, 0] * (1.0 if side == "L" else -1.0)       # grows toward the outer corner
            t = (lat - lat.min()) / max(float(lat.max() - lat.min()), 1e-9)    # 0 nasal .. 1 outer
            x = x_nasal + t * (x_outer - x_nasal)
            s = np.sqrt(np.clip(1.0 - (x / A) ** 2, 0.0, 1.0))
            z = np.where(rr[:, 2] > 0, Bu * s, -Bl * s)
            y = -np.sqrt(np.maximum((1.02 * R) ** 2 - x ** 2 - z ** 2, (0.2 * R) ** 2))
            root_new = np.stack([x, y, z], axis=1)
            near = np.argmin(np.linalg.norm(rel[:, None, :] - rr[None, :, :], axis=2), axis=1)
            k = R / r0 * (0.5 if median else 1.0) ** 0.5            # half a lid's cards on half its width
            q = np.asarray(e["centre"]) + root_new[near] + (rel - rr[near]) * k
            out.append({"fit": _refit(q, co_after, tris), "faces": card["faces"], "uv": card["uv"], "from": side})
    return out


# ------------------------------------------------------------------------------------------------ apply

def apply(human, spec, iris=None):
    """Arrange the eyes of an unbaked MPFB body (see the module docstring). Returns a report; {"human": True} when
    the spec is a person's pair and nothing was done."""
    human = bpy.data.objects[human] if isinstance(human, str) else human
    problems = validate(spec)
    if problems:
        raise ValueError("; ".join(problems))
    if is_human(spec):
        return {"human": True}
    problem = delta.check_topology(human)
    if problem:
        raise ValueError(problem)
    if human.data.shape_keys is None:
        human.shape_key_add(name="Basis", from_mix=False)
    old = human.data.shape_keys.key_blocks.get(KEY)
    if old is not None:
        human.shape_key_remove(old)
    pl = plan(spec)
    co = _full(human)
    faces = delta.body_faces(human)
    nrm = delta.vertex_normals(co, faces)
    F = features.frame(human, co, nrm, faces)
    s = F.scale
    eyes_old = {}
    for side in ("l", "r"):
        idx = _group(human, f"helper-{side}-eye")
        pts = co[idx]
        c = pts.mean(axis=0)
        eyes_old["L" if c[0] > 0 else "R"] = (c, float(np.linalg.norm(pts - c, axis=1).mean()))
    r_h = (eyes_old["L"][1] + eyes_old["R"][1]) / 2
    ey = (eyes_old["L"][0][1] + eyes_old["R"][0][1]) / 2
    report = {"plan": pl, "head_scale": round(s, 3)}

    P = co[:BODY_VERTS].copy()
    if not pl["keep_pair"]:
        for side, sgn in (("L", 1.0), ("R", -1.0)):
            rep = {}
            P = _close(P, faces, eyes_old[side][0], eyes_old[side][1], sgn, rep)
            report[f"closed_{side}"] = rep
    # the rule every new eye is held to: a person's eye on this very head, measured before anything moves - how far
    # its ball stands out of the face around it and how much of it the lids leave bare from the front, 3/4, and 60
    # the person's own eye, before the head features: a brow ridge or heavy brow pulls the lids down, and held to
    # that the cyclops' eye came out a slit (lids 0.22 as high as wide against a person's 0.33)
    plain = _full(human, skip=(features.KEY_PREFIX, features.DELTA_PREFIX))
    human_eye = exposure(plain[:BODY_VERTS], faces, *eyes_old["L"])
    report["human_eye"] = human_eye
    # the opening's shape is the person's (their lids' half width and half height over the ball, seen from the
    # front); its size is then solved below. A fixed almond (0.95 x 0.50) solved to their bare share came out an
    # iris-wide slit with no white either side - a squint, not an eye
    ap0 = tuple(spec.get("aperture") or human_eye.get("opening") or APERTURE)
    blend = float(spec.get("blend", BLEND))
    protrude = spec.get("protrude", PROTRUDE)
    protrude = human_eye["protrude"] if protrude is None else float(protrude)
    new = []
    for e in pl["eyes"]:
        R = r_h * e["size"]
        x = e["x"] * F.eye_x
        z = F.eye_z + e["rise"] * s
        # the ball's front stands `protrude` radii ahead of the face around it (the face as it was: RING radii out,
        # seen from the front; a closed orbit beside it has moved, the brow and cheeks have not)
        ring = []
        for a in np.linspace(0.0, 2 * math.pi, 24, endpoint=False):
            hit = F.tree.ray_cast(Vector((x + RING * R * math.cos(a), -0.5, z + RING * R * math.sin(a))),
                                  Vector((0.0, 1.0, 0.0)), 1.0)[0]
            if hit is not None:
                ring.append(float(hit.y))
        y_face = float(np.mean(ring)) if ring else ey - r_h
        new.append({"centre": np.array([x, y_face - protrude * R + R, z]), "radius": R})
    P_closed = P

    def carve_all(k, rep):
        Q = P_closed
        for e in new:
            Q = _carve(Q, e["centre"], e["radius"], (ap0[0] * k[0], ap0[1] * k[1]), blend, rep)
        return Q

    def bare(Q):
        return [exposure(Q, faces, e["centre"], e["radius"]) for e in new]
    # the opening: the person's share of the ball left bare and their lids' shape (the opening's height over its
    # width), both relative, so the opening grows with the eye - a 1.5x eye gets a 1.5x opening. Solved on the
    # carve's almond by multiplicative rounds (an aperture the spec gives is taken as it is). Matching the opening's
    # size in radii instead let a heavy brow's squint through, and gave a wide slit
    k = [1.0, 1.0]
    f_want = max(human_eye["bare"]["0"], EYE_NORM["bare"])
    r_want = max(human_eye.get("ratio") or 0.0, EYE_NORM["ratio"])
    report["eye_target"] = {"bare": round(f_want, 3), "ratio": round(r_want, 3)}
    if not spec.get("aperture") and r_want:
        for _ in range(7):
            got = bare(carve_all(k, {}))
            f = float(np.mean([g["bare"]["0"] for g in got]))
            r = float(np.mean([g.get("ratio") or r_want for g in got]))
            a, q = math.sqrt(f_want / max(f, 1e-3)), math.sqrt(r_want / max(r, 1e-3))
            k = [float(np.clip(k[0] * a / q, 0.4, 2.5)), float(np.clip(k[1] * a * q, 0.4, 2.5))]
    ap = (ap0[0] * k[0], ap0[1] * k[1])
    P = carve_all(k, report)
    report["aperture"] = [round(v, 3) for v in ap]
    report["exposure"] = bare(P)
    report["eyes"] = [{"centre": [round(float(v), 4) for v in e["centre"]], "radius_mm": round(e["radius"] * 1000, 2)}
                      for e in new]

    # helpers ride with the eyes: an eye's helper ball and lash helpers go to its new eye, or shrink out of sight
    full_new = co.copy()
    full_new[:BODY_VERTS] = P
    if not pl["keep_pair"]:
        for k, (side, tag) in enumerate((("L", "l"), ("R", "r"))):
            c0, r0 = eyes_old[side]
            if k < len(new):
                c1, r1 = new[k]["centre"], new[k]["radius"]
            else:
                c1, r1 = (new[0]["centre"], 0.3 * new[0]["radius"]) if new else (c0, 0.3 * r0)
            for g in (f"helper-{tag}-eye", f"helper-{tag}-eyelashes-1", f"helper-{tag}-eyelashes-2"):
                idx = _group(human, g)
                if len(idx):
                    full_new[idx] = c1 + (co[idx] - c0) * (r1 / r0)

    # the key: what moved, over the basis
    me = human.data
    n = len(me.vertices)
    basis = me.shape_keys.key_blocks[0]
    b = np.empty(n * 3)
    basis.data.foreach_get("co", b)
    kb = human.shape_key_add(name=KEY, from_mix=False)
    kb.data.foreach_set("co", (b.reshape(n, 3) + (full_new - co)).ravel())
    kb.relative_key = basis
    kb.slider_min = 0.0
    kb.value = 1.0
    me.update()
    report["key"] = KEY
    report["moved_mm"] = round(float(np.linalg.norm(full_new - co, axis=1).max()) * 1000, 2)

    # the eyeballs: the kept pair and every new eye
    from . import eyes as _eyes
    places = []
    if pl["keep_pair"]:
        places += [eyes_old["L"], eyes_old["R"]]
    places += [(e["centre"], e["radius"]) for e in new]
    _eyes.add(human, iris=iris, places=places)
    # the lash cards brows lays on the baked body: none for a closed side, one pair per new eye
    # laid on the lid margin the eye actually shows (its opening seen from the front), not on the carve's almond: wider
    # than the ball, that put the cards' corners behind it, standing up as bars either side of the eye
    ops = [e.get("opening") for e in report["exposure"] if e.get("opening")]
    lash_ap = (min(ap[0], 1.02 * max(o[0] for o in ops)), min(ap[1], 1.1 * max(o[1] for o in ops))) if ops else ap
    lash = _lash_cards(co, full_new, faces, eyes_old, new, lash_ap)
    human[PROP] = json.dumps({"hide_lashes": [] if pl["keep_pair"] else ["L", "R"], "lashes": lash,
                              "eyes": report["eyes"], "count": len(places)})
    report["count"] = len(places)
    report["lash_cards"] = len(lash)
    report["intersections"] = features.head_intersections(human, faces)
    fails = []
    bad = [i for i, (a, l) in enumerate(zip(report["aperture_verts"], report["lid_verts"])) if a < 3 or l < 6]
    if bad:
        fails.append(f"eye(s) {bad}: the mesh has too few vertices in the aperture or the lid band "
                     f"(aperture {report['aperture_verts']}, lids {report['lid_verts']}) - make the eye bigger "
                     "(size) or open it wider (aperture)")
    target = dict(human_eye, bare=dict(human_eye["bare"], **{"0": report.get("eye_target", {}).get(
        "bare", human_eye["bare"]["0"])}), ratio=report.get("eye_target", {}).get("ratio", human_eye.get("ratio")))
    stare = exposure_problems(report["exposure"], target)
    if stare:
        report["stare"] = stare
        fails.append("; ".join(stare))
    if fails:
        report["fail"] = "; ".join(fails)
    return report


def exposure(P, faces, c, R, views=EXPOSE_VIEWS):
    """How an eyeball (centre `c`, radius `R`) sits in the skin `P` (body vertices, hm08 `faces`): `protrude`, its
    front ahead of the face around it (the skin RING radii from its centre, seen from the front) in radii, and
    `bare`, per yaw in `views` (the worse side), the share of the rays that would meet the ball that meet it before
    any skin - what the lids leave uncovered. A person's eye on MPFB: protrude -0.01, bare 0.19 / 0.15 / 0.09."""
    from mathutils.bvhtree import BVHTree
    c = np.asarray(c, float)
    tree = BVHTree.FromPolygons([Vector(v) for v in np.asarray(P, float)[:BODY_VERTS]],
                                [tuple(int(i) for i in t) for t in _tris(np.asarray(faces))])
    ring = []
    for a in np.linspace(0.0, 2 * math.pi, 24, endpoint=False):
        hit = tree.ray_cast(Vector((c[0] + RING * R * math.cos(a), c[1] - 1.0, c[2] + RING * R * math.sin(a))),
                            Vector((0.0, 1.0, 0.0)), 2.0)[0]
        if hit is not None:
            ring.append(float(hit.y))
    out = {"protrude": round(float(np.mean(ring) - (c[1] - R)) / R, 3) if ring else None, "bare": {}}
    C = Vector(c)
    grid = np.linspace(-1.1 * R, 1.1 * R, 73)
    for yaw in views:
        worst = 0.0
        for sgn in ((1.0,) if yaw == 0 else (1.0, -1.0)):
            a = math.radians(yaw * sgn)
            cam = C + Vector((math.sin(a), -math.cos(a), 0.0)) * (25 * R)
            right = Vector((math.cos(a), math.sin(a), 0.0))
            ball = seen = 0
            su, sw = [], []
            for u in grid:
                for w in grid:
                    d = (C + right * float(u) + Vector((0.0, 0.0, float(w))) - cam).normalized()
                    oc = cam - C
                    bq = oc.dot(d)
                    disc = bq * bq - (oc.dot(oc) - R * R)
                    if disc < 0:
                        continue
                    ball += 1
                    t_ball = -bq - math.sqrt(disc)
                    hit = tree.ray_cast(cam, d, 50 * R)
                    if hit[0] is None or hit[3] > t_ball:
                        seen += 1
                        su.append(abs(float(u)))
                        sw.append(float(w))
            worst = max(worst, seen / max(ball, 1))
            if yaw == 0 and su:
                # the opening from the front: half its width and half its height in radii, and its shape
                w_half, h_half = max(su) / R, (max(sw) - min(sw)) / (2 * R)
                out["opening"] = [round(w_half, 3), round(h_half, 3)]
                out["ratio"] = round(h_half / max(w_half, 1e-6), 3)
        out["bare"][str(yaw)] = round(worst, 3)
    return out


def exposure_problems(eyes_exposure, human):
    """[] or why a new eye stares: bare past the person's eye on the same head (EXPOSE_TOL) at any view, or standing
    out of its face further (PROTRUDE_TOL). Each problem names the numbers and the fix."""
    out = []
    for i, e in enumerate(eyes_exposure):
        for yaw, v in e["bare"].items():
            limit = human["bare"][yaw] * (1 + EXPOSE_TOL) + 0.02
            if v > limit:
                out.append(f"eye {i} is {v:.0%} bare seen from {yaw} deg against a person's {human['bare'][yaw]:.0%} "
                           f"(limit {limit:.0%}) - the lids cover too little: narrow the aperture or leave it out")
        f, hf = e["bare"].get("0"), human["bare"].get("0")
        if f is not None and hf and f < hf * (1 - EXPOSE_TOL) - 0.02:
            out.append(f"eye {i} is {f:.0%} bare from the front against a person's {hf:.0%} - the lids cover too "
                       "much: it squints (open the aperture or leave it out)")
        r, hr = e.get("ratio"), human.get("ratio")
        if r and hr and not hr * (1 - RATIO_TOL) <= r <= hr * (1 + RATIO_TOL):
            out.append(f"eye {i}'s opening is {r:.2f} as high as wide against a person's {hr:.2f} - "
                       f"{'a slit' if r < hr else 'a stare'}: set the aperture's shape as theirs or leave it out")
        pr, hpr = e.get("protrude"), human.get("protrude")
        if pr is not None and hpr is not None and pr > hpr + PROTRUDE_TOL:
            out.append(f"eye {i} stands {e['protrude']:.2f} radii out of its face against a person's "
                       f"{human['protrude']:.2f} - it bulges: lower protrude or leave it out")
    return out
