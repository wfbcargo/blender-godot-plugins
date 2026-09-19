# skin-regions - lab notebook (Step 2 - skin)

Branch `skin-regions`, worktree `.worktrees/skin-regions`, scratch `%TEMP%/rw/skr/` (`main/` = scratch game from the
main checkout with the committed assets, `wt/` = scratch game from this worktree). Started 2026-09-19 09:19 CDT.

Task: regional tone, redness and roughness that read at 1 m and full body; forehead and lips not glossy. Measure
where the effect is lost before tuning.

## 1. Measuring where the regional tone is lost (main, before any change)

Before sheets (Godot close-shot, head,hands,full, clear_midday + overcast, paired with the game's Blender close set):
`%TEMP%/rw/skr/before/study_man/sheet.png`, `.../before/study_woman/sheet.png` (`bin/shots.sh`). study_man's face,
palm and full tiles read one uniform brown; forehead and lips carry a bright specular plateau.

Probes (in `%TEMP%/rw/skr/probe/`):

**a. `regions()` coverage on the unbaked MPFB human** (`regions_probe.py`, body stage only, area from the mixed
shape; study_man / study_woman):

| region | verts w>0.5 | max w | area w>0.5 (cm2) |
|---|---|---|---|
| lips | 328 / 328 | 1.0 | 23 / 21 |
| knee | 42 / 44 | **0.86 / 0.84** | 193 / 174 |
| elbow | 64 / 72 | 0.96 / 0.93 | 132 / 113 |
| knuckle | 634 / 612 | 0.91 / 0.91 | 118 / 97 |
| palm | 2093 / 2110 | 1.0 | **1563 / 1727** |
| sole | 522 / 542 | 1.0 | 413 / 366 |
| flush | 710 / 702 | 1.0 | 80 / 71 |
| t_zone | 509 / 480 | 1.0 | 169 / 138 |

The palm is 1563 cm2 on a 1.98 m2 body - more than both whole hands. Its z range on study_man is 0.000-1.057 m:
**917 of its 2093 vertices are below the wrist by more than 15 cm - on the feet.** The hand mask is the half-space
past the wrist along the forearm axis, unbounded, and with the arms hanging it takes in the undersides of the feet
(which face the palm normal). The knee never reaches weight 1 (Gaussian centred 4 cm in front of the joint, then
smoothed), so its REGION vertices average a tint of 0.92 / 0.84 / 0.81 where the table says 0.88 / 0.76 / 0.72.

**b. The baked albedo and ORM on the saved blend** (`texel_probe.py` on the scratch copy of
`figure_study_man.blend`; each region's REGION vertices sampled at their UVs against plain skin, region 0 with
roughness 0.5; CIELAB dE76):

| region | sRGB | R/G (skin 1.404) | dE | dL | da | tint mean |
|---|---|---|---|---|---|---|
| lips | .593 .357 .270 | 1.660 | 9.4 | -2.8 | +8.7 | .905 .635 .654 |
| knee | .599 .413 .305 | 1.452 | **3.0** | +1.0 | +2.1 | .920 .840 .814 |
| elbow | .551 .377 .279 | 1.460 | **3.2** | -2.9 | +1.4 | .932 .850 .830 |
| knuckle | .596 .407 .301 | 1.462 | **3.1** | +0.6 | +2.4 | .916 .832 .804 |
| flush | .570 .389 .291 | 1.466 | **2.6** | -1.5 | +2.1 | 1.019 .885 .885 |
| palm | .660 .452 .331 | **1.460 (redder)** | 7.8 | +5.5 | +3.7 | 1.148 1.037 .980 |
| sole | .657 .454 .322 | **1.446 (redder)** | 8.2 | +5.6 | +2.8 | 1.136 1.048 .926 |

The bake is faithful: the baked texels follow the vertex tints, and the ORM's G channel follows `hf_skin_oil`
(mean difference -0.014 over all loops; lips G 0.366 vs oil 0.365, knee 0.576 vs 0.576). So the loss is **before**
the bake: knee, elbow, knuckle and flush sit at dE 2.6-3.2 against plain skin - about one just-noticeable
difference, which the lighting and the +-7 % mottle swallow - and the palm and sole tints (1.16, 1.04, 0.98) and
(1.14, 1.05, 0.92) are *redder* than skin (R/G 1.46 against 1.40), not paler-and-yellower.

**c. Godot** (`godot_mat.gd` on the scratch copy): StandardMaterial3D `StudyMan_skin` has roughness 1.0 x the ORM
texture's GREEN channel (glTF has no roughnessFactor), metallic 1.0 x its BLUE (0). The imported (VRAM-compressed)
albedo differs from the source PNG by 0.010 / 0.004 / 0.009 mean absolute per channel, the ORM's G by 0.005.
**Nothing is lost between the bake and Godot.**

**Cause, named:** (1) the region tints are too weak - dE ~3 on knees, elbows, knuckles and cheeks; (2) the
palm/sole tints push the wrong way (redder); (3) the palm mask leaks onto the feet (44 % of its vertices), which
also moves the whole-body gain; (4) the knee's weight never reaches 1. Forehead/nose/chin (`T_ZONE_ROUGH` 0.38) and
lips (0.36) bake exactly as set: the gloss is the chosen numbers, not a loss.

## 2. The fix (humanform 0.13.0, character-pipeline 0.15.0)

In `skin.py` (this branch's seam only: REGIONS, T_ZONE_ROUGH, MOTTLE, REDNESS, `regions()`, `mark()`, the bake's
region metrics; GODOT, SUBSURFACE and DETAIL untouched):
- **Palm mask bounded** to 0.24-0.28 s past the wrist along the forearm and 0.09-0.11 s from its line: palm
  vertices on the fixture's MPFB man 2092 -> 1140 (the feet no longer count as palm).
- **Knee and elbow cores reach 1** (Gaussian x 1.25, clipped); the cheek flush is wider (sigma 1.8 -> 2.4 cm, peak
  0.8 -> 0.9).
- **Tints** (linear multipliers of the brief's tone): lips (0.84, 0.46, 0.50), knee/knuckle (0.80, 0.52, 0.48),
  elbow (0.78, 0.52, 0.48), flush (1.00, 0.70, 0.70), palm (1.35, 1.35, 1.24), sole (1.32, 1.32, 1.14). Palm and sole
  are neutral-to-yellow lifts now: a first try with green over red (1.34-1.36, 1.37-1.42, ...) turned study_woman's
  shadowed palm olive in Godot, so R = G.
- **Roughness:** T-zone 0.38 -> 0.46, lips 0.36 -> 0.45 (flush 0.46 -> 0.48). Cited in the code: Weyrich et al.
  2006 (measured faces: Torrance-Sparrow m 0.25-0.45 by region) and d'Eon & Luebke 2007 (m 0.3 for skin) put skin's
  perceptual roughness (sqrt m) at about 0.5-0.6, with the oily T-zone at the low end - 0.38 (slope 0.14) is lacquer.
- **Mottle** (4.0 /m, 0.08) + (24 /m, 0.035), redness 0.07 (was (5, 0.07) + (28, 0.035), 0.05): gentle, no blotch
  visible on any tile.
- **A T-zone REGION id** (`ZONES`, id len(REGIONS)+1 where no region claims the vertex) so the bake can report the
  forehead/nose/chin roughness; plain skin (id 0) no longer includes the T-zone.
- **The measured number:** `bake` reports `contrast` = {region: {dE (CIELAB 76), dL, rg (region R/G over skin
  R/G)}} from the finished (gain-corrected) albedo, `contrast_ok`/`contrast_fail` against `CONTRAST_FLOOR` (lips
  dE>=8 and redder; knee/elbow/knuckle dE>=5, flush dE>=4, each with rg>=1.03; palm/sole dE>=5, dL>=+3, rg<=1.02),
  and `roughness` = the baked roughness (ORM G) per region, T-zone and plain skin. `look.skin` stores them on the
  material; character-pipeline's `skin_manifest` puts `contrast`, `contrast_ok`, `contrast_fail`, `roughness` in
  the manifest's skin block.
- **Control:** `HF_SKIN_LEGACY_REGIONS=1` restores 0.12.0's tints, T-zone/lip roughness, mottle, redness, knee/flush
  shapes and the unbounded palm mask. `skin_detail` marks a copy of its human under it, bakes it and must see
  `contrast_ok` false.

Attempts: 1st tints (knee (0.84, 0.62, 0.58), palm (1.22, 1.26, 1.14)) passed the floor (knee dE 6.9, knuckle 5.5 on
study_man) but read barely at 4 m; 2nd stronger (above, palm green-over-red) read well but the woman's palm went
olive; 3rd palm/sole R = G - kept.

## 3. Results

**Manifest skin block, scratch builds from this worktree** (`%TEMP%/rw/skr/wt`, `bash build.sh study_man|study_woman`,
final quality) against **main** (the committed manifests' region tones, same formula,
`probe/main_contrast.py`), dE / rg:

| region | study_man main | study_man now | study_woman main | study_woman now |
|---|---|---|---|---|
| lips | 10.17 / 1.183 | 15.17 / 1.311 | 14.08 / 1.175 | 20.60 / 1.282 |
| knee | 3.03 / 1.035 | 9.06 / 1.146 | 3.25 / 1.027 | 12.42 / 1.134 |
| elbow | 4.22 / 1.048 | 8.94 / 1.137 | 5.54 / 1.044 | 13.71 / 1.147 |
| knuckle | 3.55 / 1.042 | 7.38 / 1.111 | 5.02 / 1.041 | 11.60 / 1.123 |
| flush | 3.74 / 1.063 | 9.00 / 1.165 | 5.02 / 1.060 | 11.60 / 1.148 |
| palm (dL) | 4.35 / 1.039 (+1.8) | 8.16 / 0.977 (+7.2) | 5.42 / 1.046 (+1.8) | 9.72 / 0.997 (+8.5) |
| sole (dL) | 4.83 / 1.028 (+1.9) | 7.81 / 0.992 (+5.9) | 6.40 / 1.036 (+2.0) | 10.28 / 0.988 (+8.1) |

`contrast_ok` true on both, `tone_ok` true, `tone_error` 0.0 on both (TONE_TOLERANCE 0.03). Baked roughness now: T-zone
0.468 / 0.467, lips 0.453 / 0.454, plain skin 0.523 (main: lips texels 0.366 on study_man; the fixture's control
reads T-zone 0.405, lips 0.367).

**skin_detail fixture** (deep tone 0.45/0.31/0.23, 512 px): contrast_ok true (knee 6.05, knuckle 5.91, elbow 7.04,
flush 6.94, lips 11.90, palm 6.02 dL +5.19 rg 0.985, sole 6.21 - the committed golden at da3688b; an
earlier draft of this line quoted attempt 2's palm 6.78 / +5.8 / 0.967, corrected after critic round 1); T-zone roughness 0.468, lips 0.453. Control
(HF_SKIN_LEGACY_REGIONS=1): contrast_ok **false**, 11 misses (knee dE 2.29, elbow 2.94, knuckle 2.71, flush 2.76, lips
7.42, palm dE 3.36 / dL 1.34 / rg 1.042, sole 3.76 / 1.32 / 1.034); its T-zone 0.405 and lips 0.367 roughness are
lower than the new ones (`rougher_than_legacy` true for both).

**Godot** (after sheets `%TEMP%/rw/skr/after/<who>/sheet.png`; before `.../before/<who>/sheet.png`; side-by-side pairs
in `.../cmp/`; knee close-ups `bone:shin.L` at 0.8 m in `.../knee_main_<who>/` and `.../knee_wt_<who>/`). Rendered
crops (`bin/crop_bl.py`, same camera before and after):
- knee vs thigh, R/G of the render: study_man clear_midday 1.556/1.498 (main) -> 1.805/1.496, overcast 1.567/1.497 ->
  1.832/1.494; study_woman 1.285/1.246 -> 1.442/1.241, overcast 1.374/1.309 -> 1.574/1.307.
- cheek R/G: study_man 1.523 -> 1.687 (clear), 1.494 -> 1.666 (overcast); study_woman 1.256 -> 1.340, 1.274 -> 1.389.
  Lips 1.612 -> 1.716 / 1.434 -> 1.523.
- palm vs wrist (palm tiles, the palm is in its own shadow in both): before the palm was redder than the wrist
  (study_man 1.792 vs 1.654, study_woman 1.545 vs 1.409); now 1.694 vs 1.674 and 1.373 vs 1.401, and its median luma
  rose 0.111 -> 0.129 and 0.187 -> 0.224 while the wrist stayed 0.157 / 0.270. Honest reading: the palm reads less red
  and lighter, but in these views it stays darker than the lit wrist because it faces away from the sun.
- forehead highlight, p99 luma: study_man 0.782 -> 0.707 (clear), 0.570 -> 0.512 (overcast); study_woman 0.840 ->
  0.800, 0.671 -> 0.641; lips p99 0.682 -> 0.645, 0.730 -> 0.694. The highlight is less white (top-1 % saturation
  0.112 -> 0.186 on study_man). The overcast vertical forehead band and the nose patch on study_man are mostly gone.
  study_woman's clear_midday forehead highlight is wider (share of pixels within 3 % of its max 0.028 -> 0.066) but
  its max is 0.80 of white: a soft sheen, not a clipped plateau.
- No seam, hard edge or blotch seen on the face, hands, knee close-up or full tiles; the knee's red falls off
  smoothly (the weights stay smoothed; only lips keep their sharp vermilion edge, as before).

## 4. Regress and goldens

- `regress --quick --jobs 4` (09:58-10:02): 7 ok, pipeline_woman and skin_detail changed, nothing else. Read the
  diff: pipeline_woman moves only `skin.body_tone` (0.62/0.45/0.36 -> 0.63/0.44/0.35 - a per-vertex mean, not the
  covered-texel mean the bake holds; tone_ok true) and `skin.lips_tone` (redder); skin_detail moves the region tones,
  the marked counts (palm 2092 -> 1140, knee 40 -> 50, elbow, flush) and gains the `contrast` block with its control.
- Re-recorded with `--only skin_detail pipeline_woman --update --twice --jobs 4`: exit 0, both builds agree. Committed
  in its own commit after reading `git diff tests/golden`.
- No Godot addon or export format changed, so no `--godot` run; the scratch game imports clean and close-shot runs.
- Not done / open: no game worktree - no spec changes needed, the game's figures get the new skin when the ship step
  rebuilds them. The palm reads less red and lighter in Godot but stays darker than the lit wrist in the palm view
  (it faces away from the sun); a palm lift scaled by skin darkness (darker skin, paler palms) would be the next
  step. The knuckle floor margin on the fixture's deep tone is about 0.9 dE (5.91 vs 5.0). Nipple/genital/nail tints
  were not retuned (not floored).

Final `regress --quick --jobs 4` (10:06-10:12): `REGRESS DONE exit=0, 9 fixtures ok`, no change (log %TEMP%/rw/skr/regress_final.txt).

## 5. Critic round 1 fixes (10:17-, 2026-09-19)

Critic round 1: pass false (LOOK-S1 palm half), mergeable. Problems and what was done:

1. **Palms not paler than the skin round them in the Godot palm tiles; study_woman's overcast palm grey-olive.**
   Cause, measured on the round-1 renders (`%TEMP%/rw/skr/cmp3/crops_out.txt`, palm = centre of the palm, wrist = the
   lit inner wrist, median luma): study_man clear_midday palm 0.129 vs wrist 0.157, study_woman 0.224 vs 0.270. The
   palm faces away from the sun, so shading takes ~20-25 % off it; round 1's fixed lift (1.35, 1.35, 1.24) gave study_man
   (medium-brown) only dL +7.2 in the map and study_woman (light) +8.5 - the wrong way round for skin: palmar skin
   holds a fraction of the rest's melanin, so how much paler a palm is grows with how dark the body is. The olive
   came from the blue being held back (0.92 of R) while R = G.
   Fix: `skin.pale_tint(tone, region)` - a CIELAB lightness step dL = clip(0.5 * (80 - L*_tone), 8.5, 16) turned into
   one linear gain, times hue (1.0, 0.985, 0.95) for palms and (1.0, 0.99, 0.90) for soles. `mark(ob, tone=)` uses it;
   `look.skin` passes the brief's tone; with no tone (or under the legacy control) the table's tints stand. Tried
   min 7.0 first: study_woman's palm fell to dL +6.0 and its render luma to 0.213 (below round 1's 0.224), so 8.5.
   Manifest (wt builds): study_man palm dE 14.62 / dL +13.57 / rg 0.980, sole 14.57 / +12.76; study_woman palm
   8.03 / +7.34 / 1.003, sole 9.07 / +7.76. Renders, median luma palm vs wrist:
   | | main | round 1 | round 2 |
   |---|---|---|---|
   | study_man clear_midday | 0.111 / 0.157 | 0.129 / 0.157 | **0.155 / 0.154** |
   | study_man overcast | 0.130 / 0.152 | 0.150 / 0.151 | **0.178 / 0.149** |
   | study_woman clear_midday | 0.187 / 0.270 | 0.224 / 0.270 | 0.220 / 0.270 |
   | study_woman overcast | 0.198 / 0.241 | 0.234 / 0.241 | 0.231 / 0.241 |
   Palm R/G against wrist R/G: study_woman overcast 1.273/1.293 (round 1, the olive) -> 1.294/1.293 (same hue as the
   wrist); study_man 1.645/1.642. So study_man's palm now reads as light as the lit wrist despite facing away from
   the sun; study_woman's is lighter than main's and no longer olive, but still darker than the lit wrist - her palm
   albedo is already sRGB (0.96, 0.75, 0.62), so more lift would push it towards white. Open: on light skin the palm
   tile's self-shadow outweighs any plausible albedo step.
2. **Knuckles only faintly redder; fixture margin thin (5.91 vs 5.0).** Knuckle tint (0.80, 0.52, 0.48) -> (0.76, 0.47,
   0.44), mark sigma 1.1 -> 1.25 cm (legacy keeps 1.1). Fixture knuckle dE 5.91 -> 7.00. Render, knuckle R/G over the
   back of the hand (hand_back.L clear_midday, `cmp3/crops_k_out.txt`): study_man main 1.097, round 1 1.166, now 1.212;
   study_woman 1.126, 1.186, 1.220.
3. **`contrast_fails` skipped a floored region with no texels.** It now reports "<region>: no texels". skin_detail
   gains `control_missing_knee` (the passing report with the knee removed) which must read failed - it does
   (["knee: no texels"]). The legacy control still fails with 11 misses.
4. **Stale fixture numbers in section 3** corrected to the committed golden's (knee 6.05, palm 6.02 / +5.19 / 0.985).

Goldens re-recorded (`--only pipeline_woman skin_detail --update --twice --jobs 2`, exit 0, both builds agree), diff
read: skin_detail - region tones (palm/sole lighter: 0.51/0.36/0.26 -> 0.62/0.43/0.32 on the deep tone), contrast
(palm dE 15.50 / dL +14.17 / rg 0.984, sole 15.73, knuckle 7.00, knee 6.24, the rest within 0.3), knuckle vertex count
694 -> 808, `pale` {palm 16, sole 16} (the fixture's deep tone hits the cap), `control_missing_knee` failed; the legacy
control unchanged. pipeline_woman - skin.body_tone 0.63/0.44/0.35 -> 0.63/0.45/0.36, lips_tone R 0.59 -> 0.58,
nipple_tone 0.53/0.33 -> 0.52/0.32 (per-vertex means shifting with the lighter palms; tone_ok is the bake's covered mean).
Sheets: `%TEMP%/rw/skr/after3/study_man/`, `%TEMP%/rw/skr/after4/study_woman/` (after4/study_man is a copy of after3);
three-way pairs main | round 1 | round 2 in `%TEMP%/rw/skr/cmp3/`. No seam, hard edge or blotch on the palm, hand_back,
face or full tiles; the knuckle red stays soft.

Final `regress --quick --jobs 4` after round-1 fixes (10:32-10:37): `REGRESS DONE exit=0, 9 fixtures ok`, no change (log %TEMP%/rw/skr/regress_final2.txt).

## 6. Critic round 2 fixes (10:41-, 2026-09-19) - last round

Critic round 2: pass false (LOOK-S1 palm half only: study_woman's palm still darker than the wrist in the palm tiles,
study_man's about equal), mergeable; minor: the wt manifests were built (10:21, 10:27) before commit 4987a23.

1. **Manifest provenance.** Rebuilt both study figures in the scratch copy at HEAD b447c34 with `from=body force=1`
   (a plain rebuild said "unchanged" - the stage hash carries plugin versions, not code, so it proved nothing; `from=bake`
   is refused on a body with hair joined). Both exit 0 (10:43-10:47). The `skin` block of each new `.moves.json` is
   byte-for-byte equal to the one the critic read (tone_ok true, tone_error 0.0, contrast_ok true, same region tones,
   contrast and roughness); only `build.stage_seconds` differs. Logs `%TEMP%/rw/skr/wt/build_study_*7.log`, the old
   manifests kept in `%TEMP%/rw/skr/r3/*.before.moves.json`.
2. **Palm half of LOOK-S1: measured why it cannot be met from the skin, left open.** Split the palm/wrist render ratio
   into albedo and shading (`%TEMP%/rw/skr/r3/shade.py`; render medians are sRGB luma from `cmp3/crops*_out.txt`,
   linearised; albedo = manifest palm vs skin region tone):
   | figure / light | albedo Y palm/skin | render palm/wrist (linear) | shading palm/wrist | albedo ratio needed | palm L* needed (dL) |
   |---|---|---|---|---|---|
   | study_woman clear_midday | 0.593/0.470 = 1.26 | 0.670 | 0.53 | 1.89 | 95.4 (+21.3) |
   | study_woman overcast | 1.26 | 0.921 | 0.73 | 1.37 | 84.2 (+10.0) |
   | study_man clear_midday | 0.337/0.194 = 1.73 | 1.012 | 0.58 | 1.71 | 64.4 (+13.2) - met |
   | study_man overcast | 1.73 | 1.376 | 0.79 | 1.26 | 56.6 (+5.4) - met |
   The cupped palm gets 0.53-0.58 of the wrist's light under clear_midday on both figures - the same on dark and light
   skin, so it is geometry and light, not the albedo. On study_woman the palm would need L* 95 (paper white) to read
   paler under the sun, and dL +10 against the skin under overcast, where palmar skin on light bodies is at most a few
   L* paler than the dorsum; the current +7.3 is already at the top of plausible. So no skin change: pushing the lift
   further would give white palms in the albedo and in every other view. No switch added - nothing that exists fails;
   the unmet part needs a lighting or pose change (a flatter hand, or fill in the palm tile), which is lookdev's, not
   humanform's. Recorded as open.

No code changed this round, so no bump beyond 0.13.0 / 0.15.0 and no golden moved.

Final `regress --quick --jobs 3` after critic round 2 on b447c34 (code identical to HEAD; 10:43-10:48): `REGRESS DONE exit=0, 9 fixtures ok`, no change (log %TEMP%/rw/skr/regress_final3.txt).
