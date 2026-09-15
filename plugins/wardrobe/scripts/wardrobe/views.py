"""Render a dressed body from several sides, posed at chosen frames, so Claude can look.

    res = views.render(["Figure", "Shirt"], r"C:/scratch/wardrobe", frames=[1, 9],
                       action="FigureWalk", views=("front", "side", "back", "three_quarter"))

Workbench, flat studio light, each object in its own colour (the body skin-toned, garments
distinct), so skin showing through cloth is obvious. Works in the MCP session and in
`blender -b`. The objects' scene is left as it was; a private scene is used and removed.
"""

from __future__ import annotations

import math
import os

import bpy
from mathutils import Vector

from . import rigmap

SKIN = (0.86, 0.62, 0.5, 1.0)
PALETTE = [(0.2, 0.42, 0.75, 1.0), (0.85, 0.75, 0.2, 1.0), (0.3, 0.65, 0.35, 1.0), (0.7, 0.25, 0.3, 1.0)]
VIEWS = {"front": 0.0, "three_quarter": 35.0, "side": 90.0, "back": 180.0, "back_three_quarter": 215.0,
         "left": -90.0}


def render(objects, out_dir, frames=(1,), action=None, views=("front", "side", "back"), size=640,
           focus=None, distance=None, elevation=8.0):
    objs = [rigmap._obj(o) for o in objects]
    os.makedirs(out_dir, exist_ok=True)
    body = objs[0]
    rig = rigmap.rig_of(body)
    hm = rigmap.humanoid(body)
    fwd = hm["forward"]

    sc = bpy.data.scenes.new("WardrobeViews")
    prev = {}
    try:
        for o in objs + [rig]:
            if o.name not in sc.collection.objects:
                sc.collection.objects.link(o)
        sc.render.engine = "BLENDER_WORKBENCH"
        sc.render.resolution_x = size
        sc.render.resolution_y = size
        sc.render.film_transparent = False
        sh = sc.display.shading
        sh.light = "STUDIO"
        sh.color_type = "OBJECT"
        sh.show_cavity = False
        sh.show_backface_culling = False
        sc.world = bpy.data.worlds.get("WardrobeWorld") or bpy.data.worlds.new("WardrobeWorld")
        sc.world.color = (0.55, 0.58, 0.62)
        for i, o in enumerate(objs):
            prev[o.name] = tuple(o.color)
            o.color = SKIN if i == 0 else PALETTE[(i - 1) % len(PALETTE)]

        cam_data = bpy.data.cameras.new("WardrobeCam")
        cam_data.lens = 50
        cam = bpy.data.objects.new("WardrobeCam", cam_data)
        sc.collection.objects.link(cam)
        sc.camera = cam

        ad = rig.animation_data or rig.animation_data_create()
        prev_action = ad.action
        if action:
            ad.action = bpy.data.actions[action]

        lo = min((body.matrix_world @ Vector(c)).z for c in body.bound_box)
        hi = max((body.matrix_world @ Vector(c)).z for c in body.bound_box)
        centre = focus if focus is not None else Vector((0, 0, (lo + hi) * 0.5))
        dist = distance if distance is not None else (hi - lo) * 2.3

        files = []
        for fr in frames:
            sc.frame_set(fr)
            for vname in views:
                yaw = math.radians(VIEWS[vname] if isinstance(vname, str) else float(vname))
                # yaw 0 looks at the body's front
                d = Vector((fwd.x * math.cos(yaw) - fwd.y * math.sin(yaw),
                            fwd.x * math.sin(yaw) + fwd.y * math.cos(yaw), 0.0))
                el = math.radians(elevation)
                pos = centre + d * dist * math.cos(el) + Vector((0, 0, dist * math.sin(el)))
                cam.location = pos
                cam.rotation_euler = (centre - pos).to_track_quat("-Z", "Y").to_euler()
                path = os.path.join(out_dir, f"f{fr:03d}_{vname}.png")
                sc.render.filepath = path
                with bpy.context.temp_override(scene=sc):
                    bpy.ops.render.render(write_still=True, scene=sc.name)
                files.append(path)
        ad.action = prev_action
    finally:
        for o in objs:
            if o.name in prev:
                o.color = prev[o.name]
        cam_obj = bpy.data.objects.get("WardrobeCam")
        if cam_obj is not None:
            bpy.data.objects.remove(cam_obj, do_unlink=True)
        bpy.data.scenes.remove(sc)
    return {"files": files}
