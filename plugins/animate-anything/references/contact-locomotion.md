# Contact locomotion

How a walk becomes a sprint for any body: the rule behind
`rig_analysis.locomotion`, the research it rests on, and what it measured on
the creatures in this project.

## Why limb typing was not enough

The first generation of gaits (`actions.gait_cycle`) was written per limb role:
every leg steps a fixed fraction of its length about its rest spot and is down
half the cycle. A run was the same cycle with fewer frames. On the quadruped
that produced a 0.16 m stroke with 3.5 cm of foot lift, and on a body standing
at 97-99% of full leg length the "run" had to fold its knees to step at all -
a crouched shuffle played quickly.

What changes between a walk and a sprint is not what the limbs *are* but what
they do against the ground: how long each contact lasts, how far it travels,
and how high the body rides above the plane those contacts make. So the rule
is written against contacts.

## The rule

1. **Find the contacts.** For each leg, the skin its distal bones dominate, the
   lowest band of it at rest (`locomotion.rest_contacts`). The joint that skin
   rolls over - the end bone's far end - is the pivot. A limb whose skin never
   reaches the ground is a leg by the body map but not a contact.
2. **Fit the support plane** through the contacts (least squares; two contacts
   give the most level plane through their line). Hip height, strides, lift and
   body drop are all measured on that plane.
3. **Pick a speed as a Froude number,** Fr = v^2 / (g h), h = hip height above
   the plane. Animals of different sizes move alike at equal Fr (Alexander &
   Jayes 1983), so "sprint" means the same thing for a rat and a dog. Named
   values: walk 0.2, trot 1.0, gallop / sprint 3.0.
4. **Derive the gait.**
   - stride / h = 2.3 Fr^0.3 (Alexander 1976)
   - duty factor (fraction of the cycle each foot is down) from Fr: 0.75 slow
     walk -> 0.5 at the walk-run change -> 0.27 fast gallop (Alexander & Jayes)
   - footfall pattern from Fr and leg count: walk below 0.5; trot, then rotary
     gallop above 2.5 for quadrupeds (LH, RH, RF, LF); alternating tripods for
     six legs, which get faster by duty factor alone (Full & Tu 1991)
   - **stroke = duty x stride** - the distance each planted contact travels.
     This is what the legs must actually reach.
5. **Fit the stroke to each leg's reach on the plane.** The contact can sit
   wherever the ankle, placed from the pivot, is within the leg's extended
   length of the hip. When the stroke will not fit, in order:
   a. roll the foot over its pivot (heel lift) - the distal segment adds reach;
   b. lower the hips, by at most 14% of hip height at a walk, 22% at a sprint;
   c. cut ground time (to 0.55 for a walk, 0.2 for a run);
   d. shorten the stride, and the speed with it - reported, never hidden.
6. **Centre the stroke** on the rest foot at a walk and under the hip at speed
   (the neutral point, and the widest part of the reach disc).
7. **Move the body with the load.** Summed mid-stance load of every leg drives
   hip height: up at mid-stance for a walk (vaulting), down for a run (spring).
   Horizontal gallopers flex the spine once a stride, extended in the flight
   after the hind feet push off.
8. **Swing to reach.** Lift peaks early; the contact swings past touchdown and
   draws back onto it; the paw holds most of its planted orientation and folds
   back mid-swing rather than following the shin out straight.
9. **Verify on playback.** Contact slip against its line on the plane, loop
   seam, reach clamps, joint fold, bones and skin through the floor. Skin
   failures give back hip drop only once the stroke has already been shortened
   by half - drop is what gives straight legs their working range.

## Measuring a clip: `locomotion.detect`

Works on any clip, generated or hand-authored. Each leg's pivot is carried
through Blender's playback; it is down while within 1% of body height of its
lowest. Returns per-leg duty factor and stance spans (as cycle phases), the
speed the planted contact sweeps back at, the flight fraction, and how much of
the cycle the skinned centre of mass sits inside the support polygon.

The exporter (`verify.check_clip`) now measures speed the same way - median
backward speed of planted feet - and falls back to the stride formula only when
no steady plant is visible. The stride formula assumes duty 0.5; on the new
clips it read the walk 30% fast and the gallop 21% slow. On every older 50/50
clip the two agree exactly, so no shipped speed moved.

## Measured

| Creature | Gait | Fr | duty | stride | stroke / IK leg | natural speed | clip checks |
|---|---|---|---|---|---|---|---|
| QuadTest | walk (lateral seq.) | 0.12 of 0.20 asked | 0.55 | 0.54 m | 0.84 | 0.75 m/s | pass, slip 0 |
| QuadTest | rotary gallop | 3.00 | 0.34 | 1.59 m | 1.53 | 3.82 m/s | pass, slip 0, flight 8% |
| HexTest | tripod walk | 0.11 of 0.20 | 0.55 | 0.27 m | 0.76 | 0.52 m/s | pass, statically stable 100% |
| HexTest | tripod run | 3.00 | 0.31 | 0.83 m | 1.33 | 2.76 m/s | pass, flight 33% |
| Rat | walk / gallop | 0.01 / 0.15 | - | 3-4 cm stroke | 0.23-0.30 | - | pass, but weaker than its old clips |

Previous quadruped run: stroke 0.45 of leg, implied 0.58 m/s, duty 0.5, no
flight. In Godot the planted contact points read 0.055-0.074 m above the body
origin - exactly the foot-bone tails' rest heights in Blender.

**The rat is limited by its asset, and the rule says so.** Its forelimbs stand
at 98% extension and its forearm skin is weighted to the breast bones, so any
hip drop sinks that skin 1-2 cm into the floor, and without drop the straight
forelimbs have no stroke. Its existing clips were kept. Fix the asset (flex the
forelimb rest pose, or reweight the forearm) before regenerating.

## Sources

- Alexander, R. McN. (1976). Estimates of speeds of dinosaurs. *Nature* 261.
  stride / hip height = 2.3 Fr^0.3.
- Alexander, R. McN. & Jayes, A. S. (1983). A dynamic similarity hypothesis for
  the gaits of quadrupedal mammals. *J. Zool.* 201. Equal Fr -> equal relative
  stride, duty factor, phase relationships.
- Full, R. J. & Tu, M. S. (1991). Mechanics of a rapid running insect: two-,
  four- and six-legged locomotion. *J. exp. Biol.* 156. Tripod running with
  aerial phases above ~1 m/s.
- Hildebrand, M. (1977). Analysis of asymmetrical gaits. *J. Mammal.* 58.
  Rotary and transverse gallop footfalls; gathered and extended suspension.
- Biancardi, C. M. & Minetti, A. E. (2012). Biomechanical determinants of
  transverse and rotary gallop in cursorial mammals. The two gallops differ in
  body yaw and roll, not energetically.
- Canine steady-locomotion studies report that dogs go faster mainly by longer
  strides at near-constant frequency, with trunk flexion adding stride at the
  highest speeds - the basis for the spine flex in rule 7.
