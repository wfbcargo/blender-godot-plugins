# Ship step - realism Step 2, skin (2026-09-19)

Main checkouts, no worktree: install, rebuild the game's six figures, selftests and verifiers, the round's one full
regress, Godot look renders. Merged this round: lookdev-golden-hour, skin-pores-distance, skin-regions,
skin-finger-edges.

## 12:39 install | kind=win
`tools/install.py --all`: character-pipeline 0.14.0 -> 0.15.0, humanform 0.12.0 -> 0.15.0, lookdev 0.7.0 -> 0.10.0;
the rest up to date. Game addons (`diff -rq --strip-trailing-cr -x '*.uid'`): only `addons/lookdev/lookdev_materials.gd`
and `presets.json` differed (golden_hour and the skin changes); copied in.

## 12:40 backups | kind=win
figure_study_man, figure_study_woman, cast_marco, cast_mei, cast_ruth and belle_realistic `.blend` copied to
`%TEMP%/rw/ship/backup/` (overwriting the Step 1 copies there).

## 12:40-12:45 rebuild | kind=win (Mei as before)
`build_human.py who=<id> from=body` (skin.DETAIL and the nail roughness are in the bake hash, so every figure goes
from body), `build_belle.py from=body`, one Blender at a time, all at final:
- study_man 32.5 s (body 5.1, muscle 0.5, bake 6.6, hair 1.1, flesh 0.6, moves 7.5, export 3.9, review 6.8)
- study_woman 31.5 s (bake 7.5, strand 0.1, review 6.7)
- cast_marco 39.1 s (body 7.5, bake 6.7, garments 3.2, review 7.6)
- cast_ruth 40.1 s (body 8.0, bake 7.9, garments 3.3, review 7.3)
- cast_mei: the full build stopped at review on the known `hand_back.L: off_body (no figure at the subject's
  centroid)` false alarm (exit 1, blend not saved); rebuilt `from=body to=export`, 31.5 s, saved. Her close set in
  `review/cast_mei/close/` is from the failed run (same body), so her look sheet is still paired.
- belle 34.7 s (garments 3.0, review 7.3), read_back PASSED.
glbs shrink 16-95 KB (study_man 5318148 -> 5301864, Belle 5514696 -> 5419804, Marco 5725992 -> 5694328).

## 12:45-12:47 Godot | kind=win
`--headless --import` exit 0, 0 ERROR lines. figure_study SELFTEST PASSED (0 failures; ponytail tip swing 51.4 deg,
control 0.03), belle_demo BELLE_SELFTEST PASSED, people_demo PEOPLE SELFTEST PASSED, cast_demo PASSED (0 failures).
verify_moves on all six manifests: MOVES VERIFY PASSED. verify_flesh on all six bodies, full course and
course=walk/run/jump with `require=within_body`: 24/24 FT_SUMMARY PASSED (Marco's butt on its limit 10.9 % jumping
is advisory, the standing jump-course item).

## 12:48 regress on a copy | kind=note
The task named the real game for `regress --godot`; the round's rules forbid that (and the classifier refused it in
Step 1's ship), so it ran on a full tar copy with the rebuilt assets at `%TEMP%/rw/ship/game` after `--import`
(exit 0, 0 ERROR).

## 12:49-12:52 look renders | kind=fail (check), renders written
`lookdev.mjs close-shot --distance 1 --views head,hands,full --presets clear_midday,overcast --pair-blender <close>`
(garments for Belle and the cast) on a second copy `%TEMP%/rw/ship/lookgame`, 13-15 s each. Sheets in
`%TEMP%/rw/ship/look/<id>/sheet.png`; rows face, face_3q, eyes, head_side, head_back, four hand views, full.
**All six exit 1 on one tile: overcast full, FLOOR_STRIPES** (stripe 0.47-0.54 at 8,5 px, contrast 1.20-1.54 %
against 1.20 %, window between the feet). Not caused by this round's figures - an A/B on the lookgame copy:

| glb | views, presets | overcast full contrast |
|---|---|---|
| rebuilt study_man | full, overcast only | 0.86 % (x2, identical) |
| pre-ship study_man (HEAD) | full, overcast only | 0.68-0.69 % |
| rebuilt | full / hands,full / head,hands,full; clear_midday,overcast | 1.21 / 1.25 / 1.25 % |
| pre-ship | same three | 1.24 / 1.30 / 1.30 % |

So overcast rendered **after** clear_midday in one close-shot process reads ~0.4-0.6 % more floor contrast than
overcast alone, on the old glb as much as the new: state carried from the clear_midday preset (shadow filter, atlas or
temporal history) into the next. A faint diagonal dot pattern is visible on the floor between the feet in a crop.
lookdev-golden-hour's notebook had overcast at 0.65 %. Open for lookdev: reset the per-preset state (or render
each preset in its own process) and add a control that renders overcast after clear_midday. Not fixed here (a code
change in the ship step needs a critic).

First look at the sheets (not an independent critic): study_woman's face under overcast shows visible grain at 1 m
and redder lips and cheeks than Step 1; overcast still darker and flatter than clear_midday; the finger webs show no
orange lines.

## 12:48-13:06 regress | kind=win
`python tools/regress.py --twice --jobs 4 --godot %TEMP%/rw/ship/game` (background, waited with Monitor):
`REGRESS DONE exit=0, 23 fixtures ok`, "no change" against the goldens (none re-recorded), 18 min wall. Godot part:
verify_moves (12 manifests) PASSED; verify_wardrobe 5 ok and 3 must-fail controls failing; verify_flesh
pipeline_woman full/walk/run ok, limits=2x control failing; jiggle spring selftest ok, down_ratio=1 control failing;
verify_strands pipeline_ponytail swing_spread 1.035 / start 1.095, both controls failing on their lines; close-shot
pipeline_woman 8 tiles ok (unpaired, as before) with the aim-offset control failing OFF_TARGET; edges pipeline_woman
clean (worst 0.05 per mille) with the old-transmittance control failing (1.29); lookdev selftest 32/32. Standing
warning: mpfb_woman_curvy's volatile `export.file`. Diff file:
`%TEMP%/regress-diffs/regress-20260919-124820-27260.diff`.

## 13:07 commits | kind=win
grungist-creek `588543a` (six figures, their skin PNGs re-extracted by --import, lookdev addon);
`assets/wardrobe/nora.walk.json` rewritten by a selftest again (whitespace only), restored and not committed.
NEXT.md: title, state, Step 2 status, versions, "Where the figures are". Not pushed.

## Time
12:39 -> about 13:10 wall. Six rebuilds 3 min 50 s (plus Mei's failed full run, 36 s); regress the critical path.
No independent look critic was run by this step.
