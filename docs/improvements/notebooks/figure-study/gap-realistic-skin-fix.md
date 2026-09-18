# gap-realistic-skin-fix lab notebook

## 01:42 setup | kind=win
Scratch copied from gap-realistic-skin (assets, characters, hflib, gproj, probe, run.sh repointed). <1 min.

## 01:44 blocker 1 (white skin on unbaked export) | kind=fail -> win, 2 attempts, ~3 min
Reproduced idea: look.skin on an MPFB human left a procedural material (Base Color linked to a Mix chain) -> exporter writes no baseColorFactor.
Attempt 1: skin.material is now FLAT by default (tone as unlinked Base Color, subsurface, no attribute refs); bake() builds the procedural tree itself, bakes, and on any error/exception rebuilds flat. regress --only mpfb_woman_curvy --keep: baseColorFactor (0.342,0.171,0.107) = linear(0.62,0.45,0.36), BUT COLOR_0 (u8 VEC4) + COLOR_1 (u16 VEC4) still exported, glb 1,642,368 B. The glTF exporter in 5.2 writes colour attributes even when no material references them.
Attempt 2: hf_skin_tint stored as FLOAT_VECTOR (not a colour attribute). glb: no COLOR_n, 1,467,524 B (= main's size). 24 s per fixture run.
Should change: humanform docs - never store helper data as a colour attribute on anything that is exported; a fixture should record the exported skin baseColorFactor and COLOR_n (added to mpfb_woman_curvy).

## 01:47 blocker 6 (lip tint oval past the mouth corners) | kind=fail -> win, 2 attempts, ~3 min
Wrote a Blender debug script that rasterises the face front-on from the built woman's body verts with per-vertex lip weights and normal shading (lipdbg/lips_variants.png) - lets a mask be judged in 10 s without a full build + Godot capture. Current mask (core smoothstep 0.55-0.85 then one more Laplacian smooth): all 418 MPFB lips verts >0.5, tint spills below the lower lip and past the corners. A "recess" filter (drop verts behind the local front) left a pale band along the lip seam - dead-end. Kept: core smoothstep 0.70-0.95, no final smoothing for lips, lateral taper 0.78-0.97 of the group half-width (326 verts >0.5): follows the vermilion, corners taper.
Should change: humanform could ship this face-raster check as a humancheck close-up (region weights over shading) - region masks were only visible after a 35 s build + Godot import + capture.

## 01:50 flat-by-default made the bake black | kind=fail -> win, 1 attempt, ~2 min
After making bake() rebuild the procedural material itself, both figures built rc=0 (21 s each) but the albedo was pure black and the report said tone_target [0,0,0], baked [0,0,0], tone_ok True. Cause: `np.asarray(mat["humanform_skin"]["tone_srgb"])` is a VIEW of the ID property's memory (buffer protocol); rebuilding the material replaced the property, so the target read freed memory = 0 and the "hold the mean" gain pulled the map to black. Fix: copy with .to_dict() / float(). Caught only because I decoded the glb myself.
Should change: (a) humanform/lookdev: never np.asarray an IDProperty array - always to_dict()/list(); (b) skin.bake should refuse a target mean < 0.02 (a skin with no tone is a bug, not a request), and tone_ok must compare against the spec passed by the caller, not a value re-read from the material.

## 01:51 blocker 3 (tone mean vs spec) | kind=win (probe bug fixed once)
New probe probe/glbtone.py (Blender): decodes the glb's embedded base-colour PNG, rasterises the skin primitives' TEXCOORD_0 for coverage (62.4 % of texels), mean in sRGB. First run double-flipped V (glTF v is already 1-v of Blender's; Blender pixel row 0 = bottom = v 0) -> error 0.16; fixed.
study_woman glb mean (0.8604, 0.6802, 0.5689) vs spec (0.86,0.68,0.57): max err 0.0011. study_man (0.6224, 0.4405, 0.3307) vs (0.62,0.44,0.33): 0.0024. Region tones (from the baked map, woman): skin .859/.680/.571, lips .824/.556/.472, nipple .741/.514/.415, genital .767/.562/.460, palm .908/.689/.565, sole .907/.694/.552, knee .840/.648/.536.
Should change: lookdev should ship this glb tone probe (review notebook asked for it too) - third agent to rewrite it.

## 01:52 blockers 2 (pipeline build log) | kind=win
Both figures rebuilt through character-pipeline from characters/*.toml with run.sh pointed at the worktree (HUMANFORM_LIBRARY = scratch hflib copy), force=1 from a deleted blend dir: rc=0, 20-28 s wall each (draft: body 3.0, muscle 0.6, bake 2.3, hair 0.4, flesh 0.9, moves 5.5, export 3.0, review 2.3). Logs: log_study_woman.txt / log_study_man.txt, runout_*.txt.

## 01:55 blockers 4/5 (preset, old/new labels, palms and soles framed) | kind=friction -> win, 3 attempts, ~5 min
- New scratch Godot project gp/ (lookdev + follow_through addons copied from the worktree), one scene with OLD (main-era glbs: draft study_man, old_study_woman) and NEW figures side by side, Label3D tags "OLD woman" / "NEW man" inside every tile, plus lying copies (soles to the camera). `lookdev.mjs preset --preset clear_midday` -> figures_midday.tscn (sun 58 deg, PhysicalSky, AgX, SDFGI, SSAO). Capture 17 shots x lit/unshaded, 16 s.
- dead-end x2: palm/sole shots computed from Blender region centroids (REST, then POSE) missed: the pose Godot shows is neither (hands 25 cm higher). Fix: a Godot probe (gp/bones.gd) prints Skeleton3D global bone positions of the instanced scene; palm centre/normal from hand.L, f_middle.01.L, thumb.01.L (same construction as skin.regions). Also my first lying transform was the wrong sign (tscn Transform3D basis is row-major in the text form I assumed column-major): soles faced away.
- Should change: lookdev capture should accept `"target_bone": "hand.L", "face": "palm"` shots resolved from the running skeleton - third agent in a row to lose time framing hands.
- Should change: capture's contact sheet has no tile labels; I composited (probe/montage.py) and labelled with Label3D in-scene.

## 01:58 transmittance too deep: whole palm glows orange | kind=fail -> win, 1 attempt, ~2 min
Under clear_midday (sun above, palm facing down) the NEW palms rendered saturated orange: GODOT extras had subsurf_scatter_transmittance_depth 0.08 m - an 8 cm slab transmits, so a 2-3 cm hand glows like a lamp. Set 0.01 m. Result: palm reads as skin, only thin orange lines at the finger-web creases remain (open, minor; possibly shadow-map edge). Overcast (the previous capture) hid this completely - a key light behind thin parts is the test for transmittance.
Should change: lookdev lint could flag transmittance_depth > ~0.02 m on a humanoid skin.

## 01:59 blocker 6 (form shading) | kind=win
Metric probe/shading.py: shading = lit/unshaded luma over skin-hued pixels in the face box. clear_midday: std/mean OLD woman 0.331 vs NEW 0.323 (98 %); OLD man 0.402 vs NEW 0.393 (98 %); p90/p10 2.71 -> 2.64, 3.43 -> 3.32. SSS softens shadow edges by ~3 %, form shading survives. The "flat" read in the earlier review came from the overcast-like hand-made environment, not the material.
Lint on figures_midday.tscn: 0 errors; SKIN_PLASTIC only on the two OLD figures, none on NEW; no ENV_MISSING / NO_LIGHTS (1 sun, 20 materials). Material dump (godot.log): NEW skins subsurf_scatter_enabled true, skin_mode, transmittance, albedo/roughness/normal textures, detail normal on UV2; OLD skins sss false.

## 02:02 blocker 7 (fixture) | kind=win, first time
New fixture tests/fixtures/skin_detail.py (15 s): deep tone (0.45,0.31,0.23) brief -> pipeline.make (flat, marks as FLOAT_VECTOR/FLOAT/INT, no colour attributes) -> bake_for_game -> direct glTF export (baseColorFactor = linear tone, no COLOR_n) -> bake with lookdev monkeypatched away (stage flat, Base Color unlinked = tone, marks kept) -> real 512 px bake + export (3 textures, TEXCOORD_1, glb-embedded PNG == baked pixels at every loop UV, tone held, lips redder+darker, nipple/genital darker, palm/sole paler, transmittance depth 0.01). mpfb_woman_curvy gains `skin_export` (baseColorFactor 0.3424/0.1706/0.1065 = linear(0.62,0.45,0.36), no texture, no COLOR_n) so the white-body regression is caught by the golden next time.
Also: skin.bake now reports each region's baked tone (`regions`, sampled at the region's loop UVs) and keeps the marks after baking (fixes the review's "from=bake rebake goes uniform" loss: marks are no longer colour attributes, so keeping them costs nothing in the glb).
friction: regress --only on a NEW fixture writes its golden immediately without --update ("RECORDED") from a single run; the rule says record with --twice. Must remember to re-record.

## 02:02-02:29 full regress --twice --jobs 2 | kind=slow (27 min)
Every fixture identical across both builds. Changed vs golden: mpfb_woman_curvy (new skin_export only) and pipeline_woman (lips_tone 0.59/0.37/0.30 -> 0.60/0.38/0.31, explained: it samples the whole MPFB lips group and the tighter mask leaves its outer/corner verts as plain skin). hair_presets, muscle_definition, pipeline_muscle, pipeline_ponytail unchanged - the flat-until-baked material and the new attributes moved nothing else. skin_detail ok twice (12 s).
friction: regress output to a redirected file is block-buffered - nothing to watch for 27 min. regress.py could flush per fixture (print(..., flush=True)).
Then --only mpfb_woman_curvy pipeline_woman skin_detail --twice --update (59 s); --update rewrote temp paths/seconds/size_bytes in mpfb_woman_curvy again (NEXT.md warns) - merged only the new key into the old golden by script. Re-check --twice: all three ok, no change.

## 02:32 commit 0dac898 on fig-realistic-skin | kind=win

## OPEN
- thin orange lines at the finger-web creases on NEW palms under clear_midday (transmittance at 0.01 m; maybe shadow-map edges) - minor.
- final quality still bakes 1024 (character-pipeline does not pass [build] quality to look.skin) - unchanged from the first round, not in my plugins.
- the muscle normal output still replaces the baked skin normal (pores still from Godot detail).
- Label3D tags from neighbouring figures leak into close-ups (cosmetic, evidence only).
