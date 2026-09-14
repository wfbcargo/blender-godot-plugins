"""follow-through: secondary motion for Blender assets headed to Godot.

Loaded inside Blender through the MCP bridge. A session is long-lived and these
modules get edited between calls, so always reload before use:

    import sys, importlib
    sys.path.insert(0, r"C:/Users/<you>/.claude/skills/follow-through/scripts")
    import follow_through
    importlib.reload(follow_through)     # picks up a changed module list
    follow_through.reload_all()
"""

import importlib

SCHEMA = "follow-through/1"
VERSION = "0.1.0"

# dependency order: classify imports measure; spec imports classify; the
# libraries import spec; export imports spec and the libraries.
MODULES = ("measure", "views", "classify", "spec", "cloth", "export", "samples")


def reload_all():
    """Re-import every submodule. Call after editing any of them."""
    done = []
    for name in MODULES:
        try:
            mod = importlib.import_module("." + name, __name__)
        except ModuleNotFoundError as exc:
            if exc.name == f"{__name__}.{name}":
                continue          # not written yet
            raise
        importlib.reload(mod)
        done.append(mod.__name__)
    return done
