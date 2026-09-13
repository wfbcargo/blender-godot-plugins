"""Reference renders in Blender that can be held up against a Godot capture.

Godot 4.6+'s AgX tonemapper defaults (tonemap_agx_white 16.29, contrast 1.25)
were chosen to match Blender's AgX view transform with no look. The match is
close from shadows through midtones and drifts in the brightest highlights,
so compare midtones and forgive highlight differences. Keep Godot glow and
colour adjustments off, and Blender exposure 0, when comparing.

    cam = reference.camera_from_godot([5, 2.2, 7], [0, 0.85, -0.8], fov=45)
    res = reference.render_reference(r"C:/tmp/ref.png", camera=cam, samples=64)

Everything this changes on the scene (engine, colour management, resolution,
camera, world) is restored afterwards.
"""

from __future__ import annotations

import math
import os

import bpy
from mathutils import Vector


def godot_to_blender(v) -> Vector:
    """Godot/glTF Y-up (x, y, z) -> Blender Z-up (x, -z, y)."""
    return Vector((v[0], -v[2], v[1]))


def camera_from_godot(eye, target, fov=75.0, name="LookdevRefCamera"):
    """A Blender camera matching a Godot Camera3D (vertical FOV, KEEP_HEIGHT).
    Use the eye/forward values in a lookdev capture's stats.json."""
    cam_data = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    cam_data.sensor_fit = "VERTICAL"
    cam_data.angle_y = math.radians(fov)
    cam = bpy.data.objects.get(name) or bpy.data.objects.new(name, cam_data)
    if bpy.context.scene.objects.get(name) is None:
        bpy.context.scene.collection.objects.link(cam)
    eye_b = godot_to_blender(eye)
    direction = godot_to_blender(target) - eye_b
    cam.location = eye_b
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam


def render_reference(out_path, camera=None, engine="CYCLES", samples=64, resolution=(1280, 720),
                     hdri=None, hdri_strength=1.0, look="None", exposure=0.0, device="CPU") -> dict:
    scene = bpy.context.scene
    vs, ds, r = scene.view_settings, scene.display_settings, scene.render
    saved = {
        "engine": r.engine, "res": (r.resolution_x, r.resolution_y, r.resolution_percentage),
        "path": r.filepath, "fmt": (r.image_settings.file_format, r.image_settings.color_depth),
        "film": r.film_transparent, "view": vs.view_transform, "look": vs.look, "exposure": vs.exposure,
        "gamma": vs.gamma, "display": ds.display_device, "camera": scene.camera, "world": scene.world,
    }
    if hasattr(scene, "cycles"):
        saved["cycles"] = (scene.cycles.samples, scene.cycles.device)
    temp_world = None
    warnings = []
    try:
        cam = bpy.data.objects[camera] if isinstance(camera, str) else camera
        if cam is not None:
            scene.camera = cam
        if scene.camera is None:
            return {"error": "no camera: pass camera=, or build one with camera_from_godot()"}
        r.engine = engine
        if engine == "CYCLES":
            scene.cycles.samples = samples
            scene.cycles.device = device
        r.resolution_x, r.resolution_y, r.resolution_percentage = resolution[0], resolution[1], 100
        r.film_transparent = False
        r.image_settings.file_format = "PNG"
        r.image_settings.color_depth = "8"
        ds.display_device = "sRGB"
        vs.view_transform = "AgX"
        try:
            vs.look = look
        except TypeError:
            warnings.append(f"look '{look}' not available; using None")
            vs.look = "None"
        vs.exposure = exposure
        vs.gamma = 1.0
        if hdri:
            temp_world = bpy.data.worlds.new("LookdevRefWorld")
            if temp_world.node_tree is None and hasattr(temp_world, "use_nodes"):  # removed in 5.0
                temp_world.use_nodes = True
            nt = temp_world.node_tree
            nt.nodes.clear()
            env = nt.nodes.new("ShaderNodeTexEnvironment")
            env.image = bpy.data.images.load(hdri, check_existing=True)
            bg = nt.nodes.new("ShaderNodeBackground")
            bg.inputs["Strength"].default_value = hdri_strength
            out = nt.nodes.new("ShaderNodeOutputWorld")
            nt.links.new(env.outputs["Color"], bg.inputs["Color"])
            nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
            scene.world = temp_world
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        r.filepath = out_path
        bpy.ops.render.render(write_still=True)
    finally:
        r.engine = saved["engine"]
        r.resolution_x, r.resolution_y, r.resolution_percentage = saved["res"]
        r.filepath = saved["path"]
        r.image_settings.file_format, r.image_settings.color_depth = saved["fmt"]
        r.film_transparent = saved["film"]
        vs.view_transform = saved["view"]
        vs.look = saved["look"]
        vs.exposure = saved["exposure"]
        vs.gamma = saved["gamma"]
        ds.display_device = saved["display"]
        scene.camera = saved["camera"]
        scene.world = saved["world"]
        if "cycles" in saved:
            scene.cycles.samples, scene.cycles.device = saved["cycles"]
        if temp_world is not None:
            bpy.data.worlds.remove(temp_world)
    return {"path": out_path, "engine": engine, "look": look, "warnings": warnings,
            "compare_with_godot": "Environment.tonemap_mode = 4 (AgX), defaults white 16.29 / contrast 1.25, glow and adjustments off, "
                                  "tonemap_exposure 1. Then: lookdev.mjs compare --a <this png> --b <capture>_lit.png"}
