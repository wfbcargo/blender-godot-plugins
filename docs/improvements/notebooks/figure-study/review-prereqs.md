# Review: figure-prereqs (8eb64a3)

## 23:55 setup | win
- Read diff stat: 14 files, +849/-33. One commit. Worktree clean. Cost <1 min.

## 00:05 diff read | win
- Read all plugin diffs, fixture and goldens (~10 min). All called APIs exist with the passed kwargs: scaffold.fit_all(iterations=10 default, face, extremities), hair.add(**overrides "subdivide"), review.sheet(frames, views, cell_px), detail.bake_normal_from_high(size, material, name), muscle.define(geometry, strength, weights_override). Final quality passes {} so defaults unchanged; bake's new "muscle" need is filtered out for specs without [muscle], so old hashes hold.
- Goldens: hair_presets stage_names +muscle; ponytail/woman manifest len 22->23 (build block); woman fresh-session compares manifest with build=None. No tolerance widened.

## 00:06 golden pipeline_muscle | gap
- spike_um 4728 > spike_limit_um 4621 (2.3% over) in the recorded golden; the muscle stage does not gate on it. humanform despike doc says six passes leave ~1% over. Not blocking, but the pipeline stores a report where the guard reads as exceeded with no warning. Change: character_pipeline/stages.py run_muscle should warn when spike_um > spike_limit_um * 1.02 (or humanform define should).

## 00:07 author renders | win
- before_front.png vs muscle_front.png: clear pecs/deltoids/abs/quads in AFTER. Done-when #1 visually met.

## 00:01 real-spec probe (probe.py) | win
- grungist-creek dante.toml copied, `muscle = 1.0` removed, `[muscle] output="geometry"`, `[hair] preset="bun"`, may_fail=["Run"] (Run arm_swing fails on current rig-anything, known). One Blender session, 8 builds, 3m21s wall (regress running in parallel, so all seconds inflated).
- final build 41.3 s (body 18.1, muscle 1.1, bake 0.2, hair 1.0, moves 9.6, export 5.5, review 5.3). report/manifest/.blend build records identical. Rerun: all unchanged, 0.1 s, manifest build block untouched.
- hair bun -> short_crop: restarted from body, verts 19123 == a fresh short_crop build's 19123 (no stacking). from_stage="body" -> bob works (20919 verts). [hair] dropped: restarted, haired=[] , 14344 verts.
- draft 15.3 s (body 4.2, muscle 0.6, bake 0.1, moves 7.2, export 2.8, review 0.2, 1 view) vs the no-hair final 22.0 s -> 0.70 (author 0.62). Draft->final rebuild reran body..review (26.5 s) as designed.
- Weights match author's (pecs 0.81, deltoids 0.90, abs 0.64); spike 4521 um vs limit 4422 um (2.2% over, same gap as the golden).
- Attempts: 1. Resolution: item 1, 2, 3, 4 behave as claimed through a real spec.

## 00:02 review dir after draft | friction
- The draft review wrote only *_front.png; the earlier final build's *_right/_three_quarter.png stay in the same review dir, so the dir mixes a draft and a stale final sheet. Change: rig_analysis/review.sheet (or character_pipeline run_review) should clear the character's review dir before writing.

## 00:03 main moved | gap
- Branch base 77408f9; main is 11 commits ahead (skirts-dresses, wardrobe 0.4.0, follow-through 0.5.2, golden version stamps). git merge-tree: textually clean. regress compares only report, not the plugins stamp, so goldens hold unless main's changes move pipeline numbers; the regress run here is on the branch tree, not the merged tree.

## 00:04 [muscle] added to an existing build (probe2.py) | win
- Draft Dante with no [muscle] built, then `[muscle] output="normal"` added: whole build restarted from body, muscled=True, bake baked a 512 px matched map (warnings [], over_5deg 0.167), skin carries Dante_muscle_normal, and the exported dante.glb has normalTexture on Dante_skin. from_stage="muscle" force on a baked file refuses with a clear message. 37 s wall, 1 attempt.
- friction: the restart message for an ADDED [muscle] reads "muscle changed and the body already carries it" - the body does not carry it, it is baked. Change: runner._build should say "the body is already baked" in that branch (stages.RESTARTS_FROM_BODY["muscle"] second clause).

## 00:25 full regress --twice --jobs 2 on the branch tree | win + slow
- `python tools/regress.py --twice --jobs 2`: all 18 fixtures ok, both builds agree, "no change", EXIT 0. It ran alongside the two probes. Wall time about 22 min. Slow (>60 s): rabbit 244+242 s, cricket 157+156 s, pipeline_muscle 74+73 s. The rest took 8-57 s each (pipeline_woman 39, hair_presets 22, pipeline_ponytail 23).
- This closes the author's open item: the full run after the pipeline_woman KeyError fix had not been repeated. It was run on the branch, not on the merged tree with main.
- Attempts: 1. Waiting was hard: Bash `until` loops hit the 600 s cap twice. Change: tests/README.md should say to wait with Monitor or a background Bash, not a foreground loop.

## 00:26 docs | gap
- tests/README.md still says "seventeen" fixtures and has no pipeline_muscle row. The humanform SKILL.md does not mention pipeline.make's fit_iterations/fit_detail (the author flagged this). Change: tests/README.md and plugins/humanform/skills/humanform/SKILL.md.

## verdict
- No blocking defects. All four items work through a real spec (a copy of dante.toml) and the pipeline. Goldens are explained, no tolerance was widened, and --twice agrees. Minor items are above.
