# Ship step - realism Step 0 (2026-09-18)

Main checkouts, no worktree: install, rebuild the game's figures, selftests, full regress, Godot look renders.
Merged this round: repo-regress-quick, lookdev-godot-tools, cp-resume-hashes, cp-close-look-set.

## 11:34 install | kind=win
`tools/install.py --all`: character-pipeline 0.7.1 -> 0.9.0, follow-through 0.6.0 -> 0.6.1, lookdev 0.3.0 ->
0.4.0, rig-anything 0.24.0 -> 0.25.0; the rest up to date. The game's four addons already matched the repo
(`diff -rq --strip-trailing-cr -x '*.uid'` empty): the lookdev-godot-tools merge had synced them. First try.

## 11:35 backups | kind=win
figure_study_man.blend, figure_study_woman.blend and belle_realistic.blend copied to `%TEMP%/rw/ship/backup/`.

## 11:35-11:37 rebuild | kind=win
build_human.py who=study_man / who=study_woman, then build_belle.py, all resuming from the saved blend
(default). Every stage ran on all three, as expected: the pre-0.8.0 blends carried no stage records.
study_man 31.5 s (body 4.8, muscle 1.5, bake 6.4, hair 0.6, flesh 0.6, moves 7.0, export 3.7, review 6.7),
study_woman about 32 s, Belle 33.1 s (read_back PASSED). Manifests carry `skin.map_px = 2048`, tone_ok;
glbs grew (study_man 3.8 -> 5.2 MB). Each figure has `review/<id>/close/` with 16 tiles + sheet.png +
close.json; Belle has one too.

Belle was rebuilt because the 2048 px final bake changes what she ships. Her committed assets were far
older than that (rig-anything 0.21-era gaits: Walk 0.80 m/s, now 1.22; no baked skin), so the rebuild
brought every round since.

## 11:39 selftests | kind=fail -> fix
`--import` exit 0, no errors (tomas_demo.tscn is gone; its two stale `.godot/editor` state files deleted).
figure_study PASSED (0 failures), people_demo PASSED, **belle_demo FAILED** on one line:
`HAIR lookdev ["Belle_skin", "Belle_hair"] retangented ["belle_Belle_body_001"] drawn: anisotropy 0.5 rim
0.25 transparency 4  BAD`. Every drawn setting was right; the check wanted `LookdevMaterials.apply` to
report exactly one material, and the baked skin is now a lookdev material too. A stale check, not a
regression: it now counts only the `*_hair` entries. Control: filter set to match nothing -> HAIR BAD,
BELLE_SELFTEST FAILED, exit 1. Re-run PASSED. 1 attempt, ~3 min.

## 11:40 verifiers | kind=win
verify_moves (study_man, study_woman, belle manifests): MOVES VERIFY PASSED. verify_flesh on both figures,
full course (all checks) and course=walk/run/jump with require=within_body: 8/8 FT_SUMMARY PASSED. 8 Godot
processes in parallel, well under a minute.

## 11:41 look renders | kind=win
`lookdev.mjs close-shot` (installed 0.4.0) on a tar copy of the project in scratch (regress stages files
into the real one): `--distance 1 --views face,hands,full --presets clear_midday,overcast`, both exit 0,
all tiles over the coverage floors. What they show, all already listed for steps 1-2: helmet-like hair caps
with a hard hairline on both, stippled fingertips and neck under clear_midday, an orange fleck on a finger,
spiky brows; new to note: a vertical specular band down both foreheads under overcast.

## 11:41-11:55 regress | kind=win
`python tools/regress.py --twice --jobs 4 --godot C:/Users/pauli/Code/GoDot/grungist-creek` (background +
Monitor): `REGRESS DONE exit=0, 21 fixtures ok`, "no change" against the goldens, 14 min wall. Godot part:
verify_moves (12 manifests) PASSED, verify_wardrobe on 4 fixtures ok with its 3 must-fail controls failing,
verify_flesh pipeline_woman full/walk/run ok and its limits=2x control failing. One standing warning:
mpfb_woman_curvy's `export.file` is volatile and never compared (already open under repo tooling).

## Time
11:34 -> about 12:00 wall. The rebuild of all three took 1 min 41 s; regress was the critical path again.
