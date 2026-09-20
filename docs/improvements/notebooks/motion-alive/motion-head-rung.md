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
