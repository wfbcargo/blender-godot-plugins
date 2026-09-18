# Merge notebook: fig-brows-lashes-hairline -> main

## 02:18 stage=start kind=win
Code review: 0 blocking, 8 minor. Visual critic's 5 blocking items reported fixed by the fix round (780bc30). main at cfeae92; branch base b496738 is in main; branch = 3 commits (6a49d9c, b4aa866, 780bc30), 14 files, +1311/-93 (humanform brows.py new, hair.py ear cut, character-pipeline spec/stages, hair_presets golden). Reviewer already ran git merge-tree against main: no conflicts.

## 02:20 stage=pre-merge-check kind=win
Looked at StudyWoman_face_front.png and godot_man_face.png from the fix evidence: brows read as separate brown hairs, lashes a fringe with no cheek streak, no grey sliver past the brow tail in Godot. Brows/lashes/body_hair are off by default in character-pipeline spec.py (Hair.brows=False), and a false switch hashes as before. The ear cut does change existing hair output (goldens pipeline_muscle/pipeline_ponytail moved in reviewed commit b4aa866) - that is the intended fix, not a failing visual item. <2 min.

## 02:21 stage=merge kind=win
`git merge --no-ff -F merge_msg.txt fig-brows-lashes-hairline` clean, no conflicts (f40c21f). 1 attempt, <5 s.

## 02:22 stage=version-bump kind=win
humanform 0.8.0 -> 0.9.0, character-pipeline 0.6.0 -> 0.7.0 (new hair.add keywords and [hair] switches: minor bumps). plugin.json + marketplace.json + "Since" sentences via byte-level Python replace; commit 4dba28a. install.py humanform character-pipeline: 0.2 s, "5 changed, 3 added" / "4 changed". 1 attempt. Friction (small): version bump is hand-edited every merge; tools/ could have `bump.py <plugin> <ver> "<since sentence>"`.

## 02:22 stage=addon-sync kind=win
No Godot addon file changed on the branch (diff main...branch over *.gd / addons empty), so nothing to sync into grungist-creek and no project commit.

## 02:23 stage=regress (running)
`regress.py --twice --jobs 4 --godot grungist-creek` started on main 4dba28a. --godot included because the exported glb content changes (ear-cut cap; new _brows/_lashes materials when on), even though no addon changed.

## 02:25 stage=cleanup kind=win
Worktree had no uncommitted changes; `git worktree remove` + `git branch -d` accepted (was 780bc30). <5 s.

## 02:33 stage=regress kind=slow
`regress.py --twice --jobs 4 --godot grungist-creek` on main 4dba28a: exit 0, 02:19:25 -> 02:32:57 = 13.5 min. 19 fixtures ok twice, "no change" against goldens (bumps to humanform 0.9.0 / character-pipeline 0.7.0 moved no golden). Slowest: rabbit 173+171 s, cricket 137+137 s, pipeline_muscle 61+60 s, traced_detail 48+48 s; hair_presets 19+19 s. Godot: verify_moves 12 manifests PASSED; verify_wardrobe 5 ok + 3 controls failing as they must; verify_flesh pipeline_woman full/walk/run PASSED, 2x peak_m control FAILED for the right reason. 1 attempt. Friction: my foreground `until grep` wait hit the Bash 600 s cap again and was moved to background (same as last merge) - for a >10 min regress, wait with Monitor (timeout 30 min) only; regress.py could print a one-line `REGRESS DONE exit=N` marker to make the wait filter trivial.

## 02:34 stage=next-md kind=win
NEXT.md: one status paragraph for this merge (with the review's open items: Belle keeps the old ear-covering cap until rebuilt since the hair hash ignores the ear cut, -0.18 mm short_crop clearance, lash sparseness / dark brows in Godot shade, body hair stipple, is_mpfb vertex-count check, stale docs) and installed versions humanform 0.9.0 / character-pipeline 0.7.0 (2a6a954). Not pushed.

## Summary
Total wall ~16 min, of which 13.5 min regress. Merge clean, no fix needed on main. Carry-over for the plugins: humanform hair stage input hash should include a hair-geometry version so the ear cut rebuilds old characters (character-pipeline stages.py run_hair hash); brows.is_mpfb should check topology (humanform brows.py); lookdev hair.strand_texture fine-card mode (lookdev); alpha-to-coverage/mip bias for card materials (lookdev_materials.gd); brow shape brief field (humanform); doc fixes in derive_face_regions.py docstring and humanform SKILL.md.
