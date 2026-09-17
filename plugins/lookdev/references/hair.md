# Hair material

`lookdev_blender.hair.material(name, colour, uv_map=...)` builds the `hair` preset from
`presets/materials.json`; `godot/addons/lookdev/lookdev_materials.gd` finishes it in Godot. Checked on
Blender 5.2 and Godot 4.7.2 with Belle's bun (improvements 05 5.2).

## What the mesh must give it

One UV map (the body's, so the hair can be joined into a body without a second map):

- **U across the strands**, in units of `tile_m` (0.04 m) of surface, so strands are the same width on
  every part. The texture repeats in U; a closed loop should span a whole number of tiles.
- **V along the strands**: 0 at the root or hairline, 1 at the tip. The texture's alpha is 0 below
  `root_zone[0] / 2` and near V = 1, so a mesh puts its geometric edges there and clamps V into 0..1.

humanform's hair: the cap's boundary at V ~ 0.003 and its hairline curve at V = 0.045; a bob's ends at
0.975; a ponytail's tip at 0.985.

## What survives glTF, and how

| Look | Blender | glTF | Godot 4.7 |
|---|---|---|---|
| strands, root-to-tip gradient | image on Base Color (`<name>_strands`, packed, sRGB) | baseColorTexture | albedo texture |
| thinned roots and tips | image alpha -> Math Round -> Alpha | alphaMode MASK, cutoff 0.5 | alpha scissor; the extras add alpha-to-coverage |
| strand relief | tangent-space normal map (`<name>_strands_normal`, Non-Color) | normalTexture | normal map |
| anisotropic highlight | Principled Anisotropic 0.65, rotation 0.25, UV tangent | KHR_materials_anisotropy (ignored by Godot) | `anisotropy_enabled`, `anisotropy` from extras |
| light through thin hair | - | - | `backlight_enabled`, `backlight` (base colour x `backlight_share`) from extras |
| soft edge light | - | - | `rim_enabled`, `rim`, `rim_tint` from extras |
| lower specular | Specular IOR Level 0.35 | KHR_materials_specular (ignored) | `metallic_specular` from extras |

The extras are the material's `lookdev` custom property, `{"preset": "hair", "godot": {property: value}}`.
Godot's glTF importer keeps material extras as `material.get_meta("extras")` (verified on 4.7.2), so they
survive a reimport with nothing extracted. `LookdevMaterials.apply(root)` sets every listed property on every
StandardMaterial3D under `root` that has them (colours from arrays, ints from numbers), warns on a property
the material does not have, marks the material applied, and returns the names it changed. Materials are
shared by the imported scene's instances, so once is enough.

## Found on the way

- **Godot-generated tangents break anisotropy on shells.** A glb written without tangents (rig-anything's
  `export_glb` does not ask for them) makes Godot generate its own, and with `anisotropy_enabled` thin
  bright lines appear along the cap's tangent seams - the same glb exported with `export_tangents=True`
  showed none, and with anisotropy off there are none either. Until the exporter writes tangents for
  meshes whose material needs them, expect those lines close up, or set `anisotropy_enabled` false in the
  extras for that character.
- **EEVEE draws no anisotropy**; Cycles does. Judge the highlight in Cycles or in Godot.
- **Roughness 0.42 read as latex** in both engines at 1 m; the preset uses 0.55 in Blender and 0.65 in
  Godot (where the anisotropic lobe is narrower) with specular lowered.
- **Root darkening reads as a dark band** behind a pulled-back hairline; `root_mult` is 0.8, not 0.62.
