# Next: realism on the figure study

A handoff for a fresh conversation. Start with:

> Read `docs/improvements/NEXT.md`, then plan the first step of "The realism work" below.

State as of 2026-09-18. Everything is pushed: this repo at `6dc9962` plus this handoff, `grungist-creek`
at `afe71f3`. The parked branch `fig-genital-anatomy` (`94ac682`) is pushed too and still has its
worktree at `.worktrees/fig-genital-anatomy`. There are no other worktrees or open branches.

Read these first, in this order:
1. The repo's `CLAUDE.md`: worktrees, scratch folders, the regression harness, install and version rules, gotchas.
2. [06-figure-study-lessons.md](06-figure-study-lessons.md): what the figure study round learned, with a
   ranked list of plugin improvements. Section 3 has every failure with its attempts and time cost;
   section 6 has the orchestration lessons. The raw lab notebooks are in
   [notebooks/figure-study/](notebooks/figure-study/).
3. [HISTORY.md](HISTORY.md) only when you need the record of rounds one to three (merge log, old loose ends,
   every number). It was this file until now.

Installed copies in `~/.claude/skills` match the repo. **This is the one list of versions**; update it
here and nowhere else:
- rig-anything 0.25.0
- animate-anything 0.10.0
- follow-through 0.6.1
- humanform 0.10.0
- character-pipeline 0.9.0
- wardrobe 0.5.0
- lookdev 0.4.0
- godot-lsp 0.1.0

---

## Where the figures are

`grungist-creek/characters/study_man.toml` and `study_woman.toml` build through character-pipeline at
`quality = "final"` in about 25 s each, into `assets/figure_study/`. `figure_study.tscn` shows both on
turntables: keys 1-7 clips (Idle, Walk, Run, Crouch, Jump, TurnL, TurnR), F/S/B/Q/C views (C is a 1 m
close-up, Tab picks the figure), L lighting presets, T turntables, J flesh, H hair strands. Its
`--selftest` passes, as do `belle_demo`, `people_demo`, `verify_moves` and `verify_flesh` (walk, run and
jump courses). Open the scene and look before planning; the scratch screenshots from the last round are gone.

**Judged honestly: clean, well-proportioned CG figures that move properly, not yet realistic.**

| Works | Wrong |
|---|---|
| Proportions (humancheck 0 fail on both) | The man's `short_crop` reads as a helmet, with a hard, spiky fringe at the hairline |
| The woman's skin tone and subsurface in Godot; her brows and eyes at 1 m | His forehead and lips are glossy, in Blender and in Godot |
| Natural-speed gaits with heel strike and toe off; a run with a flight phase; turns | A dithered, stippled shadow from the hair shell on both necks under the ear (lookdev hair preset, transparency 4) |
| The ponytail swings 45 deg on the run | Skin reads smooth at viewing distance: the pore detail is in the material but does not show past about 1 m |
| Flesh bounded on every course | Lashes read sparse (cards seen edge-on, alpha mip erosion) |
| | **No genital anatomy:** both crotches are smooth; the branch that adds it is parked (below) |
| | The game's real assets still carry 1024 px skin: final bakes at 2048 since character-pipeline 0.8.0, but they have not been rebuilt |
| | golden_hour overexposes the pale woman and stripes the floor; interior_daylight was dropped from the demo |

---

## The realism work, in order

The goal: the two study figures read as real people in `figure_study.tscn` at 1 m and at full body, in
at least clear_midday and overcast, and move like people. Every step is proven on those two specs,
built through the pipeline and looked at in Godot, not only in a fixture.

### Step 0 - make the look loop fast (do first; everything after is a look loop)

Last round, at least six agents wrote their own render scripts, framing the hands failed three times,
and a close-up that would have shown a defect was missing twice. Fix the loop before the looks:

- **06 rank 1 - a close-up look set in the review stage: done** (branch `cp-close-look-set`, rig-anything
  0.25.0, character-pipeline 0.9.0, merged 2026-09-18). rig-anything `closeups.look_set` renders lit EEVEE
  tiles of the Idle clip's frame 1 - face, face_3q, eyes, head_side, head_back, palm and back of each hand,
  bust, crotch, knees, feet, foot_inner.L, foot_outer.L at 0.4-1 m, and a 0.42 m under_bust for a spec
  wearing a top - with cameras aimed from the posed bones, a label band per tile, `sheet.png` and
  `close.json`. The review stage writes `review/<id>/close/` and fails on an empty, off-centre or
  off-body tile (wrong-bone and empty-tile controls in pipeline_woman). All views at final (+2.8 s),
  6 at preview, face and left hand at draft (0.64 s); `[review] close = false` turns it off. SKILL.md
  maps each look-checklist question onto its tile; an independent critic answered the checklist from
  the PNGs alone. Open: the framing check is centroid-only (a palm camera 6 cm up passes with the
  fingertips cut off - needs every subject point inside the tile, with a control); hand_back looks from
  the side of the curled hand (thigh fills half the tile, nails not visible); `close = false` leaves a
  stale close/ folder and still hashes the close part; the preview set was never built on a real spec;
  only the left foot has side views; a non-human rig needs `close = false`. Defects the set shows
  (hairline, glossy forehead and lips, sparse lashes, Belle's missing brows and under-bust shelf, smooth
  crotches, unmodelled ankle bones and arch, a red streak on study_woman's right thigh) belong to later steps.
- **06 rank 8 - Godot-side look tools in lookdev: done** (branch `lookdev-godot-tools`, lookdev 0.4.0,
  merged 2026-09-18). `lookdev.mjs close-shot` loads a glb, applies lookdev materials, poses a clip and
  writes a labelled sheet (face, eyes, palm and back of each hand, feet, bust, crotch, full body,
  `bone:<name>`) with cameras aimed from posed bones, under named presets; it fails on a missing
  skeleton or bone, an unknown clip, or an empty/small/off-target tile. `lookdev.mjs tone` probes a
  glb's albedo; `lookdev_presets.gd` applies `presets.json` (now in the addon) at runtime, and
  `figure_study.gd` uses it instead of its own port. interior_daylight is marked `needs: interior` and
  refused on an open stage. `lookdev.mjs selftest` runs 11 controls. Open: no control for close-shot's
  post-render tile checks and no `--min-subject` flag; `tone --expect` only reports; `tone` with no
  `--material` fails on study_woman's lashes (0.0073 under the 0.01 floor); `sky_openness` calls a
  runtime-built scene open (the refusal should name `--stage`/`--force`); `LookdevPresets.apply` can
  leave the Environment half-changed when it returns not-ok; close-shot and the selftest are not in
  `regress --godot`; bone aliases cover Rigify/rig-anything and Mixamo only; tone writes its default
  output under the shared `%TEMP%/lookdev/`. Defects the close-ups show (fingertip and neck stipple,
  orange palms on study_man, stair-step sun shadows at 1 m, clumped lashes) belong to steps 1 and 2.
- **06 rank 3 - rebuilds that match what changed: done** (branch `cp-resume-hashes`, character-pipeline
  0.8.0, follow-through 0.6.1, merged 2026-09-18). `runner.build(resume=True)` (build.py, run.sh, the game's
  build_human.py/build_belle.py) opens the spec's saved blend; `fresh=1` builds from nothing. bake, hair,
  flesh and garments hash the code and data they read (`inputs.py`) and a rerun names what changed;
  `runner.plan()` gives the hashes. A `[flesh]` edit on study_man reruns flesh..review in 18 s against 31 s
  (06 estimated 12 vs 25); on a dressed spec it restarts from body (fixed at merge: it refused). The
  `pipeline_hashes` fixture flips 19 inputs, each with a drop-control. follow-through 0.6.1: a second
  flesh.prepare gives the jiggle weight back; limit_influences keeps weight totals. Open: a resumed flesh
  rerun is within 0.074 of a fresh build's weights; moves/export/review (17 s) still rerun after a flesh
  edit; body, moves, strand, export and review name no code files (rig-anything's covered only by its
  version); from=bake on a haired body refuses; a dressed spec's flesh edit rebuilds everything; no
  dedicated control for the limit_influences fix; three pipeline_hashes flips lack drop-controls.
- **06 rank 12 - bake at final size: done** (same branch). Final bakes skin at 2048 px, preview and draft
  at 1024; the size is in the bake hash, and the manifest has a `skin` block (map_px, tone_ok, region
  tones). It adds about 7 s to a final bake. Open: the game's real assets have not been rebuilt.
- **06 section 5 - repo tooling: done** (branch `repo-regress-quick`, merged 2026-09-18). `regress.py`
  runs longest first, prints results as they finish, ends with `REGRESS DONE exit=N, K fixtures ok`,
  always writes a diff file, and has `--quick` (fixtures selected from the git diff; `--dry-run` shows why).
  `tools/bump.py` does version bumps; `tools/test_tools.py` checks both. A full `--quick --jobs 4` took
  about 3.5 min. Open: mpfb_woman_curvy's glb readback sits under the VOLATILE key `export.file` and is
  never compared (renaming it moves goldens); `--restamp` and refusing `--update` off main are not done;
  DURATIONS is a static table; addon sync and `.gitattributes` from the same list are not done.

### Step 1 - hair

- **The man's hairline.** Replace the hard cut and spiky fringe with a feathered hairline that reads as
  hair at 1 m. The hair layer already has feathering; `short_crop` is its weakest preset.
- **The neck stipple (06 rank 14).** Hair shells should cast a scissor shadow, not a dithered
  depth-pre-pass one. Also: a card mode in `hair.strand_texture` with no opaque middle, and alpha to
  coverage or a mip bias for cards.
- **Lashes and brows.** Lashes that read at 1 m from the front. A brief field for brow shape.
- **Motion.** `verify_strands` fails its cross-rate spread on the ponytail (1.26 against 1.25; the limit
  was not widened): make the strand spring frame-rate independent and add it to `regress --godot`
  (06 rank 13). `long_loose` is still rigid: it needs a sheet of chains or a route to cloth.

### Step 2 - skin

- **Detail that survives distance.** Pores exist as a Godot detail normal on UV2 but vanish past about
  1 m. Add mid-frequency variation: tone and redness by region (knees, elbows, knuckles, face, the
  soles), and a roughness map by region so the forehead and lips stop reading as gloss.
- **Small defects:** thin orange lines at the finger-web creases under clear_midday.
- **Lighting presets on an open stage:** golden_hour overexposure and floor stripes. (interior_daylight is
  marked interior-only since lookdev 0.4.0.)

### Step 3 - anatomy: genitals (parked branch)

`fig-genital-anatomy` at `94ac682` fuses MPFB's helper-genital shell into the body, weights it, types
it in follow-through (opt-in) and exports it. It failed its merge gate: in Crouch, Jump and Run the
thighs pass 27-30 mm into it. 06 section 3C has all 13 attempts. The finding that matters: **the cause
is not the genitals.** rig-anything's linear blend skinning collapses the crotch, and the two inner
thighs cross each other in Walk and Run, so there is no free space to push into.

So fix the hip first, in rig-anything: hip and thigh deformation that keeps volume (helper or twist
bones at the hip, corrective shape keys driven by thigh angle, or dual-quaternion skinning where Godot
supports it). That also serves the skirts' open problem (a raised thigh through the front panel) and
every character's crouch. Then rebase the branch onto `main`, merge `main` into it, and re-run its gate
with an **absolute** clearance limit rather than "better than before".

Also on this branch: `genital_shape = 1.0` maps onto MPFB's extreme length target (up to 16 cm longer);
a neutral anatomical default needs a sane range. And add a posed limb-clearance check to humancheck
(06 rank 10), so this failure shows up as a number.

### Step 4 - flesh correctness (06 rank 9)

The shipped specs carry workarounds that should not be needed: the man's `limit_share = { belly = 0.4 }`
and the woman's `may_miss = ["belly"]`. Give belly a registry `limit_share`; fix `peak_m` reading
0.168 m on an athletic belly; stop the breast zone claiming the belly; make `verify_flesh.within_body`
able to fail (today a 17 cm belly swing passes). Done when both figures build with neither line and pass
the jump course.

### Step 5 - motion

- **06 rank 5 - rig-anything never sets `U.running`,** so every Run is judged as a walk and the run-only
  arm checks never run. Set it where `Upper` is built (`locomotion.py` ~803, `actions.py` ~654). This
  also unblocks the crowd rebuild (below).
- **06 rank 15 - MovesController plays TurnL/TurnR** and applies the manifest's turns; the demo carries
  a port of this.
- Small gaps remain between the fingertips (the middle and end finger bones keep MPFB's rest fan).
- Run the motion critic (`animate-anything/references/motion-critic-checklist.md`) on every clip of both
  figures after each change, as an independent subagent.

### How to judge "realistic"

Last round's final critic was not independent: that agent had no Agent tool and answered its own
checklist. This round:
- Run every look and motion critic as its own subagent, questions written before any image is opened,
  and record in the result which critics were independent.
- Judge from Godot renders at stated distances (1 m and full body), in clear_midday and overcast, not
  from Blender alone: lookdev materials differ between the two.
- For each step, write the critic's questions into the step's done-when before starting it.

---

## Running the next session

What the last three rounds taught about running this work (06 section 6 has the detail):

- **Merge one branch at a time, as each finishes.** No wave waits for its slowest member. After each
  merge, branches still in flight merge `main` in before their review starts.
- **Regress is the critical path** (11-23 min per merge, about 7 hours in the last round against about
  25 min of character building). Use `--quick`-style runs per merge where possible and one full
  `--twice --godot` at the end. The repo-tooling list in 06 section 5 (`regress.py` scheduling and
  output, `tools/bump.py`, addon sync, `.gitattributes`) is worth doing early for that reason.
- **A feature is done only when a real spec uses it through the pipeline and it is looked at in Godot.**
  Last round, fixtures passed while Belle's top, the man's belly, the crowd's runs and the ponytail's
  frame rate all failed on real characters.
- **Every check ships a control that must fail, and a check that can clamp its own measurement reports
  the free value.** Nine checks passed what the eye rejected last round (listed in 06 section 6).
- **Keep the lab notebook.** Each agent appends to its own notebook as it goes: failures with exact
  errors, attempts, time cost, dead ends, and what worked first time. They feed the next lessons file.
- **Give each agent a time budget and a three-attempt rule:** after three real attempts, keep what works
  (off by default if it is not good enough), record the rest as open, and return.
- **Shell rules for every agent:** regress runs longer than 10 minutes, so start it in the background and
  wait with Monitor; write any Python longer than a line to a file; never `git stash` in a repo with
  parallel worktrees (the stash is shared); pass `cygpath -m` paths to Godot and Blender.
- **Resuming an edited workflow re-runs everything after the first changed call.** To drop a stream
  mid-run, start a fresh workflow for what remains instead.

---

## Other open work (not realism)

- **The rest of 06's ranked list:** specs safe to copy (rank 2), stage numbers never lost (4), stored body
  fits (6), a draft setting for moves (7), verifiers that exit non-zero (11).
- **The crowd rebuild** waits on the `U.running` fix (step 5). A spec workaround for 7 Run clips exists as
  a patch but was not applied and should not be.
- **Skirts (05 · 5.4), open items:** a run's raised thigh through the front panel, a stiff deep crouch, and
  no check that counts the first. Step 3's hip fix is the likely cure.
- **Loose ends from rounds one and two:** HISTORY.md items 7 (triage `grungist-creek/docs/plugin-improvements.md`)
  and 8 (a list of small defects each branch left behind).

---

## Things that cost time to learn

Most of this is now in `CLAUDE.md`. The rest:

- **Building the project's characters without touching its assets.** Copy `characters/`,
  `assets/humans/build_human.py`, `assets/save_guard.py` and `assets/belle/build_belle.py` into a scratch
  folder with the same layout. Point the specs' `[export] blend` at scratch (a build saves there; check it
  first) and set `PROJECT` to that folder. Set `RA_SCRIPTS`, `HF_SCRIPTS`, `FT_SCRIPTS`, `WD_SCRIPTS` and
  `CP_SCRIPTS` to this repo's `plugins/<name>/scripts`, and `HUMANFORM_LIBRARY` to a copy of
  `~/.claude/humanform/library`. In TOML, write Windows paths with forward slashes.
  - `who=tomas` needs `C:/Users/pauli/Code/Blender/humanform_hands_feet_demo.blend` opened.
- **Comparing a rebuild with committed assets.** Compare manifests with `regress.compare` at the harness
  tolerance, and glbs by their glTF JSON chunk with `extras` set aside.
- **Verifying in Godot** (`GODOT` = the `_console` build, path in grungist-creek's CLAUDE.md):

  ```
  "$GODOT" --headless --import --path .
  "$GODOT" --headless --path . figure_study.tscn -- --selftest
  "$GODOT" --headless --path . belle_demo.tscn -- --selftest
  "$GODOT" --headless --path . people_demo.tscn -- --selftest
  ```

  Pass full clip names to `verify_wardrobe` (`Belle_Walk`, not `Walk`) and check `samples` > 0 in every result.
- **Finding a nondeterminism:** compare the written files; checksum each stage's output in two builds and find
  the first that disagrees; hash that stage's inputs, structure (face order) as well as positions; reproduce
  it minimally in three processes. 5.7 ended in Blender itself: `create_uvsphere` shuffles faces per process.
- **Merges:** the real conflicts are the lists every branch appends to (`MODULES` in the plugins'
  `__init__.py`, lookdev's imports, SKILL.md tables, design-doc sections). They resolve as unions.
  Re-record goldens once after the last merge in a batch, not per branch.

## Loose ends outside the code

- `C:/Users/pauli/Code/Blender/belle_demo_before_rebuild.blend` (100 MB) is still there.
- The `.blend` backups from the last three rounds were in session scratch folders, which are gone. The
  real blends in `C:/Users/pauli/Code/Blender/` are current; the figure study's are
  `figure_study_man.blend` and `figure_study_woman.blend`.
- `grungist-creek/tomas_demo.tscn` is untracked and refers to a `tomas_demo.gd` that does not exist; Godot
  logs an error for it on every import. Delete it or finish it.
- This repo is public, and `plugins/humanform/data/` (ANSUR II public CSVs and the seed contact sheets) is
  published with it, a deliberate choice recorded here in case it is revisited.
