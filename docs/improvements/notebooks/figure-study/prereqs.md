# Lab notebook: prereqs (branch figure-prereqs)

## 23:09 setup | kind=win
Worktree .worktrees/figure-prereqs from main 77408f9 created first time. Read CLAUDE.md, NEXT.md items 8-9. Wall ~3 min reading.
Findings from reading: muscle.define must run on the UNBAKED humanform mesh (before bake_for_game), so the stage goes between body and bake, not after bake as the task text suggested. Hair "stacking" on main is prevented only by refusal (check_hair); the documented remedy "from_stage=body" looks like it cannot work without force because body's hash is unchanged -> body skipped -> hair refuses again. To verify.

## 23:20 baseline Dante build in scratch | kind=fail (pre-existing) + slow-ish
Dante (dante.toml, forced muscle=1.0) on the worktree plugins, scratch project, redirected library.
First attempt failed: `moves: clips failing their checks: ['Run']` - rig-anything verify.arm_swing:
"the arm swings 53 degrees but never comes back to hanging - nearest 2 degrees in front (limit 2)". This is the
whole-degree print bug from NEXT.md item 8 (a fail at 2.0x prints "2 ... limit 2") AND the predicted crowd
failure from item 9 (Dante's Run carries the arm in front). Not mine (rig-anything). Workaround in SCRATCH spec
only: moves.may_fail = ["Run"]. Attempts 2, cost ~1 min. Fix belongs in rig-anything verify.arm_swing message
(print 1 decimal) and a dante.toml [moves.per_gait.Run] upper.arm_forward tweak like Belle's Trot.
Stage times (s): body 10.9, bake 0.1, moves 6.7, export 3.3, review 3.9; total 25.6 (29 s process wall).

## 23:45 muscle stage through the pipeline on Dante | kind=win
Added spec [muscle] (output geometry|normal, strength 0..2, groups subset of humanform.muscle.GROUPS, normal_size)
and a `muscle` stage BETWEEN body and bake (humanform.muscle.define needs the unbaked MPFB body + its macros; bake
bakes the keys). Normal output: muscle makes `<Name>_muscle_high` (delta.high_copy), bake stage runs lookdev
detail.bake_normal_from_high onto the game mesh (material <Name>_skin), packs the image, deletes the high copy.
Worked first attempt on Dante (scratch spec: dante.toml minus `muscle = 1.0`, plus [muscle] output="geometry"):
weights deltoids .90 pecs .81 abs .64 quads .81 bulk .48, body fat 15.8 %, fitted macro 0.66, spike 4521 um.
Stage times: body 13.9, muscle 2.7, bake 0.2, moves 6.3, export 3.4, review 4.0 = 30.9 s.
Renders (scratch/prereqs): forced_front.png (shipped muscle=1.0: big but smooth), before_front.png (no force, no
stage: average), muscle_front.png (no force + stage: pecs, deltoids, abs, quads defined). Reads muscular.
Friction: bash heredoc with a python edit script containing \\" failed ("unexpected EOF looking for matching `\"'")
- wrote the edit script with the Write tool instead. 1 retry, ~1 min.

## 23:55 item 4 hair stacking on main | kind=gap (fixed on branch)
Probe (scratch/prereqs/test_rebuild.py) on MAIN: Dante + [hair] bun, then preset short_crop, runner.build(ch2):
`StageRefused: hair is already in this file ... rebuild from body (from_stage="body") to change [hair]`. It does NOT
stack (verts 20041 before and after), but the refusal's own advice fails too: from_stage="body" skips body as
"unchanged" (its hash does not cover [hair]) and hair refuses again. So on main a preset change can only be built
with force=True (rebuilds every stage) or a fresh file. 1 attempt, 1 min.
Fix (character-pipeline runner + stages.RESTARTS_FROM_BODY / CARRIED): a whole build (no from_stage or from body)
whose [hair]/[muscle] must rerun on a body that already carries it - or whose spec DROPPED hair/muscle the body
still carries - restarts from body (forced) and records `build.restarted`. from_stage="hair" still refuses
(hair_presets fixture's rebuild_refused unchanged).
## 00:00 muscle added to an already-baked body | kind=fail -> fixed
First run of the probe on the branch: adding [muscle] to a built Dante refused
("muscle needs the unbaked body: Dante_body is already baked"). Restart predicate for muscle widened to "muscled or
baked without the unbaked body". Then a second bug: I used that same predicate for "spec dropped the section", so
every build of a baked body without [muscle] restarted. Split into CARRIED (is it on?) vs RESTARTS_FROM_BODY (can it
go on here?). 3 attempts, ~6 min (each probe run 1-2.3 min because every restart refits the body ~12 s).
## 00:05 quality knob, Dante draft vs final | kind=slow / gap
final 27.8 s (body 13.1 [fit 10.8, fresh], muscle 0.8, bake 0.2, moves 6.1, export 3.2, review 3.9)
draft v1 (review frames 4/front only/160px, fit_iterations 3): 20.1 s (body 8.0, fit 5.8) - ratio 0.72, not enough:
face + hands/feet fits (8 its each) + settle dominated the fit.
draft v2 (+ fit_detail=False: humanform pipeline.make new kwargs fit_iterations / fit_detail, small API change,
draft fits never stored): 17.3 s (body 4.7, muscle 0.6, bake 0.1, moves 6.5, export 3.1, review 2.0) - ratio 0.62.
Draft Dante still reads right (draft_front.png).
Remaining cost is rig-anything's (moves 6.5 + export 3.1 = 56 % of a draft). No knob: role `frames` exists per role but
the gait's default frame count is chosen inside locomotion.cycle from duty, and fps changes the clip's speed, so
halving frames needs halving fps together, per role, inside rig-anything. -> rig-anything should take a
`frame_scale` (or quality) in move_set. Also: Dante's Run fails arm_swing and its retries may cost part of moves.
A library REUSE of the body (<1 s) would be the real draft win, but the pipeline never stores fits (store=False),
so every Dante build is a fresh 11 s fit. -> humanform/character-pipeline: decide whether a final build stores
its fit (regress --twice would then see reuse on the second run; needs thought).

## 00:15 new fixture pipeline_muscle | kind=win + fail found by it
tests/fixtures/pipeline_muscle.py (draft quality, review off): muscle geometry + bun, rerun unchanged, hair -> short_crop
(restart, 15581 verts == fresh short_crop build), muscle -> normal (restart, matched 512 px, high removed), muscle
dropped (restart), from_stage="hair" still refuses, spec refusals, quality table. 60 s per run.
The fixture caught a real bug on its first run: after dropping [muscle] the skin still had the old normal map wired,
because humanform look.material reuses "<Name>_skin" by name. Fix: stages._clear_for (body stage, brief) removes
<Name>_skin and <Name>_muscle_normal. 2 attempts, ~3 min.
Friction: I first named the golden block "timing" - regress's VOLATILE word list drops any key containing
"timing"/"seconds", so the whole block would have been silently uncompared. Renamed "build_record". -> tests/README.md
should say that key names in fixture reports must avoid the VOLATILE words.
Also verified in scratch: Dante with [muscle] output="normal" final: glb Dante_skin has normalTexture, image
Dante_muscle_normal embedded; manifest build block present (bake 2.5 s at 2048 px, matched).
pipeline_woman: its fresh-session manifest_equal now compares with the `build` block set aside (the second Blender's
export-only build writes its own timing).

## 00:35 full regress --twice --jobs 2 (run 1) | kind=slow + fail
Wall ~20 min (rabbit 200 s, cricket 171 s dominate; pipeline_muscle 66 s). 14 ok; CHANGED hair_presets (stage_names
gains "muscle" - expected), CHANGED pipeline_ponytail (manifest.fields 22 -> 23: the new `build` block - expected);
pipeline_woman "NONDETERMINISTIC" fresh_session.tail = my bug: its second Blender dumps
{k: v['status'] for k, v in r.items()} and runner.build's report now has a "build" entry without status -> KeyError
-> exit 1 -> tail differs by temp path. Fixed the fixture's inline code (filter to entries with status). Lesson: a
new top-level key in runner.build's report breaks callers that assume every value is a stage; -> the report's
shape should be documented as {stage: {...}, "build": {...}, "saved": path} (done in runner docstring).

## 00:50 re-record + commit | kind=fail (own) then win
First pipeline_woman fix attempt did nothing: a python str.replace on the fixture's inline code missed (escaped \n in
the source) and my Edit call failed "file not read yet" - I ran regress anyway and burned 2.5 min. Then Edit worked:
pipeline_woman, hair_presets, pipeline_ponytail, pipeline_muscle all --twice --update agree; golden diff is only
stage_names + "muscle", manifest fields 22->23, pipeline_woman fresh_session.build_block. Committed 8eb64a3.
NOT done: a second FULL --twice run after those fixes (the first full run was ~20 min; the changes after it touch only
the 4 pipeline fixtures, which were rerun twice). Merge agent should run the full suite once.
Open for others: dante.toml in grungist-creek should drop `muscle = 1.0` and add `[muscle] output = "geometry"`
(not shipped - task forbids touching grungist-creek); Dante's Run fails rig-anything arm_swing (needs a spec
per_gait.Run upper.arm_forward tweak + rig-anything message decimals); draft can't cut moves/export (rig-anything).
Total wall for the task ~105 min (budget 90).
