# Review notebook: fig-realistic-skin (7dee074)

## 01:32 | review setup | win
- What: diff stat read; 14 files, +855/-15. Worktree clean.
- Attempts: 1. Wall: <1 min. Resolution: n/a.

## 01:34 | build study_woman + study_man via character-pipeline (review scratch) | win
- What: copied draft specs (blend path repointed), run.sh repointed at the worktree, hflib copied. Both built first time: woman rc=0 25 s wall (draft build 22.2 s: body 3.1, muscle 0.6, bake 2.3, hair 0.4, flesh 0.8, moves 6.2, export 3.8, review 4.6), man rc=0 27 s.
- Attempts: 1. Wall: 52 s. Resolution: n/a.
- Change: none.

## 01:36 | glb check (decoded PNG, not Blender-side) | win
- What: decoded each glb's embedded base-colour PNG and rasterised the skin primitive's TEXCOORD_0 triangles for coverage (62.4% of texels). Covered mean sRGB: woman (0.861,0.680,0.569) vs spec (0.86,0.68,0.57); man (0.620,0.441,0.331) vs (0.62,0.44,0.33). Within 0.002. baseColorTexture, metallicRoughnessTexture, normalTexture, TEXCOORD_1 present. Author's open issue "tone not re-read from the glb" is now closed.
- p5/p95 of covered texels (woman R 0.847/0.902) - variation is narrow outside the small regions.
- Attempts: 2 (system python has no numpy; reran inside Blender). Wall: 3 min.
- Change: lookdev could ship a `glb_tone.py` probe (decode + UV coverage) so nobody rewrites it.

## 01:34 | regress --only mpfb_woman_curvy --keep <scratch> | friction
- What: review sheet failed "Render error (No error) cannot save: ...FixWoman_CrouchWalk_three_quarter.png" - Windows MAX_PATH from the long --keep path, not the branch. Fixture wall 25 s.
- Resolution: ignored the review diff; used the kept glb.
- Change: tools/regress.py --keep should warn when out paths exceed ~200 chars, or rig-anything review should use shorter names.

## 01:37 | direct-export consumer (mpfb_woman_curvy flow: pipeline.make -> bake_for_game -> export_character) | fail (branch defect)
- What: kept fixwoman.glb (1,642,272 B) skin material FixWoman_skin has pbrMetallicRoughness {'metallicFactor': 0} only - NO baseColorFactor (glTF default = white) and no texture; the mesh carries COLOR_0 and COLOR_1 (hf_skin_tint, hf_skin_oil). On main look.skin wrote the brief tone as baseColorFactor. So any humanform body exported without character-pipeline's bake stage now arrives white (tinted by vertex colour when Godot uses COLOR_0 as albedo).
- Resolution: reported as blocking.
- Change: humanform look.skin must keep a flat Base Color default (or set mat.diffuse + a fallback) the exporter can read, and not leave hf_skin_* attributes on an unbaked human that gets exported; or rig-anything export_character should call look.skin's bake when a material is still procedural.

## 01:40 | Godot scratch project (gproj: lookdev + follow_through addons copied from worktree) | win
- What: import of 4 glbs 6 s, rc 0, no errors. Headless run of the figure scene dumps: StudyWoman_skin / StudyMan_skin sss=true, skin_mode=true, transmittance=true, albedo/roughness/normal textures, detail normal on UV2 (80x), has_uv2 true, metallic_specular 0.42. Confirms author's material_dump.
- The same dump for the direct-exported fixwoman.glb (branch): albedo_color (1,1,1,1), no albedo texture, vertex_color_albedo false -> the body renders WHITE. old_study_woman (main): albedo (0.86,0.68,0.57). Defect confirmed engine-side.
- Attempts: 1. Wall: ~2 min.

## 01:42 | lookdev preset overcast + capture | win / friction
- preset: <1 s. capture 2 views x 2/7/2 shots: 8-9 s each run. Exposure median 0.40-0.59 (face/torso 0.59 = WARN overexposed for overcast by 0.01), 0% clipped.
- Unshaded: lips clearly redder, areolae darker, palms paler/pinker (hand shot from below, cap3), soles slightly paler, knees very subtle. Lips read large on the woman (author noted it).
- Friction: first hand close-ups (cap2 rows 3-4) missed the hands entirely, same as the author's. Estimating hand positions from the full shot by hand cost 2 tries.
- Change: lookdev capture could take `"target_bone": "hand.L"` / a node path so shots frame body parts without guessing coordinates.

## 01:44 | lint | friction then win
- lint on a scene whose script loads the glbs in _ready saw no materials (lint never runs scripts) - 0 findings, which looks like a pass. Rewrote as scenes that instance the glb directly.
- Then: study_woman/study_man no SKIN findings; old_study_woman SKIN_PLASTIC (all four problems); fixwoman (branch direct export) SKIN_PLASTIC (flat albedo, one roughness) - lint does not notice the white albedo itself.
- Change: lookdev lint should warn when a scene has 0 materials ("nothing checked"), the same rule as wardrobe's "a run that measured nothing fails".

## 01:45 | determinism across independent builds | win
- md5 of every embedded image in my two glbs equals the author's glbs byte for byte (skin normal/base/orm, hair). Seeded and reproducible.

## 01:47 | from=bake rerun on a built file | fail (minor, new silent loss)
- blender -b study_man.blend build_human.py who=study_man from=bake to=bake force=1: rc 0, 6 s. Region tones in the re-baked albedo: body (0.621,0.441,0.331), lips (0.619,0.437,0.328), nipple (0.615,0.432,0.324) vs first build lips (0.593,0.361,0.273), nipple (0.531,0.323,0.231). skin.bake removes hf_skin_tint after baking, so look.skin on the rerun calls unmarked() and bakes a uniform tint, while humanform_skin still reports stage=baked, tone_ok=True. (Eye/hair materials also wiped by look.skin's materials.clear() - that part is pre-existing on main.)
- Change: humanform skin.bake should keep the marks (or store them as a hidden attribute the exporter ignores), or look.skin should refuse / report "unmarked" instead of silently baking flat.

## 01:50 | regress --only pipeline_woman hair_presets pipeline_muscle --twice --jobs 3 | slow (119 s) / win
- All ok, "no change": pipeline_woman 47+47 s, hair_presets 22+24 s, pipeline_muscle 71+71 s. The golden changes are explained: hair_presets images 2->5 (the body's three skin maps); pipeline_muscle skin_textures gain skin maps, and the normal-output case replaces FixDante_skin_normal with the muscle normal (disclosed); pipeline_woman gains the skin block. tools/regress.py is untouched, so no tolerance was widened.
- Gap: pipeline_woman's version line lists no lookdev, but its bake stage now imports lookdev (skin._lookdev). A lookdev change to bake_material will not invalidate a stored bake stage or the fixture's recorded versions. humanform is also still 0.8.0, so an existing .blend rebuilt after merging finds its body and bake stages "unchanged" and keeps the flat skin until the version is bumped.
- Change: character-pipeline plugins.stage_versions should list lookdev for bake whenever humanform's look.skin is realistic; humanform's version bump is required at merge.

## 01:52 | review verdict
- Blocking: a humanform body exported without character-pipeline's bake stage is white in Godot (see 01:37).
- done_when not met: final quality still bakes 1024 maps (the author says so too). Everything else in done-when was reproduced independently.
- Review wall time about 20 min.
