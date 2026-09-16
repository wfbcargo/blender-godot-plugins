# Next: the remaining work

A handoff for a fresh conversation. Start with:

> Read `docs/improvements/NEXT.md`, then the work item it points at, and plan it.

State as of 2026-09-16. Everything below is on `main` in this repo and on `master` in `grungist-creek`,
both pushed. Installed plugin copies in
`~/.claude/skills` match the repo.

This repo was split out of `PaulClaudePlugins` on 2026-09-16 with its history kept, so every commit
hash here differs from the same commit there. `claude-architect` and `claude-boundaries` stayed
behind.

---

## Where things stand

| Item | Status |
|---|---|
| [03 Regression harness and install](03-regression-harness-and-install.md) | Steps 1-5 **done**. Steps 6-8 and five fixtures open. |
| [05 Feature gaps](05-feature-gaps.md) 5.1 jump sinks | **Done** - rig-anything 0.14.2. Belle's Jump ships unforced. |
| 05 · 5.6 garment nondeterminism | **Done** except the `--twice` harness check its "done when" asked for. wardrobe 0.1.1. |
| 05 · 5.7 `object.join` shuffles faces | **Open**, filed with a minimal repro. |
| [01 Character spec and pipeline](01-character-spec-and-staged-pipeline.md) | Not started. Biggest time saver. |
| [02 Bone roles and rig profiles](02-bone-roles-and-rig-profiles.md) | Not started. |
| [04 Checks that match the eye](04-checks-that-match-the-eye.md) | Not started. |
| 05 · 5.2 hair, 5.3 compression, 5.4 skirts, 5.5 muscle | Not started. |

Already built and worth knowing about before starting anything:

- `python tools/regress.py --jobs 2` - four fixtures rebuilt headless and compared to
  `tests/golden/` (about 3 minutes). Run it before changing shared code and before calling a
  change done. See [`tests/README.md`](../../tests/README.md).
- `python tools/install.py <plugin>` or `--all` - the only way into `~/.claude/skills`. Refuses to
  overwrite a copy edited in place.

---

## Remaining work, in the order I would take it

### 1. Finish 03 - small, and every later item leans on it

Planned 2026-09-16 against a clean baseline: `regress.py --jobs 2` passed on `main` from this repo
(`rabbit` 140 s, the other three about 20 s each). Six branches, in order. Each one ends the same
way: `regress.py --jobs 2` (plus `--twice` once 1a exists), goldens reviewed in the diff, merge
`--no-ff`, push, `tools/install.py --all`. One worktree under `.worktrees/` and one scratch subfolder
per branch.

**1a. `regress-twice` - the reproducibility check owed by 5.6.**
- `tools/regress.py --twice`: each fixture builds twice (`out/<name>/a`, `out/<name>/b`, both queued so
  `--jobs` parallelises them). The two reports are compared with each other through the existing
  `compare()` at the default tolerance (1e-3 relative is about 1 mm on a body, so 9.9 mm shows).
  A difference prints `NONDETERMINISTIC <fixture>: <key>` and fails the run; build `a` is still
  compared with the golden.
- Proof: first `--plugins <worktree at 4f46876> --twice --only dressed_figure` (the checkout before
  the 5.6 fix). That drift came from `object.join` in Belle's build and the sample Figure may have no
  join, so it may not reproduce. If not, prove the check with a `REGRESS_JITTER=1` switch that moves
  one reported value randomly. Record which one proved it.
- `tests/README.md`.

**1b. `fixtures-creatures` - cricket and starfish, generators that already exist.**
- `tests/fixtures/cricket.py`: the rabbit's pipeline on `hopper_samples.cricket` - the orthopteran
  branch of `hop.move_set` (Idle, Walk, JumpLaunch/Air/Land). Time it first (voxel 0.00022); if it runs
  far past the rabbit's 140 s, pass a coarser `voxel=` and say so in the docstring.
- `tests/fixtures/starfish.py`: `radial_samples.starfish` -> `radial.detect(kind="asteroid")` (no
  vision in a fixture) -> `radial.build` -> `radial.skin` -> `radial_moves.move_set` ->
  `export_creature`. Golden: coverage, arms, crawl checks, manifest.
- Both run `--twice` before their goldens are recorded.

**1c. `fixtures-biped-quadruped`.**
- `tests/fixtures/rigify_human.py`: `follow_through.samples.build_bodies(rig=True, walk=False)`'s
  `Figure` without flesh -> `actions.move_set` with every biped role -> `export.export`. Golden: crouch
  and jump hip drop, balance, export checks.
- New `rig_analysis/quadruped_samples.py`: a seeded dog from `hopper_samples._union_mesh` with
  `truth()` joints; `measure.analyze` must see exactly 4 ground contacts. Fixture `quadruped.py`:
  `fit_basic_quadruped` -> bind -> `move_set` (Idle, Walk, Trot, Run, Crouch) -> export, joints scored.
- Folded in from section 2: `fit_basic_human`/`fit_basic_quadruped` enable Rigify themselves;
  fixtures drop `H.enable_addons("rigify")`.
- 03's "done when": revert the ground-root crouch fix in a scratch worktree - only crouch keys move,
  in `mpfb_woman_curvy` (and `rigify_human` if it applies). rig-anything 0.14.3.

**1d. `persist-move-reports` - step 6.** Every `engine_manifest` (locomotion, hop, radial_moves,
flight, swim, maw, octopus) builds from the in-memory `reports` its set function returned; only the
floor is on the action (`hop.py:1093`).
- New `rig_analysis/stored.py`: `store(reports)` writes `action["rig_anything_report"]` as JSON of the
  report through `hop._clean` (moved here: drops `_` keys, rounds) plus `role`; `load(rig_name)`
  returns `{role: report}` from the actions whose stored `rig` matches. Measure a stored report first;
  over ~64 kB, store only the keys the manifests read.
- `store()` at the end of `actions.move_set`, `hop.move_set`/`jump_set`, `radial_moves.move_set`,
  `flight_set`, `swim_set`, `maw_set`, `octopus_set`. Every `engine_manifest`/`export_creature` takes
  `reports=None` -> `load()`. `rig_anything_floor` stays.
- Proof: `rabbit.py` saves `rabbit.blend`, starts a second Blender on it with `_export_only.py`, exports
  without reports, and reports `fresh_session_manifest_equal`. No existing golden value may move (so
  the properties do not leak into the glb). rig-anything 0.15.0; `build_human.py` needs no change.

**1e. `regress-godot` - `--godot <project>`.**
- After the fixtures pass: copy their `.glb` / `.moves.json` into `<project>/_regress/`, `--headless
  --import`, `verify_moves.gd dir=res://_regress`, and `verify_wardrobe.gd` for `dressed_figure`.
  Pass/fail from each `PASSED`/`FAILED` line and exit code. `_regress/` always removed, and ignored in
  grungist-creek.
- First diff the project's `addons/{rig_anything,wardrobe,follow_through}` against
  `plugins/*/godot/addons` (line endings ignored) and warn on drift.
- `verify_moves.gd` checks a walk-to-run ladder; if hopper/radial manifests do not fit it, `--godot`
  covers the biped and quadruped fixtures and the README says so.
- Delete grungist-creek's untracked `tomas_demo.tscn` (references a missing script) so the import is
  quiet.

**1f. `docs-hygiene` - step 8.** A `CLAUDE.md` here: own worktree and scratch subfolder per agent;
`regress.py --jobs 2 --twice` before reporting done (`--godot` when an addon changed); `install.py`
the only install; goldens move only in a reviewed commit; the tooling gotchas below. Update 03's
status block, this file, and the README's missing-fixtures line. A full `--twice` run will be
12-15 minutes with the new fixtures - required before merge, not every edit.

**1g. grungist-creek `blend-hygiene` - step 7.**
- Copy `C:/Users/pauli/Code/Blender/belle_demo.blend` to `belle_demo.backup.blend`, inventory its
  scenes and objects, save `belle.blend` (Belle's scene) and `creature_tests.blend` (the 72 test
  objects) as copies, reopen each and count. Show the counts before retiring `belle_demo.blend`.
- `assets/save_guard.py`: `save_owned(path, scenes)` reads the scene names already in the file on disk
  (`bpy.data.libraries.load`) and refuses to overwrite one holding a scene not in `scenes`. Used by
  `build_person.py` (4 saves), `build_outfits.py` and `build_human.py`. Proof: a headless run against
  a copy with an extra scene refuses.

### 2. Small fixes found along the way

- **rig-anything should enable Rigify itself.** Under `--factory-startup` it is off, and
  `fit_basic_human` dies with `'Armature' object has no attribute 'rigify_colors'`. Fixtures work
  around it with `H.enable_addons("rigify")`. Filed in 02's quirk table. Taken in 1c.
- **5.7 - a deterministic join.** `bpy.ops.object.join` (eyes and hair into a body) writes the same
  faces in a different order every run. wardrobe is immune now and the glTF exporter writes the same
  indices either way, so nothing shipped is affected - but a `.blend` is not reproducible and any
  consumer that walks faces in order inherits the trap. Give rig-anything a `join_into(target, others)`
  that merges through bmesh in the order given, and point `build_human.bake` and Belle's `hair()` at it.

### 3. The large items

- **02 Bone roles and rig profiles.** Name root, pelvis, chest, head and anchors once in
  `bodymap.build`; an MPFB profile carries its quirks. Fixes the class of bug where follow-through put
  both breast bones on Belle's chin. Do before 01: 01's stages get simpler when roles exist.
- **01 Character spec and staged pipeline.** One YAML per character, a stage runner with
  preconditions and saved results, tuned numbers moved into plugin presets. `build_human.py` and
  `build_belle.py` become thin callers.
- **04 Checks that match the eye.** 04a first: wardrobe's hole check counts cloth pressed into a
  crease as a hole. Belle's shorts fail it at 1.71% (limit 0.5%) where the screenshots show no gap;
  the sports top passes at 0.23%. Then review strips written by every export, and a motion critic.
- **05 · 5.2-5.5** - hair (Belle's reads as a helmet), compression garments (her top traces the body),
  skirts, muscle definition. Independent; take them as the look of a character demands.

### 4. Triage the old project notes

`grungist-creek/docs/plugin-improvements.md` predates this round. Some entries are stale; some are
not filed anywhere yet and may still be live - notably `flesh.add_jiggle_bones` stripping weights on a
re-run, the jiggle modifier needing physics-tick processing, the hard `max_offset_m` clamp, and the
volume API gaps (`collision_mask`, `tumble`, `push`). Check each against current code and either
file it under a category in [README.md](README.md) or strike it.

---

## Things that cost time to learn this round

**Running Blender headless**

- Binary: `C:/Program Files/Blender Foundation/Blender 5.2/blender.exe -b --factory-startup --python <script> -- key=value`.
- `bpy.context.window` exists in background mode in Blender 5.2, so scene switching works.
- Rigify is off under `--factory-startup` (see above). MPFB is not: humanform enables it.
- humanform writes to the real library at `~/.claude/humanform/library` unless `HUMANFORM_LIBRARY`
  says otherwise. Fixtures redirect it; ad-hoc build scripts do not.
- A background command's output file stayed empty until it finished - run long builds in the
  foreground with a generous timeout instead.

**Building the project's characters without touching its assets**

`build_belle.py` and `build_human.py` write into `PROJECT/assets/...`. Copy
`assets/humans/` and `assets/belle/build_belle.py` into a scratch folder with the same layout and set
`PROJECT` to it (and `BLEND_COPY`). Point `RA_SCRIPTS`, `HF_SCRIPTS`, `FT_SCRIPTS`, `WD_SCRIPTS` at this
repo's `plugins/<name>/scripts` to test a checkout. A crowd person builds in 10-20 s; Belle in 20 s
warm, a few minutes cold. `who=tomas` needs `C:/Users/pauli/Code/Blender/humanform_hands_feet_demo.blend`
passed as the file to open.

**Verifying in Godot** (`GODOT` = the `_console` build, path in the project's CLAUDE.md)

```
"$GODOT" --headless --import --path .
"$GODOT" --headless --path . belle_demo.tscn -- --selftest
"$GODOT" --headless --path . people_demo.tscn -- --selftest
"$GODOT" --headless --fixed-fps 60 --path . -s res://addons/wardrobe/verify_wardrobe.gd -- \
    body=res://assets/belle/belle.glb garment=res://assets/belle/belle_sportstop.glb \
    frames=240 every=8 hem=true jiggle=true
```

To compare against committed assets, `git show HEAD:<path> > assets/_old/<file>`, reimport, run the
verifier on both, and delete the folder afterwards.

**Finding a nondeterminism** - what worked for 5.6, in order: compare the written files; if they
differ, checksum each stage's output inside two full builds and find the first that disagrees;
checksum that stage's inputs, hashing structure (face order, sorted and unsorted) as well as
positions; then reproduce it minimally, three runs, three hashes.

**Tooling gotchas**

- `git merge -F -` does not read stdin (commit does). Write the message to a file.
- JSON the build scripts write is CRLF on Windows while git stores LF: `git status` lists every
  rebuilt manifest as modified when `git diff` is empty. Trust the diff.
- A rebuilt glb can change for reasons that have nothing to do with the change being tested -
  humanform 0.6.1 adding `"cupsize": null` to the sheet extras grew every crowd glb by 20 bytes.
  Parse the glTF JSON chunk and diff it before believing a binary changed meaningfully.

## Loose ends in the repos

- Merged branches still exist locally: `tooling-wardrobe-install` here; `belle`,
  `belle-jump-unforced`, `humanform-plan`, `tomas-walk` in grungist-creek.
- `grungist-creek/tomas_demo.tscn` is untracked and references a missing `tomas_demo.gd`; Godot logs
  an error for it on every import.
- This repo is public, and `plugins/humanform/data/` (ANSUR II public CSVs and the seed contact
  sheets) is published with it - a deliberate choice, recorded here in case it is revisited.
