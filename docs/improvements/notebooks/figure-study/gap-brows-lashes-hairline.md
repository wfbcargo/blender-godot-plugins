# gap-brows-lashes-hairline notebook

Worktree: C:/Users/pauli/Code/blender-godot-plugins/.worktrees/fig-brows-lashes-hairline (branch fig-brows-lashes-hairline from main b496738).
Scratch: scratchpad/wf3/gap-brows-lashes-hairline

## 00:34 stage=setup - kind=win
- Worktree created first try; read CLAUDE.md, NEXT.md 8-9, hair.py (1125 lines), stages.run_hair. ~6 min reading.

## 00:45 stage=inventory - kind=gap
- The task says "MPFB 'ears' group": there is none. base.obj groups are body/helper-*/joint-*; mesh_metadata/basemesh_vertex_groups.json has only HelperGeometry, JointCubes, Left/Mid/Right, body and the helper-* groups. The baked body keeps only bone groups (StudyMan_body: spine..toe.R + ft_jiggle_*), so no MPFB grouping survives the bake at all.
- Found instead: the ear *targets* (targets/ears/*.target.gz, 44 files) touch exactly 1030 body vertices, all < 13380; eyebrow targets 838 body vertices.
- Verified: baked body vertices 0..13379 ARE MPFB base indices (13378/13378 body quads identical by vertex index on the draft StudyMan). So any base-mesh vertex set can be precomputed to a humanform data file and applied after bake. 1 attempt, ~2 min.
- Should change: humanform should carry base-index region lists (ears, brows, lash proxy fits) as data - done in this branch (data/face_regions.json).

## 00:36-00:44 stage=derive face regions (ears, lash cards, brow cards) - kind=dead-end then win
- New generator humanform/scripts/derive_face_regions.py (Blender, 3-4 s) writes data/face_regions.json (36 KB): ears per side (base indices), MPFB lash helper cards (125 verts / 92 quads per side) and a generated brow card (16x4 grid) per side, each card vertex as a proxy fit (body triangle + barycentric + normal offset in triangle-size units; refit error 0.8 um).
- Lash + brow placement right first time (probe render on the draft StudyMan at rest: brows on the ridge, upper+lower lash cards on the lids).
- Ears took 4 attempts, ~6 min: (1) ear trans-* targets (their falloff reaches the jaw), (2) standing out of a quadratic skull fit (1 vertex, then the cheek), (3) Laplacian-smoothing displacement (whole head shrinks, 317 verts incl cheek), (4) union of l/r-ear-{flap,wing,lobe}-* targets at >5% of each target's max: 359 verts per side, exactly the ear + one ring. BUT attempts 2-3 were judged on a probe render where the draft body's *joined hair cap* sat over the ear (the very bug being fixed), so the ear looked unselected; one of them may have been fine. Lesson: a probe that colours body vertices must first delete the joined hair faces (material *_hair).
- Probe gotcha: the draft .blend's rig was left posed (pose_position POSE at a clip frame), so rest-space reconstructions rendered 5 cm off the evaluated body. Set armature pose_position=REST in probes.
- Should change: humanform views/sheet could offer "colour these base indices" as a debug view.

## 00:44-00:49 stage=implement brows.py + hair.py ear cut + pipeline [hair] switches - kind=win
- humanform/brows.py (new): cards rebuilt from data/face_regions.json proxy fits, weights interpolated from the ridden triangle, lookdev hair material per part with its own strand overrides (lashes doubleSided), optional body hair shell. hair.py: landmarks carry the ear vertices + a KDTree, signed_distance takes min(hairline, dist-to-ear - ear_clear_m), _cap drops faces touching an ear vertex, cap report gains ear_covered_verts. character-pipeline spec [hair] brows/lashes/body_hair (bool, default false; section() drops false switches so no existing hash moves) -> run_hair passes them (+ sex for body hair).
- NOTE: character-pipeline is not a plugin I own; the edit is the minimum to expose the switches through a spec (task asks for it). Merge agent: bump character-pipeline too.

## 00:49 stage=build study_man (draft, brows+lashes) - kind=win / fail
- Pipeline build first try rc=0, 37 s (hair stage 0.8 s). humancheck 0 fail 2 warn (12 s).
- fail: brows invisible in hair.png (EEVEE) but present in the workbench closeups. Cause: new BMVerts have index -1/stale until bm.verts.index_update(); UVs were assigned by loop.vert.index before the update, so every loop got uv[same]. Fixed in 1 attempt (~2 min). Should change: humanform hair/brows helpers - a shared "mesh from points+faces+uvs" util would avoid it.
- friction: humancheck_cli needs body=<Name>_body (not the character name); KeyError otherwise.

## 00:50-00:53 stage=tune (ears, brows, lashes) - kind=friction
- Ear set at 5% of target max took a ring of scalp incl. the sideburn in front of the ear -> bald 2 cm band round the ear. EAR_SHARE 0.3 (259 verts/side) = ear only; hair now wraps the ear closely, ear clean in lit side close-up. ear_clear_m -0.003 in hair_presets.json hairline.
- Brows too thin/sparse with root_zone [0.02,0.5]/tip [0.5,0.98] (no opaque middle); root [0.02,0.3]/tip [0.6,0.98], 90 strands/tile, darken 0.6 reads as a brow in the lit front close-up.
- Lower lash card (MPFB's is as long as the upper) read as a black eyeliner band: generator now draws it to 45% toward its roots and normalises V per lid.
- Each iteration: rebuild 31-37 s + humancheck 12 s + lit renders 10 s = ~1 min.

## 00:54-00:57 stage=glb + Godot scratch import - kind=win / friction
- glb: StudyMan/StudyWoman _hair, _brows, _lashes all alphaMode MASK with base colour + normal texture and lookdev extras (preset hair); lashes doubleSided. 2.2 / 2.4 MB.
- Godot scratch project (scratch/godot: project.godot + addons/lookdev copied from the worktree + my shot.gd, windowed off-screen): --import 3.8 s, render 7.7 s. LookdevMaterials.apply picked up all three materials; no black cards.
- friction: first shots were of the back of the head - glTF front is +Z in Godot. Cost 1 rerun.
- gap -> fixed: with the hair preset's transparency=4 (depth pre-pass) the brow read as a hard dark stroke over a grey haze and the lash cards as grey eyeshadow: every sub-cutoff strand fringe is alpha-blended. brows.py now writes godot transparency=2 (scissor) into the lookdev extras for brows/lashes/body hair (lookdev's material() takes a whole `godot` override). After: crisp strands, no haze (godot/shots/*_face.png). 1 attempt, ~2 min. Should change: lookdev hair preset could offer a "card" variant with scissor for fine cards.

## 00:58-01:03 stage=fixture hair_presets - kind=fail then win
- Added: per-preset cap.ear_covered_verts, landmarks.ear_vertices, a `face` block (control without ear cut, brows/lashes/body hair counts, weights, skin distance, glTF materials + texture hashes) and `face_spec` (parse, refusal, unchanged digest).
- fail: first ear-coverage metric (nearest cap point within 12 mm and vertex under it) gave 133 with the cut - it counted ear-root vertices next to the cap's edge. Metric 2: an ear vertex facing out of the head whose normal ray meets the cap within 2 cm -> 0 with the cut, 430 without (control). 1 extra attempt, ~2 min.
- Fixture run 20 s (--only), --twice --update 21 s at jobs 2.
- Golden moves (reviewed): every preset's cap loses the ear faces: faces_from_body 1204 -> 636 (short_crop 1176 -> 614) - the old cap covered BOTH EARS entirely (568 body faces); boundary_verts 204 -> 412 (the ear holes); boundary_d_mm max 2.7 -> 12.0 mm (boundary verts round the ear sit up to 12 mm inside the hairline curve; boundary V still <= 0.003 so still the transparent root zone); cap_min_clearance 0.30 -> 0.11 mm (short_crop 0.42 -> -0.18 mm: one cap vertex 0.18 mm inside the skin, at the ear crease - open); uv_tangent_turn over_35 falls (ponytail 120 -> 32); stage.body_verts 19411 -> 17241.

## 01:02-01:03 stage=body hair through a spec (study_man_bh, body_hair=true) - kind=gap (left off by default)
- Spec -> pipeline build rc=0, 35 s; body hair shell joined. Lit renders (look/StudyManBH_{torso,forearm}.png): forearm/shin hair reads as short dashes in regular rows (every band repeats identically every 14 mm along V -> a grid of dots); chest/belly/pubic practically invisible at 2.2 m. Not good enough to turn on; it stays default-off and is recorded open. Should change (humanform brows._sparse / _body_hair): per-strand random V offsets and lengths inside a band (or a dedicated sparse-hair texture generator in lookdev), denser torso regions, and a check that counts drawn hair pixels per region.

## 01:02-01:10 stage=regress (single, jobs 2) - kind=slow
- 8 min wall. 19 fixtures: 17 ok, 2 CHANGED - pipeline_muscle (built.verts 16323 -> 15805, three 15581 -> 15065) and pipeline_ponytail (body.verts 19411 -> 17241). Only vertex counts, by the removed ear faces of the cap. Slowest: rabbit 207 s, cricket 166 s (unrelated to this change).
- Re-recorded those two with --only a b --twice --update --jobs 2 (1 min 41 s); git diff tests/golden shows only the 5 verts lines. Committed 6a49d9c (feature + hair_presets golden) and b4aa866 (the two goldens).

## 01:17-01:32 stage=regress --twice (final, jobs 2) - kind=slow (15 min) / win
- 19 fixtures, each built twice and agreeing, no change against the goldens. rabbit 190 s x2 and cricket 169 s x2 are 40% of it.

## 01:32 stage=wrap - open items
- body hair: default off, rows-of-dashes look, torso nearly invisible (see 01:02).
- short_crop cap_min_clearance -0.18 mm (one vertex inside the skin at the ear crease).
- Lower lashes still read slightly heavy; brows same shape/width for men and women (no brief field for brow shape).
- humanform SKILL.md "Measured on Belle (bun): cap from 1054 body faces (... the ring round each ear ...)" is now stale - Belle not rebuilt.
- character-pipeline (not my plugin) edited for the [hair] switches: merge agent bumps it with humanform.
- No regress --godot run (not allowed); Godot proof is the scratch project only (godot/shots). No Godot fixture covers the cards.
