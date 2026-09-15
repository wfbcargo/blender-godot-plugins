"""Phase 4 speed test: fresh builds fill a library; similar and repeated briefs then reuse it.

    blender -b --factory-startup --python scripts/tests/phase4_library.py -- lib=C:/scratch/lib [out=C:/scratch/p4]

Uses its own library folder (lib=), so the user's library is untouched. Prints the path taken
(fresh / warm / reuse), humancheck counts and seconds per stage for every brief.
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

args = dict(a.split("=", 1) for a in sys.argv[sys.argv.index("--") + 1:] if "=" in a) if "--" in sys.argv else {}
LIB = args.get("lib")
if not LIB:
    raise SystemExit("lib=<folder> is required: the test must not write to the user's library")
if os.path.isdir(LIB):
    shutil.rmtree(LIB)
os.environ["HUMANFORM_LIBRARY"] = LIB

import bpy  # noqa: E402

import humanform  # noqa: E402

humanform.reload_all()
from humanform import pipeline, sheet  # noqa: E402

FIRST = [
    sheet.new(name="Mara", sex="female", age=34, stature=1.72, build="athletic", style="realistic"),
    sheet.new(name="Otto", sex="male", age=52, stature=1.68, build="heavy", style="realistic"),
    sheet.new(name="Juno", sex="female", age=24, build="curvy", style="stylized"),
    sheet.new(name="Kade", sex="male", age=29, stature=1.88, build="muscular", style="stylized"),
    sheet.new(name="Wren", sex="female", age=61, stature=1.55, build="slim", style="realistic", seed=7),
]
SIMILAR = [
    sheet.new(name="Ines", sex="female", age=31, stature=1.70, build="athletic", style="realistic"),
    sheet.new(name="Bram", sex="male", age=47, stature=1.71, build="heavy", style="realistic"),
    sheet.new(name="Tova", sex="female", age=27, stature=1.64, build="curvy", style="stylized"),
    sheet.new(name="Ravi", sex="male", age=33, stature=1.83, build="athletic", style="realistic"),
]
REPEAT = [dict(FIRST[0], name="Mara2"), dict(FIRST[3], name="Kade2")]


def run(label, briefs, store):
    rows = []
    for s in briefs:
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        res = pipeline.make(s, out_dir=os.path.join(args.get("out", LIB + "_out"), s["name"].lower()), store=store)
        t = res["timing"]
        near = res["nearest"]
        rows.append(f"{label:8} {s['name']:6} {res['path']:6} "
                    f"{'near ' + str(near['distance']) if near else 'library empty':18} "
                    f"fit rms {res['fit']['rms_tol']:<6} {res['fit'].get('measurements', '-'):>3} measurements | "
                    f"check {res['check']['fail']}f {res['check']['warn']}w | fit {t['fit']:5.1f}s total {t['total']:5.1f}s"
                    + (f" | reuse check {res['reuse_check']}" if res.get("reuse_check") else ""))
    return rows


out = run("fresh", FIRST, store=True) + run("similar", SIMILAR, store=False) + run("repeat", REPEAT, store=False)
print("\n".join(out))
