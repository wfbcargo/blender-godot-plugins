# motion-head-rung - the head rung: the last piece of the lag ladder

Round: motion-alive (07 step 3, "Still owed"). Branch `motion-head-rung` off `main` at 328fcbc.
Scratch: `C:/Users/pauli/AppData/Local/Temp/rw/hr/`.

## The task

The pelvis leads, the thorax lags it (rig-anything 0.30.0), the head should lag the thorax the same
way. Blocked on SHAPE: `upper.trunk` takes scalars, so the neck and head bones are given
`ends[k][1] * keep` - the thorax's own VALUE scaled by `head_hold`. A value cannot carry a phase.

## 2026-09-20 14:04 - reading the ground

- `motion-mass-model` is already merged; `main` is at 328fcbc. Worktree made off `main`.
- `upper.trunk` (upper.py:361) writes the axial chain's TOTAL world yaw/roll/pitch per bone
  (`motion.Body.bend_axial` docstring: "totals ... so a head that holds its orientation while the
  chest turns under it is a zero"). The head bone's yaw is therefore `thorax_yaw * (1 - head_hold)`
  - a scaled copy of the thorax's signal, in phase with it by construction.
- Only two other callers of `upper.trunk`: `actions.py:665` (the idle, all-zero yaw/roll) and
  nothing else. `hop.py` and `radial.py` never call it. `Upper` is only built when
  `upper.resolve` says so - upright, two legs - so the quadruped/cricket/bird/fish/radial paths
  never reach this code at all.

## 2026-09-20 14:09 - the instrument, BEFORE the change

Extended `upper.relative_phase` to return a dict of BOTH rungs
(`pelvis_thorax_phase_deg`, `thorax_head_phase_deg`), measured the same way off the BAKED clip -
the once-per-cycle Fourier phase of each bone's twist about `up`, later segment minus its driver.
`locomotion.cycle` now does `r.update(...)`, so every biped gait clip carries both, and both are
goldened.

Speed sweep instrument: `C:/Users/pauli/AppData/Local/Temp/rw/hr/sweep.py`, eight Froude numbers
(0.03 .. 2.0) on a body built from nothing, reporting both phases plus the head-and-neck
segment's gravity-pendulum frequency about each body axis.

### BEFORE - Rigify `Figure` (follow-through's lofted body, `fit_basic_human`)

| froude | speed m/s | pelvis->thorax deg | thorax->head deg |
|---|---|---|---|
| 0.03 | 0.483 | -73.3 | **-0.7** |
| 0.08 | 0.764 | -104.8 | **-0.6** |
| 0.15 | 1.077 | -122.0 | **-0.6** |
| 0.25 | 1.369 | -132.6 | **-0.6** |
| 0.40 | 1.734 | -140.2 | **-0.7** |
| 0.70 | 2.279 | -147.0 | **-0.7** |
| 1.20 | 3.014 | -152.1 | **-0.6** |
| 2.00 | 3.748 | -155.9 | **-0.6** |

The same tell the trunk had at a flat -179.3: the head reports the SAME number at every speed,
because it is a scaled copy of its driver rather than a segment with a phase of its own. The
pelvis-thorax rung sweeps 83 degrees over the same range, which is 0.30.0 working.

### BEFORE - MPFB woman (curvy, seed 7), the body the game actually ships

| froude | speed m/s | pelvis->thorax deg | thorax->head deg |
|---|---|---|---|
| 0.03 | 0.505 | -70.1 | **-0.7** |
| 0.08 | 0.798 | -101.4 | **-0.6** |
| 0.15 | 1.079 | -119.3 | **-0.6** |
| 0.25 | 1.367 | -130.6 | **-0.6** |
| 0.40 | 1.724 | -138.6 | **-0.7** |
| 0.70 | 2.254 | -145.9 | **-0.7** |
| 1.20 | 2.962 | -151.2 | **-0.6** |
| 2.00 | 3.912 | -155.2 | **-0.6** |

Two bodies that share no geometry, the same flat -0.6 on both - which is what a scaled copy of a
value looks like, and not what a segment with a phase of its own looks like.

## 2026-09-20 14:15 - the change

Two edits, and the first is the whole point:

1. **`upper.trunk` takes a signal.** New keyword `head={"yaw","roll","pitch"}` - the top of the
   chain's own drive values, read wherever its own phase puts them. The neck now interpolates from
   its driver's value at the base to `head[k] * (1 - head_hold)` at the top, instead of scaling the
   thorax's value by `1 - head_hold*(j+1)/n`. With `head=None` the two expressions are **identical**
   (`T + (T(1-h) - T)w == T(1 - hw)`), so the idle caller at `actions.py:665` and every body that
   has nothing to say about phase are untouched by construction.
2. **`upper.head_frequency(poser)`** - `mass.pendulum` on the neck and everything above it, about
   the lateral axis through the base of the neck, exactly as `limb_frequencies` measures what hangs
   off a girdle. `Upper.__init__` turns it into `self.head_lag` through `response`; `cycle_key`
   evaluates the drive at `p0 - trunk_lag - head_lag` and hands `trunk` the result.

New parameter `head_lag` (None derives; a number overrides; **0.0 is the locked head this
replaces** and is the control). Reported per clip as `head_hz`, `head_lag_cycles`, `head_lag_deg`.

### The measured natural frequency, and whether it is physically sensible

| body | neck+head bones | mass | COM vs pivot | Hz about lat | about fwd | about up |
|---|---|---|---|---|---|---|
| Rigify `Figure` (lofted) | spine.004/005/006 | 9.16 kg | **0.191 m ABOVE** | **0.9084** | 0.8978 | 0.7254 |
| MPFB woman (curvy, seed 7) | spine.004/005 | 4.12 kg | **0.141 m ABOVE** | **1.0889** | 1.1101 | 1.4034 |

**Honest reading.** `mass.pendulum` returns `sqrt(m g d / I)/2pi` and reads `d` unsigned. For
everything `limb_frequencies` measures the mass hangs BELOW its pivot, gravity restores, and the
number is a resonance. What sits on top of an upright axial chain is above its pivot on both bodies
measured, so gravity there **destabilises**: the same expression is a divergence rate, not a free
oscillation, and the real restoring stiffness is the neck's, which nobody has - the same gap that
leaves `trunk_hz` fitted at 0.82. `hz_about_up` is worse than that and is NOT used: gravity exerts
no torque about a vertical axis at all, so that column is an artifact of a few millimetres of
forward COM offset.

So the derivation is weaker than 0.31.0's hand pendulum, and the notebook says so rather than
dressing it up. What supports using it anyway: it is the only number here that is **measured**; its
size lands where the real thing does (0.91 Hz and 1.09 Hz on two bodies that share no geometry, one
9.2 kg of generic loft and one a realistic 4.1 kg head and neck); and a stride runs 0.74-1.72 Hz,
so `r = drive/natural` lands in 0.7-1.9 - the part of the transfer function that actually sweeps,
rather than pinned at either limit. The alternative is a hand-set constant, which is what 07 is
trying to remove.

### Why angular momentum could not arbitrate this one

0.31.0 settled the arm by sweeping its lag against `mass.angular_momentum`, so I ran the same
sweep here (`C:/Users/pauli/AppData/Local/Temp/rw/hr/lagsweep.py`), four head lags at a walk and a
run:

| gait | head lag | head_lag_deg | measured t->h | mean abs L | L range | passed |
|---|---|---|---|---|---|---|
| walk (fr 0.08) | locked (control) | 0.0 | -0.6 | 0.00481 | 0.02789 | yes |
| walk | derived | 89.0 | -89.6 | 0.00482 | 0.02790 | yes |
| walk | 0.25 | 90.0 | -90.6 | 0.00482 | 0.02790 | yes |
| walk | 0.50 | 180.0 | 179.4 | 0.00482 | 0.02790 | yes |
| run (fr 1.2) | locked (control) | 0.0 | -0.6 | 0.00118 | 0.00434 | yes |
| run | derived | 151.9 | -152.5 | 0.00118 | 0.00437 | yes |
| run | 0.25 | 90.0 | -90.6 | 0.00118 | 0.00435 | yes |
| run | 0.50 | 180.0 | 179.4 | 0.00118 | 0.00437 | yes |

Whole-body angular momentum does not move: 0.00481 -> 0.00482 walking, flat to five figures
running, across the whole range of the parameter. **So `mass.angular_momentum` is not the arbiter
for this rung** - this segment is too small and its amplitude is held at `1 - head_hold` = 0.15 of
the thorax's whatever the phase, so there is nothing for the residual to see. That is worth writing
down because the natural move was to reach for it: it vetoed a plausible change in 0.31.0, and here
it is simply silent. What it DOES say is that the change costs nothing, and the phase measurement
has to decide alone.

The other thing that table shows is that the instrument is honest: the measured `t->h` tracks the
lag that was asked for within about a degree at every setting, including 180 and including zero. It
is reading the BAKED clip, and the clip carries what the signal asked for.

## 2026-09-20 14:23 - AFTER, across the speed sweep, on two bodies

Same instrument, same eight Froude numbers, same bodies built from nothing.

### Rigify `Figure` - head_hz 0.9084, trunk_hz 0.82 (fitted)

| froude | speed m/s | stride Hz | asked head_lag deg | BEFORE t->h | AFTER t->h | p->t |
|---|---|---|---|---|---|---|
| 0.03 | 0.483 | 0.743 | 55.9 | -0.7 | **-56.7** | -73.3 |
| 0.08 | 0.764 | 0.903 | 89.0 | -0.6 | **-89.6** | -104.8 |
| 0.15 | 1.077 | 1.025 | 111.9 | -0.6 | **-112.5** | -122.0 |
| 0.25 | 1.369 | 1.135 | 126.8 | -0.6 | **-127.4** | -132.6 |
| 0.40 | 1.734 | 1.247 | 137.0 | -0.7 | **-137.6** | -140.2 |
| 0.70 | 2.279 | 1.394 | 145.8 | -0.7 | **-146.5** | -147.0 |
| 1.20 | 3.014 | 1.553 | 151.9 | -0.6 | **-152.5** | -152.1 |
| 2.00 | 3.748 | 1.720 | 156.3 | -0.6 | **-156.9** | -155.9 |

Flat -0.6 becomes a 100-degree sweep, and the measured value sits within 0.8 degrees of what the
transfer function asked for at every speed - the clip carries the signal. Every clip still passes.

### MPFB woman (curvy, seed 7) - head_hz 1.0889

| froude | speed m/s | stride Hz | asked head_lag deg | BEFORE t->h | AFTER t->h | p->t |
|---|---|---|---|---|---|---|
| 0.03 | 0.505 | 0.727 | 35.8 | -0.7 | **-36.6** | -70.1 |
| 0.08 | 0.798 | 0.884 | 55.1 | -0.6 | **-55.7** | -101.4 |
| 0.15 | 1.079 | 1.003 | 74.6 | -0.6 | **-75.2** | -119.3 |
| 0.25 | 1.367 | 1.111 | 93.8 | -0.6 | **-94.4** | -130.6 |
| 0.40 | 1.724 | 1.220 | 110.8 | -0.7 | **-111.4** | -138.6 |
| 0.70 | 2.254 | 1.365 | 127.2 | -0.7 | **-127.8** | -145.9 |
| 1.20 | 2.962 | 1.520 | 138.6 | -0.6 | **-139.2** | -151.2 |
| 2.00 | 3.912 | 1.683 | 146.3 | -0.6 | **-146.9** | -155.2 |

110 degrees of sweep, and on the body the game actually ships the two rungs are clearly SEPARATE
ladders - -36.6 against -70.1 at a slow walk, converging as speed rises - because her head-and-neck
sits at 1.09 Hz against the trunk's 0.82. On the lofted `Figure` the two nearly coincide, which is
what two rungs at 0.91 and 0.82 Hz should do. The ladder is one expression, not three constants,
and it separates or converges according to what was measured off each body.

Both bodies' `pelvis_thorax_phase_deg` is unchanged to the tenth of a degree at every speed: this
rung sits on top of 0.30.0's, it does not disturb it.

## The control that must fail

Two of them, and the fixture carries the permanent one.

1. **In `tests/fixtures/rigify_human.py` (`HEAD_RUNG_CASES`)**: the same body walked at Froude 0.05
   and 1.2, twice - once with the derived lag and once with `upper={"head_lag": 0.0}`, the locked
   head `upper.trunk` gave before it took a signal. Each case reports both phases at both speeds,
   the free value `sweep_deg` (how far the rung actually moved), the threshold `needs_deg` beside
   it, and the verdict `moves_with_speed`. The control's `sweep_deg` is 0.0 and its verdict is
   False; the derived case's is ~96 and True. The golden holds both, so a regression that flattens
   the rung, or one that makes the control start passing, is a CHANGED key rather than a silence.
2. **The measurement against the pre-change clip**: the BEFORE table above IS that control - the
   instrument landed one commit before the behaviour and reported the flat -0.6 on the old code.

## Not touched

`upper.resolve` builds an `Upper` only for an upright body with two legs, so the quadruped,
hopper (cricket, rabbit) and radial (starfish) paths never construct one - `Key.trunk` stays None
and neither `trunk` nor `relative_phase` is reached. There is no bird or fish fixture in this repo;
the same gate covers them. The other caller of `upper.trunk`, the idle at `actions.py:665`, passes
positional arguments only, so `head` is None there and the expression is bit-identical.

## 2026-09-20 14:28 - regress --quick, and what the goldens say

`python tools/regress.py --quick --jobs 4` selected all 23 fixtures (rig-anything changed):
**21 ok, 2 CHANGED** - `rigify_human` (57 keys) and `mpfb_woman_curvy` (23). Full output in
`C:/Users/pauli/AppData/Local/Temp/rw/hr/regress1.txt`, full diff in
`C:/Users/pauli/AppData/Local/Temp/regress-diffs/regress-20260920-141829-52220.diff`.

**Every creature fixture is `ok`**: quadruped, cricket, rabbit (hopper), starfish (radial). There
is no bird and no fish fixture in this repo; the same `upper.resolve` gate covers them.

Of the 80 changed keys, **75 are new reported keys** (`head_hz`, `head_lag`, `head_lag_cycles`,
`head_lag_deg`, `thorax_head_phase_deg`, and the whole `head_rung` block). The only numbers that
MOVED - the entire behavioural footprint of this change across 23 fixtures - are five whole-body
angular momentum readings in the fifth decimal:

| fixture / clip | key | was | now |
|---|---|---|---|
| rigify_human Run | `angular_momentum.up_mean_abs` | 0.00127 | 0.00128 |
| rigify_human Run | `angular_momentum.up_range` | 0.00403 | 0.00406 |
| rigify_human Trot | `angular_momentum.up_mean_abs` | 0.00120 | 0.00121 |
| rigify_human Trot | `angular_momentum.up_range` | 0.00423 | 0.00425 |
| mpfb_woman_curvy Run | `angular_momentum.up_range` | 0.01745 | 0.01747 |

Nothing else: no hip drop, no balance, no stride, no planted drift, no arm clearance or pose, no
export duration, no manifest. That is the head's own small contribution to L arriving at a
different phase, and it is what a correct change of this size should look like. (Those five are
the ones regress FLAGGED - above its numeric tolerance. Rewriting the goldens also recorded a
couple of within-tolerance wobbles in the same key, e.g. the MPFB Walk's `up_range` 0.03996 ->
0.03997, which is the same effect one decimal smaller.)

The goldened clips themselves now show the rung moving with the gait, which is the point - the
sweep script is scratch, these are shipped:

| | Walk | Trot | Run |
|---|---|---|---|
| rigify_human `pelvis_thorax_phase_deg` | -128.3 | -150.6 | -158.4 |
| rigify_human `thorax_head_phase_deg` | **-121.4** | **-150.7** | **-159.6** |
| mpfb_woman_curvy `pelvis_thorax_phase_deg` | -126.0 | - | -155.2 |
| mpfb_woman_curvy `thorax_head_phase_deg` | **-85.9** | - | **-146.9** |

And the fixture's control, in `report.head_rung`: derived `sweep_deg` **80.2**,
`moves_with_speed` **true**; `control_locked_head` `sweep_deg` **0.1**, `moves_with_speed`
**false**, against `needs_deg` 20.0. Both cases report the same `pelvis_thorax_phase_deg` (-89.7
and -152.1), so the new rung does not disturb the one below it.

## What cost time, and what did not

- **`tools/bump.py` refused**: "plugin.json says 0.31.0 and marketplace.json says 0.27.0: settle
  that by hand first". The 0.28.0-0.31.0 commits edited `plugins/rig-anything/.claude-plugin/
  plugin.json` by hand and never touched `.claude-plugin/marketplace.json`, which is the file
  `/plugin marketplace update` reads - so every other machine still saw 0.27.0. Settled in its own
  commit (43af2bf) by copying the four "Since" sentences plugin.json already carried and setting
  the version, with a script that reparsed both files and compared every other field and every
  other plugin before writing. **Worth knowing for the next round in this area**: a hand-edited
  plugin.json blocks the next bump.
- **Building the instrument first was again the cheap part and the whole case.** Extending
  `relative_phase` took about fifteen minutes; the flat -0.6 it printed is the entire argument for
  the change and the control for it, and it exists only because it landed one commit early.
- **`response`'s fallback is a trap for a rung that replaces a LOCK.** With nothing measured it
  returns half a cycle, which is right for the thorax (whose fast limit is anti-phase) and badly
  wrong for the head (whose predecessor is zero lag). A rig with no skinned mass would have gone
  from a locked head to an anti-phase one in silence. `Upper.__init__` now keeps the lock when
  `head_hz` is unmeasured. Found by reading the fallback path, not by a fixture.
- **The identity was worth checking as arithmetic, not as prose.** `T + (T(1-h) - T)w` against
  `T(1 - hw)` for every neck length 1..4: equal to 1e-12, so `head=None` cannot drift from the
  old behaviour.
- **No dead ends in the derivation itself**, but one honest negative: `mass.angular_momentum`, the
  arbiter that settled 0.31.0, has nothing to say here (table above). Reaching for it first was
  right; believing it would answer would have been wrong.
