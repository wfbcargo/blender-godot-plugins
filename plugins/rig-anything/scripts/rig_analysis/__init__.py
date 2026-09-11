"""rig-anything analysis package.

Loaded inside Blender through the MCP bridge. Because a session is long-lived
and these modules get edited between calls, always reload before use:

    import sys, importlib
    sys.path.insert(0, r"C:/Users/<you>/.claude/skills/rig-anything/scripts")
    import rig_analysis
    rig_analysis.reload_all()
"""

import importlib


def reload_all():
    """Re-import every submodule. Call after editing any of them."""
    from . import measure, verify, views, report
    for m in (measure, verify, views, report):
        importlib.reload(m)
    return [m.__name__ for m in (measure, verify, views, report)]
