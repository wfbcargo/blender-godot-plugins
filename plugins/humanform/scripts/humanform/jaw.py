"""A jaw bone for every humanform body: the mouth opens.

    rep = jaw.add(human)                  # the bone, its weights, and what it took them from
    jaw.audit(human)                      # what moves with it and what must not
    jaw.open_check(human, degrees=30)     # pose it and measure the skin: corners, throat, teeth

MPFB's game_engine rig ends at the head, so until now a humanform body could not open its mouth at all: no
bite, no roar, no speech, and a muzzle with a fixed jaw is a mask. rig-anything already poses a maw - a
dragon's, a whale's - from bones it tags `maw_role`, so the bone here is named and tagged the way its body map
reads (`jaw`, `maw_role = "jaw"`): the map keeps it out of the skeleton it analyses (it would otherwise read as
the far end of the axial chain) and `rig_analysis.maw` can pose it.

Where it goes, from the head's own landmarks (`features.frame`), never from a number typed for one body:

    hinge     HINGE_BACK of the head's length back from the nose tip, HINGE_DROP of the lip-line-to-eye
              height above the lip line - the temporomandibular joint, in front of and level with the ear
    tail      the chin, so the bone lies along the mandible and turns about its own x to open

What it takes with it, as a share of the skin each vertex had (`_field`): everything below the lip line,
inside a tube round the mandible, from the hinge forward - the lower lip, the chin, the floor of the mouth,
the lower teeth and the tongue, and the lower half of a muzzle, which is simply the part of that region the
snout carried forward. The split at the lip line is hard in front of the mouth's corner (or the lips are sewn
shut) and widens into a web toward the hinge, so the corner stretches instead of tearing - rig-anything's maw
rule, measured here on a human face. Behind the hinge it fades out into the neck.

The weights are taken from the bones that held that skin, in proportion, so every vertex still sums to 1 and
the neck blend under the jaw survives. Called on the unbaked MPFB body after the head features (the muzzle
moves the lip line, and the hinge and the field are read off the skin as it is drawn), before the warp - which
carries the bone with the head, since `species._Rig` gives a `maw_role` bone the head's own scale.
"""

from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import delta, features, measure

BONE = "jaw"
ROLE = "maw_role"             # rig_analysis.maw.ROLE: what its body map and its poser read
ROLE_VALUE = "jaw"
BODY_VERTS = delta.BODY_VERTS

HINGE_AHEAD = 0.10            # of the ear-to-nose-tip distance, in front of the ear: the joint
HINGE_DROP = 0.55             # of the lip line to eye height, up from the lip line
CORNER_BAND = 0.0015          # the split at the lip line in front of the mouth's corner (m, reference head)
WEB_BAND = 0.05               # ... and away from them: the cheek's web, which stretches instead of tearing
WEB_REACH = 0.05              # ... over this far from the lip line (m, reference head)
TUBE = (0.60, 0.55)           # the mandible's reach from its axis in jaw lengths: full weight, then a fade
BEHIND = 0.30                 # the weight fades out over this share of the jaw's length behind the hinge
OPEN_DEG = 25.0               # the gape the open-mouth check poses (a human's own comfortable open mouth)
OPEN_MIN_EDGE = 0.003         # the skin's edges it measures (m on the reference head): the ring of 1-2 mm edges
                              # at the lip's margin is the mouth opening, and carries no texture worth the name
# What the web may do at that gape, measured on the outer skin (`outer_faces`) with the lip line's own seam
# left out. The corner of a shut mouth is one ring of small quads, and a few of them always take a big share
# of the opening, so the ninety-ninth percentile is the web's number and the maximum only a catastrophe
# guard: a human control measures 1.82 / 3.9 and a muzzled one 2.47 / 6.6, while a jaw whose web was too hard
# measured 5.9 / 17, 11 / 29 and 15 / 43 (each a visible tear at the corner, rendered).
STRETCH_P99 = 2.8             # the web's stretch at the 99th percentile
STRETCH_MAX = 8.0             # ... and its worst single edge
QUALITY_KEEP = 0.28           # ... and a triangle may keep no less than this share of its shape
SUM_TOL = 0.15                # how far a vertex's bone weights may sit from 1 (MPFB's own reach 1.06)


def _obj(o):
    return bpy.data.objects[o] if isinstance(o, str) else o


def _rig_of(human):
    from . import body as _body
    return _body.rig_of(human)


def _frame(human):
    """(F, co, faces): the head's landmarks on the body as it is drawn, a muzzle included."""
    co = features._drawn(human)
    faces = delta.body_faces(human)
    nrm = delta.vertex_normals(co, faces)
    return features.frame(human, co, nrm, faces), co, faces


def place(F):
    """(hinge, chin) in the body's object space, from the head's landmarks: the joint under the ear, and the
    chin. Measured back from the nose tip as rig-anything's maws are (0.78-0.9 of the head's length, which is
    right for a skull that is nearly all mouth) it landed behind the ear on a human, giving a 204 mm mandible
    and a jaw that swung the whole lower face down like a plate. The ear is where the joint is on a face."""
    ear = 0.5 * (F.lm["ear.L"][0] + F.lm["ear.R"][0])
    chin = F.lm["chin"][0].copy()
    y = float(ear[1] + HINGE_AHEAD * (F.lm["nose_tip"][0][1] - ear[1]))
    z = float(F.slit_z + HINGE_DROP * (F.eye_z - F.slit_z))
    return np.array([0.0, y, z]), chin


def _field(F, co, hinge, chin):
    """The jaw's share of every vertex, in [0, 1]: below the lip line, inside the mandible's tube, from the
    hinge forward. `co` is every vertex (the mouth's helpers ride it too)."""
    ax = chin - hinge
    L = float(np.linalg.norm(ax))
    ax = ax / max(L, 1e-9)
    rel = co - hinge
    t = rel @ ax
    d = np.linalg.norm(rel - np.outer(t, ax), axis=1)
    tube = 1.0 - features._smoothstep((d / L - TUBE[0]) / TUBE[1])
    behind = 1.0 - features._smoothstep(-t / (BEHIND * L))
    # The lip line, and how hard the split across it is. On the lips themselves it is hard, a millimetre and a
    # half: softer and the lips would not part. Away from them it widens into the web - the cheek that stretches
    # when the mouth opens - by how far the skin is from the lip line, not by how far back it lies: the tear a
    # ramp measured from the corner to the hinge left was 9 mm behind the corner, where that ramp was still at
    # its hardest (17x). The ramp is centred on the line, so the two sides of the web share it.
    slit = co[np.asarray(measure.face_features()["mouth"], int)]
    z_lip = features._slit_z(slit)(co[:, 0])
    d_lip = np.linalg.norm(co[:, None, :] - slit[None, :, :], axis=2).min(axis=1)
    band = (CORNER_BAND + (WEB_BAND - CORNER_BAND)
            * features._smoothstep(d_lip / (WEB_REACH * F.scale))) * F.scale
    split = features._smoothstep(0.5 + (z_lip - co[:, 2]) / band)
    return np.clip(split * tube * behind, 0.0, 1.0)


def _edit(rig):
    view = bpy.context.view_layer
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    prev = view.objects.active
    view.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    return prev


def _bone(rig, head_bone, hinge, chin, matrix):
    """Add (or move) the jaw bone, in the rig's own space."""
    to_rig = np.array(rig.matrix_world.inverted() @ matrix)

    def to(p):
        return Vector(np.asarray(p, float) @ to_rig[:3, :3].T + to_rig[:3, 3])
    prev = _edit(rig)
    try:
        eb = rig.data.edit_bones.get(BONE) or rig.data.edit_bones.new(BONE)
        eb.head, eb.tail = to(hinge), to(chin)
        eb.parent = rig.data.edit_bones[head_bone]
        eb.use_connect = False
        eb.use_deform = True
        eb.align_roll(Vector((0.0, 0.0, 1.0)))
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        if prev is not None:
            bpy.context.view_layer.objects.active = prev
    b = rig.data.bones[BONE]
    b[ROLE] = ROLE_VALUE
    rig.pose.bones[BONE].rotation_mode = "QUATERNION"
    return b


def _apply_weights(human, rig, w, head_bone):
    """Give the jaw its share of every vertex and take it from the bones that held that skin, so each vertex's
    weights still add up to what they did and MPFB's helper groups (which are masks, not skin) are left alone.
    An earlier split of this jaw's is undone first, so building it again after the head features (a muzzle moves
    the lip line it splits at) does not hand it a second share - twice over, the weights summed to 1.48.

    Every weight is read before any is written: writing to a vertex group while walking a vertex's own group
    list gives the rest of that list back wrong, and the sums came out at 1.77."""
    bones = set(rig.data.bones.keys())
    names = {g.index: g.name for g in human.vertex_groups}
    vg = human.vertex_groups.get(BONE) or human.vertex_groups.new(name=BONE)
    names[vg.index] = BONE
    rows = {}
    for v in human.data.vertices:
        row = {names[e.group]: e.weight for e in v.groups if names.get(e.group) in bones}
        if w[v.index] > 1e-4 or row.get(BONE, 0.0) > 1e-4:
            rows[v.index] = row
    took, kept = {}, 0.0
    for i, row in rows.items():
        old = row.pop(BONE, 0.0)
        if old > 1e-4:
            # Undo the earlier split: what the other bones kept is what they had, less the jaw's share, and
            # MPFB's weights all sum to 1 - so putting their sum back at 1 restores them exactly. Scaling by
            # 1/(1 - old) instead needs a number that goes to infinity where the jaw took everything, and the
            # clamp on it left a lower lip at 0.23 of the weight it should have had (measured).
            tot = sum(row.values())
            row = {k: x / tot for k, x in row.items()} if tot > 1e-6 else {head_bone: 1.0}
        total = sum(row.values())
        s = float(np.clip(w[i], 0.0, 1.0))
        for name, x in row.items():
            took[name] = took.get(name, 0.0) + x * s
            human.vertex_groups[name].add([i], max(x * (1.0 - s), 0.0), "REPLACE")
        vg.add([i], s * total if total > 1e-6 else (1.0 if s > 1e-4 else 0.0), "REPLACE")
        if total > 1e-6:
            kept = max(kept, abs(total * (1.0 - s) + s * total - total))
    return {"verts": int(sum(1 for i in rows if w[i] > 1e-4)), "sum_error": round(kept, 5),
            "from": {k: round(v, 1) for k, v in sorted(took.items(), key=lambda kv: -kv[1])}}


def add(human, rig=None):
    """Put the jaw bone on this body and weight the mouth to it. Idempotent: it is rebuilt where the skin now
    is, so it may be called again after a head feature moves the lip line. Returns its report."""
    from . import eyes as _eyes
    human = _obj(human)
    rig = rig or _rig_of(human)
    if rig is None:
        return {"skipped": "no rig: jaw.add runs after scaffold.finish"}
    problem = delta.check_topology(human)
    if problem:
        return {"skipped": problem}
    head_bone = _eyes.head_bone(rig)
    if head_bone not in rig.data.bones:
        return {"skipped": f"the rig has no head bone {head_bone!r}"}
    F, co, faces = _frame(human)
    hinge, chin = place(F)
    _bone(rig, head_bone, hinge, chin, human.matrix_world)
    w = _field(F, co, hinge, chin)
    # the lower teeth and the tongue are islands of their own, rigid, and wholly the jaw's: taken from the field
    # they came out at 0.65 and 0.56, because their crowns sit on the lip line the field splits at
    n = len(co)
    w[features._helper_mask(human, n, ("helper-lower-teeth", "helper-tongue"))] = 1.0
    w[features._helper_mask(human, n, ("helper-upper-teeth",))] = 0.0
    rep = {"bone": BONE, "parent": head_bone, "role": ROLE_VALUE,
           "hinge": [round(float(c), 4) for c in hinge], "chin": [round(float(c), 4) for c in chin],
           "length_mm": round(float(np.linalg.norm(chin - hinge)) * 1000, 1)}
    rep["weights"] = _apply_weights(human, rig, w, head_bone)
    rep["audit"] = audit(human, rig, w=w, F=F, co=co)
    if rep["audit"].get("fail"):
        rep["fail"] = rep["audit"]["fail"]
    return rep


# ------------------------------------------------------------------ checks

def _regions(F, co, human):
    """Named parts of the head, as index arrays: what must move with the jaw and what must not."""
    feats = measure.face_features()
    lips = np.asarray(feats["lips"], int)
    slit = co[np.asarray(feats["mouth"], int)]
    z_lip = features._slit_z(slit)(co[lips, 0])
    out = {"lower_lip": lips[co[lips, 2] < z_lip - 0.001 * F.scale],
           "upper_lip": lips[co[lips, 2] > z_lip + 0.001 * F.scale]}
    n = len(co)
    for name, groups in (("lower_teeth", ("helper-lower-teeth",)), ("upper_teeth", ("helper-upper-teeth",)),
                         ("tongue", ("helper-tongue",)), ("eyes", ("helper-l-eye", "helper-r-eye"))):
        m = features._helper_mask(human, n, groups)
        if m.any():
            out[name] = np.flatnonzero(m)
    body = co[:BODY_VERTS]
    out["forehead"] = np.flatnonzero(body[:, 2] > F.eye_z + 0.02 * F.scale)
    # the neck: well below the chin and behind its front
    chin_z = float(F.lm["chin"][0][2])
    out["neck"] = np.flatnonzero((body[:, 2] < chin_z - 0.09 * F.scale) & (body[:, 2] > chin_z - 0.30 * F.scale))
    return out


# what each region may or must take of the jaw (mean weight): (at least, at most)
WANT = {"lower_lip": (0.80, 1.0), "upper_lip": (0.0, 0.05), "lower_teeth": (0.85, 1.0),
        "upper_teeth": (0.0, 0.05), "tongue": (0.60, 1.0), "eyes": (0.0, 0.0),
        "forehead": (0.0, 0.0), "neck": (0.0, 0.12)}


def audit(human, rig=None, w=None, F=None, co=None):
    """What moves with the jaw and what must not: the mean weight of each named part against `WANT`, and every
    vertex's weights still summing to 1. `fail` names the part and the number."""
    human = _obj(human)
    rig = rig or _rig_of(human)
    if F is None or co is None:
        F, co, _faces = _frame(human)
    if w is None:
        g = human.vertex_groups.get(BONE)
        w = np.zeros(len(human.data.vertices))
        if g is not None:
            for v in human.data.vertices:
                for e in v.groups:
                    if e.group == g.index:
                        w[v.index] = e.weight
    rows, bad = {}, []
    for name, idx in _regions(F, co, human).items():
        if not len(idx):
            continue
        lo, hi = WANT.get(name, (0.0, 1.0))
        m = float(w[idx].mean())
        rows[name] = {"mean": round(m, 3), "max": round(float(w[idx].max()), 3), "verts": int(len(idx))}
        if m < lo:
            bad.append(f"{name} takes {m:.2f} of the jaw, under {lo:.2f} - it would not open with it")
        if m > hi:
            bad.append(f"{name} takes {m:.2f} of the jaw, over {hi:.2f} - it would move when the mouth opens")
    # every vertex still adds up: a jaw that took more than a vertex had would shrink the skin
    bones = set(rig.data.bones.keys()) if rig is not None else set()
    by_index = {g.index: g.name for g in human.vertex_groups}
    worst = 0.0
    for v in human.data.vertices:
        if w[v.index] <= 1e-4:
            continue
        tot = sum(e.weight for e in v.groups if by_index.get(e.group) in bones)
        worst = max(worst, abs(tot - 1.0))
    out = {"regions": rows, "weight_sum_off_one": round(worst, 4)}
    # MPFB's own weights are not all normalised (some vertices sum to 1.06 before anything here touches them),
    # so what is checked is that the split left the sum where it found it - a jaw built twice over an earlier
    # one summed to 1.48 (measured)
    if worst > SUM_TOL:
        bad.append(f"a vertex's bone weights add up to {1 + worst:.3f}, over {1 + SUM_TOL:.2f} - the jaw took "
                   "weight that was not there to take (jaw._apply_weights)")
    if bad:
        out["fail"] = "; ".join(bad)
    return out


SEAM_R = 0.05     # how far round the lip line the seam reaches (m on the reference head)
SEEN_RAYS = ((0.0, 0.0), (0.7, 0.0), (-0.7, 0.0), (0.0, 0.7), (0.0, -0.7))   # the fan `outer_faces` looks along
SEEN_REACH = 0.08  # how far those rays look for skin (m on the reference head)


def outer_faces(F, co, faces, near):
    """Which of the faces `near` marks are on the outside of the head - the skin a camera sees - and not lining
    the mouth. Each face's centroid looks out along a fan about its own normal; a face most of whose fan gets
    away is outside. Nothing simpler told the two apart: the mouth's roof and floor sit at the same height as
    the lips, its cavity is roomier than a real one (so a normal meets nothing within a centimetre), and a ray
    straight ahead leaves through the crack MPFB's shut lips keep (features.SEAL)."""
    from mathutils import Vector
    co = np.asarray(co, float)
    f = np.asarray(faces, int)
    out = np.zeros(len(f), bool)
    idx = np.flatnonzero(near)
    if not len(idx):
        return out
    cen = co[f[idx]].mean(axis=1)
    nrm = delta.vertex_normals(co, f)
    fn = nrm[f[idx]].mean(axis=1)
    fn /= np.maximum(np.linalg.norm(fn, axis=1), 1e-9)[:, None]
    reach = SEEN_REACH * F.scale
    for k, i in enumerate(idx):
        n = Vector(fn[k])
        t = Vector((1.0, 0.0, 0.0)) if abs(n.x) < 0.9 else Vector((0.0, 1.0, 0.0))
        u = n.cross(t).normalized()
        v = n.cross(u).normalized()
        p = Vector(cen[k]) + n * 1e-4
        free = 0
        for a, b in SEEN_RAYS:
            d = (n + u * a + v * b).normalized()
            if F.tree.ray_cast(p, d, reach)[0] is None:
                free += 1
        out[i] = free >= 3
    return out


def seam_sides(F, co):
    """+1 above the lip line, -1 below it, 0 away from the mouth: the two sides of the seam that is meant to
    come apart when the jaw opens.

    hm08 models a shut mouth. The upper lip's margin and the lower one's are a millimetre apart and joined by
    the mesh, and its cavity's roof and floor meet at the back, so opening the jaw pulls those edges to the
    width of the gape (70x, measured). That is the seal opening, not a tear, and measuring it with the rest of
    the skin drowns every real number. Every other edge round the mouth - the cheek's web, the chin, the
    throat, both lips' own skin - lies on one side of the line and is measured as usual. Which side, and not
    whether the skin is inside the mouth, is the honest test: the inside of a lip tears exactly where the
    outside of it does."""
    co = np.asarray(co, float)
    slit = co[np.asarray(measure.face_features()["mouth"], int)]
    d = np.linalg.norm(co[:, None, :] - slit[None, :, :], axis=2).min(axis=1)
    z_lip = features._slit_z(slit)(co[:, 0])
    side = np.where(co[:, 2] > z_lip, 1, -1)
    side[d > SEAM_R * F.scale] = 0
    return side


def _axis_sign(rig):
    """Which way about the bone's own x drops the chin."""
    b = rig.data.bones[BONE]
    x = np.array(b.matrix_local.to_3x3())[:, 0]
    tail = np.array(b.tail_local) - np.array(b.head_local)
    # rotating the tail about +x: dz of the tail is (x cross tail).z
    return -1.0 if float(np.cross(x, tail)[2]) > 0 else 1.0


def pose_open(rig, degrees=OPEN_DEG):
    """Rotate the jaw open by `degrees` (the rest pose is put back by `pose_rest`)."""
    pb = rig.pose.bones[BONE]
    pb.rotation_mode = "QUATERNION"
    pb.rotation_quaternion = Matrix.Rotation(math.radians(degrees) * _axis_sign(rig), 4, "X").to_quaternion()
    bpy.context.view_layer.update()


def pose_rest(rig):
    pb = rig.pose.bones[BONE]
    pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    bpy.context.view_layer.update()


def _evaluated(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    co = np.array([v.co[:] for v in me.vertices], float)
    ob.evaluated_get(dg).to_mesh_clear()
    return co


def open_check(human, rig=None, degrees=OPEN_DEG):
    """Open the mouth and measure the skin: how far its edges stretch and what becomes of its triangles
    (`features.surface_strain`), and how far the chin travelled. `fail` when the corners or the throat tear."""
    human = _obj(human)
    rig = rig or _rig_of(human)
    if rig is None or BONE not in rig.data.bones:
        return {"skipped": "no jaw bone"}
    faces = delta.body_faces(human)
    was = rig.data.pose_position
    rig.data.pose_position = "POSE"
    pose_rest(rig)
    rest = _evaluated(human)
    pose_open(rig, degrees)
    opened = _evaluated(human)
    pose_rest(rig)
    rig.data.pose_position = was
    moved = np.linalg.norm(opened - rest, axis=1)[:BODY_VERTS] > 1e-5
    F, co, _f = _frame(human)
    rest_b = rest[:BODY_VERTS]
    # only the skin a camera sees: what lines the mouth is meant to come apart, and measured with the rest it
    # is all any number says (29x inside the cheek against 1.9x on it)
    f = np.asarray(faces, int)
    outer = outer_faces(F, rest_b, f, moved[f].any(axis=1))
    strain = features.surface_strain(rest_b, opened[:BODY_VERTS], f[outer], moved=moved, scale=F.scale,
                                     side=seam_sides(F, rest_b), min_edge=OPEN_MIN_EDGE)
    strain.pop("fail", None)              # the muzzle's limits are not the jaw's: they are checked below
    out = {"degrees": degrees, "moved_verts": int(moved.sum()), "skin": strain,
           "outer_faces": int(outer.sum()), "lining_faces": int((moved[f].any(axis=1) & ~outer).sum()),
           "gape_mm": round(float(np.linalg.norm(opened - rest, axis=1).max()) * 1000, 1)}
    bad = []
    if strain.get("stretch_p99", 0.0) > STRETCH_P99:
        bad.append(f"the skin stretches {strain['stretch_p99']:.2f}x over its worst hundredth with the mouth "
                   f"{degrees:.0f} deg open (limit {STRETCH_P99}) - the corners of the lips tear: widen the web "
                   "(jaw.WEB_BAND, WEB_REACH) or open less")
    if strain.get("stretch_max", 0.0) > STRETCH_MAX:
        bad.append(f"one edge of the skin stretches {strain['stretch_max']:.1f}x at {degrees:.0f} deg (limit "
                   f"{STRETCH_MAX}) - the skin is sewn across the mouth there: check the jaw's weights (jaw.audit)")
    if strain.get("quality_keep_min", 1.0) < QUALITY_KEEP:
        bad.append(f"a triangle keeps {strain['quality_keep_min']:.2f} of its shape at {degrees:.0f} deg (limit "
                   f"{QUALITY_KEEP}) - it folds: widen the web (jaw.WEB_BAND)")
    if not moved.any():
        bad.append("nothing moved when the jaw turned - the mouth has no weights on it")
    if bad:
        out["fail"] = "; ".join(bad)
    return out
