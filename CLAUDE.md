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
- **Run the fixtures before calling a change done**, and before changing shared code:

  ```
  python tools/regress.py --jobs 2                                          # every edit that matters
  python tools/regress.py --twice --jobs 2                                  # before merging
  python tools/regress.py --twice --jobs 2 --godot C:/Users/pauli/Code/GoDot/grungist-creek
                                                                            # when a Godot addon or an
                                                                            # export changed
  ```

  A golden moves only in a reviewed commit (`--update`, then read `git diff tests/golden`), and a
  new golden is recorded with `--twice`. Never widen a tolerance to make a change pass: find why it
  moved. A full `--twice --godot` run takes about 10 minutes. See `tests/README.md`.
- **Install only with `tools/install.py <plugin>` or `--all`.** It is the only path into
  `~/.claude/skills`, which is what Claude Code loads. It refuses to overwrite a copy that was edited
  in place: move that edit into the repo first. Other machines get a change by push and
  `/plugin marketplace update blender-godot-plugins`.
- **Bump a plugin's version** in its `.claude-plugin/plugin.json` and in `.claude-plugin/marketplace.json`,
  and add a "Since x.y.z" sentence to the marketplace description, since that is what other machines read.

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
- To build grungist-creek's characters against a checkout without touching its assets, copy
  `assets/humans/`, `assets/save_guard.py` and `assets/belle/` into a scratch folder with the same
  layout. Set `PROJECT` and `BLEND_DIR` to that folder, and `RA_SCRIPTS`, `HF_SCRIPTS`,
  `FT_SCRIPTS`, `WD_SCRIPTS` to this repo's `plugins/<name>/scripts`.

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
