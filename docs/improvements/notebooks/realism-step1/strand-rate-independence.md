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
