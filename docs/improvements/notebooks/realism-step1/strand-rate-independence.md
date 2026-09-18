# strand-rate-independence (realism Step 1, 06 rank 13)

Branch `strand-rate-independence` in both repos. Scratch `%TEMP%/rw/strand/`. Started 13:01, code done 13:43.
follow-through 0.6.2 -> 0.6.3.

## 13:02 baseline | verify_strands study_woman | kind=reproduced
Game worktree imported in 9 s. `verify_strands scene=study_woman.glb strands=study_woman_hair.glb`:
30/60/120/240 swing 53.05/49.45/62.33/62.33 deg, spread 1.260 FAILED (same as the figure-study notebook). 38 s a run.

## 13:04 diagnosis | kind=dead end, then the cause
- The modifier already steps at a fixed 1/120 s with the parent interpolated, and 120 = 240 exactly.
- More rates: 45/50/72/90/100/144 swing 59-63 deg, 29/31 51-54, 58/62 59-60. 60 alone was 49.
- Not sensitive to a tiny parameter change (collision_margin 0.004 -> 0.0041: identical numbers).
- Dumps: at 60 the run started from a lower swing and built up to a lower cycle. Clamp events logged
  (instrumented copy): the run's start (ap.play from the rest pose, a ~10 cm snap of the anchor) hit
  MAX_ACCEL at 60 and 120 (at 693 and 1387 m/s^2) and not at 30. Removing the clamp: 53/51/57/57 (1.105).
- Reseeding the strands after ap.play: 74/70/75/75 (1.07). So the start mattered.
- **Then it got worse:** the run has (at least) two stable swings. Long warm-up (6 s + 6 s run) kept each
  rate in its cycle: stride maxima ~43 (58 fps) against ~61 (60 fps), for 7+ strides. At 120 fps,
  start offsets of 1-10 ms all land high (59-64), so the choice is not random but what the rate feeds in.

## Attempts
1. **MAX_ACCEL's excess as a jump the tail does not follow** (e -= (vt - vt_c) dt) instead of dropped.
   30/60/120/240: 53/61/62/62, 1.175 PASSED - but 45/58/90 fell to 44-46 (29-144: 1.44). A lucky pass
   at the four named rates, not independence. Kept (it is right on its own) but not the fix.
2. **Snap detection** (anchor misses last frame's velocity by > 5 cm in skeleton space -> seed rigidly).
   Worse: 30/45/58/60/90/120 = 53/41/47/49/44/62 (1.53). The run's own anchor miss peaked 1.9 cm at
   30 fps. Removed.
3. **Ellipsoid collider basis turned through the frame** (it used the end-of-frame basis on every step).
   No measurable effect; first try used Basis.slerp, which errors on the rig's not-quite-orthonormal
   basis (97 ERROR lines, silently wrong) - caught by grepping the log for ERROR, fixed with a quaternion
   slerp. Kept as correct.
4. **The cause: the load.** Between frames the parent is interpolated in a straight line, so a 30 fps
   frame turns the 24 Hz clip's key-to-key velocity changes into one sharp velocity change a frame, and
   120 fps into four at the keys. Same impulse, but the length/limit/collision/friction projections are
   not linear, and the sharp steps pumped the swing into one cycle or the other. Averaging the target's
   velocity over LOAD_STEPS = 4 steps (1/30 s) before it loads the spring:
   - study_woman 30/60/120/240: 34.97/31.09/33.98/33.98, **1.125 PASSED**; 29/45/58/72/90/144: 32.9-37.3 (1.135)
   - pipeline_ponytail (fixture export): 44.18/45.50/48.21/48.21, **1.091**; 29-144: 42.7-46.5 (1.088)
   - kick settles (last 0.06-0.07 deg), fling 0.3-0.4 mm, run 2.2-3.3 mm, hitch 1.2-3.1 mm into the head
     (limit 5 mm), 74 dropped steps, nonfinite 0, no ERROR lines.
   - LOAD_STEPS = 2 tried: study_woman 1.241, pipeline_ponytail 1.78 FAILED. 4 = a 30 fps frame is the
     least that works, as the argument says.

## Control
`legacy_integration=true` (verify_strands arg -> StrandModifier.legacy_integration) steps exactly as 0.6.2:
study_woman 53.05/49.45/62.33/62.33 = master bit for bit, 1.260 FAILED; pipeline_ponytail
68.40/73.41/53.00/53.00, 1.385 FAILED. regress --godot GODOT_STRANDS runs pipeline_ponytail with and
without it; the control row passes only if the verifier fails.

## Swing on the run (done-when 2) | kind=open
The swing is lower. verify_strands tip swing at 60 fps (the demo's physics rate): 31.1 deg, was 49.4.
figure_study `--selftest`: `study_woman strands on the run: peak 40.0 deg` both before and after -
but that is peak_angle_deg over the bones, and bones 1-4 are limited to 40 deg, so it reads its own
limit; it is not a free measure. The 45.7 in figure-study/final.md was that measure on an older run.
The sharp per-step loads were pumping the swing (they are artefacts of straight-line interpolation of
24 Hz keys, not motion), so some of the loss is the fix. Raising response to 1.4 (set=response:1.4)
swings 84-91 deg and puts strands 5.7-8.1 mm into the head: too strong and not this branch's to tune.
If the look critic wants more swing, the lever is the ponytail preset (frequency/response in
follow-through strand.prepare), rebuilt, not the integration.

## long_loose (not built) | options
`long_loose` stays joined into the body and rigid (its curtain is a sheet, not a line). Options:
- **A sheet of chains:** strand.prepare hangs N chains across the curtain (e.g. 5-9 across the back,
  2-3 per side), each weighted to its strip with feathered overlap; the modifier already runs any number
  of chains. Cheap, uses the collision and rate work done here. Risk: strips separate (gaps) when
  neighbouring chains diverge; needs a lateral distance constraint between chains (a few lines in
  `_step`: pull tails of neighbouring chains toward their rest spacing), and weights that blend two
  chains across each seam.
- **Route to cloth:** follow-through's cloth route (SoftBody3D pinned along the hairline) already has
  pins, a verifier and fabric presets. Real sheet behaviour and self-consistency for free; cost is Jolt
  soft-body performance per character, a hair "fabric" preset (light, low bend stiffness, high damping),
  and collision with the head/shoulders via the body's colliders. Hair cards would need to be a
  connected sheet for the soft body.
- Recommendation: sheet of chains first (same runtime, same verifier, measurable here), cloth only if
  the seams cannot be hidden.

## Time
Baseline and diagnosis 13:01-13:17; attempts 1-3 to 13:30; the load average and both characters 13:40;
verification, bump, commits 13:44. Godot verify_strands ~38 s per 4 rates; pipeline_ponytail build 103 s.

## 13:44-14:07 final regress | kind=win
`regress.py --quick --jobs 2 --godot <game worktree>` (22 of 22 fixtures: regress.py changed), log
`%TEMP%/rw/strand/final_quick.log`: all 22 ok, no golden change, every Godot row ok, including
`verify_strands pipeline_ponytail` 1.091 PASSED and its `legacy_integration=true (must fail)` 1.385 FAILED.
`REGRESS DONE exit=0, 22 fixtures ok`. 23 min wall. (A comment-only fix to strand_modifier.gd landed
after the run started; the Godot phase read the corrected file.)

## Fix round 1 (after critic round 1), 14:17-14:30 | scratch `%TEMP%/rw/strand/r2/`

Critic: the LOAD_STEPS pass held only in the 0.5 s + 4 s window; after a 3 s warm-up the new
integration settled at 35.57/31.1/27.53/27.53 (1.292, FAILED) while 0.6.2 passed it (1.212); the
study_woman control failed only by 0.01; swing fell to 31 deg; figure_study's strand check read the
40 deg bone limit; the regress control counted any failure.

**Reading:** averaging the load changed what the spring was pushed by, but the length, limit,
collision and friction projections still ran on the straight-line-interpolated parent, which is
what differs between rates. So filter the motion itself, not the load.

**The fix:** a critically damped second-order low-pass (exact, per 1/120 s step, input moving in a
straight line over the step) on each chain's parent (origin and rotation quaternion) and each
collider's ends and rotation, SMOOTH_HZ = 10. The sim runs entirely in the smoothed body; the bone
rotations it produces are relative to their frames, so they are applied to the body as animated (no
root detaches). LOAD_STEPS removed (the load is the per-step velocity change again, of a smooth
target). Filter reset on first frame, teleport and a hitch's seed (to the window-start pose, with
the frame's own velocity, so a running body is not jolted).

verify_strands now runs 9 s of the run and tests the spread in two windows: start (0.5-4.5 s, the
old window) and settled (3-9 s, `swing_deg`). Results (warmup 0.5, run 8.5; logs r2/*.log):

| run | start swing 30/60/120/240 | settled | spreads |
|---|---|---|---|
| study_woman, new | 38.04/38.71/39.21/39.21 | 36.31/36.03/36.76/36.77 | 1.031 / 1.021 PASSED |
| study_woman 29,45,58,72,90,144 | 37.5-38.8 | 35.2-36.6 | 1.034 / 1.039 PASSED |
| study_woman 40,50,100,200 | 37.6-38.9 | 35.3-36.8 | 1.033 / 1.044 PASSED |
| study_woman legacy (control) | 53.05/49.45/62.33/62.33 (0.6.2 to the digit) | 53.95/51.43/62.33/62.33 | 1.260 FAILED / 1.212 |
| pipeline_ponytail, new | 43.93/44.3/45.25/45.25 | 39.16/37.34/36.77/36.77 | 1.030 / 1.065 PASSED |
| pipeline_ponytail legacy (control) | 68.4/73.41/53.0/53.0 | 64.81/69.37/53.04/53.04 | 1.385 / 1.308 FAILED on both |

Cutoff sweep (study_woman, settled window): 10 Hz 1.021 (36-37 deg), 15 Hz 1.067 (39-42), 20 Hz 1.206
(39-47). 10 Hz kept: the most robust, and a 30 fps frame cannot carry more than 15 Hz anyway.
Penetration 1.7-2.8 mm on the run, every kick/fling/hitch check passes, no ERROR lines.

**Controls:** the regress control is pipeline_ponytail with legacy_integration=true, and it now counts
only if the verifier fails on *both* spread lines (`control_fails` in GODOT_STRANDS); a failure for
another reason is reported as the control not failing. study_woman's legacy control stays marginal at
the start (1.26) and passes settled (1.21): it is not used as a control.

**Swing (done-when 2):** free tip swing 36-39 deg on study_woman (was 49-62, 31 in round 1), 37-45 on
pipeline_ponytail. figure_study's check now reads the modifier's new `peak_tip_deg` (the chain tip's
angle at its first bone's head from where it hangs at rest, not clamped by any bone's limit):
`study_woman strands on the run: tip swing 40.5 deg (>= 3), bone peak 40.0`, and a new control
(strands paused on the run) reads 0.03 deg (< 3). The 45.7 in figure-study/final.md was the clamped
bone peak, so "about 45" was never a free measure; 36-40 deg is what the smoothed run gives with the
shipped preset. More swing is a preset change (response/frequency), which means rebuilding the game's
characters: not done here.

Cost: the filter adds 17-43 us a frame (study_woman run 114-275 us at 240-30 fps, against 72-226).

## 14:29-14:55 fix-round regress | kind=win
`regress.py --quick --jobs 2 --keep %TEMP%/rw/strand/kr --godot <game worktree>` on 82b6833 / f4ca262,
log `%TEMP%/rw/strand/fix1_quick.log`: 22 fixtures ok, no change, every Godot row ok, including
`verify_strands pipeline_ponytail` swing_spread=1.065 start_spread=1.030 PASSED and its
`legacy_integration=true (must fail)` 1.308 / 1.385 FAILED on both spread lines.
`REGRESS DONE exit=0, 22 fixtures ok`. figure_study `--selftest` PASSED (0 failures), r2/selftest.log.

Open: jiggle_modifier.gd (flesh) still steps per frame on the raw interpolated motion and likely has
the same rate dependence; below 30 fps is not covered; more swing needs a preset change and a rebuild;
verify_strands' kick_peak_deg still sits on the 60 deg limit; long_loose not built.

## 15:02-15:14 fix round 2 (critic round 2) | kind=win
Critic round 2: Q1/Q3/Q4 yes, Q2 (about 45 deg on the run) no - the filter alone gives 36-39 deg, and
`smooth_hz:0` swings 54-64. Also: study_woman has no filter-only control that fails; regress.py
conflicts with main; jiggle_modifier.gd unexamined.

**Swing.** The filter passes the strand's own 1-3 Hz; what it removes is each footfall's >10 Hz jolt,
which drove 0.6.2's swing (and only 120-240 fps fed it in full). So the presets' response, tuned
against that drive, is made up for in the modifier: `SMOOTH_GAIN := 1.1` multiplies every bone's
response while smoothing (`smooth_gain` property; 1 gives the round-1 fix exactly; legacy and
smooth_hz=0 ignore it). Gain sweep, study_woman 30/60/120/240, `mod=response_scale:x` (r3/rs*.log):

| gain | swing settled (deg) | spreads start / settled |
|---|---|---|
| 1.0 | 36.0-36.8 | 1.031 / 1.021 |
| 1.1 | 44.5-46.3 | 1.037 / 1.041 |
| 1.15 | 55.8-57.9 | 1.035 / 1.039 |
| 1.2 | 70.3-82.4 | 1.172 / 1.172 |
| 1.3 | 107-120 | 1.133 / 1.125 |

1.1 at 25/33/47/75/165: 43.9-45.7 deg, 1.053 / 1.040. pipeline_ponytail at 1.1: 48.9-53.5,
1.095 / 1.035. Default run (SMOOTH_GAIN in the code) reproduces the 1.1 row exactly (r3/def.log),
`mod=smooth_gain:1.0` reproduces round 1 exactly (r3/gain1.log). Kick/fling/hitch/penetration checks
pass (head 3.3 mm on the run, was 2.6). figure_study --selftest PASSED: tip swing 51.4 deg, bone peak
40.0, control 0.03 (r3/selftest.log). Steep: between 1.15 and 1.2 the swing jumps onto the limits;
1.1 is ~9% under that - recorded as open.

**Second control.** pipeline_ponytail with only the low-pass off (`mod=smooth_hz:0`, everything else
0.6.3) swings 66.9/52.4/53.0/53.0 at the start (1.277 FAILED) and 1.209 settled (passes). regress.py's
GODOT_STRANDS now takes a list of controls, each with the FAIL lines it must print: legacy (both
lines) and smooth_hz:0 (the starting line). The margin (1.28 over 1.25) is thin and said so in the code.

Mistake: stopping sweep 1 I ran `taskkill //IM Godot_..._console.exe`, which kills every Godot on the
machine. ps showed only my own processes afterwards and the one killed PID was my run's (it exited 1
at that moment), but the right tool is the PID. Not repeated.

## 15:14-15:29 fix round 2 regress | kind=win
`regress.py --quick --jobs 2 --keep %TEMP%/rw/strand/k3 --godot <game worktree>`, log
`%TEMP%/rw/strand/fix2_quick.log`: 22 fixtures ok, no change, `REGRESS DONE exit=0, 22 fixtures ok`.
verify_strands pipeline_ponytail 1.035 / 1.095 PASSED (48.9-53.5 deg); legacy control 1.308 / 1.385
FAILED on both lines; smooth_hz:0 control 1.209 / 1.277 FAILED on the starting line. Addon parity
clean (diff -r, *.uid excluded).

Open: regress.py conflicts with main (GODOT_LOOKDEV/_run_lookdev vs GODOT_STRANDS/_run_strands: keep
both); SMOOTH_GAIN's steep curve (1.15 already 56 deg, 1.2 onto the limits) - a preset retune plus a
rebuild is the lasting fix; jiggle_modifier.gd not examined; below 30 fps not covered; kick_peak on
its 60 deg limit; long_loose not built.

## Merge step (2026-09-18 15:37-15:55 CDT)

Merged main (hair-hairline-lashes, lookdev-closeshot-views and earlier) into the branch and master into
the game worktree. One conflict, tools/regress.py: kept both GODOT_STRANDS/_run_strands and
GODOT_LOOKDEV/_run_lookdev in every hunk (docstring, the per-run lists, the "nothing to check" test and
the run loop). Addon parity between the repo and the game worktree was clean for follow_through, lookdev,
wardrobe and rig_anything. After `--headless --import`, `regress.py --quick --jobs 4 --godot <game
worktree>` passed: REGRESS DONE exit=0, 23 fixtures ok, "no change"; verify_strands pipeline_ponytail
1.035/1.095 PASSED, the legacy control 1.308/1.385 FAILED on both lines, the smooth_hz:0 control
1.209/1.277 FAILED on the starting line, and main's close-shot rows, its control and the lookdev
selftest all ok. Log: C:/Users/pauli/AppData/Local/Temp/rw/merge-strand/quick.log.
