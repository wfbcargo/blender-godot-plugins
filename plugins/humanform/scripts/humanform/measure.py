"""Measure a human body and judge it against a proportion preset.

    rep = measure.run("Nora", preset="realistic", sex="female", out_dir=r"C:/scratch/nora")
    print(measure.summarize(rep))

`measure.measurements(ob)` returns raw numbers (metres, degrees); `measure.check(m, preset,
sex)` turns them into findings with a status - pass, warn (outside the tolerance) or fail
(outside twice the tolerance) - and the ladder layer each belongs to. Everything is measured
in the rig's rest pose, on the evaluated mesh.
"""

from __future__ import annotations

import json
import math
import os

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import sys

from . import body as _body
from . import slicing

_pkg = sys.modules[__package__]

LAYER = {"proportion": "L1", "pose": "L2", "mesh": "L2", "feature": "L4", "surface": "L5", "rig": "L7"}


def _avg(b, name):
    l, r = b.mark(name + ".L"), b.mark(name + ".R")
    if l is None and r is None:
        return None, None
    if l is None or r is None:
        return (r if l is None else l), None
    mid = (l + r.copy()) * 0.5
    return mid, (l, r)


def _pair_len(b, a, c):
    out = []
    for s in ("L", "R"):
        p, q = b.mark(f"{a}.{s}"), b.mark(f"{c}.{s}")
        if p is not None and q is not None:
            out.append((p - q).length)
    return sum(out) / len(out) if out else None


def _front_profile(b, z0, z1, fwd, half_width=0.02, step=0.004):
    zs = np.arange(z0, z1, step)
    f = np.full(len(zs), np.nan)
    for i, z in enumerate(zs):
        pts, _, _ = slicing.points(b, (0, 0, z), (0, 0, 1))
        mid = pts[np.abs(pts[:, 0]) < half_width]
        if len(mid):
            f[i] = float((mid[:, :2] @ np.array([fwd.x, fwd.y])).max())
    return zs, f


def _components(b):
    n = len(b.co)
    lab = np.arange(n)
    e0, e1 = b.edges[:, 0], b.edges[:, 1]
    for _ in range(10000):
        m = np.minimum(lab[e0], lab[e1])
        new = lab.copy()
        np.minimum.at(new, e0, m)
        np.minimum.at(new, e1, m)
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    used = np.zeros(n, bool)
    used[b.edges.ravel()] = True
    roots, sizes = np.unique(lab[used], return_counts=True)
    return len(roots), sorted(sizes.tolist(), reverse=True)


def _joint_centering(b, joint, axis_from, axis_to):
    j, a, c = b.mark(joint), b.mark(axis_from), b.mark(axis_to)
    if j is None or a is None or c is None:
        return None
    n = (a - c).normalized()
    loops = slicing.cut(b, j, n)
    if not loops:
        return None
    lp = min(loops, key=lambda l: (l.centre - j).length)
    if lp.radius <= 0:
        return None
    return (j - lp.centre).length / lp.radius, lp.radius


def _hand(b, side, fwd, count_fingers=True):
    w, e = b.mark(f"wrist.{side}"), b.mark(f"elbow.{side}")
    if w is None or e is None:
        return None
    a = (w - e).normalized()
    rel = b.co - np.array(w)
    s = rel @ np.array(a)
    radial = np.linalg.norm(rel - s[:, None] * np.array(a)[None, :], axis=1)
    H = b.top - b.floor
    sel = (s > 0) & (s < 0.16 * H) & (radial < 0.06 * H)
    if not sel.any():
        return {"length": 0.0, "fingers": 0}
    length = float(s[sel].max())
    if not count_fingers:
        return {"length": length}
    best = 0
    per = {}
    for frac in (0.62, 0.72, 0.82):
        p = w + a * (frac * length)
        loops = [lp for lp in slicing.cut(b, p, a)
                 if (lp.centre - p).length < 0.6 * length and lp.perimeter > 0.01]
        per[frac] = len(loops)
        best = max(best, len(loops))
    return {"length": length, "fingers": best, "fingers_by_fraction": per}


def _foot(b, side, fwd):
    ank = b.mark(f"ankle.{side}")
    if ank is None:
        return None
    H = b.top - b.floor
    sel = (b.co[:, 2] < ank.z) & (np.abs(b.co[:, 0] - ank.x) < 0.07 * H)
    if not sel.any():
        return None
    f = b.co[sel][:, :2] @ np.array([fwd.x, fwd.y])
    return float(f.max() - f.min())


def _hands_feet(b, m, fwd, count_fingers):
    for s in ("L", "R"):
        hd = _hand(b, s, fwd, count_fingers=count_fingers)
        if hd:
            m[f"hand.{s}"] = hd
        ft = _foot(b, s, fwd)
        if ft:
            m[f"foot.{s}"] = ft
    hands = [m[k]["length"] for k in ("hand.L", "hand.R") if k in m]
    m["hand"] = sum(hands) / len(hands) if hands else None
    feet = [m[k] for k in ("foot.L", "foot.R") if k in m]
    m["foot"] = sum(feet) / len(feet) if feet else None


def hand_frame(b, side="L"):
    """(wrist, axis, across, back, length): the hand's long axis from the elbow, the palm's breadth
    direction (principal axis of the palm section), and the back of the hand's normal. None if no hand."""
    w, e = b.mark(f"wrist.{side}"), b.mark(f"elbow.{side}")
    if w is None or e is None:
        return None
    hd = _hand(b, side, None, count_fingers=False)
    if not hd or not hd["length"]:
        return None
    a = (w - e).normalized()
    length = hd["length"]
    p = w + a * (0.3 * length)
    loops = [lp for lp in slicing.cut(b, p, a, hull=False) if (lp.centre - p).length < 0.5 * length]
    if not loops:
        return None
    pts = max(loops, key=lambda lp: len(lp.points)).points
    q = pts - pts.mean(axis=0)
    q -= np.outer(q @ np.array(a), np.array(a))
    across = Vector(np.linalg.svd(q, full_matrices=False)[2][0])
    back = a.cross(across).normalized()
    # the back of the hand faces away from the body: outward in X on a hanging arm
    sgn = 1.0 if side == "L" else -1.0
    if back.x * sgn < 0:
        back = -back
    return w, a, across, back, length


def _extremities(b, m, fwd):
    """ANSUR II's hand and foot breadths and wrist and ankle circumferences, left side.
    Hand breadth: across the knuckles (metacarpale II to V) - the widest palm section below where
    the fingers split, thumb excluded. Wrist: the narrowest section at the wrist crease. Foot breadth:
    the widest extent across the foot's own long axis. Ankle: the narrowest girth above the malleoli."""
    fr = hand_frame(b, "L")
    if fr is not None:
        w, a, across, back, length = fr

        def hand_loops(frac):
            p = w + a * (frac * length)
            return [lp for lp in slicing.cut(b, p, a, hull=False) if (lp.centre - p).length < 0.5 * length]

        # palm length: wrist to where the fingers split (three or more sections), bisected to 0.1% of
        # the hand - ANSUR measures to the base of the middle finger, which is where the webs meet
        lo, hi = 0.40, None
        for frac in np.arange(0.40, 0.80, 0.04):
            if len(hand_loops(frac)) >= 3:
                hi = frac
                break
            lo = frac
        if hi is not None:
            for _ in range(5):
                mid = (lo + hi) / 2
                if len(hand_loops(mid)) >= 3:
                    hi = mid
                else:
                    lo = mid
            split = (lo + hi) / 2
            m["palm_length"] = split * length
            # breadth across the knuckles: the palm's widest section in the fifth of the hand below the
            # split, ignoring sections the thumb has joined (a thumb merged at the base reads ~1.5x wide)
            widths = []
            for frac in np.linspace(split - 0.22, split - 0.02, 9):
                loops = hand_loops(frac)
                if loops:
                    ext = max(loops, key=lambda lp: len(lp.points)).points @ np.array(across)
                    widths.append(float(ext.max() - ext.min()))
            if widths:
                ref = float(np.median(widths))
                m["hand_breadth"] = max(x for x in widths if x <= 1.2 * ref)
        girths = []
        for frac in np.linspace(-0.12, 0.04, 5):
            p = w + a * (frac * length)
            loops = [lp for lp in slicing.cut(b, p, a) if (lp.centre - p).length < 0.06]
            if loops:
                girths.append(min(loops, key=lambda lp: (lp.centre - p).length).perimeter)
        if girths:
            m["wrist_circ"] = min(girths)
    ank = b.mark("ankle.L")
    if ank is not None:
        H = b.top - b.floor
        low = b.co[(b.co[:, 2] < b.floor + 0.6 * (ank.z - b.floor)) & (np.abs(b.co[:, 0] - ank.x) < 0.07 * H)]
        if len(low) > 10:
            xy = low[:, :2] - low[:, :2].mean(axis=0)
            axes = np.linalg.svd(xy, full_matrices=False)[2]
            m["foot_breadth"] = float(np.ptp(xy @ axes[1]))
        girths = []
        for zz in np.linspace(ank.z + 0.02 * H, ank.z + 0.08 * H, 7):
            ls = [lp for lp in slicing.horizontal(b, zz) if 0.0 < lp.centre.x < 0.2 * H and lp.perimeter < 0.5]
            if ls:
                girths.append(min(ls, key=lambda lp: abs(lp.centre.x - ank.x)).perimeter)
        if girths:
            m["ankle_circ"] = min(girths)


def _ratio(var, sex, default):
    """ANSUR II mean height ratio for a sex, or a default when the sex is not given."""
    if sex not in ("female", "male"):
        return default
    from . import sheet
    return sheet.anthropometry()["sexes"][sex]["variables"][var]["ratio_mean"]


_FEATURES = None


def face_features():
    """data/face_features.json: base-mesh vertex indices of the nose's wings, the lips and the mouth's slit
    (scripts/derive_face_features.py)."""
    global _FEATURES
    if _FEATURES is None:
        with open(os.path.join(_pkg.DATA, "face_features.json"), encoding="utf-8") as fh:
            _FEATURES = json.load(fh)
    return _FEATURES


def _face_features(b, m, fw, face_front, depth, chin, hs=1.0):
    """The measures a face's likeness is fitted to beyond ANSUR's head set, on an MPFB body (its joint groups
    still on, so its first vertices are the base mesh's): alar breadth (`nose_breadth`), the mouth's corners
    (`mouth_breadth`), the face's outline across at the mouth (`jaw_breadth`, taken as bizygomatic is: skin within
    40% of the head's depth behind the face) and the nose's base to the chin (`nose_chin`). A mesh that is not
    MPFB's gets none of them: base-mesh indices would name arbitrary vertices on it."""
    co = getattr(b, "co_unmasked", None)
    feats = face_features()
    if not getattr(b, "mpfb", None) or co is None or len(co) < feats["n_body"]:
        return
    nose = co[feats["nose"]]
    mouth = co[feats["mouth"]]
    m["nose_breadth"] = float(nose[:, 0].max() - nose[:, 0].min())
    m["mouth_breadth"] = float(mouth[:, 0].max() - mouth[:, 0].min())
    m["nose_chin"] = float(nose[:, 2].min()) - chin
    z = float(mouth[:, 2].mean())
    pts, _, _ = slicing.points(b, (0, 0, z), (0, 0, 1))
    front = pts[((pts[:, :2] @ fw) > face_front - 0.40 * depth) & (np.abs(pts[:, 0]) < 0.12 * hs)]
    if len(front):
        m["jaw_breadth"] = float(front[:, 0].max() - front[:, 0].min())


def _head(b, m, fwd, floor, zs, f, nose, chin, hs=1.0):
    """ANSUR II's head measurements: sellion (nasion) height, menton-sellion, interpupillary,
    head breadth and length above the ears, head circumference, bizygomatic breadth. `hs`: the head's size
    against a human's, for a species body (every distance below is a human head's, in metres)."""
    up = np.isfinite(f) & (zs > nose + 0.012 * hs) & (zs < nose + 0.05 * hs)
    if up.any():
        idx = np.flatnonzero(up)[int(np.nanargmin(f[up]))]
        m["sellion_z"] = float(zs[idx]) - floor
        m["menton_sellion"] = float(zs[idx]) - chin
    eyes = [b.mpfb.get("eye.L"), b.mpfb.get("eye.R")] if getattr(b, "mpfb", None) else [None, None]
    if eyes[0] is not None and eyes[1] is not None:
        m["interpupillary"] = float((eyes[0] - eyes[1]).length)
        eye_z = float((eyes[0].z + eyes[1].z) / 2)
    else:
        eye_z = float(zs[idx]) if up.any() else nose + 0.03 * hs
    fw = np.array([fwd.x, fwd.y])

    def head_loop(z):
        loops = [lp for lp in slicing.horizontal(b, z) if lp.spans_x0 and lp.width_x < 0.25 * hs]
        return min(loops, key=lambda lp: abs(lp.centre.x)) if loops else None

    breadth = depth = circ = 0.0
    face_front = None
    for z in np.arange(eye_z + 0.01 * hs, eye_z + 0.11 * hs, 0.01 * hs):
        lp = head_loop(z)
        if lp is None:
            continue
        ext = lp.points[:, :2] @ fw                        # forward coordinate of the section
        if z <= eye_z + 0.06 * hs:                         # glabella to opisthocranion, brow level
            depth = max(depth, float(ext.max() - ext.min()))
            face_front = float(ext.max()) if face_front is None else max(face_front, float(ext.max()))
        if z >= eye_z + 0.03 * hs:          # above the ears: breadth and circumference exclude them
            breadth = max(breadth, lp.width_x)
            circ = max(circ, lp.perimeter)
    if breadth:
        m["head_breadth"], m["head_depth"], m["head_circ"] = breadth, depth, circ
    if face_front is not None and depth:
        # cheekbones: the widest section between nose tip and eyes, counting only skin within 40% of the
        # head's depth behind the face - the zygomatic arches, not the ears behind them
        biz = 0.0
        for z in np.linspace(nose, eye_z, 5):
            pts, _, _ = slicing.points(b, (0, 0, z), (0, 0, 1))
            front = pts[((pts[:, :2] @ fw) > face_front - 0.40 * depth) & (np.abs(pts[:, 0]) < 0.12 * hs)]
            if len(front):
                biz = max(biz, float(front[:, 0].max() - front[:, 0].min()))
        if biz:
            m["bizygomatic"] = biz
        _face_features(b, m, fw, face_front, depth, chin, hs)


HUMAN_HEAD_M = 0.225       # an adult human head, chin to vertex: the scale of the head's search distances


def measurements(ob, sex=None, fast=False, only=None, levels=None):
    """Raw numbers. `fast` skips what a proportion solver does not need - finger counts, joint
    centring, mesh health and symmetry, hand and foot breadths and girths - for about a third of the
    time. `only="extremities"` measures just the hands and feet, for their own fit stage.

    `levels` ((src, dst) control points, `species.levels`) is for a species body: every height humancheck
    searches or cuts at as a fraction of a human's stature (the waist at the navel, the chest, the nose's
    window) is mapped through the species' joint heights, and the head's search distances scale with its
    measured size. None - every human body - measures exactly as before."""
    b = ob if isinstance(ob, _body.Body) else _body.load(ob)
    lv = (lambda fr: float(np.interp(fr, levels[0], levels[1]))) if levels else (lambda fr: fr)
    m = {"object": b.ob.name, "rig": b.rig.name if b.rig else None,
         "landmark_source": b.landmark_source, "landmarks": {k: [round(c, 4) for c in v] for k, v in b.landmarks.items()}}
    floor, top = b.floor, b.top
    H = top - floor
    m["stature"] = H
    m["floor_offset"] = floor

    # facing: toes are in front of the ankles
    fwd = Vector((0, -1, 0))
    ank = b.mark("ankle.L")
    if ank is None:
        ank = b.mark("ankle.R")
    if ank is not None:
        low = b.co[(b.co[:, 2] < floor + 0.03 * H) & (np.abs(b.co[:, 0] - ank.x) < 0.08 * H)]
        if len(low):
            dy = float(low[:, 1].mean()) - ank.y
            fwd = Vector((0, 1 if dy > 0 else -1, 0))
    m["forward"] = list(fwd)
    left = b.mark("shoulder.L")
    m["left_is_plus_x"] = None if left is None else bool(left.x > 0)

    if only == "extremities":
        _hands_feet(b, m, fwd, count_fingers=False)
        _extremities(b, m, fwd)
        return m

    for name in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle"):
        mid, pair = _avg(b, name)
        if mid is not None:
            m[f"{name}_z"] = mid.z - floor
            if pair:
                m[f"{name}_asym"] = abs(pair[0].z - pair[1].z)

    m["upper_arm"] = _pair_len(b, "shoulder", "elbow")
    m["forearm"] = _pair_len(b, "elbow", "wrist")
    m["thigh"] = _pair_len(b, "hip", "knee")
    m["shin"] = _pair_len(b, "knee", "ankle")

    # crotch: scanning up from the knees, the first height where one loop crosses the midline -
    # 1.5 cm steps, then bisection to 0.2 mm, on extent-only sections
    def joined(z):
        return any(lp.spans_x0 and lp.width_x < 0.6 * H for lp in slicing.horizontal(b, z, hull=False))

    z_lo = floor + (m.get("knee_z") or lv(0.25) * H)
    z_hi = floor + (m.get("hip_z") or lv(0.55) * H) + 0.08 * H
    crotch = None
    prev = z_lo
    for z in np.arange(z_lo, z_hi, 0.015):
        if joined(z):
            lo, hi = prev, z
            for _ in range(7):
                mid = (lo + hi) / 2
                if joined(mid):
                    hi = mid
                else:
                    lo = mid
            crotch = hi
            break
        prev = z
    m["crotch_z"] = None if crotch is None else crotch - floor

    # head: front profile along the midline
    sh = (m.get("shoulder_z") or lv(0.8) * H) + floor
    zs, f = _front_profile(b, sh + 0.01, top, fwd)
    chin = nose = None
    if np.isfinite(f).any():
        if levels:
            win = (zs > floor + lv(0.90) * H) & (zs < floor + lv(0.965) * H) & np.isfinite(f)
        else:
            win = (zs > top - 0.10 * H) & (zs < top - 0.035 * H) & np.isfinite(f)
        if win.any():
            i_nose = int(np.flatnonzero(win)[np.nanargmax(f[win])])
            nose = float(zs[i_nose])
            below = np.isfinite(f) & (zs < nose)
            f_throat = float(np.nanmin(f[below])) if below.any() else float(np.nanmin(f))
            thresh = f_throat + 0.3 * (f[i_nose] - f_throat)
            i = i_nose
            while i > 0 and np.isfinite(f[i - 1]) and f[i - 1] > thresh:
                i -= 1
            chin = float(zs[i])
            hs0 = (top - float(zs[i])) / HUMAN_HEAD_M if levels else 1.0
            up = np.isfinite(f) & (zs > nose + 0.012 * hs0) & (zs < nose + 0.05 * hs0)
            m["face_relief"] = float(f[i_nose] - np.nanmin(f[up])) if up.any() else 0.0
    m["chin_z"] = None if chin is None else chin - floor
    m["nose_z"] = None if nose is None else nose - floor
    hs = (top - chin) / HUMAN_HEAD_M if levels and chin is not None else 1.0
    if chin is not None and nose is not None:
        _head(b, m, fwd, floor, zs, f, nose, chin, hs)
    if chin is not None:
        m["head_length"] = top - chin
        m["heads"] = H / m["head_length"] if m["head_length"] > 0 else None

    _hands_feet(b, m, fwd, count_fingers=not fast)
    if not fast:
        _extremities(b, m, fwd)

    # widths and circumferences
    if m.get("shoulder_z"):
        # bideltoid: the section through the shoulder joints that crosses the midline, so an
        # A-posed arm hanging below the joint is not counted
        loops = [lp for lp in slicing.horizontal(b, floor + m["shoulder_z"]) if lp.spans_x0]
        if loops:
            m["shoulder_width"] = loops[0].width_x

    def torso_loop(z):
        loops = [lp for lp in slicing.horizontal(b, z) if lp.spans_x0]
        return loops[0] if loops else None

    # hips at ANSUR's buttock height for the sex (its hip breadth and buttock circumference are taken
    # there, standing); the widest section above the crotch is kept as hip_max_*, but on a body
    # standing with its legs apart it catches the thighs splaying and reads 3-5 cm wide
    # (never below 2% of H over the crotch: a stylized or long-legged body's crotch can sit above it)
    hz = lv(_ratio("buttockheight", sex, 0.51)) * H
    if m["crotch_z"] is not None:
        hz = max(hz, m["crotch_z"] + 0.02 * H)
    lp = torso_loop(floor + hz)
    if lp:
        m["hip_circ"], m["hip_width"], m["hip_circ_z"] = lp.perimeter, lp.width_x, hz
        m["hip_depth"] = float(lp.max[1] - lp.min[1])
    hip_lo = floor + (m["crotch_z"] if m["crotch_z"] else lv(0.45) * H) + 0.005
    if fast:
        hip_lo = hip_hi = 0.0      # the widest and narrowest sections are reports, not fit residuals
    if not fast:
        hip_hi = floor + (m.get("hip_z") or lv(0.52) * H) + 0.05 * H
    best = None
    for z in np.arange(hip_lo, hip_hi, 0.01):
        lp = torso_loop(z)
        if lp and (best is None or lp.perimeter > best[1].perimeter):
            best = (z, lp)
    if best:
        m["hip_max_circ"], m["hip_max_z"], m["hip_max_width"] = best[1].perimeter, best[0] - floor, best[1].width_x
    # waist at the navel, as ANSUR II measures it (the narrowest section sits higher and reads several
    # cm smaller on most women); the narrowest is kept as waist_min_circ
    omph = lv(_ratio("waistheightomphalion", sex, 0.605))
    lp = torso_loop(floor + omph * H)
    if lp:
        m["waist_circ"], m["waist_circ_z"] = lp.perimeter, omph * H
        # circumference alone cannot tell a wide waist from a belly pushed forward: breadth and depth can
        m["waist_breadth"], m["waist_depth"] = float(lp.max[0] - lp.min[0]), float(lp.max[1] - lp.min[1])
    best = None
    for z in ([] if fast else np.arange(floor + lv(0.58) * H, floor + lv(0.68) * H, 0.01)):
        lp = torso_loop(z)
        if lp and (best is None or lp.perimeter < best[1].perimeter):
            best = (z, lp)
    if best:
        m["waist_min_circ"], m["waist_min_circ_z"] = best[1].perimeter, best[0] - floor
    lp = torso_loop(floor + lv(_ratio("chestheight", sex, 0.72)) * H)
    if lp:
        m["chest_circ"] = lp.perimeter
        m["chest_depth"] = float(lp.max[1] - lp.min[1])
        m["chest_arms_merged"] = bool(m.get("shoulder_width") and lp.width_x > 0.9 * m["shoulder_width"])

    # limb and neck girths (left side), where ANSUR takes them: thigh just below the buttock fold,
    # calf at its widest, upper arm at mid-humerus (ANSUR's biceps is flexed; compare with care),
    # neck at mid-neck. Without these a fit is free to thicken limbs to shape the torso.
    if m.get("crotch_z") is not None:
        lz = floor + m["crotch_z"] - 0.02 * H
        legs = [lp for lp in slicing.horizontal(b, lz) if lp.centre.x > 0.02 and not lp.spans_x0
                and lp.centre.x < 0.2 * H]
        if legs:
            m["thigh_circ"] = max(legs, key=lambda lp: lp.perimeter).perimeter
    if m.get("knee_z") is not None and m.get("ankle_z") is not None:
        best = 0.0
        for zz in np.linspace(m["knee_z"] - 0.05 * H, m["knee_z"] - 0.12 * H, 8):
            ls = [lp for lp in slicing.horizontal(b, floor + zz) if 0.0 < lp.centre.x < 0.2 * H]
            if ls:
                # a limb section, not one that took in both legs; a species body's limit grows with its size
                calf_max = 0.6 if not levels else 0.6 * max(1.0, 1.5 * H / 1.75)
                ps = [lp.perimeter for lp in ls if lp.perimeter < calf_max]
                if ps:
                    best = max(best, max(ps))
        if best:
            m["calf_circ"] = best
    sh_l, el_l = b.mark("shoulder.L"), b.mark("elbow.L")
    if sh_l is not None and el_l is not None:
        mid = (sh_l + el_l) * 0.5
        arm = [lp for lp in slicing.cut(b, mid, (el_l - sh_l).normalized()) if (lp.centre - mid).length < 0.06]
        if arm:
            m["upper_arm_circ"] = min(arm, key=lambda lp: (lp.centre - mid).length).perimeter
    if m.get("chin_z") is not None:
        # 2.5% of H under the chin is below the jaw and above the trapezius; a section wider than 12% of
        # H there is shoulders, not neck (halfway between shoulder joint and chin read up to 37 cm thick)
        neck_w = 0.12 * H if not levels else max(0.12 * H, 0.12 * 1.75 * hs)
        neck = [lp for lp in slicing.horizontal(b, floor + m["chin_z"] - 0.025 * H) if lp.spans_x0 and lp.width_x < neck_w]
        if neck:
            m["neck_circ"] = min(neck, key=lambda lp: abs(lp.centre.x)).perimeter

    if fast:
        return m

    # pose
    s_, w_ = b.mark("shoulder.L"), b.mark("wrist.L")
    if s_ is not None and w_ is not None:
        d = w_ - s_
        m["arm_rest_angle"] = math.degrees(math.asin(max(-1, min(1, -d.z / d.length))))
    for joint, a, c in (("knee", "hip", "ankle"), ("elbow", "shoulder", "wrist")):
        vals = []
        for s in ("L", "R"):
            r = _joint_centering(b, f"{joint}.{s}", f"{a}.{s}", f"{c}.{s}")
            if r:
                vals.append(r[0])
        if vals:
            m[f"{joint}_centering"] = max(vals)

    # mesh health
    counts = np.bincount(b.loop_edge, minlength=len(b.edges))
    m["verts"], m["faces"], m["tris"] = len(b.co), len(b.face_sizes), len(b.tris)
    m["quad_share"] = float((b.face_sizes == 4).mean()) if len(b.face_sizes) else 0.0
    m["boundary_edges"] = int((counts == 1).sum())
    m["nonmanifold_edges"] = int((counts > 2).sum())
    m["components"], sizes = _components(b)
    m["component_sizes"] = sizes[:6]
    v = b.co[b.tris]
    m["signed_volume"] = float(np.einsum("ij,ij->i", v[:, 0], np.cross(v[:, 1], v[:, 2])).sum() / 6.0)
    m["uv_layers"] = b.uv_layers
    m["scale_applied"] = all(abs(s - 1) < 1e-4 for s in b.ob.scale) and (
        b.rig is None or all(abs(s - 1) < 1e-4 for s in b.rig.scale))

    # distance from each mirrored vertex to the surface (not to the nearest vertex, which on a
    # decimated mesh is an edge length away even when the shape is perfectly symmetric)
    bvh = BVHTree.FromPolygons([tuple(p) for p in b.co], [tuple(t) for t in b.tris.tolist()])
    step = max(1, len(b.co) // 6000)
    d = [bvh.find_nearest(Vector((-p[0], p[1], p[2])))[3] for p in b.co[::step]]
    m["symmetry_p95"] = float(np.percentile([x for x in d if x is not None], 95))
    return m


# ------------------------------------------------------------------------------------------
def _target(entry, sex):
    if "any" in entry:
        return entry["any"]
    if sex in entry:
        return entry[sex]
    return None


def _grade(value, target, tol):
    dev = abs(value - target)
    return "pass" if dev <= tol else "warn" if dev <= 2 * tol else "fail"


def check(m, preset="realistic", sex=None, build=None):
    """Findings for a measurement dict. `build` (a sheet build word other than 'average') turns
    body-shape ratios the build deliberately moves - waist to hip, shoulder to hip - from warn or
    fail into info: a heavy brief is supposed to sit outside the population's waist-to-hip range."""
    data = _pkg.presets()
    if isinstance(preset, dict):           # a preset in hand: a species given inline (species.preset)
        p = preset
    elif preset not in data["presets"]:
        raise ValueError(f"unknown preset {preset!r}: one of {sorted(data['presets'])}")
    else:
        p = data["presets"][preset]
    feats = data["features"]
    if p.get("features"):          # a species preset's own ranges for the human-only checks
        feats = dict(feats, **{k: dict(feats.get(k, {}), **v) for k, v in p["features"].items()})
    H = m["stature"]
    out = []

    def add(fid, group, status, message, value=None, target=None, tol=None):
        out.append({"id": fid, "group": group, "layer": LAYER[group], "status": status, "message": message,
                    "value": None if value is None else round(float(value), 4),
                    "target": target, "tol": tol})

    heights = {"chin": "chin_z", "shoulder_joint": "shoulder_z", "hip_joint": "hip_z", "crotch": "crotch_z",
               "knee_joint": "knee_z", "ankle_joint": "ankle_z"}
    lengths = {"upper_arm": "upper_arm", "forearm": "forearm", "hand": "hand", "thigh": "thigh", "shin": "shin",
               "foot": "foot", "shoulder_width": "shoulder_width", "hip_width": "hip_width"}
    for key, entry in p["ratios"].items():
        tgt = _target(entry, sex)
        src = heights.get(key) or lengths.get(key)
        if tgt is None:
            add(key, "proportion", "info", f"{key}: sex not given, not judged")
            continue
        val = m.get(src)
        if val is None:
            add(key, "proportion", "fail", f"{key}: could not be measured (missing landmark or geometry)")
            continue
        r = val / H
        st = _grade(r, tgt[0], tgt[1])
        delta_cm = (r - tgt[0]) * H * 100
        kind = "height" if key in heights else "length"
        word = ("too high" if delta_cm > 0 else "too low") if kind == "height" else ("too long" if delta_cm > 0 else "too short")
        if key in ("shoulder_width", "hip_width"):
            word = "too wide" if delta_cm > 0 else "too narrow"
        msg = f"{key} {r:.3f} H, target {tgt[0]:.3f} +/- {tgt[1]:.3f}"
        if st != "pass":
            msg += f" - {abs(delta_cm):.1f} cm {word}"
        if st != "pass" and key in ("shoulder_width", "hip_width") and isinstance(build, str) and build != "average":
            st, msg = "info", msg + f" (outside the population range, as a {build} build may be)"
        add(key, "proportion", st, msg, r, tgt[0], tgt[1])

    ht = _target(p["heads"], sex)
    if m.get("heads"):
        st = _grade(m["heads"], ht[0], ht[1])
        add("heads", "proportion", st, f"{m['heads']:.2f} heads tall, target {ht[0]} +/- {ht[1]}", m["heads"], ht[0], ht[1])
    else:
        add("heads", "proportion", "fail", "head length could not be measured (no chin found on the midline)")

    d = p["derived"]
    shaped = isinstance(build, str) and build != "average"
    if m.get("shoulder_width") and m.get("hip_width"):
        tgt = _target(d["shoulder_to_hip_width"], sex)
        r = m["shoulder_width"] / m["hip_width"]
        if tgt:
            st = _grade(r, *tgt)
            add("shoulder_to_hip_width", "proportion", "info" if shaped and st != "pass" else st,
                f"shoulder/hip width {r:.2f}, target {tgt[0]} +/- {tgt[1]}"
                + (f" (outside the population range, as a {build} build may be)" if shaped and st != "pass" else ""), r, *tgt)
    if m.get("waist_circ") and m.get("hip_circ"):
        tgt = _target(d["waist_to_hip_circ"], sex)
        r = m["waist_circ"] / m["hip_circ"]
        if tgt:
            st = _grade(r, *tgt)
            add("waist_to_hip_circ", "proportion", "info" if shaped and st != "pass" else st,
                f"waist/hip circumference {r:.2f}, target {tgt[0]} +/- {tgt[1]}"
                + (f" (outside the population range, as a {build} build may be)" if shaped and st != "pass" else ""), r, *tgt)

    if m.get("hip_z") and m.get("crotch_z"):
        lo, hi = feats["hip_above_crotch"]["range"]
        r = (m["hip_z"] - m["crotch_z"]) / H
        st = "pass" if lo <= r <= hi else "fail"
        add("hip_above_crotch", "rig", st,
            f"hip joints {r * H * 100:.1f} cm above the crotch ({r:.3f} H), expected {lo}-{hi} H"
            + ("" if st == "pass" else " - the hip joints are not inside the pelvis"), r, [lo, hi])

    if m.get("kind") == "landmarks":
        return out          # a landmark set has no surface to judge

    # features
    f = feats["fingers_per_hand"]
    for s in ("L", "R"):
        hd = m.get(f"hand.{s}")
        if hd is None:
            add(f"fingers.{s}", "feature", "fail", f"hand.{s}: no wrist/elbow landmarks to find the hand")
            continue
        n = hd["fingers"]
        st = "pass" if n >= f["pass"] else "warn" if n >= f["warn"] else "fail"
        add(f"fingers.{s}", "feature", st, f"hand.{s}: {n} separate finger sections"
            + ("" if st == "pass" else " - the hand is a mitten or a stump"), n, f["pass"])
    f = feats["face_relief_m"]
    rel = m.get("face_relief")
    if rel is None:
        add("face", "feature", "fail", "no face profile found")
    else:
        st = "pass" if rel >= f["pass"] else "warn" if rel >= f["warn"] else "fail"
        add("face", "feature", st, f"nose stands {rel * 1000:.0f} mm in front of the nasion"
            + {"pass": "", "warn": " - the face is shallow", "fail": " - the face has no features"}[st], rel, f["pass"])
    if m.get("crotch_z") is None:
        add("legs_parted", "feature", "fail", "no crotch found: the legs never separate below the hips")

    for joint in ("knee", "elbow"):
        c = m.get(f"{joint}_centering")
        if c is not None:
            jc = feats["joint_centering"]
            st = "pass" if c <= jc["pass"] else "warn" if c <= jc["warn"] else "fail"
            add(f"{joint}_centering", "rig", st, f"{joint} joint is {c:.2f} limb radii off the limb's centre (worst side)"
                + ("" if st == "pass" else " - the rig's joint is not where the mesh bends"), c, jc["pass"])

    # pose and mesh
    a = m.get("arm_rest_angle")
    if a is not None:
        lo, hi = feats["arm_rest_angle_deg"]["range"]
        add("arm_rest_angle", "pose", "pass" if lo <= a <= hi else "warn",
            f"arms rest {a:.0f} deg below horizontal, expected {lo}-{hi}", a, [lo, hi])
    if m.get("left_is_plus_x") is False:
        add("left_side", "pose", "fail", "the body's left landmarks are at -X; conventions put the left at +X")
    if abs(m["forward"][1] + 1) > 0.5:
        add("facing", "pose", "fail", "the body faces +Y; conventions face -Y")
    fo = m["floor_offset"]
    add("floor", "pose", "pass" if abs(fo) <= feats["floor_offset_m"]["max"] else "warn",
        f"lowest point at z = {fo * 1000:.1f} mm", fo)
    sym = m["symmetry_p95"]
    add("symmetry", "mesh", "pass" if sym <= feats["symmetry_p95_m"]["max"] else "warn",
        f"95% of vertices within {sym * 1000:.1f} mm of their mirror", sym)
    q = m["quad_share"]
    add("quads", "mesh", "pass" if q >= feats["quad_share"]["min"] else "warn",
        f"{q * 100:.0f}% quads, {m['tris']} triangles" + ("" if q >= feats["quad_share"]["min"]
                                                          else " - needs retopology before shipping"), q)
    add("components", "mesh", "pass" if m["components"] == 1 else "warn",
        f"{m['components']} connected piece(s), largest {m['component_sizes'][:3]}", m["components"])
    add("manifold", "mesh", "pass" if m["nonmanifold_edges"] == 0 and m["boundary_edges"] == 0 else "warn",
        f"{m['boundary_edges']} open edges, {m['nonmanifold_edges']} non-manifold edges")
    add("normals", "mesh", "pass" if m["signed_volume"] > 0 else "fail",
        "normals face outward" if m["signed_volume"] > 0 else "normals face inward (negative volume)")
    add("uvs", "surface", "pass" if m["uv_layers"] else "warn",
        f"UV layers: {m['uv_layers']}" if m["uv_layers"] else "no UVs - nothing can be baked or textured")
    add("scale", "mesh", "pass" if m["scale_applied"] else "warn",
        "scale applied" if m["scale_applied"] else "object or rig scale is not 1")
    if m["landmark_source"] == "none":
        add("landmarks", "rig", "fail", "no rig bones or MPFB joint groups to read landmarks from")
    return out


def run(ob, preset="realistic", sex=None, out_dir=None, build=None):
    lv = None
    if isinstance(preset, dict):
        lv = (preset.get("levels") or {}).get(sex)
    elif preset not in ("realistic", "stylized"):
        lv = (_pkg.presets()["presets"].get(preset) or {}).get("levels", {}).get(sex)
    m = measurements(ob, sex, levels=lv)
    findings = check(m, preset, sex, build)
    if isinstance(preset, dict):
        preset = preset.get("species") or "custom"
    counts = {k: sum(1 for f in findings if f["status"] == k) for k in ("pass", "warn", "fail", "info")}
    rep = {"schema": _pkg.SCHEMA, "kind": "humancheck", "version": _pkg.VERSION, "body": m["object"],
           "preset": preset, "sex": sex, "stature_m": round(m["stature"], 4), "counts": counts,
           "findings": findings, "measurements": m}
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "humancheck.json"), "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=1, default=float)
        rep["file"] = os.path.join(out_dir, "humancheck.json")
    return rep


def summarize(rep):
    c = rep["counts"]
    lines = [f"{rep['body']}: {rep['stature_m']:.3f} m, preset {rep['preset']}, sex {rep['sex']} - "
             f"{c['fail']} fail, {c['warn']} warn, {c['pass']} pass"]
    for st in ("fail", "warn"):
        for f in rep["findings"]:
            if f["status"] == st:
                lines.append(f"  {st.upper():4} {f['layer']} {f['message']}")
    return "\n".join(lines)
