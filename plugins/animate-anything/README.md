# animate-anything

Whole-body actions for any rigged creature in Blender, beyond the walk cycle:
**crouch, crouch walk, slide, and the two ways out of a slide** - with climb
next.

> **Status: 0.1.0.** Validated on a hand-built humanoid, exported to Godot and
> driven by a real character controller. Crouch was also run on Rigify's human
> and quadruped metarigs, rig-anything's generic quadruped and hexapod, and a
> downloaded rat. Slide and its recoveries are biped-only by design.
>
> **Requires [`rig-anything`](../rig-anything/) 0.6.0 or later.** The code is
> its `scripts/rig_analysis` package; this plugin is the procedure and the rules.

## Why a second skill

`rig-anything` animates by swinging limbs through probed axes. That is enough
for a walk, where a foot may slide a little. It is not enough for moves defined
by **contacts**: a foot that must stay planted while the hips drop, a leg that
must reach out along the floor. So this poses by position instead - where each
foot and hand goes - and solves the joints.

## How it works

1. **One body for any rig.** Four naming schemes lived in one project - a
   hand-built `Thigh.L`, Rigify's `thigh.L` and `front_thigh.L`, the generic
   builder's `leg1_upper.L`. `bodymap` reads structure instead: sided chains
   are limbs, grounded limbs are legs and free ones arms, the unsided path is
   the spine, and the neck is whatever lies between the head and the nearest
   limb. It does not trust the hierarchy direction, because the generic builder
   roots a biped's spine at its neck.
2. **Pose by target, never by rotation sign.** Each bone's rest matrix is moved
   rigidly: the spine bends as segments walked out from the pelvis, each limb is
   a two-bone triangle whose bend plane is carried from rest, and a straight
   limb (which has no bend to measure) takes a role default blended in as it
   folds, so frame one still reproduces rest to 1e-6 m.
3. **Poses are values.** `keyposes.Key` is a pose in body terms - hip drop,
   lean, where each limb goes - and blends between keys compose actions. A
   slide recovery is `slide -> deep crouch -> stand`. The keys reproduce the
   end frames of the clips built before them exactly, so a new clip joins an
   old one without a seam.
4. **Everything is played back through Blender and measured.**

## What gets checked

| Check | Catches |
|---|---|
| prediction vs Blender playback | the pose maths disagreeing with Blender - unbound slots, stale rigs, odd inheritance |
| planted feet | drift while a foot should be still |
| stance line | a walking foot leaving its straight backward line - skating |
| reach and fold | IK clamping a limb straight; knees folded past what a joint does |
| bend direction | knees or elbows bending the wrong way, on the evaluated pose |
| bones and **skin** vs floor | a slide's backside through the ground, which bone checks cannot see |
| balance | centre of mass outside the feet, from the linear-blend-skinning weights |
| seams | a clip not starting exactly where the previous clip ends |

Forced failures prove the checks bite: with the fold limit removed they caught
knees folded to 8-21 degrees and a thigh 0.26 m through the floor.

## Results on the humanoid

| Clip | Result |
|---|---|
| Crouch | hips drop 0.26 m and slide back 0.21 m to keep the mass over the feet; drift 0.0 |
| CrouchWalk | stride 0.32 m, stance slip 0.0, loop seam 0.0, 0.6145 m/s - the exporter, measuring the feet independently, returned the same figure |
| Slide | lead leg out along the floor, trail knee out; skin 3 cm above the floor |
| SlideRecover | seam from Slide 0.0, ends on rest, feet planted while rising |
| SlideToCrouch | seam from Slide 0.0, seam to Crouch's held pose 0.0 |

## Quiet failures found on the way

- **Renders that did not render the frame.** Rendering the live rig in a temp
  scene and stepping the frame produced a stand and a crouch that diffed to
  zero changed pixels. `views.render_clip` now freezes each frame's evaluated
  mesh, frames on rest vertices, and reports the mesh top per frame.
- **A clamp margin that bent straight limbs.** 1e-6 bent a dead-straight arm
  0.4 degrees at rest, because a triangle's height grows with the square root
  of the shortening.
- **A stale package.** A long-lived Blender session keeps the `__init__` it
  first imported, so `reload_all` reloaded everything it knew about and
  silently missed the new modules.
- **A recovery that sat on a chair.** Lean and hips on one curve passed an
  upright torso over low hips. The chest now leads.

## Layout

```
SKILL.md                    # procedure, validation, rules
references/motion-grammar.md  # the key-pose vocabulary, and how slide and climb are planned
```

MIT licensed.
