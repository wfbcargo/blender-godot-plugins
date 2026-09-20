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

## 2026-09-20 14:20 - the instrument, BEFORE the change

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

## 2026-09-20 15:10 - the change

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
