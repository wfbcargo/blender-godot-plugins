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

[hair]                             # humanform's hair layer: the brief's hair = {preset, colour}
preset = "bun"                     # short_crop, bob, bun, ponytail, long_loose
colour = [0.17, 0.10, 0.06]        # screen (sRGB)

[flesh]                            # follow-through; limit shares come from the type registry
types = ["breast", "butt"]
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

`spec.load(path)` checks it and names the field it rejects. `spec.GAPS` lists what a spec may carry
that no plugin owns yet. Tuned numbers live with their owners, and a spec only names them:
- gait styles in rig-anything
- flesh limit shares in follow-through's registry
- garment ease, bands and cover in wardrobe's presets

## Stages

| Stage | Needs | Checks in the file before it runs |
|---|---|---|
| `body` | - | a `blend` source's object is in the open file |
| `bake` | body | the rig and the humanform mesh exist |
| `hair` | bake | baked; no garment bound; **no hair in the file already**. Runs humanform's `hair.add` and joins the hair (and a strand, after checking its follow-through contract) into the body |
| `flesh` | bake, hair | baked; no garment bound - cut first, a garment carries no jiggle weights |
| `moves` | bake, hair, flesh | baked; no garment bound - rig-anything measures arm hang against every mesh on the rig |
| `garments` | moves, flesh | every role has a stored clip; jiggle bones present if the spec has flesh |
| `export` | moves, garments | every role has a stored clip; an outfit is bound if the spec has one |

Each stage that runs stores an input hash and its report in a Text datablock,
`character_pipeline:<id>`. A text saves with the .blend and never reaches a glb. The hash covers the
spec sections the stage reads, the hashes of the stages it needs, and the plugin versions:

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
- **Hair goes on once.** It is joined into the body, because rig-anything exports one mesh, and a join
  cannot be undone - so the stage refuses when the body already has hair (`stages.haired`, humanform's
  `views.hair_objects`: a hair material on a slot, or a loose `humanform_hair` object). **To change
  `[hair]`, rebuild from `body`**, the one stage that clears the character out of the file:
  `runner.build(spec, from_stage="body")`. Rerunning hair alone used to stack a second layer on the
  first - the old bun stayed in the mesh, and humanform's landmarks read the previous cap (weighted 1.0
  to the head bone) as scalp, so the crown rose 7.8 mm and the head unit `h` grew 6.8%, moving the whole
  hairline. On a rebuild where only `[hair]` changed, bake's hash is unchanged and bake is skipped, so
  nothing else stood in the way.
- **The strand contract survives the join.** For ponytail and long_loose the strand object's
  follow-through contract (humanform SKILL.md, *Hair*) is checked before the join and reported as
  `strand_contract`; its `ft_strand` vertex group and fallback weights survive it. The hair material
  comes from lookdev (`LD_SCRIPTS`, else the installed `lookdev/blender`); in Godot call
  `LookdevMaterials.apply` on the instanced character (soft hairline, anisotropy, per-face hair tangents).
  **lookdev is optional**: `plugins.use()` imports it only if its folder is there (hair then gets a flat
  material), and its version is in the input hash of the hair stage only, and only for a preset spec
  (`plugins.stage_versions`) - a lookdev release never invalidates a body, bake, flesh, moves, garments or
  export record, nor a shell_bun build's hair. `kind = "shell_bun"` (the old scalp shell and sphere
  bun, with its own numbers) still builds but is deprecated (`spec.DEPRECATED`) - replace it with a preset.
- **The body stage reports `stature`** in metres, read from where humanform's `pipeline.make` has it:
  the fit's `stature` residual row, `fit.aged.stature` or `fit.stature` (aged and child bodies), or
  measured with `scaffold.stature` for a body reused from the library.

The `pipeline_woman` regression fixture builds a spec end to end and resumes it in a second Blender.

## Rules

- **A new character needs a spec, not code.** If a spec cannot say what it needs, the gap belongs in
  a plugin (and in `spec.GAPS` until it is there), not in a build script.
- **Never reorder stages to get past a refusal.** The order is what the refusal protects.
- **Do not edit the records text by hand.** Rerun the stage with `force` instead.
