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

## Resumed 2026-09-20 17:11 CDT: main moved under the branch twice

`motion-head-rung` merged to `main` while this was in flight and took **0.32.0**, which this
branch had already claimed. `main` merged in cleanly except for `.claude-plugin/marketplace.json`
(both sides had rewritten the rig-anything entry). Resolved by taking **main's** whole - its
0.28.0-0.32.0 "Since" sentences are the settled ones, so the hand-written repair recorded under
"Open" below is now `main`'s, not this branch's - and re-bumping on top with
`tools/bump.py rig-anything 0.33.0`. SKILL.md's variability section moved to 0.33.0 with it.
No code conflict: `main` changed the bake-side Python (`upper.py`, `locomotion.py`, two goldens),
this branch the Godot addon.

**Then it happened again.** `motion-asymmetry` - the bake half of this same L4 item, and the other
side of this branch's seam - merged to `main` an hour later and took **0.33.0** with
character-pipeline 0.16.0. Same resolution, same one conflicted file, and the runtime half is now
**0.34.0**. Worth saying plainly for the next round: a branch that bumps a version while other
branches are in flight will re-bump once per merge that lands under it, and the only cost is
noticing. `tools/bump.py` makes each one about a minute; doing it by hand is what cost the
previous round four versions of stale `marketplace.json`.

### Re-measured after the merge, on the merged tree

Every number below was taken today at 17:11-17:4x, against the game worktree
(`grungist-creek/.worktrees/motion-jitter`, all six built characters) and the scratch game copy
at `%TEMP%/rw/jit/gp`.

- **All six characters, `verify_jitter` with `seconds=40 long=200`: `RA_JIT VERIFY PASSED`,
  108 checks, 0 failures.**
- **Control `spectrum=white`** on study_man: exit 1, FAILS *phase series DFA alpha 0.500*,
  *amplitude series DFA alpha 0.532* and *planted-foot travel is no worse with jitter*
  (0.0349 m on / 0.0261 off). Three checks, each one it is there to fail.
- **Control `naive=1 long=400`** on study_man: exit 1, FAILS *stays inside the offset bound*
  (0.4585 <= 0.2160 cycles, 0.598 m of ground after 411 cycles) and *the gap does not grow with
  the run* (0.0360 cycles at 40 s -> 0.4585 at 400 s).
- **A 15-minute run, which nothing in the round had done before.** study_man at `long=900`:
  after **926 cycles** the gap is **0.0238 cycles** - 0.031 m of ground - against the 0.2160
  bound, and *smaller* than the 0.0576 read at 200 s and larger than the 0.0157 at 40 s. The
  controller's own `phi - theta` is -0.0101. A quantity that wanders inside a bound rather than
  accumulating is exactly what the design claims, and the shape of those three numbers is the
  evidence for it.
- **The spectrum, re-measured by code that shares nothing with the shipped verifier**
  (`%TEMP%/rw/jit/indep_dfa.py`: the generator rewritten in pure Python on Mersenne Twister
  rather than Godot's PCG, DFA rewritten with its own least-squares detrend). **200 seeds x 4096
  cycles: persistent mean 0.811** (0.745-0.880), **0 of 200 outside the shipped [0.70, 0.90]
  band**; **white mean 0.508** (0.446-0.571), **200 of 200 rejected by it**. The band separates
  them with room on both sides - the lowest persistent seed is 0.745 against a 0.70 floor, the
  highest white one 0.571 - and both agree with `gait_jitter.dfa`'s own 0.823 / 0.805 and
  0.500 / 0.532 to within the seed spread. (40 seeds first: 0.806 and 0.513, same picture.)
- **The seam read directly**, four manifest shapes through `GaitJitter.from_moves`
  (`%TEMP%/rw/jit/seam_check.gd`, copied into the scratch project to run):

      absent                            from_manifest=false enabled=false  seed 2033222413, all else 0.0
      full block                        from_manifest=true  enabled=true   seed 12345, asym 0.3, phase 0.6, amp 0.4
      jitter_phase only                 from_manifest=true  enabled=true   seed 416605310 (from the id), phase 0.5
      asymmetry 5, phase -2, amp 3      clamped to           asym 1.0, phase 0.0, amp 1.0

  `id_seed` is stable within and across runs (study_man 2033222413 twice, belle 810366055).
- **The three demo selftests** in the game worktree after `--headless --import`:
  `FIGURE_STUDY SELFTEST PASSED (0 failures)`, `BELLE_SELFTEST PASSED`, `PEOPLE SELFTEST PASSED`,
  all exit 0, and `git status` clean afterwards (no `nora.walk.json` rewrite this time).
- **Cost**, measured over 20000 calls against a do-nothing call, not asserted: phase warp
  1.505-1.638 us and the arm modifier 1.206-1.328 us per character per frame on study_man,
  study_woman and Belle (6 arm bones); 2.29 + 2.38 us on the 900 s run. LOD: the modifier runs
  60/60 frames at 1 m and 0/60 past 30 m on all six.

### The one real defect the re-measurement found, and the fix

Pushing the drift run out to a **simulated hour** broke the verifier - not the jitter. The check
was `d_long <= max(d_short, 0.02) * 3.0`: the gap at the end of the long run against the gap at the
end of the short one. At `long=3600` study_man read 0.0659 against a 0.0600 threshold and **FAILED
a run in which nothing had drifted** - the bound is 0.216, the controller's own `phi - theta` was
0.032, and the same run at `long=900` read 0.0238. The check was comparing two single samples of a
quantity that *wanders inside a bound*, so it reads as growth whenever the earlier sample happens
to be small. At `long=200` it had been passing by 4% (0.0576 against 0.0600), which is how close
it already was.

Two changes, neither of them a widened tolerance - the ceiling is the same 0.216-cycle bound in
both checks, and what changed is what gets measured:

1. **The gap is now sampled once a second for the whole run** (`_gap`, 160-3600 samples), and the
   two checks are *the worst gap it ever reached* (strictly stronger than the endpoint it
   replaces) and *the least-squares trend through every sample, carried over the run*. A bounded
   wander fits a slope near zero whatever its endpoints do; an accumulating error fits its own
   rate. `_fitted_drift()` in `verify_jitter.gd`.
2. **Every knot is clamped to 6 sigma** (`GaitJitter.KNOT_MAX`), inside `_draw_phase`/`_draw_amp`
   so the live stream and the measured series clamp identically and `live_gap` stays 0.0. That is
   what makes `PHASE_SPAN * jitter_phase * 6` a HARD bound rather than a statistical one: 4096
   draws reached 4.18 sigma and 3706 cycles of walking reached 4.95, so a long enough run would
   have eventually touched it. Clipping a 2e-9 tail changes nothing measurable - DFA stayed
   0.823 / 0.805 and `max |x|` stayed 4.18, i.e. the clamp never fired at these lengths.

Re-measured on the patched code:

| run | worst gap / bound | fitted trend over the run | ends at |
|---|---|---|---|
| study_man 160 s (the regress row's length) | 0.1344 / 0.2160 | +0.0422 | 0.0210 |
| study_man 200 s | 0.1408 / 0.2160 | +0.0441 | 0.0576 |
| study_man 900 s | 0.1408 / 0.2160 | -0.0100 | 0.0238 |
| **study_man 3600 s (one hour)** | **0.1783 / 0.2160** | **+0.0084** | 0.0659 |
| **CONTROL `naive=1`, 400 s** | **0.4935 / 0.2160 FAIL** | **-0.5027 FAIL** | 0.4585 |
| CONTROL `naive=1`, 3600 s (earlier, old check) | - | - | 4.6106 (6.01 m) |

The fitted trend *shrinks* as the run lengthens (0.044 -> 0.008), which is the signature of a
bounded wander and is the thing the old check could not see. And **all six characters over a simulated
hour**, 3678-3889 cycles each (17:37-17:41, 4 min of wall time for the lot):

| | cycles | worst gap / 0.2160 | fitted trend over 3600 s | ends at |
|---|---|---|---|---|
| study_man | 3706 | 0.1783 | +0.0084 | 0.0659 |
| study_woman | 3863 | 0.1767 | +0.0101 | 0.0195 |
| belle | 3833 | 0.1714 | +0.0101 | 0.0684 |
| cast_marco | 3843 | 0.1669 | +0.0102 | 0.0300 |
| cast_mei | 3678 | 0.1709 | +0.0076 | 0.0687 |
| cast_ruth | 3889 | 0.1717 | +0.0092 | 0.0422 |

`RA_JIT VERIFY PASSED`, 108 checks, 0 failures. Six bodies, six different stride frequencies, and
the worst gap lands in 0.167-0.178 on every one of them - which is what a hard bound looks like
from the outside, as against an endpoint that happens to be wherever the wander left it. All six characters at `long=160`:
worst gap 0.127-0.135, trend +0.042 to +0.045, `RA_JIT VERIFY PASSED`, 108 checks. Both controls
still fail, on exactly their own lines: `spectrum=white` on the two DFA checks and on foot skate
(0.0349 / 0.0261), `naive=1` on both drift checks with 2.3x of margin where the old check had
none to spare.

### Foot skate, on against off, all six (17:13 run, the same estimator both sides)

| | skate mean on / off (m) | worst stance on / off (m) | stride cv on | arm cv on | us/frame phase + arm |
|---|---|---|---|---|---|
| study_man | 0.0272 / 0.0261 (+4.3%) | 0.3089 / 0.3279 | 0.0259 | 0.0626 | 1.51 + 1.33 |
| study_woman | 0.0270 / 0.0246 (+9.9%) | 0.3032 / 0.3217 | 0.0261 | 0.0637 | 1.64 + 1.32 |
| belle | 0.0250 / 0.0233 (+7.0%) | 0.3035 / 0.3213 | 0.0261 | 0.0573 | 1.50 + 1.21 |
| cast_marco | 0.0267 / 0.0259 (+3.1%) | 0.2852 / 0.3047 | 0.0261 | 0.0600 | 1.52 + 1.78 |
| cast_mei | 0.0261 / 0.0247 (+5.3%) | 0.3338 / 0.3525 | 0.0261 | 0.0566 | 1.50 + 1.19 |
| cast_ruth | 0.0274 / 0.0256 (+7.0%) | 0.2972 / 0.3155 | 0.0258 | 0.0617 | 1.54 + 1.77 |

Said plainly rather than as a pass: the **mean** rises 3-10%, and the **worst stance falls** on
every one of the six (by 4-6%). The check's ceiling is 25%, and the white-noise control sits at
+34% and fails it - so the margin is real but it is not zero, and "no more skate" is only true of
the worst case. Both columns come from the same estimator on the same bones, and it counts the
ankle rolling heel to toe, so 0.027 m is not 27 mm of sliding.

### The seam, end to end - the other half landed on main mid-resume

`motion-asymmetry` merged to `main` while this was being re-measured, so the producer is no longer
hypothetical. `character_pipeline.stages.variability_block` writes exactly the agreed key and
`rig_analysis.variability.resolve` returns exactly the agreed four fields - run on the merged tree,
`resolve({'jitter_phase': 0.6, 'jitter_amp': 0.6}, 'study_man')` gives
`{"seed": 5713945625152501342, "asymmetry": 0.0, "jitter_phase": 0.6, "jitter_amp": 0.6}`.

Fed **verbatim** into the Godot consumer (`_interop.gd`, run in the game worktree and deleted):

    shipped study_man.moves.json (no key)                 -> enabled false
    {"seed": ...915, "asymmetry": 0.35, jitters 0}        -> from_manifest true, enabled FALSE,
                                                             gains 0.0000 / 0.0000
    {"seed": ...721, "asymmetry": 0.35, jitters 0.6}      -> enabled true, gains 0.0360 / 0.0900

The middle line is the one worth having: an asymmetry-only character parses, is recognised as
having asked for something, and still does **no runtime work at all** - asymmetry is baked, and
this side correctly declines to act on it.

But an **unstated** seed comes out as a 64-bit Python int, and **Godot's JSON parser returns a
19-digit integer as a float**: the literal above parses as `5713945625152500736.0` (TYPE_FLOAT),
so the engine seeds with 5713945625152500736, not ...1342. Nothing breaks - it is the same value
on every parse, so a character's series is reproducible (two parses of that manifest give an
identical 512-cycle series, worst gap 0.0, DFA 0.856) - and a seed only has to be *stable*, not to
match. But the seed in the file and the seed the engine used are then not the same number, which
will confuse the first person who tries to reproduce a walk from the manifest. The cheap fix is on
the Python side: derive the seed under 2^53 (or 2^31, matching `GaitJitter.id_seed`) so it survives
a double. Recorded for the merge step; not changed here, because that file is the other branch's.

### Still open

- **The LOD check drives `lod_override`, not a real camera.** `_lod_far()`'s camera lookup - and
  its deliberate "no camera means run" fallback, which is what a headless game gets - is not
  exercised by any check.
- The phase warp is **not** LOD-gated by design (it is one multiply, 1.5-2.3 us per character per
  frame, and gating it would snap the playhead when a character crossed the distance). A character
  with no `variability` pays an early return and has no modifier built at all, so the cost is
  bounded by the number of characters that opted in, not by the crowd.
- **Nothing checks that the amplitude modifier never reaches a leg.** "Arms only" is the argument
  that the amplitude jitter cannot add foot skate, and it rests on `arm_pose`'s roots plus
  `MAX_DEPTH`. The report prints the roots and the bone count (6 on the study figures and Belle,
  14 on Marco and Ruth, whose arm roots have more children inside the depth), and the foot-skate
  check catches the consequence, but no check tests the claim directly - a rig whose `arm_pose`
  named a thigh would build a modifier over the leg and only the skate number would notice. It
  wants a check that no collected bone is a foot chain the manifest names, with a control that
  points a root at one.
- Tidy-up, deliberately not made after the final regress started so the log matches the shipped
  bytes: `verify_jitter.gd` computes the bound as `phase_gain() * 6.0` with a literal, while the
  6 is now `GaitJitter.KNOT_MAX`. Same number today; they should be one constant.

### The final regress, and the one failure in it - which is main's, not this branch's

`python tools/regress.py --quick --jobs 4 --godot %TEMP%/rw/jit/gp` on the merged branch
(full output `%TEMP%/rw/jit/regress-final-0.34.0.log`, 17:35-17:57):
**`REGRESS DONE exit=1, 23 fixtures ok`** - every Blender fixture green and no golden moved, and
**one Godot row red**:

    FAILED  verify_strands pipeline_ponytail: ... swing_spread=1.050 start_spread=1.048 FAILED
              FAIL 30 fps: running, a strand went 0.0060 m into the head
              FAIL 60 fps: running, a strand went 0.0065 m into the head
              FAIL 120 fps: running, a strand went 0.0067 m into the head
              FAIL 240 fps: running, a strand went 0.0067 m into the head

**It is not this branch's.** This branch adds no Blender code, no bake code and no strand code -
`git diff main --stat` is the rig_anything addon, `tools/regress.py`, SKILL.md, the version files
and this notebook. Reproduced on **`main` itself** (`d367a4b`), from the main checkout, which it
left clean: `python tools/regress.py --only pipeline_ponytail --jobs 1 --godot <the same scratch
game>` gives `REGRESS DONE exit=1, 1 fixtures ok` and **the identical four numbers**, 0.0060 /
0.0065 / 0.0067 / 0.0067 m, `swing_spread=1.050`.

Where it came from, from this branch's own earlier log (`regress-quick-1436.log`, run on the base
`328fcbc`, before either motion merge):

    ok  verify_strands pipeline_ponytail: ... swing_spread=1.013 start_spread=1.040 PASSED
          30 fps: swing 101.04 deg settled, head 0.0038 m
          60 fps: swing  99.72 deg settled, head 0.0039 m

So the ponytail's head penetration went **0.0038-0.0039 m (passing) -> 0.0060-0.0067 m (failing)**
and the settled swing 100-101 -> 104-109 deg when `motion-head-rung` and `motion-asymmetry` landed.
That is the head moving more on the Run clip, which is what both of those shipped; the strand is
simply following it into the skull. Neither branch saw it because **neither of their final regress
runs used `--godot`** - `%TEMP%/rw/asym/regress-final.txt` is `REGRESS DONE exit=0, 23 fixtures ok`
with no `godot:` stage in it at all. Worth carrying as a rule: a round that changes what a clip
does needs one `--godot` run before it merges, because the strand, flesh and wardrobe verifiers are
the only things that watch the clip move.

For the merge step: this is a blocker on `main`, not on `motion-jitter`, and it is either the
ponytail's collision radius or the head rung's amplitude. The three `verify_jitter` rows in the
same run are all ok, including both must-fail controls:

    ok  verify_jitter pipeline_woman: alpha phase 0.823 amp 0.805 | stride cv 0.0261 on / 0.000000 off
        | swing cv 0.0597 on / 0.00487 off | drift 0.0652 of 0.2160 cycles over 160 s
        | skate mean 0.0248 on / 0.0236 off m | 1.99 + 2.06 us per character per frame
    ok  verify_jitter pipeline_woman spectrum=white (must fail): alpha phase 0.500 amp 0.532 | ...
    ok  verify_jitter pipeline_woman naive=1 long=400 (must fail): ... | drift 0.5185 of 0.2160 cycles over 400 s

and so is everything else the Godot stage runs: verify_moves (12 manifests), verify_wardrobe (7
rows with 3 must-fail), verify_flesh (4 rows with 1 must-fail), the jiggle spring selftest and its
control, close-shot, edges and eyes with their controls. Both `verify_strands` must-fail controls
still fail, though they now fail on the penetration line as well as their own.

---

## Critic round 1, the fix pass (2026-09-20, rig-anything 0.35.0)

The critic's verdict was `pass: false`, `mergeable: true`, with one blocker that is **main's**
(`verify_strands pipeline_ponytail`) and nine problems against this branch. What follows is what
each one turned into. My own scratch copy for all of it:
`C:/Users/pauli/AppData/Local/Temp/rw/jfix/gp`, made with `tools/scratch_project.py --who
study_man,study_woman,belle` from this worktree.

### The one that was a real bug: the gait-change path

The critic's third problem - "the gait-change path is exercised by nothing" - was a coverage gap
they could not turn into a finding, because their harness read 3.38 cycles on the shipped code and
3.39 on its own zero-jitter control, so it was measuring gait-switch bookkeeping and they withdrew
it. It **was** a bug, and the way to see it was not a new harness but the existing drift check with
the gait changing under it.

`switch=<seconds>` now alternates the commanded speed between the slowest and the fastest gait, on
BOTH bodies at the same tick, so the clip changes over and over and the gap between the two
playheads stays exactly the measurement it already was. The per-cycle checks (stride cv, arm-swing
cv, mean pace, skate) are about one clip's cycle and are skipped in this mode; the drift checks are
the point of it.

The first run of it failed, on the shipped code:

    FAIL  study_man: the jittered playhead stays inside the offset bound over 157 cycles
          (worst gap 0.4491 <= 0.2160 cycles, 0.585 m of ground)
    FAIL  study_man: the gap does not grow with the run (the trend through 120 samples
          carries +0.4202 cycles over 120 s, bound 0.2160)

17 gait changes, and the gap grew with them. The cause is the clip-change branch of
`jitter_factor`:

    _jit_phi = _jit_theta + jitter.phase_offset(fposmod(_jit_theta, 1.0))

`_jit_phi` is the playhead the controller has been integrating; the tracking term drives the rate
by `target - _jit_phi`, and at steady state `_jit_phi` sits one tracking lag behind the target
(measured below: about 0.016 cycles). Snapping it TO the target on a clip change asserts that the
real playhead is already there. It is not - nothing moved it - so that lag is thrown away and never
corrected, and the next gait change throws away the next one. One lag per gait change, and a game
character changes gait constantly. It is the plausible thing to write, which is why it was written.

The fix is to re-anchor to where the playhead actually **is**. `_jit_phi` advances at exactly the
rate the AnimationPlayer does (`r * f * dt` cycles against `base * f * dt` seconds over a clip of
`length` seconds), so its fraction and the clip's stay locked together; realign that fraction,
wrapped to +-0.5, and leave the tracking error alone:

    var d := fposmod(_anim.current_animation_position / length, 1.0) - fposmod(_jit_phi, 1.0)
    if d > 0.5: d -= 1.0
    elif d < -0.5: d += 1.0
    _jit_phi += d

With `play_gait` carrying the phase across, `d` is ~0 and nothing happens; with a `play_role` that
restarts the clip at 0, it snaps back. After the fix, 400 s and **57 gait changes**, all three
characters in my scratch copy (`three-switch.log`, exit 0, 57 PASS / 0 FAIL):

    PASS  study_man:    57 changes (1.3 <-> 4.2 m/s), worst gap 0.1162 <= 0.2160, trend +0.0178
    PASS  study_woman:  57 changes (1.3 <-> 4.1 m/s), worst gap 0.1204 <= 0.2160, trend +0.0138
    PASS  belle:        57 changes (1.3 <-> 4.1 m/s), worst gap 0.1233 <= 0.2160, trend +0.0161

and the old shape is kept as the control (`reanchor=target`), which must fail those two lines - it
reads worst gap 0.4491 and trend +0.4202, the numbers above.

The single-clip runs are unchanged by the fix. Six-manifest equivalent on the three characters this
scratch carries, `cycles=4096 seconds=40 long=160`: exit 0, 57 PASS, 0 FAIL. A simulated hour
(`long=3600`, `three-hour.log`): exit 0, 57 PASS, 0 FAIL, worst gap 0.1375-0.1444 over 3706-3863
cycles, trend +0.0084 to +0.0101.

### Controls for the checks that had none (problem 2)

Three of about twelve checks had a control. Now nine do, and every one of them was run and read:

| control | what it breaks | the lines it must fail |
|---|---|---|
| `spectrum=white` (was) | a white generator | both DFA lines |
| `naive=1` (was) | the warp read off the clip's own phase | both drift lines |
| `reanchor=target` | the clip-change branch, above | both drift lines, with `switch=` |
| `spectrum=flat` | the same knot every cycle | stride interval varies, arm swing varies |
| `absent_on=0.6` | absent `variability` resolving to jitter | both "no variability" lines |
| `lod_m=0` | the distance gate turned off | the LOD line |
| `ctl=legs` | `arm_pose` pointed at the thighs | the new "reaches no leg" line |
| `rate=1` | the bounded offset used as a playback RATE | mean stride time is unchanged |

Measured, each on study_man in my own scratch copy (`ctl-*.log`):

    flat    exit 1: stride cv 0.0001 (needs > 0.005), arm swing cv 0.0026 = 0.7x the off floor
    absent  exit 1: both absent lines, and nothing else
    lod     exit 1: "runs 60/60 frames at 1 m and 60/60 past 0 m"
    legs    exit 1: "(thigh.L, shin.L, foot.L, thigh.R, shin.R, foot.R)", and the skate line
                    too: mean 0.0463 m on / 0.0333 off
    rate    exit 1: mean stride time 3.9038% off; worst gap 1.7924; trend -1.6753

`spectrum = "flat"` and `absent_default` live in `gait_jitter.gd`, and `jitter_rate` /
`jitter_reanchor_target` in `moves_controller.gd`, deliberately: a control that drives the real
code path is worth more than one that drives a lookalike in the verifier. `absent_default` is set
only around the absent check and put back afterwards, so that control fails that check and nothing
else.

The cost check still has no control (a ceiling with a free number under it), and the LOD check
still drives `lod_override` rather than a camera. Both stay open, below.

### "Arms only" is now checked by name, not by consequence (the author's own open item)

`_legs()` walks up from every foot the manifest names, as far as the chain the arm roots hang from,
adds the feet's descendants, and requires that the amplitude modifier collected none of it:

    PASS  study_man: the modifier reaches no leg: 0 of its 6 bones are in the 8-bone leg chain
          under ["upper_arm.L", "upper_arm.R"] (none)

The critic built this control by hand (`crit_legroot.moves.json`) and found only the skate number
noticed. Now `ctl=legs` builds it inside the verifier and the check names the bones it found.

### The drift headroom (problem 4), answered with the numbers rather than a tolerance

The critic found seed 2 at 0.1959 against the 0.2160 bound over a simulated hour - 91% - and asked
whether the margin was thin. **No tolerance moved.** Instead the two halves of the gap are now
tracked in `MovesController` and printed free: the largest offset the generator ever COMMANDED,
and the largest the playhead ever LAGGED that command.

    worst gap 0.1444 <= 0.2160 ... of that gap the commanded offset reached 0.1505
                                   and the tracking lag 0.0167        (study_man, long=3600)

So the gap IS the commanded offset - which is bounded by construction, the clamp being where the
bound comes from - and the lag is 0.016, a ninth of it, and partly cancelling rather than adding.
It is also why raising the tracking gain does nothing, which I checked rather than assumed: over
900 s on study_man, `track=4` gives worst gap 0.1073 / 0.1069 / 0.1126 on seeds 2 / 7 / 101 and
`track=12` gives 0.1070 / 0.1069 / 0.1127 - a difference in the fourth decimal. The headroom is the
6-sigma clamp's and nothing else's, and that is now what the check's own text says.

### Smaller ones

- **Problem 10** (the literal 6.0): the bound is `phase_gain() * GaitJitter.KNOT_MAX`.
- **Problem 6** (`worst_gap` cannot fail by construction on the shipped path): said out loud, in a
  comment beside the bound - its remaining teeth are against a change of mechanism, which is what
  `naive=1` and `reanchor=target` supply.
- **Problem 8** (`cycle_u` came from the jitter's own phase counter): it now comes from the clip's
  playhead, `fposmod(_anim.current_animation_position / length, 1.0)`. At steady state the two
  agree within the offset; after a gait change they do not, and it is the clip the arm swing has
  to be in step with.
- **Problem 9** (plugin.json's description stops at 0.31.0): **not a defect.** `tools/bump.py` says
  so in its own docstring - plugin.json's own description is left alone, and marketplace.json is
  what `/plugin marketplace update` reads. Every plugin in the repo is like this. If the two
  descriptions should be settled, that is a change to `bump.py`, on main, for all of them at once.
- **Problem 5** (the second drift check's effective threshold moved in e2166fd): recorded as the
  critic asks - it is a replaced test, not a widened tolerance, and the merge step should read it
  as one. Nothing changed here.

### Left open deliberately

- **Problem 7, the 64-bit seed.** Confirmed, not fixed, and the reason is the rule about goldens.
  `variability._MASK` is `(1 << 64) - 1`; the fix is to derive under 2^53 (or 2^31, matching
  `GaitJitter.id_seed`). But `seed_from` feeds `_unit(seed, channel)`, so changing the mask changes
  every drawn asymmetry, and `tests/golden/rigify_human.json` records both the seeds and the drawn
  values - and `rigify_human`'s fixture asserts each draw clears zero's by `MARGIN`, so a re-record
  could fail on a draw that lands small. That is a reviewed golden move with a real chance of a
  second round in it, on a file this branch does not own. It wants one commit of its own, on main,
  with `regress --only rigify_human --update --twice` and a look at the margins.
- The cost check's missing control, and the LOD check's camera lookup (`_lod_far()`'s deliberate
  "no camera means run" fallback, which is what a headless game gets) being exercised by nothing.
- `switch=` alternates two gaits, both played through `play_gait`; it never settles to Idle through
  `play_role`, which is the path where the playhead really is reset and where the new `d`
  correction does its other job. Worth one more mode.
- **Main's `verify_strands pipeline_ponytail` is still the blocker**, unchanged and unowned by this
  branch: see the previous section for the reproduction on `main` d367a4b by itself.

### The fix pass's own `--quick --godot` run

`C:/Users/pauli/AppData/Local/Temp/rw/jfix/regress-0.35.0-run3.log`, run 19:14-19:37 from this
worktree against a freshly made scratch copy (`tools/scratch_project.py .../gp2 --who
study_man,study_woman,belle --force`, imported by that tool):

    REGRESS DONE exit=1, 23 fixtures ok

All 23 Blender fixtures pass and **no golden moved** - the diff file
(`regress-diffs/regress-20260920-191400-22760.diff`, 12 lines) contains the one red Godot row and
nothing else. All **ten** `verify_jitter` rows are ok: the base run, the new `switch=7 long=400`
run that must also pass, and all eight controls, each failing on its own named lines:

    ok  verify_jitter pipeline_woman: alpha phase 0.823 amp 0.805 | stride cv 0.0259 on / 0.000000 off
        | swing cv 0.0585 on / 0.00487 off | drift 0.0313 of 0.2160 cycles over 160 s
        | skate mean 0.0253 on / 0.0236 off m | 1.57 + 1.38 us per character per frame
    ok  verify_jitter pipeline_woman cycles=1024 seconds=20 long=400 switch=7: ... drift 0.0484 of 0.2160
    ok  verify_jitter ... spectrum=white (must fail): alpha phase 0.500 amp 0.532
    ok  verify_jitter ... naive=1 long=400 (must fail): drift 0.5185 of 0.2160
    ok  verify_jitter ... long=120 switch=7 reanchor=target (must fail): drift 0.4199 of 0.2160
    ok  verify_jitter ... spectrum=flat (must fail): stride cv 0.0003, swing cv 0.0039 / 0.00498 off
    ok  verify_jitter ... absent_on=0.6 (must fail)
    ok  verify_jitter ... lod_m=0 (must fail)
    ok  verify_jitter ... ctl=legs (must fail): skate mean 0.0442 on / 0.0336 off
    ok  verify_jitter ... rate=1 (must fail): drift 0.6746 of 0.2160 over 16 s

The single red row is **`verify_strands pipeline_ponytail`**, unchanged and still main's:
`swing_spread=1.050`, head 0.0060 / 0.0065 / 0.0067 / 0.0067 m at 30 / 60 / 120 / 240 fps - the
same four numbers the author measured and the critic reproduced on `main` d367a4b by itself. This
branch adds no Blender, bake or strand code. It is the merge/ship step's, and it blocks the round,
not this branch.

Two things the run itself taught:

- **`spectrum=flat` writes `null` where a number goes.** A constant series has no fluctuation to
  detrend, so its DFA exponent is NAN, and Godot's `JSON.stringify` writes NAN as `null`.
  `regress.py`'s `_run_jitter` formatted it with `%.3f` and raised `TypeError`, which would have
  taken the whole run down on a control that was failing exactly as it should. Every number in
  that row now goes through a lookup that gives NaN for a missing or null one. A control is a test
  of the harness; the harness has to survive it.
- **Two regress runs at `--jobs 4` on one Windows session is one too many.** An earlier attempt
  (`regress-final-0.35.0.log`) reported `exit=1, 5 fixtures ok` with 19 fixtures dying at
  `exit 3221225794` - `0xC0000142`, STATUS_DLL_INIT_FAILED, which is session resource exhaustion,
  not a fixture failure. A killed run's Blender and Godot children outlive the shell that started
  them, and the leftovers from a previous agent's headless Godot were still there too. Re-running
  at `--jobs 3` on a fresh scratch copy gave the clean log above. If a regress run reports
  `3221225794` on many fixtures at once, count the processes before believing any of it.

### Two more open items from this pass

- `_jit_worst_offset` and `_jit_worst_lag` are only updated on the shipped path, so the two control
  implementations (`jitter_naive`, `jitter_rate`) print `0.0000` for both in the drift line. The
  controls fail on the gap itself, so nothing is wrong - but the line reads oddly in their logs.
- `switch=` picks the fastest gait on the ladder and falls back to Idle only when there is one
  gait. On `pipeline_woman` it alternates Walk and Run, so the `play_role` reset path - the one the
  new wrapped-difference correction exists for - is still not what regress exercises.
