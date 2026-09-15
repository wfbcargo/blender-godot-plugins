"""Render the Phase 2 briefs side by side as mannequins, to see what the numbers mean.

    blender -b --factory-startup --python scripts/tests/lineup.py -- out=C:/scratch/lineup.png

Each mannequin is the brief's skeleton with a Skin modifier whose radii come from its measured
circumferences - a proxy for looking at proportion, not a body.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

import humanform  # noqa: E402

humanform.reload_all()
from humanform import landmarks, sheet, skeleton, views  # noqa: E402

args = dict(a.split("=", 1) for a in sys.argv[sys.argv.index("--") + 1:] if "=" in a) if "--" in sys.argv else {}
OUT = args.get("out", os.path.join(os.getcwd(), "lineup.png"))

BRIEFS = [
    sheet.new(name="Mara", sex="female", age=34, stature=1.72, build="athletic", style="realistic"),
    sheet.new(name="Otto", sex="male", age=52, stature=1.68, build="heavy", style="realistic"),
    sheet.new(name="Juno", sex="female", age=24, build="curvy", style="stylized"),
    sheet.new(name="Kade", sex="male", age=29, stature=1.88, build="muscular", style="stylized"),
    sheet.new(name="Wren", sex="female", age=61, stature=1.55, build="slim", style="realistic", seed=7),
]

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)


def mannequin(lm, v, name, x_offset):
    P = {k: Vector(p) + Vector((x_offset, 0, 0)) for k, p in lm["points"].items()}
    P["chin"].y = P["neck_base"].y
    P["head_mid"] = Vector((x_offset, 0.0, lm["points"]["chin"][2] + 0.55 * (lm["stature"] - lm["points"]["chin"][2])))
    r = lambda circ, k=1.0: k * circ / (2 * math.pi)  # noqa: E731
    chain = [  # (from, to, radius at from, radius at to)
        ("crotch", "pelvis", r(v["buttockcircumference"], 0.85), r(v["buttockcircumference"], 0.95)),
        ("pelvis", "waist", r(v["buttockcircumference"], 0.95), r(v["waistcircumference"])),
        ("waist", "chest", r(v["waistcircumference"]), r(v["chestcircumference"])),
        ("chest", "neck_base", r(v["chestcircumference"]), r(v["neckcircumferencebase"])),
        ("neck_base", "chin", r(v["neckcircumference"]), r(v["neckcircumference"])),
        ("chin", "head_mid", r(v["neckcircumference"], 1.1), r(v["headcircumference"], 0.95)),
        ("head_mid", "vertex", r(v["headcircumference"], 0.95), 0.03),
    ]
    for s in ("L", "R"):
        chain += [
            ("chest", f"shoulder.{s}", r(v["chestcircumference"], 0.7), r(v["bicepscircumferenceflexed"], 1.0)),
            ("neck_base", f"shoulder.{s}", r(v["neckcircumferencebase"], 0.9), r(v["bicepscircumferenceflexed"], 1.25)),
            (f"shoulder.{s}", f"elbow.{s}", r(v["bicepscircumferenceflexed"], 0.95), r(v["forearmcircumferenceflexed"], 0.8)),
            (f"elbow.{s}", f"wrist.{s}", r(v["forearmcircumferenceflexed"], 0.9), r(v["wristcircumference"])),
            (f"wrist.{s}", f"fingertip.{s}", r(v["wristcircumference"], 1.1), 0.01),
            (f"hip.{s}", f"knee.{s}", r(v["thighcircumference"]), r(v["lowerthighcircumference"], 0.8)),
            (f"knee.{s}", f"ankle.{s}", r(v["calfcircumference"], 0.9), r(v["anklecircumference"])),
            (f"ankle.{s}", f"toe.{s}", r(v["anklecircumference"], 0.8), 0.015),
            ("pelvis", f"hip.{s}", r(v["buttockcircumference"], 0.7), r(v["thighcircumference"])),
        ]
    verts, radii, edges, index = [], [], [], {}

    def vid(key, rad):
        if key not in index:
            index[key] = len(verts)
            verts.append(P[key])
            radii.append(rad)
        else:
            radii[index[key]] = max(radii[index[key]], rad)
        return index[key]

    for a, b, ra, rb in chain:
        n = max(2, int((P[a] - P[b]).length / 0.04))
        prev = vid(a, ra)
        for i in range(1, n):
            t = i / n
            key = f"{a}>{b}:{i}"
            P[key] = P[a].lerp(P[b], t)
            cur = vid(key, ra + (rb - ra) * t)
            edges.append((prev, cur))
            prev = cur
        edges.append((prev, vid(b, rb)))
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(p) for p in verts], edges, [])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.modifiers.new("Skin", "SKIN")
    for i, sv in enumerate(me.skin_vertices[0].data):
        sv.radius = (radii[i], radii[i])
    me.skin_vertices[0].data[index["crotch"]].use_root = True
    ob.modifiers.new("Subsurf", "SUBSURF").levels = 2
    return ob


x = 0.0
objs = []
for s in BRIEFS:
    res = sheet.resolve(s)
    lm = landmarks.from_measurements(res["values"], s["sex"], s["style"], name=s["name"])
    objs.append(mannequin(lm, res["values"], s["name"], x))
    x += 0.95

sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "MATCAP"
sc.display.shading.studio_light = views._matcap("basic_1")
sc.display.shading.color_type = "SINGLE"
sc.display.shading.single_color = (0.8, 0.8, 0.8)
sc.world = bpy.data.worlds.new("W")
sc.world.color = (0.28, 0.29, 0.31)
try:
    sc.view_settings.view_transform = "Standard"
except TypeError:
    pass
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = "ORTHO"
cam.data.ortho_scale = x + 0.2
cam.data.sensor_fit = "HORIZONTAL"
centre = Vector(((x - 0.95) / 2, 0, 1.0))
cam.location = centre + Vector((0, -10, 0))
cam.rotation_euler = (math.pi / 2, 0, 0)
cam.data.clip_end = 40
sc.render.resolution_x, sc.render.resolution_y = 1600, int(1600 * 2.1 / (x + 0.2))
cam.data.shift_y = 0.0
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("lineup", OUT)
