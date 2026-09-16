"""L2: an MPFB2 base body - quads, UVs, deformation loops, weights - driven to a landmark set.

    r = sheet.resolve(s)
    lm = landmarks.from_measurements(r["values"], s["sex"], s["style"], name=s["name"])
    human, rep = scaffold.build(r["sheet"], lm)          # create, fit, rig, rename
    print(scaffold.summarize(rep))

`create` sets MPFB's macros from the sheet (sex, age, weight from BMI, muscle from the brief or its
build, firmness and proportions from the brief).
`fit` then solves MPFB's own fine targets - segment lengths, hand and foot scale, torso and
neck lengths, circumferences, head height - plus the height macro, against the landmark set's
numbers, measured on the mesh the way humancheck measures them: a damped Gauss-Newton with a
finite-difference Jacobian, each residual in units of its preset tolerance. Joints are where
MPFB's rig will put them (the centroids of its joint-* vertex groups), so no rig is rebuilt
while solving. `rig` adds MPFB's game_engine rig with its artist weights and renames bones and
groups to rig-anything's names, so wardrobe, follow-through and animate-anything read it.

MPFB2 is GPL-3.0; it is called through its services, never copied.
"""

from __future__ import annotations

import os
import sys
import time

import bpy
import numpy as np

from . import body as _body
from . import landmarks as _landmarks
from . import measure

_pkg = sys.modules[__package__]
MPFB = "bl_ext.user_default.mpfb"
KEY_PREFIX = "hf:"

# solver parameters: (name, target group, stem, sided) - weight w in [-1, 1] loads stem-incr (w > 0)
# or stem-decr (w < 0); sided stems are applied to l- and r- together
FINE = [
    ("upper_arm", "arms", "measure-upperarm-length", False),
    ("forearm", "arms", "measure-lowerarm-length", False),
    ("hand", "hands", "hand-scale", True),
    ("foot", "feet", "foot-scale", True),
    ("ankle", "feet", "foot-scale-vert", True),
    ("thigh", "legs", "measure-upperleg-height", False),
    ("shin", "legs", "measure-lowerleg-height", False),
    ("torso", "torso", "measure-napetowaist-dist", False),
    ("hip_vert", "hip", "hip-scale-vert", False),
    ("neck", "neck", "measure-neck-height", False),
    ("head", "head", "head-scale-vert", False),
    ("shoulders", "torso", "measure-shoulder-dist", False),
    ("hips", "torso", "measure-hips-circ", False),
    ("waist", "torso", "measure-waist-circ", False),
    ("belly", "stomach", "stomach-pregnant", False),
    ("bust", "torso", "measure-bust-circ", False),
    ("thigh_girth", "legs", "measure-thigh-circ", False),
    ("calf_girth", "legs", "measure-calf-circ", False),
    ("arm_girth", "arms", "measure-upperarm-circ", False),
    ("neck_girth", "neck", "measure-neck-circ", False),
]
# residuals: (measurement key, landmark-set key, tolerance key in the preset)
RESIDUALS = [
    ("stature", "stature", None),
    ("shoulder_z", "shoulder_z", "shoulder_joint"),
    ("hip_z", "hip_z", "hip_joint"),
    ("crotch_z", "crotch_z", "crotch"),
    ("knee_z", "knee_z", "knee_joint"),
    ("ankle_z", "ankle_z", "ankle_joint"),
    ("chin_z", "chin_z", "chin"),
    ("upper_arm", "upper_arm", "upper_arm"),
    ("forearm", "forearm", "forearm"),
    ("hand", "hand", "hand"),
    ("foot", "foot", "foot"),
    ("shoulder_width", "shoulder_width", "shoulder_width"),
    ("hip_width", "hip_width", "hip_width"),
    ("waist_circ", "waist_circ", None),
    ("waist_breadth", "waist_breadth", None),
    ("waist_depth", "waist_depth", None),
    ("hip_circ", "hip_circ", None),
    ("hip_depth", "hip_depth", None),
    ("chest_circ", "chest_circ", None),
    ("thigh_circ", "thigh_circ", None),
    ("calf_circ", "calf_circ", None),
    ("upper_arm_circ", "upper_arm_circ", None),
    ("neck_circ", "neck_circ", None),
]
ABS_TOL = {"stature": 0.01, "waist_circ": 0.02, "hip_circ": 0.02, "chest_circ": 0.02,
           "waist_breadth": 0.015, "waist_depth": 0.015, "hip_depth": 0.015,
           "thigh_circ": 0.02, "calf_circ": 0.015, "upper_arm_circ": 0.015, "neck_circ": 0.015,
           "interpupillary": 0.003, "head_breadth": 0.004, "head_depth": 0.005, "bizygomatic": 0.004,
           "menton_sellion": 0.004, "head_circ": 0.01}
FACE_FINE = [
    ("head_breadth", "head", "head-scale-horiz", False),
    ("head_depth", "head", "head-scale-depth", False),
    ("eye_spacing", "eyes", "eye-trans", True, ("out", "in")),
    ("cheekbones", "cheek", "cheek-bones", True),
    ("face_height", "chin", "chin-height", False),
    ("forehead", "forehead", "forehead-scale-vert", False),
]
FACE_RESIDUALS = [
    ("interpupillary", "interpupillary", None),
    ("head_breadth", "head_breadth", None),
    ("head_depth", "head_depth", None),
    ("bizygomatic", "bizygomatic", None),
    ("menton_sellion", "menton_sellion", None),
    ("head_circ", "head_circ", None),
]
# hands and feet: every lever MPFB has that changes a measured size. Finger length trades palm for
# fingers at a fixed hand length (with hand scale), foot width is the only lever on foot breadth.
# What is left - finger thickness and spread, foot height - is free for designs (parts.STYLE).
EXTREMITY_FINE = [
    ("hand", "hands", "hand-scale", True),
    ("fingers", "hands", "hand-fingers-length", True),
    ("wrist", "hands", "measure-wrist-circ", False),
    ("foot", "feet", "foot-scale", True),
    ("foot_width", "feet", "foot-scale-horiz", True),
    ("ankle_girth", "feet", "measure-ankle-circ", False),
]
EXTREMITY_RESIDUALS = [
    ("hand", "hand", None),
    ("hand_breadth", "hand_breadth", None),
    ("palm_length", "palm_length", None),
    ("wrist_circ", "wrist_circ", None),
    ("foot", "foot", None),
    ("foot_breadth", "foot_breadth", None),
    ("ankle_circ", "ankle_circ", None),
]
# hand breadth gets 3 mm (0.8 sd): the free finger targets a design uses move it by up to 2-3 mm
ABS_TOL.update({"hand": 0.003, "hand_breadth": 0.003, "palm_length": 0.003, "wrist_circ": 0.004, "foot": 0.004,
                "foot_breadth": 0.0025, "ankle_circ": 0.006})
EXTREMITY_PRIOR = {"hand": 0.2, "fingers": 0.3, "wrist": 0.3, "foot": 0.2, "foot_width": 0.3, "ankle_girth": 0.3}
FACE_PRIOR = {"head_breadth": 0.5, "head_depth": 0.5, "eye_spacing": 0.5, "cheekbones": 0.5, "face_height": 0.5,
              "forehead": 0.5}
BUILD_MUSCLE = {"slim": 0.45, "average": 0.5, "athletic": 0.7, "muscular": 0.9, "curvy": 0.5, "soft": 0.3,
                "heavy": 0.4}

# MPFB game_engine -> rig-anything names (Nora's layout)
RENAME = {"Root": "root", "pelvis": "spine", "spine_01": "spine.001", "spine_02": "spine.002",
          "spine_03": "spine.003", "neck_01": "spine.004", "head": "spine.005"}
for _mp, _hf in (("clavicle", "shoulder"), ("upperarm", "upper_arm"), ("lowerarm", "forearm"), ("hand", "hand"),
                 ("thigh", "thigh"), ("calf", "shin"), ("foot", "foot"), ("ball", "toe")):
    for _s in ("l", "r"):
        RENAME[f"{_mp}_{_s}"] = f"{_hf}.{_s.upper()}"
for _f in ("thumb", "index", "middle", "ring", "pinky"):
    for _i in (1, 2, 3):
        for _s in ("l", "r"):
            RENAME[f"{_f}_0{_i}_{_s}"] = (f"thumb.0{_i}.{_s.upper()}" if _f == "thumb" else f"f_{_f}.0{_i}.{_s.upper()}")


def services():
    import addon_utils
    if MPFB not in bpy.context.preferences.addons:
        addon_utils.enable(MPFB, default_set=True)   # MPFB reads its own preferences entry
    from bl_ext.user_default.mpfb.entities.objectproperties import HumanObjectProperties
    from bl_ext.user_default.mpfb.services.humanservice import HumanService
    from bl_ext.user_default.mpfb.services.locationservice import LocationService
    from bl_ext.user_default.mpfb.services.targetservice import TargetService
    return HumanService, TargetService, HumanObjectProperties, LocationService


def age_macro(years):
    """MakeHuman's age slider: 0 is 1 year old, 0.1875 is 11, 0.5 is 25, 1.0 is 90."""
    if years is None:
        return 0.5
    if years < 11:
        return float(np.clip(0.1875 * (years - 1) / 10, 0.0, 0.1875))
    if years < 25:
        return float(np.clip(0.1875 + (years - 11) / 14 * 0.3125, 0.1875, 0.5))
    return float(np.clip(0.5 + (years - 25) / 65 * 0.5, 0.5, 1.0))


def weight_macro(bmi):
    return float(np.interp(bmi, [17.0, 25.0, 35.0], [0.0, 0.5, 1.0]))


# median BMI for age, both sexes (CDC 2000 growth charts, 50th percentile, rounded)
CHILD_BMI = {1: 17.2, 2: 16.4, 3: 15.9, 4: 15.5, 5: 15.3, 6: 15.3, 7: 15.5, 8: 15.8, 9: 16.2, 10: 16.6, 11: 17.2,
             12: 17.8, 13: 18.4, 14: 19.0, 15: 19.6, 16: 20.2, 17: 20.7}


def child_weight_macro(bmi, years):
    """A child's BMI read against the median for its age, with the adult scale's shape (17 / 25 / 35 is
    0.68 / 1 / 1.4 of 25): MPFB's weight macro at a child's age is relative to that age."""
    if bmi is None:
        return 0.5
    ages = sorted(CHILD_BMI)
    med = float(np.interp(years, ages, [CHILD_BMI[a] for a in ages]))
    return float(np.interp(bmi, [0.68 * med, med, 1.4 * med], [0.0, 0.5, 1.0]))


# macros the fit never moves: set from the brief (MPFB's default when it says nothing), and put back on a
# warm or reused start so a stored body's firmness or proportions are not inherited
UNFITTED = ("age", "firmness", "proportions", "cupsize", "asian", "caucasian", "african")


def create_macros(sheet_resolved):
    """The MPFB macros a sheet sets before any fit: sex, age (capped at ANSUR's 58 for a fitted adult),
    weight from BMI, muscle from the brief or its build, and the unfitted macros the brief may give."""
    from . import sheet as _sheet
    s = sheet_resolved
    build = s.get("build") if isinstance(s.get("build"), str) else "average"
    age = s.get("age")
    path = _sheet.ansur_path(age)
    if path == "aged":
        age = _sheet.AGE_RANGE[1]
    weight = child_weight_macro(s.get("bmi"), age) if path == "child" else weight_macro(s.get("bmi") or 25.0)
    muscle = s.get("muscle") if s.get("muscle") is not None else BUILD_MUSCLE.get(build, 0.5)
    out = {"gender": 1.0 if s["sex"] == "male" else 0.0, "age": age_macro(age), "weight": weight, "muscle": muscle}
    defaults = _default_macros()
    for k in UNFITTED[1:]:
        out[k] = float(s[k]) if s.get(k) is not None else defaults[k]
    return out


def _default_macros():
    _, TargetService, _, _ = services()
    d = TargetService.get_default_macro_info_dict()
    flat = {k: v for k, v in d.items() if not isinstance(v, dict)}
    flat.update(d.get("race", {}))
    return flat


def reset_macros(human, sheet_resolved, names=("weight", "muscle") + UNFITTED):
    """Put the brief's own macros back on a body started from a stored one. Returns {name: (was, now)}
    for each that moved by more than 0.02."""
    _, TargetService, HOP, _ = services()
    own = create_macros(sheet_resolved)
    changed = {}
    for n in names:
        was = HOP.get_value(n, entity_reference=human)
        if abs(was - own[n]) > 0.02:
            HOP.set_value(n, own[n], entity_reference=human)
            changed[n] = (round(float(was), 3), round(float(own[n]), 3))
    if changed:
        TargetService.reapply_macro_details(human)
    return changed


def stature(human):
    bpy.context.view_layer.update()
    b = _body.Body(human)
    return float(b.top - b.floor)


def fit_stature(human, target, iterations=14, tol=0.0005):
    """Bisect MPFB's height macro until the body stands `target` metres tall - for bodies no ANSUR fit
    sizes: a child (MPFB's 8-year-old is 1.15 m, a real one about 1.28) and an aged body (MPFB's
    ageing shortens it). Returns {macro, stature_m, target_m}."""
    _, TargetService, HOP, _ = services()
    lo, hi = 0.0, 1.0
    mid, got = HOP.get_value("height", entity_reference=human), None
    for _ in range(iterations):
        mid = (lo + hi) / 2
        HOP.set_value("height", mid, entity_reference=human)
        TargetService.reapply_macro_details(human)
        got = stature(human)
        if abs(got - target) < tol:
            break
        if got < target:
            lo = mid
        else:
            hi = mid
    return {"macro": round(mid, 3), "stature_m": round(got, 4), "target_m": target,
            "reached": abs(got - target) < 0.005}


def create(sheet_resolved, name=None):
    HumanService, TargetService, HOP, _ = services()
    s = sheet_resolved
    name = name or s.get("name") or "Human"
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    macro = TargetService.get_default_macro_info_dict()
    own = create_macros(s)
    for k in ("asian", "caucasian", "african"):
        macro.setdefault("race", {})[k] = own.pop(k)
    macro.update(own)
    human = HumanService.create_human(macro_detail_dict=macro)
    human.name = name
    human["humanform_sheet"] = __import__("json").dumps(s)
    return human


def _spec(entry):
    """(name, group, stem, sided[, (positive suffix, negative suffix)]) -> all six fields."""
    name, group, stem, sided = entry[:4]
    pos, neg = entry[4] if len(entry) > 4 else ("incr", "decr")
    return name, group, stem, sided, pos, neg


def _load_targets(human, fine):
    _, TargetService, _, LocationService = services()
    root = LocationService.get_mpfb_data("targets")
    kb = human.data.shape_keys.key_blocks
    keys = {}
    for entry in fine:
        name, group, stem, sided, pos, neg = _spec(entry)
        keys[name] = []
        for side in (("l", "r") if sided else (None,)):
            pair = {}
            for role, suffix in (("pos", pos), ("neg", neg)):
                fname = f"{side}-{stem}-{suffix}" if side else f"{stem}-{suffix}"
                path = os.path.join(root, group, fname + ".target.gz")
                if not os.path.exists(path):
                    raise FileNotFoundError(path)
                kname = KEY_PREFIX + fname
                if kb.get(kname) is None:
                    TargetService.load_target(human, path, weight=0.0, name=kname)
                pair[role] = kname
            keys[name].append(pair)
    return keys


MACROS = ("height", "weight", "muscle")
# penalty per unit of weight squared: global levers are cheap, local girth targets are last resorts -
# pushed to their limits they put all of a waist's extra girth into a belly (every first fit did)
PRIOR = {"height": 0.0, "weight": 0.3, "muscle": 0.5, "waist": 3.0, "belly": 6.0, "hips": 2.0, "bust": 2.0, "shoulders": 1.0,
         "hip_vert": 1.0, "neck": 1.0, "head": 1.0}
DEFAULT_PRIOR = 0.3
# builds whose girth really does sit in the belly
BUILD_PRIOR = {"heavy": {"belly": 1.0, "waist": 1.0}, "soft": {"belly": 1.5, "waist": 1.5},
               # a muscular brief is about muscle: without this the solver traded it for fat to hit girth
               # (Kade's muscle fell from 0.9 to 0.34 and he read as average)
               "muscular": {"muscle": 6.0}, "athletic": {"muscle": 4.0}}
# a macro the brief gives outright: Dante's muscle 1.0 under the muscular prior alone fell to 0.72
HOLD_PRIOR = 40.0


class _State:
    """A parameter vector over some MPFB macros and target pairs, pushed onto the mesh on set()."""

    def __init__(self, human, macros, fine, prior=None):
        _, _, HOP, _ = services()
        self.human, self.macros = human, tuple(macros)
        self.fine = [_spec(e) for e in fine]
        self.keys = _load_targets(human, fine)
        kb = human.data.shape_keys.key_blocks
        self.names = list(self.macros) + [e[0] for e in self.fine]
        cur = []
        for e in self.fine:
            pair = self.keys[e[0]][0]
            cur.append(kb[pair["pos"]].value - kb[pair["neg"]].value)
        self.x = np.array([HOP.get_value(m, entity_reference=human) for m in self.macros] + cur, dtype=float)
        self.start = self.x.copy()
        prior = prior or {}
        self.lam = np.array([prior.get(n, DEFAULT_PRIOR) for n in self.names])
        self.lo = np.array([0.0] * len(self.macros) + [-1.0] * len(self.fine))
        self.hi = np.ones(len(self.x))

    def set(self, x):
        _, TargetService, HOP, _ = services()
        x = np.clip(np.array(x, dtype=float), self.lo, self.hi)
        nm = len(self.macros)
        if nm and np.any(np.abs(x[:nm] - self.x[:nm]) > 1e-9):
            for i, mname in enumerate(self.macros):
                HOP.set_value(mname, float(x[i]), entity_reference=self.human)
            TargetService.reapply_macro_details(self.human)
        kb = self.human.data.shape_keys.key_blocks
        for i, e in enumerate(self.fine):
            w = float(x[nm + i])
            for pair in self.keys[e[0]]:
                kb[pair["pos"]].value = max(w, 0.0)
                kb[pair["neg"]].value = max(-w, 0.0)
        self.x = x

    def prior_cost(self, x):
        return float(np.sum(self.lam * (x - self.start) ** 2))

    def values(self):
        return {n: round(float(v), 3) for n, v in zip(self.names, self.x)}


def _measure(human, sex, only=None):
    bpy.context.view_layer.update()
    return measure.measurements(_body.Body(human), sex, fast=True, only=only)


def _residuals(m, target, tol, spec):
    r = []
    for mkey, tkey, _ in spec:
        mv, tv = m.get(mkey), target.get(tkey)
        r.append(0.0 if mv is None or tv is None else (mv - tv) / tol[mkey])
    return np.array(r)


def _tolerances(spec, preset, sex, H):
    tol = {}
    for mkey, _, pkey in spec:
        if pkey is None:
            tol[mkey] = ABS_TOL[mkey]
        else:
            e = preset[pkey]
            tol[mkey] = (e.get("any") or e.get(sex))[1] * H
    return tol


GOOD = 0.75          # stop once every residual is within this many tolerances
STALL = 0.02         # ... or once an accepted step improves the cost by less than this fraction


def _solve(human, st, target, spec, tol, sex, iterations=10, damping=0.3, steps=None, verbose=True, label="fit",
           jacobian=None, only=None):
    """Levenberg-Marquardt with a finite-difference Jacobian built once and then kept current with
    Broyden rank-one updates from each accepted step - one measurement per step instead of one per
    parameter. A step the updated Jacobian cannot improve rebuilds it once before giving up."""
    t0 = time.time()
    evals = [0]

    def evaluate():
        evals[0] += 1
        mm = _measure(human, sex, only)
        return mm, _residuals(mm, target, tol, spec)

    steps = np.array(steps if steps is not None else [0.3] * len(st.x))
    m, r = evaluate()
    cost = float(np.sum(r ** 2)) + st.prior_cost(st.x)
    J = np.array(jacobian, dtype=float) if jacobian is not None else None
    if J is not None and J.shape != (len(r), len(st.x)):
        J = None
    fresh, history, stalled = False, [], False
    for it in range(iterations):
        rms = float(np.sqrt(np.mean(r ** 2)))
        worst = int(np.argmax(np.abs(r)))
        history.append({"iteration": it, "rms_tol": round(rms, 3), "worst": spec[worst][0],
                        "worst_tol": round(float(r[worst]), 2), "evals": evals[0]})
        if verbose:
            print(f"  {label} {it}: rms {rms:.2f} tol, worst {spec[worst][0]} {r[worst]:+.2f} ({evals[0]} measurements)")
        if np.max(np.abs(r)) < GOOD or stalled:
            break
        x0 = st.x.copy()
        if J is None:
            J = np.zeros((len(r), len(x0)))
            for j in range(len(x0)):
                h = steps[j] if x0[j] + steps[j] <= st.hi[j] else -steps[j]
                xp = x0.copy()
                xp[j] += h
                st.set(xp)
                J[:, j] = (evaluate()[1] - r) / h
            st.set(x0)
            fresh = True
        L = np.diag(st.lam)
        best, mu = None, damping
        for _attempt in range(4):
            dx = -np.linalg.solve(J.T @ J + L + mu * np.eye(len(x0)), J.T @ r + L @ (x0 - st.start))
            xn = np.clip(x0 + dx, st.lo, st.hi)
            st.set(xn)
            mn, rn = evaluate()
            cn = float(np.sum(rn ** 2)) + st.prior_cost(xn)
            if best is None or cn < best[0]:
                best = (cn, xn, mn, rn)
            if cn < cost:
                damping = max(mu / 3, 0.05)
                break
            mu *= 4
        if best[0] >= cost:
            st.set(x0)
            if not fresh:
                J = None          # the Broyden estimate went stale; rebuild it once
                continue
            if verbose:
                print(f"  {label}: no step improves; stopping")
            break
        step, dr = best[1] - x0, best[3] - r
        if step @ step > 1e-12:
            J = J + np.outer(dr - J @ step, step) / (step @ step)
        fresh = False
        st.set(best[1])
        stalled = best[0] > cost * (1.0 - STALL)
        cost, m, r = best[0], best[2], best[3]

    rows = []
    for (mkey, tkey, _), rv in zip(spec, r):
        mv, tv = m.get(mkey), target.get(tkey)
        rows.append({"measure": mkey, "value": round(float(mv or 0), 4), "target": round(float(tv or 0), 4),
                     "error_cm": round(float((mv or 0) - (tv or 0)) * 100, 2), "tol": round(float(rv), 2)})
    return {"params": st.values(), "residuals": rows, "history": history, "measurements": evals[0],
            "seconds": round(time.time() - t0, 1), "rms_tol": round(float(np.sqrt(np.mean(r ** 2))), 3),
            "max_tol": round(float(np.max(np.abs(r))), 3), "names": list(st.names),
            "jacobian": None if J is None else np.round(J, 4).tolist()}


def fit(human, lm, iterations=10, damping=0.3, verbose=True, build=None, start=None, jacobian=None, hold=()):
    """L2 body stage: MPFB's height, weight and muscle macros and the body targets, to the landmark set.
    `start` is a params dict (a library body's) to begin from instead of the macros' own values. `hold`
    names macros the brief set outright (muscle): the fit keeps them near the value the body had when
    the fit began."""
    sex, style = lm["sex"], lm["style"]
    target = _landmarks.as_measurements(lm)
    tol = _tolerances(RESIDUALS, _pkg.presets()["presets"][style]["ratios"], sex, lm["stature"])
    prior = dict(PRIOR, **BUILD_PRIOR.get(build, {}))
    prior.update({n: HOLD_PRIOR for n in hold})
    st = _State(human, MACROS, FINE, prior)
    if start:
        st.set([start.get(n, v) for n, v in zip(st.names, st.x)])
    return _solve(human, st, target, RESIDUALS, tol, sex, iterations, damping,
                  steps=[0.04, 0.08, 0.08] + [0.3] * len(FINE), verbose=verbose, label="body", jacobian=jacobian)


def fit_face(human, lm, iterations=8, verbose=True, start=None, jacobian=None):
    """L4 face stage: head breadth and depth, eye spacing, cheekbones, face height - its own small
    solve after the body, so the body's Jacobian never pays for the face."""
    target = _landmarks.as_measurements(lm)
    st = _State(human, (), FACE_FINE, FACE_PRIOR)
    if start:
        st.set([start.get(n, v) for n, v in zip(st.names, st.x)])
    tol = {k: ABS_TOL[k] for k, _, _ in FACE_RESIDUALS}
    return _solve(human, st, target, FACE_RESIDUALS, tol, lm["sex"], iterations, 0.3, verbose=verbose, label="face",
                  jacobian=jacobian)


def fit_extremities(human, lm, iterations=8, verbose=True, start=None, jacobian=None):
    """L4 hands and feet: hand and foot length, hand breadth, palm length, wrist, foot breadth and
    ankle girth to ANSUR (plus any design offsets already in `lm`). Skipped for a landmark set that
    predates these measurements."""
    target = _landmarks.as_measurements(lm)
    spec = [r for r in EXTREMITY_RESIDUALS if target.get(r[1]) is not None]
    if len(spec) < 3:
        return None
    st = _State(human, (), EXTREMITY_FINE, EXTREMITY_PRIOR)
    if start:
        st.set([start.get(n, v) for n, v in zip(st.names, st.x)])
    tol = {k: ABS_TOL[k] for k, _, _ in spec}
    return _solve(human, st, target, spec, tol, lm["sex"], iterations, 0.3, verbose=verbose, label="extremities",
                  jacobian=jacobian, only="extremities")


def rig(human, rig_name=None):
    """MPFB's game_engine rig and weights, renamed to rig-anything's bone names."""
    HumanService, _, _, _ = services()
    rig_ob = HumanService.add_builtin_rig(human, "game_engine")
    rig_ob.name = rig_ob.data.name = rig_name or f"{human.name}_rig"
    # rig-anything's profile for exactly this rig after RENAME: its roles (head spine.005), rotation
    # mode and how its skin is baked for a game (rig_analysis/profiles/mpfb_game_engine.json)
    rig_ob["body_profile"] = "mpfb_game_engine"
    renamed = 0
    for b in rig_ob.data.bones:
        new = RENAME.get(b.name)
        if new:
            vg = human.vertex_groups.get(b.name)
            b.name = new                              # bone rename updates the pose and constraints
            if vg is not None:
                vg.name = new
            renamed += 1
    return rig_ob, renamed


def finish(human, rep):
    """Stand the fitted body on the floor and rig it."""
    bpy.context.view_layer.update()
    low = float(_body.Body(human).floor)
    if abs(low) > 1e-5:
        # shift the basis and every shape key alike, so the deltas MPFB and the fit rely on are kept
        # and the object stays at the origin (rig-anything's export requires it)
        for kb in human.data.shape_keys.key_blocks:
            co = np.empty(len(kb.data) * 3, np.float32)
            kb.data.foreach_get("co", co)
            co[2::3] -= low
            kb.data.foreach_set("co", co)
        human.data.update()
    rig_ob, renamed = rig(human)
    rep["rig"] = rig_ob.name
    rep["bones_renamed"] = renamed
    rep["floor_shift_m"] = round(-low, 4)
    return rig_ob


def fit_all(human, lm, build=None, start=None, jacobians=None, iterations=10, verbose=False, face=True,
            extremities=True, hold=()):
    """Body stage, face stage, hands-and-feet stage, then a settle pass: the face moves the chin, and
    the neck is measured under the chin, so the body is re-measured once and refined briefly if the
    face disturbed it. A stored body therefore reproduces its residuals when it is applied again.
    `hold`: macros the brief set outright, kept where they start (see `fit`)."""
    jacobians = jacobians or {}
    rep = fit(human, lm, iterations=iterations, verbose=verbose, build=build, start=start, jacobian=jacobians.get("body"),
              hold=hold)
    stages = {}
    if face:
        stages["face"] = fit_face(human, lm, verbose=verbose, start=start, jacobian=jacobians.get("face"))
    if extremities:
        ext = fit_extremities(human, lm, verbose=verbose, start=start, jacobian=jacobians.get("extremities"))
        if ext is not None:
            stages["extremities"] = ext
    if stages:
        settle = fit(human, lm, iterations=3, verbose=verbose, build=build, jacobian=rep.get("jacobian"), hold=hold)
        settle["measurements"] += rep["measurements"] + sum(s["measurements"] for s in stages.values())
        settle["seconds"] = round(rep["seconds"] + sum(s["seconds"] for s in stages.values()) + settle["seconds"], 1)
        settle.update(stages)
        rep = settle
    return rep


def build(sheet_resolved, lm, name=None, iterations=10, verbose=True, face=True, start=None):
    human = create(sheet_resolved, name)
    build = sheet_resolved.get("build") if isinstance(sheet_resolved.get("build"), str) else None
    rep = fit_all(human, lm, build=build, start=start, iterations=iterations, verbose=verbose, face=face)
    finish(human, rep)
    return human, rep


def summarize(rep):
    lines = [f"fit: rms {rep['rms_tol']} tolerances after {len(rep['history'])} iteration(s), {rep['seconds']} s; "
             f"rig {rep.get('rig')} ({rep.get('bones_renamed')} bones renamed)"]
    for row in rep["residuals"]:
        flag = "  " if abs(row["tol"]) <= 1 else "!!"
        lines.append(f"  {flag} {row['measure']:15} {row['value']:.3f} target {row['target']:.3f} "
                     f"({row['error_cm']:+.1f} cm, {row['tol']:+.2f} tol)")
    lines.append("  params " + ", ".join(f"{k} {v:+.2f}" for k, v in rep["params"].items()))
    return "\n".join(lines)
