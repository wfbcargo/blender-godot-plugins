# 03 - Regression harness and install

Category: **5 tooling friction**. Do this before 01 or 02 - they change shared code.

## Problem

- **No regression tests for rig-anything, animate-anything, follow-through or lookdev.** The only
  tests in this repo are `plugins/claude-boundaries/tests/*.test.mjs`. humanform has Blender scripts
  in `scripts/tests/` (not a runner). A change to shared code is verified on whichever character the
  author happens to be building: the MPFB crouch fix was "tested on Belle only" until a separate
  comparison on four other rigs.
- **Three copies of each plugin**: this repo, `~/.claude/skills/<plugin>` (what actually loads), and
  the marketplace clone `~/.claude/plugins/marketplaces/paul-claude-plugins` (updates only from
  GitHub). No install script exists; `rig-anything/README.md:209` says `cp -r`.
- **wardrobe is not under version control anywhere.** It exists only as
  `~/.claude/skills/wardrobe/` (and its Godot addon copied into grungist-creek), although its
  `plugin.json` names this repo.
- **humanform** is a git repo with no remote, and commits there need an explicit identity
  (`git -c user.name=wfbcargo -c user.email=...`).
- **Build state is not persistent**: the stylized Belle kept move results in
  `bpy.app.driver_namespace`, so export only worked in the same Blender session as `moves()`.
- **Blends mix unrelated content**: `C:/Users/pauli/Code/Blender/belle_demo.blend` holds Belle's
  scene *and* a second scene of 72 creature test objects; saving a rebuilt Belle over it nearly
  lost them.
- **Parallel agents collided** in a shared scratch directory.

## What worked as a stand-in (reuse it)

- Committed `<who>.moves.json` / `.rig.json` in grungist-creek were the baseline; a rebuild with
  identical output proved no regression (`git diff` empty).
- A PowerShell loop built all 16 people headless (~7-10 s each) against a chosen plugin checkout via
  env overrides `RA_SCRIPTS`, `HF_SCRIPTS`, `FT_SCRIPTS`, `PROJECT`, `BLEND_DIR`, `BLEND_COPY`
  (already supported by `build_human.py` / `build_belle.py`).
- Old-vs-new comparison of `actions.crouch` / `actions.jump` reports on `QuadTest_rig`,
  `Rat_metarig`, `RigTest_rig`, `HumanoidRig` from `belle_demo.blend` (link the rigs into the active
  scene first; headless Blender has no window to switch scenes).
- Godot checks: `people_demo.tscn -- --selftest`, `belle_demo.tscn -- --selftest`,
  `addons/rig_anything/verify_moves.gd`, `addons/wardrobe/verify_wardrobe.gd`.

## Design

**Fixtures** - a small, versioned set of bodies that exercise every path:

| Fixture | Source | Exercises |
|---|---|---|
| `mpfb_man`, `mpfb_woman_curvy`, `mpfb_child`, `mpfb_elderly` | humanform briefs (seeded) | MPFB quirks, ages, posture, styles |
| `rigify_human` | rig-anything `fit_basic_human` on a sample mesh | non-MPFB biped, crouch/jump |
| `quadruped`, `rat` | existing test rigs | legs, trot, crouch |
| `rabbit`, `cricket` | `hopper_samples.build_all()` | hop code |
| `jellyfish`, `starfish` | `radial_samples.build_all()` | radial code |
| `flesh_figure` | `follow_through.samples` | jiggle regions |
| `dressed_figure` | wardrobe samples | tailor, cover, verifier |

Fixtures live as **generator scripts plus seeds**, not blends, so they rebuild identically.

**Goldens** - for each fixture, the JSON reports a build produces (move reports, export clip report,
manifest, flesh regions, wardrobe cover summary) with volatile keys (timestamps, paths) stripped.
Stored under `tests/golden/<fixture>/`.

**Runner** - one command:

```
python tools/regress.py [--plugins <checkout>] [--only rig-anything] [--update]
```

- Runs each fixture headless in its own Blender process with env overrides pointing at the checkout.
- Compares to goldens with numeric tolerance (default 1e-3 relative, per-key overrides), prints a
  table of changed keys per fixture, exits non-zero on any unexplained change.
- `--update` rewrites goldens (the diff is then reviewed in the commit).
- Optional `--godot <project>` runs the Godot verifiers and self-tests on the exported fixtures.

**Install** - `tools/install.py <plugin>... [--all]`: mirror `plugins/<name>` to
`~/.claude/skills/<name>` excluding `__pycache__`, print old -> new version, refuse if the installed
copy has changes not in the repo (diff first). Document "push, then update the marketplace" as the
follow-up for other machines.

## Steps

1. **Bring wardrobe under git**: copy `~/.claude/skills/wardrobe` into `plugins/wardrobe/` here
   (drop `__pycache__`), add it to `.claude-plugin/marketplace.json`, commit. Diff the project's
   `grungist-creek/addons/wardrobe` against it (only CRLF differences were seen).
2. **humanform**: decide its home - move into this repo as `plugins/humanform` (its `data/` library
   included) or give it a remote; set a repo-local git identity either way.
3. **`tools/install.py`** as above; replace the `cp -r` instructions in READMEs.
4. **Fixture generators** in `tests/fixtures/*.py` (start with `mpfb_woman_curvy`, `rigify_human`,
   `quadruped`, `rabbit`, `flesh_figure`, `dressed_figure` - six covers most paths).
5. **`tools/regress.py`** with golden comparison and tolerances; record the first goldens from
   current `main`.
6. **Persist stage results** on objects, not session memory: `move_set` writes each role's report to
   the action (`action["rig_anything_report"]`), so export can run in a fresh session. (01's pipeline
   generalises this.)
7. **Blend hygiene**: split `belle_demo.blend` into `belle.blend` (Belle only) and
   `creature_tests.blend` (the 72 test objects); build scripts refuse to `save_as_mainfile` over a
   file containing scenes they did not create.
8. **Agent hygiene** (add to CLAUDE.md / plugin SKILL.md "working on this plugin"): each agent uses its
   own scratch subfolder and its own worktree; run `tools/regress.py` before reporting done.

## Done when

- `python tools/regress.py` passes on `main` and fails, naming the fixture and key, when a known
  behaviour change is introduced (e.g. revert the ground-root crouch fix: `mpfb_woman_curvy` crouch
  changes, others don't).
- Every plugin that loads from `~/.claude/skills` has a source in this repo, and `tools/install.py`
  is the only install path used.
- Export works in a fresh Blender session after `moves()` ran in another.
