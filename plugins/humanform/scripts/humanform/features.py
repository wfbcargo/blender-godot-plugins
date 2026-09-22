"""Head features for any creature (08 fantasy species, layer 2): a head shape plus features, each a region of the
face moved by a displacement profile, optional MPFB targets and optional rigid parts (horns, tusks, spikes).

    rep = features.apply(human, {"shape": "invertedtriangular", "shape_weight": 0.8,
                                 "features": {"ears_pointed": 1.0, "brow_ridge": -0.2}})
    features.apply(human, {"features": {"horn_nubs": {"displace": {"region": {"anchor": "forehead",
        "offset": [0.025, 0, 0.01], "radius": 0.012}, "amount": 0.004}, "attach": {"kind": "horn",
        "anchor": "forehead", "offset": [0.025, 0, 0.01], "length": 0.03, "base_radius": 0.006}}}})
    features.validate(spec)          # [] or the problems, each naming the fix
    features.FEATURES                # the preset names; features.PRESETS their definitions

A feature is a definition (`PRESETS[name]`, or written inline in the spec) with up to three parts:

    targets       MPFB targets by file stem and gain, {"nose-volume-incr": 0.7}; sided stems (l-/r-) are found
                  and loaded in pairs. A negative weight loads `neg_targets`, or else each stem's opposite
                  (incr/decr, in/out, up/down, forward/backward) where MPFB has one.
    displace      a displacement (or a list): `region` (a name in REGIONS, or {"anchor": landmark, "offset",
                  "radius", "mirror", "facing", "side"}), `direction` (normal, up, down, forward, back, out, in,
                  a vector [out, forward, up], {"toward": landmark}, {"away": landmark}, {"axis": [a, b]}),
                  a region may be cut to `above` or `below` a landmark (or [landmark, margin m]),
                  `falloff` (FALLOFFS), `amount` in metres on the reference head (scaled by this head's size and
                  by the weight, negative to press in), `smooth` (Laplacian passes).
    attach        a rigid part (or a list): `kind` (cone, horn, tusk: defaults in KINDS), `anchor` (a landmark),
                  `offset`, `direction`, `length`, `base_radius`, `tip_radius`, `curve` (the tip's bend as a
                  vector [out, forward, up] in lengths), `curl` (degrees the tip turns about `curl_axis`, default
                  [1, 0, 0]: a spiral like a ram's), `sink` (base radii buried along the skin's normal),
                  `clear` (a gap in metres: the part above `clear_above` is tilted forward until it stands that far
                  in front of the face), `color` (sRGB), `roughness`, `bone` ("head" or a bone name), `grow`
                  (its size at weight 0+, as a fraction of weight 1's).

Vectors are in the head's own frame, [out, forward, up] metres: `out` is away from the midline, so a sided
landmark's pair mirrors. Sizes are for a reference head (crown to lip line REF_HEAD) and scale with this head.
Inline definitions may start from a preset, `{"preset": "tusks", "attach": {"length": 0.03}}`, and carry their
own `weight` (default 1). Designing a new one from a description: references/head-features.md.

Keys: every target is its own shape key `hfs:<file stem>`, set (never added to) from the spec, so a fit's `hf:`
levers keep their values and `library.capture` never stores a species head; each feature's displacement is the
key `hfd:head-<feature>` (delta.py's prefix, so `mixed_coords` leaves it out). Parts are one object,
`<human>_headparts`, each part skinned 100% to its bone, which character-pipeline's bake joins into the body beside
the eyes. `apply` sets the head to the spec: keys and parts of features no longer named go.

The rest of the head's anatomy is kept, not replaced: the eyes follow MPFB's eye helpers when a target moves the
sockets (`report["eyes_moved_mm"]`), and `mouth` gives the head its teeth and tongue (`<human>_teeth`, from MPFB's
helpers, which a humanform body otherwise loses in the bake); tusks sit in front of those teeth. Brows and lashes
are laid on the baked body later by `brows` from its own triangles, so they follow every feature.

The head `shape` is MPFB's whole-head target `head/head-<shape>` (`sheet.FACE_SHAPES`) at `shape_weight`. Some
lower the crown (square at 0.5: 5 mm, round 2.4 mm), so humancheck's stature-relative proportions shift a little
on a body fitted without it - a species warp that sets stature afterwards takes that back.

Call it on the unbaked MPFB body (rigged or not) before any proportion warp: the parts are skinned to the head
bone, so a warp that moves bones and skin carries them.
"""

from __future__ import annotations

import copy
import gzip
import math
import os
from types import SimpleNamespace

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from . import delta, measure, sheet

KEY_PREFIX = "hfs:"
DELTA_PREFIX = delta.KEY_PREFIX + "head-"          # hfd:head-<feature>
PARTS_SUFFIX = "_headparts"
BODY_VERTS = delta.BODY_VERTS
REF_HEAD = 0.175          # crown to lip line (m) of the head sizes are written for (MPFB's man near 1.75 m)
IVORY = (0.86, 0.80, 0.66)
HORN = (0.30, 0.26, 0.22)

PRESETS = {
    "ears_pointed": {"targets": {"ear-shape-pointed": 1.0, "ear-scale-vert-incr": 0.25},
                     "neg_targets": {"ear-shape-round": 1.0}},
    "ear_size": {"targets": {"ear-scale-incr": 1.0, "ear-scale-vert-incr": 0.3}},
    "ears_large": {"targets": {"ear-scale-incr": 1.0, "ear-scale-vert-incr": 0.4, "ear-wing-incr": 0.45}},
    "brow_ridge": {"targets": {"eyebrows-trans-forward": 0.4},
                   "displace": {"region": "brow", "direction": "normal", "falloff": "linear", "amount": 0.0048}},
    "nose_size": {"targets": {"nose-scale-horiz-incr": 0.8, "nose-scale-vert-incr": 0.55, "nose-scale-depth-incr": 0.6,
                              "nose-volume-incr": 0.7, "nose-flaring-incr": 0.5, "nose-width3-incr": 0.4}},
    # not head-square: it lowers the crown 3-4 mm, which moves every proportion measured in statures; not
    # chin-prognathism: on a closed mouth it pushes the lower lip through the upper (16 faces at 0.35)
    "jaw_heavy": {"targets": {"chin-bones-incr": 1.0, "chin-width-incr": 0.8, "chin-prominent-incr": 0.5},
                  "displace": {"region": "jaw", "direction": "normal", "falloff": "linear", "amount": 0.004}},
    "cheek_gaunt": {"targets": {"cheek-volume-decr": 1.0, "cheek-inner-decr": 0.6, "cheek-bones-incr": 0.45,
                                "head-fat-decr": 0.3}},
    # the lower lip pushed out where the tusks rise - below the lip line only, or it goes through the upper lip
    "tusks": {"displace": {"region": {"anchor": "tusk_root", "radius": 0.018, "facing": "forward",
                                      "below": ["mouth", 0.0015]},
                           "direction": "normal", "falloff": "gauss", "amount": 0.0035, "smooth": 3},
              "attach": {"kind": "tusk", "anchor": "tusk_root", "length": 0.024, "base_radius": 0.0038}},
    "horn_nubs": {"displace": {"region": {"anchor": "forehead", "offset": [0.024, 0, 0.004], "radius": 0.016},
                               "amount": 0.004},
                  "attach": {"kind": "cone", "anchor": "forehead", "offset": [0.024, 0, 0.004], "length": 0.022,
                             "base_radius": 0.007, "color": [0.35, 0.30, 0.26]}},
    "horns": {"displace": {"region": {"anchor": "temple", "offset": [0, 0, 0.03], "radius": 0.02}, "amount": 0.003},
              "attach": {"kind": "horn", "anchor": "temple", "offset": [0, 0, 0.03], "direction": [0.5, -0.1, 0.85],
                         "length": 0.10, "base_radius": 0.013, "curve": [0.35, 0.55, -0.6], "rings": 14}},
    "ram_horns": {"attach": {"kind": "horn", "anchor": "temple", "offset": [0, 0, 0.03], "direction": [0.35, 0.3, 0.9],
                             "length": 0.20, "base_radius": 0.016, "tip_radius": 0.12, "curl": -330,
                             "curve": [0.25, 0, 0], "rings": 24, "segments": 14}},
}
FEATURES = tuple(PRESETS)

KINDS = {
    "cone": {"rings": 5, "segments": 10, "curve": [0.0, 0.0, 0.0], "tip_radius": 0.1, "sink": 0.3,
             "direction": "normal", "color": IVORY, "roughness": 0.4, "grow": 0.45},
    "horn": {"rings": 9, "segments": 12, "curve": [0.15, -0.25, 0.0], "tip_radius": 0.08, "sink": 0.35,
             "direction": "normal", "color": HORN, "roughness": 0.55, "grow": 0.4},
    # up, a little out and forward; the tip curls out; resting on the upper lip (a human upper lip sits in front
    # of the lower one, so a tusk rooted in the lower lip is tilted forward until it clears)
    "tusk": {"rings": 7, "segments": 10, "curve": [0.10, 0.0, 0.0], "tip_radius": 0.13, "sink": 0.4,
             "direction": [0.15, 0.10, 1.0], "clear": -0.0003, "clear_above": "mouth", "max_tilt": 0.45,
             "color": IVORY, "roughness": 0.4, "grow": 0.45},
}
ATTACH_KEYS = {"kind", "anchor", "offset", "mirror", "side", "direction", "length", "base_radius", "tip_radius",
               "curve", "curl", "curl_axis", "sink", "clear", "clear_above", "max_tilt", "color", "roughness", "bone",
               "grow", "rings", "segments"}
DISPLACE_KEYS = {"region", "direction", "falloff", "amount", "smooth"}
REGION_KEYS = {"anchor", "offset", "radius", "mirror", "facing", "side", "name", "above", "below"}
DEF_KEYS = {"preset", "weight", "targets", "neg_targets", "displace", "attach", "notes"}
FALLOFFS = ("smooth", "linear", "gauss", "sharp", "dome", "flat")
DIRECTIONS = ("normal", "up", "down", "forward", "back", "out", "in")
# landmarks: sided ones are named bare (both sides) or with .L / .R
SIDED = ("eye", "brow", "temple", "cheek", "jaw", "ear", "ear_tip", "mouth_corner", "tusk_root")
CENTRAL = ("glabella", "nose_bridge", "nose_tip", "forehead", "crown", "occiput", "lip_upper", "lip_lower", "chin",
           "mouth")
LANDMARKS = SIDED + CENTRAL
REGIONS = ("brow", "forehead", "crown", "temple", "nose", "ear", "ear_tip", "cheek", "jaw", "chin", "lips")
OPPOSITE = (("incr", "decr"), ("in", "out"), ("up", "down"), ("forward", "backward"))


def _obj(o):
    return bpy.data.objects[o] if isinstance(o, str) else o


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------------ definitions

def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def resolve(name, value):
    """(definition, weight) for one entry of `features`: a preset name with a weight, or an inline definition -
    merged over `preset` when it names one, or over the preset of its own name (so a preset is changed by giving
    only what differs). (None, weight) for a name that is neither."""
    if isinstance(value, dict):
        d = dict(value)
        base = d.pop("preset", None)
        if base is None and name in PRESETS:
            base = name     # {"tusks": {"weight": 0.7, "attach": {"length": 0.03}}}: the preset, changed
        if base is not None:
            if base not in PRESETS:
                return None, 0.0
            d = _merge(PRESETS[base], d)
        return d, float(d.pop("weight", 1.0))
    return (copy.deepcopy(PRESETS[name]) if name in PRESETS else None), float(value)


def _listify(x):
    return [] if x is None else list(x) if isinstance(x, (list, tuple)) and x and isinstance(x[0], dict) else [x]


def _vec_ok(v):
    return isinstance(v, (list, tuple)) and len(v) == 3 and all(isinstance(c, (int, float)) for c in v)


def _anchor_ok(a):
    base = a.split(".")[0] if isinstance(a, str) else None
    return base in LANDMARKS and (a == base or (base in SIDED and a[len(base):] in (".L", ".R")))


def _direction_problems(where, d):
    if d is None or d in DIRECTIONS or _vec_ok(d):
        return []
    if isinstance(d, dict) and len(d) == 1:
        (k, v), = d.items()
        if k in ("toward", "away") and _anchor_ok(v):
            return []
        if k == "axis" and isinstance(v, (list, tuple)) and len(v) == 2 and all(_anchor_ok(a) for a in v):
            return []
    return [f"{where}.direction {d!r}: one of {', '.join(DIRECTIONS)}, a vector [out, forward, up], "
            f"{{toward|away: landmark}} or {{axis: [landmark, landmark]}}"]


def check_definition(name, d):
    """The problems with one feature definition (resolved), each naming the fix."""
    out = []
    where = f"head.features.{name}"
    for k in sorted(set(d) - DEF_KEYS):
        out.append(f"{where}: unknown key {k!r} - a feature takes {', '.join(sorted(DEF_KEYS))}")
    for tk in ("targets", "neg_targets"):
        t = d.get(tk) or {}
        if not isinstance(t, dict):
            out.append(f"{where}.{tk} must be a table of MPFB target stem = gain")
            continue
        for stem, gain in t.items():
            if not _target_files(stem):
                out.append(f"{where}.{tk}: no MPFB target {stem!r} (a file stem under mpfb/data/targets, "
                           "without l-/r- or .target.gz)")
            if not isinstance(gain, (int, float)):
                out.append(f"{where}.{tk}.{stem} = {gain!r} must be a number")
    for i, dp in enumerate(_listify(d.get("displace"))):
        w = f"{where}.displace[{i}]"
        if not isinstance(dp, dict):
            out.append(f"{w} must be a table")
            continue
        out += [f"{w}: unknown key {k!r} - it takes {', '.join(sorted(DISPLACE_KEYS))}"
                for k in set(dp) - DISPLACE_KEYS]
        r = dp.get("region")
        if isinstance(r, str):
            if r not in REGIONS:
                out.append(f"{w}.region {r!r}: one of {', '.join(REGIONS)} or {{anchor = landmark, radius = m}}")
        elif isinstance(r, dict):
            out += [f"{w}.region: unknown key {k!r} - it takes {', '.join(sorted(REGION_KEYS))}"
                    for k in set(r) - REGION_KEYS]
            if "name" in r and r["name"] not in REGIONS:
                out.append(f"{w}.region.name {r['name']!r}: one of {', '.join(REGIONS)}")
            if "name" not in r and not _anchor_ok(r.get("anchor")):
                out.append(f"{w}.region.anchor {r.get('anchor')!r}: one of {', '.join(LANDMARKS)} (sided: .L/.R)")
            for key in ("above", "below"):
                v = r.get(key)
                if v is not None and not (_anchor_ok(v) or (isinstance(v, (list, tuple)) and len(v) == 2
                                                           and _anchor_ok(v[0]) and isinstance(v[1], (int, float)))):
                    out.append(f"{w}.region.{key} {v!r}: a landmark, or [landmark, margin in metres]")
            if "anchor" in r and not isinstance(r.get("radius"), (int, float)):
                out.append(f"{w}.region.radius: an anchored region needs a radius in metres")
            if r.get("offset") is not None and not _vec_ok(r["offset"]):
                out.append(f"{w}.region.offset must be [out, forward, up] in metres")
        else:
            out.append(f"{w}.region: a region name or {{anchor = landmark, radius = m}}")
        out += _direction_problems(w, dp.get("direction"))
        if dp.get("falloff", "smooth") not in FALLOFFS:
            out.append(f"{w}.falloff {dp['falloff']!r}: one of {', '.join(FALLOFFS)}")
        if not isinstance(dp.get("amount"), (int, float)):
            out.append(f"{w}.amount: metres on the reference head (e.g. 0.004), negative to press in")
    for i, at in enumerate(_listify(d.get("attach"))):
        w = f"{where}.attach[{i}]"
        if not isinstance(at, dict):
            out.append(f"{w} must be a table")
            continue
        out += [f"{w}: unknown key {k!r} - it takes {', '.join(sorted(ATTACH_KEYS))}" for k in set(at) - ATTACH_KEYS]
        if at.get("kind", "cone") not in KINDS:
            out.append(f"{w}.kind {at['kind']!r}: one of {', '.join(KINDS)}")
        if not _anchor_ok(at.get("anchor")):
            out.append(f"{w}.anchor {at.get('anchor')!r}: one of {', '.join(LANDMARKS)} (sided: .L/.R)")
        for k in ("length", "base_radius"):
            if not isinstance(at.get(k), (int, float)) or at[k] <= 0:
                out.append(f"{w}.{k}: a positive size in metres on the reference head")
        for k in ("offset", "curve"):
            if at.get(k) is not None and not _vec_ok(at[k]):
                out.append(f"{w}.{k} must be [out, forward, up]")
        out += _direction_problems(w, at.get("direction"))
    return out


def validate(head_spec):
    """The problems with a species `head` block, each saying what to write instead; [] when it is fine.
    A feature name that is neither a preset nor a definition is listed here too (apply itself only reports it)."""
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
        return out + [f"head.features must be a table of name = weight or name = {{definition}}, "
                      f"not {type(feats).__name__}"]
    for name, v in feats.items():
        if not isinstance(v, (dict, int, float)):
            out.append(f"head.features.{name} = {v!r}: a weight in [-1, 1] or a definition table")
            continue
        if isinstance(v, dict) and v.get("preset") is not None and v["preset"] not in PRESETS:
            out.append(f"head.features.{name}.preset {v['preset']!r}: one of {', '.join(FEATURES)}")
            continue
        d, w = resolve(name, v)
        if d is None:
            out.append(f"head.features: unknown feature {name!r} - a preset ({', '.join(FEATURES)}) or a "
                       "definition table (targets / displace / attach)")
            continue
        if not -1.0 <= w <= 1.0:
            out.append(f"head.features.{name}: weight {w!r} must be in [-1, 1] (0 is human)")
        out += check_definition(name, d)
    return out


# ------------------------------------------------------------------ MPFB targets

_ROOT = None
_INDEX = None


def _root():
    global _ROOT
    if _ROOT is None:
        from . import scaffold
        _, _, _, LocationService = scaffold.services()
        _ROOT = LocationService.get_mpfb_data("targets")
    return _ROOT


def _target_files(stem):
    """[(file stem, path)] for an MPFB target stem: the pair l-/r- when it is sided, else the one file."""
    global _INDEX
    if _INDEX is None:
        _INDEX = {}
        for group in os.listdir(_root()):
            gdir = os.path.join(_root(), group)
            if os.path.isdir(gdir):
                for f in os.listdir(gdir):
                    if f.endswith(".target.gz"):
                        _INDEX[f[:-len(".target.gz")]] = os.path.join(gdir, f)
    if stem in _INDEX:
        return [(stem, _INDEX[stem])]
    return [(f"{s}-{stem}", _INDEX[f"{s}-{stem}"]) for s in ("l", "r") if f"{s}-{stem}" in _INDEX]


def _opposite(stem):
    parts = stem.split("-")
    for a, b in OPPOSITE:
        for x, y in ((a, b), (b, a)):
            if parts[-1] == x:
                cand = "-".join(parts[:-1] + [y])
                if _target_files(cand):
                    return cand
    return None


def _key(human, fname, path):
    from . import scaffold
    _, TargetService, _, _ = scaffold.services()
    kname = KEY_PREFIX + fname
    kb = human.data.shape_keys.key_blocks.get(kname) if human.data.shape_keys else None
    if kb is None:
        kb = TargetService.load_target(human, path, weight=0.0, name=kname)
    return kb


_MAGS = {}


def _magnitude(stem):
    """How far MPFB's target (both sides of a sided stem) moves each base-mesh vertex, normalised to 1."""
    if stem not in _MAGS:
        m = np.zeros(BODY_VERTS)
        for _, path in _target_files(stem):
            with gzip.open(path, "rt") as fh:
                for line in fh:
                    p = line.split()
                    if len(p) == 4 and p[0].isdigit() and int(p[0]) < BODY_VERTS:
                        m[int(p[0])] = max(m[int(p[0])], math.sqrt(sum(float(c) ** 2 for c in p[1:])))
        _MAGS[stem] = m / max(m.max(), 1e-12)
    return _MAGS[stem]


# ------------------------------------------------------------------ the head's frame: landmarks

def _eye_centres(human, co):
    out = {}
    for side in ("l", "r"):
        g = human.vertex_groups.get(f"helper-{side}-eye")
        if g is None:
            raise ValueError(f"{human.name} has no helper-{side}-eye group (not an MPFB2 body?)")
        idx = [v.index for v in human.data.vertices if any(e.group == g.index for e in v.groups)]
        c = co[idx].mean(axis=0)
        out["L" if c[0] > 0 else "R"] = c
    return out


def frame(human, co, nrm, faces):
    """The head as features see it: surface, size, scale (head size / REF_HEAD) and landmarks {name: (point,
    normal)}, sided ones as `name.L` (+x, the body's left) and `name.R`. `co`: every vertex (the eye helpers,
    which come after the body's, are read from it)."""
    from mathutils.bvhtree import BVHTree
    eyes = _eye_centres(human, co)                       # the eye helpers come after the body's vertices
    co = co[:BODY_VERTS]
    tree = BVHTree.FromPolygons([Vector(c) for c in co], [tuple(int(i) for i in f) for f in faces])
    F = SimpleNamespace(co=co, nrm=nrm, faces=faces, tree=tree, lm={})
    ez = float((eyes["L"][2] + eyes["R"][2]) / 2)
    ex = float(abs(eyes["L"][0] - eyes["R"][0]) / 2)
    ey = float((eyes["L"][1] + eyes["R"][1]) / 2)
    f = measure.face_features()
    mouth = co[f["mouth"]]
    slit = float(mouth[:, 2].mean())
    top = int(np.argmax(co[:, 2]))
    F.crown_z, F.slit_z, F.eye_z, F.eye_x = float(co[top, 2]), slit, ez, ex
    F.size = F.crown_z - slit
    F.scale = F.size / REF_HEAD
    s = F.scale

    def ray(origin, direction):
        hit, n, _, _ = tree.ray_cast(Vector(origin), Vector(direction).normalized(), 1.0)
        return None if hit is None else (np.array(hit), np.array(n))

    def front(x, z):
        return ray((x, -0.5, z), (0, 1, 0))

    def put(name, value):
        if value is not None:
            n = np.asarray(value[1], float)
            F.lm[name] = (np.asarray(value[0], float), n / max(np.linalg.norm(n), 1e-9))

    def vert(i):
        return co[i].copy(), nrm[i].copy()

    def centroid(mask, sgn=0):
        w = mask * (1 if sgn == 0 else (np.sign(co[:, 0]) == sgn))
        return (co * w[:, None]).sum(axis=0) / max(w.sum(), 1e-9)

    for side, sgn in (("L", 1.0), ("R", -1.0)):
        put(f"eye.{side}", (eyes[side], np.array([0.0, -1.0, 0.0])))
        put(f"brow.{side}", front(sgn * ex, ez + 0.013 * s))
        put(f"temple.{side}", ray((sgn * 0.5, ey + 0.025 * s, ez + 0.02 * s), (-sgn, 0, 0)))
        c = centroid(_magnitude("cheek-volume-incr"), sgn)
        put(f"cheek.{side}", front(c[0], c[2]))
        c = centroid(_region_jaw(F), sgn)
        put(f"jaw.{side}", ray((sgn * 0.5, c[1], c[2]), (-sgn, 0, 0)))
        ear = _magnitude("ear-scale-incr") * (np.sign(co[:, 0]) == sgn)
        c = centroid(ear)
        put(f"ear.{side}", (c, np.array([sgn, 0.0, 0.0])))
        idx = np.flatnonzero(ear > 0.3)
        put(f"ear_tip.{side}", vert(int(idx[np.argmax(co[idx, 2])])))
        m = f["mouth"][int(np.argmax(sgn * mouth[:, 0]))]
        put(f"mouth_corner.{side}", vert(m))
    for p, n, sgn in _tusk_roots(co, nrm, s):
        put(f"tusk_root.{'L' if sgn > 0 else 'R'}", (p, n))
    put("glabella", front(0.0, ez + 0.010 * s))
    put("nose_bridge", front(0.0, ez))
    put("forehead", front(0.0, ez + 0.045 * s))
    put("crown", vert(top))
    put("occiput", ray((0.0, 0.5, ez + 0.02 * s), (0, -1, 0)))
    nose = np.flatnonzero(_magnitude("nose-volume-incr") > 0.3)
    put("nose_tip", vert(int(nose[np.argmin(co[nose, 1])])))
    put("mouth", front(0.0, slit))
    put("lip_upper", front(0.0, slit + 0.005 * s))
    put("lip_lower", front(0.0, slit - 0.006 * s))
    c = centroid(_magnitude("chin-prominent-incr"))
    put("chin", front(0.0, c[2]))
    return F


def _tusk_roots(co, nrm, s):
    """On the lower lip, 62% of the way from the middle to the corner, a little below the lip line."""
    f = measure.face_features()
    mouth, lips = co[f["mouth"]], np.asarray(f["lips"])
    slit = float(mouth[:, 2].mean())
    half = float(mouth[:, 0].max() - mouth[:, 0].min()) / 2
    lower = lips[co[lips, 2] < slit - 0.001 * s]
    out = []
    for sgn in (1.0, -1.0):
        want = np.array([sgn * 0.62 * half, 0.0, slit - 0.0045 * s])
        cand = lower[np.sign(co[lower, 0]) == sgn]
        i = int(cand[np.argmin(np.linalg.norm((co[cand] - want)[:, [0, 2]], axis=1))])
        out.append((co[i].copy(), nrm[i].copy(), sgn))
    return out


def _landmarks(F, name, mirror=True):
    """[(point, normal, x sign)] for a landmark name: a sided bare name gives both sides (one with mirror False:
    the left), `.L`/`.R` one, a central one itself (sign +1)."""
    if "." in name:
        p, n = F.lm[name]
        return [(p, n, 1.0 if name.endswith(".L") else -1.0)]
    if name in SIDED:
        sides = ("L", "R") if mirror else ("L",)
        return [(*F.lm[f"{name}.{s}"], 1.0 if s == "L" else -1.0) for s in sides]
    p, n = F.lm[name]
    return [(p, n, 1.0)]


def _head_vec(v, sgn):
    """[out, forward, up] -> body space for the side with x sign `sgn`."""
    return np.array([sgn * v[0], -v[1], v[2]], float)


# ------------------------------------------------------------------ regions

def _region_brow(F):
    """Above the eye, peaking over it, fading to the glabella and the temples: MPFB's eyebrow target's reach."""
    s, co = F.scale, F.co
    x, z = co[:, 0], co[:, 2]
    up = _smoothstep((z - (F.eye_z + 0.006 * s)) / (0.009 * s))     # none on the upper lid
    top = 1.0 - _smoothstep((z - (F.eye_z + 0.017 * s)) / (0.016 * s))
    lateral = 1.0 - _smoothstep((np.abs(x) - (F.eye_x + 0.010 * s)) / (0.014 * s))
    h = np.sqrt(_magnitude("eyebrows-trans-forward")) * up * top * lateral * _smoothstep(-F.nrm[:, 1] / 0.4)
    return delta.smooth(h, F.faces, iterations=10)


def _region_jaw(F):
    """The angle of the mandible: MPFB's chin-bones target's reach, weighted to its outer back."""
    side = _smoothstep((np.abs(F.co[:, 0]) - 0.02 * F.scale) / (0.03 * F.scale))
    return delta.smooth(_magnitude("chin-bones-incr") * side * _smoothstep(np.abs(F.nrm[:, 0]) / 0.5), F.faces, 6)


def _region(F, name):
    co, s = F.co, F.scale
    if name == "brow":
        m = _region_brow(F)
    elif name == "jaw":
        m = _region_jaw(F)
    elif name == "forehead":
        z = co[:, 2]
        m = (_smoothstep((z - (F.eye_z + 0.022 * s)) / (0.012 * s))
             * (1 - _smoothstep((z - (F.eye_z + 0.065 * s)) / (0.02 * s)))
             * (1 - _smoothstep((np.abs(co[:, 0]) - F.eye_x) / (0.02 * s))) * _smoothstep(-F.nrm[:, 1] / 0.5))
    elif name == "crown":
        m = _smoothstep((co[:, 2] - (F.crown_z - 0.06 * s)) / (0.06 * s)) * _smoothstep(F.nrm[:, 2] / 0.5)
    elif name == "temple":
        m = _magnitude("forehead-temple-incr")
    elif name == "nose":
        m = np.maximum(_magnitude("nose-volume-incr"), _magnitude("nose-scale-depth-incr"))
    elif name == "ear":
        m = _magnitude("ear-scale-incr")
    elif name == "ear_tip":
        m = np.zeros(BODY_VERTS)
        for sgn in (1.0, -1.0):
            ear = _magnitude("ear-scale-incr") * (np.sign(co[:, 0]) == sgn)
            c = F.lm["ear.L" if sgn > 0 else "ear.R"][0]
            m += ear * _smoothstep((co[:, 2] - c[2]) / (0.025 * s))
    elif name == "cheek":
        m = _magnitude("cheek-volume-incr")
    elif name == "chin":
        m = _magnitude("chin-prominent-incr")
    elif name == "lips":
        m = np.zeros(BODY_VERTS)
        m[np.asarray(measure.face_features()["lips"])] = 1.0
        m = delta.smooth(m, F.faces, iterations=2)
    else:
        raise ValueError(f"unknown region {name!r}: one of {', '.join(REGIONS)}")
    return m / max(m.max(), 1e-12)


def _anchored(F, r):
    """[(s in [0, 1] per vertex, x sign)] - 1 at each anchor (plus offset, mirrored), 0 at `radius`."""
    out = []
    for p, n, sgn in _landmarks(F, r["anchor"], r.get("mirror", True)):
        centre = p + _head_vec(r.get("offset") or (0, 0, 0), sgn) * F.scale
        # a central anchor with an offset out of the midline makes a pair unless mirror is false
        pairs = [(centre, sgn)]
        paired = r["anchor"] in CENTRAL and r.get("mirror", True) and (r.get("offset") or [0])[0]
        if paired:
            pairs.append((p + _head_vec(r["offset"], -1.0) * F.scale, -1.0))
        for c, sg in pairs:
            d = np.linalg.norm(F.co - c, axis=1)
            out.append((np.clip(1 - d / (float(r["radius"]) * F.scale), 0, 1), sg))
    return out


def _facing(F, name):
    return _smoothstep(np.einsum("ij,j->i", F.nrm, _named_dir(name, 1.0)) / 0.3) if name != "out" else \
        _smoothstep(np.abs(F.nrm[:, 0]) / 0.3)


def _named_dir(name, sgn):
    return {"up": np.array([0, 0, 1.0]), "down": np.array([0, 0, -1.0]), "forward": np.array([0, -1.0, 0]),
            "back": np.array([0, 1.0, 0]), "out": np.array([sgn, 0, 0]), "in": np.array([-sgn, 0, 0])}[name]


FALL = {"smooth": _smoothstep, "linear": lambda s: np.clip(s, 0, 1), "sharp": lambda s: np.clip(s, 0, 1) ** 2,
        "gauss": lambda s: np.where(s > 0, np.exp(-4.5 * (1 - np.clip(s, 0, 1)) ** 2), 0.0),
        "dome": lambda s: np.sqrt(np.clip(1 - (1 - np.clip(s, 0, 1)) ** 2, 0, 1)),
        "flat": lambda s: _smoothstep((np.clip(s, 0, 1) - 0.3) / 0.2)}


def _direction(F, d, sgn_vertex):
    """Per-vertex unit directions (BODY_VERTS, 3)."""
    n = len(F.co)
    if d is None or d == "normal":
        return F.nrm
    if isinstance(d, str):
        if d in ("out", "in"):
            v = np.zeros((n, 3))
            v[:, 0] = sgn_vertex if d == "out" else -sgn_vertex
            return v
        return np.tile(_named_dir(d, 1.0), (n, 1))
    if isinstance(d, (list, tuple)):
        v = np.stack([sgn_vertex * d[0], np.full(n, -d[1]), np.full(n, d[2])], axis=1)
        return v / np.maximum(np.linalg.norm(v, axis=1), 1e-9)[:, None]
    (k, a), = d.items()

    def point(name):
        pts = _landmarks(F, name)
        if len(pts) == 1:
            return np.tile(pts[0][0], (n, 1))
        return np.where((sgn_vertex > 0)[:, None], pts[0][0], pts[1][0])
    if k == "axis":
        v = point(a[1]) - point(a[0])
    else:
        v = point(a) - F.co
        v = v if k == "toward" else -v
    return v / np.maximum(np.linalg.norm(v, axis=1), 1e-9)[:, None]


def _displacement(F, dp, weight):
    """(BODY_VERTS, 3) metres for one displace entry at this weight."""
    r = dp["region"]
    fall = FALL[dp.get("falloff", "smooth")]
    if isinstance(r, str) or "name" in (r or {}):
        s = fall(_region(F, r if isinstance(r, str) else r["name"]))
        if isinstance(r, dict) and r.get("side") in ("L", "R"):
            s = s * (np.sign(F.co[:, 0]) == (1 if r["side"] == "L" else -1))
    else:
        s = np.zeros(BODY_VERTS)
        for m, _ in _anchored(F, r):
            s = np.maximum(s, fall(m))
    if isinstance(r, dict) and r.get("facing"):
        s = s * _facing(F, r["facing"])
    for key, sign in (("above", 1.0), ("below", -1.0)):
        if isinstance(r, dict) and r.get(key) is not None:
            lm, margin = (r[key], 0.0) if isinstance(r[key], str) else (r[key][0], float(r[key][1]))
            z0 = _landmarks(F, lm)[0][0][2] + sign * margin * F.scale
            s = s * _smoothstep(sign * (F.co[:, 2] - z0) / (0.004 * F.scale))
    it = int(dp.get("smooth", 2))
    if it:
        s = delta.smooth(s, F.faces, iterations=it)
    from . import muscle
    h = muscle.despike(s * float(dp["amount"]) * F.scale * weight, F.faces, limit=muscle.SPIKE_LIMIT * F.scale)
    sgn = np.where(F.co[:, 0] >= 0, 1.0, -1.0)
    return _direction(F, dp.get("direction", "normal"), sgn) * h[:, None]


# ------------------------------------------------------------------ attached parts

def _ring(bm, centre, axis, radius, n):
    a = Vector(axis).normalized()
    side = Vector((1.0, 0.0, 0.0)) if abs(a.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    u = side.cross(a).normalized()
    v = a.cross(u).normalized()
    return [bm.verts.new(Vector(centre) + radius * (math.cos(t) * u + math.sin(t) * v))
            for t in (2 * math.pi * k / n for k in range(n))]


def _clearance(F):
    def dist(p):
        hit, _, _, _ = F.tree.ray_cast(Vector((p[0], p[1] - 0.2, p[2])), Vector((0.0, 1.0, 0.0)), 0.4)
        return 0.2 if hit is None else float(hit.y - p[1])
    return dist


def _part(bm, F, at, weight, report):
    """One attach entry: a tapered, curved tube with a closed base and a point, per side. Returns the new faces."""
    at = _merge(KINDS[at.get("kind", "cone")], at)
    grow = float(at["grow"]) + (1 - float(at["grow"])) * weight
    length = float(at["length"]) * F.scale * grow
    r0 = float(at["base_radius"]) * F.scale * grow
    tip_r = float(at["tip_radius"]) * r0 if at["tip_radius"] < 1 else float(at["tip_radius"]) * F.scale * grow
    rings, seg = int(at["rings"]), int(at["segments"])
    dist = _clearance(F)
    new = []
    places = []
    for p, n, sgn in _landmarks(F, at["anchor"], at.get("mirror", True)):
        places.append((p, n, sgn))
        # a central anchor with an offset out of the midline makes a pair unless mirror is false
        if at["anchor"] in CENTRAL and at.get("mirror", True) and (at.get("offset") or [0])[0]:
            places.append((p, n, -1.0))
    for p, n, sgn in places:
        if at.get("side") in ("L", "R") and sgn != (1.0 if at["side"] == "L" else -1.0):
            continue
        p = p + _head_vec(at.get("offset") or (0, 0, 0), sgn) * F.scale
        if at["anchor"] in CENTRAL and (at.get("offset") or [0])[0]:
            # re-seat an offset anchor on the skin: the nearest surface point along the anchor's normal
            hit, hn, _, _ = F.tree.ray_cast(Vector(p + 0.05 * n), Vector(-n), 0.1)
            if hit is not None:
                p, n = np.array(hit), np.array(hn)
        base = p - float(at["sink"]) * r0 * n
        d = at.get("direction", "normal")
        if d == "normal":
            axis = n.copy()
        elif isinstance(d, str):
            axis = _named_dir(d, sgn)
        elif isinstance(d, dict):
            axis = _direction(F, d, np.full(len(F.co), sgn))[0] if "axis" in d else \
                (_landmarks(F, d.get("toward") or d.get("away"))[0 if sgn > 0 else -1][0] - base) * \
                (1 if "toward" in d else -1)
        else:
            axis = _head_vec(d, sgn)
        axis = axis / np.linalg.norm(axis)
        ts = np.linspace(0.0, 1.0, rings)
        rad = [float(r0 * (1 - t) ** 0.8 + tip_r * t) for t in ts]
        bend = _head_vec(at["curve"], sgn) * length
        tilt = 0.0
        curl = math.radians(float(at.get("curl", 0.0)))
        cax = _head_vec(at.get("curl_axis") or (1.0, 0.0, 0.0), 1.0)
        if sgn < 0:                                   # an axis is a pseudovector: its mirror keeps x, flips y and z
            cax = np.array([cax[0], -cax[1], -cax[2]])
        cax = cax / np.linalg.norm(cax)
        for _ in range(12):
            if curl:
                # an arc: the tangent turns by `curl` about `curl_axis` over the length (a ram's spiral)
                pts, q, t = [base.copy()], base.copy(), axis.copy()
                step = curl / (rings - 1)
                for k in range(1, rings):
                    t = (t * math.cos(step) + np.cross(cax, t) * math.sin(step)
                         + cax * np.dot(cax, t) * (1 - math.cos(step)))
                    q = q + t * length / (rings - 1)
                    pts.append(q.copy())
                pts = np.array(pts) + np.outer(ts * ts, bend)
            else:
                pts = base + np.outer(ts, axis) * length + np.outer(ts * ts, bend)
            if at.get("clear") is None:
                break
            above = _landmarks(F, at.get("clear_above", "mouth"))[0][0][2] + 0.003 * F.scale
            worst = 0.0
            for k in range(1, rings):
                if pts[k, 2] >= above:
                    worst = max(worst, (rad[k] + float(at["clear"]) * F.scale - dist(pts[k])) / (ts[k] * length))
            if worst <= 1e-4 or axis[1] < -float(at.get("max_tilt", 0.45)):
                break
            tilt += worst
            axis = axis + np.array([0.0, -worst, 0.0])
            axis /= np.linalg.norm(axis)
        loops = [_ring(bm, pts[k], pts[min(k + 1, rings - 1)] - pts[max(k - 1, 0)], rad[k], seg)
                 for k in range(rings - 1)]
        tip = bm.verts.new(Vector(pts[-1]))
        cap = bm.verts.new(Vector(base - 0.4 * r0 * axis))
        for a, b in zip(loops, loops[1:]):
            for k in range(seg):
                new.append(bm.faces.new((a[k], a[(k + 1) % seg], b[(k + 1) % seg], b[k])))
        for k in range(seg):
            new.append(bm.faces.new((loops[-1][k], loops[-1][(k + 1) % seg], tip)))
            new.append(bm.faces.new((loops[0][(k + 1) % seg], loops[0][k], cap)))
        report.append({"kind": at.get("kind", "cone"), "side": "L" if sgn > 0 else "R",
                       "base": [round(float(c), 4) for c in base], "tip": [round(float(c), 4) for c in pts[-1]],
                       "length_mm": round(length * 1000, 1), "radius_mm": round(r0 * 1000, 1),
                       "tilt": round(tilt, 3), "bone": at.get("bone", "head")})
    return new, at


def _build_parts(human, F, parts):
    """`parts`: [(feature, attach entry, weight)] -> the one `<human>_headparts` object (or None), skinned."""
    from . import eyes, look
    from . import body as _body
    name = human.name + PARTS_SUFFIX
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    if not parts:
        return None
    rig = _body.rig_of(human)
    head = eyes.head_bone(rig)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    mats, groups, report = [], {}, {}
    for feat, at, w in parts:
        rows = report.setdefault(feat, [])
        faces, full = _part(bm, F, at, w, rows)
        mname = f"{human.name}_{feat}_part"
        mat = look.material(mname, srgb=tuple(full["color"]), roughness=float(full["roughness"]))
        if mat not in mats:
            mats.append(mat)
        bone = head if full.get("bone", "head") == "head" else full["bone"]
        for f in faces:
            f.material_index = mats.index(mat)
            f.smooth = True
            for lp in f.loops:
                c = lp.vert.co
                lp[uv].uv = (0.5 + math.atan2(c.y, c.x) / (2 * math.pi), c.z)
                groups.setdefault(bone, set()).add(lp.vert)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.verts.index_update()
    by_bone = {b: [v.index for v in vs] for b, vs in groups.items()}
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    for c in human.users_collection:
        c.objects.link(ob)
    ob.matrix_world = human.matrix_world.copy()
    for b, idx in by_bone.items():
        ob.vertex_groups.new(name=b).add(idx, 1.0, "REPLACE")
    missing = [b for b in by_bone if rig is None or b not in rig.data.bones]
    if rig is not None and not missing:
        ob.parent = rig
        ob.matrix_parent_inverse = rig.matrix_world.inverted()
        ob.modifiers.new("Armature", "ARMATURE").object = rig
    else:
        ob.parent = human
        ob.matrix_parent_inverse = human.matrix_world.inverted()
    return {"object": name, "verts": len(me.vertices), "faces": len(me.polygons), "bones": sorted(by_bone),
            "unbound": missing if rig is not None else "no rig", "parts": report}


# ------------------------------------------------------------------ the mouth and the eyes follow the head

TEETH = (0.93, 0.91, 0.85)
TONGUE = (0.72, 0.38, 0.38)
MOUTH_PARTS = (("teeth", "helper-upper-teeth", TEETH, 0.3), ("teeth", "helper-lower-teeth", TEETH, 0.3),
               ("tongue", "helper-tongue", TONGUE, 0.45))
TEETH_SUFFIX = "_teeth"


def mouth(human):
    """Teeth and tongue: `<human>_teeth`, MPFB's own teeth and tongue helpers (hidden behind its helper mask and
    deleted by the bake) as a mesh of their own, where every target on the body has put them, with the body's
    skin weights (deform bones only; a vertex with none rides the head bone). A tusk is added in front of these
    teeth, never in place of them. Rebuilt on every call; returns its report, or None without the helpers."""
    from . import eyes, look
    from . import body as _body
    name = human.name + TEETH_SUFFIX
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    me0 = human.data
    co = delta.mixed_coords(human)
    rig = _body.rig_of(human)
    bones = set(rig.data.bones.keys()) if rig is not None else set()
    head = eyes.head_bone(rig)
    gname = {g.index: g.name for g in human.vertex_groups}
    bm = bmesh.new()
    mats, weights, rep = [], [], {}
    for part, group, colour, rough in MOUTH_PARTS:
        g = human.vertex_groups.get(group)
        if g is None:
            continue
        vs = [v.index for v in me0.vertices if any(e.group == g.index and e.weight > 0.5 for e in v.groups)]
        inside = set(vs)
        faces = [p for p in me0.polygons if all(i in inside for i in p.vertices)]
        mat = look.material(f"{human.name}_{part}", srgb=colour, roughness=rough)
        if mat not in mats:
            mats.append(mat)
        vmap = {}
        for i in vs:
            vmap[i] = bm.verts.new(Vector(co[i]))
            w = {gname[e.group]: e.weight for e in me0.vertices[i].groups
                 if gname[e.group] in bones and e.weight > 1e-4}
            weights.append(w or {head: 1.0})
        for p in faces:
            f = bm.faces.new([vmap[i] for i in p.vertices])
            f.material_index = mats.index(mat)
            f.smooth = True
        rep[group] = {"verts": len(vs), "faces": len(faces)}
    if not rep:
        bm.free()
        return None
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            lp[uv].uv = (0.5 + lp.vert.co.x * 5, lp.vert.co.z * 5)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    for c in human.users_collection:
        c.objects.link(ob)
    ob.matrix_world = human.matrix_world.copy()
    groups = {}
    for vi, w in enumerate(weights):
        for bone, x in w.items():
            groups.setdefault(bone, []).append((vi, x))
    for bone, rows in groups.items():
        vg = ob.vertex_groups.new(name=bone)
        for vi, x in rows:
            vg.add([vi], x, "REPLACE")
    if rig is not None:
        ob.parent = rig
        ob.matrix_parent_inverse = rig.matrix_world.inverted()
        ob.modifiers.new("Armature", "ARMATURE").object = rig
    else:
        ob.parent = human
        ob.matrix_parent_inverse = human.matrix_world.inverted()
    return {"object": name, "parts": rep, "bones": sorted(groups)}


def _eye_spheres(human):
    co = delta.mixed_coords(human)
    out = {}
    for side in ("l", "r"):
        g = human.vertex_groups.get(f"helper-{side}-eye")
        if g is None:
            return None
        idx = [v.index for v in human.data.vertices if any(e.group == g.index for e in v.groups)]
        pts = co[idx]
        c = pts.mean(axis=0)
        out["L" if c[0] > 0 else "R"] = (c, float(np.linalg.norm(pts - c, axis=1).mean()))
    return out


def _follow_eyes(human, before):
    """Move `<human>_eyes` with MPFB's eye helpers when a target moved or resized the sockets: each eyeball is
    translated and scaled about its centre to the helper's new centre and radius. Returns the largest move (mm)."""
    ob = bpy.data.objects.get(human.name + "_eyes")
    if ob is None or before is None:
        return None
    after = _eye_spheres(human)
    me = ob.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    worst = 0.0
    for side in ("L", "R"):
        (c0, r0), (c1, r1) = before[side], after[side]
        sel = (co[:, 0] > 0) if side == "L" else (co[:, 0] <= 0)
        co[sel] = c1 + (co[sel] - c0) * (r1 / max(r0, 1e-9))
        worst = max(worst, float(np.linalg.norm(c1 - c0)) * 1000, abs(r1 - r0) * 1000)
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    return round(worst, 3)


def head_intersections(human, faces=None):
    """{region: faces} of the head's skin (above the lip line - 9 cm) crossing other head faces that share no
    vertex with them, on the body as its keys now mix, by region (ear, nose, lips, other). {} on a human head."""
    from mathutils.bvhtree import BVHTree
    keys = human.data.shape_keys
    n = len(human.data.vertices)
    b = np.empty(n * 3)
    keys.key_blocks[0].data.foreach_get("co", b)
    b = b.reshape(n, 3)
    co, t = b.copy(), np.empty(n * 3)
    for kb in keys.key_blocks[1:]:
        if kb.mute or not kb.value:
            continue
        kb.data.foreach_get("co", t)
        co += (t.reshape(n, 3) - b) * kb.value
    co = co[:BODY_VERTS]
    faces = delta.body_faces(human) if faces is None else faces
    f = measure.face_features()
    slit = float(co[f["mouth"], 2].mean())
    head = faces[np.all(co[faces, 2] > slit - 0.09, axis=1)]
    tree = BVHTree.FromPolygons([Vector(c) for c in co], [tuple(int(i) for i in q) for q in head])
    ear, nose = _magnitude("ear-scale-incr") > 0.05, _magnitude("nose-volume-incr") > 0.05
    lips = np.zeros(BODY_VERTS, bool)
    lips[f["lips"]] = True
    lips[f["mouth"]] = True
    out = {}
    for i, j in tree.overlap(tree):
        if i < j and not (set(head[i]) & set(head[j])):
            v = head[i]
            r = "ear" if ear[v].any() else "nose" if nose[v].any() else "lips" if lips[v].any() else "other"
            out[r] = out.get(r, 0) + 1
    return out


# ------------------------------------------------------------------ apply

def _set_shape(human, shape, weight):
    if human.data.shape_keys:
        for kb in human.data.shape_keys.key_blocks:
            if kb.name.startswith(KEY_PREFIX + "head-") and kb.name[len(KEY_PREFIX + "head-"):] in sheet.FACE_SHAPES:
                kb.value = 0.0
    if not shape:
        return None
    (fname, path), = _target_files(f"head-{shape}")
    kb = _key(human, fname, path)
    kb.value = float(weight)
    return kb.name


def apply(human, head_spec):
    """Put a species head on an unbaked MPFB body. `head_spec`: {"shape": FACE_SHAPES name or None,
    "shape_weight": float, "features": {name: weight in [-1, 1] | definition}}. Returns a report: the shape key,
    per feature its weight, target keys, displacement key and size, and its parts; `unknown` lists names skipped;
    `objects` the parts object."""
    human = _obj(human)
    problem = delta.check_topology(human)
    if problem:
        raise ValueError(problem)
    if human.data.shape_keys is None:
        human.shape_key_add(name="Basis", from_mix=False)
    spec = dict(head_spec or {})
    report = {"shape": None, "features": {}, "unknown": [], "keys": [], "objects": []}
    feats = {}
    for name, v in (spec.get("features") or {}).items():
        d, w = resolve(name, v)
        if d is None:
            report["unknown"].append(name)
        else:
            feats[name] = (d, float(np.clip(w, -1.0, 1.0)))
    eyes_before = _eye_spheres(human)
    report["shape"] = _set_shape(human, spec.get("shape"), spec.get("shape_weight", 0.5))
    if report["shape"]:
        report["keys"].append(report["shape"])

    # 1. MPFB targets: every hfs: key this spec owns, summed over features; the rest of ours go to 0
    owned = {}
    for name, (d, w) in feats.items():
        rows, skipped = [], []
        table = d.get("targets") or {}
        if w < 0:
            table = d.get("neg_targets") or {}
            if not d.get("neg_targets"):
                for stem, gain in (d.get("targets") or {}).items():
                    opp = _opposite(stem)
                    if opp:
                        table[opp] = gain
                    else:
                        skipped.append(stem)
        for stem, gain in table.items():
            for fname, path in _target_files(stem):
                kname = KEY_PREFIX + fname
                owned[kname] = (owned.get(kname, (0.0, path))[0] + abs(w) * float(gain), path)
                if w:
                    rows.append(kname)
        report["features"][name] = {"weight": round(w, 3), "targets": rows}
        if skipped:
            report["features"][name]["no_opposite"] = skipped
    for kb in human.data.shape_keys.key_blocks:
        if kb.name.startswith(KEY_PREFIX) and kb.name not in owned and kb.name != report["shape"]:
            kb.value = 0.0
    for kname, (v, path) in owned.items():
        kb = human.data.shape_keys.key_blocks.get(kname)
        if kb is None and v <= 0:
            continue
        kb = kb or _key(human, kname[len(KEY_PREFIX):], path)
        kb.value = float(min(v, 1.0))
        if v > 0:
            report["keys"].append(kname)
    human.data.update()
    report["eyes_moved_mm"] = _follow_eyes(human, eyes_before)

    # 2. displacements, on the surface the targets now shape (hfd: keys are not in mixed_coords, so an old one
    # of ours does not bend the normals it is recomputed on)
    co = delta.mixed_coords(human)
    faces = delta.body_faces(human)
    nrm = delta.vertex_normals(co, faces)
    F = frame(human, co, nrm, faces)
    report["head"] = {"size_m": round(F.size, 4), "scale": round(F.scale, 3)}
    kb_all = human.data.shape_keys.key_blocks
    for kb in [k for k in kb_all if k.name.startswith(DELTA_PREFIX)]:
        if kb.name[len(DELTA_PREFIX):] not in feats:
            human.shape_key_remove(kb)
    disp_all = np.zeros((BODY_VERTS, 3))
    from . import muscle
    for name, (d, w) in feats.items():
        kname = DELTA_PREFIX + name
        entries = _listify(d.get("displace"))
        kb = human.data.shape_keys.key_blocks.get(kname)
        if not entries or not w:
            if kb is not None:
                human.shape_key_remove(kb)
            continue
        disp = sum(_displacement(F, dp, w) for dp in entries)
        n = len(human.data.vertices)
        kb = kb or human.shape_key_add(name=kname, from_mix=False)
        basis = human.data.shape_keys.key_blocks[0]
        b = np.empty(n * 3)
        basis.data.foreach_get("co", b)
        b = b.reshape(n, 3)
        b[:BODY_VERTS] += disp
        kb.data.foreach_set("co", b.ravel())
        kb.relative_key = basis
        kb.slider_min = 0.0
        kb.value = 1.0
        h = np.einsum("ij,ij->i", disp, nrm)
        report["features"][name]["displace"] = {
            "key": kname, "max_mm": round(float(np.linalg.norm(disp, axis=1).max()) * 1000, 2),
            "spike_um": int(round(float(np.abs(muscle.spikes(h, faces)).max()) * 1e6))}
        report["keys"].append(kname)
        disp_all += disp

    # 3. parts, on the surface as it is drawn (targets and displacements)
    parts = [(name, at, w) for name, (d, w) in feats.items() if w > 0 for at in _listify(d.get("attach"))]
    F2 = F
    if parts:
        surf = co.copy()
        surf[:BODY_VERTS] += disp_all
        F2 = frame(human, surf, delta.vertex_normals(surf, faces), faces)
    built = _build_parts(human, F2, parts)
    if built:
        for name, rows in built.pop("parts").items():
            report["features"][name]["parts"] = rows
        report["parts"] = built
        report["objects"].append(built["object"])
    # 4. the check that catches a feature pushing skin through skin (a lip through a lip, an ear fold through
    # the helix) before a build does: the head's faces that cross other head faces not beside them. A human head
    # has none.
    report["intersections"] = head_intersections(human, faces)
    if report["intersections"]:
        report.setdefault("warnings", []).append(
            f"head skin crosses itself after these features: {report['intersections']} faces by region - lower "
            "the weight or amount of the feature over that region (a lip through a lip shows in the game)")

    # 5. the teeth and tongue, where the targets put the mouth (displacements move the skin, not them)
    report["mouth"] = mouth(human)
    if report["mouth"]:
        report["objects"].append(report["mouth"]["object"])
    human.data.update()
    bpy.context.view_layer.update()
    return report
