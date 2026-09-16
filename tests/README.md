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
```

A change is not by itself a failure — a fix moves numbers. The point is that the move is **seen**,
on every fixture rather than on one character, and that accepting it is a reviewed commit to
`tests/golden/`.

## Fixtures

Each is a script Blender runs in its own process, building from nothing — no `.blend`, no stored
asset — and writing a report of what it got. About ten minutes for all eight one after another,
or six with `--jobs 2`; the rabbit and the cricket are most of it (over two minutes each alone),
because a voxel remesh is slow.

| Fixture | Builds | Exercises |
|---|---|---|
| `mpfb_woman_curvy` | a woman from a seeded brief: ANSUR fit through MPFB2, baked, Idle/Walk/Run/Crouch/CrouchWalk, exported | humanform's fit and check, `bake_for_game`, `move_set`, the crouch on an MPFB rig, the export re-check |
| `rabbit` | `hopper_samples.rabbit`, detected, rigged, skinned, hopped, exported | leg detection against the sample's known joints, `hoppers.build`/`skin`, `hop.move_set`, `export_creature` |
| `flesh_figure` | follow-through's `Figure` and `Bloater`, rigged, walked, fleshed, exported | `fit_basic_human`, bind coverage, `flesh.prepare` region placement, the glTF read back |
| `dressed_figure` | a shirt cut onto the fleshed `Figure`, and that body exported walking | `tailor`/`fit`/`hem`/`cover`, the flesh-before-garments order, and (with `--godot`) the shirt worn in Godot |
| `cricket` | `hopper_samples.cricket`, detected, rigged, skinned, walked, jumped, exported | six-leg detection against the sample's known joints, the orthopteran branch of `hop.move_set` (Idle, Walk, JumpLaunch/Air/Land), `export_creature`'s refusal of a failed clip |
| `starfish` | `radial_samples.starfish`, detected as `asteroid`, rigged, skinned, crawled, exported | `radial.detect`'s hub and arms, `radial.build`/`skin` and the weights actually written, `radial_moves` Crawl and Idle, the `radial` manifest |
| `rigify_human` | follow-through's `Figure`, unfleshed, given every biped move, exported | `fit_basic_human` with Rigify off, `move_set`'s ten default roles on a rig with no ground root, the export re-check. The three slides fail their floor checks and are dropped from the export with the reasons in the golden |
| `quadruped` | `quadruped_samples.dog`, fitted, bound, given Idle/Walk/Trot/Run/Crouch, exported | four ground contacts, `fit_basic_quadruped` scored against the sample's known joints, `skin.bind`, `move_set` on four legs, the export re-check |

## In the engine: `--godot <project>`

A glb that Blender wrote correctly can still play wrongly in Godot. `--godot` takes each fixture that
built, copies its `.glb` and `.moves.json` files into `<project>/_regress/<fixture>/`, imports them,
and runs the project's copies of the verifiers:

- **`verify_moves.gd`** on every manifest. It checks MovesController's gait choice and playback rate
  from standing to the fastest gait and back, the hysteresis around each change of gait, and the
  stride phase carried across it. A manifest's `scene` is repointed at the glb beside it.
- **`verify_wardrobe.gd`** for the fixtures listed in `GODOT_WARDROBE`. `dressed_figure` has its
  shirt put on the body it was cut from, walked for 240 frames, and counted for holes and skin
  through the cloth. The limits are 0.5% each.

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

- **Deterministic.** Seed every generator, and record a new golden with `--twice`. Never read the user's humanform library — the harness
  points `HUMANFORM_LIBRARY` at a scratch folder, and fits run with `use_library=False`.
- **Report results, not the run.** Timings, dates and absolute paths are stripped by the runner
  (`VOLATILE`, `PATHLIKE`), but a fixture that reports them is reporting noise.
- **Report what would look wrong.** Region centroids, joint errors, hip drop, cover counts —
  the numbers a person would have gone looking for after a change.

Which plugin checkout a fixture imports comes from `RA_SCRIPTS`, `HF_SCRIPTS`, `FT_SCRIPTS` and
`WD_SCRIPTS` — the names `grungist-creek`'s build scripts already use — so `--plugins <checkout>`
needs no edit to the fixture. A checkout that predates a plugin moving into this repo keeps that
plugin on this checkout's copy.

## Comparison

Reports are flattened to dotted keys and compared one by one: numbers within a relative tolerance
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
random order when `REGRESS_SHUFFLE_FACES=1` - what `object.join` does to a body on every run (5.7) -
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
