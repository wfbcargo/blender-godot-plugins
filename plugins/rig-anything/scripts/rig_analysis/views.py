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


def render_clip(mesh_name, rig_name, action_name, frames, out_dir,
                views=("right", "iso"), size=480):
    """Render chosen frames of a clip, one image per (frame, view).

    A generated action can pass every numeric check and still look wrong - a
    lean that reads as a fall, an elbow pointing somewhere odd. Numbers catch
    what they are written for; this is for what they are not.

    Same throwaway-scene rules as `render_views`. The camera is framed on the
    REST bounds so every frame shares one scale and they compare directly.

    Each frame is rendered from a FROZEN COPY of the evaluated mesh, never from
    the live rig. Rendering the rig and stepping the temp scene's frame was
    tried first and every frame came out pixel-identical - a crouch and a stand
    diffed to zero changed pixels - because the render reused a stale pose
    while the depsgraph, queried directly, had the right one. Freezing the
    shape takes animation evaluation out of rendering altogether.
    """
    from . import verify

    mesh = bpy.data.objects.get(mesh_name)
    rig = bpy.data.objects.get(rig_name)
    action = bpy.data.actions.get(action_name)
    if mesh is None or rig is None or action is None:
        return {"error": "missing mesh, rig or action"}
    os.makedirs(out_dir, exist_ok=True)

    main = bpy.context.scene
    prev_frame = main.frame_current
    ad = rig.animation_data or rig.animation_data_create()
    prev_action = ad.action
    snap = verify._snapshot(rig)
    # Frame on the REST vertices. `bound_box` is the last EVALUATED shape, so
    # after a clip has been stepped through it is whatever pose came last - and
    # a camera that re-centres on the posed body makes a crouch and a stand
    # render identically, which is exactly how this was found.
    rest = [mesh.matrix_world @ v.co for v in mesh.data.vertices]
    lo = Vector((min(p.x for p in rest), min(p.y for p in rest), min(p.z for p in rest)))
    hi = Vector((max(p.x for p in rest), max(p.y for p in rest), max(p.z for p in rest)))
    centre, dims = (lo + hi) / 2.0, hi - lo
    radius = max(dims) * 0.5 or 1.0
    tops = {}

    scene = bpy.data.scenes.new("rig_anything_clip_tmp")
    cam_data = bpy.data.cameras.new("rig_anything_cam")
    cam = bpy.data.objects.new("rig_anything_cam", cam_data)
    written = []
    frozen = []
    try:
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.render.fps = bpy.context.scene.render.fps
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.resolution_x = scene.render.resolution_y = size
        scene.render.image_settings.file_format = "PNG"
        shading = scene.display.shading
        shading.light = "STUDIO"
        shading.color_type = "SINGLE"
        shading.single_color = (0.8, 0.8, 0.82)
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = radius * 2.6
        cam_data.clip_start = 0.001
        cam_data.clip_end = radius * 40.0

        binding = verify.bind_action(rig, action)
        if not binding["bound"]:
            return {"error": binding["note"]}
        for f in frames:
            main.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            dg.update()
            shape = bpy.data.meshes.new_from_object(mesh.evaluated_get(dg),
                                                    depsgraph=dg)
            tops[f] = round(max((mesh.matrix_world @ v.co).z
                                for v in shape.vertices), 4)
            obj = bpy.data.objects.new("rig_anything_frozen", shape)
            obj.matrix_world = mesh.matrix_world.copy()
            scene.collection.objects.link(obj)
            frozen.append(obj)
            for name in views:
                d = Vector(STANDARD_VIEWS[name]).normalized()
                cam.location = centre + d * radius * 6.0
                cam.rotation_euler = (centre - cam.location).normalized() \
                    .to_track_quat("-Z", "Y").to_euler()
                path = os.path.join(out_dir, "%s_%s_f%03d_%s.png"
                                    % (rig_name, action_name, f, name))
                scene.render.filepath = path
                bpy.ops.render.render(write_still=True, scene=scene.name)
                written.append(path)
            scene.collection.objects.unlink(obj)
    finally:
        for obj in frozen:
            shape = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.meshes.remove(shape, do_unlink=True)
        main.frame_set(prev_frame)
        bpy.data.scenes.remove(scene, do_unlink=True)
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.cameras.remove(cam_data, do_unlink=True)
        if prev_action is not None:
            verify.bind_action(rig, prev_action)
        else:
            ad.action = None
        verify._restore(rig, snap)
    # evaluated top of the mesh per frame: if these agree the render shows a
    # static body, whatever the clip claims
    return {"files": written, "mesh_top_z": tops}
