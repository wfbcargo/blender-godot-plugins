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
