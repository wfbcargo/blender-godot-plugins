# Ship step - realism Step 0.5 + Step 1 (2026-09-18)

Main checkouts, no worktree: install, rebuild the game's figures, selftests, full regress, Godot look renders.
Merged this round: ra-closeup-framing, cp-cascade-stop, tools-scratch-project, lookdev-closeshot-views,
hair-godot-transfer, hair-hairline-lashes, strand-rate-independence (critic-checklists-controls earlier).

## 15:55 install | kind=win
`tools/install.py --all`: animate-anything 0.10.0 -> 0.10.1, character-pipeline 0.9.0 -> 0.12.0, follow-through
0.6.1 -> 0.6.3, humanform 0.10.0 -> 0.12.0, lookdev 0.4.0 -> 0.7.0, rig-anything 0.25.0 -> 0.26.0, wardrobe 0.5.0 ->
0.5.1; godot-lsp up to date. The game's four addons already matched the repo (`diff -rq --strip-trailing-cr -x
'*.uid'` empty): the merges had synced them.

## 15:56 backups | kind=win
figure_study_man.blend, figure_study_woman.blend, belle_realistic.blend copied to `%TEMP%/rw/ship/backup/`
(overwriting Step 0's copies, which were the same files: the blends had not changed since 11:37).

## 15:56-15:58 rebuild | kind=win
build_human.py who=study_man / who=study_woman, build_belle.py, resuming from the saved blends. Every stage reran
on all three (new versions of every plugin in the hashes): study_man 37.6 s (body 6.0, muscle 0.8, bake 9.1,
hair 1.1, flesh 0.6, moves 7.9, export 3.8, review 7.9), study_woman 34.3 s (strand 0.1), Belle 36.5 s (garments
3.0; read_back PASSED). One Blender at a time. study_man's hair/lash strand PNGs and both figures' lash PNGs
changed (edge hairs, denser lashes); glbs 5.23 -> 5.32 MB (man), 5.69 -> 5.71 MB (woman), 4.81 -> 5.51 MB (Belle,
now with brows and lashes). Manifest diffs are small numeric drift (balance margins, lowest-bone frames).

## 15:58 selftests and verifiers | kind=win
`--import` exit 0, no ERROR lines. figure_study SELFTEST PASSED (0 failures; study_woman strands on the run: tip
swing 51.4 deg, off-control 0.03), belle_demo PASSED (HAIR line now lists Belle_skin, Belle_hair, Belle_brows,
Belle_lashes: OK), people_demo PASSED. verify_moves on the three manifests: MOVES VERIFY PASSED. verify_flesh on
both figures, full course and course=walk/run/jump require=within_body: 8/8 FT_SUMMARY PASSED. 48 s in all.

A demo selftest rewrote `assets/wardrobe/nora.walk.json` with tab indentation (whitespace only); restored, not
committed. Which selftest writes it is not tracked down (open, small).

## 16:00 regress refused on the real game | kind=fail -> workaround
`regress.py --twice --jobs 4 --godot C:/Users/pauli/Code/GoDot/grungist-creek` was refused by the auto-mode
permission classifier ("Interfere With Workloads"): regress stages fixture exports into the project it is given.
The round's rules also say regress --godot runs only on a worktree or scratch copy, so it ran on a full tar copy of
the game (rebuilt assets included) at `%TEMP%/rw/ship/game`, after `--headless --import` there (exit 0).
The ship task's line for this step should name a scratch copy.

## 16:00-16:02 look renders | kind=win
`lookdev.mjs close-shot` (installed 0.7.0) on a second copy (`%TEMP%/rw/ship/lookgame`): `--distance 1 --views
head,hands,full --presets clear_midday,overcast --pair-blender <close dir>` (Belle with `--garments` top and
shorts), all three exit 0, about 20 s each. Rows: face, face_3q, eyes, head_side, head_back, palm and back of each
hand, full; the Blender tile first. Sheets in `%TEMP%/rw/ship/look/<id>/sheet.png`.
First look (not an independent critic): study_man's hairline now has fine edge hairs instead of a spiky comb, but
the cap is still a smooth dark shell with a hard front line; brows and lashes read as hair at 1 m on all three;
Belle has brows and lashes; the vertical specular band on study_woman's forehead under overcast is still there
(Step 2's).

## 16:00-16:21 regress | kind=win
`python tools/regress.py --twice --jobs 4 --godot C:/Users/pauli/AppData/Local/Temp/rw/ship/game` (background,
waited with an until-loop; a `Monitor` tail was refused by the permission classifier): `REGRESS DONE exit=0, 23
fixtures ok`, "no change" against the goldens (none re-recorded), 21 min wall. Godot part: verify_moves (12
manifests) PASSED; verify_wardrobe 5 fixtures ok and 3 must-fail controls failing; verify_flesh pipeline_woman
full/walk/run ok, limits=2x control failing; verify_strands pipeline_ponytail swing_spread 1.035 / start 1.095,
both controls failing on their named lines (legacy 1.31/1.39, smooth_hz:0 1.28 start); close-shot pipeline_woman
8 tiles ok (unpaired: the close_off case removes its close set, already open) with the aim-offset control
failing OFF_TARGET; lookdev selftest 21/21. Standing warning: mpfb_woman_curvy's volatile `export.file`.
Diff file: `%TEMP%/regress-diffs/regress-20260918-160013-41164.diff`.

## Time
15:55 -> about 16:25 wall. The three rebuilds took 1 min 48 s; regress was the critical path (21 min against
Step 0's 14, two more fixtures and the strands/close-shot Godot rows).
