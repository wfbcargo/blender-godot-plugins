# Ship - 07 motion that reads as alive (the head rung and L4 variability)

Round `motion-alive`. Merged into `main` this round: `motion-head-rung` (rig-anything 0.32.0),
`motion-asymmetry` (0.33.0, character-pipeline 0.16.0) and `motion-jitter` (0.34.0-0.36.0).
Working in the **main checkouts**, nobody else running. Started 2026-09-20 21:15 CDT.

## 1. Install and addon sync

`python tools/install.py --all`:

    animate-anything 0.10.1: up to date
    character-pipeline 0.15.0 -> 0.16.0: 4 changed, 0 added, 0 removed
    follow-through 0.10.0: up to date
    godot-lsp 0.1.0: up to date
    humanform 0.17.0: up to date
    lookdev 0.12.0: up to date
    rig-anything 0.31.0 -> 0.36.0: 6 changed, 4 added, 0 removed
    wardrobe 0.5.2: up to date

The game's four addons (`follow_through`, `lookdev`, `rig_anything`, `wardrobe`) were **already in
sync**: `diff -r --strip-trailing-cr -x '*.uid'` against each plugin's `godot/addons/<name>` is empty
for all four. The merge commits on `master` (`0856750`..`acdd442`) had carried every rig_anything
change across as it landed, so there was nothing to copy.

## 2. The rebuild, and the one spec change that goes with it

Blends backed up to `%TEMP%/rw/ship/backup/` first (`figure_study_man.blend`,
`figure_study_woman.blend`, `belle_realistic.blend`).

NEXT.md's L4 item ends "no real game character carries `[variability]` yet and no motion critic has
looked at an asymmetric or jittered walk in Godot - the ship step should put `asymmetry = 0.35` on
the cast, rebuild, and have one look." So the three rebuilt specs get

    [variability]
    asymmetry = 0.35

and nothing else: `jitter_phase`/`jitter_amp` stay 0, because the runtime half is off by default and
Godot's JSON parser still truncates the manifest's 19-digit seed (NEXT.md, open). Asymmetry is baked
in Blender, so the truncated seed does not reach it.

Rebuilt from body at `quality = "final"` (`character-pipeline` `build.py`, `BLEND_DIR=C:/Users/pauli/Code/Blender`),
21:16-21:19 CDT:

| id | wall | stages |
|---|---|---|
| study_man | 56 s (53.6 s build) | body 7.0, muscle 0.7, bake 8.0, hair 1.4, flesh 1.0, moves 20.6, export 5.5, review 9.0 |
| study_woman | 56 s (53.7 s) | body 5.2, muscle 0.7, bake 9.8, hair 0.8, flesh 0.9, moves 21.5, strand 0.2, export 5.8, review 8.5 |
| belle | 55 s (52.7 s) | body 5.9, bake 8.8, hair 0.7, flesh 0.9, moves 17.5, garments 3.9, export 6.0, review 8.8 |

Every stage ran (the 0.32.0-0.36.0 bumps invalidate every stage hash, as NEXT.md warns), `skipped: []`,
no review false alarm on any of the three. `study_man.moves.json` now carries

    "variability": {"seed": 5713945625152501342, "asymmetry": 0.35, "jitter_phase": 0.0, "jitter_amp": 0.0}

- the seed drawn from the id, and the 19 digits that Godot's JSON parser truncates. Harmless here
because nothing at runtime reads it while `jitter_*` are 0.

## 3. Godot: import, the three selftests, verify_moves and verify_flesh

`--headless --import`: exit 0, **0 ERROR lines**. Then (21:19-21:22):

    figure_study   FIGURE_STUDY SELFTEST PASSED (0 failures)
    belle_demo     BELLE_SELFTEST PASSED
    people_demo    PEOPLE SELFTEST PASSED

    verify_moves  study_man    MOVES VERIFY PASSED
    verify_moves  study_woman  MOVES VERIFY PASSED
    verify_moves  belle        MOVES VERIFY PASSED

    verify_flesh (course=walk|run|jump, require=within_body), 9 runs, all exit 0:
      study_man    walk/run/jump  FT_SUMMARY 1 fleshed bodies, PASSED
      study_woman  walk/run/jump  FT_SUMMARY 1 fleshed bodies, PASSED
      belle        walk/run/jump  FT_SUMMARY 1 fleshed bodies, PASSED

So `asymmetry = 0.35` on three real game characters costs nothing that any existing check can see:
the gait ladder still verifies (no foot skate, no "planted at a different speed" refusal) and the
flesh stays inside the body on every course.

## 4. The blocker, diagnosed before the regress came back

NEXT.md hands the ship step one red row on `main` and no owner: `verify_strands pipeline_ponytail`,
a strand 0.0060 / 0.0065 / 0.0067 / 0.0067 m into the head at 30 / 60 / 120 / 240 fps against a bound
of 0.005, `swing_spread=1.050`. It read 0.0038-0.0039 and passed before `motion-head-rung` and
`motion-asymmetry` merged.

**The convergence with frame rate is the clue.** A collision miss caused by stepping gets *worse*
as the step gets coarser; this one is 0.0060 at 30 fps and 0.0067 at 240, settling on a value. That
is not a stepping artefact - it is a steady-state geometric miss: the strand is resting **on its
collider**, and the skin at that spot is outside the collider.

`follow_through.strand.colliders` makes the head "an ellipsoid on its bone's axes: centred on the
middle of its skin's bounds in that frame, **half those bounds its radii**". An ellipsoid with the
half-bounds for radii is *inscribed* in the skin's bounding box: it touches the skin only at the six
extreme points and lies inside it everywhere the head is not an ellipsoid - most of all on the
diagonals. `verify_strands` measures penetration against the **skin**, not the collider, so every
millimetre of that gap is penetration the moment a strand rests there.

Probed on the rebuilt `figure_study_woman.blend` (9431 head-skin vertices, ellipsoid radii
0.0881 / 0.1189 / 0.1206 m), with `t = |d/r|` the ellipsoid's own radial coordinate (t = 1 is its
surface):

    t:  p50 0.8593   p90 0.9856   p95 1.0158   p99 1.0543   max 1.1379
    outside the collider: 696 of 9431 vertices (7.4%), worst 0.0166 m

and the worst points sit at `u = (0.00, -0.85, 0.76)` in the bone's own axes - down and back, on the
diagonal between them. **That is the nape**, which is exactly where a ponytail hangs. The block's
`collision_margin_m` is 0.004, so the margin covers 4 mm of a gap that reaches 16.6.

So the mechanism is: the head collider does not enclose the head. The head rung did not cause it -
it moved the head enough for the tail to ride that part of the skull, where the collider has always
been up to 16 mm too small.

## 5. The round's one full regress

`python tools/regress.py --twice --jobs 4 --godot C:/Users/pauli/Code/GoDot/grungist-creek`
from the main checkout, started 21:22:40 CDT. **All 23 Blender fixtures `ok`, both builds agreeing,
no golden moved** (one standing WARNING, `mpfb_woman_curvy`'s volatile `export.file` key). The
Blender half finished 21:36.

The Godot half came back at 21:52 with **exactly one red row**, and it is the one NEXT.md named:

    FAILED  verify_strands pipeline_ponytail: ... swing_spread=1.050 start_spread=1.048 FAILED
              30 fps: swing 109.08 deg settled (mean 57.75), 109.07 starting, head 0.006 m, rest drift 0.034
              60 fps: swing 107.74 ... head 0.0065   120 fps: 103.87 ... 0.0067   240 fps: 103.87 ... 0.0067
              FAIL 30/60/120/240 fps: running, a strand went 0.0060 / 0.0065 / 0.0067 / 0.0067 m into the head

    1 fixture(s) changed or failed: verify_strands pipeline_ponytail
    REGRESS DONE exit=1, 23 fixtures ok

Everything else green, including all of them: `verify_moves` (12 manifests), five `verify_wardrobe`
rows and their three must-fail controls, `verify_flesh pipeline_woman` full/walk/run and its
`limits=2x` control, the jiggle spring selftest and its control, both `verify_strands` controls
(each still failing on every line it must), **eleven `verify_jitter` rows** - the shipped run at
alpha phase 0.823 / amp 0.805, stride cv 0.0259 on against 0.000000 off, drift 0.0313 of 0.2160
cycles over 160 s, 3.30 + 2.52 us per character per frame - with all nine of its must-fail controls
failing, close-shot, edges, eyes and `lookdev selftest` (34/34 controls failed as they must).

## 6. The blocker: one attempt, ruled out, and where it actually is

**Attempt (follow-through 0.11.0, reverted).** Grew the head ellipsoid until it enclosed the skin
(`fit` = the largest `|d/r|` over the head skin, reported in the spec, the strand report and
`summarize`). It did exactly what it claimed - the fixture's head collider went `radius_m`
0.1191 -> 0.1355 with `fit` 1.1375 - and the run's settled swing moved 109.08 -> 113.91 deg at
30 fps. **The penetration did not move by one digit**: 0.0060 / 0.0065 / 0.0067 / 0.0067 m, the same
four numbers. So the hypothesis is dead, and being dead this precisely is itself the evidence.

**Why it cannot work, read back out of `strand_modifier.gd`.** Each bone's collision limit is
`minf(1.0, k_rest - eps)` - the collider's surface *or the gap the bone had at rest, whichever is
tighter*, "so nothing is pushed out at rest and nothing goes deeper than it started". The strand's
root is grown into the scalp, so its samples are inside the ellipsoid at rest and their limit is
their own rest scale. **Growing the ellipsoid cannot change a limit that is already pinned to rest.**

**Where the penetration is.** Run on the game's own rebuilt `study_woman` (she has the ponytail;
`verify_strands.gd`, 60 fps), which **also fails** - `run_head_penetration_m` 0.0053, so this is a
live defect on a shipped character and not only a fixture's:

    run_penetration_at [0.003, 1.58, -0.059, "ft_strand_StudyWoman_hair_strand_00", -0.001]
    run_collision_hits 360   run_limit_hits 643   run_peak_bone_angle_deg 53.94

The vertex that goes in belongs to `..._00`, the **root** bone, and it sat 0.001 m *outside* the skin
at rest. The root is at its 60 deg limit 643 times in the run. The collision solver limits four
sample points *along each bone's centreline*, grown by the strand's own radius; the tie's mesh
vertices swing wider than that centreline, and the measurement is against the skin. So the defect is
the root bone's swing carrying its skinned vertices through a scalp its centreline never enters -
not the collider's size.

**Left for its own branch, not taken here.** Fixing it means changing either the root's angular
limit or how a bone's skinned envelope (not its centreline) is kept out, both of which move
`tests/golden/pipeline_ponytail.json` and `strand_ponytail.json` and need their own `--godot` run and
their own control. That is a reviewed commit on a branch, not something for a ship step at the end of
its budget, so the working tree was put back to `main` exactly (`git checkout --` on
`plugins/follow-through/` and `.claude-plugin/marketplace.json`, `install.py --all` back to
follow-through 0.10.0) and the round ships with the row red and named.

## 7. Godot look renders

`lookdev close-shot --views face,face_3q,eyes,head_side,hands,full --presets clear_midday,overcast
--pair-blender <the build's Blender close set>` on the real project, into
`%TEMP%/rw/ship/look/<id>/` (65 files each, `sheet.png` the sheet):

| id | exit | note |
|---|---|---|
| study_man | 0 | clean - last round every run exited 1 on overcast `full` FLOOR_STRIPES; that tile passes now |
| study_woman | 0 | clean |
| belle | 1 | `FAIL TONE_SHIFT: skin saturation moves -21.0% from clear_midday to overcast (max 15%)` |

Belle's is a lookdev-preset row, not a motion one, and it is the only failing tile of the three
sheets. `head_back`, `bust`, `crotch`, `knees`, `feet` and the foot views exist in the Blender close
set and have no Godot view, so those tiles are unpaired (unchanged, and a close-shot gap already on
the list).
