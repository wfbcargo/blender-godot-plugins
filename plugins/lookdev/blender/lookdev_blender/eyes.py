"""The eye material preset: an eyeball that reads alive in Godot.

    from lookdev_blender import eyes
    mats, rep = eyes.materials(iris_srgb=(0.22, 0.14, 0.09), names={"iris": "HF_iris_Marco_eyes"})

An eye reads as an eye from three things, and none of them survived glTF before this preset, because
the eye materials carried no `lookdev` extras at all and the Godot addon skipped them:

- **A wet cornea.** The whole ball is covered by the tear film, which is what makes the small hard
  catchlight a live eye always has. glTF cannot carry a clearcoat, so it rides in the extras and
  `godot/addons/lookdev/lookdev_materials.gd` sets `clearcoat_*` after import. The base stays diffuse
  tissue; the coat alone makes the highlight, so the sclera does not turn into plastic.
- **A limbal ring.** Real irises are bounded by a darker ring. It also hides the facet boundary between
  the iris and sclera material slots, which on a 32-segment sphere is a visible polygon edge - the
  defect every benchmark critic named as "a faceted iris polygon".
- **A pupil that stays a hole.** An iris colour written as sRGB in a brief converts to a linear value
  that can sit almost on top of the pupil's. On the benchmark's three characters the iris was 6.97x the
  pupil's luminance (read as a distinct disc), 2.14x and 1.35x (both read as one dark blob). So the
  pupil is fixed at `pupil_linear` and the iris is lifted to at least `iris_floor_ratio` times its
  luminance, which is reported as `iris_lifted` rather than done silently.

The caller owns the mesh: it decides which faces take which of the four slots (`slot_for_angle` gives
the preset's answer from a face's angle off the gaze axis). This module only makes materials.
"""

from __future__ import annotations

import json
import os

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
PRESETS = os.path.normpath(os.path.join(HERE, "..", "..", "presets", "materials.json"))

PARTS = ("sclera", "iris", "limbal", "pupil")
DEFAULT_NAMES = {p: f"LD_eye_{p}" for p in PARTS}
# a mid brown, the same default humanform's eyes.py has carried
DEFAULT_IRIS = (0.537, 0.437, 0.313)


def presets():
    with open(PRESETS, encoding="utf-8") as fh:
        return json.load(fh)["materials"]


def preset(name="eye", **overrides):
    p = presets().get(name)
    if p is None:
        raise KeyError(f"no material preset {name!r} (have: {sorted(presets())})")
    p = json.loads(json.dumps(p))
    for k, v in overrides.items():
        if k not in p:
            raise KeyError(f"material preset {name!r} has no field {k!r}")
        p[k] = v
    return p


def _srgb_to_linear(c):
    c = min(max(float(c), 0.0), 1.0)
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luma(lin):
    """Rec. 709 relative luminance of a linear colour."""
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def slot_for_angle(deg, p=None):
    """Which of PARTS a face belongs to, from its angle off the gaze axis in degrees.

    The limbal ring is the outermost `limbal_width_deg` of the iris, so a mesh that used to split at
    `iris_half_angle` keeps the same outer edge and loses no iris area to the ring."""
    p = p or preset()
    if deg < p["pupil_half_angle"]:
        return "pupil"
    if deg < p["iris_half_angle"] - p["limbal_width_deg"]:
        return "iris"
    if deg < p["iris_half_angle"]:
        return "limbal"
    return "sclera"


def colours(iris_srgb=None, preset_name="eye", **overrides):
    """The four linear colours the preset gives for an iris, and what it had to change.

    Returns (colours, report). `report["iris_lifted"]` is None when the brief's iris was already far
    enough above the pupil, or {"was", "now", "ratio_was", "ratio_now"} when it was not."""
    p = preset(preset_name, **overrides)
    iris_lin = [_srgb_to_linear(c) for c in (iris_srgb if iris_srgb is not None else DEFAULT_IRIS)[:3]]
    pupil_lin = [float(p["pupil_linear"])] * 3
    pupil_luma = luma(pupil_lin)
    # a little over the floor, not exactly on it: the colour is written to the glb as a float32 and
    # `lookdev eyes` re-reads it, so landing on the line makes the check fail on rounding alone
    floor = float(p["iris_floor_ratio"]) * pupil_luma
    target = floor * float(p["iris_lift_margin"])
    lifted = None
    if luma(iris_lin) < floor:
        was, ratio_was = list(iris_lin), luma(iris_lin) / pupil_luma
        # scale the hue up rather than washing it toward grey, so a dark brown eye stays brown
        k = target / max(luma(iris_lin), 1e-9)
        iris_lin = [min(1.0, c * k) for c in iris_lin]
        lifted = {"was": [round(c, 4) for c in was], "now": [round(c, 4) for c in iris_lin],
                  "ratio_was": round(ratio_was, 2), "ratio_now": round(luma(iris_lin) / pupil_luma, 2)}
    out = {
        "sclera": [_srgb_to_linear(c) for c in p["sclera_srgb"]],
        "iris": iris_lin,
        "limbal": [c * float(p["limbal_darken"]) for c in iris_lin],
        "pupil": pupil_lin,
    }
    rep = {"iris_lifted": lifted, "iris_pupil_ratio": round(luma(out["iris"]) / pupil_luma, 2),
           "floor_ratio": float(p["iris_floor_ratio"])}
    return out, rep


def _coat(bsdf, p):
    """Blender's Principled coat, so an EEVEE review tile shows the same catchlight Godot will.

    The socket names moved between Blender versions ("Clearcoat" before 4.0, "Coat Weight" after), so
    they are looked up and skipped when absent rather than assumed."""
    got = {}
    for names, value in ((("Coat Weight", "Clearcoat"), p["godot"]["clearcoat"]),
                         (("Coat Roughness", "Clearcoat Roughness"), p["godot"]["clearcoat_roughness"])):
        for n in names:
            if n in bsdf.inputs:
                bsdf.inputs[n].default_value = float(value)
                got[n] = float(value)
                break
    return got


def materials(iris_srgb=None, names=None, preset_name="eye", **overrides):
    """The four eye materials, reused and rebuilt by name.

    `names` maps any of PARTS to a material name; the rest take DEFAULT_NAMES. Every part carries the
    same `lookdev` extras, because the cornea covers the whole ball - only the base colour differs.

    Returns ({part: material}, report)."""
    p = preset(preset_name, **overrides)
    names = dict(DEFAULT_NAMES, **(names or {}))
    cols, rep = colours(iris_srgb, preset_name, **overrides)
    g = dict(p["godot"])
    mats, coat = {}, {}
    for part in PARTS:
        mat = bpy.data.materials.get(names[part]) or bpy.data.materials.new(names[part])
        mat.use_nodes = True
        bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        lin = cols[part]
        bsdf.inputs["Base Color"].default_value = (*lin, 1.0)
        bsdf.inputs["Roughness"].default_value = float(p["roughness"])
        coat = _coat(bsdf, p)
        mat.diffuse_color = (*lin, 1.0)
        mat["lookdev"] = {"preset": preset_name, "godot": g, "part": part}
        mats[part] = mat
    rep.update({"materials": {k: v.name for k, v in mats.items()},
                "colours_linear": {k: [round(c, 4) for c in v] for k, v in cols.items()},
                "godot_extras": g, "blender_coat": coat,
                "angles": {"pupil": p["pupil_half_angle"], "iris": p["iris_half_angle"],
                           "limbal_width": p["limbal_width_deg"]}})
    return mats, rep
