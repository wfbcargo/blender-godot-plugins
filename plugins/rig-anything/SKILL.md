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
**A worm still moves** - it just does not walk:

```python
u = gait.undulate("WormTest_rig", forward="-Y", amplitude_degrees=26.0,
                  wavelengths=1.25)
print(u["implied_speed_playback_mps"], u["verification"]["passed"])
```

A travelling lateral wave along the spine - the same machinery as a gait, one
curve with a phase offset per element, except the offset comes from position
along the body rather than rank and side. Speed comes from the serpentine
model, not from stride: a snake slides along its own track, so while the wave
sweeps one wavelength backward the body advances by that wavelength's
straight-line extent.

**Do not use the exporter's stride figure for an undulator.** It will happily
produce one - it measured 0.2827 m/s for a worm whose real figure is 0.4105 -
because what it read as a stride was the head and tail wobbling. A stride means
nothing to something with no feet.

**Do not hand it rotation signs.** Which axis swings each limb forward is
probed per bone, and which way a mid-joint folds is measured from that limb's
own rest shape - so a quadruped's front legs fold like arms and its rear legs
like legs without anyone writing that down. See the rule below for why this is
not optional.

**7. Export, and get the playback speed with it.**

```python
m = export.export("MyMesh", res["rig"], r"C:/proj/assets/thing.glb",
                  foot_bones=["Foot.L", "Foot.R"],
                  actions=["Idle", "Walk", "Run", "Jump"],
                  loop_clips=["Idle", "Walk", "Run"],   # Jump is a one-shot
                  forward="-Y")
print(export.summarize(m))
```

Preflights, writes the glb, then **reads the file back** and checks the duration
actually written against the duration the frame range implied. `verified.
durations_match` is the whole point of the phase: if those disagree the speeds
are wrong, and wrong speeds are invisible until the feet slide.

`m["godot"]` is the locomotion speeds as pasteable GDScript constants, with the
derivation in the comment. Hand-transcribing those is how the wrong period got
into a shipped game.

Name the cycles in `loop_clips`. A one-shot is not required to close its seam,
and only a cycle has a speed - a jump travels 0.163 m, which clears any stride
threshold and means nothing when divided by the clip length.

A clip that cannot be measured blocks the export and `force=True` does not
waive it - `force` waives preflight, where the caller can see the problem and
judge it, while an unmeasurable clip means the deliverable itself is missing.
Drop one deliberately with `skip_bad_clips=True`, which reports what it dropped.

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

**An unbound action reads as zero too, and reads beautifully.** Blender 4.4 put
an action's curves in named *slots*, and a slot remembers the object it was
authored for. `animation_data.action = a` alone binds nothing when those names
no longer agree, so the rig holds its rest pose while every frame is stepped
through: stride 0.0000, loop seam 0.000000, floor clearance perfect. The clip
looks not merely fine but flawless. `verify.bind_action` binds the slot, checks
the action against the rig's own bones, and errors instead of reporting that.
Never assign an action by hand.

**Never take an action name that already exists.** The gait generator names its
clip after the gait, so it defaults to `Walk`. Generate a quadruped walk in a
file that already holds a humanoid's hand-authored `Walk` and the humanoid's is
deleted - same name, different skeleton, no warning, no undo. It surfaces much
later, as a character that exports standing still. `gait._fresh_action` replaces
an action only when its channels belong to this rig, and prefixes with the rig
name otherwise. This is not hypothetical; it ate a working humanoid Walk whose
only surviving copy was an already-exported `.glb`.

**Export exactly the clips you mean.** The glTF exporter's ACTIONS mode means
every action in the *file* carrying a fake user, not the ones belonging to what
is being exported - and every rig this skill builds leaves its clips behind with
a fake user set. Exporting a humanoid from a file also used to rig a rat and a
hexapod put `RatWalk`, `Trot` and `Tripod` into the humanoid's glb. `export_glb`
stages the wanted actions onto temporary NLA tracks instead, and the manifest
fails on any clip in the file that nobody asked for.

**Blocked means blocked.** When `health.verdict` is `blocked`, bone heat will
fail or silently skip geometry. Fix the mesh first; do not bind and hope.

**Real assets arrive broken, and the repair is usually a weld.** A downloaded
rat came in as 83 components in mirrored pairs with 6,504 non-manifold edges -
separate left/right shells with coincident seams. `clean_for_binding(weld=...)`
stitched it to a single component and 223 non-manifold edges. Prefer welding to
`keep_largest`, which would have thrown away half the animal.

**Scale matters before binding.** Bone heat is unreliable below ~0.1 units and
a real rat is 0.148 m long. Scale up, apply, then bind.

**Dense meshes need a proxy.** Above `max_verts` the analysis runs on a
decimated copy automatically; a 32k-vertex asset blocked the bridge entirely
before that existed. Results are world-space so they transfer unchanged.

**When classification is uncertain, ask.** A wrong archetype produces a rig that
is wrong in a way that is tedious to undo. Even commercial auto-riggers ask the
user to name a similar species. Say what you think it is, say why you are
unsure, and ask.

**Assets with no gait get no gait - but "no legs" is not "no locomotion."**
A chair and a rock do not move, and no walk should be invented for them. A worm
does move; it just has no feet to do it with, so `gait.undulate` drives a
travelling wave down its spine instead. The test to decline on is whether the
body has anything to push with at all - legs, or a chain long enough to carry a
wave - not whether it has legs.

**Order a spine by the hierarchy, never by position.** Ranking bones along the
travel axis looks obviously right and is wrong on real generated rigs. The
worm's own spine doubles back: `spine.001` sits behind its parent and in front
of its child. Rank by position and neighbouring phases land on bones that are
not neighbours, so the wave comes out as noise rather than a wave - and it
still animates, perfectly smoothly, going nowhere. `_arc_positions` walks the
skeleton instead, and decides each branch's direction once from the branch as a
whole, because deciding it per step reintroduces the same bug at one kinked
link.

## What the numbers mean

| Reading | Interpretation |
|---|---|
| `ground_contacts.count` | PAIRED contacts only: 2 biped, 4 quadruped, 6 hexapod, 0 not standing |
| `ground_contacts.midline_contacts` | A tail, belly or chin on the floor. A real rat rests its tail down, which read as a fifth leg until contacts were paired by mirror symmetry |
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
- **Phase 5** - export with stride-derived playback speed. Done.
- **Phase 5.5** - legless locomotion: a travelling lateral wave for anything
  with a spine and no legs. Done (`gait.undulate`).

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

Export was validated against a clip already shipped in a game. The run cycle's
implied speed had been worked out by hand, got the wrong period, and slid the
feet 4%; re-derived here from the same rig it comes back **2.138 m/s**, matching
the hand-corrected constant exactly, and every clip's written duration matches
the duration its frame range implies. Doing that surfaced three more quiet
failures - the slot-binding zero, the eaten `Walk`, and three foreign clips in
the humanoid's glb - all in the rules above.

The crotch is measured but is deliberately *not* used as the hip anchor. The
femoral head sits inside the pelvis, above where the legs visibly meet, so
anchoring to it dragged the leg chain 7 cm low. Anchoring on ground, shoulder
and top and letting the reference's proportions place the hip more than halves
the error. The crotch is kept as a lower bound.
