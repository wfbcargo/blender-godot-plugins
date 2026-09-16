"""Export a saved creature in a fresh Blender session, from nothing but the .blend.

    blender -b <file.blend> --factory-startup --python tests/fixtures/_export_only.py --
        kind=hop mesh=<mesh> rig=<rig> glb=<out.glb> creature=<name>

Not a fixture (the leading underscore keeps `tools/regress.py` from running it): a fixture that
authored moves saves its .blend and starts this in a second Blender, which has none of the first
session's memory - no `{role: report}` dict - so the exporter must read the reports `move_set`
stored on the actions. It writes `<glb>` and `<glb base>.moves.json`, and prints
`EXPORT_ONLY <json>` with the exporter's answer.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS")


def main():
    a = H.args()
    kind = a.get("kind", "hop")
    if kind == "hop":
        from rig_analysis import hop as mod
    elif kind == "radial":
        from rig_analysis import radial_moves as mod
    else:
        raise ValueError("unknown kind " + repr(kind))
    os.makedirs(os.path.dirname(os.path.abspath(a["glb"])), exist_ok=True)
    result = mod.export_creature(a["mesh"], a["rig"], None, a["glb"], a["creature"])
    print("EXPORT_ONLY " + json.dumps(H.stable(result)))
    if "error" in result:
        sys.exit(1)


try:
    main()
except Exception:                                   # a crash must not look like success
    import traceback
    traceback.print_exc()
    sys.exit(1)
