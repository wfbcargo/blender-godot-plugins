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

## 11:08 - final regress

`regress.py --quick --jobs 4 --godot rw/sfe/game` after the commit (golden in): `REGRESS DONE exit=0, 23 fixtures
ok` (log `rw/sfe/regress_final.log`, 10:46-11:08). edges pipeline_woman 0 tiles with lines (worst 0.05 per mille,
ratio 0.57 - a thin margin under the 0.1 limit on the fixture body's hand_palm.L); control 2 tiles, 1.35 per mille.

Open: the pale fingertip lines (skin-regions' REGIONS `nail` rough, above); `stipple` reading pore grain on
study_woman hand_palm.L (above); the edges limit has 2x margin on the fixture but its ratio criterion trips on any
real backlit glow, so backlit tiles are judged by eye; the game's figures are not rebuilt (the ship step does it).

## Critic round 1 fixes (11:11 on)

Critic round 1: orange lines fixed, the pale fingertip crescent under overcast not (study_man
`overcast_hand_back.L`); humanform 0.13.0 / lookdev 0.8.0 collided with main. Scratch for this round:
`rw/sfe2/`.

**Versions.** Main moved twice during the round (skin-pores-distance took humanform 0.13.0 and lookdev 0.9.0,
then skin-regions took humanform 0.14.0). Merged main into the branch (7155c7c): versions taken from main
and bumped with tools/bump.py to **humanform 0.15.0, lookdev 0.10.0**. Conflicts in lookdev SKILL.md, lookdev.mjs
(usage, imports, command table: edges beside grain and stripes), close_shot.gd (sun elevation/azimuth plus
main's `presets` option) were resolved by keeping both. I took skin_detail.json from main and re-recorded it
below. Both figures were rebuilt on the merged code (exit 0) and imported.

**Pale crescent: the cause.** Every probe is study_man, overcast hand_back.L, window 180,470 200x120. "Pale add"
is the most light the specular adds to all three channels (render against `metallic_specular=0`); "px" is the
pixel count with add >= 10 and > 0.3x the skin under it:

| probe | pale add | px |
|---|---|---|
| merged branch (nail rough 0.30) | 33 | 256 |
| nail mask not smoothed (0.30) | 33 | 215 |
| nail gloss faded over the free edge's last 3-6 mm, nail 0.30 | 31 | 178 |
| fingertip pad zone at 0.62, nail gloss on the dorsal plate only | 31 | 200 |
| nail 0.40 | 21 | 144 |
| nail 0.45 | 17 | 77 |
| nail 0.50 | 14 | 22 |
| **nail 0.55 (chosen)** | 13 | 17 (not at a tip: 266,528) |
| flat roughness 0.7 (no ORM, Godot `--material-set`) | 8 | 0 |
| ORM roughness 1.0 everywhere | - | 0 |
| ORM background (G=0 outside the islands) filled with 0.5 | 33 | 256 |

The line comes and goes with the nail region's roughness and nothing else. The plate's end catches the overcast
sky at grazing. The UV-island background (roughness 0 in 31% of the ORM) and mipmapping were ruled out
(`p_fill`, `p_nomip`). A sampled ORM (`orm3.py`) showed the probes did land on the fingertip texels. Crops:
`rw/sfe2/tip_probe*.png`, `tip_n.png` (0.30 | 0.50 | 0.55), `ba_tip_m.png` (before | after).

One trap for whoever reruns this. Two renders after overwriting and restoring the ORM PNG by hand gave 18 in
place of 33 for the same code (`b1`, `b2`). Every build-then-import render reproduces 33 (`s1`, `r1`, `det1-3`,
which are identical). Only the build-then-import renders are used above.

**Fix.** REGIONS `nail` rough 0.30 -> 0.55 (humanform skin.py). This is rougher than a real nail. At 1 m the plate
is a few pixels, and at 0.50 a faint line still showed. The tint is unchanged. Toenails share the region.

**Check.** `lookdev edges --kind specular`: the same two renders as the transmittance check, but the second one is
`metallic_specular=0`. A pale pixel is one whose three channels all rise by >= 10 and by > 0.4x the brightest channel of
the skin there. PALE_LINES fires over 0.1 per thousand. Line-ratio sweep over both figures, pre and fix, hands, both presets
(`sweep.mjs`):

- 0.3: flags a grazing sheen on the lit thigh's silhouette in the fixed man (clear_midday hand_back.R, 0.44 per
  mille; overcast palm.L 0.25). That sheen is not a hand line.
- **0.4: pre man overcast hand_back.L 0.87 and palm.L 0.13 per mille fail; every fixed tile of both figures is 0.**
  Its worst ratio is 0.38x (thigh rim), so the margin is thin.
- 0.5: pre man hand_back.L still fails (0.52).

The study_woman before the fix is clean at every ratio. Her round-1 problem was the orange glow, not pale lines.

On the rebuilt figures, clear_midday + overcast hands: specular clean on 16/16 tiles. Transmittance `edges` (hands +
head_back): clean on 20/20. Glow, clear_midday: man hand_back.R 0.18, woman 0.23. Controls: the selftest has
the PNG pair `controls/pale_fingers_main_*` (pre, overcast hand_back.L crop), which gives PALE_LINES at 2.22 per mille
and exit 1, and `pale_fingers_fixed_*`, which is clean at worst 0.30x. selftest on study_man: every edges control ok. One
FAIL: "close-shot full under the shipped golden_hour passes" (FLOOR_STRIPES 0.549 at 2.80% on study_man's full
tile). That is main's golden_hour control, run on this figure rather than the regress fixture. It is untouched here.

LOOK-S5 stipple, `--region 180,300,300,250` on the clear_midday hand tiles: clean on 8/8, worst lattice
0.177 (woman hand_palm.L; round 1 had 0.313 there before the merged pore change).

skin_detail golden re-recorded with `--update --twice` and reviewed. `godot_transmittance_depth` 0.01 -> 0.03
(round 1's change). Plain skin roughness 0.523 -> 0.525 and control_legacy 0.511 -> 0.514, where the smoothed nail
weight feathers onto skin. Plugin stamps now read humanform 0.15.0, lookdev 0.10.0.

Not rechecked this round: the backlit glow (`--sun-elevation 15 --sun-azimuth 90`). The transmittance settings
did not change. The nail roughness does not enter transmittance.

### 12:00 - stale addon in the scratch game; everything above rerun

The first regress of this round (`rw/sfe2/regress_final.log`, exit 1) failed a single control: lookdev selftest's "close-shot full
under the shipped golden_hour passes" (FLOOR_STRIPES 0.550). main's lookdev.mjs and the branch's gave identical
numbers on the scratch game (`gh_main`, `gh_br`), and neither passed. The cause was the scratch game itself. Its
`addons/lookdev` was copied in round 1, before main's golden_hour and pore-detail changes (presets.json,
lookdev_materials.gd). Every Godot number in the section above was rendered with that old addon. Fix: I copied each
`plugins/*/godot/addons/*` of the branch over the scratch game's addons (only lookdev differed), reimported, and
reran everything (`rw/sfe2/redo.sh`, `redo.log`):

- Before the fix (HEAD~2's skin.py via `hf_pre`, both figures rebuilt): `edges --kind specular` gives study_man
  PALE_LINES on overcast hand_back.L at 0.86 per mille (worst 0.62x) and on overcast hand_palm.L at 0.14. study_woman is clean.
- Branch (both rebuilt): specular clean on 16/16 hand tiles, worst 0.35x. Transmittance clean on 20/20. Glow at
  clear_midday: man hand_back.R 0.18, woman 0.23. The transmittance control (main's 1 cm, alpha 1.0 via `--material-set`) fails on
  both figures: man palm.L 1.07 / back.R 0.90 per mille; woman palm.L 0.43 / back.R 4.44.
- PNG controls regenerated from these renders, overcast hand_back.L cropped to 300x200: main pair 2.18 per mille
  PALE_LINES, exit 1; fixed pair clean at 0.30x.
- Sheets: `rw/sfe2/before2/<id>/sheet.png` against `rw/sfe2/after2/<id>/sheet.png`. Fingertip crop:
  `rw/sfe2/ba2_tip_m.png`.
- Stipple, region 180,300,300,250, clear_midday hands: 7/8 clean. study_woman hand_palm.R flags 0.266 at 4 px,
  identical before and after (`stw_r.png`). The window is the heel of the palm, and the grain is main's coarse pore detail
  (skin-pores-distance), not shadow dither. The fingers show none.
