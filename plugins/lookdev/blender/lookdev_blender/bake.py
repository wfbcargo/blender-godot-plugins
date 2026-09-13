"""Bake a material graph into the textures glTF (and Godot) can carry.

Procedural nodes do not export - see material_lint. The fix is to evaluate
them into images and rebuild the material from those images in the one layout
the exporter reads without guessing:

    Base Color   <- <obj>_base_color.png   (sRGB)
    ORM image    -> Separate Color: G -> Roughness, B -> Metallic   (Non-Color)
                 -> R -> glTF Material Output group "Occlusion"
    Normal       <- Normal Map (tangent) <- <obj>_normal.png   (Non-Color)
    Emission     <- <obj>_emission.png, strength carried as a scalar

Godot imports that as one StandardMaterial3D with the ORM image in both the
metallic and roughness slots and AO read from its red channel.

How each channel is baked: Cycles has no metallic bake, and a diffuse-colour
bake darkens metallic areas. So for base colour, roughness, metallic and
emission the socket's input is temporarily routed into an Emission shader and
baked as EMIT - that returns exactly what the graph computes for that socket,
with no lighting in it. Normals bake as tangent-space NORMAL (OpenGL / +Y,
which is what glTF and Godot expect). AO bakes as AO and needs real samples.

    res = bake.bake_object("Crate", r"C:/proj/assets/crate_tex", size=2048)
    print(bake.summarize(res))

By default the object is DUPLICATED (mesh data included) and the copy gets the
baked material, so the procedural original is untouched.
"""

from __future__ import annotations

import os
import time

import bpy

try:
    import numpy as np
except ImportError:  # Blender ships numpy; this is only for linters.
    np = None

DATA_MAPS = {"roughness", "metallic", "normal", "ao"}
ALL_MAPS = ("base_color", "roughness", "metallic", "normal", "emission", "ao")
SOCKET_FOR = {"base_color": "Base Color", "roughness": "Roughness", "metallic": "Metallic", "emission": "Emission Color"}


def _principled(mat):
    if mat is None or mat.node_tree is None:
        return None, None
    tree = mat.node_tree
    outs = [n for n in tree.nodes if n.type == "OUTPUT_MATERIAL"]
    out = next((n for n in outs if n.is_active_output), outs[0] if outs else None)
    if out is None or not out.inputs["Surface"].is_linked:
        return None, out
    src = out.inputs["Surface"].links[0].from_node
    return (src if src.type == "BSDF_PRINCIPLED" else None), out


def _uses_emission(mats) -> bool:
    for m in mats:
        bsdf, _ = _principled(m)
        if bsdf is None:
            continue
        strength = bsdf.inputs["Emission Strength"]
        color = bsdf.inputs["Emission Color"]
        if (strength.is_linked or strength.default_value > 0) and (color.is_linked or max(color.default_value[:3]) > 0):
            return True
    return False


class _State:
    """Everything the bake touches on the scene, restored in finally."""

    def __init__(self, scene):
        self.scene = scene
        self.engine = scene.render.engine
        self.samples = scene.cycles.samples if hasattr(scene, "cycles") else None
        self.device = scene.cycles.device if hasattr(scene, "cycles") else None
        self.denoise = scene.cycles.use_denoising if hasattr(scene, "cycles") else None
        vl = bpy.context.view_layer
        self.active = vl.objects.active
        self.selected = [o for o in scene.objects if o.select_get()]

    def restore(self):
        s = self.scene
        s.render.engine = self.engine
        if self.samples is not None:
            s.cycles.samples = self.samples
            s.cycles.device = self.device
            s.cycles.use_denoising = self.denoise
        for o in s.objects:
            o.select_set(o in self.selected)
        bpy.context.view_layer.objects.active = self.active


def _target_nodes(mats, image):
    """An Image Texture node holding `image`, selected and active, in every
    material. Blender 5 bakes only to image nodes that are both."""
    added = []
    for m in mats:
        tree = m.node_tree
        for n in tree.nodes:
            n.select = False
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        node.select = True
        tree.nodes.active = node
        added.append((tree, node))
    return added


def _route_to_emission(mats, socket_name):
    """Temporarily drive each material's surface with an Emission shader fed by
    whatever feeds `socket_name`. Returns a restore list."""
    undo = []
    for m in mats:
        bsdf, out = _principled(m)
        tree = m.node_tree
        em = tree.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = 1.0
        prev = out.inputs["Surface"].links[0].from_socket if out and out.inputs["Surface"].is_linked else None
        if bsdf is not None:
            sock = bsdf.inputs[socket_name]
            if sock.is_linked:
                tree.links.new(sock.links[0].from_socket, em.inputs["Color"])
            else:
                v = sock.default_value
                em.inputs["Color"].default_value = (v, v, v, 1.0) if isinstance(v, float) else (v[0], v[1], v[2], 1.0)
        else:
            # Not Principled: nothing to isolate. Neutral defaults keep the bake
            # from failing; the summary flags it.
            em.inputs["Color"].default_value = {"Base Color": (0.5, 0.5, 0.5, 1), "Roughness": (0.5, 0.5, 0.5, 1)}.get(socket_name, (0, 0, 0, 1))
        tree.links.new(em.outputs["Emission"], out.inputs["Surface"])
        undo.append((tree, em, out, prev))
    return undo


def _undo_route(undo):
    for tree, em, out, prev in undo:
        tree.nodes.remove(em)
        if prev is not None:
            tree.links.new(prev, out.inputs["Surface"])


def _new_image(name, size, data):
    if name in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[name])
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False, is_data=data)
    img.colorspace_settings.name = "Non-Color" if data else "sRGB"
    return img


def _save(img, path):
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return path


def _bake(kind, margin, **kw):
    bpy.ops.object.bake(type=kind, margin=margin, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES", **kw)


def _gltf_output_group():
    """The node group the glTF exporter reads Occlusion from. Found by name."""
    name = "glTF Material Output"
    group = bpy.data.node_groups.get(name)
    if group is None:
        group = bpy.data.node_groups.new(name, "ShaderNodeTree")
        group.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        group.interface.new_socket("Thickness", in_out="INPUT", socket_type="NodeSocketFloat")
    return group


def _pack_orm(images, size, name, out_path):
    """R = AO (or 1), G = roughness, B = metallic."""
    orm = _new_image(name, size, True)
    n = size * size
    px = np.ones(n * 4, dtype=np.float32)
    for channel, key in ((0, "ao"), (1, "roughness"), (2, "metallic")):
        if key in images:
            src = np.empty(n * 4, dtype=np.float32)
            images[key].pixels.foreach_get(src)
            px[channel::4] = src[0::4]
        elif key != "ao":
            px[channel::4] = 0.5 if key == "roughness" else 0.0
    orm.pixels.foreach_set(px)
    orm.update()
    return orm, _save(orm, out_path)


def _build_material(name, images, emission_strength):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    if mat.node_tree is None and hasattr(mat, "use_nodes"):  # removed in 5.0, where materials always have nodes
        mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (250, 0)
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    def tex(img, y):
        n = tree.nodes.new("ShaderNodeTexImage")
        n.image = img
        n.location = (-500, y)
        return n

    if "base_color" in images:
        tree.links.new(tex(images["base_color"], 300).outputs["Color"], bsdf.inputs["Base Color"])
    if "orm" in images:
        orm = tex(images["orm"], 0)
        sep = tree.nodes.new("ShaderNodeSeparateColor")
        sep.location = (-200, 0)
        tree.links.new(orm.outputs["Color"], sep.inputs["Color"])
        tree.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        tree.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
        if images.get("_has_ao"):
            grp = tree.nodes.new("ShaderNodeGroup")
            grp.node_tree = _gltf_output_group()
            grp.location = (250, -450)
            tree.links.new(sep.outputs["Red"], grp.inputs["Occlusion"])
    if "normal" in images:
        nm = tree.nodes.new("ShaderNodeNormalMap")
        nm.space = "TANGENT"
        nm.location = (-200, -300)
        tree.links.new(tex(images["normal"], -300).outputs["Color"], nm.inputs["Color"])
        tree.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if "emission" in images:
        tree.links.new(tex(images["emission"], -600).outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def bake_object(obj, out_dir, size=2048, maps=None, samples_data=1, samples_ao=128, margin=None,
                device="CPU", duplicate=True, suffix="_baked", uv_map=None) -> dict:
    """Bake `obj`'s materials to textures in `out_dir` and build an export-ready
    material. Returns a dict with files, the material and object used, timings
    and warnings. `maps` defaults to base colour, roughness, metallic, normal,
    plus emission when any material emits. Add 'ao' explicitly - it is slower.
    """
    if np is None:
        raise RuntimeError("numpy unavailable in this Blender")
    obj = bpy.data.objects[obj] if isinstance(obj, str) else obj
    if obj.type != "MESH":
        return {"error": f"'{obj.name}' is a {obj.type}, not a mesh"}
    if not obj.data.uv_layers:
        return {"error": f"'{obj.name}' has no UV map. Unwrap first (bpy.ops.uv.smart_project) - bakes write into UV space."}
    mats = [s.material for s in obj.material_slots if s.material is not None]
    if not mats:
        return {"error": f"'{obj.name}' has no materials to bake"}
    if bpy.context.scene.objects.get(obj.name) is None:
        return {"error": f"'{obj.name}' is not in the current scene"}

    os.makedirs(out_dir, exist_ok=True)
    maps = list(maps) if maps else ["base_color", "roughness", "metallic", "normal"] + (["emission"] if _uses_emission(mats) else [])
    unknown = [m for m in maps if m not in ALL_MAPS]
    if unknown:
        return {"error": f"unknown maps {unknown}; choose from {ALL_MAPS}"}
    margin = margin if margin is not None else max(4, size // 128)
    warnings = []
    for m in mats:
        if _principled(m)[0] is None:
            warnings.append(f"material '{m.name}' is not driven by a Principled BSDF; base colour and roughness baked as neutral "
                            "defaults and metallic as 0. Rebuild it around a Principled BSDF first for a faithful bake.")
    if uv_map is not None:
        obj.data.uv_layers.active = obj.data.uv_layers[uv_map]

    # Emission strength can exceed 1, which an 8-bit image cannot hold. Bake the
    # colour and carry the largest constant strength as a scalar.
    strengths = set()
    for m in mats:
        bsdf, _ = _principled(m)
        if bsdf is not None and not bsdf.inputs["Emission Strength"].is_linked and bsdf.inputs["Emission Strength"].default_value > 0:
            strengths.add(round(bsdf.inputs["Emission Strength"].default_value, 3))
    emission_strength = max(strengths) if strengths else 1.0
    if "emission" in maps and len(strengths) > 1:
        warnings.append(f"materials use different emission strengths {sorted(strengths)}; the baked material carries only "
                        f"{emission_strength}. Bake emissive parts separately if the difference matters.")

    scene = bpy.context.scene
    state = _State(scene)
    base = bpy.path.clean_name(obj.name)
    images, files, timings = {}, {}, {}
    try:
        scene.render.engine = "CYCLES"
        scene.cycles.device = device
        scene.cycles.use_denoising = False
        for o in scene.objects:
            o.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        for key in maps:
            t0 = time.time()
            img = _new_image(f"{base}_{key}", size, key in DATA_MAPS)
            targets = _target_nodes(mats, img)
            try:
                if key in SOCKET_FOR:
                    scene.cycles.samples = samples_data
                    undo = _route_to_emission(mats, SOCKET_FOR[key])
                    try:
                        _bake("EMIT", margin)
                    finally:
                        _undo_route(undo)
                elif key == "normal":
                    scene.cycles.samples = max(samples_data, 4)
                    _bake("NORMAL", margin, normal_space="TANGENT", normal_r="POS_X", normal_g="POS_Y", normal_b="POS_Z")
                elif key == "ao":
                    scene.cycles.samples = samples_ao
                    _bake("AO", margin)
            finally:
                for tree, node in targets:
                    tree.nodes.remove(node)
            images[key] = img
            if key not in ("roughness", "metallic", "ao"):
                files[key] = _save(img, os.path.join(out_dir, f"{base}_{key}.png"))
            timings[key] = round(time.time() - t0, 2)
    finally:
        state.restore()

    if any(k in images for k in ("roughness", "metallic", "ao")):
        orm, files["orm"] = _pack_orm(images, size, f"{base}_orm", os.path.join(out_dir, f"{base}_orm.png"))
        for k in ("roughness", "metallic", "ao"):
            if k in images:
                bpy.data.images.remove(images.pop(k))
        images["orm"] = orm
        images["_has_ao"] = "ao" in maps

    mat = _build_material(f"{base}{suffix}", images, emission_strength)
    target = obj
    if duplicate:
        target = obj.copy()
        target.data = obj.data.copy()
        target.name = f"{obj.name}{suffix}"
        for coll in obj.users_collection:
            coll.objects.link(target)
    target.data.materials.clear()
    target.data.materials.append(mat)

    return {
        "object": target.name,
        "source": obj.name,
        "material": mat.name,
        "size": size,
        "maps": maps,
        "files": files,
        "timings_s": timings,
        "emission_strength": emission_strength if "emission" in maps else None,
        "warnings": warnings,
    }


def summarize(res: dict) -> str:
    if "error" in res:
        return "ERROR: " + res["error"]
    lines = [f"baked '{res['source']}' -> object '{res['object']}', material '{res['material']}' at {res['size']}px"]
    for k, path in res["files"].items():
        lines.append(f"  {k:11} {path}")
    lines.append("  timings    " + ", ".join(f"{k} {v}s" for k, v in res["timings_s"].items()))
    for w in res["warnings"]:
        lines.append("  WARN " + w)
    return "\n".join(lines)
