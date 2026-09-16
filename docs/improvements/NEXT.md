# Next: the remaining work

A handoff for a fresh conversation. Start with:

> Read `docs/improvements/NEXT.md`, then the work item it points at, and plan it.

State as of 2026-09-16. Everything below is on `main` here and on `master` in `grungist-creek`, both
pushed, with no open branches or worktrees. Installed copies in `~/.claude/skills` match the repo:
- rig-anything 0.18.0
- follow-through 0.2.6
- wardrobe 0.2.0
- humanform 0.6.3
- character-pipeline 0.1.0
- animate-anything 0.9.0
- lookdev 0.1.0
- godot-lsp 0.1.0

Read the repo's `CLAUDE.md` first: worktrees, scratch folders, the regression harness, install and version rules,
and the gotchas are there.

---

## Where things stand

| Item | Status |
|---|---|
| [03 Regression harness and install](03-regression-harness-and-install.md) | **Done.** |
| [02 Bone roles and rig profiles](02-bone-roles-and-rig-profiles.md) | **Done, lean.** One "done when" unmet: Belle still needs hand-marked flesh zones (blocked on 05 · 5.9). |
| [01 Character spec and pipeline](01-character-spec-and-staged-pipeline.md) | **Done.** Belle and the 16 people build from `grungist-creek/characters/*.toml`. Two small conventions open (below). |
| [04 Checks that match the eye](04-checks-that-match-the-eye.md) | **Not started.** Next. |
| [05 Feature gaps](05-feature-gaps.md) | 5.1, 5.6, 5.7 done. Open: 5.2 hair, 5.3 compression garments, 5.4 skirts, 5.5 muscle, 5.8 fixture findings, 5.9 buttocks read low. |
| Old project notes | Not triaged (item 7 below). |

What exists now, and is worth knowing before starting anything:

- **`python tools/regress.py --jobs 2`** rebuilds 11 fixtures headless and compares them to `tests/golden/`:
  `mpfb_woman_curvy`, `rigify_human`, `mixamo_names`, `quadruped`, `rabbit`, `cricket`, `starfish`,
  `flesh_figure`, `dressed_figure`, `dressed_presets`, `pipeline_woman`.
  - `--twice` fails a build that doesn't reproduce.
  - `--godot C:/Users/pauli/Code/GoDot/grungist-creek` plays the exports in the engine's verifiers.
  - A full `--twice --godot` run takes about 12-15 minutes. See `tests/README.md`.
- **Bone roles:** `bodymap.build(rig)["roles"]` gives root, pelvis, chest, neck, head, tail, anchors, hands and feet, and
  controls. Rig profiles live in `rig_analysis/profiles/`. rig-anything SKILL.md, "Bone roles".
- **Characters:** `character_pipeline.runner.build(spec)` runs the stages body, bake, hair, flesh, moves, garments,
  export. They refuse out of order, record their inputs in the .blend, and resume in a fresh session. Its SKILL.md
  has Belle as the worked example.
  - `assets/humans/build_human.py who=<name>` and `assets/belle/build_belle.py` are thin callers.
- **Presets and exporter:** wardrobe garment presets with `wardrobe.dress`; follow-through `limit_share` per flesh type;
  `export.export_character` writes the `.moves.json` for bipeds and quadrupeds.

---

## What to do next, in order

### 1. 04a - the hole check counts cloth in a crease as a hole

Belle's shorts fail `verify_wardrobe.gd` at 1.708% holes (limit 0.5%) where the renders show no gap; the sports top
passes at 0.227%. The same numbers came from the old hand-built assets and from the spec-built ones, so this is the
check, not the build. Every wardrobe result is less trustworthy until it is fixed.

- Design and steps: 04 section **a**.
- Reproduce with:

  ```
  "$GODOT" --headless --fixed-fps 60 --path . -s res://addons/wardrobe/verify_wardrobe.gd -- \
      body=res://assets/belle/belle.glb garment=res://assets/belle/belle_shorts.glb frames=240 every=8 hem=true jiggle=true
  ```

  The failing frame is 88; the fixtures `dressed_figure` and `dressed_presets` pass and must keep passing.
- Done when Belle's shorts pass without loosening the limit, a real hole (a deliberately removed garment face)
  still fails, and the goldens that move are reviewed.

### 2. Small open findings (05 · 5.8), each with its numbers in the golden

Take them one at a time; each is a short branch.

- **The cricket's landing never exports.** JumpLand fails its foot-slide check by 0.14 mm (0.5 mm against a
  0.36 mm limit at `hop.py` ~1251). Decide whether that is a real slide or a limit too tight at 30 mm scale.
  The messages also name legs by root bone (`fore_femur.L`), not leg (`fore.L`).
- **The slides put feet through the floor on a Rigify biped.** `rigify_human` drops Slide, SlideRecover and
  SlideToCrouch with the reasons under `export.dropped_clips`.
- **Starfish arms get 3 and 4 bones** off a rounding edge in `radial.build`. Take one count per appendage kind.
- **`radial.skin` reports coverage without measuring it.**

### 3. 05 · 5.9 - flesh reads the buttocks low, then retire Belle's hand marks

On every body measured, the buttock region sits under the mass (Belle 7 cm low, facing down), because the lean
envelope absorbs the upper buttock. Changing the zone height does not help. 5.9 has the numbers and the steps.

When it is fixed, remove the `[[flesh.zones]]` from `grungist-creek/characters/belle.toml`. Then prove the result:
- rebuild her
- run `belle_demo.tscn -- --selftest` and the wardrobe verifier

That meets the last unmet "done when" of 02. Belle's swing limits live in follow-through's registry (`limit_share`)
and were tuned against the low reading, so check them again on the self-test.

### 4. Loose ends from 01

- **Standing height has two conventions.** `export.height = "mesh"` (the crowd: mesh top) and `"idle"` (Belle: the
  Idle clip's standing height, which a hair bun doesn't raise). Pick one, move the crowd or Belle, and remove the
  spec field.
- **`upper_body` in a manifest means different things.** For the crowd it is the move reports; in Belle's old
  manifest it was her input table. No Godot code reads it. Decide what it is for, or drop it.
- **The body stage reports `stature: null`.** `stages.run_body` reads `fit.stature`, and humanform's result has it
  elsewhere. This is cosmetic.
- **Nora (`assets/wardrobe/build_person.py`) is still a script.** She has a sculpted body on mocap, and nothing in a
  spec covers that. Convert her only if a spec grows a source for it.
- **The real `.blend` files were not rebuilt** (`C:/Users/pauli/Code/Blender/human_*.blend`, `belle_realistic.blend`).
  The spec builds ran in scratch. The next real `build_human.py who=<name>` saves them through the pipeline's
  scene guard.

### 5. 04 b-d - review strips, a motion critic, numeric guards

These come after 04a. 04 has the design:
- **b:** fixed-scale review strips written by every export.
- **c:** a critic that judges a clip's motion from those strips.
- **d:** numeric guards distilled from what the critic keeps finding.

The character pipeline's stage table already reserves a `review` stage after `export` for this.

### 6. 05 · 5.2-5.5 - the look of a character

These are independent; take them as a character needs them:
- hair (Belle's reads as a helmet; today it is the pipeline's `shell_bun`, listed in `spec.GAPS`)
- compression garments (her top traces the body)
- skirts and dresses
- muscle definition (Dante reads average)

A new hair or garment kind should arrive as a plugin preset or builder that a spec names, not as code in a build
script.

### 7. Triage the old project notes

`grungist-creek/docs/plugin-improvements.md` predates all of this. Some entries are stale. Others may still be live
and are not filed anywhere:
- `flesh.add_jiggle_bones` stripping weights on a re-run
- the jiggle modifier needing physics-tick processing
- the hard `max_offset_m` clamp
- the volume API gaps (`collision_mask`, `tumble`, `push`)

Check each against current code, then file it under a category in [README.md](README.md) or strike it.

---

## Things that cost time to learn

Most of this is now in `CLAUDE.md`. The rest:

- **Building the project's characters without touching its assets.** Copy these into a scratch folder with the same
  layout:
  - `characters/`
  - `assets/humans/build_human.py`
  - `assets/belle/build_belle.py`

  Then point the specs' `blend =` at scratch and set `PROJECT` to that folder. Set `RA_SCRIPTS`, `HF_SCRIPTS`,
  `FT_SCRIPTS`, `WD_SCRIPTS` and `CP_SCRIPTS` to this repo's `plugins/<name>/scripts`, and `HUMANFORM_LIBRARY` to a
  copy of `~/.claude/humanform/library`.
  - Timing: a crowd person builds in 10-20 s, Belle in about 40 s.
  - `who=tomas` needs `C:/Users/pauli/Code/Blender/humanform_hands_feet_demo.blend` opened.
  - Always check the spec's `blend` path first. A build saves there.
- **Comparing a rebuild with committed assets.** Compare manifests with `regress.compare` at the harness tolerance.
  Compare glbs by their glTF JSON chunk with `extras` set aside. Both one-offs were in the 01 conversion; bone-role
  tags, rig profiles and humanform sheets are all extras.
- **Verifying in Godot** (`GODOT` = the `_console` build, path in grungist-creek's CLAUDE.md):

  ```
  "$GODOT" --headless --import --path .
  "$GODOT" --headless --path . belle_demo.tscn -- --selftest
  "$GODOT" --headless --path . people_demo.tscn -- --selftest
  ```

- **Finding a nondeterminism.** What worked, in order:
  1. Compare the written files.
  2. Checksum each stage's output in two builds and find the first that disagrees.
  3. Hash that stage's inputs, structure (face order, sorted and unsorted) as well as positions.
  4. Reproduce it minimally: three processes, three hashes.

  5.7 ended in Blender itself: `create_uvsphere` shuffles faces per process.
- **Parallel agents.** Give each agent a worktree, a scratch folder, and a list of the files it must not touch. Keep
  version bumps, NEXT.md and tests/README.md for whoever merges. Merges then only conflicted in goldens, which
  resolve by taking one side and re-recording with `--twice --update`, then reviewing the diff.

## Loose ends outside the code

- `C:/Users/pauli/Code/Blender/belle_demo_before_rebuild.blend` (100 MB) is still there. `belle_demo.blend` and its
  backup are in the Recycle Bin, split into `belle_stylized.blend` and `creature_tests.blend`.
- This repo is public, and `plugins/humanform/data/` (ANSUR II public CSVs and the seed contact sheets) is published
  with it. That was a deliberate choice, recorded here in case it is revisited.
