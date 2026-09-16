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
```

A change is not by itself a failure — a fix moves numbers. The point is that the move is **seen**,
on every fixture rather than on one character, and that accepting it is a reviewed commit to
`tests/golden/`.

## Fixtures

Each is a script Blender runs in its own process, building from nothing — no `.blend`, no stored
asset — and writing a report of what it got. About four minutes for all four, or two and a half
with `--jobs 2`; the rabbit is most of it, because a voxel remesh is slow.

| Fixture | Builds | Exercises |
|---|---|---|
| `mpfb_woman_curvy` | a woman from a seeded brief: ANSUR fit through MPFB2, baked, Idle/Walk/Run/Crouch/CrouchWalk, exported | humanform's fit and check, `bake_for_game`, `move_set`, the crouch on an MPFB rig, the export re-check |
| `rabbit` | `hopper_samples.rabbit`, detected, rigged, skinned, hopped, exported | leg detection against the sample's known joints, `hoppers.build`/`skin`, `hop.move_set`, `export_creature` |
| `flesh_figure` | follow-through's `Figure` and `Bloater`, rigged, walked, fleshed, exported | `fit_basic_human`, bind coverage, `flesh.prepare` region placement, the glTF read back |
| `dressed_figure` | a shirt cut onto the fleshed `Figure` | `tailor`/`fit`/`hem`/`cover`, and the flesh-before-garments order |

Still missing, from `docs/improvements/03`: `rigify_human`, `quadruped`, `cricket`, the radial
bodies, and the Godot-side verifiers (`--godot`).

## Writing one

A fixture is `tests/fixtures/<name>.py`. It imports `_harness`, builds, and returns a dict:

```python
import _harness as H
H.use("RA_SCRIPTS", "FT_SCRIPTS")          # plugins on sys.path, versions noted

def build():
    H.clear_scene()                        # factory startup's cube, camera and light
    H.enable_addons("rigify")              # --factory-startup starts with Rigify off
    ...
    return {"regions": H.stable(found)}    # stable() drops Blender objects, private keys,
                                           # and the middle of a long per-frame trace
H.run("<name>", build)
```

Rules that keep a golden meaningful:

- **Deterministic.** Seed every generator. Never read the user's humanform library — the harness
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

## What it caught the first time

- Against the checkout before `71d84fe` (the MPFB ground-root crouch fix), `mpfb_woman_curvy`
  moves in 98 keys — all crouch — and `dressed_figure` not at all. `flesh_figure` moves in exactly
  four: the buttock anchor `spine` → `spine.001`, which is follow-through 0.2.1's registry-anchor
  fix, the other change in that range.
- The rabbit's **`JumpAir` clip failed the export-time floor re-check** (foot 0.074 m below the
  floor at frame 1) although it passed at authoring, so `export_creature` refused - a clip whose
  vertical motion the engine owns, measured against the floor. Fixed with the biped jump under
  `docs/improvements/05` 5.1: a clip now carries the floor it was authored against. The rabbit
  exports all six clips, and the goldens moved to match.
- `--factory-startup` starts with **Rigify disabled**, and `fit_basic_human` then dies with
  `'Armature' object has no attribute 'rigify_colors'` — the trap already filed under category 1.
  Fixtures call `H.enable_addons("rigify")`; rig-anything should do it itself.
