# rig-anything

Works out how an arbitrary Blender mesh should be rigged: whether automatic
weights can bind to it at all, which way is up and forward, how many limbs touch
the ground, and which skeleton archetype fits.

> **Status: phases 0-5, validated on a real asset and against shipped code.**
> It measures, classifies, builds a skeleton - from a template where one fits,
> otherwise from discovered structure - binds it with bone-heat weights,
> generates a looping gait for any number of legs, and exports it with the
> playback speed an engine needs to keep the feet from sliding.
>
> Tested end to end on a downloaded PolyHaven rat (31,937 verts, 83 mesh
> components, 6,504 non-manifold edges): classified as a quadruped, fitted,
> bound at 1.0 weight coverage, and walking. Five defects that only a real
> asset could expose are fixed below.
>
> Export was then validated against a clip already shipped in a game, whose
> implied speed had been derived by hand from the wrong period and slid the feet
> 4%. Re-derived here it returns **2.138 m/s**, matching the hand-corrected
> constant exactly. That pass exposed three further quiet failures - an action
> bound to no slot measuring as a flawless zero, a generated gait deleting
> another rig's identically-named clip, and three unrelated creatures' clips
> riding along inside the exported glb.
>
> Still **not listed in the marketplace manifest** - one real asset is
> evidence, not coverage.
>
> Biped, against a hand-built rig on a 1.69 m figure: **mean joint error
> 0.037 m, 2.2% of height**. Quadruped, against a synthetic model with known
> joints: **mean 0.046 m**, every limb joint inside the mesh. Both bound at 1.0
> weight coverage.

## The idea

Auto-rigging splits into two questions, and the literature almost only answers
the first: *where are the joints*, and *what do they do*. Template embedding
([Pinocchio, 2007](https://www.cs.toronto.edu/~jacobson/seminar/baran-and-popovic-2007.pdf))
fits a skeleton you supply; learned approaches
([RigNet](https://zhan-xu.github.io/rig-net/),
[UniRig](https://github.com/VAST-AI-Research/UniRig)) predict joints and weights
with no shape-class assumption. Nearly all of them stop at the rig; animation
comes from retargeting a library clip, which needs the skeleton to match a known
profile already.

The design here does not compete with those on geometry. It splits the work by
what each side is actually good at:

| Step | Who | Why |
|---|---|---|
| Measure landmarks | Deterministic Python | Must be reproducible |
| Classify archetype and forward axis | **Vision, from renders** | Judgement, not arithmetic |
| Fit a template | Deterministic + solver | Made tractable by knowing the archetype |
| Skin | Blender `ARMATURE_AUTO` | Already Baran & Popović's bone heat |
| Verify | Assertions | See below |

Geometry alone cannot tell a dog from a table, and counting ground contacts
cannot tell front from back. Looking at the thing can. Even commercial
auto-riggers ask the user to name a similar species; this asks a model that can
see instead.

## Why there is a verification harness

Generated rigs and clips fail **quietly**. A wrong rotation sign still plays. A
foot six millimetres through the floor still renders. A rig exported carrying a
translation still animates, and merely orbits a point off to one side. None of
these raise an error, so every one of them becomes a number you can assert on.

Three failures this harness was built around, each found the hard way:

- **Bone axes cannot be assumed.** A knee bends backward and an elbow bends
  forward. Deriving the elbow's sign from the shin's produces arms that hinge
  the wrong way - invisible at the 10-20 degrees a walk uses, unmistakable at
  the 75-85 a run uses. `verify.probe_bone_axis` measures instead.
- **A stale rig reads as zero.** An armature can reach a state where posing
  updates `matrix_basis` but never moves the bone, and `view_layer.update`,
  `update_tag`, an explicit depsgraph update and `frame_set` all return stale
  values. Every measurement then reads zero, and zeros yield a complete,
  confident, fictional table of rotation signs. The probe self-checks, repairs,
  and errors rather than reporting zeros.
- **Correlate against the mean, not zero.** A bent elbow leaves the hand
  permanently in front of the body, so its absolute sign never flips even while
  it swings perfectly. Comparing raw positions reports a false failure.

Phase 5 supplied a fifth, and the worst of them. Blender 4.4 moved an action's
curves into named *slots*, and a slot remembers which object it was authored
for. Assign the action without binding a slot and nothing is bound: the rig
holds its rest pose while every frame is stepped through, so stride reads
0.0000, the loop seam 0.000000 and floor clearance perfect. The failure does not
look like a failure; it looks like the best clip the generator ever produced.

Phase 2 supplied a fourth, from the same mesh rigged two ways: on the
hand-built humanoid every limb swings forward on **-X**, while on the fitted
`basic_human` the `upper_arm` swings about **Z** and the `forearm`'s forward is
**+X**. Bone roll is a property of the rig, not of the anatomy, so carrying a
convention between two rigs of the same character inverts the arms.

## Contents

```
SKILL.md                          the procedure, and the rules
scripts/rig_analysis/
  measure.py    riggability, symmetry, ground contacts, extremities, profile
  verify.py     axis probe, slot binding, clip checks, contralateral, origin
  export.py     preflight, glb write, read-back duration check, GDScript out
  views.py      orthographic renders in an isolated throwaway scene
  report.py     compact text output
references/
  archetypes.md          Rigify templates measured, and what evidence picks one
  joint-conventions.md   which way each joint bends, and the quadruped trap
```

## Requirements

Blender 4.x/5.x reachable through a Blender MCP server. `measure` and `verify`
need nothing else; `views` renders with Workbench, so no lights or materials are
required. Template fitting (phase 2) will need Rigify enabled:
`bpy.ops.preferences.addon_enable(module="rigify")`.

## Developing it

The repository copy is canonical. Blender only auto-loads skills from
`~/.claude/skills/`, so copy it there to test:

```
cp -r plugins/rig-anything ~/.claude/skills/
```

Blender sessions are long-lived and cache imports, so always
`rig_analysis.reload_all()` after editing.

## Roadmap

- **0** measurement and verification harness — done
- **1** analysis, rendering, classification, report — done
- **2** fit `Basic/basic_human`, skin, verify against a known-good biped — done
- **3** fit `Basic/basic_quadruped` — done
- **3.5** template-free decompose + build for any limb count — done
  (`decompose.py`, `build.py`). Structure is discovered from a Reeb graph over
  geodesic distance and a skeleton is built from the parts, so a worm, a
  hexapod or anything else with no template gets rigged. Legs, spine, head and
  tail are exact on every test shape; free-limb counts are resolution-sensitive
  and want confirming from the renders. Prefer the template fitters where a
  template fits — they inherit proportions for joints the silhouette cannot
  show.
- **4** generalised gait generator — done (`gait.py`). A gait is phase offsets
  over one shared stance/swing curve, so the same code covers any leg count:
  biped 0.0/0.5, quadruped lateral-sequence walk or diagonal trot, hexapod
  alternating tripods. Rotation signs are probed per bone and fold direction is
  measured from each limb's rest shape, so a quadruped's front legs fold like
  arms and its rear like legs with nobody writing that down. Verified clean on
  4 and 6 legs: loop seam 0.000000, no foot below the floor. Declines a worm
  rather than inventing a walk for it.
- **5** export, with stride-derived playback speed — done (`export.py`).
  Preflights what is silently wrong in an engine rather than in Blender (a rig
  off its origin orbits instead of turning; unapplied scale desynchronises the
  gait from the metres it was measured in), stages exactly the wanted actions
  onto temporary NLA tracks so no other rig's clips ride along, writes the glb,
  then **reads the file back** and asserts each written duration against the
  duration its frame range implied. Emits the locomotion speeds as pasteable
  GDScript, because transcribing them by hand is how the wrong period shipped.
- **6** shapes matching no archetype — fall back to curve-skeleton extraction or
  shell out to UniRig. Do not reimplement either.
