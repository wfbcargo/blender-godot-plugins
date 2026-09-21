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
   b. lower the hips, by at most 14% of hip height at a walk, 22% at a sprint
      - or by `max_drop`, which the playback retries then never exceed;
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

## Shaping a gait: hip drop, stance width, posture

The rule picks everything from one speed, which makes every body of a kind walk
the same way. A character is more than its proportions - an old man stoops and
shuffles, a heavy one walks with the feet apart - so `cycle` (and `plan`) take
four more arguments, and `actions.idle` takes the stance and posture so the
character stands the way it walks:

| Argument | Unit | Meaning |
|---|---|---|
| `max_drop` | share of the lowest hip height | Hard cap on the hip drop. The plan fills it before cutting ground time, and the playback retries (which otherwise lower the hips up to 0.3 leg lengths) stop there and shorten the stroke. A leg still out of reach fails with `... out of reach with the hips at max_drop`. None: 0.10 + 0.08 sqrt(Fr). |
| `centre_weight` | 0..1 | Stroke centre fore/aft: 0 the rest foot, 1 under the hip. None: by speed. |
| `stance_width` | multiple of the hip's lateral offset | Each ankle's distance from the midline (the mean of the leg roots) over its hip joint's: 1.0 feet under the hips, None the rest stance. Moves each stroke line sideways; reach, the skate check and the Idle's planted feet follow the moved line. |
| `posture` | degrees, `{"pelvis", "flex", "neck"}` | Held pitches about the body map's lateral axis, positive toward `fwd` (down, on a horizontal body): `pelvis` anterior tilt with everything above riding it; `flex` the trunk above the pelvis, shared in a ramp so the top bones take most (a thoracic curve, not a hinge at the waist); `neck` the neck and head together relative to the top of the trunk. A torso of one bone takes all the flex; a body with no neck bends the head. |

`move_set(options={role: {keyword: value}})` passes these per role.

**Why posture is solved inside the key.** Walter's hunch was first keyed on top
of the finished clip as rotations about armature +X. Its sign had to be found
by trial (the first version leaned him back), and because it came after the IK
nothing else saw it - the legs were placed under an upright body, and the
plan measured reach from hips the pelvis tilt had moved. Posed through
`keyposes.posture_angles` into `bend_axial`, the same pitch rule `lean` uses,
the legs are solved under the posed body, the plan reads the tilted hips, and
floor, reach and skate checks all measure the stooped figure. The stance the
humans used was the same story: a thigh turn keyed after the clip brought the
feet in but lowered them, and Walter's and Margaret's exported walks put a foot
1-2 cm through the floor.

Measured on the humanform crowd (MPFB bodies, resting with ankles ~1.6x the
hip offset), rebuilt with the stance and posture as arguments:

| | Before (keyed over the clip) | Arguments |
|---|---|---|
| Tomas ankle half-separation, walk / run | 0.123 / 0.131 m | 0.117 / 0.117 m (hip 0.116) |
| Ines ankle half-separation, walk / run | 0.107 / 0.115 m | 0.100 / 0.100 m (hip 0.101) |
| Walter walk, lowest foot in the exporter's check | -0.020 m | +0.010 m |
| Margaret walk, lowest foot | -0.010 m | +0.010 m |
| Walk stride, 11 people at Fr 0.2-0.25 | - | 2-5% longer: feet under the hips leave more reach |
| Base hip drop vs max_drop, every gait | - | at or under the cap (Tomas run 7.0% of 7%) |

Walter still reads hunched forward with the trunk 20 degrees ahead of its rest
line and the gaze level, and the per-bone split (0.17 / 0.33 / 0.5 of the flex
over spine.001-.003) matches the hand-tuned 0.2 / 0.35 / 0.45 it replaced.

## The upper body: `upper.py`

A walk is not legs under a statue. `cycle(upper=...)` poses the rest of an
upright biped inside the same keys, from the gait's own phase offsets - no sine
fitted to the feet afterwards:

| Term | Signal | Default walk / run |
|---|---|---|
| pelvis turn (about `up_vec`) | hip over the forward foot forward: mean of side x `leg_forward(phase)` | 4 / 9 deg |
| pelvis list (about `fwd`) | loaded hip up, pivoting on it so the stance leg reaches no further (the drop is added) | 4.5 / 6 deg |
| thorax turn, side bend | chest against the pelvis; trunk over the stance leg, in anti-phase with the list, unlagged | 3 / 7, 2 / 4 deg |
| lean, lean_bob, lean_lag | held, and a pitch twice a stride off each footstrike (`footstrike`): forward peak at the strike walking, a quarter cycle after it running | 3 / 8, 1.25 / 2.5 deg, 0 / 0.25 |
| head hold | neck and head take back this share of the chest's turn and roll (the head keeps ~64% walking, ~26% running: Pontzer et al. 2009) | 0.35 / 0.75 |
| head nod (`gaze_m`) | the head keeps 15% of the held lean, none of the bob, and pitches to hold its gaze `gaze_m` ahead as the body rises and falls (Hirasaki et al. 1999) | 1.0 m |
| arm swing | opposite the same-side leg, forward swing 15% larger; a run swings about a line 15 deg behind hanging | 16 / 25 deg each way |
| elbow, elbow_swing | walking, more flexed as the arm comes forward; running, held | 15 / 85 deg, +8 / 0 |

`leg_forward(ph, duty) = -sin(2 pi (ph - duty/2))`: +1 at touchdown, crossing
zero at mid-stance where the foot passes under its hip. The trunk terms go to
`bend_axial` as per-bone yaw and roll beside the pitch (`Key.trunk`), ramped
pelvis -> top of torso and handed back by the neck and head. Senses come from
`Body.axis_turns` - which side a positive rotation brings forward - never a
bone's roll.

**Arms are IK targets hung from gravity.** Upper-arm direction from `-up_vec`,
tilted `arm_out` away from the midline and swung about `lat`; forearm folded
`elbow` degrees in the arm's rest bend plane (the hand-side of `rest_dev`
decomposed into heading and outward shares; a straight arm folds forward); the
IK pole is the elbow that geometry implies. The old layer rotated bones in the
chest's rest frame, so Walter's hunch hung his arms 28-30 degrees behind him.

**Arm hang is measured, then checked on playback.** `arm_out` None: the least
abduction whose forearm and hand skin clears the linear-blend-skinned trunk
and thighs by `hand_clearance` (1.5 cm) at the swing's back, middle and front.
After baking, `verify.limb_clearance` on Blender's playback; while it reads
under the margin the hang widens and the clip is re-authored (up to 3 times).
A hand still inside fails the clip. `verify.signed_gap` counts a sample inside
only when it is behind the face it projects onto: the body patch is cut open at
the arms and neck, and a point nearest that cut edge read a forearm 8 cm clear
of Hugo's hip as 8 cm inside.

**An idle stands balanced.** With a posture or hanging arms the skinned centre
of mass moved off the feet - Walter's by 5.5 cm, failing export's balance
check - so `idle` shifts the hips back until it is inside the foot's inner 70%,
and softens the knees by what the legs then lack. Centring it fully put Walter's
seat 16 cm back, behind his heels; now 6.6 cm.

**Numbers that passed while the arms looked wrong.** Floor, skin, clearance and
seam all passed on a run whose centred swing (+-28 deg, elbow 75 opening on the
back swing) threw the forward forearm above level with the hand at the neck, and
on Walter's arms hung from gravity off a 30-degree hunch, hands out past his
knees. `verify.arm_pose` now runs on every `upper` clip's playback: per arm the
upper arm's angle from gravity, elbow flexion, and `hand_rise` - the palm's
height from hip (0) to shoulder (1). A walk or idle fails above 0.7 (chest), a
run above 0.65 or with an elbow opened past 140 degrees. The shipped run read
0.72; with the swing about -15 deg and the elbow held at 85 it reads 0.44-0.55
(hand from hip to lower chest). `elderly_shuffle` hangs its arms 8 degrees
behind vertical, so a stooped body's hands fall at the front of the thighs.

**And the arms that reached without rising.** `hand_rise` caught Tomas' run and
missed Walter's walk: his pre-fix hands were carried out in front of his thighs
at hip height, `hand_rise` -0.20, nowhere near the 0.7 line. The motion critic
flagged it on the strips (04 c), so `arm_pose` also reports `arm_carry_deg` -
the whole arm's angle from gravity, the palm seen from the shoulder, which reads
the same on a stooped body as on an upright one - and `verify.arm_swing` fails a
non-running clip whose arm swings 8 degrees or more and still never comes back
within 2 degrees of hanging. Across the 17 walks shipped in grungist-creek that
have arms - the 16 characters of `assets/humans/*` and Belle; the other six
walks there are armless creatures - the
arm passes behind hanging every cycle, by 3.9 degrees (Margaret's shuffle) to
17.5 (Lily); the pre-fix Walter walk comes no nearer than 8.8 degrees in front.
Idles are left out by the swing gate (every shipped idle moves 2.0-2.1 degrees)
and runs by `running` (every shipped run keeps both arms in front, 1.2-6.7
degrees at the back of the stroke) - a run is held by `hand_rise` and the elbow.
In a side view a far arm forward looks like the near arm forward, and no
per-frame angles are kept - `arm_pose` reports each arm's range over the whole
clip - so alternation is a front-view question, not one to settle from two
stills of `_right.png`.

Measured on the 16 humanform people (Phase 1-2 layered arms -> `upper`), legs
unchanged to the millimetre:

| | Layered over the clip | Inside the keys |
|---|---|---|
| Walter walk: mean upper-arm angle, forward of hanging | -30.5 deg (behind) | +6.3 deg (in front) |
| Walter walk: closest hand to body | -1.6 cm (inside) | +5.0 cm |
| Mei walk: closest hand to body | -2.5 cm | +4.9 cm |
| Margaret walk: mean arm angle | -15.4 deg | +5.4 deg |
| Hugo walk: arm out from vertical / clearance | 20.7 deg (set) / 8.0 cm | 12.7 deg (measured) / 2.7 cm |
| Walk arm swing, each way (adults) | 21 deg | 19 deg |
| Idle arms hanging behind (hunched) | Walter -28, Margaret -14 deg | +6, +4 deg |
| Clips exported without force, rechecks | 16 / 16 | 16 / 16 |

## Gait styles

Speed fixes a gait's shape for every body of a kind; people of one size walk
differently at the same Froude number. `plan` and `cycle` take the hooks, in
physical terms:

| Argument | Replaces | Meaning |
|---|---|---|
| `duty` | `duty_factor(Fr)` | ground time as a share of the cycle; reach may still cut it |
| `stride_scale` | x `relative_stride(Fr)` | at the same speed: below 1 shorter, quicker steps, above 1 slower cadence |
| `lift_scale` | x `swing_lift(Fr)` | swing foot height |
| `bounce_scale` | x `body_bounce` | hip rise and fall |
| `sway` | 0.01 (upright walk) | side-to-side hip sway, share of leg length |
| `min_knee` | `Reach(min_knee=50)` | smallest included stance knee angle |
| `extension` | 0.97 | longest a stance leg may reach, share of its length (below 1: soft knees) |

`GAIT_STYLES` presets gather them with `upper`, `posture`, `stance_width` and
`max_drop`, in "walk", "run" and "idle" sections (the section is chosen by the
Froude number asked, under 0.5 walks):

| Style | Walk | Upper body | Held |
|---|---|---|---|
| `elderly_shuffle` | duty 0.74, stride x0.8, lift x0.8, bounce x0.5, sway 0.012, extension 0.94, max_drop 0.06 | swing 5, elbow 20, arms 8 behind vertical, no lean, pelvis turn 1.5, head hold 0.9 | stoop {pelvis 2, flex 12, neck -8} |
| `heavy` | stride x1.08, lift x0.8, bounce x0.6, sway 0.03, max_drop 0.045 | swing 12, side bend 4, list 2.5, hand clearance 4 cm | stance_width 1.4 |
| `child` | stride x0.88, lift x1.15, bounce x1.5, max_drop 0.035 | swing 24 (run 30), elbow 18 | - |
| `brisk` | stride x1.05, lift x1.05 | swing 24, elbow 35, lean 4, chest turn 6 | - |
| `relaxed` | stride x0.95, lift x0.85, bounce x0.9 | swing 13, elbow 12, head hold 0.75 | - |

The elderly lift is a floor, not a taste: at x0.55 (4.7 cm on Walter) the
swing toe stayed inside `verify.recheck`'s 1% stance band for several frames
and read as a planted foot skating 31 cm; x0.65 still skated 1 cm; x0.75 was
the first clean one.

Measured on the humanform crowd, layered arms and per-person numbers (before)
against brief + style (after); stride and duty from the manifest, lift, arm
swing (upper-arm angle, half range) and sway (pelvis, half range) from
Blender's playback:

| Person, style | duty | stride m | lift m | arm swing deg | sway m |
|---|---|---|---|---|---|
| Walter, elderly_shuffle | 0.72 -> 0.78 | 0.86 -> 0.69 | 0.085 -> 0.068 | 7.1 -> 6.4 | 0.008 -> 0.010 |
| Margaret, elderly_shuffle | 0.72 -> 0.78 | 0.87 -> 0.70 | 0.082 -> 0.065 | 9.6 -> 6.4 | 0.008 -> 0.009 |
| Frank, elderly_shuffle | 0.63 -> 0.78 | 1.10 -> 0.88 | 0.099 -> 0.079 | 11.9 -> 6.4 | 0.009 -> 0.011 |
| Hugo, heavy | 0.59 -> 0.63 | 1.14 -> 1.17 | 0.098 -> 0.077 | 17.5 -> 12.9 | 0.008 -> 0.025 |
| Rosa, heavy | 0.59 -> 0.59 | 1.03 -> 1.09 | 0.089 -> 0.071 | 17.6 -> 12.9 | 0.008 -> 0.023 |
| Milo, child walk / run | 0.56 / 0.38 | 0.83 -> 0.81 / 1.88 -> 1.69 | 0.075 -> 0.089 / 0.140 -> 0.153 | 25.5 -> 25.8 / 41.8 -> 32.1 | 0.006 -> 0.007 |
| Ava, child walk | 0.56 | 0.77 -> 0.75 | 0.066 -> 0.079 | 25.5 -> 25.8 | 0.005 -> 0.006 |
| Dante, brisk walk | 0.56 | 1.22 | 0.111 -> 0.115 | 23.8 -> 25.8 | 0.009 |
| Mei, relaxed walk | 0.56 -> 0.59 | 1.03 -> 1.04 | 0.091 -> 0.079 | 21.2 -> 14.0 | 0.007 |

Duty is measured on playback (`detect`), which reads a little above the plan's.
Heavy bodies' planned 0.67 is cut to 0.55 by reach under the 4.5% drop cap - the
longer step costs ground time, not height. Stride frequency follows: the heavy
walk at 0.90 Hz, a child's at 1.46-1.56 Hz, Walter's shuffle 1.04 Hz at 0.72 m/s.

The manifests also carry `collider` from `export.collider`: children 0.13-0.18 m,
adults 0.19-0.22 m, Hugo 0.23 m - where the controller's fallback clamped every
adult at 0.22 - and Belle 0.199 m against her hand-set 0.2.

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
