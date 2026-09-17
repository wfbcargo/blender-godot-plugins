# Flesh reference

Research behind the flesh library, how soft masses are found, and the measurements that
set its numbers. Sources are at the end; *unverified* marks what has no primary source.

## How games and films move flesh

| technique | how | where |
|---|---|---|
| jiggle bones | a damped spring on one bone's position and/or rotation, driven by its parent's motion | Source `$jigglebone`, Unreal AnimDynamics, Unity Dynamic Bone, VRChat PhysBones, VRM spring bones |
| per-vertex jiggle | each vertex a damped spring toward its skinned position, painted stiffness and weight | Maya `jiggle` deformer (stiffness 0.5, damping 0.5, jiggleWeight painted) |
| cluster skinning | shape-matching clusters as bones, four weights a vertex | NVIDIA FleX soft bodies |
| FEM tissue | muscle, fat and skin layers simulated as solids | Ziva VFX, Weta tissue, Unreal Chaos Flesh |
| body ripple | physics-driven fat and muscle response on impact, a secondary rig per body type | Fight Night Champion (EA art blog) |

Jiggle bones win for a game character built programmatically: bones and weights are core
glTF, the cost is a spring per bone, and the animation stays authored. Source's jigglebone
code is instructive: its "mass" is subtracted from Z acceleration - it is gravity - and its
stiffness is per unit mass, so w = sqrt(stiffness).

### Why not Godot's SpringBoneSimulator3D

Read at 4.7.2-stable (`scene/3d/spring_bone_simulator_3d.cpp`): the tail moves by
`(current - prev) * (1 - drag) + rot.xform(forward * (stiffness * delta) + external)`, then is
re-projected to the bone's length and converted to a rotation. It simulates **rotation
only**, stiffness is multiplied by delta but not squared (so its frequency depends on the
frame rate), and drag is per frame. Flesh needs translation and squash, and a frequency in
Hz. `SkeletonModifier3D._process_modification_with_delta` is the hook instead.

### The spring

x'' = -w^2 x - 2 zeta w x' + load, over each frame, solved exactly (under-, critically and
over-damped branches). Semi-implicit Euler at step h is stable only while
w^2 h^2 + 4 zeta w h < 4 and zeta w h < 1: at 60 Hz, f < 19 Hz undamped but < 7.9 Hz critically
damped - and firm flesh lives at 5-10 Hz.

x is the tail's offset from where the animated skeleton puts it. The load is the anchor
point's acceleration (estimated from its positions, clamped to 400 m/s^2 so a snapping key
cannot fling it, reset on a teleport past 1 m), times `response`, plus the change of gravity
relative to the rest pose times `gravity_scale`.

The pose: the head moves `translate` of the offset, the bone turns (slerped by `aim`) toward
the sprung tail, and stretches along its length by 1 + (s - 1) `squash` with the two other
axes at 1 / sqrt so the product - the volume - stays 1.

## Finding the soft masses

### What did not work

| attempt | what happened on the test figure |
|---|---|
| distance to the strongest-weighted bone, per bone | bone heat spread the breasts over `shoulder.L` and `spine.004`, whose own spread swamped them |
| basic_human's own `breast` bones | 14 cm below the breasts |
| Taubin smoothing as the lean body | 200 passes on a 1.2 cm voxel mesh moved the surface under 1.4 mm at the 99th percentile |
| one ellipse per cross-section, on the bone | the skull sits ahead of the head bone: the whole back of the head read as a bulge |
| the same ellipse with a free centre | the fit slid toward the bulges and erased the belly and buttocks |
| subtracting each ring's 30th-percentile excess | hips cancelled, and so did the buttocks; every other region grew |
| chains by nearest segment | the bloater's torso sides went to its A-posed upper arms |
| bones placed by area-weighted centroid | breast bones 11 cm low, pulled by the ribcage front |

### What does

1. **Chains.** Core deform bones (not breast, pelvis, shoulder, clavicle, heel, twist, face,
   fingers, or `ft_` bones - matched as whole name tokens, since `ear` is inside `forearm`)
   joined into polylines, continuing through the most collinear child within 35 degrees.
2. **Assignment.** A vertex belongs to the chain of its strongest-weighted bone (or that
   bone's nearest ancestor on a chain), at the arc length of its nearest point on it.
   Searched: the spine chain up to 10% of body height above the shoulder joints; limbs'
   first two segments.
3. **Envelope.** Rings of body height / 40; 24 angular sectors; the median radius per ring
   and sector. Per sector, a local line through the rings within 0.15 and within 0.30 of body
   height, refitted without rings more than 8% above it; the lower of the two scales is the
   lean radius. Excess = radius - lean.
4. **Zones.** Body coordinates per vertex: height (hip joints 0, shoulder joints 1), facing
   (0 front, 180 back), lateral distance over half the shoulder width, side, chain role.
   Each flesh type's zone selects; seeds stand out by 1.2% of body height and 25% of the lean
   radius; regions grow through 10% within a slightly larger zone; smaller than 0.3% of the
   vertices is noise. Order: bloater_belly, breast, butt, belly, love_handle, arm_flab, thigh.
5. **Bones.** Tail at the region's surface weighted by area x excess^2 (or by mark weight
   squared); head inside it by the mean excess plus half the peak; parent the core bone
   nearest the head. Weights smoothstep from 10% to 60% of the region's peak relative
   excess, averaged twice with neighbours.

### 2D marks

Rendered orthographic, rest pose, a 16-cell lettered grid and numbered candidates drawn as
geometry in a throwaway scene. Marks (cells, ellipses, candidates) are projected back with
each view's camera axes; a vertex counts when it faces the camera (normal . view > 0.05) and
a BVH ray toward the camera hits nothing. Views are merged by maximum weight; marked
weights are softened by the tissue measure (full where the surface stands out, half where
it is lean) and feathered.

### Scored on the sample bodies

Bodies are lofted super-ellipse torsos with Gaussian bumps of known centre and radius,
fused with capsule limbs by voxel remesh, rigged with rig-anything's `fit_basic_human`
(coverage 1.0) and walked with its contact locomotion. A true mass is found when a region of
its type puts its tail within max(12 cm, 60% of the mass's radius).

| body | measure alone | notes |
|---|---|---|
| Figure (breasts, buttocks, small belly) | 5/5 | breast tails 6-8 cm from the peaks; also love handles, arm flab, thighs |
| Bloater (belly, moobs, love handles, buttocks) | 5/7 | moob bones 16-19 cm low, toward the belly |
| Bloater with 2D marks | moobs 7.6 cm (0.9-cell ellipses), belly 9.8 cm, buttocks 4.2 cm | a 2x2-cell mark put the moobs 12.6 cm off |

Detection runs in 0.2-0.5 s on 17-23k vertices.

## Measured in Godot 4.7.2

- Jiggle bone heads matched the spec to 0.0000 m, and every tail lay exactly along the bone's
  local Y, on both bodies - Blender's glTF exporter keeps bones Y-along and Godot's importer
  keeps that.
- Kicked (1 m/s up), zero animation: soft_fat regions rang at 2.61 Hz for an expected damped
  2.61 (2.7 Hz at zeta 0.25); the bloated belly 1.76 for 1.77.
- Walking (rig-anything's walk, chest bounce 1.2 cm): soft fat 4-5 mm at response 1; the
  bloater's belly 10 mm. Breast and belly offsets were identical - both ride the same rigid
  spine bones.
- `verify_volume.gd` on both bodies: PASSED - heads, axes, frequencies, settling within five
  time constants, offsets within limits while walking.
- Before capping influences at four, Blender's exporter warned "more than 4 joint vertex
  influences" and renormalised on its own.

## Swing limits from Godot

`max_offset_m` is the only thing keeping a mass out of the body. A region pinned on it looks wrong,
because the clamp stops the swing dead. The limit used to be tuned by rerunning Belle's self-test
and guessing. Godot now measures it, and Blender reads what Godot measured.

**Measuring.** `JiggleModifier.measure_limits()` counts three things per region:
- the ticks within 1 mm of the limit (the test belle_demo uses);
- the separate contacts with the limit;
- the longest contact.

Beside each region it also runs shadow springs that get the same load:
- one spring with no limit, which gives `free_peak_m` and a `demand` curve;
- 33 springs on a ladder of limits, 2^(k/8) times the region's own (a quarter to four times it,
  9% apart).

The load is the anchor's acceleration plus the change of gravity. It comes from the skeleton and
never from the flesh, so each rung does exactly what the region would do with that limit. The
region's own rung reproduces its measured share to the tick.

`limit_report()` returns the report, and `print_limit_report()` prints it as
`FT_FLESH_LIMITS {json}`. `verify_flesh.gd` drives a body round a fixed 13.6 s course (below) and
prints one line per body. A game's self-test can call the same two functions around its own script.

**Suggesting.** `flesh.suggest_limits(report)` works through each region in this order:
1. A region inside the band is kept.
2. Otherwise it takes the measured rung inside the band that is nearest the target.
3. `.L`/`.R` pairs get one limit, read on both ladders. The course turns one way, so the two sides
   measure differently.
4. Sometimes the share falls across the whole band between two neighbouring rungs. That is one long
   stay on the limit, which a limit either catches or misses. The looser rung is taken and the row
   is marked `cliff`. The ladder is geometric, so a rerun measures the same rungs and the answer
   settles.
5. If the band lies past the ladder's end, the end is taken and the row says to run again.

Two more cases:
- A type's `limit_max_share` caps a raise. For breasts it is 0.66: swung in further, the skin passes
  into the chest. The row is then `capped` and says to lower `response` or raise `damping_ratio`
  instead.
- Old `FLESH ... on the limit x%` lines have no ladder, so they get an estimate: share ~
  limit^-1.74, from Belle's buttocks at 5.8 and 6.9 cm. The row says to measure again.

`flesh.apply_limits(obj, suggestion)` writes the suggested limits into the spec.

**The band is 3-9% of ticks on the limit, with a target of 6%.**

*Upper edge, 9%.* The numbers behind it:
- Belle's self-test fails a region at 10%.
- Her buttocks at 5.8 cm sat on the limit 11-12% of the time, and the eye rejected them as pinned.
  At 6.9 cm they sat at 8-9% and were kept.
- Her shipped regions read 7.5-9.0% on the self-test. Her breasts read 7.5/8.7 on one run and
  7.6/9.0 on another, so runs differ by about 0.3 points.

A 9% edge keeps that accepted look inside the band, with a margin for ticks and run-to-run spread
under the failing line.

*Lower edge, 3%.* The limit protects the mesh and the garments, so it should be as tight as the eye
allows. On the course, with the sample bodies' shipped limits:
- Breasts, buttocks and bellies sat on the limit 0.5-1.2% of the time.
- Every contact was a jump takeoff or landing: 4-7 contacts of 1-3 ticks.
- Everything else swung freely up to 12 cm. The Bloater's belly swung 25 cm, inside a 26.5 cm limit.

From 3% up, the limit also catches the stops and the turn (13-17 contacts). Below 3%, it bounds only
the hardest moment of the script, and the limit is a guess rather than a measurement.

*Target, 6%.* The middle of the band leaves 3 points either way for a script that differs from the
one measured. Belle's shipped limits sit inside the band on both her tests, so the suggestion keeps
them:
- 4.4-4.9% on `verify_flesh`'s course at her demo's response of 1.5, and 2.4-3.4% at 1.0;
- 7.5-9% on her harder self-test, which has rolls and sprint jumps.

**The course** runs in `verify_flesh.gd` at 60 Hz and measures 816 ticks:
- settle for 1 s, not measured;
- walk 3 s at 1.2 m/s, then stop for 1.5 s;
- walk through a 90-degree turn for 2 s;
- run 2.5 s at 2.6 m/s, then stop for 1.2 s;
- two standing jumps at 3.28 m/s (belle_controller's 0.55 m jump), 1.2 s each, then stand for 1 s.

Speed changes at 7 m/s^2, belle_controller's `ACCEL`. Takeoff and landing each take one tick, as a
CharacterBody3D's do. The walk clip plays at speed / 1.2.

**Converged** on follow-through's sample bodies, built and exported the way `flesh_figure` builds
them. Each suggested limit went into the spec through `apply_limits`, and the body was exported and
measured again with no override. The Godot-side `limits=` override gave the same numbers.

| body, response | run 0 (shipped limits) | applied | run after |
|---|---|---|---|
| Figure, 1.0 | breasts 1.1/1.2%, butts 0.7/0.7, belly 1.0, arm flab 90.7/88.3 (held 176-184 ticks), thighs 7.1/8.7 | breasts 5.15/5.27 -> 3.64 cm, butts 7.50/7.46 -> 3.73, belly 5.44 -> 3.53, arm flab 2.64/2.65 -> 5.76, thighs kept | breasts 5.4/3.4%, butts 3.2/3.4, belly 6.0, arm flab 5.6/4.8 (longest 9 ticks), thighs 7.1/8.7: all inside, settled |
| Bloater, 1.0 | belly 0.0%, breasts 0.5/0.5, butts 1.0/0.7, love handles 0.0/0.0, arm flab 13.9/9.6, thighs 5.1/5.0 | belly 26.5 -> 7.89 cm, breasts -> 3.74, butts -> 3.66, love handles 21.0 -> 5.31 (the ladder's end), arm flab -> 5.93 | love handles 2.7/1.2%, so run 1 moved them to 3.75 cm; run 2: every region 3.4-7.2%, settled |
| Figure, 1.5 | breast.L 11.9%, breast.R 3.7, thighs 15.2/18.4, arm flab 90.1/87.0, butts 1.1/1.1 | arm flab -> 6.85 cm, thighs -> 2.75, butts -> 5.28; breasts capped at 0.66 x peak | every region inside except breast.L at 11.9%, reported `capped` (needs 5.6 cm, allowed 5.15): settled, `in_band` false, verifier FAILED on it |
| Bloater, 1.5 | arm flab 21.5/14.1%, belly 0.6, love handles 0.0 | belly -> 12.16 cm, arm flab -> 7.06, breasts -> 5.29, butts -> 5.23, love handles -> 5.31 | every region 3.4-7.4%, settled |

The suggested limits are much tighter than the shipped ones: the Figure's breasts come out at
0.47 x peak instead of 0.66. On this course at response 1, the shipped limits bound only the jumps.

`limit_share` in the registry is left as it was. A type's share should be judged on more bodies than
two samples, and on Belle's self-test. `suggestion["types"]` gives the median suggested share per
type for that purpose.

## Tissue data

| quantity | value | source |
|---|---|---|
| breast adipose Young's modulus | 3.25 +- 0.91 kPa (fibroglandular 3.24) | Samani et al. 2007, ex vivo, small strain |
| adipose density | ~900-970 kg/m3 | BioNumbers 111213 |
| soft tissue after impact | 10-40 Hz band, higher with muscle activation | PMC6339545; 10-40 Hz figure *unverified* |
| breast, derived | G = E / 3, c_s ~ 1.07 m/s, f ~ c_s / 4R ~ 2.7 Hz at R = 0.1 m | derived, before skin and ligament stiffening |
| damping ratio of flesh | 0.2-0.35 as games use it | *unverified* in vivo |
| bloated corpse torso | 1.5-3 Hz, zeta 0.15-0.3 | design values |

## Sources

- Source SDK jigglebones.cpp - https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/public/jigglebones.cpp
- Godot SpringBoneSimulator3D, 4.7.2-stable - https://github.com/godotengine/godot/blob/4.7.2-stable/scene/3d/spring_bone_simulator_3d.cpp
- Godot SkeletonModifier3D - https://docs.godotengine.org/en/latest/classes/class_skeletonmodifier3d.html
- Unreal AnimDynamics - https://dev.epicgames.com/documentation/en-us/unreal-engine/animation-blueprint-animdynamics-in-unreal-engine
- VRM springBone 1.0 - https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_springBone-1.0/README.md
- VRChat PhysBones - https://creators.vrchat.com/common-components/physbones/
- Maya jiggle node - https://download.autodesk.com/us/Maya/2009help/Nodes/jiggle.html
- Holden, Spring-It-On - https://theorangeduck.com/page/spring-roll-call
- Fight Night Champion art blog - https://www.ea.com/news/fight-night-champion-art-blog
- Unreal Chaos Flesh - https://dev.epicgames.com/documentation/en-us/unreal-engine/chaos-flesh-overview
- Mancewicz et al. 2014, Delta Mush - https://dl.acm.org/doi/10.1145/2633374.2633376
- Samani, Zubovits, Plewes 2007, breast tissue elastic moduli - https://pubmed.ncbi.nlm.nih.gov/17327649/
- Adipose tissue density - https://bionumbers.hms.harvard.edu/bionumber.aspx?id=111213
- Soft tissue vibration - https://pmc.ncbi.nlm.nih.gov/articles/PMC6339545/
