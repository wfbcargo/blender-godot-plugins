# lookdev-golden-hour - lab notebook

Round: Step 2 - skin. Branch `lookdev-golden-hour` (plugins), no game branch (the game gets the addon at ship).
Scratch: `C:/Users/pauli/AppData/Local/Temp/rw/lookdev-golden-hour/` (`game` = `tools/scratch_project.py --who
study_man,study_woman`, relative light units as the game; `game_phys` = the same copy with
`use_physical_light_units=true`; `probe/` = probe scripts and renders).

## 09:19 start

Task: golden_hour overexposes the pale study_woman and stripes the floor on the open stage. Own only the
golden_hour block; overcast is lookdev-overcast's.

## 09:21 before (main, lookdev 0.7.0)

`close-shot --views full,head --presets golden_hour,clear_midday --clip Idle` on both figures:
`before_study_woman/sheet.png`, `before_study_man/sheet.png`. The woman's face and body are a flat pale peach
glow under golden_hour; the floor carries fine parallel bands (3x crop: `probe/floor_gh.png`). clear_midday is clean.

## Overexposure: what "clipped" means under AgX

First measure: share of figure pixels (close-shot's `_mask.png`, eroded by one mask pixel) with a channel >= 250.
It reads **0.00% on every tile, golden_hour included**: AgX never hard-clips skin, it rolls it into its shoulder,
where hue and saturation wash out - the "pale" the eye sees. So a 250-level clip count is blind here.

Probe (`probe/agx_curve.gd`, emissive grey quads, Godot 4.7.2 AgX defaults, tonemap_exposure 1): scene-linear ->
display luma: 0.18 -> 0.463, 0.5 -> 0.675, 0.7 -> 0.737, **1.0 -> 0.796**, 1.5 -> 0.851, 2.0 -> 0.882, 4.0 -> 0.937.

So the check counts skin **past diffuse white**: display luma >= 0.796, i.e. brighter than a white card in the
metered key. Skin albedo is at most ~0.5, so skin only gets there when exposure is past the key.

Albedo (`lookdev.mjs tone --material skin`): study_woman skin luma **0.474** linear (sRGB 0.862,0.681,0.570) -
the pale end of real skin; study_man 0.197.

G:full, figure past white (luma >= 0.796), main:
| preset | woman | man |
|---|---|---|
| golden_hour | **4.08%** (p50 0.742, p99 0.812) | 0.00% (p50 0.553) |
| clear_midday | 0.01% (p50 0.626) | 0.00% |
| overcast | 0.00% | 0.00% |
| night | 0.00% | 0.00% |
Face tile: woman golden 9.53% vs midday 0.60%.

Cause: the sun at 7 degrees hits a standing figure face-on (cos 7 = 0.99 of its energy 3.0 on a vertical face,
where midday's 58-degree sun gives a face ~cos 58 of 1.8), and the relative exposure (1.0) meters a white card
facing that key at 0.83-1.02 with the sky fill on top: the pale skin sits at ~0.72 linear median, in AgX's
shoulder. Physical mode already exposed half a stop darker (key 0.61) and read 0.00% past white on the same
render - only relative mode (the game's) is over.

Exposure sweep (with the stripe fix below), woman G:full past white / p50: 1.0 -> 4.04% / 0.741; 0.85 -> 0.00% /
0.702; 0.75 -> 0.00% / 0.672; 0.7 -> 0.00% / 0.656; 0.65 -> 0.00% / 0.639. Chose **0.7** (-0.5 stop): golden hour
is shot under the key, it lands the relative key (0.58) beside the physical one (0.61), and it stays inside the
golden key_exposure range (-0.78 stop; limit -1.0). Lower (0.6) would sit on that limit.

## Stripes: probes (woman G:full, `stripes` on the floor below 0.72 of the picture, figure masked out)

A new measure, `bin/stripes.mjs` (`lookdev.mjs stripes`): high-passed luma of smooth floor pixels (edge filter
and a 5 px margin keep the figure's cast-shadow edge out), 96 px windows, stripe = correlation at a lag less
the positive part of that at half the lag, one direction (stipple asks for two). Limits stripe 0.3, contrast 1.2%.
First cut had contrast 0.6% and margin 3: it flagged clear_midday's cast-shadow edge (stripe 0.308, 0.66%,
`probe/mid_win.png` - an aliased penumbra). margin 5 + contrast 1.2% (stipple's) cleared it (0.15%).

Base: stripe 0.640 at lag 1,8, contrast **2.96%** (man 0.604 / 2.70%). Probe rounds (`probe/v1..v5`, one change
each from golden_hour unless named; contrast is the number that moves):
| variant | contrast | verdict |
|---|---|---|
| base (angular 1.0, normal bias 1.5, bias 0.05, filter 4, pancake 20) | 2.96% | STRIPES |
| shadow_bias 0.2 / 0.0 | 1.92% / 3.20% | STRIPES |
| normal_bias 0 / 2 / 3 / 4 / 6 | 4.37 / 2.37 / 1.43 / 0.53 / 0.26% | S / S / S / clean / clean |
| soft_shadow_filter_quality 1 | 6.77% | STRIPES |
| light_angular_distance 0.0 | 1.69% | STRIPES |
| **light_angular_distance 0.5** | **0.25%** | clean |
| max distance 40 | 2.31% | STRIPES |
| elevation 15 | 1.51% | STRIPES |
| pancake 0 / 5 / 10 / 40 | 0.29 / 1.40 / 1.29 / 2.21% | clean / S / S / S |
| blend_splits | 0.28% | clean |
| orthogonal / 2 splits | 1.33 / 2.87% | STRIPES |
| pancake 0 + angular 0 / + normal bias 0 / + filter 1 | 2.23 / 11.72 / 1.88% | STRIPES |
| angular 0.5 + normal bias 0 / + filter 1 | 7.39 / 2.29% | STRIPES |
| angular 0.5, elevation 4 | 1.38% | STRIPES |
| angular 0.5 + normal bias 2.5 or 3.0, elevation 4 | 0.33% | clean |
| angular 0.5 + normal bias 3.0, elevation 2 | 0.55% | clean |

**Cause: shadow acne from the receiver's depth slope at a grazing sun, widened by the soft-shadow kernel.** At 7
degrees the floor meets the light almost edge-on, so each shadow-map texel spans a long run of floor depth
(tan 83 = 8x the texel). The bias covers that only for taps close to the receiver point; with
light_angular_distance 1.0 the PCSS penumbra kernel reaches twice as far across the slope as at 0.5, and the far
taps land under the floor's own depth: bands. Evidence: it scales with normal bias (4.37 -> 0.26% from 0 to 6),
with the filter (quality 1 = 6.77%), with elevation (worse at 4 degrees), and halving the angular size removes it
(2.96 -> 0.25%); hard shadows (angular 0) still band (1.69%) because the bias is short at 1.5 either way. Pancake 0
and blend splits hide it at this elevation but not in combination with a weaker filter or bias - symptoms, not cause.

Fix: **light_angular_distance 0.5** (the sun's real 0.53 deg; 1.0 was an artistic "soft-edged") and **shadow
normal bias 3.0** (margin down to a 2-degree sun; at 1.5 the bands come back below ~4 degrees). Feet keep their
contact shadows at normal bias 3 (`probe/feet_cmp.png`). Stripes are a units-independent geometry problem:
physical mode had them too (2.36% main -> 0.24% fixed, `probe/vP`).

## 09:40 the checks, in close-shot

`lookdev.mjs close-shot` now measures every `full` tile (`fullLook`) and writes `look` into close.json:
`skin_past_white_pct` (limit 1%: SKIN_PAST_WHITE) and `floor_stripes` (FLOOR_STRIPES), both reported as measured.
`--presets-file` (and spec `presets_file` in close_shot.gd, passed to `LookdevPresets.apply` as `presets`) renders
another presets.json's recipes, so a control can restore main's golden_hour: `bin/controls/presets_golden_hour_0.7.0.json`.

Selftest controls (3 new, 24/24 PASSED on the scratch game with study_woman, `selftest.log`):
- shipped golden_hour, full: passes both (past white 0.00%, stripe 0.521 at 0.32%);
- lookdev 0.7.0's golden_hour: FLOOR_STRIPES (and SKIN_PAST_WHITE 4.08% on study_woman);
- 0.7.0's golden_hour two stops over (exposure x4): SKIN_PAST_WHITE 95.32% - body-independent (a darker body
  fails it too), because the 0.7.0 recipe fails past-white only on pale skin (study_man 0.00%).

## After (branch)

`after_study_woman/sheet.png`, `after_study_man/sheet.png` (golden_hour + clear_midday, full + head):
| G:full golden_hour | past white | floor stripe / contrast |
|---|---|---|
| woman main (`main_study_woman`) | 4.08% FAIL | 0.557 / 2.76% FAIL |
| woman branch (`after_study_woman`) | **0.00%** | 0.530 / **0.32%** clean |
| man main (`main_study_man`) | 0.00% | 0.549 / 2.80% FAIL |
| man branch (`after_study_man`) | 0.00% | 0.466 / 0.21% clean |
clear_midday unchanged (woman 0.01%, 0.06%). Woman p50 0.742 -> 0.656 (clear_midday 0.626). By eye: the floor is
clean; the face is still evenly lit because this sun comes from the camera side - a composition matter, not exposure.

capture --kind golden (stage `game/golden_stage.tscn`: close-shot's floor and backdrop, study_woman at rest,
camera at 0,1,4.5; `preset golden_hour` then `capture --camera Camera3D --probes`):
- main, relative: median 0.55 -> **EXPOSURE warn (0.22-0.52)**, key 0.832, key/fill 3.5 (`probe/cap_gh_base`).
- branch, relative: median 0.47, grey probe 0.38, key 0.582 (-0.78 stop), key/fill 3.4, warm/cool 18.7, no
  findings (`capture_game`).
- branch, physical (camera unchanged): median 0.48, grey 0.39, key 0.607, key/fill 3.2, no findings (`capture_game_phys`).
`_calibration` updated (golden_hour relative 0.58 / 3.4, physical re-measured 0.61 / 3.2); the top-level string is
shared with lookdev-overcast, a one-line merge.

Other presets in presets.json: byte-for-byte equal to main as parsed JSON (clear_midday, overcast,
interior_daylight, night; `_comment` too).

## Open / notes
- The 0.796 threshold is AgX at Godot 4.7.2's default agx white/contrast; a preset that changes
  tonemap_agx_white would move it (none does). A control that re-measures it would need a render.
- Overcast's floor reads stripe 0.600 at 0.65% contrast (under the 1.2% limit): faint, periodic - for lookdev-overcast.
- `stripes` without a mask flags aliased silhouettes (a probe sphere's edge in a capture: 0.329 / 1.30%); close-shot
  always passes the figure mask, and its stage has nothing else below the horizon.
- The woman is still front-lit at golden hour on this stage (sun behind the camera); a golden-hour look usually
  wants the sun to the side or behind. The preset keeps a sun's side when it is up; close-shot's fresh sun takes
  azimuth 150.
