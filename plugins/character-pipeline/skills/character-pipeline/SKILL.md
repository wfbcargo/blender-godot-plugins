---
name: character-pipeline
description: Build a whole character for Godot 4.7 from one TOML spec - a humanform body from a brief, baked, with hair, follow-through flesh, rig-anything's move set and wardrobe garments, exported as the glb, .moves.json and garment glbs. Stages check the file before they run, so doing them in the wrong order (garments before moves, flesh after garments) refuses and names the order; each stage records an input hash in the .blend, so a rebuild skips what has not changed and a fresh Blender session resumes from a saved file. Use when asked to build, rebuild or add a character, person, NPC or crowd member from a description; to write or change a character spec; to rebuild one stage of a character (its moves, its outfit); or when a build script calls humanform, rig-anything, follow-through and wardrobe in sequence by hand; to build several characters at once and time them (build_many); or when a build failed and should resume where it stopped.
---

# character-pipeline

A character is **a description, a style and an outfit** - a spec file - and one call builds it:

```python
import sys, importlib
sys.path.insert(0, r"C:/Users/<you>/.claude/skills/character-pipeline/scripts")
import character_pipeline
importlib.reload(character_pipeline)
character_pipeline.reload_all()
from character_pipeline import runner

report = runner.build(r"C:/.../project/characters/belle.toml")
```

It finds the four plugins it drives through `RA_SCRIPTS`, `HF_SCRIPTS`, `FT_SCRIPTS` and
`WD_SCRIPTS` (else the installed copies under `~/.claude/skills`).

From the command line, use the thin caller `scripts/build.py` (or the `scripts/run.sh` template, which sets
the paths and calls it):

```
blender -b --factory-startup --python-exit-code 1 --python <cp>/scripts/build.py -- spec=<spec.toml>     [from=<stage>] [to=<stage>] [force=1] [quality=draft] [fresh=1]
```

**A command-line build resumes from the spec's saved `[export] blend`.** `runner.build(spec, resume=True)`
(what `build.py`, `run.sh` and a project's own build scripts call) first opens that file when it exists and
Blender was started with no file of its own (`runner.open_saved`), so the stage records in it are used: a
`[flesh]`-only edit reruns flesh, export and review, and skips moves when the rig and the weights came out the
same (a swing limit, `limit_share`) - study_man 12.1 s against 18 s before 0.10.0 and about 40 s for the whole
build (see "The cascade stops" below). On a dressed spec (an `[outfit]`) a `[flesh]` change takes the garments
off (`stages.undress`), reruns flesh and cuts them again (Belle 24 s against 47 s, the same files as a fresh
build); a `[moves]` change there still restarts from body, since moves refuses while garments are bound
(`RESTARTS_FROM_BODY`). Without resuming every call started from an empty scene and rebuilt from body.
`fresh=1` (`resume=False`) builds from nothing. A Blender started on a .blend of your own keeps it (a
`body.source = "blend"` spec's source file).

## The spec

TOML, because Blender's Python reads it with no add-on. Belle, as the project builds her:

```toml
[character]
id = "belle"                       # file names; the manifest's creature
name = "Belle"                     # objects: Belle_rig, Belle_body

[body]                             # humanform's brief, passed through (sheet.new)
sex = "female"
age = 28
stature = 1.70
build = "curvy"
style = "realistic"
firmness = 0.3
cupsize = 1.0
measurements = { chestcircumference = 1.02, waistcircumference = 0.72, buttockcircumference = 1.07 }
skin = [0.78, 0.58, 0.47]
iris = [0.36, 0.45, 0.30]
ancestry = { caucasian = 1.0 }     # optional: MPFB's african / asian / caucasian shares, normalised
[body.parts]                       # humanform library parts
face = "face-female-11-1-49f17892"
[body.face]                        # optional: a likeness, ratios read off a frontal photo (humanform
width_to_height = 1.18             #   SKILL.md, "A likeness from a photo"); fitted by the face stage,
eye_spacing = 0.49                 #   never reused from or stored in the library. The body stage's
nose_width = 0.26                  #   report has `likeness.fit`, each measure against its target
mouth_width = 0.35
jaw_width = 0.82
lower_face = 0.56
shape = "oval"                     # an MPFB head shape, at shape_weight (default 0.5)
shape_weight = 0.3

[moves]                            # rig-anything move_set
roles = ["Idle", "Walk", "Trot", "Run", "Crouch", "CrouchWalk", "Jump"]
loops = ["Idle", "Walk", "Trot", "Run", "CrouchWalk"]
gaits = { Walk = 0.2, Trot = 1.0, Run = 2.0 }     # role -> Froude number
style = "adult"                    # locomotion.GAIT_STYLES
stance_width = 1.15
export_gaits = ["Walk", "Trot", "Run", "CrouchWalk"]
clearance_check = ["Crouch", "CrouchWalk", "Jump"]
[moves.per_gait.Run]               # anything move_set takes per role, over the style
max_drop = 0.07
upper = { lean = 9.0, arm_swing = 25.0, elbow = 85.0 }

[variability]                      # rig-anything's variability.py: what makes this body's motion its
                                   #   own. EVERY FIELD DEFAULTS TO 0, and 0 changes nothing, so a
                                   #   spec without this table builds the clips it always built
seed = 1234                        # optional; absent: derived from character.id (SHA-256), which is
                                   #   deterministic, so two builds of one spec agree and two
                                   #   characters differ
asymmetry = 0.35                   # 0..1: a FIXED left/right asymmetry, drawn once and baked into arm
                                   #   swing, step length, shoulder dip and arm lag. Identity, not
                                   #   noise. 0.35 is a real person (arm swing up to +-12%, a step
                                   #   asymmetry of a few percent); 1 is the dial's end
jitter_phase = 0.0                 # 0..1: the runtime half of L4 - per-cycle phase and amplitude
jitter_amp = 0.0                   #   jitter. Carried through to the manifest, not baked here

[muscle]                           # humanform's muscle definition, weighted by the brief's muscle and body fat
output = "geometry"                # or "normal": baked into the skin's normal map (bulk stays geometry)
strength = 1.0                     # 0..2, scales every definition group
groups = ["pectorals", "abdominals", "deltoids"]   # default: all of humanform.muscle.GROUPS
# normal_size = 2048               # output = "normal" only; default by quality

[build]
quality = "final"                  # "draft" | "preview" | "final"; runner.build(quality=) overrides it

[hair]                             # humanform's hair layer: the brief's hair = {preset, colour}
preset = "bun"                     # short_crop, bob, bun, ponytail, long_loose
colour = [0.17, 0.10, 0.06]        # screen (sRGB)
brows = true                       # optional, default false: humanform.brows' brow and lash cards and
lashes = true                      #   light body hair, in the hair colour darkened, joined with the hair
body_hair = false                  #   (a switch left false hashes as before, so no build restarts)
beard = "short"                    # optional: stubble, short, goatee, moustache (humanform.brows)
beard_colour = [0.70, 0.69, 0.68]  # optional, screen (sRGB); default the hair colour a little darker
fringe = true                      # optional: a fringe across the forehead to the brows, over any preset

[flesh]                            # follow-through; limit shares come from the type registry
types = ["breast", "butt"]
may_miss = []                      # types the stage may come back without (see below)
overrides = { belly = { frequency_hz = 4.5, damping_ratio = 0.6 } }
                                   # optional: jiggle parameters over the material's, per type in `types`
                                   #   or region (`breast.L`): frequency_hz, damping_ratio, squash,
                                   #   gravity_scale, aim, translate, response, frequency_down_ratio,
                                   #   frequency_ap_ratio, max_offset. A firm belly: soft_fat is a
                                   #   breast's tissue, and Marco's swung 4.6 cm walking on it, 1.2 at 4.5 Hz
[[flesh.zones]]                    # only while the measure reads a mass wrong (05 5.9)
type = "butt"
view = "back"
ellipse = ["G12", 1.3, 1.6]
side = "L"

[[outfit]]                         # wardrobe presets, innermost first
preset = "sports_top"
name = "SportsTop"
colour = [0.035, 0.16, 0.20]

[export]
dir = "assets/belle"               # under the project (characters/ sits in it)
res_dir = "res://assets/belle"
blend = "belle_realistic.blend"    # relative: under $BLEND_DIR, else characters/pipeline.toml's
                                   #   [blend] dir, else the project
```

**Where the .blend files live** (`characters/pipeline.toml`, optional, never hashed):

```toml
[blend]
dir = "C:/Users/me/Blends"         # relative [export] blends resolve here; relative is under the project
inside_godot = false               # true: a .blend inside the Godot project is meant to be imported
```

`$BLEND_DIR` still wins over it. A build **refuses to save a .blend inside a Godot project** (a folder with
`project.godot` above it and no `.gdignore` between) unless `inside_godot = true`: Godot imports any .blend it
finds with its Blender importer, and with no Blender path in the editor settings a headless `--import` fails
there and the glbs beside it are not imported - the demo then loads no figures (a likeness build's blends in
grungist-creek's root, 2026-09-21). The refusal names the file and the fixes.

**A stage that fails** raises `runner.StageFailed`: `[<id>] <stage> failed after <s>s: <cause> - <where the file
was left>`. The build saves the .blend after every stage that runs (`runner.CHECKPOINT`, 0.0-0.3 s a save), so
the file on disk holds the build as the last good stage left it and the next build resumes at the failed stage:
Mei's review failed on a close-up tile, the check was fixed, and the rebuild ran review alone in 7.7 s. The moves
stage's failure lists each failing clip's own failures (`TurnL: upper_arm.R: the arm swings 9 degrees ...`),
so the fix - a `[moves.per_gait.<role>]` option or `may_fail` - is chosen from the message.

**Several characters at once:** `scripts/build_many.py` (plain Python, no bpy) runs one Blender per spec,
`--jobs` at a time (default half the cores, at most 4), passes anything after `--` to every `build.py`, writes
each log to `--logs`, and prints a table - status, wall seconds, the build's own seconds and its three slowest
stages, or a failure's `StageFailed` line - ending `BUILD_MANY DONE <ok> ok, <failed> failed, <s> s wall`. Its
exit code is the number of failures. humanform's library locks its index, so the builds can share it.

```
python <cp>/scripts/build_many.py characters/a.toml characters/b.toml characters/c.toml --jobs 3 -- fresh=1
```

Three likeness NPCs built cold took 58.5 s wall together (53-58 s each); nine figures, 189 s at `--jobs 3`.

It reads every spec first and prints its refusals and warnings before building. A **warning** is a spec that
pins one of rig-anything's upper-body parameters derived from speed and a published source (`spec.SOURCED_UPPER`:
`pelvis_list`, `side_bend`, `lean_bob`, `lean_lag`, `head_hold`, `gaze_m`) in `[moves.per_gait.<role>] upper`.
Pinning is allowed - a character may be meant to move differently - but a pin left from an older default is how
Belle's head stayed held at 16% while every other body's moved to 64%. A single `build.py` logs the same lines
and puts them in the build summary's `warnings`.

**Then it looks in Godot.** When the builds are done, each that built (and reviews) is shot in Godot's look by
`scripts/review_godot.py`: the project imported once, then lookdev's `close-shot` of each character, dressed in the
garments its manifest lists, with its Blender close set's tile first in each row, into
`<export dir>/review/<id>/godot/` (`sheet.png`, `close.json`). What is judged is what ships: the likeness round's
dress bust points and beard patches were plain in Godot and hidden in Blender's close-ups (seven rebuilds). A
close-shot failure fails the run (`BUILD_MANY DONE ... godot review FAILED`). It runs after the builds, not in the
review stage, because parallel builds' Godot imports of one project would race. `--no-godot-review` skips it; no
Godot, node or lookdev skips it with a line saying so. Run it alone after a single build:

```
python <cp>/scripts/review_godot.py characters/a.toml [--presets clear_midday,overcast] [--views face,bust,full]
```

**The flesh stage says what it found.** The build log gets `flesh: found <type>: <regions>` and
`flesh: MISSED <type>: <reason with numbers>` (follow-through's `missed`), the stage report `found`
and `missed`, and the manifest a `flesh` block - `types`, per region `name, type, bone, parent,
peak_m, max_offset_m, material, frequency_hz, damping_ratio`, and `missed` `[{type, reason,
allowed}]`. A type in `types` that finds no mass fails the stage, naming why, unless `may_miss`
lists it. A region outside its type's anatomical zone, or with weight on the face, fails the stage
too (`flesh: MISPLACED ...`, follow-through's `check_placement`; the stage report's `placement` has
each region's heights and `head_share`); nothing lets it through. Keep the limit at or under `peak_m`: a larger one fails `verify_flesh.gd`'s `within_body`
(a figure study's belly at the material's 1.2 x peak_m swung 0.198 m off a 0.165 m stand-out on the
Jump clip).

`spec.load(path)` checks it and names the field it rejects. `spec.GAPS` lists what a spec may carry
that no plugin owns yet. Tuned numbers live with their owners, and a spec only names them:
- gait styles in rig-anything
- flesh limit shares in follow-through's registry
- garment ease, bands and cover in wardrobe's presets

## Stages

| Stage | Needs | Checks in the file before it runs |
|---|---|---|
| `body` | - | a `blend` source's object is in the open file |
| `muscle` | body | only with `[muscle]` (a `brief` body): the rig and the **unbaked** humanform mesh exist, no definition on it yet. Runs `humanform.muscle.define` (`hfd:muscle` at 1 for geometry, at 0 plus a `<name>_muscle_high` copy for a normal map; `hfd:muscle-bulk` always at 1) |
| `bake` | body, muscle | the rig and the humanform mesh exist. With `output = "normal"` it bakes the high copy into the skin's normal map (lookdev `detail.bake_normal_from_high`, matched), packs the image and removes the copy; the glb carries it as the skin's `normalTexture` |
| `hair` | bake | baked; no garment bound; **no hair in the file already**. Runs humanform's `hair.add` and joins the hair into the body; a strand part the strand stage will chain stays its own object (its follow-through contract checked either way) |
| `flesh` | bake, hair | baked; no garment bound - cut first, a garment carries no jiggle weights |
| `moves` | bake, hair, flesh | baked; no garment bound - rig-anything measures arm hang against every mesh on the rig |
| `strand` | hair, moves | only where the hair preset grows a strand that is a line (`ponytail`): a strand mesh is in the file and the move set is stored. Runs follow-through's `strand.prepare` |
| `garments` | moves, flesh, strand | every role has a stored clip; jiggle bones present if the spec has flesh |
| `export` | moves, garments, strand | every role has a stored clip; an outfit is bound if the spec has one; every strand mesh has its chain |
| `review` | export | the glb and every role's clip exist; the close-up set's bones (head, neck, shoulders, hands and fingers, thighs, shins, feet, toes) are found at run time |

**`review`** writes rig-anything's review sheet of the character as the game shows it - the body with
its hair and every garment bound to the rig, garments in their own colours - to `<export dir>/review/<id>/`: `<clip>_<view>.png`
strips of 8 frames from the front, right and three-quarter views, `contact.png` and `review.json`, with
a `.gdignore` in `review/`. A person is framed 2.1 m tall like everyone else. The export stage passes
`review=False` to rig-anything, so the sheet is rendered once, dressed. It raises if a strip has a cell
with no body, or a cell whose body reaches an edge of the picture (`edge_cells`): sideways the pose
would sit in the next frame's cell, and at the bottom or the top the frame has cut it off, which is
exactly what the sheet exists to show. It is on unless the spec says so, and its hash covers only
`[review]`:

```toml
[review]                           # optional
enabled = true                     # false: no review stage
frame_height_m = 2.1               # default: 2.1 m upright, a size rung for a creature
close = true                       # false: no close-up look set
```

**The close-up look set** (06 rank 1). After the sheet, the review stage writes rig-anything's
`closeups.look_set` of the dressed character to `<export dir>/review/<id>/close/`: lit EEVEE close-ups, one
`<view>.png` each with a label band (view, distance, the tile's width in metres, clip and frame), `sheet.png`
(all of them at half size) and `close.json`. The pose is the **Idle clip's first frame** (else the first
role's), frozen, and every camera is aimed from that posed frame's bones - never height fractions. The stage
raises if a tile shows no body (`empty`, figure under 5% of the tile), if the view's own points project off
the tile's centre (`off_centre`, beyond 0.3 of the tile), if any one of them - the wrist, each knuckle and
fingertip; both eyes; each foot's heel, ankle and toe - is cut by or near the tile's edge (`cut`, within 0.04),
or if no figure is drawn where they project (`off_body`). The quality picks the views (`quality.py` `close`, in
the review hash at every quality unless `close = false`):

| view | distance | final | preview | draft |
|---|---|---|---|---|
| `face`, `eyes` | 0.6, 0.4 m | yes | yes | face |
| `face_3q`, `head_side`, `head_back` | 0.6, 1.0, 1.0 m | yes | | |
| `hand_palm.L/.R`, `hand_back.L/.R` | 0.5 m | yes | yes | the left hand |
| `bust`, `crotch`, `knees` | 0.8 m | yes | | |
| `feet`, `foot_inner.L/.R`, `foot_outer.L/.R` | 1.0, 0.6, 0.6 m | yes | | |
| `under_bust` | 0.42 m | a spec wearing a top (a shirt or dress cut) | | |

It adds about 2.8 s to a final review (study_man: review 4.1-4.8 s without it, 6.8-7.6 s with 15 tiles; the right
foot's two side views since 0.9.1 add about 0.3 s) and 0.6-0.8 s to a draft one (3 tiles). The pictures show the file's
Blender materials; judge the Godot look with lookdev's `close-shot`. `[review] close = false` renders no set, removes
a `close/` folder an earlier build wrote (the report names it, `close_removed`) and leaves the close part out of
review's hash.

**Answering the look checklist from the set.** The look questions critics ask are humanform's
`references/critic-checklist.md` (L4 parts, L6 hair, L5-L6 surface) plus the realism list in
`docs/improvements/NEXT.md`. Each is answered from these tiles, with no script:

| question | tiles |
|---|---|
| Nose, lips, eye sockets and brow readable; eyes at about half the head's height; ears between brow and nose base | `face`, `face_3q`, `head_side` |
| Face free of mirror-perfect symmetry; forehead and lips not glossy | `face`, `eyes` |
| Brows and lashes read; iris and sclera look like eyes | `eyes` |
| Hairline reads as hair, not a cap edge; follows the forehead, temples, round the ear, down to the nape | `face_3q`, `head_side`, `head_back` |
| At 1 m, hair reads as hair on a head, not a helmet | `head_side`, `head_back` (1.0 m) |
| Bun, tie or tail attached, clear of ears, neck and shoulders, shaped like what it is; no seam at the cap | `head_back`, `head_side` |
| Four fingers and a thumb, separate, with knuckles; nails on the thumb, index and middle finger (`hand_back`, from the front a little below the knuckles; ring and pinky nails are behind them); no orange web creases; hand about the face's length (compare the widths in the labels) | `hand_back.L/.R`, `hand_palm.L/.R` |
| Deltoid cap at the shoulder; clavicles and sternum notch readable; breasts or chest plausible | `bust` |
| A top's lower edge: no shelf bridging under the bust | `under_bust` |
| Crotch anatomy (genitals present or smooth); inner thighs | `crotch` |
| Kneecaps readable | `knees` |
| Heel, arch and toes; toes in order, big toe largest; inner ankle bone higher than the outer; the two feet alike | `feet`, `foot_inner.L/.R`, `foot_outer.L/.R` |
| Surface free of faceting, lumps and seams | every tile |

Not answerable here, and why: the dithered neck shadow and pore detail past 1 m are Godot effects (lookdev
`close-shot`); proportions and silhouette are humancheck's `body.png`; motion is the strips above.

Each stage that runs stores an input hash and its report in a Text datablock,
`character_pipeline:<id>`. A text saves with the .blend and never reaches a glb. The hash covers the
spec sections the stage reads, the hashes of the stages it needs, the plugin versions, the quality settings
it reads, and **the data and code files it reads** (`inputs.py`; the record keeps them as `inputs`, and a
rerun logs `<stage>: what it reads changed: <labels>`):

| Stage | Reads, besides the spec |
|---|---|
| `bake` | humanform `skin.py` and `look.py`, lookdev `bake.py` (and `detail.py` for a muscle normal map); the skin map size at every quality |
| `hair` | the hair preset as humanform resolves it (`hair_presets.json`: the preset, defaults, hairline), humanform `hair.py` and `brows.py`, `face_regions.json` when brows, lashes or body hair are on, lookdev `hair.py` and its `hair` material preset; a `shell_bun` reads the pipeline's own `hair.py` instead |
| `flesh` | follow-through's type registry, built-in and user (`FOLLOW_THROUGH_TYPES`), merged; follow-through `flesh.py` |
| `garments` | the contents of each preset the outfit wears (`wardrobe/presets/garments.json`) |

So editing a worn garment preset reruns garments, export and review with no `force`; editing humanform's
hair code reruns hair (which restarts from body: hair cannot come off); editing a preset the spec does not
wear, or a hair preset it does not use, reruns nothing. Data is hashed as parsed JSON, code with its line
endings normalised, so a CRLF and an LF checkout agree. A stage that starts reading a new file must add it to
`inputs.READS`, and `tests/fixtures/pipeline_hashes.py` must flip it (the fixture edits each input on a copy
of the plugins and checks that its stage, and nothing before it, moves; `runner.plan(spec)` gives the hashes
without building).

**The cascade stops where an output did not change (0.10.0).** A stage's input hash covers the hashes of
the stages it needs, so any rerun upstream reruns it. Where a stage reads an earlier one only through what it
left in the file, the earlier stage digests that output when it runs (`inputs.outputs`, kept in its record
as `output`) and the later stage's record keeps a *view* hash with the digest in place of the need's input
hash (`runner.view_hash`). A stage whose input hash moved but whose view did not is skipped - `unchanged`
with a `why` - and takes the new input hash, so the stages after it still rerun. Today that is moves after
flesh (`inputs.READS_OUTPUT`): the flesh stage digests the rig (object, bones with their tags, pose
constraints and locks, the rotation mode of the bones follow-through added), which meshes are bound to it,
and per bound mesh its geometry, vertex groups, weights, modifiers, materials, shape keys and skin/cloth marks.
What flesh writes that moves never reads - the jiggle block of the `follow_through` spec - is left out, so a
`limit_share` edit skips moves; a `[flesh] types` edit moves the bones and weights and reruns it (logged as
`flesh: what later stages read of it changed: <labels>`). A record from before 0.10.0 has no view and reruns.
For the weights to come out the same, the first flesh run keeps the unfleshed body (`<mesh>:preflesh`, a mesh
with a fake user and no object, so no exporter sees it) and a rerun swaps it back in before `prepare`
(`stages._preflesh`): a resumed rebuild's glb is byte-identical to a fresh build's. `pipeline_hashes` flips
each part of the digest with a drop-control (`PIPELINE_HASHES_DROP=flesh:output:<label>` must fail it).

```python
runner.build(spec)                                        # runs what changed, skips the rest
runner.build(spec, to_stage="moves", save=False)          # stop early
runner.build(spec, from_stage="garments")                 # in Blender opened on the .blend saved after moves
runner.build(spec, from_stage="moves", to_stage="moves", force=True)   # rerun one stage
```

- A stage runs only if its hash differs from the stored one, or with `force`. A stage that runs
  forgets the records of every stage after it.
- `from_stage` refuses when an earlier stage never ran in the file, or ran from another spec.
- A stage whose checks fail raises `stages.StageRefused` naming what to run first.
- **Where the minutes went:** `report["build"]` is `{quality, stage_seconds, skipped, total_seconds}` for
  this build (plus `restarted` when it rebuilt from body). The same record goes into the .blend (Text
  `character_pipeline:<id>:build`, `runner.build_record(ch)`) and, when export ran, the manifest's `build`
  block, rewritten after review so it covers the whole build.
- **Quality** (`quality.py`): "final" is every plugin's default and hashes as before the knob existed,
  except the skin map size. "preview"/"draft" pass cheaper settings - body fit iterations (draft also skips
  the face and hands-and-feet fits and is never stored in the library), review frames/views/cell size, the
  muscle normal map size, the hair cap's subdivision - and put them in those stages' hashes, so a final build
  of a draft file reruns them.
- **The skin maps are 2048 px at final, 1024 at preview and draft** (`quality.py` `skin`, passed to humanform's
  `look.skin(size=)`). Final builds baked at humanform's 1024 default until 0.8.0, so the size is in the bake
  hash at every quality: a final build of a file baked then rebakes (and, since the body carries hair, restarts
  from body - a bake that has to run again on a haired body is in `RESTARTS_FROM_BODY`). The bake report and
  the manifest carry a **`skin` block** read from the skin material: `{stage, map_px, tone_ok, tone_error,
  regions}`, `regions` being each marked region's tone in the baked albedo (lips, nipple, palm, sole, knee...:
  a bake that lost its marks has them all equal to `skin`). Dante: final 27.8 s, draft 17.3 s (0.62). What is left is rig-anything's (moves
  6.5 s, export 3.1 s), which has no cheaper setting yet.
- With `save` (the default) the .blend goes to `export.blend`, refusing to overwrite a file holding a
  scene this session lacks.
- **Specs are safe to copy.** A relative `export.blend` resolves under `$BLEND_DIR` when it is set, else under
  the spec's project (the folder holding `characters/`); an absolute one is still accepted
  (`spec.resolve_blend`, `Character.blend_path()`). `runner.build` refuses, before any stage runs, to save
  outside the project and `$BLEND_DIR` unless `save_outside=True` (`build.py ... save_outside=1`), so a spec
  copied into a scratch project cannot save over the real blend. The string is hashed as written, so a spec
  copied unedited, with its saved .blend copied beside it, resumes there with every stage unchanged. To make
  such a copy of a project, use the plugins repo's `tools/scratch_project.py`.

What the stages write that is the pipeline's own convention rather than a plugin's:

- **`height_m.stand` is the Idle clip's standing height** for every character: the rig standing at
  rest, which a hair bun does not raise. rig-anything's exporter writes the collider height there,
  and the export stage replaces it. There is no spec field for it; a spec that still has
  `export.height` is rejected with a message saying to delete the line. With no `standing_height_m`
  in the stored Idle report (a report from an older rig-anything) export raises and asks for moves
  to be rerun, rather than falling back to the mesh top.
- **The manifest's `variability` block** (only for a spec with a `[variability]` table) is the seam
  between the bake and the engine: ONE top-level key holding the **resolved** values this build used,
  `{"seed": <int>, "asymmetry": <float>, "jitter_phase": <float>, "jitter_amp": <float>}`. `seed` is
  already resolved, so an engine reading it never has to derive anything and never sees None.
  rig-anything bakes `asymmetry` into the gait clips (`variability.py`); `jitter_phase` and
  `jitter_amp` are the runtime half and are carried through untouched for the engine to read. A spec
  with no `[variability]` writes no key, so every manifest built before this existed is unchanged.
- **The manifest has no `upper_body`.** The clips' upper-body parameters are in the move reports
  stored on the actions; nothing in Godot read the copy.
- **Hair and muscle go on once.** Hair is joined into the body, because rig-anything exports one mesh,
  and a join cannot be undone; muscle is shape keys `bake` bakes in. So the hair stage refuses when the
  body already has hair (`stages.haired`, humanform's `views.hair_objects`: a hair material on a slot, or
  a loose `humanform_hair` object), and muscle when it has definition or is baked. **A whole build whose
  `[hair]` or `[muscle]` changed, appeared or was dropped rebuilds from `body` by itself**
  (`stages.RESTARTS_FROM_BODY`, `CARRIED`; body is forced, since its own hash did not change) and says so in
  `report["build"]["restarted"]`. Before this a changed preset refused, and its advice -
  `from_stage="body"` - skipped body as unchanged and refused again. A build started at `hair` still refuses.
  Rerunning hair alone used to stack a second layer on the
  first - the old bun stayed in the mesh, and humanform's landmarks read the previous cap (weighted 1.0
  to the head bone) as scalp, so the crown rose 7.8 mm and the head unit `h` grew 6.8%, moving the whole
  hairline. On a rebuild where only `[hair]` changed, bake's hash is unchanged and bake is skipped, so
  nothing else stood in the way.
- **Hair that swings is its own object and its own file.** For `ponytail` humanform makes the moving
  part as `<name>_hair_strand`, and the hair stage does **not** join it: the join drops
  the object properties follow-through builds a chain from (`ft_centreline`, `ft_root_bone`), and a mesh
  can carry one follow-through spec, which on a fleshed body is its jiggle. The hair stage checks the
  strand contract (humanform SKILL.md, *Hair*) and reports it as `strand_contract`; the **`strand`
  stage** then hands the object to `follow_through.strand.prepare`, which hangs 3-8 sprung bones off the
  head bone, weights the mesh along them and measures head and neck colliders from the body's own skin.
  The export writes it as `<id>_hair.glb` beside the body and names it in the manifest's `strands`, so a
  controller can do:

  ```gdscript
  var body := (load(manifest.scene) as PackedScene).instantiate()
  FollowThrough.attach(body, load(manifest.strands[0]))      # the chain bones are already on the body's rig
  FollowThrough.apply(body, {"routes": ["spring_bones"]})    # strand_modifier.gd springs them
  ```

  The order is **moves before strand before garments**: rig-anything reads a rig's structure to find its
  limbs and neck, so the move set is authored before chain bones hang off the head; and the chain's
  colliders are measured from every other mesh on the rig, so a top's cloth round the neck must not be
  there yet. Nothing about this is in a build script - the spec's preset is what says there is a strand
  (`stages.hair_strand_kind` asks humanform for the shape of the part, and `CHAINED_STRAND_KINDS` says
  which shapes get a chain). **`long_loose` is not one of them**: its strand is a curtain 16 cm wide and a
  chain is a line, so one chain down its middle twists it into a wedge while running (2.9 cm into the head
  in `verify_strands.gd`, against 1.2 mm for a ponytail). A curtain is joined into the body and rides the
  head rigidly, exactly as it did before this stage existed, until follow-through can build a sheet.
- **The hair material** comes from lookdev (`LD_SCRIPTS`, else the installed `lookdev/blender`); in Godot call
  `LookdevMaterials.apply` on the instanced character (soft hairline, anisotropy, per-face hair tangents).
  **lookdev is optional**: `plugins.use()` imports it only if its folder is there (hair then gets a flat
  material), and its version is in the input hash of the hair stage only, and only for a preset spec
  (`plugins.stage_versions`) - a lookdev release never invalidates a body, bake, flesh, moves, garments or
  export record, nor a shell_bun build's hair. `kind = "shell_bun"` (the old scalp shell and sphere
  bun, with its own numbers) still builds but is deprecated (`spec.DEPRECATED`) - replace it with a preset.
- **The body stage reports `stature`** in metres, read from where humanform's `pipeline.make` has it:
  the fit's `stature` residual row, `fit.aged.stature` or `fit.stature` (aged and child bodies), or
  measured with `scaffold.stature` for a body reused from the library.

The `pipeline_woman` regression fixture builds a spec end to end and resumes it in a second Blender;
`pipeline_hashes` flips every file a stage reads and checks which stage moves.

## Rules

- **A new character needs a spec, not code.** If a spec cannot say what it needs, the gap belongs in
  a plugin (and in `spec.GAPS` until it is there), not in a build script.
- **Never reorder stages to get past a refusal.** The order is what the refusal protects.
- **Do not edit the records text by hand.** Rerun the stage with `force` instead.
