# Review: compression-on-belle (sports_top on Belle)

## 00:23 - setup - kind=gap
- What: fit.py diff shows 2022 lines changed (+1308/-1031 overall) for a feature that adds two functions. Checked line endings to see whether the whole file was rewritten.
- Attempts: 1. Wall time: <1 min.
- Resolution: see next entry.

## 00:25 - diff read - kind=fail
- What: fit.py was rewritten with CRLF line endings in cc4f5f4 (56d2c1b is still LF): 1062 CRLF lines plus 9 lines ending "\r\r\n" (the new `_vertex_normals` and the blank lines after it, fit.py lines 430-438). `git ls-files --eol` reports `i/-text` - git now classifies fit.py as NOT TEXT in the index; every other file is i/lf. `git diff --stat` shows +1062/-960 for what `--ignore-cr-at-eol` shows is +105/-3. Python still parses it (lone CR is a newline) but it breaks diff, blame and any merge of fit.py from another branch.
- Attempts: 1. Wall time: 2 min.
- Resolution: blocking. Fix: normalise fit.py to LF (`git add --renormalize` won't help with -text; rewrite with LF, check `git ls-files --eol` says i/lf).
- Change: the implementing agent's edit path wrote CRLF (core.autocrlf=true + a Windows write of the file). Add `*.py text eol=lf` (and *.json, *.md, *.gd) to blender-godot-plugins/.gitattributes, and a regress.py / pre-commit check that fails on a CR in any tracked text file.

## 00:27 - merge check - kind=friction
- What: branch base is 77408f9; main moved to 2a1d0f8 during the work (skirts-dresses merge 23:09, wardrobe 0.4.0 23:10, character-pipeline 0.5.0 00:15). `git merge-tree main compression-on-belle`: CONFLICT in plugins/wardrobe/presets/garments.json and plugins/wardrobe/scripts/wardrobe/cover.py (main's floor_z/max_front signature vs the branch's crease). presets.py, SKILL.md, both goldens auto-merge.
- Attempts: 1. Wall: 1 min.
- Resolution: merge agent must merge main in, resolve both conflicts, and re-run regress (dressed_skirts did not exist on the branch's tree; the goldens were recorded without wardrobe 0.4.0's version stamps).
- Change: workflow script should branch from current main or merge main before the review stage.

## 00:32 - setup independent Belle build - kind=win
- What: fresh scratch proj (review-belle-top/proj) from grungist-creek HEAD characters/belle.toml, build_belle.py, build_human.py, save_guard.py; `git apply --include=characters/belle.toml --include=assets/belle/build_belle.py belle_spec_ready.patch` applied first try; blend path sed-ed into scratch; HUMANFORM_LIBRARY copied fresh from ~/.claude/humanform/library (not the implementer's copy). All *_SCRIPTS env vars point at the worktree. ~3 min.
- Also started `regress.py --only traced_detail dressed_presets --twice` (no --update) in background.

## 00:26-00:27 - full pipeline build of Belle (force=1, renders=) - kind=win
- What: `blender -b --factory-startup build_belle.py -- force=1 renders=...` on the patched spec, worktree plugins: exit 0, 45 s wall (body 6.4, bake 0.2, hair 0.6, flesh 1.2, moves 12.4, garments 5.7, export 6.6, review 5.6). read_back PASSED. 1st try.
- Friction: the garments stage prints no detail/lift/folded numbers (stages.py line 474 keeps only verts/cut/cover/jiggle_groups/export/passed). Had to write measure.py to reopen the blend and re-measure. Change: character-pipeline stages.garments should keep `ease.detail.regions`, `lifted`, `folded_faces` in its report.

## 00:29 - measure the built top - kind=win
- Belle SportsTop as built: detail all 0.044 mm (traced 0.040) vs limit 0.06; breast 0.064 (unlimited); cover recomputed: hidden 876, creased 15, inside 7, drawn_over_cloth 0; blend's wd_hide group == recomputed (876, identical). Matches the implementer's 0.044 exactly (deterministic across two separate builds). 15 s.

## 00:30 - verify_wardrobe 21 runs with the branch's addons - kind=win
- 21/21 pass, 73 s at -P 4 (+4 s import). top worst holes 0.328% (Jump), poke 0.257% (Trot); shorts worst holes 0.392% (Walk); both worst 0.211% holes / 0.267% poke. Identical to the implementer's numbers to 3 decimals. A wrong clip= fails setup (verify_wardrobe.gd:182), so the full names were really used.

## 00:30 - regress --only traced_detail dressed_presets --twice (no update) - kind=slow
- ok both, builds agree, "no change" against goldens. 195 s wall (run beside the Belle build). `git status` clean after.

## 00:33 - verify_wardrobe 21 runs with MAIN's addons (post-merge verifier, thigh check) - kind=win
- 21/21 pass, identical numbers to the branch's addons. 72 s. cut=0.04 control on the top: Walk fails 1.31%, Jump fails 1.64% (as it must). 2 runs, ~20 s.

## 00:35-00:40 - close renders, before/after at one tight camera - kind=fail
- What: render_saved.py at distance 0.8 (the implementer's) is too far to judge the rim; re-rendered at focus (0,-0.12,1.11) distance 0.42, el 8 and -20. Then redress.py: same saved blend, SportsTop dropped and re-dressed with MAIN's wardrobe vs the BRANCH's, same camera (both processes in parallel, ~15 s).
  - main: detail 0.171, 10 drawn over, 4 lifts (20/7/6/7 tris) - NEXT 9 reproduced exactly. branch: 0.044, 0 drawn over, 2 lifts (10/4), folded 0.
  - Visual: the dark wedge at the bottom of the cleavage is gone. But the faceted, pointed rim under each breast is essentially the same in both: in the front el8 view the outer-bottom corners (after ~x190/710 y500, before ~x230/690 y510) are the same sharp polygon, and in the side view the cloth still tucks up under the breast's overhang exactly as before. The shelf is the cloth following the body's 1.9 cm underside, not spanning from breast to ribs.
- Resolution: done-when "close front/3-4 render shows a smooth compressed top with no shelf" is NOT met; the implementer's summary says "the pointed shelf is gone" - the tight renders say otherwise (only the wedge is gone). Blocking. Renders: review-belle-top/tight/el8/*, review-belle-top/redress_main/el8/* vs redress_branch/el8/*.
- Change: wardrobe needs a real span under an overhang (e.g. settle the cloth with a convex-hull / one-sided membrane under the breast, or ease against the compressed body's lower hull), and the review camera in build_belle outfit renders (2.9 m) and render_saved (0.8 m) is too far to see this - add a close under-bust camera to character-pipeline's review stage.

## 00:42 - goldens and consumers - kind=win
- Goldens: traced_detail adds top_pressed_cone_lift (0.038/0.058 mm, 3 lifts) beside smooth top_pressed (0.003/0.0, 2 lifts); new keys folded_faces/creased/settle are additive. dressed_presets sports_top on the sample figure: cloth_relief 0.096 -> 0.038 but traced 0.761 -> 0.962 and relief_mm 0.025 -> 0.032 (disclosed). Limit still 0.06 everywhere; no tolerance widened.
- Stale text (minor): garments.json sports_top note still says "0.02 mm on the smooth sample figure"; the golden now holds 0.032.
- Consumers: cover.compute(crease=0), lift_over(smooth=0), ease(settle=0) all default off; only sports_top opts in; samples.py / layer_cover calls unaffected. After a merge with main, cover.compute has both main's floor_z/max_front and crease - resolve by keeping both.
- 5 min.

## 00:44 - verdict - kind=fail
- Blocking: (1) fit.py committed CRLF with 9 "\r\r\n" lines, git classifies it -text; (2) done-when visual not met - the faceted rim/overhang shelf under each breast is unchanged against main at a tight camera; only the wedge is gone.
- Minor: branch conflicts with main (garments.json, cover.py) and its goldens/regress predate wardrobe 0.4.0 and dressed_skirts; stale 0.02 mm note; character-pipeline garments hash ignores preset contents (force=1 needed after merge); garments stage report drops detail/lift/folded numbers.
- Whole review wall: ~22 min (00:22-00:44).
