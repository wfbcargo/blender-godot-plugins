# Merge notebook: fig-flesh-reporting-and-godot-proof -> main

## 01:31 stage=start kind=win
Code review: 0 blocking, 8 minor. Merge allowed. main at de0c3ed (wardrobe 0.5.0 merged since branch point). Branch commit ca493d3.

## 01:33 stage=merge kind=win
`git merge --no-ff -F msgfile` clean, no conflicts (a3f7bd5), even though main had gained wardrobe 0.5.0 since the branch point. 1 attempt, <10 s.

## 01:35 stage=version-bump kind=win
follow-through 0.5.2 -> 0.6.0, character-pipeline 0.5.0 -> 0.6.0 (new spec field [flesh] may_miss, new manifest block, new verifier args: minor bumps). plugin.json + marketplace.json version + "Since 0.6.0" sentences, edited with a byte-level Python replace (478a65b). install.py 0.2 s.

## 01:36 stage=addon-sync kind=friction
`diff -rq` of plugin addons vs grungist-creek/addons lists 5 follow_through files + every *.uid as different; `--strip-trailing-cr -x '*.uid'` shows only verify_flesh.gd truly differs. Cost ~1 min. Change: tools/ should have a `sync_addons.py --check` that compares ignoring CRLF and .uid files (and lookdev has no addon in the project at all - diff errors on it).

## 01:38 stage=fix-on-main kind=fail
Review minor: verify_flesh.gd `_initialize` had no return after quit(2). Adding `return` alone was NOT enough: `course=fly scene=res://x.tscn` then hit `_start` from `_process` ("cannot load res://x.tscn", backtrace verify_flesh.gd:160 <- :258), because quit() only takes effect at the end of the iteration. Fix: `refused` flag set before each early quit, `_process` returns true at once when set. Verified: course=fly, require=bogus, missing scene each print one line and exit 2. 2 attempts, ~3 min. Plugin/file: follow-through verify_*.gd - every headless verifier with early quit(2) in _initialize should use the same guard (worth a grep of verify_cloth/volume/strands and wardrobe's verifier).

## 01:40 stage=addon-commit kind=win
verify_flesh.gd copied into grungist-creek/addons/follow_through and committed on master (e108495); tomas_demo.tscn left untracked. <1 min.

## 01:41 stage=cleanup kind=win
Worktree removed and branch deleted (`git branch -d` accepted it as merged). <5 s.

## 01:40 stage=regress kind=slow (running)
`python tools/regress.py --twice --jobs 4 --godot C:/Users/pauli/Code/GoDot/grungist-creek` started on main 74ebef8 (--godot because verify_flesh.gd and the export's .moves.json changed).

## 01:54 stage=regress kind=slow
`regress.py --twice --jobs 4 --godot grungist-creek` on main 74ebef8: exit 0, 806 s (13.4 min). 19 fixtures ok twice, "no change" against goldens (the version bump to 0.6.0 moved no golden). Slowest: rabbit 212+211 s, cricket 120+119 s, traced_detail 59+60 s, pipeline_muscle 53+53 s. Godot: verify_moves 12 manifests PASSED; verify_wardrobe 5 ok, 3 controls fail as they must; verify_flesh pipeline_woman full/walk/run PASSED (breast peak 0.057/limit 0.057/stands 0.086, butt 0.080/0.080/0.088, on_limit <=1.0%), 2x peak_m control FAILED as it must for the right reason (breast/butt swung 0.122 m past stand-out 0.086/0.088). No addon drift warning. 1 attempt. My Bash `until grep` wait hit the 600 s tool cap once and was moved to background - use Monitor for >10 min waits from the start.

## 01:56 stage=next-md kind=win
NEXT.md: one status paragraph for this merge before "Installed copies", installed-versions list updated to follow-through 0.6.0 / character-pipeline 0.6.0 (cfeae92).

## Summary
Total wall ~25 min, of which 13.4 min regress. Carry-over for the plugins (from review minors, not fixed here): registry belly limit_share (follow-through builtin.json) so study_man passes jump without a spec line; study_woman breast zone growth eating the belly (flesh.py _grown_zone/ORDER); regress _run_flesh control should assert the failure is within_body; flesh._miss message should say "of the unclaimed vertices"; stages.run_flesh with marked zones lists missed with reason None; manifest missed reasons can be null past runner._small's 4000-char cut; regress --update still writes temp paths into flesh_figure golden.
