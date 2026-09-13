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
| `locomotion` | Walk to sprint from ground contacts: support plane, Froude-scaled stride and duty factor, reach on the plane; `detect` reads contacts back out of any clip |
| `wings` / `flight` | Wings found from the skin or names; folded, stroked, twisted; flight speeds from size; spread, flap, glide, dive, take-off, land |

**Requires the `rig-anything` plugin, 0.9.0 or later.** The code ships there, in
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

## Any number of legs: `actions.move_set`

```python
res = actions.move_set("QuadTest_rig")    # Idle Walk Trot Run Crouch CrouchWalk
                                          # Jump Slide SlideRecover SlideToCrouch
m = locomotion.engine_manifest("QuadTest_rig", res)   # gaits + footfall schedules
```

Clips are named `<rig>_<Role>`, and the recoveries measure their seams against
that set's own Slide and Crouch. What changes with the body:

| Move | Biped | Horizontal body (4, 6 legs) |
|---|---|---|
| Walk / Trot / Run | `locomotion.cycle` at Fr 0.2 / 1.0 / 3.0 - see below | same rule; lateral-sequence walk, trot, rotary gallop, tripods |
| CrouchWalk | `gait_cycle`, alternating | same code, on the crouch pose |
| Jump | the authored humanoid Jump | `jump_keys`: load -> stretch launch -> tuck -> reach, by leg zone (front / middle / rear) |
| Slide | `slide_key`, on its back | `skid_key`: belly down, legs along the floor - front forward, rear back, middle out |
| Recovery | through a 0.9 squat, feet leading | through the ordinary crouch, feet and body together |

Validated: QuadTest_rig and HexTest_rig pass all nine; exported speeds match the
generator's (quadruped walk 0.2294 / run 0.7915 m/s, hexapod 0.1276 / 0.4403).
The downloaded rat, once tails were told apart from spines, passes all nine too.

**Flex before shortening the stride.** The quadruped stands at 97-99% of full
leg length, so any stride asked for more than 100% reach and shrinking the
stride alone walked it in place. `gait_cycle` adds knee flex first (up to +0.4
depth), then shortens. Real quadrupeds walk flexed.

**A launch is a stretch, not a rise.** Rising on planted feet needs spare leg
length; the quadruped had none, and its first jump rose 0.0.

**Solve belly height against the skin.** Spine bones put the hexapod's belly
4.5 cm through the floor; a skin estimate weighted to the spine still left
1.2 cm. `skid_key` iterates the drop on `Body.skin_lowest` - the posed
linear-blend-skinned mesh - until the lowest vertex sits at the clearance.

**Splay costs reach.** A hexapod's legs spend much of their length sideways;
`along_floor` pays for that splay before stretching, or it asks for 104%.

**Horizontal recoveries rise with their feet.** Drawing the feet in first, as a
biped does, folded the quadruped's front legs to 24-25 degrees under a belly
still on the floor.

## Walk to sprint from contacts: `locomotion`

A run is not a walk played faster. `move_set` authors Walk and Run with
`locomotion.cycle`, which works from what touches the ground rather than what
each limb is called. Full rule, research and measurements:
`references/contact-locomotion.md`.

```python
from rig_analysis import locomotion as lm
r = lm.cycle("QuadTest_rig", froude="sprint", action_name="QuadTest_rig_Run")
print(lm.summarize(r))     # gait, Fr, duty, stride, stroke/leg, natural speed, slip
d = lm.detect("QuadTest_rig", "QuadTest_rig_Run")   # contacts read back from ANY clip
```

1. Contacts are measured on the skin; a plane is fitted through them.
2. One number sets speed: the Froude number, Fr = v^2 / (g * hip height), so the
   same request means the same gait on a rat and a dog.
3. Stride (2.3 Fr^0.3 hip heights) and ground time (0.75 -> 0.27) follow from
   it; stroke = duty x stride is what the legs must reach.
4. Reach is solved on the plane: roll the foot over its toe, then drop the
   hips, then cut ground time, then - reported - shorten stride and speed.

Validated: quadruped rotary gallop at Fr 3 - stroke 1.53x its IK leg (the old
run managed 0.45), duty 0.34, 8% flight, contact slip 0.0; hexapod tripod run,
stroke 1.33x leg, 33% flight. Both walks pass, and say plainly what they could
not do - these stiff-legged test bodies reach only Fr ~0.12 of the 0.2 asked.

**Measure speed on the planted feet.** `verify.check_clip` used 2 x foot travel
per cycle, true only at duty 0.5; it read the gallop 21% slow. It now takes the
median backward speed of planted feet, and agrees with the old figure exactly
on every 50/50 clip already shipped.

**Paws do not follow the shin in swing.** At zero plant weight a straight swung
shin carried the paw out level, like a swimmer. Swing holds 70% of the planted
orientation and folds the paw back mid-swing - turning it about the ankle, not
moving the ankle, or the fold pulled legs to 115% of their length.

**Skin can outrank reach.** The rat's forearm skin is weighted to its breast
bones, so every centimetre of hip drop sank it into the floor, and its
forelimbs stand at 98% extension so without drop they have no stroke. The cycle
shortens the stroke first and only then gives back height; the rat still ends
at a 3-4 cm stroke, weaker than its old clips, which were kept. That is the
asset, not the rule.

## Tails are not spine

`bodymap` reports `tail` (base > tip) separately from `rear` (behind the pelvis
but not tail). A bone is tail when it is named so, or when its pelvis-side end
already lies behind the rearmost hip joint; everything past the first tail bone
is tail too. Neither test alone works: Rigify names its tail `spine`-`spine.003`,
and the generic builder's spine doubles back so its tail starts 0.3 m ahead of
its hips. Validated: rat and Rigify quadruped `spine.003 > ... > spine` (with
`spine.004` the pelvis), generic quadruped `tail > tail.001 > tail.002`, worm
`tail.*`, and no tail on the hexapod or either humanoid.

A tail is posed by its own rules (`motion.Body.pose_tail`): it rides the pelvis,
curls by `Key.tail_lift` and swings by `Key.tail_sway` as shares along the
chain, then **drapes** - any bone whose skin would pass below the floor swings
up about its base and lies on it. Gaits carry it lifted and swinging, the jump
streams it up, the skid lifts it clear of the stretched rear legs.

What treating it as spine had broken, all found on the rat:

| Symptom | Cause | Now |
|---|---|---|
| crouch, jump, slide, recoveries 1-3 cm through the floor | tail rode the pelvis down into the ground | drapes on the floor |
| walk and crouch walk "not locomotion", no speed | exporter sized the creature by its largest dimension - mostly tail | body sized without the tail |
| slide collision box 0.46 m against 0.34 m standing | collision height counted the lifted tail | heights and lengths exclude tail skin |
| slide ran so long the next sprint never started | slide distance scaled by a body length that was 52% tail | tail-free length (1.48 -> 0.72 m) |

**Contacts are skin, not bones.** The same drape lays toes on the floor, and a
crouch is only as deep as the skin allows (`keyposes.limit_drop_by_skin`): the
rat's wrists bulged 7-9 mm into the floor in a crouch its bones allowed. Gaits
shorten the stride when predicted skin dips. The allowance is always the rest
pose's own lowest skin, so a body authored touching the ground stays exact on
frame one.

**Rolling onto the toe only helps some feet.** `solve_contact_tilts` pivots a
planted end bone on its toe, but only where that lifts the skin: the rat's
forefoot stands near vertical, so any pivot swung its wrist down, and the first
version drove it to the 50 degree limit and sank it deeper.

**Measure skin against rest, not the first frame.** A gait's first frame is
mid-stride; as a baseline it let a run 3.6 cm under the floor pass.

**Run straight-legged first.** A flexed run folded the rat's wrists into the
ground and cut its stride to 3 cm; starting at depth 0.05 it ran at 3x its walk,
and reach still adds flex where a body needs it.

## Wings: fold, flap, glide, take off and land

A free limb whose skin is a sheet is a wing. Full rule, research and numbers:
`references/wings.md`.

```python
from rig_analysis import flight
print(bodymap.summary(bodymap.build("DragonTest_rig")))
#   WING upperarm.L membrane, by skin sheet: reach 1.427 m, area 0.746 m2, sheet 0.11, 3 fingers
res = flight.flight_set("DragonTest_rig")     # Glide Flap WingSpread TakeOff Dive Land
print(flight.summarize(res["Flap"]))
manifest_flight = flight.engine_manifest(res)
```

`actions.move_set` needs nothing new: a key that says nothing about wings holds
them folded against the flank, so walk, crouch, jump and slide all carry them.
Within `flight_set` the order is fixed - TakeOff measures its end against this
set's Flap, and Land its start against this set's Glide.

Poses: `keyposes.Key(wings=wings.state(fold, stroke, sweep, twist, fan, tilt,
tuck))`, or `{"L": ..., "R": ...}` for a roll. `fold` moves every segment
together - the avian linkage - and `tuck` belongs on the ground.

**Wings are measured against the body's skin and midline**, on Blender's
playback, and the allowance comes from the bind pose - never from a pose built
by the fold under test.

**Numbers say when a body could not fly.** Mass is skinned volume times a
density; override `mass_kg`. The dragon's 563 N/m2 is flagged, and flown anyway.

**Steer, don't blend, in the engine.** Blending flight velocity toward a new
heading cut the corner and stalled a 26 m/s dragon in a 90 degree turn.

## Playing them: `creature_controller.gd`

In the GrungistCreek project a creature's `<name>.moves.json` (clip names,
exporter-measured speeds, stand / crouch / slide heights, body size) drives one
controller for any leg count, with a box collider turned with the model and
resized per stance. `creature_demo.tscn` switches humanoid / quadruped / hexapod
live; `-- --selftest` scripts every move on each and prints the result.

Quadruped and hexapod sets add a `Trot` (Fr 1.0) between them, and the
controller changes gait where neighbouring gaits' speeds meet as a ratio, with
8% hysteresis, carrying the stride phase across so the feet do not reset.
Without it a speed change played the walk clip at up to 6x its rate.

Walk, trot and run move at the manifest's `gaits.<role>.natural_speed_mps` - the
gait's real speed at that body's size - and `contacts.<role>` carries each
foot's stance phases as `locomotion.detect` measured them, plus the foot bone's
length so the engine finds the contact at its tail. The demo's F overlay draws
the planted feet and their support polygon from that schedule.

## Status

- Body map for every rig in the project. Done.
- Pose-by-target IK, bake, playback verification. Done.
- `crouch`, `slide`. Done.
- `keyposes`, `crouch_walk`, `slide_recover` (stand / crouch). Done.
- `move_set` for any leg count: idle, walk, run, jump, skid, recoveries. Done.
- Tails told apart from spines; tail lift, sway and floor drape; skin contacts. Done.
- Contact locomotion: support plane, Froude-scaled stride and duty, reach on the
  plane, rotary gallop, spine flex, contact detection in any clip, stance-foot
  speed in the exporter. Done (0.3.0, rig-anything 0.8.0).
- Wings (0.4.0, rig-anything 0.9.0): recognised from skin or names, folded by
  one linkage, flight numbers from size, six flight clips, wing clearance and
  swept-area checks, ground moves with wings folded, flight in the controller.
  Done - `references/wings.md`.
- `climb`. Next - see `references/motion-grammar.md`.
