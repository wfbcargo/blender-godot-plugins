---
name: animate-anything
description: Author whole-body actions - crouch, crouch walk, slide and slide recovery now, climb next - for any rigged creature in Blender by identifying its spine, neck, head, tail, legs and arms and posing it by target positions with IK, so planted feet and hands stay put. Works on hand-built, Rigify and rig-anything generic rigs alike, with every clip played back through Blender and checked for foot drift, floor penetration, joint folding and balance. Use when asked to make a creature crouch, squat, duck, sneak, crouch-walk, slide, get up, climb or perform any action beyond a walk cycle, or when asked which bones are a rig's arms, legs, spine or neck.
---

# animate-anything

Walk cycles come from `rig-anything`'s `gait`, which swings limbs through probed
axes. That is fine when feet may slide. **Crouching, sliding and climbing are
defined by contacts** - a foot stays planted while the hips drop, a hand stays
on a wall while the body rises - so this skill poses by position instead.

Four layers, in the `rig_analysis` package that `rig-anything` ships:

| Module | Does |
|---|---|
| `bodymap` | Any rig -> one body: axial chain (rear, torso, neck, head), tails, limbs with role, side, girdle/upper/lower/end/digits, lengths and bend direction |
| `motion` | Axial bends and two-bone IK as armature-space matrices, COM from the skin weights, bake to keys, **play back through Blender and compare** |
| `keyposes` | A pose as a value (`Key`) and blends between poses, so actions compose: slide -> deep crouch -> stand |
| `actions` | Whole-body actions in body-relative terms: `crouch`, `crouch_walk`, `slide`, `slide_recover` |

**Requires the `rig-anything` plugin, 0.6.0 or later.** The code ships there, in
its `scripts/rig_analysis` package; this plugin is the procedure and the rules
for using it.

## Running it

Same bootstrap as `rig-anything`, through the `blender` MCP server, with `P`
pointing at the installed rig-anything plugin's `scripts` directory:

```python
import sys, importlib
P = r"<rig-anything plugin>/scripts"
if P not in sys.path:
    sys.path.insert(0, P)
import rig_analysis
importlib.reload(rig_analysis)      # the package itself, not just its modules
rig_analysis.reload_all()
from rig_analysis import bodymap, motion, keyposes, actions, views
```

Reload the package before `reload_all`. A long-lived Blender session keeps the
`__init__` it first imported, and an old `reload_all` does not know the modules
added since: it reloads everything it lists, reports success, and
`actions.slide` is still not there.

**1. Read the body.** Always first - it is what every action is built on.

```python
print(bodymap.summary(bodymap.build("HumanoidRig", forward="-Y")))
```
```
HumanoidRig: upright body, height 1.750
  axial  Hips > Spine > Chest > Neck > Head
  torso  Hips, Spine, Chest
  neck   Neck
  head   Head
  arm  UpperArm.L Shoulder.L > UpperArm.L > Forearm.L > Hand.L   on Chest ...
  leg  Thigh.L    Thigh.L > Shin.L > Foot.L   on Hips ...
```

Check it before animating. A `(guessed)` head, a limb with the wrong role or a
warning about mirrored limbs disagreeing is cheaper to catch here than in a clip.

**2. Author.**

```python
r = actions.crouch("HumanoidRig", depth=0.6, frames=12, forward="-Y")
print(actions.summarize(r))
```

`depth` is 0..1 of what the most constrained leg allows, so the same number
means the same thing on a rat and a human. `r["crouched_height_m"]` is what to
size the engine's crouch collision shape from. The clip ends held low; stand
back up in Godot by playing it backwards.

**3. Look at it.**

```python
views.render_clip("Humanoid_Skin", "HumanoidRig", r["action"], [1, 6, 12],
                  r"C:/scratch/crouch", views=("right", "iso"))
```

Then read the PNGs. The checks cover what they were written for; a pose can
pass all of them and still read badly.

**4. Export** with `rig-anything`'s `export.export(..., actions=[...])`. List the
crouch as a one-shot, never in `loop_clips`.

## Validated

| Rig | Scheme | Result |
|---|---|---|
| HumanoidRig | hand-built | pass - hips back 0.21 m to keep COM over feet, feet drift 0.0 |
| RigTest_metarig | Rigify human | pass |
| QuadTest_rig | generic builder | pass - no hip shift needed, COM already inside |
| QuadTest_metarig, Rat_metarig | Rigify quadruped, real rat | pass |
| HexTest_rig | generic, 6 legs + 1 arm | pass |
| WormTest_rig | legless | refused - nothing to crouch on |

Blender's evaluated pose matched the prediction to ~1e-6 m on every rig. Forced
failures (fold limit removed) are caught: knees folding to 8-21 degrees and a
thigh 0.26 m through the floor.

## Rules

**Never read bone names in an action.** Read the body map. Four naming schemes
exist in this project alone.

**Never trust the hierarchy direction.** The generic builder roots a biped's
spine at the top of its neck. The map orders the axial chain rear-to-head from
geometry, and `motion` bends it as rigid segments walked out from the pelvis,
so the same bend works whichever way the parents run.

**A straight limb has no bend to measure.** The hand-built humanoid's knee sits
exactly on the hip-ankle line; reading its bend direction from rest returns
noise. The map uses the rest shape only when the mid-joint is clearly off the
line (2% forward, or 5% any direction) and otherwise a role default - knees
forward, elbows back - blended in as the limb folds, so frame one still
reproduces rest exactly.

**IK clamp margins are not free.** A triangle's height grows with the square
root of how far it is shortened, so a 1e-6 margin bent a dead-straight hexapod
arm 0.4 degrees at rest. The margin is 1e-10.

**Play it back through Blender, every time.** `motion` duplicates Blender's pose
maths; `motion.evaluate` exists to prove the duplicate right. A bone with odd
inheritance, an unbound slot or a stale armature all produce a clip whose
numbers look fine.

**Render frozen meshes, never the live rig.** Rendering the rig in a temp scene
and stepping the frame produced pixel-identical images for a stand and a crouch
- zero changed pixels out of 230,400 - while the depsgraph, queried directly,
had the right pose. And `bound_box` is the last evaluated shape, so framing a
camera on it re-centres on whatever pose came last. `render_clip` freezes each
frame's evaluated mesh and frames on rest vertices, and returns the evaluated
mesh top per frame: if those agree, the clip does not move.

**Balance comes from the skin, not a constant.** The hips are slid until the
centre of mass - computed exactly from linear blend skinning weights - sits
over the feet. On a biped that pushes the hips back; on a quadruped it does
nothing. One rule, no special case.

## Key poses and the second wave of actions

`keyposes.py` makes a pose a value - `Key(drop, shift, sway, lean, head_level,
limbs)` - and `Poser.blend(a, b, w, w_legs=, w_arms=, w_lean=)` the body between
two. `crouch_key` and `slide_key` reproduce the last frames of the Crouch and
Slide clips exactly (0.000000 m against Blender's playback), so anything built
from them joins those clips without a seam.

| Action | Built as | Checked |
|---|---|---|
| `actions.crouch_walk` | crouch key + stance feet on a straight line, swing arcs, bob, sway, arm counter-swing; stance exactly half the cycle | loop seam, stance-line slip (the skate test), reach auto-shrinks stride |
| `actions.slide_recover(to="stand")` | slide key -> deep crouch key -> rest | seam from Slide's last frame, ends at rest, feet planted while rising, balance at the deep crouch |
| `actions.slide_recover(to="crouch")` | slide key -> crouch key | seam from Slide, seam to Crouch's held pose |

Humanoid results: CrouchWalk stride 0.32 m, slip 0.0, implied speed 0.6145 m/s -
and the exporter, measuring the feet independently, returned the same 0.6145.
SlideRecover and SlideToCrouch seams all 0.0.

**Lead with the chest.** A blend moving lean and hips on one curve passed
through an upright torso over low hips mid-recovery - it read as sitting on an
invisible chair. `w_lean` runs the lean ahead.

**Reimport after re-exporting a glb.** Godot kept serving the previous file's
clips from its import cache and the player logged `Animation not found` every
frame until `godot --headless --import --path .` ran.

## Status

- Body map for every rig in the project. Done.
- Pose-by-target IK, bake, playback verification. Done.
- `crouch`, `slide`. Done.
- `keyposes`, `crouch_walk`, `slide_recover` (stand / crouch). Done.
- `climb`. Next - see `references/motion-grammar.md`.
