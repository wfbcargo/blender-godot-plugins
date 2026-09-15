"""Phase 3a: briefs -> MPFB2 scaffold fitted to their landmarks -> humancheck on the real mesh.

    blender -b --factory-startup --python scripts/tests/phase3_scaffold.py -- out=C:/scratch/p3 [only=Mara] [views=1]
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
SKILLS = os.path.dirname(os.path.dirname(SCRIPTS))
for p in (SCRIPTS, os.path.join(SKILLS, "rig-anything", "scripts"), os.path.join(SKILLS, "wardrobe", "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import bpy  # noqa: E402

import humanform  # noqa: E402

humanform.reload_all()
from humanform import landmarks, measure, scaffold, sheet, views  # noqa: E402

args = dict(a.split("=", 1) for a in sys.argv[sys.argv.index("--") + 1:] if "=" in a) if "--" in sys.argv else {}
OUT = args.get("out", os.path.join(os.getcwd(), "p3"))

BRIEFS = [
    sheet.new(name="Mara", sex="female", age=34, stature=1.72, build="athletic", style="realistic"),
    sheet.new(name="Otto", sex="male", age=52, stature=1.68, build="heavy", style="realistic"),
    sheet.new(name="Juno", sex="female", age=24, build="curvy", style="stylized"),
    sheet.new(name="Kade", sex="male", age=29, stature=1.88, build="muscular", style="stylized"),
    sheet.new(name="Wren", sex="female", age=61, stature=1.55, build="slim", style="realistic", seed=7),
]
if args.get("only"):
    BRIEFS = [s for s in BRIEFS if s["name"] in args["only"].split(",")]

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

summary = []
for s in BRIEFS:
    t = time.time()
    r = sheet.resolve(s)
    lm = landmarks.from_measurements(r["values"], s["sex"], s["style"], name=s["name"])
    human, rep = scaffold.build(r["sheet"], lm, verbose=True)
    print(s["name"], scaffold.summarize(rep))
    out = os.path.join(OUT, s["name"].lower())
    hc = measure.run(human.name, preset=s["style"], sex=s["sex"], out_dir=out, build=s["build"])
    print(measure.summarize(hc))
    with open(os.path.join(out, "fit.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)

    try:
        from wardrobe import rigmap
        hm = rigmap.humanoid(human.name)
        wd = f"wardrobe reads spine {len(hm['spine'])}, arms {sorted(hm['arms'])}, legs {sorted(hm['legs'])}"
    except Exception as exc:  # noqa: BLE001
        wd = f"wardrobe rigmap failed: {exc!r}"
    try:
        from rig_analysis import bodymap
        bm = bodymap.build(rep["rig"])
        roles = sorted(l["role"] for l in bm.get("limbs", []))
        ra = f"bodymap limbs {roles}" if not bm.get("error") else bm["error"]
    except Exception as exc:  # noqa: BLE001
        ra = f"bodymap failed: {exc!r}"
    print("  ", wd, "|", ra)
    if args.get("views") == "1":
        views.contact_sheet(human.name, out, preset=s["style"], sex=s["sex"], report=hc)
    c = hc["counts"]
    summary.append(f"{s['name']}: fit rms {rep['rms_tol']} tol in {rep['seconds']} s; humancheck {c['fail']} fail "
                   f"{c['warn']} warn {c['pass']} pass; {time.time() - t:.0f} s total")

print("\n".join(summary))
if args.get("save"):
    for i, o in enumerate([o for o in bpy.data.objects if o.type == "ARMATURE"]):
        o.location.x = i * 1.0          # side by side; each rig carries its body
    bpy.ops.wm.save_as_mainfile(filepath=args["save"])
    print("saved", args["save"])
