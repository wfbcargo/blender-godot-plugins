# Archetypes and templates

Which skeleton template fits which shape, and what evidence picks it.

## Rigify templates that ship with Blender

Measured from Blender 5.2 by building each one. Bone counts matter: a template
you have to fit automatically must be small enough to land every bone
plausibly, and a face rig is not fittable from a silhouette.

| Template | Bones | Tips | Composition |
|---|---:|---:|---|
| `Basic/basic_human` | **29** | 11 | arm x2, leg x2, spine, head |
| `Basic/basic_quadruped` | **34** | 10 | front_paw x2, rear_paw x2, spine, tail, head |
| `Animals/shark` | 35 | 14 | tentacle x6 (fins), spine, tail |
| `Animals/horse` | 70 | 25 | front/rear paw x2, finger x6 |
| `Animals/bird` | 75 | 29 | paw x2, tentacle x13 (wings, feathers) |
| `human` | 159 | 39 | + full face, 10 fingers |
| `Animals/cat` | 174 | 41 | + face rig |
| `Animals/wolf` | 190 | 42 | + face rig |

**Fit the `Basic/` pair, not the detailed animal rigs.** 29 and 34 bones are
tractable to place automatically and export cleanly to a game engine. The
`Animals/` rigs carry face rigs at 174-190 bones - far too much detail to land
reliably, and mostly discarded on export anyway.

Rigify also exposes composable rig *types* — `limbs.front_paw`, `limbs.rear_paw`,
`limbs.paw`, `limbs.simple_tentacle`, `limbs.spline_tentacle`, `spines.basic_tail`,
`spines.super_head` — so a morphology with no template can be assembled from
parts rather than forced into the nearest wrong one.

Rigify is not enabled by default. Enable before use:
`bpy.ops.preferences.addon_enable(module="rigify")`.

## Choosing an archetype

No single signal is sufficient. Ground contacts give the limb count, symmetry
gives the lateral axis, the profile gives the torso, and the renders settle what
the thing actually *is*.

| Archetype | Ground contacts | Profile along up | Renders show |
|---|---|---|---|
| Biped | 2, balanced, side by side | narrow legs, wide torso+arms, narrow head | upright, arms free |
| Quadruped | 4, balanced, in a rectangle | wide and shallow, long horizontally | horizontal spine, head forward |
| Bird | 2, plus wings as extremities | upright-ish, wide at the wings | wings distinct from arms - `bodymap` reports them as WING |
| Fish / shark | **0** | streamlined, fins as extremities | no legs, dorsal/tail fins |
| Snake / tentacle | 0 or 1 long contact | uniform cross-section | one long chain, no limbs |
| Prop / static | 1 large, or an arbitrary count | no limb structure | not a creature |

Extremity counts help confirm: a biped has ~5 leaf extremities (2 hands, 2 feet,
head), a quadruped ~6 (4 feet, head, tail).

## Failure modes to watch

**A quadruped lying down reads as 0 contacts.** Check the renders before
concluding "fish".

**A biped with arms at its sides** puts the hands near the hips, so Euclidean
clustering merges them into the torso. Extremities use geodesic distance for
exactly this reason.

**A rounded sole fragments into strips** in the contact band. Ground contacts
are clustered geodesically and merged by the widest gap in pairwise distance;
a plain Euclidean radius cannot separate "two strips of one foot" from "two
feet" at any value.

**T-pose vs A-pose changes the profile** but not the contact count. Do not read
limb count off the width profile.

**An asset not at the world origin** reports landmark positions offset by its
location. That is also a rigging problem in itself: a rig exported carrying a
translation makes the character orbit a point off to one side instead of turning
in place. `verify.check_export_origin` checks it.

## Wings

A wing is its own body part too: a free limb whose skin is a sheet.
`bodymap.build` reports it with role `wing` and a `wings` entry (kind, planform
area, reach, fold frame). A dragon is four legs and two wings - a hexapod's
topology - and must not be rigged or animated as one. See animate-anything's
`references/wings.md`.

| Rig | Found by | Kind |
|---|---|---|
| DragonTest (hand-built, bones `upperarm/forearm/hand/finger`) | skin: thickness 0.11 | membrane, 3 fingers |
| BirdTest (hand-built) | name `primary` and skin | feathered |
| Rigify `Animals/bird` metarig, no skin | name `Wing` | feathered, 3 feather bones |

## Tails

A tail is its own body part, not the end of the spine. It carries no limb,
trails rather than supports, and may rest on the ground, which the spine never
does. `bodymap.build` reports it as `tail` (base to tip), apart from `rear`
(bones behind the pelvis that are not tail - a sacrum).

Recognition: named `tail*`, or the bone's pelvis-side end lies behind the
rearmost hip joint by more than 3% of the body; everything further from the
pelvis is tail too. Both tests are needed:

| Rig | Tail bones | Found by |
|---|---|---|
| Rigify basic_quadruped, downloaded rat | `spine.003 > spine.002 > spine.001 > spine` (`spine.004` is the pelvis) | position |
| generic builder quadruped | `tail > tail.001 > tail.002` | name - its spine doubles back, tail starts ahead of the hips |
| worm (no legs, so no hips) | `tail.*` | name only |

Build and size rules that follow from it:
- **Size a creature without its tail.** A rat is about half tail by length;
  thresholds scaled by overall size (the exporter's "is this locomotion" 5%)
  read its real strides as standing still.
- **Collide with the body, not the tail.** A lifted tail made a slide's box taller
  than standing.
- **Let the tail touch the floor.** Posed as rigid spine it went through the
  ground whenever the body dropped; see `motion.Body.pose_tail`.
