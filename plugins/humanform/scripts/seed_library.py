"""Seed a humanform library: fitted bodies, judged face parts, and a composition that reuses both.

    blender -b --factory-startup --python seed_library.py -- faces=<dir with *_variants.json and *_verdict.json, e.g. ../data/seed>
        out=<dir> [lib=<library folder>] [save=<demo.blend>]

1. Builds the five reference briefs through the pipeline and stores each as a body card with its
   contact sheet as the thumbnail.
2. Stores every face design a batch critic kept as a part, tagged with the critic's tags, and feeds
   every verdict to the style statistics that tune future designs.
3. Composes two new people from stored assets - a warm-started body plus a stored face part - and
   renders their contact sheets, to show the parts transfer.
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
FACES = args["faces"]
os.makedirs(OUT, exist_ok=True)
print("library:", library.root())


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


REFERENCE = [
    (sheet.new(name="Mara", sex="female", age=34, stature=1.72, build="athletic", style="realistic"), ["reference"]),
    (sheet.new(name="Otto", sex="male", age=52, stature=1.68, build="heavy", style="realistic"), ["reference"]),
    (sheet.new(name="Juno", sex="female", age=24, build="curvy", style="stylized"), ["reference"]),
    (sheet.new(name="Kade", sex="male", age=29, stature=1.88, build="muscular", style="stylized"), ["reference", "hero"]),
    (sheet.new(name="Wren", sex="female", age=61, stature=1.55, build="slim", style="realistic", seed=7), ["reference"]),
]
for s, tags in REFERENCE:
    clear()
    res = pipeline.make(s, out_dir=os.path.join(OUT, s["name"].lower()), store=True, contact_sheet=True,
                        tags=tags + [s["build"], s["style"]])
    print(f"body  {s['name']:5} {res['path']:6} {res['timing']['total']:5.1f}s check {res['check']} -> {res['stored']}")

stored_parts = {}
for who, sex, style in (("mara", "female", "realistic"), ("kade", "male", "stylized")):
    with open(os.path.join(FACES, f"{who}_variants.json"), encoding="utf-8") as fh:
        variants = json.load(fh)
    with open(os.path.join(FACES, f"{who}_verdict.json"), encoding="utf-8") as fh:
        verdict = json.load(fh)
    parts.record_verdicts(variants, verdict)
    clear()
    base = pipeline.make(sheet.new(name=f"{who}_host", sex=sex, age=30, style=style), use_library=True, eyes=False)
    host = bpy.data.objects[base["human"]]
    for panel in verdict["panels"]:
        if not panel.get("keep"):
            continue
        card = parts.store(host, "face", variants[panel["panel"]], tags=panel["tags"], sex=sex, style=style,
                           critic={"evidence": panel.get("evidence"), "grid": os.path.join(FACES, f"{who}_faces.png"),
                                   "panel": panel["panel"]})
        stored_parts[(who, panel["panel"])] = card["id"]
        print(f"part  face {who} panel {panel['panel']} {panel['tags']} -> {card['id']}")

print("style stats:", parts.style_stats("face")["judged"], "judged; amplitude scale", parts.amplitude_scale("face"))

COMPOSED = [
    (sheet.new(name="Bram", sex="male", age=47, stature=1.71, build="heavy", style="realistic"), ("kade", 8)),
    (sheet.new(name="Ines", sex="female", age=31, stature=1.70, build="athletic", style="realistic"), ("mara", 7)),
]
clear()
for i, (s, part_key) in enumerate(COMPOSED):
    res = pipeline.make(s, out_dir=os.path.join(OUT, s["name"].lower()), contact_sheet=True,
                        face_part=stored_parts[part_key])
    print(f"compose {s['name']:5} body {res['path']} (nearest {res['nearest']}) + face {stored_parts[part_key]}: "
          f"{res['timing']['total']:.1f}s check {res['check']} face rms {res['fit'].get('face', {}).get('rms_tol')}")
    rig = bpy.data.objects[res["human"]].parent
    if rig is not None:
        rig.location.x = i * 1.0
if args.get("save"):
    bpy.ops.wm.save_as_mainfile(filepath=args["save"])
    print("saved", args["save"])
print("library items:", len(library.index()["items"]))
