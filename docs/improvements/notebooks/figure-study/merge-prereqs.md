# Merge agent: figure-prereqs -> main

## 00:13 | preflight | win
Code review blocking list is empty, so the branch is mergeable. Branch 8eb64a3 is 1 commit ahead and 11 behind main (aaa5405). Worktree is clean.

## 00:16 | merge | win
`git merge --no-ff figure-prereqs -F msg` merged cleanly (ort auto-merged the three shared goldens: hair_presets, pipeline_ponytail, pipeline_woman). 1 attempt, <1 min.

## 00:18 | version bump | friction
character-pipeline 0.4.0 -> 0.5.0, humanform 0.7.1 -> 0.8.0 (new optional pipeline.make params). marketplace.json has each version twice-ish per entry (plugin.json + marketplace "version" + "Since" sentence); my first script only added the Since sentences and missed the marketplace "version" fields - caught by reading the JSON back. 2 attempts, ~2 min. Suggest: tools/bump.py <plugin> <version> "<since sentence>" that edits all three and verifies. Also: plugin versions feed character-pipeline stage input hashes (plugins.stage_versions), so a humanform bump invalidates every stored body hash - expected, but worth a sentence in CLAUDE.md.

## 00:19 | install | win
`python tools/install.py character-pipeline humanform` first time: 0.4.0 -> 0.5.0 (7 changed, 1 added), 0.7.1 -> 0.8.0 (2 changed). It warned "uncommitted changes in the repo" because I ran it before committing the bump - harmless, but install after commit next time. No Godot addon changed (only Blender-side scripts and fixtures), so nothing synced into grungist-creek and no --godot in regress. The [muscle] output="normal" glb path is opt-in and changes no existing export.

## 00:20 | regress | (running)
`python tools/regress.py --twice --jobs 4` started in background on main 2a1d0f8.

## 00:24 | docs | gap
While regress runs: tests/README.md still said "seventeen" fixtures with no pipeline_muscle row (there are 19 goldens). Fixed: "nineteen", a pipeline_muscle row, and a warning in Comparison that a key with a VOLATILE whole word (build_timing, stage_seconds) drops everything under it (the author nearly lost a golden block to this). humanlib SKILL.md now documents pipeline.make's fit_iterations / fit_detail. Resolution file: tools/regress.py could warn when a volatile key holds a dict (it drops a block, not a duration) - that would make the README warning unnecessary.

## 00:25 | regress | win (slow)
`python tools/regress.py --twice --jobs 4` on 2a1d0f8: 19 fixtures ok, both builds agree, "no change", EXIT 0, wall 9 min 50 s (00:15:07-00:24:57), 1 attempt. Slowest: rabbit 237 s + 235 s, cricket 177 s x2, pipeline_muscle 95 s + 96 s (the author measured 66 s at --jobs 2; at --jobs 4 contention costs ~45%), dressed_presets 61 s, flesh_figure 62 s, pipeline_woman 57 s. --jobs 4 is ~2x faster than the reviewer's --jobs 2 run (22 min). The review's suggested targeted check (--only pipeline_* hair_presets on the merged tree) is covered by this full run.

## 00:27 | goldens | friction
Version stamps in 6 goldens edited in place (humanform 0.8.0, character-pipeline 0.5.0; pipeline_muscle also carried follow-through 0.5.1 / wardrobe 0.3.0 from being recorded on a branch cut before those merged). Regress ignores stamps, so a stale stamp never fails - it just lies. 1 attempt, 1 min. Suggest: regress.py --stamp (rewrite only the plugins block from the run) so nobody hand-edits JSON.

## 00:28 | cleanup | win
NEXT.md status line added, docs committed (b496738), humanform reinstalled for the humanlib SKILL.md edit, worktree .worktrees/figure-prereqs removed and branch deleted. No Godot addon changed, so nothing synced into grungist-creek and nothing committed there. Not pushed. Total merge wall time ~15 min.
