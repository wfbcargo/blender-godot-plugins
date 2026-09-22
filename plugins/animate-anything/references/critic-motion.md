# Motion critic checklist (a round's pick list)

Questions a round's done-when and its motion critic **pick** from. The protocol, the JSON a critic returns,
how to read a review strip, the keep-or-revert rule and the full per-clip question bank are
`motion-critic-checklist.md`'s, and this file does not repeat them: it gives each question an id, names the
one strip, manifest key or verifier that answers it, and adds the questions only the engine can answer
(the strips are Blender renders). Every question is yes/no with `yes` good. A critic answers `unclear` when
the source named is missing, never from another picture.

## Sources

| name | what | where |
|---|---|---|
| **strip `<Clip>_<view>`** | eight frames of one clip, `front`, `right`, `three_quarter`, workbench-lit, floor line in orange | `<glb dir>/review/<id>/<Name>_<Clip>_<view>.png` (e.g. `StudyWoman_Run_right.png`), `contact.png`; written by every export |
| **review.json** | per strip `cells_with_body`, `distinct_cells`, `edge_cells`, `centred`; `frames`, `ortho_scale_m`, `cell_px` | beside the strips |
| **manifest** | `clip_checks.<clip>` (`passed`, `lowest_foot`, `loop_seam`, `failures`), `arm_pose.<clip>.<arm>` (`hand_rise`, `elbow_flex_deg`, `upper_arm_deg`, `arm_carry_deg`, `arm_swing_deg`), `turns.<TurnL/R>` (`yaw_deg`, `floor_skid_m`), `verified`, `known_failures`, `forced_clips` | `<id>.moves.json` |
| **verify_moves** | the gait ladder in a plain MovesController: role and rate at each speed, hysteresis, stride phase carried; `MOVES VERIFY PASSED` | `godot --headless --path <project> -s res://addons/rig_anything/verify_moves.gd -- dir=res://assets/<folder>` |
| **verify_strands** | a strand chain at 30/60/120/240 fps: rest drift, kick settle, fling and run head penetration, `swing_deg`, cross-rate spread; `FT_SUMMARY ... PASSED` | `... -s res://addons/follow_through/verify_strands.gd -- scene=<glb> strands=<id>_hair.glb clip=<Name>_Run` |
| **figure_study selftest** | every clip played to its end, turn hand-off keeps the feet, flesh and strands finite and moving; `FIGURE_STUDY SELFTEST PASSED` | `godot --headless --path <project> figure_study.tscn -- --selftest` (grungist-creek) |

## Question bank

### Numbers first (each is a locked number in `motion-critic-checklist.md`'s keep-or-revert rule)
- **MOT-N1** Does every clip pass its checks - `clip_checks.<clip>.passed` true, `failures` empty, and
  `known_failures` and `forced_clips` empty? *manifest*.
- **MOT-N2** Has no `arm_pose` range moved toward its limit since the previous version? *manifest* `arm_pose`
  of both versions (`unclear` when the previous has none).
- **MOT-N3** Does each turn keep its pivot foot planted - `turns.<turn>.floor_skid_m` 0 for both legs - and
  turn the named `yaw_deg`? *manifest* `turns`.
- **MOT-N4** Is every strip complete - `cells_with_body` 8 and `edge_cells` 0 on every strip? *review.json*.

### From the strips (the bank's sections, by id)
- **MOT-S1** "Every clip": on or above the floor line, no limb through the torso, head upright and facing the
  travel. *strip `<Clip>_front`, `<Clip>_three_quarter`*, every clip.
- **MOT-S2** "Walk and run": arms opposite the legs. *strip `Walk_front`, `Run_front`* only (a side view cannot
  tell the arms apart - the checklist's blind spots).
- **MOT-S3** "Walk and run": hands between hip and chest, elbows bent and more bent in the run; torso upright,
  leaning a little in the run. *strip `Walk_right`, `Run_right`*; *manifest* `arm_pose` `hand_rise`,
  `elbow_flex_deg`.
- **MOT-S4** "Walk and run": a flight phase in the run and none in the walk; each foot landing under or behind
  the knee. *strip `Run_right`* (check `frames` against the clip length before calling it: eight frames
  alias).
- **MOT-S5** Eight different poses in each gait, not one pose slid sideways? *review.json* `distinct_cells`
  (8 for a gait; 4-5 is normal for an idle or a launch) and *strip `Walk_right`*.
- **MOT-S6** "Idle": arms hanging with gravity, weight over the feet, some motion? *strip `Idle_right`*,
  *manifest* `arm_pose.<Idle>` `arm_swing_deg`.
- **MOT-S7** "Crouch and jump": heels down and knees over the feet in the crouch; arms swinging on the launch
  and knees absorbing the landing? *strip `Crouch_front`, `Crouch_right`, `Jump_right`*.
- **MOT-S8** "Posture": the brief's stoop or lift in the spine, the same in the idle and the walk? *strip
  `Idle_right`, `Walk_right`*.
- **MOT-S9** "Outfit" (dressed): no skin at a hem, no cloth through the body, a loose hem lagging the body?
  *strip `<Clip>_three_quarter`* of the dressed sheet, with wardrobe's numbers
  (`wardrobe/references/critic-fit.md`).

### In the engine (the strips cannot show these)
- **MOT-G1** Does the gait ladder play the right clip at the right rate from standing to the fastest gait and
  back, with the stride phase carried across each change? *verify_moves* `MOVES VERIFY PASSED`.
- **MOT-G2** Does every clip play to its end in the game scene, and each turn hand its facing over without
  moving the feet? *figure_study selftest* `FIGURE_STUDY SELFTEST PASSED` (its per-clip `FIGURE_STUDY ok`
  lines).
- **MOT-G3** Does a strand chain (a ponytail) swing on the run by about the same amount at every frame rate -
  `swing_deg` max/min within 1.25 across 30-240 fps? *verify_strands* (study_woman's ponytail read 1.26 at
  Step 0: a known `no`).
- **MOT-G4** Does a strand stay out of the head - `head_penetration_m` <= 0.005 in the fling, run and hitch -
  and settle after a kick? *verify_strands* per-rate `FT_STRAND` lines.

## Not answerable from these today

- Whether a Run was judged as a run: rig-anything never sets `U.running`, so the run-only arm checks never
  run (NEXT Step 5); `clip_checks` of a Run are a walk's.
- Per-frame arm angles (which arm is forward on a frame): no file keeps them; alternation is MOT-S2 from
  `front` only.
- Flesh swinging on a clip: Blender's strips do not simulate the jiggle bones - that is follow-through's
  `verify_flesh` (`follow-through/references/critic-flesh.md`).
- Motion in Godot as a picture: the close-shot poses one frame (`--clip`, `--time`); there is no Godot strip.
