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

## 12:06-12:10 pipeline_hashes drop-controls | kind=win (first time)
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

## 12:10-12:16 limit_influences fixture | kind=win (first time)
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
