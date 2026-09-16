"""Regression test: a warm start keeps the brief's own macros; ages ANSUR did not measure; colours.

    blender -b --factory-startup --python scripts/tests/phase4_warm_ages.py -- lib=C:/scratch/lib_ages

Uses its own library folder (lib=), emptied first, so the user's library is untouched. Exits 1 on any
failed check and prints every measured number.

1. warm start: a stored body with a different age, build, firmness and proportions is the starting shape
   for a brief; the macros the fit starts from and the unfitted ones it ends with are the brief's own
   (control: they differ from the stored body's by more than the tolerance, so the check can fail)
2. a child (8) and an 81-year-old: stature within 5 mm of the brief, the age macro is the real age, the
   result says "not measured against ANSUR", and store=True stores neither
3. an adult brief is unchanged: `ansur` "measured", no such note
4. colour: the sRGB curve at known points, round trip, and the linear values on the eye and skin materials
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
from humanform import library, look, pipeline, scaffold, sheet  # noqa: E402

FAILS = []
MACRO_TOL = 0.02
STATURE_TOL = 0.005


def check(label, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        FAILS.append(label)


def _bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def macros(human, names):
    _, _, HOP, _ = scaffold.services()
    return {n: round(float(HOP.get_value(n, entity_reference=human)), 3) for n in names}


# ---------------------------------------------------------------- 1. warm start
print("1. warm start keeps the brief's macros")
stored_brief = sheet.new(name="Store", sex="female", age=55, stature=1.68, build="soft", firmness=0.95,
                         proportions=0.9, style="realistic")
clear()
res0 = pipeline.make(stored_brief, store=True, eyes=False)
check("stored body saved", res0["stored"] is not None, f"check {res0['check']}")
stored = library.load(res0["stored"])["payload"]["macros"]

brief = sheet.new(name="Warm", sex="female", age=30, stature=1.70, build="athletic", firmness=0.15,
                  style="realistic")
clear()
res = pipeline.make(brief, store=False, eyes=False)
human = bpy.data.objects[res["human"]]
own = scaffold.create_macros(sheet.resolve(brief)["sheet"])
print(f"  path {res['path']}, nearest {res['nearest']}")
check("started from the stored body", res["path"] in ("warm", "reuse"), res["path"])
for n in ("age", "weight", "muscle", "firmness", "proportions"):
    check(f"control: stored {n} differs from the brief's", abs(stored[n] - own[n]) > MACRO_TOL,
          f"stored {stored[n]:.3f}, brief {own[n]:.3f}")
for n in ("age", "weight", "muscle", "firmness", "proportions", "cupsize"):
    got = res["start_macros"][n]
    check(f"fit starts from the brief's {n}", abs(got - own[n]) <= MACRO_TOL, f"{got:.3f} vs {own[n]:.3f}")
end = macros(human, ("age", "firmness", "proportions"))
for n, v in end.items():
    check(f"finished body keeps the brief's {n}", abs(v - own[n]) <= MACRO_TOL, f"{v:.3f} vs {own[n]:.3f}")

# weight and muscle are fitted, so they move from where the fit started; they must still end nearer the
# brief's own start than the stored body's (a warm and a fresh fit of one brief can settle on different
# weight/muscle pairs that meet the same measurements, so they are printed, not compared)
clear()
fresh = pipeline.make(brief, store=False, eyes=False, use_library=False)
for n in ("weight", "muscle"):
    w, f, st = res["macros"][n], fresh["macros"][n], stored[n]
    check(f"fitted {n} nearer the brief's than the stored body's", abs(w - own[n]) < abs(st - own[n]),
          f"warm {w:.3f}, brief {own[n]:.3f}, stored {st:.3f} (fresh fit {f:.3f})")

# the same brief again started from the same weight and muscle, so its fitted ones are kept and it reuses
clear()
again = pipeline.make(dict(stored_brief, name="Store2"), store=False, eyes=False)
check("a repeated brief reuses the stored body", again["path"] == "reuse",
      f"{again['path']}, reuse check {again['reuse_check']}")
check("a repeated brief keeps its firmness", abs(again["macros"]["firmness"] - 0.95) <= MACRO_TOL,
      f"{again['macros']['firmness']:.3f}")

# ---------------------------------------------------------------- 2. ages outside ANSUR
for label, b in (("child", sheet.new(name="Kid", sex="male", age=8, stature=1.27, bmi=14.5, firmness=0.6,
                                     skin=(0.56, 0.37, 0.26))),
                 ("aged", sheet.new(name="Elder", sex="male", age=81, stature=1.70, build="slim", firmness=0.3))):
    print(f"2. {label}: age {b['age']}, stature {b['stature']}")
    clear()
    r = pipeline.make(b, store=True)
    human = bpy.data.objects[r["human"]]
    got = scaffold.stature(human)
    check(f"{label}: ansur is {label}", r["ansur"] == label, str(r["ansur"]))
    check(f"{label}: stature within {STATURE_TOL * 1000:.0f} mm", abs(got - b["stature"]) <= STATURE_TOL,
          f"{got:.4f} m vs {b['stature']} m")
    m = macros(human, ("age", "firmness"))
    check(f"{label}: age macro is age {b['age']}", abs(m["age"] - scaffold.age_macro(b["age"])) <= MACRO_TOL,
          f"{m['age']:.3f} vs {scaffold.age_macro(b['age']):.3f}")
    check(f"{label}: firmness from the brief", abs(m["firmness"] - b["firmness"]) <= MACRO_TOL, f"{m['firmness']:.3f}")
    check(f"{label}: notes say not measured against ANSUR", any(sheet.NOT_MEASURED in n for n in r["notes"]),
          r["notes"][0][:90])
    bodies = [c for c in library.index()["items"] if c["kind"] == "body"]
    check(f"{label}: not stored", r["stored"] is None and len(bodies) == 1, f"stored {r['stored']}, {len(bodies)} bodies")
    check(f"{label}: rigged with eyes", bpy.data.objects.get(f"{human.name}_rig") is not None
          and bpy.data.objects.get(f"{human.name}_eyes") is not None)
    if label == "aged":
        a = r["fit"]["aged"]
        print(f"  age macro {a['age_macro_fitted']} -> {a['age_macro']}, stature after ageing "
              f"{a['stature_after_ageing_m']} m, height macro -> {a['stature']['macro']}; check {r['check']}")
        check("aged: fitted at 58", abs(a["age_macro_fitted"] - scaffold.age_macro(58)) <= MACRO_TOL)
    else:
        check("child: no humancheck against adult presets", r["check"] is None)
        mat = human.data.materials[0] if human.data.materials else None
        lin = look.srgb_to_linear(b["skin"])
        bc = _bsdf(mat).inputs["Base Color"].default_value if mat else None
        check("child: skin material holds the linear colour", mat is not None
              and all(abs(bc[i] - lin[i]) < 1e-4 for i in range(3)), f"{mat.name if mat else None}")

print("2b. validation")
check("child stature 1.12 m at age 6 accepted", not sheet.validate(sheet.new(sex="female", age=6, stature=1.12)))
check("stature 1.12 m for an adult rejected", bool(sheet.validate(sheet.new(sex="female", age=30, stature=1.12))))
check("firmness 1.4 rejected", bool(sheet.validate(sheet.new(sex="female", firmness=1.4))))

# ---------------------------------------------------------------- 3. adults unchanged
print("3. adult")
r = sheet.resolve(sheet.new(name="Adult", sex="female", age=34, stature=1.72, build="athletic"))
check("adult: ansur measured", r["ansur"] == "measured")
check("adult: no not-measured note", not any(sheet.NOT_MEASURED in n for n in r["notes"]), str(r["notes"]))
check("adult: age resolved as given", r["sheet"]["age"] == 34.0)

# ---------------------------------------------------------------- 4. colour
print("4. colour")
for s_, lin in ((0.0, 0.0), (1.0, 1.0), (0.04045, 0.04045 / 12.92), (0.5, 0.214041), (0.05, 0.003936)):
    check(f"srgb {s_} -> linear {lin:.6f}", abs(look.srgb_to_linear(s_) - lin) < 1e-6, f"{look.srgb_to_linear(s_):.6f}")
for v in (0.001, 0.02, 0.3, 0.77):
    check(f"round trip {v}", abs(look.linear_to_srgb(look.srgb_to_linear(v)) - v) < 1e-9)
clear()
eyes_body = pipeline.make(sheet.new(name="Eyes", sex="male", age=8, stature=1.27, iris=(0.46, 0.57, 0.63)))
iris = bpy.data.materials.get("HF_iris_Eyes_eyes")
bc = _bsdf(iris).inputs["Base Color"].default_value
want = look.srgb_to_linear((0.46, 0.57, 0.63))
check("iris material holds the linear colour", all(abs(bc[i] - want[i]) < 1e-4 for i in range(3)),
      f"{tuple(round(c, 4) for c in bc[:3])}")

print(f"\n{'PASS' if not FAILS else 'FAIL'}: {len(FAILS)} failed" + (": " + "; ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
