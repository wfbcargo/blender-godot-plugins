# Merge notebook: compression-on-belle -> main

## 01:11 | stage: orient | kind: win
Branch head f89f836 (2 fixer commits on c4f4cb3). Main is b496738 (moved past 2a1d0f8 the review saw: figure-prereqs merged). Attempts 1, 1 min.

## 01:14 | stage: gate check | kind: win
Blocking 1 (CRLF): `git ls-files --eol` fit.py = i/lf w/lf attr/text eol=lf; .gitattributes has `*.py text eol=lf`. Fixed.
Blocking 2 (shelf under bust): compared belle-top-fix/tight/sheet.png (after) with p/p0/sheet.png (before), same 0.42 m camera.
Before: separate breasts, pointed polygon rim under each, deep cleavage, overhang tucked in side view. After: cloth spans cleavage and underbust,
breasts read as compressed mounds, side view runs bust to band without a tuck. Residual: a faint faceted corner at the outer-lower breast in
el8 front (top-left, about 5% from the edge) and a soft low-poly crease under the near breast in el8 3/4. Judged fixed (not perfect).
The visual critic's answers were against the pre-fix renders (it cites p0-like spikes); the fixer's new evidence covers detail numbers and bun hair.
Attempts 1, 3 min. Plugin change: the review/critic should be handed the tight camera sheet by default (wardrobe views should offer a close
bust preset), so a far camera never hides this again.

## 01:14 | stage: merge-tree | kind: friction
`git merge-tree` main(b496738) x branch: conflicts in plugins/wardrobe/presets/garments.json and plugins/wardrobe/scripts/wardrobe/cover.py (as the review predicted).

## 01:18 | stage: merge | kind: friction
Conflicts: cover.compute signature (main floor_z/max_front, branch crease) -> kept both, crease appended after behind (all callers pass keywords:
presets.py **_args, samples.py); report dict keeps floor_z, max_front and crease/creased. garments.json "about": both edits (cut list with skirt/dress
+ soft, and branch's `lift`). Resolved with a Python edit normalising CRLF first (per CLAUDE.md gotcha). 1 attempt, 4 min.
Plugin change: presets' "about" is one long line every branch edits -> guaranteed conflict; split it into an "about" object keyed by field.

## 01:22 | stage: version bump | kind: win
wardrobe 0.4.0 -> 0.5.0 (plugin.json, marketplace.json version and "Since 0.5.0" sentence). Stale sports_top note ("0.005 mm smooth, 0.02 mm embossed")
updated to the goldens (0.015 / 0.003 mm). 1 attempt, 3 min. Only wardrobe's Python changed: no Godot addon diff, so no grungist-creek addon sync.
## 01:22 | stage: merge | kind: gap
After the merge, 119 tracked *.py in the working copy are still CRLF while .gitattributes now says eol=lf (`git ls-files --eol` w/crlf attr eol=lf).
git status is clean; they convert on next checkout. Harmless, but tools/ could run `git add --renormalize .` check once. File: .gitattributes / tools/regress.py preflight.

## 01:27 | stage: install | kind: win
`python tools/install.py wardrobe`: "wardrobe 0.4.0 -> 0.5.0: 6 changed, 0 added, 0 removed". First time, <5 s.
## 01:28 | stage: NEXT.md | kind: friction
NEXT.md's "Installed copies" list was stale from the previous merge (humanform 0.7.1, character-pipeline 0.4.0 while the repo is 0.8.0 / 0.5.0).
Fixed alongside wardrobe 0.5.0. File: tools/install.py could print the list, or NEXT.md should stop duplicating versions.
## 01:25 | stage: regress | kind: slow (started)
`regress.py --twice --jobs 4 --godot grungist-creek` started 01:25 (included --godot: sports_top's exported garment changes on every body, as the review asked).

## 01:31 | stage: regress | kind: slow
`regress.py --twice --jobs 4 --godot`: 17 min 54 s wall. 19 fixtures ok, both builds agree, "no change". Godot: every verify_wardrobe ok
(dressed_presets holes 0.064% poke 0.008%, traced_detail 0/0, pipeline_woman 0/0.145%), cut=0.04 control 1.129% fails as it must, skirts
controls fail as they must, MOVES VERIFY PASSED. Longest fixtures: rabbit 249 s x2, cricket 197 s x2 (at --jobs 4 each is ~20% slower than at
--jobs 2). Passed first time: no golden re-recorded (the version stamps are not compared). 1 attempt.
Plugin change: rabbit and cricket are 60% of the critical path; a --quick mode that skips them when rig-anything did not change would cut a
wardrobe-only merge to ~8 min (tools/regress.py: pick fixtures by the plugins they stamp vs the changed plugins).
## 01:34 | stage: NEXT.md + cleanup | kind: win
NEXT.md status line added (de0c3ed). No Godot addon diff since b496738 (`git diff --stat -- '*.gd' plugins/*/godot` empty), so grungist-creek
untouched. Worktree removed, branch deleted. Not pushed. Whole merge: ~25 min, 18 of it regress.
