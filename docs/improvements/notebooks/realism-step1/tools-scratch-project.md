# tools-scratch-project - lab notebook

Round realism-step1 (Step 0.5 tooling + Step 1 hair, second attempt). Branch `tools-scratch-project` in both
repos. Owns `tools/scratch_project.py`, character-pipeline `spec.py` ([export] blend resolution) and
`runner._save`; not `runner._build` or stage hashes (cp-cascade-stop).

## 13:01 start

Read NEXT.md, CLAUDE.md, 06 rank 2, spec.py, runner.py, build_human.py, build_belle.py, the pipeline fixtures.

Findings before writing anything:
- `[export] blend` is used raw (`ch.export.blend`) in `runner.open_saved` and `runner.build` -> `_save`. A
  relative path resolves against the process cwd today, which is why `pipeline_woman` overrides it with an
  absolute path.
- The export stage hashes the `export` section, `blend` string included. So keeping the *raw string* in the
  section (and resolving only where the file is opened/saved) means a spec copied byte-for-byte to a scratch
  project hashes identically, and its copied blend resumes with every stage "unchanged". That is the design:
  resolve at use, never rewrite the string. Changing the game's specs from absolute to relative moves the
  export hash once (export + review rerun, ~17 s), not the outputs.
- `BLEND_DIR` appears only in docs today (CLAUDE.md, 03); nothing reads it.
- `tools/` changes make `--quick` select every fixture.

## 13:03-13:07 spec.py / runner._save (character-pipeline 0.10.0)

- `spec.resolve_blend(blend, project, blend_dir_override=None)`: absolute as written; relative under
  `$BLEND_DIR`, else the project (folder holding `characters/`), else `$PROJECT`, else cwd.
  `Character.blend_path()`, `save_roots()`, `spec.inside()` (commonpath, not a prefix test).
- `runner.check_save_path` refuses outside project/$BLEND_DIR unless `save_outside=True`; `runner.build` calls
  it **before** any stage runs (a refusal after a 45 s build would be a waste), `_save` again. `build.py
  save_outside=1`. `runner._build` and stage hashes untouched (cp-cascade-stop's seam).
- First fixture run failed: `Cannot open file ...\blends\fixpath.blend@ for writing` - Blender's save does not
  create the folder. `_save` now makes it (a fresh BLEND_DIR). Worked second time.

## 13:06-13:08 tools/scratch_project.py, first attempts

1. Import refused: `ERROR: Blender path is invalid or not set` - the copied .blend files under `<dir>/blends`
   were being imported by Godot. Fix: `.gdignore` in `blends/` and `humanform_library/`.
2. Import refused: `SCRIPT ERROR: Preload file "res://assets/humanoid_actions.glb" does not exist` - root scripts
   of demos whose assets are not copied. Fix: `drop_unresolved` removes root .gd/.tscn/.tres naming a res://
   file the copy lacks (a `%` format path is not a reference), iterated to a fixed point.
3. Import refused: `ERROR: Cannot open file 'res://main.tscn'` - main.tscn was one of those. Fix: take
   `run/main_scene` out of the copy's project.godot when it was dropped.
4. Clean: `--import` exit 0, no ERROR line, 4.5 s for the whole tool. figure_study.tscn and belle_demo.tscn
   survive (all their files are there).
5. Later (13:19) copying a scratch that had been imported crashed: `ROOT_FILES` `*.godot` matched the `.godot/`
   directory. The game worktree had never been imported, so the first runs missed it; the real game would have
   crashed. Fixed (`is_file`), with a test_tools check whose control (the fix reverted) crashes.

## 13:08-13:12 study_man, study_woman, Belle built in the scratch copy by the printed command

`bash <dir>/build.sh study_man` (no other setup). Every stage *ran* (47.7 s): the real blends were built on
humanform 0.10.0 / follow-through 0.6.1 / wardrobe 0.5.0 and the critic round bumped them (docs only), and plugin
versions are in every stage hash - so the resume cannot skip against today's real blends. Not this branch's.
study_woman 44.3 s, Belle 61.6 s. Real blends' mtimes unchanged (11:36/11:36/11:37), game checkout clean.

Outputs against the committed game (regress.compare at harness tolerance, `build.*` timing aside):
study_man, study_woman, belle manifests: **0 changes** each. Control: height_m.stand * 1.01 reported (1 change).
glTF JSON chunks (extras aside): only `meshes[0].name` differs - committed `StudyMan_body.001`,
`StudyWoman_body.001`, `Belle_body.001`, `Shorts.001`, `SportsTop.001`; the scratch rebuild has no `.001`.
The ship step's resumed rebuild left the old mesh datablock in the session, so the new one got `.001`. A resumed
build that reruns body therefore names its glb meshes differently from a fresh one - an open item for the
pipeline (stages/_build, not this seam).

## 13:19-13:21 a copy of a copy resumes

`scratch_project.py proj2 --who study_man --game proj --game-blend-dir proj/blends`, then
`bash proj2/build.sh study_man`: **every stage unchanged, 0.3 s**, saved `proj2/blends/figure_study_man.blend`,
`proj`'s blend not written (mtime 13:08:54 before and after). The spec file was copied byte for byte: no sed.
After the builds, `--import` of the scratch: exit 0, 0 ERROR lines; `figure_study.tscn -- --selftest`:
`FIGURE_STUDY SELFTEST PASSED (0 failures)`.

## Game specs relative

All 19 `characters/*.toml` now say `blend = "<file>.blend"`. `build_human.py` sets `BLEND_DIR` to
`C:/Users/pauli/Code/Blender` only when PROJECT is the game itself; a scratch PROJECT without BLEND_DIR keeps its
blends under itself. Checked without building: every spec resolves (game PROJECT, that BLEND_DIR) to exactly the
file master's absolute path named (19/19); in Blender, build_human imported with no PROJECT/BLEND_DIR gives
BLEND_DIR = the real folder and `check_save_path` allows it; with PROJECT = a scratch, BLEND_DIR stays unset.
The export stage hashes the `blend` string, so the next real build of each figure reruns export and review once
(~17 s); its outputs are the same (above).

**Merge order matters:** the game branch needs character-pipeline 0.10.0 installed first - 0.9.0 would resolve a
relative blend against the cwd.

## Fixture pipeline_paths (new golden, --twice, 28 s + 28 s)

Draft body in project a; spec copied byte for byte to b: saves a/…, b/…, a not rewritten by b; BLEND_DIR set →
blends/…; `runner.plan` of the copy equals the original (control: absolute blend moves export, review).
Refusals before any stage runs (scene emptied first, so a build past the guard would log "body ...") for an
absolute outside path, `../`, and a prefix sibling `c2`; each with a `save_outside=True` control that saves there.
First golden had keys `blend_dir`, `after_blend_dir` - regress treats any key with the word `dir` as volatile and
drops it (it warned). Renamed to `with_env`, `after_env_build`, `env_resolves_to`, re-recorded.
Harness control: `PIPELINE_PATHS_NO_GUARD=1 regress --only pipeline_paths` → exit 1, 15 keys changed (refusals
gone, builds saved outside).

## For NEXT.md (the merge step edits it, not this branch)

Replace the "Building the project's characters without touching its assets" paragraph under "Things that cost
time to learn" with:

> - **Building the project's characters without touching its assets.** From the plugins checkout you want to
>   test: `python tools/scratch_project.py <scratch dir> [--who study_man,study_woman,belle]`. It copies the specs,
>   build scripts, addons (the checkout's), the chosen characters' blends and exports and the humanform library,
>   writes `env.sh`/`env.ps1`, runs `--headless --import` (fails on an ERROR line) and prints the build command:
>   `bash <dir>/build.sh study_man` (about 50 s from a stale blend, 0.3 s when nothing changed). Specs' `[export]
>   blend` are relative (character-pipeline 0.10.0): under `BLEND_DIR`, else the project; a build refuses to save
>   outside both unless `save_outside=1`. `who=tomas` still needs his source blend opened.

And in Step 0.5, the scratch_project bullet: done (branch `tools-scratch-project`, character-pipeline 0.10.0).
