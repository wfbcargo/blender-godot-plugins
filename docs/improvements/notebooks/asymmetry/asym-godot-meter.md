# asym-godot-meter - a left/right asymmetry meter in Godot, off the playing skeleton

NEXT.md "Where to pick up" item 2 and the L4 variability record. Branch `asym-godot-meter` off `main`
at `07e10a5`; rig-anything 0.38.0. Scratch: `%TEMP%/rw/agm/` (scratch game from
`tools/scratch_project.py --who belle`). Started 00:52, 2026-09-21.

## What was built

- `plugins/rig-anything/godot/addons/rig_anything/asymmetry_meter.gd` - `AsymmetryMeter`, a
  `RefCounted`: `new(skeleton, manifest)`, `sample(phase)` per tick, `cycles()`, `report()` keyed by
  channel `{plus_lat, minus_lat, ratio, index, diff}`, plus `stance_offset_m`, `fourier` (first-harmonic
  amplitude per side beside the peak-to-peak), `bones`, `problems`; `swap_sides` for the control.
  Channels: arm_swing_deg, step_length_m, stride_m, shoulder_dip_m (bake-time's definition),
  shoulder_dip_chest_m (engine-only, the motion_demo frame), lag_cycles.
- `verify_asymmetry.gd` - the verifier (a new script, not a verify_moves mode: verify_moves drives the
  gait ladder, this plays each clip at rate 1 for whole cycles). One `RA_ASYM` row per channel, a
  `RA_ASYM_REPORT` JSON line, the stride and is-asymmetric checks, `swap=1`, `poison=1`, `tick=`.
- `variability.measure` gains `lag_cycles` (no golden moves: rigify_human picks its keys by name).
- `tests/fixtures/asym_meter.py` - the Figure exported at 0.35 / 0 / mirror, measured, plus a Blender
  side-swap (body map `lat` negated), verdicts in the golden.
- `tools/regress.py` `GODOT_ASYM` / `_run_asym`: engine against bake per channel, controls.

## Bone roles, and what the meter never reads

Legs from `contacts.<gait>.feet` (`leg`, `bone`), arms from the KEYS of `arm_pose`, hand = two bones
down the arm chain by longest subtree (bodymap's rule). Up from the skeleton transform, forward from
the foot bones' +Y (glTF keeps Blender's bone axes: probe showed forearm and hand +Y along the limb,
foot +Y toward the toe), lat = up x fwd (bodymap's own formula, so +lat is the same physical side).
`poison=1` rewrites `variability`, `arm_pose` values, `gaits`, `contacts` stance/duty/length,
`implied_speed_mps`, `arm_gait` and the report hash does not change.

## What cost time (in order)

1. **Godot does not play the baked frames.** First engine-vs-bake comparison (game-default import,
   60 Hz): stride 5-23 mm short, arm swing up to 1 degree off, run stance offset 8 mm off. Sampling at
   1/120 changed nothing on the walk, so it was not the tick. `animation/fps=30` resamples the 24 fps
   clip; switched to 24 - still 1-2 mm per bone. Printed Godot's imported keys: the spine rotation
   track had **18 keys of 24** - Godot's keyframe optimizer (per AnimationPlayer node, `_subresources`
   `{"nodes": {"PATH:AnimationPlayer": {"optimizer/enabled": false}}}`; putting it under
   `"animations"` does nothing). With fps = clip fps and the optimizer off, every bone agrees with
   Blender's frame to **9e-7 m**. A `.import` written BEFORE the first import is honoured, which is
   how regress stages the keyed copy. ~20 min.
2. **Godot's phase 0 is Blender's frame lo, held for one interval.** glTF keys start at 1/24 (frame
   lo at t = 1/24, the duplicated frame hi at 23/24) and the clip is (hi-lo+1)/fps long (verify's
   `playback_duration_s`), so t in [0, 1/24] holds frame lo. The multiset of poses over a cycle is
   the same as Blender's lo..hi, which is why ranges and the stance mean agree exactly. My first
   Blender lag dropped the duplicate frame (lo..hi-1); that disagreed with the engine and is not what
   the engine plays, so lag is now taken over lo..hi evenly (both engines).
3. **That hold makes a symmetric body read ~0.006 cycles of lag difference.** Over the true cycle a
   symmetric build reads <= 0.0012; over the played cycle, 0.0060 (zero Walk) - the hold sits at phase
   0 where the legs are half a cycle apart. Floor LAG raised 0.005 -> 0.012 before any golden existed
   (asymmetric reads 0.020-0.030). Recorded, not hidden: it is a real per-cycle hitch every
   rig-anything loop has in Godot.
4. **A leaf hand has no length in the file.** Palm = wrist + half the hand along +Y; the Figure's hand
   is a leaf, and the first fallback (distance to the parent's head = the forearm, 0.200 m) put walk
   arm swing +0.69 deg off. Blender's hand is 0.106 m; `LEAF_HAND_SHARE = 0.5` of the forearm gives
   0.100 and walk -0.05/-0.06 deg, run +0.007. Sensitivity ~0.07 deg per cm (walk), ~0.01 (run). The
   one estimate in the meter; ASYM_TOL arm swing 0.1 deg is built on it.
5. Probe gotchas: a glb instanced by hand did not animate under manual callback mode with `seek`;
   the MovesController path (as verify_moves) does. `anim.speed_scale` must be reset to 1 after
   MovesController's own `_ready`.

## Numbers (asym_meter, at the keys, engine against bake, worst side)

| case / clip | arm swing deg | step, stride, dip, stance m | lag cycles |
|---|---|---|---|
| asym Walk | 0.060 | 0.00000 | 0.00000 |
| asym Run | 0.007 | 0.00000 | 0.00000 |
| zero Walk / Run | 0.060 / 0.007 | <= 0.00001 | 0.00000 |
| mirror Walk / Run | 0.060 / 0.008 | <= 0.00001 | 0.00000 |

As the game imports it (30 fps resample + optimizer, 60 Hz): arm swing 0.24-1.01 deg, stride
0.011-0.024 m, step 0.007-0.013 m, stance offset 0.002-0.003 m, dip <= 0.0013 m, lag <= 0.0004
cycles. Printed, not gated; verdicts still hold (asym passes both checks, zero and mirror fail
is-asymmetric only).

Engine table, asym (at the keys):

| | Walk +lat / -lat | ratio | index | Run +lat / -lat | ratio | index |
|---|---|---|---|---|---|---|
| arm swing deg | 44.875 / 36.642 | 1.2247 | 0.202 | 59.356 / 46.370 | 1.2801 | 0.246 |
| step length m | 0.39619 / 0.35418 | 1.1186 | 0.112 | 0.48856 / 0.44758 | 1.0916 | 0.088 |
| stride m | 0.75028 / 0.75046 | 0.9998 | 0.0002 | 0.94077 / 0.93151 | 1.0099 | 0.0099 |
| shoulder dip m | 0.01609 / 0.01728 | 0.9308 | 0.072 | 0.02543 / 0.02868 | 0.8867 | 0.120 |
| lag cycles | 0.00935 / 0.03937 | diff -0.0300 | | 0.02579 / 0.04609 | diff -0.0203 | |
| stance offset m | +0.02100 | | | +0.02049 | | |

Drawn lag -0.01232 per side -> expected diff -0.0246; measured -0.0300 (walk) / -0.0203 (run) over the
played cycle (the hold, point 3); over the true cycle it read -0.0247 / -0.0238.

Controls: zero and mirror FAIL is-asymmetric on Walk and Run and nothing else (golden False);
swap inverts every ratio (product 1 to 1e-6), flips stance offset exactly, agrees with Blender's own
swap and disagrees with the unswapped bake on every channel; poison: identical report hash; stance
offset moved +0.0105 (walk) / +0.0123 (run) m against zero for asym, 0.00000 for mirror.

## Belle, the question NEXT.md asked ("is 0.35 subtle or inert?")

Belle (asymmetry 0.35, seed from her id), scratch game, the game's own import, 60 Hz, 12 cycles:

| | Walk +lat / -lat | index | Run +lat / -lat | index |
|---|---|---|---|---|
| arm swing deg | 44.81 / 51.68 | 0.143 | 45.81 / 54.28 | 0.169 |
| step length m | 0.386 / 0.350 | 0.099 | 0.436 / 0.392 | 0.105 |
| stride m | 0.742 / 0.730 | 0.016 | 0.827 / 0.829 | 0.003 |
| shoulder dip m | 0.0133 / 0.0131 | 0.010 | 0.0233 / 0.0227 | 0.029 |
| shoulder dip, chest frame m | 0.0064 / 0.0061 | 0.040 | 0.0171 / 0.0160 | 0.065 |
| lag cycles | 0.035 / 0.017 | diff 0.018 | 0.044 / 0.021 | diff 0.024 |
| stance offset m | +0.0183 | | +0.0217 | |

**Not inert**: 7-8 degrees of arm swing between her sides and about a fiftieth of a cycle of arm
timing, in the engine. **The shoulder dip channel is**: 1-3% - her draw on it is small (bake ratio
1.0178). She FAILS the all-channel is-asymmetric check for that reason alone. Her walking stride
index 0.016 is the game import's resampling (the keyed fixture reads 0.0002), under the 0.02 line.

## Checks run

- `python tools/test_tools.py`: all passed.
- regress's Godot stage driven directly on the scratch game (asym_meter only): 12 rows ok, 1 m 53 s.
- `regress --only asym_meter --twice --update --jobs 2`: RECORDED asym_meter [84 s + 83 s], the two
  builds agree; `REGRESS DONE exit=0, 1 fixtures ok`.
- final `regress --quick --jobs 4 --godot %TEMP%/rw/agm/game` on d2e5a23 (log:
  `%TEMP%/rw/agm/final_quick_regress.log`): all 24 fixtures ok (no golden moved; rigify_human
  unchanged by `lag_cycles`), every verify_asymmetry row ok (12), verify_moves 15 manifests PASSED.
  **`REGRESS DONE exit=1`**, and the one red row is `verify_strands pipeline_ponytail`: 0.0060 /
  0.0065 / 0.0067 / 0.0067 m into the head, swing_spread 1.050 - digit for digit the blocker NEXT.md
  records as red on `main` ("The one red row the round ships with"). Not this branch's; not touched.
  Started 01:27, done ~02:08 (the Godot stage alone ~35 min at --jobs 4).

## Open

- The run shipped exit=1 only because of the pre-existing ponytail row; it needs its own branch.
- `LEAF_HAND_SHARE` is an estimate; if a rig with a leaf hand of a very different proportion appears,
  arm swing agreement will move (0.07 deg per cm at a walk). A manifest-carried hand length would
  remove it, at the price of every export golden's `fields`.
- The game's default import (30 fps resample + keyframe optimizer) costs 5-23 mm of stride and up to
  1 degree of swing against the bake on this fixture. Worth deciding whether rig-anything's exports
  should ship with a `.import` preset (clip fps, optimizer off) - it is a playback-fidelity question
  beyond this meter.
- The played cycle's held duplicate frame puts a 0.006-cycle lag asymmetry into every symmetric
  rig-anything loop in Godot. Small, real, and a candidate for the exporter (drop the duplicate or
  shorten the clip by one interval).

## Critic round 1, and the fixes (started 02:16)

The critic passed questions 1-4 and failed 5 on `REGRESS DONE exit=1` (the ponytail row on main).
Its soundness notes, and what I did with each:

1. **The controls fail an AND.** "is asymmetric" is arm AND dip AND lag, so zero and mirror failing it
   only proves ONE channel is under its floor. Fixed: the fixture's verdicts gain `over_floor`
   (`{arm_swing_deg, shoulder_dip_m, lag_cycles}`, each against its own floor) and `asymmetric` is
   now `all(over_floor)`. regress (`_asym_over`) computes the same three from the engine's report,
   in BOTH imports, and gates: each must equal the golden's, and a `must_fail` case must read under
   its floor on every channel. The golden moves by the new `over_floor` keys only (re-recorded,
   `--twice`).
2. **Thin margins** (asym Run dip index 0.0431 on the game import against 0.04; Belle Walk stride
   0.016 against 0.02). Floors are not moved. Every asym row now prints each gated free value against
   its floor as `value (xR of floor)`, and marks `THIN` any within x1.25 either side (`ASYM_THIN`,
   printed, never gated), so a verdict that could flip is visible in the log rather than hidden
   behind "ok". The cause of the game-import dip drop is the keyframe optimizer (open item below).
3. **Notebook folder** `asymmetry/`: kept. This round's other branch uses a topic folder too
   (`notebooks/cloth-hug/cloth-span-loose.md`), so it matches; the merge step can move both.
4. **exit=0**: not reachable on this branch - the ponytail row is main's, and needs its own branch.

### What the per-channel gate found (02:19)

`regress --only asym_meter --twice --update --godot` with `over_floor` gated in both imports:
RECORDED (two builds agree; the golden moved by the 8 new `over_floor` blocks only), and two rows
went **red**: zero and mirror *as the game imports it*, `Run shoulder_dip_m: the engine says over
its floor=True, the golden False`. The free values (dip index, Run):

| import | asym | zero | mirror |
|---|---|---|---|
| at the keys (24 fps, optimizer off) | 0.120 | 0.019 | 0.022 |
| game default (30 fps resample + optimizer) | **0.043** | **0.050** | **0.041** |
| ad hoc: 30 fps, optimizer off | 0.070 | 0.033 | 0.032 |
| ad hoc: 24 fps, optimizer on | 0.130 | 0.029 | 0.033 |

So the critic's thin 0.0431 was worse than thin: at the game's default import **a symmetric body
reads MORE run shoulder dip asymmetry than the asymmetric one** - that channel cannot be told apart
there, and the old AND verdict on asym Run passed by luck. Walk dip, arm swing and lag all still
separate by x2-x40 at the game import. It is the two import defaults together; either alone restores
the channel (script: `%TEMP%/rw/agm/adhoc_import.py`, on the kept exports `k2/a`).

Not a meter defect (at the keys it matches the bake to 1e-5), and the floors do not move. What I did:
- the per-channel gate stays ON at the keys (engine = bake), and is behind
  `RA_REGRESS_ASYM_GAME_CHANNELS=1` (off by default) at the game import, where its findings print as
  `(ungated, ASYM_GAME_CHANNELS off)` lines on the row;
- a new always-printed row, "what the game's default import can tell apart", gives every clip and
  channel as asym against the controls' worst, and marks `CANNOT TELL APART`;
- SKILL.md and tests/README say so.
