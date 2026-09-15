"""Phase 4 faces: design variants on a fitted body, rendered as one grid for one critic call.

    blender -b --factory-startup --python scripts/tests/phase4_faces.py -- out=C:/scratch/faces [n=8] [seed=11]

Builds Mara (female) and Kade (male) through the pipeline without the library, renders n face
designs on each as <out>/<name>_faces.png, and writes <out>/<name>_variants.json for the critic
and for storing the accepted ones.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import bpy  # noqa: E402

import humanform  # noqa: E402

humanform.reload_all()
from humanform import parts, pipeline, sheet, views  # noqa: E402

args = dict(a.split("=", 1) for a in sys.argv[sys.argv.index("--") + 1:] if "=" in a) if "--" in sys.argv else {}
OUT = args["out"]
N = int(args.get("n", 8))
SEED = int(args.get("seed", 11))
os.makedirs(OUT, exist_ok=True)

for s in (sheet.new(name="Mara", sex="female", age=34, stature=1.72, build="athletic", style="realistic"),
          sheet.new(name="Kade", sex="male", age=29, stature=1.88, build="muscular", style="stylized")):
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    res = pipeline.make(s, use_library=False)
    human = bpy.data.objects[res["human"]]
    vs = [{"name": f"{s['sex']}-base", "region": "face", "targets": {}}]
    vs += parts.variants("face", n=N, seed=SEED + (0 if s["sex"] == "female" else 100), name=s["sex"], strength=1.3)
    t = time.time()
    png = views.variant_grid(human.name, os.path.join(OUT, f"{s['name'].lower()}_faces.png"), vs,
                             apply=lambda v, h=human: parts.apply(h, v))
    with open(os.path.join(OUT, f"{s['name'].lower()}_variants.json"), "w", encoding="utf-8") as fh:
        json.dump(vs, fh, indent=1)
    print(s["name"], "built", res["timing"]["total"], "s;", len(vs), "faces rendered in", round(time.time() - t, 1), "s ->", png)
