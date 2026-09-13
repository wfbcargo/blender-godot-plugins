"""Colour conversions and plausible-value checks shared by the other modules.

Blender socket colours (default_value) are scene-linear. The PBR validation
ranges people quote (Filament, DONTNOD: base colour 30/50-240 sRGB, metals
170-255) are in 8-bit sRGB, so convert before comparing.
"""

from __future__ import annotations


def linear_to_srgb(c: float) -> float:
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def srgb8(rgb) -> tuple[int, int, int]:
    return tuple(int(round(linear_to_srgb(v) * 255)) for v in rgb[:3])


def albedo_problems(rgb_linear, metallic: float, emissive: bool = False) -> list[tuple[str, str, str]]:
    """(severity, code, message) for a constant base colour."""
    out = []
    r, g, b = srgb8(rgb_linear)
    mx, mn = max(r, g, b), min(r, g, b)
    if metallic >= 0.5:
        if mx < 170:
            out.append(("warn", "METAL_TOO_DARK",
                        f"metal base colour ({r},{g},{b}) sRGB is below 170. For metals base colour is the "
                        "specular reflectance: iron ~196, aluminium ~232, gold (255,220,145). Darken with roughness or dirt."))
    elif not emissive:
        if mx < 30:
            out.append(("warn", "ALBEDO_TOO_DARK",
                        f"base colour ({r},{g},{b}) sRGB is darker than real dielectrics (charcoal ~40-56). "
                        "It kills bounce light and reads as a hole."))
        if mx > 240:
            out.append(("warn", "ALBEDO_TOO_BRIGHT",
                        f"base colour ({r},{g},{b}) sRGB is brighter than real surfaces (fresh snow ~240, white paint 215-230)."))
        if mx > 60 and (mx - mn) / mx > 0.85:
            out.append(("info", "ALBEDO_SATURATED",
                        f"base colour ({r},{g},{b}) is nearly fully saturated; natural materials rarely exceed ~0.6."))
    if 0.1 < metallic < 0.9:
        out.append(("warn", "METALLIC_PARTIAL",
                    f"metallic {metallic:.2f}: surfaces are metal or not. In-between is only for masked transitions."))
    return out
