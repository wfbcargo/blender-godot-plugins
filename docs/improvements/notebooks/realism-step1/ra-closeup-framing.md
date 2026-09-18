# ra-closeup-framing lab notebook

Branch `ra-closeup-framing` (plugins, cut from main 9007067). Task: NEXT.md Step 0.5 "the look set's framing" plus the
Step 0 open items: every subject point inside the tile with a shifted-camera control; hand_back from the front;
`[review] close = false` removes a stale close/ and drops the close part from review's hash; right-foot side views.
Seam: rig-anything closeups.py; in character-pipeline only run_review's close handling and quality's close part
(cp-cascade-stop owns runner._build and the other hashing). No game worktree (no game file changes).
Scratch: `C:/Users/pauli/AppData/Local/Temp/rw/ra-closeup-framing/` (p/ = project copy with study_man and
study_woman specs whose `[export] blend` points at blend/, a copy of the real blends; lib/ = humanform library copy;
build.sh sets PROJECT, *_SCRIPTS and HUMANFORM_LIBRARY to this worktree; look.sh/py/look.py open a scratch blend
and run closeups.look_set with overrides). tools/scratch_project.py does not exist on main yet: made by hand (3 min).

## 13:02 baseline resumed build of study_man (main code) | kind=win
37.4 s, rc 0; every stage ran (the copied blend's records were made against other paths). review 9.3 s.

## 13:04-13:06 every subject point in the tile | kind=win
closeups.py: `MARGIN = 0.04`; a tile fails `cut` when any subject point projects closer than that to an edge,
alongside the centroid check. The free value is `subject_margin` (the worst point's distance inside the edge,
negative outside; in close.json and the manifest summary). Subjects now: hands - wrist, the thumb and four finger
knuckles, the five fingertips (end bones' tails; the old extrapolated tip is gone); face/face_3q - the head and
both eyes; eyes - both eyes; feet and the side views - each foot's ankle, heel and toe tip. A rig has no heel
bone: `_heel` takes the body's rearmost vertex below the ankle within a foot's reach (fallback: an offset).
First full set on study_man: every tile ok, margins 0.09 (foot sides) to 0.37.

## 13:06 right-foot side views | kind=win
foot_inner.R / foot_outer.R, the left ones mirrored (camera away from / toward the other foot; the inner view
clips the other foot and drops the key shadow as the left did). First try; subject_off and margin identical to .L.

## 13:06-13:09 hand_back | kind=fail -> fixed (4 attempts)
Old: from the hand's outer side (+0.25 front): thigh half the tile, nails hidden.
1. (outer 0.6, front 1, up 0.6) "front and above the knuckles": the thigh behind the hand fills most of the tile,
   coverage 0.66; curled fingertips hide the nails. (1,0.6,1.0), (0.3,1,1.2), (1,1,1.8): same, the higher the
   worse - from above, the thigh is what lies behind the hand.
2. A far clip: nothing further than the subject's deepest point + 2 cm is drawn (`far_behind`). The thigh is gone
   from every direction tried; coverage drops to the hand alone (0.27-0.41).
3. Heights with the clip: from above (0.7,1,0.4) a bit of thigh in front of the clip plane stays and the nails are
   hidden; from level or a little below the knuckles (1,0.7,-0.2), (1,1,-0.6), (0.5,1,-0.3) the nails of the
   thumb, index and middle finger face the camera.
4. Chosen `HAND_BACK = (1.0, 0.8, -0.4)` + `HAND_BACK_BEHIND = 0.02`: at 1024 px on study_woman the back of the
   hand, the knuckles and the thumb, index and middle nails read; no thigh. Mirrored on .R. So the camera is in
   front and outside, a little *below* the knuckles, not above as the task guessed: from above the nails are hidden.

## 13:08 controls on study_man | kind=win
palm camera moved 6 cm up (the Step 0 critic's case): fails `cut` (index/middle/ring/thumb tips, margin -0.116)
and now also `off_centre` (0.388: the centroid includes every tip and knuckle, so it sits lower in the tile).
3 cm up: `cut` only (middle tip 0.022 inside the edge), centroid still central - the every-point check alone sees it.
The correct palm: margin 0.158, ok. 3 cm is about where the margin runs out ((0.158-0.04) x 0.23 m = 2.7 cm).

## 13:10 close = false in the pipeline | kind=win
stages.run_review: with `[review] close = false` it calls `clear_close` (removes only what look_set writes - pngs,
close.json, .gdignore - then the folder if empty) and reports `close_removed`. quality: `PART_ON = {"close": spec's
review.close}`, `stage_parts(stage, ch)`, `for_hash(q, stage, ch=None)` leaves an off part out. The one line
outside the seam: runner.stage_hash passes `ch` to `for_hash` (no other runner change; note for cp-cascade-stop's
merge). A spec with close on hashes exactly as before (pipeline_hashes: no existing flip or stage list moved).

## 13:10-13:13 fixtures (regress --only pipeline_hashes pipeline_woman) | kind=win
First try, both CHANGED only in the new/close keys (diff read, nothing outside close.* / the new row):
- pipeline_hashes: new row "final close-up views, [review] close = false": moved [] (ok); control (PART_ON
  emptied, the old behaviour) sees review move. final_hash_part_review: full {close: ...}, noclose null.
- pipeline_woman (fixwoman, sports top): 19 files (17 views + under_bust + sheet), every tile ok, margins
  0.12-0.5; control_palm_up_6cm -> [cut, off_centre] (margin -0.13, off 0.40); control_palm_up_3cm -> [cut] only
  (margin 0.02, off 0.27); control_wrong_bone still raises on hand_palm.L (first reason now `cut`); speck control
  unchanged; close_off: had the folder, review with close = false removed it and reported it, no close in the
  report; its control (clear_close a no-op) leaves the folder, so the check sees it. hand_back coverage 0.80 -> 0.29
  (the hand alone). Timing: pipeline_woman review 5.6 s.

## 13:15 goldens | kind=win
`regress --only pipeline_hashes pipeline_woman --update --twice --jobs 2`: 2 ok, both builds agree. Diff read:
only the close block of pipeline_woman (new controls, close_off, right-foot tiles, subject_margin, the first
reason of the wrong-bone control now `cut`, subject_off of face/face_3q/feet/foot sides moved because their
subjects now include the eyes and heels) and pipeline_hashes' new row and final_hash_part_review; plus stamps.

## 13:15-13:18 real specs through the pipeline (scratch, final) | kind=win
study_man 41.7 s, study_woman 55.6 s (every stage reran: the rig-anything version is in every stage's hash),
review 10.0 / 10.2 s, 19 files each in close/, every tile ok. Opened hand_back.L/.R of both: the back of the hand,
knuckles, and the thumb, index and middle nails; no thigh at all (the hand alone covers 0.29-0.30 of the tile,
against 0.66-0.80 before). The right-foot tiles mirror the left. Seen, not this branch's: a pale rectangular
patch at the thumb's base on the back of every hand (skin bake or mesh seam) -> skin step.
close = false on the real study_man (spec edited in scratch, resumed): only review reran (7.9 s), close/ removed,
the review sheet kept. runner.plan: review's final quality part {close: ...} with the set on, None with it off
(hash 08398051e1a5a6fa vs 0d7ffa7a3b35e187); with PART_ON emptied (the control) the off spec hashes the close part
again. Restored close = true and rebuilt: review only, 8.2 s, 19 files back.

## 13:19-13:31 final regress --quick --jobs 2 | kind=win
`REGRESS DONE exit=0, 22 fixtures ok`, "no change", 12 min (full log: scratch final_quick.log). No --godot: no
Godot addon or export changed.

## Open
- The seam: runner.stage_hash now passes `ch` to `quality.for_hash` (one line); cp-cascade-stop owns runner.
- hand_back looks from a little *below* the knuckles, not above as the task proposed: from above the curled
  fingertips hide the nails and the thigh fills the tile. Ring and pinky nails sit behind the middle finger.
- A far clip removes the thigh from hand_back; it still casts its shadow (clipping is camera-only).
- humanform `references/critic-body.md` and lookdev `references/critic-look.md` list the Blender views with the
  left foot's side views only; the .R views are new here (those plugins were not bumped on this branch).
- A non-human rig still needs `close = false` (missing bones raise); the preview set was still not built on a
  real spec.
- Pale rectangular patch at the thumb's base on the back of both figures' hands (Blender material) -> skin step.
