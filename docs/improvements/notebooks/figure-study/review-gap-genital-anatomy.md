# Review: fig-genital-anatomy (2ec1200)

## 01:49 setup | kind=win
Diff stat read: 12 files, +1223/-8. genitals.py 670 lines new, fixture + golden new, spec/stages/measure/flesh/builtin.json touched. 1 attempt, <1 min.

## 01:52 pipeline build (real specs) | kind=win
Copied draft study_man/study_woman specs into review scratch, added `genitals = true` (+ 'genital' in man's flesh.types), fresh empty hflib. Both built first try through character-pipeline: study_man rc=0 wall 21 s (draft 18.7 s: body 3.4, muscle 1.4, bake 1.6, hair 0.3, flesh 0.6, moves 5.9, export 2.9, review 2.3); study_woman rc=0 wall 19 s. 1 attempt. No change needed.

## 01:57 inspect built study_man (bmesh + skinning sweep over every clip frame) | kind=fail (confirms implementer's open issue)
Own script dev/inspect.py (bmesh pieces/open edges, weights, per-frame signed distance of shell verts to thigh-dominated faces, depth >1 mm = inside). Took 2 attempts (first used wrong object name StudyMan_mesh; the pipeline's mesh is `<Name>_body` - 1 min lost). Wall 12 s.
Result: bake report open_edges 34 -> 0, main piece 0 open edges, 0 non-manifold, 0 unweighted, shell weights spine 0.934 / thighs 0.033 before flesh; after flesh ft_jiggle_genital 0.52 / spine 0.45 / thighs 0.015; ft_jiggle_genital parented to spine (spine is the root's child = pelvis). Thigh intersection worst frame (n verts, depth): Walk 202/14.9 mm f9, Run 257/15.5 mm f4, Crouch 217/27.3 mm f7, Jump 194/16.1 mm f3, Idle 12/2.4 mm f14. Depths match implementer's walk/run (15 mm); my counts are looser (nearest-face sign test). DONE-WHEN "no thigh intersection" NOT met.
Plugin to change: humanform/genitals.py (needs corrective or runtime collider), and humanform/humancheck should gain a posed shell-vs-thigh penetration check so this is measured by the gate, not ad hoc scripts.

## 02:00 lit close-ups (Eevee, sun+fill, own dev/render.py) | kind=fail
8 shots rendered in 5.7 s wall, first try. Idle reads, but the scrotum is a narrow finger-like lobe, not the MPFB helper's round scrotum (compare draft/look/helper_threeq.png). Crouch7 low: shell visibly swallowed by the thigh. Walk9: thigh passes over the scrotum.
Quantified (dev/width.py, 1 attempt, 3 s): lower-shell width/height at 10/30% of its height = 0.23/0.30 fused vs 0.54/0.67 in MPFB base.obj helper -> scrotum ~2.4 cm wide instead of ~5 cm. Cause: genitals._sweep_push adds BOTH thighs' pushes (up to 15 mm each) over 126 poses up to 100 deg flexion, pinching the scrotum from both sides.
Plugin to change: humanform/genitals.py (_sweep_push / MAX_PUSH_M: cap the combined lateral squeeze or preserve volume; or drop the sweep for a runtime collider). humancheck should compare the part's shape to its source.

## 02:03 humancheck both bodies | kind=win (+ friction)
humancheck_cli on the built blends, 7 s each, first try: StudyMan 0 fail / 2 warn (6 pieces, 128 open edges, 0 non-manifold), StudyWoman 0 fail / 2 warn (7 pieces, 110 open edges). crotch_z man 0.867.
Friction: with an EMPTY humanform library the man's body stage takes the `fresh` path and fits 1.8147 m (brief 1.79); the implementer's and the draft's `warm` path gave 1.7881. Not this branch (fit happens before genitals.add) but a fresh fit missing stature by 2.5 cm is worth a humanform/humanlib look. Cost 2 min to rule out.

## 02:08 regress --only pipeline_genitals --twice | kind=win
rc 0, 32 s wall (16 s + 16 s), "ok ... no change": the new fixture is deterministic. Golden records walk_in_thighs (7..74 verts, up to 14.7 mm) as an observed number, not a pass gate - honest but it means the regress would never fail on the defect.

## 02:10 body digest, default-off path | kind=win (after 1 dead-end)
Loaded spec.py from main and branch outside Blender and digested 'body' for the 2 draft specs + 17 grungist-creek characters: all 19 identical. First try failed (dataclass needs module in sys.modules when loaded via importlib - 1 min). Suggest character-pipeline ship a tiny `python -m character_pipeline.spec digest <toml>` for this.

## 02:14 Godot verify_flesh on my own glb | kind=win (+ gap)
Scratch project review-gap-genital-anatomy/godot, addons copied from worktree: import 3 s, verify_flesh 0-1 s, rc 0, PASSED; genital limit 0.018, peak 0.018, free peak 0.038, on limit 0.5% (jump 4 ticks), within_body true. First try.
GAP: within_body only checks peak offset <= peak_m (0.018 <= 0.056) - it never tests the swung skin against the thighs, so it cannot see the 15 mm thigh intersection. follow-through/verify_flesh.gd needs a thigh-capsule (or neighbouring-skin) clearance check for regions between the legs.
Also seen (pre-existing, not this branch): belly on the muscled man limit 0.201 m / peak 0.122 m.

## 02:18 edge specs through the pipeline | kind=fail
Two extra real specs (characters/edge_big.toml: heavy, age 52, genital_shape all 1.0, [muscle] output="normal"; edge_small.toml: slim 1.62 m, age 20, genital_shape all 0.0, no muscle). Built in parallel, 27 s wall each (draft 24.9 / 25.1 s; bake 3.1 / 2.7 s). Topology robust on both: open_edges 34->0, 1 piece at the join, 0 non-manifold, 0 unweighted.
FAIL 1 (edge_big): bake's muscle_normal fell back to rays: "EdgeBig_skin faces is 14144 faces, EdgeBig_muscle_high is 13560" - the high copy is made in the muscle stage (unfused shell, 182 quads) and the fused low differs, so the matched bake is lost for the WHOLE body. Lit render shows a flat faceted collar at the join and a dotted streak down the groin; with the normal link removed (dev/nonormal.py) both vanish -> it is the rays bake. pipeline_muscle / muscle_definition goldens expect method "matched". Fix: character-pipeline stages.run_bake (or genitals.fuse) - bake the normal map before fuse, or rebuild the high copy's shell region, or refuse genitals+normal in spec.parse.
FAIL 2: thigh intersection worse on non-study bodies: edge_big Walk 152 verts / 25.0 mm, Run 23.3 mm, IDLE 48 verts / 10.7 mm; edge_small Jump 25.6 mm, Crouch 19.6 mm. MAX_PUSH_M 15 mm caps the sweep so big shapes stay inside.
Attempts: 3 renders (1 KeyError from my own prefix/tag mix-up, 1 sed quoting miss - 2 min). Plugin: humanform/genitals.py + character-pipeline.

## 02:15 (clock correction: my earlier headings from 01:57 on ran ~5 min ahead of `date`) resume from saved blend, from=bake force=1 | kind=win
rc 0, 21 s wall: bake "already baked" 0.0 s, fuse guarded by hf_genitals_fused, later stages reran. glb: StudyMan_body carries JOINTS/WEIGHTS/UV, no stray hf_genital attribute, ft_jiggle_genital node present. NOTE: the resume saved over blend/study_man.blend (the spec's blend path), so the inspect numbers above are from the first build.

## 02:17 consumer fixtures (flesh_figure, mpfb_woman_curvy), singly | kind=slow
Started 02:07; the 600 s Bash timeout hit and they moved to the background. 5 other Blender processes from parallel workflow agents are competing for CPU, so wall time here says nothing about the fixtures. tools/regress.py should print progress per fixture while it runs (right now the log was empty for 10 min).

## 02:23 consumer fixtures result | kind=slow (flesh_figure) / win
flesh_figure ok, no change, 891 s (CPU shared with other agents' Blenders; the README lists it as a normal fixture, so most of that is contention). mpfb_woman_curvy ok, no change, 22 s. Together these cover the opt_in filter in flesh.find_regions and the hf_genital-only crotch filter in measure.py on bodies without genitals. Working tree still clean.

## 02:24 verdict | kind=gap
Blocking: (1) done-when not met, thigh intersection (study_man Walk/Run 15 mm, Crouch visibly swallowed; edge_big Walk 25 mm and Idle 10.7 mm at rest); (2) the sweep pinches the scrotum to about half its width (0.23-0.30 vs 0.54-0.67 width/height); (3) genitals + [muscle] output="normal" makes the whole-body normal bake fall back from matched to rays, with visible streaks and a faceted collar at the join. Minor: the woman's relief is barely visible, 32 seam triangles, seam UVs are stretched across islands, versions not bumped, the opt_in flag cannot be set through registry.define_type, and verify_flesh within_body cannot catch thigh contact.
Total review wall about 35 min.
