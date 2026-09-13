"""Wings: find them on any rig, then fold, spread, flap and glide on them.

A wing is a limb in a third role. `bodymap` already calls a grounded limb a leg
and a free one an arm; a free limb whose skin is a SHEET is a wing. That test
is measured, not read from names - the generic builder calls a dragon's wing
`arm1_upper.L` and a hand-built rig may call it `upperarm.L` - though a bone
called wing, feather, primary or patagium is taken at its word, which is what
lets a bare Rigify bird metarig with no skin be read at all.

RECOGNITION
-----------

For each free limb, the skin its bones dominate is measured:

- thickness: the smallest principal spread of that skin over the middle one.
  An arm is a tube (near 1); a membrane or a feathered wing is a sheet (0.1).
- planform: the skin's faces projected onto the sheet's own plane, halved
  because a closed sheet is counted top and bottom. Over reach squared it
  separates a paddle from a stick.
- structure: two or more long chains fanning off the hand is a MEMBRANE wing
  (bat, dragon, pterosaur's single finger aside); a hand carrying a primary
  chain, or feather bones branching off the arm segments, is FEATHERED; a
  wing with no hand segment is SIMPLE (and folds as one hinge).

POSING
------

A wing is not solved by IK: nothing it does is a contact. It is posed as a
chain of rigid segments in its own frame, measured from the rest shape:

    o  outward along the rest span, in the sheet's plane
    b  backward, in the sheet's plane
    k  o x b - the fold axis, so a positive angle always swings a segment
       toward the tail, on either side, whatever the bone roll

Every segment's rest angle in that plane is measured, and a pose asks for
absolute angles. One number, `fold`, interpolates every segment toward its
folded angle together, which is the avian automatic linkage: the radius slides
along the ulna so elbow and wrist flex as one (Fisher 1957; Vazquez 1994) - the
humerus swings back, the forearm forward, the hand back again into a Z. A
membrane wing does the same with its fingers collapsing into a bundle.

Then, about the shoulder, in this order: `tuck` (a folded wing rolls down
along the flank), `stroke` (elevation: + up), `sweep` (+ tip forward) and
`twist` (+ leading edge down - pronation - growing toward the tip). All axes
are built from the body map's fwd / up / lat and the wing's own outward
direction, so the same number means the same thing on both sides.

fold = 0 with every angle 0 reproduces rest exactly. A negative fold spreads a
wing modelled folded.

FLIGHT NUMBERS
--------------

What `locomotion` does with the Froude number, `plan` does with size: wing
area and span are measured, mass comes from the skinned volume, and wingbeat
frequency, cruise speed, glide speed and sink rate follow from published
scaling relationships - see `references/wings.md` in animate-anything.
"""

from __future__ import annotations

import math
import re

import bpy
from mathutils import Matrix, Vector

NAME = re.compile(r"wing|feather|primar|secondar|tertial|alula|patag|membrane|pteroid|remige",
                  re.I)
FEATHER = re.compile(r"feather|primar|secondar|tertial|remige", re.I)

# Folded in-plane angles (degrees from outward toward the tail) per segment.
# Humerus back along the flank, forearm forward, hand back again: a Z. No
# measured table of folded joint angles was found; these give an elbow of
# ~43 and a wrist of ~30 degrees included for a bird, the middle of what
# references show, and a tighter wrist for a membrane wing, whose fingers lie
# back along the forearm.
FOLDED = {
    "feathered": {"upper": 72.0, "lower": -65.0, "end": 85.0, "digit": 90.0},
    "membrane": {"upper": 70.0, "lower": -70.0, "end": 90.0, "digit": 95.0},
    "simple": {"upper": 70.0, "lower": 100.0, "end": 100.0, "digit": 100.0},
}
# Spread angles, for a wing modelled folded and asked for fold < 0.
SPREAD = {"upper": 0.0, "lower": -4.0, "end": 4.0, "digit": 8.0}
# How far a folded wing rolls down against the flank, degrees.
TUCK = 55.0
# Twist reaches the tip in full; nearer the body it is a share of it (washout).
TWIST_SHARE = {"upper": 0.35, "lower": 0.7, "end": 1.0, "digit": 1.0}


def _wrap(a):
    return (a + 180.0) % 360.0 - 180.0


# --------------------------------------------------------------------------
# recognition
# --------------------------------------------------------------------------

def _bound_meshes(rig):
    return [o for o in bpy.data.objects if o.type == "MESH" and any(
        m.type == "ARMATURE" and m.object == rig for m in o.modifiers)]


def skin_table(rig):
    """[(armature-space coords, dominant bone per vertex, polygons)] per bound
    mesh. Cached on the armature data for the life of the call chain."""
    to_arm = rig.matrix_world.inverted()
    out = []
    bones = rig.data.bones
    for o in _bound_meshes(rig):
        names = {g.index: g.name for g in o.vertex_groups if g.name in bones}
        m = to_arm @ o.matrix_world
        cos, dom = [], []
        for v in o.data.vertices:
            best, bw = None, 0.0
            for g in v.groups:
                if g.group in names and g.weight > bw:
                    best, bw = names[g.group], g.weight
            cos.append(m @ v.co)
            dom.append(best)
        polys = [tuple(p.vertices) for p in o.data.polygons]
        out.append((cos, dom, polys))
    return out


def _descendants(bone, side):
    from .bodymap import side_of
    out = [bone]
    for c in bone.children:
        if side_of(c.name)[0] == side:
            out.extend(_descendants(c, side))
    return out


def _chain_from(bone, side):
    """Longest sided chain starting at `bone`."""
    from .bodymap import side_of
    chain = [bone]
    cur = bone
    while True:
        kids = [c for c in cur.children if side_of(c.name)[0] == side]
        if not kids:
            return chain
        cur = max(kids, key=lambda c: sum(x.length for x in _chain_from(c, side)))
        chain.append(cur)


def _pca(points):
    import numpy as np
    a = np.array([tuple(p) for p in points])
    c = a.mean(axis=0)
    w, v = np.linalg.eigh(np.cov((a - c).T))
    # ascending eigenvalues: v[:, 2] is the major axis, v[:, 0] the normal
    return (Vector(c), [max(float(x), 0.0) for x in w],
            [Vector(tuple(v[:, i])) for i in range(3)])


def planform(table, bone_names, root, up):
    """Measure the sheet a set of bones' skin forms. None without skin."""
    names = set(bone_names)
    pts, faces_area = [], None
    for cos, dom, _ in table:
        pts.extend(co for co, d in zip(cos, dom) if d in names)
    if len(pts) < 12:
        return None
    centre, lam, vecs = _pca(pts)
    normal = vecs[0].normalized()
    if normal.dot(up) < 0.0:
        normal = -normal
    thickness = math.sqrt(lam[0] / lam[1]) if lam[1] > 1e-12 else 1.0

    area = 0.0
    for cos, dom, polys in table:
        for poly in polys:
            inside = sum(1 for i in poly if dom[i] in names)
            if inside * 2 < len(poly):
                continue
            # Newell's area vector, projected on the sheet normal
            nv = Vector((0.0, 0.0, 0.0))
            for j in range(len(poly)):
                p, q = cos[poly[j]], cos[poly[(j + 1) % len(poly)]]
                nv += p.cross(q)
            area += abs(nv.dot(normal)) * 0.5
    area *= 0.5                 # a closed sheet is counted top and bottom

    tip, reach = None, 0.0
    for p in pts:
        d = p - root
        d = d - normal * d.dot(normal)
        if d.length > reach:
            reach, tip = d.length, p
    return {"normal": normal, "thickness": thickness, "area": area,
            "reach": reach, "tip": tip, "centroid": centre, "vertices": len(pts)}


def detect(rig, limbs, fwd, upv, lat, midline, grounded):
    """Find the wings among a body map's limbs. Mutates each wing limb's role
    to "wing" (unless it is grounded, which keeps it a leg and warns), and
    returns (wings, warnings).

    `grounded(limb)` says whether the body map found that limb on the ground;
    `midline` is the lateral coordinate of the body's centre plane.
    """
    from .bodymap import side_of
    bones = rig.data.bones
    table = skin_table(rig)
    wings, warnings = [], []
    for l in limbs:
        side = l["side"]
        upper = bones[l["upper"]]
        every = _descendants(upper, side)
        named = any(NAME.search(b.name) for b in every + ([bones[l["girdle"]]]
                                                           if l["girdle"] else []))
        root = l["rest_root"]
        pf = planform(table, [b.name for b in every], root, upv) if table else None
        sheet = False
        if pf is not None and pf["reach"] > 1e-9:
            sheet = pf["thickness"] <= 0.35 and pf["area"] / pf["reach"] ** 2 >= 0.12
        if not (named or sheet):
            continue
        if pf is None and not named:
            continue

        main = [l["upper"], l["lower"]] + ([l["end"]] if l["end"] else []) + l["digits"]
        end = bones[l["end"]] if l["end"] else None
        fingers = []
        if end is not None:
            for c in end.children:
                # Rigify's bird hangs w_feather bones off its hand; two of them
                # made it a bat.
                if side_of(c.name)[0] != side or (FEATHER.search(c.name)
                                                  and c.name not in main):
                    continue
                ch = [b.name for b in _chain_from(c, side)]
                if sum(bones[n].length for n in ch) >= 0.25 * l["b"]:
                    fingers.append(ch)
        in_fingers = {n for ch in fingers for n in ch}
        feathers = []           # (bone, the main-chain segment it hangs from)
        for seg in [l["upper"], l["lower"]] + ([l["end"]] if l["end"] else []):
            for c in bones[seg].children:
                if side_of(c.name)[0] != side or c.name in main or c.name in in_fingers:
                    continue
                for d in _descendants(c, side):
                    feathers.append((d.name, seg))
        if end is None:
            kind = "simple"
        elif len(fingers) >= 2:
            kind = "membrane"
        else:
            kind = "feathered"

        # modelled spread or folded: how straight the arm segments lie
        joints = [bones[l["upper"]].head_local, bones[l["lower"]].head_local,
                  (end.head_local if end else bones[l["lower"]].tail_local)]
        path = sum((joints[i + 1] - joints[i]).length for i in range(2))
        straightness = (joints[2] - joints[0]).length / max(path, 1e-9)

        outward = lat if (root.dot(lat) - midline) > 0.0 else -lat
        normal = pf["normal"] if pf else upv.copy()
        tip = pf["tip"] if pf else bones[main[-1]].tail_local
        span = tip - root
        o = span - normal * span.dot(normal)
        if o.length < 1e-9 or o.dot(outward) <= 0.0:
            o = outward - normal * outward.dot(normal)
        o.normalize()
        back = -fwd - normal * (-fwd).dot(normal)
        back = back - o * back.dot(o)
        if back.length < 1e-9:
            back = normal.cross(o)
        back.normalize()

        if grounded(l):
            warnings.append("%s looks like a wing but reaches the ground - kept as a "
                            "leg (a bat or pterosaur walking on its wrists)" % l["name"])
        else:
            l["role"] = "wing"
        info = {
            "name": l["name"], "limb": l["name"], "side": side, "kind": kind,
            "girdle": l["girdle"], "upper": l["upper"], "lower": l["lower"],
            "end": l["end"], "digits": list(l["digits"]), "fingers": fingers,
            "feathers": feathers, "attach": l["attach"],
            "root": root.copy(), "outward": outward, "normal": normal,
            "o": o, "back": back, "tip": tip.copy(),
            "reach": pf["reach"] if pf else (tip - root).length,
            "area": pf["area"] if pf else None,
            "thickness_ratio": round(pf["thickness"], 3) if pf else None,
            "straightness": round(straightness, 3),
            "rests_folded": straightness < 0.6,
            "evidence": ("name and skin" if named and sheet else
                         "name" if named else "skin sheet"),
            "grounded": grounded(l),
        }
        if info["rests_folded"]:
            warnings.append("%s rests folded (straightness %.2f): fold 0 is that pose; "
                            "spread it with a negative fold" % (l["name"], straightness))
        if named and pf is not None and not sheet:
            warnings.append("%s is named like a wing but its skin is not a sheet "
                            "(thickness %.2f) - area and flight numbers will be poor"
                            % (l["name"], pf["thickness"]))
        wings.append(info)
    # mirrored pair should agree
    by_side = {w["side"]: w for w in wings}
    if len(wings) == 2 and set(by_side) == {"L", "R"}:
        a, b = by_side["L"], by_side["R"]
        if a["kind"] != b["kind"]:
            warnings.append("left and right wings disagree on kind: %s / %s"
                            % (a["kind"], b["kind"]))
        if a["area"] and b["area"] and abs(a["area"] - b["area"]) > 0.1 * max(a["area"], b["area"]):
            warnings.append("left and right wing areas differ by more than 10%%: "
                            "%.3f / %.3f" % (a["area"], b["area"]))
    elif len(wings) % 2:
        warnings.append("%d wings - an unpaired wing will not fly straight" % len(wings))
    return wings, warnings


# --------------------------------------------------------------------------
# posing
# --------------------------------------------------------------------------

REST_STATE = {"fold": 0.0, "stroke": 0.0, "sweep": 0.0, "twist": 0.0, "fan": 1.0,
              "tilt": 0.0, "tuck": 0.0}
# The pose a wing is carried in on the ground: folded and tucked to the flank.
GROUND = {"fold": 1.0, "tuck": 1.0}


def state(**kw):
    s = dict(REST_STATE)
    s.update(kw)
    return s


def blend_states(a, b, w):
    """Blend two wing states, each either one state or {"L": s, "R": s}."""
    def per_side(s, side):
        if s is None:
            return dict(REST_STATE)
        if "L" in s or "R" in s:
            return dict(REST_STATE, **s.get(side, {}))
        return dict(REST_STATE, **s)
    out = {}
    for side in ("L", "R"):
        sa, sb = per_side(a, side), per_side(b, side)
        out[side] = {k: sa[k] + (sb[k] - sa[k]) * w for k in REST_STATE}
    return out


class WingRig:
    """Rest measurements for every wing on a body, and the pose maths."""

    def __init__(self, body):
        self.body = body
        self.bm = body.bm
        self.wings = body.bm.get("wings", [])
        bones = body.rig.data.bones
        self.seg = {}
        for w in self.wings:
            o, b = w["o"], w["back"]
            k = o.cross(b).normalized()

            def angle(v, o=o, b=b):
                return math.degrees(math.atan2(v.dot(b), v.dot(o)))
            rest = {}
            main = [("upper", w["upper"]), ("lower", w["lower"])]
            if w["end"]:
                main.append(("end", w["end"]))
            main += [("digit", d) for d in w["digits"]]
            for role, n in main:
                bone = bones[n]
                rest[n] = {"role": role, "alpha": angle(bone.tail_local - bone.head_local)}
            fingers = []
            for i, ch in enumerate(w["fingers"]):
                first = bones[ch[0]]
                a0 = angle(bones[ch[-1]].tail_local - first.head_local)
                fingers.append(a0)
                for n in ch:
                    rest[n] = {"role": "finger", "alpha": a0, "index": i}
            lead = min(fingers) if fingers else None
            for n, parent in w["feathers"]:
                bone = bones[n]
                rest[n] = {"role": "feather", "alpha": angle(bone.tail_local - bone.head_local),
                           "parent": parent}
            self.seg[w["name"]] = {"k": k, "rest": rest, "lead": lead,
                                   "order": self._order(w)}

    def _order(self, w):
        """Every posed bone of a wing, parents before children."""
        from .motion import _depth
        rig = self.body.rig
        names = {w["upper"], w["lower"]} | ({w["end"]} if w["end"] else set())
        names |= set(w["digits"]) | {n for ch in w["fingers"] for n in ch}
        names |= {n for n, _ in w["feathers"]}
        return sorted(names, key=lambda n: _depth(rig.data.bones[n]))

    def bones(self):
        return {n for s in self.seg.values() for n in s["order"]}

    def fold_angles(self, w, fold, fan):
        """In-plane delta angle per bone for a fold amount."""
        seg = self.seg[w["name"]]
        folded = FOLDED[w["kind"]]
        out = {}
        f = max(-1.0, min(1.0, fold))
        for n, r in seg["rest"].items():
            role = r["role"]
            if role in ("upper", "lower", "end", "digit"):
                goal = (folded if f >= 0 else SPREAD)[role]
                out[n] = abs(f) * _wrap(goal - r["alpha"])
        end_delta = out.get(w["end"], out.get(w["lower"], 0.0))
        for n, r in seg["rest"].items():
            if r["role"] == "finger":
                goal = (folded["digit"] + 4.0 * r["index"]) if f >= 0 else r["alpha"]
                d = max(f, 0.0) * _wrap(goal - r["alpha"])
                # fan opens or closes the fingers about the leading one
                spread = (r["alpha"] - seg["lead"]) * (fan - 1.0) * (1.0 - max(f, 0.0))
                out[n] = d + spread
            elif r["role"] == "feather":
                parent = seg["rest"][r["parent"]]
                delta = r["alpha"] - parent["alpha"]
                base = out.get(r["parent"], end_delta)
                # feathers close up along their bone as it folds, open with fan
                out[n] = base - max(f, 0.0) * 0.85 * delta + (fan - 1.0) * delta * (1.0 - max(f, 0.0))
        return out

    def pose(self, posed, states):
        """Overrides for every wing bone. `states` is {"L": state, "R": state}."""
        body, bm = self.body, self.bm
        rig = body.rig
        bones = rig.data.bones
        fwd, up = bm["fwd"], bm["up_vec"]
        out = {}
        for w in self.wings:
            s = states.get(w["side"], REST_STATE)
            seg = self.seg[w["name"]]
            carrier = w["girdle"] or w["attach"]
            if carrier:
                C = posed[carrier].to_3x3() @ body.rest[carrier].to_3x3().inverted()
                root_now = body.carried(posed, carrier, w["root"])
            else:
                C, root_now = Matrix.Identity(3), w["root"].copy()
            oh = w["outward"]
            k_fold = seg["k"]
            k_stroke = oh.cross(up).normalized()
            if s["tilt"]:
                # Stroke-plane tilt: positive sends the downstroke forward, on
                # either side, whichever way lat happens to point.
                k_t = Matrix.Rotation(math.radians(s["tilt"]), 3, bm["lat"]) @ k_stroke
                probe = Matrix.Rotation(math.radians(-10.0), 3, k_t) @ oh
                if (probe - oh).dot(fwd) * s["tilt"] < 0.0:
                    k_t = Matrix.Rotation(math.radians(-s["tilt"]), 3, bm["lat"]) @ k_stroke
                k_stroke = k_t
            k_sweep = oh.cross(fwd).normalized()
            fold = s["fold"]
            # tuck rolls a folded wing down against the flank; a flight
            # upstroke flexes the wing without it
            elevation = s["stroke"] - TUCK * s["tuck"] * max(fold, 0.0)
            G = (Matrix.Rotation(math.radians(s["sweep"]), 3, k_sweep)
                 @ Matrix.Rotation(math.radians(elevation), 3, k_stroke))
            deltas = self.fold_angles(w, fold, s["fan"])
            pre = {n: G @ Matrix.Rotation(math.radians(deltas[n]), 3, k_fold)
                   for n in seg["order"]}
            # twist about the span as it stands after fold, tuck, stroke, sweep
            wrist_bone = w["end"] or w["lower"]
            span = (pre[w["upper"]] @ (bones[w["lower"]].head_local - w["root"])
                    + pre[w["lower"]] @ (bones[wrist_bone].head_local
                                         - bones[w["lower"]].head_local)
                    if w["end"] else pre[w["upper"]] @ (bones[w["lower"]].tail_local - w["root"]))
            span = span.normalized() if span.length > 1e-9 else oh
            k_twist = span if span.cross(fwd).dot(up) < 0.0 else -span
            heads, rots = {}, {}
            for n in seg["order"]:
                r = seg["rest"][n]
                role = r["role"]
                if role == "feather":
                    role = seg["rest"][r["parent"]]["role"]
                elif role == "finger":
                    role = "digit"
                R = (C @ Matrix.Rotation(math.radians(s["twist"] * TWIST_SHARE[role]), 3,
                                         k_twist) @ pre[n])
                bone = bones[n]
                if n == w["upper"]:
                    head = root_now
                else:
                    p = bone.parent
                    head = heads[p.name] + rots[p.name] @ (bone.head_local - p.head_local)
                heads[n], rots[n] = head, R
                out[n] = (Matrix.Translation(head) @ R.to_4x4()
                          @ Matrix.Translation(-bone.head_local) @ body.rest[n])
        return out
