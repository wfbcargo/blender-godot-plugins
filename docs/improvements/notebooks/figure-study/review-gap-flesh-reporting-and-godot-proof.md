# Review: fig-flesh-reporting-and-godot-proof (ca493d3)

## 01:08 - setup - win
Read `git diff main...HEAD` (10 files, +643/-39). 1 attempt, ~2 min. Plan: rebuild both figures through
character-pipeline from the draft specs in my scratch, check log/manifest, run verify_flesh in a scratch
Godot project, run single fixtures pipeline_woman / flesh_figure --twice.

## 01:10 - scratch setup - friction
Copied wf3/draft (hflib, build_human.py, save_guard.py, specs) into review-.../build and sed-repointed `[export] blend`
from draft/blend to my scratch; removed copied blends so the build is fresh. 1 attempt, ~2 min. Same friction the
implementer logged: a spec's absolute `blend` path makes copying specs unsafe (would overwrite the draft lead's blend).
Change: character-pipeline spec.py - allow `blend` relative to BLEND_DIR.

## 01:11 - pipeline build, draft specs, branch code - win
study_woman (draft spec, no may_miss): rc=1 in 7 s, flesh stage raises naming belly with numbers:
"belly: its zone's bulge (146 seed vertices) was already taken by breast (190 vertices) ... stands at most 0.0366 m out
(a seed needs 0.0201 m ...) ... 1 both (a region needs 47); 298 of 298 zone vertices searched, 190 claimed". Log also has
`flesh: found breast/butt` lines. No .blend saved on failure (good).
study_man (draft spec): rc=0, 22 s wall (19.5 s build: body 4.8, flesh 0.7, moves 6.4, export 3.1, review 3.2).
Manifest flesh: butt.L/R (peak 0.0546, limit 0.0491) and belly (peak 0.1652, limit 0.1982 = 1.2 x peak), missed [].
0 RuntimeWarning lines in both logs. First try.

## 01:12 - pipeline build, woman + may_miss=["belly"] - win
rc=0, 19 s. Log: MISSED belly ... "(allowed: [flesh] may_miss)". Manifest flesh.missed = [{belly, claimed, allowed:true}],
regions breast.L/R (peak 0.095, limit 0.063), butt.L/R (0.085 / 0.076). 0 RuntimeWarning. First try.
Note (friction, cosmetic): the "claimed" message's "stands at most 0.0366 m out ... 1 both" numbers are over the
UNCLAIMED zone vertices only, but the sentence reads as if about the whole zone (flesh_figure golden even says
"stands at most 0.0000 m out" for a Bloater whose belly is huge). Change: follow-through flesh.py `_miss` message
should say "of the unclaimed vertices".

## 01:15 - Godot proof, my own scratch project (review-.../godot, addons copied from the worktree) - win + fail
Import 4 s. Each verify_flesh run ~1 s wall headless at --fixed-fps 60. Numbers reproduce the implementer's exactly.
- study_woman (may_miss belly) walk/run/jump require=within_body: PASS. Jump: breasts on limit 10.6% (advisory NOTE).
- study_man, DRAFT spec (belly limit 1.2 x peak = 0.198): walk/run PASS, jump FAILS within_body
  ("belly swung 0.198 m, past 1.00 x its 0.165 m stand-out"). kind=fail, as disclosed.
- study_man rebuilt with `[flesh] limit_share = { belly = 1.0 }` (22 s): walk/run/jump PASS.
- Full course (no args), both figures: PASS all checks. course=jump with all checks on the woman: FAILS (on_limit).
So the done-when's Godot line holds only with a spec edit the draft spec does not have.
Observation (gap): within_body is peak_offset <= peak_m, and peak_offset is clamped at max_offset, so with a limit
<= peak_m within_body cannot fail - on the jump course the free (unclamped) peak is 0.41 m (breasts) / 0.40 m (belly)
against 0.095 / 0.165 m stand-outs; the flesh is slammed into its limit and only on_limit (made advisory) sees it.
The one-motion within_body proof is in effect a static "limit <= peak_m" check. Change: follow-through verify_flesh.gd
could report free_peak/peak_m, or the harness should keep on_limit deciding on walk/run (it is 0% there anyway).
Friction: `course=fly` prints the right error then a SCRIPT ERROR (no `return` after quit(2) at verify_flesh.gd:153);
exit code is still 2. Change: verify_flesh.gd _initialize, return after quit(2).

## 01:20 - flesh.py quiet nan helpers - win
Checked _nanmin_quiet/_nanmean_quiet against np.nanmin/np.nanmean on 500 random half-NaN stacks in Blender's numpy
2.3.4: bit-identical (array_equal, equal_nan). 1 attempt, ~1 min (system python has no numpy; ran via blender -b).

## 01:21 - consumers - win
.moves.json gains one `flesh` key (absent before; the task's "null" meant .get() -> None). Godot readers
(moves_controller.gd, verify_moves.gd, grungist-creek controllers) read named keys only. The only project spec with
[flesh] is belle.toml (breast, butt); her shipped glb has ft_jiggle_breast.L/R and butt.L/R, so the new fail-on-miss
would not break her rebuild (not rebuilt - her blend is the user's). ~2 min.

## 01:14 - regress --only pipeline_woman flesh_figure --twice --keep <scratch>/keep1 - fail (tooling)
flesh_figure ok [54 s + 54 s]. pipeline_woman ERROR after 29 s: "Render error (No error) cannot save:
...\keep1\a\pipeline_woman\pipeline_woman\assets\fixwoman\review\fixwoman\FixWoman_Idle_front.png" - the path is past
Windows MAX_PATH (see length below) because --keep pointed deep into the session scratch. Not a branch defect.
Cost ~3 min. Resolution: rerun with --keep at a short path (C:/t/...) or without --keep. Change: tools/regress.py
could warn when --keep + fixture paths exceed 240 chars; Blender's "(No error)" hides the real cause.

## 01:17 - regress --only pipeline_woman --twice --keep C:/Users/pauli/AppData/Local/Temp/rvf - win
ok [49 s + 43 s], "no change" against the branch golden. flesh_figure ok [54 s + 54 s] in the earlier run.
Total regress wall this review: ~5 min.

## 01:19 - resume a main-built .blend (draft study_woman.blend, same plugin versions 0.5.2/0.5.0) - win
Worried the unchanged plugin versions would let a rebuild skip flesh as "unchanged" and never judge the miss. It does
not: the [flesh] section's hash changed (Flesh gained may_miss), so flesh re-ran (4 s to the named failure). With
may_miss the resume built in 25 s (flesh 1.1, moves 10.2, export 5.8, review 4.0), manifest missed=[belly claimed
allowed]. Side effect to know: every existing [flesh] spec (belle.toml) re-runs flesh -> moves -> export on its next
build even with no spec change. Still, bump follow-through / character-pipeline versions at merge as usual.

## 01:22 - GODOT_FLESH entry reproduced by hand (not via regress --godot) - win
Copied pipeline_woman's kept fixwoman.glb/.moves.json into my scratch Godot project and ran the entry's runs:
full PASS (breasts 0.057/limit 0.057, butts 0.080/0.080, on limit 0.7-1.0%), walk PASS, run PASS (require=within_body),
control limits=2 x peak_m (0.171/0.177) FAILS within_body ("breast.L swung 0.122 m, past 1.00 x its 0.086 m") as it
must; course=jump refuses with rc=2 (no Jump clip), as the entry's comment says. ~2 min, first try.
Gap: the control counts as passing on ANY failure (exit != 0), not specifically within_body; a verifier that breaks
(problems -> FAILED) would also satisfy it. Change: tools/regress.py _run_flesh - require "swung" failures in the
control's report. Also: every region on every body shows free peak 0.122 m on the full course and ~0.037 m on walk -
the course's root motion (scripted hard landing) dominates, so body-to-body differences barely show.

## 01:25 - merge safety: main moved (wardrobe 0.5.0, 257ab62) since the branch base b496738 - win
git merge-tree main + branch: clean (tree 07702ec). Ran pipeline_woman --twice on a git-archive of that merged tree
(--plugins pointing at it): ok [54 s + 50 s], no change, wardrobe 0.5.0. 105 s wall (kind=slow). Deleted temp dirs.

## 01:27 - verdict - win
No blocking defect. Done-when reproduced through the pipeline on real specs: woman fails naming belly with numbers,
passes with may_miss; man's manifest lists butt.L/R + belly; 0 RuntimeWarning; verify_flesh walk/run/jump pass within_body
on both (man only with limit_share belly = 1.0, which the draft spec lacks); both changed fixtures pass --twice, also on
the merged tree. Minor items: man's draft spec fails jump (1.2 x peak belly default), within_body is near-static under
the clamp, control accepts any failure, `_miss` numbers cover unclaimed vertices only, course=fly SCRIPT ERROR,
zones path skips judgement, every [flesh] spec rebuilds flesh->export once, bump versions at merge.
Wall time of this review: ~20 min (builds 4 x 19-25 s, Godot ~15 runs x ~1 s, regress 2 x ~1.5-3 min).
