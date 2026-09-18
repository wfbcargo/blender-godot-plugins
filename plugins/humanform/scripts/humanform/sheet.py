"""L0: a character sheet - the brief as data - and the full set of body measurements it implies.

    s = sheet.new(name="Mara", sex="female", age=34, stature=1.72, build="athletic", style="realistic")
    r = sheet.resolve(s)            # every ANSUR II variable, in metres, consistent with the brief
    r["values"]["crotchheight"], r["guessed"], r["notes"]

A body is drawn from ANSUR II as a multivariate normal per sex: whatever the brief fixes
(stature, weight or BMI, age, any measurement, a build's leanings) is conditioned on, and every
other measurement takes its conditional mean - or, with a seed, a draw from its conditional
distribution scaled by `variation`, so bodies differ the way people do: a tall woman gets the
crotch height, arm length and hip breadth tall women have, not a scaled-up average.
"""

from __future__ import annotations

import copy
import json
import os
import sys

import numpy as np

_pkg = sys.modules[__package__]
SCHEMA = "humanform-sheet/1"

# Build words -> what they fix: a BMI, and z-scores (in conditional sd) for measurements.
BUILDS = {
    "slim":      {"bmi": 20.5, "z": {"waistcircumference": -0.6, "buttockcircumference": -0.4}},
    "average":   {"bmi": None, "z": {}},
    "athletic":  {"bmi": 24.0, "z": {"waistcircumference": -1.0, "bideltoidbreadth": 0.8,
                                     "bicepscircumferenceflexed": 0.8, "thighcircumference": 0.3}},
    "muscular":  {"bmi": 27.5, "z": {"waistcircumference": -0.8, "bideltoidbreadth": 1.4, "chestcircumference": 1.0,
                                     "bicepscircumferenceflexed": 1.6, "neckcircumference": 1.0}},
    "curvy":     {"bmi": 25.5, "z": {"waistcircumference": -0.8, "buttockcircumference": 1.2, "hipbreadth": 1.0,
                                     "thighcircumference": 0.8}},
    "soft":      {"bmi": 27.0, "z": {"bicepscircumferenceflexed": -0.5, "waistcircumference": 0.5}},
    "heavy":     {"bmi": 31.0, "z": {"waistcircumference": 0.8}},
}
STYLES = ("realistic", "stylized")
AGE_RANGE = (17.0, 58.0)      # ANSUR II subjects
# MPFB's age slider: 0 is one year old, 1 is ninety
AGE_LIMITS = (1.0, 90.0)
STATURE = {"adult": (1.3, 2.2), "child": (0.6, 2.0)}
# MPFB macros a brief may set directly (0..1): nothing ANSUR measures decides them
MACRO_FIELDS = ("firmness", "proportions", "muscle", "cupsize")
COLOUR_FIELDS = ("skin", "iris")
# humanform.hair presets a brief may name (data/hair_presets.json)
HAIR_PRESETS = ("short_crop", "bob", "bun", "ponytail", "long_loose")
# humanform.brows brow shapes a brief may name (`hair.brow_shape`); "natural" is MPFB's brow card as fitted
BROW_SHAPES = ("natural", "straight", "arched", "soft")


def ansur_path(age):
    """How a body of this age is made: "measured" (fitted to ANSUR II), "aged" (fitted at the top of
    ANSUR's range, then aged by MPFB and its stature restored) or "child" (MPFB's own body at that age,
    its height set to the stature, nothing fitted)."""
    if age is None or AGE_RANGE[0] <= age <= AGE_RANGE[1]:
        return "measured"
    return "aged" if age > AGE_RANGE[1] else "child"


def _data():
    with open(os.path.join(_pkg.DATA, "anthropometry.json"), encoding="utf-8") as fh:
        return json.load(fh)


_CACHE = {}


def anthropometry():
    if "doc" not in _CACHE:
        _CACHE["doc"] = _data()
    return _CACHE["doc"]


def new(name="Human", sex="female", age=None, stature=None, weight=None, bmi=None, build="average",
        style="realistic", measurements=None, seed=None, variation=0.5, budget_tris=30000, notes="",
        firmness=None, proportions=None, muscle=None, cupsize=None, skin=None, iris=None, hair=None):
    """A sheet. Leave anything unknown as None; resolve() fills it and marks it guessed.

    `firmness` (soft 0 .. firm 1), `proportions` (MPFB's regular 0 .. idealised 1), `muscle` (0..1) and
    `cupsize` (a woman's bust, small 0 .. full 1 - the fit never moves it, and still fits ANSUR's chest
    girth around it) are MPFB macros; None leaves MPFB's 0.5, or for muscle the build's value. An adult's muscle is where
    the fit starts and what its build prior holds it near. `skin` and `iris` are screen (sRGB) colours;
    None leaves the body clay and the eyes a mid brown. `hair` is `{"preset": ..., "colour": (r, g, b)}` -
    a `HAIR_PRESETS` name and a screen colour, and optionally `"brow_shape"`, one of `BROW_SHAPES` - read by
    `hair.add(body, sheet=s)` after the body is baked; `pipeline.make` does not build it."""
    return {"schema": SCHEMA, "name": name, "sex": sex, "age": age, "stature": stature, "weight": weight,
            "bmi": bmi, "build": build, "style": style, "measurements": dict(measurements or {}),
            "seed": seed, "variation": variation, "budget_tris": budget_tris, "notes": notes,
            "firmness": firmness, "proportions": proportions, "muscle": muscle, "cupsize": cupsize,
            "skin": None if skin is None else list(skin), "iris": None if iris is None else list(iris),
            "hair": None if hair is None else dict({"preset": hair.get("preset"),
                                                     "colour": None if hair.get("colour") is None else list(hair["colour"])},
                                                    **({"brow_shape": hair["brow_shape"]} if hair.get("brow_shape")
                                                       else {}))}


def validate(s):
    """A list of problems; empty when the sheet can be resolved."""
    p = []
    if s.get("schema") != SCHEMA:
        p.append(f"schema must be {SCHEMA}")
    if s.get("sex") not in ("female", "male"):
        p.append("sex must be 'female' or 'male' (the measurement data is per sex)")
    if s.get("style") not in STYLES:
        p.append(f"style must be one of {STYLES}")
    b = s.get("build")
    if isinstance(b, str) and b not in BUILDS:
        p.append(f"build {b!r} is not one of {sorted(BUILDS)} (or pass a dict with bmi and z)")
    age = s.get("age")
    if age is not None and not AGE_LIMITS[0] <= age <= AGE_LIMITS[1]:
        p.append(f"age {age} is outside {AGE_LIMITS[0]:g}-{AGE_LIMITS[1]:g} years (MPFB's age range)")
    kind = "child" if age is not None and age < AGE_RANGE[0] else "adult"
    lo, hi = STATURE[kind]
    st = s.get("stature")
    if st is not None and not lo <= st <= hi:
        p.append(f"stature {st} m is outside {lo}-{hi} m for {'a child' if kind == 'child' else 'an adult'} "
                 "(is it in metres?)")
    for k in MACRO_FIELDS:
        v = s.get(k)
        if v is not None and not 0.0 <= v <= 1.0:
            p.append(f"{k} {v} must be between 0 and 1 (an MPFB macro)")
    for k in COLOUR_FIELDS:
        v = s.get(k)
        if v is not None and (len(v) != 3 or not all(0.0 <= c <= 1.0 for c in v)):
            p.append(f"{k} must be an (r, g, b) screen colour with channels 0..1")
    hair = s.get("hair")
    if hair is not None:
        if not isinstance(hair, dict) or hair.get("preset") not in HAIR_PRESETS:
            p.append(f"hair must be {{'preset': one of {HAIR_PRESETS}, 'colour': (r, g, b)}}")
        elif hair.get("colour") is not None and (len(hair["colour"]) != 3
                                               or not all(0.0 <= c <= 1.0 for c in hair["colour"])):
            p.append("hair colour must be an (r, g, b) screen colour with channels 0..1")
        elif hair.get("brow_shape") is not None and hair["brow_shape"] not in BROW_SHAPES:
            p.append(f"hair brow_shape {hair['brow_shape']!r} is not one of {BROW_SHAPES}")
    names = set(anthropometry()["variables"])
    for k in s.get("measurements", {}):
        if k not in names:
            p.append(f"measurement {k!r} is not an ANSUR II variable")
    return p


def _condition(mu, cov, idx, values):
    """Gaussian conditioning: mean and covariance of the rest given x[idx] = values."""
    n = len(mu)
    rest = np.array([i for i in range(n) if i not in set(idx)], dtype=int)
    if not len(idx):
        return rest, mu[rest], cov[np.ix_(rest, rest)]
    idx = np.array(idx, dtype=int)
    soo = cov[np.ix_(idx, idx)]
    sro = cov[np.ix_(rest, idx)]
    k = sro @ np.linalg.pinv(soo)
    m = mu[rest] + k @ (np.asarray(values) - mu[idx])
    c = cov[np.ix_(rest, rest)] - k @ sro.T
    return rest, m, c


NOT_MEASURED = "not measured against ANSUR"


def _resolve_child(s):
    """A child: ANSUR II has no children, so nothing is drawn from it. The sheet keeps what the brief
    says; weight is only known when the brief gives it."""
    out = copy.deepcopy(s)
    guessed = [k for k in ("stature", "weight") if s.get(k) is None]
    bmi = s.get("bmi")
    if s.get("weight") is not None and s.get("stature"):
        bmi = s["weight"] / s["stature"] ** 2
    elif bmi is not None and s.get("stature"):
        out["weight"] = round(bmi * s["stature"] ** 2, 1)
        guessed.remove("weight")
    out["bmi"] = None if bmi is None else round(bmi, 1)
    out["guessed"] = guessed
    notes = [f"age {s['age']:g} is below ANSUR II's adults ({AGE_RANGE[0]:g}-{AGE_RANGE[1]:g}): MPFB's own body at "
             f"that age, its height macro set to the stature; {NOT_MEASURED} - no proportion, girth or "
             "length was checked"]
    if s.get("measurements"):
        notes.append("measurements are ignored for a child: there is no fit to hold them")
    if isinstance(s.get("build"), str) and BUILDS.get(s["build"], {}).get("bmi") and s.get("bmi") is None \
            and s.get("weight") is None:
        notes.append(f"build {s['build']!r} sets a child's muscle only; its adult BMI is not used (give bmi)")
    return {"sheet": out, "values": None, "z": None, "guessed": guessed, "notes": notes, "ansur": "child"}


def resolve(s):
    """Fill every ANSUR variable for the sheet. Returns {sheet, values, guessed, notes, z, ansur}.

    `ansur` is `ansur_path(age)`. A child has no values or z-scores. An adult past ANSUR's range is
    resolved at 58 (values["Age"]) while the sheet keeps the real age; both carry a note saying the body
    is not measured against ANSUR."""
    problems = validate(s)
    if problems:
        raise ValueError("; ".join(problems))
    path = ansur_path(s.get("age"))
    if path == "child":
        return _resolve_child(s)
    doc = anthropometry()
    names = doc["variables"]
    sx = doc["sexes"][s["sex"]]
    mu = np.array([sx["variables"][v]["mean"] for v in names])
    cov = np.array(sx["covariance"])
    ix = {v: i for i, v in enumerate(names)}
    out = copy.deepcopy(s)
    guessed, notes = [], []

    fixed = {}
    if s.get("age") is not None:
        a = float(np.clip(s["age"], *AGE_RANGE))
        if a != s["age"]:
            notes.append(f"age {s['age']:g} is past ANSUR II's measured range ({AGE_RANGE[0]:g}-{AGE_RANGE[1]:g}): "
                         f"proportions are fitted at {a:g}, then MPFB's age macro ages the body to {s['age']:g} and "
                         f"its height macro restores the stature. The aged shape is MPFB's, {NOT_MEASURED}; "
                         "a stoop is not modelled.")
        fixed["Age"] = a
    if s.get("stature") is not None:
        fixed["stature"] = float(s["stature"])
    for k, v in s.get("measurements", {}).items():
        fixed[k] = float(v)

    build = s.get("build") or "average"
    spec = BUILDS[build] if isinstance(build, str) else build
    bmi = s.get("bmi") if s.get("bmi") is not None else spec.get("bmi")
    if s.get("weight") is not None:
        fixed["weightkg"] = float(s["weight"])
    elif bmi is not None:
        if "stature" not in fixed:
            fixed["stature"] = float(mu[ix["stature"]])
            guessed.append("stature")
        fixed["weightkg"] = bmi * fixed["stature"] ** 2

    idx = [ix[k] for k in fixed]
    rest, m, c = _condition(mu, cov, idx, [fixed[k] for k in fixed])

    # a build's leanings: set each named measurement z conditional sd from its conditional mean, in turn
    for var, z in spec.get("z", {}).items():
        if var in fixed or var not in ix:
            continue
        j = int(np.flatnonzero(rest == ix[var])[0])
        fixed[var] = float(m[j] + z * np.sqrt(max(c[j, j], 0.0)))
        idx = [ix[k] for k in fixed]
        rest, m, c = _condition(mu, cov, idx, [fixed[k] for k in fixed])

    if s.get("seed") is not None:
        # one correlated draw from what is left free, each measurement kept within 2 sd, scaled down
        rng = np.random.default_rng(int(s["seed"]))
        c_sym = (c + c.T) / 2
        w, vec = np.linalg.eigh(c_sym)
        draw = vec @ (np.sqrt(np.clip(w, 0, None)) * rng.standard_normal(len(w)))
        sd = np.sqrt(np.clip(np.diag(c_sym), 0, None))
        m = m + float(s.get("variation", 0.5)) * np.clip(draw, -2 * sd, 2 * sd)

    values = dict(fixed)
    for j, i in enumerate(rest):
        values[names[i]] = float(m[j])
    for k in ("age", "stature", "weight"):
        if s.get(k) is None and k not in guessed:
            guessed.append(k)

    z = {}
    for v in names:
        sd = sx["variables"][v]["sd"]
        z[v] = round((values[v] - sx["variables"][v]["mean"]) / sd, 2) if sd > 0 else 0.0
    out["age"] = round(values["Age"], 1) if path == "measured" else float(s["age"])
    out["stature"] = round(values["stature"], 4)
    out["weight"] = round(values["weightkg"], 1)
    out["bmi"] = round(values["weightkg"] / values["stature"] ** 2, 1)
    out["guessed"] = guessed
    extreme = [f"{v} ({z[v]:+.1f} sd)" for v in names if abs(z[v]) > 2.5 and v not in fixed]
    if extreme:
        notes.append("beyond 2.5 sd of the measured population: " + ", ".join(extreme))
    return {"sheet": out, "values": values, "z": z, "guessed": guessed, "notes": notes, "ansur": path}


def save(s, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(s, fh, indent=1)


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
