"""glTF export with Godot-safe settings, and a read-back of what was written.

The setting that matters most is lighting mode. Blender's default ('SPEC',
physical units) multiplies light power by 683 lm/W on export, and Godot's
importer copies glTF intensity straight into light_energy - so a 1000 W point
light arrives at ~54,000 energy. Godot's own .blend importer uses 'COMPAT', so
this does too. Lights are still off by default: Godot scenes light themselves.

    res = export.export_gltf(r"C:/proj/assets/crate.glb", ["Crate_baked"])
    print(export.summarize(res))
"""

from __future__ import annotations

import json
import os
import struct

import bpy

GODOT_SETTINGS = {
    "export_format": "GLB",
    "use_selection": True,
    # Without this the exporter walks every scene, and picks up whatever is
    # selected in them too.
    "use_active_scene": True,
    # This helper is for props. Rigs and clips go through blender-to-godot or
    # rig-anything's exporter; pass export_animations=True to override.
    "export_animations": False,
    "export_apply": True,
    "export_yup": True,
    "export_materials": "EXPORT",
    "export_image_format": "AUTO",
    "export_tangents": True,
    "export_lights": False,
    "export_cameras": False,
    "export_import_convert_lighting_mode": "COMPAT",
}

# Extensions Godot 4.7's importer understands. Anything else in
# extensionsUsed is exported effort that disappears on import.
GODOT_READS = {
    "KHR_lights_punctual", "KHR_materials_emissive_strength", "KHR_materials_pbrSpecularGlossiness",
    "KHR_materials_unlit", "KHR_texture_transform", "KHR_node_visibility", "KHR_animation_pointer",
    "KHR_mesh_quantization", "KHR_texture_basisu", "EXT_texture_webp",
}


def _valid_kwargs(settings: dict) -> tuple[dict, list[str]]:
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    ok = {k: v for k, v in settings.items() if k in props}
    return ok, [k for k in settings if k not in props]


def export_gltf(path, objects, **overrides) -> dict:
    """Export the named objects (plus their children's meshes via selection) to
    `path` with GODOT_SETTINGS, then read the file back."""
    objs = [bpy.data.objects[o] if isinstance(o, str) else o for o in objects]
    settings = dict(GODOT_SETTINGS, **overrides)
    if path.lower().endswith(".gltf"):
        settings["export_format"] = "GLTF_SEPARATE"
    kwargs, skipped = _valid_kwargs(settings)
    vl = bpy.context.view_layer
    prev_sel = [o for o in bpy.context.scene.objects if o.select_get()]
    prev_active = vl.objects.active
    try:
        for o in bpy.context.scene.objects:
            o.select_set(False)
        for o in objs:
            o.select_set(True)
        vl.objects.active = objs[0] if objs else None
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        bpy.ops.export_scene.gltf(filepath=path, **kwargs)
    finally:
        for o in bpy.context.scene.objects:
            o.select_set(o in prev_sel)
        vl.objects.active = prev_active
    res = inspect_gltf(path)
    res["settings_skipped"] = skipped
    return res


def _read_json(path) -> dict:
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] == b"glTF":
        length = struct.unpack_from("<I", data, 12)[0]
        return json.loads(data[20:20 + length])
    return json.loads(data)


def inspect_gltf(path) -> dict:
    """What a .glb/.gltf actually contains, from Godot's point of view."""
    doc = _read_json(path)
    warnings = []
    used = set(doc.get("extensionsUsed", []))
    dropped = sorted(used - GODOT_READS)
    if dropped:
        warnings.append(f"extensions Godot 4.7 ignores: {', '.join(dropped)} - their effect will not appear in Godot")
    materials = []
    for m in doc.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        slots = []
        if "baseColorTexture" in pbr:
            slots.append("baseColor")
        if "metallicRoughnessTexture" in pbr:
            slots.append("metallicRoughness")
        for key in ("normalTexture", "occlusionTexture", "emissiveTexture"):
            if key in m:
                slots.append(key.replace("Texture", ""))
        entry = {
            "name": m.get("name", "?"),
            "textures": slots,
            "base_color_factor": pbr.get("baseColorFactor"),
            "metallic": pbr.get("metallicFactor", 1.0),
            "roughness": pbr.get("roughnessFactor", 1.0),
            "alpha_mode": m.get("alphaMode", "OPAQUE"),
            "extensions": sorted(m.get("extensions", {}).keys()),
        }
        # glTF's defaults are metallic 1 / roughness 1. A material that lands on
        # exactly those with no texture is usually one whose graph did not export.
        if not slots and "metallicFactor" not in pbr and "roughnessFactor" not in pbr and entry["base_color_factor"] is None:
            warnings.append(f"material '{entry['name']}' has no textures and all-default factors (white, fully metallic, rough) - "
                            "its node graph most likely did not export; run material_lint / bake")
        materials.append(entry)
    for light in doc.get("extensions", {}).get("KHR_lights_punctual", {}).get("lights", []):
        if light.get("intensity", 1.0) > 500:
            warnings.append(f"light '{light.get('name')}' intensity {light['intensity']:.0f} - Godot copies this into light_energy; "
                            "exported with lighting mode SPEC? Use COMPAT.")
    meshes = doc.get("meshes", [])
    has_tangents = any("TANGENT" in p.get("attributes", {}) for mesh in meshes for p in mesh.get("primitives", []))
    has_normal_maps = any("normal" in m["textures"] for m in materials)
    if has_normal_maps and not has_tangents:
        warnings.append("normal maps without exported tangents; Godot generates them on import, which can seam differently than Blender")
    uv_sets = max((sum(1 for a in p.get("attributes", {}) if a.startswith("TEXCOORD_"))
                   for mesh in meshes for p in mesh.get("primitives", [])), default=0)
    return {
        "path": path,
        "size_kb": round(os.path.getsize(path) / 1024, 1),
        "meshes": len(meshes),
        "materials": materials,
        "images": len(doc.get("images", [])),
        "uv_sets": uv_sets,
        "extensions_used": sorted(used),
        "warnings": warnings,
    }


def summarize(res: dict) -> str:
    lines = [f"{res['path']}  {res['size_kb']} KB  meshes {res['meshes']}  images {res['images']}  UV sets {res['uv_sets']}"]
    for m in res["materials"]:
        lines.append(f"  material {m['name']}: textures [{', '.join(m['textures']) or 'none'}]  metallic {m['metallic']}  "
                     f"roughness {m['roughness']}  {m['alpha_mode']}" + (f"  ext {m['extensions']}" if m["extensions"] else ""))
    if res.get("settings_skipped"):
        lines.append(f"  note: this Blender's exporter has no {res['settings_skipped']} option (skipped)")
    for w in res["warnings"]:
        lines.append("  WARN " + w)
    return "\n".join(lines)
