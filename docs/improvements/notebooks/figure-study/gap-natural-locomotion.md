# gap-natural-locomotion lab notebook

## 00:35 setup | kind=win
Worktree .worktrees/fig-natural-locomotion from main b496738; scratch copied from wf3/draft (build_human.py, save_guard, specs, hflib). Specs: roles += TurnL, TurnR. Took 1 attempt, ~2 min.

## 00:45 diagnosis: implied speed 0.7 of natural | kind=gap
locomotion.cycle keyed every walk at a fixed 32 frames (runs 24) whatever the stride period. StudyMan's natural period is 0.975 s (1.026 Hz) but 32 frames @24 fps = 1.33 s, so implied = stroke/(duty*frames/fps)*frames/(frames+1) = 0.818 vs natural 1.154 (ratio 0.71 = 0.975/1.333*32/33). Same on Belle/Nadia. Fix: frames = clamp(round(period_s*fps), FRAMES_MIN 16|12, old 32|24). Walk now 23-24 frames, run 15-16. First attempt. Wall ~10 min reading code. Change: rig-anything locomotion.py.

## 00:50 diagnosis: knee flexed at mid-stance | kind=gap
The plan drops the hips by ONE amount for the whole cycle (needed at the stroke extremes; adult style caps at 3.5% of hip height = 3.2 cm). MPFB legs rest at 0.9982 of full length (7 deg flex) so a 3.2 cm drop is ~30 deg flex everywhere: measured 31.7 deg at mid-stance (new report field stance_knee_flex_deg). Walk bounce (0.015 h) is far too small to undo it. Also Fr asked 0.2 achieved 0.147: the toe-contact stroke was centred on the standing toe (centre_weight ~0 for walks), the front of the stroke did not fit, duty was cut 0.65->0.55 and stride to 86%.
Fix (attempt 1, worked): (a) vaulting walk - per phase, the least hip drop that lets every stance leg reach its contact (Reach.tilt bisection, 96 samples), eased by a parabola of VAULT_CURVE=6 leg/cycle^2 so hips don't snap at touchdown; replaces the load bounce for upright 2-leg walks (option vault=False restores). (b) BIPED_WALK_CENTRE=0.6 floor on centre_weight for an upright biped walk (heel-toe roll puts the toe's stance line behind the standing toe).
Numbers StudyMan: Fr 0.147->0.200, duty 0.55->0.61, stride 1.125->1.313 m, natural 1.154->1.347, implied 0.818->1.313 (0.974), knee mid-stance 31.7->11.5 deg, vault drop 0..2.5 cm. StudyWoman: natural 1.289 implied 1.254, duty 0.643, knee 11.5. Iteration via a single-role script on the saved draft .blend: 6 s per try (kind=win: much faster than a pipeline build).

(times below are wall clock; the two entries above were written ~00:40-00:44, not 00:45/00:50)

## 00:44 relaxed hands | kind=win
keyposes.hand_digits: hand = arm limb's end bone, digits = hand->leaf paths, thumb = path pointing furthest from the mean, palm plane = PCA of finger first-joint tails + wrist, palm side = where thumb tip and the fingers' own rest bend lie (both agreed on MPFB L and R: -0.056 / -0.042). Curl per joint (14,22,16,10), thumb (18,12,10,8), applied at the end of Poser.blend for every clip; Key.hands scales per arm; gait lag HAND_LAG 0.08 cycle, +-25%. Ground rest now includes the curled hands (like folded wings) so "frame one is rest" holds. First attempt passed every clip. Bone roles only, no names.

## 00:46 TurnL/TurnR | kind=win
actions.turn: whole-body rotation about the inside foot's contact pivot (toe tail + stance shift), outside foot lifted (8% leg), carried round in the air, the yaw only while it is off the floor; hips sway 0.5 of hip gap over the pivot. Checked by _check_common with skid=True (floor-skid on both contacts through every on-floor run): skid 0.0 both, all pass first attempt. Report + manifest carry turns {yaw_deg, pivot_leg, pivot_m, end_offset_m}. move_set hands Idle's stance/posture/style to turns. 1 attempt, ~6 min.

## 00:47 idle breath | kind=win
BREATH_CHEST_DEG 1.5: upper.trunk pitch on the torso with the idle's breath phase, head held. Passed first run.

## 00:49 pipeline builds at preview | kind=win / slow
study_man preview build 44.3 s (body 10.4, moves 16.0 [was 7.4 draft w/o turns], export 8.3, review 4.3); study_woman 44 s. Both: 7 roles, all clip_checks pass, no forced clips. Walk implied 1.304 vs natural 1.343 (97%), woman 1.253 vs 1.288 (97%); stance knee 11.5 deg both; Fr 0.2 achieved; duty 0.615 / 0.643. arm_swing: walk swing 41.9 deg, carry -10..31.9 (passes, it comes back through hanging).

## 00:52 look renders + Godot verify | kind=win
Lit close-ups (draft look/lit.py extended: hand close-ups, turn mid/end) in gap-natural-locomotion/look/. Walk side: stance leg straight at mid-stance, fingers curled, palm toward the thigh in idle, thumb forward. Fingers still spread sideways a little (no adduction) - noted, not fixed.
Godot scratch project (addons/rig_anything copied from worktree, both glbs+manifests): import 5.9 s, verify_moves.gd 0.7 s, MOVES VERIFY PASSED 18/18. Walk now plays x1.03 at its natural speed (was ~x1.41 with the 32-frame clip). MovesController does NOT consume turns yet (manifest has them) - gap for the Godot side.

## 00:53-01:02 regress (full, once) | kind=slow
python tools/regress.py --jobs 2: 8m45s. 8 fixtures CHANGED, none failed: cricket, flesh_figure, mpfb_woman_curvy, pipeline_ponytail, pipeline_woman, quadruped, rigify_human, strand_ponytail. Friction: the output was piped to tail -60 so I lost the per-fixture list and re-ran the 8 with output to a file (3m39s wasted). Lesson for tests/README: always `> log` a full regress run.
Moves: frames now follow the natural period for every body with legs, so quadruped Walk/Trot/Run 33/25/25 -> 17/13/13 (clamped at FRAMES_MIN) and cricket Walk 33->17; their implied speeds double (dog walk 0.44->0.85, still below natural - clamped). MPFB women: Fr 0.163->0.2, duty 0.55->0.627, knee 11.5, walk frames 33->24, implied 0.80->1.23. Idle hand_rise moves ~1 mm from the chest breath. New report keys stance_knee_flex_deg, vault, vault_drop_m.

## 01:03 fixture extended | kind=win
mpfb_woman_curvy: roles += TurnL, TurnR; report "hands" (bones and degrees hand_digits found). 35 s.

## 01:04-01:10 goldens re-recorded | kind=slow / friction
--twice --update --jobs 2 --only <8>: 6m03s, deterministic (no NONDETERMINISTIC). The known --update noise (temp paths, seconds) rides along in every rewritten golden (NEXT.md item 8); left as is, comparison ignores it. The cricket alone is ~145 s a build - the long pole.

## 01:15 motion critic checklist (self-run, NOT an independent critic) | kind=gap
No subagent tool in this session, so the checklist was answered by the author - the protocol wants a critic that did not author the clips. Questions written from the brief before opening the preview strips (though I had already seen the draft walk_right and my lit renders - honest caveat):
- Walk_right (both): fingers curled, not flat, every cell? YES - curl visible at f1/f5/f12/f16 and in the lit close-up (look/StudyMan_walk_hand_R.png); fingers still spread sideways (no adduction) - carriage, minor.
- Walk_right: stance leg near straight at mid-stance? YES - f9/f20 (man), f8/f19 (woman) show a straight stance leg; manifest stance_knee_flex_deg 11.5 both legs.
- Walk: hands below the chest through the swing? YES - arm_pose hand_rise max -0.001 (man) / 0.023 (woman), arm_carry -10..31.9 deg.
- Walk: forward arm opposite forward leg? YES every cell.
- Idle: palm toward the thigh, fingers relaxed? YES - look/StudyMan_idle_hand.png: palm to thigh, thumb forward and a little out.
- TurnL_front: ends facing its left? YES - f25 in profile facing image right (her left). Pivot foot fixed? YES by floor_skid 0.0 and the strip. Stepping foot up while travelling? YES f11-f15.
- Run: reads as a run with flight? not re-judged (unchanged except frames).
No gross issues. Answer to the task's two questions: relaxed hands YES, straight stance leg YES.

## 01:13-01:34 full regress --twice --jobs 2 | kind=slow / win
~21 min wall, all 19 fixtures ok and deterministic on commit 9ebb810. Long poles: cricket 207 s x2, rabbit 200 s x2 (they dominate; worth a --fast path in regress.py). Waiting cost: my first "until" waiter hit the 600 s Bash cap twice - use Monitor or a background waiter from the start.

## Open (for the user)
- MovesController (Godot) does not play TurnL/TurnR or apply manifest `turns` (yaw + end_offset) - rig-anything godot addon.
- Fingers are curled but not adducted (still spread sideways); palm of the forward-swinging hand still turns forward a little (no forearm pronation twist) - keyposes.hand_digits / upper.arm_spec.
- FRAMES_MIN clamps small creatures (dog 17/13 frames, cricket 17): their clips still play slower than natural; the engine time-scales them. Belle/Nadia/crowd not rebuilt (not allowed on this branch) - they get the fix on their next rebuild.
- Critic checklist was self-answered, not by an independent critic.
- StudyMan walk natural speed 1.343 m/s is just above the "about 1.1-1.3" band (Fr 0.2 at hip 0.925 m); implied 1.304.
