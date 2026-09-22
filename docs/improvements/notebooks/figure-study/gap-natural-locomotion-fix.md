# gap-natural-locomotion-fix lab notebook

## 01:46 setup | kind=win
Scratch copied from gap-natural-locomotion (assets, blend, characters, hflib, look, godot, iter) + review's styles.py probe. Worktree already at 9ebb810. 1 attempt, ~3 min reading prior notebook + review.

## 01:48 blocking 1: styles lost under the vault | kind=fail -> fixed (attempt 1)
locomotion.py: "vault" added to STYLE_KEYS (and threaded through cycle's style_args, so a style may set it); elderly_shuffle and heavy walk sections get vault False (a shuffle / a heavy body sinks into each stance leg); bounce_scale now scales the vault profile's rise and fall (anchored at the profile's highest drop when <1 so the hips stay low = softer knees, at its lowest when >1 so they sink further in double support; capped at the drop limit).
Probe (styles.py on study_man.blend, Fr 0.2, 16 s): adult knee 11.5/11.5 range 0-25.3 mm (unchanged); elderly_shuffle 26.9/25.3 no vault (was 11.5); heavy 36.0/35.1 no vault (was 12.1/11.5); child vault 0-25.1 mm (was 0-16.8; linear bs 1.5 of its own shorter-stride need, so now equal to the adult's, not above it - a child's stride is 0.88 so its unscaled need is 0.66 of the adult's); relaxed (bs 0.9) 2.6-26 mm.
Plugin to change so it never costs time again: a styled walk in a fixture headline (next).

## 01:51 blocking 2+3: thumb C-grip, clawed spread fingers | kind=fail -> fixed (2 attempts)
keyposes.hand_digits rewritten: curl table (22,20,12,8) knuckle-heavy (was 14,22,16 = tip-heavy claw), cascade +10%/finger from the index (index 0.9 .. pinky 1.2), each finger's base closed toward the hand's mean finger direction in the palm plane (FINGER_CLOSE of the angle, capped), thumb base swung toward a spot beside the index finger's middle joint (THUMB_IN 0.7, cap 30 deg) instead of curling across the palm (thumb table 0,10,8,6). Each base bone's close/swing and curl compose into one axis-angle entry, so Key.hands' share scaling still works. Index/thumb found by role: thumb = path furthest from the mean (as before), index = finger root nearest the thumb root. StudyMan R: index.01 23.8, middle 22.0, ring 25.9, pinky 29.8, thumb.01 24.9 deg.
Iteration script iter/handit.py (move_set Idle+Walk on the saved blend + 4 EEVEE hand close-ups): 7-11 s a try (kind=win). Friction: out=relative path wrote the pngs to C:\iter (Blender resolves // against the drive root when the blend is elsewhere) - always pass absolute out=.
Attempt 2 (FINGER_CLOSE 0.6->0.85, cap 10->14) looked nearly identical: the remaining tip gaps come from MPFB's rest fan in the .02/.03 bones plus the mesh's finger valleys; kept 0.85/14.

## 01:53 scratch leak | kind=fail (mine) / friction
The copied specs carry [export] blend = an ABSOLUTE path into the previous agent's scratch (wf3/gap-natural-locomotion/blend). My first pipeline build therefore saved study_man.blend over that folder's copy (32 s build). Fixed the two specs to point at my scratch and rebuilt. Plugin to change: character-pipeline spec should accept a relative [export] blend (resolved against PROJECT/BLEND_DIR) and the runner should warn when the save path lies outside PROJECT and BLEND_DIR. Also run.sh's BLEND_DIR is ignored when the spec names a blend - confusing.

## 01:57 fixture: styled walks + manifest field list | kind=win
rigify_human gets styled_walks (child, elderly_shuffle, heavy at Fr 0.2, after the export so the clips stay out of the glb): child vault 0-29 mm (capped at its max_drop), knee 11.5; elderly no vault, knee 41.0; heavy no vault, knee 33.3. _harness.moves_manifest keeps the full  list (review gap: stable(max_list=16) collapsed it to first/last/len once  made 17). regress --only rigify_human mpfb_woman_curvy: 41 s, both CHANGED as expected, nothing failed. First try.

## 01:57 blocking 4-7: evidence | kind=win
Rebuilt both study figures through character-pipeline at preview (force=1): 25 s / 24 s wall (stages man: body 5.3, moves 9.4, export 4.7, review 3.8). Manifests: roles Idle Walk Run Crouch Jump TurnL TurnR, all 7 clip_checks passed, forced {}; Walk natural 1.3427 / implied 1.3041 (97.1%), woman 1.2882 / 1.2525 (97.2%); stance_knee_flex_deg 11.5/11.5 both; turns listed with yaw +-90. New: manifest turns carry floor_skid_m {thigh.L 0.0, thigh.R 0.0} and skid_tolerance_m (0.0089 man / 0.0083 woman) - actions.turn report -> export.
Independent pivot measurement (look/evidence.py, world positions per frame): pivot ball (toe head) drift 0.0000 m, height fixed at 9.1 mm (man) / 11.0 mm (woman); pivot heel swings 0.196 / 0.186 m round it (the foot rotating about the ball); stepping foot lifts to 7.8 / 7.5 cm. Review strips at preview exist for all 7 roles x front/right. Lit evidence in gap-natural-locomotion-fix/evidence/.
Godot scratch project (addons copied from the worktree, both glb+manifests): import 3 s, verify_moves.gd MOVES VERIFY PASSED 12/12, Walk x1.030 / x1.029. First try.

## 01:58 motion critic questions, written before opening this build's strips | kind=gap (self-answered)
No subagent tool in this session again, so the author answers (protocol wants an independent critic). Questions (yes = good):
Q1 Walk_right f9/f20 (man), f8/f19 (woman): is the stance leg near straight at mid-stance? Q2 Walk_right all cells: are fingers curled, not flat? Q3 Walk_right: forward arm opposite forward leg? Q4 Walk_right: hands below chest? Q5 Idle_front: arms hang, hands beside thighs, fingers relaxed (lit idle_hand: thumb along the index, no C-grip)? Q6 Run_right: a flight cell? Q7 Crouch_right: heels down, hips and knees fold together? Q8 Jump_right: knees bend on landing? Q9 TurnL/TurnR_front: ends facing its left / its right? Q10 TurnL/TurnR_front: pivot foot stays put while the other steps round (numbers: skid 0.0, ball drift 0.0)? Q11 every strip: body in every cell, nothing through the floor?
Answers (strips from this build, assets/humans/<who>/review/<who>/):
Q1 YES - man Walk_right f9/f20 and woman f8/f19: the stance leg is straight under the hip; manifest stance_knee_flex_deg 11.5/11.5. Q2 YES - curl visible at the hands in every cell; lit evidence/StudyMan_walk_hand_R.png: fingers close together, the curl spread from the knuckles (tip gaps of a few mm remain). Q3 YES every cell. Q4 YES (hand_rise max -0.001 man). Q5 YES - evidence/Study*_idle_hand.png: palm to thigh, thumb lying along the side of the index finger, no C-grip. Q6 YES - Run_right f8-ish cell airborne. Q7 YES - heels down, hips and knees fold together (Crouch_right f11-f21). Q8 YES - Jump_right landing cells bend the knees. Q9 YES - TurnL_right ends facing the camera (+X = his left from -Y forward), TurnR_right ends showing his back. Q10 YES by numbers (strips cannot show it): floor_skid 0.0/0.0 against 0.0089, ball drift 0.0000 m. Q11 YES - body in every cell, nothing through the floor line.
Relaxed hands YES, straight stance leg YES.

## 01:58-02:25 regress --twice --update --jobs 2 (full) | kind=slow
26m51s wall, all 19 deterministic. --update rewrote all 19 goldens; 7 differed only in temp paths/seconds (cricket, dressed_figure, dressed_presets, dressed_skirts, flesh_figure, rabbit, starfish) and were restored with git checkout. Real moves: rigify_human (+styled_walks), mpfb_woman_curvy (hands, arm-out clearance search, turn skid), pipeline_woman / pipeline_ponytail (arm_pose from the hands, full fields list). No pass/fail moved. Long pole: pipeline_muscle 910 s x2 (!), then rabbit 202 s, cricket 123 s. Plugin to change: tools/regress.py --update should not rewrite a golden whose only differences are the noise its comparison already ignores (NEXT.md item 8) - it cost a review pass over 7 files. pipeline_muscle at 15 min is worth a look (the prereqs notebook may have a lower number).

## 02:26 commit | kind=win
276b7b7 on fig-natural-locomotion, message explains every moved golden number. Final full --twice next.

## 02:26-02:36 final regress --twice --jobs 2 (full) on 276b7b7 | kind=win / slow
10m17s wall, all 19 ok, deterministic, no change. pipeline_muscle 50 s here vs 910 s in the --update run: the 910 s was a one-off (a cold library fit or contention), not a regression - worth regress.py printing per-stage times for the pipeline fixtures so a spike explains itself.

## Open (for the user)
- The child style now rises and falls 1.5x its own need (0-25.1 mm on StudyMan), about equal to the adult's 0-25.3 because its 0.88 stride needs less; not above it. If "bouncier than an adult" is wanted in absolute terms, child needs a larger bounce_scale or a separate rise term.
- stance_knee_flex_deg 11.5 on every vaulting MPFB walk is Reach's straight-leg cap, not a free measurement (now said in SKILL.md).
- Small gaps remain between the fingertips (MPFB's rest fan in the .02/.03 bones and the mesh's finger valleys); the base bones are closed, the distal ones are not.
- MovesController (Godot) still does not play TurnL/TurnR or apply manifest `turns`.
- Motion critic checklist answered by the author again (no subagent tool in this session), with questions written before opening this build's strips.
- character-pipeline spec [export] blend is an absolute path; copying a spec to a new scratch silently writes into the old one (happened once here, see 'scratch leak').
