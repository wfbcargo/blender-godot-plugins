"""Head features for a species (08 fantasy species, layer 2): a head shape and named features on an MPFB body.

    rep = features.apply(human, {"shape": "invertedtriangular", "shape_weight": 0.8,
                                 "features": {"ears_pointed": 1.0}})
    features.validate(spec)          # [] or the problems, each naming the fix
    features.FEATURES                # the names apply knows

What each feature is made of (weights 0..1; a feature's MPFB targets are scaled by its weight times a gain):

    ears_pointed   ears/l|r-ear-shape-pointed (a single-file target: no incr/decr pair), plus a little
                   ear-scale-vert-incr so the point reads from the front
    ears_large     ears/l|r-ear-scale-incr, -scale-vert-incr and -wing-incr (they stand off the head)
    brow_ridge     eyebrows-trans-forward, forehead-nubian-incr and the delta `hfd:head-brow_ridge`: a
                   supraorbital bulge along the normal, its extent read off MPFB's own eyebrow target
    nose_size      nose-scale-horiz/-vert/-depth-incr, nose-volume-incr, nose-flaring-incr, nose-width3-incr
    jaw_heavy      chin-bones-incr, chin-width-incr, chin-prominent-incr, chin-prognathism-incr and the delta
                   `hfd:head-jaw_heavy` (mass at the mandible's angle, below the ears). Not head-square: it
                   lowers the crown 3-4 mm, which moves every proportion measured in statures (a square head
                   is `shape`'s job)
    tusks          the delta `hfd:head-tusks` (the lower lip pushed out where they rise) and the object
                   `<human>_tusks`: two small rigid ivory cones skinned 100% to the head bone, as the eyes are
    cheek_gaunt    l|r-cheek-volume-decr, -cheek-inner-decr, -cheek-bones-incr and head-fat-decr

The head `shape` is MPFB's whole-head target `head/head-<shape>` (`sheet.FACE_SHAPES`) at `shape_weight`. Some
lower the crown (square at 0.5: 5 mm, round 2.4 mm), so humancheck's stature-relative proportions shift a little
on a body fitted without it - a species warp that sets stature afterwards takes that back.

Every target is loaded as its own shape key `hfs:<file stem>` - never the `hf:` key a fit may already have set
(chin-bones and cheek-bones are likeness and face-fit levers), so a species adds to the fitted face instead of
overwriting it, and `library.capture` (which reads `hf:`) never stores a species head as a human body. `apply` sets
the head to the spec: calling it again with other weights, or without a feature, puts those keys where the new
spec says (0 for a feature no longer named). The delta keys are `delta.py` keys (`hfd:head-<feature>`), heights
computed on this body. `bake_for_game` folds every key in at its value; the tusks object is joined into the
baked mesh by character-pipeline's bake stage beside the eyes.

Call it on the unbaked MPFB body (rigged or not) before any proportion warp: the tusks are skinned to the
head bone, so a warp that moves bones and skin carries them.
"""

from __future__ import annotations

import gzip
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from . import delta, measure, sheet

KEY_PREFIX = "hfs:"
DELTA_PREFIX = delta.KEY_PREFIX + "head-"          # hfd:head-<feature>
TUSKS_SUFFIX = "_tusks"
IVORY = (0.86, 0.80, 0.66)                          # screen colour, a little yellower than eye white
FEATURES = ("ears_pointed", "ears_large", "brow_ridge", "nose_size", "jaw_heavy", "tusks", "cheek_gaunt")

# feature -> [(target group, file stem, sided, gain)]; a sided stem loads l- and r- together
TARGETS = {
    "ears_pointed": [("ears", "ear-shape-pointed", True, 1.0), ("ears", "ear-scale-vert-incr", True, 0.25)],
    "ears_large": [("ears", "ear-scale-incr", True, 1.0), ("ears", "ear-scale-vert-incr", True, 0.4),
                   ("ears", "ear-wing-incr", True, 0.45)],
    "brow_ridge": [("eyebrows", "eyebrows-trans-forward", False, 0.4)],
    "nose_size": [("nose", "nose-scale-horiz-incr", False, 0.8), ("nose", "nose-scale-vert-incr", False, 0.55),
                  ("nose", "nose-scale-depth-incr", False, 0.6), ("nose", "nose-volume-incr", False, 0.7),
                  ("nose", "nose-flaring-incr", False, 0.5), ("nose", "nose-width3-incr", False, 0.4)],
    "jaw_heavy": [("chin", "chin-bones-incr", False, 1.0), ("chin", "chin-width-incr", False, 0.8),
                  ("chin", "chin-prominent-incr", False, 0.5), ("chin", "chin-prognathism-incr", False, 0.35)],
    "tusks": [],
    "cheek_gaunt": [("cheek", "cheek-volume-decr", True, 1.0), ("cheek", "cheek-inner-decr", True, 0.6),
                    ("cheek", "cheek-bones-incr", True, 0.45), ("head", "head-fat-decr", False, 0.3)],
}
# delta features: peak height (m, on a 1.75 m body) at weight 1
DELTA_PEAK = {"brow_ridge": 0.0048, "jaw_heavy": 0.004, "tusks": 0.0035}
REF_STATURE = 1.75
BODY_VERTS = delta.BODY_VERTS


def _obj(o):
    return bpy.data.objects[o] if isinstance(o, str) else o


def validate(head_spec):
    """The problems with a species `head` block, each saying what to write instead; [] when it is fine.
    A feature name `apply` does not know is listed here too (apply itself only reports it)."""
    out = []
    if head_spec is None:
        return out
    if not isinstance(head_spec, dict):
        return [f"head must be a table, not {type(head_spec).__name__}"]
    extra = sorted(set(head_spec) - {"shape", "shape_weight", "features"})
    if extra:
        out.append(f"head: unknown key(s) {extra} - it takes shape, shape_weight and features")
    shape = head_spec.get("shape")
    if shape is not None and shape not in sheet.FACE_SHAPES:
        out.append(f"head.shape {shape!r} is not one of {', '.join(sheet.FACE_SHAPES)}")
    sw = head_spec.get("shape_weight", 0.5)
    if not isinstance(sw, (int, float)) or not -1.0 <= float(sw) <= 1.0:
        out.append(f"head.shape_weight {sw!r} must be a number in [-1, 1]")
    feats = head_spec.get("features") or {}
    if not isinstance(feats, dict):
        return out + [f"head.features must be a table of name = weight, not {type(feats).__name__}"]
    for name, w in feats.items():
        if name not in FEATURES:
            out.append(f"head.features: unknown feature {name!r} - known: {', '.join(FEATURES)}")
        elif not isinstance(w, (int, float)) or not 0.0 <= float(w) <= 1.0:
            out.append(f"head.features.{name} = {w!r} must be a weight in [0, 1]")
    return out


# ------------------------------------------------------------------ MPFB targets

def _root():
    from . import scaffold
    _, _, _, LocationService = scaffold.services()
    return LocationService.get_mpfb_data("targets")


def _files(group, stem, sided):
    return [(f"{s}-{stem}" if s else stem, os.path.join(_root(), group, (f"{s}-{stem}" if s else stem) + ".target.gz"))
            for s in (("l", "r") if sided else (None,))]


def _key(human, fname, path):
    from . import scaffold
    _, TargetService, _, _ = scaffold.services()
    kname = KEY_PREFIX + fname
    kb = human.data.shape_keys.key_blocks.get(kname) if human.data.shape_keys else None
    if kb is None:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        kb = TargetService.load_target(human, path, weight=0.0, name=kname)
    return kb


def _magnitude(group, stem, sided=False):
    """How far MPFB's target moves each base-mesh vertex, normalised to its largest (BODY_VERTS,)."""
    m = np.zeros(delta.BODY_VERTS)
    for _, path in _files(group, stem, sided):
        with gzip.open(path, "rt") as fh:
            for line in fh:
                p = line.split()
                if len(p) == 4 and p[0].isdigit():
                    i = int(p[0])
                    if i < delta.BODY_VERTS:
                        m[i] = max(m[i], math.sqrt(sum(float(c) ** 2 for c in p[1:])))
    return m / max(m.max(), 1e-12)


# ------------------------------------------------------------------ delta heights, per feature

def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _eye_centres(human, co):
    out = []
    for side in ("l", "r"):
        g = human.vertex_groups.get(f"helper-{side}-eye")
        if g is None:
            raise ValueError(f"{human.name} has no helper-{side}-eye group (not an MPFB2 body?)")
        idx = [v.index for v in human.data.vertices if any(e.group == g.index for e in v.groups)]
        out.append(co[idx].mean(axis=0))
    return out


def _brow_heights(human, co, nrm, faces, scale):
    """A supraorbital bulge: where MPFB's eyebrow target moves the skin, above the eye, peaking over it and
    fading to the glabella and the temples, pushed out along the normal."""
    mask = _magnitude("eyebrows", "eyebrows-trans-forward")
    el, er = _eye_centres(human, co)
    ez = (el[2] + er[2]) / 2
    ex = abs(el[0] - er[0]) / 2
    x, z = co[:BODY_VERTS, 0], co[:BODY_VERTS, 2]
    fwd = -nrm[:, 1]                                          # MPFB faces -Y
    up = _smoothstep((z - (ez + 0.006 * scale)) / (0.009 * scale))     # none on the upper lid
    top = 1.0 - _smoothstep((z - (ez + 0.017 * scale)) / (0.016 * scale))
    lateral = 1.0 - _smoothstep((np.abs(x) - (ex + 0.010 * scale)) / (0.014 * scale))
    h = np.sqrt(mask) * up * top * lateral * _smoothstep(fwd / 0.4)
    h = delta.smooth(h, faces, iterations=10)
    return h / max(h.max(), 1e-12)


def _jaw_heights(human, co, nrm, faces, scale):
    """Mass at the angle of the mandible: MPFB's chin-bones target's region, weighted to its outer back."""
    mask = _magnitude("chin", "chin-bones-incr")
    side = _smoothstep((np.abs(co[:BODY_VERTS, 0]) - 0.02 * scale) / (0.03 * scale))
    out = _smoothstep(np.abs(nrm[:, 0]) / 0.5)
    h = delta.smooth(mask * side * out, faces, iterations=6)
    return h / max(h.max(), 1e-12)


def _mouth(co):
    f = measure.face_features()
    mouth = co[f["mouth"]]
    lips = np.asarray(f["lips"])
    return mouth, lips


def _tusk_bases(co, nrm, scale):
    """Where each tusk rises: on the lower lip, 55% of the way from the middle to the corner, a little below
    the lip line. Returns [(point, normal, x sign)] for the left (+x) and right tusk."""
    mouth, lips = _mouth(co)
    slit_z = float(mouth[:, 2].mean())
    half = float(mouth[:, 0].max() - mouth[:, 0].min()) / 2
    lower = lips[co[lips, 2] < slit_z - 0.001 * scale]
    out = []
    for sgn in (1.0, -1.0):
        want = np.array([sgn * 0.62 * half, 0.0, slit_z - 0.0045 * scale])
        cand = lower[np.sign(co[lower, 0]) == sgn]
        d = np.linalg.norm((co[cand] - want)[:, [0, 2]], axis=1)
        i = int(cand[np.argmin(d)])
        out.append((co[i].copy(), nrm[i].copy(), sgn))
    return out, slit_z, half


def _tusk_lip_heights(co, nrm, faces, scale):
    bases, _, _ = _tusk_bases(co, nrm, scale)
    h = np.zeros(BODY_VERTS)
    for p, _, _ in bases:
        r = np.linalg.norm(co[:BODY_VERTS] - p, axis=1)
        h = np.maximum(h, np.exp(-0.5 * (r / (0.006 * scale)) ** 2))
    h *= _smoothstep(-nrm[:, 1] / 0.3)                       # only skin facing forward
    h = delta.smooth(h, faces, iterations=3)
    return h / max(h.max(), 1e-12)


DELTA_SHAPES = {"brow_ridge": _brow_heights, "jaw_heavy": _jaw_heights,
                "tusks": lambda human, co, nrm, faces, scale: _tusk_lip_heights(co, nrm, faces, scale)}


def _write_delta(human, feature, heights_m):
    """The delta key `hfd:head-<feature>` with these heights (metres, this body's scale)."""
    st = delta.stature_of(delta.mixed_coords(human))
    card = {"id": f"species-head-{feature}", "region": f"head-{feature}",
            "payload": {"type": "delta", "frame": "normal", "unit": "um", "reference": {"stature_m": st},
                        "groups": {feature: delta.pack(heights_m)}}}
    from . import muscle
    return delta.apply(human, card, mode="key", value=1.0, key_name=DELTA_PREFIX + feature,
                       refine=muscle.facet_guard())


# ------------------------------------------------------------------ tusks

def _tusk_ring(bm, centre, axis, side, radius, n):
    """n vertices round `centre` in the plane normal to `axis`."""
    a = Vector(axis).normalized()
    u = Vector(side).cross(a).normalized()
    v = a.cross(u).normalized()
    ring = [2 * math.pi * k / n for k in range(n)]
    return [bm.verts.new(Vector(centre) + radius * (math.cos(t) * u + math.sin(t) * v)) for t in ring]


def _surface(co, faces):
    """dist(p): how far p stands in front of the face (+ in front, along -Y), from a ray cast back at the body
    along +Y from in front of p. A nearest-vertex test is fooled by the lips' inner surface."""
    from mathutils.bvhtree import BVHTree
    tree = BVHTree.FromPolygons([Vector(c) for c in co], [tuple(int(i) for i in f) for f in faces])

    def dist(p):
        start = Vector((p[0], p[1] - 0.2, p[2]))
        hit, _, _, _ = tree.ray_cast(start, Vector((0.0, 1.0, 0.0)), 0.4)
        return 0.2 if hit is None else float(hit.y - p[1])
    return dist


def _tusks(human, co, nrm, faces, weight, scale, segments=10, rings=7):
    """Two tapered, slightly curved cones rising from the lower lip past the upper, their upper part held
    clear of the skin. `co`/`nrm`: the body's surface as it now is (every key, deltas included)."""
    from . import eyes, look
    from . import body as _body
    name = human.name + TUSKS_SUFFIX
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    if weight <= 0:
        return None
    bases, slit_z, half = _tusk_bases(co, nrm, scale)
    dist = _surface(co[:BODY_VERTS], faces)
    length = (0.011 + 0.013 * weight) * scale
    r0 = (0.0024 + 0.0014 * weight) * scale
    bm = bmesh.new()
    report = {"length_mm": round(length * 1000, 1), "radius_mm": round(r0 * 1000, 1), "tusks": []}
    for p, n, sgn in bases:
        base = p - 0.4 * r0 * n                             # rooted in the lower lip, which the delta pushed out
        # a straight tusk from the root, up and a little out, tilted forward just enough that everything above the
        # lip line stands clear of the upper lip (a human upper lip sits in front of the lower one); its tip curls
        # out a little. Straight, so tilting it leaves no kink.
        axis = np.array([0.15 * sgn, -0.10, 1.0])
        axis /= np.linalg.norm(axis)
        ts = np.linspace(0.0, 1.0, rings)
        rad = [float(r0 * (1 - t) ** 0.8 + 0.12 * r0 * t) for t in ts]
        clear = -0.0003 * scale                            # resting on the upper lip, pressing 0.3 mm
        tilt = 0.0
        for _ in range(12):
            pts = base + np.outer(ts, axis) * length + np.outer(ts * ts, [0.10 * sgn * length, 0.0, 0.0])
            worst = 0.0
            for k in range(1, rings):
                if pts[k, 2] < slit_z + 0.003 * scale:       # still in the lips, where it is rooted
                    continue
                worst = max(worst, (rad[k] + clear - dist(Vector(pts[k]))) / (ts[k] * length))
            if worst <= 1e-4 or axis[1] < -0.45:            # at most ~27 degrees forward
                break
            tilt += worst
            axis = axis + np.array([0.0, -worst, 0.0])
            axis /= np.linalg.norm(axis)
        shift = tilt * length
        report["tusks"].append({"side": "L" if sgn > 0 else "R", "base": [round(float(c), 4) for c in base],
                                "tip": [round(float(c), 4) for c in pts[-1]], "cleared_mm": round(shift * 1000, 2)})
        side = Vector((1.0, 0.0, 0.0))
        loops = []
        for k in range(rings - 1):
            ax = pts[min(k + 1, rings - 1)] - pts[max(k - 1, 0)]
            loops.append(_tusk_ring(bm, pts[k], ax, side, rad[k], segments))
        tip = bm.verts.new(Vector(pts[-1]))
        cap = bm.verts.new(Vector(pts[0] - 0.4 * r0 * (pts[1] - pts[0]) / np.linalg.norm(pts[1] - pts[0])))
        for a, b in zip(loops, loops[1:]):
            for k in range(segments):
                bm.faces.new((a[k], a[(k + 1) % segments], b[(k + 1) % segments], b[k]))
        for k in range(segments):
            bm.faces.new((loops[-1][k], loops[-1][(k + 1) % segments], tip))
            bm.faces.new((loops[0][(k + 1) % segments], loops[0][k], cap))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = True
    # a simple cylindrical UV, so a join into a textured body keeps a valid layer
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            c = lp.vert.co
            lp[uv].uv = (0.5 + math.atan2(c.y, c.x) / (2 * math.pi), c.z)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(look.material(f"{name}_ivory", srgb=IVORY, roughness=0.4))
    ob = bpy.data.objects.new(name, me)
    for c in human.users_collection:
        c.objects.link(ob)
    ob.matrix_world = human.matrix_world.copy()
    rig = _body.rig_of(human)
    head = eyes.head_bone(rig)
    vg = ob.vertex_groups.new(name=head)
    vg.add(list(range(len(me.vertices))), 1.0, "REPLACE")
    if rig is not None and head in rig.data.bones:
        ob.parent = rig
        ob.matrix_parent_inverse = rig.matrix_world.inverted()
        ob.modifiers.new("Armature", "ARMATURE").object = rig
    else:
        ob.parent = human
        ob.matrix_parent_inverse = human.matrix_world.inverted()
    report.update(object=name, bone=head, verts=len(me.vertices), faces=len(me.polygons))
    return report


# ------------------------------------------------------------------ apply

def _set_shape(human, shape, weight):
    # every head shape this module ever loaded goes to 0 first: the spec's is the only one
    if human.data.shape_keys:
        for kb in human.data.shape_keys.key_blocks:
            if kb.name.startswith(KEY_PREFIX + "head-") and kb.name[len(KEY_PREFIX + "head-"):] in sheet.FACE_SHAPES:
                kb.value = 0.0
    if not shape:
        return None
    (fname, path), = _files("head", f"head-{shape}", False)
    kb = _key(human, fname, path)
    kb.value = float(weight)
    return kb.name


def apply(human, head_spec):
    """Put a species head on an unbaked MPFB body. `head_spec`: {"shape": FACE_SHAPES name or None,
    "shape_weight": float, "features": {name: weight 0..1}}. Returns a report: the shape key, per feature
    its weight, target keys, delta key and heights, and the tusks object; `unknown` lists names it skipped."""
    human = _obj(human)
    problem = delta.check_topology(human)
    if problem:
        raise ValueError(problem)
    if human.data.shape_keys is None:
        human.shape_key_add(name="Basis", from_mix=False)
    spec = dict(head_spec or {})
    feats = {k: float(v) for k, v in (spec.get("features") or {}).items()}
    report = {"shape": None, "features": {}, "unknown": sorted(k for k in feats if k not in FEATURES),
              "keys": [], "objects": []}
    report["shape"] = _set_shape(human, spec.get("shape"), spec.get("shape_weight", 0.5))
    if report["shape"]:
        report["keys"].append(report["shape"])

    # 1. MPFB targets, at weight x gain (a key this module owns, so it is set, never added to)
    owned = {}
    for feat in FEATURES:
        w = float(np.clip(feats.get(feat, 0.0), 0.0, 1.0))
        rows = []
        for group, stem, sided, gain in TARGETS[feat]:
            for fname, path in _files(group, stem, sided):
                kname = KEY_PREFIX + fname
                owned[kname] = (owned.get(kname, (0.0, path))[0] + w * gain, path)
                if w > 0:
                    rows.append(kname)
        if feat in feats and feat in FEATURES:
            report["features"][feat] = {"weight": round(w, 3), "targets": rows}
    for kname, (v, path) in owned.items():
        kb = human.data.shape_keys.key_blocks.get(kname)
        if kb is None and v <= 0:
            continue
        kb = kb or _key(human, kname[len(KEY_PREFIX):], path)
        kb.value = float(min(v, 1.0))
        if v > 0:
            report["keys"].append(kname)
    human.data.update()

    # 2. deltas, on the surface the targets now shape (hfd: keys are not in mixed_coords, so an old one of
    # ours does not bend the normals it is recomputed on)
    co = delta.mixed_coords(human)
    faces = delta.body_faces(human)
    nrm = delta.vertex_normals(co, faces)
    scale = delta.stature_of(co) / REF_STATURE
    disp = np.zeros((BODY_VERTS, 3))
    for feat, fn in DELTA_SHAPES.items():
        kname = DELTA_PREFIX + feat
        w = float(np.clip(feats.get(feat, 0.0), 0.0, 1.0))
        kb = human.data.shape_keys.key_blocks.get(kname)
        if w <= 0:
            if kb is not None:
                human.shape_key_remove(kb)
            continue
        h = fn(human, co, nrm, faces, scale) * DELTA_PEAK[feat] * scale * w
        rep = _write_delta(human, feat, h)
        report["features"][feat]["delta"] = {"key": rep["key"], "max_mm": rep.get("refined_max_mm", rep["max_mm"])}
        report["keys"].append(rep["key"])
    for kb in human.data.shape_keys.key_blocks:
        if kb.name.startswith(DELTA_PREFIX) and kb.value:
            d = delta.key_heights(human, kb.name)
            disp += nrm * d[:, None]

    # 3. tusks, on the surface as it is drawn (targets and deltas)
    w = float(np.clip(feats.get("tusks", 0.0), 0.0, 1.0))
    surf = co[:BODY_VERTS] + disp
    tusks = _tusks(human, surf, delta.vertex_normals(surf, faces), faces, w, scale)
    if tusks:
        report["features"]["tusks"]["object"] = tusks
        report["objects"].append(tusks["object"])
    human.data.update()
    bpy.context.view_layer.update()
    return report
