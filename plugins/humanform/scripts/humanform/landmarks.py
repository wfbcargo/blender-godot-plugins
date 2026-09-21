"""L1: landmarks - where a body's joints and reference points are - from resolved measurements.

    r = sheet.resolve(s)
    lm = landmarks.from_measurements(r["values"], sex="female", style="stylized")
    lm["points"]["shoulder.L"]            # (x, y, z) metres, rest pose
    m = landmarks.as_measurements(lm)     # the dict measure.check() judges
    findings = measure.check(m, "stylized", "female")

Rest pose and frame are the shared contract: metres, Z up, the body faces -Y, its left is +X,
feet on Z = 0, arms `arm_angle` degrees below horizontal (45 by default), legs `stance` metres
wider at the ankle than at the hip.

ANSUR II gives skin landmarks; joint centres are placed from them with the offsets documented in
scripts/derive_anthropometry.py. Depths (y) and the spacing of the hip joints are anatomical
approximations, not measurements - the mesh, not these numbers, is authoritative for them.
"""

from __future__ import annotations

import math
import sys

import numpy as np

_pkg = sys.modules[__package__]
SCHEMA = "humanform-landmarks/1"

# joint heights the stylized warp moves, in order up the body: (preset key, landmark height key)
WARP_KEYS = ("ankle_joint", "knee_joint", "crotch", "hip_joint", "shoulder_joint", "chin")


def _t(entry, sex):
    if entry is None:
        return None
    return entry.get("any") or entry.get(sex)


def _warp(z, src, dst):
    """Piecewise-linear map of heights through matching control points (both start at 0, end at 1)."""
    return float(np.interp(z, src, dst))


FACE_MEASURES = ("nose_breadth", "mouth_breadth", "jaw_breadth", "nose_chin")


def likeness(measures, face):
    """A face's likeness ratios (sheet.FACE_RATIOS, read off a photo) as absolute targets, in place: the body's
    own bizygomatic breadth - ANSUR's, for its size - is the scale, so the face stays the size of the body it is
    on and only its proportions follow the photo. `width_to_height` sets menton-sellion from it, `lower_face`
    then sets the nose's base to the chin from that. Returns the keys it set."""
    face = face or {}
    biz = measures["bizygomatic"]
    set_ = []

    def put(key, value):
        measures[key] = value
        set_.append(key)

    if face.get("width_to_height"):
        put("menton_sellion", biz / face["width_to_height"])
    if face.get("eye_spacing"):
        put("interpupillary", face["eye_spacing"] * biz)
    for ratio, key in (("nose_width", "nose_breadth"), ("mouth_width", "mouth_breadth"), ("jaw_width", "jaw_breadth")):
        if face.get(ratio):
            put(key, face[ratio] * biz)
    if face.get("lower_face"):
        put("nose_chin", face["lower_face"] * measures["menton_sellion"])
    return set_


def from_measurements(v, sex, style="realistic", arm_angle=45.0, stance=0.02, name=None, face=None):
    """Landmarks and target measures for a body from its ANSUR values. `face`: a brief's likeness ratios
    (`likeness`), which replace or add head targets."""
    H = v["stature"]
    presets = _pkg.presets()["presets"]
    real, styl = presets["realistic"]["ratios"], presets["stylized"]["ratios"]

    # heights as fractions of H, from the measurements
    f = {
        "ankle_joint": v["lateralmalleolusheight"] / H + 0.003,
        "knee_joint": v["lateralfemoralepicondyleheight"] / H,
        "crotch": v["crotchheight"] / H,
        "hip_joint": v["trochanterionheight"] / H - 0.003,
        "iliac_crest": v["iliocristaleheight"] / H,
        "waist": v["waistheightomphalion"] / H,
        "tenth_rib": v["tenthribheight"] / H,
        "chest": v["chestheight"] / H,
        "shoulder_joint": v["acromialheight"] / H - 0.024,
        "suprasternale": v["suprasternaleheight"] / H,
        "neck_base": v["cervicaleheight"] / H,
        "chin": _t(real["chin"], sex)[0],
        "head_base": (H - v["tragiontopofhead"]) / H - 0.01,
    }
    lengths = {"upper_arm": v["acromionradialelength"] / H - 0.017, "forearm": v["radialestylionlength"] / H,
               "hand": v["handlength"] / H, "foot": v["footlength"] / H, "ball": v["balloffootlength"] / H}
    widths = {"shoulder_width": v["bideltoidbreadth"], "hip_width": v["hipbreadth"],
              "biacromial": v["biacromialbreadth"]}

    limb_scale = {"upper_arm": 1.0, "forearm": 1.0, "hand": 1.0, "foot": 1.0}
    if style == "stylized":
        # shift each joint height by how far the canon sits from the measured population's mean,
        # dragging everything between them along - so a long-legged person stays longer-legged than
        # the canon, instead of every stylized body snapping to one set of proportions
        src = [0.0] + [f[k] for k in WARP_KEYS] + [1.0]
        dst = [0.0] + [f[k] + _t(styl[k], sex)[0] - _t(real[k], sex)[0] for k in WARP_KEYS] + [1.0]
        # a canon that reorders a measured body's joints would fold it; keep the measured order
        if all(b > a for a, b in zip(dst, dst[1:])):
            f = {k: _warp(z, src, dst) for k, z in f.items()}
        for k in ("upper_arm", "forearm", "hand", "foot"):
            scale = _t(styl[k], sex)[0] / _t(real[k], sex)[0]
            lengths[k] *= scale
            limb_scale[k] = scale
            if k == "foot":
                lengths["ball"] *= scale
        for k, extra in (("shoulder_width", ("biacromial",)), ("hip_width", ())):
            scale = _t(styl[k], sex)[0] / _t(real[k], sex)[0]
            widths[k] *= scale
            for e in extra:
                widths[e] *= scale

    head_scale = (1.0 - f["chin"]) / (1.0 - _t(real["chin"], sex)[0])
    z = {k: r * H for k, r in f.items()}
    L = {k: r * H for k, r in lengths.items()}
    P = {"vertex": (0.0, 0.0, H), "chin": (0.0, -0.06 * H / 1.7, z["chin"])}

    # spine centreline sits behind the body's mid-plane; depth grows from the neck to the chest
    P["head_base"] = (0.0, 0.010, z["head_base"])
    P["neck_base"] = (0.0, 0.020, z["neck_base"])
    P["suprasternale"] = (0.0, -0.06 * H / 1.7, z["suprasternale"])
    P["chest"] = (0.0, 0.030, z["chest"])
    P["tenth_rib"] = (0.0, 0.030, z["tenth_rib"])
    P["waist"] = (0.0, 0.025, z["waist"])
    P["iliac_crest"] = (0.0, 0.020, z["iliac_crest"])
    P["pelvis"] = (0.0, 0.020, z["hip_joint"] + 0.024 * H)
    P["crotch"] = (0.0, 0.0, z["crotch"])

    a = math.radians(arm_angle)
    hip_x = 0.30 * widths["hip_width"]
    sh_x = widths["biacromial"] / 2 - 0.018 * H / 1.75
    for side, s in (("L", 1.0), ("R", -1.0)):
        d = np.array([s * math.cos(a), 0.0, -math.sin(a)])
        sh = np.array([s * sh_x, 0.005, z["shoulder_joint"]])
        el = sh + d * L["upper_arm"]
        wr = el + d * L["forearm"]
        P[f"clavicle.{side}"] = (s * 0.02, -0.01, z["suprasternale"])
        P[f"shoulder.{side}"] = tuple(sh)
        P[f"elbow.{side}"] = tuple(el)
        P[f"wrist.{side}"] = tuple(wr)
        P[f"fingertip.{side}"] = tuple(wr + d * L["hand"])
        ax = s * (hip_x + stance)
        kx = s * (hip_x + stance * (z["hip_joint"] - z["knee_joint"]) / max(z["hip_joint"] - z["ankle_joint"], 1e-6))
        P[f"hip.{side}"] = (s * hip_x, 0.0, z["hip_joint"])
        P[f"knee.{side}"] = (kx, -0.005, z["knee_joint"])
        ank_y = 0.010
        P[f"ankle.{side}"] = (ax, ank_y, z["ankle_joint"])
        heel_y = ank_y + 0.25 * L["foot"]
        P[f"heel.{side}"] = (ax, heel_y, 0.0)
        P[f"ball.{side}"] = (ax + s * 0.008, heel_y - L["ball"], 0.02 * H / 1.7)
        P[f"toe.{side}"] = (ax + s * 0.012, heel_y - L["foot"], 0.012 * H / 1.7)

    lm = {"schema": SCHEMA, "name": name, "sex": sex, "style": style, "stature": H,
            "arm_angle": arm_angle, "stance": stance,
            "points": {k: [round(float(c), 5) for c in p] for k, p in P.items()},
            "measures": {"hand": L["hand"], "foot": L["foot"], "shoulder_width": widths["shoulder_width"],
                         "hip_width": widths["hip_width"], "waist_circ": v["waistcircumference"],
                         "hip_circ": v["buttockcircumference"], "chest_circ": v["chestcircumference"],
                         "waist_breadth": v["waistbreadth"], "waist_depth": v["waistdepth"],
                         "hip_depth": v["buttockdepth"], "chest_depth": v["chestdepth"],
                         "thigh_circ": v["thighcircumference"], "calf_circ": v["calfcircumference"],
                         # ANSUR's biceps is flexed; relaxed mid-arm girth is taken as 0.92 of it (estimate)
                         "upper_arm_circ": 0.92 * v["bicepscircumferenceflexed"], "neck_circ": v["neckcircumference"],
                         # the head, scaled with the canon's head size on a stylized body
                         "interpupillary": v["interpupillarybreadth"] * head_scale,
                         "head_breadth": v["headbreadth"] * head_scale, "head_depth": v["headlength"] * head_scale,
                         "bizygomatic": v["bizygomaticbreadth"] * head_scale,
                         "menton_sellion": v["mentonsellionlength"] * head_scale,
                         "head_circ": v["headcircumference"] * head_scale,
                         # hands and feet, scaled with the canon's hand and foot length on a stylized body
                         "hand_breadth": v["handbreadth"] * limb_scale["hand"],
                         "palm_length": v["palmlength"] * limb_scale["hand"],
                         "wrist_circ": v["wristcircumference"] * limb_scale["hand"],
                         "foot_breadth": v["footbreadthhorizontal"] * limb_scale["foot"],
                         "ankle_circ": v["anklecircumference"] * limb_scale["foot"]}}
    if face:
        lm["likeness"] = likeness(lm["measures"], face)
    return lm


EXTREMITIES = ("hand_breadth", "palm_length", "wrist_circ", "foot_breadth", "ankle_circ")


def as_measurements(lm):
    """The subset of measure.measurements() a landmark set can answer, for measure.check()."""
    P = {k: np.array(p) for k, p in lm["points"].items()}
    H = lm["stature"]

    def mean_z(n):
        return (P[n + ".L"][2] + P[n + ".R"][2]) / 2

    def seg(a, b):
        return float((np.linalg.norm(P[a + ".L"] - P[b + ".L"]) + np.linalg.norm(P[a + ".R"] - P[b + ".R"])) / 2)

    ms = lm["measures"]
    m = {"kind": "landmarks", "object": lm.get("name"), "stature": H, "floor_offset": 0.0,
         "shoulder_z": mean_z("shoulder"), "elbow_z": mean_z("elbow"), "wrist_z": mean_z("wrist"),
         "hip_z": mean_z("hip"), "knee_z": mean_z("knee"), "ankle_z": mean_z("ankle"),
         "crotch_z": float(P["crotch"][2]), "chin_z": float(P["chin"][2]),
         "upper_arm": seg("shoulder", "elbow"), "forearm": seg("elbow", "wrist"),
         "thigh": seg("hip", "knee"), "shin": seg("knee", "ankle"),
         "hand": ms["hand"], "foot": ms["foot"], "shoulder_width": ms["shoulder_width"],
         "hip_width": ms["hip_width"], "waist_circ": ms["waist_circ"], "hip_circ": ms["hip_circ"],
         "chest_circ": ms["chest_circ"], "waist_breadth": ms["waist_breadth"], "waist_depth": ms["waist_depth"],
         "hip_depth": ms["hip_depth"], "chest_depth": ms["chest_depth"], "thigh_circ": ms["thigh_circ"],
         "calf_circ": ms["calf_circ"], "upper_arm_circ": ms["upper_arm_circ"], "neck_circ": ms["neck_circ"]}
    head = ("interpupillary", "head_breadth", "head_depth", "bizygomatic", "menton_sellion", "head_circ")
    for k in head + EXTREMITIES + FACE_MEASURES:
        if k in ms:            # landmark sets saved before hands and feet were measured lack them
            m[k] = ms[k]
    m["head_length"] = H - m["chin_z"]
    m["heads"] = H / m["head_length"]
    return m
