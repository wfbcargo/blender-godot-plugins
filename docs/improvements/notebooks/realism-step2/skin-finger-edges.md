# skin-finger-edges - lab notebook (realism Step 2, skin)

Branch `skin-finger-edges`. Task: no orange-red lines at the finger edges and the thumb web (clear_midday), no
pale lines at the fingertips (overcast), keeping a warm backlit glow. Scratch: `%TEMP%/rw/sfe/` (game copy from
`tools/scratch_project.py --who study_man,study_woman`, probe renders, crops).

## 09:19 - baseline (main, humanform 0.12.0 / lookdev 0.7.0)

`close-shot --views hands,head_side --presets clear_midday,overcast` on both figures (`rw/sfe/base/<id>/sheet.png`).
Seen: study_man hand_palm.L thumb-web fleck and hand_back.R red flecks at the far hand's finger webs and along
the index finger (clear_midday); study_woman hand_back.R orange-red glow between the ring and middle fingers;
pale grey crescents at the man's fingertips under overcast (hand_back.L). From behind (head_back) the ears show
red *specks*, not a glow.

## Probes (a probe hook in the scratch copy's addon only, then close-shot `--material-set`)

Each toggled on the scratch game, clear_midday, both figures (`rw/sfe/p_*`, `c_*`, `o_*`):

| probe | orange lines/flecks | pale fingertip lines (overcast) |
|---|---|---|
| transmittance off | **gone** | still there |
| subsurface off entirely | gone (with the transmittance) | still there |
| albedo texture removed | still there (it is light, not paint) | still there |
| normal map + pore detail off | still there | still there |
| transmittance colour [0,1,0] (skin mode) | still **orange** - skin mode ignores the RGB | - |
| skin mode off | softer, colour follows the material | - |
| ORM removed, roughness 0.55 | - | mostly gone |
| metallic_specular 0 | - | **gone** |

So the orange lines are the transmittance, and the pale lines are a specular reflection of the overcast sky off a
glossy fingertip (the nail region's roughness in the baked ORM).

Why the transmittance draws lines (read from Godot 4.7.2's shaders, extracted from the binary): for a
directional light `transmittance_z = z - shadow_z`, sampled from the shadow atlas at `vertex - geo_normal *
shadow_transmittance_bias`; skin mode's `SSS_skin` then computes `d = 8.25 / depth * abs(transmittance_z)` and a
six-Gaussian profile that is ~white at d=0 and **pure red** (0.358, 0.004, 0) + (0.078, 0, 0) terms for d from
about 0.5 to 3, times `transmittance_color.a` only - the RGB is never read. At 1 cm depth that red band is 0.6-3.6
mm of "thickness", which is exactly the size of the shadow map's texels at 1 m (the presets' sun has a 150 m
shadow distance): the thickness the finger reads is noise, and it is ~0 just past the terminator where the
surface occludes itself. A real finger (15 mm, d = 12) never transmits at all; only the noise does.

## Measuring it: `lookdev edges`

Render each tile twice, as shipped and with `subsurf_scatter_transmittance_enabled=false` (close-shot's new
`--material-set`); Godot is deterministic here (base vs a rerun: identical numbers), so red(on) - red(off) is the
transmitted light. First tries that failed: a hot-pixel count by hue against the tile median (flags the palm's
lit side and grey background: useless), a local-anomaly version (flags finger creases with transmittance off too),
a local-peak of the added light (flags the silhouette of a legitimate glow). What separates a line from a glow: a
line **outshines the skin under it**. `lines` = pixels with added red >= 8 and > 0.5x the red the skin has there
without it, per thousand subject pixels; limit 0.1.

main, clear_midday: study_man hand_palm.L 1.09 per mille (worst 1.29x), hand_back.R 0.91; study_woman hand_palm.L
0.46, hand_back.R 4.19 (worst 0.92x). Overcast: 0 everywhere (its sun is weak).

## Choosing the setting (sweep with `--material-set`, `rw/sfe/ed/*`)

- Skin mode off, colour [0.95,0.60,0.48], depth 5-8 cm, strength 0.2-0.3: lines gone, soft orange glow - but
  **faces go grey** (face_3q: skin mode also picks the screen-space scatter's skin kernel; the woman loses her
  pink). Rejected: skin tone is on the "works" list.
- Skin mode on, strength 0.3: depth 1 cm passes the count but the woman's finger gap keeps a sharp red streak;
  3 cm fails study_woman hand_palm.L at exactly 0.10.
- Skin mode on, depth 5 cm, strength 0.2-0.25: passes, but with a low sun behind the hand (`--sun-elevation 15
  --sun-azimuth 90`) the whole palm glows dark red - the failure SKILL.md recorded at 8 cm.
- **Skin mode on, depth 3 cm, strength 0.2: chosen.** Every hand tile clean under both presets; backlit, the
  finger webs glow softly and the palm stays dark; main at the same backlight draws hot red contours.

The strength is the one lever against the zero-thickness noise (its brightness is `alpha * light * -NdotL`);
the depth sets which real thicknesses glow. 3 cm puts finger edges, webs and ears (<= ~10 mm, d <= 2.75) in the
profile's red tail and a palm (25 mm, d = 6.9) out of it.

## Pale fingertip lines - not this branch's seam

Cause: the specular (metallic_specular 0 removes it; a flat roughness 0.55 nearly does) on the fingertip's
glossy rim - the baked ORM's `nail` region (REGIONS rough 0.30) reaching the fingertip's underside, which the
overcast sky lights at grazing. REGIONS belongs to skin-regions. The fix I would make there: raise `nail` rough
to ~0.40 and/or keep the nail weight on the dorsal nail plate (MPFB's `fingernails` group feathers round the
free edge). Flagged, not changed here.

## 10:05 - rebuilt figures (scratch game, humanform 0.13.0), `--import`, after sheets

`bash build.sh study_man` / `study_woman`: both exit 0 (bake reran on the skin.py change; the glb extras read
depth 0.03, colour alpha 0.2). Sheets: `rw/sfe/after/<id>/sheet.png` (hands, head_side, head_back, face_3q, both
presets) against `rw/sfe/base/<id>/sheet.png`; crops `rw/sfe/ba_m.png`, `rw/sfe/ba_w.png`.

`lookdev edges` on the rebuilt figures (hands + head_back, clear_midday + overcast): **0 lines on every tile**
(worst ratio 0.43x man palm.L, 0.42x woman palm.L). Glow, clear_midday: man hand_back.R 0.18 (main 0.24),
woman 0.24 (main 0.54) - still there, now spread instead of concentrated in marks. Control on the same glbs,
`--material-set subsurf_scatter_transmittance_depth=0.01 --material-set subsurf_scatter_transmittance_color=[0.92,0.42,0.30,1.0]`:
fails exactly as main did (man palm.L 1.09 per mille / back.R 0.91; woman palm.L 0.46 / back.R 4.19).

Backlit (`--sun-elevation 15 --sun-azimuth 90`, hand_palm.L and head_back): main draws hot red contours round the
finger bases (worst 12-15x); the new setting a soft red-orange glow at the finger webs with the palm dark
(`rw/sfe/gazk5_<id>.png`: main | 3 cm 0.2 | 5 cm 0.2). Ears from behind: main red specks, now a faint smooth warm
edge (glow 0.01-0.03 both; `rw/sfe/cmp_earz_*` for main).

Stipple (LOOK-S5), `lookdev stipple --region` on the finger area of each hand tile, clear_midday: clean on 7 of 8
after (and 8 of 8 before); study_woman hand_palm.L flags 0.313 at lags -3,7 / 7,4 in window 284,452 (before
0.238). The zoom (`rw/sfe/stw3.png`, before | after) shows the same pore-detail grain in both, no shadow dither;
the transmittance change removed a red patch that had lowered the window's contrast. Whole-tile stipple on
study_man hand_back.L/.R flags thigh and forearm pore grain identically before and after (not fingers).
Recorded as open: `stipple` reads the pore detail normal's 4-7 px cell grain as a lattice on a pale, lit window.

## Regress

`regress.py --quick --jobs 4 --godot rw/sfe/game` (every fixture: regress.py changed): 22 ok, skin_detail CHANGED
`baked.godot_transmittance_depth` 0.01 -> 0.03 (the intended change); Godot side all ok, including the new
`edges pipeline_woman` (0 tiles with lines, worst 0.05 per mille, ratio 0.57) and its must-fail control (old
transmittance: 2 tiles with lines, hand_back.R 1.35 per mille, ratio 1.22), and lookdev selftest 23/23 (the two new
PNG controls: main's fingers report lines, the fixed pair is clean). Golden re-recorded with `--only skin_detail
--update --twice` (no other key moved).

Time: about 85 min to here (over the 60 min budget: the skin-mode-off detour and the backlit check cost ~20).
