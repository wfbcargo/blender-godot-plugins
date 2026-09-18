# critic-checklists-controls - lab notebook

Branch `critic-checklists-controls` (plugins, from main bed0536; no game worktree - docs and tests only).
Step 0.5 items: critic checklists shipped with the plugins, and Step 0's missing controls (follow-through
0.6.1's limit_influences fix; three pipeline_hashes flips without drop-controls). Scratch:
`C:/Users/pauli/AppData/Local/Temp/rw/critic-checklists-controls/`.

Note on the trigger: the user request relayed with this run was "do you have any preview images or demos so
I can see how things are coming along?". This branch changes docs and tests only; it produces no new
preview. The existing previews are listed in NEXT.md "Where the figures are".

## 12:02 start | kind=setup
Worktree made first time. Read NEXT.md, CLAUDE.md, tests/README.md, pipeline_hashes.py, inputs.py,
runner.plan/stage_hash, plugins.stage_versions, quality.for_hash, flesh.limit_influences and its history
(bd22728 the stale-element write, 419925c the fix).

Findings:
- `plan(drop=)` only drops `inputs.py` labels. The three flips without controls go through other parts of
  the hash: the skin size through `quality.for_hash` (bake), the spec `[flesh]` edit through
  `ch.digest(*sections)` (flesh's sections in `stages.STAGES`), the wardrobe version through
  `plugins.stage_versions`. So the controls need a way to leave those out too. The seam is docs and tests
  only (cp-cascade-stop also edits the pipeline), so the fixture does it by patching those three functions
  for the duration of one plan - no plugin code changes.

## 12:04-12:08 pipeline_hashes drop-controls | kind=win (first time)
`_left_out(drop, run)` in the fixture: labels `version:<plugin>`, `quality:<part>`, `spec:<section>` are left
out by wrapping `plugins.stage_versions`, `quality.for_hash` and `stages.STAGES` for one plan (restored in a
`finally`); every other label goes to `runner.plan(drop=)` as before. Rows given `label` + `control_unseen`:
wardrobe version (`body` / `version:wardrobe`; the row's expected stage was `None` with an `expect_first`
override, now `body` directly), final skin size (`bake` / `quality:skin`), spec `[flesh]` edit
(`flesh` / `spec:flesh`), and also final close-up views (`review` / `quality:close`, the same kind, cheap).
Fixture 6.7 s, all four `control_unseen: true`. Harness controls, each `PIPELINE_HASHES_DROP=...` run must
fail - all four exit 1:
- `body:version:wardrobe` -> wardrobe version first=muscle (body unseen);
- `bake:quality:skin` -> final skin map size fails (its error printed `{}` because the failed name differed from
  the row key - fixed, the name is now the row key);
- `flesh:spec:flesh` -> moved [] ;
- `review:quality:close` -> moved [].
Golden: +8 lines (label and control_unseen on four rows), recorded with `--twice --update --only`.

## 12:05-12:09 limit_influences fixture | kind=win (first time)
New fixture `tests/fixtures/limit_influences.py` (2 s): 64 loose vertices, 8 bones, 1-8 influences each in
rotated add order, two non-bone groups interleaved in group index order, zero-weight bone entries, totals
0.6-1.0 (below Blender's 1.0 clamp so a kept weight scaled up cannot be clamped and hide a loss). Measures
max_total_lost (free, signed), gained, over_four, not_strongest, ratio_spread, other_groups_moved,
untouched_moved, changed vs expected. Fixed: all 0, 32 of 32 changed, ok. In-fixture control (bd22728's
loop verbatim): max_total_lost 0.311731 -> not ok, as it must. By-hand harness control: the fixture run
with FT_SCRIPTS at a copy of follow-through whose `limit_influences` is reverted to the stale write ->
exit 1, "does not keep the weights ... max_total_lost 0.311731". Note the stale write leaves ratio_spread 0
(it scales nothing at all), so only the total catches it. Golden recorded with `--twice`.
tests/README.md: rows for limit_influences, and the two that were missing (pipeline_hashes, skin_detail).
Not added to regress.py DURATIONS (a tools/ edit makes --quick run everything); an unknown fixture starts
first, and this one takes 2 s.

## 12:10-12:26 the five critic checklists | kind=win
Written from the code and the shipped outputs, not from memory: rig-anything `closeups.VIEWS`, lookdev
`CLOSE_VIEWS` (face, eyes, hand_palm/back.L/R, feet, bust, crotch, full, bone:<name> - no face_3q/head_side/
head_back in Godot yet), verify_flesh/verify_wardrobe/verify_moves/verify_strands headers and output keys,
humancheck `check()` ids, study_woman's `.moves.json` and `review.json`, `flesh.render_heat` file names,
`limits.suggest` keys, `wardrobe.dress` report keys.
- `plugins/lookdev/references/critic-look.md` LOOK-H1..5, E1..3, S1..8, F1..3, P1..3 (from the Step 0
  baseline ranks 1-7); sources G:<view>, B:<view>, hair.png, tone, capture, manifest `skin`.
- `plugins/animate-anything/references/critic-motion.md` MOT-N1..4, S1..9, G1..4. Reconciled with
  `motion-critic-checklist.md`: that file keeps the protocol and the full bank; this one is ids + the one
  source per question + the engine-only questions (verify_moves, verify_strands, figure_study selftest).
  A pointer added at the top of motion-critic-checklist.md. MOT-G5 (Run judged as a run) removed: it named
  nothing that exists (U.running never set) - moved to "not answerable".
- `plugins/wardrobe/references/critic-fit.md` FIT-V1..7, B1..5, M1..3.
- `plugins/follow-through/references/critic-flesh.md` FLESH-R1..4, G1..6, W1..2 (W1 is the new fixture).
- `plugins/humanform/references/critic-body.md` BODY-P1..8, F1..8, W1..3. First draft named `legs_parted`,
  `facing`, `left_side`, `landmarks` as ordinary ids: a real humancheck.json showed they appear only as a
  fail, and that `elbow_centering`/`knee_centering` exist - corrected (BODY-P6, new P8).
Each file ends with "Not answerable from these today" so a gap is named rather than answered from the wrong
picture. Linked from animate-anything, lookdev, wardrobe, follow-through flesh, humancheck and humanform
SKILL.md. Bumped lookdev 0.4.1, animate-anything 0.10.1, wardrobe 0.5.1, follow-through 0.6.2, humanform
0.10.1 (tools/bump.py).

Spot-checks, each run or opened (scratch Godot project = project.godot + addons + assets/figure_study copied
to `rw/critic-checklists-controls/game`, `--headless --import`, 4 s):
1. verify_moves dir=res://assets/figure_study -> 21 MOVES lines, `MOVES VERIFY PASSED` (MOT-G1).
2. verify_flesh study_man course=walk -> `FT_FLESH_LIMITS` with regions belly/butt.L/butt.R, checks
   finite/moved/on_limit/within_body/within_limit, regions_measured 3 = total, `FT_SUMMARY ... PASSED`
   (FLESH-G1..4 keys exist as named).
3. lookdev close-shot study_woman --views face,eyes,hand_palm.L,crotch,full --presets overcast -> tiles
   `overcast_<view>.png`, `close.json` (tiles[].failures, figure_coverage), sheet opened: the forehead
   specular band and hard black brows are visible under overcast (LOOK-S2, LOOK-E1 are answerable).
4. Blender close set of study_man (game's review/study_man/close/sheet.png) opened: all 15 tiles present
   with the names used in B:<view>.
5. humancheck_cli mpfb=female views=1 -> body.png (3 rows x 4 columns as named), closeups.png,
   humancheck.json (2 fail: upper_arm, foot), views.json.
6. verify_strands study_woman ponytail on StudyWoman_Run -> `FT_SUMMARY ... swing_spread=1.260 FAILED`
   (MOT-G3's known `no`, same 1.26 as NEXT).

## For the merge step: text for NEXT.md (not edited here)
Under "Running the next session", after "For each step, write the critic's questions into the step's
done-when": "Pick done-when and look questions from the shipped banks, by id: lookdev
`references/critic-look.md` (LOOK-*), animate-anything `references/critic-motion.md` (MOT-*), wardrobe
`references/critic-fit.md` (FIT-*), follow-through `references/critic-flesh.md` (FLESH-*), humanform
`references/critic-body.md` (BODY-*). Each question names the tile, view or verifier that answers it; a
question the banks lack is added to the bank in the same round." And under Step 0: "Controls still missing
from Step 0: done (critic-checklists-controls): `limit_influences` fixture with the stale-write control;
pipeline_hashes drop-controls for wardrobe version, final skin size, spec [flesh] and final close-up views."
