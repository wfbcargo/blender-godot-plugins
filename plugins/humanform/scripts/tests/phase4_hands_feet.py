"""Phase 4 hands and feet: design variants on a fitted body, rendered as one grid per region for one
critic call each, with every design refitted to its size offsets.

    blender -b --factory-startup --python scripts/tests/phase4_hands_feet.py -- out=C:/scratch/hf [n=8] [seed=21] [only=Mara]

Builds Mara (female) and Kade (male) without the library, checks that the hands-and-feet fit holds
every measurement within 1.5 tolerances, renders <out>/<name>_hands.png and <name>_feet.png, and writes
<out>/<name>_<region>_variants.json (designs plus the residuals each refit reached) for the critic
and for storing the accepted designs. Prints HANDS_FEET PASSED when every fit and refit held.
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
from humanform import landmarks, parts, pipeline, sheet, views  # noqa: E402

args = dict(a.split("=", 1) for a in sys.argv[sys.argv.index("--") + 1:] if "=" in a) if "--" in sys.argv else {}
OUT = args["out"]
N = int(args.get("n", 8))
SEED = int(args.get("seed", 21))
STRENGTH = float(args.get("strength", 1.3))
LIMIT = 1.5
os.makedirs(OUT, exist_ok=True)
failures = []

for s in (sheet.new(name="Mara", sex="female", age=34, stature=1.72, build="athletic", style="realistic"),
          sheet.new(name="Kade", sex="male", age=29, stature=1.88, build="muscular", style="stylized")):
    if args.get("only") and s["name"] != args["only"]:
        continue
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    res = pipeline.make(s, use_library=False)
    human = bpy.data.objects[res["human"]]
    base = res["fit"]["extremities"]
    print(s["name"], "built", res["timing"], "check", res["check"])
    print(f"  hands and feet: rms {base['rms_tol']} tol, max {base['max_tol']}, {base['measurements']} measurements, {base['seconds']} s")
    if base["max_tol"] > LIMIT:
        failures.append(f"{s['name']} base extremities max {base['max_tol']} tol")
    lm = landmarks.from_measurements(sheet.resolve(s)["values"], s["sex"], s["style"], name=s["name"])
    for region in ("hands", "feet"):
        salt = {"hands": 0, "feet": 50}[region] + (0 if s["sex"] == "female" else 100)
        drawn = [{"name": f"{s['sex']}-{region}-base", "region": region, "targets": {}}]
        drawn += parts.variants(region, n=2 * N, seed=SEED + salt, name=f"{s['sex']}-{region}", strength=STRENGTH)
        t = time.time()
        vs, lost = parts.screen(human, lm, drawn, base, n=N + 1)
        ts = time.time() - t
        dropped, tried = len(lost), len(vs) + len(lost)
        for v in lost:
            print(f"    unreachable {v['name']}: offsets {v.get('offsets')}, refit {v['fit']['max_tol']} tol")
        if not vs or vs[0]["name"] != drawn[0]["name"]:
            failures.append(f"{s['name']} {region}: the base design did not refit")
        if len(vs) < N + 1 or dropped > N // 4:
            failures.append(f"{s['name']} {region}: {dropped} of {tried} designs unreachable")
        t = time.time()
        png = views.variant_grid(human.name, os.path.join(OUT, f"{s['name'].lower()}_{region}.png"), vs,
                                 apply=lambda v, h=human: parts.show(h, v), region=region)
        dt = time.time() - t
        with open(os.path.join(OUT, f"{s['name'].lower()}_{region}_variants.json"), "w", encoding="utf-8") as fh:
            json.dump(vs, fh, indent=1)
        worst = max(v["fit"]["max_tol"] for v in vs)
        print(f"  {region}: screened {tried} designs in {ts:.1f} s ({dropped} unreachable), rendered {len(vs)} in {dt:.1f} s, "
              f"worst kept refit {worst} tol -> {png}")
        parts.show(human, vs[0])            # leave the base look for the next region

print("HANDS_FEET", "FAILED: " + "; ".join(failures) if failures else "PASSED")
