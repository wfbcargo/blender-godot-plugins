# final (figure study ship) lab notebook

## 03:17 setup | stage=read | kind=win
Read plugin CLAUDE.md, NEXT.md items 8-9. Genital branch NOT merged, so figure study ships without genital shells
(smooth crotch from humanform's helper removal). Building against plugin main 9e3051c via worktree figure-final.

## 03:31 build | stage=build (final quality, both figures in parallel) | kind=win
Specs written to grungist-creek/characters/study_{man,woman}.toml from the draft lead's specs plus every merged
feature: quality=final, [hair] brows/lashes=true, TurnL/TurnR roles, man `[flesh] limit_share = { belly = 1.0 }`,
woman `may_miss = ["belly"]`; export to assets/figure_study/<id>, blends C:/Users/pauli/Code/Blender/figure_study_{man,woman}.blend
(new files). First try, rc=0 both, 27 s / 26 s wall. Attempts 1. Skin textures (albedo/ORM/normal), brows, lashes, hair
all in the glb; 7 clips each; woman's ponytail -> study_woman_hair.glb.
Stage seconds FINAL vs DRAFT (draft lead, pre-skin main):
  man   final 24.1 (body 4.9, muscle 0.6, bake 1.9, hair 0.6, flesh 0.6, moves 7.0, export 3.6, review 4.4)
        draft 24.4 (body 6.3, muscle 2.4, bake 0.2, hair 0.5, flesh 1.1, moves 7.4, export 3.8, review 1.8)
  woman final 23.8 (body 3.6, muscle 0.5, bake 1.9, hair 0.7, flesh 0.7, moves 7.2, strand 0.1, export 3.8, review 4.8)
        draft 22.1 (body 3.0, muscle 0.8, bake 0.2, hair 0.6, flesh 1.2, moves 8.6, strand 0.2, export 5.0, review 2.3)
Final costs no more than draft: only bake (+1.7 s: skin bake) and review (+2.6 s) grow. Draft is not a speed knob for
these figures (moves dominates, and it has no cheaper setting - known). The skin bake at final is still 1024 px
(gap-realistic-skin open item: character-pipeline does not pass quality to look.skin) -> character-pipeline stages.py.
Noise: 4x per build glTF "More than one shader node tex image used for a texture" warning (skin normal+detail?) -> lookdev/humanform skin material, harmless but noisy.

## ~03:34 judge | stage=humancheck + look (Blender) | kind=win
humancheck_cli on both saved blends (read only, not saved): man 1.797 m 0 fail 2 warn 30 pass; woman 1.678 m 0 fail
2 warn 30 pass. Warns are the known L2 ones, now 12/13 pieces and 612/624 open edges (was 8 pieces/120 edges in draft):
the rise is the brow and lash cards joined into the body. humancheck should exclude ft/hair card pieces from the
piece/open-edge count (humanform measure) or it will warn on every browed body. 4 Blender jobs in parallel: 12 s wall.
No Agent tool in this subagent: the look and motion critics were answered by me, not independent (kind=gap, same as
gap-natural-locomotion). Look (EEVEE lit, draft lead's lit.py + 1 m shots): skin reads as skin (SSS, tone within spec),
woman at 1 m convincing; man's face is glossy on forehead and lips (spec a touch high for skin at 1 m); man's hairline
is a hard cut with a short spiky fringe; brows read well at 1 m, lashes sparse. A dark patch on the man's right thigh
turned out to be his hand's cast shadow (dead-end, 1 render, 10 s). Crotch smooth on both (genital branch not merged).
Motion (review strips, right view): woman walk heel-strike/toe-off and straight-ish stance leg read natural, ponytail
visible; man run has flight phase and arm pump. All 7 clips x 2 have empty clip_checks failures, no forced clips.
OPEN: man belly peak_m 0.168 m (max_offset 0.168 with limit_share 1.0) on an athletic 1.79 m man - same suspicious
number the flesh branch saw; not investigated (follow-through flesh.py peak measurement).

## ~03:37 godot scratch | stage=import + verifiers | kind=win
Scratch project = tar copy of grungist-creek without .git (incl .godot cache): 1 s; --headless --import 5 s rc 0 (only
pre-existing tomas_demo.gd errors from the untracked tomas_demo.tscn). 6 verifiers in parallel 37 s wall:
verify_moves on both manifests PASSED; verify_flesh full course PASSED both (man belly with limit_share 1.0 passes
within_body); course=jump require=within_body PASSED both (butt on_limit advisory NOTE).

## ~03:39 godot | stage=verify_strands study_woman ponytail | kind=fail
FT_SUMMARY ... swing_spread=1.260 FAILED: run swing [53.05, 49.45, 62.33, 62.33] deg at 30/60/120/240 fps
(max/min 1.26 > 1.25). Every other strand check passes (head pen <= 3.2 mm, rest drift 0.03 deg, kick settles 1.9 s).
Diagnosis (2 extra runs, 40 s): it is a real frame-rate dependence, not a marginal number: set=max_angle_deg:50 ->
[32.4, 32.0, 44.6, 44.6] (1.395); damping 0.7 -> 1.535; the walk clip -> [24.6, 24.9, 31.8, 32.6] (1.32). 120 and
240 fps agree with each other and 30/60 agree with each other, so the step size or sub-stepping in
strand_modifier.gd (with ~280 head-collider contacts per run) changes the swing. Likely exposed by the natural-speed
run (rig-anything 0.24.0: run now 3.8 m/s) after hair-strands-integration last passed it. Not fixable from a spec
(no [hair] strand overrides) and the tolerance stays. OPEN -> follow-through strand_modifier.gd (+ a strand fixture on
a natural-speed run in regress --godot, NEXT item 8). The demo runs at 60 Hz physics, where the swing is 49 deg.

## ~03:42 demo | stage=figure_study.gd selftest | kind=win
figure_study.tscn/.gd written (turntables, 1-7 clips, F/S/B/Q/C views, Tab, L lookdev presets at runtime, T, J, H, R,
HUD, --selftest, --shot). Selftest passed on the first run, 17 s headless: every clip plays to its end, turn hand-off
(manifest `turns` yaw + end_offset applied to a Facing node - the MovesController gap) keeps the hips within 8-14 mm,
flesh finite/within limit/moved/within body, strands swing 45.7 deg on the run, 5 presets, 5 views.
Porting lookdev apply_preset.gd to runtime took ~40 lines: lookdev has no runtime preset applier (only an offline
SceneTree script that rewrites a .tscn) and its presets.json is not shipped in the Godot addon. -> lookdev: add
godot/addons/lookdev/lookdev_presets.gd (apply(preset, env, sun)) and ship presets.json with the addon.

## ~03:44 judge | stage=flesh numbers in Godot | kind=fail -> fixed (spec)
The selftest showed every region peaking exactly on its limit and the man's belly swinging 0.168 m (limit_share 1.0 x
peak_m 0.168). verify_flesh agreed: belly peak 0.122 m on the full course, 0.168 on jump. A 12-17 cm belly swing on an
athletic man is a visible fault; within_body cannot see it because the stand-out itself (peak_m = 90th pct of excess
over the lean envelope, flesh.py ~l.915) is over-measured. Fix inside my remit (narrows, never widens): study_man
`limit_share = { belly = 0.4 }` -> limit 0.067 m. Rebuild 25 s (the whole build re-ran from body: build_human.py opens no
blend, so a [flesh]-only edit costs a full build - friction, character-pipeline/thin callers could open the saved blend).
verify_flesh after: full PASSED belly on_limit 1.1%; jump (require=within_body) PASSED belly 7.1%. Attempts 1, ~5 min.
Root cause OPEN -> follow-through flesh.py peak_m for belly on MPFB athletic male (lean envelope too thin at the belly?).
Per-clip on_limit (measure_label per clip): ticks on the limit come from Jump (6-8), Crouch (1-6) and TurnL/TurnR (1-3,
the 0-blend Idle start after the hand-off). Nothing on Walk/Run/Idle.

## ~03:46 judge | stage=look in Godot (demo shots, 1600x900, 58 s for 10 shots) | kind=gap
Godot shots in wf3/final/shots. Skin survives: SSS skin mode, tone matches Blender, reads as skin at 1 m and full
body. Brows read; lashes thin (known). NEW: a dithered/stippled shadow on both figures' necks under the ear
(clear_midday close views). Materials dump: hair shell and ponytail are lookdev `hair` preset with transparency 4
(ALPHA_DEPTH_PRE_PASS); brows/lashes are 2 (scissor). The man has no ponytail, so it is the hair shell's shadow, drawn
dithered. Not fixed: the hair is a surface of the joined body mesh, so a per-mesh shadow proxy is not possible from the
demo, and the material belongs to lookdev. OPEN -> lookdev presets/materials.json hair (`transparency` 4) /
lookdev_materials.gd: give hair shells an alpha-scissor shadow (or split hair to its own mesh with a scissor
shadow-only copy). Also seen: golden_hour over-exposes the pale woman and shows fine stripes on the floor (shadow
acne, shadow_bias 0.05 in the preset?) -> lookdev presets.json golden_hour; the man's face is glossy (skin roughness at
the forehead/lips) in both Blender and Godot. Close view reframed (target 0.88 H, fov 40) so the head is not cut.

## ~03:47 demo | stage=lighting presets on an open stage | kind=friction
interior_daylight (tonemap_exposure 20, "exposure opens ~4.5 stops") clipped both figures to white on the open stage;
dropped from the L cycle with a comment (4 presets remain). presets.json has no flag saying a preset needs an
enclosure -> lookdev presets.json: add `"needs": "interior"` so a runtime cycler can skip or build walls. 1 attempt, 2 min.

## ~03:48 verify | stage=step 4, all in the scratch mirror | kind=win
--headless --import rc 0; figure_study --selftest PASSED; belle_demo BELLE_SELFTEST PASSED; people_demo PEOPLE SELFTEST
PASSED; verify_moves (both manifests, man rebuilt) PASSED; verify_strands rates=60 PASSED (the demo's rate). 5 Godot
jobs in parallel: 40 s wall. Shots (10, 1600x900 windowed, 58 s) in wf3/final/shots.
Project files copied back: .gd.uid and every .import from the scratch import, plus the extracted skin/hair/brow/lash
PNGs (Belle commits hers too). Godot was never run inside grungist-creek.

## 03:49 ship | stage=commit grungist-creek master | kind=win
afe71f3 "Figure study: StudyMan and StudyWoman at final quality, and figure_study.tscn": 56 files, 13 MB (glbs 3.8+4.1+0.5 MB
plus textures). Only my files added; tomas_demo.tscn left untracked. Review dirs are gitignored (assets/**/review/).
Not pushed.
(Times marked ~ are estimates between measured clock readings 03:17, 03:31 and 03:49.)

## 03:58 regress | stage=python tools/regress.py --twice --jobs 2 on worktree figure-final (= main 9e3051c) | kind=slow
~9.5 min wall (03:49 -> 03:58), 20 fixtures ok, both builds agree, "no change". Longest: rabbit 120 s x2, cricket 92 s,
pipeline_muscle 53 s (the 910 s seen by gap-natural-locomotion did not recur). No plugin code changed on this branch
(no commits), so this is a check of main as shipped against.

## Summary / open items handed back
- verify_strands cross-rate swing spread 1.26 > 1.25 on study_woman's ponytail (30/60 vs 120/240 fps) -> follow-through strand_modifier.gd.
- Belly peak_m 0.168 m on an athletic man: spec uses limit_share belly 0.4 -> follow-through flesh.py peak_m / lean envelope.
- Dithered hair-shell shadow on both necks in Godot -> lookdev hair preset (transparency 4) / lookdev_materials.gd.
- interior_daylight unusable on an open stage; golden_hour over-exposes the pale woman and stripes the floor -> lookdev presets.json.
- No runtime preset applier in the lookdev Godot addon (demo carries a ~40-line port) -> lookdev addon.
- humancheck counts brow/lash cards as pieces/open edges (12-13 pieces, 612-624 open edges) -> humanform measure.
- Critics were run by me (no Agent tool), not by independent subagents.
- Genital branch not merged: figures ship with smooth crotches.
- A [flesh]-only spec edit rebuilds from body (thin caller opens no blend): 25 s here, fine, but still a full build.
- Total wall ~41 min.
