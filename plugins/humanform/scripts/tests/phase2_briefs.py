"""Phase 2 acceptance: five varied briefs -> sheet -> landmarks -> checks -> rig, read back by the
other plugins.

    blender -b --factory-startup --python scripts/tests/phase2_briefs.py

Passes when every brief resolves, its landmark set passes every proportion check for its own
preset and sex, the rig's joints read back within 1 mm of the landmarks through humancheck's own
landmark reader, and rig-anything's bodymap finds a spine, two arms and two legs.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
SKILLS = os.path.dirname(os.path.dirname(SCRIPTS))
for p in (SCRIPTS, os.path.join(SKILLS, "rig-anything", "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import humanform  # noqa: E402

humanform.reload_all()
from humanform import body, landmarks, measure, sheet, skeleton  # noqa: E402

BRIEFS = [
    sheet.new(name="Mara", sex="female", age=34, stature=1.72, build="athletic", style="realistic"),
    sheet.new(name="Otto", sex="male", age=52, stature=1.68, build="heavy", style="realistic"),
    sheet.new(name="Juno", sex="female", age=24, build="curvy", style="stylized"),
    sheet.new(name="Kade", sex="male", age=29, stature=1.88, build="muscular", style="stylized"),
    sheet.new(name="Wren", sex="female", age=61, stature=1.55, build="slim", style="realistic", seed=7),
]

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

failures = 0
rows = []
for s in BRIEFS:
    r = sheet.resolve(s)
    lm = landmarks.from_measurements(r["values"], s["sex"], s["style"], name=s["name"])
    m = landmarks.as_measurements(lm)
    findings = measure.check(m, s["style"], s["sex"], s["build"])
    bad = [f for f in findings if f["status"] in ("warn", "fail")]

    rig = skeleton.build(lm, s["name"])
    got = body.rig_landmarks(rig)
    worst = 0.0
    for k, p in got.items():
        worst = max(worst, (Vector(p) - Vector(lm["points"][k])).length)
    missing = [k for k in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")
               for sd in ("L", "R") if f"{k}.{sd}" not in got]

    try:
        from rig_analysis import bodymap
        bm = bodymap.build(rig.name)
        limbs = bm.get("limbs", [])
        arms = sum(1 for l in limbs if l.get("role") == "arm")
        legs = sum(1 for l in limbs if l.get("role") == "leg")
        bm_ok = not bm.get("error") and arms == 2 and legs == 2
        bm_note = f"arms {arms} legs {legs}" if not bm.get("error") else bm["error"]
    except Exception as exc:  # noqa: BLE001
        bm_ok, bm_note = False, f"bodymap raised {exc!r}"

    ok = not bad and worst < 1e-3 and not missing and bm_ok
    failures += not ok
    rv = r["sheet"]
    rows.append(f"{'PASS' if ok else 'FAIL'} {s['name']:5} {s['sex']:6} {s['style']:9} "
                f"{rv['stature']:.3f} m {rv['weight']:5.1f} kg bmi {rv['bmi']:4.1f} age {rv['age']:4.1f} | "
                f"{m['heads']:.2f} heads, crotch {m['crotch_z'] / m['stature']:.3f} H | "
                f"{len(bad)} off-target | rig {worst * 1000:.3f} mm | bodymap {bm_note}")
    for f in bad + [f for f in findings if f["status"] == "info"]:
        rows.append(f"      {f['status']}: {f['message']}")
    for n in r["notes"]:
        rows.append(f"      note: {n}")
    if r["guessed"]:
        rows.append(f"      guessed: {r['guessed']}")

# The presets must agree with themselves: a thigh target that is not hip minus knee makes every
# body fail one of the two, whatever it looks like.
for pname, preset in humanform.presets()["presets"].items():
    r = preset["ratios"]
    for sx in ("female", "male"):
        t = {k: (r[k].get("any") or r[k].get(sx))[0] for k in ("hip_joint", "knee_joint", "ankle_joint", "thigh", "shin")}
        for seg, a, b in (("thigh", "hip_joint", "knee_joint"), ("shin", "knee_joint", "ankle_joint")):
            gap = abs(t[seg] - (t[a] - t[b]))
            ok = gap <= 0.006
            failures += not ok
            rows.append(f"{'PASS' if ok else 'FAIL'} preset {pname}/{sx}: {seg} {t[seg]:.3f} vs {a} - {b} = {t[a] - t[b]:.3f}")

    chin = (r["chin"].get("any") or r["chin"].get("female"))[0]
    heads = preset["heads"]["any"]
    ok = abs(1.0 / (1.0 - chin) - heads[0]) <= heads[1] / 2
    failures += not ok
    rows.append(f"{'PASS' if ok else 'FAIL'} preset {pname}: heads {heads[0]} vs 1/(1-chin) = {1.0 / (1.0 - chin):.2f}")

# Negative controls: a checker that passes everything proves nothing. Break one thing at a time on
# Mara's landmarks and require the matching finding to fail or warn.
import copy  # noqa: E402

base = landmarks.from_measurements(sheet.resolve(BRIEFS[0])["values"], "female", "realistic", name="Mara")
H = base["stature"]


def broken(edit):
    lm = copy.deepcopy(base)
    edit(lm["points"])
    return {f["id"]: f["status"] for f in measure.check(landmarks.as_measurements(lm), "realistic", "female")}


def lower(names, dz):
    def edit(P):
        for n in names:
            P[n][2] -= dz
    return edit


def pull(joint, toward, frac):
    def edit(P):
        for sd in ("L", "R"):
            a, b = P[f"{joint}.{sd}"], P[f"{toward}.{sd}"]
            P[f"{joint}.{sd}"] = [a[i] + (b[i] - a[i]) * frac for i in range(3)]
    return edit


CONTROLS = [
    ("hips 8 cm low (Belle-like)", lower(["hip.L", "hip.R"], 0.08), "hip_joint"),
    ("shoulders 16 cm low (Figure-like)", lower(["shoulder.L", "shoulder.R"], 0.16), "shoulder_joint"),
    ("crotch 20 cm low (fused thighs)", lower(["crotch"], 0.20), "crotch"),
    ("elbow 40% toward the shoulder", pull("elbow", "shoulder", 0.4), "upper_arm"),
    ("head 1.5x too long", lower(["chin"], 0.5 * (H - base["points"]["chin"][2])), "heads"),
]
for label, edit, fid in CONTROLS:
    st = broken(edit).get(fid)
    ok = st in ("warn", "fail")
    failures += not ok
    rows.append(f"{'PASS' if ok else 'FAIL'} control: {label} -> {fid} {st}")

# Seeds: drawn bodies vary like people. A warn is 1.5 sd, so across ~14 correlated checks most
# people trip one; a fail is 3 sd, and a draw at the default variation must not produce one.
from collections import Counter  # noqa: E402

for s in BRIEFS:
    warned, failed, which = 0, 0, Counter()
    for seed in range(40):
        v = sheet.resolve(dict(s, seed=seed))["values"]
        lm = landmarks.from_measurements(v, s["sex"], s["style"])
        fs = measure.check(landmarks.as_measurements(lm), s["style"], s["sex"], s["build"])
        warned += any(f["status"] == "warn" for f in fs)
        failed += any(f["status"] == "fail" for f in fs)
        which.update(f["id"] for f in fs if f["status"] in ("warn", "fail"))
    ok = failed == 0
    failures += not ok
    rows.append(f"{'PASS' if ok else 'FAIL'} seeds: {s['name']} 40 draws at variation 0.5 - {failed} with a fail, "
                f"{warned} with a warn {dict(which.most_common(4))}")

print("\n".join(rows))
print(f"PHASE2 {'PASSED' if not failures else f'FAILED ({failures})'}")
