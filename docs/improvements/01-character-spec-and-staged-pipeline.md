# 01 - Character spec and staged pipeline

Categories: **2 cross-plugin ordering**, **4 re-derived decisions**. Biggest time saver.

> **Done** (September 2026). Checked against "Done when":
> - **Belle and all 16 people build from spec files alone** - met. The build scripts only pick a spec.
> - **Rebuilt manifests match the committed ones** - met. Same clips, checks, colliders and durations; the only
>   additions are `contacts` and documentation fields.
> - **`build(spec, from_stage=...)` in a fresh session reproduces the build** - met. The `pipeline_woman` fixture
>   resumes export in a second Blender with an identical manifest; Belle resumed from her .blend runs garments and
>   export only.
> - **Out-of-order stages refuse with the order** - met.
> - **A new character needs no new code** - met for anything the spec covers (see `spec.GAPS`: hair until a hair
>   plugin exists, flesh zones while 05 · 5.9 is open).
> - Specs are TOML, not YAML: Blender's Python has `tomllib` and no YAML parser.
>
> Loose ends settled afterwards (branch `pipeline-conventions`):
> - **Standing height has one convention.** `height_m.stand` is the Idle clip's `standing_height_m` for every
>   character, so a hair bun does not raise it. The `export.height` field (`"mesh"` for the crowd, `"idle"` for
>   Belle) is gone. A spec that still names it is rejected, because silently ignoring `"mesh"` would build a
>   different height than it asked for. A stored Idle report without the measurement makes export raise and asks
>   for moves to be rerun: the stages cannot reach export without an Idle report, and falling back to the mesh
>   top would bring the second convention back. In Godot, `collider.height` still sizes the capsule at load;
>   `height_m.stand` is what Belle's and the creature controller's capsule return to after a crouch, and
>   MovesController's fallback when a manifest has no collider.
> - **`upper_body` is dropped from the manifest.** No Godot code read it; the parameters stay in the stored move
>   reports.
> - **The body stage reports `stature`.** It read `fit.stature`, which humanform only sets for a child; an adult's
>   stature is the fit's `stature` residual row (or `fit.aged.stature` when aged, or measured with
>   `scaffold.stature` when the body was reused as is).

## Problem

A character is built by a hand-written script that calls five plugins in an order only the author
knows. Every plugin documents its own step; nothing encodes what must already exist before a step
runs, or remembers a step's result.

- `grungist-creek/assets/humans/build_human.py` (`class Human`) and `assets/belle/build_belle.py`
  (`class Belle(Human)`) are the current form. Belle needed a subclass, overridden `options()`,
  `moves()`, `manifest_extra()`, and new `hair()`, `flesh_sheet()`, `flesh()`, `garments()`.
- State passes through instance attributes (`self.res`, `self.worn`) and objects looked up by name.
  Re-running one stage means re-running the script from the top; the stylized Belle kept move
  results in `bpy.app.driver_namespace`, lost when Blender closed.

## What we saw

Ordering constraints that were each found by breaking them (all now comments in `build_belle.py`):

- **Clips before garments.** rig-anything measures arm hang against every mesh bound to the rig;
  with 8 mm of sports top at the armpits the run's arms went up over her head.
- **Flesh before garments.** Garments are cut from the skin and inherit its weights; cut first,
  they don't carry the jiggle bones.
- **Bake before moves**, **rotation mode before keys**, **flesh `set_params` must not iterate the
  regions it replaces** (crashed Blender).

Decisions re-derived per character, each by trial:

- Garment ease: 4 mm collapsed onto skin at folds (holes tripled), 12 mm was worse, 8 mm worked.
- Sports-top band: at the under-bust fold skin showed through; moved lower.
- Flesh limits: follow-through measured the seat at 3.7 cm, so the buttocks limit was tuned by
  running the Godot self-test (5.8 cm on the limit 11-12%, 6.9 cm 9%). `LIMIT_SHARE = {"breast":
  0.66, "butt": 1.9}` now lives in the build script.
- Firmness before or after the fit; stance-width units; posture signs; gait style per build word.

## Design

**A character spec** - one declarative file per character, no code:

```yaml
name: Belle
body:                       # humanform brief
  sex: female
  age: 28
  stature: 1.70
  build: curvy
  firmness: 0.3
  cupsize: 1.0
  measurements: {chest: 1.02, waist: 0.72, seat: 1.07}   # ANSUR II variable names in the real schema
                                                          # - see build_belle.py's BELLE brief
  parts: {face: ..., hands: ..., feet: ...}
  skin: [0.62, 0.45, 0.36]
hair: short_bun             # a preset, once hair exists (see 05)
moves:
  roles: [Idle, Walk, Trot, Run, Crouch, CrouchWalk, Jump]
  style: adult              # locomotion.GAIT_STYLES
  gaits: {Walk: 0.2, Trot: 1.0, Run: 2.0}
  may_fail: [Jump]          # exported forced and listed, never silently
flesh:
  types: [breast, butt]     # registry types; zones only if the automatic find is wrong
outfit:
  - {preset: sports_top}
  - {preset: shorts_mid_thigh}
export: {dir: res://assets/belle, manifest_extra: [heights, contacts, garments]}
```

**A staged pipeline** that builds any spec:

| Stage | Needs (checked before running) | Produces (saved on the objects) |
|---|---|---|
| `body` | spec.body | mesh + MPFB rig, `profile` (see 02) |
| `bake` | body | one skinned mesh, <=4 weights, no shape keys |
| `hair` | bake | hair mesh skinned to the head role |
| `flesh` | bake; no garments bound | jiggle bones, `follow_through` spec |
| `moves` | bake; **no garments bound** | actions + per-role reports |
| `garments` | flesh (if spec has flesh); moves | garment meshes, cover/hide spec |
| `export` | moves; every stage the spec names | glb(s), `.moves.json`, `.rig.json` |
| `review` | export | fixed-scale strips + critic verdict (see 04) |

- Each stage writes its result and an **input hash** to a custom property on the rig
  (`rig["pipeline"][stage] = {hash, report, when}`), so `build(spec, from_stage="garments")` can
  resume in a fresh Blender session and skip stages whose inputs are unchanged.
- A stage refuses with a named reason when a precondition fails ("garments are bound to the rig -
  run moves before garments"), instead of producing a wrong result.
- **Presets carry the re-derived decisions**: garment presets own ease, band placement and cover
  settings; flesh types own limit shares; gait styles already own gait shape. A build script never
  holds a tuned number.

- **The `export` stage's `.moves.json` belongs in rig-anything, not in a build script.** The hopper
  and radial exporters (`hop.export_creature`, `radial_moves.export_creature`) write the manifest
  MovesController reads. A biped or quadruped exported with `export.export` gets only a `.rig.json`,
  and `build_human.py` assembles `scene`, `clips`, `loops`, `implied_speed_mps`, `gaits`,
  `collider`, `height_m` and `verified` by hand. The regression harness hit this in 03 step 1e:
  `mpfb_woman_curvy`, `flesh_figure`, `rigify_human` and `quadruped` cannot reach `verify_moves.gd`
  under `regress.py --godot`. Give rig-anything an `export_character(mesh, rig, reports, glb,
  name, res_path)` in the shape of `export_creature`, and let `manifest_extra` add to what it wrote.
  Once one exists, add those fixtures' manifests to `--godot`.

**Where it lives**: a new small plugin in this repo (working name `character-pipeline`), depending
on humanform, rig-anything, follow-through and wardrobe. It owns the spec schema, the stages and
the presets that span plugins. Presets that belong to one plugin (a garment's ease, a flesh type's
limit share) go into that plugin's own registry and are only referenced by name from the spec.

## Steps

1. **Freeze the contract.** Write the spec schema (JSON Schema or a validated dataclass) from the
   two real cases: one crowd person from `build_human.CHARACTERS` and Belle. Every field must map
   to an existing plugin argument; list any that don't as gaps.
2. **Move tuned numbers into their owners.**
   - follow-through `types/builtin.json`: add `limit_share` per type (breast 0.66, butt 1.9) and use
     it in `flesh.prepare` instead of `material.max_offset x 2 x peak_m` when present.
   - wardrobe: add garment presets (`sports_top`, `shorts_mid_thigh`, `tshirt`, `trousers`, `briefs`)
     holding the tailor arguments, `fit.ease(base, loose)`, band placement and `cover.compute` args
     that Belle's `GARMENTS`/`COVER` constants use today.
3. **Stage runner.** `pipeline.build(spec_path, from_stage=None, to_stage=None, force=False)`:
   preconditions table as above, input hashing, results saved on the rig, a report per stage.
   Port `Human.source/bake/moves/export/renders` and Belle's `hair/flesh/garments` into stages - move,
   don't copy; `build_human.py` and `build_belle.py` become thin callers.
4. **Ordering guards in the plugins themselves**, so they hold even without the runner:
   - rig-anything `upper` / `verify.limb_clearance`: measure against the body mesh only (mesh with
     the most skinned vertices, or a `role=body` tag), ignore meshes tagged as garments.
   - wardrobe `tailor.*`: warn if the body has a follow-through spec but no `ft_jiggle_*` groups
     yet ("flesh after garments loses the jiggle weights").
5. **Convert the project.** Write `grungist-creek/characters/<name>.yaml` for the 16 people and
   Belle; rebuild all with the runner; outputs must match the committed manifests (see 03's
   harness).
6. **Document** the spec in the new plugin's SKILL.md with Belle as the worked example; point
   humanform, rig-anything, follow-through and wardrobe SKILL.md files at it for "build a whole
   character".

## Done when

- Belle and all 16 people build from spec files alone; `build_human.py`/`build_belle.py` contain no
  tuned numbers and no stage logic.
- Rebuilt manifests match the committed ones (same clips, checks, colliders; numeric drift within
  the harness tolerance).
- `build(spec, from_stage="garments")` in a fresh Blender session reproduces the full build.
- Running stages out of order (garments then moves) refuses with a message naming the order.
- A new character that is "a description plus a style plus an outfit" needs no new code.
