"""Maws: find a mouth on the skin, give it a jaw, and open it.

A head arrives as one bone. A dragon that breathes fire or a whale that
swallows a ship needs a lower jaw that hinges, skin that parts cleanly along
the lips and stretches at the corners, teeth that stay rigid, a throat that
swells, and a socket an engine can hang fire or an engulf volume on. None of
that is in the bones yet; all of it is in the skin.

FINDING THE MOUTH
-----------------

A modelled mouth is a cavity entering the head from the front. Rays cast
upward through the head at stations along it cross solid skin twice where the
head is shut (chin in, skull out) and four times where the mouth is (chin in,
mouth floor out, palate in, skull out). The gap between the second and third
crossing is the mouth at that station, and the rearmost station that still
has one is the corner. Loose parts - teeth, baleen, a tongue - are set aside
first, because a ray that clips a tooth sees a false wall.

    upper / lower  which side of the lips a vertex belongs to - decided by the
                   mesh, not by height: seeds are taken only well clear of the
                   gap, and the rest take the label of the seed nearest along
                   the surface. An upper lip that overhangs below the lower
                   one is still upper, because it is connected to the snout.
    hinge          the jaw joint: 75-90% of head length back from the snout
                   (the standard ear-lobe placement in side view), never in
                   front of the corner.

BUILDING
--------

`build` adds, parented to the head:

    jaw        deforming, from the hinge to the chin
    throat     deforming, under the jaw: moved down, it swells a gular pouch
               or a rorqual's pleated throat
    tongue*    deforming chain, parented to the jaw, when a loose part lies
               along the mouth floor
    mouth      NOT deforming: a socket at the lips, aimed along the bisector
               of the open jaws - where an engine attaches fire, a bite
               volume or an engulf volume

and stores what it measured on the armature (`rig_anything_maw`), so the body
map can read the maw back and actions can pose it without measuring again.

SKINNING
--------

`skin` splits whatever weight the head already had - bone heat's, a hand
painter's - so neck blends survive:

- in front of the corner the split is hard: a lower-lip vertex takes nothing
  from the head, or the mouth is sewn shut;
- between the corner and the hinge it softens into a ramp that widens toward
  the hinge, so the corner stretches as a web rather than tearing;
- behind the hinge the jaw's share fades out into the throat and neck;
- the throat takes a share of ventral skin along the pouch, whatever bones
  held it (a rorqual's pleats run half the body);
- every loose part is rigid - one bone, weight 1 - on the side of the mouth
  whose skin it sits on, and a tongue is weighted along its own chain.

POSING
------

One state per key, like a wing's: `gape` 0..1 of the kind's maximum opening,
`throat` 0..1 of its pouch drop, `tongue` -1..1, `pitch` degrees of extra head
lift. Part of the opening is the skull lifting: in geckos the snout rises 4.1
degrees and adds 8.7% of the gape, peaking with the jaw (PMC4521707), so a
share of the angle goes to the head. The rest is the jaw about the hinge. See
`references/maws.md` in animate-anything for the numbers and their sources.
"""

from __future__ import annotations

import heapq
import json
import math
import re

import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

PROP = "rig_anything_maw"
ROLE = "maw_role"
NAME = re.compile(r"jaw|mandib|tongue|throat|gular|pouch|mouth|teeth|tooth|beak|maw|"
                  r"(^|[._\-])lip([._\-]|$)", re.I)

# Per kind of mouth. Sourced figures are cited in references/maws.md.
#   gape         maximum opening, degrees, jaws combined
#   lift_share   share of the opening the skull takes by lifting
#   hinge_back   hinge position back from the snout tip, share of head length
#   hinge_drop   hinge height from the lip line, share of head depth (+ up)
#   slide        forward-down jaw translation at full gape, share of jaw length
#   throat_drop  pouch drop at full swell, share of the depth below the lips
#   throat_front where the pouch starts, share of mouth length back from the tip
#   throat_back  where it ends, mouth lengths behind the hinge
KINDS = {
    # theropods: T. rex 70.5-80, Allosaurus 79-92 (Lautenschlager 2015)
    "reptile": dict(gape=80.0, lift_share=0.087, hinge_back=0.82, hinge_drop=-0.05,
                    slide=0.0, throat_drop=0.35, throat_front=0.55, throat_back=0.8,
                    stretch_limit=3.0),
    # alligator 43.5-49.5 (Lautenschlager 2015)
    "crocodilian": dict(gape=45.0, lift_share=0.0, hinge_back=0.9, hinge_drop=-0.05,
                        slide=0.0, throat_drop=0.25, throat_front=0.6, throat_back=0.6,
                    stretch_limit=3.0),
    # lion ~65, popular figures to 90 - conflicting
    "mammal": dict(gape=70.0, lift_share=0.0, hinge_back=0.78, hinge_drop=0.15,
                   slide=0.06, throat_drop=0.2, throat_front=0.55, throat_back=0.5,
                    stretch_limit=3.0),
    # lower jaws drop 78-80 (PMC8179629); pleats stretch ~162% around the body
    # and the tissue past 4x sideways (JEB 2013). The hinge sits low: at the lip
    # line, skin a metre under it swung back into the chest and folded.
    "rorqual": dict(gape=80.0, lift_share=0.05, hinge_back=0.9, hinge_drop=-0.35,
                    slide=0.0, throat_drop=0.9, throat_front=0.9, throat_back=1.6,
                    stretch_limit=4.0),
    # "almost 90" - popular source
    "anglerfish": dict(gape=90.0, lift_share=0.0, hinge_back=0.85, hinge_drop=0.0,
                       slide=0.0, throat_drop=0.5, throat_front=0.5, throat_back=0.6,
                    stretch_limit=3.0),
}
# Jaw muscles at 170% of resting length set a theropod's maximum gape
# (Lautenschlager 2015). Skin is not muscle, so this is REPORTED - the gape at
# which the corner's skin first passes it, where a real jaw of that shape
# would stop - not failed.
MUSCLE_STRETCH = 1.7
# What fails a clip, unless the kind says otherwise: an edge past 3x its
# length. A hard seam at the corner put a 7 mm edge at 14x and tore visibly;
# the relaxed web's worst edge at the test dragon's full 80 degrees is 2.3x and
# renders as a smooth cheek.
STRETCH_LIMIT = 3.0


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------

def _bound_meshes(rig):
    return [o for o in bpy.data.objects if o.type == "MESH" and any(
        m.type == "ARMATURE" and m.object == rig for m in o.modifiers)]


def _components(me):
    """Connected-component id per vertex, and each component's size."""
    parent = list(range(len(me.vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for e in me.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[a] = b
    comp = [find(i) for i in range(len(me.vertices))]
    sizes = {}
    for c in comp:
        sizes[c] = sizes.get(c, 0) + 1
    return comp, sizes


class Skin:
    """Every bound mesh in armature space: positions, normalized weights,
    edges, faces, and which vertices are body and which are loose parts."""

    def __init__(self, rig):
        self.rig = rig
        to_arm = rig.matrix_world.inverted()
        self.meshes = []
        for o in _bound_meshes(rig):
            me = o.data
            m = to_arm @ o.matrix_world
            names = {g.index: g.name for g in o.vertex_groups if g.name in rig.data.bones}
            cos, ws = [], []
            for v in me.vertices:
                w = {names[g.group]: g.weight for g in v.groups
                     if g.group in names and g.weight > 0.0}
                tot = sum(w.values())
                ws.append({k: x / tot for k, x in w.items()} if tot > 0 else {})
                cos.append(m @ v.co)
            comp, sizes = _components(me)
            largest = max(sizes.values()) if sizes else 0
            # Body: the largest component and anything of comparable size (a
            # mirrored shell). Loose parts: teeth, baleen, tongue, eyes.
            body = {c for c, n in sizes.items() if n >= 0.2 * largest}
            self.meshes.append({
                "object": o, "cos": cos, "weights": ws, "comp": comp, "sizes": sizes,
                "body": body, "edges": [tuple(e.vertices) for e in me.edges],
                "faces": [tuple(p.vertices) for p in me.polygons],
            })

    def body_tree(self):
        verts, polys = [], []
        for m in self.meshes:
            index = {}
            for i, co in enumerate(m["cos"]):
                if m["comp"][i] in m["body"]:
                    index[i] = len(verts)
                    verts.append(co)
            for f in m["faces"]:
                if all(i in index for i in f):
                    polys.append([index[i] for i in f])
        return BVHTree.FromPolygons(verts, polys, epsilon=0.0)


def _hits(tree, origin, direction, limit, eps):
    """Every surface crossing along a ray, as distances from `origin`."""
    out = []
    o = origin.copy()
    while len(out) < 64:
        loc, _, _, _ = tree.ray_cast(o, direction, max(limit - (o - origin).dot(direction), 0.0))
        if loc is None:
            break
        t = (loc - origin).dot(direction)
        if not out or t - out[-1] > 2.0 * eps:
            out.append(t)
        o = loc + direction * eps
    return out


def _gaps(hits):
    """Empty spans between solid spans: (exit, entry) pairs."""
    if len(hits) % 2:
        return None
    return [(hits[i], hits[i + 1]) for i in range(1, len(hits) - 1, 2)]


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _v(x):
    return [round(float(c), 6) for c in x]


# --------------------------------------------------------------------------
# detection
# --------------------------------------------------------------------------

class Frame:
    """Head coordinates: u forward from the head joint, h up from it, l across
    from the body's midline."""

    def __init__(self, joint, fwd, up, lat, midline):
        self.joint, self.fwd, self.up, self.lat = joint, fwd, up, lat
        self.l0 = midline - joint.dot(lat)

    def ulh(self, p):
        d = p - self.joint
        return d.dot(self.fwd), d.dot(self.up), d.dot(self.lat) - self.l0

    def point(self, u, h, l=0.0):
        return self.joint + self.fwd * u + self.up * h + self.lat * (l + self.l0)


def detect(rig_name, bm=None, kind="reptile", stations=56, forward="-Y", up="Z"):
    """Find the mouth on a rig's head skin. Returns a description or an error."""
    from . import bodymap
    rig = bpy.data.objects.get(rig_name)
    if rig is None or rig.type != "ARMATURE":
        return {"error": "no armature named %r" % rig_name}
    if kind not in KINDS:
        return {"error": "unknown kind %r - one of %s" % (kind, ", ".join(KINDS))}
    bm = bm or bodymap.build(rig_name, forward=forward, up=up)
    if "error" in bm:
        return bm
    head = bm["head"]
    if head is None:
        return {"error": "%s has no head in its body map" % rig_name}
    skin = Skin(rig)
    if not skin.meshes:
        return {"error": "a maw is found on the skin, and %s has no bound mesh" % rig_name}
    bones = rig.data.bones
    idx = bm["axial"].index(head)
    joint = bm["axial_joints"][idx].copy()
    F = Frame(joint, bm["fwd"], bm["up_vec"], bm["lat"], bm["midline"])

    # head skin: body vertices the head holds at least half of - counting a
    # previous maw's bones as head, or a rebuild finds its chin at the corner
    family = {head} | {n for ns in maw_bones(rig).values() for n in ns}
    pts = []
    for m in skin.meshes:
        for i, (co, w) in enumerate(zip(m["cos"], m["weights"])):
            if m["comp"][i] in m["body"] and sum(w.get(b, 0.0) for b in family) >= 0.5:
                pts.append(F.ulh(co))
    if len(pts) < 50:
        return {"error": "only %d skin vertices follow %s - bind the mesh first" % (len(pts), head)}
    u_tip = max(p[0] for p in pts)
    u_min = min(p[0] for p in pts)
    h_lo = min(p[1] for p in pts)
    h_hi = max(p[1] for p in pts)
    head_len = u_tip
    if head_len <= 0.0:
        return {"error": "the head skin lies behind its joint - check forward=%r" % forward}
    depth_all = h_hi - h_lo
    eps = 1e-5 * max(bm["size"], 1e-3)
    tree = skin.body_tree()

    def half_width(u, du):
        ws = [abs(p[2]) for p in pts if abs(p[0] - u) <= du]
        return max(ws) if ws else 0.0

    base = h_lo - 3.0 * depth_all

    def column(u, l):
        # from well under the head: behind it a body can hang lower than a chin
        hits = _hits(tree, F.point(u, base, l), F.up, 7.0 * depth_all, eps)
        return [base + t for t in hits]

    du = head_len / stations
    rows = []
    prev_split = None
    started, corner_row, misses = False, None, 0
    for k in range(stations):
        u = u_tip - (k + 0.5) * du
        hw = half_width(u, du)
        cols = []
        for share in (0.0, -0.35, 0.35):
            hs = column(u, share * hw)
            gaps = _gaps(hs) or []
            gaps = [g for g in gaps if g[1] - g[0] > 0.004 * head_len]
            if prev_split is not None and gaps:
                g = min(gaps, key=lambda g: abs(0.5 * (g[0] + g[1]) - prev_split))
            elif gaps:
                g = max(gaps, key=lambda g: g[1] - g[0])
            else:
                g = None
            cols.append({"l": share * hw, "hits": hs, "gap": g})
        mid = cols[0]
        any_gap = [c for c in cols if c["gap"]]
        row = {"u": u, "half_width": hw, "cols": cols,
               "bottom": mid["hits"][0] if mid["hits"] else None,
               "top": mid["hits"][-1] if mid["hits"] else None,
               "gap": (mid["gap"] or (any_gap[0]["gap"] if any_gap else None))}
        rows.append(row)
        if row["gap"]:
            prev_split = 0.5 * (row["gap"][0] + row["gap"][1])
            if not started and k <= 0.3 * stations:
                started = True
            if started:
                corner_row, misses = k, 0
        elif started:
            misses += 1
            if misses >= 2:
                break
        elif k > 0.3 * stations:
            break
    if corner_row is None:
        return {"error": "no mouth modelled on %s: no cavity enters the head from the front. "
                         "A closed head has nothing to open - model a mouth (even shut, with "
                         "separate lips) and bind again" % rig_name,
                "stations_checked": len(rows)}

    mouth_rows = [r for r in rows[:corner_row + 1] if r["gap"]]
    # Lips fused in front of the corner: a column through the mouth that meets
    # no gap while columns beside it do. The remesh that built one test dragon
    # left such a pillar where its jaws came within two voxels, and at full
    # gape the skin across it stretched 24x.
    bridges = []
    first_gap = next(k for k, r in enumerate(rows) if r["gap"])
    u_last = rows[corner_row]["u"]
    u_first = rows[first_gap]["u"]
    for r in rows[first_gap:corner_row + 1]:
        # the mouth narrows into its corner and its front, so side columns
        # close there without anything being fused
        if r["u"] < u_last + 0.15 * (u_first - u_last) or r["u"] > u_first - 0.1 * (u_first - u_last):
            continue
        shut = [c["l"] for c in r["cols"] if not c["gap"]]
        if shut and len(shut) < len(r["cols"]):
            bridges.append((r["u"], shut))
    u_c = rows[corner_row]["u"] - 0.5 * du
    mouth_len = u_tip - u_c
    samples = [(r["u"], 0.5 * (r["gap"][0] + r["gap"][1]), r["gap"][1] - r["gap"][0])
               for r in mouth_rows]
    # the lip line behind the corner: a straight fit through the rear third
    rear = samples[-max(3, len(samples) // 3):]
    n = len(rear)
    mu = sum(s[0] for s in rear) / n
    mh = sum(s[1] for s in rear) / n
    suu = sum((s[0] - mu) ** 2 for s in rear)
    slope = sum((s[0] - mu) * (s[1] - mh) for s in rear) / suu if suu > 1e-12 else 0.0
    slope = max(-0.6, min(0.6, slope))

    # corner width: across from the midline at the corner, at the lip line
    h_c = mh + slope * (u_c + 0.5 * du - mu)
    corner_hw = None
    for share in (0.5, 1.0):
        u_probe = u_c + share * du
        origin = F.point(u_probe, h_c, 0.0)
        for sign in (1.0, -1.0):
            loc, _, _, _ = tree.ray_cast(origin, F.lat * sign, 2.0 * half_width(u_probe, du) + eps)
            if loc is not None:
                w = abs(F.ulh(loc)[2])
                corner_hw = w if corner_hw is None else max(corner_hw, w)
    if corner_hw is None:
        corner_hw = 0.6 * half_width(u_c, du)

    # widest point of the cavity, across from the midline at the lip line
    mouth_hw = corner_hw
    for r in mouth_rows:
        h_mid = 0.5 * (r["gap"][0] + r["gap"][1])
        origin = F.point(r["u"], h_mid, 0.0)
        for sign in (1.0, -1.0):
            loc, _, _, _ = tree.ray_cast(origin, F.lat * sign, 2.0 * r["half_width"] + eps)
            if loc is not None:
                mouth_hw = max(mouth_hw, abs(F.ulh(loc)[2]))

    # lip tips: the frontmost skin above and below the lip line
    h_front = samples[0][1]
    upper_tip = max((p for p in pts if p[1] > h_front), key=lambda p: p[0], default=None)
    lower_tip = max((p for p in pts if p[1] <= h_front), key=lambda p: p[0], default=None)

    # rows further back, for the throat: columns behind the head too
    k_spec = KINDS[kind]
    back_rows = []
    u = u_c - 0.5 * du
    while u > min(u_min, 0.0) - k_spec["throat_back"] * mouth_len - du and len(back_rows) < 4 * stations:
        hs = column(u, 0.0)
        if hs:
            back_rows.append({"u": u, "bottom": hs[0], "top": hs[-1]})
        u -= du
    # body skin further back than the head: cast from under the body instead
    profile = [(r["u"], r["bottom"], r["top"]) for r in rows[:corner_row + 1] if r["bottom"] is not None]
    profile += [(r["u"], r["bottom"], r["top"]) for r in back_rows]

    hinge_u = u_tip - k_spec["hinge_back"] * head_len
    hinge_u = min(hinge_u, u_c - 0.1 * mouth_len)
    hinge_u = max(hinge_u, min(0.02 * head_len, u_c - 0.1 * mouth_len))
    bottom_h, top_h = _profile_at(profile, hinge_u)
    split_h = h_c + slope * (hinge_u - u_c)
    depth = top_h - bottom_h
    hinge_h = split_h + k_spec["hinge_drop"] * depth
    hinge_h = max(bottom_h + 0.15 * depth, min(top_h - 0.15 * depth, hinge_h))

    # loose parts: which is a tongue, which are rigid (teeth, baleen, horns)
    parts = []
    for mi, m in enumerate(skin.meshes):
        groups = {}
        for i, c in enumerate(m["comp"]):
            if c not in m["body"]:
                groups.setdefault(c, []).append(i)
        for c, ids in groups.items():
            ulh = [F.ulh(m["cos"][i]) for i in ids]
            cu = sum(p[0] for p in ulh) / len(ulh)
            ch = sum(p[1] for p in ulh) / len(ulh)
            cl = sum(p[2] for p in ulh) / len(ulh)
            ext_u = max(p[0] for p in ulh) - min(p[0] for p in ulh)
            ext_l = max(p[2] for p in ulh) - min(p[2] for p in ulh)
            ext_h = max(p[1] for p in ulh) - min(p[1] for p in ulh)
            gap = _gap_at(samples, cu)
            inside = (u_c - 0.1 * mouth_len <= cu <= u_tip and gap is not None
                      and gap[0] - 0.02 * mouth_len <= ch <= gap[1] and abs(cl) < corner_hw)
            tongue = (inside and ext_u >= 0.3 * mouth_len and ext_u > 1.5 * ext_l
                      and ext_h < 0.5 * ext_u)
            parts.append({"mesh": mi, "component": c, "vertices": len(ids),
                          "centre_u": cu, "centre_h": ch, "length": ext_u,
                          "kind": "tongue" if tongue else "rigid"})

    tongues = [p for p in parts if p["kind"] == "tongue"]
    if len(tongues) > 1:
        keep = max(tongues, key=lambda p: p["vertices"] * p["length"])
        for p in tongues:
            if p is not keep:
                p["kind"] = "rigid"
        tongues = [keep]

    warnings = []
    if bridges:
        warnings.append("the lips are fused at %d station(s) in front of the corner (%s ahead "
                        "of the head joint): skin joins upper and lower jaw there and will tear "
                        "or stretch when the mouth opens - separate them in the mesh"
                        % (len(bridges), ", ".join("%.3f" % b[0] for b in bridges[:4])))
    if abs(slope) >= 0.6:
        warnings.append("the lip line tilts steeply behind the corner - clamped")
    if mouth_len < 0.15 * head_len:
        warnings.append("a mouth only %.0f%% of the head's length - is this a nostril?"
                        % (100 * mouth_len / head_len))
    if not rows[0]["gap"] and not rows[1]["gap"]:
        warnings.append("the gap starts behind the snout tip - an overbite, or lips "
                        "that meet in front")

    return {
        "rig": rig_name, "kind": kind, "head": head,
        "frame": {"joint": _v(joint), "fwd": _v(F.fwd), "up": _v(F.up), "lat": _v(F.lat),
                  "l0": F.l0},
        "u_tip": u_tip, "u_corner": u_c, "mouth_length": mouth_len,
        "head_length": head_len, "corner_half_width": corner_hw,
        "mouth_half_width": mouth_hw,
        "lip_line": [(s[0], s[1]) for s in samples], "lip_slope_behind": slope,
        "gap_at_front": samples[0][2],
        "hinge": (hinge_u, hinge_h), "hinge_depth": depth,
        "upper_tip": upper_tip, "lower_tip": lower_tip,
        "profile": profile,
        "parts": parts,
        "tongue": tongues[0] if tongues else None,
        "rigid_parts": sum(1 for p in parts if p["kind"] == "rigid"),
        "bridges": [b[0] for b in bridges],
        "warnings": warnings,
    }


def _profile_at(profile, u):
    """(bottom, top) skin heights at u, interpolated along the body."""
    pr = sorted(profile)
    if not pr:
        return 0.0, 0.0
    if u <= pr[0][0]:
        return pr[0][1], pr[0][2]
    if u >= pr[-1][0]:
        return pr[-1][1], pr[-1][2]
    for a, b in zip(pr, pr[1:]):
        if a[0] <= u <= b[0]:
            t = (u - a[0]) / max(b[0] - a[0], 1e-12)
            return a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t
    return pr[-1][1], pr[-1][2]


def _gap_at(samples, u):
    for s in samples:
        if abs(s[0] - u) <= abs(samples[0][0] - samples[-1][0]) / max(len(samples) - 1, 1):
            return (s[1] - 0.5 * s[2], s[1] + 0.5 * s[2])
    return None


def lip_height(d, u):
    """The lip line at u: measured in front of the corner, fitted behind it."""
    line = d["lip_line"]
    if u >= line[0][0]:
        return line[0][1]
    for a, b in zip(line, line[1:]):
        if b[0] <= u <= a[0]:
            t = (a[0] - u) / max(a[0] - b[0], 1e-12)
            return a[1] + (b[1] - a[1]) * t
    last = line[-1]
    return last[1] + d["lip_slope_behind"] * (u - last[0])


def measure_limit(rig_name, forward="-Y", up="Z", steps=9):
    """The widest gape - share of the kind's maximum - this skin takes with no
    face turned inside out and no edge past the kind's stretch limit, found by
    bisection on predicted poses, and stored so gape 1 means it. Skin can
    outrank the kind, as it outranks reach in a crouch: the test whale folded
    28 faces at a rorqual's 80 degrees and one at 40."""
    from . import bodymap, keyposes as kp, motion
    rig = bpy.data.objects[rig_name]
    raw = json.loads(rig.data[PROP])
    raw.pop("gape_clean_deg", None)
    rig.data[PROP] = json.dumps(raw)        # measure against the kind, not a stale limit
    kind_max = raw["spec"]["gape"]
    bm = bodymap.build(rig_name, forward=forward, up=up)
    body = motion.Body(rig, bm)
    P = kp.Poser(body)
    C = MawChecks(P)
    limit = P.maw_rig.spec.get("stretch_limit", STRETCH_LIMIT)
    rest_flips = C.measure(body.fk())["flipped_faces"]

    def clean(g):
        m = C.measure(P.pose(kp.Key(maw=state(gape=g)))[0])
        return m["flipped_faces"] <= rest_flips and m["stretch_max"] <= limit, m
    ok, full = clean(1.0)
    why = None
    if ok:
        best = 1.0
    else:
        lo, hi = 0.0, 1.0
        for _ in range(steps):
            mid = 0.5 * (lo + hi)
            if clean(mid)[0]:
                lo = mid
            else:
                hi = mid
        best = lo
        why = ("%d faces fold" % (full["flipped_faces"] - rest_flips)
               if full["flipped_faces"] > rest_flips else
               "skin stretches to %.1fx" % full["stretch_max"])
    raw["gape_clean_deg"] = best * kind_max
    rig.data[PROP] = json.dumps(raw)
    return {"gape_clean": round(best, 3), "gape_clean_deg": round(best * kind_max, 1),
            "kind_max_deg": kind_max, "at_kind_max": why,
            "stretch_at_kind_max": round(full["stretch_max"], 2)}


def summarize_detection(d):
    if "error" in d:
        return "ERROR: " + d["error"]
    lines = [
        "%s: %s mouth on %s, %.3f long (%.0f%% of the head), %.3f wide at the corner"
        % (d["rig"], d["kind"], d["head"], d["mouth_length"],
           100 * d["mouth_length"] / d["head_length"], 2 * d["corner_half_width"]),
        "  corner %.3f ahead of the head joint, hinge at u %.3f h %.3f; gap at the lips %.4f"
        % (d["u_corner"], d["hinge"][0], d["hinge"][1], d["gap_at_front"]),
        "  loose parts: %d rigid%s" % (d["rigid_parts"], ", a tongue" if d["tongue"] else ""),
    ]
    lines += ["  WARN " + w for w in d["warnings"]]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# building bones
# --------------------------------------------------------------------------

def _edit(rig):
    view = bpy.context.view_layer
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in view.objects:
        o.select_set(False)
    view.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")


def maw_bones(rig):
    """Bones this module added, by role."""
    out = {}
    for b in rig.data.bones:
        role = b.get(ROLE)
        if role:
            out.setdefault(role, []).append(b.name)
    for k in out:
        out[k].sort()
    return out


def unbuild(rig_name):
    """Remove a maw this module built: its weights go back to the head, its bones
    and the stored description are deleted. Safe to call on a rig without one."""
    rig = bpy.data.objects[rig_name]
    info = read(rig)
    roles = maw_bones(rig)
    names = {n for ns in roles.values() for n in ns}
    if not names:
        return {"removed": []}
    head = info["head"] if info else None
    if _restore_weights(rig):
        for o in _bound_meshes(rig):
            txt = bpy.data.texts.get(_weights_key(o))
            if txt is not None:
                bpy.data.texts.remove(txt)
    for o in _bound_meshes(rig):
        groups = {g.name: g for g in o.vertex_groups}
        target = groups.get(head) if head else None
        for v in o.data.vertices:
            moved = 0.0
            for g in v.groups:
                gname = o.vertex_groups[g.group].name
                if gname in names:
                    moved += g.weight
            if moved > 0.0 and target is not None:
                cur = next((g.weight for g in v.groups if g.group == target.index), 0.0)
                target.add([v.index], cur + moved, "REPLACE")
        for n in names:
            if n in groups:
                o.vertex_groups.remove(groups[n])
    _edit(rig)
    eb = rig.data.edit_bones
    for n in sorted(names, key=lambda n: -len(n)):
        if n in eb:
            eb.remove(eb[n])
    bpy.ops.object.mode_set(mode="OBJECT")
    if PROP in rig.data:
        del rig.data[PROP]
    return {"removed": sorted(names)}


def build(rig_name, detection=None, kind="reptile", forward="-Y", up="Z",
          tongue_bones=3, prefix=""):
    """Add jaw, throat, tongue and mouth bones for a detected mouth, and store
    the description on the armature. Rebuilding replaces a previous maw."""
    if detection is None:
        unbuild(rig_name)           # measure the skin as bound, not as split
    d = detection or detect(rig_name, kind=kind, forward=forward, up=up)
    if "error" in d:
        return d
    rig = bpy.data.objects[rig_name]
    unbuild(rig_name)
    fr = d["frame"]
    F = Frame(Vector(fr["joint"]), Vector(fr["fwd"]), Vector(fr["up"]), Vector(fr["lat"]),
              0.0)
    F.l0 = fr["l0"]
    spec = KINDS[d["kind"]]
    L = d["mouth_length"]
    hinge = F.point(*d["hinge"])
    lower = d["lower_tip"]
    chin = F.point(lower[0], lip_height(d, lower[0]) - 0.25 * d["gap_at_front"])
    u_front = d["u_tip"]
    mouth_head = F.point(u_front, lip_height(d, u_front))
    names = {"jaw": prefix + "jaw", "throat": prefix + "throat", "gular": prefix + "gular",
             "mouth": prefix + "mouth"}

    # The pouch is two bones. Skin under the jaw rides on it - a rorqual's pleats
    # start at the chin - and skin behind the hinge rides the head and neck. One
    # head-parented throat bone held skin under the jaw back as the jaw dropped,
    # and the dragon's jaw sides turned inside out.
    t_front = d["u_tip"] - spec["throat_front"] * L
    t_back = d["hinge"][0] - spec["throat_back"] * L
    hinge_u = d["hinge"][0]

    def pouch_point(u):
        bottom, _ = _profile_at(d["profile"], u)
        lips = lip_height(d, u)
        return F.point(u, bottom + 0.35 * (lips - bottom)), lips - bottom
    throat_head, throat_depth = pouch_point(0.5 * (hinge_u + t_back))
    has_gular = t_front > hinge_u + 0.1 * L
    gular_head, gular_depth = pouch_point(0.5 * (t_front + hinge_u)) if has_gular else (None, 0.0)

    _edit(rig)
    eb = rig.data.edit_bones
    head = eb[d["head"]]
    made = []

    def bone(name, h, t, parent, deform, role, roll_up=F.up):
        b = eb.new(name)
        b.head, b.tail = h, t
        b.parent = parent
        b.use_connect = False
        b.use_deform = deform
        b.align_roll(roll_up)
        made.append((name, role))
        return b

    jaw = bone(names["jaw"], hinge, chin, head, True, "jaw")
    bone(names["throat"], throat_head, throat_head + F.fwd * max(0.15 * L, 1e-3), head, True,
         "throat")
    if has_gular:
        bone(names["gular"], gular_head, gular_head + F.fwd * max(0.15 * L, 1e-3), jaw, True,
             "gular")
    bone(names["mouth"], mouth_head, mouth_head + F.fwd * max(0.25 * L, 1e-3), head, False,
         "mouth")
    tongue_names = []
    tg = d.get("tongue")
    if tg and tongue_bones > 0:
        m = Skin(rig).meshes[tg["mesh"]]
        ids = [i for i, c in enumerate(m["comp"]) if c == tg["component"]]
        ulh = [F.ulh(m["cos"][i]) for i in ids]
        u0 = min(p[0] for p in ulh)
        u1 = max(p[0] for p in ulh)
        prev = jaw
        for k in range(tongue_bones):
            ua = u0 + (u1 - u0) * k / tongue_bones
            ub = u0 + (u1 - u0) * (k + 1) / tongue_bones
            ha = sum(p[1] for p in ulh if abs(p[0] - ua) < 0.1 * (u1 - u0) + 1e-9) / max(
                1, sum(1 for p in ulh if abs(p[0] - ua) < 0.1 * (u1 - u0) + 1e-9))
            hb = sum(p[1] for p in ulh if abs(p[0] - ub) < 0.1 * (u1 - u0) + 1e-9) / max(
                1, sum(1 for p in ulh if abs(p[0] - ub) < 0.1 * (u1 - u0) + 1e-9))
            name = prefix + ("tongue" if k == 0 else "tongue.%03d" % k)
            b = bone(name, F.point(ua, ha), F.point(ub, hb), prev, True, "tongue")
            if k:
                b.use_connect = True
            prev = b
            tongue_names.append(name)
    bpy.ops.object.mode_set(mode="OBJECT")
    for name, role in made:
        rig.data.bones[name][ROLE] = role

    stored = {
        "version": 1, "kind": d["kind"], "head": d["head"],
        "jaw": names["jaw"], "throat": names["throat"], "mouth": names["mouth"],
        "gular": names["gular"] if has_gular else None, "gular_depth": gular_depth,
        "tongue": tongue_names,
        "frame": fr, "hinge": list(d["hinge"]),
        "u_tip": d["u_tip"], "u_corner": d["u_corner"], "mouth_length": L,
        "head_length": d["head_length"], "corner_half_width": d["corner_half_width"],
        "mouth_half_width": d["mouth_half_width"],
        "lip_line": [list(s) for s in d["lip_line"]], "lip_slope_behind": d["lip_slope_behind"],
        "gap_at_front": d["gap_at_front"],
        "upper_tip": list(d["upper_tip"]) if d["upper_tip"] else None,
        "lower_tip": list(d["lower_tip"]) if d["lower_tip"] else None,
        "throat_span": [t_back, t_front],
        "throat_depth": throat_depth,
        "hinge_depth": d["hinge_depth"],
        "profile": [list(p) for p in d["profile"]],
        "spec": dict(spec),
    }
    rig.data[PROP] = json.dumps(stored)
    return {"rig": rig_name, "bones": dict(made), "tongue": tongue_names,
            "hinge": _v(hinge), "chin": _v(chin), "mouth_socket": _v(mouth_head),
            "throat": _v(throat_head), "gular": _v(gular_head) if has_gular else None}


def read(rig):
    """The stored maw description with vectors restored, or None."""
    raw = rig.data.get(PROP) if rig is not None else None
    if not raw:
        return None
    d = json.loads(raw)
    bones = rig.data.bones
    for k in ("jaw", "throat", "gular", "mouth", "head"):
        if d.get(k) and d[k] not in bones:
            return None
    fr = d["frame"]
    d["F"] = Frame(Vector(fr["joint"]), Vector(fr["fwd"]), Vector(fr["up"]), Vector(fr["lat"]), 0.0)
    d["F"].l0 = fr["l0"]
    d["lip_line"] = [tuple(s) for s in d["lip_line"]]
    d["profile"] = [tuple(p) for p in d["profile"]]
    return d


# --------------------------------------------------------------------------
# skinning
# --------------------------------------------------------------------------

def _weights_key(o):
    return "rig_anything_maw_weights:" + o.name


def _restore_weights(rig):
    """Put back the weights `skin` found before it first split them, so skinning
    again - with other settings, or after a rebuild - starts from the same place.
    Kept in a text block: it lives in the .blend and never reaches a glb."""
    restored = 0
    for o in _bound_meshes(rig):
        txt = bpy.data.texts.get(_weights_key(o))
        if txt is None:
            continue
        data = json.loads(txt.as_string())
        if data.get("n") != len(o.data.vertices):
            bpy.data.texts.remove(txt)
            continue
        groups = {g.name: g for g in o.vertex_groups}
        names = {b for w in data["w"].values() for b in w} | set(data.get("maw", []))
        for b in names:
            if b not in groups and b in rig.data.bones:
                groups[b] = o.vertex_groups.new(name=b)
        for key, w in data["w"].items():
            i = int(key)
            for b in names:
                if b in groups:
                    if w.get(b, 0.0) > 0.0:
                        groups[b].add([i], w[b], "REPLACE")
                    else:
                        groups[b].remove([i])
        restored += len(data["w"])
    return restored


def skin(rig_name, corner=0.5, ramp=0.8, taper=0.5, ahead=0.0, behind=0.5, roof=1.0,
         relax=3000, seed_band=0.12, throat_share=0.85, limit=True):
    """Split the head's weights between head and jaw along the lips, give the
    throat its pouch, and make loose parts rigid. Needs `build` first.

    The web where skin is shared between jaw and head has a half-width of
    `corner` x the head's depth at the corner, `ramp` x its depth at the hinge,
    and narrows to a hard split `taper` mouth lengths in front of the corner.
    A hard split at the corner itself put a 7 mm edge across the whole arc of
    the jaw: 14x its length at full gape. `seed_band` is how far from the lip line (share of the gap at
    the lips, at least 1% of the mouth length) a vertex must lie to be labelled
    by height; nearer ones take the label of the nearest seed along the mesh.
    """
    rig = bpy.data.objects[rig_name]
    d = read(rig)
    if d is None:
        return {"error": "%s has no maw - run maw.build first" % rig_name}
    F = d["F"]
    head, jaw, throat, gular = d["head"], d["jaw"], d["throat"], d.get("gular")
    tongue = d["tongue"]
    L = d["mouth_length"]
    u_c, u_tip = d["u_corner"], d["u_tip"]
    hinge_u, hinge_h = d["hinge"]
    depth_h = d.get("hinge_depth") or max(_profile_at(d["profile"], hinge_u)[1]
                                          - _profile_at(d["profile"], hinge_u)[0], 1e-6)
    band = max(seed_band * d["gap_at_front"], 0.01 * L)
    t_back, t_front = d["throat_span"]
    restored = _restore_weights(rig)
    S = Skin(rig)
    report = {"meshes": [], "rigid_parts": 0, "tongue_vertices": 0,
              "restored_first": restored}

    for m in S.meshes:
        o = m["object"]
        cos, ws, comp = m["cos"], m["weights"], m["comp"]
        n = len(cos)
        ulh = [F.ulh(c) for c in cos]
        split = [lip_height(d, p[0]) for p in ulh]
        dist = [p[1] - s for p, s in zip(ulh, split)]
        in_mouth = [p[0] >= u_c - 0.02 * L for p in ulh]

        # neighbours along the body surface
        nbr = [[] for _ in range(n)]
        for a, b in m["edges"]:
            if comp[a] in m["body"]:
                w = (cos[a] - cos[b]).length
                nbr[a].append((b, w))
                nbr[b].append((a, w))

        # 1. upper / lower labels for the head's skin, by the mesh near the lips
        label = [None] * n
        heap = []
        for i in range(n):
            if comp[i] not in m["body"] or ws[i].get(head, 0.0) <= 0.0:
                continue
            if abs(dist[i]) > band or not in_mouth[i]:
                label[i] = dist[i] < 0.0
                heapq.heappush(heap, (0.0, i, label[i]))
        best = [math.inf] * n
        for _, i, lab in heap:
            best[i] = 0.0
        while heap:
            g, i, lab = heapq.heappop(heap)
            if g > best[i]:
                continue
            for j, w in nbr[i]:
                if ws[j].get(head, 0.0) <= 0.0:
                    continue
                if g + w < best[j]:
                    best[j] = g + w
                    label[j] = lab
                    heapq.heappush(heap, (g + w, j, lab))
        relabelled = sum(1 for i in range(n) if label[i] is not None and in_mouth[i]
                         and abs(dist[i]) <= band and label[i] != (dist[i] < 0.0))

        # 2. jaw share per body vertex
        depth_c = max(_profile_at(d["profile"], u_c)[1] - _profile_at(d["profile"], u_c)[0], 1e-6)
        span = max(u_c - hinge_u, 1e-9)

        def web(u):
            """Half-width of the band where the jaw's share runs 1 -> 0, across
            the lip line. Wide at the corner - which sits at 50/50 - wider still
            toward the hinge, and narrowing to a hard split along the lips."""
            w_c = corner * depth_c
            if u >= u_c:
                return w_c * (1.0 - _smooth((u - u_c) / max(taper * L, 1e-9)))
            t = min(1.0, (u_c - u) / span)
            return w_c + (ramp * depth_h - w_c) * _smooth(t)

        def jaw_share(i):
            u = ulh[i][0]
            lower = label[i] if label[i] is not None else dist[i] < 0.0
            w = web(u)
            if w <= 1e-9:
                return 1.0 if lower else 0.0
            j = max(0.0, min(1.0, 0.5 - dist[i] / (2.0 * w)))
            if u >= u_c:
                # in front of the corner the lips are separate skin: never across
                j = max(j, 0.5) if lower else min(j, 0.5)
            # Skin around the hinge is not jaw: rotated with it, skin under the
            # joint swings back into the throat, and the whale's flanks turned
            # inside out. The share fades from `ahead` spans in front of the
            # hinge to `behind` spans behind it.
            lo, hi = hinge_u - behind * span, hinge_u + ahead * span
            return j * _smooth((u - lo) / max(hi - lo, 1e-9))

        # The head claims its mouth. Bone heat gave the whale's lower-jaw flanks
        # a quarter of their weight from the CHEST, 1-2 m in front of the hinge;
        # splitting only the head's share left that skin glued to the body, and
        # 124 faces turned inside out. In front of the corner every other bone's
        # share moves to the head, fading out toward the hinge.
        maw_names = {jaw, throat} | set(tongue) | ({gular} if gular else set())
        claim_lo = hinge_u - behind * span
        new = [dict(w) for w in ws]
        claimed = 0
        for i in range(n):
            if comp[i] not in m["body"]:
                continue
            u = ulh[i][0]
            c = _smooth((u - claim_lo) / max(u_c - claim_lo, 1e-9))
            if c <= 0.0:
                continue
            other = sum(x for b, x in new[i].items() if b != head and b not in maw_names)
            if other <= 1e-6 or (new[i].get(head, 0.0) <= 0.0 and u < u_c):
                continue
            moved = other * c
            new[i] = {b: (x if b == head or b in maw_names else x * (1.0 - c))
                      for b, x in new[i].items()}
            new[i][head] = new[i].get(head, 0.0) + moved
            claimed += 1
        # The analytic share is a first guess. Where it runs from jaw to head it
        # is then RELAXED: pinned on the lower jaw in front of the lips' blend,
        # on the skull roof and behind the hinge, and smoothed in between with
        # each edge weighted by its squared distance from the hinge - the
        # stretch an edge suffers is its change in share times the arc there,
        # so this spends the change where the arc is short. Tapers alone left
        # a 0.17 step over 8 cm of the whale's lip, 1.1 m in front of the
        # corner, and at 80 degrees that edge ran to 4.8x.
        import numpy as np
        jv = np.zeros(n)
        free = np.zeros(n, dtype=bool)
        active = np.zeros(n, dtype=bool)
        front_fixed = u_c + taper * L
        for i in range(n):
            if comp[i] not in m["body"] or new[i].get(head, 0.0) <= 0.0:
                continue
            active[i] = True
            u = ulh[i][0]
            lower = label[i] if label[i] is not None else dist[i] < 0.0
            if u >= front_fixed:
                jv[i] = 1.0 if lower else 0.0
            elif u <= claim_lo:
                jv[i] = 0.0
            else:
                jv[i] = jaw_share(i)
                # the skull above the corner's web is head, whatever the depth
                free[i] = dist[i] < roof * corner * depth_c
        relaxed_n = int(free.sum())
        if relax and relaxed_n:
            ea = np.array([a for a, b in m["edges"] if active[a] or active[b]], dtype=np.int64)
            eb = np.array([b for a, b in m["edges"] if active[a] or active[b]], dtype=np.int64)
            if len(ea):
                U = np.array([p[0] for p in ulh])
                Hh = np.array([p[1] for p in ulh])
                P3 = np.array([tuple(c) for c in cos])
                length = np.maximum(np.linalg.norm(P3[ea] - P3[eb], axis=1), 1e-9)
                r2 = ((0.5 * (U[ea] + U[eb]) - hinge_u) ** 2 + (0.5 * (Hh[ea] + Hh[eb]) - hinge_h) ** 2
                      + (0.05 * L) ** 2)
                wgt = r2 / length
                den = np.bincount(ea, wgt, n) + np.bincount(eb, wgt, n)
                ok = den > 0
                for _ in range(relax):
                    num = np.bincount(ea, wgt * jv[eb], n) + np.bincount(eb, wgt * jv[ea], n)
                    upd = np.where(ok, num / np.where(ok, den, 1.0), jv)
                    jv = np.where(free, upd, jv)
        for i in range(n):
            if not active[i]:
                continue
            hw = new[i].get(head, 0.0)
            j = float(min(1.0, max(0.0, jv[i])))
            if j > 0.0:
                new[i][head] = hw * (1.0 - j)
                new[i][jaw] = new[i].get(jaw, 0.0) + hw * j

        # 3. the throat pouch: ventral skin below the lips along its span
        ramp_len = 0.25 * (t_front - t_back)
        for i in range(n):
            if comp[i] not in m["body"]:
                continue
            u, h, l = ulh[i]
            if not (t_back <= u <= t_front) or dist[i] >= 0.0:
                continue
            bottom, _ = _profile_at(d["profile"], u)
            below = max(split[i] - bottom, 1e-9)
            v = _smooth(((split[i] - h) / below - 0.3) / 0.6)
            along = min(_smooth((u - t_back) / ramp_len), _smooth((t_front - u) / ramp_len))
            tau = throat_share * v * along
            if tau <= 0.0:
                continue
            new[i] = {k: x * (1.0 - tau) for k, x in new[i].items()}
            # the gular bone turns with the jaw, so the pouch divides on the
            # jaw's own relaxed share - a separate blend about the hinge put
            # 35% jaw rotation into skin under the joint
            g = float(min(1.0, max(0.0, jv[i]))) if gular else 0.0
            if g > 0.0:
                new[i][gular] = new[i].get(gular, 0.0) + tau * g
            if g < 1.0:
                new[i][throat] = new[i].get(throat, 0.0) + tau * (1.0 - g)

        # 4. loose parts: rigid on the side they sit on; a tongue along its chain
        body_ids = [i for i in range(n) if comp[i] in m["body"]
                    and (ws[i].get(head, 0.0) > 0.0)]
        kd = KDTree(len(body_ids))
        for k, i in enumerate(body_ids):
            kd.insert(cos[i], k)
        kd.balance()
        parts = {}
        for i in range(n):
            if comp[i] not in m["body"]:
                parts.setdefault(comp[i], []).append(i)
        tongue_comp = None
        stored_tongue = None
        for c, ids in parts.items():
            cu = sum(ulh[i][0] for i in ids) / len(ids)
            ch = sum(ulh[i][1] for i in ids) / len(ids)
            ext_u = max(ulh[i][0] for i in ids) - min(ulh[i][0] for i in ids)
            ext_l = max(ulh[i][2] for i in ids) - min(ulh[i][2] for i in ids)
            if (tongue and u_c - 0.1 * L <= cu <= u_tip and ext_u >= 0.3 * L
                    and ext_u > 1.5 * ext_l and (stored_tongue is None or ext_u > stored_tongue)):
                tongue_comp, stored_tongue = c, ext_u
        for c, ids in parts.items():
            if not body_ids:
                break
            if c == tongue_comp:
                bones = rig.data.bones
                segs = [(bones[t].head_local, bones[t].tail_local) for t in tongue]
                total = len(segs)
                for i in ids:
                    p = cos[i]
                    # nearest segment, and the position along the whole chain
                    best_k, best_s, best_d = 0, 0.0, math.inf
                    for k, (a, b) in enumerate(segs):
                        ab = b - a
                        s_ = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.dot(ab), 1e-12)))
                        dd = (p - (a + ab * s_)).length
                        if dd < best_d:
                            best_k, best_s, best_d = k, s_, dd
                    # shared between the two nearest bone centres
                    c_pos = max(0.0, min(total - 1.0, best_k + best_s - 0.5))
                    k0 = int(math.floor(c_pos))
                    f = c_pos - k0
                    w = {tongue[k0]: 1.0 - f}
                    if k0 + 1 < total and f > 1e-6:
                        w[tongue[k0 + 1]] = f
                    new[i] = w
                report["tongue_vertices"] += len(ids)
                continue
            votes = {}
            for i in ids:
                _, k, _ = kd.find(cos[i])
                src = new[body_ids[k]]
                top = max(src, key=src.get)
                votes[top] = votes.get(top, 0) + 1
            if not votes:
                continue
            winner = max(votes, key=votes.get)
            # a loose part near the lips goes to head or jaw, never to a blend
            if winner not in (head, jaw):
                j_votes = sum(v for b, v in votes.items() if b == jaw)
                h_votes = sum(v for b, v in votes.items() if b == head)
                if j_votes or h_votes:
                    winner = jaw if j_votes > h_votes else head
            for i in ids:
                new[i] = {winner: 1.0}
            report["rigid_parts"] += 1

        # 5. write
        changed = set()
        for i in range(n):
            if new[i] != ws[i]:
                changed.add(i)
        txt = bpy.data.texts.get(_weights_key(o))
        keep = json.loads(txt.as_string()) if txt else {"n": n, "w": {}}
        for i in changed:
            keep["w"].setdefault(str(i), {b: round(x, 6) for b, x in ws[i].items()})
        keep["maw"] = sorted({jaw, throat, head} | set(tongue) | ({gular} if gular else set()))
        if txt is None:
            txt = bpy.data.texts.new(_weights_key(o))
        txt.clear()
        txt.write(json.dumps(keep))
        wanted = {b for i in changed for b in new[i]} | {b for i in changed for b in ws[i]}
        groups = {g.name: g for g in o.vertex_groups}
        for b in wanted:
            if b not in groups:
                groups[b] = o.vertex_groups.new(name=b)
        for i in changed:
            tot = sum(new[i].values())
            for b in set(new[i]) | set(ws[i]):
                g = groups[b]
                x = new[i].get(b, 0.0) / tot if tot > 0 else 0.0
                if x > 1e-6:
                    g.add([i], x, "REPLACE")
                else:
                    g.remove([i])
        jaw_vs = sum(1 for i in range(n) if new[i].get(jaw, 0.0) >= 0.5)
        throat_vs = sum(1 for i in range(n) if new[i].get(throat, 0.0) >= 0.25)
        report["meshes"].append({"object": o.name, "changed": len(changed),
                                 "claimed_for_head": claimed, "relaxed": relaxed_n,
                                 "jaw_dominant": jaw_vs, "throat_quarter": throat_vs,
                                 "relabelled_by_surface": relabelled})
    if limit:
        report["limit"] = measure_limit(rig_name)
    return report


# --------------------------------------------------------------------------
# posing
# --------------------------------------------------------------------------

REST_STATE = {"gape": 0.0, "throat": 0.0, "tongue": 0.0, "pitch": 0.0}


def state(**kw):
    s = dict(REST_STATE)
    s.update(kw)
    return s


def blend_states(a, b, w):
    sa = dict(REST_STATE, **(a or {}))
    sb = dict(REST_STATE, **(b or {}))
    return {k: sa[k] + (sb[k] - sa[k]) * w for k in REST_STATE}


class MawRig:
    """Rest measurements for a stored maw, and the pose maths.

    No IK and no rotation signs taken on trust: which way about the lateral
    axis drops the chin, lifts the snout and curls the tongue up is tested on
    the rest points, once, here.
    """

    def __init__(self, body):
        self.body = body
        d = self.d = body.bm["maw"]
        rig = body.rig
        bones = rig.data.bones
        F = d["F"]
        self.F = F
        self.head, self.jaw, self.throat, self.mouth = d["head"], d["jaw"], d["throat"], d["mouth"]
        self.tongue = list(d["tongue"])
        self.spec = d["spec"]
        self.hinge = F.point(*d["hinge"])
        self.joint = F.joint.copy()
        ut, lt = d["upper_tip"], d["lower_tip"]
        self.upper_tip = F.point(ut[0], ut[1]) if ut else F.point(d["u_tip"], lip_height(d, d["u_tip"]))
        self.lower_tip = F.point(lt[0], lt[1]) if lt else self.upper_tip - F.up * d["gap_at_front"]
        self.jaw_len = (self.lower_tip - self.hinge).length

        def opens(pivot, point, want_up):
            v = point - pivot
            r = Matrix.Rotation(math.radians(10.0), 3, F.lat) @ v
            return 1.0 if ((r - v).dot(F.up) > 0.0) == want_up else -1.0
        self.sign_jaw = opens(self.hinge, self.lower_tip, want_up=False)
        self.sign_lift = opens(self.joint, self.upper_tip, want_up=True)
        self.sign_tongue = opens(self.hinge, self.lower_tip, want_up=True)
        self.throat_drop = self.spec["throat_drop"] * d.get("throat_depth", 0.0)
        self.gular = d.get("gular")
        self.gular_drop = self.spec["throat_drop"] * d.get("gular_depth", 0.0)
        self.bones_posed = ([self.head, self.jaw, self.throat, self.mouth] + self.tongue
                            + ([self.gular] if self.gular else []))
        self.rest_gape = self._angle(self.upper_tip - self.hinge, self.lower_tip - self.hinge)
        # gape 1 is the kind's maximum - or, if smaller, the widest opening this
        # skin takes without folding or tearing, as `skin` measured it
        self.gape_max = min(self.spec["gape"], d.get("gape_clean_deg") or self.spec["gape"])

    def _angle(self, a, b):
        return math.degrees(a.angle(b)) if a.length > 1e-12 and b.length > 1e-12 else 0.0

    def angles(self, s):
        total = s["gape"] * self.gape_max
        return total, self.spec["lift_share"] * total + s["pitch"]

    def pose(self, posed, s):
        """Overrides for head, jaw, throat, tongue and mouth socket."""
        body = self.body
        rest, rest_local = body.rest, body.rest_local
        F = self.F
        total, lift = self.angles(s)
        H = posed[self.head]
        C = H.to_3x3() @ rest[self.head].to_3x3().inverted()
        joint_now = body.carried(posed, self.head, self.joint)
        R_l = Matrix.Rotation(math.radians(lift * self.sign_lift), 4, C @ F.lat)
        H2 = Matrix.Translation(joint_now) @ R_l @ Matrix.Translation(-joint_now) @ H
        out = {self.head: H2}
        C2 = H2.to_3x3() @ rest[self.head].to_3x3().inverted()
        to_head = H2 @ rest[self.head].inverted()
        lat_now = (C2 @ F.lat).normalized()

        hinge_now = to_head @ self.hinge
        R_j = Matrix.Rotation(math.radians(total * self.sign_jaw), 4, lat_now)
        slide = Vector((0.0, 0.0, 0.0))
        if self.spec["slide"]:
            # the condyle slides forward and down once the opening is under way
            # (humans: rotation first, translation dominating past ~20 mm)
            k = _smooth((s["gape"] - 0.25) / 0.75)
            slide = (C2 @ (F.fwd - 0.5 * F.up)).normalized() * self.spec["slide"] * self.jaw_len * k
        J = (Matrix.Translation(hinge_now + slide) @ R_j @ Matrix.Translation(-hinge_now)
             @ H2 @ rest_local[self.jaw])
        out[self.jaw] = J

        parent = J
        for i, t in enumerate(self.tongue):
            Tb = parent @ rest_local[t]
            if s["tongue"]:
                axis = (J.to_3x3() @ rest[self.jaw].to_3x3().inverted() @ F.lat).normalized()
                a = math.radians(s["tongue"] * 22.0 * self.sign_tongue)
                p = Tb.translation.copy()
                Tb = Matrix.Translation(p) @ Matrix.Rotation(a, 4, axis) @ Matrix.Translation(-p) @ Tb
            out[t] = Tb
            parent = Tb

        T0 = H2 @ rest_local[self.throat]
        down = -(C2 @ F.up).normalized()
        out[self.throat] = Matrix.Translation(down * s["throat"] * self.throat_drop) @ T0
        if self.gular:
            # under the jaw, "down" turns with the jaw
            G0 = J @ rest_local[self.gular]
            down_j = -(J.to_3x3() @ rest[self.jaw].to_3x3().inverted() @ F.up).normalized()
            out[self.gular] = Matrix.Translation(down_j * s["throat"] * self.gular_drop) @ G0

        # the socket swings with half the jaw about the hinge: on the bisector
        M0 = H2 @ rest_local[self.mouth]
        R_h = Matrix.Rotation(math.radians(0.5 * total * self.sign_jaw), 4, lat_now)
        out[self.mouth] = (Matrix.Translation(hinge_now + 0.5 * slide) @ R_h
                           @ Matrix.Translation(-hinge_now) @ M0)
        return out


# --------------------------------------------------------------------------
# checks, on Blender's evaluated pose
# --------------------------------------------------------------------------

class MawChecks:
    """Gape, corner stretch, skin turned inside out, rigid parts, jaw into the
    neck, socket aim, aperture and swallowed volume - from the skin."""

    def __init__(self, poser):
        self.P = poser
        body, bm = poser.body, poser.bm
        self.body, self.bm, self.mr = body, bm, poser.maw_rig
        rig = body.rig
        mr = self.mr
        maw_set_ = set(mr.bones_posed)
        S = Skin(rig)
        self.meshes = []
        for m in S.meshes:
            cos, ws, comp = m["cos"], m["weights"], m["comp"]
            region = {i for i, w in enumerate(ws) if any(b in maw_set_ for b in w)}
            faces = [f for f in m["faces"] if any(i in region for i in f)]
            used = sorted({i for f in faces for i in f})
            edges = set()
            for f in faces:
                for k in range(len(f)):
                    a, b = f[k], f[(k + 1) % len(f)]
                    edges.add((min(a, b), max(a, b)))
            rest_len = {e: (cos[e[0]] - cos[e[1]]).length for e in edges}
            # A sliver - area under a tenth of its longest edge squared, which a
            # decimated mesh is full of - has no normal worth trusting: one
            # flipped at 40 degrees on the test whale and capped its gape at 15.
            sliver = []
            for f in faces:
                nv = Vector((0.0, 0.0, 0.0))
                for k in range(len(f)):
                    nv += cos[f[k]].cross(cos[f[(k + 1) % len(f)]])
                longest = max((cos[f[k]] - cos[f[(k + 1) % len(f)]]).length for k in range(len(f)))
                sliver.append(0.5 * nv.length < 0.1 * longest * longest)
            # a loose part held by one bone is rigid; a tongue is not
            held = {}
            for i, c in enumerate(comp):
                if c not in m["body"]:
                    held.setdefault(c, set()).update(b for b, w in ws[i].items() if w > 1e-6)
            rigid = {c: len(bs) == 1 for c, bs in held.items()}
            self.meshes.append({
                "cos": cos, "ws": ws, "comp": comp, "body": m["body"], "used": used,
                "faces": faces, "edges": [e for e in edges if rest_len[e] > 1e-9],
                "rest_len": rest_len, "rigid": rigid, "sliver": sliver,
            })
        # body radius per axial bone other than the head (80th percentile)
        tail = set(bm.get("tail", []))
        self.axial = [n for n in bm["axial"] if n not in tail and n != mr.head]
        dists = {n: [] for n in self.axial}
        from .flight import _seg_dist
        self._seg_dist = _seg_dist
        for m in S.meshes:
            for co, w in zip(m["cos"], m["weights"]):
                if not w:
                    continue
                top = max(w, key=w.get)
                if top in dists:
                    b = rig.data.bones[top]
                    dists[top].append(_seg_dist(co, b.head_local, b.tail_local))
        self.radius = {}
        for n, ds in dists.items():
            ds.sort()
            self.radius[n] = ds[int(0.8 * (len(ds) - 1))] if ds else 0.0
        self.scale = sum(rig.matrix_world.to_scale()) / 3.0

    def _skin(self, mats, m):
        deform = {n: mats[n] @ self.body.rest[n].inverted() for n in self.body.rest}
        pos = {}
        for i in m["used"]:
            p = Vector((0.0, 0.0, 0.0))
            for n, w in m["ws"][i].items():
                p += (deform[n] @ m["cos"][i]) * w
            pos[i] = p if m["ws"][i] else m["cos"][i]
        return pos, deform

    def measure(self, mats):
        """Everything for one evaluated frame."""
        mr, body, F = self.mr, self.body, self.mr.F
        rest = body.rest
        out = {}
        to_head = mats[mr.head] @ rest[mr.head].inverted()
        to_jaw = mats[mr.jaw] @ rest[mr.jaw].inverted()
        hinge = to_head @ mr.hinge
        up_tip, low_tip = to_head @ mr.upper_tip, to_jaw @ mr.lower_tip
        out["gape_deg"] = mr._angle(up_tip - hinge, low_tip - hinge) - mr.rest_gape
        # socket aim against the bisector of the two jaw lines
        a = (up_tip - hinge).normalized()
        b = (low_tip - hinge).normalized()
        bis = (a + b).normalized()
        rest_bis = ((mr.upper_tip - mr.hinge).normalized()
                    + (mr.lower_tip - mr.hinge).normalized()).normalized()
        # the socket keeps its rest aim relative to the bisector: it turns with it
        carried_bis = (to_head.to_3x3() @ rest_bis).normalized()
        R_bis = carried_bis.rotation_difference(bis).to_matrix()
        s_rest = (to_head.to_3x3() @ (rest[mr.mouth].to_3x3() @ Vector((0, 1, 0)))).normalized()
        s_now = (mats[mr.mouth].to_3x3() @ Vector((0, 1, 0))).normalized()
        out["socket_error_deg"] = math.degrees(s_now.angle(R_bis @ s_rest))
        out["aperture_height"] = (up_tip - low_tip).length
        stretch, at, flipped, rigid_err = 1.0, None, 0, 0.0
        vol_change = 0.0
        for m in self.meshes:
            pos, deform = self._skin(mats, m)
            for e in m["edges"]:
                r = (pos[e[0]] - pos[e[1]]).length / m["rest_len"][e]
                if m["comp"][e[0]] in m["body"]:
                    if r > stretch:
                        stretch, at = r, F.ulh(m["cos"][e[0]])[0]
                elif m["rigid"][m["comp"][e[0]]]:
                    rigid_err = max(rigid_err, abs(r - 1.0))
            for fi, f in enumerate(m["faces"]):
                if m["comp"][f[0]] not in m["body"]:
                    continue
                n0, n1 = Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, 0.0))
                for k in range(len(f)):
                    p, q = m["cos"][f[k]], m["cos"][f[(k + 1) % len(f)]]
                    n0 += p.cross(q)
                    p, q = pos[f[k]], pos[f[(k + 1) % len(f)]]
                    n1 += p.cross(q)
                w = m["ws"][f[0]]
                if w and n0.length > 1e-12 and n1.length > 1e-12 and not m["sliver"][fi]:
                    top = max(w, key=w.get)
                    if n1.dot(deform[top].to_3x3() @ n0) < 0.0:
                        flipped += 1
                # divergence theorem, only faces that can move
                if len(f) >= 3:
                    for k in range(1, len(f) - 1):
                        a0, b0, c0 = m["cos"][f[0]], m["cos"][f[k]], m["cos"][f[k + 1]]
                        a1, b1, c1 = pos[f[0]], pos[f[k]], pos[f[k + 1]]
                        vol_change += (a1.dot(b1.cross(c1)) - a0.dot(b0.cross(c0))) / 6.0
        out["stretch_max"] = stretch
        out["stretch_at"] = at
        out["flipped_faces"] = flipped
        out["rigid_error"] = rigid_err
        out["volume_change"] = vol_change
        # jaw into the body: chin and jaw midpoint against the neck and chest
        worst, where = float("inf"), None
        pts = [low_tip, (hinge + low_tip) * 0.5]
        for n in self.axial:
            r = self.radius.get(n, 0.0)
            if r <= 0.0:
                continue
            from .motion import tail_of
            aa, bb = mats[n].translation, tail_of(body, mats, n)
            for p in pts:
                q = self._seg_dist(p, aa, bb) / r
                if q < worst:
                    worst, where = q, n
        out["jaw_clearance"] = worst
        out["jaw_clearance_at"] = where
        return out


def _check_maw(poser, checks, keyed, ev, infos, asked, loop=False, aquatic=False,
               starts_at_rest=True, stretch_limit=None):
    """Common checks with the feet planted, then the maw's own on every frame.
    `asked` maps frame -> the state that frame was posed with."""
    from .actions import _check_common, _pose_gap
    body, bm = poser.body, poser.bm
    stretch_limit = stretch_limit or poser.maw_rig.spec.get("stretch_limit", STRETCH_LIMIT)
    r = _check_common(body, bm, keyed, ev, infos, planted=poser.legs,
                      posed_limbs=poser.legs, rest_floor=bm["floor"],
                      starts_at_rest=starts_at_rest)
    if aquatic:
        # a swimmer's jaw opens below its belly; there is no floor to go through
        dropped = [f for f in r["failures"] if "the floor" in f]
        r["failures"] = [f for f in r["failures"] if "the floor" not in f]
        r["note_floor"] = "aquatic: %d floor failure(s) ignored" % len(dropped)
    evaluated = ev["evaluated"]
    frames = [f for f, _ in keyed]
    rest_m = checks.measure(body.fk())
    allowed_clear = min(0.8, 0.9 * rest_m["jaw_clearance"])
    worst = {"gape_error": 0.0, "stretch": 1.0, "flipped": 0, "rigid": 0.0, "socket": 0.0,
             "clear": float("inf")}
    per = {}
    for f in frames:
        m = checks.measure(evaluated[f])
        per[f] = m
        total, _ = poser.maw_rig.angles(asked[f])
        worst["gape_error"] = max(worst["gape_error"], abs(m["gape_deg"] - total))
        if m["stretch_max"] > worst["stretch"]:
            worst["stretch"], worst["stretch_frame"], worst["stretch_u"] = m["stretch_max"], f, m["stretch_at"]
        if m["flipped_faces"] - rest_m["flipped_faces"] > worst["flipped"]:
            worst["flipped"], worst["flipped_frame"] = m["flipped_faces"] - rest_m["flipped_faces"], f
        worst["rigid"] = max(worst["rigid"], m["rigid_error"])
        worst["socket"] = max(worst["socket"], m["socket_error_deg"])
        if m["jaw_clearance"] < worst["clear"]:
            worst["clear"], worst["clear_frame"], worst["clear_at"] = m["jaw_clearance"], f, m["jaw_clearance_at"]
    sc = checks.scale
    mr = poser.maw_rig
    L = mr.d["mouth_length"]
    r["gape_max_measured_deg"] = round(max(per[f]["gape_deg"] for f in frames), 2)
    r["gape_kind_max_deg"] = mr.spec["gape"]
    r["gape_skin_max_deg"] = round(mr.gape_max, 2)
    r["gape_error_deg"] = round(worst["gape_error"], 3)
    if worst["gape_error"] > 0.5:
        r["failures"].append("Blender opens the jaws %.2f degrees away from the pose asked"
                             % worst["gape_error"])
    r["stretch_max"] = round(worst["stretch"], 3)
    if worst["stretch"] > 1.0 + 1e-6:
        r["stretch_where"] = ("frame %d, %.0f%% of the mouth back from the tip"
                              % (worst["stretch_frame"],
                                 100 * (mr.d["u_tip"] - worst["stretch_u"]) / L))
    if worst["stretch"] > stretch_limit:
        r["failures"].append("skin stretches to %.0f%% of its rest length (%s) - past %.0f%%, "
                             "where a seam tears" % (100 * worst["stretch"], r["stretch_where"],
                                                     100 * stretch_limit))
    over = [f for f in frames if per[f]["stretch_max"] > MUSCLE_STRETCH]
    if over:
        f0 = min(over, key=lambda f: per[f]["gape_deg"])
        r["gape_at_muscle_stretch_deg"] = round(per[f0]["gape_deg"], 1)
    r["flipped_faces"] = worst["flipped"]
    if worst["flipped"]:
        r["failures"].append("%d faces turn inside out at frame %d - the lips or corner fold "
                             "through themselves" % (worst["flipped"], worst["flipped_frame"]))
    r["rigid_error"] = round(worst["rigid"], 6)
    if worst["rigid"] > 1e-3:
        r["failures"].append("a rigid part (tooth, baleen) bends by %.2f%%" % (100 * worst["rigid"]))
    r["socket_error_deg"] = round(worst["socket"], 3)
    if worst["socket"] > 0.5:
        r["failures"].append("the mouth socket is %.1f degrees off the jaws' bisector" % worst["socket"])
    r["jaw_clearance"] = round(worst["clear"], 3)
    r["jaw_clearance_allowed"] = round(allowed_clear, 3)
    if worst["clear"] < allowed_clear:
        r["failures"].append("the jaw passes into the %s at frame %d (%.2f of its radius)"
                             % (worst["clear_at"], worst["clear_frame"], worst["clear"]))
    width = 2.0 * mr.d.get("mouth_half_width", mr.d["corner_half_width"])
    best = max(frames, key=lambda f: per[f]["aperture_height"])
    h = per[best]["aperture_height"]
    area = math.pi / 4.0 * width * h
    r["aperture_m2"] = round(area * sc * sc, 5)
    # a pyramid from the aperture back to the corner - geometry, labelled as such
    r["mouth_volume_m3"] = round(area * L / 3.0 * sc ** 3, 5)
    r["volume_gain_m3"] = round(max(per[f]["volume_change"] for f in frames) * sc ** 3, 5)
    r["per_frame"] = {f: {"gape_deg": round(per[f]["gape_deg"], 2),
                          "aperture_m": round(per[f]["aperture_height"] * sc, 4),
                          "volume_gain_m3": round(per[f]["volume_change"] * sc ** 3, 5)}
                      for f in frames}
    if loop:
        seam, bone = _pose_gap(body.rig, evaluated[frames[0]], evaluated[frames[-1]])
        r["loop_seam"] = round(seam, 6)
        if seam > 1e-4 * bm["size"]:
            r["failures"].append("loop seam %.5f on %s" % (seam, bone))
    return r


# --------------------------------------------------------------------------
# timing from size
# --------------------------------------------------------------------------

G = 9.81
# One bite cycle in units of sqrt(mouth length / g): a juvenile alligator's
# feeding cycle is 0.21-0.23 s (PMC5192416) for a mouth of roughly 6 cm - the
# mouth length is an assumption. Dynamic similarity, as `locomotion` does with
# the Froude number, carries it to other sizes.
BITE_K = 2.8
# Engulfment (rorquals): 1.2 s at 8 m, 5.7 s at 22 m, 6.6 s at 27 m (PMC8179629;
# Goldbogen 2006). A power law through the two ends: 0.065 L^1.4 seconds.
ENGULF_A, ENGULF_B = 0.065, 1.4
# Purge after engulfment: 27.5-61.9 s.
PURGE_S = 45.0


def timing(poser, fps):
    mr = poser.maw_rig
    sc = sum(poser.rig.matrix_world.to_scale()) / 3.0
    L = mr.d["mouth_length"] * sc
    t0 = math.sqrt(L / G)
    body_len = poser.bm["size"] * sc
    return {"mouth_length_m": L, "t0_s": t0, "bite_cycle_s": BITE_K * t0,
            "engulf_s": ENGULF_A * body_len ** ENGULF_B, "body_length_m": body_len,
            "fps": fps}


# --------------------------------------------------------------------------
# clips
# --------------------------------------------------------------------------

def _setup(rig_name, forward, up, floor):
    from . import bodymap, keyposes as kp, motion
    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return None, bm
    if not bm.get("maw"):
        return None, {"error": "%s has no maw - run maw.detect / build / skin first" % rig_name}
    rig = bpy.data.objects[rig_name]
    body = motion.Body(rig, bm)
    P = kp.Poser(body)
    return (bm, rig, body, P, MawChecks(P)), None


def _track(frames, keys):
    """Piecewise-eased state per frame. `keys` is [(frame, state, ease)] where
    ease names how the segment INTO that key runs: smooth, in (slow start,
    fast finish - a snap), out (fast start), linear."""
    eases = {
        "smooth": _smooth,
        "in": lambda t: t * t * t,
        "out": lambda t: 1.0 - (1.0 - t) ** 3,
        "linear": lambda t: max(0.0, min(1.0, t)),
    }
    out = {}
    for f in range(1, frames + 1):
        prev = keys[0]
        for k in keys[1:]:
            if f <= k[0]:
                t = (f - prev[0]) / float(max(k[0] - prev[0], 1))
                out[f] = blend_states(prev[1], k[1], eases[k[2]](t))
                break
            prev = k
        else:
            out[f] = dict(REST_STATE, **keys[-1][1])
    return out


def _author_maw(rig_name, action_name, frames, states_fn, forward, up, floor, fps,
                aquatic=False, loop=False, starts_at_rest=True, extra_check=None,
                stretch_limit=None):
    from . import keyposes as kp
    from .actions import _author_samples
    ctx, err = _setup(rig_name, forward, up, floor)
    if err:
        return err, None
    bm, rig, body, P, checks = ctx
    asked = states_fn(P, frames)
    samples = [P.pose(kp.Key(name="maw", maw=asked[f])) for f in range(1, frames + 1)]

    def check(keyed, ev, infos):
        r = _check_maw(P, checks, keyed, ev, infos, asked, loop=loop, aquatic=aquatic,
                       starts_at_rest=starts_at_rest, stretch_limit=stretch_limit)
        if extra_check:
            extra_check(r, P, keyed, ev)
        return r

    keyed, infos, action, report = _author_samples(body, rig, action_name, samples, fps, check)
    if "error" not in report:
        report.update({"rig": rig.name, "action": action.name, "frames": [1, frames],
                       "fps": bpy.context.scene.render.fps})
    return report, (P, asked)


def _frames_for(seconds, fps, minimum):
    return max(minimum, int(round(seconds * fps)) + 1)


def gape(rig_name, frames=None, forward="-Y", up="Z", floor=0.0, action_name="Gape", fps=None,
         aquatic=False, amount=1.0):
    """Rest -> jaws wide open, held. Play backwards to close."""
    fps_now = fps or bpy.context.scene.render.fps

    def states(P, n):
        return _track(n, [(1, state(), "smooth"), (n, state(gape=amount), "smooth")])
    probe, err = _setup(rig_name, forward, up, floor)
    if probe is None:
        return err
    tm = timing(probe[3], fps_now)
    n = frames or _frames_for(1.5 * tm["bite_cycle_s"], fps_now, 10)
    r, _ = _author_maw(rig_name, action_name, n, states, forward, up, floor, fps, aquatic=aquatic)
    if "error" not in r:
        r.update({"role": "Gape", "timing": _round(tm)})
    return r


def bite(rig_name, frames=None, forward="-Y", up="Z", floor=0.0, action_name="Bite", fps=None,
         aquatic=False, open_to=0.7, contact_deg=15.0):
    """Slow open -> snap shut -> settle. One cycle at the size-scaled bite time.

    Lizards open slowly and crocodilians close fast; the head dips into the snap.
    `contact_s` is the first closing frame at or under `contact_deg` of gape - the
    engine's damage window opens there and closes at `end_s`.
    """
    fps_now = fps or bpy.context.scene.render.fps
    probe, err = _setup(rig_name, forward, up, floor)
    if probe is None:
        return err
    tm = timing(probe[3], fps_now)
    n = frames or _frames_for(tm["bite_cycle_s"], fps_now, 12)
    k_open, k_snap = max(2, round(0.55 * n)), max(3, round(0.78 * n))

    def states(P, nn):
        return _track(nn, [(1, state(), "smooth"),
                           (k_open, state(gape=open_to, pitch=4.0, tongue=-0.3), "out"),
                           (k_snap, state(gape=0.0, pitch=-5.0), "in"),
                           (nn, state(), "smooth")])
    r, ctx = _author_maw(rig_name, action_name, n, states, forward, up, floor, fps, aquatic=aquatic)
    if "error" in r:
        return r
    per = r["per_frame"]
    contact = next((f for f in range(k_open, n + 1) if per[f]["gape_deg"] <= contact_deg), k_snap)
    r.update({"role": "Bite", "timing": _round(tm), "open_frame": k_open, "snap_frame": k_snap,
              "open_s": (k_open - 1) / float(fps_now), "contact_s": (contact - 1) / float(fps_now),
              "end_s": (k_snap - 1) / float(fps_now) + 2.0 / fps_now,
              "length_s": (n - 1) / float(fps_now), "contact_deg": contact_deg})
    return r


def roar(rig_name, frames=None, forward="-Y", up="Z", floor=0.0, action_name="Roar", fps=None,
         aquatic=False):
    """Head back, jaws wide, throat pulsing, then closed. Twelve bite-units long:
    a design length, not a measurement."""
    fps_now = fps or bpy.context.scene.render.fps
    probe, err = _setup(rig_name, forward, up, floor)
    if probe is None:
        return err
    tm = timing(probe[3], fps_now)
    n = frames or _frames_for(4.0 * tm["bite_cycle_s"], fps_now, 36)
    k_open, k_close = round(0.22 * n), round(0.8 * n)

    def states(P, nn):
        base = _track(nn, [(1, state(), "smooth"),
                           (round(0.1 * nn), state(gape=0.1, pitch=-3.0, throat=0.3), "smooth"),
                           (k_open, state(gape=0.95, pitch=14.0, throat=0.2, tongue=0.4), "out"),
                           (k_close, state(gape=0.85, pitch=10.0, throat=0.15, tongue=0.3), "linear"),
                           (nn, state(), "smooth")])
        for f in range(k_open, k_close + 1):
            t = (f - k_open) / float(fps_now)
            base[f]["gape"] += 0.02 * math.sin(2 * math.pi * 9.0 * t)
            base[f]["throat"] += 0.08 * (0.5 + 0.5 * math.sin(2 * math.pi * 6.0 * t))
        return base
    r, _ = _author_maw(rig_name, action_name, n, states, forward, up, floor, fps, aquatic=aquatic)
    if "error" not in r:
        r.update({"role": "Roar", "timing": _round(tm), "peak_s": (k_open - 1) / float(fps_now)})
    return r


BREATH_LOOP = {"gape": 0.75, "throat": 0.3, "tongue": -0.6}
# Fire leaves along the socket - the bisector of the open jaws, which points
# half the gape below the skull. Left there, the test dragon's blast went 31
# degrees down into the ground two metres out. Animals lift the head as the jaw
# drops; the breath clips lift it until the bisector points this far below the
# head's rest aim.
AIM_DOWN_DEG = 12.0


def breath_pitch(mr, gape=BREATH_LOOP["gape"], aim_down=AIM_DOWN_DEG):
    """Head pitch, degrees, that aims the jaws' bisector `aim_down` below rest."""
    total = gape * mr.gape_max
    return 0.5 * total - mr.spec["lift_share"] * total - aim_down


def _breath_loop_state(p, pitch):
    s = dict(BREATH_LOOP, pitch=pitch)
    s["gape"] += 0.03 * math.sin(2 * math.pi * p)
    s["pitch"] += 1.5 * math.sin(2 * math.pi * p + 1.0)
    s["throat"] -= 0.05 * math.cos(2 * math.pi * 2 * p)
    return s


def breath_start(rig_name, frames=None, forward="-Y", up="Z", floor=0.0,
                 action_name="BreathStart", loop_clip="Breath", fps=None, aquatic=False):
    """Inhale - throat swelling, head drawn back, jaws parted - then the exhale:
    head thrown forward, jaws wide. Ends on the Breath loop's first frame.

    Animators key a clear inhale before a sharp exhale; the charge-up is what
    sells a big blast. `fire_start_s` is where the jaws pass half their opening
    on the way out - where the engine lights the fire.
    """
    from .actions import _evaluated_frame, _pose_gap
    fps_now = fps or bpy.context.scene.render.fps
    probe, err = _setup(rig_name, forward, up, floor)
    if probe is None:
        return err
    tm = timing(probe[3], fps_now)
    n = frames or _frames_for(3.0 * tm["bite_cycle_s"], fps_now, 24)
    k_in = round(0.62 * n)
    before = _evaluated_frame(bpy.data.objects[rig_name], loop_clip, 1)

    def states(P, nn):
        return _track(nn, [(1, state(), "smooth"),
                           (k_in, state(gape=0.12, throat=0.85, pitch=breath_pitch(P.maw_rig) + 12.0,
                                        tongue=0.2), "smooth"),
                           (nn, _breath_loop_state(0.0, breath_pitch(P.maw_rig)), "out")])

    def extra(r, P, keyed, ev):
        if before is None:
            r["failures"].append("no %s clip to measure the end seam against" % loop_clip)
            return
        gap, bone = _pose_gap(P.rig, ev["evaluated"][keyed[-1][0]], before)
        r["seams"] = {"to " + loop_clip: round(gap, 6)}
        if gap > 0.002 * P.bm["size"]:
            r["failures"].append("last frame is %.4f from %s's first (%s)" % (gap, loop_clip, bone))
    r, _ = _author_maw(rig_name, action_name, n, states, forward, up, floor, fps, aquatic=aquatic,
                       extra_check=extra)
    if "error" in r:
        return r
    per = r["per_frame"]
    half = 0.5 * BREATH_LOOP["gape"] * probe[3].maw_rig.spec["gape"]
    fire = next((f for f in range(k_in, n + 1) if per[f]["gape_deg"] >= half), n)
    r.update({"role": "BreathStart", "timing": _round(tm), "inhale_frame": k_in,
              "fire_start_s": (fire - 1) / float(fps_now), "length_s": (n - 1) / float(fps_now)})
    return r


def breath(rig_name, frames=None, forward="-Y", up="Z", floor=0.0, action_name="Breath",
           fps=None, aquatic=False):
    """Loop: jaws held wide, head steady on the blast, throat working."""
    fps_now = fps or bpy.context.scene.render.fps
    n = frames or 24

    def states(P, nn):
        return {f: _breath_loop_state((f - 1) / float(nn - 1), breath_pitch(P.maw_rig))
                for f in range(1, nn + 1)}
    r, _ = _author_maw(rig_name, action_name, n, states, forward, up, floor, fps, aquatic=aquatic,
                       loop=True, starts_at_rest=False)
    if "error" not in r:
        r.update({"role": "Breath"})
    return r


def breath_end(rig_name, frames=None, forward="-Y", up="Z", floor=0.0, action_name="BreathEnd",
               loop_clip="Breath", fps=None, aquatic=False):
    """Breath's first frame -> jaws closing, throat settling -> rest."""
    from .actions import _evaluated_frame, _pose_gap
    fps_now = fps or bpy.context.scene.render.fps
    probe, err = _setup(rig_name, forward, up, floor)
    if probe is None:
        return err
    tm = timing(probe[3], fps_now)
    n = frames or _frames_for(1.5 * tm["bite_cycle_s"], fps_now, 12)
    before = _evaluated_frame(bpy.data.objects[rig_name], loop_clip, 1)

    def states(P, nn):
        return _track(nn, [(1, _breath_loop_state(0.0, breath_pitch(P.maw_rig)), "smooth"),
                           (round(0.55 * nn), state(gape=0.15, pitch=-2.0, throat=0.1), "smooth"),
                           (nn, state(), "smooth")])

    def extra(r, P, keyed, ev):
        if before is None:
            r["failures"].append("no %s clip to measure the start seam against" % loop_clip)
            return
        gap, bone = _pose_gap(P.rig, ev["evaluated"][keyed[0][0]], before)
        rest_gap, rbone = _pose_gap(P.rig, ev["evaluated"][keyed[-1][0]], P.body.ground_rest
                                    if getattr(P.body, "ground_rest", None) else P.body.fk())
        r["seams"] = {"from " + loop_clip: round(gap, 6), "to rest": round(rest_gap, 6)}
        if gap > 0.002 * P.bm["size"]:
            r["failures"].append("first frame is %.4f from %s's first (%s)" % (gap, loop_clip, bone))
        if rest_gap > 0.002 * P.bm["size"]:
            r["failures"].append("last frame is %.4f from rest (%s)" % (rest_gap, rbone))
    r, _ = _author_maw(rig_name, action_name, n, states, forward, up, floor, fps, aquatic=aquatic,
                       starts_at_rest=False, extra_check=extra)
    if "error" not in r:
        r.update({"role": "BreathEnd", "length_s": (n - 1) / float(fps_now)})
    return r


def swallow(rig_name, frames=None, forward="-Y", up="Z", floor=0.0, action_name="Swallow",
            fps=None, aquatic=False):
    """Jaws shut, tongue pressing up, throat bulging then settling: a gulp."""
    fps_now = fps or bpy.context.scene.render.fps
    probe, err = _setup(rig_name, forward, up, floor)
    if probe is None:
        return err
    tm = timing(probe[3], fps_now)
    n = frames or _frames_for(2.5 * tm["bite_cycle_s"], fps_now, 16)

    def states(P, nn):
        return _track(nn, [(1, state(), "smooth"),
                           (round(0.3 * nn), state(tongue=0.8, pitch=6.0), "smooth"),
                           (round(0.55 * nn), state(tongue=0.4, throat=0.45, pitch=-4.0), "smooth"),
                           (nn, state(), "smooth")])
    r, _ = _author_maw(rig_name, action_name, n, states, forward, up, floor, fps, aquatic=aquatic)
    if "error" not in r:
        r.update({"role": "Swallow", "length_s": (n - 1) / float(fps_now)})
    return r


def engulf(rig_name, frames=None, forward="-Y", up="Z", floor=0.0, action_name="Engulf",
           fps=None, aquatic=True):
    """A lunge: the mouth opens to its maximum over half the engulfment, the
    throat balloons behind it, and the jaws close on a full pouch.

    Engulfment time follows body length (1.2 s at 8 m to 6.6 s at 27 m); a fin
    whale opens for ~3 s and closes for ~3 s, so the two halves are equal. The
    clip ends with the pouch full: `Purge` empties it.
    """
    fps_now = fps or bpy.context.scene.render.fps
    probe, err = _setup(rig_name, forward, up, floor)
    if probe is None:
        return err
    tm = timing(probe[3], fps_now)
    n = frames or _frames_for(tm["engulf_s"], fps_now, 24)
    k_max = round(0.5 * n)

    def states(P, nn):
        return _track(nn, [(1, state(), "smooth"),
                           (round(0.18 * nn), state(gape=0.25, throat=0.05), "in"),
                           (k_max, state(gape=1.0, throat=0.55, tongue=-0.5), "out"),
                           (round(0.78 * nn), state(gape=0.45, throat=1.0, tongue=-0.3), "smooth"),
                           (nn, state(gape=0.0, throat=1.0), "smooth")])
    r, _ = _author_maw(rig_name, action_name, n, states, forward, up, floor, fps, aquatic=aquatic)
    if "error" in r:
        return r
    per = r["per_frame"]
    opening = next((f for f in range(1, n + 1) if per[f]["gape_deg"] >= 5.0), 1)
    closed = next((f for f in range(k_max, n + 1) if per[f]["gape_deg"] <= 5.0), n)
    r.update({"role": "Engulf", "timing": _round(tm), "open_s": (opening - 1) / float(fps_now),
              "max_gape_s": (k_max - 1) / float(fps_now), "close_s": (closed - 1) / float(fps_now),
              "length_s": (n - 1) / float(fps_now),
              "engulf_s_from_size": round(tm["engulf_s"], 3)})
    return r


def purge(rig_name, frames=48, forward="-Y", up="Z", floor=0.0, action_name="Purge",
          engulf_clip="Engulf", fps=None, aquatic=True, seconds=PURGE_S):
    """Engulf's last frame -> the pouch emptying through barely parted jaws.

    A real purge takes 27.5-61.9 s. The clip is short and the engine plays it
    at `playback_speed_scale`.
    """
    from .actions import _evaluated_frame, _pose_gap
    fps_now = fps or bpy.context.scene.render.fps
    before = _evaluated_frame(bpy.data.objects[rig_name], engulf_clip, None)

    def states(P, nn):
        return _track(nn, [(1, state(throat=1.0), "smooth"),
                           (round(0.15 * nn), state(gape=0.06, throat=0.9), "smooth"),
                           (round(0.85 * nn), state(gape=0.05, throat=0.08), "linear"),
                           (nn, state(), "smooth")])

    def extra(r, P, keyed, ev):
        if before is None:
            r["failures"].append("no %s clip to measure the start seam against" % engulf_clip)
            return
        gap, bone = _pose_gap(P.rig, ev["evaluated"][keyed[0][0]], before)
        r["seams"] = {"from " + engulf_clip: round(gap, 6)}
        if gap > 0.002 * P.bm["size"]:
            r["failures"].append("first frame is %.4f from %s's last (%s)" % (gap, engulf_clip, bone))
    r, _ = _author_maw(rig_name, action_name, frames, states, forward, up, floor, fps,
                       aquatic=aquatic, starts_at_rest=False, extra_check=extra)
    if "error" not in r:
        dur = (frames - 1) / float(fps_now)
        r.update({"role": "Purge", "purge_s": seconds,
                  "playback_speed_scale": round(dur / seconds, 5)})
    return r


DEFAULT_ROLES = {
    "rorqual": ("Gape", "Engulf", "Purge", "Swallow"),
    "_": ("Gape", "Bite", "Roar", "Breath", "BreathStart", "BreathEnd", "Swallow"),
}


def maw_set(rig_name, prefix=None, forward="-Y", up="Z", floor=0.0, fps=None, aquatic=None,
            roles=None):
    """Author every mouth clip for one creature. Returns {role: report}.

    Order matters: BreathStart and BreathEnd measure their seams against this
    set's Breath, Purge against its Engulf."""
    rig = bpy.data.objects[rig_name]
    d = read(rig)
    if d is None:
        return {"error": "%s has no maw - run maw.detect / build / skin first" % rig_name}
    prefix = prefix or rig_name
    kind = d["kind"]
    if aquatic is None:
        aquatic = kind == "rorqual"
    roles = roles or DEFAULT_ROLES.get(kind, DEFAULT_ROLES["_"])
    name = lambda role: "%s_%s" % (prefix, role)
    common = dict(forward=forward, up=up, floor=floor, fps=fps, aquatic=aquatic)
    makers = {
        "Gape": lambda: gape(rig_name, action_name=name("Gape"), **common),
        "Bite": lambda: bite(rig_name, action_name=name("Bite"), **common),
        "Roar": lambda: roar(rig_name, action_name=name("Roar"), **common),
        "Breath": lambda: breath(rig_name, action_name=name("Breath"), **common),
        "BreathStart": lambda: breath_start(rig_name, action_name=name("BreathStart"),
                                            loop_clip=name("Breath"), **common),
        "BreathEnd": lambda: breath_end(rig_name, action_name=name("BreathEnd"),
                                        loop_clip=name("Breath"), **common),
        "Swallow": lambda: swallow(rig_name, action_name=name("Swallow"), **common),
        "Engulf": lambda: engulf(rig_name, action_name=name("Engulf"), **common),
        "Purge": lambda: purge(rig_name, action_name=name("Purge"), engulf_clip=name("Engulf"),
                               **common),
    }
    return {role: makers[role]() for role in roles}


def engine_manifest(reports, rig_name):
    """The `maw` entry of `.moves.json`, from `maw_set` reports."""
    rig = bpy.data.objects[rig_name]
    d = read(rig)
    sc = sum(rig.matrix_world.to_scale()) / 3.0
    fps = float(bpy.context.scene.render.fps)
    problems = ["%s did not pass: %s" % (role, "; ".join(r.get("failures", [])))
                for role, r in reports.items() if isinstance(r, dict) and "error" not in r
                and not r.get("passed")]
    problems += ["%s: %s" % (role, r["error"]) for role, r in reports.items()
                 if isinstance(r, dict) and "error" in r]
    ok = {k: r for k, r in reports.items() if isinstance(r, dict) and "error" not in r}
    widest = max(ok.values(), key=lambda r: r.get("aperture_m2", 0.0), default={})
    out = {
        "kind": d["kind"],
        # what gape 1 opens to: the kind's maximum, or less where the skin folds
        "gape_max_deg": round(min(d["spec"]["gape"], d.get("gape_clean_deg") or d["spec"]["gape"]), 2),
        "gape_kind_max_deg": d["spec"]["gape"], "lift_share": d["spec"]["lift_share"],
        "bones": {"head": d["head"], "jaw": d["jaw"], "throat": d["throat"], "gular": d.get("gular"),
                  "mouth": d["mouth"],
                  "tongue": d["tongue"]},
        # tracks an engine layers over locomotion: every maw clip moves only these
        "layer_bones": ([d["head"], d["jaw"], d["throat"], d["mouth"]] + list(d["tongue"])
                        + ([d["gular"]] if d.get("gular") else [])),
        "mouth_length_m": round(d["mouth_length"] * sc, 4),
        "mouth_width_m": round(2.0 * d.get("mouth_half_width", d["corner_half_width"]) * sc, 4),
        "aperture_max_m2": widest.get("aperture_m2"),
        "mouth_volume_m3": widest.get("mouth_volume_m3"),
        "throat_volume_gain_m3": max((r.get("volume_gain_m3", 0.0) for r in ok.values()), default=0.0),
        "stretch_max": max((r.get("stretch_max", 1.0) for r in ok.values()), default=1.0),
        "clips": {role: r["action"] for role, r in ok.items()},
        "problems": problems,
    }
    if "Bite" in ok:
        b = ok["Bite"]
        out["bite"] = {k: round(b[k], 4) for k in ("open_s", "contact_s", "end_s", "length_s")}
    if "BreathStart" in ok:
        out["breath"] = {"fire_start_s": round(ok["BreathStart"]["fire_start_s"], 4),
                         "start_length_s": round(ok["BreathStart"]["length_s"], 4),
                         "end_length_s": round(ok.get("BreathEnd", {}).get("length_s", 0.0), 4)}
    if "Engulf" in ok:
        e = ok["Engulf"]
        out["engulf"] = {k: round(e[k], 4) for k in ("open_s", "max_gape_s", "close_s", "length_s")}
    if "Purge" in ok:
        out["purge"] = {"seconds": ok["Purge"]["purge_s"],
                        "playback_speed_scale": ok["Purge"]["playback_speed_scale"]}
    if "Roar" in ok:
        out["roar"] = {"peak_s": round(ok["Roar"]["peak_s"], 4)}
    return out


def summarize(r):
    from .actions import summarize as base
    if "error" in r:
        return "ERROR: " + r["error"]
    lines = [base(r)]
    for k in ("gape_max_measured_deg", "gape_error_deg", "stretch_max", "stretch_where",
              "gape_at_muscle_stretch_deg",
              "flipped_faces", "rigid_error", "socket_error_deg", "jaw_clearance",
              "aperture_m2", "mouth_volume_m3", "volume_gain_m3", "loop_seam", "seams",
              "open_s", "contact_s", "fire_start_s", "max_gape_s", "close_s",
              "playback_speed_scale", "note_floor"):
        if r.get(k) is not None:
            lines.append("  %s %s" % (k, r[k]))
    return "\n".join(lines)


def _round(d):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}
