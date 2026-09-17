# Next: the remaining work

A handoff for a fresh conversation. Start with:

> Read `docs/improvements/NEXT.md`, then the work item it points at, and plan it.

State as of 2026-09-17. Everything below is on `main` here and on `master` in `grungist-creek`, with no
open branches or worktrees; the merges of radial-counts, flesh-end-rings and pipeline-conventions and the
character rebuild (grungist-creek `ed654b0`) are not pushed yet. `python tools/regress.py --twice --jobs 2 --godot` passed on `main` after them (11 fixtures, no
change, 9 manifests and the wardrobe fixtures pass in Godot). Installed copies in `~/.claude/skills` match
the repo:
- rig-anything 0.21.0
- follow-through 0.4.0
- wardrobe 0.2.1
- humanform 0.6.3
- character-pipeline 0.2.0
- animate-anything 0.9.2
- lookdev 0.1.0
- godot-lsp 0.1.0

Read the repo's `CLAUDE.md` first: worktrees, scratch folders, the regression harness, install and version rules,
and the gotchas are there.

---

## Where things stand

| Item | Status |
|---|---|
| [03 Regression harness and install](03-regression-harness-and-install.md) | **Done.** |
| [02 Bone roles and rig profiles](02-bone-roles-and-rig-profiles.md) | **Done.** Belle's hand-marked flesh zones retired with 05 · 5.9. |
| [01 Character spec and pipeline](01-character-spec-and-staged-pipeline.md) | **Done.** Belle and the 16 people build from `grungist-creek/characters/*.toml`. Its loose ends are settled (character-pipeline 0.2.0) and the committed characters are rebuilt on them (grungist-creek `ed654b0`). |
| [04 Checks that match the eye](04-checks-that-match-the-eye.md) | **a done** (wardrobe 0.2.1). b-d not started. |
| [05 Feature gaps](05-feature-gaps.md) | 5.1, 5.6, 5.7 done. Open: 5.2 hair, 5.3 compression garments, 5.4 skirts, 5.5 muscle. 5.8 done (rig-anything 0.21.0). 5.9 done, with its end-ring follow-up (follow-through 0.4.0). |
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

### 1. 04a - done (wardrobe 0.2.1)

The hole check now counts only skin a viewer can see into; Belle passes all 7 clips in the shorts, the top and both at
the unchanged 0.5%, and a cut patch still fails. What was found and what shipped is under 04 section **a**. When
checking a garment, pass `clip=` for every clip: the default is the first in the list, and the sports top's earlier
"passes" was only its crouch.

### 2. Small open findings (05 · 5.8) - done (rig-anything 0.21.0)

- **Done (rig-anything 0.19.0): the cricket exports.** The landing's slide was real and came from shared
  code, as did a toe drag in the walk that it hid; every clip is now checked for a foot moving along the floor.
  05 · 5.8 has the details.
- **Done (rig-anything 0.20.0): the slides pass and export on a Rigify biped.** Three shared causes (a hand-written
  slide path, feet not laid on the floor, feet blended along the floor between spots); 05 · 5.8 has the details.
- **Done (rig-anything 0.21.0): one bone count per radial appendage kind.** `radial.build` gives every appendage of a
  role the median of its kind's length / (1.2 width) ratios; the starfish's five arms all have 4 bones (21 bones), and
  the scratch anemone went from mixed 4/5 to 5 on all ten tentacles. Every outlier appendage now gets the kind's count
  whatever its own length; a warning for a far outlier is not written yet.
- **Done (rig-anything 0.21.0): `radial.skin` measures coverage** by reading the written weights back
  (`coverage`, `vertices_unweighted`). `plugins/animate-anything/references/radial-bodies.md` (lines ~16 and ~96) still
  describes the old per-appendage count and unmeasured coverage; update it with animate-anything's next change.

### 3. 05 · 5.9 - done (follow-through 0.3.0, end rings 0.4.0), Belle's hand marks retired

Buttocks are read from the side across the spine and thigh chains; both sample bodies score their butts, and
Belle's `[[flesh.zones]]` are gone from `grungist-creek/characters/belle.toml`. Rebuilt with every stage forced, her
self-test passes (breasts 7.5/8.7%, buttocks 8.6/8.4% on the limit, under 10%) and the wardrobe verifier passes all 7
clips in both garments. That meets 02's last "done when". Since follow-through 0.4.0 a chain's first ring (and its last built ring when the
chain is searched to its end) fits its envelope from wall vertices only, so the Figure's crotch no longer skews its
breasts and belly and its false love handles are gone; `render_heat` and the marks sheet draw a profile-read butt from
its profile. Belle is rebuilt on 0.4.0 (see 4): breasts 267 -> 271 vertices, limit
0.0781 m, buttocks unchanged. Still open: the Bloater's moobs score as misses (0.19 m), and
Belle's two-segment root-spine chain counts as searched to its end, so its top ring at 0.961 m (a hand-off to the next
chain, not a cap) is wall-filtered; her regions do not move.

### 4. Loose ends from 01 - conventions settled (character-pipeline 0.2.0), character rebuild in progress

- **Done: one standing height.** `height_m.stand` is always the Idle clip's `standing_height_m`; export fails if no
  Idle report is stored. `export.height` is gone from the spec and a spec naming it is a `SpecError`; Belle's
  `height = "idle"` line is removed on grungist-creek `master`. `collider.height` (rig-anything, mesh top) still differs
  from `stand` by under a millimetre on pipeline_woman; a hair bun would widen that. rig-anything's SKILL.md (~305) and
  `export_character` docstring still say `stand` is the mesh top.
- **Done: `upper_body` dropped** from the manifest. rig-anything's SKILL.md (~309) still shows it as an example extra.
- **Done: body stature reported** (`stages._stature`): fit residual row, aged, child, or measured on a reused library
  body. Only the fitted-adult path is covered by a fixture.
- **Done: the characters are rebuilt** (grungist-creek `ed654b0`). Belle and the 16 people ran every stage
  (`force=1`) through `build_belle.py` / `build_human.py` with these versions installed.
  - `upper_body` is gone from all 17 manifests.
  - The crowd's `height_m.stand` moved from the mesh top to the Idle standing height, by -12.6 mm (lily) to +7.8 mm
    (walter): the Idle height is the highest rest bone point, so it is where the head bone's tip sits against the
    scalp. `collider.height` is still the mesh top, so on the crowd the two now differ by up to 12.6 mm, not the
    under a millimetre measured on pipeline_woman. Belle's stand (1.6998) did not change.
  - The crowd's walks and runs changed only in `foot.L`/`foot.R` (quaternion delta up to 0.054) and their walk duty
    factors (0.781 -> 0.75 and similar): the crowd had last been built before rig-anything 0.19's planted-foot fix.
    The glTF JSON is otherwise identical with extras set aside.
  - The crowd specs have no `[flesh]`, so there was no butt measure to redo; only Belle carries flesh. Her breasts
    moved with the end rings (above); her buttocks did not.
  - Checks: both self-tests pass (Belle's flesh 7.6/9.0% and 8.6/8.4% on the limit). `verify_wardrobe` passes all 7
    clips in the shorts, the top and both, 21 runs; the worst holes are 0.39% (shorts walk) and the worst poke 0.24%.
    The `cut=0.04` control fails at 6.5%.
  - **Found: `verify_wardrobe.gd` passes a clip that does not exist.** `clip=Walk` on Belle (her clips are
    `Belle_Walk` and so on) raises a script error at `player.get_animation(clip).loop_mode`, samples nothing and still
    prints `WD_RESULT` with `"passed": true` and zero holes. It should fail with `unknown clip`, and so should a run
    with no samples. Until it does, pass the full clip name and check `samples` in the result.
- **Nora (`assets/wardrobe/build_person.py`) is still a script.** She has a sculpted body on mocap, and nothing in a
  spec covers that. Convert her only if a spec grows a source for it.
- **Done: the real `.blend` files are rebuilt.** The rebuild saved `C:/Users/pauli/Code/Blender/human_*.blend` and
  `belle_realistic.blend` through the pipeline's scene guard; copies from before it are in that conversation's scratch
  (`wf/rebuild/blend-backup`).

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
