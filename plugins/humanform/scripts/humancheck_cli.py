"""Run humancheck on a body in a .blend without touching an open Blender session.

    blender -b <file.blend> --factory-startup --python humancheck_cli.py -- \
        body=Nora preset=realistic sex=female out=C:/scratch/nora [views=1] [include=Nora_hair]

    blender -b --factory-startup --python humancheck_cli.py -- mpfb=female out=C:/scratch/mpfb

`mpfb=female|male` builds a default MPFB2 human (with its game_engine rig) to check instead.
Prints the summary and writes humancheck.json (and the contact sheets with views=1) to `out`.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402

import humanform  # noqa: E402

humanform.reload_all()
from humanform import measure  # noqa: E402

args = dict(a.split("=", 1) for a in sys.argv[sys.argv.index("--") + 1:] if "=" in a) if "--" in sys.argv else {}
out = args.get("out")
sex = args.get("sex")

name = args.get("body")
if "mpfb" in args:
    import addon_utils
    addon_utils.enable("bl_ext.user_default.mpfb", default_set=True)  # MPFB reads its own preferences entry
    from bl_ext.user_default.mpfb.services.humanservice import HumanService
    from bl_ext.user_default.mpfb.services.targetservice import TargetService
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    macro = TargetService.get_default_macro_info_dict()
    sex = sex or args["mpfb"]
    macro["gender"] = 1.0 if args["mpfb"] == "male" else 0.0
    human = HumanService.create_human(macro_detail_dict=macro)
    human.name = name or ("MPFB_" + args["mpfb"])
    HumanService.add_builtin_rig(human, args.get("rig", "game_engine"))
    name = human.name

rep = measure.run(name, preset=args.get("preset", "realistic"), sex=sex, out_dir=out)
print(measure.summarize(rep))
if args.get("verbose"):
    m = rep["measurements"]
    for k in sorted(m):
        if k != "landmarks":
            print(f"    {k} = {m[k]}")

if args.get("views") == "1" and out:
    from humanform import views
    include = [s for s in args.get("include", "").split(",") if s]
    res = views.contact_sheet(name, out, preset=args.get("preset", "realistic"), include=include, report=rep)
    for f in res["sheets"]:
        print("sheet", f)
