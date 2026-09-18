# crowd - arm-swing check on the 16 crowd people (installed plugins: rig-anything 0.23.0, humanform 0.7.1, character-pipeline 0.4.0)

## 23:30 setup - win
- stage: scratch setup. Copied characters/, assets/humans/build_human.py, assets/save_guard.py to scratch/proj, sed'd `blend =` to scratch/blends, HUMANFORM_LIBRARY -> copy of ~/.claude/humanform/library (18 MB, copy 2 s).
- attempts 1, wall ~3 min (mostly reading NEXT.md / runner / verify).
- no draft quality exists anywhere in character-pipeline or rig-anything (grep "draft" in ~/.claude/skills: 0 hits). Not needed: a crowd person body+bake+moves is ~12 s.
- change: none needed; NEXT.md "Things that cost time to learn" recipe worked first time.

## 23:36 probe design - friction
- stage: moves. `stages.run_moves` raises `moves: clips failing their checks` and the per-clip report (arm_pose, carry ranges) is lost with the exception. To see numbers of a failing clip I had to replicate run_moves' option assembly in a probe (runner.build to_stage=<stage before moves>, then actions.move_set directly).
- wall ~5 min. resolution: probe.py in scratch/crowd.
- change: character-pipeline stages.run_moves should attach `out` (with arm_pose carry ranges) to the raised error, or support a `dry`/report-only mode, so a failing build still says the numbers.

## 23:40 Ava first probe - win / fail
- Ava body 2.3 s, bake 0.1 s, moves 6.8 s; whole process 12 s.
- Idle pass, Walk pass (carry -17.6..44.2), Run FAIL: "the arm swings 53 degrees but never comes back to hanging - nearest 4 degrees in front (limit 2)" (carry 3.9..57.1, elbow 85, hand_rise 0.17..0.54).

## 23:42 run clips are never exempt - gap (plugin bug)
- rig-anything 0.23.0 upper.py:527 `verify.arm_pose(..., running=getattr(U, "running", False))` - nothing ever sets `U.running` (grep across installed rig_analysis and repo main: only `running = duty < 0.5` locals in upper.defaults and locomotion.cycle). So every Run is judged as a walk: arm_swing applies to it (its docstring says a run is exempt, "every shipped run comes no nearer hanging than 1.2 degrees"), and RUN_HAND_RISE / RUN_ELBOW_OPEN are never applied.
- consequence: every crowd Run whose arms stay in front fails; a spec fix would pull the run's arms back to hide a plugin bug. Fix belongs in rig-anything: locomotion.cycle (line ~803) should set `U.running = running` after constructing Upper (and actions.py:654 for other clips). Then re-probe; the spec patch below for Run clips may become unnecessary.

## 23:45 all 15 remaining probed - win (speed) / fail (7 runs)
- 15 people, xargs -P 4, 84 s wall total. Per person pre-moves (body+bake) 0.8-18.5 s (Rosa 18.5, Dante 15.7, Walter 15.5), moves 5-9.6 s. No stage > 60 s.
- Every Idle and every Walk passes all checks (walks come back 4.2 (Margaret) .. 17.6 (child) deg behind hanging). Frank, Hugo, Margaret, Nadia, Rosa, Walter have no Run.
- 7 of 10 Runs FAIL only `arm_swing`: Ava 3.9, Dante 2.4, Lily 2.9, Mei 3.4, Milo 5.0, Noah 3.6, Sam 2.1 deg nearest-to-hanging (limit 2.0). Runs that pass do so narrowly: Freya 0.6, Ines 0.9, Tomas 1.2. All runs: elbow 85, hand_rise <= 0.55 - would pass RUN_HAND_RISE 0.65 / RUN_ELBOW_OPEN 140 if the running flag were set (see 23:42 gap). So all 7 failures are the unset `U.running`, not bad clips.

## 23:50 arm_forward sweep - win
- Run `upper.arm_forward` -16..-20 (default at these Froude numbers is -15; style child/brisk/relaxed/adult do not set it). Carry minimum moves ~1.0 deg per deg of arm_forward, swing unchanged (+-1 deg). 7 people x 5 values in one process each, 128 s wall (-P 4).
- smallest passing: Ava -17 (1.8), Dante -16 (1.2), Lily -16 (1.9), Mei -17 (1.6), Milo -18 (1.9), Noah -17 (1.6), Sam -16 (1.1).
- chosen with >= 0.4 deg margin under the 2.0 limit (a 1.9 pass is one humanform tweak from failing): Ava -18 (0.8), Dante -16 (1.2), Lily -17 (0.9), Mei -17 (1.6), Milo -19 (1.0), Noah -17 (1.6), Sam -16 (1.1).
- change: the patch is a workaround; the real fix is rig-anything setting U.running (then no crowd spec needs changing, and Belle's Trot fix should be re-checked: is her Trot duty < 0.5?).

## 23:56 patch - friction (small)
- `git diff --no-index a/characters b/characters` from inside scratch/patchwork wrote `a/a/characters/...` paths; `git apply --check` in grungist-creek failed "No such file or directory". Fixed with sed; 1 extra attempt, ~1 min. Tip: run `git diff --no-index` from inside a/.. with `--src-prefix=a/ --dst-prefix=b/` on bare dir names, or sed the headers.
- crowd_specs.patch: 7 files, one `[moves.per_gait.Run] upper = { arm_forward = X }` table each (partial upper merges over the style's upper and upper.defaults - locomotion.style_args / upper.resolve), with a comment naming the numbers and the rig-anything bug. `git apply --check` clean in grungist-creek; NOT applied there (git status unchanged).

## 23:58 pipeline proof - win
- Patch applied to scratch/proj/characters only; `build_human.py who=<each of 16> to=moves` (character-pipeline runner, run_moves raises on any failing clip): all 16 exit 0, moves 4.6-9.2 s each, 16 people in 85 s wall at -P 4. Blends saved to scratch/crowd/blends only.
- open: export/garments/review stages and Godot verify_moves not run for the crowd (task scope was the moves stage). Belle not probed here (belle-top's scratch covers her).
- open (plugin): rig-anything `U.running` never set -> run clips judged as walks. Fix in rig-anything upper.py/locomotion.py, add a fixture Run whose arms stay in front (e.g. a child run at Froude 2.2) that must pass; after it lands this patch can be dropped (runs then pass at default -15: elbow 85 incl. 95 < 140, hand_rise <= 0.55 < 0.65).
