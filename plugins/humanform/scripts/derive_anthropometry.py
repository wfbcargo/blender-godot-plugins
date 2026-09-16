"""Derive data/anthropometry.json from the ANSUR II public CSVs.

    "C:/Program Files/Blender Foundation/Blender 5.2/5.2/python/bin/python.exe" derive_anthropometry.py

ANSUR II (US Army, 2012; published 2017 by Penn State's OpenLab): 4,082 men and 1,986 women aged
17-58, 93 direct measurements. CSVs: data/sources/ansur2/. Lengths are millimetres and weightkg is
hectograms; everything is written in metres and kilograms.

Per sex: n, mean, sd, percentiles, the mean and sd of each length as a fraction of stature, and
the covariance of every variable, so a body can be sampled or conditioned on known values (a
tall woman keeps a matching crotch height, arm length and hip breadth).
"""

import csv
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "data", "sources", "ansur2")
OUT = os.path.join(ROOT, "data", "anthropometry.json")

VARIABLES = [
    # heights, standing
    "stature", "acromialheight", "axillaheight", "suprasternaleheight", "cervicaleheight", "chestheight",
    "tenthribheight", "waistheightomphalion", "iliocristaleheight", "trochanterionheight", "buttockheight",
    "crotchheight", "wristheight", "lateralfemoralepicondyleheight", "kneeheightmidpatella", "tibialheight",
    "lateralmalleolusheight", "sittingheight",
    # limb lengths
    "acromionradialelength", "radialestylionlength", "shoulderelbowlength", "handlength", "palmlength",
    "footlength", "balloffootlength", "span", "shoulderlength",
    # breadths and depths
    "biacromialbreadth", "bideltoidbreadth", "chestbreadth", "waistbreadth", "hipbreadth", "bicristalbreadth",
    "chestdepth", "waistdepth", "buttockdepth", "handbreadth", "footbreadthhorizontal", "heelbreadth",
    "bimalleolarbreadth",
    # circumferences
    "neckcircumference", "neckcircumferencebase", "shouldercircumference", "chestcircumference",
    "waistcircumference", "buttockcircumference", "thighcircumference", "lowerthighcircumference",
    "calfcircumference", "anklecircumference", "bicepscircumferenceflexed", "forearmcircumferenceflexed",
    "wristcircumference",
    # head
    "headcircumference", "headbreadth", "headlength", "mentonsellionlength", "tragiontopofhead",
    "bizygomaticbreadth", "interpupillarybreadth", "earlength", "earbreadth", "earprotrusion",
    # mass and age
    "weightkg", "Age",
]
NOT_LENGTH = {"weightkg", "Age"}
# the public CSV records interpupillary breadth in tenths of a millimetre (female mean 617 = 61.7 mm);
# every other length is in millimetres
TENTH_MM = {"interpupillarybreadth"}


def load(path):
    with open(path, encoding="latin-1", newline="") as fh:
        rows = list(csv.DictReader(fh))
    data = np.array([[float(r[v]) for v in VARIABLES] for r in rows], dtype=np.float64)
    for j, v in enumerate(VARIABLES):
        if v == "weightkg":
            data[:, j] /= 10.0          # hectograms -> kg
        elif v in TENTH_MM:
            data[:, j] /= 10000.0       # 0.1 mm -> m
        elif v not in NOT_LENGTH:
            data[:, j] /= 1000.0        # mm -> m
    return data


def summarise(data):
    stature = data[:, VARIABLES.index("stature")]
    out = {"n": int(len(data)), "variables": {}}
    for j, v in enumerate(VARIABLES):
        col = data[:, j]
        entry = {"mean": round(float(col.mean()), 5), "sd": round(float(col.std(ddof=1)), 5),
                 "p": {str(q): round(float(np.percentile(col, q)), 5) for q in (1, 5, 25, 50, 75, 95, 99)}}
        if v not in NOT_LENGTH and v != "stature":
            r = col / stature
            entry["ratio_mean"] = round(float(r.mean()), 5)
            entry["ratio_sd"] = round(float(r.std(ddof=1)), 5)
        out["variables"][v] = entry
    out["covariance"] = [[round(float(c), 9) for c in row] for row in np.cov(data, rowvar=False)]
    return out


# Surface landmarks -> joint centres, as fractions of stature. ANSUR measures skin landmarks; a
# rig needs joint centres. Offsets are anatomical approximations, stated here once:
#   shoulder: glenohumeral centre ~4 cm below the acromion at 1.75 m        -> acromialheight - 0.024 H
#   hip:      femoral head centre ~level with the greater trochanter tip     -> trochanterionheight - 0.003 H
#   knee:     flexion axis through the femoral epicondyles                   -> lateralfemoralepicondyleheight
#   ankle:    talocrural axis just above the lateral malleolus's centre      -> lateralmalleolusheight + 0.003 H
#   elbow:    radiale marks the joint line; the humerus runs from the GH centre, ~3 cm below the acromion
#             along the arm                                                  -> acromionradialelength - 0.017 H
JOINTS = {
    "shoulder_joint": ("acromialheight", -0.024),
    "hip_joint": ("trochanterionheight", -0.003),
    "knee_joint": ("lateralfemoralepicondyleheight", 0.0),
    "ankle_joint": ("lateralmalleolusheight", 0.003),
    "crotch": ("crotchheight", 0.0),
    "upper_arm": ("acromionradialelength", -0.017),
    "forearm": ("radialestylionlength", 0.0),
    "hand": ("handlength", 0.0),
    "foot": ("footlength", 0.0),
    "shoulder_width": ("bideltoidbreadth", 0.0),
    "hip_width": ("hipbreadth", 0.0),
}


def derived(data):
    """Per-subject quantities that are not single ANSUR columns: their mean and sd."""
    c = {v: data[:, j] for j, v in enumerate(VARIABLES)}
    H = c["stature"]
    hip = c["trochanterionheight"] / H - 0.003
    knee = c["lateralfemoralepicondyleheight"] / H
    ankle = c["lateralmalleolusheight"] / H + 0.003
    q = {
        "thigh": hip - knee,
        "shin": knee - ankle,
        "hip_above_crotch": hip - c["crotchheight"] / H,
        "shoulder_to_hip_width": c["bideltoidbreadth"] / c["hipbreadth"],
        "waist_to_hip_circ": c["waistcircumference"] / c["buttockcircumference"],
        "bmi": c["weightkg"] / H ** 2,
    }
    return {k: {"mean": round(float(v.mean()), 5), "sd": round(float(v.std(ddof=1)), 5),
                "p": {str(p): round(float(np.percentile(v, p)), 5) for p in (1, 5, 50, 95, 99)}} for k, v in q.items()}


def realistic_preset(doc):
    """The realistic preset's targets: ANSUR means per sex, warn band 1.5 sd, fail band 3 sd."""
    ratios = {}
    for key, (var, off) in JOINTS.items():
        entry = {"source": f"ANSUR II {var}" + (f" {off:+.3f} H (joint centre)" if off else "")}
        for sex in ("female", "male"):
            v = doc["sexes"][sex]["variables"][var]
            entry[sex] = [round(v["ratio_mean"] + off, 4), round(max(1.5 * v["ratio_sd"], 0.006), 4)]
        ratios[key] = entry
    for key in ("thigh", "shin"):
        entry = {"source": f"ANSUR II, per subject from the joint centres above"}
        for sex in ("female", "male"):
            d = doc["sexes"][sex]["derived"][key]
            entry[sex] = [round(d["mean"], 4), round(max(1.5 * d["sd"], 0.006), 4)]
        ratios[key] = entry
    ratios["chin"] = {"any": [0.870, 0.012], "source": "Drillis & Contini; ANSUR II has no menton height"}
    derived_ = {}
    for key in ("shoulder_to_hip_width", "waist_to_hip_circ"):
        entry = {"source": "ANSUR II, per subject"}
        for sex in ("female", "male"):
            d = doc["sexes"][sex]["derived"][key]
            entry[sex] = [round(d["mean"], 3), round(1.5 * d["sd"], 3)]
        derived_[key] = entry
    return {"label": "Realistic adult (ANSUR II means; warn beyond 1.5 sd, fail beyond 3 sd)",
            "heads": {"any": [7.7, 0.35], "source": "1 / (1 - chin 0.870): the same head length the chin target implies"},
            "ratios": ratios, "derived": derived_}


def main():
    doc = {
        "schema": "humanform-anthropometry/1",
        "source": "ANSUR II public data (US Army Natick, 2012 survey; OpenLab, Penn State, 2017)",
        "units": "metres; weightkg in kg; Age in years",
        "variables": VARIABLES,
        "sexes": {},
    }
    for sex, fname in (("male", "ANSUR_II_MALE_Public.csv"), ("female", "ANSUR_II_FEMALE_Public.csv")):
        data = load(os.path.join(SRC, fname))
        doc["sexes"][sex] = summarise(data)
        doc["sexes"][sex]["derived"] = derived(data)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"))

    presets_path = os.path.join(ROOT, "data", "presets.json")
    with open(presets_path, encoding="utf-8") as fh:
        presets = json.load(fh)
    presets["presets"]["realistic"] = realistic_preset(doc)
    presets["notes"] = ("Heights and lengths are fractions of stature H (floor to top of skull); joint heights are "
                        "joint centres, as a rig places them. [target, tol]: warn outside tol, fail outside twice "
                        "tol. Keys female/male, or any. The realistic preset is generated by "
                        "scripts/derive_anthropometry.py from ANSUR II - edit the script, not this block.")
    with open(presets_path, "w", encoding="utf-8") as fh:
        json.dump(presets, fh, indent=2)
    print("wrote realistic preset into", presets_path)
    for sex in ("male", "female"):
        s = doc["sexes"][sex]["variables"]
        print(sex, doc["sexes"][sex]["n"], "stature", s["stature"]["mean"],
              "| ratios:", {k: s[k]["ratio_mean"] for k in (
                  "acromialheight", "trochanterionheight", "crotchheight", "lateralfemoralepicondyleheight",
                  "lateralmalleolusheight", "wristheight", "acromionradialelength", "radialestylionlength",
                  "shoulderelbowlength", "handlength", "footlength", "span", "biacromialbreadth",
                  "bideltoidbreadth", "hipbreadth", "cervicaleheight", "suprasternaleheight")})
    print("wrote", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
