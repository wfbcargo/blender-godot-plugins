# hair-godot-transfer - lab notebook

Branch `hair-godot-transfer` (plugins and grungist-creek), round realism-step1, second attempt (the first
stalled with nothing committed). Started 13:01, 2026-09-18. Scratch: `%TEMP%/rw/hair-godot-transfer/`.
Crops referenced below are in [hair-godot-transfer/](hair-godot-transfer/).

## Setup (13:01-13:05)

- Worktrees from `main` 9007067 and `master` 8e25538. `tools/scratch_project.py` does not exist on main yet, so the
  scratch game was made by hand (NEXT.md "Building the project's characters"): `game/` = project.godot, icon,
  addons (synced from this branch), characters (specs' `[export] blend` pointed at `game/blend/`), build_human.py,
  save_guard.py; `HUMANFORM_LIBRARY` a copy; env in `env.sh`.
- Dead end, 1 min: resuming from a copy of the real `figure_study_man.blend` refuses ("body in this file was built
  from a different spec or plugin versions") - the real blends were built before humanform 0.10.1. `fresh=1`
  builds each figure in 62 s (man) / 110 s (woman).
- Dead end, 1 min: blends inside the scratch game make `--import` try the Blender importer; `blend/.gdignore`.
- Baseline Godot renders: `lookdev.mjs close-shot` on the game worktree's committed glbs (Step 0 ship), views
  face, eyes, hands, bone:spine.004 (the neck; `bone:neck` does not exist on these rigs), clear_midday and
  overcast, 1024 px tiles -> `base/<id>/`. Blender close set: `assets/figure_study/<id>/review/<id>/close/`.

## Tooling written first (13:05-13:10)

- `plugins/lookdev/bin/png.mjs`: PNG read/write/crop/side-by-side with Node's zlib only (no PIL or numpy on the
  system Python). Used by `stipple` and by every crop in this notebook.
- An experiment hook for isolating causes, **scratch only, not committed**: a copy of lookdev with
  `LOOKDEV_EXPERIMENT` (material property overrides by material suffix, plus `@cov`/`@edge` for the alpha extras)
  and `LOOKDEV_SUN` (sun properties, `@soft` filter quality, `@atlas`, `@msaa`, `@taa`, `@hairshadow`).

## 1. The stipple (13:05-13:20) - cause: the soft-shadow filter, not the hair

Seen: a regular lattice of single lit pixels, 5-8 px apart, over the shadowed front of both necks and the sides of
the fingers under clear_midday (`cause_stipple_filter.png`, first tile).

One variable at a time on study_man's face tile, crop of the neck (`cause_stipple_filter.png`, left to right):

| Change | Stipple |
|---|---|
| none (Step 0) | yes |
| skin `subsurf_scatter_transmittance_enabled = false` | yes - my first guess (transmittance samples the shadow map unfiltered), wrong |
| skin SSS off / pores (`detail_enabled`) off / normal map off | yes, yes, yes |
| hair shell `cast_shadow = off` (NEXT.md's guess, "hair shell casting a depth-pre-pass shadow") | yes - **not the hair** |
| `shadow_bias` 0.2 / `shadow_normal_bias` 3 / both | yes (bias 0.2 peter-pans the jaw's shadow) |
| directional shadow atlas 8192 | yes |
| `light_angular_distance` 0.2 or 0.25 | gone on the neck, **still on the fingers** (`cause_stipple_fingers.png`, 2nd) |
| soft shadow filter quality 0 (hard) | a different, coarser pattern |
| soft shadow filter quality 3 (medium) | neck clean, **fingers still stippled** (`cause_stipple_fingers.png`, 3rd) |
| soft shadow filter quality 4 (high) / 5 (ultra) | gone on neck and fingers |

Cause: Godot's default directional soft-shadow filter (soft low) takes too few taps for a 0.5 deg sun's PCSS
kernel; on skin turned from the sun the taps alias against the shadow map's texels, so the lattice is the shadow
map's grid seen through the filter (the same lag vectors, (8,5), (-1,5), (-4,4) px at 1 m, show on every stippled
tile of both figures). The sun's angular size (0.5 deg is right for the real sun) stays.

Fix: `presets.json` gives every sun `soft_shadow_filter_quality: 4`, which `LookdevPresets.apply` sets through
`RenderingServer.directional_soft_shadow_filter_set_quality` (it is project-wide, not a light property, and a
scene cannot carry it: `apply_preset.gd` warns when the project setting is below it). figure_study, close-shot
and belle_demo all go through `LookdevPresets.apply`.

Before/after on the rebuilt figures: `stipple_neck_study_man.png`, `stipple_neck_study_woman.png`,
`stipple_fingers_study_man.png`, `stipple_fingers_study_woman.png` (left Step 0, right this branch).

## 2. `lookdev.mjs stipple` (13:20-13:45)

`bin/stipple.mjs`, its own file; lookdev.mjs only imports it and adds `stipple` to `commands` (a union with any
other branch's commands). No Godot.

Attempts:
1. Luma high-pass (minus a 5x5 mean) over shadowed smooth pixels, best autocorrelation at lags 2-8 px. Neck
   old 0.747 / new 0.175 - good; but the fixed (soft high) fingers read 0.266 at lag (0,3): a finger's edge
   correlates with itself along its length.
2. Periodic only: correlation at a lag less (the positive part of) that at half the lag. Fingers fixed 0.115. But
   a single window over a large region missed the woman's middle finger (a strip 15 px wide): 0.104.
3. 48 px windows, worst window: finds the strip, and then flags everything - hair, brows, the aliased silhouette,
   a grey backdrop. Added: a second repeat at least 30 deg from the first (a lattice repeats along two directions,
   parallel strands along one); a skin test (warmer than blue, 7x7 mean luma over 0.06); 96 px windows; and the
   mask eroded 3 px (the stair-steps of an unantialiased silhouette repeat too).

Result, regions on skin (neck: face tile 330,780,360,244 and spine.004 tile 0.15,0.3,0.7,0.6; fingers: lower half
of each hand tile), full table `%TEMP%/rw/hair-godot-transfer/stipple_table.txt`:

| | clear_midday, Step 0 | clear_midday, this branch |
|---|---|---|
| study_man neck (face / spine.004) | STIPPLE 0.786 / 0.761 | clean 0.178 / 0.185 |
| study_man fingers (back L, R; palm L, R) | STIPPLE 0.845, 0.674, 0.716, 0.855 | clean 0.144, 0.205, 0.167, 0.123 |
| study_woman neck | STIPPLE 0.792 / 0.775 | clean 0.170 / 0.168 |
| study_woman fingers | STIPPLE 0.620, 0.624, 0.710, 0.681 | clean 0.175, 0.183, 0.183, 0.182 |

Controls in `lookdev.mjs selftest` (`bin/controls/`): the Step 0 neck and fingers crops must STIPPLE (0.786,
0.590), the same neck at soft high must be clean (0.178). `selftest` on the game worktree: 14/14.

Limits of the check, stated in SKILL.md: aimed at a whole tile it still flags hair edges; give it a region on skin.

**Open - overcast.** Under overcast the same lattice is there, faint, before and after: study_man's neck 0.399 at
1.46% contrast (Step 0) and 0.570 at 2.08% (this branch); study_woman's clean after. Soft ultra (5) does not
remove it (0.453 at 1.34%). Overcast's sun has `light_angular_distance` 20 and `shadow_opacity` 0.6; its kernel is
the likely cause. Not visible at the tile's scale by eye; not attempted further (three-attempt rule spent on the
detector).

## 3. The hairline and the brows (13:10-13:30)

Paired crops, Blender close set left, Step 0 Godot middle, this branch right:
`hairline_study_{man,woman}_{clear_midday,overcast}.png`, `brows_study_{man,woman}_{clear_midday,overcast}.png`.

Causes, each isolated on study_man's face tile (crops `cause_hair_alpha_mode.png`, `cause_brow_alpha.png`):

1. **Alpha mode on the mips' average (hairline).** `cause_hair_alpha_mode.png`: depth pre-pass (Step 0) - a
   translucent brown film ~1 cm below the hairline, the mip-averaged strands blended; scissor - strands, but a
   hard comb; scissor + alpha to coverage with MSAA 4x - softer, fewer strands (the project has no MSAA, so it
   would do nothing in the game anyway); alpha hash - noise without TAA; pre-pass + coverage mips + alpha ramp
   0.5 +- 0.25 - separate strands, soft, closest to Blender. TAA and MSAA 8x on the scissor hair changed little.
2. **Mip erosion.** Measured by `LookdevMaterials.coverage_mips` (share of texels at or over alpha 0.5, level 0 ->
   worst level): lashes 12.4% -> 5.1% by level 5 and 0 by level 7; brows 38.8% -> 33.6%; hair 87.8% -> 85.7%.
   After: each level within 0.5 percentage points of level 0 down to level 6 (levels 7-10, 8x2 texels and smaller, cannot hold a share).
3. **VRAM compression.** The PNGs import as BC3 with mips (Godot's default for a glb's extracted images); the
   strand alpha moves by up to 31/255 (brows mean 2.4/255, lashes 1.1, hair 0.3). coverage_mips reads the source
   PNG when present and gives an uncompressed texture. Minor next to 1 and 2.
4. **Scissor on the brow cards (brows darker and harder).** Darkest 2% of brow pixels as a share of the skin's p90
   luma, same region of the face tile: Blender 0.158; Step 0 Godot 0.078 (twice as dark, hard pixelated
   cut-outs); scissor + coverage mips 0.089; plain blend 0.263 (too light, a haze - the reason humanform went to
   scissor in the first place); blend + coverage mips + edge 0.25: **0.152**; edge 0.15: 0.113.
   `cause_brow_alpha.png`: Step 0, scissor+coverage, blend, blend+coverage+edge 0.25.
5. Not causes: texture size (12 texels/mm against 3.5 screen px/mm at 1 m); the card export (the rebuilt PNGs are
   pixel-identical to Step 0's, max difference 0, for hair, brows, lashes and normals on both figures).
   Blender's reddish fringe at the hairline is a Blender-side colour bleed at the alpha edge, not in Godot.

Fix:
- lookdev `presets/materials.json` hair: `alpha: {coverage_mips: 0.5, edge: 0.25}`, carried as material extras
  by `hair.material`; `LookdevMaterials.apply` replaces the albedo texture with `coverage_mips(...)`. The shell
  keeps transparency 4 (pre-pass).
- `strand_texture` `mode: "card"` (no opaque middle); `hair.material(pixels=(colour, normal))` for a caller's own
  hairs; the report's `pixels` says whose.
- humanform `brows.py`: `card_pixels` returns arrays and hands them to lookdev (no more writing into lookdev's
  images); brows and lashes `CARD_GODOT` transparency 1 (blend) with `CARD_ALPHA` {0.5, 0.25}; body hair's
  `_sparse` works on the arrays too. Blender-side pixels unchanged (checked, above).

Not done here (hair-hairline-lashes owns it): the man's hairline shape and spiky fringe, lash density from the
front, brow shape.

## 4. Proof on the real figures (13:22-13:44)

Scratch builds of study_man and study_woman (fresh, final) with this branch's plugins, `--import`, close-shot at
1 m, clear_midday and overcast, 1024 px -> `new/<id>/`. figure_study `--selftest` PASSED and belle_demo
`--selftest` PASSED on the game worktree with the synced addon (Belle's committed glb has no alpha extras yet;
its hair still draws: "transparency 4 OK").

## Regress

`python tools/regress.py --quick --jobs 2 --godot <game worktree>`: see the result line at the end of this file.

## What worked first time / what cost time

- First time: the soft-filter sweep (the fix was the 9th single-variable render, ~20 s each); coverage mips
  (15-30 ms a texture in GDScript); passing pixels through lookdev (identical PNGs).
- Cost: the stipple detector's false positives (25 min, three attempts); a shell loop that reused `$@` after
  `set --` (3 min) - use a Node script for tables; a bash heredoc with nested quotes failed to parse, so longer
  Python edits went into files.
