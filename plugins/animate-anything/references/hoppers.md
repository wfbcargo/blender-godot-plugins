# Hoppers: rabbits and crickets

How `rig-anything` finds a jumping animal's legs and joints on a bare mesh, rigs
and weights them, and makes it hop, bound and jump - a launch the legs make, a
flight the engine makes, a landing. Modules: `hoppers` (detection, rig, weights),
`hop` (numbers, clips, checks, manifest, export) and `hopper_samples` (a test
cricket and rabbit with known joints). Requires rig-anything 0.13.0.

```python
from rig_analysis import hoppers, hop, hopper_samples as hs
hs.build_all()                               # CricketTest (30 mm), RabbitTest (0.40 m)
d = hoppers.detect("RabbitTest")             # kind= orthopteran | leporid, from the renders if the guess is wrong
print(hoppers.summary(d))                    # every leg: segments, roles, rest angles, what was inferred
print(hoppers.score(d, hs.truth("RabbitTest")))   # joint error in metres - test bodies only
hoppers.build("RabbitTest", detection=d)     # spine rooted at the pelvis, a bone per leg segment
print(hoppers.skin("RabbitTest_rig"))        # weights from the parts; warns on skin fused shut
res = hop.move_set("RabbitTest_rig")         # Idle Hop Bound JumpLaunch JumpAir JumpLand
hop.export_creature("RabbitTest", "RabbitTest_rig", res, ".../rabbit.glb", "rabbit")   # glb + .moves.json `hop`
```

## Why a jumping leg needs its own detection

A walking leg is two bones and an end. A jumping leg is a **Z**: three segments
folded against each other, and the jump is the Z opening. A cricket's hind femur
is swollen with the extensor muscle and its tibia folds flat under it; a rabbit
sits on a hind foot as long as its shin, heel on the floor, its femur buried in
the haunch. `decompose`'s Reeb graph read the test cricket as "a spine of 2
joints" and gave the rabbit five legs and its ears as arms. Ground contacts, on
the other hand, came back right on both (6 and 4) - so detection starts there.

| Step | How | Found the hard way |
|---|---|---|
| seed | each paired contact's patch - the connected run of low skin - and in it the vertex geodesically **farthest from high skin** | "farthest from the body's centre" took the rabbit's heel: sitting, its knee is over its toes. A box round the contact reached the other forefoot |
| walk | geodesic windows two bands wide, one band apart, every piece touching the last window kept | single bands broke into 12 pieces on a cricket femur; keeping the largest lost the leg at the knee |
| stop | the window reaches the body's **core thickness** (shape diameter, Shapira et al. 2008: 0.7 x the 90th percentile), crosses the midline, or grows past half the body's half-width | centroid stall alone ran up a small tube-like body; a radius jump would stop at a cricket femur five times its tibia |
| joints | optimal k-segment polyline through the window centroids (dynamic programming), k the count the kind's legs have, no segment under a tenth of the walk; each joint where the lines through its neighbours meet | fitted on samples the cricket's knee sat 3.2 mm short - a fold rounds its corner |
| flat foot | the walk leaves the floor far in front of the patch's other end (gap > 2.5 foot radii) and the foot is >= 30% of the leg: walk again **from the heel** over skin the first walk did not take | a sitting rabbit's shin lies on its foot; the first walk climbed it from the ball and never met the heel |
| corners too straight to see | a corner over 160 degrees on a floor segment, or a ball bend under 35: split the foot by the kind's toe share | the rabbit's paw bends ~7 degrees; the fit spent that joint mid-forearm |
| hidden joints | the walk ends below 60% of the body's middle height: hip fore-aft at the flesh the leg entered, at the body's middle height; on a flat foot the knee where a tibia circle about the hock (tibia = 1.25 foot) meets a femur circle about the hip (femur = 0.87 tibia), picking the meeting along the visible shank | the shank line alone - 25 mm of shin under a haunch - missed the hip |

**Kind.** Six legs, the hind pair over 1.35x the others on the skin and its femur
over 1.5x the mid femur's thickness: `orthopteran`. Four legs standing heel down on
a flat foot: `leporid` - a sitting rabbit hides most of its hind leg, so its skin
lengths can make the hind pair look *shorter*, and the flat foot is the sign that
survives. Otherwise `detect` refuses and prints the evidence.

**Published cues** (from the literature review): a locust's hind leg is about body
length and its femur 3.2x the fore femur (Burrows & Sutton 2008; Heitler); a
bush cricket's hind leg is 1.5x body length and >4x the fore leg (Burrows & Morris
2003); locust hind femur depth / length ~0.20 (Rogers et al. 2016). No published
hard threshold separates saltatorial from cursorial legs.

### Accuracy on the test bodies

| Body | Legs | Mean joint error | Worst |
|---|---|---|---|
| CricketTest, 30 mm | all six, every joint measured | 0.36-0.43 mm | 1.15 mm (a root joint, under the skin) |
| RabbitTest, 0.40 m | measured joints (hock, ball region, toes, wrist) | - | 5.5 mm |
| RabbitTest | hind leg incl. inferred hip and knee | 12.5 mm | 26 mm (knee) |
| RabbitTest | foreleg incl. inferred shoulder | 8.3 mm | 23 mm (shoulder) |

The rabbit's hind proportions are the NZ White literature numbers the priors use,
so its inferred joints test the geometry, not the priors. A real rabbit with
other proportions will be as wrong as its ratios differ.

## Rigging and weights

- Axial chain through slice centroids of the leg-free body, last bone `head`,
  **rooted at the pelvis** - the bone nearest the jumping legs' hips - pointing
  forward to the head and back to the rear.
- One bone per leg segment, named by role: `hind_femur.L > hind_tibia.L >
  hind_metatarsus.L > hind_toes.L`, `fore_femur.R > fore_tibia.R > fore_tarsus.R`.
  `bodymap` reads them as upper / lower / end / digits with no change. Each carries
  `hop_role`; the detection is stored on the rig (`hoppers.read`).
- Weights written from the parts, 1.0 coverage: leg skin by where it projects along
  its chain, handed over across each joint within ~1.8 radii; body skin along the
  spine, except that a **hidden** femur takes the haunch skin near it; smoothed 12
  iterations, 4 influences.

| Found | Rule now |
|---|---|
| a cricket rooted at its abdomen tip: the abdomen reads as a tail and sways, so the ROOT bone carried sub-millimetre translation - Godot's importer kept one key of 33 and the whole body slid 0.87 mm under planted feet | root at the pelvis |
| the inside of the rabbit's foot was never walked, weighted as body, stretched 70x | grow each leg over adjacent skin nearer its own visible segments than the spine |
| foot-top skin as near the shin above as the foot below at the Z's inner corner | a vertex belongs to a segment only if it faces away from that segment's axis |
| body skin resting on the heel followed the tibia | only hidden segments reach into body skin |
| skin fused shut - belly onto foot, shin onto foot | `skin` warns (`fused_webs`, `closed_folds`); it cannot be weighted well either way |

## The leg in stance: measured angles, not a guessed height

Hall et al. (2022, PeerJ 10:e13611) filmed NZ White rabbits hopping: **the ankle is
103 degrees at foot strike, 66 at 38% of stance, 137 at toe-off; the heel never
touches.** The tri-segmented mammal leg keeps the femur roughly parallel to the
metatarsus (Fischer & Blickhan 2006) - the pantograph Rigify's `rear_paw` imposes -
so the knee's included angle equals the ankle's. `hop.pantograph` builds hind
stance from those: the ball on its contact, the ankle at the profile's angle, femur
parallel to metatarsus, the hip where the stroke puts it fore and aft. The hip's
height is the output.

A cricket does not pantograph. Its tarsus lies on the floor and a jump is the
femur-tibia joint opening from full flexion.

## Gaits (leporid)

| | Rule | Source |
|---|---|---|
| footfalls | hind feet together, forefeet in sequence | Carneiro et al. 2021; Simons 1996 |
| `Bound` | half-bound, 3.5 strides/s and 0.95 m stride at 12 km/h, scaled by dynamic similarity on hind-leg length | Simons 1996 (J Morphol 230:299) |
| `Hop` | 0.40 s of hind stance at duty 0.5; stroke 0.55 leg | Hall 2022 for the stance time; duty and stroke design |
| body | hips ride the pantograph in hind stance; shoulders ride the forelegs in fore stance; each free while the other works, pitch solved per frame from the two, the trunk pitched as one piece | design |

| Found | Rule now |
|---|---|
| centred under the hips, the pantograph stood the legs straight and the head 26 degrees down | hind feet come down 0.15 leg lengths ahead of the hips |
| one body height and one pitch for the whole cycle: stilts, then a 47 degree nose-dive | separate hip and shoulder curves |
| `lean` tips the pelvis half as far as the chest; 47 degrees crushed the belly | rigid pitch: lean 4/3 theta, counter-arch theta/3 |
| a foreleg that could not reach got a shorter stroke - its planted foot swept back at 44% of the body's speed. Every check passed; the exporter's independent speed read the clip 60% slow | every stance foot on one belt speed; a short foreleg spends less time down (fore duty), never sweeps slower |

## The jump

| Phase | Clip | What moves |
|---|---|---|
| gather, cock, push | `JumpLaunch` | the body, over planted feet; ends on take-off |
| flight | `JumpAir` | the engine: ballistic from `takeoff_velocity_model`; the clip shapes the legs, played over the flight this launch makes |
| touchdown, settle | `JumpLand` | the body, from `land_offset_model` to rest; each foot plants the first frame its contact is in reach |

| Number | Cricket | Rabbit |
|---|---|---|
| take-off | 2.0 m/s at 25 deg | 3.0 m/s at 40 deg - **UNVERIFIED design**: no rabbit take-off measurement was found |
| source | Acheta 1-3 m/s at 20-30 deg (Hustert & Baldus 2010) | - |
| knee | cocked 10 deg (full flexion), 145 at take-off; Acheta's range is 10-150 | 140 at take-off (design) |
| co-contraction | 60 ms (Acheta 10-120 ms) | 0.20 s gather (design) |
| push | constant acceleration over the hips' travel D: 2 D / v | same |
| order | - | hip, knee, then ankle (frog: Astley & Roberts 2014) |
| landing | 139 ms (locust landing, Reichel et al. 2019), legs spread, tibiae folding | forefeet first, hind feet after |

Measured on Blender's playback: the cricket's push lasts **21.6 ms** over 21.6 mm
(Acheta: 8-30 ms), its knee goes 12.5 -> 145 degrees and its hips leave at 24.9
degrees. The rabbit leaves at 39.9 degrees, its ankle opening one frame after hip
and knee. Seams, with the engine's offsets taken out: launch -> air 0.01 / 0.59 mm,
air -> land 0.0 / 0.01 mm (cricket / rabbit).

| Found | Rule now |
|---|---|
| a planted tarsus and a still hip fix the knee angle; lowering the cricket closed its knee from 32 to 28 degrees before its belly met the floor | the hind tarsi **step in** under the femur to cock |
| a take-off offset read from the hips included the pitch: a 36 mm seam | offsets are the body's pure translation |
| toes draped onto the origin's floor in the air clip | the air clip's floor is the one the body left |
| at toe-off the ball's skin rolled 4 mm into the floor | the foot rises by it on the last push frames |
| the cricket landed mid air-clip - its flight is shorter than the clip's frames | the engine plays the air clip over its predicted flight |

## Checks

Every clip also passes the shared ones: Blender's pose against the prediction,
reach, joints folding the wrong way, bones and skin through the floor.

| Clip | Checked |
|---|---|
| `Hop`, `Bound` | loop seam; every stance contact on its line; forefeet and hind feet at one belt speed (2%); hind ankle at strike / minimum / toe-off against Hall (minimum within 15 deg); femur parallel to metatarsus (12 deg); both hind feet together; a bound's hind feet overstep the forefeet's prints |
| `JumpLaunch` | toes planted until take-off; cocked knee (cricket <= 18 deg); take-off knee within 12 deg; hips leave within 8 deg of the angle; rabbit: ankle opens after the knee |
| `JumpAir` | seam from the launch's last frame, offset removed |
| `JumpLand` | seam from the air clip, offset removed; forefeet before hind feet (rabbit); feet stay planted after touchdown; ends at rest |
| skin, all | 99th-percentile edge stretch <= 3.5x, worst edge <= 20x, <= 2% of faces inverted - against the face's **blended** rotation, edges under a quarter of the median left out |

**The skin limits were set from these bodies, and say so.** A gathered hind swing
tucks the test rabbit's thighs under its belly and inverts 1.3-1.8% of its faces
there; no weighting tried removed it (less femur influence made it worse, more too).
That is a linear-blend limit - corrective shapes would fix it and are not done. The
inherited flip test (top-weighted bone only) read skin half on a femur swinging 90
degrees as 270 inverted faces; the blended test does not.

### Results

| Clip | Result |
|---|---|
| Rabbit Hop | 0.323 m/s, 1.20 Hz; ankle 103.1 / 66.9 / 133.5 (Hall 103 / 66 / 137); femur-metatarsus <= 4.1 deg; slip 0.0; p99 stretch 3.1 |
| Rabbit Bound | 3.48 m/s, 3.35 Hz, 1.04 m stride; hind feet overstep 0.37 m; fore duty cut to 0.12 (short forelegs), belt speeds equal; p99 3.5 |
| Cricket Walk | tripods at 11.9 Hz (Acheta walks at up to 12); 0.038 m/s; slip 0.0 |
| exporter vs plan | Bound implied 1.4631 m/s x playback 2.3754 = 3.4755 natural - exactly |

All 11 clips pass; both glbs read back with matching durations.

## Engine

`hop` block: `kind`, `evidence`, `legs` (bones, roles, lengths, rest angles,
measured / inferred, plantigrade, saltatorial), `mass_kg`, `clips`, `loops`, `gaits`
(speed, frequency, stride, duty, fore touchdown phases, playback scale, overstep,
ankle), `jump` (speed, angle, flight time, range, apex, `takeoff_offset_model`,
`takeoff_velocity_model`, `land_offset_model`, push, knee, onsets, seams),
`checks`, `problems`. Plus `gaits` / `contacts` in the shape
`creature_controller.gd` reads. Model-space vectors are glTF / Godot.

GrungistCreek: `hopper_controller.gd` plays any manifest with a `hop` block;
`hopper_demo.tscn -- --selftest` runs 16 checks on Godot's skeleton - gait speeds
(2%), planted feet under 10% of body speed (rabbit 4.6% / 6.1%, cricket 3.8%), take-off
angle (1 deg), landing distance against the launch's own ballistics (1.117 m / 0.349 m,
to the millimetre), apex, and no bone jumping more than 2% of body length at a clip
switch (worst 0.12%). `-- --shot=<dir>` saves frames.

| Found in Godot | Fix |
|---|---|
| a semi-implicit step peaked the rabbit 1.6 cm low | the arc integrated exactly |
| snapping the root to the floor at touchdown left the feet a step's fall off | back up to the crossing within the step |
| the cricket's walk plays at 16x: a 60 Hz tick is a third of its stride | the selftest samples at 480 Hz |

## Not done

- **Kangaroos and frogs.** Research is in hand (kangaroo contact time 0.218 -
  0.0126 v s, near-constant hop frequency, Kram & Dawson 1998; frog proximal-to-distal
  timing, Astley & Roberts 2014) but no kind, test body or clips.
- **A rabbit take-off measurement** - the leap's speed and angle are design.
- Rabbit ears are weighted to the head and do not move.
- Real downloaded assets: both bodies here are procedural. The rat taught the rest
  of this package what real assets break; hoppers have not met one.
- Corrective shapes for the groin fold; in-air body pitch; turning mid-hop.
- Locust-style aiming (body yaw and pitch set by the front legs ~20 ms before thrust)
  is folded into a fixed nose-up aim.
