# cp-close-look-set lab notebook

Branch `cp-close-look-set` (plugins, cut from main 5fda318). Task: 06 rank 1, a close-up look set in the review
stage. Scratch: `C:/Users/pauli/AppData/Local/Temp/rw/cp-close-look-set/` (p/ = project copy, blend/, lib/ =
humanform library copy, build.sh sets PROJECT, *_SCRIPTS and HUMANFORM_LIBRARY to this worktree).

## 10:35 setup | kind=win
Worktree and scratch made; read NEXT.md, 06 sections 3G/5/6, stages.run_review, quality.py, rig-anything
review.sheet, lookdev close_shot.gd (its view aiming is the model for the Blender set).
The "look checklist": there is no single file by that name. The critics' checklist is humanform
`references/critic-checklist.md` (its L4 part questions, L6 hair and L5-L6 surface are the look questions),
plus lookdev `references/judging.md` "CG tells" (scene lighting, mostly not about a character).

## 10:38-10:40 baseline builds (main code, final, scratch) | kind=win
First try, rc 0. study_man 37.9 s (review 4.2), study_woman 35.4 s (review 4.0), belle 38.0 s (review 4.6).

## 10:44 closeups.look_set, first render | kind=win
New module rig-anything `rig_analysis/closeups.py` (port of close_shot.gd's aiming to Blender: frozen posed
meshes, EEVEE, film_transparent alpha as the figure mask, labels from one workbench render of text objects).
First try rendered all 14 tiles on study_man, 3.9 s, every part framed; no failures.
Found by looking (1 attempt each, ~2 min each):
- head_back dark: lights were fixed on the body -> key/fill now follow each camera (`_aim_lights`).
- foot_inner.L showed the right foot in front -> near clip at the foot's half width (first 6 cm cut the big
  toe's side, the tile showed a dark patch there; 9 cm clean).
- palms black in shadow: the thigh (clipped out of the picture) still shadows the key -> hand views take the
  key over the camera, and the fill casts no shadow.
- label text ran off the tile -> shorter label, smaller font.

## 10:46 controls | kind=win
aim_override {hand_palm.L: hand.R, bust: foot.L, feet: head, face: +2 m x}: every one failed (off_centre 0.56-6.1,
empty 0.000 for the face). First try.

## 10:47-10:50 pipeline + builds | kind=win
stages.run_close after the sheet; quality.py `close` part (final all, preview face/eyes/hands, draft face and left
hand), in HASHED_ALWAYS so a final file reviewed before reruns review; inputs.py hashes closeups.py into review.
Resumed builds after a closeups.py edit: every stage unchanged but review ("what it reads changed:
code:rig_analysis.closeups"). Knees view added after checking the checklist (kneecaps had no tile).

## 10:52 regress --only pipeline_woman pipeline_hashes pipeline_muscle | kind=fail -> fixed
pipeline_woman: ZeroDivisionError in closeups._project (the fixture's report had no traceback; reran the fixture
by hand to get it, 1 min). Cause: the empty-tile control draws a 1 mm speck, and the frame size came from the
first mesh's height -> 0 -> fov 0. Fix: stature from the rig's bones. Second: the wrong-bone control recorded
`raised: []` because the list's repr quotes a message holding "subject's" with double quotes; regex takes both.

## 10:57-11:00 goldens | kind=win
`regress --only pipeline_woman pipeline_hashes pipeline_muscle --update --twice`: 3 ok, both builds agree. Diff read:
pipeline_woman gains a `close` block only (16 pngs incl. under_bust, every tile ok, coverage/subject_off to 2
places, controls: wrong bone -> [hand_palm.L, off_centre]; speck -> empty (+off_body) on every tile; draft
views face, hand_palm.L, hand_back.L); pipeline_hashes gains the closeups.py flip (review moves, control unseen),
the final close-views flip (only review moves) and an unrelated flip ([review] close = false: nothing moves);
pipeline_muscle's final_hash_part.review is now the close part. Plus version stamps. Nothing else moved.

## 11:01 timing (study_man, final, machine quiet, 3 runs each, from=review force=1) | kind=win
review without the set 4.1-4.8 s, with it 6.8-7.6 s: +2.8 s (close.json 2.8-3.0 s, 15 tiles).
Draft (3 tiles): the set takes 0.64 s, review 2.0-2.1 s. A timing taken while regress ran in the
background read +4.5 s: contention, discarded.

## 11:03 inner-foot toe patch | kind=fail -> fixed (attempts 3)
foot_inner.L showed a dark patch over the big toe with a straight edge. Attempt 1 (clip 6 -> 9 cm) and attempt 2
(12 and 15 cm, via a monkeypatched _aim) changed nothing: not the clip. It was the right foot, clipped out of the
picture, still shadowing the toe from the key (as the thigh did the palm). Key casts no shadow in that view.
Worth knowing: near-clipping removes geometry from the picture, not from the shadow maps.

## Look checklist answered from the PNGs alone (author, NOT an independent critic: no Agent tool here)
Checklist = humanform critic-checklist L4/L6/L5-L6 + NEXT.md realism list (mapping in character-pipeline SKILL.md).
Scratch final builds, review/<id>/close/*.png, Idle f1.
- Nose, lips, sockets, brow readable (face, face_3q): yes, all three. Eyes at ~half head height, ears between brow
  and nose base (face, head_side): yes.
- Mirror-perfect symmetry (face): man and woman read symmetric -> no. Forehead/lips not glossy (face, eyes): NO for
  the man and Belle (strong specular on forehead, nose, lips); woman milder, still shiny lips.
- Brows and lashes read (eyes): brows yes on both study figures; lashes present but sparse/clumped; Belle has no brows.
- Hairline reads as hair, follows forehead/temples/ear/nape (face_3q, head_side, head_back): NO - hard cut edge with a
  row of short spikes on all three; the path round the ear is a clean cut; nape edge visible on head_back.
- At 1 m hair reads as hair not a helmet (head_side, head_back): man no (helmet); woman partly (strand streaks, but a
  shell); Belle partly.
- Volumes attached and shaped (head_back, head_side): woman's ponytail tie reads, tail hangs clear of the neck,
  attached; Belle's bun a coiled bun, attached. No seam visible at the tie.
- Four fingers and a thumb, separate, knuckles (hand_back/palm): yes, but finger ends stubby/blunt; nails not
  readable at 0.5 m; small gaps between fingertips; no orange web creases in Blender (the Godot defect is Godot's).
  Hand ~0.19 m vs face ~0.18 m: about the face's length, yes.
- Deltoid cap, clavicles, sternum notch (bust): deltoids yes; clavicles faint; sternum notch faint.
- Top's lower edge, shelf under the bust (Belle under_bust, bust): the top spans flat from the breast underside to the
  ribcage - a shelf is visible from below. -> wardrobe.
- Crotch anatomy (crotch): smooth on both; a short cleft only (genital branch parked).
- Kneecaps (knees): faint on the woman; a thin red line on her right thigh's outer edge (image left in a front view; corrected at merge after the critic; SSS rim?) -> skin step.
- Heel, arch, toes; big toe largest; ankle bones (feet, foot_inner/outer): heel and toes yes, toes in order;
  arch faint; malleoli not modelled (inner vs outer height cannot be said to differ) -> no.
- Faceting/seams (all): none seen.
Not answerable from the set: the Godot neck stipple and pore detail past 1 m (lookdev close-shot).

## 11:05-11:16 regress --twice --jobs 2 (full, at 43eb9d3) | kind=win
`REGRESS DONE exit=0, 21 fixtures ok`, "no change", ~11 min. No --godot: no addon or export changed.

## Open
- Critics: the checklist above was answered by the author (no Agent tool in this leaf); an independent critic should
  answer it from the PNGs.
- The set shows Blender materials; the Godot look (stipple, pores past 1 m, orange webs) stays lookdev close-shot's.
- foot_inner/foot_outer frame the foot slightly right of centre (target from ankle-to-toe, the heel is behind the
  ankle); passes its check (subject_off 0.09).
- Only the left foot has side views; the right foot is seen in `feet` only.
- The pipeline does not run the set on a non-human rig (missing bones raise); `[review] close = false` for those.
- Preview quality's set (6 tiles) was not built on a real spec, only recorded in the quality table.

## Merge step (Fri Sep 18 11:30:59 CDT 2026)

- main had not moved since the branch was cut (merge-base 5fda318 = main), so no merge of main was needed; no game worktree.
- Independent critic: pass, mergeable. Fixed at merge from its list: the marketplace "Since 0.9.0" wording (draft is face and the LEFT hand), the SKILL.md hands row no longer claims nails (not visible on the curled hand), and the red streak is on the right thigh, not the left.
- Left open from the critic: framing check is centroid-only (a palm camera 6 cm up passes with fingertips cut off: needs an all-points-inside-tile check with a control); hand_back tiles look from the lateral side with the thigh filling half the tile; [review] close = false leaves a stale close/ folder; STAGE_PARTS review hashes the close part even when close = false; the preview set was never built on a real spec.
