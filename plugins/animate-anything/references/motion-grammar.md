# Motion grammar

How a whole-body action is expressed, and how to add the next one.

## The vocabulary

Every action speaks in the body map's parts, never in bone names:

| Part | Map key | Posed with |
|---|---|---|
| pelvis / body root | `axial_joints[pelvis_index]` | `bend_axial(translation, ...)` |
| torso, neck, head | `torso`, `neck`, `head` | per-bone total pitch in `bend_axial(..., angles)` |
| rear (tail side of the chain) | `rear` | follows the pelvis pitch |
| legs (grounded) | `limbs[role == "leg"]` | `solve_limb(target, end_rotation=Identity)` to plant |
| arms (free) | `limbs[role == "arm"]` | `solve_limb(target)`, end follows |
| tails, digits, girdles | - | plain FK from their parent |

Distances are fractions of the creature: leg length `a + b`, arm reach, body
`height`. Angles are totals, not increments. Directions are `fwd`, `up_vec` and
`lat` from the map, all in armature space.

## The shape of an action

```python
def pose(s):                       # s = eased progress, 0 = rest
    axial = body.bend_axial(translation(s), angles(s))
    posed = body.fk(axial)
    overrides = dict(axial)
    for limb in contacts:          # planted: fixed target, fixed end
        ov, info = body.solve_limb(posed, limb, target_of(limb, s), end_rotation=I)
        overrides.update(ov)
    for limb in free:              # reaching: target relative to its shoulder
        ...
    return body.fk(overrides)
```

Then `motion.bake` -> `motion.evaluate` -> checks. `actions.crouch` is the
worked example; copy its structure, including the `try/finally` that restores
the rig's previous action and pose.

A frame 1 at `s = 0` MUST reproduce rest. The crouch checks it; keep that
check in every action.

## Locomotion is written against contacts

Loops that travel - walk, trot, gallop, tripod run - do not hand-write limb
targets. They go through `locomotion.plan` / `cycle`, which express everything
on the support plane fitted through the measured contacts: a contact's line on
the plane, the hip's height above it, the stroke each leg can reach on it. A
new travelling gait is a new footfall pattern in `gait.phase_offsets` (as
touchdown times) and, if it needs one, a body motion keyed off the load signal
- not a new limb routine. See `contact-locomotion.md`.

Key additions this uses: `Key.flex` (spine arch, `keyposes.flex_angles`), a
limb spec's `planted` as a 0..1 weight, and `tilt` as a function solved against
the body posed that frame.

## Planned: slide

One-shot. Contacts change mid-clip, which crouch never needed.

- Axial: drop well below crouch, pitch the torso BACK (negative lean), head
  pitched forward to keep looking ahead.
- Lead leg: extended forward along the ground - target at `fwd * 0.9 * (a+b)`
  from its hip, at floor height.
- Trail leg: folded under - the crouch solution at high depth.
- Arms: out and back for balance.
- Root motion: in place, like the other clips; report the slide distance the
  pose implies so the engine moves the body.
- New check: the lead foot and the trailing shin stay above the floor for the
  whole clip - they are meant to skim it.

## Planned: climb

Loop. Contacts are on a WALL, and swap between diagonal pairs.

- Wall plane: `fwd` distance in front of the body. Contacts sit on it.
- Pairing: left arm with right leg, like a trot - reuse `gait.phase_offsets`
  with `gait="trot"` over all limbs, arms included.
- Arm in stance: hand fixed on the wall while the body rises past it (pull).
  Arm in swing: hand leaves the wall, moves up by one rung, reattaches.
- Leg in stance: foot fixed on the wall, limb extends (push). Swing: fold, lift
  one rung, reattach.
- Body: rises one rung per half cycle - that rise per cycle is the climb's
  implied speed, the vertical analogue of `implied_speed_playback_mps`.
- Quadruped: front legs take the arm role for the duration of the action.
  Hexapod: front ranks pull, rear ranks push.
- New checks: stance contacts do not slide on the wall; no body point passes
  through the wall plane; seam closes.

## Adding a check

Checks read Blender's evaluated matrices from `motion.evaluate(...)["evaluated"]`,
never the prediction. A check measuring the prediction proves only that the
maths agrees with itself.
