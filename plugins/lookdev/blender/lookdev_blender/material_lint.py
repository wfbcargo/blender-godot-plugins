"""Will these materials survive the trip to Godot?

Two filters stand between a Blender material and what Godot renders, and both
drop things silently:

1. Blender's glTF exporter does not translate shader graphs. It walks back
   from Principled BSDF sockets looking for Image Texture nodes and a few
   recognised patterns; anything else (Noise, Voronoi, Color Ramp, Bump, Mix
   Shader, node groups...) falls back to the socket's default value.
2. Godot 4.7's glTF importer reads only KHR_materials_emissive_strength,
   _unlit, _pbrSpecularGlossiness and KHR_texture_transform. Clearcoat,
   sheen, transmission, specular, IOR, volume, anisotropy, iridescence and
   dispersion are exported and then ignored.

So this lints for both, plus colour-space mistakes and implausible PBR values.

    r = material_lint.lint()          # selected meshes, or all in the scene
    print(material_lint.summarize(r))
"""

from __future__ import annotations

import os

import bpy

from . import pbr

# Principled inputs Godot's importer reads, and the colour space the image
# feeding each must be tagged with.
CORE_INPUTS = {
    "Base Color": "sRGB",
    "Metallic": "Non-Color",
    "Roughness": "Non-Color",
    "Normal": "Non-Color",
    "Emission Color": "sRGB",
    "Alpha": "Non-Color",
}

# Exported by Blender, ignored by Godot 4.7. Value is (default, Godot substitute).
DROPPED_BY_GODOT = {
    "Coat Weight": (0.0, "StandardMaterial3D clearcoat_enabled / clearcoat / clearcoat_roughness"),
    "Sheen Weight": (0.0, "StandardMaterial3D rim_enabled (approximates cloth sheen) or a shader"),
    "Transmission Weight": (0.0, "StandardMaterial3D refraction_enabled or transparency + roughness"),
    "Anisotropic": (0.0, "StandardMaterial3D anisotropy_enabled / anisotropy"),
    "Specular Tint": ((1.0, 1.0, 1.0, 1.0), "not available in StandardMaterial3D; a ShaderMaterial can tint SPECULAR"),
    "Thin Film Thickness": (0.0, "a ShaderMaterial (iridescence)"),
    "Subsurface Weight": (0.0, "StandardMaterial3D subsurf_scatter_enabled - glTF has no subsurface at all"),
}

PASS_THROUGH = {"REROUTE"}
UV_SOURCES = {"MAPPING", "UVMAP", "TEX_COORD", "REROUTE"}
IMAGE_FORMATS_OK = {"PNG", "JPEG"}


def _finding(out, severity, code, where, message, fix=""):
    out.append({"severity": severity, "code": code, "where": where, "message": message, "fix": fix})


def _source(socket):
    """The node and output socket feeding an input, skipping reroutes."""
    if not socket.is_linked:
        return None, None
    link = socket.links[0]
    node, out = link.from_node, link.from_socket
    while node.type in PASS_THROUGH:
        if not node.inputs[0].is_linked:
            return None, None
        link = node.inputs[0].links[0]
        node, out = link.from_node, link.from_socket
    return node, out


def _image_uv_ok(tex_node) -> bool:
    vec = tex_node.inputs.get("Vector")
    if vec is None or not vec.is_linked:
        return True
    node, _ = _source(vec)
    while node is not None and node.type == "MAPPING":
        node, _ = _source(node.inputs["Vector"])
    return node is None or node.type in UV_SOURCES


def _classify(input_name: str, node, out_socket) -> tuple[str, list]:
    """('ok' | 'repack' | 'bake', [image nodes]) for what feeds a core input."""
    if node is None:
        return "ok", []
    t = node.type
    if t == "TEX_IMAGE":
        if not _image_uv_ok(node):
            return "bake", [node]
        if input_name in ("Metallic", "Roughness"):
            return "repack", [node]
        return "ok", [node]
    if input_name == "Base Color":
        if t == "RGB":
            return "ok", []
        if t in ("VERTEX_COLOR", "ATTRIBUTE"):
            return "ok", []
        if t == "MIX" and getattr(node, "blend_type", "") == "MULTIPLY":
            imgs = []
            for sock in node.inputs:
                if sock.is_linked and sock.enabled:
                    n, _ = _source(sock)
                    if n is not None and n.type != "TEX_IMAGE":
                        return "bake", []
                    if n is not None:
                        imgs.append(n)
            return ("ok", imgs) if len(imgs) == 1 else ("bake", imgs)
    if input_name in ("Metallic", "Roughness", "Alpha"):
        if t == "SEPARATE_COLOR":
            n, _ = _source(node.inputs[0])
            if n is None or n.type == "TEX_IMAGE":
                wanted = {"Metallic": "Blue", "Roughness": "Green"}.get(input_name)
                status = "ok" if wanted is None or out_socket.name == wanted else "repack"
                return status, [n] if n else []
            return "bake", []
        if t == "MATH" and node.operation in ("MULTIPLY", "ROUND", "LESS_THAN", "SUBTRACT"):
            imgs = []
            for sock in node.inputs:
                if sock.is_linked:
                    status, found = _classify(input_name, *_source(sock))
                    if status == "bake":
                        return "bake", found
                    imgs += found
            return "ok", imgs
    if input_name == "Normal" and t == "NORMAL_MAP":
        if node.space != "TANGENT":
            return "bake", []
        n, _ = _source(node.inputs["Color"])
        if n is None:
            return "ok", []
        if n.type == "TEX_IMAGE" and _image_uv_ok(n):
            return "ok", [n]
        return "bake", []
    if input_name == "Emission Color" and t == "RGB":
        return "ok", []
    return "bake", []


def _active_output(tree):
    outs = [n for n in tree.nodes if n.type == "OUTPUT_MATERIAL"]
    for n in outs:
        if n.is_active_output:
            return n
    return outs[0] if outs else None


def lint_material(mat, users: list[str] | None = None) -> list[dict]:
    out: list[dict] = []
    where = f"material '{mat.name}'"
    if users:
        where += f" (on {', '.join(users[:3])}{'...' if len(users) > 3 else ''})"
    tree = mat.node_tree
    if tree is None:
        _finding(out, "warn", "NO_NODES", where, "material has no node tree; exports as its viewport colour only.")
        return out
    output = _active_output(tree)
    if output is None or not output.inputs["Surface"].is_linked:
        _finding(out, "error", "NO_OUTPUT", where, "no active Material Output with a Surface link; exports as a default grey material.")
        return out
    surface, _ = _source(output.inputs["Surface"])
    if output.inputs.get("Displacement") is not None and output.inputs["Displacement"].is_linked:
        _finding(out, "info", "DISPLACEMENT", where, "displacement is not exported. Bake it to a normal map, or model the detail.",
                 "bake.bake_object(obj, maps=('normal',)) after routing the displacement into Bump -> Normal")
    if surface is None or surface.type != "BSDF_PRINCIPLED":
        kind = surface.type if surface is not None else "nothing"
        _finding(out, "warn", "NOT_PRINCIPLED", where,
                 f"surface is driven by {kind}, not a Principled BSDF. The exporter only understands Principled; this material "
                 "will export with defaults.", "bake.bake_object(obj) - it evaluates the whole graph into textures")
        return out

    bsdf = surface
    base_const = None
    metallic_const = None
    emissive = False
    needs_bake = []
    for name, space in CORE_INPUTS.items():
        sock = bsdf.inputs.get(name)
        if sock is None:
            continue
        node, out_sock = _source(sock)
        status, images = _classify(name, node, out_sock)
        if status == "bake":
            needs_bake.append(f"{name} <- {node.bl_label if node else '?'}")
        elif status == "repack" and name in ("Metallic", "Roughness"):
            _finding(out, "info", "REPACK", where,
                     f"{name} reads an image without Separate Color on the glTF channel (roughness = G, metallic = B); the exporter "
                     "repacks it at export, which is slow and doubles texture memory if the image is also used elsewhere.",
                     "pack an ORM image (R=AO, G=roughness, B=metallic) and wire it through Separate Color")
        for img_node in images:
            img = img_node.image
            if img is None:
                _finding(out, "error", "IMAGE_EMPTY", where, f"the Image Texture feeding {name} has no image.")
                continue
            cs = img.colorspace_settings.name
            want_data = space == "Non-Color"
            is_data = cs in ("Non-Color", "Raw", "Linear Rec.709", "Generic Data") or getattr(img.colorspace_settings, "is_data", False)
            if want_data and not is_data:
                _finding(out, "error", "COLORSPACE_DATA", where,
                         f"image '{img.name}' feeds {name} but is tagged '{cs}'. Data maps must be Non-Color, or the values are "
                         "gamma-shifted in Blender and on export.", f"bpy.data.images['{img.name}'].colorspace_settings.name = 'Non-Color'")
            if not want_data and is_data:
                _finding(out, "error", "COLORSPACE_COLOR", where,
                         f"image '{img.name}' feeds {name} but is tagged '{cs}'. Colour maps must be sRGB.",
                         f"bpy.data.images['{img.name}'].colorspace_settings.name = 'sRGB'")
            _check_image(out, where, img)
        if name == "Base Color" and node is None:
            base_const = sock.default_value[:]
        if name == "Metallic" and node is None:
            metallic_const = float(sock.default_value)
        if name == "Emission Color":
            strength = bsdf.inputs.get("Emission Strength")
            emissive = (node is not None or max(sock.default_value[:3]) > 0) and strength is not None and strength.default_value > 0

    if needs_bake:
        _finding(out, "warn", "BAKE_REQUIRED", where,
                 "these inputs are driven by nodes the glTF exporter cannot translate, so they export as flat default values: "
                 + "; ".join(needs_bake) + ".",
                 "bake.bake_object(obj) - bakes base colour, roughness, metallic, normal (and emission if used) to textures and "
                 "builds an export-ready material")

    if base_const is not None:
        for sev, code, msg in pbr.albedo_problems(base_const, metallic_const if metallic_const is not None else 0.0, emissive):
            _finding(out, sev, code, where, msg)
    elif metallic_const is not None and 0.1 < metallic_const < 0.9:
        _finding(out, "warn", "METALLIC_PARTIAL", where, f"metallic {metallic_const:.2f}: surfaces are metal or not.")

    for name, (default, substitute) in DROPPED_BY_GODOT.items():
        sock = bsdf.inputs.get(name)
        if sock is None:
            continue
        value = sock.default_value
        changed = sock.is_linked
        if not changed:
            if isinstance(default, tuple):
                changed = any(abs(a - b) > 1e-3 for a, b in zip(value[:], default))
            else:
                changed = abs(float(value) - default) > 1e-3
        if changed:
            _finding(out, "warn", "DROPPED_BY_GODOT", where,
                     f"'{name}' is set. Blender exports it, but Godot 4.7's glTF importer ignores it, so the effect disappears.",
                     f"recreate in Godot: {substitute}")
    if abs(float(bsdf.inputs["IOR"].default_value) - 1.5) > 0.05 and not bsdf.inputs["IOR"].is_linked:
        _finding(out, "info", "IOR_IGNORED", where,
                 f"IOR {bsdf.inputs['IOR'].default_value:.2f} is ignored by Godot. The equivalent control is metallic_specular "
                 "(0.5 = IOR 1.5; water ~0.35).")

    # glTF Material Output group: occlusion.
    for n in tree.nodes:
        if n.type == "GROUP" and n.node_tree and n.node_tree.name in ("glTF Material Output", "glTF Settings"):
            occ = n.inputs.get("Occlusion")
            if occ is not None and occ.is_linked:
                src, _ = _source(occ)
                if src is not None and src.type == "SEPARATE_COLOR":
                    src, _ = _source(src.inputs[0])
                if src is None or src.type != "TEX_IMAGE":
                    _finding(out, "warn", "OCCLUSION_UNTRANSLATABLE", where, "Occlusion is fed by nodes, not an image; it will not export.",
                             "bake.bake_object(obj, maps=(..., 'ao'))")
                elif src.image is not None:
                    _check_image(out, where, src.image)
    return out


def _check_image(out, where, img):
    if img.source == "TILED":
        _finding(out, "info", "UDIM", where, f"image '{img.name}' is a UDIM set; the exporter splits it per tile into separate materials.")
    fmt = (img.file_format or "").upper()
    if img.source == "FILE" and fmt and fmt not in IMAGE_FORMATS_OK:
        _finding(out, "info", "IMAGE_FORMAT", where, f"image '{img.name}' is {fmt}; glTF allows PNG/JPEG, so it is converted on export.")
    if img.source == "FILE" and not img.packed_file:
        path = bpy.path.abspath(img.filepath)
        if path and not os.path.exists(path):
            _finding(out, "error", "IMAGE_MISSING", where, f"image '{img.name}' points at a missing file: {path}")


def _mesh_findings(obj) -> list[dict]:
    out: list[dict] = []
    where = f"object '{obj.name}'"
    me = obj.data
    textured = False
    for slot in obj.material_slots:
        if slot.material is None:
            _finding(out, "info", "EMPTY_SLOT", where, "has an empty material slot; those faces export with a default material.")
            continue
        tree = slot.material.node_tree
        if tree and any(n.type == "TEX_IMAGE" for n in tree.nodes):
            textured = True
    if not obj.material_slots:
        _finding(out, "info", "NO_MATERIAL", where, "no material; exports as glTF default (white, roughness 1).")
    if textured and not me.uv_layers:
        _finding(out, "error", "NO_UV", where, "uses image textures but has no UV map; textures will not map.", "unwrap (smart_project) before export")
    sx, sy, sz = obj.scale
    if min(sx, sy, sz) < 0:
        _finding(out, "warn", "NEGATIVE_SCALE", where, "negative scale flips winding; faces can render inside-out after export.",
                 "apply scale (Ctrl+A) and recalculate normals")
    elif max(abs(sx - 1), abs(sy - 1), abs(sz - 1)) > 1e-3:
        _finding(out, "info", "SCALE_NOT_APPLIED", where,
                 f"scale ({sx:.2f}, {sy:.2f}, {sz:.2f}) is not applied. Godot's lightmapper warns on non-uniform scale and texel density goes uneven.",
                 "apply scale before export")
    if len(me.uv_layers) > 1:
        _finding(out, "info", "UV2_PRESENT", where,
                 f"{len(me.uv_layers)} UV maps: the second exports as TEXCOORD_1 and Godot uses it as UV2 for lightmaps, unless the import "
                 "is set to 'Static Lightmaps', which regenerates it.")
    return out


def lint(objects=None) -> dict:
    """Lint materials on the given objects (names or objects). Defaults to the
    selected meshes, or every mesh in the scene if nothing is selected."""
    if objects is None:
        objects = [o for o in bpy.context.selected_objects if o.type == "MESH"] or \
                  [o for o in bpy.context.scene.objects if o.type == "MESH"]
    objects = [bpy.data.objects[o] if isinstance(o, str) else o for o in objects]
    findings: list[dict] = []

    ws = getattr(getattr(bpy.data, "colorspace", None), "working_space", "Linear Rec.709")
    if ws != "Linear Rec.709":
        _finding(findings, "error", "WORKING_SPACE", "file",
                 f"working colour space is '{ws}'. glTF and Godot assume Rec.709 primaries; colours will shift on export.")

    users: dict = {}
    for obj in objects:
        findings += _mesh_findings(obj)
        for slot in obj.material_slots:
            if slot.material is not None:
                users.setdefault(slot.material, []).append(obj.name)
    for mat, names in users.items():
        findings += lint_material(mat, names)
    order = {"error": 0, "warn": 1, "info": 2}
    findings.sort(key=lambda f: order[f["severity"]])
    return {"objects": len(objects), "materials": len(users), "findings": findings}


def summarize(result: dict) -> str:
    counts = {"error": 0, "warn": 0, "info": 0}
    for f in result["findings"]:
        counts[f["severity"]] += 1
    lines = [f"lookdev material lint: {result['objects']} objects, {result['materials']} materials - "
             f"{counts['error']} error, {counts['warn']} warn, {counts['info']} info"]
    for f in result["findings"]:
        lines.append(f"{f['severity'].upper():5} {f['code']}  {f['where']}")
        lines.append(f"      {f['message']}")
        if f["fix"]:
            lines.append(f"      fix: {f['fix']}")
    if not result["findings"]:
        lines.append("  clean")
    return "\n".join(lines)
