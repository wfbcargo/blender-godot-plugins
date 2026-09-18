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
| thinned roots and tips | image alpha -> Math Round -> Alpha | alphaMode MASK, cutoff 0.5 | the extras set `transparency` 4 (depth pre-pass); `alpha.coverage_mips` 0.5 rebuilds the mips so each level keeps level 0's share of texels over 0.5, and `alpha.edge` 0.25 ramps alpha from 0 at 0.25 to 1 at 0.75: separate strands at the hairline at any distance |
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
other surfaces, skin weights and materials. V takes no part: the strand texture's normal map and the
anisotropy only use the across-strand axis. Materials and meshes are shared by the imported scene's
instances, so once is enough.

A mesh it cannot retangent it leaves untouched and unmarked, returning `false`: blend shapes are the case,
since the rebuild de-indexes and a shape's arrays are indexed against its surface, and so is a surface that
is not a triangle list. Nothing is torn down and `lookdev_tangents` is not stamped, so the mesh is not
counted in `tangents_per_face` and a later correct pass still runs. (character-pipeline bakes shape keys
away before export, so the shipped path never has them; lookdev is general-purpose and any mesh can arrive
at `apply`.)

A corner then takes the mean of the tangents of every face that meets at its position, each flipped onto
this face's own first (mod 180 degrees, since a strand axis has no direction), and keeps its own where that
mean collapses below half. Averaging without the flip is what Godot's own generator does and what
collapses round a hole; averaging with it undoes the faceting a per-face tangent leaves where the U field
turns fast, without bringing the glints back.

**The alpha.** Along V the strands' coverage is multiplied by `smoothstep(root_fade) ^ root_fade_power`
([0, 0.11], 0.25): 0.39 at V 0.01, 0.78 at the hairline (0.045), 1 by 0.11. Blender's Round (and glTF's
MASK at 0.5) turns that into strands that start a little later and thinner; Godot's depth pre-pass blends
it, so what was an alpha-scissor comb with a crisp boundary is a fade of strand tips.

**A feathered hairline (lookdev 0.7.0, off at the defaults).** Four strand settings for a hairline that thins
out instead of starting on a ruled line, used by humanform's `short_crop`: `root_ragged` (V by which the opaque
middle's start wanders across U past `root_zone[1]`, a slow wave plus a value per strand blurred over three),
`root_power` (each strand's root skewed toward that start: < 1, fewer strands reach the edge), `root_width`
(a strand's width at its root, as a share; 0.35 before) and `fine_per_tile` (short, thin, lighter hairs rooted
before the dense hair starts). They draw from their own random stream, so a preset without them gets exactly
the texture it always did.

Also in 0.7.0, **edge hairs** (off at the defaults: `edge_hairs` 0): `edge_hairs` short hairs per tile scattered in
front of the dense start, more of them nearer it (`edge_power`), reaching up to `edge_depth` of V in front of it
(the reach itself wandering 0.4-1.6 x across U), each `edge_len` long and `edge_width` of the strand pitch wide,
leaning `edge_lean` texels off a slowly turning direction, and lighter toward the front by `edge_tone`. With the
long strands rooted close to the dense start (`root_power` well under 1), the hairline is a thinning scatter of
hairs instead of a comb of parallel spikes. Their own random stream (seed + 15485), so nothing else moves.

**The alpha in Godot (lookdev 0.6.0).** The Blender close set drew fine strands at the hairline and Godot a
smeared shell; brows came out harder and darker. Measured on study_man and study_woman at 1 m (notebook
`realism-step1/hair-godot-transfer`), the causes:

- *The alpha mode, blending the mips' average.* A strand one texel wide averages with its gaps into grey alpha by
  the second mip; depth pre-pass blended that into a translucent film a centimetre deep below the hairline.
  Scissor gave strands back (a hard comb), alpha hash was noise without TAA, alpha to coverage needs MSAA the
  project does not have. What reads like Blender's supersampled alpha test is the pre-pass kept, fed alpha that
  is ramped over 0.5 +- 0.25 (`alpha.edge`): 0 below 0.25, so no film; soft over half a strand's width.
- *Mip erosion.* Box mips lose coverage: the lash texture keeps 12.4% of texels over 0.5 at level 0, 5.1% by
  level 5 and none by level 7; the hair 87.8 -> 85.7%, the brows 38.8 -> 33.6%. `LookdevMaterials.coverage_mips`
  scales each level's alpha until as many texels pass 0.5 as at level 0 (Castano), reported per level in
  `LookdevMaterials.last_coverage`. It reads the source PNG when it is on disk, because the import's VRAM
  compression (BC3) moves the alpha of a strand a texel wide by up to 31/255 (mean 2.4/255 on the brows), and
  gives an uncompressed texture; 15-30 ms per texture.
- *The brows' scissor.* Cut at 0.5, each brow hair is solid and a screen pixel either black or skin: the darkest
  2% of brow pixels were half as bright as Blender's (0.078 of the skin's luma against 0.158). Blended with the
  ramp, 0.152. humanform's brow and lash cards now blend (`CARD_GODOT` transparency 1, `CARD_ALPHA`).
- Not a cause: the texture size (512 x 1024 per 4 cm tile is 12 texels a mm; at 1 m and 1024 px the screen has
  3.5 px a mm), the import's detect-3D flag (the textures were already VRAM-compressed with mipmaps, the default
  for a glb's extracted images), and the card export (Blender and Godot read pixel-identical PNGs).

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
