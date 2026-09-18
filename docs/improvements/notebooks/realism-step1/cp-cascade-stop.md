# cp-cascade-stop - lab notebook

Branch `cp-cascade-stop` (plugins, from main 9007067; no game branch). NEXT.md Step 0.5 "rebuilds that skip what
did not change downstream". Scratch: `C:/Users/pauli/AppData/Local/Temp/rw/ccs/` (scratch project `proj/` with
the game's characters, blends in `blends/`; `proj2/` + `blends2/` for the fresh builds compared against;
`env.sh` points every `*_SCRIPTS` at this worktree and `HUMANFORM_LIBRARY` at a copy). Times read from `date`.

## 13:01 start | kind=setup
Read NEXT.md, CLAUDE.md, runner.py, inputs.py, stages.py, the cp-resume-hashes notebook, follow-through
flesh.prepare / add_jiggle_bones / remove_jiggle_weights / limit_influences, rig-anything's use of
`follow_through` and rotation modes. No earlier attempt's branch or notes existed (the critic folder
`rw/critic-cp-cascade-stop-3` is empty). tools/scratch_project.py is not on main yet (its branch is in
flight), so the scratch project was made by hand as NEXT.md says (about 1 min).

Baseline, main's code, study_man final fresh: 39.8 s build (flesh 1.1, moves 9.8, export 4.1, review 8.0).

## 13:05 design | kind=design
- Keep every input hash as it is (no stored record goes stale, `plan()` unchanged). Add a *view* hash: the
  stage's hash with, for a need whose output it reads (`inputs.READS_OUTPUT = {"moves": ("flesh",)}`), the
  digest of that need's output in place of the need's input hash. The flesh stage digests, right after it
  runs, what moves reads of the file (`inputs.outputs`: rig object, bones, pose setup, which meshes are bound,
  and per bound mesh geometry, groups, weights, modifiers, skin/cloth marks, shape keys, materials); the
  jiggle block of the `follow_through` spec (swing limits etc.) is the only thing flesh writes that is left
  out. Moves is skipped when its input hash moved but its view did not and its clips are still stored; its
  record then takes the new input hash, so export and review (which read flesh) still rerun.
- `_forget` after flesh keeps moves' record (only a stage that reads the rerun stage through its output).
- Conservative: a record without a view or an output (anything built before 0.10.0) reruns as before.
- The 0.020 weight drift of a flesh rerun (cp-resume-hashes open item) would make the weights digest move on
  the first edit after every fresh build, so the flesh stage now keeps the unfleshed mesh (a fake-user copy
  of its data, linked to no object) and a rerun swaps it back in before `prepare` (`stages._preflesh`),
  checked by vertex count, geometry digest and vertex-group prefix; otherwise the old give-back path.
Bumped character-pipeline 0.10.0 first (lesson from cp-resume-hashes: bump before the first real build).

## 13:08 first [flesh] edit (limit_share belly 0.4 -> 0.38) | kind=fail, found a real difference
flesh reran, geometry and weights came out the same (the preflesh restore works), but `rig:pose` moved and
moves reran (20.3 s). Probe of the saved file: every pose bone QUATERNION after moves. rig-anything's
`verify.adopt_rotation_modes` puts every bone moves keys into its keys' mode, so after the first moves run
the body's bones are no longer in MPFB's Euler; flesh never sets the mode of a bone it did not add. So the
digest keeps the rotation mode only of bones follow-through added (`ft_role`); constraints, locks and pose
props of every bone stay in. (Skipping is the closer-to-fresh choice here: a moves rerun would see
quaternion modes a fresh build's moves never saw.)

## 13:11 [flesh] edit again, after a fresh build on the fixed digest | kind=win
Fresh final build 56.8 s (machine loaded: review 19.4). Edit limit_share belly 0.4 -> 0.38, resumed:
body..hair unchanged, flesh 0.9 ("what later stages read of it came out the same"), moves "unchanged (its
input hash moved, but what it reads of flesh came out the same)", export 3.9, review 6.8 = **12.1 s build,
16 s wall** (date 13:11:42 -> 13:11:58), against 18.1 s before (cp-resume-hashes) and 23 s on main in this load.

Fresh build of the edited spec (`proj2`, 37.3 s) compared with the resumed one (`compare.py`): manifest 0
changes by `regress.compare` (control: v1 fresh vs resumed shows exactly `flesh.regions[2].max_offset_m
0.0672 -> 0.0638`); glb JSON chunk with extras set aside identical; **BIN chunk byte-identical** (so the
weights are now exactly a fresh build's - the 0.020 drift is gone for a file built on 0.10.0).
The glb extras differ: `materials[0].extras.humanform_skin` is present in a glb exported from a reopened
.blend and absent from one exported in the session that built it. Not this branch: `from=export to=export
force=1` on the fresh proj2 file (no flesh, no moves) shows the same 44 extras keys appearing.

## 13:14 a [flesh] edit that moves really reads (types ["butt","belly"] -> ["belly"]) | kind=win (control)
Resumed: "flesh: what later stages read of it changed: mesh:groups, mesh:weights, rig:bones, rig:pose",
"moves: what it reads of flesh changed", moves 8.4 s ran, export, review; 25.7 s. The cascade still flows
when the rig or the weights move.

## 13:14-13:17 pipeline_hashes output flips | kind=win (first run; one bash heredoc failed on quoting, so the
patch went through a file)
`_output_scene` builds a small rig (hips, spine, a tagged ft_jiggle bone) and a skinned cube under the spec's
names; `_output_flips` flips one thing at a time and judges `inputs.outputs(ch, "flesh")` and
`runner.view_hash` for moves: 15 flips (bone tail, parent, ft_role tag, pose constraint, a jiggle bone's
rotation mode, the rig's place, a second bound mesh, a vertex, a weight, an empty group, a modifier, the
follow-through route, a wardrobe mark, a material, a shape key), each moving exactly its labels and moves'
view, each with a control (its labels dropped from the digest -> unseen); 4 unrelated edits that must move
nothing (a jiggle swing limit, a body bone's rotation mode, a pose, an action on the rig); and "no output
recorded" gives no view. All ok first run.
Harness controls by hand, `PIPELINE_HASHES_DROP=flesh:output:<label>`: rig:bones (3 flips missed),
mesh:weights (2), rig:pose (3) each exit 1 with an AssertionError naming the flips.

## 13:18-13:21 Belle: a [flesh] edit on a dressed spec without restarting from body | kind=win, first attempt
`stages.undress`: remove every garment bound to the rig (object, its mesh, materials only it used), the hem
bones wardrobe hung (`wd_role`) and the cover groups on the body (`wd_hide_*`, `wd_edge_*`); if anything of
wardrobe's is left, restart from body as before. The runner calls it for flesh in a whole build
(`UNDRESS_FOR_FLESH`); `[moves]` on a dressed spec still restarts from body (not attempted: moves' view would need
garments' effect on arm hang reasoned about, and the task asked for flesh).
Fresh Belle 46.9 s. Edit `limit_share = { butt = 0.8 }`, resumed: "took off Shorts, SportsTop (0 hem bones, 4
cover groups on the body)", flesh 0.7 "what later stages read of it came out the same" - so the undressed and
restored body is, for everything moves reads, the pre-garment body of the fresh build - moves unchanged,
garments 4.8, export 6.6, review 11.8 = **24.3 s build** (13:19:36 -> 13:20:04 wall 28 s) against a 46-47 s
restart. Fresh build of the edited spec (proj2, 46.0 s) against the resumed one: manifest 0 changes (control v1
vs resumed: the two butt regions' max_offset_m 0.0733 -> 0.0651, 0.0732 -> 0.065); belle.glb JSON without extras
identical and BIN byte-identical; belle_sportstop.glb and belle_shorts.glb identical including extras and BIN.
(belle.glb's extras show the same reopened-blend `humanform_skin` material extras as study_man.)

## 13:22 pipeline_woman dressed_flesh_edit rewritten | kind=build
Was: a dressed flesh edit restarts from body; control without flesh in RESTARTS_FROM_BODY refuses. Now, in
order on the dressed file: (1) no undress and no restart -> refuses (old control, kept); (2) no undress -> the
build restarts from body (stopped by a log hook at the restart line, before anything is rebuilt, so the file
stays dressed); (3) the real build, to_stage=moves, save=False: statuses, `undressed`, `unfleshed`, moves' why.
Docs: SKILL.md (resume paragraph, a "cascade stops" paragraph), build.py, run.sh, runner docstring, the
RESTARTS_FROM_BODY comment, tests/README rows.

## 13:21-13:25 goldens | kind=win
`regress.py --only pipeline_woman pipeline_hashes --jobs 2` (13:21-13:23): both CHANGED, only in the new blocks
(pipeline_hashes `outputs`; pipeline_woman `dressed_flesh_edit`: body and bake unchanged instead of ran, flesh
ran, moves unchanged "what it reads of flesh came out the same", unfleshed "restored", 2 garments and 4 cover
groups taken off, nothing left, control_restart = the old restart line, control = the old refusal). Recorded
with `--only ... --twice --update` (13:23:19-13:25:21): both agree twice; `git diff tests/golden` read: those
blocks and version stamps only.
