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
    muzzle        a snout (one table): the face carried forward along the jaw's axis and gathered into a tube -
                  `length`, `width`, `bridge`, `pad`, `pad_tilt`, `lip`, `eye_set_back`, `cheek`, `smooth`. It
                  carries the mouth, the teeth and the tongue with it and leaves the eyes in their sockets; what
                  it does to the skin is measured (`surface_strain`). See "the muzzle" below.
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
bone, so a warp that moves bones and skin carries them. `humanform.jaw` goes on after it, because a muzzle moves
the lip line the jaw's weights split at.
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
    # A snout (see "the muzzle" below): numbers, not a creature. These are a dog's - a 55 mm snout on the
    # reference head, narrowed to 0.62 of the face it grows from, a low dorsum, a big nose pad tilted down, a
    # lip line running a third of the way back, the eyes 12 mm behind the stop. MPFB's nose is flattened into
    # the snout first (it would otherwise ride out on the end of it as a human nose).
    "muzzle": {"targets": {"nose-scale-depth-decr": 0.55, "nose-point-down": 0.3, "nose-nostrils-angle-up": 0.3},
               "muzzle": {"length": 0.052, "width": 0.58, "bridge": 0.005, "pad": 0.018, "pad_tilt": 40.0,
                          "lip": 0.30, "eye_set_back": 0.015, "cheek": 0.7, "smooth": 6}},
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
DEF_KEYS = {"preset", "weight", "targets", "neg_targets", "displace", "attach", "muzzle", "notes"}
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
    m = d.get("muzzle")
    if m is not None:
        w = f"{where}.muzzle"
        if not isinstance(m, dict):
            out.append(f"{w} must be a table of {', '.join(sorted(MUZZLE_KEYS))}")
        else:
            out += [f"{w}: unknown key {k!r} - it takes {', '.join(sorted(MUZZLE_KEYS))}" for k in set(m) - MUZZLE_KEYS]
            for k, v in m.items():
                if k not in MUZZLE_RANGE:
                    continue
                lo, hi = MUZZLE_RANGE[k]
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                    out.append(f"{w}.{k} = {v!r}: a number in {lo}..{hi}"
                               + (" (metres on the reference head)" if k in ("length", "bridge", "pad",
                                                                             "eye_set_back") else ""))
            if float(m.get("length", MUZZLE["length"])) > 0.075 and float(m.get("cheek", MUZZLE["cheek"])) < 0.5:
                out.append(f"{w}: a snout over 75 mm with cheek under 0.5 pinches the skin where it meets the "
                           "face - raise cheek (how broadly the cheeks fair into it) or shorten it")
    return out


def validate(head_spec):
    """The problems with a species `head` block, each saying what to write instead; [] when it is fine.
    A feature name that is neither a preset nor a definition is listed here too (apply itself only reports it)."""
    out = []
    if head_spec is None:
        return out
    if not isinstance(head_spec, dict):
        return [f"head must be a table, not {type(head_spec).__name__}"]
    extra = sorted(set(head_spec) - {"shape", "shape_weight", "features", "eyes"})
    if extra:
        out.append(f"head: unknown key(s) {extra} - it takes shape, shape_weight, features and eyes")
    if head_spec.get("eyes") is not None:
        from . import eye_layout                  # how many eyes and where: its own module, its own checks
        out += eye_layout.validate(head_spec["eyes"])
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


# ------------------------------------------------------------------ the muzzle

# A snout is the one form a displacement cannot make: it is not a bump on the face but the whole front of the
# face carried forward along the jaw's axis, with the mouth, the teeth and the tongue riding in it and the eyes
# left where they were. So it is a fourth part of a definition, `muzzle`, beside targets / displace / attach -
# a field over the head, not a region of it. No creature is named here: a canine muzzle is the preset `muzzle`,
# a table of numbers, and `[body.species] head.features` may give its own.
#
#   length        how far the tip travels along the jaw's axis (m on the reference head)
#   width         the snout's breadth as a share of the face it grows from (< 1 narrows it)
#   bridge        the dorsum's rise over the middle of the snout (m; negative dishes it)
#   pad           the nose pad's radius at the tip (m); it stands 0.45 of that out of the snout
#   pad_tilt      degrees the pad's face turns down from the axis (a dog's rhinarium points down-forward)
#   lip           how far the front of the lip line runs out along the snout, as a share of `length`
#   eye_set_back  how far the orbits are drawn back out of the growing face (m): the eyes sit back from it
#   cheek         how broadly the cheeks fair into it, in mouth half-breadths of transition
#   smooth        Laplacian passes over the field (a fair field is what keeps the skin unstretched)
MUZZLE_KEYS = {"length", "width", "bridge", "pad", "pad_tilt", "lip", "eye_set_back", "cheek", "smooth"}
MUZZLE = {"length": 0.0, "width": 1.0, "bridge": 0.0, "pad": 0.0, "pad_tilt": 0.0, "lip": 0.0,
          "eye_set_back": 0.0, "cheek": 0.6, "smooth": 4}
MUZZLE_RANGE = {"length": (0.0, 0.12), "width": (0.25, 1.8), "bridge": (-0.012, 0.025), "pad": (0.0, 0.035),
                "pad_tilt": (-70.0, 70.0), "lip": (0.0, 1.0), "eye_set_back": (0.0, 0.06), "cheek": (0.1, 2.0),
                "smooth": (0, 16)}
# What the skin may take. The texture is baked on MPFB's own UVs, so an edge that grows by a factor shows the
# pores at that factor: 1.45 is the most a face stood at the neck of a snout before the pores read as smeared.
STRETCH_MAX = 1.85
SQUASH_MIN = 0.50
CROWN_FOLLOW = 0.35      # how much of the snout's carry the crown takes: the face grows, the skull mostly not
NECK_FADE = (0.85, 0.85)  # where under the lip line the carry starts to fade and over how deep a band, in head
                          # sizes: a short band pinched the chin (1.7x), a deep one leaves it on the neck
EYE_BLOCK = 0.06          # the radius of the blob `eye_set_back` draws the orbit back by (m, reference head)
LIP_REACH = 0.05          # ... and the reach of the one `lip` carries the front of the mouth out by
EYE_CLEAR = 0.018         # how far in front of the eyes the gathering starts (m, reference head)
# ... and the triangles: the worst one on the head may not lose more than this share of the quality it had
# (4*sqrt(3)*area / sum of squared sides: 1 is equilateral, 0 a sliver).
QUALITY_KEEP = 0.40
EYE_HOLD_MM = 2.0        # how much the eye socket's radius may change: past it the ball stops fitting it


def _muzzle_params(m):
    """One muzzle block over the defaults, every value a float (`smooth` an int)."""
    out = dict(MUZZLE)
    out.update({k: v for k, v in (m or {}).items() if k in MUZZLE_KEYS})
    out = {k: (int(v) if k == "smooth" else float(v)) for k, v in out.items()}
    return out


def _muzzle_frame(F):
    """(origin, axis, up, lateral half breadth): the jaw's axis, from the mandible's angle to the mouth, with the
    midline's up across it. The snout grows along it, so it runs forward and a little down, as a jaw does."""
    jaw = 0.5 * (F.lm["jaw.L"][0] + F.lm["jaw.R"][0])
    mouth = F.lm["mouth"][0]
    ax = np.array([0.0, mouth[1] - jaw[1], mouth[2] - jaw[2]])
    if np.linalg.norm(ax) < 1e-6:
        ax = np.array([0.0, -1.0, 0.0])
    ax = ax / np.linalg.norm(ax)
    up = np.array([0.0, ax[2], -ax[1]])               # in the midplane, across the axis, pointing up
    if up[2] < 0:
        up = -up
    half = 0.5 * abs(float(F.lm["mouth_corner.L"][0][0] - F.lm["mouth_corner.R"][0][0]))
    return mouth, ax, up, max(half, 0.01 * F.scale)


def muzzle_field(F, mp, co=None):
    """The snout's weight per vertex, in [0, 1]: 1 over the snout itself, falling away over the whole depth of
    the head to 0 at the back of it and under the jaw.

    The ramp is as long as the head, on purpose. hm08's face is a fine mesh - 1.6 mm edges round the nostrils -
    and the skin's texture rides its own UVs, so a snout that grew over a short ramp stretched the pores by 7x
    where the ramp crossed the nose (measured). Carrying the whole head forward by a share that falls off over
    its 190 mm spreads that same 55 mm over the coarse skin of the cheeks and the skull, where the worst edge
    grows by about a third. The cranium follows at CROWN_FOLLOW, so the face grows and the skull mostly does
    not - and the eyes, being in it, move with their sockets rather than staying behind them."""
    origin, ax, up, half = _muzzle_frame(F)
    s = F.scale
    co = F.co if co is None else np.asarray(co, float)
    bridge = F.lm["nose_bridge"][0]
    u = (co - bridge) @ ax
    u_back = float((F.lm["occiput"][0] - bridge) @ ax)          # behind the face: negative
    w = _smoothstep((u - u_back) / max(-u_back, 1e-6))            # 0 at the back of the head, 1 at the face
    # the skull follows the face only in part, so the snout grows out of the head rather than the head with it
    v = 1.0 - (1.0 - CROWN_FOLLOW) * _smoothstep((co[:, 2] - F.eye_z) / max(F.crown_z - F.eye_z, 1e-6))
    # and the neck is not the head: under the jaw it fades out, over a band as deep as the head is tall, so the
    # fall lands on the neck's coarse skin instead of pinching the chin
    z0 = F.slit_z - NECK_FADE[0] * F.size
    w = w * v * _smoothstep((co[:, 2] - z0) / (NECK_FADE[1] * F.size))
    it = int(mp["smooth"])
    if it and len(w) >= BODY_VERTS:
        w[:BODY_VERTS] = delta.smooth(w[:BODY_VERTS], F.faces, iterations=it)
    return w


def _muzzle_displacement(F, mp, weight, co_all=None, teeth_mask=None):
    """(n, 3) metres for one muzzle block at this weight: the snout carried along the jaw's axis, its breadth,
    the dorsum's rise, the nose pad and the lip line. `co_all` is every vertex (the helpers included, so the
    eye balls and the mouth's own parts are carried with the skin round them); `teeth_mask` marks the mouth's
    helpers, which ride the lip line rather than taking the field where they happen to sit."""
    origin, ax, up, half = _muzzle_frame(F)
    s = F.scale
    co = F.co if co_all is None else np.asarray(co_all, float)
    w = muzzle_field(F, mp, co) * float(weight)
    disp = np.outer(w * float(mp["length"]) * s, ax)
    # The snout is a tube, not a face carried forward. Carrying the face alone keeps its own shape - the nose
    # still stands out in front of the lips, and it reads as a long face, not a muzzle (rendered, first try).
    # What makes a snout is the gathering: round the jaw's axis the face draws in toward it, most at the tip
    # and fading back over the cheeks (`cheek`), so the nose comes down, the chin comes up, and the lips run
    # out to the end of it.
    axis_o = 0.5 * (F.lm["nose_tip"][0] + F.lm["mouth"][0])
    t = (co - axis_o) @ ax
    rad = (co - axis_o) - np.outer(t, ax)
    # the gathering starts a little in front of the eyes, or it draws the orbit in with it and the
    # ball stops fitting its socket (measured: 1.45 mm of socket radius at width 0.58)
    t_eye = float((F.lm["eye.L"][0] - axis_o) @ ax) + EYE_CLEAR * s
    t_tip = float((F.lm["nose_tip"][0] - axis_o) @ ax) + float(mp["length"]) * s
    taper = _smoothstep((t - t_eye) / max(t_tip - t_eye, 1e-6)) ** (1.0 / max(float(mp["cheek"]), 0.05))
    disp += rad * ((float(mp["width"]) - 1.0) * w * taper)[:, None]
    if mp["bridge"]:
        # the dorsum: a rise over the middle of the snout, above the jaw's axis and near the midline. Every
        # factor is a position, never a vertex normal: a normal flips between neighbours on the ear's folds and
        # round the eye's inner corner, where hm08's edges are half a millimetre, and a 4 mm rise across one of
        # those tore it (4.8x, measured).
        h = (co - origin) @ up
        above = _smoothstep((h - 0.2 * half) / max(0.8 * half, 1e-6))
        near = 1.0 - _smoothstep((np.abs(co[:, 0]) - 0.5 * half) / max(half, 1e-6))
        t = np.clip((w - 0.6) / 0.4, 0.0, 1.0)
        disp += np.outer(4.0 * t * (1.0 - t) * above * near * float(mp["bridge"]) * s, up)
    if mp["pad"]:
        # the nose pad at the tip, its face turned down from the axis by `pad_tilt`
        tip = F.lm["nose_tip"][0] + float(mp["length"]) * s * ax * float(weight)
        r = float(mp["pad"]) * s
        g = FALL["smooth"](np.clip(1.0 - np.linalg.norm(co - tip, axis=1) / max(r, 1e-6), 0.0, 1.0))
        a = math.radians(float(mp["pad_tilt"]))
        d_pad = ax * math.cos(a) - up * math.sin(a)
        disp += np.outer(g * 0.45 * r * float(weight), d_pad)
    if mp["lip"]:
        # The lip line runs out along the muzzle. A human's lips sit 25 mm behind the nose; carried forward as
        # one the face keeps that step and reads as a long face, not a snout (rendered). So the front of the
        # mouth is carried further than the rest, by a share of the length, falling off with distance from the
        # middle of the lip line - the corners stay where they are, which is what makes the long lip line a
        # muzzle has. Both lips of a place move together, so the mouth stays shut.
        out_ = float(mp["lip"]) * float(mp["length"]) * s * float(weight)
        c = F.lm["mouth"][0]
        g = _smoothstep(np.clip(1.0 - np.linalg.norm(co - c, axis=1) / max(LIP_REACH * s, 1e-6), 0.0, 1.0))
        disp += np.outer(w * g * out_, ax)
    if mp["eye_set_back"]:
        # the eyes sit back from the snout: the face grows forward as one (that is what keeps the skin whole),
        # so the orbits are then drawn back out of it by their own soft blob, and the balls follow their sockets
        for side in ("L", "R"):
            c = F.lm[f"eye.{side}"][0]
            g = _smoothstep(np.clip(1.0 - np.linalg.norm(co - c, axis=1) / max(EYE_BLOCK * s, 1e-6), 0.0, 1.0))
            disp -= np.outer(g * float(mp["eye_set_back"]) * s * float(weight), ax)
    if teeth_mask is not None and teeth_mask.any():
        # the teeth and the tongue are rigid: they ride the lip line, or the field would shear them
        slit = np.asarray(measure.face_features()["mouth"], int)
        disp[teeth_mask] = disp[slit].mean(axis=0)
    return disp, w


def _eyes_with_sockets(human, co, disp, eye_mask):
    """Carry `<human>_eyes` with the sockets a muzzle moved: each ball is translated by its own eye helper's
    mean displacement. Reports how far each socket went and how far it deformed doing it (`in_socket_mm`: the
    spread of its helper's displacement, which is what the ball cannot follow)."""
    if eye_mask is None or not eye_mask.any():
        return None
    out = {"socket_moved_mm": 0.0, "in_socket_mm": 0.0, "socket_radius_mm": 0.0}
    ob = bpy.data.objects.get(human.name + "_eyes")
    eco = None
    if ob is not None:
        n = len(ob.data.vertices)
        eco = np.empty(n * 3)
        ob.data.vertices.foreach_get("co", eco)
        eco = eco.reshape(n, 3)
    for sgn in (1.0, -1.0):
        idx = np.flatnonzero(eye_mask & (np.sign(co[:, 0]) == sgn))
        if not len(idx):
            continue
        d = disp[idx]
        mean = d.mean(axis=0)
        out["socket_moved_mm"] = max(out["socket_moved_mm"], round(float(np.linalg.norm(mean)) * 1000, 2))
        out["in_socket_mm"] = max(out["in_socket_mm"],
                                  round(float(np.linalg.norm(d - mean, axis=1).max()) * 1000, 2))
        # what the ball cannot follow at all: how much wider or narrower its socket became
        p0 = co[idx]
        r0 = float(np.linalg.norm(p0 - p0.mean(axis=0), axis=1).mean())
        p1 = p0 + d
        r1 = float(np.linalg.norm(p1 - p1.mean(axis=0), axis=1).mean())
        out["socket_radius_mm"] = max(out["socket_radius_mm"], round(abs(r1 - r0) * 1000, 2))
        if eco is not None:
            sel = (eco[:, 0] > 0) if sgn > 0 else (eco[:, 0] <= 0)
            eco[sel] += mean
    if eco is not None:
        ob.data.vertices.foreach_set("co", eco.ravel())
        ob.data.update()
    return out


def _helper_mask(human, n, groups):
    """A bool mask over every vertex: the ones MPFB's named helper groups hold (weight over a half)."""
    m = np.zeros(n, bool)
    idx = {human.vertex_groups[g].index for g in groups if g in human.vertex_groups}
    if not idx:
        return m
    for v in human.data.vertices:
        if any(e.group in idx and e.weight > 0.5 for e in v.groups):
            m[v.index] = True
    return m


def _quads_edges(faces):
    f = np.asarray(faces, int)
    return np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 3]], f[:, [3, 0]]])


def _quality(co, faces):
    """Per triangle of each quad, 4*sqrt(3)*area / sum of squared sides (1 equilateral, 0 a sliver)."""
    f = np.asarray(faces, int)
    tris = np.concatenate([f[:, [0, 1, 2]], f[:, [0, 2, 3]]])
    a, b, c = co[tris[:, 0]], co[tris[:, 1]], co[tris[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    ss = (np.sum((b - a) ** 2, axis=1) + np.sum((c - b) ** 2, axis=1) + np.sum((a - c) ** 2, axis=1))
    return 4.0 * math.sqrt(3.0) * area / np.maximum(ss, 1e-18)


MIN_EDGE = 0.001         # edges shorter than this (m on the reference head) are not measured: see `surface_strain`


def surface_strain(before, after, faces, moved=None, scale=1.0, side=None, min_edge=None):
    """What a reshaping did to the skin, over the faces it touched: how far its edges grew or shrank (the texture
    rides MPFB's own UVs, so an edge that grows by a factor shows the pores stretched by it) and what became of
    the triangles. `moved` marks the vertices that moved. Returns the report, `fail` set when it is past the
    limits (STRETCH_MAX, SQUASH_MIN, QUALITY_KEEP).

    Edges under MIN_EDGE are left out, and so are the triangles that have one. hm08 puts sub-millimetre edges
    where surfaces turn into the body - the eye's inner corner, the nostril's rim, the ear's folds - and a
    tenth of a millimetre of difference across one of those is a ratio of 3 while showing nothing at all: the
    texel they carry is smaller than a pixel at arm's length. The count of them is reported (`tiny`).

    `side` (+1 / -1 / 0 per vertex) marks the two sides of a seam that is meant to come apart - the lips when
    the jaw opens. An edge that crosses it, and a quad that has both sides in it, are left out and reported
    apart (`seam_edges`, `seam_max`): they are the mouth opening, not a tear. Skin wholly on one side of the
    line - the cheek's web, the throat, the chin - is measured as usual."""
    before, after = np.asarray(before, float), np.asarray(after, float)
    f = np.asarray(faces, int)
    if moved is None:
        moved = np.linalg.norm(after - before, axis=1) > 1e-9
    touched = moved[f].any(axis=1)
    if not touched.any():
        return {"edges": 0}
    f = f[touched]
    e = _quads_edges(f)
    L0 = np.linalg.norm(before[e[:, 0]] - before[e[:, 1]], axis=1)
    L1 = np.linalg.norm(after[e[:, 0]] - after[e[:, 1]], axis=1)
    small = (MIN_EDGE if min_edge is None else min_edge) * scale
    ok = L0 > small
    n = len(f)
    seam = np.zeros(len(e), bool)
    quad_seam = np.zeros(n, bool)
    if side is not None:
        side = np.asarray(side, int)
        seam = (side[e[:, 0]] * side[e[:, 1]]) < 0
        s4 = side[f]
        quad_seam = (s4 > 0).any(axis=1) & (s4 < 0).any(axis=1)
        ok = ok & ~seam
    if not ok.any():
        return {"edges": 0, "tiny": int(len(L0))}
    ratio = L1[ok] / L0[ok]
    shortest = L0.reshape(4, n).min(axis=0)           # each quad's shortest side
    big = (shortest > small) & ~quad_seam
    q0, q1 = _quality(before, f[big]), _quality(after, f[big])
    keep = q1 / np.maximum(q0, 1e-6)
    rep = {"edges": int(ok.sum()), "tiny": int((~ok).sum()), "faces": int(big.sum()),
           "stretch_max": round(float(ratio.max()), 3), "stretch_p99": round(float(np.percentile(ratio, 99)), 3),
           "squash_min": round(float(ratio.min()), 3),
           "quality_min": round(float(q1.min()), 3), "quality_keep_min": round(float(keep.min()), 3)}
    if seam.any():
        sm = seam & (L0 > small)
        rep["seam_edges"] = int(seam.sum())
        if sm.any():
            rep["seam_max"] = round(float((L1[sm] / L0[sm]).max()), 2)
    bad = []
    if rep["stretch_max"] > STRETCH_MAX:
        bad.append(f"the skin stretches {rep['stretch_max']:.2f}x at its worst edge (limit {STRETCH_MAX}) - the "
                   "pores stretch with it: lower length, or start the shape further back (eye_set_back) and "
                   "raise smooth")
    if rep["squash_min"] < SQUASH_MIN:
        bad.append(f"the skin pinches to {rep['squash_min']:.2f}x at its worst edge (limit {SQUASH_MIN}) - raise "
                   "width or cheek, or lower length")
    if rep["quality_keep_min"] < QUALITY_KEEP:
        bad.append(f"a triangle keeps only {rep['quality_keep_min']:.2f} of the shape it had (limit "
                   f"{QUALITY_KEEP}) - the mesh is tearing there: raise smooth or cheek")
    if bad:
        rep["fail"] = "; ".join(bad)
    return rep


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
MOUTH_MATERIALS = {"teeth": "_teeth", "tongue": "_tongue", "seal": "_mouth"}     # material name endings
# A closed mouth shows no teeth. MPFB's closed lips do not seal: the upper lip's edge and the lower lip stand 0.3-2.8
# mm apart along a crack that runs back into a mouth cavity much roomier than a real one, and its teeth helpers bite
# edge to edge right at the crack. So every ray through the crack found enamel: a pale dashed line at the slit and the
# corners of every build since the teeth went on every body, which Godot's subsurface blur spread into bands on a
# dark skin (species-1 trials, the drow and the cyclops). Moving the teeth cannot fix it on its own - seen from above
# at 3/4, a ray through the crack reaches the far side's premolars wherever they are. What a real closed mouth has
# is lips that meet, and behind them darkness: so the mouth gets a seal, a strip of dark membrane standing just
# behind the lip line across the crack, inside the lips' flesh above and below it (`mouth_seal`), which is the dark
# lip line a close-up shows; and the teeth are kept a clearance behind it. Sizes are fractions of the mouth's breadth
# (the lip line's corner to corner), so they hold for any head.
SEAL = (0.035, 0.09, 0.62)   # the seal: its depth behind the lip line, its half height, its half width (x breadth)
SEAL_GROW = 1.5              # ... its half height grown by this while a ray still reaches a tooth, up to 3 times
SEAL_COLOUR = (0.26, 0.12, 0.11)     # the lips' inner skin in their own shadow (sRGB): black read as a drawn line
TEETH_BACK = 0.03            # a tooth at least this far (x breadth) behind the seal and the skin in front of it
MOUTH_VIEWS = ((0, 0), (35, 0), (-35, 0), (60, 0), (-60, 0), (0, 12), (35, 12), (-35, 12), (0, -8))
# (yaw, pitch) in degrees of the cameras the closed-mouth check looks from: front, 3/4 and near profile either side,
# from above (lookdev's face camera sits at eye height) and from a little below
MOUTH_CAM = 12.0             # camera distance in mouth breadths (~0.55 m on a person: lookdev's face close-up)


def _tris_of(faces):
    """Triangles of a list of polygons (index tuples), fanned."""
    out = []
    for p in faces:
        p = tuple(int(i) for i in p)
        for k in range(1, len(p) - 1):
            out.append((p[0], p[k], p[k + 1]))
    return out


def mouth_views(skin_co, skin_faces, parts, slit, views=MOUTH_VIEWS):
    """The closed-mouth check: cast a fine grid of rays at the mouth from each camera in `views` ((yaw, pitch)
    degrees; the face looks down -Y) and count, per part, the rays whose first hit is that part, not the skin.
    `parts` is {name: (co, faces)}, `slit` the lip line's points (N, 3). The grid is finer than a close-up's pixels
    (0.25% of the mouth's breadth vertically), so a hairline crack that a render shows as a dashed line is caught.
    Returns {"views": {"yaw/pitch": {part: rays}}, part: total, "rays": cast, "breadth_m": mouth breadth}."""
    from mathutils.bvhtree import BVHTree
    skin_co = np.asarray(skin_co, float)
    verts = [Vector(v) for v in skin_co]
    tris = _tris_of(skin_faces)
    label = [None] * len(tris)
    for name, (co, faces) in parts.items():
        base = len(verts)
        verts += [Vector(v) for v in np.asarray(co, float)]
        t = [(a + base, b + base, c + base) for a, b, c in _tris_of(faces)]
        tris += t
        label += [name] * len(t)
    tree = BVHTree.FromPolygons(verts, tris)
    slit = np.asarray(slit, float)
    b = float(slit[:, 0].max() - slit[:, 0].min())
    c = Vector(slit.mean(axis=0))
    xs = np.linspace(-0.75 * b, 0.75 * b, 181)
    zs = np.linspace(-0.12 * b, 0.12 * b, 97)
    out = {"views": {}, "rays": 0, "breadth_m": round(b, 4)}
    for name in parts:
        out[name] = 0
    for yaw, pitch in views:
        a, p = math.radians(yaw), math.radians(pitch)
        cam = c + Vector((math.sin(a) * math.cos(p), -math.cos(a) * math.cos(p), math.sin(p))) * (MOUTH_CAM * b)
        row = {name: 0 for name in parts}
        for z in zs:
            for x in xs:
                d = Vector((c.x + x, c.y, c.z + z)) - cam
                hit = tree.ray_cast(cam, d.normalized(), 3 * MOUTH_CAM * b)
                out["rays"] += 1
                if hit[2] is not None and label[hit[2]] is not None:
                    row[label[hit[2]]] += 1
        out["views"][f"{yaw}/{pitch}"] = row
        for name, n in row.items():
            out[name] += n
    return out


def _slit_z(slit):
    """z of the lip line as a function of x (the corners held beyond the ends)."""
    s = np.asarray(slit, float)
    o = np.argsort(s[:, 0])
    return lambda x: np.interp(x, s[o, 0], s[o, 2])


def _slit_y(slit):
    s = np.asarray(slit, float)
    o = np.argsort(s[:, 0])
    return lambda x: np.interp(x, s[o, 0], s[o, 1])


def mouth_seal(skin_co, skin_faces, slit, half_height=None, cols=41, rows=9):
    """The seal of a closed mouth: a grid of `cols` x `rows` points spanning the lip line's crack, SEAL[0] behind
    the skin in front of it (a front ray's first hit, or the lip line where that ray went into the crack), from the
    corners' outside to the middle. Returns (co (rows*cols, 3), quads, report); the report's `exposed` counts the
    points away from the crack with no skin in front of them (0, or the seal pokes out of the face)."""
    from mathutils.bvhtree import BVHTree
    slit = np.asarray(slit, float)
    b = float(slit[:, 0].max() - slit[:, 0].min())
    zf, yf = _slit_z(slit), _slit_y(slit)
    depth, h = SEAL[0] * b, (half_height if half_height is not None else SEAL[1]) * b
    tree = BVHTree.FromPolygons([Vector(v) for v in np.asarray(skin_co, float)], _tris_of(skin_faces))
    y0 = float(slit[:, 1].min()) - 0.5 * b
    pts = []
    for t in np.linspace(-1.0, 1.0, rows):
        for x in np.linspace(-SEAL[2] * b, SEAL[2] * b, cols):
            z = float(zf(x)) + t * h
            yl = float(yf(x))
            hit = tree.ray_cast(Vector((x, y0, z)), Vector((0.0, 1.0, 0.0)), 1.0)
            surf = yl if hit[0] is None or hit[0].y > yl + 0.2 * b else max(float(hit[0].y), yl)
            pts.append((x, surf + depth, z))
    co = np.array(pts)
    quads = [(r * cols + c, r * cols + c + 1, (r + 1) * cols + c + 1, (r + 1) * cols + c)
             for r in range(rows - 1) for c in range(cols - 1)]
    exposed = 0
    for k, v in enumerate(co):
        if abs(np.linspace(-1.0, 1.0, rows)[k // cols]) < 0.5:
            continue                                 # the rows at the crack look out through it: that is the line
        if tree.ray_cast(Vector(v), Vector((0.0, -1.0, 0.0)), 0.5 * b)[0] is None:
            exposed += 1
    return co, quads, {"half_height_mm": round(h * 1000, 2), "depth_mm": round(depth * 1000, 2), "exposed": exposed}


def fit_mouth(skin_co, skin_faces, slit, teeth, tongue=None):
    """A closed mouth: its seal (`mouth_seal`), and the teeth and tongue moved straight back until every tooth is
    TEETH_BACK behind the seal and behind the skin in front of it; the seal is made taller (SEAL_GROW) while a
    `mouth_views` ray still reaches a tooth. `teeth`, `tongue` are (co, faces). Returns (teeth_co, tongue_co,
    (seal_co, seal_faces), report)."""
    from mathutils.bvhtree import BVHTree
    skin_co = np.asarray(skin_co, float)
    slit = np.asarray(slit, float)
    b = float(slit[:, 0].max() - slit[:, 0].min())
    T0 = np.asarray(teeth[0], float)
    G0 = np.asarray(tongue[0], float) if tongue is not None else np.zeros((0, 3))
    skin_tree = BVHTree.FromPolygons([Vector(v) for v in skin_co], _tris_of(skin_faces))
    hh = SEAL[1]
    for rnd in range(4):
        sco, sfaces, srep = mouth_seal(skin_co, skin_faces, slit, half_height=hh)
        seal_tree = BVHTree.FromPolygons([Vector(v) for v in sco], _tris_of(sfaces))
        back = 0.0
        for v in T0:
            for tree in (skin_tree, seal_tree):
                hit = tree.ray_cast(Vector(v), Vector((0.0, -1.0, 0.0)), 0.5 * b)
                if hit[0] is not None:
                    back = max(back, TEETH_BACK * b - float(v[1] - hit[0].y))
                # a tooth in front of the seal: the ray back from it meets the seal
                hit = tree.ray_cast(Vector(v), Vector((0.0, 1.0, 0.0)), 0.5 * b) if tree is seal_tree else (None,)
                if hit[0] is not None:
                    back = max(back, float(hit[0].y - v[1]) + TEETH_BACK * b)
        shift = np.array([0.0, back, 0.0])
        T = T0 + shift
        G = G0 + shift if len(G0) else G0
        parts = {"teeth": (T, teeth[1]), "seal": (sco, sfaces)}
        if len(G):
            parts["tongue"] = (G, tongue[1])
        seen = mouth_views(skin_co, skin_faces, parts, slit)
        if not seen["teeth"]:
            break
        hh *= SEAL_GROW
    rep = dict(srep, breadth_m=round(b, 4), back_mm=round(back * 1000, 2), rounds=rnd + 1, teeth_rays=seen["teeth"],
               tongue_rays=seen.get("tongue", 0), rays=seen["rays"])
    return T, G, (sco, sfaces), rep


def _drawn(ob):
    """The body's vertices as drawn: every shape key at its value, hfd: displacements included."""
    from . import eye_layout
    return eye_layout._full(ob)


def closed_mouth(ob):
    """The closed-mouth check on a body (`mouth_views` from every MOUTH_VIEWS camera): the unbaked MPFB body and its
    `<human>_teeth` object, or a baked mesh whose teeth, tongue and seal are joined in (MOUTH_MATERIALS). Rest pose. Returns the report with `fail` set when any ray reaches a tooth; None when there are no
    teeth or no lip line to look at."""
    ob = _obj(ob)
    feats = measure.face_features()
    me = ob.data
    if len(me.vertices) < feats["n_body"]:
        return None
    teeth_ob = bpy.data.objects.get(ob.name + TEETH_SUFFIX)
    if teeth_ob is not None:
        co = _drawn(ob)[:BODY_VERTS]
        skin_faces = [tuple(f) for f in delta.body_faces(ob)]
        tm = teeth_ob.data
        tco = np.array([v.co[:] for v in tm.vertices], float)
        # the teeth object is parented with its own world matrix: bring it into the body's space
        M = np.array(ob.matrix_world.inverted() @ teeth_ob.matrix_world)
        tco = tco @ M[:3, :3].T + M[:3, 3]
        names = [m.name if m else "" for m in tm.materials]
        parts = {}
        for key, suffix in MOUTH_MATERIALS.items():
            fs = [tuple(p.vertices) for p in tm.polygons if names[p.material_index].endswith(suffix)]
            if fs:
                parts[key] = (tco, fs)
    else:
        co = np.array([v.co[:] for v in me.vertices], float)
        names = [m.name if m else "" for m in me.materials]
        by = {k: [] for k in ("skin", *MOUTH_MATERIALS)}
        for p in me.polygons:
            n = names[p.material_index] if p.material_index < len(names) else ""
            key = next((k for k, suffix in MOUTH_MATERIALS.items() if n.endswith(suffix)), None)
            if key:
                by[key].append(tuple(p.vertices))
            elif all(i < BODY_VERTS for i in p.vertices):
                by["skin"].append(tuple(p.vertices))
        skin_faces = by["skin"]
        parts = {k: (co, by[k]) for k in MOUTH_MATERIALS if by[k]}
    if "teeth" not in parts:
        return None
    packed = {}                                      # only the vertices each part uses
    for k, (pco, fs) in parts.items():
        used = sorted({i for f in fs for i in f})
        remap = {j: n for n, j in enumerate(used)}
        packed[k] = (pco[used], [tuple(remap[i] for i in f) for f in fs])
    rep = mouth_views(co[:BODY_VERTS], skin_faces, packed, co[feats["mouth"]])
    if rep["teeth"]:
        worst = max(rep["views"].items(), key=lambda kv: kv[1].get("teeth", 0))
        rep["fail"] = (f"a closed mouth shows its teeth: {rep['teeth']} of {rep['rays']} rays at the lips reach a tooth "
                       f"(most from the {worst[0]} yaw/pitch camera) - rebuild the mouth (humanform.features.mouth "
                       "sets the teeth behind the lips), or lower the head feature that parted them")
    return rep


def mouth(human):
    """Teeth and tongue: `<human>_teeth`, MPFB's own teeth and tongue helpers (hidden behind its helper mask and
    deleted by the bake) as a mesh of their own, where every target on the body has put them, with the body's
    skin weights (deform bones only; a vertex with none rides the head bone), and the closed mouth's seal (`fit_mouth`:
    a dark membrane across the lip crack, with the lips' weights, and the teeth kept behind it). A tusk is added in
    front of these teeth, never in place of them. Rebuilt on every call; returns its report, or None without the
    helpers. The report's `closed` is the closed-mouth check (`mouth_views`), with `fail` when a tooth shows."""
    from mathutils.kdtree import KDTree
    from . import eyes, look
    from . import body as _body
    name = human.name + TEETH_SUFFIX
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    me0 = human.data
    # the body as it is drawn, displacements included: a muzzle carries the teeth and the tongue forward with the
    # lip line (`_muzzle_displacement`), so reading them from the targets alone would leave them inside the head
    co = _drawn(human)
    rig = _body.rig_of(human)
    bones = set(rig.data.bones.keys()) if rig is not None else set()
    head = eyes.head_bone(rig)
    gname = {g.index: g.name for g in human.vertex_groups}

    def deform_weights(i):
        w = {gname[e.group]: e.weight for e in me0.vertices[i].groups if gname[e.group] in bones and e.weight > 1e-4}
        return w or {head: 1.0}
    rows = {}                                       # part -> (vertex indices, faces), MPFB's helpers
    rep = {}
    for part, group, _colour, _rough in MOUTH_PARTS:
        g = human.vertex_groups.get(group)
        if g is None:
            continue
        vs = [v.index for v in me0.vertices if any(e.group == g.index and e.weight > 0.5 for e in v.groups)]
        inside = set(vs)
        faces = [tuple(p.vertices) for p in me0.polygons if all(i in inside for i in p.vertices)]
        old_vs, old_fs = rows.get(part, ([], []))
        rows[part] = (old_vs + vs, old_fs + faces)
        rep[group] = {"verts": len(vs), "faces": len(faces)}
    if "teeth" not in rows:
        return None

    def packed(part):
        vs, fs = rows[part]
        remap = {j: n for n, j in enumerate(vs)}
        return co[vs], [tuple(remap[i] for i in f) for f in fs]
    # the closed mouth, on the skin as it is drawn (displacements included: a tusk's lip is where it is drawn)
    drawn = _drawn(human)[:BODY_VERTS]
    skin_faces = [tuple(f) for f in delta.body_faces(human)]
    slit = drawn[measure.face_features()["mouth"]]
    t_co, g_co, (s_co, s_faces), fit = fit_mouth(drawn, skin_faces, slit, packed("teeth"),
                                                 packed("tongue") if "tongue" in rows else None)
    placed = {"teeth": t_co, "tongue": g_co}

    bm = bmesh.new()
    mats, weights = [], []
    colours = {part: (colour, rough) for part, _g, colour, rough in MOUTH_PARTS}
    for part in ("teeth", "tongue"):
        if part not in rows:
            continue
        mats.append(look.material(f"{human.name}_{part}", srgb=colours[part][0], roughness=colours[part][1]))
        vs, fs = rows[part]
        new = [bm.verts.new(Vector(p)) for p in placed[part]]
        weights += [deform_weights(i) for i in vs]
        remap = {j: n for n, j in enumerate(vs)}
        for f in fs:
            face = bm.faces.new([new[remap[i]] for i in f])
            face.material_index = len(mats) - 1
            face.smooth = True
    # The seal takes the weights of the nearest skin ABOVE the lip line, so it rides the skull and tucks in
    # behind the upper lip when the jaw opens. Taken from the nearest skin either way, its lower half went with
    # the jaw and the strip was drawn out into a dark curtain across the open mouth (rendered).
    mats.append(look.material(f"{human.name}{MOUTH_MATERIALS['seal']}", srgb=SEAL_COLOUR, roughness=0.7))
    z_lip = _slit_z(slit)(drawn[:BODY_VERTS, 0])
    upper = np.flatnonzero(drawn[:BODY_VERTS, 2] > z_lip)
    kd = KDTree(len(upper))
    for i in upper:
        kd.insert(Vector(drawn[i]), int(i))
    kd.balance()
    new = [bm.verts.new(Vector(p)) for p in s_co]
    weights += [deform_weights(kd.find(Vector(p))[1]) for p in s_co]
    for f in s_faces:
        face = bm.faces.new([new[i] for i in f])
        face.material_index = len(mats) - 1
        face.smooth = True
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
    for bone, rws in groups.items():
        vg = ob.vertex_groups.new(name=bone)
        for vi, x in rws:
            vg.add([vi], x, "REPLACE")
    if rig is not None:
        ob.parent = rig
        ob.matrix_parent_inverse = rig.matrix_world.inverted()
        ob.modifiers.new("Armature", "ARMATURE").object = rig
    else:
        ob.parent = human
        ob.matrix_parent_inverse = human.matrix_world.inverted()
    rep["seal"] = {"verts": len(s_co), "faces": len(s_faces)}
    closed = dict(fit)
    fails = []
    if fit["teeth_rays"]:
        fails.append(f"a closed mouth shows its teeth: {fit['teeth_rays']} of {fit['rays']} rays at the lips reach a "
                     "tooth past the seal - lower the head feature that parts the lips")
    if fit["exposed"]:
        fails.append(f"the mouth's seal stands out of the face at {fit['exposed']} points - the lips are too thin "
                     "for it here (SEAL's depth and half height)")
    if fails:
        closed["fail"] = "; ".join(fails)
    return {"object": name, "parts": rep, "bones": sorted(groups), "closed": closed}


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
    n = len(human.data.vertices)
    teeth_mask = _helper_mask(human, n, ("helper-upper-teeth", "helper-lower-teeth", "helper-tongue"))
    eye_mask = _helper_mask(human, n, ("helper-l-eye", "helper-r-eye"))
    from . import muscle
    for name, (d, w) in feats.items():
        kname = DELTA_PREFIX + name
        entries = _listify(d.get("displace"))
        muz = d.get("muzzle")
        kb = human.data.shape_keys.key_blocks.get(kname)
        if (not entries and not muz) or not w:
            if kb is not None:
                human.shape_key_remove(kb)
            continue
        full = np.zeros((n, 3))
        if entries:
            full[:BODY_VERTS] += sum(_displacement(F, dp, w) for dp in entries)
        if muz:
            mp = _muzzle_params(muz)
            grown, field = _muzzle_displacement(F, mp, w, co_all=co, teeth_mask=teeth_mask)
            full += grown
            after = co[:BODY_VERTS] + full[:BODY_VERTS]
            strain = surface_strain(co[:BODY_VERTS], after, faces, moved=field[:BODY_VERTS] > 1e-4)
            eye_moved = _eyes_with_sockets(human, co, full, eye_mask)
            rep_m = {"params": {k: round(v, 4) if isinstance(v, float) else v for k, v in mp.items()},
                     "grown_mm": round(float(np.linalg.norm(full[:BODY_VERTS], axis=1).max()) * 1000, 1),
                     "field_verts": int((field > 0.5).sum()), "skin": strain,
                     "teeth_moved_mm": round(float(np.linalg.norm(full[teeth_mask], axis=1).max()) * 1000, 1)
                     if teeth_mask.any() else None,
                     "eyes": eye_moved}
            if strain.get("fail"):
                rep_m["fail"] = f"{name}: {strain['fail']}"
            if (eye_moved or {}).get("socket_radius_mm", 0.0) > EYE_HOLD_MM:
                rep_m["fail"] = (rep_m.get("fail", "") + f"; {name}: the eye socket changes size by "
                                 f"{eye_moved['socket_radius_mm']} mm (limit {EYE_HOLD_MM}) - the ball no longer "
                                 "fits it: shorten the muzzle or raise eye_set_back").strip("; ")
            report["features"][name]["muzzle"] = rep_m
            if rep_m.get("fail"):
                report.setdefault("warnings", []).append(rep_m["fail"])
                report["fail"] = "; ".join([report["fail"], rep_m["fail"]] if report.get("fail") else [rep_m["fail"]])
        disp = full[:BODY_VERTS]
        kb = kb or human.shape_key_add(name=kname, from_mix=False)
        basis = human.data.shape_keys.key_blocks[0]
        b = np.empty(n * 3)
        basis.data.foreach_get("co", b)
        b = b.reshape(n, 3)
        b += full
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
