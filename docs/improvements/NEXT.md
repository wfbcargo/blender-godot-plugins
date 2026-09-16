# Next: the remaining work

A handoff for a fresh conversation. Start with:

> Read `docs/improvements/NEXT.md`, then the work item it points at, and plan it.

State as of 2026-09-16. Everything below is on `main` in this repo (`b5333bc` and later) and on
`master` in `grungist-creek` (`3263b74`), both pushed. Installed plugin copies in
`~/.claude/skills` match the repo.

This repo was split out of `PaulClaudePlugins` on 2026-09-16 with its history kept, so every commit
hash here differs from the same commit there. `claude-architect` and `claude-boundaries` stayed
behind.

---

## Where things stand

| Item | Status |
|---|---|
| [03 Regression harness and install](03-regression-harness-and-install.md) | Steps 1-5 **done**. Steps 6-8 and five fixtures open. |
| [05 Feature gaps](05-feature-gaps.md) 5.1 jump sinks | **Done** - rig-anything 0.14.2. Belle's Jump ships unforced. |
| 05 · 5.6 garment nondeterminism | **Done** except the `--twice` harness check its "done when" asked for. wardrobe 0.1.1. |
| 05 · 5.7 `object.join` shuffles faces | **Open**, filed with a minimal repro. |
| [01 Character spec and pipeline](01-character-spec-and-staged-pipeline.md) | Not started. Biggest time saver. |
| [02 Bone roles and rig profiles](02-bone-roles-and-rig-profiles.md) | Not started. |
| [04 Checks that match the eye](04-checks-that-match-the-eye.md) | Not started. |
| 05 · 5.2 hair, 5.3 compression, 5.4 skirts, 5.5 muscle | Not started. |

Already built and worth knowing about before starting anything:

- `python tools/regress.py --jobs 2` - four fixtures rebuilt headless and compared to
  `tests/golden/` (about 3 minutes). Run it before changing shared code and before calling a
  change done. See [`tests/README.md`](../../tests/README.md).
- `python tools/install.py <plugin>` or `--all` - the only way into `~/.claude/skills`. Refuses to
  overwrite a copy edited in place.

---

## Remaining work, in the order I would take it

### 1. Finish 03 - small, and every later item leans on it

- **`--twice` reproducibility check** (owed by 5.6). Build a fixture twice in one `regress.py` run and
  compare the two reports to each other, not to a golden. Belle's garments differed by 9.9 mm between
  builds and no golden could have caught it, because the golden was recorded from one of the draws.
- **Missing fixtures**: `rigify_human` (`fit_basic_human` on a sample mesh), `quadruped`, `cricket`
  (`hopper_samples.cricket`), a radial body (`radial_samples`), and `--godot <project>` to run the
  Godot verifiers and self-tests on the exported fixtures. Generators and seeds, never a `.blend`.
- **Step 6 - stage results on objects, not session memory.** A first instance exists:
  `hop.air` stamps `action["rig_anything_floor"]` and the exporter reads it. Generalise to
  `move_set` writing each role's report onto its action, so export works in a fresh session.
- **Step 7 - blend hygiene.** Split `C:/Users/pauli/Code/Blender/belle_demo.blend` into Belle and the
  72 creature test objects; build scripts refuse to save over a file with scenes they did not make.
- **Step 8 - agent hygiene.** Write down in a CLAUDE.md or SKILL.md section: own scratch subfolder,
  own worktree, `tools/regress.py` before reporting done.

### 2. Small fixes found along the way

- **rig-anything should enable Rigify itself.** Under `--factory-startup` it is off, and
  `fit_basic_human` dies with `'Armature' object has no attribute 'rigify_colors'`. Fixtures work
  around it with `H.enable_addons("rigify")`. Filed in 02's quirk table.
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

- Merged branches still exist locally: `tooling-wardrobe-install` here; `belle`,
  `belle-jump-unforced`, `humanform-plan`, `tomas-walk` in grungist-creek.
- `grungist-creek/tomas_demo.tscn` is untracked and references a missing `tomas_demo.gd`; Godot logs
  an error for it on every import.
- This repo is public, and `plugins/humanform/data/` (ANSUR II public CSVs and the seed contact
  sheets) is published with it - a deliberate choice, recorded here in case it is revisited.
