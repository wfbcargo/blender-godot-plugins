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
- **A round has a budget, and it is stated before it starts** (the user's rule, 2026-09-22, after a round of
  fantasy species spent most of a weekly usage limit). Say in one line how many agents and roughly how many
  full builds a round will take, and ask before exceeding **4 agent tasks or ~10 builds**. Report spend at each
  checkpoint. The cost is never the engineering - it is the loop of looking at a render, calling it not quite
  right, and dispatching another pass, because each pass is a 1-4 minute character build plus Godot renders.
- **Send work back only for a regression or a wrong check.** A defect that is merely "could read better" is a
  line in NEXT.md, not another pass; a *third* pass on the same defect needs the user to ask for it. That round
  put beards through four passes and the gnoll through four builds, and the beard ended up worse in Godot than
  the shell it replaced.
- **One proof run per round, at the end**, and build the character a change touches rather than the whole cast.
  Prefer a number - a measurement, a check, a diff - to a render, because a render costs a build. Reuse a saved
  .blend or an existing scratch project before making a fresh one.
- **Agents that share files serialise.** Four agents extending the same body-plan code (legs, feet, fur, muzzle)
  cost a hand-merge in one function and a rebuild each time; split by file ownership or run them in turn.
- **The regression suite is optional, and never a merge gate.** It was consistently the slowest part of a
  round (10-20+ minutes for `--twice --godot`) and the least useful. Keep what it is good at, cheaply:
  - **Run `--quick` in the background and never wait on it.** Start it when a change touches shared code,
    carry on building and looking, and when it ends read it for **crashes and pass/fail flips** only - a value
    that moved is expected when behaviour was meant to change; do not chase it or block a merge on it. It
    earns its keep there: in the likeness round it alone caught a knee change that took a crouch, a jump and
    a slide off the rest pose (a fresh build of the humans did not show it).
  - **Re-record the goldens at the end of every round, unreviewed** (`--update`, one command, run in the
    background), so the next round's run is quiet and a real flip stands out. A suite nobody refreshes fills
    with CHANGED rows until no one can see a failure in it.
  - **When a change touches shared rig code, also build one creature fresh** (the cricket, rabbit or quadruped
    fixture), not only humans: they share rig-anything's legs and a human round never rebuilds them.

  ```
  python tools/regress.py --quick --jobs 2      # background: only the fixtures the change reaches
  python tools/regress.py --update --jobs 2     # background, end of round: goldens follow what shipped
  ```

  Never widen a tolerance to hide a real failure. Every run ends with `REGRESS DONE exit=N, K fixtures ok`
  and prints the path of the full diff. See `tests/README.md`.
- **Catch it upfront.** The goal is plugins that guide the work to a great design quickly, so a mistake found
  by a check before a build is worth far more than one found by looking after it. When a round finds a
  mistake by eye, add the check that would have caught it first (a spec refusal, a stage check, a warning
  with the fix in it) - `docs/improvements/NEXT.md`, "Catch it upfront", lists the open ones. Until those
  checks exist, do by hand what they will do (each cost the likeness round rebuilds):
  - **Judge the look in Godot, not in Blender's review tiles.** A dress showing the bust and a beard's
    square patches looked fine or different in Blender and were obvious in the game. Import, run the demo,
    orbit in close (the figure-study demos' camera), and use lookdev's `close-shot`.
  - **Build an extreme body alongside the change** - petite, very tall, elderly or heavy. A 1.53 m body found
    three problems the 1.57-1.80 m reference figures never showed.
  - **Look at the rest skeleton before animating a new body.** A knee a few millimetres off the hip-ankle
    line bowed every clip's legs (rig-anything's body map now warns: read its warnings).
  - **A garment preset over the bust or belly needs an `ease` with a `detail_limit`**, or it traces the body.
  - **A likeness takes a frontal photo.** A turned head hides a cheek and shortens every width: find another
    photo rather than fit to it, and check the fit's `likeness.at_limit` before trusting the face.
  - **A real person's likeness gets no breast or butt jiggle and no garment that shows the body.**
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
