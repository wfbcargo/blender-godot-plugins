"""rig-anything analysis package.

Loaded inside Blender through the MCP bridge. Because a session is long-lived
and these modules get edited between calls, always reload before use:

    import sys, importlib
    sys.path.insert(0, r"C:/Users/<you>/.claude/skills/rig-anything/scripts")
    import rig_analysis
    importlib.reload(rig_analysis)      # picks up a changed module list
    rig_analysis.reload_all()
"""

import importlib
import os

# Modules another plugin or session may add beside these; reloaded when present,
# in this order (octopus imports tentacles).
OPTIONAL = ("tentacles", "octopus")

# Hoppers: `hoppers` (legs, joints, rig, weights), `hop` (gaits and jumps) and
# their test bodies. Loaded after locomotion and actions, which `hop` imports.
HOPPERS = ("hoppers", "hopper_samples", "hop")

# The pictures a build is judged from: the review sheet and the close-up look set (lit, aimed from bones).
PICTURES = ("review", "closeups")


def reload_all():
    """Re-import every submodule. Call after editing any of them.

    This function does not reload the package itself, so a list changed here
    is not seen until `importlib.reload(rig_analysis)` - a new module left off
    the stale list kept running its old code while its file was already fixed."""
    from . import (stored, measure, verify, views, report, fit, skin, decompose, build, gait,
                   export, bodymap, motion, keyposes, upper, actions, locomotion, wings,
                   flight, maw, fins, swim, radial, radial_moves, radial_samples)
    # dependency order: stored imports nothing of ours; actions imports keyposes, motion and bodymap; flight
    # imports all of them; radial_moves imports radial and swim
    mods = [stored, measure, verify, views, report, fit, skin, decompose, build, gait, export,
            wings, maw, fins, radial, bodymap, motion, keyposes, upper, actions, locomotion,
            flight, swim,
            radial_moves, radial_samples]
    here = os.path.dirname(__file__)
    for name in HOPPERS + PICTURES + OPTIONAL:
        if os.path.exists(os.path.join(here, name + ".py")):
            mods.append(importlib.import_module("." + name, __name__))
    for m in mods:
        importlib.reload(m)
    return [m.__name__ for m in mods]
