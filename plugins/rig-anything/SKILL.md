---
name: rig-anything
description: Analyse a Blender mesh to work out how it should be rigged - whether it can be skinned at all, which way is up and forward, how many limbs touch the ground, and what archetype it is (biped, quadruped, bird, fish, a radial body with no front or back, or something with no template). Use when asked to rig, skeleton, bone, auto-rig or animate an arbitrary 3D asset, when deciding which skeleton template fits a model, when a head needs a jaw or a mouth that opens (dragon fire breath, a whale engulfing, a bite), when a fish or whale needs fins rigged or needs to swim, when a jellyfish, sea star, brittle star, anemone or other radially symmetric creature needs rigging or needs to pulse, crawl or row, when a hopper - a cricket, grasshopper, locust, rabbit or hare - needs its jumping legs and their joints found, rigged, or made to hop, bound or jump, or when Blender's automatic weights fail and the reason is unclear.
---

# rig-anything

> **Building a whole character?** Write a spec and let `character-pipeline` run this plugin in the right order with the others - see that plugin's SKILL.md.

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
import importlib, rig_analysis
importlib.reload(rig_analysis)       # reload_all cannot see a module list it was loaded without
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
Each object fills its frame; to compare sizes pass `frame_height_m=2.1` (to
`render_views` or `views.render_clip`) - a fixed-height frame from the floor up,
grown only if the body needs more, so a child renders smaller than a man and
their feet line up. The scale used comes back as `ortho_scale`.

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
limbs. A limb is one structure in three roles: grounded and weight-bearing is a
leg, free is an arm, and free with a skin that is a sheet is a **wing** - found
by `bodymap` from the skin, or from bone names on a bare metarig. Rigify agrees;
it ships the same vocabulary as composable rig types.

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

`gait.generate` swings limbs through probed axes and is fine for a first look.
**For clips that ship, use `locomotion.cycle`**, which poses by contact on the
support plane and derives stride, ground time, footfall pattern and reach from
one Froude number - a walk and a sprint from the same rule:

```python
from rig_analysis import locomotion as lm
r = lm.cycle(rig_name, froude="sprint")      # or "walk", "trot", or a number
print(lm.summarize(r))
```

A character's way of walking goes in as arguments, not as keys layered over the
clip afterwards: `max_drop` (hip drop cap, share of hip height), `stance_width`
(ankle offset from the midline over the hip's; 1.0 feet under the hips) and
`posture` (`{"pelvis", "flex", "neck"}` degrees, positive toward `fwd`). The
same stance and posture reach `actions.idle`, and
`actions.move_set(options={role: {...}})` passes them per role.

An upright biped's **upper body moves inside the same keys** (`upper.py`):
pelvis turn and list, chest counter-turn, side bend, lean, a head that holds
its orientation, and arms swinging opposite their own side's leg - driven by
IK hand targets built against gravity and the body's heading, with the elbow
pole from each arm's rest bend plane, so a hunch hangs the arms in front and a
bent-elbow rest pose bends the same way as a straight one. How far the arms
hang out is measured on the skin and widened on playback until the forearm and
hand clear the hips (`verify.limb_clearance`, now a cycle check). Parameters
are degrees and metres, scaled by Froude (`upper.defaults`); `idle` gets
relaxed arms and puts the hips back over the feet when a posture or hanging
arms would tip the body forward. `cycle(upper={...})` / `idle(upper={...})`
override, `upper=False` leaves the rest pose; bodies other than upright
bipeds are untouched unless asked.

**The axial chain is a lag ladder** (0.30.0, completed in 0.32.0). The legs
drive the pelvis, the thorax chases the pelvis, and what the chain carries at
its top chases the thorax - each rung reading the same drive a little later
rather than mirroring the rung below it, by the lag `upper.response` (a driven
damped oscillator) gives at that clip's stride frequency. No sign is written
down anywhere: half a cycle of lag IS anti-phase, and it falls out as the fast
limit. The segment frequencies are measured, not set - `mass.pendulum` on the
mass model, through `upper.limb_frequencies` and `upper.head_frequency`
(whose caveat is in its docstring: what sits on top of an upright chain is
above its pivot, so its number is a gravitational time scale rather than a
resonance). `trunk_hz`, `trunk_damping`, `arm_lag`, `hand_lag`, `head_lag` and
`limb_damping` override; `head_lag=0.0` is the locked top that predates
0.32.0. Every gait clip reports what it resolved to (`head_hz`,
`head_lag_deg`, `trunk_lag_deg`) and, measured off the BAKED clip rather than
off the prediction, what came out: `pelvis_thorax_phase_deg` and
`thorax_head_phase_deg` (`upper.relative_phase`). Both should MOVE with speed -
a rung that reads the same number at every speed is a rung that is not really
there.

**Gait styles** say how a body walks at a speed: `duty`, `stride_scale`,
`lift_scale`, `bounce_scale`, `sway`, `min_knee` (and `extension`) on
`plan`/`cycle`, gathered with `upper`, `posture`, `stance_width` and
`max_drop` into `locomotion.GAIT_STYLES` - `elderly_shuffle`, `heavy`,
`child`, `brisk`, `relaxed`. `cycle(style="heavy")`,
`idle(style=...)`, `move_set(options={"Walk": {"style": "child"}})`; a style
has "walk", "run" and "idle" sections, and any explicit argument beats it.

**A clip lasts one natural stride** (since 0.24.0): `cycle` keys `round(period x fps)` frames,
between 16 (12 running) and the old fixed 32 (24), so played at its own rate it moves at its
natural speed. The fixed 32 frames had every adult walk 0.7 of its natural speed (StudyMan 0.82
against 1.15 m/s). **An upright biped's walk vaults** (`cycle(vault=None)`): each frame the hips
drop only as far as the stance legs need to reach their contacts, eased so they rise and fall
smoothly - highest as a foot passes under them, lowest in double support - where the plan
used to drop them by one amount for the whole cycle and every stance knee stayed bent about
30 degrees. The toe's stance line for such a walk is centred at least `BIPED_WALK_CENTRE` (0.6)
of the way back from the standing toe towards under the hip, because a person lands on the heel
ahead and leaves on the toe behind. Each report gives `stance_knee_flex_deg` per leg (half-way
through stance; a walk 5-15, a run 35-50) and `vault`, and both reach `.moves.json` `gaits`.
A vaulting walk reads 11.5 there on every MPFB body: that is `Reach`'s straight-leg cap
(extension 0.995), not a free measurement. A style keeps its character under the vault:
`bounce_scale` scales the vault's rise and fall (under 1 the hips stay near their lowest, so the
knees stay softer; over 1 they sink further in double support), and `vault` is a style key -
`elderly_shuffle` and `heavy` set it False, so a shuffle keeps soft knees (about 25 degrees at
mid-stance) and a heavy body sinks into each stance leg (about 35).

**Hands hang relaxed in every clip** of an upright body (`keyposes.hand_digits`): the fingers
curl towards the palm most at the knuckle and least at the tip (22, 20, 12 degrees; a tip-heavy
curl reads as a claw), each finger further from the thumb a tenth more than the last, and close
together in the palm's plane; the thumb does not oppose but swings in beside the index finger's
middle joint. All from the skeleton's shape - the arm's end bone is the hand, its paths to leaves
the digits, the one pointing furthest from the rest the thumb, the finger whose root is nearest
it the index, the palm side where the thumb and the fingers' own rest bend lie. It is the
body's ground rest (like folded wings), so "frame one is rest" still holds. A gait's fingers
trail the arm swing a little (`upper.HAND_LAG`, `HAND_SWING`); `Key.hands` scales the curl per arm.
An idle's chest lifts 1.5 degrees with each breath (`actions.BREATH_CHEST_DEG`).

**Turning on the spot** (`actions.turn`, roles `TurnL` / `TurnR`, asked for by name in
`move_set(roles=...)`): 90 degrees about the inside foot's ball while the outside foot is lifted
and carried round, the turn only while it is off the floor. The floor-skid check follows both
contacts through every frame. A turn takes the Idle's stance, posture and style unless given its
own. It is not a loop and ends turned: the report's `turn` = `{yaw_deg, pivot_leg, pivot_m,
end_offset_m, floor_skid_m, skid_tolerance_m}` goes into `.moves.json` `turns`, for the engine to apply to the character when
the clip ends. MovesController does not play turns yet.

See `animate-anything`'s `references/contact-locomotion.md`.

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
export.bake_for_game("MyMesh", res["rig"])      # shape keys + modifiers baked, 4 bones a vertex
m = export.export("MyMesh", res["rig"], r"C:/proj/assets/thing.glb",
                  foot_bones=["Foot.L", "Foot.R"],
                  actions=["Idle", "Walk", "Run", "Jump"],
                  loop_clips=["Idle", "Walk", "Run"],   # Jump is a one-shot
                  gaits=["Walk", "Run"],                # these must move their feet
                  forward="-Y")
print(export.summarize(m))
```

**Every clip is played back and re-checked before it ships** (`verify.recheck`):
bone floor (bones that carry skin), skin through the floor, loop seam, stance
contacts that skate (drift sideways or vertically, move unevenly, or disagree on
speed), balance for a clip that stands still, and rotation modes. Authoring checks
see the clip once, as generated; a hunch or an arm swing keyed over it afterwards is
only ever measured here. A failing clip **blocks the export** - `skip_bad_clips=True`
drops it, `force=True` ships it and lists it under `forced_clips`. Tolerances are the
authoring ones (`verify.PLANT_TOL`, `SLIP_TOL`, `SKIN_TOL`), not looser.
`verify.limb_clearance` (or `clearance=True`) measures how close hands come to the
body, from the body map rather than bone names.

**Arm clearance measures the skin, not the clothes.** How far the arms hang out
(`upper`) and `limb_clearance` read only `verify.clearance_meshes(rig)`: every mesh
bound to the rig except wardrobe garments (`wardrobe_cut` or `wardrobe` property) and
follow-through cloth and volumes (`follow_through` routed to `soft_body` or
`shape_matching`). 8 mm of sports top at Belle's armpits had sent the arms of a clip
authored after dressing up over her head; on the sample Figure a bound, eased shirt
moved the hanging gap from -8.9 to -13.3 mm and the walk's arms from 4.2 to 6.3 degrees
out. A fleshed body is still skin. Every other check still reads every bound mesh.

A clip named in `gaits` whose stride is ~0 fails: the legs are not moving. That is
what a quaternion-keyed clip on an Euler rig (MPFB's) looks like - every other number
reads the rest pose and passes. Authoring now leaves keyed bones in the mode their
keys use (`verify.adopt_rotation_modes`), and `preflight(..., actions=)` and
`check_clip` refuse a mismatch (`verify.rotation_mode_mismatches`).

`preflight` also refuses shape keys with a value (they ship as morph targets, not as
the body's shape) and warns about Mask modifiers and vertices pulled by more than 4
bones. `bake_for_game` fixes all three: it bakes shape keys and every modifier but
Armature into one mesh at rest, drops groups that are not deform bones, keeps the 4
heaviest influences and normalises. `export_glb` sets `export_morph` from whether
shape keys remain.

The file carries object custom properties as node extras, and only the active scene's
selected objects. That is how `follow-through` rides along: its **flesh** library adds jiggle
bones and weights to a rig (breasts, bellies, a bloater's torso) and writes its spec on the
mesh before this export, and Godot springs them after the walk plays. Without extras the
spec was dropped; without `use_active_scene`, a body exported after work in another scene
carried eleven meshes selected there.

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
waive it - `force` waives preflight and failing checks, where the caller can see
the problem and judge it, while an unmeasurable clip means the deliverable itself
is missing. Drop one deliberately with `skip_bad_clips=True`, which reports what
it dropped.

**Export does not need the session that authored the moves.** Every set function -
`actions.move_set`, `hop.move_set` / `jump_set`, `radial_moves.move_set`, `flight.flight_set`,
`swim.swim_set`, `maw.maw_set`, `octopus.octopus_set` - stores each role's report on its
action as a JSON string (`action["rig_anything_report"]`, via `rig_analysis.stored`), and the
action is saved with the .blend. Pass `None` for the reports and the manifest or exporter
reads them back for that rig:

```python
# a later session, the .blend reopened - no `res` in hand
hop.export_creature("MyRabbit", "MyRabbit_rig", None, path_glb, "rabbit")
rm.export_creature("MyJelly", "MyJelly_rig", None, path_glb, "jellyfish")   # and the mass move_set was given
m = locomotion.engine_manifest(rig)                   # gaits + contacts from actions.move_set's reports
m = flight.engine_manifest(rig_name=rig)              # flight and swim take the rig by keyword
m = maw.engine_manifest(None, rig)
```

`stored.load(rig)` returns `{role: report}` in authoring order; a role authored again
replaces the older copy. A role that errored has no action, so its report is kept on the rig
object (`rig["rig_anything_failed"]`): a manifest built later still lists it under `problems`
and the export refuses, just as it would have in the authoring session, until the role is
authored again successfully. The stored text is unrounded - a manifest from
stored reports is the same file as one from the originals (the `rabbit` fixture checks this
in a second Blender) - and it does not reach the glb.

**A biped or quadruped: `export.export_character` writes the `.moves.json`.** `export.export`
writes only the glb and a `.rig.json`. Hoppers and radial bodies have `export_creature`.
`export_character` runs `export`, then `locomotion.engine_manifest` for the gaits, and writes
`<glb base>.moves.json` beside the glb:

```python
r = export.export_character("MyMesh", rig, r"C:/proj/assets/humans/ann/ann.glb", name="Ann",
                            reports=res,              # move_set's; None reads the stored ones
                            extra={"style": "brisk", "note": "built by ..."})
```

- **What it writes.** `creature` (the glb's base name unless given), `name`, `rig`, `scene`,
  `clips` and `loops` (by role), `implied_speed_mps` (by role), `height_m` (`stand` is the mesh
  top, plus `crouch` and `crouch_walk` when those roles are exported), `gaits`, `contacts`,
  `verified`, `clip_checks`, `arm_pose` (per clip with arms, per arm: `hand_rise`,
  `elbow_flex_deg`, `upper_arm_deg`, `arm_carry_deg`, `arm_swing_deg` - shipped so the motion
  critic's keep-or-revert rule can compare a rebuild against the previous version after the build
  log is gone), `forced_clips`, `known_failures` (each role's authoring failures),
  `collider`, `turns` when a turn was exported (`{role: {yaw_deg, pivot_leg, pivot_m,
  end_offset_m}}`), and `dropped_clips` if any. `extra` is merged in last, so a project's own fields
  (`style`, `posture`, `stance_width`, `upper_body`, `note`) go there and can replace any of
  these.
- **Defaults, all from the reports and the rig, never from bone names.**
  - `roles`: every report. One of them must be `Idle`.
  - `loops`: roles whose report measured a `loop_seam`, so Crouch and Jump are left out.
  - `gaits`: roles with a `natural_speed_mps`, i.e. the `cycle` reports.
  - `foot_bones`: each leg's end bone from `bodymap.build(rig)["roles"]["limbs"]`.
  - `scene`: the glb's `res://` path in the Godot project folder that holds it.
- **Refusals.** It refuses, writing no manifest, when a role errored, when there is no Idle
  (MovesController starts on it), when the export refuses, or when no collider can be
  measured. A clip dropped by `skip_bad_clips` is left out of `clips` and `loops` too.

On grungist-creek's Hugo it writes the same manifest as `build_human.py`'s hand-assembled one.
Only `scene` differs (a path), plus the added `contacts` and the project's own fields. The
`mpfb_woman_curvy`, `rigify_human`, `quadruped` and `flesh_figure` fixtures export through it,
so `regress.py --godot` plays them in `verify_moves.gd`.

**Every export writes a review sheet** (improvements 04 b), because clips that pass every
numeric check can still look wrong: Walter's arms reached forward with near-straight elbows and
Tomas' run hand rose to his neck while floor, slide, balance and clearance all passed. `export.export`
(so `export_character`, `hop.export_creature` and `radial_moves.export_creature` too) renders, after
the glb is written and verified:

```
<glb folder>/review/.gdignore                  # Godot does not import the pngs
<glb folder>/review/<glb name>/<clip>_<view>.png   # 8 evenly spaced frames side by side
<glb folder>/review/<glb name>/contact.png     # every strip at half size: a row per clip, a column per view
<glb folder>/review/<glb name>/review.json     # frames, scale, cell sizes, per-strip measures
```

- **Views** `front`, `right` (Blender's Right view: from +X, so a body facing -Y shows its left
  side and faces left in the image) and `three_quarter`, turned to the export's `forward`. A flat
  body (under 0.35 of its length tall: the sea star, the cricket) gets `three_quarter_above` instead, from 40
  degrees up - level, it is a line. Workbench, flat grey body, the
  floor as an orange line with a band below it (a foot through the floor shows), the clip and frame
  numbers written above.
- **One scale.** `frame_height_m` is 2.1 m for an upright body (taller than twice its depth), so every
  person lines up at the feet and a child renders smaller than a man; anything else takes the smallest
  of `review.CREATURE_FRAMES_M` holding 1.15 times its size (the dog fixture 1.5 m). Cells are 320 px
  tall; loops leave out their repeated last frame.
- **Fast.** One render per strip: the 8 frozen poses stand side by side along the camera's right
  axis. Measured in the fixtures (two Blenders at once on a shared machine): about 4 s for a 1-clip
  body (most of it the first render), 5-7 s for 2-3 clips, 8-10 s for 5-6 clips, 15.6 s for the
  Rigify figure's 10 clips.
- **Several meshes** (`review.sheet`, and the pipeline's dressed character): the first is grey,
  every further one (garments, hair) blue, green, then purple.
- **Measured.** Per strip, `cells_with_body` (cells where a body was drawn), `distinct_cells` (cells
  showing different poses: one pose rendered 8 times is 1; compared on an undithered render with a
  tolerance of 12 pixels differing by more than 10/255, so a sub-pixel breath can merge frames) and
  `edge_cells` (cells whose body touches any edge of the strip - a side, so it spills into its
  neighbour, or the bottom or top, so the frame cut it off).
- **The frame holds every pose, up and down too.** The cell is the rest body's frame, and a pose
  leaves it in every direction: the rabbit's and the cricket's `JumpAir` legs go through the floor, a
  launch rises above the standing head. The bands above and below the cell are grown from the
  evaluated poses (`bands_px` [label, above, below] in `review.json` and the manifest), in whole
  pixels at the same metres-per-pixel, so the shared scale, the cell and the floor line stay put and
  only the picture gets taller - rabbit 13 -> 46 px of ground (strips 378 -> 411 px tall), cricket
  13 -> 58 (378 -> 423), and a sheet of the `review_sheet` fixture's `Dip` clip 13 -> 57 below and
  0 -> 81 above. A band stops at 2 cell heights (`review.GROW_MAX`), so a clip whose root runs away
  cannot render a picture thousands of pixels tall; past the cap the pose really is out of the
  picture and `edge_cells` says so. With a fixed 4% ground band those legs were cut off at image row
  0 while `edge_cells`, which then looked only at the side columns, reported 0: the sheet cropped the
  evidence and called itself clean.
- **Poses stay in their cells.** Every clip is evaluated before rendering. A strip whose poses would
  reach out of the rest body's cell (the cricket's JumpLaunch stretches and rises out of it) is drawn
  with each frame's extent centred in its cell - `centred` in the strip, `(each frame centred)` in its
  heading - and the cells widen to the widest centred pose. How far a body travelled between frames is
  then not shown; each pose is. `review_options={"centre_poses": False}` draws poses where they stand. The manifest's `review` holds these and the
  folder; a sheet that failed is `review.error` (and a `problems` line from `export_character`), never
  a refused export - the glb is already verified.
- `review=False` turns it off; `review_options` go to `review.sheet` (`frame_height_m`, `views`,
  `frames`, `cell_px`, `title`, `centre_poses`). `review.sheet(meshes, rig, actions, out_dir, ...)` renders any
  meshes on a rig - several, e.g. a body with its garments - without exporting.

**A close-up look set of a person** (`closeups.look_set`, improvements 06 rank 1): lit EEVEE close-ups of
the face (front and three-quarter), eyes, the head from the side and behind, each hand's palm and back,
the bust, the crotch, the knees, both feet and each foot's inner and outer side, at 0.4-1 m, plus a
0.42 m under-bust view on request (`under_bust=True`). One frame of one clip is frozen (`action`, `frame`,
default the first) and every camera is aimed from that posed frame's bones - the head's facing, the
knuckle line and the hand's length, the shoulders, the hip and knee joints, the foot and toe bones; the eyes
from the sclera faces - with the lens chosen so the part fills the tile at the stated distance (the view
math of lookdev's Godot `close_shot.gd`). Each `<view>.png` carries a label band (view, distance, width of
the tile in metres, clip and frame); `sheet.png` has them all at half size, `close.json` the numbers. A tile
fails (`failed`, the pipeline's review stage raises) when the figure covers under 5% of it (`empty`), when the
centroid of the view's own points projects more than 0.3 of the tile from its centre (`off_centre`), when any
one of them - the wrist, each knuckle and fingertip; both eyes; each foot's heel, ankle and toe - is within
0.04 of the tile's edge or outside it (`cut`; `subject_margin` is the worst point's free value), or when no
figure is drawn at the centroid (`off_body`, body views). `hand_back` looks from the front and the hand's outer
side, a little below the knuckles (the curled fingertips show their nails), and draws nothing further than
the hand (the thigh). `aim_override={view: bone | (dx, dy, dz)}` is the control: a camera aimed from the wrong
bone fails, and so does a palm camera moved 3 cm up the arm (`cut`: the fingertips at the edge). About 3-4 s
for the full set of a person, 0.6-0.8 s for three tiles.

```python
from rig_analysis import closeups, review
r = closeups.look_set(review.bound_meshes("Walter_rig", first="Walter_body"), "Walter_rig",
                      "C:/.../review/walter/close", action="Walter_Idle", under_bust=True)
```

**In Godot, drive it with `MovesController`.** Copy
`${CLAUDE_PLUGIN_ROOT}/godot/addons/rig_anything` to `<project>/addons/` once. It is a
`CharacterBody3D` (`class_name MovesController`) that reads any `.moves.json`: set
`manifest_path` before adding it, and `input_source` -> `{dir, run}`:

```gdscript
var body := MovesController.new()
body.manifest_path = "res://assets/thing.moves.json"
body.input_source = func(_b): return {"dir": Vector3.FORWARD, "run": false}
add_child(body)
```

Only `scene` and `clips` are required. The gait ladder is whichever of Walk, Trot, Run
(Amble, Canter, Gallop...) and `gaits` roles have a speed, slowest first, each at
`gaits.<role>.natural_speed_mps` (else `implied_speed_mps` x `implied_pace`). Gaits change
at the geometric mean of neighbouring speeds +-8%, carry the stride phase across, and play
at speed / implied speed, so the feet do not skate. The collider is a capsule from an
optional `collider: {radius, height}` block, else `height_m.stand`; write it with
`export.collider(mesh, rig)` or `engine_manifest(..., mesh_name=mesh)["collider"]` - the
trunk and thighs' horizontal reach from the origin (98th percentile), arms left out, and
the mesh's top. For more moves, extend it:
override `_setup()` (after model, ladder and collider exist), `_physics_process`, and
`_build_collider` / `_set_height` for another shape, and call `play_gait_for(speed)`,
`play_role`, `add_hold`. Check a manifest headless:

```bash
godot --headless --path <project> -s res://addons/rig_anything/verify_moves.gd -- dir=res://assets/humans
```

It drives 0 -> walk -> each change-up -> run -> back down -> 0 and checks role, rate,
hysteresis and phase at every step (`MOVES VERIFY PASSED`).

**8. Wings: fold, flap, glide.** Any free limb whose skin is a sheet is a wing
(see `animate-anything`'s `references/wings.md`):

```python
from rig_analysis import flight, keyposes as kp, motion
bm = bodymap.build(rig)
print(bodymap.summary(bm))                  # WING upperarm.L membrane, by skin sheet ...
P = kp.Poser(motion.Body(bpy.data.objects[rig], bm))
print(flight.summarize_plan(flight.plan(P)))
res = flight.flight_set(rig)                # Glide Flap WingSpread TakeOff Dive Land
m = flight.engine_manifest(res)             # the .moves.json `flight` block
```

Wingbeat, stroke, cruise, glide and stall speeds come from measured wing area,
span and skinned mass (Pennycuick, Nudds, Taylor). Ground actions carry wings
folded without being asked. Pass `mass_kg` - the default density is a guess.

**9. Maws: find the mouth, add a jaw, open it.** A head arrives as one bone; the
mouth is in the skin (see `animate-anything`'s `references/maws.md`):

```python
from rig_analysis import maw
d = maw.detect(rig, kind="reptile")   # or crocodilian, mammal, rorqual, anglerfish - from the renders
print(maw.summarize_detection(d))     # mouth length, corner, hinge, teeth, tongue, fused lips
maw.build(rig, detection=d)           # jaw, throat, gular, tongue chain, mouth socket (non-deforming)
print(maw.skin(rig))                  # weights split along the lips, relaxed for stretch; gape limit
res = maw.maw_set(rig)                # Gape Bite Roar Breath* Swallow, or Engulf Purge for a rorqual
m = maw.engine_manifest(res, rig)     # the .moves.json `maw` block
```

Bind the body before joining loose teeth, baleen or a tongue - bone heat refuses
a mesh in pieces - and let `maw.skin` weight them. `gape = 1` is the kind's
maximum or the widest the skin takes without folding, whichever is smaller.
Maw clips move only `layer_bones`, so an engine plays them over locomotion.
Existing clips are unchanged: a key that says nothing about the maw keeps it shut.

**10. Fins and swimming.** A fish arrives as a mesh; its fins are the skin that is a
sheet (see `animate-anything`'s `references/fins-and-swimming.md`):

```python
from rig_analysis import fins, swim
d = fins.detect("MyFish")                  # caudal, dorsal, anal, pectoral, pelvic - or flukes
print(fins.summary(d))
fins.build_fish("MyFish", detection=d)     # no rig yet: head, spine, a fan of rays per fin
print(fins.bind("MyFish", "MyFish_rig"))   # or fins.build_rays + fins.skin on an existing rig
swim.measure_fin_limits("MyFish_rig")      # clean fold, C-bend and brake, from the skin
res = swim.swim_set("MyFish_rig", mode="carangiform")   # Swim Sprint Glide Hover TurnL/R Escape Brake
m = swim.engine_manifest(res)              # the .moves.json `swim` block
```

Speeds and tail beats come from length (stride 0.7 L, Strouhal 0.29); flukes make
the wave vertical. Export a swimmer with `foot_bones=[]` and a floor far below it.

**11. Radial bodies: no front, no back.** Step 2's report says `BODY PLAN RADIAL`
when the body turns onto itself about an axis - a jellyfish, a sea star, a brittle
star, an anemone. Do not pick a forward for it; there is none (see
`animate-anything`'s `references/radial-bodies.md`):

```python
from rig_analysis import radial, radial_moves as rm
print(measure.rotational_symmetry(obj))   # order: 4 a jellyfish, 5 a star, continuous a bare bell
d = radial.detect("MyJelly")              # kind= medusa | polyp | asteroid | ophiuroid, from the renders
print(radial.summary(d))                  # hub, every appendage with its angle, root and direction
radial.build("MyJelly", detection=d)      # hub, bell ribs, a chain per tentacle / oral arm / arm
                                          #   bones per kind: median length / 1.2 widths, every arm alike
print(radial.skin("MyJelly_rig"))         # weights from the parts, no bone heat - coverage read back
res = rm.move_set("MyJelly_rig")          # Pulse Drift Turn | Crawl Idle | Row RowBack Idle | Sway Retract Extend
rm.export_creature("MyJelly", "MyJelly_rig", res, path_glb, "jellyfish")   # glb + .moves.json `radial` block
```

A bell's pulse rate, contraction and distance a pulse come from its diameter and
fineness; a sea star crawls at 1 mm/s any way it likes; a brittle star rows behind
whichever arm is nearest. Loose tentacles are welcome - they are rigged where
they lie. `radial_samples.build_all()` makes the four test bodies.

**12. Hoppers: legs that fold as a Z.** A cricket's swollen hind femur with its tibia
folded under it, a rabbit sitting on a foot as long as its shin - `decompose` sees
neither (see `animate-anything`'s `references/hoppers.md`):

```python
from rig_analysis import hoppers, hop
d = hoppers.detect("MyRabbit")            # kind= orthopteran | leporid, from the renders if the guess is wrong
print(hoppers.summary(d))                 # every leg's segments by role, rest angles, joints inferred
hoppers.build("MyRabbit", detection=d)    # spine rooted at the pelvis, a bone per segment: hind_femur.L > hind_tibia.L > ...
print(hoppers.skin("MyRabbit_rig"))       # weights from the parts; warns on skin fused shut
res = hop.move_set("MyRabbit_rig")        # Idle Hop Bound JumpLaunch JumpAir JumpLand | Idle Walk JumpLaunch JumpAir JumpLand
hop.export_creature("MyRabbit", "MyRabbit_rig", res, path_glb, "rabbit")   # glb + .moves.json `hop` block
```

Legs are walked up the skin from each ground contact; joints are the corners of
that walk's centreline, and joints the skin hides - a rabbit's knee in its haunch -
are placed from published proportions and reported as inferred. Hind stance runs
on a rabbit's measured ankle angles through a femur-parallel-to-metatarsus leg; a
jump is a launch, an engine-owned ballistic flight, and a landing, with the body
offsets the engine applies between them. `hopper_samples.build_all()` makes the test
cricket and rabbit, and `hoppers.score` measures a detection against their joints.

### Bone roles

Anything that needs to know which bone is the pelvis, the chest or a foot reads it from the body
map rather than from names, so a fix made for one rig reaches every consumer:

```python
r = bodymap.build(rig)["roles"]      # skin read from the meshes bound to the rig, or meshes=[...]
r["root"]        # a motion bone that moves no skin (MPFB's root on the floor), else None
r["pelvis"], r["chest"], r["neck"], r["head"], r["tail"]
r["butt_anchor"], r["breast_anchor"]              # pelvis and chest
r["limbs"]["foot.L"]    # {"role", "girdle", "upper", "lower", "end", "digits"}; "front_foot.L" on four legs
r["controls"]    # no skin and on no limb chain: the root, Rigify's heel helpers, IK and pole bones
r["unskinned"], r["skinned"], r["warnings"]       # skinned: whether any skin was read at all
```

Roles come from structure (where the legs attach, where the arms attach, which end of the axial
chain is the head), with names only as tie-breakers: a Rigify body renamed to `mixamorig:` gets
the same roles (the `mixamo_names` fixture). `chest` on a quadruped is where the front legs attach.
With no mesh bound, `root` falls back to "lies wholly below the ankles" and says so in `warnings`.
Bones another plugin hangs on a finished rig (tagged `ft_role` / `wd_role`, or named `ft_jiggle_*`
/ `wd_*`) are in no role and on no chain; the map lists them in `added_bones`.

**Profiles.** `scripts/rig_analysis/profiles/*.json` hold what is known ahead of time about a body
source: `mpfb_game_engine` (humanform's renamed MPFB rig), `rigify_basic_human` and
`rigify_basic_quadruped` (the metarigs `fit` fits), `rig_anything_generic` (`build_from_parts`) and
`rig_anything_hopper` (`hoppers.build`). Each has `detect` (`bones_all` / `bones_any` / `bones_none`
/ `vertex_groups_any`, shell patterns), the `roles` its bones always play, the `rotation_mode` its
bones come in with (authoring may change it), measured `rest` facts and a `bake` block
(`shape_keys`, `mask_modifiers`, `strip_groups`, `max_influences`). The builders tag the rig
(`rig["body_profile"]`, which also reaches Godot as a node extra); `bodymap.load_profile(rig)` takes
the tag while the rig's bones still match it, else the first profile whose `detect` does, and
`roles["profile"]` names it. A claim fills a role the shape left empty or only guessed (neither
Rigify's nor MPFB's head bone is called head); a claim the shape contradicts is not applied, and
`warnings` names both. `export.preflight` and `bake_for_game` read the `bake` block; with no profile
they behave as before.

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

**A speed is only as honest as its duty factor.** The exporter used to call a
clip's speed 2 x foot travel / cycle, which assumes each foot is down exactly
half the time. A gallop's feet are down a third of it and swing past their
touchdown point; that formula read it 21% slow and the walk 30% fast.
`check_clip` now measures the median backward speed of planted feet and says
which it used in `speed_source`.

**A wing is not an arm, and its skin is not body.** Left as an arm, a
dragon's wing would counter-swing through every walk. Counted as body, a
modelled wing sheet - centimetres thick - weighed a 1.9 m test bird at 22 kg,
and its span loosened every tolerance scaled by size; `bodymap` and the exporter
size a creature without its wings as they do without its tail.

**A mouth is measured on the skin, and the skin sets the gape.** A test whale's
jaw folded 21 faces at a rorqual's 80 degrees and none at 47, so its clips open
to 47 and say so. Fused lips, loose parts and bone heat's weights bleeding in from
the chest are all reported or repaired by `maw`, never skinned over.

**A fin's edge is not body.** Its rim vertices have normals in the sheet, and an
inward ray along one runs the fin's length: the test fish's spine ran into its tail
fin and its fin edges folded. `fins.detect` grows fins across their rims, takes the
body as the largest connected non-fin skin, and a fin's base as where it touches
that.

**A radial body has no forward - do not give it one.** A mirror test scores a
starfish's two horizontal axes alike, and any front chosen from that is
arbitrary, so every fitter downstream inherits a coin toss. `rotational_symmetry`
measures what such a body does have: an axis it turns onto itself about. Centre
that axis on the skin's area-weighted centroid - a bounding box is centred on an
even order only, and a five-armed star scored no symmetry at all about its box.

**Bone heat is the wrong tool for a bell and a loose tentacle.** A bell is a
thin shell and a modelled tentacle a separate tube; bone heat fails on the one
and skips the other. `radial.skin` writes each vertex's weights from the part it
belongs to and where along it, then reads the weights back off the mesh: `coverage`
and `vertices_unweighted` are measured, and `passed` needs every vertex held.

**Count bones per kind, not per arm.** Each arm's length over 1.2 widths, rounded,
gave a symmetric test star 3 bones on one arm (3.49) and 4 on the others (3.63-3.89):
metaball widths vary about 10%, and the count sat on a rounding edge. `radial.build`
takes the median ratio of each kind (arm, tentacle, oral arm) and gives every
appendage of that kind the same count.

**A tentacle hangs.** Parented to a rib and carried rigidly, a closing bell swung
all eight test tentacles in until they crossed under it - with every number
passing. The render found it; `radial_moves` now undoes the carried bend and
checks tip radius.

**Walk a leg from its toe, and seed the toe from high skin.** A flat contact patch
has two ends; "farthest from the body's centre" took a sitting rabbit's heel, because
its knee is over its toes. The toe is the patch vertex farthest over the skin from
anything high. And a foot on the floor that the walk never passed has a heel worth
walking from: a sitting rabbit's shin rests on its foot, and the first walk climbed
the shin from the ball.

**Root a creature at its pelvis.** Rooted at a swaying abdomen's tip, a cricket's
root bone carried sub-millimetre translation that Godot's importer reduced to a single
key, and the whole body slid under planted feet - with every Blender check passing.

**Every planted foot sweeps at the body's speed.** Shortening one leg pair's stroke
to fix its reach made its feet slower than the body; each foot followed its own line
perfectly and the clip still skated. Cut the time a short leg spends down instead.

**Decide `passed` last.** Actions add their own failures - loop seams, skating
feet, seams, wing clearance - after the shared checks have run; the verdict was
being written before them, so a clip could print PASSED over its own failure
list. `_author_samples` now sets it from the final list.

**Never measure a pose against itself.** Wing clearance was first allowed as
much as the folded ground rest had - posed by the same fold under test - so a
fold driven into the chest passed. The allowance comes from the bind pose.

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
| `axes.forward_sign` | `unknown` for a bilateral body - geometry cannot settle it, the renders can. `none` for a radial one: there is nothing to settle |
| `rotational_symmetry.order` | Largest k whose 360/k turn lands the body on itself: 4-5 jellyfish and stars, 8+ many medusae, `continuous` a body of revolution. None for every bilateral test creature (best 0.32, pass 0.6) |

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
- **Phase 6** - whole-body actions (crouch; slide and climb next): a body map
  of spine/neck/head/tail/legs/arms for any rig, pose-by-target IK, playback
  verification. Documented in the companion **`animate-anything`** skill;
  modules `bodymap`, `motion`, `actions`, plus `views.render_clip`.
- **Phase 8** - wings (0.9.0): recognised from the skin (sheet thickness and
  planform) or names, kind from structure (membrane, feathered, simple); posed
  by one fold through the avian linkage plus stroke, tilt, sweep, twist, fan and
  tuck; flight numbers from size; WingSpread, Flap, Glide, Dive, TakeOff and
  Land, checked for wing clearance, midline and swept area. Done (`wings`,
  `flight`).
- **Phase 9** - maws (0.10.0): the mouth found on the skin as a cavity, jaw,
  throat, gular pouch, tongue and a mouth socket added; weights claimed from
  bleeding bones, split along the lips by mesh labels and relaxed by
  stretch-weighted smoothing; gape limited by the skin; Gape, Bite, Roar,
  BreathStart/Breath/BreathEnd, Swallow, Engulf and Purge, checked for stretch,
  folded faces, rigid teeth, socket aim and jaw clearance. Done (`maw`).
- **Phase 10** - fins and swimming (0.11.0): fins found on the skin by sheet
  thickness, classified by base and normal, a fish rigged from a bare mesh, rays
  fanned and weighted between neighbours, fold / bend / brake limited by the
  skin; a travelling wave scaled by length for five modes including a whale's
  vertical one; Swim, Sprint, Glide, Hover, turns, a C-start and a brake, checked
  for tail sweep, a tailward wave, folds and fin clearance. Done (`fins`, `swim`).
- **Phase 11** - radial bodies (0.12.0): an axis the body turns onto itself about,
  and its order, in the identification report; hub and appendages found on the skin
  by geodesic bands - loose tentacles included - and the kind suggested (medusa,
  polyp, asteroid, ophiuroid); hub, bell ribs and appendage chains built, weights
  written without bone heat; a pulse, drift and turn from bell diameter and
  fineness, a tube-foot crawl, rowing and reverse rowing, a sway and a retraction
  limited by the skin; checked for margin closure, symmetry, contraction timing,
  tentacle lag and crossing, tips on the floor, stroke direction. Done (`radial`,
  `radial_moves`, `radial_samples`).
- **Phase 12** - hoppers (0.13.0): jumping legs found on the skin by walking up from
  each ground contact - seeded at the toe, stopped at the body's core thickness, a
  second walk from a flat foot's heel - joints at the corners of the walk's
  centreline, joints the skin hides placed from published proportions; orthopteran
  and leporid kinds; a pelvis-rooted rig weighted from the parts with fused-skin
  warnings; a rabbit's hop and half-bound on Hall et al.'s ankle profile through a
  pantograph leg, a cricket's tripod walk, and launch / air / land jumps from
  published take-off numbers, checked on playback and in Godot. Done (`hoppers`,
  `hop`, `hopper_samples`).
- **Phase 7** - contact locomotion (0.8.0): contacts measured on the skin, a
  support plane through them, Froude-scaled stride and duty factor, per-leg
  reach on the plane with toe roll, rotary gallop and spine flex, contact
  detection in any clip, and stance-foot speed in the exporter. Done
  (`locomotion`).

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
