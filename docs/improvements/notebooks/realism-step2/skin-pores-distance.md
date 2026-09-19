# skin-pores-distance - pore and micro detail that still reads at 1 m

Branch `skin-pores-distance` (plugins), no game branch (the game changes only by rebuilding figures, which the
ship step does). Scratch: `C:/Users/pauli/AppData/Local/Temp/rw/skin-pores/` - `main/` (scratch game made from
this worktree before any edit = main's addons and the committed glbs), `game/` (the branch: worktree addons,
figures rebuilt), `shots/` (every close-shot set, named by variant), `py/` (probe scripts).
Started 09:19 CDT 2026-09-19.

## Seam

Owns `skin.py` DETAIL and the detail code in `lookdev_materials.gd` (`detail_normal`, `set_detail`, and new
`detail_albedo`, `_detail_maps`, `_coarse`, `_upscale_wrapped`, `_fade_mips`, `_detail_key`). Did not touch
REGIONS/roughness, GODOT/SUBSURFACE, transmittance or presets. `set_detail` now also changes `normal_scale` and
`albedo_color` when the spec says `keep_base` (see below) - both are material properties no other branch sets.

## 1. Why the pores vanished past about 1 m (measured)

Measured numbers:
- metres per UV unit (glb, `py/uvdens.py`): front of the head 1.12 m (man) / 1.08 m (woman), whole body 1.79 /
  1.71 m. UV2 (`hf_detail`) is the same map.
- main's detail: 256 px tile x 80 across UV2 -> a tile is 13.8 mm on the face, a texel 0.054 mm, a pore cell
  (48 per tile) 0.29 mm.
- close-shot's face tile at 1 m: frame 0.292 m over 640 px = 0.46 mm per pixel (eyes tile 0.25 mm/px, full body
  at 4 m 3.1 mm/px).
- So one screen pixel covers 8.5 detail texels on the face: the GPU samples mip log2(8.5) = 3.1 (trilinear 3-4),
  where the 256 tile is 32 px and holds 48 cells - 0.67 texel a cell. A box-filtered normal mip of that is the
  average normal: flat. At the eyes tile it is mip 2.2 (1.15 px a cell, still under Nyquist); at full body mip 5.2.

Experiments (the face tile at 1 m, cheek patch, `lookdev.mjs grain`, 3-7 px band as % of luma):

| variant | man clear | man overcast | woman clear | woman overcast |
|---|---|---|---|---|
| main | 0.23 | 0.38 | 0.16 | 0.21 |
| detail off (spec `normal: none`) | 0.24 | 0.37 | 0.16 | 0.23 |
| main's pores, no mipmaps | 1.45 (finest 3.44) | 2.37 (5.99) | 1.34 (2.87) | 1.98 (4.53) |
| main's pores at strength 1.0 | (0.70 on the older 5x5 high-pass; main 0.47 there) | | | |

**Named cause: mip averaging of sub-pixel pores.** Main's detail adds nothing measurable at 1 m (main = detail
off to the second decimal). The pores are there - sampled without mips they fill the band - but only as
aliasing salt-and-pepper (finest 2.9-6 %, `shots/nomips_*/..._cheek.png` shows a pixel checker), which is why
mips exist. Strength is not the cause (1.0 instead of 0.35 moves it a little). A side finding: Godot's detail
mix is a lerp of the two normal maps' colours by the detail albedo's alpha, so `strength` 0.35 also took 35 % off
the baked body normal map everywhere.

## 2. The fix (lookdev 0.8.0, humanform 0.13.0)

A second, coarser octave that is 2+ pixels at 1 m and under a pixel at full body:
- `_coarse`: a periodic Voronoi pattern (12 cells per tile) - a pit at each cell centre (40 % of a cell in radius,
  random depth 0.3-1 so no lattice shows) and shallow furrows on the borders. Made periodic in GDScript (3x3
  wrapped neighbours) rather than with FastNoiseLite's `get_seamless_image`, whose cross-fade skirt leaves a visible
  seam band in every tile (`proto/h_*_512.png`) - fine for 0.3 mm pores, a grid line for a 2 mm octave.
- tile 512 px x 40 (pores unchanged in size: 96 cells per tile), height = 0.3 pores + 0.7 coarse (native
  `blend_rect` of the upscaled coarse with alpha 0.7), normal at bump 5.5.
- a detail albedo from the coarse octave (128 px, its own size): the skin's linear colour times
  1 - cavity (0.26) x depth after Godot's mix. This is what makes the grain show in diffuse light; the normal
  alone shows only in highlights.
- `_fade_mips`: every mip level where a coarse cell spans under 3 texels fades towards flat (all the way by 1.5).
  Without it, a half-pixel camera shift at full body changed the pixel-level detail up to 45 % more than main
  (control in 3); with it, the same as main.
- `keep_base`: `normal_scale /= 1 - strength` gives the baked normal map back what the lerp takes;
  `albedo_color` is lifted by 1 / the cavity's mean (0.951), so the tone is unchanged: cheek mean luma main
  0.398 / 0.229 / 0.564 / 0.366, branch 0.399 / 0.229 / 0.564 / 0.366.
- `shared`: the texture ignores the per-body seed, so every body shares one (a crowd pays once).
- A spec without `coarse_cells` takes exactly main's path: main's glbs rendered with the branch addon measure the
  same to 0.01 (`shots/compat_*`).

Attempts (face 1 m cheek grain, woman clear / man overcast; look at `shots/cmp_v*`):
- v1 furrow network (F2-F1) 16 cells, cavity 0.08: 0.43 / 1.05 on the old 5x5 measure - faint.
- v2 same, cavity 0.16, bump 5: clearly visible but reads as reptile scales / cobbles in the eyes tile
  (`shots/cmp_v2_eyes_w.png`). Rejected.
- v3 pits 20 cells: too fine, mips to nothing (0.40 / 1.16 old measure).
- v4 pits 14 cells, cavity 0.14: pores visible in the eyes tile, faint at 1 m.
- v5 pits 12 cells, cavity 0.20: good in the eyes tile; 0.41 at 1 m.
- v6/v7 cavity 0.26, bump 5.5, coarse 0.7: chosen look. v8 added the mip fade, v9 the shared seed and the 128 px
  albedo. Final = v9 = the rebuilt figures (`shots/after_*`).

## 3. Measures

`lookdev.mjs grain` (new): luma band-passed (3x3 mean less 7x7 mean: 3-7 px features) over warm skin pixels, RMS
as % of mean luma (`grain`), and the pixel-to-pixel part apart (`finest`). The first version was a plain 5x5
high-pass; Godot's renderer dither (a regular 1-2 px pattern, visible in main's cheek crops, relatively stronger
on dark skin) put main's man-overcast at 1.07 % there, above the branch's woman-clear - the band-pass drops it.
Check: `--region cheek --min 0.40 --max-finest 2.0` (limits set from the data: main's highest grain 0.38, the
branch's lowest 0.47; the branch's highest finest 1.47 - its 2 mm pits are 2-4 px at 1 m - and the mip-less
pores' lowest 2.87; 1.5 was tried first and was too close to the branch's 1.47). Controls in `lookdev.mjs selftest` (crops of the cheek
patch in `bin/controls/`): branch passes; main (man overcast, main's highest) and detail-off fail SMOOTH;
main's pores without mips pass the band but fail NOISY.

Face tile at 1 m, cheek (grain %, finest %), before -> after (rebuilt figures, `shots/main_*`, `shots/after_*`):

| | man clear | man overcast | woman clear | woman overcast |
|---|---|---|---|---|
| main | 0.23 / 0.42 | 0.38 / 0.93 | 0.16 / 0.25 | 0.21 / 0.40 |
| branch | 0.61 / 0.80 | 0.94 / 1.47 | 0.47 / 0.64 | 0.70 / 0.96 |

Full body at 4 m, torso patch `0.45,0.40,0.09,0.07` (grain / finest): main 0.31/0.53, 0.58/0.69, 0.17/0.25,
0.31/0.47; branch (after) 0.31/0.52, 0.58/0.67, 0.17/0.25, 0.31/0.48 - no added texture or noise at full body.

Shimmer (`py/dolly.sh`, `py/shimmer.mjs`): full at 4 m, t=0.5, camera moved 1.7 x 1.1 mm (about half a pixel),
change of the pixel-level detail, % of luma, torso / thigh:

| | man clear | man overcast | woman clear | woman overcast |
|---|---|---|---|---|
| main | 0.621 / 2.078 | 0.688 / 2.034 | 0.310 / 0.503 | 0.469 / 0.530 |
| branch (after) | 0.606 / 2.076 | 0.678 / 2.045 | 0.303 / 0.506 | 0.455 / 0.578 |
| branch, mip fade off (control) | 0.670 / 2.134 | 0.804 / 2.075 | 0.362 / 0.726 | 0.624 / 0.769 |

The control is the same build with `_fade_mips` returning its input (scratch addon only, restored after): up
to 45 % over main (woman clear thigh 0.726 against 0.503), so the fade is what keeps full body at main's level.
(A first try dollied the camera 4.00 -> 4.03 m: useless, close-shot refits the full view so the picture barely
moved.) Full-body torso grain/finest with the fade off: 0.33/0.59, 0.54/0.74, 0.19/0.31, 0.34/0.58.

## 4. Cost

`LookdevMaterials.last_detail` and `py/cost.gd` (3 runs each):
- texture memory: main 256 px RGBA8 normal with mips = 0.35 MB per body seed (+ a 4x4 albedo). Branch: 512 px
  normal (1.40 MB) + 128 px albedo (0.09 MB) = 1.49 MB, **shared by every body** (`shared`). Uncompressed,
  like main's.
- generation: main about 11 ms per seed (FastNoiseLite 256 + normal, from `proto/proto.gd`). Branch 143-180 ms,
  once per session: coarse Voronoi in GDScript 60 ms, cubic upscale 22 ms, pores 32 ms, normal + mips 29 ms,
  fade 3 ms. `LookdevMaterials.apply` on a whole study figure (hair coverage mips included) is 240-900 ms on both
  main and branch (noisy; dominated by other work). A first version with per-body seeds and a 512 px albedo was
  2.8 MB and 150 ms per body.

## 5. Notes and open

- Any change to skin.DETAIL changes the bake stage's hash (`code:humanform.skin`), and since a bake cannot be
  taken off, the pipeline rebuilds from body: 2.3 min per study figure. The ship step pays that for every figure.
- Toksvig / roughness-from-variance was not done: StandardMaterial3D has no detail roughness, so the pore variance
  the mips lose cannot become roughness without a custom shader. The mip fade drops it instead.
- Pores in the fine octave still use `get_seamless_image` (its skirt band is under a pixel at 1 m).
- The eyes tile (0.25 mm/px) shows pores clearly; a critic may find the forehead in clear_midday a touch strong.
- The grain limits (0.40 / 1.5) are measured on 640 px close-shot tiles; another tile size needs its own.
