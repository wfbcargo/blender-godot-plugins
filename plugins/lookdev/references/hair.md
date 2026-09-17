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
| thinned roots and tips | image alpha -> Math Round -> Alpha | alphaMode MASK, cutoff 0.5 | the extras set `transparency` 4 (depth pre-pass): the texture's unrounded alpha blends, so the hairline fades |
| strand relief | tangent-space normal map (`<name>_strands_normal`, Non-Color) | normalTexture | normal map |
| anisotropic highlight | Principled Anisotropic 0.65, rotation 0.25, UV tangent | KHR_materials_anisotropy (ignored by Godot) | `anisotropy_enabled`, `anisotropy` from extras; tangents rebuilt from U per face, averaged where faces meet (`mesh.tangents = "per_face"`) |
| light through thin hair | - | - | `backlight_enabled`, `backlight` (base colour x `backlight_share`) from extras |
| soft edge light | - | - | `rim_enabled`, `rim`, `rim_tint` from extras |
| lower specular | Specular IOR Level 0.35 | KHR_materials_specular (ignored) | `metallic_specular` from extras |

The extras are the material's `lookdev` custom property, `{"preset": "hair", "godot": {property: value},
"mesh": {"tangents": "per_face"}}`.
Godot's glTF importer keeps material extras as `material.get_meta("extras")` (verified on 4.7.2), so they
survive a reimport with nothing extracted. `LookdevMaterials.apply(root)` sets every listed property on every
StandardMaterial3D under `root` that has them (colours from arrays, ints from numbers), warns on a property
the material does not have, marks the material applied, and returns the names it changed. Where a preset's
`mesh.tangents` is `"per_face"` it rebuilds that surface of the ArrayMesh in place - one vertex per triangle
corner, each from the triangle's U gradient made perpendicular to the corner's normal, sign +1 - keeping the
other surfaces, skin weights and materials (a mesh with blend shapes is left alone). V takes no part: the
strand texture's normal map and the anisotropy only use the across-strand axis. Materials and meshes are
shared by the imported scene's instances, so once is enough.

A corner then takes the mean of the tangents of every face that meets at its position, each flipped onto
this face's own first (mod 180 degrees, since a strand axis has no direction), and keeps its own where that
mean collapses below half. Averaging without the flip is what Godot's own generator does and what
collapses round a hole; averaging with it undoes the faceting a per-face tangent leaves where the U field
turns fast, without bringing the glints back.

**The alpha.** Along V the strands' coverage is multiplied by `smoothstep(root_fade) ^ root_fade_power`
([0, 0.11], 0.25): 0.39 at V 0.01, 0.78 at the hairline (0.045), 1 by 0.11. Blender's Round (and glTF's
MASK at 0.5) turns that into strands that start a little later and thinner; Godot's depth pre-pass blends
it, so what was an alpha-scissor comb with a crisp boundary is a fade of strand tips.

## Found on the way

- **Godot-generated tangents break anisotropy on shells.** A glb written without tangents (rig-anything's
  `export_glb` does not ask for them) gets Godot's, generated per shared vertex. Where the mesh's UV frame
  has no V change or turns over (a clamped V, V running away from a hairline on both sides of an ear) the
  corners disagree and their sum collapses: with `anisotropy_enabled`, bright glint streaks and wormy
  highlight patches; with anisotropy off, none. Blender-exported tangents fixed the streaks but left dark
  triangular patches. The fix is two-sided: humanform's cap never has flat or crown-flipped V, and
  `apply` rebuilds hair tangents per face from U.
- **A per-face tangent is faceted where the U field turns fast.** Round the axis the strands run to (a
  bun), neighbouring faces' U gradients differ by 60-80 degrees (305 of Belle's 9872 hair triangles are
  more than 35 degrees from their neighbours', nearly all within 3 cm of the bun's axis), and each flat
  facet catches a different part of the anisotropic lobe: half a dozen dark polygons, 1-2 cm across, on
  the sheen between crown and bun. They are the tangent alone - flattening the normal map leaves them,
  `anisotropy_enabled = false` removes them. Averaging the tangents of the faces that meet at each
  position, flipped mod 180 onto the face's own, removes them and keeps the hairline and the ear clean.
- **EEVEE draws no anisotropy**; Cycles does. Judge the highlight in Cycles or in Godot.
- **Roughness 0.42 read as latex** in both engines at 1 m; the preset uses 0.55 in Blender and 0.65 in
  Godot (where the anisotropic lobe is narrower) with specular lowered.
- **Root darkening reads as a dark band** behind a pulled-back hairline; `root_mult` is 0.8, not 0.62.
- **Alpha scissor makes the hairline a comb.** Hard-edged dark strand ends over skin read as a cap edge with a
  fringe at 1 m in Godot, however well they read in Blender (whose dithered alpha averages over samples).
  Alpha hash was noisy without TAA; the depth pre-pass blend is what reads as a fade.
