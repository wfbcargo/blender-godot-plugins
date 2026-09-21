# blender-godot-plugins

Claude Code plugins for 3D characters and creatures built in Blender 5.2 and played in Godot 4.7:
humanform, rig-anything, animate-anything, follow-through, wardrobe, lookdev, godot-lsp. The
project they are exercised on is `C:/Users/pauli/Code/GoDot/grungist-creek`. Planned work lives in
`docs/improvements/`; start with `NEXT.md` there.

## Working on these plugins

- **One worktree per piece of work, one agent per worktree.** `git worktree add .worktrees/<branch>
  -b <branch>` (`.worktrees/` is ignored). Merge to `main` with `--no-ff`, then remove the worktree
  and the branch. Parallel agents in one checkout have overwritten each other's edits before.
- **One scratch folder per agent.** Nothing in the repo root, a shared temp folder or the project:
  loose logs and blends from a shared folder have been mistaken for another agent's results.
- **The goal is plugins that produce assets, not perfect assets** (the user's rule, 2026-09-21). Capture
  the improvement, build fresh, and move on; do not spend a round scrutinising small numeric drift. What
  proves a change is a fresh build of the characters it affects (`character-pipeline/scripts/build_many.py`)
  and the game's demo self-tests passing in Godot - not the regression suite.
- **The regression suite is optional, and never a merge gate.** It was consistently the slowest part of a
  round (10-20+ minutes for `--twice --godot`) and the least useful. Run `--quick` only when a change
  touches shared code whose other callers you cannot build fresh (a creature rig, a fixture-only path),
  and read it for **crashes and pass/fail flips**, not for values that moved:

  ```
  python tools/regress.py --quick --jobs 2      # optional: only the fixtures the change reaches
  ```

  A CHANGED row whose checks still pass is expected when behaviour was meant to change - do not chase it,
  and do not block a merge on it. Goldens go stale between rounds; refresh them (`--update`) only when
  someone is about to rely on the suite. Never widen a tolerance to hide a real failure. Every run ends
  with `REGRESS DONE exit=N, K fixtures ok` and prints the path of the full diff. See `tests/README.md`.
- **Install only with `tools/install.py <plugin>` or `--all`.** It is the only path into
  `~/.claude/skills`, which is what Claude Code loads. It refuses to overwrite a copy that was edited
  in place: move that edit into the repo first. Other machines get a change by push and
  `/plugin marketplace update blender-godot-plugins`.
- **Bump a plugin's version** with `python tools/bump.py <plugin> <x.y.z> "<what changed>"`: it sets the
  version in its `.claude-plugin/plugin.json` and in `.claude-plugin/marketplace.json`, and appends the
  "Since x.y.z" sentence to the marketplace description, since that is what other machines read. It
  refuses a malformed or non-increasing version and an unknown plugin.

## Running Blender and Godot headless

- Blender: `"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup
  --python <script> -- key=value`. Add `--python-exit-code 1`, because otherwise a script that raises
  still exits 0.
- Godot: `C:/Users/pauli/Downloads/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64_console.exe`.
  Always use the `_console` build, because the other one detaches and its output is lost.
- humanform writes to the real library at `~/.claude/humanform/library` unless `HUMANFORM_LIBRARY`
  points elsewhere. Fixtures redirect it; ad-hoc scripts must do the same.
- A background command's output file stays empty until the command ends. Run long builds in the
  foreground with a generous timeout.
- To build grungist-creek's characters against a checkout without touching its assets:
  `python tools/scratch_project.py <scratch dir> [--who study_man,...]` (run from that checkout). It copies
  the specs, build scripts, addons and the chosen characters' blends and exports, writes `env.sh`/`env.ps1`
  (`PROJECT`, `BLEND_DIR`, `*_SCRIPTS` at the checkout, `HUMANFORM_LIBRARY` at a copy), imports it in Godot
  and prints the one command that builds a figure (`bash <dir>/build.sh study_man`). Specs' `[export] blend`
  are relative (under `BLEND_DIR`, else the project), and a build refuses to save outside both.

## Gotchas

- `git merge -F -` does not read stdin (`commit` does). Write the message to a file.
- Checkouts are CRLF (autocrlf) while git stores LF. A Python edit that matches multi-line text must
  normalise line endings first, or use the Edit tool.
- JSON written by build scripts is CRLF, so `git status` can list a rebuilt manifest as modified
  while `git diff` is empty. Trust the diff.
- A rebuilt glb can change size for reasons unrelated to the change under test. Parse the glTF JSON
  chunk and diff it before believing the change is meaningful.
- `bmesh.ops.create_uvsphere` writes its faces in a different order in every Blender process
  (improvements 5.7). `create_icosphere`, `_cube`, `_circle` and `_cone` do not. Sort the new faces
  (see `humanform/eyes.py` `_uvsphere`) unless a voxel remesh follows. `H.face_order` in a fixture
  report makes `--twice` catch a shuffle; `REGRESS_SHUFFLE_FACES=1` checks that a consumer does not care.
