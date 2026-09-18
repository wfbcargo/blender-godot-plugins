# gap-genital-anatomy notebook

Branch fig-genital-anatomy at main b496738, worktree .worktrees/fig-genital-anatomy. Scratch wf3/gap-genital-anatomy
(copied draft's build_human.py, save_guard.py, hflib, lit.py; specs re-pointed at scratch blend dir; run.sh -> my worktree).

## 00:34 stage=setup - kind=win
- Read CLAUDE.md, NEXT.md 8-9, draft-lead notebook. Worktree + scratch mirror in 1 attempt, ~4 min.

## 00:37 stage=explore helper-genital - kind=win
- study_man body-only build (to=body) 8 s. On the fitted body the shell is OPEN, not closed: one boundary loop of 34 verts lying -2.4..+1.7 mm from the body surface (signed); 42/200 shell verts up to 3 mm inside; MPFB already weights it 91% `spine` (pelvis) + ~4.5% each thigh. Body edge length at the crotch 21 mm vs shell 11 mm. So no boolean needed: cut footprint + fill the annulus.
- Resolution for plugins: record in humanform genitals.py docstring (done).

## 00:40 stage=fuse v1 (bmesh.ops.bridge_loops, on the unbaked MPFB human) - kind=fail
- bridge_loops with 34 (shell) vs 20 (rim) verts made 21 triangles, 0 quads, and left 35 open edges (should be 0). bmesh's bridge_loops does not handle unequal loops the way the Bridge Edge Loops operator does.
- Also a bug: BMFace used after bm.free (ReferenceError). 2 attempts, ~2 min.
- Resolution: own zipper fill + join_triangles. humanform/genitals.py `_zipper`.

## 00:42 stage=fuse v2 (greedy shortest-diagonal zipper, unbaked) - kind=fail
- 0 open edges, 1 piece, but renders show a faceted shell (182 quads read low-poly in a lit close-up) and a fin/fold at the join; could not smooth or subdivide because the unbaked MPFB mesh carries 70 shape-key layers (editing v.co moves only one layer).
- Resolution: move the fuse AFTER rig-anything bake_for_game (no keys, plain weights): keep() marks the shell with a point attribute `hf_genital` (survives the Mask apply), fuse() subdivides the shell once (Subsurf on a temp split-off object, joined back), cuts, zips.

## 00:45 stage=fuse v3 (baked mesh, subdivided, greedy zipper) - kind=fail -> v4 win
- v3: fin at the top-left of the join (greedy diagonal crossing between a 68-vert loop and a 20-vert rim).
- v4: zipper merges the two loops by angle about the footprint centre (both CCW in the fitted plane). Result: 68/20 loops, 58 seam faces (30 quads), open edges 34 -> 0, one piece, shell shares spine 0.934 / thighs 0.033 each. Lit close-ups clean (look/StudyMan_t3_*.png). fuse 0.5 s.
- 4 attempts total for the fuse, ~8 min.

## 00:49 stage=pipeline study_man (genitals=true, flesh +genital) - kind=win
- First pipeline run passed, rc=0, wall 40 s (draft 34.7 s: body 9.8, muscle 1.1, bake 0.7, hair 0.7, flesh 1.7, moves 11.6, export 5.9, review 2.6). bake report: loops 68/20, open edges 34->0, unweighted 0, shell shares spine 0.934. flesh found `genital` (452 verts, stands 0.056 m out, on spine, facing 5 deg), bone ft_jiggle_genital, max offset 0.0168 m (0.3 x peak). glb carries ft_jiggle_genital.
- gap (not mine): the man's `belly` region is 682 verts at height 0.57 (chest), stands 0.161 m out, 20.9% of the body - follow-through reads a muscled chest as belly. follow-through flesh.py zones.
- follow-through flesh.py still prints numpy RuntimeWarnings (empty slice) on every build (draft-lead noted it too).

## 00:51 stage=thigh intersection check (dev/pen.py, skinning only, 12 frames per clip) - kind=fail
- Shell vertices (>2.5 cm from the join) inside the body: REST 0; Idle 44 (7.8 mm, thighs); Walk 151 (27.3 mm); Run 177 (28.4 mm); Crouch 82 (13.7 mm); Jump 51 (9.9 mm). All against thigh.L/R faces. The pelvis-held scrotum sits 0-1 cm from the inner thighs at rest and the thighs sweep through it.
- There is no check in any plugin for a part entering a neighbouring limb in Blender (humancheck is rest-only; verify_flesh within_body is Godot-side and for jiggle offset only). Should exist: humanform humancheck or rig-anything clip_checks "limb self-intersection".

## 00:53-01:06 stage=thigh intersection fixes - kind=dead-end x2, partial win (5 attempts, ~13 min, 5 rebuilds of ~30-50 s)
Metric: dev/pen.py (shell verts >2.5 cm from the join inside the body, Blender skinning only, 12 frames/clip, worst frame).
- baseline (MPFB weights, thigh share capped 0.06): Idle 44/7.8 mm, Walk 151/27.3, Run 177/28.4, Crouch 82/13.7, Jump 51/9.9.
- A contact weights (thigh takes up to 0.5 where the shell lies within 3.5 cm, +8 mm rest clearance): Idle 0, Walk 104/9.2, Run 137/13.8, Crouch 57/8.0, Jump 29/5.8. At 0.8/5 cm: Walk 4, but Crouch 48/34 mm and visible SPIKES at the join in a crouch (scrotum sides lifted with the flexed thighs): dead-end - linear blend skinning with thigh weight on the scrotum cannot survive 90 deg hip flexion.
- B thigh sweep clearance at bake time (pelvis still, each thigh posed through flex x abd x twist, shell pushed CLEAR_M=6 mm off the swept thigh skin, capped 15 mm, smoothed): v1 24 poses: Walk 142/18.1. v2 126 poses with knee-direction sign logic: Idle 0, Walk 70/15.1, Run 102/15.7, Crouch 26/9.5 (against pubic `spine` skin, not a thigh), Jump 4/6.8. v3 symmetric Euler grid 210 poses: WORSE (Walk 122/19.3, Idle 6/10.9) - opposite pushes from the two thighs overwrite each other; v2 + per-thigh accumulation: same as v2 (kept). Bake stage 0.7 s -> 2.4 s.
- Kept: B v2 (pelvis-dominant weights 0.934 spine). OPEN: Walk/Run still bring the inner thigh 15 mm into the scrotum's side at the worst frame. Real fix needs either a runtime collider (Godot jiggle bone vs thigh capsules, follow-through) or corrective shape keys driven by hip flexion (rig-anything / humanform), not static geometry.

## 01:04 stage=pipeline study_woman (genitals=true) - kind=win
- First run rc=0, wall 27 s (draft 24.2 s: body 3.7 ...). Relief key hfd:genital: mons 4.2 mm (132 verts), labia 2.8 mm (85), cleft -1.1 mm (23); crotch landmark found at z 0.789. Lit close-ups (look/StudyWoman_w1_*): a soft mons and a deeper cleft; the labia pads barely read at hm08's ~2 cm crotch edges - honest: subtle.

## 01:06 stage=humancheck - kind=fail -> fixed (1 attempt, 3 min)
- Woman: 0 fail, 2 warn (7 pieces, 110 open edges - same as draft). Man: 1 FAIL "hip joints 14.4 cm above the crotch (0.081 H)" + WARN crotch 6.7 cm low: measure.py's crotch scan took the scrotum's section (spans x=0, ~9 cm wide) as the crotch.
- Fix: humanform/measure.py `joined` requires the midline loop to be wider than 0.08 H (two thighs). Man then 0 fail, 2 warn: 8 pieces, 120 open edges - identical counts to the draft build without genitals; largest piece 13380 -> 14128 (the shell is in the body's piece).
- Should change: nothing more; the guard is in humanform.

## 01:08 stage=godot verify_flesh (scratch project wf3/gap-genital-anatomy/godot, addons from my worktree) - kind=fail -> win (3 attempts, 4 min)
- Setup: project.godot + follow_through + rig_anything addons copied, import 3 s, verify 1 s. Worked first time.
- soft_fat genital (as the task asked): within_body PASS on walk and run, but FAILED on_limit: 16.7% of the course on its 1.7 cm limit (jump 74 ticks, stop 26, turn 21, run 9, walk 7), free peak 12.2 cm. Physics: soft_fat 2.7 Hz with gravity 1.0 sags g/(2 pi f)^2 = 3.4 cm, twice the limit.
- Probes (verify_flesh limits=/set=): limit 2.2 cm 15.5%, 2.8 cm 11.2%, 3.4 cm 9.4% (passes but not tight); set 6 Hz/0.6/gravity 0.5 (= firm_flesh) 0.5%; 4.5 Hz/0.4/0.7 1.0%.
- Resolution: genital type uses firm_flesh (existing material). Rebuilt: FT_SUMMARY PASSED; genital limit 0.017, peak 0.017, free peak 0.038, on limit 0.5% (4 jump ticks), within_body true, moved true. Deviation from the brief's "soft_fat" recorded in the type's limit_note.
- Should change: follow-through flesh types could carry a size-scaled frequency (f ~ c_s/4R from peak_m) instead of one per material.

## 01:10 stage=fixture pipeline_genitals - kind=win (2 attempts, 4 min)
- New fixture tests/fixtures/pipeline_genitals.py (seeded briefs in TOML, no .blend): man through every stage (genital_shape length 0.4 -> hfg:penis-length-decr 0.2, flesh genital), woman body+bake, hashing neutrality, 6 spec refusals. One run 25 s; --twice --update 22 s + 22 s, the two builds agree (seam ordering made deterministic first: rim edges and smoothed verts sorted by index, since BMEdge sets iterate by address).
- Attempt 1 recorded a numpy bool as the string "True" and anchor_bone null (region dicts carry no anchor); fixed to bool() and the jiggle bone's parent (`spine`).
- Golden: open edges 34 -> 0, body one piece (largest 14130), shares spine 0.934, clearance 407 verts pushed max 14.9 mm, walk frames inside the thighs 10-77 verts / 5.5-13.6 mm (the open issue, now tracked by the golden), glb has ft_jiggle_genital.
- friction: `regress.py --keep` needs a DIR argument (not a flag); cost one call.

## 01:15 stage=final rebuild + look + godot - kind=win / gap
- Final code rebuilt through the pipeline (scratch specs with genitals = true; man flesh types butt, belly, genital): study_man 26 s wall (draft 22.9 s: body 4.4, muscle 0.5, bake 1.8, ...), study_woman 20 s (16.8 s). Godot verify_flesh on the final glb: FT_SUMMARY PASSED, genital within_body true, on limit 0.5%.
- Lit close-ups look/StudyMan_final_{Idle1,Walk9,Crouch6}_{threeq,side,low}.png and StudyWoman_final_*: Idle clean; Walk: scrotum side into the inner thigh at the worst frames (numbers above); Crouch: the flexed thigh covers/swallows the genitals from the side. No tearing at the seam in any frame of the kept version (the spikes were only in the contact-weight dead-end).
- gap: close.py's side camera (0.9 m, from +x) is blocked by the arm and thigh in half the shots; a crotch close-up belongs in the review stage with the camera placed from the jiggle bone (character-pipeline review / rig-anything review.sheet).
- Docs: humanform SKILL.md "Genitals" section + status row; character-pipeline SKILL.md spec fields + body/bake rows; follow-through flesh SKILL.md material table + why firm_flesh. NOT edited (merge agent's): tests/README.md fixture table row for pipeline_genitals, NEXT.md, versions.

## 01:26 stage=regress --twice --jobs 2 (full, 20 fixtures) - kind=fail + slow (~15 min wall)
- 11 fixtures CHANGED: dressed_figure, dressed_presets, dressed_skirts, flesh_figure, hair_presets, mpfb_woman_curvy, muscle_definition, pipeline_muscle, pipeline_ponytail, pipeline_woman, traced_detail. Every build reproduced (twice agreed); pipeline_genitals matched its golden.
- Cause 1: flesh.prepare with no `types` searches EVERY registry flesh type, so the new `genital` type found a 10th region on the sample Figure and the MPFB women (a crotch bulge), moving jiggle bone counts, garment groups, cover counts, glb sizes. Fix: registry `"opt_in": true` - find_regions skips opt-in types unless named in `types`.
- Cause 2: my measure.py crotch-width guard moved MPFB fits (mpfb_woman_curvy stature 1.6985 -> 1.6957, Dante's fitted muscle 0.6443 -> 0.6463): the fit reads crotch height, and a narrow midline section exists at the crotch of plain bodies too. Fix: the width guard applies only to a body carrying the `hf_genital` attribute.
- Should change: follow-through registry docs - any new flesh type silently joins every default search; "opt_in" (or a default types list) should be the rule for new types. humanform measure: crotch detection is fit-critical; its width filter needs a fixture that pins crotch_z.

## 01:33 stage=regress rerun of the 11 + fixes - kind=win
- --twice --only the 11 changed + pipeline_genitals: all 11 `ok` (no change against goldens), 352 s wall at --jobs 2 (kind=slow). pipeline_genitals moved slightly (MPFB fit back to the original crotch reading: clearance pushed 407->403, peak_m 0.0646->0.065, woman landmarks <1 mm) - re-recorded --twice --update, diff reviewed: expected.
- Rebuilt study_man/woman on the final code: humancheck 0 fail both (man 8 pieces/120 open edges, woman 7/110 - same as without genitals); pen.py same as before (Walk 69/15.1 mm, Run 101/15.7, Crouch 26/9.5 vs pubic skin, Jump 4/6.8, Idle 0); Godot verify_flesh PASSED (genital within_body true, on limit 0.5%).
- Commit 2ec1200 on fig-genital-anatomy. Final full regress --twice --jobs 2 started on the commit.

## 01:48 stage=final regress --twice --jobs 2 on 2ec1200 - kind=win / slow
- rc=0, 709 s wall (kind=slow; cricket 152 s and rabbit 128 s per build dominate). All 20 fixtures ok, both builds agree, "no change". (The log prints traced_detail's line twice - cosmetic in regress.py's summary.)
- Session total ~75 min. Open at hand-off: thigh passes into the scrotum in Walk/Run (15 mm) and the pubic skin in Crouch (9.5 mm); female relief subtle at hm08 resolution; tests/README.md row for pipeline_genitals and version bumps left to the merge agent.
