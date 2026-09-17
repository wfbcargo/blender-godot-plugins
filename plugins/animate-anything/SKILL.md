---
name: animate-anything
description: Author whole-body actions - crouch, crouch walk, slide and slide recovery now, climb next - for any rigged creature in Blender by identifying its spine, neck, head, tail, legs and arms and posing it by target positions with IK, so planted feet and hands stay put. Works on hand-built, Rigify and rig-anything generic rigs alike, with every clip played back through Blender and checked for foot drift, floor penetration, joint folding and balance. Use when asked to make a creature crouch, squat, duck, sneak, crouch-walk, slide, get up, climb or perform any action beyond a walk cycle, to open a jaw - bite, roar, breathe fire, swallow, engulf - to rig fins or make a fish or whale swim, to make a jellyfish pulse, a sea star or brittle star crawl or row, or an anemone sway and retract, to make a rabbit hop, bound or leap or a cricket or grasshopper walk and jump, or when asked which bones are a rig's arms, legs, spine or neck.
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
| `maw` | Mouth found on the skin; jaw, throat, gular, tongue and socket bones; lip-split relaxed weights; gape, bite, roar, breath, swallow, engulf, purge |
| `fins` / `swim` | Fins found on the skin, a fish rigged from a mesh, rays fanned; a travelling wave from body length - swim, sprint, glide, hover, turn, C-start, brake |
| `radial` / `radial_moves` | Bodies with no front or back: hub and appendages found on the skin, rigged and weighted without bone heat; a jellyfish pulses, drifts and turns, a sea star crawls, a brittle star rows, an anemone sways and retracts |
| `hoppers` / `hop` | Jumping legs found on the skin and their joints - hidden ones inferred - rigged and weighted; a rabbit hops and half-bounds on measured ankle angles, a cricket walks on tripods, both launch, fly and land |

**Requires the `rig-anything` plugin, 0.14.0 or later.** The code ships there, in
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
crouch as a one-shot, never in `loop_clips`, and name the walks and runs in
`gaits=`. Export plays every clip back through `verify.recheck` - floor, skin,
seam, skating stance feet, balance while standing still - and refuses a failing
one, so anything layered over a clip after authoring (an arm swing, a hunch, feet
brought in) is held to the same tolerances the clip was authored under. Call
`verify.recheck(rig, action)` yourself after layering to see it before export.

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
that set's own Slide and Crouch. `options={role: {keyword: value}}` hands each
role its own keywords over the defaults - a gait's `froude`, `max_drop`,
`stance_width` and `posture`, the idle's stance and posture (see below) - so
nothing needs monkeypatching. What changes with the body:

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

A character's way of walking - and the idle it stands in - goes in as
arguments:

```python
hunch = {"pelvis": 4, "flex": 30, "neck": -22}      # degrees, positive toward the front
r = lm.cycle("Walter_rig", froude=0.06, max_drop=0.06, stance_width=1.03, posture=hunch)
res = actions.move_set("Walter_rig", roles=("Idle", "Walk"), options={
    "Idle": {"stance_width": 1.03, "posture": hunch},
    "Walk": {"froude": 0.06, "max_drop": 0.06, "stance_width": 1.03, "posture": hunch}})
```

- `max_drop` - largest hip drop as a share of hip height, and a hard cap: past
  it the retries shorten the stroke, and a leg that still cannot reach fails
  with a message naming max_drop. None lets speed choose (10-22%), and the
  retries may go past it.
- `stance_width` - each ankle's distance from the midline as a multiple of its
  hip joint's: 1.0 feet under the hips, None the rest stance. Stroke lines, the
  reach solve and the skate check all move with it; `idle` holds it too.
- `posture` - held pitches in degrees about the body map's lateral axis, never
  a bone axis: `pelvis` anterior tilt (all above rides it), `flex` the trunk
  above the pelvis (ramped, most at the top), `neck` the neck and head relative
  to the top of the trunk, negative craned back. Positive moves the head end
  toward `fwd` - down, on a horizontal body.
- `centre_weight` - 0 steps about the rest foot, 1 under the hip; None by speed.
- `upper` - the upper body, moved inside the same keys on an upright biped
  (`upper.py`): pelvis turn and list, chest turning against it, side bend, lean,
  head held toward the world, arms swinging opposite their own side's leg with
  the elbow bending as they come forward. None uses `upper.defaults(froude,
  duty)` (a walk subtle, a run with 75-degree elbows); a dict overrides
  parameters in degrees and metres (`arm_swing`, `arm_forward`, `arm_out`,
  `elbow`, `elbow_swing`, `hand_in`, `pelvis_turn`, `pelvis_list`,
  `thorax_turn`, `side_bend`, `lean`, `lean_bob`, `head_hold`,
  `hand_clearance`); False leaves the rest pose. `idle` takes it too, for
  relaxed arms.

- `style` - a way of walking from `locomotion.GAIT_STYLES` (`elderly_shuffle`,
  `heavy`, `child`, `brisk`, `relaxed`) or a dict of the same shape: defaults
  for `duty`, `stride_scale`, `lift_scale`, `bounce_scale`, `sway`, `min_knee`,
  `extension`, `max_drop`, `stance_width`, `posture` and `upper`, in "walk",
  "run" and "idle" sections. Explicit arguments beat it; an `upper` dict is laid
  over the style's.

```python
res = actions.move_set("Hugo_rig", roles=("Idle", "Walk"), options={
    "Idle": {"style": "heavy", "stance_width": 1.48},
    "Walk": {"style": "heavy", "froude": 0.14, "stance_width": 1.48}})
```

**Hang arms from gravity, not from the chest.** The humans' arm swing was once
keyed over finished clips as rotations in the chest's rest frame: under
Walter's 30-degree hunch that hung his arms 28-30 degrees *behind* him, and the
forward lean subtracted from the swing sent them further back. `upper` builds
each upper-arm direction from `up_vec` and `fwd` and places the hand by IK,
with the elbow pole taken from the arm's rest bend plane (MPFB forearms rest
bent 40 degrees, Belle's arms straight - both fold forward). `arm_out` None is
measured: the least abduction that keeps forearm and hand skin
`hand_clearance` off the posed hips and thighs, then widened on Blender's
playback until `verify.limb_clearance` agrees - a heavy body's thighs move
under a swinging arm, and only playback sees that. A hand still inside the body
fails the clip. An idle with a posture or hanging arms puts the hips back until
the centre of mass is over the feet, softening the knees to reach.

**Pose the body inside the clip, not over it.** Walter's hunch and every
human's narrowed stance were once keyed on top of finished clips. The legs never
saw them, the thigh turn that brought the feet in put Walter's and Margaret's
feet 1-2 cm through the floor in the exporter's check, and the hunch's sign was
found by trial - the first Walter leaned back like a limbo dancer. Solved inside
the key, the legs stand under the posed body and every check sees it.

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

**A foot is on the ground or over its spot, never skidding into it.** Three
shared pieces each dragged a cricket's feet, and each clip's own check measured
from a touchdown it guessed, so none saw it: `hop._within_reach` pulled an
out-of-reach foot straight back to the hip, so a landing forefoot met the floor
short of its spot and slid 0.5 mm in (1.7% of the body); the poser's floor clamp
tested a folded swing foot's ankle without the fold's lift, held it planted at
floor height and dragged it 1 mm; and the swing fold, sized for paws, tipped a
5 mm tarsus into the floor. `keyposes.within_reach` now gives up height before
ground position, the clamp tests a swinging foot on the ankle it solves (a
planted foot rolling over its toe keeps the old test - with the lift, a dog's toe
sank 3.4 mm at heel-off), and `locomotion` folds only as far as the contact
stays clear. `_check_common` checks every clip: a limb that
stands on the floor at rest may not move along it while on it (`floor_skid`,
0.5% of body size). Slides opt out (`skid=False`); gaits played in place pass
their stance (`skid=in_stance`) so only swing is checked - with the three bugs
put back, the cricket walk fails it at 1.4 mm.

**Limbs are named as limbs.** `bodymap.limb_name` drops the first segment from
the upper bone: `hind_femur.L` is `hind.L`, `front_thigh.L` is `front.L`; a bone
that is only the segment (`thigh.L`, `upper_arm.L`) keeps its name. Every report
key, failure and manifest contact uses it.

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

**Bones below the floor count only if they carry skin.** MPFB's `root` has no
weights and dips 3-7 cm under the floor as the hips drop; every human walk and run
failed on it while nothing visible touched the ground. The skin check still holds
the body itself. A rig with no bound mesh keeps checking every bone.

**Leave keyed bones in their keys' rotation mode.** Authoring used to restore each
bone's mode after baking. MPFB bones rotate in Euler XYZ, so every quaternion key
was ignored and Tomas walked with still legs - while every check, run before the
restore, passed. Authoring now ends with `verify.adopt_rotation_modes`, and export
refuses a mismatch.

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

## Maws: bite, roar, breathe fire, engulf

A head with a modelled mouth gets a jaw. Full rule, research and numbers:
`references/maws.md`.

```python
from rig_analysis import maw
d = maw.detect("DragonTest_rig", kind="reptile")
maw.build("DragonTest_rig", detection=d)
print(maw.skin("DragonTest_rig")["limit"])      # widest clean gape
res = maw.maw_set("DragonTest_rig")             # Gape Bite Roar Breath BreathStart BreathEnd Swallow
manifest_maw = maw.engine_manifest(res, "DragonTest_rig")
views.render_clip("DragonTest", "DragonTest_rig", res["Gape"]["action"], [1, 16], out,
                  focus_bones=["head", "jaw"])  # look at the corner up close
```

Poses: `keyposes.Key(maw=maw.state(gape, throat, tongue, pitch))`. `gape` is 0..1
of the widest clean opening; part of it goes to the skull lifting (8.7% for a
reptile). A key without `maw` keeps the mouth shut.

**Look at the corner.** The checks catch tearing and folding; whether a cheek
reads right is a render.

**Fire goes where the jaws point.** The socket follows the bisector of the open
jaws, half the gape below the skull - so breath clips lift the head to aim.

## Fins and swimming

A fish is a spine that waves and fins that fold. Full rule, research and numbers:
`references/fins-and-swimming.md`.

```python
from rig_analysis import fins, swim
fins.build_fish("FishTest"); fins.bind("FishTest", "FishTest_rig")
swim.measure_fin_limits("FishTest_rig")
res = swim.swim_set("FishTest_rig")        # mode guessed from slenderness; flukes -> cetacean
views.render_clip("FishTest", "FishTest_rig", res["Swim"]["action"], [1, 8, 15], out, views=("top",))
```

**Look from above.** A swim reads in the top view: an S travelling to the tail.
The checks say the wave travels tailward and the tail sweeps what was planned;
whether it looks like a fish is a render.

**The engine sets the beat.** Clips play at speed / (stride x clip beat): a fish
never swims faster by wagging the same tail faster than its stride allows.

## Radial bodies: pulse, crawl, row

A jellyfish, a sea star, a brittle star and an anemone have no front, so no move
is written "forward". Full rules, research and numbers:
`references/radial-bodies.md`.

```python
from rig_analysis import radial, radial_moves as rm
radial.build("JellyTest"); radial.skin("JellyTest_rig")
res = rm.move_set("JellyTest_rig")        # medusa: Pulse Drift Turn
m = rm.engine_manifest(res, "JellyTest_rig")
views.render_clip("JellyTest", "JellyTest_rig", res["Pulse"]["action"], [1, 19, 49], out, views=("front",))
```

**A heading is chosen per move.** A bell swims aboral end first and steers by
closing one side harder; a sea star glides any way without turning; a brittle
star rows behind whichever arm is nearest. A symmetric body spun by 360/order
looks exactly as it did, so the engine spins by whole sectors and never visibly
turns.

**Look under the bell.** Every number passed while the first pulse drew all
eight tentacles in until they crossed; a front render showed it at once.

**For an octopus**, eight arms on a bilateral mantle, see
`references/tentacles.md` and the `tentacles` / `octopus` modules.

## Hoppers: hop, bound, jump

A jumping leg is a Z of three segments, and the jump is the Z opening. Full rules,
research and numbers: `references/hoppers.md`.

```python
from rig_analysis import hoppers, hop
d = hoppers.detect("RabbitTest"); hoppers.build("RabbitTest", detection=d); hoppers.skin("RabbitTest_rig")
res = hop.move_set("RabbitTest_rig")       # Idle Hop Bound JumpLaunch JumpAir JumpLand
print(hop.summarize(res["Bound"]))         # speed, ankle angles vs Hall 2022, overstep, belt speeds, skin
views.render_clip("RabbitTest", "RabbitTest_rig", res["Hop"]["action"], [1, 7, 13, 19], out, views=("right",))
```

**Build stance from measured joint angles.** The hind leg's ankle follows Hall et
al.'s 103 / 66 / 137 degrees with the femur parallel to the metatarsus; the hip's
height falls out. Guessing a body height and solving the leg to it gave stilts.

**Hips and shoulders are separate.** A bounding body rocks: the hips ride the hind
legs while they push and the shoulders the forelegs while they catch. One body
height and one pitch for the cycle put the test rabbit's head 26, then 47, degrees
down.

**Look at the hop.** Every check passed on a rabbit standing on stilts; the render
showed it at once.

**A jump is three clips and a flight.** The launch and landing move the body over
planted feet; the engine owns the arc between, applies `takeoff_offset_model` and
`land_offset_model` at the switches, and plays the air clip over the flight it
predicts. `hopper_controller.gd` in GrungistCreek does exactly that.

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
- Maws (0.5.0, rig-anything 0.10.0): mouth found on the skin, jaw and pouch
  bones, relaxed lip-split weights, gape limited by the skin, nine clips with
  stretch / fold / rigid / socket / clearance checks; a MawLayer plays them over
  locomotion in Godot. Done - `references/maws.md`.
- Fins and swimming (0.6.0, rig-anything 0.11.0): fins found on the skin, a fish
  rigged from a bare mesh, five swimming modes from body length including a
  whale's vertical wave, eight clips checked for tail sweep, tailward wave, folds
  and fin clearance; `swim_controller.gd` in Godot. Done -
  `references/fins-and-swimming.md`.
- Radial bodies (0.7.0, rig-anything 0.12.0): rotational symmetry in the
  identification report, hub and appendages on the skin, weights without bone
  heat; pulse, drift and turn for a bell, a tube-foot crawl, rowing and reverse
  rowing, sway and retract, checked for closure, symmetry, lag, crossing and
  stroke; `radial_controller.gd` in Godot. Done - `references/radial-bodies.md`.
- Hoppers (0.8.0, rig-anything 0.13.0): jumping legs and joints found on the skin,
  a pelvis-rooted rig weighted from the parts; hop and half-bound on measured ankle
  angles, tripod walk, launch / air / land jumps from published take-off numbers;
  `hopper_controller.gd` and a 16-check Godot selftest. Done - `references/hoppers.md`.
- `climb`. Next - see `references/motion-grammar.md`.
