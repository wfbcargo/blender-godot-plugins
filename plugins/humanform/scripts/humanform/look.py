"""Colours and plain materials: a description gives screen colours, the shader takes linear ones.

    look.srgb_to_linear((0.55, 0.40, 0.33))      # (0.263, 0.133, 0.089) - what Base Color wants
    look.skin(human, (0.55, 0.40, 0.33))         # one Principled skin material on the whole body
    look.material("HF_iris_x", srgb=(0.54, 0.44, 0.31), roughness=0.35)

A colour picked on screen, read off a photo or written in a brief (`skin`, `iris`) is sRGB. Blender's
Principled Base Color is scene-linear, and so is glTF's baseColorFactor, so every such colour is
converted once, here, with the exact IEC 61966-2-1 curve (a linear toe below 0.04045, a 2.4 power
above). `c ** 2.2` is close at mid-grey (2% off at 0.5) but not in the darks: at 0.05 it gives a
third of the true value, and dark irises and deep skin tones live there.

`material` makes flat colours. `skin` makes real skin (`humanform.skin`): on an MPFB human it marks the
regions (lips, areolae, palms, soles, knees, elbows, genital skin, flushed cheeks, an oily T-zone) and gives it a
FLAT Principled skin with subsurface (the brief's tone as Base Color, so a body exported without a bake still
arrives in its colour); on a game mesh (rig-anything's `bake_for_game`, which keeps the marks) it bakes the
procedural skin into albedo, roughness and normal maps glTF carries, with the brief's colour as the albedo's
mean. If the bake cannot run (no lookdev) the material stays flat. `skin(..., realistic=False)` is the old flat material.
"""

from __future__ import annotations

import bpy

SKIN_ROUGHNESS = 0.55


def _one(c, forward):
    c = min(max(float(c), 0.0), 1.0)
    if forward:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def srgb_to_linear(colour):
    """A screen (sRGB) value or RGB(A) tuple, each channel 0..1, as scene-linear. Alpha is left as it is."""
    if isinstance(colour, (int, float)):
        return _one(colour, True)
    c = tuple(colour)
    return tuple(_one(v, True) for v in c[:3]) + tuple(float(v) for v in c[3:])


def linear_to_srgb(colour):
    """The inverse: a scene-linear value or RGB(A) tuple as sRGB."""
    if isinstance(colour, (int, float)):
        return _one(colour, False)
    c = tuple(colour)
    return tuple(_one(v, False) for v in c[:3]) + tuple(float(v) for v in c[3:])


def material(name, srgb=None, roughness=0.5, linear=None):
    """A Principled BSDF material with a flat colour, reused by name. Give `srgb` (a screen colour, the
    usual case) or `linear` (already scene-linear)."""
    if (srgb is None) == (linear is None):
        raise ValueError("give exactly one of srgb or linear")
    lin = tuple(linear)[:3] if linear is not None else srgb_to_linear(srgb)[:3]
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*lin, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = (*lin, 1.0)
    return mat


SKIN_MAP_PX = 1024     # the skin maps' size when a caller does not say (draft budget; a final build wants 2048)


def _is_mpfb_human(ob):
    """An unbaked MPFB human still has MPFB's joint groups; `bake_for_game` removes them."""
    return any(g.name.startswith("joint-") for g in ob.vertex_groups)


def skin(ob, srgb, roughness=SKIN_ROUGHNESS, name=None, realistic=True, size=None):
    """Give a body mesh one skin material (`<object name>_skin` unless named): every other material slot
    is removed and every face uses it. Returns the material.

    `realistic` (the default) makes it `humanform.skin`'s: on an MPFB human the regions are marked and the
    material is flat (tone, subsurface) until a bake; on any other mesh (a baked game mesh carries the marks) it is baked to maps of
    `size` px (`SKIN_MAP_PX`), packed in the .blend. The bake's report is on the material as
    `humanform_skin`. `realistic=False` is a flat colour at `roughness`."""
    ob = bpy.data.objects[ob] if isinstance(ob, str) else ob
    name = name or f"{ob.name}_skin"
    if realistic:
        from . import skin as _skin
        mat = _skin.material(name, srgb)
    else:
        mat = material(name, srgb=srgb, roughness=roughness)
    me = ob.data
    me.materials.clear()
    me.materials.append(mat)
    if len(me.polygons):
        me.polygons.foreach_set("material_index", [0] * len(me.polygons))
    me.update()
    if realistic:
        if _is_mpfb_human(ob):
            rep = _skin.mark(ob)
            mat["humanform_skin"] = dict(mat["humanform_skin"], stage="flat", marked=rep["regions"],
                                         notes=rep["notes"])
        else:
            if _skin.TINT not in me.attributes:
                _skin.unmarked(ob)
            rep = _skin.bake(ob, mat, size=size or SKIN_MAP_PX)
            info = {k: rep[k] for k in ("size", "tone_target", "baked", "tone_error", "tone_ok", "regions", "contrast",
                                         "contrast_ok", "contrast_fail", "roughness") if k in rep}
            mat["humanform_skin"] = dict(mat["humanform_skin"], stage="baked" if "error" not in rep else "flat",
                                         error=rep.get("error", ""), **info)
    return mat
