# asym-motion-demo - motion_demo reads each body's left against its right; is 0.35 subtle or inert?

NEXT.md "Where to pick up" item 2, the game-side follow-on to `asym-godot-meter` (rig-anything 0.38.0,
merged at `3434209`). Branches `asym-motion-demo` in both repos: plugins off `main` at `45a97cd`, the game
off `master` at `dd94be9`. Scratch: `%TEMP%/rw/amd/`. Started 04:42, 2026-09-21. This branch MEASURES:
no character, spec, blend, export or asymmetry value was changed, and no plugin code changed (so no bump).

## What was built (grungist-creek `55cd66a`)

- `addons/rig_anything/` gains `asymmetry_meter.gd` and `verify_asymmetry.gd` from the merged plugin
  (plus the `.uid`s Godot wrote). `diff -rq --strip-trailing-cr` against
  `plugins/rig-anything/godot/addons/rig_anything`, ignoring `.uid`: identical.
- `motion_demo.gd`: one `AsymmetryMeter` per line-up body, sampled every physics tick with the playing
  clip's phase, reset with the demo's own meters (clip change, M, a gait key). The selftest prints per
  body per clip (Walk, Run), for all six channels,
  `MOTION_DEMO   <who> <clip>  ASYM <channel>  +lat .. -lat .. ratio .. index .. diff ..` and the stance
  offset. The HUD gets a "left vs right" block (arm swing, step, stride, shoulder dip indices, lag diff),
  refreshed once a second (report() walks every sample); the HUD's meter restarts after 40 strides.
  The selftest ends by printing the HUD (`MOTION_DEMO HUD | ...`) so its rows are seen to render.
- New checks, 16 rows: per body per clip, the meter read >= 3 whole cycles with no problems (8), and
  the asymmetry check (8), below.
- `--control=mirror`: `MirrorMeter`, an inner subclass of `AsymmetryMeter`, overwrites every -lat
  limb's signals (foot fore-aft, carry angle, dip, chest dip) with its +lat partner's shifted half a
  cycle - what a mirror-symmetric body plays - just before `report()`, then restores them.

## The check, and why it is not "every channel over the floor"

A body whose manifest turns asymmetry on (`variability.asymmetry > 0`, read for that yes/no only) must
read NON-ZERO on at least one of arm swing (index) and lag (|+lat - -lat|), on Walk and on Run. Non-zero
is "over twice what a mirror-symmetric build reads at the game's import": asym-godot-meter's own
`zero` and `mirror` rows "as the game imports it, at 60 Hz" (`%TEMP%/rw/agm/final_quick_regress3.log`):
arm index 0.00514, |lag diff| 0.00572. Each gated reading also prints whether it is over the fixture's
"is asymmetric" floors (0.04, 0.012).

The first version gated every channel at the fixture's floors (arm 0.04, step 0.04, lag 0.012) and
failed 6 of 8 rows on the real figures. That was not a meter fault, and I did not move a floor:

1. **The draw lands near zero on some channels.** `variability.draw` gives each channel
   `SPREAD * asymmetry * u`, u uniform in (-1, 1). At 0.35, computed from each manifest's seed for this
   analysis only (never in the check, `%TEMP%/rw/amd/draws.py`):

   | | arm_swing | step_length | shoulder_dip | lag (cycles) |
   |---|---|---|---|---|
   | max at 0.35 | +-0.1225 | +-0.0105 | +-0.0875 | +-0.014 |
   | Marco | -0.0155 | +0.0003 | -0.0194 | +0.0052 |
   | Mei | +0.0471 | -0.0056 | +0.0408 | -0.0003 |
   | Belle | -0.0893 | +0.0061 | +0.0179 | +0.0113 |
   | Ruth | -0.0037 | -0.0034 | -0.0454 | +0.0116 |
   | study_man | -0.0609 | -0.0032 | +0.0668 | +0.0053 |
   | study_woman | -0.0234 | -0.0024 | +0.0458 | +0.0060 |

   Ruth drew 0.4% on arm swing and Mei 0.0003 cycles of lag: those channels are inert in the BAKE
   (Blender's `variability.measure`, below: Ruth arm index 0.009 / 0.002, Mei lag diff -0.006 / +0.002).
   "Every channel non-zero" is false of the characters as built, so no check can hold it.
2. **The game's import moves step length and shoulder dip more than the draw does.** At the clip's own
   keys (fps 24, optimizer off, tick 1/24, `%TEMP%/rw/amd/scr2/keys.log`) the engine meter reproduces the
   bake to the digit (Belle Walk step index 0.22145 both, Ruth Walk 0.04023 both). At the game's own import
   the stance offset moves by up to 25 mm against the bake - study_man's walk -12.9 -> +12.2 mm and run
   +9.8 -> -12.2 mm (sign flips), Mei's run +5.1 -> -17.3, Belle's walk +41.0 -> +18.3. A symmetric body
   could read a step index of ~0.1 there, and asym-godot-meter showed a symmetric body's run dip reads
   0.05. So step and dip are printed and not gated. Arm swing (index within 0.004 of the bake on all six)
   and lag (diff within 0.0025) survive, and are what the check reads.

The margin of two over the symmetric reading is mine; everything it multiplies is measured. The
thinnest passes: Marco Walk arm 0.0266 (x2.6 of the line), Marco Run lag 0.0140 (x1.2 of 0.0114).

## Runs (all in the game worktree, after `--headless --import`, which was clean)

- baseline on `dd94be9` before any edit: `MOTION_DEMO ok, 0 failures`, 55 ok (`%TEMP%/rw/amd/baseline.log`).
- `motion_demo.tscn -- --selftest`: **71 ok, 0 FAIL, exit 0** - the 55 pre-existing, 8 cycle rows,
  8 asymmetry rows (`%TEMP%/rw/amd/selftest.log`).
- `motion_demo.tscn -- --selftest --control=mirror`: **63 ok, 8 FAIL, exit 1**; the 8 failures are
  exactly the 8 asymmetry rows (`%TEMP%/rw/amd/control_mirror.log`). Arm index 0.000-0.005, lag diff
  0.000-0.0013 under the control.
- the demo without `--selftest`, `--quit-after 900`: exit 0, no ERROR (the HUD path).

What cost time: the first mirror control shifted by the NEAREST sample, which is up to half a tick off -
at a run's ~36 ticks a cycle that is 0.014 cycles of lag diff, over the lag line, so the control PASSED
on three runs (Marco, Belle, Ruth: 0.0133). Interpolating between the two samples either side fixed it
(now <= 0.0013). A control that can pass by its own quantisation is worth catching: it did.

## The numbers - the four line-up bodies (engine, the game's own import, 60 Hz, ~8 cycles)

**Marco**

| channel | Walk +lat / -lat | ratio | index | Run +lat / -lat | ratio | index |
|---|---|---|---|---|---|---|
| arm_swing_deg | 41.22 / 42.33 | 0.9738 | 0.0266 | 50.73 / 52.47 | 0.9667 | 0.0338 |
| step_length_m | 0.3691 / 0.3367 | 1.0961 | 0.0917 | 0.4280 / 0.3925 | 1.0904 | 0.0865 |
| stride_m | 0.7010 / 0.7107 | 0.9863 | 0.0138 | 0.8175 / 0.8236 | 0.9926 | 0.0074 |
| shoulder_dip_m | 0.0150 / 0.0151 | 0.9927 | 0.0074 | 0.0220 / 0.0223 | 0.9877 | 0.0123 |
| shoulder_dip_chest_m | 0.0073 / 0.0075 | 0.9735 | 0.0268 | 0.0191 / 0.0191 | 1.0012 | 0.0012 |
| lag_cycles | 0.0280 / 0.0229 | 1.2199 | 0.1981 | 0.0407 / 0.0267 | 1.5239 | 0.4152 |
| lag diff (+lat - -lat) | +0.0050 | | | +0.0140 | | |
| stance offset m | +0.0162 | | | +0.0178 | | |

**Mei**

| channel | Walk +lat / -lat | ratio | index | Run +lat / -lat | ratio | index |
|---|---|---|---|---|---|---|
| arm_swing_deg | 43.25 / 40.08 | 1.0789 | 0.0759 | 52.67 / 47.96 | 1.0982 | 0.0936 |
| step_length_m | 0.3991 / 0.3981 | 1.0025 | 0.0025 | 0.4347 / 0.4692 | 0.9264 | 0.0764 |
| stride_m | 0.8020 / 0.7923 | 1.0122 | 0.0122 | 0.9053 / 0.9024 | 1.0033 | 0.0033 |
| shoulder_dip_m | 0.0129 / 0.0125 | 1.0315 | 0.0310 | 0.0197 / 0.0183 | 1.0743 | 0.0716 |
| shoulder_dip_chest_m | 0.0064 / 0.0059 | 1.0854 | 0.0819 | 0.0167 / 0.0155 | 1.0772 | 0.0743 |
| lag_cycles | 0.0231 / 0.0287 | 0.8079 | 0.2125 | 0.0353 / 0.0316 | 1.1180 | 0.1114 |
| lag diff (+lat - -lat) | -0.0055 | | | +0.0037 | | |
| stance offset m | +0.0005 | | | -0.0173 | | |

**Belle**

| channel | Walk +lat / -lat | ratio | index | Run +lat / -lat | ratio | index |
|---|---|---|---|---|---|---|
| arm_swing_deg | 44.81 / 51.68 | 0.8670 | 0.1425 | 45.81 / 54.28 | 0.8439 | 0.1694 |
| step_length_m | 0.3862 / 0.3496 | 1.1047 | 0.0995 | 0.4359 / 0.3924 | 1.1107 | 0.1049 |
| stride_m | 0.7418 / 0.7299 | 1.0163 | 0.0161 | 0.8272 / 0.8294 | 0.9974 | 0.0026 |
| shoulder_dip_m | 0.0132 / 0.0131 | 1.0101 | 0.0100 | 0.0233 / 0.0227 | 1.0294 | 0.0290 |
| shoulder_dip_chest_m | 0.0064 / 0.0061 | 1.0403 | 0.0395 | 0.0171 / 0.0160 | 1.0673 | 0.0651 |
| lag_cycles | 0.0345 / 0.0170 | 2.0359 | 0.6825 | 0.0445 / 0.0208 | 2.1425 | 0.7271 |
| lag diff (+lat - -lat) | +0.0176 | | | +0.0237 | | |
| stance offset m | +0.0183 | | | +0.0217 | | |

**Ruth**

| channel | Walk +lat / -lat | ratio | index | Run +lat / -lat | ratio | index |
|---|---|---|---|---|---|---|
| arm_swing_deg | 41.48 / 41.73 | 0.9941 | 0.0059 | 50.77 / 50.79 | 0.9997 | 0.0003 |
| step_length_m | 0.3616 / 0.3390 | 1.0665 | 0.0643 | 0.4081 / 0.3985 | 1.0242 | 0.0239 |
| stride_m | 0.6998 / 0.7014 | 0.9977 | 0.0023 | 0.8026 / 0.8107 | 0.9899 | 0.0101 |
| shoulder_dip_m | 0.0134 / 0.0139 | 0.9648 | 0.0358 | 0.0187 / 0.0198 | 0.9422 | 0.0595 |
| shoulder_dip_chest_m | 0.0061 / 0.0066 | 0.9258 | 0.0771 | 0.0161 / 0.0168 | 0.9574 | 0.0436 |
| lag_cycles | 0.0342 / 0.0173 | 1.9793 | 0.6574 | 0.0449 / 0.0206 | 2.1851 | 0.7442 |
| lag diff (+lat - -lat) | +0.0169 | | | +0.0244 | | |
| stance offset m | +0.0113 | | | +0.0048 | | |

Belle's rows agree with asym-godot-meter's ad hoc Belle table to the printed digit, from a different
driver (motion_demo's own ticks, ~8 cycles, against verify_asymmetry's 12).

## study_man and study_woman (figure_study), once

`verify_asymmetry.gd` in the game worktree, the game's own import, 60 Hz, 12 cycles
(`%TEMP%/rw/amd/study_figures_meter.log`):

| | StudyMan Walk (+lat / -lat, index) | StudyMan Run | StudyWoman Walk | StudyWoman Run |
|---|---|---|---|---|
| arm_swing_deg | 39.78 / 44.01, 0.1010 | 49.19 / 55.38, 0.1184 | 41.04 / 42.67, 0.0388 | 48.93 / 51.14, 0.0442 |
| step_length_m | 0.3975 / 0.3731, 0.0634 | 0.4346 / 0.4591, 0.0548 | 0.3752 / 0.3571, 0.0493 | 0.4170 / 0.4037, 0.0325 |
| stride_m | 0.7719 / 0.7694, 0.0033 | 0.8970 / 0.8905, 0.0073 | 0.7352 / 0.7293, 0.0082 | 0.8158 / 0.8257, 0.0120 |
| shoulder_dip_m | 0.0155 / 0.0146, 0.0582 | 0.0240 / 0.0217, 0.1017 | 0.0138 / 0.0133, 0.0378 | 0.0203 / 0.0186, 0.0889 |
| shoulder_dip_chest_m | 0.0078 / 0.0070, 0.1023 | 0.0206 / 0.0184, 0.1145 | 0.0065 / 0.0061, 0.0702 | 0.0174 / 0.0156, 0.1094 |
| lag diff (cycles) | +0.0050 | +0.0121 | +0.0060 | +0.0131 |
| stance offset m | +0.0122 | -0.0122 | +0.0090 | +0.0067 |

verify_asymmetry's all-channel "is asymmetric" verdict: both Walks FAIL (lag under 0.012), both Runs
pass. By this branch's check both would pass on arm swing (0.039-0.118, over 0.0103).

## Bake against engine (Blender `variability.measure` on scratch copies of the real blends)

`tools/scratch_project.py` copies (`%TEMP%/rw/amd/scr`, `scr2`), `%TEMP%/rw/amd/bake_measure.py`, read
only, never saved. Index, bake / engine at the game import:

| | arm swing | step length | shoulder dip | lag diff | stance offset mm |
|---|---|---|---|---|---|
| Marco W | 0.029 / 0.027 | 0.069 / 0.092 | 0.018 / 0.007 | +0.0052 / +0.0050 | +12.3 / +16.2 |
| Marco R | 0.031 / 0.034 | 0.064 / 0.087 | 0.029 / 0.012 | +0.0117 / +0.0140 | +13.3 / +17.8 |
| Mei W | 0.077 / 0.076 | 0.021 / 0.003 | 0.041 / 0.031 | -0.0057 / -0.0055 | +4.2 / +0.5 |
| Mei R | 0.093 / 0.094 | 0.022 / 0.076 | 0.066 / 0.072 | +0.0019 / +0.0037 | +5.1 / -17.3 |
| Belle W | 0.143 / 0.143 | 0.221 / 0.100 | 0.018 / 0.010 | +0.0175 / +0.0176 | +41.0 / +18.3 |
| Belle R | 0.171 / 0.169 | 0.112 / 0.105 | 0.016 / 0.029 | +0.0233 / +0.0237 | +23.6 / +21.7 |
| Ruth W | 0.009 / 0.006 | 0.040 / 0.064 | 0.039 / 0.036 | +0.0171 / +0.0169 | +7.0 / +11.3 |
| Ruth R | 0.002 / 0.000 | 0.033 / 0.024 | 0.067 / 0.060 | +0.0240 / +0.0244 | +6.7 / +4.8 |
| study_man W | 0.100 / 0.101 | 0.067 / 0.063 | 0.064 / 0.058 | +0.0050 / +0.0050 | -12.9 / +12.2 |
| study_man R | 0.125 / 0.118 | 0.043 / 0.055 | 0.094 / 0.102 | +0.0123 / +0.0121 | +9.8 / -12.2 |
| study_woman W | 0.034 / 0.039 | 0.049 / 0.049 | 0.039 / 0.038 | +0.0059 / +0.0060 | +8.9 / +9.0 |
| study_woman R | 0.044 / 0.044 | 0.041 / 0.033 | 0.067 / 0.089 | +0.0129 / +0.0131 | +8.6 / +6.7 |

Two findings beyond this branch's question:

- **The step asymmetry is not the draw's.** The step draw is at most 0.6% of the stroke (Belle +0.0061:
  steps ~18 mm apart), yet the bake's steps differ by 25 mm on Marco (drawn 0.0003, about 1 mm) and
  82 mm on Belle's walk (step ratio 1.25). Rest skeletons are mirror-exact (probe:
  `%TEMP%/rw/amd/probe/rest_probe.gd`, every thigh and foot mirrored to 0.1 mm), so it comes from the
  bake's gait solve, not the body. Where exactly is open - it is the largest left/right difference any
  figure has, and nobody asked for it.
- **The game's import resamples a limp in or out.** Its stance offset differs from the bake's by up to
  25 mm and flips sign on study_man (both clips) and Mei's run. That is the same 30 fps resample +
  keyframe optimizer asym-godot-meter found erasing run dip; an `.import` preset (clip fps, optimizer off)
  shipped with rig-anything exports would make what the game shows what was baked.

## The answer: is asymmetry 0.35 subtle, visible or inert?

References (index here is 2|L-R|/(L+R); converted where a paper uses another form):

- **Arm swing, normal human**: Killeen et al. 2018, "Arm swing asymmetry in overground walking",
  *Scientific Reports* 8:12803 (334 healthy adults, overground): non-directional ASI
  = |L-R|/max(L,R) x 100 = **39.5 +- 21.8** at comfortable speed (our index 0.49; mean - 1 SD is ASI 17.7,
  index 0.19), and two-thirds swing the LEFT arm more. Plate et al. 2015, "Normative data for arm swing
  asymmetry: how (a)symmetrical are we?", *Gait & Posture* 41:13-18 (60 healthy, 40-75 y): an ASI above
  **50** ("one side has twice the amplitude of the other") may be abnormal (index 0.67).
- **Step length, normal human**: Patterson et al. 2012, "Gait symmetry and velocity differ in their
  relationship to age", *Gait & Posture* 35:590-594 (81 healthy adults): step length symmetry ratio
  (larger/smaller) **1.03 +- 0.02** (index 0.030 +- 0.020); the asymmetry cut-off from the 95% CI of the
  same healthy group, **1.08** (index 0.077), is Patterson et al. 2010, "Evaluation of gait symmetry after
  stroke: a comparison of current methods and recommendations for standardization", *Gait & Posture*
  31:241-246, as quoted by the 2012 paper.
- **Perceptibility**: Willaert, Aissaoui, Vallageas, Nadeau, Duclos and Labbe 2024, "Detection threshold
  of distorted self-avatar step length during gait and the effects on the sense of embodiment",
  *Frontiers in Virtual Reality* 5:1339296: walkers watching their own avatar noticed a one-sided step
  lengthening at **+12 %** (ascending) / **+9 %** (descending), step ratio 1.09-1.12, index **0.086-0.113**.
  It is a first-person, self-avatar threshold, the closest published one I found. Lauziere et al. 2014,
  *Perceptual & Motor Skills* 118(2):475-490, is proprioceptive (split-belt speed ratio 0.85-0.88,
  elderly), not visual. **I found no published threshold for a third-person observer judging arm swing,
  shoulder dip or arm-leg timing asymmetry**, and no normal human range for shoulder dip or for the
  left/right difference in arm-behind-leg lag.

Per channel, on what the game plays:

| channel | the six at 0.35 (index) | against people | verdict |
|---|---|---|---|
| arm swing | 0.000-0.169 (ASI 0.03-15.6) | all six BELOW the healthy mean (ASI 39.5) and below mean - 1 SD (17.7); the largest the draw can give at 0.35 is ASI 21.8 | **subtle at best, and too symmetric to be human**; inert on Ruth (0.006 / 0.000) and near it on Marco (0.027 / 0.034) and study_woman (0.039 / 0.044) |
| step length | 0.003-0.105 at the game import; 0.021-0.221 in the bake | Mei, Ruth, study_woman inside normal (ratio <= 1.07); Marco (1.09-1.10) and Belle (1.10-1.11; bake walk 1.25) ABOVE the 1.08 cut-off and at or over the self-avatar detection threshold | **visible on Belle and Marco - but not caused by the draw**, and changed by up to 25 mm by the import |
| shoulder dip | 0.007-0.102 | no human reference found | not classifiable against people; the game import attenuates it, and Marco and Belle read 1-3 % (inert) |
| arm-leg lag | diff 0.004-0.024 cycles (1-9 degrees of phase) | no human reference found | readable on Belle and Ruth (0.017-0.024); inert on Mei (drew 0.0003) and at the noise on Marco's walk |

**Paragraph for NEXT.md item 2:**

> Measured on all six figures in Godot (motion_demo's selftest now prints each body's left against its
> right on Walk and Run, and fails under `--control=mirror`): **asymmetry 0.35 is subtle to inert, not
> visible, on the channels it draws.** Arm swing - the channel people are most asymmetric on - reads a
> symmetry index of 0.000-0.169 (ASI 0.03-15.6 as |L-R|/max x 100) against a healthy mean of 39.5 +- 21.8
> (Killeen et al. 2018, *Sci Rep* 8:12803, 334 adults) with abnormal only past 50 (Plate et al. 2015,
> *Gait Posture* 41:13), so every figure swings its arms more evenly than a typical person, and even the
> largest draw 0.35 allows (ASI 21.8) is below that mean; Ruth and Marco are effectively inert there,
> because the draw is uniform per channel and at 0.35 often lands near zero (Ruth drew 0.4 % arm, Mei
> 0.0003 cycles of lag). Lag reads 1-9 degrees of phase and shoulder dip 1-10 %, with no published human
> range to hold them against. The only asymmetry above normal is **step length** - Belle's and Marco's
> step ratios 1.09-1.11 as the game plays them (Belle's bake 1.25) sit past the healthy 95 % cut-off of 1.08
> (Patterson et al. 2010/2012, *Gait Posture* 31:241, 35:590) and at a self-avatar detection threshold of
> 9-12 % (Willaert et al. 2024, *Front Virtual Real* 5:1339296) - but it is NOT the draw's (step draws are
> <= 0.6 % of the stroke), it comes from the bake's gait solve, and the game's default glb import moves it
> by up to 25 mm and flips its sign on study_man. So: raise arm swing (a spread that lands a typical body
> near index 0.3-0.5, and a draw that cannot land near zero, e.g. |u| in [0.5, 1] with a random sign),
> find where the undrawn step asymmetry comes from, and ship an `.import` preset so the game plays what was
> baked. This **unblocks item 6** (runtime jitter): there is now a left-against-right instrument on the
> playing skeleton, with a must-fail control, to judge it by.

## Open

- The step-length asymmetry that is not in the draw (Belle's walk steps 82 mm apart in the bake), cause
  unknown. Diagnose on a scratch build at asymmetry 0 (not done here: this branch does not rebuild).
- The game's default glb import changes stance offset by up to 25 mm and shoulder dip; an import preset
  from rig-anything would fix what the game shows (asym-godot-meter's open item, now with numbers on the
  six real figures).
- The asymmetry check's line (2x the symmetric reading) is mine; the symmetric readings are measured, but
  on asym-godot-meter's fixture Figure, not on these bodies - a zero-asymmetry build of a real figure would
  be the better baseline.
- Marco Walk passes on arm swing alone at x2.6 of the line; Marco Run's lag 0.0140 includes Godot's held
  duplicate frame (~0.006 on a symmetric loop), the bake reads 0.0117.
- No third-person perceptibility threshold for arm swing asymmetry was found; the arm-swing verdict rests
  on the normal range, not on perception.
