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

## ~09:03 belle, garments.json edit through a scratch wardrobe copy | kind=win, first time
`WD_SCRIPTS` at a copy of wardrobe with `sports_top/tailor/sleeve` -0.15 -> -0.149, no force: log says
`garments: what it reads changed: preset:sports_top`; body..moves unchanged; garments 3.1, export 5.0,
review 4.5; build 12.9 s, wall 15 s (the full belle build: 34-37 s).

## ~09:03-09:06 flesh_figure prepare_again | kind=fail x2, then win (3 attempts)
Added a check to flesh_figure: `flesh.prepare` twice on the fleshed Figure, and a control rerunning the
old way (jiggle groups deleted). 1st: my criterion `min_total >= 0.99` was wrong - the sample Figure's
weights are not normalised (min total 0.62 before anything). 2nd, measured as weight lost per vertex against
the first run: 0.1156 lost on vertex 3746 with no jiggle group on it at all. Cause, pre-existing in
follow-through `limit_influences`: it removed the weakest group from the vertex and then wrote the kept
weights through `VertexGroupElement`s read before the removal, which point at the wrong slot after
`v.groups` compacts - the kept weights were never scaled back up (up to 22 % of a vertex's weight lost on
the first run too; the second run lost more because the jiggle had been the dropped fifth influence).
Fixed with (group, weight) pairs and `vertex_groups[g].add(..., "REPLACE")`. 3rd: 0 weight lost, 0
unweighted, same regions; weights differ from the first run by up to 0.074 where a fifth influence was
dropped the first time (cannot be put back). Control: 25 unweighted, 0.9999 lost -> fails as it must.
This moves every fleshed golden (the first run now keeps each vertex's total).

## 09:06 study_man [flesh]-only edit, after the fixes | kind=win
Fresh final build 35.3 s (body 5.4, muscle 0.6, bake 8.8, hair 0.8, flesh 0.7, moves 7.6, export 6.2,
review 4.9). `limit_share belly 0.38 -> 0.4`, resumed: flesh 0.8, moves 7.9, export 4.1, review 5.3 =
build 18.4 s, wall 20.7 s. The resumed glb has the same node names as the fresh one (no neutral_bone).
The skin at 2048 costs bake about +7 s (8-9 s against 1.9 s at 1024 in 06's table), so a final build is
now ~33-35 s here, not 25.

## ~09:07 hair code change on the saved blend | kind=win
`HF_SCRIPTS` at a humanform copy with a line appended to hair.py: `hair: what it reads changed:
code:humanform.hair`, then "hair changed and the body already carries it: rebuilding from body", all
stages, 37.4 s.

## ~09:08 draft and final skin sizes | kind=win
study_woman final manifest `skin`: baked, map_px 2048, tone_ok. study_man_draft (scratch spec, quality
draft, own blend and export dir): map_px 1024, build 23.5 s (bake 3.4).

## 09:08-09:11 from=bake | kind=fail, then 2 fixes (3 attempts)
1st, study_woman's saved (haired) file, from=bake to=bake force=1: albedo near black - tone_error 0.787,
every region grey (lips 0.026...). The marks were kept (hf_skin_tint/region/oil present), but `look.skin`
gave every face - hair cards and eyes - the skin material and the bake read their UVs. `check_bake` now
refuses a bake on a haired body (the whole-build path restarts from body before it, above).
2nd, a file saved after bake (to=bake from body, then from=bake to=bake force=1): every marked region's
tone identical, but the unmarked "skin" sample moved 0.858 -> 0.772 and the eyes had lost their materials:
the eyes joined by the first bake were re-skinned and baked into the maps. `stages._separate_joined` takes
the non-skin faces off as the eyes object again before `look.skin` (first try with `bpy.ops.mesh.separate`
failed: "Selection not supported in object mode" - the view layer's active object was not the body; done
with a copy and two bmesh deletes instead). 3rd: every region, "skin" included, unchanged to 3 decimals
(max change 0.0), tone_ok, eye materials back (HF_iris, HF_pupil, HF_sclera), 1024 faces separated.
(Heading times marked ~ were reconstructed from the order of runs after the fact; the rest were read from date.)

## 09:12 flesh code into the flesh hash | kind=design
`runner.plan` on study_woman's saved file matched every stored hash - after 0.6.1 changed how `flesh.py`
weights the jiggle bones. Exactly the staleness rank 3 is about, so `code:follow_through.flesh` joined the
flesh stage's reads (and a flip in pipeline_hashes: moves flesh first, control unseen). The plugin's
`scripts/run.sh` template on study_woman's saved file then logged `flesh: what it reads changed:
code:follow_through.flesh` and ran flesh, moves, strand, export, review: 21.2 s.

## 09:11-09:26 regress --update --twice --jobs 2 | kind=win (14.6 min)
All 21 fixtures built twice and agreed. `--update` rewrote all 21 goldens; 13 differed only in paths,
seconds and version stamps (by `regress.compare`) and were put back with `git checkout`. Kept:
- pipeline_woman: manifest fields gain `skin`; `skin.size` 1024 -> 2048 (the final bake size, intended).
- pipeline_ponytail: manifest fields gain `skin`.
- flesh_figure: the new `prepare_again` block (0 weight lost, control 25 unweighted).
- dressed_figure, dressed_presets, dressed_skirts, traced_detail: garment cover/ease/detail counts move
  by a few percent (e.g. sports_top hidden 2738 -> 2797, breast skin_verts 727 -> 739, skirt pelvis shares
  0.0180 -> 0.0179, Dress face_order hash): the garments are cut from the fleshed skin and take its
  weights, which now keep each vertex's total where limit_influences dropped a fifth influence (0.6.1).
- pipeline_hashes: new (re-recorded with --twice after flesh.py joined the flesh reads).

## 09:28 study_man [flesh]-only edit on the final code (regress running beside it) | kind=win
Whole build from the saved file (the previous one had the scratch humanform's hair): 31.6 s build, 34 s wall.
`limit_share belly 0.4 -> 0.39`: body, muscle, bake, hair unchanged; flesh 0.7, moves 8.0, export 4.3,
review 4.9 = 18.1 s build, 20 s wall; no neutral_bone. 06 estimated 12 s against 25 s; here 18 s against
32 s (0.57 of a whole build). What is left is moves + export + review (17 s), which follow flesh by
design: 06's other rows (cache clips across a flesh edit, skip export's re-check of unchanged clips,
review only changed clips) are what would cut it further.

## Open
- A resumed flesh rerun weights the body within 0.074 of a fresh build (flesh_figure), 0.020 on study_man:
  where the first run's `limit_influences` dropped a fifth influence that share cannot be restored. Exact
  would need the pre-jiggle weights kept somewhere the exporter ignores.
- Moves, strand, export, review and body name no files of their own: rig-anything's gait styles live in
  its code and are covered only by its version. A code edit there without a bump is still "unchanged".
- An explicit `from=bake` on a haired body now refuses (it cannot be done without taking the hair off);
  a whole build restarts from body instead.
- The skin at 2048 px adds about 7 s to a final bake (8-9 s against 1.9 s at 1024).
