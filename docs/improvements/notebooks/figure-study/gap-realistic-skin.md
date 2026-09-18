# gap-realistic-skin lab notebook

## 00:34 setup | kind=win
Worktree fig-realistic-skin from main b496738; scratch copied from draft (characters, build_human.py, hflib copy, run.sh pointed at worktree). ~2 min.

## 00:58 humanform skin.py first bake | kind=fail (fixed, 1 attempt)
Baked albedo came out orange/dark (~185,110,75) though the reported mean matched the spec exactly: byte sRGB images' `Image.pixels` are the stored sRGB-encoded values, not linear, and my tone correction encoded them a second time. Cost ~3 min. Fix: treat px as sRGB, linearise, gain, re-encode. Should change: lookdev bake.py docstring now says so for `adjust`; worth a line in lookdev references/blender-handoff.md.

## 00:58 pipeline bake stage with skin bake | kind=win
First build through body->muscle->bake worked first time: skin bake (coverage + base colour + roughness + normal at 1024) adds ~2.5 s to the bake stage (3.3 s total). Region marks survive rig-anything bake_for_game (preserve_all_data_layers) as point attributes, as planned.

## 00:59 runner from=bake refuses on a fresh process | kind=friction
`from=bake` needs the .blend opened first (BuildRefused: body has not run in this file). run.sh does not open the blend. Cost 1 run (3 s). Rebuilding from body is 9 s anyway. character-pipeline run.sh template could pass the saved blend as Blender's first arg when from != body.

## 01:10 both figures through the pipeline | kind=win
study_man 33.1 s, study_woman 31.0 s (bake stage 3.4 / 3.9 s incl. skin bake). glbs: skin has baseColorTexture, metallicRoughnessTexture, normalTexture, TEXCOORD_1 (hf_detail) and extras lookdev.preset=skin with the Godot SSS props. Tone mean after bake = spec exactly (the gain normalisation), before the gain it drifted by the regions/mottling.

## 01:12 Godot scratch import + apply + lint | kind=win (one friction)
Import 7 s. LookdevMaterials.apply -> subsurf_scatter_enabled/skin_mode/transmittance true, detail normal on UV2 (80x). lint.gd new SKIN_PLASTIC: fires on the old draft woman glb (flat albedo, one roughness, no normal, no SSS), silent on the new ones.
friction: passed Godot `--out /c/Users/...` (Git Bash path) and Godot silently wrote nothing; must be `cygpath -m`. Cost 1 run. Should change: lookdev lint.gd/capture.gd could fail loudly when the out file cannot be opened (FileAccess.open returns null -> currently crashes silently in headless).

## 01:20 Godot capture under a calibrated preset | kind=friction then win
interior_daylight on an open scene (no walls): median luma 0.95, 24-33% clipped - the preset is for rooms; wrong choice by me, cost 1 capture (15 s). overcast: medians 0.38-0.59, 0 % clipped. Unshaded + lit views show lips, areolae, genital skin, cheeks and lighter palms distinct. Capture itself 15 s for 6 shots x 2 views.
fail (fixed, 1 attempt): MPFB's `lips` group covers the skin round the mouth (clown mouth once tinted) - now eroded to its core by smoothing membership 3 iterations and keeping >0.55..0.85. Cheek flush toned down (radius 18 mm, 0.8 weight). Lips still read slightly large on the woman: open.
dead-end: the hand close-up shot (eye below the hand) missed the hand twice; palms judged from the torso shots instead. lookdev capture could accept `target_node`/bone name for shots.

## 01:25 regress pipeline_woman with skin block | kind=fail then win
First run: AttributeError lookdev_blender.bake has no bake_material - the harness/pipeline had already imported the INSTALLED lookdev (~/.claude/skills) before humanform looked for the checkout's. Fix: skin._lookdev prefers a loaded module only if it has bake_material, else re-imports from LD_SCRIPTS / sibling plugin path. Cost 1 run (18 s). Should change: character-pipeline plugins.use should honour LD_SCRIPTS the way it does the other *_SCRIPTS (and the harness should export LD_SCRIPTS for pipeline fixtures).
Second run: only new keys under `skin` differ; nothing else in pipeline_woman moved.

## 01:27 full regress --twice --jobs 2 | kind=slow
> 10 min (ran past the 600 s tool timeout, continued in background).

## 01:50 full regress --twice (before goldens) | kind=slow + 2 real regressions found
1013 s. Changed: pipeline_woman (new skin keys only), hair_presets, muscle_definition, pipeline_muscle.
- fail: hair_presets uv_tangent_turn moved (tris 12750->9632 on every preset): hair parts inherited the body's new `hf_detail` UV layer AS ACTIVE, so the strand texture sampled body UVs. Fixed in humanform hair.add: parts keep only their own UV map. 1 attempt, ~6 min (a debug Blender run on the built woman showed `[('hf_detail', True), ('UVMap', False)]`). Lesson: adding any UV layer to the body is visible to everything cut from it (hair, garments) - a fixture-level check of "active UV name" on derived meshes would catch it at once.
- fail: muscle normal bake skipped ("Normal input is already linked") because the skin now has a baked normal (pipeline_muscle) or the procedural bump (muscle_definition, which bakes without look.skin again). Fixed in lookdev detail.py: humanform's own skin normal/bump is released and replaced by the geometry bake. 2 attempts. Open: the muscle normal REPLACES the skin micro-normal (pores still come from Godot detail).
- my output piping (`| tail -40`) threw away the diffs of the other fixtures; had to rerun them with --only (70 s). regress.py could write the full diff to a file by default.
After fixes: hair_presets only gltf.images 2->5 (the skin maps now ship in the export), muscle_definition no change, pipeline_muscle only new skin_textures entries.

## 01:55 figures rebuilt after fixes + Godot re-verify | kind=win
study_woman 36 s, study_man 34 s; glbs carry baseColor/ORM/normal textures + TEXCOORD_1; Godot dump subsurf_scatter_enabled true on both; lint: no SKIN_PLASTIC; overcast capture 0% clipped (cap3).

## 02:25 regress --twice --update + commit 7dee074 | kind=slow (win)
~17 min, every fixture identical across both runs. --update churned 11 goldens; 8 were temp paths / seconds only (put back with git checkout, as NEXT.md warns). Kept: pipeline_woman (skin block), pipeline_muscle (skin textures), hair_presets (images 2->5).
gap: mpfb_woman_curvy's glb grew 1.47 -> 1.64 MB (size_bytes is volatile so not flagged): an unbaked MPFB human exported directly now has the hf_skin_tint colour attribute read by its procedural material -> probably exported as COLOR_0. The pipeline bakes and drops it; a direct export does not. Should change: skin.mark could store tint where the exporter ignores it, or export with export_vertex_color="NONE".

## OPEN
- quality -> map size: look.skin cannot see [build] quality (character-pipeline is not mine); final builds still bake 1024. Needs a one-line character-pipeline change (pass size=2048 for final, 1024 draft) in run_bake.
- muscle normal output replaces the baked skin normal (pores still from Godot detail); combining would need a normal blend before bake.
- lips still read a little large on the woman (MPFB lips group); hands/palms judged only from torso shots.
- humanform_skin extras in the glb carry only seed/tone (the bake's later keys did not reach the glb extras - not investigated).
