# Lab notebook: skirts-dresses merge (2026-09-17)

## 23:09 | stage: orient | kind: win
- What: read plugins CLAUDE.md; main at 77408f9 (two NEXT.md-only commits past 17e2e8e); worktree skirts-dresses at f1e6d00 present as briefed.
- Attempts: 1. Wall: ~30 s. Resolution: n/a.
- Change: none.

## 23:10 | stage: merge | kind: win
- What: `git merge --no-ff -F <msgfile> skirts-dresses` merged clean, 18 files, +2411/-48. No NEXT.md/docs conflict: the branch never touched NEXT.md, and main's two post-17e2e8e commits touched only NEXT.md/tests/README.md. The expected conflict step was not needed.
- Attempts: 1. Wall: ~5 s. Resolution: n/a.
- Change: none (message-file route from CLAUDE.md gotcha worked).

## 23:12 | stage: opt-in review | kind: win
- What: read the merged diff of the shared paths. cover.compute's new floor_z/max_front come only from cut keys (`cover_floor_z`, `cover_max_front`) that skirts.py sets; hem.prepare's new branch is gated on kind in (skirt, dress); presets.dress keeps shirt/pants on the old path (`ease: null` only in the three new presets; `er is not None` guards added); hem_modifier.gd collides only when the spec block carries `colliders` (written only for skirts); wardrobe.gd builds cloth only for route == soft_body. No existing preset changed (garments.json diff is additive + two new `exclusive` groups). Static read says opt-in; regress goldens are the proof (next).
- Attempts: 1. Wall: ~2 min. Resolution: n/a.
- Change: a merge-time "does this change existing output" check could be automated: regress.py could list which goldens moved vs. main before/after a merge (it only reports pass/fail per fixture).

## 23:10 | stage: bump + install | kind: win
- What: wardrobe 0.3.0 -> 0.4.0, follow-through 0.5.1 -> 0.5.2 (branch touched only its cloth SKILL.md, a docs bump); both plugin.json + marketplace.json with a "Since" sentence; commit 90223e0. `python tools/install.py wardrobe follow-through`: "wardrobe 0.3.0 -> 0.4.0: 13 changed, 1 added"; "follow-through 0.5.1 -> 0.5.2: 2 changed". First try.
- Attempts: 1 (bump done with a Python string edit, CRLF preserved via newline=''). Wall: ~1 min, install 1 s.
- Friction/gap: bumping is hand-editing JSON inside a 3-4 kB one-line description string; a `tools/bump.py <plugin> <version> "<since sentence>"` would make it one call and cannot miss one of the two files. Note: timestamps in the two entries above were estimated before I started reading `date`; real clock from here.
- Change: tools/ (new bump.py) or CLAUDE.md "Bump a plugin's version".

## 23:11 | stage: addon sync | kind: friction
- What: no sync tool exists (tools/ has only install.py and regress.py). Found drift by `diff -rq --strip-trailing-cr` of plugins/<p>/godot/addons/<a> vs the project's addons/ for all three addons: only wardrobe's hem_modifier.gd, verify_wardrobe.gd, wardrobe.gd differed (plus project-only .uid files, expected). cp'd the three, diff stat matched the plugin diff exactly (+597/-14), committed 64eeb40 on grungist-creek master with only those three paths (tomas_demo.tscn left untracked).
- Attempts: 1. Wall: ~1 min.
- Change: install.py could take `--godot-project <path>` to sync addons (regress.py already has addon_drift() listing exactly these files - reuse it), so the sync is one call and cannot skip a file.

## 23:21 | stage: regress | kind: friction
- What: started `python tools/regress.py --twice --jobs 4 --godot <project>` at ~23:11 in the foreground with the 600 s max Bash timeout; it outran it and was moved to the background. Redirected log stays empty until the end (as CLAUDE.md warns), so no progress is visible mid-run.
- Attempts: 1. Wall: >10 min so far.
- Change: regress.py should print each fixture line with flush=True (and ideally a start line per fixture) so a redirected log shows progress; CLAUDE.md's "about 10 minutes" for --twice --godot is at the Bash limit - say "run it with run_in_background and a Monitor".

## 23:28 | stage: regress | kind: slow (and win)
- What: `regress.py --twice --jobs 4 --godot grungist-creek` exit 0, "no change", ~17 min wall (23:11 -> 23:28). 18 fixtures built twice and agreeing; slowest rabbit 217+216 s, cricket 165+164 s (these two are ~half the Blender time). No addon-drift warning (the sync was complete). 11 manifests MOVES VERIFY PASSED. verify_wardrobe: dressed_figure holes 0.000% poke 0.016% (cut=0.04 control fails 1.129%), dressed_presets 0.062%/0.008%, pipeline_woman 0.000%/0.145%, traced_detail 0.000%/0.000% - every existing-garment number identical to NEXT.md's pre-merge run, which with the goldens unchanged is the evidence that merging changed no existing character's output. New dressed_skirts: holes 0.000% poke 0.018%; controls fail as they must: rigid=spine thighs 46 verts (6.53%) poke 0.71%, colliders=false thighs 47 (6.68%) poke 0.52%.
- Attempts: 1, no breakage to fix. Wall: ~17 min (kind=slow).
- Change: tools/regress.py - order fixtures longest-first in the pool (rabbit/cricket start last alphabetically-ish and bound the wall time with --jobs 4); NEXT.md's "about 40 minutes" (jobs 2) vs CLAUDE.md's "about 10 minutes" disagree - measured 17 min at jobs 4.

## 23:31 | stage: golden stamps | kind: friction
- What: the bump left 11 goldens' "plugins" stamps stale (7 wardrobe 0.3.0, 11 follow-through 0.5.1). compare() reads only "report", so the run passed; re-recording with --update would churn temp paths/timings (a known NEXT.md loose end) and cost another ~17 min run. Edited only the stamps in place with a small script asserting one occurrence each; git diff shows exactly 18 stamp lines. Commit c63ea18.
- Attempts: 1. Wall: ~1 min (saved ~17 min).
- Change: tools/regress.py - a `--restamp` flag (rewrite "plugins" in every golden from the current plugin.json versions, touch nothing else), or have the bump tool do it.

## 23:29 | stage: docs + cleanup | kind: win
- What: NEXT.md updated (header paragraph now says skirts merged with the run's numbers; installed versions; status table; fixture count 17 -> 18; item 6 lists the three open items; item 9 unblocked; a lesson on stamps). tests/README.md gained the dressed_skirts row and its controls. Commit aaa5405. `git worktree remove .worktrees/skirts-dresses && git branch -d skirts-dresses` clean first time (branch fully merged). Two other worktrees (compression-on-belle, figure-prereqs at 77408f9) belong to other work and were left alone. Nothing pushed.
- Attempts: 1. Wall: ~3 min.
- Gap: NEXT.md edits are many exact-string replacements across a 395-line file; the "state as of" header, the installed-versions list and the status table repeat the same facts, so every merge must edit three places consistently. Change: docs/improvements/NEXT.md - keep versions in one place (or generate the installed list from install.py).

## Totals
- Wall ~22 min (23:09 -> 23:31), of which regress ~17 min. No failures, no breakage, no conflicts. Commits: plugins 863ffe4 (merge), 90223e0 (bump), c63ea18 (stamps), aaa5405 (docs); grungist-creek 64eeb40 (addon sync).
