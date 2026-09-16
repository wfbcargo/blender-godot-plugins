# Next: the remaining work

A handoff for a fresh conversation. Start with:

> Read `docs/improvements/NEXT.md`, then the work item it points at, and plan it.

State as of 2026-09-16. Everything below is on `main` in this repo and on `master` in `grungist-creek`,
both pushed. Installed plugin copies in
`~/.claude/skills` match the repo.

This repo was split out of `PaulClaudePlugins` on 2026-09-16 with its history kept, so every commit
hash here differs from the same commit there. `claude-architect` and `claude-boundaries` stayed
behind.

---

## Where things stand

| Item | Status |
|---|---|
| [03 Regression harness and install](03-regression-harness-and-install.md) | **Done** - eight fixtures, `--twice`, `--godot`, stored move reports, save guard. |
| [05 Feature gaps](05-feature-gaps.md) 5.1 jump sinks | **Done** - rig-anything 0.14.2. Belle's Jump ships unforced. |
| 05 · 5.6 garment nondeterminism | **Done** - wardrobe 0.1.1, guarded by `regress.py --twice` with shuffled faces (1a). |
| 05 · 5.7 `object.join` shuffles faces | **Open**, filed with a minimal repro. |
| [01 Character spec and pipeline](01-character-spec-and-staged-pipeline.md) | Not started. Biggest time saver. |
| [02 Bone roles and rig profiles](02-bone-roles-and-rig-profiles.md) | Not started. |
| [04 Checks that match the eye](04-checks-that-match-the-eye.md) | Not started. |
| 05 · 5.2 hair, 5.3 compression, 5.4 skirts, 5.5 muscle | Not started. |

Already built and worth knowing about before starting anything:

- `python tools/regress.py --jobs 2` - eight fixtures rebuilt headless and compared to
  `tests/golden/`; `--twice` before merging, `--godot <project>` when an export or addon changed.
  See [`tests/README.md`](../../tests/README.md) and the repo's `CLAUDE.md`.
- `python tools/install.py <plugin>` or `--all` - the only way into `~/.claude/skills`. Refuses to
  overwrite a copy edited in place.

---

## Remaining work, in the order I would take it

### 1. Finish 03 - DONE (2026-09-16)

All of 03 is done. What was built, and what it found:

- **`regress.py --twice`** (1a): each fixture builds twice, and a build that does not reproduce fails
  as `NONDETERMINISTIC` before any golden is compared or written. `REGRESS_SHUFFLE_FACES=1` stores
  `dressed_figure`'s body faces in a random order, which is 5.6's cause; that reproduces the drift on
  wardrobe 0.1.0 and passes on 0.1.1.
- **Eight fixtures** (1b, 1c): `cricket`, `starfish`, `rigify_human` and `quadruped` join the four.
  `quadruped_samples.dog` is new in rig-anything and scored against known joints (mean error
  27 mm). rig-anything enables Rigify itself, and needs `default_set=True`: with `False`, Rigify
  registers half-way. 03's "done when": against the checkout before the ground-root crouch fix,
  `mpfb_woman_curvy` moves only in Crouch, CrouchWalk and Jump. A Rigify rig moves only in Jump,
  and that change is the separate jump-floor fix.
- **Stored move reports** (1d, 03 step 6): every set function stores each role's report on its
  action, and a failed role on the rig. Every manifest and exporter loads them when given no
  reports. The `rabbit` fixture proves it: a second Blender exports from the saved .blend and
  writes the same manifest. rig-anything 0.15.0.
- **`regress.py --godot <project>`** (1e): exports are played in grungist-creek. Every manifest
  with gaits goes through `verify_moves.gd`, and `dressed_figure`'s shirt is worn and walked by
  `verify_wardrobe.gd`. The addon drift check found `verify_volume.gd`'s `clip=` living only in the
  project; it is now in follow-through 0.2.2. Bipeds and quadrupeds have no `.moves.json` writer,
  filed under 01.
- **`CLAUDE.md`** (1f, 03 step 8): worktrees, scratch folders, the fixtures before done, install and
  version rules, and the gotchas.
- **Blend hygiene** (1g, 03 step 7, in grungist-creek): `belle_demo.blend` is split into
  `belle_stylized.blend` and `creature_tests.blend`, with a backup and every object and action
  accounted for. `assets/save_guard.py` refuses a save that would delete a scene the session never
  loaded, and every build script that overwrites a file uses it. `belle_demo.blend` and its backup
  are still on disk, for Paul to retire.
- **Found along the way:** filed as 05 · 5.8. The cricket's landing fails its slide check, so it never
  exports. The slides put feet through the floor on a Rigify biped. A symmetric starfish gets 3- and
  4-bone arms. `radial.skin` reports coverage without measuring it.

A full `regress.py --twice --jobs 2 --godot` run takes about 10 minutes on this machine (the rabbit and the cricket are 6 of them).

### 2. Small fixes found along the way

- **5.7 - a deterministic join.** `bpy.ops.object.join` (eyes and hair into a body) writes the same
  faces in a different order every run. wardrobe is immune now and the glTF exporter writes the same
  indices either way, so nothing shipped is affected - but a `.blend` is not reproducible and any
  consumer that walks faces in order inherits the trap. Give rig-anything a `join_into(target, others)`
  that merges through bmesh in the order given, and point `build_human.bake` and Belle's `hair()` at it.

### 3. The large items

- **02 Bone roles and rig profiles.** Name root, pelvis, chest, head and anchors once in
  `bodymap.build`; an MPFB profile carries its quirks. Fixes the class of bug where follow-through put
  both breast bones on Belle's chin. Do before 01: 01's stages get simpler when roles exist.
- **01 Character spec and staged pipeline.** One YAML per character, a stage runner with
  preconditions and saved results, tuned numbers moved into plugin presets. `build_human.py` and
  `build_belle.py` become thin callers.
- **04 Checks that match the eye.** 04a first: wardrobe's hole check counts cloth pressed into a
  crease as a hole. Belle's shorts fail it at 1.71% (limit 0.5%) where the screenshots show no gap;
  the sports top passes at 0.23%. Then review strips written by every export, and a motion critic.
- **05 · 5.2-5.5** - hair (Belle's reads as a helmet), compression garments (her top traces the body),
  skirts, muscle definition. Independent; take them as the look of a character demands.

### 4. Triage the old project notes

`grungist-creek/docs/plugin-improvements.md` predates this round. Some entries are stale; some are
not filed anywhere yet and may still be live - notably `flesh.add_jiggle_bones` stripping weights on a
re-run, the jiggle modifier needing physics-tick processing, the hard `max_offset_m` clamp, and the
volume API gaps (`collision_mask`, `tumble`, `push`). Check each against current code and either
file it under a category in [README.md](README.md) or strike it.

---

## Things that cost time to learn this round

**Running Blender headless**

- Binary: `C:/Program Files/Blender Foundation/Blender 5.2/blender.exe -b --factory-startup --python <script> -- key=value`.
- `bpy.context.window` exists in background mode in Blender 5.2, so scene switching works.
- Rigify is off under `--factory-startup` (see above). MPFB is not: humanform enables it.
- humanform writes to the real library at `~/.claude/humanform/library` unless `HUMANFORM_LIBRARY`
  says otherwise. Fixtures redirect it; ad-hoc build scripts do not.
- A background command's output file stayed empty until it finished - run long builds in the
  foreground with a generous timeout instead.

**Building the project's characters without touching its assets**

`build_belle.py` and `build_human.py` write into `PROJECT/assets/...`. Copy
`assets/humans/` and `assets/belle/build_belle.py` into a scratch folder with the same layout and set
`PROJECT` to it (and `BLEND_COPY`). Point `RA_SCRIPTS`, `HF_SCRIPTS`, `FT_SCRIPTS`, `WD_SCRIPTS` at this
repo's `plugins/<name>/scripts` to test a checkout. A crowd person builds in 10-20 s; Belle in 20 s
warm, a few minutes cold. `who=tomas` needs `C:/Users/pauli/Code/Blender/humanform_hands_feet_demo.blend`
passed as the file to open.

**Verifying in Godot** (`GODOT` = the `_console` build, path in the project's CLAUDE.md)

```
"$GODOT" --headless --import --path .
"$GODOT" --headless --path . belle_demo.tscn -- --selftest
"$GODOT" --headless --path . people_demo.tscn -- --selftest
"$GODOT" --headless --fixed-fps 60 --path . -s res://addons/wardrobe/verify_wardrobe.gd -- \
    body=res://assets/belle/belle.glb garment=res://assets/belle/belle_sportstop.glb \
    frames=240 every=8 hem=true jiggle=true
```

To compare against committed assets, `git show HEAD:<path> > assets/_old/<file>`, reimport, run the
verifier on both, and delete the folder afterwards.

**Finding a nondeterminism** - what worked for 5.6, in order: compare the written files; if they
differ, checksum each stage's output inside two full builds and find the first that disagrees;
checksum that stage's inputs, hashing structure (face order, sorted and unsorted) as well as
positions; then reproduce it minimally, three runs, three hashes.

**Tooling gotchas**

- `git merge -F -` does not read stdin (commit does). Write the message to a file.
- JSON the build scripts write is CRLF on Windows while git stores LF: `git status` lists every
  rebuilt manifest as modified when `git diff` is empty. Trust the diff.
- A rebuilt glb can change for reasons that have nothing to do with the change being tested -
  humanform 0.6.1 adding `"cupsize": null` to the sheet extras grew every crowd glb by 20 bytes.
  Parse the glTF JSON chunk and diff it before believing a binary changed meaningfully.

## Loose ends in the repos

- Merged branches still exist locally in grungist-creek: `belle`, `belle-jump-unforced`,
  `humanform-plan`, `tomas-walk`.
- `grungist-creek/tomas_demo.tscn` (untracked, pointing at a missing `tomas_demo.gd`) was moved out of
  the project into a session scratch folder, which the OS cleans up, so treat it as gone.
- `C:/Users/pauli/Code/Blender/belle_demo.blend` and `belle_demo.backup.blend` (100 MB each) are
  still there after the split. Retire them once `belle_stylized.blend` and `creature_tests.blend`
  have been opened by hand.
- This repo is public, and `plugins/humanform/data/` (ANSUR II public CSVs and the seed contact
  sheets) is published with it - a deliberate choice, recorded here in case it is revisited.
