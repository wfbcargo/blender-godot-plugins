# Next: realism on the figure study

A handoff for a fresh conversation. Start with:

> Read `docs/improvements/NEXT.md`, then plan the next step of "The realism work" below and run it with
> the `plugin-round` workflow (see "Running the next session").

**The goal of all this work:** tools that make a new human asset from a brief **in under 30 seconds** and
have it **look great** in Godot. The study figures are the test bench; the scoreboard is the benchmark
(below): three brand-new characters built cold from their briefs, timed, and judged by an independent critic.
Every round's ship step runs it, and every plan should say which of the two numbers it moves.

State as of 2026-09-18, after realism Step 0.5 and Step 1 (hair) shipped. Everything is pushed: this
repo's `main` and `grungist-creek`'s `master` (the rebuilt figures and Belle). The parked branch
`fig-genital-anatomy` (`94ac682`) is pushed and still has its worktree at `.worktrees/fig-genital-anatomy`.
There are no other worktrees or open branches. Step 2 (skin) is next; Step 1's leftovers (the short cap's
volume and colour, `long_loose`) are listed under it.

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
- rig-anything 0.26.0
- animate-anything 0.10.1
- follow-through 0.10.0
- humanform 0.12.0
- character-pipeline 0.14.0
- wardrobe 0.5.2
- lookdev 0.7.0
- godot-lsp 0.1.0

---

## Where the figures are

`grungist-creek/characters/study_man.toml` and `study_woman.toml` build through character-pipeline at
`quality = "final"` in about 32 s each from nothing (a resumed rebuild skips unchanged stages), into
`assets/figure_study/`, with skin baked at 2048 px. They and Belle were rebuilt on 2026-09-18 by the Step 1
ship step on every version listed above (study_man 37.6 s, study_woman 34.3 s, Belle 36.5 s, every stage rerun);
Belle now has brows and lashes. `figure_study.tscn` shows both on
turntables: keys 1-7 clips (Idle, Walk, Run, Crouch, Jump, TurnL, TurnR), F/S/B/Q/C views (C is a 1 m
close-up, Tab picks the figure), L lighting presets, T turntables, J flesh, H hair strands. Its
`--selftest` passes, as do `belle_demo`, `people_demo`, `verify_moves` and `verify_flesh` (full, walk, run and
jump courses).

To look at them: each build writes the Blender close-up set to
`assets/figure_study/<id>/review/<id>/close/` (`sheet.png`, 16 tiles, `close.json`; the folder is git-ignored).
In Godot,

    node ~/.claude/skills/lookdev/bin/lookdev.mjs close-shot --project .       --glb res://assets/figure_study/study_woman/study_woman.glb --views head,hands,full       --presets clear_midday,overcast --pair-blender assets/figure_study/study_woman/review/study_woman/close       --out <scratch>

writes a sheet with one row per view (face, face_3q, eyes, head_side, head_back, the four hand views, full),
the Blender close-set tile first and one column per preset, in about 20 s (Belle needs `--garments
res://assets/belle/belle_sportstop.glb,res://assets/belle/belle_shorts.glb`). Run it on a copy of the project
(`tools/scratch_project.py`, or a tar copy), not the game itself. The Step 1 ship step's sheets (study_man,
study_woman, belle; 1 m, clear_midday and overcast) are in `%TEMP%/rw/ship/look/<id>/sheet.png` (a scratch
folder; regenerate rather than rely on it). They show the table below: the neck stipple is gone, the man's
hairline has fine edge hairs, and brows and lashes read as hair at 1 m; the vertical specular band on the
foreheads under overcast is still there.

**Judged honestly: clean, well-proportioned CG figures that move properly, not yet realistic.**

| Works | Wrong |
|---|---|
| Proportions (humancheck 0 fail on both) | The man's `short_crop` is still a smooth, dark, slicked shell at 1 m with a hard front line behind the edge hairs (needs volume and colour variation) |
| The woman's skin tone and subsurface in Godot; brows, lashes and eyes at 1 m on all three | His forehead and lips are glossy, in Blender and in Godot; both foreheads carry a vertical specular band under overcast |
| Natural-speed gaits with heel strike and toe off; a run with a flight phase; turns | An orange fleck at the man's thumb web under clear_midday |
| The ponytail swings 44-46 deg on the run at any frame rate | Skin reads smooth at viewing distance: the pore detail is in the material but does not show past about 1 m |
| Flesh bounded on every course; no neck stipple (sun soft-shadow filter) | study_man goes dark and muddy under overcast |
| | **No genital anatomy:** both crotches are smooth; the branch that adds it is parked (below) |
| | golden_hour overexposes the pale woman and stripes the floor; interior_daylight was dropped from the demo |

**Baseline after Step 0** (independent look critic, Godot close-shot sheets at 1 m and 4 m, clear_midday and
overcast; notebook `notebooks/realism-step0/ship.md`). Ranked, what most separates the figures from real people:
1. **Hair** reads as a helmet: a smooth, hard-edged shell, the hairline a smeared radial gradient, no flyaways,
   a hard dark band in front of each ear. **The Blender close set shows fine strands at the hairline, so
   the look is lost between Blender and Godot**: start Step 1 there, not in the hair layer.
2. **Brows and lashes**: brows are hard, pixelated black cut-outs (darker and heavier than in Blender), lashes
   a few black blocks with one clump spiking over the pupil; pupils flat black discs.
3. **Skin**: one uniform colour at 1 m and 4 m, no regional tone, pore grain only in highlights.
4. **Specular under overcast**: hard, mirror-like patches (a vertical band on the forehead, nose, lips) -
   lacquered plastic. Clear midday's sheen is acceptable.
5. **Dithered shadow stipple under clear_midday** on the front of the neck *and on shadowed fingers*,
   visible at 4 m; absent under overcast.
6. **Coloured edges on the fingers**: orange-red at finger edges and the thumb web (clear_midday), pale lines
   at the fingertips (overcast).
7. **Overcast exposure**: study_man goes dark and muddy (reads as a different skin tone); study_woman grey.

**After Step 1** (independent look critic on study_man, study_woman and Belle; notebook
`notebooks/realism-step1/ship.md`). Fixed: the neck and finger stipple (study_woman keeps an orange glow between
the fingers), brows made of hairs instead of cut-outs, a feathered hairline on all three. Still **clean CG at
1 m and full body**. Ranked, what now most separates them from real people:
1. **Hair volume:** above the hairline every head is a smooth glossy shell with painted streaks; the nape and
   sideburns end in a hard cut (on Belle a vertical flap in front of the ear); the ponytail is a flat, banded ribbon.
2. **Skin:** plastic and uniform - no pores, redness or micro-detail - and waxy under overcast.
3. **Eyes:** flat irises, oversized black pupils, no limbal ring or wet line, a dark ring around the socket.
4. **Pose and body:** stiff A-pose/rest pose with rubbery fingers; mannequin-smooth at full length.
5. **Lashes and hairline edge:** too even and comb-like, no clumping or scatter.
6. **Leftover shading:** the orange glow between study_woman's fingers; the man's orange thumb-web fleck.

Close-shot gaps the critic hit: no Blender tile for `full`, no neck view, and the Blender pairs are shot at
0.4-0.6 m against Godot's 1 m, so a pair is not like for like.

---

## The benchmark: a new human in under 30 s that looks great

The `plugin-round` workflow runs it after the ship step when given `benchmark` (the briefs are in
`.claude/workflows/benchmark-briefs.json`; keep them fixed so rounds compare):

| id | brief |
|---|---|
| `bench_marco` | A stocky Hispanic man in his 40s with a strong jaw. |
| `bench_mei` | A skinny, tall Asian woman in her 20s: slim figure, athletic build, long hair. |
| `bench_ruth` | An older Caucasian woman in her 60s: a little heavier in build but fit and healthy, cropped grey hair. |

For each, one at a time so the timings are clean: a scratch project (`tools/scratch_project.py`) with a library
copy that holds no body for the brief; a spec written from the brief with only what a user would choose; three
cold `fresh=1` builds at final quality in a fresh Blender process (median wall time, Blender start-up included,
against **30 s**), a warm rebuild and a one-line `[flesh]` edit; a Godot close-shot sheet paired with Blender;
the three slowest stages; and a **brief-fidelity** list - every part of the brief the tools could not express.
An independent critic then scores the sheet on `lookdev/references/critic-look.md` (pass count), says whether it
reads as a real person, and names each mismatch with the brief.

Where it starts: the study figures build from nothing in 34-38 s with every stage rerun (Step 1 ship), and a
fresh body fit alone took 11-14 s in the figure study round. Gaps the briefs will likely hit, from reading
humanform: age is capped at 58 for a fitted adult (ANSUR II has no older adults), so Ruth's 60s need handling
past the fit; MPFB's ancestry macros are asian/caucasian/african only, so "Hispanic" needs a mapping to a mix
plus skin tone; no confirmed jaw-shape control in the brief; `long_loose` hair is still rigid (Mei); Ruth's
cropped grey hair is `short_crop`, whose shell is the critic's first complaint.

**The cast demo (2026-09-18): the first new characters from briefs.** `grungist-creek/cast_demo.tscn` shows
`characters/cast_marco.toml`, `cast_mei.toml` and `cast_ruth.toml` (the three benchmark briefs, built by hand from
specs with the installed plugins: Marco 40.6 s, Ruth 38.9 s; review 7-8 s and bake 7-9 s are the biggest stages).
**The user's review, recorded as given:**
- Something jiggles on their mouths that looks unnatural (all three).
- Marco's chest and stomach jiggle together, in the same motion, far too much - it looks very odd.
- Walking and running are very stiff: animation work to do.
- Breast and butt jiggle does not feel correctly weighted; the point of attachment and the weight distribution
  are the likely cause.

**Diagnosed and researched: [research-flesh-jiggle.md](research-flesh-jiggle.md).** The mouth jiggle was
follow-through's breast search landing on the lips and chin (Mei's and Ruth's breast bones sat on the face, so their
breasts did not move at all); Marco's belly region was his whole front torso, 0.92-1.31 m. Fixed at spec level in the
game (`72effe5`: hand-marked `[[flesh.zones]]`, Marco's belly off). The plugin changes, ranked, with checks and
controls, are items A-G there: bone placement and a zone check first, then graded weights from the attachment, the
pivot at the upper attachment, an asymmetric spring, mass-scaled response, and spec material overrides.
**A and G: done** (branch `flesh-zone-placement`, follow-through 0.7.0, character-pipeline 0.13.0, merged to main
2026-09-18; installed and shipped: grungist-creek `3b30199` drops the cast's hand-marked zones, rebuilds Marco,
Mei and Ruth, cast_demo selftest and verify_flesh full/walk/run pass, breasts peak 5.4-5.7 cm on the run). Face vertices never seed a region, a breast keeps the patch nearest its zone
centre a side, and `flesh.check_placement` fails a bone or weight centre above the chin or outside its zone, or face
weight over 2 %; the pipeline's flesh stage fails on it (`MISPLACED`). Built without hand-marked zones in scratch, Mei
and Ruth's breast bones sit on the breasts (weight at the bust point 1.00 / 0.99, was 0.00). pipeline_woman's golden
had the same chin bug; it now carries the `FT_FLESH_LEGACY_PLACEMENT=1` control. The breast zone top stays 1.45
(1.0 broke the sample Figure's sports top and changed nothing on the cast). Independent critic: pass. Open: tail
5.7-8 cm from the bust point (item C); a rig with no head bone found passes the face tests silently; no escape for a
deliberate mark outside a zone; "above the fold" unchecked. Next: B+C, D+E, F. Notebook:
[notebooks/flesh-cast/flesh-zone-placement.md](notebooks/flesh-cast/flesh-zone-placement.md).

**B and C: done** (branches `flesh-graded-pivot` and `wardrobe-apex-cover`, follow-through 0.8.0, wardrobe 0.5.2,
merged 2026-09-18). Breasts and buttocks hang from above: pivot 3-6 cm over the apex, tail on it (shipped 0.5-3.8 cm
from the bust point), weight 0 at the attachment and on the thigh; check_placement tests it. It exposed a wardrobe
false positive (skin beside an armhole rim counted as through the cloth; runaway lifts), fixed. Critic: mergeable.
Open: a direct second `flesh.prepare` on a fleshed body can fail the check (fix with D+E: cap the jiggle share
below 1); the plain jump course fails on_limit for the cast (10.2-10.9 %; D is the fix); FACING_MIN vs cover's
fold rules. Notebooks: [flesh-graded-pivot](notebooks/flesh-cast/flesh-graded-pivot.md),
[wardrobe-apex-cover](notebooks/flesh-cast/wardrobe-apex-cover.md). Shipped: grungist-creek rebuilt cast, study figures and Belle; selftests and verify_flesh 24/24 pass. Next: D+E.

**D and E: done** (branch `flesh-spring`, follow-through 0.9.0, merged 2026-09-19). The jiggle spring is solved per
axis: soft_fat 2.4 Hz above rest, 2.8x below, 1.4x front to back (a breast floats up and stops hard); a kick
selftest runs in `regress --godot`. Mass-scaled frequency is built but off: the swing limit, not the spring, bounds
amplitude on every body. The 0.98 jiggle-share cap closes B+C's re-run item. Critic: pass. Open: the jump-only
course stays over its 10 % line for the cast (D did not fix it); walking in phase 0.69-0.85 against people's 0.66;
running amplitude ~6 cm against ~15 cm, bounded by the limits; E's lag and mass-scaled response. Notebook:
[flesh-spring](notebooks/flesh-cast/flesh-spring.md). Shipped: grungist-creek rebuilt (cast, study figures, Belle), selftests and verify_flesh 24/24. Remaining flesh item: F (spec overrides, Marco's belly).

**F: done** (branch `flesh-overrides`, character-pipeline 0.14.0, follow-through 0.10.0, merged 2026-09-19). A spec's
`[flesh] overrides` sets jiggle parameters per type or region. The belly's zone stops at 0.6 of the span and it hangs
from the lower ribs, so it no longer takes a man's chest (the research's cause 2); it ships limit_share 0.6. Marco's
belly is back at 4.5 Hz / 0.6 (1.2 cm walking, 1.3 running). Critic: pass. Open: study_woman's belly missed by
0.0001 m (may_miss stays); an empty above-apex window reads 0.0; registry.define lacks the attach keys. Notebook:
[flesh-overrides](notebooks/flesh-cast/flesh-overrides.md). **All of research-flesh-jiggle.md's A-G are now done.**

Also seen: garments are cut from the skin, so Ruth's long-sleeve top shows her nipples through it (a smoothing pass
on the cut surface).

Also found building them:
- **rig-anything close-up check, false alarm:** Mei's `hand_back.L` tile is framed well but fails `off_body`: the
  check tests one pixel at the landmarks' centroid, which falls between her spread fingers (the mirrored `.R`
  passes by a pixel). Her build stopped at review, so her blend was not saved. Test a neighbourhood or the nearest
  body pixel within a radius, with a control.
- **Brief fidelity:** no ancestry field (Hispanic and Asian carried only by skin, iris and hair colour, so the
  faces do not read as either); "stocky" via `build = "heavy"` reads average; the strong-jaw face part is too
  subtle; Ruth's face has no age at 64 (no age lines or skin change); `long_loose` is shoulder length, rigid and
  helmet-edged.
- **Godot runs rewrite committed JSON:** `addons/lookdev/presets.json` came back reformatted (content identical)
  after the cast selftest and shots, like `assets/wardrobe/nora.walk.json` in the Step 1 ship step. Find the writer.

---

## The realism work, in order

The goal: new characters read as real people at 1 m and at full body, in at least clear_midday and overcast,
and move like people - proven on the two study specs and on the benchmark, built through the pipeline and
looked at in Godot, not only in a fixture.

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
  dedicated control for the limit_influences fix; three pipeline_hashes flips lack drop-controls (both done
  in Step 0.5, critic-checklists-controls).
- **06 rank 12 - bake at final size: done** (same branch). Final bakes skin at 2048 px, preview and draft
  at 1024; the size is in the bake hash, and the manifest has a `skin` block (map_px, tone_ok, region
  tones). It adds about 7 s to a final bake. The game's study_man, study_woman and Belle were rebuilt at
  2048 px by the ship step (below).
- **06 section 5 - repo tooling: done** (branch `repo-regress-quick`, merged 2026-09-18). `regress.py`
  runs longest first, prints results as they finish, ends with `REGRESS DONE exit=N, K fixtures ok`,
  always writes a diff file, and has `--quick` (fixtures selected from the git diff; `--dry-run` shows why).
  `tools/bump.py` does version bumps; `tools/test_tools.py` checks both. A full `--quick --jobs 4` took
  about 3.5 min. Open: mpfb_woman_curvy's glb readback sits under the VOLATILE key `export.file` and is
  never compared (renaming it moves goldens); `--restamp` and refusing `--update` off main are not done;
  DURATIONS is a static table; addon sync and `.gitattributes` from the same list are not done.

**Step 0 status: done and shipped (2026-09-18).** All four branches merged; `~/.claude/skills` and the
game's addons match `main`. The ship step rebuilt study_man, study_woman and Belle in the game at final
quality (skin at 2048 px, close sets written) and they pass `--import`, the figure_study, belle_demo and
people_demo selftests, verify_moves (3 manifests) and verify_flesh (full, walk, run, jump on both figures).
`regress.py --twice --jobs 4 --godot` on `main`: `REGRESS DONE exit=0, 21 fixtures ok`, no change, 14 min.
One stale check fixed in the game: belle_demo's HAIR line wanted lookdev to set exactly one material, and
the baked skin is now a second one. What stays open is listed under each item above; the ones that bear
on the look loop first are close-shot's missing tile-check control and `--min-subject`, the look set's
centroid-only framing check and side-on hand_back, and neither close set being in `regress --godot`.
The round's lab notebooks: [notebooks/realism-step0/](notebooks/realism-step0/) (`repo-regress-quick`,
`lookdev-godot-tools`, `cp-resume-hashes`, `cp-close-look-set`, `ship`).

### Step 0.5 - tooling and plugin items to build first (branches of about 30 min, run in parallel with Step 1)

Suggested after the Step 0 round; each saves agent minutes on every later round.
- **`tools/scratch_project.py <dir> [--who study_man,...]`: done** (branch `tools-scratch-project`,
  character-pipeline 0.11.0, merged 2026-09-18; the game's specs and `build_human.py` merged to master too).
  One call copies characters, build scripts, root scenes, addons (the checkout's), the chosen blends and
  exports and the humanform library, writes `env.sh`/`env.ps1`/`build.sh` and runs `--headless --import`
  (about 5-9 s). With it, **06 rank 2**: a relative `[export] blend` resolves under `$BLEND_DIR`, else the
  project; `runner.build` refuses to save outside both unless `save_outside=True`. All 19 game specs are
  relative; `build_human.py` sets `BLEND_DIR` to `C:/Users/pauli/Code/Blender` only for the game itself.
  Fixture `pipeline_paths` (control `PIPELINE_PATHS_NO_GUARD=1`), `test_tools.py test_scratch_project`.
  Critic: pass. Open: the export hash covers the blend string, so each game figure's next build reruns
  export and review once (outputs match, 0 manifest changes); `make()` prefers `$BLEND_DIR` over the game's
  folder and `build_human.py` uses `setdefault`, so a sourced scratch env.sh leaks into the next copy or a
  real build (surprising, never writes the real blends); `rewrite_blend` handles only a double-quoted
  `blend = "..."` line (fails safe); the committed glbs carry a stale `.001` mesh name from a resumed build
  (runner/stages, not this seam); crowd humans and creatures are not copied. Notebook:
  [notebooks/realism-step1/tools-scratch-project.md](notebooks/realism-step1/tools-scratch-project.md).
- **close-shot views the look critic missed: done** (the stipple detector came with `hair-godot-transfer`,
  lookdev 0.6.0; branch
  `lookdev-closeshot-views`, lookdev 0.5.0, merged 2026-09-18; the stipple/dither detector belongs to
  `hair-godot-transfer`). New Godot views face_3q, head_side and head_back (a `head` group, in the default
  list), aimed with closeups._aim's formulas so frame widths match the Blender set. One row per view, one
  column per preset; each label sits in a band above its picture, and `full` checks the head's box against
  the band (LABEL_OVER_HEAD, control `--label inside`). Tile checks use each view's subject points
  (OFF_TARGET, SUBJECT_CUT in full; free values in close.json); `--aim-offset view=x,y,z` and `--min-subject`.
  `--pair-blender <close dir>` puts the Blender tile first in each row at its distance and lists unpaired
  views. selftest 11 -> 18 controls. `regress --godot` runs close-shot on pipeline_woman's glb (must pass), a
  camera-offset control (must fail) and the selftest. This also closes the Step 0 open items (tile-check
  control, `--min-subject`, close-shot and the selftest in `regress --godot`). Critic: pass. Open: SUBJECT_CUT
  has no committed selftest control; regress counts the must-fail control ok on any failure, not only
  OFF_TARGET; tile checks are centroid-only (the Blender set's every-point margin is not ported); since
  ra-closeup-framing's `close_off` case removes pipeline_woman's close/, regress's close-shot row runs
  unpaired (`--pair-blender` is still covered by the selftest's fake set; regress should keep a close set
  and fail when an expected pair is missing); `full` never pairs and Blender's crotch, knees, under_bust and
  foot side views have no Godot twin; a sheet over 16384 px is cut, not split; `--columns` is gone. Notebook:
  [notebooks/realism-step1/lookdev-closeshot-views.md](notebooks/realism-step1/lookdev-closeshot-views.md).
- **The look set's framing: done** (branch `ra-closeup-framing`, rig-anything 0.26.0, character-pipeline
  0.9.1, merged 2026-09-18). Every subject point (wrist, knuckles, fingertips; both eyes; ankle, heel, toe
  tip) must project 0.04 inside the tile, next to the centroid check. A failure is `cut`, and the free
  `subject_margin` goes in close.json. A palm camera 6 cm up fails [cut, off_centre]; at 3 cm only cut
  fails (pipeline_woman controls). hand_back looks from the front, a little below the knuckles (from above,
  the curled tips hid the nails). A far clip keeps the thigh out, so coverage is 0.30, down from 0.66-0.80.
  New foot_inner.R and foot_outer.R views. `[review] close = false` clears close/ and drops the close part
  from review's hash (pipeline_woman close_off, pipeline_hashes row, each with a control). Open: ring and
  pinky nails are hidden; the thigh's shadow still falls on the hand; humanform critic-body.md and lookdev
  critic-look.md still list only the left foot's side views; runner.stage_hash passes `ch` to for_hash, a
  one-line change outside the seam that cp-cascade-stop should keep; non-human rigs need close = false; a
  pale patch at the thumb base belongs to the skin step. Notebook:
  [notebooks/realism-step1/ra-closeup-framing.md](notebooks/realism-step1/ra-closeup-framing.md).
- **Rebuilds that skip what did not change downstream: done** (branch `cp-cascade-stop`,
  character-pipeline 0.10.0, merged 2026-09-18). Flesh saves a digest of what moves reads of its output
  (`inputs.READS_OUTPUT`), and moves keeps a view hash, so a [flesh] edit that leaves rig and weights alone
  skips moves: study_man limit_share edit 12.1 s (flesh, export, review) against 18.1 s. A flesh rerun
  restores the kept unfleshed mesh (`<mesh>:preflesh`), so a resumed glb is byte-identical to a fresh one.
  On a dressed spec, flesh takes the garments off (`stages.undress`) instead of restarting: Belle 24.3 s
  against 46-47 s, identical to fresh. pipeline_hashes: 15 output flips with drop-controls; pipeline_woman
  dressed_flesh_edit with restart and refusal controls. Open: the hem-bone undress path (tee_man) gives
  garment weights up to 6e-8 off fresh and no fixture covers it; marketplace's Since 0.10.0 omits undress;
  `_preflesh` swaps the whole mesh back after a count/geometry/prefix check, so a bake rerun without a body
  restart could lose new UVs or slots (speculative); a chained strand (study_woman) still reruns moves;
  export and review rerun on every flesh edit (review is now the cost); files built before 0.10.0 rerun
  moves once; a [moves] edit on a dressed spec restarts from body; the game's `build_belle.py` docstring
  still says a dressed flesh edit restarts. Notebook:
  [notebooks/realism-step1/cp-cascade-stop.md](notebooks/realism-step1/cp-cascade-stop.md).
- **Critic checklists shipped with the plugins: done** (branch `critic-checklists-controls`, merged
  2026-09-18; lookdev 0.4.1, animate-anything 0.10.1, wardrobe 0.5.1, follow-through 0.6.2, humanform
  0.10.1, docs only). `references/critic-look.md`, `critic-motion.md`, `critic-fit.md`, `critic-flesh.md`,
  `critic-body.md`; see "How to judge \"realistic\"" for how to use them. Open: the Godot close-shot lacks
  a stipple detector (face_3q, head_side and head_back came in lookdev 0.5.0, and critic-look names them); no
  tool renders flesh jiggle in motion, a posed thigh through a skirt or limb clearance in a pose (listed as
  not answerable).
- **Controls still missing from Step 0: done** (same branch). `limit_influences` fixture with the
  stale-write control (fixed 0.0 lost, stale write 0.311731); `pipeline_hashes` drop-controls for wardrobe
  version, final skin size, spec `[flesh]` and final close-up views. Open: limit_influences is not in
  regress.py DURATIONS; `--quick` treats a .md-only plugin change as a plugin change and runs all its
  fixtures (a docs-only rule belongs in regress.py). Notebook:
  [notebooks/realism-step1/critic-checklists-controls.md](notebooks/realism-step1/critic-checklists-controls.md).

### Step 1 - hair

- **Blender to Godot, and the neck stipple: done** (branch `hair-godot-transfer`, lookdev 0.6.0, humanform
  0.11.0, merged 2026-09-18). The stipple was Godot's default directional soft-shadow filter (soft low), not
  the hair: every lighting preset now sets `sun.soft_shadow_filter_quality` 4 through `LookdevPresets.apply`
  (apply_preset warns when the project setting is lower). The hairline smear was the depth pre-pass blending
  mip-averaged strand alpha plus box mips eroding coverage: `LookdevMaterials.coverage_mips` keeps level 0's
  coverage per mip (read from the source PNG, since BC3 moves alpha) and ramps alpha over 0.5 +- 0.25, asked
  for by the hair preset's alpha extras. Brows and lashes blend instead of scissor (darkest 2% of brow over
  skin: study_man Blender 0.158, Step 0 0.078, now 0.133; study_woman 0.285, 0.154, 0.251).
  `strand_texture` card mode, `hair.material(pixels=)`, humanform's brows and lashes go through lookdev.
  New `lookdev.mjs stipple <png> --region` with three selftest controls (selftest 21). Critic: pass. Open:
  study_man's overcast neck keeps a faint stipple (0.399 -> 0.570; ultra does not clear it; likely overcast's
  20 deg angular distance); the filter is set on every preset and its GPU cost is unmeasured; coverage_mips
  makes 1-2 MB uncompressed runtime textures, load cost unverified, no must-fail control; stipple needs a
  skin `--region` and is not in `regress --godot`; the game's committed glbs are not rebuilt (the ship step
  must rebuild study_man, study_woman and Belle to get the alpha changes); no MSAA/TAA, so alpha to coverage
  is unused; Blender's reddish hairline fringe. Notebook:
  [notebooks/realism-step1/hair-godot-transfer.md](notebooks/realism-step1/hair-godot-transfer.md).
- **The man's hairline, lashes and brow shape: done** (branch `hair-hairline-lashes`, humanform 0.12.0,
  lookdev 0.7.0, character-pipeline 0.12.0, merged 2026-09-18). lookdev's strand texture has `edge_*` settings
  (off by default, own random stream): short, thin, leaning edge hairs in front of the dense start; short_crop
  uses 900 per tile and `root_power` 0.15. humanform's `line_u_m` (off by default, 3 cm for short_crop) carries U
  along the hairline so V crosses it squarely at the temples and sideburns (median U-V angle near the line
  26 -> 61 deg on study_man). Denser lashes (upper-lid root coverage 0.736 against Step 0's 0.513), a brief/spec
  `brow_shape` field (natural is the default and unchanged; arched lifts the outer third 2.05 mm), and Belle has
  brows and lashes (`belle.toml`). New hair_presets checks with must-fail controls: fringe ratio (0.161 vs 0.050,
  floor 0.1), line-U angle (57.7 vs 35.5, floor 50), edge wobble, lash root coverage, brow shapes. Critic: pass,
  after one fix round. Open: the short cap is still a smooth, dark, slicked shell at 1 m (needs volume and colour
  variation); short_crop's `uv_tangent_turn` over 35 deg rose 83 -> 246; crossing hairs just above the ear; the
  pale temple line is unremeasured; the fringe floor does not catch losing the edge hairs alone (0.107; the
  golden's hash does) and the edge_wobble control is tautological; the "Since" sentences omit `edge_*` and
  `line_u_m`; humanform SKILL.md's brow/lash colour factors are stale; the game's glbs are not rebuilt (the ship
  step must rebuild study_man, study_woman and Belle). Notebook:
  [notebooks/realism-step1/hair-hairline-lashes.md](notebooks/realism-step1/hair-hairline-lashes.md).
- **Motion: frame-rate independent strands: done** (branch `strand-rate-independence`, follow-through 0.6.3,
  merged 2026-09-18). strand_modifier.gd simulates each strand against the body's motion low-passed at 10 Hz,
  with `SMOOTH_GAIN` 1.1 (property `smooth_gain`; 1 is off) restoring the run's swing: study_woman's ponytail
  swings 44.5-46.3 deg at 30/60/120/240 fps, spread 1.037 start / 1.041 settled (limit 1.25 unchanged;
  1.053/1.040 at 25/33/47/75/165). verify_strands checks a starting and a settled window and reports
  `peak_tip_deg`; `regress --godot` runs it on pipeline_ponytail with two controls that must print their FAIL
  lines (`legacy_integration=true`, 1.31/1.39; `mod=smooth_hz:0`, 1.28 on the start only). figure_study's
  selftest reads the free tip swing (51.4 deg) with a strands-off control. Critic: pass, after two fix rounds.
  Open: SMOOTH_GAIN sits on a steep curve (1.15 -> 56 deg, 1.2 -> 70-82 deg on the bone limits) and
  verify_strands has no swing ceiling, so a hotter preset could whirl unnoticed (retune the ponytail preset's
  response instead); the smooth_hz:0 control's margin is thin and the legacy control's is about zero at odd
  rates; jiggle_modifier.gd likely has the same rate dependence; under 30 fps is not covered; kick_peak_deg
  sits on the 60 deg bone limit; `long_loose` is still not built. The ship step installs follow-through 0.6.3
  (the game carries the addon). Notebook:
  [notebooks/realism-step1/strand-rate-independence.md](notebooks/realism-step1/strand-rate-independence.md).
- **Blender to Godot first.** The critic found fine strands at the hairline in Blender and a smeared shell in
  Godot, and brows darker and harder in Godot than in Blender. Find where it is lost (strand texture
  resolution or mips, alpha mode, lookdev's hair material, card export) before touching the hair layer.
- **The man's hairline.** Replace the hard cut and spiky fringe with a feathered hairline that reads as
  hair at 1 m. The hair layer already has feathering; `short_crop` is its weakest preset.
- **The neck stipple (06 rank 14).** Hair shells should cast a scissor shadow, not a dithered
  depth-pre-pass one. Also: a card mode in `hair.strand_texture` with no opaque middle, and alpha to
  coverage or a mip bias for cards.
- **Lashes and brows.** Lashes that read at 1 m from the front. A brief field for brow shape.
- **Motion.** `verify_strands` fails its cross-rate spread on the ponytail (1.26 against 1.25; the limit
  was not widened): make the strand spring frame-rate independent and add it to `regress --godot`
  (06 rank 13). `long_loose` is still rigid: it needs a sheet of chains or a route to cloth.

**Step 0.5 and Step 1 status: done and shipped (2026-09-18).** All eight branches merged; `~/.claude/skills`
and the game's addons match `main`. The ship step rebuilt study_man, study_woman and Belle in the game at final
quality, and they pass `--import`, the figure_study, belle_demo and people_demo selftests, verify_moves (3
manifests) and verify_flesh (full, walk, run, jump on both figures). `regress.py --twice --jobs 4 --godot` on
`main`, run against a full scratch copy of the game (the permission classifier refuses it on the real project,
which it stages files into): `REGRESS DONE exit=0, 23 fixtures ok`, no change, 21 min. Godot close-shot sheets at
1 m (clear_midday, overcast) of all three are listed under "Where the figures are". No independent look critic
was run by the ship step. Still open from Step 1: the short cap's volume and colour variation, `long_loose`,
and each branch's open items above; a demo selftest rewrites `assets/wardrobe/nora.walk.json` with tabs
(whitespace only; restored). Notebook: [notebooks/realism-step1/ship.md](notebooks/realism-step1/ship.md).

### Step 2 - skin

- **Detail that survives distance.** Pores exist as a Godot detail normal on UV2 but vanish past about
  1 m. Add mid-frequency variation: tone and redness by region (knees, elbows, knuckles, face, the
  soles), and a roughness map by region so the forehead and lips stop reading as gloss.
- **Specular under overcast:** hard, mirror-like forehead band and nose and lip patches (the baseline's
  item 4); check the roughness range the bake writes and lookdev's skin preset under a soft sky.
- **Overcast exposure:** study_man drops to a muddy brown under overcast, study_woman goes grey.
- **Small defects:** thin orange lines at the finger-web creases and thumb web under clear_midday, pale
  lines at the fingertips under overcast.
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
- Pick done-when and look questions from the shipped banks, by id: lookdev
  `references/critic-look.md` (LOOK-*), animate-anything `references/critic-motion.md` (MOT-*), wardrobe
  `references/critic-fit.md` (FIT-*), follow-through `references/critic-flesh.md` (FLESH-*), humanform
  `references/critic-body.md` (BODY-*). Each question names the tile, view or verifier that answers it; a
  question the banks lack is added to the bank in the same round.

---

## Running the next session

**Use the `plugin-round` workflow** (`.claude/workflows/plugin-round.js`; run from this repo by name, or from
another by `scriptPath`). Give it the step and its branches as args:

```
{ "step": "Step 1 - hair",
  "branches": [ { "key": "...", "title": "...", "task": "...", "done": "1. ...?\n2. ...?", "after": "<key, optional>" } ],
  "ship": { "rebuild": ["study_man", "study_woman"], "belle": false },
  "look": "1. ...?\n2. ...?",
  "benchmark": <the contents of .claude/workflows/benchmark-briefs.json> }
```

The Workflow tool only runs a script it can read from the session's working directory or one it returned
itself, so from another project copy `plugin-round.js` into the session scratchpad and pass that path.

From the Step 1 round (8 branches; first attempt 45 agents with 1 branch built, second attempt 29 agents,
3 h 24 min, 4.4 M subagent tokens, every branch merged, 5 of 7 on the first critic pass):

- **A chat message sent while a round runs reaches its agents.** In the first Step 1 attempt a question about
  previews was relayed to every agent as the user's request, and 6 of 7 builders declined to build; their
  critics and fixers repeated it for two more rounds. The script now states the round's task as the user's
  request and names the last chat message as answered, and a builder with no commits ends its branch at once.
  Keep questions to the orchestrator separate from a running round's task.
- **The permission classifier refuses some ship-step actions:** `regress --godot` on the real game project
  and a Monitor tail of the regress log. The ship step ran regress on a full scratch copy of the game with the
  rebuilt assets instead, which is what the round's rules ask anyway.

It builds each branch in its own worktrees, has an independent critic answer the branch's `done` questions,
fixes at most twice, merges one branch at a time, then installs, rebuilds the real figures, runs the round's
one full regress and has an independent look critic judge them in Godot. What it encodes, from the Step 0
round (4 branches, 14 agents, 3 h 14 min, 2.4 M subagent tokens):

- **One full regress per round, not three per branch.** In Step 0 the builder, the critic and the merge step
  each ran a full `--twice`: a critic spent 23 of its 27 min on one. Now builders and merges run `--quick`
  (about 3.5 min), critics read the builder's regress log and run only the targeted checks and controls, and
  the ship step runs the one `--twice --jobs 4 --godot` (about 14 min).
- **Branches of about 30 min.** cp-resume-hashes (two ranks plus game changes) took 65 min against 25 for the
  others and set the critical path. Split large items; a branch that is "two things" is two branches.
- **Agree the seam, don't queue on the merge.** cp-close-look-set waited about 110 min for cp-resume-hashes to
  merge because both touched `stages.py`/`quality.py`. Write the shared interface (here, the review stage's
  quality keys) into both tasks and build in parallel; `after` is the fallback.
- **The merge gate is pass AND mergeable.** Step 0's gate was "pass or mergeable", so a branch the critic
  held (Belle's dressed flesh edit refused) went to the merge step, which fixed it itself - correctly, but
  unreviewed. Now a merge step that changes code stops, a second critic reviews the fix, then it merges.
- **Effort by kind:** builders, fixers and critics high; merge and ship medium.
- **Merge one branch at a time, as each finishes.** No wave waits for its slowest member. After each
  merge, branches still in flight merge `main` in before their review starts.
- **Regress was the critical path** before `--quick` (11-23 min per merge, about 7 hours in the round before
  Step 0 against about 25 min of character building).
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

- **The rest of 06's ranked list:** stage numbers never lost (4), stored body
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

- **Building the project's characters without touching its assets.** From the plugins checkout you want to
  test: `python tools/scratch_project.py <scratch dir> [--who study_man,study_woman,belle]`. It copies the specs,
  build scripts, addons (the checkout's), the chosen characters' blends and exports and the humanform library,
  writes `env.sh`/`env.ps1`, runs `--headless --import` (fails on an ERROR line) and prints the build command:
  `bash <dir>/build.sh study_man` (about 50 s from a stale blend, 0.3 s when nothing changed). Specs' `[export]
  blend` are relative (character-pipeline 0.11.0): under `BLEND_DIR`, else the project; a build refuses to save
  outside both unless `save_outside=1`. Do not run it with a scratch `env.sh` still sourced (its `BLEND_DIR`
  wins). `who=tomas` still needs his source blend opened.
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
- The real blends in `C:/Users/pauli/Code/Blender/` are current; the figure study's are
  `figure_study_man.blend` and `figure_study_woman.blend`, and they now carry character-pipeline's stage
  records, so a rebuild resumes from them. The ship step backed up the pre-rebuild copies (and
  `belle_realistic.blend`) to `%TEMP%/rw/ship/backup/`, a scratch folder: do not count on it.
- `grungist-creek/tomas_demo.tscn` is gone (nothing referred to it; its stale editor-state files were
  removed), and `--import` is clean.
- This repo is public, and `plugins/humanform/data/` (ANSUR II public CSVs and the seed contact sheets) is
  published with it, a deliberate choice recorded here in case it is revisited.
