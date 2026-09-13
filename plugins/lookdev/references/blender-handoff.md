# Blender → Godot: materials and light

Checked against glTF-Blender-IO (blender-v5.2-release) and Godot 4.7.2's glTF
importer. The one-line summary: **Blender writing it doesn't mean Godot reads
it**, and neither side warns.

## What exports

The exporter walks back from Principled BSDF sockets. It recognises:

| glTF slot | Blender setup |
|---|---|
| baseColor | Image Texture → Base Color; RGB or constant; Mix (Multiply) of image × constant |
| metallicRoughness | Image (Non-Color) → Separate Color: **G → Roughness, B → Metallic**. Other wiring is repacked at export. |
| normal | Image (Non-Color) → Normal Map (**Tangent** only) → Normal; Strength → scale |
| occlusion | Node group named exactly **`glTF Material Output`**, input `Occlusion` (reads R). Blender doesn't render it. |
| emissive | Emission Color × Emission Strength; > 1 writes KHR_materials_emissive_strength |
| alpha | Constant 1 → OPAQUE; Math Round on alpha → MASK; otherwise BLEND |
| UV transform | UV Map → Mapping (Point) → image Vector |

**Silently lost** (the socket's default value is exported instead): Noise,
Voronoi, Wave and every procedural texture; Color Ramp; Bump; Math beyond
multiply/round; Mix Shader, Add Shader; node groups; attribute and geometry
nodes; non-tangent normal maps; displacement.

**Exported, then ignored by Godot 4.7:** clearcoat, sheen, specular / specular
tint, transmission, IOR, volume, anisotropy, iridescence, dispersion. Recreate
on the Godot side:

| Blender | Godot StandardMaterial3D |
|---|---|
| Coat | `clearcoat_enabled`, `clearcoat`, `clearcoat_roughness` |
| Transmission | `refraction_enabled` or transparency with low roughness |
| Sheen | `rim_enabled` (approximation) |
| Anisotropic | `anisotropy_enabled`, `anisotropy` (+ flowmap) |
| Subsurface | `subsurf_scatter_enabled` (glTF has no subsurface at all) |
| IOR | `metallic_specular` (0.5 = IOR 1.5) |

To keep those overrides through reimports, extract the material in the `.glb`
import settings (`_subresources` → materials → `use_external/enabled`, `path`)
and edit the extracted `.tres`.

## The tools

```python
r = material_lint.lint()              # selected meshes, else all in scene
print(material_lint.summarize(r))
```

Flags: `BAKE_REQUIRED` (with which input is fed by what), `DROPPED_BY_GODOT`,
`COLORSPACE_DATA` / `COLORSPACE_COLOR`, `NOT_PRINCIPLED`, `REPACK`, albedo and
metal range, missing images or UVs, unapplied or negative scale, UDIMs,
non-PNG/JPEG images, and the file's working colour space (must be Linear Rec.709).

```python
res = bake.bake_object("Crate", r"C:/proj/assets/crate_tex", size=2048, maps=None)
```

- Default maps: base_color, roughness, metallic, normal, plus emission if any
  material emits. Add `"ao"` explicitly (it's slower; `samples_ao=128`).
- Base colour, roughness, metallic and emission bake by routing the socket
  into an Emission shader and baking EMIT. That's exact, with no lighting in it,
  and metallic has no other bake. Normal bakes tangent-space +Y (glTF/Godot
  convention).
- Output: `<obj>_base_color.png` (sRGB), `<obj>_orm.png` (R AO / G roughness /
  B metallic, Non-Color), `<obj>_normal.png`, `<obj>_emission.png`.
- Builds `<obj>_baked` in the canonical layout and assigns it to a **duplicate**
  object (mesh copied too), so the procedural original stays. `duplicate=False`
  to replace in place.
- Needs a non-overlapping UV map for any map with position-dependent content
  (AO, procedural noise). Mirrored UVs are fine for tiling data.
- 8-bit output. Emission strength above 1 is carried as a scalar on the material.
- Restores render engine, samples, device and selection afterwards.

Verified end to end: a Noise/Color Ramp/Bump material → bake → export →
Godot import gave StandardMaterial3D with albedo, metallic (B), roughness (G),
AO (R) and normal map all bound.

```python
res = export.export_gltf(r"C:/proj/assets/crate.glb", ["Crate_baked"])
```

Godot-safe settings: GLB, selection in the **active scene only** (otherwise it
walks every scene), apply modifiers, tangents on, lights/cameras/animations off,
and `export_import_convert_lighting_mode = "COMPAT"`. It reads the file back and
warns about ignored extensions, materials that exported as all-defaults, normal
maps without tangents, and light intensities that look unconverted.

## Lights

Default lighting mode ("Standard") multiplies power by 683 lm/W, and Godot copies
glTF intensity straight into `light_energy`. A 1000 W point light arrives at
~54,000. Use **COMPAT**, which is what Godot's own `.blend` importer uses. Better
still, don't export lights: light the scene in Godot. Area lights and world
lighting don't export at all.

## Colour management

- Base colour and emission images: **sRGB**. Normal, roughness, metallic, AO,
  masks, displacement: **Non-Color**. The wrong tag shifts values in Blender
  and in the exporter's repacking.
- Working space (5.0+): `bpy.data.colorspace.working_space` must be
  `Linear Rec.709`. glTF and Godot assume Rec.709 primaries.
- Poly Haven and ambientCG: use **`nor_gl` / `NormalGL`**, not DX (flipped green).

## Lightmap UV2

- Godot import `meshes/light_baking = Static Lightmaps` unwraps UV2 itself
  (xatlas, `lightmap_texel_size` 0.2 m) and caches it. Commit the
  `.unwrap_cache` files. This is Godot's recommendation.
- Author UV2 in Blender only for heavy, often-reimported meshes: a second UV
  map, no overlaps, uniform texel density, scale applied; exports as
  TEXCOORD_1 → UV2.

## Reference renders

```python
cam = reference.camera_from_godot(eye, target, fov)       # from capture stats.json
reference.render_reference(r"C:/tmp/ref.png", camera=cam, samples=64, hdri=None)
```

Renders with AgX (look None), exposure 0, sRGB display, then restores the
scene's settings. Godot's AgX defaults were tuned to match. Compare **midtones**:
highlights drift. On the Godot side keep glow and adjustments off and
`tonemap_exposure` 1, then `lookdev.mjs compare --a ref.png --b <capture>_lit.png`.
Camera conversion: Godot (x, y, z) → Blender (x, −z, y), vertical FOV.
