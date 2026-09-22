# merge-gap-natural-locomotion notebook

## 02:50 stage=survey kind=win
- Branch fig-natural-locomotion (276b7b7, 2 commits: 9ebb810, 276b7b7) based on b496738; main is 7ddabcc, which is 17 commits ahead (skin, brows, flesh reporting, wardrobe 0.5.0).
- Diff touches rig-anything scripts (actions, export, keyposes, locomotion, upper), SKILL.md, tests harness + 2 fixtures, 8 goldens.
- export.py changed, so the final regress needs --godot.
- Wall time: ~1 min.

## 02:53 stage=gate kind=win
- Code-review blocker (vault flattens styles) checked in the branch source, not just the report: `vault` is in STYLE_KEYS (locomotion.py:174-176), elderly_shuffle and heavy walks carry `vault: False`, vault_drop scales the profile by bounce_scale (locomotion.py ~887-895), and rigify_human golden has `styled_walks` (child vault 0-29 mm, elderly 41.0 deg knee). Fixed.
- Visual blockers: looked at evidence/StudyMan_idle_hand.png (thumb lies along the index, no C-grip) and StudyMan_walk_hand_R.png (curl from the base, small gaps between fingers, not a claw). Strips for all 7 roles + manifest/Godot numbers are in the fixer's report. Gate passes -> merge.
- Wall time: ~3 min.

## 02:55 stage=merge kind=friction
- `git merge --no-ff` conflicted in tests/golden/pipeline_woman.json only: main's golden had `moves_json.fields` truncated to {first: arm_pose, last: verified, len: 24}; the branch fixed the harness to keep the full list (23 names, pre-main fields). Took the branch side (full list) and committed the merge a646fa4; the list is expected to miss main's newer field, to be settled by the regress run on the merged tree.
- Attempts: 1. Wall time ~1 min.
- Should change: tests/fixtures/_harness.py `stable(max_list=16)` truncation made every manifest golden conflict-prone; now fixed on this branch (full field list). Goldens that summarise a list should never collapse it to first/last/len for field-name lists.

## 02:58 stage=bump kind=win
- rig-anything 0.23.0 -> 0.24.0 in plugin.json + marketplace.json with a "Since 0.24.0" sentence (66fab34). First try.
- Godot addon check: rig_anything/moves_controller.gd and verify_moves.gd in grungist-creek differ from the repo only by CRLF (diff --strip-trailing-cr empty); the branch changed no .gd, so no addon sync / grungist-creek commit needed. export.py changed -> regress with --godot.
- Wall time ~2 min.

## 02:52 stage=regress-1 started
- (clock correction: earlier entries' times were estimated; real clock at this point 02:52.) `python tools/regress.py --twice --jobs 4 --godot C:/Users/pauli/Code/GoDot/grungist-creek` on 66fab34, log scratchpad/wf3/merge-gap-natural-locomotion/regress1.log.

## 03:04 stage=regress-1 kind=slow
- 12 min wall (02:52-03:04), --twice --jobs 4 --godot. 20 of 21 fixtures ok, every Godot verifier passing (verify_moves 12 manifests PASSED, wardrobe/flesh controls failing as they must).
- CHANGED pipeline_woman: 16 keys, all in manifest.fields - main's `flesh` field (follow-through 0.6.0) now appears at index 8 and shifts the rest; list length 24. Exactly the merge-resolution gap predicted at 02:55 (branch golden predates main's flesh block; main golden had it hidden inside {first,last,len:24}). No number moved. Explained -> re-record pipeline_woman only.
- Slowest fixtures: rabbit 170 s, cricket 102 s, pipeline_muscle 68 s (no repeat of the builder's 910 s).

## 03:06 stage=golden+install kind=win
- `regress.py --only pipeline_woman --twice --update --jobs 2`: 31 s, both builds agree; diff = `flesh` added to fields + the golden's stale plugin-version header (was character-pipeline 0.5.0 / rig-anything 0.23.0...). Committed 4510034.
- gap: goldens carry a plugin-version header that is only refreshed when that golden is re-recorded, so pipeline_woman's said character-pipeline 0.5.0 on a 0.7.1 main. tools/regress.py could refresh or ignore that header so it does not show up as noise in unrelated diffs.
- `tools/install.py rig-anything`: 0.23.0 -> 0.24.0, 7 files changed. First try, <5 s.
- NEXT.md status paragraph written + installed-version list bumped (committed after regress-2).
- Final full regress (regress-2) started 03:05.

## 03:17 stage=regress-2 kind=slow
- Final `regress.py --twice --jobs 4 --godot` on 4510034: 11 min (03:05-03:16), 20 fixtures ok, "no change", verify_moves 12 manifests PASSED, all wardrobe/flesh verifiers passing and controls failing. rc=0.
- friction: the regress log's last line is just "no change"; counting fixtures needed a grep. (The fixture count is 20, not 21 as the fig-realistic-skin NEXT entry says.) regress.py could print "N fixtures ok" in its summary.

## 03:18 stage=close kind=win
- NEXT.md status committed (589e802), worktree .worktrees/fig-natural-locomotion removed, branch deleted (was 276b7b7). Not pushed. grungist-creek untouched (no addon change; tomas_demo.tscn left alone).
- Total merge wall time ~28 min, of which ~23 min regress.
