"""humanform: build and judge adult human bodies in Blender for Godot.

Loaded inside Blender (through the MCP bridge, or `blender -b --python`). A session is
long-lived and these modules get edited between calls, so always reload before use:

    import sys, importlib
    sys.path.insert(0, r"C:/Users/<you>/.claude/skills/humanform/scripts")
    import humanform
    importlib.reload(humanform)
    humanform.reload_all()

Conventions shared with rig-anything, follow-through and wardrobe: metres, Z up, the body
faces -Y, the body's left is +X, feet on Z = 0.
"""

import importlib
import json
import os

SCHEMA = "humanform/1"
VERSION = "0.5.0"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")

# dependency order
MODULES = ("body", "slicing", "sheet", "landmarks", "skeleton", "measure", "views", "scaffold", "library", "parts", "look", "eyes", "pipeline")


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


def presets():
    with open(os.path.join(DATA, "presets.json"), encoding="utf-8") as fh:
        return json.load(fh)
