# The regression harness

Until now a change to shared code was verified on whichever character its author happened to be
building. The MPFB crouch fix was "tested on Belle only" until someone thought to compare four
other rigs by hand. This is the thing that stops that: one command that rebuilds a set of bodies
from nothing and says which numbers moved.

```
python tools/regress.py                       # every fixture, against tests/golden/
python tools/regress.py --only rabbit         # one of them
python tools/regress.py --jobs 2              # two Blenders at once
python tools/regress.py --plugins <checkout>  # run the fixtures against another checkout
python tools/regress.py --update              # rewrite the goldens, then review the diff
python tools/regress.py --twice --jobs 2      # build each fixture twice; the builds must agree
python tools/regress.py --godot <project>     # then play the exports in Godot's verifiers
python tools/regress.py --quick --jobs 2      # only the fixtures the branch's changes reach
python tools/regress.py --quick --dry-run     # what --quick would run and skip, and why
python tools/test_tools.py                    # regress's and bump.py's own checks, no Blender
```

Every run ends with exactly one line, `REGRESS DONE exit=N, K fixtures ok`: wait on that line when a run
is in the background. The longest fixtures start first (`DURATIONS` in `regress.py`, measured; a fixture
missing from it starts before all of them), and each result is printed and flushed the moment its
builds are in, so a slow fixture no longer holds back the ones after it. A `CHANGED` result shows its
first 40 keys; the full diff of every fixture goes to a file whose path the run prints (`--diff FILE`
to choose it, else the `--keep` folder or `<temp>/regress-diffs/`). A pipeline fixture's exported
manifests record how long each character-pipeline stage took, and the result line is followed by
them, so a slow run explains itself. `--keep` warns when its folder plus the deepest fixture output
comes within 20 characters of Windows' 260-character MAX_PATH.

## `--quick`

`--quick` lists what changed against `main` - `git diff --name-only main...HEAD`, plus staged,
unstaged and untracked files (`--base` for another ref, `--changed PATH...` to name them yourself) -
and runs only the fixtures that change reaches:

- `plugins/<name>/...`: every fixture that uses that plugin, directly (`H.use`, or any `*_SCRIPTS` it
  reads) or through another plugin's imports, scanned from the plugin sources at run time (humanform
  imports wardrobe and lookdev, so a wardrobe change also runs `mpfb_woman_curvy`). A plugin no
  fixture reaches (godot-lsp, animate-anything) runs nothing.
- `tests/fixtures/<name>.py` or `tests/golden/<name>.json`: that fixture. A helper
  `tests/fixtures/_<x>.py`: every fixture that names it, so `_harness.py` runs all of them and
  `_export_only.py` runs `rabbit`.
- `tools/`: everything. Documentation (`*.md`, `docs/`) and `.claude-plugin/`: nothing. Anything
  else: everything, since it is not known what reads it.

It prints each changed path with what it selected, then every fixture it will run and why and every
one it skips and why. `--quick` is for iterating. The suite is optional and never a merge gate (CLAUDE.md): a fresh build of
the affected characters and the game's demo selftests are what prove a change.

## `--update`

`--update` rewrites the goldens whose report moved. A golden whose fresh report is within tolerance of
it is left as it was (`ok ... (golden within tolerance, kept)`), so re-recording after a change that
moved three fixtures touches three files, not twenty with rounding noise and new version stamps.

## Bumping a version: `tools/bump.py`

```
python tools/bump.py wardrobe 0.6.0 "skirts fold with the thighs."
```

edits `plugins/<plugin>/.claude-plugin/plugin.json`'s `version`, and that plugin's `version` and
description in `.claude-plugin/marketplace.json`, appending "Since 0.6.0 skirts fold with the thighs."
It edits text, keeping line endings and layout, and re-parses both files to prove nothing else moved.
It refuses (and writes nothing) on a version that is not `x.y.z` or not above the current one, an
unknown plugin, versions that already disagree between the two files, or a description that already
has that version's sentence. Goldens record the versions that built them (`plugins`), but regress
never compares that stamp and there is no restamp mechanism, so bump.py leaves `tests/golden` alone.

A change is not by itself a failure — a fix moves numbers. The point is that the move is **seen**,
on every fixture rather than on one character, and that accepting it is a reviewed commit to
`tests/golden/`.

## Fixtures

Each is a script Blender runs in its own process, building from nothing — no `.blend`, no stored
asset — and writing a report of what it got. There are twenty-four of them (the table lists every one), and a `--twice --jobs 2` run
takes about half an hour; the rabbit and the cricket are the biggest single builds (over two minutes
each alone), because a voxel remesh is slow, and since rig-anything 0.22.0 every export renders a
review sheet as well (4-12 s a character).

| Fixture | Builds | Exercises |
|---|---|---|
| `mpfb_woman_curvy` | a woman from a seeded brief: ANSUR fit through MPFB2, baked, Idle/Walk/Run/Crouch/CrouchWalk, exported | humanform's fit and check, `bake_for_game`, `move_set`, the crouch on an MPFB rig, the export re-check |
| `rabbit` | `hopper_samples.rabbit`, detected, rigged, skinned, hopped, exported | leg detection against the sample's known joints, `hoppers.build`/`skin`, `hop.move_set`, `export_creature` |
| `flesh_figure` | follow-through's `Figure` and `Bloater`, rigged, walked, fleshed, exported | `fit_basic_human`, bind coverage, `flesh.prepare` region placement (end rings fitted from wall vertices), the glTF read back |
| `dressed_figure` | a shirt cut onto the fleshed `Figure`, and that body exported walking | `tailor`/`fit`/`hem`/`cover`, the flesh-before-garments order, and (with `--godot`) the shirt worn in Godot |
| `dressed_presets` | the fleshed `Figure` dressed through `wardrobe.dress` in `sports_top` and `shorts_mid_thigh`, body exported | wardrobe's garment presets reproduce the hand calls, two garments worn together in Godot |
| `pipeline_woman` | a curvy MPFB woman from a TOML spec with flesh and two presets, through every stage; rerun, a refused out-of-order stage, and export resumed in a second Blender | character-pipeline's stages, records, refusals and fresh-session resume; `height_m.stand` taken from the stored Idle clip (`idle_standing_height_m`), a spec naming `export.height` refused (`height_field`), the body's `body_stature`; a `[flesh]` edit on the dressed file taking the garments off and skipping moves (`dressed_flesh_edit`; controls: without the undress it restarts from body, and without either it refuses); the spec-built character in Godot |
| `cricket` | `hopper_samples.cricket`, detected, rigged, skinned, walked, jumped, exported | six-leg detection against the sample's known joints, the orthopteran branch of `hop.move_set` (Idle, Walk, JumpLaunch/Air/Land), `export_creature`'s refusal of a failed clip |
| `starfish` | `radial_samples.starfish`, detected as `asteroid`, rigged, skinned, crawled, exported | `radial.detect`'s hub and arms, `radial.build`'s one bone count per appendage kind (all five arms 4 bones), `radial.skin`'s coverage read back off the mesh (`vertices_unweighted`, cross-checked by the fixture's own count), `radial_moves` Crawl and Idle, the `radial` manifest |
| `rigify_human` | follow-through's `Figure`, unfleshed, given every biped move, exported | `fit_basic_human` with Rigify off, `move_set`'s ten default roles on a rig with no ground root, the export re-check. The three slides fail their floor checks and are dropped from the export with the reasons in the golden. `verify.arm_swing` over carry angles from real clips (`ARM_SWING_CASES`: a walk through hanging passes, the pre-fix Walter walk carried in front fails), and each clip's `arm_pose` read back off the written `.moves.json` (`arm_pose_on_disk`, also recorded by every other export fixture) |
| `quadruped` | `quadruped_samples.dog`, fitted, bound, given Idle/Walk/Trot/Run/Crouch, exported | four ground contacts, `fit_basic_quadruped` scored against the sample's known joints, `skin.bind`, `move_set` on four legs, the export re-check |
| `mixamo_names` | the Rigify `Figure`, fitted and bound, then every bone renamed to `mixamorig:` | `bodymap` roles come from structure: the same root, pelvis, chest, head, hands, feet and controls under Mixamo names (`same`) |
| `review_sheet` | a box on a one-bone rig with four clips (`Static`, `Tilt`, `Travel`, `Dip`), rendered as review sheets | rig-anything's `review`: `distinct_cells` on identical and on moving poses, `edge_cells` counting a body against any edge, and `bands_px` growing above and below the cell from the evaluated poses — `Dip` sinks 0.35 m through the floor and rises 0.9 m above it and is still wholly in frame |
| `traced_detail` | the sample `Figure` embossed with a 12 mm bump on each breast and buttock, dressed six ways | wardrobe's `fit.relief` / `fit.detail`: a `detail_limit` that passes for a reason, one that **fails**, one that goes unmeasured and therefore fails, and `cover.drawn_over_cloth` + `fit.lift_over` lifting cloth back over skin pressed through it |
| `dressed_skirts` | `skirt_knee`, `skirt_mini` and `dress_sleeveless` on the fleshed `Figure`, and `skirt_knee` again with `soft=True` | wardrobe's `tailor.skirt` / `tailor.dress` (a tube built round the body, not cut from it): rings, girths, weight shares, hem bones hinged above the hip joints with thigh colliders, covered-skin counts, the export, and the follow-through cloth spec of the soft one |
| `hair_presets` | a spec-built MPFB woman given each of `short_crop`, `bob`, `bun`, `ponytail`, `long_loose` | humanform's `hair`: the cap's feathered boundary (thickness and texture V), part sizes and skin clearance, the follow-through strand contract, lookdev's hair material read back out of the glb (MASK, textures, extras), the pipeline's hair stage — and its refusal to join a second hair layer onto a body that already has one |
| `strand_ponytail` | a tapering tube grown from the back of the `Figure`'s head, chained, exported beside the walking body | follow-through's `strand`: `classify` routing to `spring_bones`, the chain's per-bone frequencies and colliders, a centreline derived from the mesh against the given one, the glb read back — and a degenerate centreline returning an error that leaves the object's bones, spec and vertex groups alone |
| `pipeline_ponytail` | a woman from a TOML spec with `[hair] preset = "ponytail"` through every stage, Run included | character-pipeline's `strand` stage between moves and garments: the tail left loose by the hair stage, `follow_through.strand.prepare` hanging its chain on the head bone, `<id>_hair.glb` and the manifest's `strands`, both glbs read back; export refused before the strand stage and the strand stage refused before the moves. The swing itself is Godot's (`verify_strands.gd`, run by hand - see follow-through's strands reference) |
| `muscle_definition` | the definition delta authored from nothing on MPFB's default male, weighted onto Dante, a soft body and Freya, as geometry and as a baked map | humanform's `sdf` / `delta` / `muscle`: per-group and composite `spike_um` (the guard runs on the sum the mesh carries), `muscle.weights` falling away with body fat, humancheck before and after, and lookdev's `detail.bake_normal_from_high` on the baked mesh with the eyes joined in |
| `pipeline_muscle` | a lean muscular man (Dante's brief, no forced muscle macro) from a TOML spec with `[muscle] output = "geometry"`, `[hair] preset = "bun"` and `[build] quality = "draft"`, then edited as a person would: hair to `short_crop`, muscle to `"normal"`, muscle dropped | character-pipeline's `muscle` stage (per-group weights, body fat, the composite `spike_um`, the baked `hfd:muscle` keys), the `build` record in the report, the manifest and the .blend, a whole build restarting from body when `[hair]` or `[muscle]` changes (one hair layer: the vertex count equals a fresh build's), the normal-map bake and its removal, and the quality table |
| `pipeline_hashes` | nothing: `runner.plan` on four small specs against copies of the plugins, each copy edited one file at a time | every file a character-pipeline stage reads is in its input hash: each flip moves its stage first and nothing before it, each unrelated edit moves nothing, and each flip has a drop-control (the input left out of the hash, the flip must go unseen) - including the plugin version, the final skin map size, the final close-up views and a spec `[flesh]` edit, which the fixture leaves out itself (`_left_out`). `PIPELINE_HASHES_DROP=<stage>:<label>` must fail it. Then what moves reads of flesh's output (`inputs.outputs`, `runner.view_hash`) on a small rig and skinned cube: 15 flips (bones, tags, pose constraints, a jiggle bone's rotation mode, the rig's place, a second bound mesh, geometry, a weight, a group, a modifier, the follow-through route, a wardrobe mark, a material, a shape key) each move their labels and moves' view, each with a drop-control, and 4 unrelated edits (a swing limit, a body bone's rotation mode, a pose, an action) move nothing; `PIPELINE_HASHES_DROP=flesh:output:<label>` must fail it |
| `pipeline_paths` | one draft body (`to_stage="body"`) from a spec with a relative `[export] blend`, the spec copied byte for byte into a second project, then specs whose blend leaves the project | specs safe to copy (06 rank 2, character-pipeline 0.11.0): each build saves only under its own project (every .blend listed after each build), under `$BLEND_DIR` when set, a copy plans the same stage hashes (control: an absolute blend moves export); an absolute, a `../` and a prefix-sibling blend are refused before any stage runs, each with a `save_outside=True` control that saves there. `PIPELINE_PATHS_NO_GUARD=1` must fail it |
| `limit_influences` | 64 loose vertices on an eight-bone armature with one to eight bone weights each, in varied group order, beside non-bone groups | follow-through's `flesh.limit_influences` (0.6.1): at most four influences, the four strongest kept, each vertex's total bone weight kept (`max_total_lost`, the free value), non-bone groups and vertices with four or fewer untouched. Its control, the pre-0.6.1 stale-element write, must lose weight (0.31) |
| `skin_detail` | a seeded MPFB human with a deep skin tone, exported unbaked, baked with lookdev unavailable, and baked for real at 512 px | humanform's `look.skin`: the flat fallback material and its `baseColorFactor` in the glb, no `COLOR_n`, and the baked maps (albedo mean held to the tone, lips and areolae darker and redder, palms and soles paler, the embedded map the same pixels); regional contrast (humanform 0.14.0): each floored region's CIELAB dE, dL and red/green against plain skin must clear `skin.CONTRAST_FLOOR` (`contrast_ok`), and the T-zone's and lips' baked roughness is higher than 0.12.0's. Its control, a copy of the human marked and baked with `HF_SKIN_LEGACY_REGIONS=1`, must fail the floor (`control_legacy`) |
| `asym_meter` | follow-through's `Figure` given Idle/Walk/Run three times - `[variability] asymmetry = 0.35` on an id whose draw is large on every channel, 0, and 0.35 with `RA_ASYM_MIRROR=1` - each exported as its own character | `variability.measure` per side on Walk and Run (arm swing, step length, stride, shoulder dip, arm lag, stance offset), a side-swap measurement (the body map's `lat` negated), and the verdicts Godot's `verify_asymmetry.gd` must reproduce: asymmetric True at 0.35 and **False at 0 and for the mirror** (the controls), stride even everywhere, the stance offset moved against 0's at 0.35 and not for the mirror (rig-anything 0.38.0) |

## In the engine: `--godot <project>`

A glb that Blender wrote correctly can still play wrongly in Godot. `--godot` takes each fixture that
built, copies its `.glb` and `.moves.json` files into `<project>/_regress/<fixture>/`, imports them,
and runs the project's copies of the verifiers:

- **`verify_asymmetry.gd`** for the fixtures in `GODOT_ASYM` (`asym_meter`): each export measured left
  against right off the playing skeleton and held against the fixture's own `variability.measure` numbers
  for the same clips, at the clip's keys (a second copy imported at its own frame rate with the keyframe
  optimizer off) within `ASYM_TOL`, and as the game imports it (verdicts only). The asymmetry-0 and mirror
  builds must fail "is asymmetric" on every clip and nothing else, and read under the floor on each of its
  three channels one at a time (the golden's `over_floor`, at the keys; at the game's import only with
  `RA_REGRESS_ASYM_GAME_CHANNELS=1`, off because that import cannot tell the run's shoulder dip apart - a row
  prints what it can and cannot), not only on the one that fails the AND; every
  row prints the gated values against their floors and marks a margin within x1.25 `THIN`; `swap=1` must invert every ratio (lag_cycles: exchange its two sides exactly) and
  disagree with the unswapped bake; `poison=1` (the manifest's variability block and measured values
  rewritten) must not move a digit.
- **`verify_moves.gd`** on every manifest. It checks MovesController's gait choice and playback rate
  from standing to the fastest gait and back, the hysteresis around each change of gait, and the
  stride phase carried across it. A manifest's `scene` is repointed at the glb beside it.
- **`verify_wardrobe.gd`** for the fixtures listed in `GODOT_WARDROBE`. `dressed_figure` has its
  shirt put on the body it was cut from, walked for 240 frames, and counted for holes and skin
  through the cloth. The limits are 0.5% each. A fixture's `controls` run again with extra
  arguments and must fail: `dressed_figure` with `cut=0.04`, a 4 cm patch removed from the shirt, so
  a hole check that stops seeing real holes fails the harness. `dressed_presets`, `pipeline_woman`,
  `traced_detail` and `dressed_skirts` are walked the same way; `traced_detail` is the compression pair on the
  embossed body, where the cloth is eased inside 12 mm of relief and lifted back over the skin that
  stood through it, and must still leave no hole and no skin showing.
  `dressed_skirts` wears the mini every 4th frame (a thigh goes through a skirt for only a few frames
  of a stride) and adds a count of skirt vertices inside a thigh; its controls `rigid=spine` (the skirt
  skinned to the pelvis alone) and `colliders=false` (no thigh capsules, no fold) must fail on it.

`_regress/` is removed afterwards whatever happens (and grungist-creek ignores it). Before
anything runs, the project's `addons/{rig_anything,wardrobe,follow_through}` are compared with this
repo's, ignoring line endings. A difference prints a warning, because the project's copy is what
the verifiers load. The first run found `verify_volume.gd` ahead in the project (a `clip=`
argument); that change now lives here.

Only fixtures that write a `.moves.json` reach `verify_moves`. rig-anything's hopper and radial
exporters write one, but a biped or quadruped exported with `export.export` gets only a `.rig.json`:
grungist-creek's `build_human.py` assembles its manifest by hand. So `mpfb_woman_curvy`,
`flesh_figure`, `rigify_human` and `quadruped` are not played in Godot. A manifest writer for them is filed under
`docs/improvements/01`.

A manifest with no `gaits` - the starfish's radial crawl - is reported as skipped: `verify_moves.gd`
drives a gait ladder, and radial bodies have no engine verifier of their own yet.

**`rabbit` also exports in a fresh session.** After its export it saves `rabbit.blend`, and a
second Blender opens that file and runs `tests/fixtures/_export_only.py`, which calls
`hop.export_creature(..., None, ...)` with no reports in hand - only what `move_set` stored on the
actions (`rig_analysis.stored`). `fresh_session.manifest_equal` is whether the two `.moves.json`
agree, path-like values aside; when they do not, `fresh_session.differs` names the first keys.
It proves a .blend saved after authoring exports the same creature later (03 step 6). Helpers
whose names start with `_` are not fixtures, so the runner never runs `_export_only.py` itself.

## Writing one

A fixture is `tests/fixtures/<name>.py`. It imports `_harness`, builds, and returns a dict:

```python
import _harness as H
H.use("RA_SCRIPTS", "FT_SCRIPTS")          # plugins on sys.path, versions noted

def build():
    H.clear_scene()                        # factory startup's cube, camera and light
    ...
    return {"regions": H.stable(found)}    # stable() drops Blender objects, private keys,
                                           # and the middle of a long per-frame trace
H.run("<name>", build)
```

Rules that keep a golden meaningful:

- **Deterministic.** Seed every generator, and record a new golden with `--twice`. A number cannot see the order faces are stored in; report `H.face_order(obj)` for any mesh
  whose order someone downstream walks. Never read the user's humanform library — the harness
  points `HUMANFORM_LIBRARY` at a scratch folder, and fits run with `use_library=False`.
- **Report results, not the run.** Timings, dates and absolute paths are stripped by the runner
  (`VOLATILE`, `PATHLIKE`), but a fixture that reports them is reporting noise.
- **Report what would look wrong.** Region centroids, joint errors, hip drop, cover counts —
  the numbers a person would have gone looking for after a change.

Which plugin checkout a fixture imports comes from `RA_SCRIPTS`, `HF_SCRIPTS`, `FT_SCRIPTS`,
`WD_SCRIPTS`, `CP_SCRIPTS` and `LD_SCRIPTS` — the names `grungist-creek`'s build scripts already use —
so `--plugins <checkout>` needs no edit to the fixture. Each points at the folder holding that
plugin's importable packages: `plugins/<name>/scripts`, except lookdev, whose Blender package lives in
`plugins/lookdev/blender` (`PACKAGE_DIR`, and it must say the same in `tools/regress.py` and
`tests/fixtures/_harness.py`). A checkout that predates a plugin moving into this repo keeps that
plugin on this checkout's copy.

## Comparison

Keys holding a path, a duration or a date are skipped (`VOLATILE`), matched as whole words of the key -
substrings once skipped `profile`, `direction_model` and `path_m` - and a key ending in a unit (`_m`, `_deg`) is
always compared. Because the match is on whole words of the key, a report key such as `build_timing` or `stage_seconds` drops the whole value under it, block and all: name a report block that holds more than durations with no volatile word in it, or check the golden holds what you meant. Reports are flattened to dotted keys and compared one by one: numbers within a relative tolerance
(`DEFAULT_TOLERANCE`, 1e-3, with per-pattern overrides in `TOLERANCES`), everything else exactly.
Keys that appear or vanish are changes too — a report that stops carrying `balance` is a
regression that a value comparison alone would miss.

## Reproducibility: `--twice`

A golden is one build's answer, so it cannot see a step that answers differently on every run:
Belle's garments moved 9.9 mm between two builds, and whichever draw the golden was recorded from
would have looked right. `--twice` builds every fixture a second time in the same run, each build in
its own folder with its own humanform library, and compares the two with each other before either
is compared with the golden. A disagreement prints `NONDETERMINISTIC` with the keys that differ
and fails the run, and `--update` writes no golden from a build that did not reproduce. It doubles
the time, so run it before merging and whenever a golden is recorded, not on every edit.

A fixture can also make its input vary on purpose. `H.shuffle_faces(obj)` stores a body's faces in a
random order when `REGRESS_SHUFFLE_FACES=1` - what a body joined with humanform's eyes got on every
run until 5.7 -
and is a no-op otherwise. `dressed_figure` shuffles its body before the shirt is cut, so

```
REGRESS_SHUFFLE_FACES=1 python tools/regress.py --twice --jobs 2 --only dressed_figure
```

checks that a fit does not depend on how the body was stored. Against the checkout before the 5.6
fix (`4f46876`, wardrobe 0.1.0) that reports `ease.gap_min_m` 0.0057 / 0.0058 and a hem ring's
`weighted_verts` 213 / 215 between two builds. On wardrobe 0.1.1 both shuffled builds agree with
each other and with the golden. Without the shuffle the old code agrees with itself too: the sample
body is never joined, so it never had its faces reordered.

## What it caught the first time

- Against the checkout before `2fe56b8` (the MPFB ground-root crouch fix), `mpfb_woman_curvy`
  moves in 98 keys — all crouch — and `dressed_figure` not at all. `flesh_figure` moves in exactly
  four: the buttock anchor `spine` → `spine.001`, which is follow-through 0.2.1's registry-anchor
  fix, the other change in that range.
- The rabbit's **`JumpAir` clip failed the export-time floor re-check** (foot 0.074 m below the
  floor at frame 1) although it passed at authoring, so `export_creature` refused - a clip whose
  vertical motion the engine owns, measured against the floor. Fixed with the biped jump under
  `docs/improvements/05` 5.1: a clip now carries the floor it was authored against. The rabbit
  exports all six clips, and the goldens moved to match.
- `--factory-startup` starts with **Rigify disabled**, and `fit_basic_human` then died with
  `'Armature' object has no attribute 'rigify_colors'` — the trap already filed under category 1.
  rig-anything now enables it itself (`fit.ensure_rigify`, wherever a metarig is added), and no
  fixture enables it, so `flesh_figure`, `dressed_figure`, `rigify_human` and `quadruped` all prove
  that. Enabling it cost a second find: with `default_set=False`, as the harness first did, Rigify's
  `register()` raises a KeyError reading its own preferences entry and is left half-registered.
