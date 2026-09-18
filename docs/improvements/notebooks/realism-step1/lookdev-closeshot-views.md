# lookdev-closeshot-views - lab notebook

Branch `lookdev-closeshot-views` (plugins, from main 9007067; game worktree
`grungist-creek/.worktrees/lookdev-closeshot-views` from master 8e25538, used only as the Godot project for
close-shot and `regress --godot`, nothing committed there). NEXT.md Step 0.5 "close-shot views the look critic
missed" plus Step 0's open close-shot items. Second attempt: the first stalled and left no branch. Seam:
this branch owns `godot/close_shot.gd` and the `close-shot` command in `lookdev.mjs`; hair-godot-transfer
owns lookdev's materials and adds a `stipple` command (lookdev.mjs command lists resolve as unions).
Scratch: `C:/Users/pauli/AppData/Local/Temp/rw/lcv/`.

## 13:01 start | kind=setup
Read NEXT.md, CLAUDE.md, close_shot.gd, lookdev.mjs (close-shot, selftest), regress.py's --godot part and
rig-anything `closeups.py` (the Blender look set whose view math close_shot.gd mirrors). Game worktree
`--headless --import` took 10 s. Copied study_woman's Blender close set (git-ignored in the game) to
scratch `blender_close/study_woman/`.

Baseline (main): `close-shot --views face,eyes,hands,full --presets clear_midday,overcast` on study_woman,
9.9 s, 14 tiles all pass. In `clear_midday_full.png` the two-line label band covers the top of the head and
the hair (the defect the task names). The sheet is presets as rows, views as columns wrapped at 5.

Blender's tiles are 512x546: its label band sits *above* the picture (34 px), so it never covers anything.
face_3q/head_side come from the head's left (`hl = hu x hf`, +X in both Blender and glTF for a figure
facing -Y / +Z), head_back from -hf; frames are ipd*4.8 and (top-bottom)*1.25 as in `closeups._aim`.
Blender distances per view: face/face_3q 0.6, eyes 0.4, head_side/back 1.0, hands 0.5, bust/crotch 0.8,
feet 1.0; Godot takes one `--distance` for all (1 m).

Plan:
- views face_3q, head_side, head_back ported from `closeups._aim` (same formulas, so a pair lines up);
- the label band above the picture, as Blender's (tile = band + render); the head's projected box is
  still checked against the band, and `--label inside` (the old overlay) is kept as the control that fails;
- per-view subject points (Blender's `subject`): OFF_TARGET from the subject centroid's offset (>0.3,
  Blender's CENTRAL) and whether the figure covers it; the free values `subject_uv`/`subject_off` reported;
- `--aim-offset view=x,y,z` moves a camera and not its subject (the control: empty and off-target must fail),
  `--min-subject` passed through;
- sheet: one row per view, one column per preset, composed in a SubViewport with column headers;
- `--pair-blender <close dir>`: a Blender column; a paired view without @ or --distance takes the Blender
  tile's distance; unpaired views are named;
- regress --godot: close-shot on pipeline_woman's fixwoman.glb (paired with its own Blender close set) and
  `lookdev.mjs selftest`, with a control.

## 13:05-13:10 views, band, subjects, sheet | kind=win (after one fix)
Ported face_3q/head_side/head_back; label band above the picture drawn in its own SubViewport (64 px at a
640 px tile); sheet composed in a SubViewport (column headers, a Blender/Godot tag per cell). First run
11 s for 7 views x 2 presets, all pass. The head's subject point: the glb has no head-bone tail (study_woman's
head is `spine.005`, no connected child), so `(head bone + crown)/2` put it 0.26 off centre in the face tile
(Blender's is 0.169). Set it to eyes + 0.4 ipd up: face now 0.17, matching Blender.

## 13:10 --pair-blender on study_woman | kind=win (first time)
`--views face,eyes,face_3q,head_side,head_back,hands,full --presets clear_midday,overcast --pair-blender
<scratch copy of review/study_woman/close>`: 15 s, exit 0, 9 of 10 views paired at Blender's distances (face
0.6, eyes 0.4, head 1.0, hands 0.5); `full` named as having no Blender twin; Blender-only bust, crotch,
knees, feet, foot_inner.L, foot_outer.L listed. Sheet 1160x4286: the Blender and Godot tiles line up view
for view (same frame widths: face 0.280 m, face_3q 0.306, head 0.471, hands 0.236). The hair and brow loss
of NEXT.md's baseline is visible at once in the pair (Blender's hairline strands vs Godot's shell).

## 13:11 controls | kind=fail then fix
- `--aim-offset hand_palm.L=0.12,0,0` first reported "knuckle, tip behind the camera": `is_position_behind`
  tests the near plane, which hand views pull up to the hand. Now: behind the eye (camera-space z). Then the
  same x offset passed (off 0.208): the palm camera looks mostly along x, so an x offset moves it along the
  view. The control uses `0,0.12,0` (across the view): OFF_TARGET at 0.52, while the forearm fills 48% of the
  tile - so neither EMPTY_TILE nor SUBJECT_SMALL could have caught it. Known limit, same as the Blender
  set's: the check is centroid-only; a camera that cuts the fingertips with the centroid inside passes.
- face `0,3,0`: EMPTY_TILE (0.0%), plus SUBJECT_SMALL and OFF_TARGET (off 11.28, the free value).
- `--min-subject 0.95`: SUBJECT_SMALL (40.8%); `--min-subject 0.3` passes.
- `--label inside`: LABEL_OVER_HEAD, head px [291,19,349,114] under band [0,0,407,61]; default band
  [0,-64,640,0] is clear.
Selftest now 18 controls (was 11), 49.5 s on study_woman, PASSED.
