# cp-resume-hashes - lab notebook

Branch `cp-resume-hashes` (plugins, from main 5a218d3; game, from master 3e36eb2). 06 rank 3 (rebuilds that
match what changed) and rank 12 (bake at final size). Scratch: `C:/Users/pauli/AppData/Local/Temp/rw/cp-resume-hashes/`.

## 08:44 start | kind=setup
Worktrees made first time. Read NEXT.md, CLAUDE.md, 06 sections 3G/4/5/6, runner.py, stages.py, quality.py,
plugins.py, the game's build_human.py / build_belle.py and the pipeline fixtures.

Findings before writing code:
- There is no `run.sh` template in character-pipeline: every agent wrote its own scratch `run.sh`
  (notebooks gap-realistic-skin, -fix, genital-anatomy). So "the run.sh template" has to be created.
- Stage hashes today: spec sections + needs' hashes + plugin versions (+ quality when not final). Nothing
  names a data file or code file, so a garments.json edit or a hair.py edit without a version bump is
  "unchanged".
- humanform `skin.bake` already keeps the region marks after baking (gap-realistic-skin-fix); needs a
  from=bake check on a real figure, not a fix.

## 08:48-08:51 code | kind=build
- `character_pipeline/inputs.py` (new): per-stage `{label: digest}` of the data and code a stage reads
  (bake: humanform skin.py/look.py, lookdev bake.py; hair: resolved hair preset, hair.py, brows.py,
  face_regions.json when a face switch is on, lookdev hair.py + its hair material preset; flesh: the merged
  follow-through registry; garments: each worn preset's resolved contents). Data hashed as canonical JSON,
  code with CRLF normalised. Goes into `_hash` as `reads` and into each stage record as `inputs`, and a
  rerun logs which labels moved.
- `runner.stage_hash`, `runner.plan(spec, quality, drop)` (hashes without building, for the test),
  `runner.open_saved`, `runner.build(resume=True)`.
- quality.py: a `skin` part (final 2048, preview/draft 1024), hashed at every quality (`HASHED_ALWAYS`) so
  an old final file baked at 1024 rebakes. `run_bake` passes it to `look.skin(size=)`; `skin_manifest`
  reads the skin material's `humanform_skin` into the bake report and the manifest's `skin` block.
- New `scripts/build.py` and `scripts/run.sh` (the template); the game's build_human.py / build_belle.py
  call `runner.build(resume=not fresh)` and take `fresh=1`.

## 08:51 first real build, study_man final, fresh | kind=win
rc 0 first time, 64.3 s (the machine is shared with other agents: body 14.2, bake 16.1 at 2048 px, moves
11.5). Manifest `skin`: stage baked, map_px 2048, tone_ok, per-region tones (lips 0.592/0.356/0.269 against
skin 0.62/0.441/0.332). Unchanged rerun: opened the saved blend, every stage "unchanged", 0.3 s.

## 08:53 [flesh]-only edit (limit_share belly 0.4 -> 0.38) | kind=win, then a found bug
flesh, moves, export, review ran; body..hair unchanged. Build 30.0 s, wall 32.7 s, against 64.3 s for the
fresh build in the same load (a second fresh build a minute later: 42.1 s build, 45 s wall).

But the resumed glb had one node more than a fresh one: `neutral_bone`, in the body's skin. Probe: a second
`flesh.prepare` on a fleshed body left 5 vertices with no deform weight. follow-through's `add_jiggle_bones`
takes the jiggle weight out of a vertex's other weights and, on a rerun, only deleted the jiggle groups: the
share taken was lost. It never showed because no caller ever resumed a fleshed file (every [flesh] edit
rebuilt from body). Fix in follow-through (outside this branch's listed plugins, but rank 3 is wrong
without it): `flesh.remove_jiggle_weights` gives the weight back in proportion (exact) or to the jiggle
bone's parent where nothing else was left, called at the start of `prepare` and `add_jiggle_bones`.
After: 0 unweighted, jiggle spec identical to the fresh build's, but 317 of 17373 vertices differ by up to
0.020 in weight: `limit_influences` dropped a fifth influence on the first run, and that weight cannot be
put back. A rerun after that is stable. Open: exact restoration would need the pre-jiggle weights stored
somewhere the exporter does not carry.

## 08:58-09:00 tests/fixtures/pipeline_hashes.py | kind=win (second attempt)
No build: copies the six plugins into the fixture's folder (no docs, Godot files, humanform seed/sources),
repoints the pipeline at them (purging sys.modules and sys.path of the originals, else `importlib.reload`
re-reads the originals), and flips one file at a time with `runner.plan`. 18 flips + 5 unrelated edits +
the final skin size + a spec [flesh] edit, 7 s. First attempt failed on my own helper (`_bump_number` on
plugin.json, whose version is a string: `AssertionError: no number under []`); the version flip now
appends to the version string. Second attempt: every flip moved exactly its stage first, every unrelated
edit moved nothing, every control (input dropped from the stage's hash) left the flip unseen.
Harness control by hand, `PIPELINE_HASHES_DROP=<stage>:<label>`: garments:preset:sports_top,
hair:code:humanform.hair, flesh:data:follow_through.registry, bake:code:humanform.skin each make the
fixture exit 1 naming the flip it missed.

## 09:00 bake on a haired body | kind=design
A whole build whose bake hash moved (every final file after this branch: the skin size is new in the hash)
ran bake on the haired body - `look.skin` gives every face the skin material, hair and eyes too - and only
then restarted from body at hair. `RESTARTS_FROM_BODY["bake"] = CARRIED["hair"]`: it restarts before the
wasted bake. An explicit `from=bake` (not restartable) still reskins the hair faces: open, below.

## 09:01 versions | kind=friction
Bumped character-pipeline 0.8.0 and follow-through 0.6.1 after the first builds, which moves every stage
hash (versions are in all of them): belle, study_man and study_woman rebuilt from scratch again (~2.5 min
of machine time). Bump before the first real build next time.
