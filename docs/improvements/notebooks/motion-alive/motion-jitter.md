# motion-jitter - L4 variability, the runtime half

rig-anything 0.32.0. Branch `motion-jitter` off `main` at 328fcbc. Started 2026-09-20 14:04 CDT.

Per-cycle phase and amplitude jitter with a persistent spectrum, so a looping clip stops reading as a
loop. 07 calls L4 the cheapest realism in the document.

## Why it has to be runtime

`plugins/rig-anything/scripts/rig_analysis/locomotion.py:962` samples ONE cycle:

    samples = [P.pose(key_at((f - 1) / float(frames))) for f in range(1, frames + 2)]

Godot loops that one cycle, so nothing placed inside the clip can differ from stride to stride. The
variation has to be drawn while the clip plays.

## What shipped

Three new files in `plugins/rig-anything/godot/addons/rig_anything/`, plus a hook in
`moves_controller.gd` and a `GODOT_JITTER` row in `tools/regress.py`.

- **`gait_jitter.gd`** - the generator. Reads the manifest's `variability` block (the seam), draws
  two scalars per cycle, and gives `phase_offset(u)`, `phase_slope(u)`, `amp_scale(u)`. It also
  carries the `dfa()` static the verifier measures with.
- **`jitter_modifier.gd`** (`class_name GaitJitterModifier`) - a `SkeletonModifier3D` that scales
  the arm swing, LOD-gated.
- **`verify_jitter.gd`** - the headless verifier, with two controls that must fail: `spectrum=white`
  (a naive gaussian per cycle) and `naive=1` (the warp read off the playing phase, which drifts).

### The spectrum, and how it is made cheaply

DFA alpha 0.8 is beta about 0.6 in S(f) ~ 1/f^beta for an ideal fractional Gaussian noise, but a
generator is not an ideal fGn and the number that matters is what the measurement reads. A bank of
first-order relaxations (AR(1)) with geometrically spaced time constants sums Lorentzians into a
1/f^beta band over the ladder's range; weights `tau^((beta-1)/2)` are what make the ladder flat in
log-log.

Tuned in Python first (`%TEMP%/rw/jit/proto.py`), because a sweep there takes seconds and a sweep
through Godot takes minutes. Mean DFA alpha over 8 seeds, 4096 samples, scales 8..256:

| tau0 (cycles) | beta | DFA alpha |
|---|---|---|
| 0.6 | 0.20 | 0.701 |
| 1.0 | 0.20 | 0.753 |
| **1.0** | **0.40** | **0.799** |
| 1.0 | 0.60 | 0.855 |
| 1.6 | 0.40 | 0.849 |

Shipped: 7 modes, tau0 = 1.0, ratio 3.0 (so tau 1 -> 729 cycles), beta 0.40. Over 40 seeds at 4096
cycles: persistent 0.761-0.845 (mean 0.805), white 0.446-0.571 (mean 0.513). The check band is
[0.70, 0.90], which passes every persistent seed and rejects every white one with room either side.
Cost is 7 multiply-adds and 7 gaussians **per cycle** - about 1 Hz, not per frame.

### Why it cannot drift

The obvious implementation is `speed_scale = base * (1 + w'(phi))`, where `phi` is the clip's own
playing position. **It drifts, and the arithmetic says so before any run does.** Over one cycle the
playhead goes 0 -> 1 and the base phase advances by

    integral du / (1 + w'(u))  ~  1 - integral w' du + integral w'^2 du

The `integral w'` term is `g*(q1 - q0)`, which telescopes over cycles and so stays bounded. The
second-order term does not: with `w'(u) = g*dq*6u(1-u)`, `integral (6u(1-u))^2 du = 1.2`, so the
bias is `1.2 * g^2 * E[dq^2]` per cycle - 0.0022 cycles at g = 0.036, which is 8 cycles of drift
over an hour of walking.

The shipped form keeps a **base** phase, `_jit_theta`, advancing at exactly `base_rate / length`,
evaluates the slope there rather than at the playhead, and steers the playhead onto
`theta + offset(theta)` with a proportional term (`jitter_track`, 4 per cycle). Evaluating at theta
is what removes the second-order term; the tracking term is defence in depth against integration
error and against anything else that moves the playhead. Measured: 0.057 cycles of gap after 308
cycles against a 0.216-cycle bound, the gap at 60 s (0.025) the same size as at 300 s (0.057).

**This is what the drift control tests.** `naive=1` puts the slope back on the playing phase -
`MovesController.jitter_naive` - and it drifts as predicted: study_man reads 0.036 cycles of gap at
40 s and 0.200 at 200 s, against 0.016 and 0.058 for the shipped path. It fails `the gap does not
grow with the run`, which is what `regress.py --godot` requires of it. Worth recording that the
first control written, `track=0` (the tracking term off, slope still read at theta), did **not**
fail - 0.041 cycles after 205 - which is how it became clear that the theta evaluation, not the
tracking term, is what carries the guarantee.

### Why the amplitude jitter is arms only

Amplitude has to come off the pose. Scaling a leg's rotation moves where the foot lands, which is
the foot skate this branch promised not to add. The arm chain carries no ground contact and is the
most visible swing on a walk. So the scaled set is the arm roots `arm_pose` names (`upper_arm.L`,
`upper_arm.R`) and their chains to depth 2 - 6 bones on a human - and the scale is a slerp **from
the bone's rest rotation** toward its animated rotation by `1 + jitter`, so jitter 0 is the
animation untouched, bit for bit.

## Measured (study_man, 60 Hz, jitter_phase = jitter_amp = 0.6, seed 7)

| | jitter on | jitter off |
|---|---|---|
| stride-interval cv, 60 strides | **0.0266** | 3.7e-14 |
| arm-swing cv, 60 cycles | **0.0622** | 0.0036 (the estimator's own floor) |
| mean stride time | 0.9717 s | 0.9713 s (0.044% apart) |
| playhead gap after 308 cycles | 0.0572 cycles (0.075 m of ground), bound 0.216 | - |
| planted-foot travel, mean over 62 stances | 0.0247 m | 0.0236 m |
| planted-foot travel, worst stance | 0.3089 m | 0.3279 m |
| cost per character per frame | 3.73 us phase + 3.28 us arm modifier | 0 |

DFA alpha: phase 0.823, amplitude 0.805 over 4096 cycles. **Controls, both shipped in
`regress --godot`:** `spectrum=white` reads 0.500 and 0.532 and FAILS both DFA checks;
`naive=1` FAILS the drift check (above). The white control also fails foot skate (0.0455 m against
0.0333), which was not designed for and is worth keeping: white noise jumps between cycles, so its
instantaneous rate deviation is larger. It skates more as well as looking wrong.

### All six characters in the game, 40 s window, 200 s drift leg

`verify_jitter.gd` over study_man, study_woman, belle, cast_marco, cast_mei and cast_ruth in the
game worktree (none of them carries a `variability` block, so the verifier injects one - which is
also how the absent-key check has something real to test):

| | stride cv on / off | arm cv on / off | drift after ~210 cycles (bound 0.216) | skate mean on / off (m) | us/frame phase + arm |
|---|---|---|---|---|---|
| study_man | 0.0259 / 0 | 0.0626 / 0.0036 | 0.0576 | 0.0272 / 0.0261 | 9.64 + 8.49 (under load) |
| study_woman | 0.0261 / 0 | 0.0637 / 0.0031 | 0.0438 | 0.0270 / 0.0246 | 4.04 + 3.77 |
| belle | 0.0261 / 0 | 0.0573 / 0.0039 | 0.0403 | 0.0250 / 0.0233 | 4.25 + 3.46 |
| cast_marco | 0.0261 / 0 | 0.0600 / 0.0027 | 0.0318 | 0.0267 / 0.0259 | 3.73 + 4.66 (14 bones) |
| cast_mei | 0.0261 / 0 | 0.0566 / 0.0040 | 0.0341 | 0.0261 / 0.0247 | 3.69 + 3.16 |
| cast_ruth | 0.0258 / 0 | 0.0617 / 0.0068 | 0.0261 | 0.0274 / 0.0256 | 5.91 + 7.53 (14 bones) |

`RA_JIT VERIFY PASSED`, 108 checks, 32 s for all six. The DFA numbers are identical across the six
because the verifier fixes the seed at 7: what is being measured is the generator, not the
character. Marco and Ruth get 14 arm bones rather than 6 because their arm roots have more children
inside `MAX_DEPTH`; the cost scales with that and is still single-digit microseconds. The timings
were taken with `regress --quick --jobs 4` running beside them, so they are pessimistic.

## Three measurement traps, each of which read as a result before it was one

1. **Stride intervals quantised to the tick.** Detecting the loop wrap by "u went down" puts the
   wrap on a 1/60 s grid, which is 1.7% of a 0.97 s stride - most of the jitter being measured.
   Interpolating where inside the frame the playhead crossed took the off run's cv from 0.0077 to
   4e-14.
2. **A partial first cycle.** The run starts mid-cycle, so the first amplitude window is short and
   its value is wrong. One bad value in 19 read as 3.6% of "variation" on a clip that has none.
3. **The pose read from outside the modifier pass is not the pose that gets skinned.** This cost
   the most. `Skeleton3D` restores the bone poses once its modifier pass is over, so
   `get_bone_global_pose()` called from a script returns the animation's pose, not the modified one:
   the arm-swing measurement sat at cv 0.0095 with the modifier demonstrably running (4800 passes
   counted). The fix is an **independent observer**: a second, do-nothing `SkeletonModifier3D`
   (`PoseProbe`, inside the verifier) added to the skeleton *after* the jitter modifier, recording
   what it sees during the pass. Every bone measurement in the verifier goes through it, so nothing
   is taken on the jitter modifier's own word. With it, the same run reads cv 0.0708.

   Related: `Skeleton3D.advance(delta)` exists and reads as if it runs the modifier pass from a
   script loop. It does not - not before a real frame has built the modifier list, and not reliably
   after. The verifier drives on real frames with `--fixed-fps 60`, the way `verify_flesh.gd` does.
   The whole verifier was written as a tight loop first and had to be rewritten as a `_process`
   state machine.

Also, cheaply learned: `var active` on a `SkeletonModifier3D` subclass is a parse error, because
`active` is already native there - and `SkeletonModifier3D.active` is the switch that was wanted.
And a static method on a script loaded with `load()` is not callable; the script needs a
`class_name`, which also means the project has to be `--import`ed before the name resolves.

## The seam

Built to the agreed text verbatim, Godot side only. `variability` is read; `seed`, `jitter_phase`
and `jitter_amp` are used; `asymmetry` is read, resolved and exposed on `GaitJitter.resolved` but
not consumed here (it is bake-time, and `motion-asymmetry` owns it). Absent means all zeros, which
means off, and `verify_jitter.gd` checks exactly that against a shipped manifest that has no such
key - which is every character built before this round. Nothing here waits on that branch.

## regress

`python tools/regress.py --quick --jobs 4 --godot <scratch game>` (a `tools/scratch_project.py` copy
of grungist-creek with this worktree's addons, at `%TEMP%/rw/jit/gp`, imported first):
**`REGRESS DONE exit=0, 23 fixtures ok`, no change**, 31 min. `--quick` selects all 23 because
`tools/regress.py` itself changed. The two new rows, on pipeline_woman:

    ok  verify_jitter pipeline_woman: alpha phase 0.823 amp 0.805 | stride cv 0.0261 on / 0.000000 off
        | swing cv 0.0597 on / 0.00487 off | drift 0.0652 of 0.2160 cycles over 160 s
        | skate mean 0.0248 on / 0.0236 off m | 2.09 + 2.27 us per character per frame
    ok  verify_jitter pipeline_woman spectrum=white (must fail): alpha phase 0.500 amp 0.532
        | ... | skate mean 0.0327 on / 0.0236 off m
          fixwoman: phase series DFA alpha 0.500 in [0.70, 0.90] over 4096 cycles
          fixwoman: amplitude series DFA alpha 0.532 in [0.70, 0.90] over 4096 cycles
          fixwoman: planted-foot travel is no worse with jitter (mean 0.0327 m on / 0.0236 off)

Nothing else moved: verify_moves 12 manifests PASSED, verify_wardrobe, verify_flesh, the jiggle
selftest, verify_strands and the lookdev rows all unchanged, every must-fail control still failing.
The game's three demo selftests (figure_study, belle_demo, people_demo) pass in the game worktree
after `--headless --import`.

## Open

- The marketplace entry for rig-anything was at **0.27.0** while `plugin.json` said 0.31.0: the
  motion-mass-model round bumped one file and not the other for four versions, and `tools/bump.py`
  correctly refused to work on top of it. Settled here by hand (0.28.0-0.31.0 "Since" sentences
  written from NEXT.md's own summaries) so that 0.32.0 could be bumped. The merge step should read
  that commit rather than take it on trust.
- `asymmetry` is read and not used. It is `motion-asymmetry`'s to apply.
- The foot-skate number includes the ankle rolling heel to toe, so 0.024 m is not 24 mm of skate.
  Only the on/off ratio is claimed, and both sides use the same estimator on the same bones.
- Jitter is applied to Idle and to gait clips, not to one-shot roles played through `play_role`
  (Jump, TurnL/R). Turns are L5's.
- `GaitJitterModifier` runs twice per frame in the harness (4800 passes over 2400 frames); the cost
  figure is per pass, so a frame with two passes costs twice the quoted number.
- The amplitude estimator's floor (0.0036) is sampling, not motion; the check gates on the on/off
  ratio (17x measured, 5x required) rather than on an absolute floor.
- No character spec in the game sets `[variability]` yet, so nothing in the game changes behaviour.
  The verifier injects the block itself, which is how it can run against pre-seam manifests.
