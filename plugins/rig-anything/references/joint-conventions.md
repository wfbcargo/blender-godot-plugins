# Joint conventions

`verify.probe_bone_axis` reports **mechanics**: rotate this bone by +30 about
local X and the observed tip moves *there*. It cannot tell you whether that is
anatomically right, because that depends on which joint it is.

This file is the missing half.

## The bug this exists to prevent

Probing a humanoid established that negative local X swings a limb forward, and
that positive X on the shin bends the knee correctly. The forearm was then
assumed to follow the shin. It does not:

| Joint | Bends | Correct sign (for the rig probed) |
|---|---|---|
| Knee (shin) | backward | **positive** X |
| Elbow (forearm) | **forward** | **negative** X |

A knee and an elbow bend in opposite directions. Using the knee's sign on the
elbow produces arms that hinge backwards.

The magnitude hides it. At the 10-22 degrees a walk cycle uses, backwards elbows
read as merely "stiff". At the 75-85 degrees a run uses, the hands never come
forward at all and it is unmistakable. A clip can therefore look acceptable and
still be wrong, which is why this is a checklist item and not an eyeball test.

## Bend directions by joint

Relative to the creature's forward direction, with the limb hanging in rest:

| Joint | Bends toward | Notes |
|---|---|---|
| Knee | backward | Digitigrade animals add an extra backward-bending hock |
| Elbow | forward | |
| Ankle | toe points down/back | Plantigrade rests flat; digitigrade rests raised |
| Wrist | mostly forward | Small range, rarely animated in a gait |
| Shoulder | swings fore/aft | Opposite phase to the same-side leg |
| Hip | swings fore/aft | |
| Neck / spine | forward flexion | Twist is a separate axis |

**Quadruped front legs are arms, not legs.** The front knee of a dog is an
elbow and bends forward; the rear stifle bends backward. A quadruped rig that
uses one sign for all four limbs is wrong on two of them. This is the single
most common quadruped rigging error and the direct analogue of the bug above.

## Which bone is which joint

The tables above say how a joint bends; which bone *is* the knee, the pelvis or the chest is
never read from its name. `bodymap.build(rig)["roles"]` names them by structure - `pelvis`, `chest`,
`head`, and per limb `upper` (hip or shoulder), `lower` (knee or elbow), `end` (ankle or wrist) under
`limbs["foot.L"]`, `limbs["hand.R"]`, `limbs["front_foot.L"]` - and a rig profile confirms them for a
known body source. Take the joint from the role, then its bend from this file. (SKILL.md, "Bone roles".)

## How to check a whole rig

1. Probe every limb bone with `verify.probe_chain`, observing the chain's end
   effector rather than the bone itself.
2. For each joint, compare the measured direction against the table above.
3. Any mismatch means the sign must be flipped for that bone - not for the
   chain, and not for the rig.

## Verification after authoring

Mechanically correct signs still permit a wrong *phase*. Check both:

- `verify.contralateral(rig, clip, "Foot.L", "Hand.L")` should be near **-1**
  (opposite limbs swing together) and `Foot.L` vs `Hand.R` near **+1**.
- Correlate each joint against **its own mean**, never against zero. A bent
  elbow leaves the hand permanently in front of the body, so its absolute sign
  never flips even while it swings perfectly well. Comparing raw positions
  reports a false failure - which it did, once.
