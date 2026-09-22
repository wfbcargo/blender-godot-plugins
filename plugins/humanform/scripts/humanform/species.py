"""Layer 1 of a fantasy species: fit the nearest human, then warp its proportions.

    sp = species.load("dwarf")                      # data/species/dwarf.json (schema humanform-species/1)
    species.ids()                                   # ["human", "dwarf", "elf", ...]; "human" has no file
    species.validate("dwarf", s)                    # problems, with the species' range in the message
    s_pre, info = species.pre_warp(s, sp)           # the human sheet to fit (stature H_pre, BMI and build kept)
    ... pipeline.make(s_pre) fits, rigs and checks that human ...
    rep = species.warp(human, sp, report={}, sex="male", stature=1.32)

A species is data (docs/improvements/08-fantasy-species.md, "Layer 1" and "The spec"). MPFB cannot reach a
dwarf, so the body is a real human first - the one sharing the species body's trunk (a disproportionate
species) or its head size (a proportionate one) - fitted, stored in the library and checked like any other.
Then every bone gets a new rest transform: length along the bone, girth across it, the head a uniform scale
about the neck joint, shoulders and hips spread by their roots, the spine bent by the species' kyphosis and
lordosis. Vertices follow by linear blend skinning with the body's own weights (numpy, `v' = sum w T v`),
applied to the base mesh, every shape key and every other mesh skinned to the rig (eyes, brows, teeth); then
the rig's rest bones are moved to match. No modifier is applied and no Blender operator touches the mesh.

The final factors are solved, not taken from the file: the file's `segments`, `girth` and `widths` are the
starting point and the shape of the change, and each measured joint lands on the fitted human's own fraction
shifted by (species mean - human preset mean), so two dwarves from different briefs still differ.
"""

from __future__ import annotations

import copy
import json
import math
import os
import sys
import time
import zlib

import numpy as np

_pkg = sys.modules[__package__]
SCHEMA = "humanform-species/1"
HUMAN = "human"
# the pre-warp human is a real one: inside ANSUR's plausible adults
STATURE_PRE = (1.40, 2.05)
# heights the measuring levels are warped through, in order up the body (as landmarks.WARP_KEYS)
LEVEL_KEYS = ("ankle_joint", "knee_joint", "crotch", "hip_joint", "shoulder_joint", "chin")
# how far each factor may go: past these a limb folds or a head swallows the neck
LIMITS = {"length": (0.25, 2.5), "head": (0.5, 2.0), "ankle": (0.4, 2.0), "girth_follow": (0.8, 1.25)}
# an individual keeps its own deviation from the human mean, up to this many tolerances (in the species')
INDIVIDUAL = 0.5
# kyphosis density along the spine (0 hip joint, 1 neck base, past 1 the neck): a rounded upper back
KYPHOSIS_PROFILE = ((0.0, 0.1), (0.2, 0.6), (0.35, 1.0), (0.6, 0.8), (1.0, 0.55), (1.4, 0.5))
# the warp skins the body with its weights diffused this many passes over the mesh (see _smooth_weights)
WEIGHT_SMOOTH = 12
ALONG = True              # the shaft mapping (`_along`) on; off is plain affine linear blend skinning
SOFT = 0.10               # the share of a bone's shaft next to its head that keeps its length (see _along)
TOL_REFINE = 0.25          # passes stop once every solved measure is within this share of its tolerance


# ------------------------------------------------------------------ data

def _dir():
    return os.path.join(_pkg.DATA, "species")


def ids():
    """Every species id: "human" (implicit, no file) and one per data/species/<id>.json."""
    d = _dir()
    found = sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json")) if os.path.isdir(d) else []
    return [HUMAN] + [i for i in found if i != HUMAN]


_CACHE = {}


def inline(d):
    """A species given in place of an id - in a brief or a character spec, with no file. Either a whole
    humanform-species/1 preset (it has `ratios` and `heads`), or what humanform.species_design turns into one:
    observables (`species_design.design_from`: stature, heads, a trunk-to-leg ratio ... as a description gives
    them, bare or under "observables") or `{"knobs": {...}, "stature": ...}` (`species_design.design`). Beside
    them, `head`, `skin` and `moves` are its look, `graft`, `legs` (a leg plan: humanform.legs), `foot` (a foot plan:
    humanform.feet; `feet` is already the observable for foot LENGTH) and `tail` (humanform.tail) its body plan, and `anatomy` its declared absences and scales; `id` and `label` are kept
    (an unnamed species is "custom")."""
    d = copy.deepcopy(d)
    if d.get("schema") == SCHEMA or ("ratios" in d and "heads" in d):
        d.setdefault("schema", SCHEMA)
        d.setdefault("id", "custom")
        return d
    try:
        from . import species_design as sd
    except ImportError:
        raise ValueError("an inline species needs `ratios` and `heads` (a whole humanform-species/1 preset): "
                         "humanform.species_design, which designs one from observables or knobs, is not installed")
    sid, label = d.pop("id", None) or "custom", d.pop("label", None)
    look = {k: d.pop(k) for k in ("head", "skin", "moves", "graft", "legs", "foot", "tail", "fur") if k in d} or None
    anatomy = d.pop("anatomy", None)
    if "knobs" in d:
        knobs = dict(d.pop("knobs"))
        stature = d.pop("stature", knobs.pop("stature", None))
        out = sd.design(id=sid, label=label, stature=stature, look=look, anatomy=anatomy, **knobs)
    else:
        obs = dict(d.pop("observables", d))
        # a knob beside the observables (character-pipeline's [body.species] takes both at the top level, and
        # species-design.md: "anything no observable expresses is given as a knob") goes to solve() as a knob;
        # a name that is both (hunch_deg, sway_deg) stays an observable
        knobs = {n: obs.pop(n) for n in list(obs) if n in sd.KNOBS and n not in sd.OBSERVABLES}
        out = sd.design_from(obs, id=sid, look=look, anatomy=anatomy, **knobs)
    if label:
        out["label"] = label
    return out


def load(sid):
    """The species dict for an id, or for an inline dict (`inline`). "human" and None are None: no warp."""
    if isinstance(sid, dict):
        return sid if sid.get("schema") == SCHEMA and "ratios" in sid else inline(sid)
    if sid in (None, HUMAN):
        return None
    path = os.path.join(_dir(), f"{sid}.json")
    if not isinstance(sid, str) or not os.path.isfile(path):
        raise ValueError(f"unknown species {sid!r}: one of {ids()}")
    mt = os.path.getmtime(path)
    hit = _CACHE.get(path)
    if hit is None or hit[0] != mt:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if doc.get("schema") != SCHEMA:
            raise ValueError(f"{path}: schema must be {SCHEMA}")
        _CACHE[path] = hit = (mt, doc)
    return copy.deepcopy(hit[1])


def _t(entry, sex):
    """[target, tol] (or a bare number / range) from a presets.json-style entry."""
    if entry is None:
        return None
    if isinstance(entry, (list, tuple, int, float)):
        return entry
    return entry.get("any") if entry.get("any") is not None else entry.get(sex)


def sexed(block, sex):
    """A block keyed by sex ({"female": {...}, "male": {...}}), or one for both."""
    block = block or {}
    if sex in block and isinstance(block[sex], dict):
        return block[sex]
    if "any" in block and isinstance(block["any"], dict):
        return block["any"]
    return {k: v for k, v in block.items() if not isinstance(v, dict)}


def _real():
    return _pkg.presets_file()["presets"]


def _mean(ratios, key, sex):
    v = _t(ratios.get(key), sex)
    return None if v is None else float(v[0])


def heads(sp, sex):
    return float(_t(sp["heads"], sex)[0])


def _chin(sp, sex):
    c = _mean(sp["ratios"], "chin", sex)
    return c if c is not None else 1.0 - 1.0 / heads(sp, sex)


def preset(sp, doc=None):
    """The species as a humancheck preset, in presets.json's format: its `ratios`, `heads` and `derived`, the
    human-only feature ranges it overrides (`features`), and the measuring `levels` per sex - where humancheck
    takes its waist, hip and chest sections on this body (the human fractions mapped through the species'
    joint heights)."""
    sp = load(sp)
    doc = doc or _pkg.presets_file()
    real = doc["presets"]["realistic"]
    feats = doc["features"]
    h = sp["heads"]
    p = {"label": sp.get("label", sp["id"]), "species": sp["id"],
         "heads": h if isinstance(h, dict) else {"any": list(h)},
         "ratios": sp["ratios"], "derived": sp.get("derived") or real["derived"], "bmi": sp.get("bmi"),
         "bmi_build": (sp.get("pre_warp") or {}).get("bmi"),
         "features": copy.deepcopy(sp.get("features") or {}), "levels": {}}
    for sex in ("female", "male"):
        src, dst = [0.0], [0.0]
        for k in LEVEL_KEYS:
            a = _mean(real["ratios"], k, sex)
            b = _chin(sp, sex) if k == "chin" else _mean(sp["ratios"], k, sex)
            if a is None or b is None or a <= src[-1] or b <= dst[-1]:
                continue
            src.append(a)
            dst.append(b)
        src.append(1.0)
        dst.append(1.0)
        p["levels"][sex] = [src, dst]
    if "hip_above_crotch" not in p["features"]:
        # a pelvis the warp scaled: the human range, scaled by how far the species' hip sits above its crotch
        rows = []
        for sex in ("female", "male"):
            hs, cs = _mean(sp["ratios"], "hip_joint", sex), _mean(sp["ratios"], "crotch", sex)
            hr, cr = _mean(real["ratios"], "hip_joint", sex), _mean(real["ratios"], "crotch", sex)
            if None not in (hs, cs, hr, cr) and hr > cr:
                rows.append((hs - cs) / (hr - cr))
        if rows:
            k = float(np.clip(np.mean(rows), 0.4, 2.5))
            lo, hi = feats["hip_above_crotch"]["range"]
            p["features"]["hip_above_crotch"] = {"range": [round(lo * min(k, 1.0), 4), round(hi * max(k, 1.0), 4)],
                                                 "note": f"the human range scaled by the {sp['id']} pelvis ({k:.2f})"}
    return p


def levels(sp, sex):
    """(src, dst) control points for measure.measurements(levels=...): a human height fraction -> this body's."""
    sp = load(sp)
    return None if sp is None else preset(sp)["levels"][sex]


# ------------------------------------------------------------------ the brief

def prewarp_stature(sp, sex, H):
    """(H_pre, extra): the human stature to fit, and the uniform scale the clamp to STATURE_PRE took off it
    (every start factor is multiplied by `extra`). `pre_warp.stature_factor` when the file gives one, else from
    its basis: "trunk" (shoulder - hip joint, species over human) or "head" (human heads over species heads)."""
    pw = sp.get("pre_warp") or {}
    f = _t(pw.get("stature_factor"), sex)
    if isinstance(f, (list, tuple)):
        f = f[0]
    if f is None:
        real = _real()["realistic"]
        basis = pw.get("basis") or ("head" if sp.get("proportionate") else "trunk")
        if basis == "head":
            f = float(_t(real["heads"], sex)[0]) / heads(sp, sex)
        else:
            f = ((_mean(sp["ratios"], "shoulder_joint", sex) - _mean(sp["ratios"], "hip_joint", sex))
                 / (_mean(real["ratios"], "shoulder_joint", sex) - _mean(real["ratios"], "hip_joint", sex)))
    raw = float(H) * float(f)
    lo = max(float(pw.get("min_stature") or STATURE_PRE[0]), STATURE_PRE[0])
    hi = min(float(pw.get("max_stature") or STATURE_PRE[1]), STATURE_PRE[1])
    H_pre = float(np.clip(raw, lo, hi))
    return H_pre, raw / H_pre


def default_stature(sp, sex):
    rng = _t(sp.get("stature"), sex)
    return round((rng[0] + rng[1]) / 2, 3)


def validate(species, s):
    """Problems with a brief for this species; empty when it can be built. "human" has none of its own."""
    try:
        sp = load(species)
    except (ValueError, TypeError, KeyError) as exc:
        return [str(exc)]
    if sp is None:
        return []
    p = []
    sid = sp.get("id", "custom")
    for key in ("stature", "heads", "ratios", "segments"):
        if key not in sp:
            p.append(f"species {sid}: its file has no {key!r} (see docs/improvements/08-fantasy-species.md)")
    if p:
        return p
    sex = s.get("sex")
    if sex not in ("female", "male"):
        return p
    from . import sheet
    age = s.get("age")
    if age is not None and age < sheet.AGE_RANGE[0]:
        p.append(f"a {sid} body is built from an adult human: age {age:g} is below {sheet.AGE_RANGE[0]:g}")
    rng = _t(sp["stature"], sex)
    st = s.get("stature")
    if st is not None and rng and not rng[0] <= st <= rng[1]:
        p.append(f"stature {st} m is outside the {sid} range {rng[0]:.2f}-{rng[1]:.2f} m for a {sex}")
    H = st if st is not None else default_stature(sp, sex)
    bmi = s.get("bmi")
    if s.get("weight") is not None and H:
        bmi = s["weight"] / H ** 2
    br = sp.get("bmi")
    if bmi is not None and br and not br[0] <= bmi <= br[1]:
        p.append(f"BMI {bmi:.1f} is outside the {sid} range {br[0]}-{br[1]}")
    H_pre, _ = prewarp_stature(sp, sex, H)
    lo, hi = sheet.STATURE["adult"]
    if not lo <= H_pre <= hi:
        p.append(f"the {sid}'s pre-warp human would be {H_pre:.2f} m, outside {lo}-{hi} m")
    return p


def draw_skin(sp, s):
    """A screen colour from the species' palette, by the brief's seed (else its name): a random point between
    two neighbouring palette tones."""
    sk = sp.get("skin") or {}
    if sk.get("tone") is not None:             # an inline species' own tone
        return [round(float(c), 4) for c in sk["tone"]]
    pal = sk.get("palette") or []
    if not pal:
        return None
    seed = s.get("seed")
    if seed is None:
        seed = zlib.crc32(str(s.get("name", "")).encode("utf-8"))
    rng = np.random.default_rng(int(seed) + 7919)
    if len(pal) == 1:
        return [round(float(c), 4) for c in pal[0]]
    i = int(rng.integers(0, len(pal) - 1))
    t = float(rng.random())
    a, b = np.array(pal[i], float), np.array(pal[i + 1], float)
    return [round(float(c), 4) for c in a + t * (b - a)]


def pre_warp(s, sp):
    """(sheet, info): the human sheet the warp starts from - the brief with stature H_pre, BMI kept (a weight
    becomes the BMI it implies at the species stature), ANSUR measurements dropped (they would be a human's),
    and a skin drawn from the species palette when the brief gives none."""
    sp = load(sp)
    sex = s["sex"]
    H = float(s["stature"]) if s.get("stature") is not None else default_stature(sp, sex)
    H_pre, extra = prewarp_stature(sp, sex, H)
    out = copy.deepcopy(s)
    out.pop("species", None)
    out["stature"] = round(H_pre, 4)
    notes = []
    # the brief's BMI (or its weight at the species stature) is the species body's: it is mapped from the
    # species' BMI range onto the pre-warp human's (`pre_warp.bmi`); a build word's BMI is a human's, only held
    # inside that range
    pw = sp.get("pre_warp") or {}
    rng_pre, rng_sp = pw.get("bmi"), sp.get("bmi")
    bmi = s.get("bmi")
    if s.get("weight") is not None:
        bmi = s["weight"] / H ** 2
        out["weight"] = None
    if bmi is not None:
        if rng_pre and rng_sp and rng_sp[1] > rng_sp[0]:
            t = float(np.clip((bmi - rng_sp[0]) / (rng_sp[1] - rng_sp[0]), 0.0, 1.0))
            pre_bmi = rng_pre[0] + t * (rng_pre[1] - rng_pre[0])
        else:
            pre_bmi = bmi
        out["bmi"] = round(float(pre_bmi), 2)
        notes.append(f"BMI {bmi:.1f} (the {sp['id']}'s) fitted as BMI {out['bmi']} on the pre-warp human")
    elif rng_pre and isinstance(s.get("build"), str):
        from . import sheet
        b = (sheet.BUILDS.get(s["build"]) or {}).get("bmi")
        if b is None:
            # a build word with no BMI ("average") fits ANSUR's mean for the sex, which is the species' build only
            # when it lies in its pre-warp range: a scrawny goblin's average brief came out an average man's
            from . import species_design as sd
            b = sd.LIMB_BAND[sex]["bmi"]
        if not rng_pre[0] <= b <= rng_pre[1]:
            out["bmi"] = round(float(np.clip(b, *rng_pre)), 2)
            notes.append(f"build {s['build']!r} (BMI {b}) held at BMI {out['bmi']}, inside the pre-warp range "
                         f"{rng_pre[0]}-{rng_pre[1]}")
    if out.get("measurements"):
        notes.append("measurements dropped: they are ANSUR (human) measures, and the warp moves them")
        out["measurements"] = {}
    drawn = None
    if out.get("skin") is None:
        drawn = draw_skin(sp, s)
        if drawn is not None:
            out["skin"] = drawn
    info = {"species": sp["id"], "stature": round(H, 4), "stature_pre": round(H_pre, 4),
            "clamp_scale": round(extra, 4), "skin_drawn": drawn, "notes": notes}
    if abs(extra - 1.0) > 1e-4:
        notes.append(f"pre-warp human clamped to {H_pre:.2f} m (from {H_pre * extra:.2f} m): every start factor "
                     f"is scaled {extra:.3f}")
    return out, info


def fur_block(sp):
    """The species' `fur` block (humanform.fur's coverage map as data), or None - a human has none, and a
    species with none is drawn with bare skin exactly as it was before fur existed."""
    sp = load(sp)
    if sp is None:
        return None
    return sp.get("fur") or None


def skin_block(sp):
    """The species' `skin` block as humanform.skin's `species_skin` (regions off, pattern, subsurface tint), or
    None for a human - whose skin then takes exactly the path it always did."""
    sp = load(sp)
    if sp is None:
        return None
    sk = {k: v for k, v in (sp.get("skin") or {}).items() if k not in ("palette", "tone")}
    return sk or None


def apply_features(human, sp):
    """Head features (pointed ears, brow ridge ...) as shape deltas on the human, before the warp - through
    humanform.features when it is installed; skipped, and said so, when it is not."""
    head = (sp or {}).get("head") or {}
    try:
        from . import features
    except ImportError:
        return {"skipped": "humanform.features is not installed", "requested": head.get("features")}
    try:
        return features.apply(human, head) or {}
    except Exception as exc:           # a feature pass must not cost the body
        return {"error": f"{type(exc).__name__}: {exc}"}


# ------------------------------------------------------------------ the warp

# The roles a rig's body profile names (rig-anything's `roles`), read from it when rig_analysis is importable.
# Without it: the names humanform's own rig carries (scaffold.RENAME), as eyes.HEAD_BONE does. Limbs are never
# named: a leg is a sided chain off the pelvis, an arm a sided chain off the spine above it.
DEFAULT_ROLES = {"root": "root", "pelvis": "spine", "chest": "spine.003", "neck": ["spine.004"], "head": "spine.005"}


def _rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], float)


def profile_roles(rig):
    roles = dict(DEFAULT_ROLES)
    if rig.get("body_profile"):
        try:
            from rig_analysis import bodymap
        except ImportError:
            bodymap = None
        if bodymap is not None:
            roles.update((bodymap.load_profile(rig) or {}).get("roles") or {})
    if isinstance(roles.get("neck"), str):
        roles["neck"] = [roles["neck"]]
    return roles


class _Rig:
    """The rest skeleton as arrays (parents before children), and what each bone is to the body: its role, found
    from the profile's roles and the skeleton's structure, never from a limb's name."""

    def __init__(self, rig):
        from . import body as _body
        bones = list(rig.data.bones)
        depth = {}

        def d(b):
            if b.name not in depth:
                depth[b.name] = 0 if b.parent is None else d(b.parent) + 1
            return depth[b.name]

        bones.sort(key=d)
        self.names = [b.name for b in bones]
        self.ix = {n: i for i, n in enumerate(self.names)}
        self.parent = np.array([self.ix[b.parent.name] if b.parent else -1 for b in bones])
        self.head = np.array([tuple(b.head_local) for b in bones], float)
        self.tail = np.array([tuple(b.tail_local) for b in bones], float)
        self.R = np.array([[list(r) for r in b.matrix_local.to_3x3()] for b in bones], float)
        self.length = np.array([b.length for b in bones], float)
        self.deform = np.array([b.use_deform for b in bones])
        self.connect = {b.name: b.use_connect for b in bones}
        self.children = [[self.ix[c.name] for c in b.children] for b in bones]
        kids = {n: [] for n in self.names}
        for b in bones:
            if b.parent is not None:
                kids[b.parent.name].append(b.name)
        size = {}

        def count(n):
            if n not in size:
                size[n] = 1 + sum(count(c) for c in kids[n])
            return size[n]

        def chain(n, k):
            out = [n]
            while len(out) < k and kids[out[-1]]:
                out.append(max(kids[out[-1]], key=count))
            return out

        def below(n):
            out = []
            for c in kids[n]:
                out += [c] + below(c)
            return out

        roles = profile_roles(rig)
        missing = [roles[k] for k in ("pelvis", "chest", "head") if roles.get(k) not in self.ix]
        missing += [n for n in roles.get("neck") or [] if n not in self.ix]
        if missing:
            raise ValueError(f"{rig.name}: its body profile names bones it does not have: {missing}")
        self.roles = roles
        self.root = self.ix.get(roles.get("root"))
        spine = [roles["chest"]]
        while spine[-1] != roles["pelvis"]:
            p = rig.data.bones[spine[-1]].parent
            if p is None:
                raise ValueError(f"{rig.name}: the chest {roles['chest']} is not under the pelvis {roles['pelvis']}")
            spine.append(p.name)
        self.spine = spine[::-1]                          # pelvis first, chest last
        self.neck = list(roles.get("neck") or [])
        self.headbone = roles["head"]
        self.legs, self.arms = {}, {}
        for c in kids[self.spine[0]]:
            side = _body._side_of(c)
            if side:
                self.legs[side] = chain(c, 4)             # hip, knee, ankle, toe
        for sb in self.spine[1:]:
            for c in kids[sb]:
                side = _body._side_of(c)
                if side and side not in self.arms:
                    ch = chain(c, 4)
                    self.arms[side] = ch if len(ch) == 4 else [None] + ch    # clavicle, shoulder, elbow, wrist
        self.kind = {}
        for n in self.spine:
            self.kind[n] = "pelvis" if n == self.spine[0] else "spine"
        for n in self.neck:
            self.kind[n] = "neck"
        self.kind[self.headbone] = "head"
        # a jaw (humanform.jaw, tagged the way rig-anything's maw tags one) hangs off the head and scales with
        # it: left unknown it would keep a human's scale while the skin round it took the head's, and a
        # troll's mouth would tear along the lip line
        for c in below(self.headbone):
            if rig.data.bones[c].get("maw_role"):
                self.kind[c] = "head"
        for ch in self.legs.values():
            for n, k in zip(ch, ("thigh", "shin", "foot", "toe")):
                self.kind[n] = k
        for ch in self.arms.values():
            for n, k in zip(ch, ("clavicle", "upper", "fore", "hand")):
                if n:
                    self.kind[n] = k
            if ch[3]:
                for dg in below(ch[3]):
                    self.kind[dg] = "digit"

    def mean_head_z(self, H, limb, i):
        vals = [H[self.ix[ch[i]], 2] for ch in limb.values() if len(ch) > i and ch[i]]
        return float(np.mean(vals)) if vals else None


def _skinned(rig):
    import bpy
    return [o for o in bpy.data.objects if o.type == "MESH"
            and any(m.type == "ARMATURE" and m.object is rig for m in o.modifiers)]


def _weights(ob, rigd, k=8):
    """(idx, w): each vertex's deform-bone influences, normalised, padded to k. A vertex with none rides a
    pseudo-bone (index len(bones)) that only takes the floor shift."""
    n_b = len(rigd.names)
    gi = {g.index: rigd.ix.get(g.name) for g in ob.vertex_groups}
    gi = {g: b for g, b in gi.items() if b is not None and rigd.deform[b]}
    n = len(ob.data.vertices)
    idx = np.full((n, k), n_b, int)
    w = np.zeros((n, k))
    for v in ob.data.vertices:
        row = sorted(((gi[e.group], e.weight) for e in v.groups if e.group in gi and e.weight > 1e-6),
                     key=lambda r: -r[1])[:k]
        for j, (b, ww) in enumerate(row):
            idx[v.index, j] = b
            w[v.index, j] = ww
    tot = w.sum(axis=1)
    none = tot <= 1e-9
    w[~none] /= tot[~none, None]
    w[none, 0] = 1.0
    return idx, w


def _smooth_weights(idx, w, edges, nb, passes, k=8):
    """The skin weights diffused over the mesh's edges `passes` times, renormalised, top k again. MPFB's weights
    change from one bone to the next over a few centimetres; where the two bones are scaled differently (a 0.6
    upper arm on a 1.0 forearm) the skin folds across that seam into a step. Spread over a wider band, the two
    transforms - which agree at the joint - blend without one. Used for the warp only: the rig keeps its weights."""
    n = len(idx)
    if not passes or not len(edges):
        return idx, w
    W = np.zeros((n, nb + 1))
    np.add.at(W, (np.repeat(np.arange(n), idx.shape[1]), idx.ravel()), w.ravel())
    tgt = np.concatenate([edges[:, 0], edges[:, 1]])
    src = np.concatenate([edges[:, 1], edges[:, 0]])
    order = np.argsort(tgt, kind="stable")
    tgt, src = tgt[order], src[order]
    rows, starts, deg = np.unique(tgt, return_index=True, return_counts=True)
    for _ in range(passes):
        acc = np.add.reduceat(W[src], starts, axis=0)          # each vertex's neighbours, summed
        W[rows] = 0.5 * W[rows] + 0.5 * acc / deg[:, None]
    top = np.argsort(-W, axis=1)[:, :k]
    wt = np.take_along_axis(W, top, axis=1)
    wt[wt < 1e-4] = 0.0
    tot = wt.sum(axis=1)
    ok = tot > 1e-9
    wt[ok] /= tot[ok, None]
    top[~ok, 0], wt[~ok, 0] = nb, 1.0
    return top, wt


class _Mesh:
    """One skinned mesh's original coordinates (armature space): the vertices, every shape key, the weights."""

    def __init__(self, ob, rig, rigd, smooth=0):
        mw = np.array(rig.matrix_world.inverted() @ ob.matrix_world, float)
        self.ob, self.A = ob, mw
        self.Ainv = np.linalg.inv(mw)
        me = ob.data
        n = len(me.vertices)
        self.keys = []
        if me.shape_keys is not None:
            for kb in me.shape_keys.key_blocks:
                co = np.empty(n * 3, np.float32)
                kb.data.foreach_get("co", co)
                self.keys.append((kb.name, self._arm(co.reshape(-1, 3))))
        co = np.empty(n * 3, np.float32)
        me.vertices.foreach_get("co", co)
        self.base = self._arm(co.reshape(-1, 3))
        self.idx, self.w = _weights(ob, rigd)
        if smooth:
            e = np.empty(len(me.edges) * 2, np.int64)
            me.edges.foreach_get("vertices", e)
            self.idx, self.w = _smooth_weights(self.idx, self.w, e.reshape(-1, 2), len(rigd.names), smooth)

    def _arm(self, co):
        return co.astype(np.float64) @ self.A[:3, :3].T + self.A[:3, 3]

    def _local(self, co):
        return co @ self.Ainv[:3, :3].T + self.Ainv[:3, 3]

    def mixed(self, keys):
        """The shape as MPFB shows it (basis plus every key at its value) for these key coordinates."""
        if not keys:
            return None
        kbs = self.ob.data.shape_keys.key_blocks
        by = dict(keys)
        basis = keys[0][1]
        co = basis.copy()
        for name, k in keys[1:]:
            kb = kbs[name]
            if kb.mute or kb.value == 0.0:
                continue
            co += kb.value * (k - by.get(kb.relative_key.name, basis))
        return co


def _along(s, L, l, k, m):
    """How far along a bone a point at `s` (its distance along the old bone from the head) lands. Above the head
    it scales by `k`, the parent's scale along this bone's axis, and past the tail by `m`, the child's: the flesh
    over a joint weighted to one side of it (a buttock over the hip, a heel under the ankle) goes the way the part
    it sits on goes, so both sides of every joint agree. Over the first and last SOFT of the shaft the slope eases
    (C1) from k into the shaft's and from it into m, and the tail lands exactly where the bone's scale puts it
    (`l * L`)."""
    a = SOFT * L
    c = (l * L - 0.5 * a * (k + m)) / np.maximum(L - a, 1e-9)
    ga = 0.5 * a * (k + c)
    gb = ga + c * (L - 2 * a)
    u = s - (L - a)
    return np.where(s < 0.0, k * s,
                    np.where(s < a, k * s + (c - k) * s * s / (2.0 * a),
                             np.where(s < L - a, ga + c * (s - a),
                                      np.where(s < L, gb + c * u + (m - c) * u * u / (2.0 * a),
                                               l * L + m * (s - L)))))


def _lbs(co, idx, w, T):
    """sum_i w_i T_i(v) for every vertex: T_i affine (A_i v + t_i), with the length scale moved from the whole
    bone onto its shaft (`_along`)."""
    A, t, _, _, _, (h0, y0, L, l, k, mm, Y) = T
    Aw = np.einsum("nk,nkij->nij", w, A[idx])
    tw = np.einsum("nk,nki->ni", w, t[idx])
    out = np.einsum("nij,nj->ni", Aw, co) + tw
    if not ALONG:
        return out
    s = np.einsum("nkj,nkj->nk", co[:, None, :] - h0[idx], y0[idx])
    corr = _along(s, L[idx], l[idx], k[idx], mm[idx]) - l[idx] * s
    return out + np.einsum("nk,nk,nkj->nj", w, corr, Y[idx])


def _clamp_girth(sp, sex, region, extra):
    """The girth factor the clamp's uniform scale `extra` gives a region: by the adult build law on the whole scale
    from the fitted human (species_design.clamp_girth, with the preset's girth_law), else geometric (`extra`, a
    preset without one)."""
    gl = sp.get("girth_law") or {}
    a = (gl.get("exponents") or {}).get(region)
    s = (gl.get("scale") or {}).get(sex)
    if a is None or abs(extra - 1.0) < 1e-9:
        return extra

    def law(x):
        return x ** float(a) if x < 1.0 else x
    if s is None:                                 # a preset before girth_law.scale: the law on the clamp alone
        return law(extra)
    return law(float(s) * extra) / law(float(s))


class _Warp:
    """What the solve varies (x) and what the preset fixes, turned into per-bone transforms by role."""

    SOLVED = ("tibia", "femur", "spine", "neck", "head", "ankle")

    def __init__(self, rigd, sp, extra, sex):
        self.r = rigd
        seg = sexed(sp.get("segments"), sex)
        self.seg = {k: float(seg.get(k, 1.0)) * extra for k in
                    ("femur", "tibia", "humerus", "forearm", "hand", "foot", "spine", "neck", "head")}
        g = sexed(sp.get("girth"), sex)
        # a pre-warp human clamped to STATURE_PRE is scaled by `extra` after the fit: its girths take the adult
        # build law (species_design.GIRTH_LAW, in the preset's girth_law) when it is shrunk, as design() did
        self.girth = {k: float(g.get(k, 1.0)) * _clamp_girth(sp, sex, k, extra) for k in ("legs", "arms", "neck", "torso")}
        # the ribcage's own depth and breadth and the forearm's girth, on top (1 on a preset without them)
        self.extra_girth = {k: float(g.get(k, 1.0)) for k in ("forearm", "chest_depth", "chest_breadth")}
        # a preset with a girth_law gives the chest a depth that follows the breadth broad shoulders spread it to
        self.chest_follows = bool(sp.get("girth_law"))
        # the limbs' support girth (a big body's): the limbs', not the pelvis's - the buttocks and the hip section
        # keep the trunk's build (a troll's waist over hip fell 1.02 -> 0.86 with it on the pelvis)
        self.support = float((((sp.get("girth_law") or {}).get("support") or {}).get(sex)) or 1.0)
        w = sexed(sp.get("widths"), sex)
        self.widths = {k: float(w.get(k, 1.0)) * extra for k in ("shoulder_width", "hip_width")}
        sc = sp.get("spine") or {}
        self.kyph = math.radians(float(sc.get("kyphosis_deg", 0.0)))
        self.lord = math.radians(float(sc.get("lordosis_deg", 0.0)))
        self.lumbar = float(sc.get("lumbar_share", 0.4))
        self.lean = 0.0            # an extra backward lumbar bend (radians) that keeps a curved body balanced
        # set outside the Newton solve (arms, hands, feet, widths), refined from measurement
        self.fixed = {"humerus": self.seg["humerus"], "forearm": self.seg["forearm"], "hand": self.seg["hand"],
                      "foot": self.seg["foot"], "clavicle": self.widths["shoulder_width"],
                      "pelvis_x": self.widths["hip_width"]}
        self.bend = self._bends()

    def x0(self):
        return np.array([self.seg["tibia"], self.seg["femur"], self.seg["spine"], self.seg["neck"],
                         self.seg["head"], self.seg["foot"]], float)

    def _follow(self, solved, spec):
        return float(np.clip(solved / spec, *LIMITS["girth_follow"])) if spec > 1e-6 else 1.0

    def set_lean(self, lean):
        self.lean = float(lean)
        self.bend = self._bends()

    def _bends(self):
        """{bone: radians about X} for the spine curve. Kyphosis is a smooth forward curve over the whole spine
        above the pelvis and the neck (KYPHOSIS_PROFILE: little in the lumbar spine, most at the upper back,
        some in the neck), so a hunch reads as a rounded back with the head carried forward, not a fold at one
        bone. Lordosis bends the lumbar span (the lower lumbar_share of hip joint to neck base) back, and the
        thoracic forward again so the chest is upright. Each bone takes the curve over the span it covers (to the
        next bone's head). The head bends back by what the chain above the pelvis took, so the gaze stays level
        with the head forward, and each arm bends back at its shoulder joint, so the arms hang as they did."""
        r = self.r
        bend = {n: 0.0 for n in r.names}
        if not (self.kyph or self.lord or self.lean):
            return bend
        z0 = r.mean_head_z(r.head, r.legs, 0) or r.head[r.ix[r.spine[0]], 2]
        z1 = r.head[r.ix[r.neck[0]], 2] if r.neck else r.head[r.ix[r.headbone], 2]
        zh = r.head[r.ix[r.headbone], 2]
        span = max(z1 - z0, 1e-6)
        chain = r.spine[1:]                               # the pelvis carries the legs: it is never bent
        ends = [r.head[r.ix[n], 2] for n in chain] + [z1]
        cut = self.lumbar

        def overlap(a, b, lo, hi):
            return max(0.0, min(b, hi) - max(a, lo))

        segs = [((ends[i] - z0) / span, (ends[i + 1] - z0) / span) for i in range(len(chain))]
        lum = np.array([overlap(a, b, 0.0, cut) for a, b in segs])
        tho = np.array([overlap(a, b, cut, 1.0) for a, b in segs])
        if lum.sum() <= 0 and len(chain):
            lum[0] = 1.0
        if tho.sum() <= 0 and len(chain):
            tho[-1] = 1.0
        lum, tho = lum / lum.sum(), tho / tho.sum()
        # kyphosis over the chain and the neck (s past 1: neck base to head base), by the profile's integral
        necks = [(1.0 + (r.head[r.ix[n], 2] - z1) / span, 1.0 + ((r.head[r.ix[r.neck[i + 1]], 2] if i + 1 < len(r.neck)
                  else zh) - z1) / span) for i, n in enumerate(r.neck)]
        s_pts, w_pts = zip(*KYPHOSIS_PROFILE)

        def mass(a, b):
            xs = np.linspace(a, b, 24)
            return float(np.trapezoid(np.interp(xs, s_pts, w_pts), xs)) if b > a else 0.0

        ky = np.array([mass(a, b) for a, b in segs + necks])
        ky = ky / ky.sum() if ky.sum() > 0 else ky
        for i, n in enumerate(chain):
            bend[n] = self.kyph * ky[i] - self.lord * lum[i] + self.lord * tho[i] - self.lean * lum[i]
        for i, n in enumerate(r.neck):
            bend[n] = self.kyph * ky[len(chain) + i]
        net = sum(bend[n] for n in chain) + sum(bend[n] for n in r.neck)
        bend[r.headbone] = -net
        for side, ch in r.arms.items():
            root = ch[0] or ch[1]
            p = r.parent[r.ix[root]]
            up = 0.0
            while p >= 0:
                up += bend.get(r.names[p], 0.0)
                p = r.parent[p]
            bend[ch[1]] = -up
        return bend

    def scales(self, x):
        """{bone: (sx, sy, sz)} in each bone's own frame (y along it)."""
        l_tib, l_fem, l_sp, l_neck, s_head, f_ank = x
        f = self.fixed
        gl, ga, gn, gt = (self.girth[k] for k in ("legs", "arms", "neck", "torso"))
        # the chest's breadth, beyond its girth: half of what broad shoulders ask over the torso's own girth
        chest_x = float(np.clip(math.sqrt(max(self.widths["shoulder_width"] / max(gt, 1e-3), 1e-3)), 0.8, 1.25))
        chest = self.r.spine[-1]
        # the ribcage: the upper two bones of the spine above the pelvis (the chest and the one under it)
        ribs = set(self.r.spine[max(1, len(self.r.spine) - 2):])
        cd, cb, gf = (self.extra_girth[k] for k in ("chest_depth", "chest_breadth", "forearm"))
        S = {}
        for n in self.r.names:
            k = self.r.kind.get(n)
            if k == "pelvis":
                # the pelvis carries the buttocks and the tops of the thighs: it takes the legs' girth, so a
                # buttock does not overhang a thigh girthed less than the trunk
                gp = gl / self.support
                S[n] = (gp * f["pelvis_x"], l_sp, gp)
            elif k == "spine":
                bx = chest_x if n == chest else 1.0
                dz = chest_x if (n == chest and self.chest_follows) else 1.0
                if n in ribs:
                    bx, dz = bx * cb, dz * cd
                S[n] = (gt * bx, l_sp, gt * dz)
            elif k == "neck":
                S[n] = (gn, l_neck, gn)
            elif k == "head":
                S[n] = (s_head,) * 3
            elif k == "clavicle":
                S[n] = (gt, f["clavicle"], gt)
            elif k == "upper":
                g = ga * self._follow(f["humerus"], self.seg["humerus"])
                S[n] = (g, f["humerus"], g)
            elif k == "fore":
                g = ga * self._follow(f["forearm"], self.seg["forearm"]) * gf
                S[n] = (g, f["forearm"], g)
            elif k in ("hand", "digit"):
                S[n] = (f["hand"],) * 3
            elif k == "thigh":
                g = gl * self._follow(l_fem, self.seg["femur"])
                S[n] = (g, l_fem, g)
            elif k == "shin":
                g = gl * self._follow(l_tib, self.seg["tibia"])
                S[n] = (g, l_tib, g)
            elif k in ("foot", "toe"):
                # length and breadth with the foot, height (the bone's own z, near the world's up) with the ankle
                S[n] = (f["foot"], f["foot"], f_ank)
            else:
                S[n] = (1.0, 1.0, 1.0)
        return S

    def transforms(self, x, shift=0.0):
        """T = (A, t, head, R, S, along): each bone's affine skinning transform (the pseudo-bone last), its new
        rest head and rotation, its scale, and the arrays `_along` needs."""
        r = self.r
        S = self.scales(x)
        n = len(r.names)
        A = np.zeros((n + 1, 3, 3))
        t = np.zeros((n + 1, 3))
        H = np.zeros((n, 3))
        R = np.zeros((n, 3, 3))
        Q = np.zeros((n, 3, 3))
        for i, name in enumerate(r.names):
            p = r.parent[i]
            if p < 0:
                h, q = r.head[i].copy(), np.eye(3)
            else:
                h, q = A[p] @ r.head[i] + t[p], Q[p]
            b = self.bend.get(name, 0.0)
            q = q @ _rx(b) if b else q
            Q[i] = q
            R[i] = q @ r.R[i]
            A[i] = R[i] @ np.diag(S[name]) @ r.R[i].T
            t[i] = h - A[i] @ r.head[i]
            H[i] = h
        A[n] = np.eye(3)
        h0 = np.vstack([r.head, np.zeros((1, 3))])
        y0 = np.vstack([r.R[:, :, 1], np.array([[0.0, 0.0, 1.0]])])
        Ln = np.append(np.maximum(r.length, 1e-6), 1.0)
        # a uniform scale (head, hand) needs no shaft correction: its whole bone scales alike
        uni = [S[nm][0] == S[nm][1] == S[nm][2] for nm in r.names]
        ln = np.array([1.0 if u else S[nm][1] for nm, u in zip(r.names, uni)] + [1.0])
        # above its head a bone's flesh takes its parent's scale along this bone's axis, past its tail its
        # child's (the child whose head is at the tail) - or its own, where there is none or it is not scaled;
        # a uniform scale needs no correction at all
        def along_scale(j, axis):
            return float(np.linalg.norm(np.array(S[r.names[j]]) * (r.R[j].T @ axis)))

        kn, mn = np.ones(n + 1), np.ones(n + 1)
        for i, nm in enumerate(r.names):
            if uni[i]:
                continue
            p = r.parent[i]
            kp = along_scale(p, r.R[i][:, 1]) if p >= 0 and r.kind.get(r.names[p]) else ln[i]
            kids = [j for j in r.children[i] if r.kind.get(r.names[j])]
            if kids:
                c = min(kids, key=lambda j: np.linalg.norm(r.head[j] - r.tail[i]))
                mc = along_scale(c, r.R[i][:, 1])
            else:
                mc = ln[i]
            # the two sides of a joint take one scale between them - the mean of the bones' along the axis - so a
            # vertex weighted half to each lands in one place (a 0.6 upper arm on a 1.0 forearm stepped at the elbow)
            kn[i] = float(np.clip(0.5 * (kp + ln[i]), *LIMITS["head"]))
            mn[i] = float(np.clip(0.5 * (mc + ln[i]), *LIMITS["head"]))
        Y = np.vstack([R[:, :, 1], np.array([[0.0, 0.0, 1.0]])])
        T = [A, t, H, R, S, (h0, y0, Ln, ln, kn, mn, Y)]
        _shift(T, r, shift)
        return tuple(T)


BALANCE_ALLOW = 0.25       # of a foot's length (ankle to ball): how far a curved body's centre may move over its feet


def _com_over_feet(co, feet):
    """How far the body's centre (its vertices' mean, forward -Y) is in front of the middle of its feet."""
    return float(np.mean(feet, axis=0)[1] - co[:, 1].mean())


def _balance(wp, rigd, body, mask, mix0, H0, H):
    """A spine curve moves the chest and head forward (a hunch) or back: balance it with a backward (or forward)
    lumbar bend - as a stooped body leans back from the hips - only as far as it needs: the body's centre no
    more than BALANCE_ALLOW of a foot's length further forward (or back) over its feet than the fitted human's
    is, for its size. A hunch that stays inside that keeps its whole curve. Sets wp's lean; returns it
    (radians)."""
    sub = np.flatnonzero(mask)[::3]

    def feet(Hh, R, S):
        pts = []
        for ch in rigd.legs.values():
            i = rigd.ix[ch[2]]
            pts += [Hh[i], Hh[i] + R[i][:, 1] * rigd.length[i] * S[ch[2]][1]]
        return np.array(pts)

    ident = [rigd.head, rigd.R, {n: (1.0, 1.0, 1.0) for n in rigd.names}]
    base = _com_over_feet(mix0[sub], feet(*ident)) * H / H0
    T0 = wp.transforms(wp.x0())
    fp = feet(T0[2], T0[3], T0[4])
    allow = BALANCE_ALLOW * float(np.mean([np.linalg.norm(fp[2 * i + 1] - fp[2 * i]) for i in range(len(fp) // 2)]))

    def raw(lean):
        wp.set_lean(lean)
        T = wp.transforms(wp.x0())
        return _com_over_feet(_lbs(mix0[sub], body.idx[sub], body.w[sub], T), feet(T[2], T[3], T[4])) - base

    d0 = raw(0.0)
    if abs(d0) <= allow:
        wp.set_lean(0.0)
        return 0.0
    target = allow if d0 > 0 else -allow

    def off(lean):
        return raw(lean) - target

    lo, hi = -0.6, 0.6               # a forward-heavy body leans back: more lean, less forward offset
    f_lo, f_hi = off(lo), off(hi)
    if f_lo * f_hi > 0:
        wp.set_lean(lo if abs(f_lo) < abs(f_hi) else hi)
        return wp.lean
    for _ in range(24):
        mid = (lo + hi) / 2
        f = off(mid)
        if (f > 0) == (f_lo > 0):
            lo, f_lo = mid, f
        else:
            hi = mid
    wp.set_lean((lo + hi) / 2)
    return wp.lean


def _shift(T, r, dz):
    """Move everything but the root - which stays on the floor and carries no skin - up by dz."""
    if not dz:
        return
    A, t, H = T[0], T[1], T[2]
    for i in range(len(r.names)):
        if i != r.root:
            t[i, 2] += dz
            H[i, 2] += dz
    t[len(r.names), 2] += dz


def _body_mask(ob):
    g = ob.vertex_groups.get("body")
    n = len(ob.data.vertices)
    if g is None:
        return np.ones(n, bool)
    keep = np.zeros(n, bool)
    for v in ob.data.vertices:
        for e in v.groups:
            if e.group == g.index and e.weight > 0.5:
                keep[v.index] = True
                break
    return keep if keep.any() else np.ones(n, bool)


def _knee_off_line(r, H):
    """Each knee's distance (mm) off its hip-ankle line."""
    out = {}
    for s, ch in r.legs.items():
        if len(ch) < 3:
            continue
        hp, kn, an = (H[r.ix[b]] for b in ch[:3])
        d = an - hp
        tt = float(np.dot(kn - hp, d) / np.dot(d, d))
        out[s] = round(float(np.linalg.norm(kn - (hp + tt * d))) * 1000, 1)
    return out


MEASURE = {"ankle_joint": "ankle_z", "knee_joint": "knee_z", "hip_joint": "hip_z", "shoulder_joint": "shoulder_z",
           "crotch": "crotch_z", "chin": "chin_z", "upper_arm": "upper_arm", "forearm": "forearm", "hand": "hand",
           "foot": "foot", "thigh": "thigh", "shin": "shin", "shoulder_width": "shoulder_width",
           "hip_width": "hip_width"}


def targets(m0, sp, sex, H, style="realistic"):
    """Absolute targets (metres) for the warped body: each species ratio is the fitted human's own fraction
    shifted by (species mean - human preset mean) - its deviation carried in tolerances and capped at
    INDIVIDUAL of them - times the species stature H."""
    ref = _real().get(style, _real()["realistic"])["ratios"]
    H0 = m0["stature"]
    out = {}
    for key, meas in MEASURE.items():
        spm = _chin(sp, sex) if key == "chin" else _mean(sp["ratios"], key, sex)
        if spm is None or m0.get(meas) is None:
            continue
        tol = (float(_t(sp["ratios"].get(key), sex)[1]) if key in sp["ratios"] else
               float(_t(sp["heads"], sex)[1]) / heads(sp, sex) ** 2)
        rt = _t(ref.get(key), sex)
        own = m0[meas] / H0
        if rt is None:
            frac, dev = spm, 0.0
        else:
            # the individual's deviation from the human mean, in the human's tolerances, carried over in the
            # species' - capped, so what the fit missed on the pre-warp human (MPFB's big head on a short body,
            # a low shoulder) is not carried into the species body as if it were the person
            dev = float(np.clip((own - float(rt[0])) / float(rt[1]), -INDIVIDUAL, INDIVIDUAL))
            frac = spm + dev * tol
        out[key] = {"frac": round(frac, 4), "m": frac * H, "species": spm, "tol": tol, "own_tol": round(dev, 2)}
    return out


def warp(human, sp, report=None, sex=None, stature=None, style="realistic", clamp_scale=1.0, passes=5,
         verbose=False):
    """Warp a fitted, rigged human to the species in place: every skinned mesh, every shape key, the rig's rest
    bones. `stature` is the species body's height (floor to vertex, spine curve included); `clamp_scale` the
    uniform scale pre_warp's clamp took off the human (`info["clamp_scale"]`). Returns `report`, filled in:
    the solved factors, each target and what the mesh measures after the warp."""
    import bpy
    from . import body as _body
    from . import measure

    t0 = time.time()
    report = {} if report is None else report
    sp = load(sp)
    if sp is None:
        report.update({"species": HUMAN, "warped": False})
        return report
    human = _body.obj(human)
    rig = _body.rig_of(human)
    if rig is None:
        raise ValueError(f"{human.name} has no rig: species.warp runs after scaffold.finish")
    sex = sex or "female"
    H = float(stature) if stature is not None else default_stature(sp, sex)
    lv = levels(sp, sex)

    bpy.context.view_layer.update()
    m0 = measure.measurements(human, sex, fast=True, girths=True)
    if verbose:
        print("species setup", round(time.time() - t0, 2), "s")
    tg = targets(m0, sp, sex, H, style)
    rigd = _Rig(rig)
    meshes = [_Mesh(o, rig, rigd, smooth=WEIGHT_SMOOTH if o is human else 0) for o in _skinned(rig)]
    body = next(m for m in meshes if m.ob is human)
    mask = _body_mask(human)
    mix0 = body.mixed(body.keys) if body.keys else body.base.copy()
    # the chin as the profile finds it: the most forward midline vertex at the measured chin height
    chin0 = m0.get("chin_z")
    near = np.flatnonzero(mask & (np.abs(mix0[:, 0]) < 0.006) & (np.abs(mix0[:, 2] - chin0) < 0.008))
    if not len(near):
        near = np.flatnonzero(mask & (np.abs(mix0[:, 0]) < 0.02) & (np.abs(mix0[:, 2] - chin0) < 0.02))
    chin_v = int(near[np.argmin(mix0[near, 1])])
    # the model needs the floor and the top: the soles and the head (far below and above anything the warp moves
    # past them), not the 19k vertices between
    H0 = float(m0["stature"])
    sel = np.flatnonzero(mask & ((mix0[:, 2] < 0.12 * H0) | (mix0[:, 2] > chin0 - 0.02 * H0)))
    knee_before = _knee_off_line(rigd, rigd.head)
    wp = _Warp(rigd, sp, clamp_scale, sex)
    # arms, hands, feet and widths: straight from their targets, refined by measurement below
    for key, fk in (("upper_arm", "humerus"), ("forearm", "forearm"), ("hand", "hand"), ("foot", "foot")):
        if key in tg and m0.get(MEASURE[key]):
            wp.fixed[fk] = tg[key]["m"] / m0[MEASURE[key]]
    clav = [rigd.ix[ch[0]] for ch in rigd.arms.values() if ch[0]]
    clav_x = float(np.mean([abs(rigd.tail[i, 0] - rigd.head[i, 0]) for i in clav])) if clav else 0.15
    if "shoulder_width" in tg and m0.get("shoulder_width") and clav:
        wp.fixed["clavicle"] = 1.0 + (tg["shoulder_width"]["m"] - m0["shoulder_width"] * wp.girth["arms"]) / (2 * clav_x)
    if "hip_width" in tg and m0.get("hip_width"):
        wp.fixed["pelvis_x"] = tg["hip_width"]["m"] / (m0["hip_width"] * wp.girth["legs"] / wp.support)

    lean = _balance(wp, rigd, body, mask, mix0, float(m0["stature"]), H) if (wp.kyph or wp.lord) else 0.0

    joints = {"ankle_joint": (rigd.legs, 2), "knee_joint": (rigd.legs, 1), "hip_joint": (rigd.legs, 0),
              "shoulder_joint": (rigd.arms, 1)}

    def model(x):
        T = wp.transforms(x)
        co = _lbs(mix0[sel], body.idx[sel], body.w[sel], T)
        floor = float(co[:, 2].min())
        z = {k: rigd.mean_head_z(T[2], limb, i) for k, (limb, i) in joints.items()}
        z = {k: v - floor for k, v in z.items() if v is not None}
        z["chin"] = float(_lbs(mix0[chin_v:chin_v + 1], body.idx[chin_v:chin_v + 1], body.w[chin_v:chin_v + 1],
                               T)[0, 2]) - floor
        z["top"] = float(co[:, 2].max()) - floor
        return z, floor

    goal = {k: tg[k]["m"] for k in ("ankle_joint", "knee_joint", "hip_joint", "shoulder_joint", "chin") if k in tg}
    goal["top"] = H
    offset = {k: 0.0 for k in goal}          # model-to-mesh corrections from each measuring pass
    lo = np.array([LIMITS["length"][0]] * 4 + [LIMITS["head"][0], LIMITS["ankle"][0]])
    hi = np.array([LIMITS["length"][1]] * 4 + [LIMITS["head"][1], LIMITS["ankle"][1]])

    def solve(x):
        z0, _ = model(x)
        use = [e for e in goal if e in z0]

        def res(xx):
            z, _ = model(xx)
            return np.array([z[e] - (goal[e] + offset[e]) for e in use])

        for _ in range(12):
            r0 = res(x)
            if np.max(np.abs(r0)) < 2e-4:
                break
            J = np.zeros((len(use), len(x)))
            for j in range(len(x)):
                dx = np.zeros(len(x))
                dx[j] = 1e-3
                J[:, j] = (res(x + dx) - r0) / 1e-3
            x = np.clip(x + np.linalg.lstsq(J, -r0, rcond=None)[0], lo, hi)
        return x

    if verbose:
        print("species meshes read", round(time.time() - t0, 2), "s")
    x = wp.x0()
    history = []
    m = None
    best = None                    # (worst error in tolerances, x, fixed, pass): the pass that is kept
    for p in range(passes):
        x = solve(x)
        _, floor = model(x)
        T = wp.transforms(x, shift=-floor)
        _apply(meshes, body, mask, rigd, rig, T)
        bpy.context.view_layer.update()
        m = measure.measurements(human, sex, fast=True, levels=lv)
        errs = {}
        for key in list(goal) + ["hand", "foot", "shoulder_width", "hip_width"]:
            meas = "stature" if key == "top" else MEASURE[key]
            if (key in tg or key == "top") and m.get(meas) is not None:
                want = H if key == "top" else tg[key]["m"]
                tol = 0.01 if key == "top" else tg[key]["tol"] * H
                errs[key] = (m[meas] - want, tol)
        # the crotch: thighs thickened by the build meet below it when the hips stay narrow (the first halfling
        # and dwarf on the adult build law: 6-8 cm low, the hip joints outside the pelvis). Scored with the rest
        # and, when low, answered by spreading the pelvis rather than holding the hip breadth
        crotch_low = 0.0
        if "crotch" in tg and m.get("crotch_z") is not None:
            errs["crotch"] = (m["crotch_z"] - tg["crotch"]["m"], tg["crotch"]["tol"] * H)
            if errs["crotch"][0] < -0.5 * errs["crotch"][1]:
                crotch_low = -errs["crotch"][0] / H
        history.append({k: round(v[0] / v[1], 3) for k, v in errs.items()})
        score = max((abs(e) / tol for e, tol in errs.values()), default=0.0)
        if best is None or score < best[0]:
            best = (score, x.copy(), dict(wp.fixed), p)
        if verbose:
            print("species pass", p, round(time.time() - t0, 2), "s", history[-1], "x", np.round(x, 3), wp.fixed)
        if all(abs(e) <= TOL_REFINE * tol for e, tol in errs.values()) or p == passes - 1:
            break
        # correct the model by what the mesh says - the chin and the top, which the model reads off one vertex and
        # the rig's bones do not give (the joints are the bones' own heads: an error there is one the solve could
        # not meet, and chasing it winds up) - and the fixed factors by their own ratio
        for key in ("chin", "top"):
            if key in errs:
                offset[key] -= errs[key][0]
        for key, fk in (("hand", "hand"), ("foot", "foot")):
            if key in errs:
                wp.fixed[fk] *= tg[key]["m"] / m[key]
        if "shoulder_width" in errs and clav:
            wp.fixed["clavicle"] -= errs["shoulder_width"][0] / (2 * clav_x)
        if crotch_low:
            wp.fixed["pelvis_x"] *= 1.0 + min(0.15, 2.0 * crotch_low)
        elif "hip_width" in errs:
            wp.fixed["pelvis_x"] *= tg["hip_width"]["m"] / m["hip_width"]

    if best is not None and best[3] != len(history) - 1:
        # a later pass came out worse (the corrections interact): put the best one back
        x, wp.fixed = best[1], best[2]
        _, floor = model(x)
        _apply(meshes, body, mask, rigd, rig, wp.transforms(x, shift=-floor))
        bpy.context.view_layer.update()
        m = measure.measurements(human, sex, fast=True, levels=lv)
    er = eye_ratio(sp, sex)
    eyes_rep = scale_eyes(human, rig, er) if abs(er - 1.0) > 1e-3 else {"ratio": 1.0}
    bpy.context.view_layer.update()
    after = _Rig(rig)
    achieved = {}
    Hm = float(m["stature"])
    for key, row in tg.items():
        v = m.get(MEASURE[key])
        if v is not None:
            v = float(v) / Hm
            achieved[key] = {"target": row["frac"], "value": round(v, 4), "species": round(row["species"], 4),
                             "off_tol": round((v - row["frac"]) / max(row["tol"], 1e-4), 2)}
    hd = (Hm / float(m["head_length"])) if m.get("head_length") else None
    report.update({"build": _build_landed(m0, m, wp, x, rigd)})
    report.update({
        "species": sp["id"], "warped": True, "stature": round(Hm, 4), "stature_target": H,
        "stature_pre": round(float(m0["stature"]), 4),
        "heads": None if hd is None else round(hd, 2), "heads_target": round(heads(sp, sex), 2),
        "factors": {"solved": dict(zip(_Warp.SOLVED, [round(float(v), 4) for v in x])),
                    "fixed": {k: round(float(v), 4) for k, v in wp.fixed.items()},
                    "girth": {k: round(v, 4) for k, v in wp.girth.items()},
                    "start": {k: round(v, 4) for k, v in wp.seg.items()},
                    "bend_deg": {k: round(math.degrees(v), 2) for k, v in wp.bend.items() if v}},
        "balance_lean_deg": round(math.degrees(lean), 2),
        "roles": {"spine": rigd.spine, "neck": rigd.neck, "head": rigd.headbone, "legs": rigd.legs, "arms": rigd.arms},
        "achieved": achieved, "passes": history, "eyes": eyes_rep,
        "knee_off_line_mm": {"before": knee_before, "after": _knee_off_line(after, after.head)},
        "meshes": [mm.ob.name for mm in meshes], "shape_keys": len(body.keys),
        "seconds": round(time.time() - t0, 2)})
    return report


def _build_landed(m0, m, wp, x, rigd):
    """Whether the girth the preset asks for lands on the mesh: each limb's girth over its length before and
    after the warp, their ratio (`landed`) against the bones' own girth-over-length scale (`asked`), and the
    chest's depth and breadth likewise (the ribcage bones' depth and breadth scales)."""
    S = wp.scales(x)
    first = {k: ch for k, ch in (("thigh", rigd.legs), ("shin", rigd.legs), ("upper_arm", rigd.arms),
                                 ("forearm", rigd.arms))}
    idx = {"thigh": 0, "shin": 1, "upper_arm": 1, "forearm": 2}
    out = {}
    for limb, limbs in first.items():
        ch = next(iter(limbs.values()), None)
        key = f"{limb}_girth_to_length"
        if not ch or len(ch) <= idx[limb] or not ch[idx[limb]] or m0.get(key) is None or m.get(key) is None:
            continue
        sx, sy, _ = S[ch[idx[limb]]]
        out[limb] = {"before": round(m0[key], 3), "after": round(m[key], 3), "landed": round(m[key] / m0[key], 3),
                     "asked": round(sx / sy, 3)}
    chest = rigd.spine[-1]
    if m0.get("chest_depth") and m.get("chest_depth") and m0.get("chest_breadth") and m.get("chest_breadth"):
        sx, _, sz = S[chest]
        out["chest"] = {"depth_to_breadth": {"before": round(m0["chest_depth"] / m0["chest_breadth"], 3),
                                             "after": round(m["chest_depth"] / m["chest_breadth"], 3)},
                        "depth_landed": round(m["chest_depth"] / m0["chest_depth"], 3),
                        "breadth_landed": round(m["chest_breadth"] / m0["chest_breadth"], 3),
                        "asked_depth": round(sz, 3), "asked_breadth": round(sx, 3),
                        "merged_with_arms": bool(m.get("chest_arms_merged"))}
    for k in ("thigh_circ", "calf_circ", "upper_arm_circ", "forearm_circ", "neck_circ", "chest_circ"):
        if m0.get(k) and m.get(k):
            out.setdefault("circ_m", {})[k] = [round(m0[k], 4), round(m[k], 4)]
    return out


EYE_FALLOFF = 2.4         # eyeball radii out from the eye's centre over which its region's scale fades to none


def eye_ratio(sp, sex):
    """The eyes' size against the head's through the warp: the preset's anatomy.parts.eyes.scale over its head
    segment (eyes grow slower than heads: `^0.53` in species_design's ANATOMY). 1 without them."""
    eyes = (((sp or {}).get("anatomy") or {}).get("parts") or {}).get("eyes") or {}
    e = eyes.get("scale")
    e = e.get(sex) if isinstance(e, dict) else e
    head = sexed(sp.get("segments"), sex).get("head")
    return float(e) / float(head) if e and head else 1.0


def scale_eyes(human, rig, r):
    """Scale each eye's region about its centre by `r`: the eyeball (every mesh on the rig whose vertices sit in
    the eye, the eyes object) whole, and the body's lids, socket and lashes around it fading to none by
    EYE_FALLOFF eyeball radii - on the mesh and every shape key. Returns {centre_m, radius_m, ratio} per side."""
    rigd = _Rig(rig)
    meshes = [_Mesh(o, rig, rigd) for o in _skinned(rig)]
    body = next(m for m in meshes if m.ob is human)
    mix = body.mixed(body.keys) if body.keys else body.base
    eyes = []
    for g in ("helper-l-eye", "helper-r-eye"):
        idx = _members(human, [g])
        if idx is None or not len(idx):
            continue
        c = mix[idx].mean(axis=0)
        eyes.append((c, float(np.linalg.norm(mix[idx] - c, axis=1).mean())))
    if len(eyes) < 2 or abs(r - 1.0) < 1e-4:
        return {}
    cs = np.array([c for c, _ in eyes])
    rad = float(np.mean([q for _, q in eyes]))

    def factors(pts, whole):
        d = np.linalg.norm(pts[:, None, :] - cs[None, :, :], axis=2)
        near = np.argmin(d, axis=1)
        dn = d[np.arange(len(pts)), near]
        if whole:
            t = (dn > EYE_FALLOFF * rad).astype(float)
        else:
            u = np.clip((dn - 1.05 * rad) / ((EYE_FALLOFF - 1.05) * rad), 0.0, 1.0)
            t = u * u * (3 - 2 * u)
        return cs[near], r + (1.0 - r) * t

    for mm in meshes:
        pts = mm.mixed(mm.keys) if mm.keys else mm.base
        whole = mm is not body
        c, f = factors(pts, whole)
        if np.all(f == 1.0):
            continue
        me = mm.ob.data
        for name, co in mm.keys:
            new = c + (co - c) * f[:, None]
            me.shape_keys.key_blocks[name].data.foreach_set("co", mm._local(new).astype(np.float32).ravel())
        new = c + (mm.base - c) * f[:, None]
        me.vertices.foreach_set("co", mm._local(new).astype(np.float32).ravel())
        me.update()
    return {"ratio": round(r, 4), "radius_m": round(rad, 4), "centres_m": [[round(float(v), 4) for v in c] for c in cs]}


def _apply(meshes, body, mask, rigd, rig, T):
    """Every mesh from its original coordinates, then the rest bones - so each pass starts from the human - and
    the whole character stands on the floor again (the shaft mapping moves the soles a little)."""
    import bpy
    out = {}
    for mm in meshes:
        base = _lbs(mm.base, mm.idx, mm.w, T)
        keys = [(name, _lbs(co, mm.idx, mm.w, T)) for name, co in mm.keys]
        out[mm.ob.name] = (base, keys)
    b_base, b_keys = out[body.ob.name]
    mix = body.mixed(b_keys) if b_keys else b_base
    dz = -float(mix[mask, 2].min())
    T = [T[0], T[1], T[2].copy(), T[3], T[4], T[5]]
    _shift(T, rigd, dz)
    for mm in meshes:
        base, keys = out[mm.ob.name]
        me = mm.ob.data
        for name, co in keys:
            co = co.copy()
            co[:, 2] += dz
            me.shape_keys.key_blocks[name].data.foreach_set("co", mm._local(co).astype(np.float32).ravel())
        base = base.copy()
        base[:, 2] += dz
        me.vertices.foreach_set("co", mm._local(base).astype(np.float32).ravel())
        me.update()
    Hh, R, S = T[2], T[3], T[4]
    vl = bpy.context.view_layer
    prev = vl.objects.active
    hidden = rig.hide_get()
    rig.hide_set(False)
    vl.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        ebs = rig.data.edit_bones
        for eb in ebs:
            eb.use_connect = False
        for i, name in enumerate(rigd.names):
            eb = ebs[name]
            eb.head = tuple(Hh[i])
            eb.tail = tuple(Hh[i] + R[i][:, 1] * rigd.length[i] * S[name][1])
            eb.align_roll(tuple(R[i][:, 2]))
        for name, c in rigd.connect.items():
            if c:
                ebs[name].use_connect = True
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        rig.hide_set(hidden)
        if prev is not None:
            vl.objects.active = prev


# ------------------------------------------------------------------ the anatomy inventory

# The drawn parts of an MPFB body, by the groups MPFB made for them (skin.MPFB_GROUPS reads the same ones), and
# what each is measured against: the part it sits on. "pair" parts are split by side and measured against the
# distance between their halves (areolae across the chest, eye sockets across the face); the rest against a
# body region read off the skin weights (the head, a hand, a foot, the hip joints' spacing).
# Part names are species_design's ANATOMY names (a preset's `anatomy.parts` and `anatomy.absent`); a name with
# a suffix ("nails.toes") answers to the name before the dot.
PARTS = {
    "nipples": {"groups": ("nipple", "nippleTip"), "host": "pair"},
    "lips": {"groups": ("lips",), "host": "head"},
    "ears": {"groups": ("ears",), "host": "head"},
    "nails": {"groups": ("fingernails",), "host": "hand"},
    "nails.toes": {"groups": ("toenails",), "host": "foot"},
    "eyes": {"groups": ("helper-l-eye", "helper-r-eye"), "host": "pair"},
    "teeth": {"groups": ("helper-upper-teeth", "helper-lower-teeth"), "host": "head"},
    "tongue": {"groups": ("helper-tongue",), "host": "head"},
    "lashes": {"groups": ("helper-l-eyelashes-1", "helper-r-eyelashes-1"), "host": "head"},
    "genitals": {"groups": ("helper-genital",), "host": "pelvis", "opt_in": "hf_genitals"},
    # A tail (humanform.tail: the group is `tail.GROUP`, and `tail.PROP` on the body is what says one was
    # grown). Present only on a species whose description gives it one, and then held to its size against
    # the pelvis like any other part, so a bake or a later warp cannot quietly lose it.
    "tail": {"groups": ("hf_tail",), "host": "pelvis", "opt_in": "hf_tail"},
}
# the parts that are meshes of their own on the rig, by the suffix humanform names them with: the eyeballs
# (humanform.eyes) and the teeth and tongue (humanform.features.mouth). Missing and not declared absent fails.
OBJECT_PARTS = {"eyes": "_eyes", "teeth": "_teeth"}
# a part's size over its host's may change this much through a warp before it is a warn / a fail
RATIO_WARN, RATIO_FAIL = (0.67, 1.5), (0.5, 2.0)
SKINNED_SHARE = 0.99       # the share of a part's vertices that must carry deform weights


def _absent(sp):
    """{part: reason} the preset (or an inline species) declares the creature does not have."""
    a = ((sp or {}).get("anatomy") or {}).get("absent") or {}
    if isinstance(a, dict):
        return {k: str(v) for k, v in a.items()}
    out = {}
    for row in a:
        if isinstance(row, dict):
            out[row.get("part")] = str(row.get("reason", "declared absent"))
        else:
            out[str(row)] = "declared absent"
    return out


def _members(ob, names, thresh=0.5):
    gids = {ob.vertex_groups[n].index for n in names if n in ob.vertex_groups}
    if not gids:
        return None
    return np.array([v.index for v in ob.data.vertices
                     if any(e.group in gids and e.weight > thresh for e in v.groups)], int)


def _key_moved(human, mesh, key, least=5e-4):
    """The vertices a shape key moves at least `least` metres off its reference, or None without the key."""
    by = dict(mesh.keys)
    if key not in by:
        return None
    kb = human.data.shape_keys.key_blocks[key]
    d = np.linalg.norm(by[key] - by.get(kb.relative_key.name, mesh.keys[0][1]), axis=1)
    return np.flatnonzero(d >= least)


def _size(pts):
    return float(np.linalg.norm(np.ptp(pts, axis=0))) if len(pts) > 1 else 0.0


def inventory(human, sp=None, reference=None, expected=None):
    """Every drawn part of the body - MPFB's areolae, lips, ears, nails, eye sockets, teeth, tongue and lashes,
    the genital shell when it was asked for, and every other mesh skinned to the rig (eyes, brows, lashes, hair,
    tusks) - checked present, skinned and not degenerate, and, given the `reference` inventory taken before a
    warp, still the size it was against the part it sits on. A part the species declares absent
    (`anatomy.absent`) is skipped with its reason; one missing and not declared absent fails.
    `expected` ({part: ratio}) is a change a part is meant to make against its host (the eyes' allometry, from
    `eye_ratio`); the rest are meant to keep theirs. Returns {parts, counts, fail}."""
    from . import body as _body
    human = _body.obj(human)
    rig = _body.rig_of(human)
    absent = _absent(load(sp) if sp is not None else None)
    if rig is None:
        return {"parts": [], "counts": {"fail": 1}, "fail": 1, "error": f"{human.name} is not skinned to a rig"}
    rigd = _Rig(rig)
    meshes = {o.name: _Mesh(o, rig, rigd) for o in _skinned(rig)}
    bm = meshes.get(human.name)
    if bm is None:
        return {"parts": [], "counts": {"fail": 1}, "fail": 1, "error": f"{human.name} is not skinned to {rig.name}"}
    co = bm.mixed(bm.keys) if bm.keys else bm.base
    nb = len(rigd.names)

    def top_bone(mm):
        return mm.idx[np.arange(len(mm.idx)), np.argmax(mm.w, axis=1)]

    def dominant(mm, kinds):
        ids = [rigd.ix[n] for n, k in rigd.kind.items() if k in kinds]
        return np.isin(top_bone(mm), ids)

    hosts = {"head": _size(co[dominant(bm, ("head",))]),
             "hand": _size(co[dominant(bm, ("hand", "digit")) & (co[:, 0] > 0)]),
             "foot": _size(co[dominant(bm, ("foot", "toe")) & (co[:, 0] > 0)]), "pelvis": 0.0}
    hips = [rigd.head[rigd.ix[ch[0]]] for ch in rigd.legs.values()]
    if len(hips) > 1:
        hosts["pelvis"] = float(np.linalg.norm(hips[0] - hips[-1]))
    ref = {r["part"]: r for r in (reference or {}).get("parts", [])}

    def judge(row):
        r0 = ref.get(row["part"])
        if r0 and r0.get("ratio") and row.get("ratio"):
            # a sub-part first (a foot plan draws the TOEnails together and leaves the fingernails alone),
            # then the whole part it is of
            want = (expected or {}).get(row["part"],
                                        (expected or {}).get(row["part"].split(".")[0], 1.0))
            ch = row["ratio"] / r0["ratio"] / want
            if want != 1.0:
                row["expected_change"] = round(want, 3)
            row["ratio_change"] = round(ch, 3)
            if not RATIO_FAIL[0] <= ch <= RATIO_FAIL[1]:
                return dict(row, status="fail", reason=f"{ch:.2f}x the size it was against its {row['host']}: "
                                                        "the warp did not carry it with the part it sits on")
            if not RATIO_WARN[0] <= ch <= RATIO_WARN[1]:
                return dict(row, status="warn", reason=f"{ch:.2f}x the size it was against its {row['host']}")
        return dict(row, status="pass")

    def basic(row, pts, on):
        row.update(verts=int(len(pts)), skinned=round(float(on.mean()) if len(on) else 0.0, 3))
        if not len(pts) or not np.isfinite(pts).all() or _size(pts) < 1e-4:
            return dict(row, status="fail", reason="degenerate: empty, collapsed or not finite")
        if row["skinned"] < SKINNED_SHARE:
            return dict(row, status="fail", reason=f"only {row['skinned']:.0%} of its vertices carry deform weights")
        return None

    rows = []
    for part, spec in PARTS.items():
        row = {"part": part, "host": spec["host"]}
        name = part.split(".")[0]
        if part in absent or name in absent:        # the part (nails.toes) or the whole part it is of (nails)
            rows.append(dict(row, status="skip", reason=f"declared absent: {absent.get(part) or absent[name]}"))
            continue
        if spec.get("opt_in") and not human.get(spec["opt_in"]):
            rows.append(dict(row, status="skip", reason=f"not asked for (opt-in: {spec['opt_in']} is unset)"))
            continue
        idx = _members(human, spec["groups"])
        if part == "genitals" and human.get("hf_genitals") == "female":
            # a woman's part is humanform.genitals' relief (a delta key), not MPFB's male shell: the vertices it moves
            idx = _key_moved(human, bm, "hfd:genital")
            if idx is None:
                rows.append(dict(row, status="fail", reason="missing: hf_genitals is 'female' and there is no "
                                                            "hfd:genital relief key (humanform.genitals.relief)"))
                continue
        if idx is None or not len(idx):
            rows.append(dict(row, status="fail", reason=f"missing: no vertices in {', '.join(spec['groups'])}, "
                                                        "and not declared absent (anatomy.absent)"))
            continue
        pts = co[idx]
        bad = basic(row, pts, bm.idx[idx, 0] < nb)
        if bad:
            rows.append(bad)
            continue
        if spec["host"] == "pair":
            l, r = pts[pts[:, 0] > 0], pts[pts[:, 0] <= 0]
            if not len(l) or not len(r):
                rows.append(dict(row, status="fail", reason="one side is missing"))
                continue
            host, size = float(np.linalg.norm(l.mean(axis=0) - r.mean(axis=0))), (_size(l) + _size(r)) / 2
        else:
            host = hosts.get(spec["host"], 0.0)
            size = _size(pts[pts[:, 0] > 0]) if spec["host"] in ("hand", "foot") else _size(pts)
        row.update(size_m=round(size, 4), host_m=round(host, 4), ratio=round(size / host, 4) if host > 1e-6 else None)
        rows.append(judge(row))

    # every other mesh on the rig: eyes, brows, lashes, hair, tusks
    for name, mm in meshes.items():
        if name == human.name:
            continue
        label = next((f"{p}.object" for p, suf in OBJECT_PARTS.items() if name == human.name + suf), None)
        row = {"part": label or f"object:{name}"}
        if name in absent or (label and label.split(".")[0] in absent):
            rows.append(dict(row, status="skip", reason=f"declared absent: {absent[name]}"))
            continue
        pts = mm.mixed(mm.keys) if mm.keys else mm.base
        bad = basic(row, pts, mm.idx[:, 0] < nb)
        if bad:
            rows.append(bad)
            continue
        kinds = {rigd.kind.get(rigd.names[b]) for b in set(top_bone(mm).tolist()) if b < nb}
        row["host"] = "head" if kinds <= {"head", "neck"} else "body"
        hs = hosts["head"] if row["host"] == "head" else _size(co)
        size = _size(pts)
        row.update(size_m=round(size, 4), host_m=round(hs, 4), ratio=round(size / hs, 4) if hs > 1e-6 else None)
        rows.append(judge(row))
    for part, suf in OBJECT_PARTS.items():
        if part in absent or any(r["part"] == f"{part}.object" for r in rows):
            continue
        rows.append({"part": f"{part}.object", "status": "fail",
                     "reason": f"missing: no {human.name}{suf} skinned to {rig.name}, and not declared absent"})
    for part, reason in absent.items():
        if not any(r["part"] in (part, f"object:{part}") or r["part"].split(".")[0] == part for r in rows):
            rows.append({"part": part, "status": "skip", "reason": f"declared absent: {reason}"})
    # Fur is a part (species_design.ANATOMY), and the only one that is not geometry: it is the coverage map
    # on the body. A species that says it has fur and a body that does not carry the map fails here, before
    # the bake ever looks at a texture.
    want_fur = fur_block(sp) if sp is not None else None
    if want_fur is not None and "fur" not in absent:
        from . import fur as _fur
        row = {"part": "fur", "host": "body"}
        block = _fur.read(human)
        if block is None or _fur.DEN not in human.data.attributes:
            rows.append(dict(row, status="fail", reason="missing: the species asks for fur and the body carries "
                                                        "no coverage map (humanform.fur.apply)"))
        else:
            verts = int(block.get("vertices") or 0)
            names = sorted(r["name"] for r in block.get("regions", []))
            asked = sorted(r.get("name", "") for r in want_fur.get("regions", []))
            if verts <= 0:
                rows.append(dict(row, status="fail", reason="the fur map covers no vertex: every region's areas "
                                                            "landed on skin that is never furred"))
            elif names != asked:
                rows.append(dict(row, status="fail", reason=f"the body carries fur regions {names}, the species "
                                                            f"asks for {asked}"))
            else:
                rows.append(dict(row, status="pass", verts=verts, regions=names,
                                 covered=int(block.get("covered_vertices") or 0)))
    counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("pass", "warn", "fail", "skip")}
    return {"parts": rows, "counts": counts, "fail": counts["fail"]}
