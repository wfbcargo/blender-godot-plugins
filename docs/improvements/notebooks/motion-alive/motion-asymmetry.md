# motion-asymmetry - L4, the bake half: a fixed per-character left/right asymmetry

Round: **motion-alive** (07 - motion that reads as alive). Branch `motion-asymmetry`,
off `main` at `328fcbc`. rig-anything 0.32.0, character-pipeline 0.16.0.

Sibling branch `motion-jitter` owns the Godot side and only reads what this one writes.
The seam was agreed before either started and is quoted verbatim in both tasks; it is
not renegotiated here.

## What it is

Nobody is symmetric. A generated walk is mirror-symmetric to the last digit, and that is
one of the tells that nobody walked it. So: a **fixed** left/right asymmetry, drawn once
from the character's own identity, stored in its spec, and baked into the gait clips. It
is not noise and it is not per-cycle - it is the same in every clip of that character and
in every build of it, which is exactly what makes it identity rather than jitter.

Four channels, each a small signed per-side term on what is mirrored today: `arm_swing`
(a gain), `shoulder_dip` (a gain), `lag` (an offset in cycles - how far behind its own leg
that side's arm swings) and `step_length` (an offset along the travel direction - where
that foot plants). `variability.SPREAD` holds each one's half-spread at `asymmetry = 1`.

## The shape it took, and why

- **A module of its own** (`rig_analysis/variability.py`), not a handful of parameters in
  `upper.py`. The seam names four fields, two of which this branch does not bake at all
  (`jitter_phase`, `jitter_amp`); somewhere has to own resolving and carrying them, and
  `locomotion.cycle` is not it.
- **The seed is SHA-256 of the character's id.** Not `hash()` - Python salts that per
  process, so two builds of one spec would disagree. Not `random.Random(seed)` either:
  each channel is drawn from `sha256("<seed>:<channel>")`, so nothing depends on the order
  channels are asked for or on any dict's iteration order. improvements 5.7 was a whole
  round lost to a per-process face shuffle, and that is the failure mode this is designed
  against.
- **Zero is the identity exactly**, not nearly. `draw(seed, 0.0)` returns a shared
  `IDENTITY` object whose every gain is the literal `1.0` and every offset the literal
  `0.0`, so the arithmetic in `arm_terms` and `key_at` is `x * 1.0` and lands on the same
  float it landed on before. A spec that asks for nothing bakes the clip it always baked.
- **No `variability` key in the report at asymmetry 0.** This is what keeps the goldens
  from moving: a block that was always present, even full of zeros, would be a diff on
  every fixture.
- **`[variability]` rides the `moves` spec section** rather than having one of its own,
  and only once the spec asks for something. A section that is always in the digest would
  move the input hash of every character that has never heard of the feature, and every
  one of them would rebuild from moves on its next build. The character's **id** rides
  with it, because that is what an unstated seed is derived from.
- **Only `locomotion.cycle`'s roles take it** (Walk, Trot, Run). `move_set` looks up which
  makers *are* `locomotion.cycle` rather than matching role names, so `legacy_gaits=True`
  (where Walk and Run are `gait_cycle`) is skipped for free and a new gait role is picked
  up for free. An idle, a crouch or a jump has no two sides taking turns.

## What cost time

- **The first shoulder-dip measurement could not possibly have worked.** It took each
  shoulder's height minus the mean of the two shoulders. With exactly two of them, each
  one's deviation from their mean is precisely minus the other's, so the two ranges come
  out *identically equal* whatever the shoulders do - the measurement reported ratio
  1.0000 on a clip whose arms were visibly 13% apart. Caught in the probe, before it
  reached a fixture, because the probe printed the free values and not a verdict. It now
  measures each shoulder over the **mean hip height**, which carries the body's own bounce
  out and leaves the side's own drop in. Cost: one probe run, about 5 minutes. Lesson: a
  measurement whose reference is derived from the quantity being compared is not a
  measurement.
- **Step length as a longer stroke on one side is physically wrong, and the exporter said
  so.** The first version scaled each side's stroke: one foot swept 2% further while planted,
  in the same stance time, at a different speed from the other. On a real character it got as
  far as the export and then `export_character` refused every gait - `thigh.L is planted at a
  different speed from the other feet - it slides 0.0182 over its stance`. It was right: for a
  body moving at one speed both planted feet must sweep back at that speed, or one of them
  skates. What actually differs in an asymmetric walk is WHERE each foot plants - each foot
  still carries one full stride a cycle - so the whole thing became one shift of each leg's
  stance centre, applied once to `pl["centres"]`, with `key_at`, the vault profile and the
  skate test needing no changes at all. The second version is both correct and about a third
  of the code. Cost: one Belle build (2 min) plus the rewrite (~20 min).
  **Lesson: an existing check refusing a change is the cheapest review there is - the check
  that caught this had been there since 0.14.0 and knew more about walking than I did.**
- **Per-leg stroke had three call sites, not one** - `key_at`, the vault profile and the skate
  test all read `state["stroke"]`. Found by grepping every `foot_state(` before running
  anything, which is why the first version at least failed for the right reason. The stance
  shift has one call site, which is the tell that it is the right shape.
- **The touchdown-frame step measurement jumped 2-3 cm at a time.** Taking each foot's step at
  the FRAME where it is furthest forward quantises to the frame rate: at 32 frames a one-frame
  move is ~2.6 cm, and the measurement came out non-monotone in the dial (0.35 read a bigger
  change than 1.0). Replaced by the mean over the planted frames, which is continuous, and the
  measured offset then tracked the drawn shift to 1e-5 m.
- **`tools/bump.py` refused both plugins** because `plugin.json` said rig-anything 0.31.0
  and `marketplace.json` still said 0.27.0 - the motion round bumped one and not the
  other, so four shipped versions were invisible to any other machine. Settled in its own
  commit by copying plugin.json's version and description across, rather than by writing
  four "Since" sentences from memory.

## Measured, off the BAKED clip

Every number below is `variability.measure` on Blender's playback of the finished action,
never the parameter that was set:

- **arm swing** - the palm's carry angle range seen from its own shoulder, the same quantity
  `verify.arm_pose` reports;
- **step length** - the gait lab's, from one foot's plant to the other's, derived from each
  foot's stance position relative to the HIPS, with **stance offset** (the +lat foot's stance
  position minus the -lat foot's) reported beside it as the free value the bake moves one for
  one, and **stride** (each foot's own travel) as the no-skate invariant;
- **shoulder dip** - the shoulder's height over the mean hip height, so the body's own bounce
  is out of it.

`index` is the symmetry index `2|L-R|/(L+R)`; a perfectly mirrored clip reads 0.

### Belle, through the whole character-pipeline, at `asymmetry = 0` and at `0.35`

The honest comparison: Belle built cold (`fresh=1`) in a scratch copy of the game from `main`
(no `[variability]`, so asymmetry 0) and from this branch with `[variability] asymmetry = 0.35`.
`+lat` / `-lat` are the body map's two sides; nothing here knows the words left and right.

**Walk** (`Belle_Walk`, Froude 0.2)

| measure | at 0 (`+lat` / `-lat`) | ratio | at 0.35 (`+lat` / `-lat`) | ratio |
|---|---|---|---|---|
| arm swing | 47.980 / 47.960 deg | **1.0004** | 44.616 / 51.481 deg | **0.8667** |
| step length | 0.4016 / 0.3386 m | 1.1860 | 0.4110 / 0.3291 m | 1.2490 |
| stance offset | +0.03148 m | - | +0.04097 m | - |
| stride (each foot's own travel) | 0.7404 / 0.7400 m | 1.0005 | 0.7418 / 0.7383 m | 1.0048 |
| shoulder dip | 0.01343 / 0.01340 m | **1.0021** | 0.01353 / 0.01329 m | **1.0178** |

**Run** (`Belle_Run`, Froude 2.0)

| measure | at 0 | ratio | at 0.35 | ratio |
|---|---|---|---|---|
| arm swing | 52.067 / 52.067 deg | **1.0000** | 47.341 / 56.189 deg | **0.8425** |
| stance offset | +0.01287 m | - | +0.02362 m | - |
| stride | 0.8409 / 0.8409 m | 1.0000 | 0.8409 / 0.8409 m | 1.0000 |
| shoulder dip | 0.02420 / 0.02420 m | **1.0000** | 0.02440 / 0.02402 m | **1.0159** |

Read it this way:

- **At 0 the machinery is exact, not nearly.** Arm swing 1.0000 on the run and 1.0004 on the
  walk, shoulder dip 1.0000 and 1.0021, stride 1.0000 and 1.0005.
- **Belle's 3.1 cm stance offset at asymmetry 0 is HERS, not this branch's.** Her two feet rest
  at different positions along the travel direction, and they did before this existed. That is
  why step length is judged on how far the offset MOVED (+0.00949 m on the walk) and not on its
  symmetry index.
- **The offset moves exactly as drawn.** Belle's draw shifts each stance line 0.00475 m, so the
  offset should move 2 x 0.00475 = 0.00950 m; it moved 0.00949. On the run, 0.01075 against
  0.01074.
- **Each foot still travels one stride at the body's speed** (0.7418 / 0.7383 on the walk,
  identical on the run). That is the invariant the first attempt broke.
- The seed Belle's id gives is `3408906589675928721`, and it is the same number in every
  process, on every build.

### The fixture body, at 0, at 0.35 on two ids, and at the dial's end

`rigify_human`'s Figure at Froude 0.2. Its own feet plant 6.5 mm apart, which is why `a_035`
below reads MORE symmetric in step length than the default while still being just as large a
change - the draw happens to shift against the body's own offset. The signed offset is what is
judged; the index is reported beside it and is not the verdict.

| case | arm swing `+lat`/`-lat` | index | stance offset | stride index | shoulder dip index |
|---|---|---|---|---|---|
| `zero` (the default) | 36.661 / 36.477 | 0.0050 | +0.00647 | 0.0011 | 0.0055 |
| `a_035` | 36.136 / 37.191 | 0.0288 | +0.00034 | 0.0017 | 0.0642 |
| `b_035` (a different id) | 33.655 / 39.803 | 0.1674 | +0.01752 | 0.0001 | 0.0251 |
| `b_10` (the dial's end) | 27.740 / 45.991 | 0.4951 | +0.03777 | 0.0020 | 0.0819 |
| `mirror` control at 0.35 | 36.137 / 35.953 | 0.0051 | (unmoved) | - | 0.0057 |

Every one of these clips **passed** its own playback checks - floor, skin, seam, balance and
the skate test - with no failures.

**The controls, and that they fail.** `RA_ASYM_MIRROR=1` gives both sides one side's draw: the
asymmetry is still drawn and still applied (both arms swing 36.1 rather than the default's
36.7), and every verdict comes back False. `RA_ASYM_NONDETERMINISTIC=1` takes the seed off the
process: `seed_from(id) == seed_from(id)` is then False, in one process, immediately.

**What a real person is worth.** `variability.SENSIBLE = 0.35`, and it is what the round should
ship: arm swing up to +-12% between the sides (healthy adults commonly differ 10-20%), the two
stance lines up to +-1% of a stroke apart, shoulder dip up to +-9%, arm lag up to +-1.4% of a
cycle. `asymmetry = 1.0` puts arm swing 27.7 against 46.0 degrees, which is a neurological
finding, not a person.

## Done when

1. **At asymmetry 0, is every existing fixture and every existing character bit-identical?**
   Yes, and there are three independent pieces of evidence.
   - `regress --quick --jobs 4`, 23 fixtures: **21 ok, 2 CHANGED, and every one of the 142
     changed keys across the whole run reads `was '<new>'`** - there is not one key in any
     golden whose value moved. The two CHANGED fixtures are the two this branch added sections
     to (`rigify_human`, `pipeline_hashes`). Log and diff kept in the scratch folder
     (`regress1.txt`, `regress1.diff`).
   - A real character: Belle built cold (`fresh=1`, every stage) in a scratch copy of the game,
     once against `main` and once against this branch, with no `[variability]` in her spec.
     `belle.glb`, `belle_sportstop.glb` and `belle_shorts.glb` are **byte-identical** (sha256
     `bcc0bd5e2f5489da...`, `ced2f12279aada62...`, `708fd3567467a396...`), and the only
     difference anywhere in `belle.moves.json` is the build's stage TIMINGS.
   - At the hash: `pipeline_hashes` flips a spec to an all-default `[variability]` and **no
     stage moves**, so no existing character even reruns.
2. **At a non-zero asymmetry, is the BAKED clip measurably different left against right, and
   does it track the spec value?** Yes - both tables above, every number off the clip through
   `variability.measure` on Blender's playback. Belle's walk goes from arm-swing ratio 1.0004 to
   0.8667 and shoulder dip 1.0021 to 1.0178; her stance offset moves 0.00949 m against a drawn
   0.00950. It tracks the dial monotonically on the fixture body: arm-swing index 0.0050 (0) to
   0.1674 (0.35) to 0.4951 (1.0); stance offset +0.00647 to +0.01752 to +0.03777.
3. **Is it deterministic?** Yes.
   - `regress --only rigify_human pipeline_hashes --twice --update --jobs 2`: each fixture built
     **twice in two separate Blender processes** (`UPDATED rigify_human [113s + 113s]`),
     `REGRESS DONE exit=0, 2 fixtures ok`, `no change` - nothing NONDETERMINISTIC. The four
     asymmetric clips are in that report, so that is `--twice` on this feature.
   - Two different ids differ: `rigify_human_a` seed 1160722956121454133 draws arm_swing
     -0.01893, `rigify_human_b` seed 14048036347988158411 draws -0.10760, and their baked clips
     differ (arm-swing ratio 0.9716 against 0.8455, stance offset +0.00034 against +0.01752).
   - In the golden: `determinism.same_id_same_draw` True, `two_ids_differ` True,
     `zero_is_exact` True (every gain the literal 1.0, every offset the literal 0.0), and the
     control `control_nondeterministic_agrees` **False**.
4. **Is `[variability]` real in the spec, documented in the skill, and echoed into
   `.moves.json` with the RESOLVED values?** Yes, exactly as the seam says. `spec.Variability`
   parses and refuses (`asymmetry = 1.5`, an unknown field, a negative seed, a boolean seed all
   raise `SpecError` naming the field). Belle's spec with `[variability] asymmetry = 0.35` built
   through the pipeline and her manifest gained **exactly one** top-level key - the set
   difference of top-level keys against the same build without the table is `['variability']` -
   holding `{"seed": 3408906589675928721, "asymmetry": 0.35, "jitter_phase": 0.0,
   "jitter_amp": 0.0}`. Documented in rig-anything's `SKILL.md` ("Nobody is symmetric") and in
   character-pipeline's (the spec block, and the manifest's `variability` block).
5. **A control that must fail, regress green, goldens reviewed, both plugins bumped, a
   notebook?** Yes: two controls (`RA_ASYM_MIRROR=1`, `RA_ASYM_NONDETERMINISTIC=1`), both
   committed in the fixture with their False verdicts in the golden, so the check fails if the
   side plumbing goes AND if a control stops working. `regress --quick --jobs 4` green. The
   goldens are additive only (the one non-added line in either is the `plugins:` version stamp,
   which regress never compares). rig-anything 0.32.0, character-pipeline 0.16.0. This file.

## Open

- **`[variability]` is not on any real game character.** Belle carries it only in the scratch
  copy; the game's own specs are untouched, as the branch rules ask. The ship step should put
  `asymmetry = 0.35` on the cast and rebuild - and then it wants an eye on it in Godot, because
  no motion critic has yet looked at an asymmetric walk.
- **`jitter_phase` and `jitter_amp` are carried, not used.** That is the seam, and `motion-jitter`
  owns them; but nothing on this side proves a value put there survives to the manifest except
  that it passes through `resolve`, which is thin.
- **Only `locomotion.cycle`'s roles take it.** Idle, Crouch, Jump and the Turns are still exactly
  mirror-symmetric. An idle is where a viewer looks longest, and an asymmetric arm hang there is
  probably the cheapest remaining win of this kind.
- **The shoulder-dip channel is quiet.** 1.0178 on Belle's walk at the shipped dial against
  1.0000 at 0 - real and measured, but the girdle only drops 2.5 degrees at a walk, so most of
  the measured excursion is the body rather than the clavicle. It earns its place on the run
  (1.0159 of a 2.4 cm excursion) more than on the walk.
- **The step-length spread is set from two bipeds.** `SPREAD["step_length"] = 0.03` of the stroke
  each way gives 4-9% step asymmetry on the two bodies measured. Nothing has measured it on a
  quadruped or a hexapod, where "the two sides" is four or six legs sharing two centres - the
  code handles it (the shift is per leg, by side) but no fixture looks.
- **`measure` takes the forward half of a foot's travel as its stance.** True for a walk and a
  run; unchecked at extreme duty factors, and with no control.
- **A body whose own feet plant unevenly hides the effect in the index.** Belle's 3.1 cm and the
  Figure's 6.5 mm are pre-existing and nobody has asked why. It may be a real asymmetry in those
  meshes, or it may be `plan`'s centre choice.
