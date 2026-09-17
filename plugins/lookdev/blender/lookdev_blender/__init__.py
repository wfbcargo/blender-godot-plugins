"""lookdev Blender tools: material lint, texture baking, glTF export settings,
and AgX reference renders that line up with Godot's tonemapper.

Loaded inside Blender through the blender MCP server. The session is
long-lived and these modules may be edited between calls, so reload first:

    import sys
    P = r"C:/Users/<you>/.claude/skills/lookdev/blender"
    if P not in sys.path:
        sys.path.insert(0, P)
    import lookdev_blender
    lookdev_blender.reload_all()
    from lookdev_blender import material_lint, bake, export, reference, hair
"""

import importlib


def reload_all():
    """Re-import every submodule. Call after editing any of them."""
    from . import pbr, material_lint, bake, export, reference, hair
    mods = (pbr, material_lint, bake, export, reference, hair)
    for m in mods:
        importlib.reload(m)
    return [m.__name__ for m in mods]
