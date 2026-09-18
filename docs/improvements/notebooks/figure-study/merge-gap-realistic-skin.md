# Merge notebook: fig-realistic-skin -> main

## 02:34 stage=gate kind=win
- Code review had one blocker (white skin on unbaked export). Author's 0dac898 claims fixed, with skin_detail fixture stage "unbaked export: baseColorFactor = tone, no COLOR_n" and mpfb_woman_curvy golden gaining skin_export. Visual items all addressed per report. Gate passes on paper; will confirm with the fixtures after merge.
- Main has moved since branch point b496738: fig-brows-lashes-hairline (humanform 0.9.0, character-pipeline 0.7.0) and flesh-reporting (follow-through 0.6.0). Expect conflicts in humanform and goldens.

## 02:36 stage=merge kind=friction
- `git merge --no-ff --no-commit fig-realistic-skin`: one conflict, humanform/__init__.py MODULES (main added "brows", branch added "skin"). Kept both. 1 attempt, ~1 min. Everything else auto-merged (hair.py, SKILL.md, pipeline_woman fixture, three goldens).
- Checked the branch's hair.py UV-layer pruning against main's new brows.py: brows builds its cards with bmesh and a single UV, so no hf_detail layer reaches them. No change needed.
- Should change: humanform/__init__.py MODULES as a one-line tuple invites a conflict on every module added; one name per line would auto-merge.

## 02:38 stage=bump kind=gap
- Versions: humanform 0.9.0 -> 0.10.0, lookdev 0.2.0 -> 0.3.0 (plugin.json, marketplace.json, "Since" sentences).
- Also fixed the review's minor finding at merge: character-pipeline plugins.STAGE_READS["bake"] listed lookdev only for a muscle normal bake, but look.skin now bakes with lookdev on every bake. Now always ("lookdev_blender",). character-pipeline 0.7.0 -> 0.7.1. Expect hair_presets stage_version_keys.bake and pipeline_* version lines to move (explained).
- friction: an inline python heredoc in Git Bash lost a backslash ('\' became '\'), SyntaxError. Wrote the script to a file instead. 2 attempts, ~1 min.
- humanform/__init__.py still says VERSION = "0.5.0" (stale since 0.5.0, not read by stage hashes, which read plugin.json). Plugin: humanform - drop it or derive it from plugin.json.

## 02:40 stage=sync+install kind=win
- Only addons/lookdev/lookdev_materials.gd differed (the other addons match modulo CRLF and .uid). Copied, committed on grungist-creek master as a8fc064 (tomas_demo.tscn left untracked).
- tools/install.py humanform lookdev character-pipeline: first try, a few seconds.
- friction: `diff -rq` between repo and project reports every CRLF file as differing; needs --strip-trailing-cr -x '*.uid'. regress.py's own drift check handles this; a tools/sync_addons.py would save the manual diff.

## 02:37-02:47 stage=regress kind=slow (and fail)
- `regress.py --twice --jobs 4 --godot grungist-creek --keep <scratch>/keep1`: ~11 min wall. 19 of 21 ok on both builds, all Godot verifiers ok (moves 11 manifests, wardrobe incl. must-fail controls).
- fail: pipeline_woman ERROR `RuntimeError: Render error (No error) cannot save: '...\keep1\a\pipeline_woman\pipeline_woman\assets\fixwoman\review\fixwoman\FixWoman_Idle_three_quarter.png'` - that path is exactly 260 chars: Windows MAX_PATH, caused by my deep --keep folder, not by the merge. Blender's "(No error)" message hides it. Its verify_flesh runs were skipped as a result.
- Resolution: reran `--twice --jobs 2 --only pipeline_woman hair_presets --godot` without --keep (63 s): pipeline_woman ok twice, verify_flesh full/walk/run pass and the 2x control fails as it must.
- Should change: tools/regress.py - warn when --keep plus the deepest known fixture path nears 260 chars (or use \?\ paths / a short temp root); rig-anything review render - report the path length on a save failure.
- CHANGED hair_presets: only optional_lookdev.stage_version_keys.bake gains "lookdev" - my STAGE_READS fix, explained. `--twice --update --only hair_presets` (31 s): diff = that one line plus the plugins version header. Committed.
- mpfb_woman_curvy ok twice: its golden now carries skin_export (baseColorFactor = tone, no COLOR_n), so the code review's white-skin blocker is confirmed fixed on merged main.

## 02:52 stage=close kind=win
- NEXT.md status line + installed-versions list updated (7ddabcc). Worktree .worktrees/fig-realistic-skin removed, branch deleted (was 0dac898). Not pushed.
- main: 77d8b7a merge, c11b85d bumps, fcb2fbb golden, 7ddabcc NEXT.md. grungist-creek master: a8fc064 (lookdev addon).
- Total wall ~19 min (02:33-02:52), of which ~11 min full regress and ~1.5 min reruns.
- gap left open for the plugins: skin.bake deletes hf_skin_tint so a bake-only rerun flattens regions (humanform/skin.py); quality not passed to look.skin (character-pipeline stages.run_bake); lint.gd name match on "skin" (lookdev/godot/lint.gd); skin.bake temp dir leak (humanform/skin.py).
