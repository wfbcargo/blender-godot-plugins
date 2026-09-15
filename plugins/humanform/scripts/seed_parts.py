"""Store judged hand and foot designs as library parts, and compose a body that wears them.

    blender -b --factory-startup --python seed_parts.py -- designs=<dir with <who>_<region>_variants.json and
        <who>_<region>_verdict.json, e.g. ../data/seed> out=<dir> [lib=<library folder>] [save=<demo.blend>]

1. For Mara (female, realistic) and Kade (male, stylized) and each region (hands, feet): stores every
   design the batch critic kept, tagged with its tags, and feeds every verdict to the region's statistics.
2. Composes a new person from a stored body, a stored hand part and a stored foot part through the
   pipeline, and reports how closely the hands and feet reached the parts' offset sizes.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

args = dict(a.split("=", 1) for a in sys.argv[sys.argv.index("--") + 1:] if "=" in a) if "--" in sys.argv else {}
if args.get("lib"):
    os.environ["HUMANFORM_LIBRARY"] = args["lib"]

import bpy  # noqa: E402

import humanform  # noqa: E402

humanform.reload_all()
from humanform import library, parts, pipeline, sheet  # noqa: E402

OUT = args["out"]
DESIGNS = args["designs"]
os.makedirs(OUT, exist_ok=True)
print("library:", library.root())


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


stored = {}
for who, sex, style in (("mara", "female", "realistic"), ("kade", "male", "stylized")):
    clear()
    host = None
    for region in ("hands", "feet"):
        stem = os.path.join(DESIGNS, f"{who}_{region}")
        if not os.path.exists(stem + "_verdict.json"):
            print("no verdict for", who, region)
            continue
        with open(stem + "_variants.json", encoding="utf-8") as fh:
            variants = json.load(fh)
        with open(stem + "_verdict.json", encoding="utf-8") as fh:
            verdict = json.load(fh)
        verdict.setdefault("region", region)
        parts.record_verdicts(variants, verdict)
        if host is None:
            res = pipeline.make(sheet.new(name=f"{who}_host", sex=sex, age=30, style=style), use_library=True, eyes=False)
            host = bpy.data.objects[res["human"]]
        for panel in verdict["panels"]:
            v = variants[panel["panel"]]
            if not panel.get("keep") or (not v["targets"] and not v.get("offsets")):
                continue
            card = parts.store(host, region, v, tags=panel["tags"], sex=sex, style=style,
                               critic={"evidence": panel.get("evidence"), "grid": stem + ".png", "panel": panel["panel"],
                                       "refit_max_tol": (v.get("fit") or {}).get("max_tol")})
            stored.setdefault((who, region), []).append(card["id"])
            print(f"part  {region:5} {who} panel {panel['panel']} {card['tags']} (critic: {panel['tags']}) -> {card['id']}")
    for region in ("hands", "feet"):
        print(f"stats {region}: {parts.style_stats(region)['judged']} judged; scale {parts.amplitude_scale(region)}")

hands = stored.get(("kade", "hands")) or stored.get(("mara", "hands"))
feet = stored.get(("kade", "feet")) or stored.get(("mara", "feet"))
if hands and feet:
    clear()
    s = sheet.new(name="Tomas", sex="male", age=38, stature=1.80, build="athletic", style="realistic")
    res = pipeline.make(s, out_dir=os.path.join(OUT, "tomas"), contact_sheet=True, hand_part=hands[0], foot_part=feet[0])
    ext = res["fit"].get("extremities") or {}
    print(f"compose Tomas body {res['path']} (nearest {res['nearest']}) + hands {hands[0]} + feet {feet[0]}: "
          f"{res['timing']['total']:.1f}s check {res['check']} extremities rms {ext.get('rms_tol')} max {ext.get('max_tol')}")
    for row in ext.get("residuals", []):
        print("   ", row)
    if args.get("save"):
        bpy.ops.wm.save_as_mainfile(filepath=args["save"])
        print("saved", args["save"])
print("library items:", len(library.index()["items"]))
