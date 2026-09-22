# gap-genital-anatomy-fix notebook

Branch fig-genital-anatomy (at 2ec1200), worktree .worktrees/fig-genital-anatomy. Scratch wf3/gap-genital-anatomy-fix
(copied review-gap-genital-anatomy's assets, dev tools, specs incl. edge_big/edge_small; paths repointed).

## 02:21 stage=setup - kind=win
- Read CLAUDE.md, both prior notebooks (implementer + review). Scratch mirror by cp + sed in 1 attempt, ~2 min.

## 02:24 stage=baseline builds (study_man, edge_big, parallel) - kind=win
- Both rc=0, 30 s wall each on the unchanged 2ec1200 code. 1 attempt.

## 02:30 stage=design - kind=gap
- Static geometry cannot clear a thigh that sweeps through the scrotum (implementer tried contact weights and a
  bake-time sweep; the sweep pinched the scrotum to 2.4 cm, review issue 2). Plan: (a) the bake-time clearance
  only at rest (no swept poses -> no pinch, MPFB's shape kept); (b) two corrective deform bones hf_genital.L/.R
  (children of ft_jiggle_genital when flesh made it, else the pelvis) holding the shell's halves, faded to 0 at
  the join (no tearing), and per clip frame keyed translations solved so each half stands off the thigh skin
  of that frame: exported as ordinary bone tracks, so Godot plays it with no runtime code. Called after the
  moves stage builds the clips. (c) muscle normal: rebuild <name>_muscle_high on the fused topology
  (fused low + the muscle key's per-vertex delta through a source-index attribute) so matched still holds.

## 02:27-02:40 stage=thigh clearance v1..v3 (corrective side bones keyed per frame) - kind=fail x3 (3 builds of 27 s)
Metric = my clear_thighs report (shell verts >= 1 cm from the join more than 1 mm inside a thigh's skin, worst frame).
Before (no keys, rest-only bake clearance, i.e. MPFB's full-width scrotum): Idle 62/7.4 mm, Walk 174/24.9, Run 205/26.3, Crouch 110/11.3, Jump 108/11.5.
- v1 translation-only, min-norm cyclic projection, squash clamp 18 mm after: Idle 0, Walk 112/14.9, Run 151/17.4, Crouch 71/11.3. The squash clamp bound every hard frame.
- v2 squash as a constraint row: Walk 68/8.8, Run 159/17.7, Crouch 84/10.7; bones hit the 40 mm cap and scissored (one half up 35 mm, the other down 33).
- v3 + a turn about each half's root (12 unknowns, linearised): worse everywhere (Walk 28.8 mm, Jump 30.2) - the linearisation is wrong at the 46 deg it asked for.
- dev/slice.py (horizontal sections of the posed crotch, thigh.L red / thigh.R blue / shell green, look/slice_m_*.png) shows why: at Walk 25 the two thighs' inner skins CROSS EACH OTHER behind and around the scrotum (linear blend skinning collapses the crotch). There is no free space between the thighs at all; the only free space is forward (the V in front). A local projection from the nearest-skin normals pushes laterally into the other thigh and never finds it.
- Resolution in progress: search the escape explicitly (common forward swing about the root + forward/down travel, scored by summed depth) then the lateral projection for the rest.
- Plugin to change: humanform/genitals.py; and rig-anything should know its crotch collapses (thigh-vs-thigh self-intersection at the groin in Walk/Run) - a humancheck/limb_clearance check for it.

## 02:40-02:50 stage=thigh clearance v4..v8 - kind=fail (partial win), attempts 4-8 (each a 26-35 s build + 5 s render)
- v4 escape search (swing up to 40 deg + 30 mm travel) with the side bones over the WHOLE shell: Walk 9/6.2 mm but the shaft swung UP (reads as an erection - unacceptable for neutral figure study; look/StudyMan_a4_Walk25_low.png) and at Idle the shaft was pushed 30 mm sideways.
- v5 side bones on the scrotum only: new point attribute hf_genital_scrotum (0 shaft .. 1 scrotum) from WHICH MPFB target moves the vertex (penis-testicles moves 78 helper verts = scrotum; penis-length 49 + penis-circ 105 = shaft), diffused to unmoved verts; carried by the bake and the subdivision. Worked first time. But the 40 deg swing flipped the scrotum up in front of the shaft (a5_Walk25_low).
- v6/v7 swing <= 16 deg, travel <= 30 mm; v8 solve only the verts the bones can move and a 1.5 mm margin (4 mm made every resting contact a 'shortfall' and moved the Idle scrotum 30 mm into a finger shape).
- KEPT v8. Clips (shell verts >= 1 cm from the join more than 1 mm inside a thigh, worst frame): Idle 62/7.4 -> 0; Walk 174/24.9 -> 61/7.3; Run 204/26.3 -> 112/11.5; Crouch 110/11.3 -> 69/16.2; Jump 108/11.5 -> 52/9.1. Moves stage 5.9 s -> 12.8 s (kind=win, cost ok).
- Rest shape (issue 2) FIXED by dropping the swept bake clearance: width/height at 10/30% of the lower shell 0.46/0.55 (MPFB helper 0.54/0.67; before this fix 0.23/0.30). The remaining 15% is Catmull-Clark shrink from the one subdivision.
- OPEN (resisted 8 attempts - stopping per the 3-attempt rule): what stays inside is (a) the SHAFT and the root band (<2 cm from the join), which no side bone holds - in Crouch the flexed thighs close on the shaft (27 mm at f7 in the unkeyed state); (b) Run frames where the thighs' inner skins cross each other through the whole crotch (look/slice_m_Walk25.png). Real fix: rig-anything/humanform crotch weights or a pelvis-space corrective for the thigh-vs-thigh collapse (the body's own problem), then a shaft corrective; or a Godot runtime collider (follow-through jiggle vs thigh capsules).
- friction: I ran `git stash` + `stash apply` as a backup - the stash is shared by every worktree of the repo, so it would show up for other agents; dropped it at once. Don't use stash in a shared repo with parallel worktrees.

## 02:52 stage=muscle normal with genitals (issue 3) - kind=win (1 attempt, ~6 min)
- genitals.mark_source (int point attr hf_src = pre-fuse index, -1 on the shell) before fuse, genitals.refit_high after: the muscle stage's
  <name>_muscle_high rebuilt as the fused mesh + the high's per-vertex offset at the source vertex. character-pipeline run_bake calls both
  when [muscle] output = "normal". edge_big through the pipeline: muscle_high faces 13560 -> 14144 (= the fused skin), bake method
  'matched' (was 'rays'). Its "map is flat" warning also appears on edge_big with genitals = false (edge_big_off built for the comparison):
  heavy 52-year-old body, next to no definition - pre-existing, not this change. Fixture man now has [muscle] output="normal": matched,
  no warnings.

## 02:58 stage=woman relief (issue 7) - kind=win / gap
- Relief amplitudes x1.45 (mons 4.5 -> 6.5 mm, labia 3.5 -> 5.5, cleft -1.5 -> -2.5). Lit look/StudyWoman_w1_Idle1_{front,low}.png: mons,
  cleft and labia pads read; Crouch from below the thighs cover the crotch (an occlusion, not a missing form). The groin crease in Walk9 is
  the same on StudyWomanOff (genitals=false) look/StudyWomanOff_off_Walk9_low.png: pre-existing hip skinning, not the relief.
- gap: hm08's ~2 cm crotch edges cap how much relief can read; a local subdivision (or a detail normal) would be the next step (humanform).

## 03:00 stage=issue 4 (groin crease beside the root) - kind=win (evidence)
- StudyManOff (genitals=false, same spec) Walk24_threeq / Walk9_low show the same jagged dark groin crease: it is the body's hip skinning
  crease, not the join (look/StudyManOff_off_*.png).

## 03:05 stage=fixture pipeline_genitals extended - kind=win (1 attempt + record)
- Added: [muscle] output="normal" (matched, no warnings), thigh_clearance per clip before/after + clearance_better gate, rest_shape
  (0.55/0.57, gate >= 0.4; old sweep gave ~0.23/0.30), chain_shares (pelvis chain 0.975 / thigh 0.025), glb corrective nodes and their
  tracks per clip. --only --twice --update 36 s (19 s + 18 s), both builds agree.
- Golden moves reviewed: clearance poses 126 -> 2 (rest only), pushed 403 -> 22, max 14.9 -> 2.0 mm; genital peak 0.065 -> 0.0647;
  walk_in_thighs (fixture's whole-body metric) worst 74 verts/14.7 mm -> 20/5.6 mm; woman relief max 4.82 -> 7.01 mm.

(clock correction: `date` said 02:49 at the entry headed 03:05 - headings from 02:40 on ran ~15 min ahead. Real times from here.)

## 02:50 stage=evidence: humancheck + open edges (issues 8) - kind=win (1 attempt, parallel with inspect, ~40 s wall)
- humancheck_cli on the pipeline-built blends: StudyMan 0 fail / 2 warn / 30 pass (128 open edges, 0 non-manifold); StudyManOff
  (same spec, genitals=false) 0 fail, 128 open edges - identical, so the join raises nothing; StudyWoman 0 fail, 110 open edges.
- review's dev/inspect.py on study_man: 6 pieces, shell in piece 0 (the body), open edges on the body's piece 0, touching the shell 0,
  0 non-manifold, 0 unweighted.
- Its thigh metric (ALL shell verts incl. the shaft and root, thigh-dominated faces): study_man Walk 11.5 mm (review 14.9), Run 14.7
  (15.5), Crouch 27.3 (27.3), Jump 30.1 (16.1 - WORSE: the old sweep's pinch also narrowed the shaft's root; the shaft has no corrective),
  Idle 2.3. edge_big: Walk 8.4 (25.0), Run 8.8 (23.3), Idle 1.0 (10.7 at rest), Crouch 13.0, Jump 14.1.

## 02:51 stage=evidence: glb weights and bones (issue 9) - kind=win (2 attempts: system python has no numpy -> ran the glTF parse in
Blender's python, 1 min lost)
- dev/glbw.py: 1042 glb vertices on the shell (KD match to the blend's shell). Shares ft_jiggle_genital 0.479, spine 0.180, hf_genital.R
  0.159, hf_genital.L 0.158, thigh.L 0.014, thigh.R 0.011 -> pelvis chain 0.975 (spine -> ft_jiggle_genital -> hf_genital.L/.R, the node
  parents in the glb), thighs 0.025. Every clip (Idle, Walk, Run, Crouch, Jump) has hf_genital.L/.R translation+rotation(+scale) tracks.
- friction: "pelvis-dominant" per bone no longer holds once correctives exist; the fixture now records chain shares instead.

## 02:52 stage=evidence: Godot verify_flesh (issue 10) - kind=win (1 attempt; import 2 s, verify <1 s)
- Scratch project gap-genital-anatomy-fix/godot, addons copied from my worktree, study_man.glb from the pipeline build: FT_SUMMARY
  PASSED. genital: within_body true, within_limit, moved, limit 0.0179 m, peak 0.0179, free peak 0.0383, on limit 0.5% (4 jump ticks),
  820 ticks over the course (settle, walk, turn, RUN, stop, jumps). The corrective tracks play under the jiggle bone with no runtime code.
- gap (still, not mine to fix here): within_body tests the jiggle offset against peak_m only - it cannot see skin in a thigh
  (follow-through verify_flesh.gd should get a neighbouring-skin clearance check).

## 02:53 stage=renders (issue 4-7, 10) - kind=win
- look/final/*.png: StudyMan Idle14_threeq, Idle1_low, Walk9_low, Walk24_threeq, Walk25_low, Run4_low, Run16_threeq, Crouch6_low,
  Crouch7_threeq, Jump4_low; StudyWoman Idle1_front/low, Walk9_low, Crouch7_front; EdgeBig Idle18_front/threeq, Walk11_low.
  Render batch ~15 s wall for 17 shots in 3 parallel Blenders.
- gap: EdgeBig's genital_shape all 1.0 makes the shaft 26 cm tall (shell extent z 264 mm vs 105 on study_man): MPFB's penis-length-incr
  moves a vertex up to 1.625 dm (16 cm). The spec's 0..1 maps straight onto MPFB's extreme; a figure-study range should cap the incr side
  (humanform genitals._shape / character-pipeline spec). Not changed here (the fixture pins the decr side only).

## 02:54 stage=commit 94ac682 - kind=win. Full regress --twice --jobs 2 started.

## 03:05 stage=final regress --twice --jobs 2 on 94ac682 (issue 11) - kind=win / slow
- rc=0, 653 s wall (kind=slow; cricket 128+130 s, rabbit 126+126 s dominate). All 21 fixtures ok, both builds agree, "no change":
  every existing golden unchanged on the default-off path; pipeline_genitals matches its new golden.
- Session ~45 min of work. Open at hand-off: DONE-WHEN not met on "no thigh intersection" - the shaft and root band have no corrective
  (study_man Crouch 27 mm, Jump 30 mm on the review's all-vertex metric) and Run frames where the thighs cross the whole crotch
  (11.5 mm on the scrotum). Next: a shaft corrective bone with a forward/down-only escape, or fix the body's crotch collapse
  (rig-anything/humanform crotch weights), or a Godot thigh-capsule collider in follow-through. Also: cap genital_shape's incr side.
