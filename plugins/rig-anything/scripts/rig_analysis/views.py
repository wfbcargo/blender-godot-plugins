"""Render orthographic views of one object for visual classification.

Geometry alone identifies structure poorly: a medial axis cannot tell a dog
from a table, and ground-contact counting cannot tell front from back. Looking
at the thing can. These renders are the input to that judgement.

Everything happens in a throwaway scene containing only the target object, so
the user's scene, its camera, its render settings and its visibility flags are
never touched. The temp scene is removed even if rendering raises.
"""

from __future__ import annotations

import math
import os

import bpy
from mathutils import Vector

# (name, direction the camera looks FROM, in object-local axis terms)
STANDARD_VIEWS = {
    "front": (0.0, -1.0, 0.0),
    "back": (0.0, 1.0, 0.0),
    "right": (1.0, 0.0, 0.0),
    "left": (-1.0, 0.0, 0.0),
    "top": (0.0, 0.0, 1.0),
    "iso": (1.0, -1.0, 0.7),
}


def _bounds(obj):
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi, (lo + hi) / 2.0, (hi - lo)


def render_views(obj_name, out_dir, views=("front", "right", "top", "iso"),
                 size=640, engine="BLENDER_WORKBENCH"):
    """Render `views` of `obj_name` into `out_dir`. Returns the file paths.

    Workbench is the default engine on purpose: it is fast, needs no lights or
    materials, and its flat shading gives a clean silhouette, which is what
    matters for reading structure. Textures would actively distract here.
    """
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        return {"error": "no object named " + repr(obj_name)}

    os.makedirs(out_dir, exist_ok=True)
    _, _, centre, dims = _bounds(obj)
    radius = max(dims) * 0.5 or 1.0

    scene = bpy.data.scenes.new("rig_anything_tmp")
    cam_data = bpy.data.cameras.new("rig_anything_cam")
    cam = bpy.data.objects.new("rig_anything_cam", cam_data)
    written = []

    try:
        scene.collection.objects.link(obj)
        scene.collection.objects.link(cam)
        scene.camera = cam

        scene.render.engine = engine
        scene.render.resolution_x = size
        scene.render.resolution_y = size
        scene.render.resolution_percentage = 100
        scene.render.film_transparent = False
        scene.render.image_settings.file_format = "PNG"
        if engine == "BLENDER_WORKBENCH":
            shading = scene.display.shading
            shading.light = "STUDIO"
            shading.color_type = "SINGLE"
            shading.single_color = (0.8, 0.8, 0.82)
            shading.show_cavity = True
            scene.display.render_aa = "8"

        cam_data.type = "ORTHO"
        # a little headroom so nothing is clipped at the frame edge
        cam_data.ortho_scale = radius * 2.4
        cam_data.clip_start = 0.001
        cam_data.clip_end = radius * 40.0

        for name in views:
            if name not in STANDARD_VIEWS:
                continue
            d = Vector(STANDARD_VIEWS[name]).normalized()
            cam.location = centre + d * radius * 6.0
            # point the camera's -Z at the object, with +Y up
            track = (centre - cam.location).normalized()
            cam.rotation_euler = track.to_track_quat("-Z", "Y").to_euler()

            path = os.path.join(out_dir, obj_name.replace(".", "_") + "_" + name + ".png")
            scene.render.filepath = path
            bpy.ops.render.render(write_still=True, scene=scene.name)
            written.append(path)
    finally:
        # unlink the user's object before deleting the scene, or it goes too
        try:
            if obj.name in scene.collection.objects:
                scene.collection.objects.unlink(obj)
        except Exception:
            pass
        bpy.data.scenes.remove(scene, do_unlink=True)
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.cameras.remove(cam_data, do_unlink=True)

    return {
        "object": obj_name,
        "files": written,
        "ortho_scale": round(radius * 2.4, 4),
        "centre": [round(v, 4) for v in centre],
        "note": "front looks along +Y, right looks along -X, top looks down -Z",
    }
