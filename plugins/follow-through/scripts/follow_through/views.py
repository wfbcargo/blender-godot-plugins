"""Render an object, and what it touches, for the visual half of recognition.

Measures say a sheet is open, vertical and touching a cylinder. Whether that is a
flag on a pole or a poster on a pipe is decided by looking. The renders show the
object in flat workbench grey and everything it touches in a darker tone, so the
thing holding it up is visible at a glance.

Everything is rendered in a throwaway scene; the user's scene, camera and
render settings are never touched, and the temp scene is removed even if a
render raises.
"""

from __future__ import annotations

import os

import bpy
from mathutils import Vector

VIEWS = {
    "front": (0.0, -1.0, 0.0),
    "right": (1.0, 0.0, 0.0),
    "top": (0.0, 0.0, 1.0),
    "iso": (1.0, -1.0, 0.7),
}


def _bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (lo + hi) / 2.0, hi - lo


def render_views(obj_name, out_dir, context=None, views=("front", "right", "iso"), size=560):
    """Render `views` of `obj_name`, plus `context` objects (default: what it touches).

    Returns {"files": [...]} - read the PNGs, then classify with `cls=` if the
    measures got it wrong."""
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        return {"error": "no object named " + repr(obj_name)}
    if context is None:
        from . import measure
        context = list(measure.contacts(obj)["by_object"])
    others = [bpy.data.objects[n] for n in context if n in bpy.data.objects]
    os.makedirs(out_dir, exist_ok=True)
    centre, dims = _bounds([obj] + others)
    radius = max(dims) * 0.5 or 1.0

    scene = bpy.data.scenes.new("follow_through_tmp")
    cam_data = bpy.data.cameras.new("follow_through_cam")
    cam = bpy.data.objects.new("follow_through_cam", cam_data)
    linked = []
    colours = {}
    written = []
    try:
        for o in [obj] + others:
            scene.collection.objects.link(o)
            linked.append(o)
            colours[o.name] = tuple(o.color)
            o.color = (0.85, 0.85, 0.88, 1.0) if o is obj else (0.35, 0.37, 0.42, 1.0)
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.resolution_x = size
        scene.render.resolution_y = size
        scene.render.image_settings.file_format = "PNG"
        sh = scene.display.shading
        sh.light = "STUDIO"
        sh.color_type = "OBJECT"
        sh.show_backface_culling = False
        sh.show_cavity = True
        scene.display.render_aa = "8"
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = radius * 2.4
        cam_data.clip_start = 0.001
        cam_data.clip_end = radius * 40.0
        for name in views:
            d = Vector(VIEWS[name]).normalized()
            cam.location = centre + d * radius * 6.0
            cam.rotation_euler = (centre - cam.location).normalized().to_track_quat("-Z", "Y").to_euler()
            path = os.path.join(out_dir, obj_name.replace(".", "_") + "_" + name + ".png")
            scene.render.filepath = path
            bpy.ops.render.render(write_still=True, scene=scene.name)
            written.append(path)
    finally:
        for o in linked:
            o.color = colours.get(o.name, o.color)
            if o.name in scene.collection.objects:
                scene.collection.objects.unlink(o)
        bpy.data.scenes.remove(scene, do_unlink=True)
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.cameras.remove(cam_data, do_unlink=True)
    return {"object": obj_name, "context": [o.name for o in others], "files": written,
            "note": "the object is light grey, what it touches dark grey; front looks along +Y"}
