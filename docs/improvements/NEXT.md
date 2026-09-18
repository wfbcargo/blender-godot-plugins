# Next: the remaining work

A handoff for a fresh conversation. Start with:

> Read `docs/improvements/NEXT.md`, then the work item it points at, and plan it.

State as of 2026-09-17, second round. Both repos are pushed up to `899da4d` here and `2d1118d` in
`grungist-creek`; everything after that is local. The first round merged six branches (review-strips,
flesh-limit-suggest, compression-garments, hair-layer, strand-chains, muscle-definition) and synced
the follow-through addon into `grungist-creek` (`d23bd17`). The second round merged two more:

- **motion-critic** (04 c): animate-anything's motion critic reads the review strips, rig-anything's
  `verify.arm_swing` fails an arm carried out in front of hanging, and export writes each idle and gait
  clip's `arm_pose` into `.moves.json` so the critic's keep-or-revert rule runs from two manifests alone.
- **hair-strands-integration** (05 5.2): a `[hair] preset = "ponytail"` spec keeps the tail loose, a
  `strand` stage hangs follow-through's chain on it, export writes `<id>_hair.glb` and lists `strands`
  in the manifest; `verify_strands.gd` reads the head's surface between radius-map cells. The new
  `verify_strands.gd` is synced into `grungist-creek` (`f7a039b`).

Versions bumped, goldens re-recorded (version stamps, and `pipeline_ponytail` gaining the
`arm_pose_on_disk` the other branch added), plugins installed, and
`python tools/regress.py --twice --jobs 2 --godot C:/Users/pauli/Code/GoDot/grungist-creek` run on
`main` afterwards (result below). None of the second round is pushed.

It passes: 17 fixtures, each built twice and agreeing, no change against the goldens; 11 manifests
through `verify_moves` (the starfish's has no gaits and is skipped); `verify_wardrobe` on
`dressed_figure` (holes 0.000%, poke 0.016%), `dressed_presets` (0.062% / 0.008%), `pipeline_woman`
(0.000% / 0.145%) and `traced_detail` (0.000% / 0.000%), with the `cut=0.04` control failing at 1.129%
as it must. The project's addons matched the repo's (no drift warning).

**One branch is parked, not merged: `skirts-dresses` (05 5.4).** Its fix round is unfinished (the WIP
commit `bfc55f7`, "hem collision ring, dressed_skirts fixture", and follow-ups; another agent was still
working in `.worktrees/skirts-dresses` and merging `main` into it during this round). It had no
finished code review and no critic pass, so merging it would have put half a fix on `main`. Its
worktree and branch are deliberately left in place: finish it there and merge it on its own.

Installed copies in `~/.claude/skills` match the repo:
- rig-anything 0.23.0
- animate-anything 0.10.0
- follow-through 0.5.1
- humanform 0.7.1
- character-pipeline 0.4.0
- wardrobe 0.3.0
- lookdev 0.2.0
- godot-lsp 0.1.0

Read the repo's `CLAUDE.md` first: worktrees, scratch folders, the regression harness, install and version rules,
and the gotchas are there.

---

## Where things stand

| Item | Status |
|---|---|
| [03 Regression harness and install](03-regression-harness-and-install.md) | **Done.** |
| [02 Bone roles and rig profiles](02-bone-roles-and-rig-profiles.md) | **Done.** Belle's hand-marked flesh zones retired with 05 · 5.9. |
| [01 Character spec and pipeline](01-character-spec-and-staged-pipeline.md) | **Done.** Belle and the 16 people build from `grungist-creek/characters/*.toml`. Its loose ends are settled (character-pipeline 0.2.0) and the committed characters are rebuilt on them (grungist-creek `ed654b0`). |
| [04 Checks that match the eye](04-checks-that-match-the-eye.md) | **a done** (wardrobe 0.2.1), **b done** (rig-anything 0.22.0, character-pipeline 0.3.0: every export writes a review sheet), **c done** (animate-anything 0.10.0: a motion critic reading the strips; rig-anything 0.23.0: `arm_pose` in `.moves.json`), **d part done** for flesh limits, garment relief and arm carry (follow-through 0.5.0, wardrobe 0.3.0, rig-anything 0.23.0 `verify.arm_swing`). |
| [05 Feature gaps](05-feature-gaps.md) | 5.1, 5.6, 5.7, 5.8, 5.9 done. **5.2 hair done** (humanform 0.7.0, lookdev 0.2.0, character-pipeline 0.3.0; strand motion follow-through 0.5.0; a spec's ponytail swings through the pipeline since character-pipeline 0.4.0). `long_loose` is still rigid. **5.3 compression garments done** (wardrobe 0.3.0). **5.5 muscle done** (humanform 0.7.0, lookdev 0.2.0). Open: **5.4 skirts and dresses**, parked mid-fix on the `skirts-dresses` branch. |
| Old project notes | Not triaged (item 7 below). |

What exists now, and is worth knowing before starting anything:

- **`python tools/regress.py --jobs 2`** rebuilds 17 fixtures headless and compares them to `tests/golden/`:
  `mpfb_woman_curvy`, `rigify_human`, `mixamo_names`, `quadruped`, `rabbit`, `cricket`, `starfish`,
  `flesh_figure`, `dressed_figure`, `dressed_presets`, `pipeline_woman`, and this round's
  `review_sheet`, `traced_detail`, `hair_presets`, `strand_ponytail`, `muscle_definition`, and the
  second round's `pipeline_ponytail`.
  - `--twice` fails a build that doesn't reproduce.
  - `--godot C:/Users/pauli/Code/GoDot/grungist-creek` plays the exports in the engine's verifiers -
    now four wardrobe fixtures, not two.
  - `--plugins <checkout>` routes all six plugin variables, lookdev included (its Blender package is
    `plugins/lookdev/blender`, not `scripts`).
  - A full `--twice --godot` run takes about 40 minutes. See `tests/README.md`.
- **Bone roles:** `bodymap.build(rig)["roles"]` gives root, pelvis, chest, neck, head, tail, anchors, hands and feet, and
  controls. Rig profiles live in `rig_analysis/profiles/`. rig-anything SKILL.md, "Bone roles".
- **Characters:** `character_pipeline.runner.build(spec)` runs the stages body, bake, hair, flesh, moves, strand
  (only when the hair preset has a chain), garments, export, review. They refuse out of order, record their inputs in the .blend, and resume in a fresh session. Its SKILL.md
  has Belle as the worked example.
  - `assets/humans/build_human.py who=<name>` and `assets/belle/build_belle.py` are thin callers.
- **Presets and exporter:** wardrobe garment presets with `wardrobe.dress`; follow-through `limit_share` per flesh type;
  `export.export_character` writes the `.moves.json` for bipeds and quadrupeds.

---

## What to do next, in order

### 1. 04a - done (wardrobe 0.2.1)

The hole check now counts only skin a viewer can see into; Belle passes all 7 clips in the shorts, the top and both at
the unchanged 0.5%, and a cut patch still fails. What was found and what shipped is under 04 section **a**. When
checking a garment, pass `clip=` for every clip: the default is the first in the list, and the sports top's earlier
"passes" was only its crouch.

### 2. Small open findings (05 · 5.8) - done (rig-anything 0.21.0)

- **Done (rig-anything 0.19.0): the cricket exports.** The landing's slide was real and came from shared
  code, as did a toe drag in the walk that it hid; every clip is now checked for a foot moving along the floor.
  05 · 5.8 has the details.
- **Done (rig-anything 0.20.0): the slides pass and export on a Rigify biped.** Three shared causes (a hand-written
  slide path, feet not laid on the floor, feet blended along the floor between spots); 05 · 5.8 has the details.
- **Done (rig-anything 0.21.0): one bone count per radial appendage kind.** `radial.build` gives every appendage of a
  role the median of its kind's length / (1.2 width) ratios; the starfish's five arms all have 4 bones (21 bones), and
  the scratch anemone went from mixed 4/5 to 5 on all ten tentacles. Every outlier appendage now gets the kind's count
  whatever its own length; a warning for a far outlier is not written yet.
- **Done (rig-anything 0.21.0): `radial.skin` measures coverage** by reading the written weights back
  (`coverage`, `vertices_unweighted`). `plugins/animate-anything/references/radial-bodies.md` (lines ~16 and ~96) still
  describes the old per-appendage count and unmeasured coverage; update it with animate-anything's next change.

### 3. 05 · 5.9 - done (follow-through 0.3.0, end rings 0.4.0), Belle's hand marks retired

Buttocks are read from the side across the spine and thigh chains; both sample bodies score their butts, and
Belle's `[[flesh.zones]]` are gone from `grungist-creek/characters/belle.toml`. Rebuilt with every stage forced, her
self-test passes (breasts 7.5/8.7%, buttocks 8.6/8.4% on the limit, under 10%) and the wardrobe verifier passes all 7
clips in both garments. That meets 02's last "done when". Since follow-through 0.4.0 a chain's first ring (and its last built ring when the
chain is searched to its end) fits its envelope from wall vertices only, so the Figure's crotch no longer skews its
breasts and belly and its false love handles are gone; `render_heat` and the marks sheet draw a profile-read butt from
its profile. Belle is rebuilt on 0.4.0 (see 4): breasts 267 -> 271 vertices, limit
0.0781 m, buttocks unchanged. Still open: the Bloater's moobs score as misses (0.19 m), and
Belle's two-segment root-spine chain counts as searched to its end, so its top ring at 0.961 m (a hand-off to the next
chain, not a cap) is wall-filtered; her regions do not move.

### 4. Loose ends from 01 - conventions settled (character-pipeline 0.2.0), character rebuild in progress

- **Done: one standing height.** `height_m.stand` is always the Idle clip's `standing_height_m`; export fails if no
  Idle report is stored. `export.height` is gone from the spec and a spec naming it is a `SpecError`; Belle's
  `height = "idle"` line is removed on grungist-creek `master`. `collider.height` (rig-anything, mesh top) still differs
  from `stand` by under a millimetre on pipeline_woman; a hair bun would widen that. rig-anything's SKILL.md (~305) and
  `export_character` docstring still say `stand` is the mesh top.
- **Done: `upper_body` dropped** from the manifest. rig-anything's SKILL.md (~309) still shows it as an example extra.
- **Done: body stature reported** (`stages._stature`): fit residual row, aged, child, or measured on a reused library
  body. Only the fitted-adult path is covered by a fixture.
- **Done: the characters are rebuilt** (grungist-creek `ed654b0`). Belle and the 16 people ran every stage
  (`force=1`) through `build_belle.py` / `build_human.py` with these versions installed.
  - `upper_body` is gone from all 17 manifests.
  - The crowd's `height_m.stand` moved from the mesh top to the Idle standing height, by -12.6 mm (lily) to +7.8 mm
    (walter): the Idle height is the highest rest bone point, so it is where the head bone's tip sits against the
    scalp. `collider.height` is still the mesh top, so on the crowd the two now differ by up to 12.6 mm, not the
    under a millimetre measured on pipeline_woman. Belle's stand (1.6998) did not change.
  - The crowd's walks and runs changed only in `foot.L`/`foot.R` (quaternion delta up to 0.054) and their walk duty
    factors (0.781 -> 0.75 and similar): the crowd had last been built before rig-anything 0.19's planted-foot fix.
    The glTF JSON is otherwise identical with extras set aside.
  - The crowd specs have no `[flesh]`, so there was no butt measure to redo; only Belle carries flesh. Her breasts
    moved with the end rings (above); her buttocks did not.
  - Checks: both self-tests pass (Belle's flesh 7.6/9.0% and 8.6/8.4% on the limit). `verify_wardrobe` passes all 7
    clips in the shorts, the top and both, 21 runs; the worst holes are 0.39% (shorts walk) and the worst poke 0.24%.
    The `cut=0.04` control fails at 6.5%.
  - **Fixed (wardrobe 0.2.2): `verify_wardrobe.gd` passed runs that measured nothing.** `clip=Walk` on Belle (her
    clips are `Belle_Walk` and so on) raised a script error, sampled nothing and printed `"passed": true`. So did
    every `still=true` run: with no clip playing the skeleton never updates, so the rest-pose check SKILL.md asks
    for had never sampled a frame. An unknown clip (the problem lists the body's clips), a missing body or garment,
    setup cut short, or `samples: 0` now fail; still mode samples from the frame loop (Belle's shorts at rest: 5
    samples, 0 holes, 0 poke).
- **Nora (`assets/wardrobe/build_person.py`) is still a script.** She has a sculpted body on mocap, and nothing in a
  spec covers that. Convert her only if a spec grows a source for it.
- **Done: the real `.blend` files are rebuilt.** The rebuild saved `C:/Users/pauli/Code/Blender/human_*.blend` and
  `belle_realistic.blend` through the pipeline's scene guard; copies from before it are in that conversation's scratch
  (`wf/rebuild/blend-backup`).

### 5. 04 b-d - review strips (done), a motion critic (done), numeric guards (part done)

- **b done (rig-anything 0.22.0, character-pipeline 0.3.0).** Every export writes a review sheet beside
  the glb: eight frames of each clip in a strip, three views, one contact montage, all at one scale with
  one floor line. The frame is grown from the evaluated poses along both screen axes, so a rabbit's
  JumpAir legs going through the floor stay in the picture (`bands_px` [label, above, below]), and
  `edge_cells` counts a body touching any edge. The pipeline's `review` stage raises on a cell with no
  body in it or a body against an edge. Fixture `review_sheet`, whose `Dip` clip spills 0.35 m below the
  floor and 0.9 m above it, is the regression.
- **c done (animate-anything 0.10.0, rig-anything 0.23.0).**
  `plugins/animate-anything/references/motion-critic-checklist.md` turns each clip's strips into yes/no
  questions per view and compares a new version against the previous one. The keep-or-revert rule reads
  only the two `.moves.json` files: export now writes `arm_pose` (per arm `hand_rise`, `elbow_flex_deg`,
  `upper_arm_deg`, `arm_carry_deg`, `arm_swing_deg`) beside `clip_checks` for idle and gait clips. Arm
  alternation has no number behind it and is a front-view question. The loop produced one guard,
  `verify.arm_swing`: a walk or run whose arm stays in front of hanging fails (the pre-fix Walter walk).
  The manifests already shipped in `grungist-creek` have no `arm_pose` until those characters are
  rebuilt on 0.23.0; until then the critic compares `clip_checks` only.
- **d part done.** The numeric guards distilled so far are follow-through's flesh limit caps and
  `within_body` check (0.5.0), wardrobe's millimetres-of-relief `detail_limit` (0.3.0) and rig-anything's
  `arm_swing` (0.23.0). More should come out of running the critic on real characters.

### 6. 05 · 5.2-5.5 - the look of a character: three done, skirts parked

- **5.2 hair - done** (humanform 0.7.0, lookdev 0.2.0, character-pipeline 0.3.0, and the strand motion in
  follow-through 0.5.0). A spec says `[hair] preset = "bun"`; the cap is cut from the body's own faces
  with its boundary inside the texture's transparent root zone, so the hairline reads as strand tips, and
  lookdev's hair material plus `LookdevMaterials.apply` carry the anisotropy into Godot. Hair joins into
  the body and nothing takes it off, so changing `[hair]` rebuilds from the `body` stage - the stage says
  so rather than joining a second layer on. Since character-pipeline 0.4.0 a ponytail spec keeps its tail loose;
  a `strand` stage between moves and garments hangs follow-through's chain on it, and export writes
  `<id>_hair.glb` and the manifest's `strands`. Checked on Nadia rebuilt in scratch: `verify_strands.gd`
  passes at 30-240 fps (head penetration 0.2-1.2 mm, swing 32.6-35.2 deg; collisions off fails at
  11.9 cm). `long_loose` is not chained - one chain twists its 16 cm curtain into a wedge 2.9 cm into
  the head - so it still joins into the body rigidly.
- **5.3 compression garments - done** (wardrobe 0.3.0). `fit.relief` measures a surface's height over
  itself smoothed across 3 cm and `detail_limit` holds millimetres of the skin's relief the cloth carries
  through; a limited region that could not be measured fails instead of passing quietly.
- **5.5 muscle definition - done** (humanform 0.7.0, lookdev 0.2.0). Definition is a sculpted delta part
  weighted by the brief's muscle and estimated body fat, applied as geometry or baked into a normal map.
  Dante reads muscular with the forced macro dropped, and a soft body at the same brief muscle gains bulk
  without abdominals.
- **5.4 skirts and dresses - open, and parked mid-fix.** The `skirts-dresses` branch (WIP commit
  `bfc55f7` and follow-ups, worktree `.worktrees/skirts-dresses`) has a hem collision ring and a
  `dressed_skirts` fixture in progress. It was not merged in either round because its fix was
  unfinished and it had no completed review or critic pass; the worktree and branch are left as they
  were. Finish it there.

Still to do on the characters themselves: Belle's top and hair (Belle and the crowd still use
`kind = "shell_bun"`), and Dante's `muscle = 1.0`, are still built the old way in `grungist-creek`,
and no shipped manifest carries `arm_pose` yet. Rebuilding them on these versions is the next real use of all
four features - and the thing that would show whether the review sheets and the detail limits hold on a
shipped character rather than a fixture.

A new hair or garment kind should arrive as a plugin preset or builder that a spec names, not as code in a build
script.

### 7. Triage the old project notes

`grungist-creek/docs/plugin-improvements.md` predates all of this. Some entries are stale. Others may still be live
and are not filed anywhere:
- `flesh.add_jiggle_bones` stripping weights on a re-run
- the jiggle modifier needing physics-tick processing
- the hard `max_offset_m` clamp
- the volume API gaps (`collision_mask`, `tumble`, `push`)

Check each against current code, then file it under a category in [README.md](README.md) or strike it.

### 8. Loose ends the merges left behind

Each was found and written up by the branch that caused it, and none blocks anything today:

- **`regress.py --godot` still runs only `verify_moves.gd` and `verify_wardrobe.gd`.** The second
  round's ponytail pass was another hand run in a scratch project, so `pipeline_ponytail`'s swing is
  not in the suite either. follow-through's
  `verify_flesh.gd` (with the new `within_body` check) and `verify_strands.gd` have no harness entry, so
  the whole Godot half of flesh limits and strand springs is covered by hand runs in scratch projects.
  That is now the largest hole in the suite.
- **Review sheets are written into the game project on every character rebuild** - the rigify_human
  fixture's sheet is 24 MB, the cricket's 13 MB - and nothing gitignores them. `grungist-creek` wants a
  `.gitignore` line for `assets/**/review/` before the characters are rebuilt, and the SKILL.md tables
  should carry megabytes beside the seconds.
- **`review.sheet` is destructive to the folder it is handed:** it deletes every `*.png` and `review.json`
  in `out_dir` and writes `.gdignore` into `out_dir`'s parent. rig-anything's SKILL.md advertises calling
  it directly. It wants a guard, or at least the warning.
- **follow-through puts an MPFB curvy woman's breast regions on her jaw** (the zone reaches to 1.45 of
  shoulder height and the chin leaves the lean envelope first), so wardrobe cannot flatten her bust.
  `sports_top` works around it with an `all` limit and no flatten; the zone itself is unfixed.
- **A flesh type with no `limit_share` still gets `max_offset x 2 x peak_m` = 1.2 x peak_m from the
  material,** looser than the 1.0 geometric cap, so such a limit can only ever be lowered. Both sample
  bodies' `arm_flab` fails `within_body` at its shipped limit and needs `soft_fat` retuned (at 2.7 Hz it
  sags 3.4 cm off a 2.2 cm flab), not a different limit.
- **Changing `[hair]` costs a rebuild from the `body` stage,** because hair joins into the body and there
  is no `hair.remove`. Fine for shipping a character, expensive for iterating on presets.
- **Nothing in character-pipeline calls `muscle.define` or `detail.bake_normal_from_high` yet.** The
  `[body] definition = "geometry" | "normal"` field is still open, and `dante.toml` still forces
  `muscle = 1.0`.

From the second round (motion-critic, hair-strands-integration):

- **Idle dead band in `verify.arm_swing`.** Both fixtures' idles sit 8-11 deg in front of hanging and
  pass only because their swing is under `SWING_MIN_DEG` (8). An idle given 8-15 deg of arm swing (about
  3 of `upper.idle_defaults()` `arm_swing`) would be checked and fail. Its failure message also prints
  whole degrees against a 2.0 deg limit, so a fail at 2.049 prints the same numbers as a pass.
- **`upper.py` stores only `ap["arms"]`,** so the build report does not say whether the arm guard ran
  on a clip (`running` and `checked` are dropped). `arm_swing` (style: share of reach) and
  `arm_swing_deg` (report: degrees of carry range) share a name in unrelated units.
- **Two strand checks disagree.** `check_export` refuses any loose unchained `ft_type="strand"` mesh,
  but the strand stage exists only when the preset has a chain, so a `blend`-source body with a stray
  strand object and a bun or long_loose preset cannot export. `run_export` also leaves a stale
  `<id>_hair.glb` behind when a spec moves off ponytail.
- **"moves before strand" is documented, not enforced on a rebuild** (harmless in practice: `prepare`
  is idempotent and bodymap skips `ft_role` bones), and nothing covers the chain settling on Idle after
  a Run. `strands.md`'s Figure and MPFB-woman rows were measured with the old nearest-cell reader.
- **`long_loose` needs a sheet of chains,** or to be typed as a shell and routed to cloth.
- **`regress.py --update` writes temp paths and timings into goldens,** which the comparison ignores;
  every update churns all goldens with noise that has to be put back by hand.
- **04's doc cites session scratch paths** (`scratchpad/wf2/critic/...`) as evidence; they die with the
  session.

---

## Things that cost time to learn

Most of this is now in `CLAUDE.md`. The rest:

- **Building the project's characters without touching its assets.** Copy these into a scratch folder with the same
  layout:
  - `characters/`
  - `assets/humans/build_human.py`
  - `assets/belle/build_belle.py`

  Then point the specs' `blend =` at scratch and set `PROJECT` to that folder. Set `RA_SCRIPTS`, `HF_SCRIPTS`,
  `FT_SCRIPTS`, `WD_SCRIPTS` and `CP_SCRIPTS` to this repo's `plugins/<name>/scripts`, and `HUMANFORM_LIBRARY` to a
  copy of `~/.claude/humanform/library`.
  - Timing: a crowd person builds in 10-20 s, Belle in about 40 s.
  - `who=tomas` needs `C:/Users/pauli/Code/Blender/humanform_hands_feet_demo.blend` opened.
  - Always check the spec's `blend` path first. A build saves there.
- **Comparing a rebuild with committed assets.** Compare manifests with `regress.compare` at the harness tolerance.
  Compare glbs by their glTF JSON chunk with `extras` set aside. Both one-offs were in the 01 conversion; bone-role
  tags, rig profiles and humanform sheets are all extras.
- **Verifying in Godot** (`GODOT` = the `_console` build, path in grungist-creek's CLAUDE.md):

  ```
  "$GODOT" --headless --import --path .
  "$GODOT" --headless --path . belle_demo.tscn -- --selftest
  "$GODOT" --headless --path . people_demo.tscn -- --selftest
  ```

- **Finding a nondeterminism.** What worked, in order:
  1. Compare the written files.
  2. Checksum each stage's output in two builds and find the first that disagrees.
  3. Hash that stage's inputs, structure (face order, sorted and unsorted) as well as positions.
  4. Reproduce it minimally: three processes, three hashes.

  5.7 ended in Blender itself: `create_uvsphere` shuffles faces per process.
- **Parallel agents.** Give each agent a worktree, a scratch folder, and a list of the files it must not touch. Keep
  version bumps, NEXT.md and tests/README.md for whoever merges. Merges then only conflicted in goldens, which
  resolve by taking one side and re-recording with `--twice --update`, then reviewing the diff.
  - Six branches in one round bore that out: the golden conflicts were all volatile temp paths, and the
    only real conflicts were the places two branches added to the same list - `follow_through.MODULES`,
    `humanform.MODULES`, `lookdev_blender`'s imports, two SKILL.md tables and two design-doc sections.
    All of them resolve as a union, and every one is a list a branch appends to. Worth knowing the shape
    before the next round.
  - The second round merged two branches with no textual conflict. Their one interaction was in a
    golden: `pipeline_ponytail`, recorded on one branch before the other's export wrote `arm_pose`,
    gained `arm_pose_on_disk` on the re-record - so re-record once after all merges, not per branch.
  - A parked branch is worth stating out loud. `skirts-dresses` was mid-fix when the round ended, so it
    was left with its worktree and branch in place and this file says why; without that a later merge
    agent sees an unmerged branch and has to guess.

## Loose ends outside the code

- `C:/Users/pauli/Code/Blender/belle_demo_before_rebuild.blend` (100 MB) is still there. `belle_demo.blend` and its
  backup are in the Recycle Bin, split into `belle_stylized.blend` and `creature_tests.blend`.
- This repo is public, and `plugins/humanform/data/` (ANSUR II public CSVs and the seed contact sheets) is published
  with it. That was a deliberate choice, recorded here in case it is revisited.
