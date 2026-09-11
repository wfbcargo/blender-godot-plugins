---
name: rig-anything
description: Analyse a Blender mesh to work out how it should be rigged - whether it can be skinned at all, which way is up and forward, how many limbs touch the ground, and what archetype it is (biped, quadruped, bird, fish, or something with no template). Use when asked to rig, skeleton, bone, auto-rig or animate an arbitrary 3D asset, when deciding which skeleton template fits a model, or when Blender's automatic weights fail and the reason is unclear.
---

# rig-anything

Works out how an arbitrary Blender mesh should be rigged, rigs it, and gives
it a walk cycle - including shapes no template covers. **It measures,
classifies, builds a skeleton, binds it, and generates a looping gait for any
number of legs.**

The design splits deliberately: deterministic Python measures, and vision
classifies. Geometry alone cannot tell a dog from a table, and ground-contact
counting cannot tell front from back. Looking at the thing can.

## Running it

The scripts live beside this file and run inside Blender through the `blender`
MCP server. Blender sessions are long-lived and these modules get edited between
calls, so always reload:

```python
import sys
P = r"C:/Users/<you>/.claude/skills/rig-anything/scripts"
if P not in sys.path:
    sys.path.insert(0, P)
import rig_analysis
rig_analysis.reload_all()
from rig_analysis import measure, report, views, verify, fit, skin, decompose, build, gait
```

## Workflow

**1. Pick a target.**

```python
print(report.scene_overview())
```

One line per mesh object with vertex counts and whether it is already rigged.

**2. Measure.**

```python
print(report.summarize(measure.analyze("MyObject")))
```

Returns riggability, axes, ground contacts, extremities and a width profile.
`measure.analyze(name, up="Y")` overrides the up axis when an asset is authored
on its side.

**3. Look at it.**

```python
res = views.render_views("MyObject", r"C:/path/to/scratch", views=("front", "right", "iso"))
```

Then read the PNGs. Flat workbench shading on an isolated temp scene: clean
silhouettes, no textures to distract, and the user's scene is never touched.

**4. Classify, using both.** The measurements constrain; the renders decide.
State the archetype, the forward axis *and its sign*, and your confidence.

**5. Fit and bind.**

```python
print(skin.preflight("MyObject"))              # will bone heat bind?
skin.clean_for_binding("MyObject", keep_largest=True)   # MUTATES - copy first

res = fit.fit_basic_human("MyObject", forward_sign=-1)      # 2 contacts
res = fit.fit_basic_quadruped("MyObject", head_at=-0.3)     # 4 contacts

print(skin.bind("MyObject", res["rig"]))
```

Each fitter refuses the wrong contact count rather than producing a plausible
wrong rig. `bind` reports weight coverage; below 1.0 means geometry that will
not follow the rig.

`head_at` is the forward coordinate of the head end, and it comes from the
renders. Geometry cannot supply it: both ends of a quadruped have an extremity
and a tail can be longer than a muzzle. Omitting it falls back to a guess,
flagged as `head_end_guessed`.

**For anything else - a worm, a hexapod, a six-armed statue - there is no
template, so discover the structure and build from it:**

```python
parts = decompose.classify(obj, bands=18, head_at=-0.5)
print(parts["summary"])          # e.g. "spine of 10 joints with 6 legs"
res = build.build_from_parts("MyObject", parts=parts)
print(skin.bind("MyObject", res["rig"]))
```

Every creature is a spine, an optional head and tail continuing it, and N
limbs. A limb is one structure in two roles: grounded and weight-bearing is a
leg, free is an arm - which makes a wing an arm and a fin a limb for nothing
extra. Rigify agrees; it ships the same vocabulary as composable rig types.

**Prefer the template fitters where a template fits.** They inherit proportions
for joints that leave no trace on the silhouette - knees and elbows sit inside
the limb - so a biped fits to 2.2% of height where the generic builder has to
infer everything from the mesh.

**6. Generate a gait.**

```python
legs = gait.limbs_from_rig(res["rig"], forward="-Y")
r = gait.generate(res["rig"], legs, forward="-Y", gait="walk", frames=32)
print(r["verification"])        # floor clearance, loop seam, implied speed
```

A gait is a set of phase offsets over one shared stance/swing curve, so the
same code covers any leg count: biped 0.0/0.5, quadruped lateral-sequence walk
or diagonal trot, hexapod alternating tripods, n legs alternating by rank and
side. `gait` accepts `walk`, `trot`, `tripod`, `bound`; omit it and one is
chosen from the leg count.

It refuses a creature with no legs rather than inventing a walk for a worm.

**Do not hand it rotation signs.** Which axis swings each limb forward is
probed per bone, and which way a mid-joint folds is measured from that limb's
own rest shape - so a quadruped's front legs fold like arms and its rear legs
like legs without anyone writing that down. See the rule below for why this is
not optional.

## Rules

**Never trust a measurement you have not sanity-checked.** This harness exists
because generated rigs fail quietly - a wrong rotation sign still plays, a foot
6 mm through the floor still renders, a rig offset from its origin still
animates and merely orbits.

**Probe bone axes, never assume them.** `verify.probe_bone_axis` rotates a bone
and reports where the tip actually went. Bone roll varies per rig, per limb and
per asset. Two bones in the same chain do not have to agree, and an elbow and a
knee bend in *opposite* directions - assuming the forearm matched the shin is
the exact bug this function exists to prevent.

This is not hypothetical across rigs either. Probed on a hand-built humanoid,
every limb swung forward on **-X**. Probed on a `basic_human` fitted by this
skill to *the same mesh*, `upper_arm` swings about **Z** and `forearm`'s forward
is **+X**. Carrying one rig's convention to the other inverts the arms.

The probe reports mechanics, not anatomy. "+X moves the hand backward" is a
fact; whether that is correct depends on the joint. See
`references/joint-conventions.md`.

**A stale rig silently reads as zero.** An armature can reach a state where
posing updates `matrix_basis` but never moves the bone - and `view_layer.update`,
`update_tag`, an explicit depsgraph update and `frame_set` all return stale
values. Every measurement then reads zero and yields a complete, confident,
fictional table of rotation signs. `probe_bone_axis` self-checks and repairs
before measuring, and errors rather than reporting zeros. Do not bypass it.

**Blocked means blocked.** When `health.verdict` is `blocked`, bone heat will
fail or silently skip geometry. Fix the mesh first; do not bind and hope.

**When classification is uncertain, ask.** A wrong archetype produces a rig that
is wrong in a way that is tedious to undo. Even commercial auto-riggers ask the
user to name a similar species. Say what you think it is, say why you are
unsure, and ask.

**Assets with no gait get no gait.** A chair, a rock or a tentacle has no
locomotion. Detect and decline rather than inventing a walk cycle.

## What the numbers mean

| Reading | Interpretation |
|---|---|
| `ground_contacts.count` | 2 biped, 4 quadruped, 6 hexapod, 0 not standing (fish, flying, lying down) |
| `symmetry.scores` | Highest = mirror plane normal = the left/right axis. Near 1.0 is a clean mirror |
| `extremities` at ~100% of span | Limb tips. Head and tail usually 60-100% |
| Profile: narrow between wide | Neck and waist pinch points - candidate spine joints |
| `axes.forward_sign` | Always `unknown`. Geometry cannot settle it; the renders can |

## Status

- **Phase 0** - measurement and verification harness. Done.
- **Phase 1** - analysis, rendering, classification, report. Done.
- **Phase 2** - `basic_human` fit and bone-heat bind. Done.
- **Phase 3** - `basic_quadruped` fit and bind. Done.
- **Phase 3.5** - template-free decompose + build, any limb count. Done.
- **Phase 4** - generalised gait generation. Done.
- **Phase 5** - export with stride-derived playback speed. Not built.

Biped, measured on a 1.69 m figure against a hand-built rig: **mean joint error
0.037 m, 2.2% of height**. Quadruped, against a synthetic model with known
joints: **mean 0.046 m**, with every limb joint inside the mesh.

Template-free builds on a worm, a quadruped, a biped and a hexapod all bound at
**1.0 weight coverage** and deform correctly. Leg symmetry is good on the
quadruped and hexapod (spread 0.09). It is poor on the **biped**, where a
spurious junction splits one leg and the two come out 0.345 and 0.810 - use
`fit_basic_human` for bipeds, which is what it is for.

Gaits generated for 4 and 6 legs verify clean: **loop seam 0.000000**, no foot
below the floor, implied speeds 0.92 m/s (quadruped walk), 0.82 (trot) and 0.57
(hexapod tripod). Opposite legs correlate at -0.899, as they should. A trot's
diagonal pair correlates only +0.468 rather than near +1: the hips move in
phase, but front and rear legs fold in opposite directions so their feet trace
different paths. That is expected, not a fault.

The crotch is measured but is deliberately *not* used as the hip anchor. The
femoral head sits inside the pelvis, above where the legs visibly meet, so
anchoring to it dragged the leg chain 7 cm low. Anchoring on ground, shoulder
and top and letting the reference's proportions place the hip more than halves
the error. The crotch is kept as a lower bound.
