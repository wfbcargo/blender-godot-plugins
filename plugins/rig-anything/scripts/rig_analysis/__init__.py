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
    from . import (measure, verify, views, report, fit, skin, decompose, build, gait,
                   export, bodymap, motion, keyposes, actions, locomotion, wings, flight,
                   maw, fins, swim)
    # dependency order: actions imports keyposes, motion and bodymap; flight
    # imports all of them
    mods = (measure, verify, views, report, fit, skin, decompose, build, gait, export,
            wings, maw, fins, bodymap, motion, keyposes, actions, locomotion, flight, swim)
    for m in mods:
        importlib.reload(m)
    return [m.__name__ for m in mods]
