"""wardrobe: layered clothing for rigged Blender bodies headed to Godot.

Loaded inside Blender (through the MCP bridge, or `blender -b --python`). A session is
long-lived and these modules get edited between calls, so always reload before use:

    import sys, importlib
    sys.path.insert(0, r"C:/Users/<you>/.claude/skills/wardrobe/scripts")
    import wardrobe
    importlib.reload(wardrobe)
    wardrobe.reload_all()
"""

import importlib

SCHEMA = "wardrobe/1"
VERSION = "0.1.0"

# dependency order
MODULES = ("rigmap", "tailor", "fit", "skirts", "cover", "hem", "spec", "views", "export", "samples", "presets")


def reload_all():
    """Re-import every submodule. Call after editing any of them."""
    done = []
    for name in MODULES:
        try:
            mod = importlib.import_module("." + name, __name__)
        except ModuleNotFoundError as exc:
            if exc.name == f"{__name__}.{name}":
                continue
            raise
        importlib.reload(mod)
        done.append(mod.__name__)
    return done


def dress(body_name, preset, name=None, colour=None, out_path=None, layer=None, over=(), soft=False):
    """One garment from a preset (`presets.list()`), cut from `body_name`, fitted, hidden and
    exported: see `presets.dress`."""
    from . import presets
    return presets.dress(body_name, preset, name=name, colour=colour, out_path=out_path, layer=layer, over=over,
                         soft=soft)
