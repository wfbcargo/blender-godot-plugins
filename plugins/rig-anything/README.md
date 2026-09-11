# rig-anything

Works out how an arbitrary Blender mesh should be rigged: whether automatic
weights can bind to it at all, which way is up and forward, how many limbs touch
the ground, and which skeleton archetype fits.

> **Status: phases 0 and 1.** It measures, classifies and reports. It does not
> yet build skeletons, bind weights or generate animation, and is deliberately
> **not listed in the marketplace manifest** until it does.

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

## Contents

```
SKILL.md                          the procedure, and the rules
scripts/rig_analysis/
  measure.py    riggability, symmetry, ground contacts, extremities, profile
  verify.py     axis probe, clip checks, contralateral, export origin
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
- **2** fit `Basic/basic_human`, skin, verify against a known-good biped
- **3** fit `Basic/basic_quadruped`
- **4** generalised gait generator (phase offsets scale past four legs)
- **5** export, with stride-derived playback speed
- **6** shapes matching no archetype — fall back to curve-skeleton extraction or
  shell out to UniRig. Do not reimplement either.
