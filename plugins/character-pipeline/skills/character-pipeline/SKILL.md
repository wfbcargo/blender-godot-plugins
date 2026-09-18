---
name: character-pipeline
description: Build a whole character for Godot 4.7 from one TOML spec - a humanform body from a brief, baked, with hair, follow-through flesh, rig-anything's move set and wardrobe garments, exported as the glb, .moves.json and garment glbs. Stages check the file before they run, so doing them in the wrong order (garments before moves, flesh after garments) refuses and names the order; each stage records an input hash in the .blend, so a rebuild skips what has not changed and a fresh Blender session resumes from a saved file. Use when asked to build, rebuild or add a character, person, NPC or crowd member from a description; to write or change a character spec; to rebuild one stage of a character (its moves, its outfit); or when a build script calls humanform, rig-anything, follow-through and wardrobe in sequence by hand.
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
`[flesh]`-only edit reruns flesh, moves, export and review - study_man 30 s against 64 s for the whole build
on the same loaded machine. Without it every call started from an empty scene and rebuilt from body.
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
[body.parts]                       # humanform library parts
face = "face-female-11-1-49f17892"

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

[flesh]                            # follow-through; limit shares come from the type registry
types = ["breast", "butt"]
may_miss = []                      # types the stage may come back without (see below)
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
blend = "C:/Users/pauli/Code/Blender/belle_realistic.blend"
```

**The flesh stage says what it found.** The build log gets `flesh: found <type>: <regions>` and
`flesh: MISSED <type>: <reason with numbers>` (follow-through's `missed`), the stage report `found`
and `missed`, and the manifest a `flesh` block - `types`, per region `name, type, bone, parent,
peak_m, max_offset_m, material, frequency_hz, damping_ratio`, and `missed` `[{type, reason,
allowed}]`. A type in `types` that finds no mass fails the stage, naming why, unless `may_miss`
lists it. Keep the limit at or under `peak_m`: a larger one fails `verify_flesh.gd`'s `within_body`
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
| `review` | export | the glb and every role's clip exist |

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
```

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

What the stages write that is the pipeline's own convention rather than a plugin's:

- **`height_m.stand` is the Idle clip's standing height** for every character: the rig standing at
  rest, which a hair bun does not raise. rig-anything's exporter writes the collider height there,
  and the export stage replaces it. There is no spec field for it; a spec that still has
  `export.height` is rejected with a message saying to delete the line. With no `standing_height_m`
  in the stored Idle report (a report from an older rig-anything) export raises and asks for moves
  to be rerun, rather than falling back to the mesh top.
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
