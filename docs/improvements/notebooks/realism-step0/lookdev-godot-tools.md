# lookdev-godot-tools - lab notebook

Branch `lookdev-godot-tools` (plugins and grungist-creek). 06 rank 8: Godot-side look tools in lookdev.
Scratch: `C:/Users/pauli/AppData/Local/Temp/rw/lookdev-godot-tools/`.

## 08:44 start

- Worktrees made from `main` 5a218d3 and `master` 3e36eb2. `--headless --import` of the fresh game worktree: 19 s, exit 0.
- Read: figure_study.gd's port (~110 lines: apply_preset, _set_all, _has_property, _convert, kelvin_to_color),
  apply_preset.gd, capture.gd, lint.gd, lookdev.mjs. The game's `lighting_presets.json` is byte-identical
  (after CRLF) to lookdev's `presets/presets.json`.
- Checked first: a script outside the project that loads the plugin's `lookdev_materials.gd` inside a
  project that has the addon fails with `Parse Error: Class "LookdevMaterials" hides a global script class.`
  So tools run from the plugin must use the project's copy of a class_name script when there is one.
  The new `lookdev_presets.gd` has no class_name for that reason (preload it by path, as figure_study does).
- `load("<abs>/presets.json")` returns a JSON resource (`.data` a Dictionary) from outside the project too,
  so the addon's applier can `preload("presets.json")` next to itself.
- Runtime `GLTFDocument.append_from_file` under `--headless` keeps the images (`ImageTexture.get_image()`
  returns 1024x1024 for the skin): the tone probe can be a headless .gd, no numpy/PIL (neither is installed
  in the system Python).
- The study figures' rig has no eye or jaw bones (head = `spine.005`); the eyes are materials
  `HF_sclera`, `HF_iris_*`, `HF_pupil` on the body mesh. The eye anchor comes from the sclera vertices
  carried by the head bone's skin bind, so it is still posed-frame and bone-driven.

## 08:50-09:03 the tools (times from `date`: branch made 08:44, fresh import done 08:47, figure_study selftest run 09:03)

- `lookdev_presets.gd` (runtime applier, no class_name) written; `apply_preset.gd` now finds/owns the
  WorldEnvironment and sun and calls it, so the offline and runtime paths are one piece of code.
  `presets.json` moved (git mv) into `godot/addons/lookdev/`; `interior_daylight` carries `"needs": "interior"`.
- Stage test for `preset`: `sky_openness` casts 9 rays up (zenith and a 45-degree ring) against every mesh's
  `TriangleMesh` (exposed in 4.7). Empty/runtime-built scene -> 100% open -> interior_daylight refused; a
  closed 8x3x6 box with the camera inside -> 0% -> applied. Worked first time.
- `glb_tone.gd` worked first time: skin of study_woman 0.4742 linear luminance, sRGB mean
  (0.862, 0.681, 0.570) against the brief's (0.86, 0.68, 0.57). First threshold (0.03 min) failed the
  woman's hair (0.027), brows (0.023), lashes (0.007) and pupils (0.010), which are legitimately that dark;
  moved the not-ok line to 0.01 with a "dark" note under 0.03. The black control reads 0.0010 (bilinear
  bleed from the white padding at the island edge), still well under 0.01.
- `close_shot.gd` first run: 9.5 s for 18 tiles, framing right on the first try for face, eyes, feet, bust,
  full. Two bugs:
  1. Every body tile failed OFF_TARGET although the mask was right. `Camera3D.unproject_position` works in
     the viewport's visible rect, which the project's `window/stretch/mode="canvas_items"` makes 1152 px
     wide in a 640 px window: the centre came back as (576, 576). Scaled by `get_visible_rect()`. The same
     stretch made the tile label 9 px tall; sized it from the visible rect (0.03 of its height) on a dark
     panel.
  2. The palm tiles showed mostly the side of the hand: in Idle the palms face the thighs. Moved the palm
     camera to palm + 0.6 x forward (back of hand stays at 0.25) and near-clipped anything more than
     0.35 hand-lengths in front of the hand; the palm and curled fingers now read.
  Figure coverage alone counts the thigh behind a hand as "the subject" (87% for hand_back), so a second
  mask with the near/far planes pulled in to +/- a slab round the target depth gives `subject_coverage`
  (hand_back 36%, palm 48%, face 41%, eyes 87%). Fails SUBJECT_SMALL under 8%.
- Seen in the tiles (not this branch's to fix): a dotted/stippled pattern on the fingertips in the palm
  tile under clear_midday and on the neck below the ear (the known hair-shell stipple); blocky stair-step
  sun shadow edges on the floor at 1 m (clear_midday's directional_shadow_max_distance 150 m); lashes read
  as black clumps at 1 m.
- `lookdev.mjs selftest`: 10 controls, all failed as they must on the first run (8 s). Added an 11th, the
  positive control for the stage test (closed room -> interior -> applies).
- MISTAKE, caught and undone: a `python edit && cd <worktree> && ... ; git rm ...` chain failed at the
  python step, so the `cd` never ran and `git rm assets/figure_study/lighting_presets.json` ran in the
  shell's default directory - the game's MAIN checkout. Restored at once with `git restore --staged
  --worktree` (status clean again). From here every git call uses `git -C <absolute worktree>`.

## 09:03-09:08 the game, equivalence, docs (plugins commit at 09:08)

- figure_study.gd: the port (apply_preset + _set_all + _has_property + _convert + kelvin_to_color, 77 lines)
  replaced by a 15-line call to the addon's applier with `{"stage": "open"}`; `lighting_presets.json`
  deleted (nothing else read it). New selftest control: interior_daylight is refused on this stage and the
  previous preset's Environment is kept. First version of that check compared tonemap_exposure < 5, which
  failed because night's own exposure is 5.0; compared the Environment object instead.
  `--selftest`: PASSED, 55 ok lines, exit 0, 17 s.
- Equivalence of the runtime applier with the port: rendered `--shot` with master's figure_study.gd (a
  temporary untracked copy, deleted after) and with the new one: all 10 pictures within 2/255 per pixel,
  mean difference <= 0.001 - the same light.
- Equivalence of `preset` before/after the refactor: main's apply_preset.gd and the new one on main.tscn
  and showcase.tscn x golden_hour, overcast, night: the written scenes are identical once Godot's random
  resource ids are masked.
- Crouch (study_man, Crouch @ 0.5 s) put the feet and full-body cameras under the floor: the chest's
  forward leans down in a crouch. Views of the body now use the chest's facing projected on the ground;
  face/eyes still follow the head. The `root` bone sits under the floor in a crouch and was stretching the
  full-body frame; skipped with the `ft_` bones.
- Docs: SKILL.md (tools table, exit codes, close-shot section, runtime presets, two Don'ts), README,
  references/recipes.md (presets.json's new home and `needs`), lookdev 0.4.0 with a "Since 0.4.0" sentence.
  `regress.py` GODOT_ADDONS gains lookdev, so `--godot` warns on a stale addons/lookdev like the others.

## Open (added at merge, from the author's report and the critic)

- No selftest control for close-shot's post-render tile checks (EMPTY_TILE, SUBJECT_SMALL, OFF_TARGET).
  `--min-coverage 0.95` does make EMPTY_TILE fail (critic, exit 1); `--min-subject` is spec-only, not on the CLI.
- `tone --expect` only reports: `--expect 0.2,0.2,0.2` on study_woman's skin exits 0 and says ok. Its
  "vs expect" output prints the difference, which reads like the target.
- `tone` with no `--material` exits 1 on study_woman: StudyWoman_lashes reads 0.0073 linear, under the
  0.01 floor. Needs a per-kind floor (lashes, hair, pupils) or a warning band.
- `LookdevPresets.apply` says nothing changes when ok is false; a problem found in _apply_sky, _apply_sun
  or _apply_exposure comes after the Environment was edited.
- `sky_openness` calls a scene built at runtime open (figure_study.tscn is empty until _ready); the
  refusal should name `--stage interior` and `--force`.
- The lookdev selftest and close-shot are not in `regress --godot` (they need a window).
- close-shot's bone aliases cover Rigify/rig-anything and Mixamo only; other rigs need `bone:<name>`.
- Defects the close-ups show: stipple on fingertips and the neck under the ear (clear_midday); orange palms
  and fingertips on study_man; stair-step sun shadow edges on the floor at 1 m; lashes as black clumps.
- Regress: the author's run was killed when the agent ended. The critic's `--twice --jobs 2 --godot` passed
  (09:31), and the merge step's `--quick --jobs 4 --godot` after merging main is recorded in the merge commit.
