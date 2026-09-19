# lookdev-overcast - Overcast: no mirror-like forehead band; skin keeps its tone

Round: realism Step 2 (skin). Branch `lookdev-overcast` in both repos. Started 09:19, 2026-09-19.
Scratch: `%TEMP%/rw/lookdev-overcast/` (`game/` from `tools/scratch_project.py --who study_man,study_woman`).
lookdev 0.7.0 -> 0.8.0.

## Method

- Before: `close-shot --views head,hands,full --presets clear_midday,overcast` on main's lookdev, both figures
  (`before/<id>/sheet.png`). After: the same with the branch (`after/<id>/sheet.png`).
- Probes: a copy of the plugin (`probe/lookdev`) whose `presets.json` gains overcast variants, synced into the
  scratch game's addon (close-shot applies the project's copy, and checks names against the plugin's), views
  face, eyes, full on study_man (and study_woman where noted).
- Metrics (`lookdev-overcast_measure.mjs` beside this file): in *G:face* a forehead strip (x 0.35-0.65, y
  0.25-0.32 of the picture) averaged into a column profile; **step** = the largest change across 6 px of that
  profile (a hard-edged vertical band makes it large), **band** = its peak over its median; the same in *G:eyes*
  (x 0.3-0.7, y 0.14-0.26); **nose hi** = p99/p50 luma on the nose. Skin mean in *G:full* = mean display RGB over
  the figure mask less pixels under 0.1 luma -> HSV hue, saturation, value.

## Probe numbers (study_man, overcast unless named)

main: clear_midday fh step 0.019, hue 22.3 sat 0.476 val 0.564 | overcast fh step **0.115**, eyes step 0.043,
nose hi 1.60, hue **18.0** sat **0.397** val **0.330**.

First batch (one process, 11 variants) was misleading after the 4th: `LookdevPresets.apply` sets only the sun
properties a recipe names, so `light_specular = 0` from one probe stayed on the sun for every later probe
(p_nospec and p_noreflsky gave identical numbers). Every probe after that set light_specular, sky_mode and the
shadow biases explicitly, and a repeat of the base at the end of a batch matched the first to 3 decimals.

| probe | fh step | fh band | eyes step | nose hi | hue | sat | val |
|---|---|---|---|---|---|---|---|
| base | 0.116 | 0.021 | 0.044 | 1.60 | 18.0 | 0.397 | 0.330 |
| sun shadow off | **0.012** | 0.026 | 0.018 | 1.47 | 18.2 | 0.408 | 0.324 |
| sun specular 0 | 0.009 | 0.011 | 0.016 | 1.43 | 18.5 | 0.420 | 0.324 |
| angular distance 5 deg | 0.018 | 0.041 | 0.027 | 1.47 | 18.4 | 0.398 | 0.339 |
| angular distance 0.5 deg (batch 1) | 0.011 | 0.022 | 0.017 | 1.45 | 18.5 | 0.398 | 0.341 |
| sun in sky off (sky_mode light only) | 0.101 | 0.026 | 0.041 | 1.55 | 18.3 | 0.389 | 0.348 |
| shadow bias 0.05/1.5 | 0.115 | 0.021 | 0.043 | 1.60 | 18.0 | 0.397 | 0.329 |
| soft shadow filter 2 | 0.116 | 0.021 | 0.044 | 1.60 | 18.0 | 0.397 | 0.329 |
| sun energy 0 (batch 1, specular leaked 0) | 0.009 | 0.009 | 0.016 | 1.52 | 18.1 | 0.369 | 0.257 |
| SDFGI off (batch 1, specular leaked 0) | 0.004 | 0.007 | 0.015 | 1.07 | 20.7 | 0.366 | 0.536 |

Tone levers, sun shadow off in all (both figures; woman in brackets):

| probe | hue | sat | val |
|---|---|---|---|
| shadow off | 18.2 (18.8) | 0.408 (0.282) | 0.324 (0.451) |
| + SDFGI off | 20.5 (21.2) | 0.366 (0.208) | 0.527 (0.662) |
| + SDFGI energy 2 | 18.6 (19.3) | 0.369 (0.244) | 0.412 (0.549) |
| + neutral grey sky | 19.2 (20.2) | 0.433 (0.307) | 0.335 (0.464) |
| + exposure 1.3 | 18.3 (19.0) | 0.392 (0.265) | 0.371 (0.505) |
| + fog off | 19.1 (19.3) | 0.442 (0.295) | 0.321 (0.450) |

SDFGI off brightened the skin by 0.2 but, on the open ground plane of the calibration stage, SDFGI on and off
differ little - so SDFGI was not the cause, what it saw was. close-shot's stage has a cylinder backdrop (r 9 m,
7 m tall, centre 3 m behind the figure). A probe copy of close_shot.gd without the backdrop, then one with it
kept but `gi_mode = GI_MODE_DISABLED`:

| stage | clear_midday hue/sat/val | overcast hue/sat/val | shadow off |
|---|---|---|---|
| backdrop in GI (main) | 22.3 / 0.476 / 0.564 | 18.0 / 0.397 / 0.330 | 18.2 / 0.408 / 0.324 |
| no backdrop | 22.2 / 0.436 / 0.589 | 20.1 / 0.362 / 0.508 | 20.2 / 0.368 / 0.504 |
| backdrop out of GI | 22.2 / 0.438 / 0.588 | 20.0 / 0.365 / 0.503 | 20.1 / 0.370 / 0.500 |

Woman, backdrop out of GI: clear 22.8 / 0.265 / 0.708, overcast 20.7 / 0.216 / 0.640.

## The causes, named

1. **The forehead band is the sun's shadow**, not its specular or the sky's reflection: overcast's sun had
   `shadow_enabled` with `light_angular_distance` 20 deg, and that shadow drew a hard-edged bright vertical band
   down the forehead and a patch on the nose (forehead column step 0.116 -> 0.012 with the shadow off; bias and
   filter quality change nothing; the sun disc in the sky, sky_mode light-only, changes little: 0.101). With the
   shadow off the sun's specular is a soft, low highlight (fh band 0.026, hi 1.27 in the courtyard stage; 0.008
   out of it). Overcast casts no hard shadows, so the fix is `shadow_enabled: false` (and `shadow_opacity`,
   which only applied to that shadow and leaked into later presets at runtime, is gone).
2. **The muddy / grey tone is mostly the stage**: close-shot's (and figure_study's) backdrop cylinder, seen by
   SDFGI, hides the sky below ~38 deg. Overcast is lit ~90% by its sky, so the figures were rendered as in a
   courtyard: study_man's skin value 0.33 against 0.50 with the backdrop out of GI, hue 18.0 vs 20.0.
   clear_midday, lit by its sun, barely moves (0.564 vs 0.588). Fixed on the stage: the backdrop's gi_mode
   is disabled in close_shot.gd and in the game's figure_study.gd.
3. **The rest is the sky's colour**: the blue-grey procedural sky (0.62, 0.65, 0.69 top) moved skin hue ~1 deg and
   saturation ~8% down; a neutral grey (0.66, 0.67, 0.68 top, 0.74 horizon) keeps it.
4. **Exposure**: on an open 18%-grey ground plane (`lookdev-overcast_stage.tscn`, camera 1.6 m at 4 m; clear_midday
   reproduces the calibration's key 1.07 / 2.5 stops there) main's overcast already failed its thresholds: grey
   probe 0.60 display (max 0.58), median 0.59 (max 0.58). With the neutral sky it read 0.62; exposure 0.9 -> 0.60,
   0.85 -> 0.59, **0.75 -> 0.56** (key -0.74 stops, limit -0.8), 0.7 -> 0.54 but KEY_EXPOSURE fails (-0.8).

Not the cause: SSAO (step 0.113 with it off, as the base; rerun in a clean order), fog (step 0.117 with it off;
hue +0.9, sat +0.03: kept, overcast has haze). Tonemap (linear) and sky energy 1.0 were only probed in the
leaked batch (sun specular 0), so they are not measured against the band.
Not changed: the skin material (humanform skin.py - other branches). The man's lips still read glossy under both
presets at 1 m; that is the material's roughness, open for the skin branches.

## Result

Branch (lookdev 0.8.0) vs main, close-shot `after/` vs `before/`:

| | fh step | eyes step | nose hi | full hue | full sat | full val |
|---|---|---|---|---|---|---|
| study_man main overcast | 0.115 | 0.043 | 1.60 | 18.0 | 0.397 | 0.330 |
| study_man branch overcast | 0.008 | 0.015 | 1.19 | 20.8 | 0.426 | 0.456 |
| study_man branch clear_midday | 0.015 | 0.020 | 1.38 | 22.2 | 0.438 | 0.588 |
| study_woman main overcast | 0.060 | 0.029 | 1.29 | 18.7 | 0.278 | 0.457 |
| study_woman branch overcast | 0.010 | 0.021 | 1.10 | 22.0 | 0.274 | 0.597 |
| study_woman branch clear_midday | 0.017 | 0.019 | 1.19 | 22.8 | 0.265 | 0.708 |

Tone shift clear_midday -> overcast (`lookdev.mjs tone-shift`): study_man main **-4.29 deg, -16.6%** (FAIL both),
branch **-1.40 deg, -2.6%**; study_woman main **-4.56 deg, -7.6%** (FAIL hue), branch **-0.84 deg, +3.6%**.

Capture `--probes --kind overcast` on the stage above: branch median 0.55, p1-p99 0.44-0.58, clipped 0.0%,
grey probe 0.56, key/fill 0.3 stops (key 0.597, fill 0.500 linear), cast b* -1.1 (main -3.6); only INFO
FLAT_RANGE (as main; overcast is flat). `_calibration` updated (physical mode not re-measured, said so).
clear_midday, golden_hour, interior_daylight and night are identical to main in presets.json (parsed and compared).

## The check

`lookdev.mjs tone-shift <close-shot dir>` (bin/toneshift.mjs): |hue shift| <= 3 deg and |saturation shift| <=
15% (relative) of the full tile's figure mean; reports unclamped values, the value ratio, pixel counts. close-shot
runs it when it renders full under clear_midday and overcast (tone_shift.json; exit 1 on TONE_SHIFT). Controls in
selftest: `bin/controls/tone_shift/main_0.7.0` (study_man's full tiles from main, 320 px) must fail - it does,
-4.30 deg / -16.6%; `branch_0.8.0` must pass - -1.41 deg / -2.6%. lookdev selftest 23/23 on the scratch game;
figure_study --selftest PASSED on the scratch game with the branch's figure_study.gd and addon.

## Open

- `LookdevPresets.apply` leaves on the sun any light property a previous recipe set and this one does not name
  (found by the probes; fresh processes are unaffected, figure_study's L key is). Overcast no longer sets
  `shadow_opacity`, the only such leak among the shipped recipes; a general reset is not done.
- Physical-units overcast not re-measured.
- The backdrop change moves every preset's close-shot a little (clear_midday study_man sat 0.476 -> 0.438,
  val 0.564 -> 0.588): lookdev-golden-hour's before/after numbers on main's stage will not compare with
  numbers after this merges.
- The man's lips and forehead read glossy under clear_midday: skin material (roughness), other branches.
- The forehead-band measurement is a probe script, not a shipped check (tone-shift covers LOOK-S6 only).

## Final regress

`python tools/regress.py --quick --jobs 4 --godot %TEMP%/rw/lookdev-overcast/game` (09:49-10:05): `REGRESS DONE
exit=0, 9 fixtures ok`, no change; close-shot pipeline_woman and its must-fail control, lookdev selftest 23/23.
Full output: `%TEMP%/rw/lookdev-overcast/regress_final.log`. Wall time for the branch about 50 min.
