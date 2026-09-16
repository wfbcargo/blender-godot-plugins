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
    H.enable_addons("rigify")              # --factory-startup starts with Rigify off
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
- `--factory-startup` starts with **Rigify disabled**, and `fit_basic_human` then dies with
  `'Armature' object has no attribute 'rigify_colors'` — the trap already filed under category 1.
  Fixtures call `H.enable_addons("rigify")`; rig-anything should do it itself.
