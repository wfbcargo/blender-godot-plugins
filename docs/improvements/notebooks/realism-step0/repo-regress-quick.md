# repo-regress-quick - lab notebook

Branch `repo-regress-quick`, plugins repo only. 06 section 5 "Repo tooling" items 1 and 2:
`tools/regress.py` scheduling, `--quick`, output, and `tools/bump.py`.

## 08:44 start

- Worktree `.worktrees/repo-regress-quick` from `main` at `5a218d3`. Scratch `C:/Users/pauli/AppData/Local/Temp/rw/repo-regress-quick/`.
- Read regress.py (500 lines), tests/README.md, _harness.py, 06 section 5.
- Findings before writing code:
  - regress keeps no durations anywhere, and no notebook of the last round recorded per-fixture times
    in a greppable form. So the longest-first order has to be measured: started a baseline
    `regress.py --jobs 2 --keep <scratch>/base` on the unchanged branch at 08:47.
  - The old loop waits on fixtures in name order, so `cricket` (one of the longest) holds every later
    result back even when they finished first. The baseline log showed only the `plugins:` line for
    minutes.
  - The pipeline fixtures silence `runner.build`'s log (`log=lambda m: None`), so stage times are not
    on stdout. They are in each exported `.moves.json`'s `build.stage_seconds` block, which regress
    can read from the fixture's output folder before the temp dir goes.
  - Fixture -> plugin: `H.use("RA_SCRIPTS", ...)` in each fixture. But plugins import each other
    (humanform imports wardrobe and lookdev_blender; wardrobe imports follow_through and rig_analysis),
    so `--quick` takes the import closure, scanned from the plugin sources at run time.
  - Version stamps: goldens carry `plugins: {name: version}` from `_harness._version`, which
    `compare` never reads (it compares `report` only). There is no restamp mechanism.
  - The "Since" sentence lives in marketplace.json only; plugin.json carries the version (three
    plugin.json descriptions have old Since sentences that stopped being updated at 0.5.0-0.14.0).

(Correction: the baseline started at about 08:45, not 08:47.)

## 08:47-08:55 regress.py, bump.py, test_tools.py

- regress.py: `schedule` (DURATIONS, unmeasured first), results judged in `as_completed` order once
  every build of a fixture is in, `_print` flushes every line, `main` wraps `_main` so every exit -
  argparse errors (exit 2) and crashes (exit 3) included - ends with `REGRESS DONE exit=N, K fixtures ok`.
  `--quick` / `--base` / `--changed` / `--dry-run`; `--diff FILE` (default in `--keep` or
  `<temp>/regress-diffs/`); `volatile_blocks` warning; `stage_times` from exported manifests;
  `path_warning` before (from DEEPEST_OUTPUT) and after (from what the run wrote); `--update` keeps a
  golden within tolerance.
- First failure: my splice script replaced every `started = time.time()` in the file, including
  `run_fixture`'s, so every fixture died with `NameError: name 'started' is not defined` inside the
  pool. The new `main` caught it and still printed `REGRESS DONE exit=3, 0 fixtures ok`, which is the
  point of the wrapper. Found by the fake-Blender end-to-end test, not by a real run.
- bump.py worked first time on a scratch copy (only the two version lines and the description line
  change; CR count 214/214 and 13/13 before and after). Refuses `0.6`, `v0.6.0`, `0.06.0`, `0.6.0.1`,
  a non-increasing version, an unknown plugin and a "Since 0.8.0" sentence on 0.7.0.
- tools/test_tools.py: selection, schedule, done line, VOLATILE warning, path warning, bump, and an
  end-to-end regress run against a fake Blender (`blender.cmd` calling back into test_tools.py with the
  golden as the report, `FAKE_DELAYS` to control finish order, `FAKE_BREAK` to move a key). Two of my own
  test mistakes on the first run: `timing_s` *is* volatile (`s` is not in UNITS), and a tuple unpack
  that read the wrong column. Fixed the tests, not the code. All pass in ~10 s.
- --quick on a wardrobe-only change selects 11 of 20: the 8 that use wardrobe plus mpfb_woman_curvy,
  muscle_definition and skin_detail, because humanform imports wardrobe (the import closure). Skips
  rabbit, cricket, starfish, quadruped, review_sheet, mixamo_names, rigify_human, flesh_figure,
  strand_ponytail.

## 08:55 baseline in; DURATIONS and DEEPEST_OUTPUT measured

Baseline `--jobs 2` on the unchanged branch: 20 ok, "no change", 08:44-08:55 (11 min). One build each:
rabbit 193 s, cricket 182, pipeline_muscle 130, dressed_presets 69, pipeline_woman 67, dressed_skirts 55,
flesh_figure 54, traced_detail 53, rigify_human 53, quadruped 49, mpfb_woman_curvy 49, pipeline_ponytail 40,
dressed_figure 38, hair_presets 36, strand_ponytail 32, muscle_definition 31, mixamo_names 21,
skin_detail 18, review_sheet 9, starfish 6. Under the old name order `rabbit` was 14th of 20 to start,
so at `--jobs 2` its 193 s ran after most of the rest: that is the tail the new order removes.

Deepest output under a fixture folder: 93 characters (pipeline_woman's
`pipeline_woman/pipeline_woman/assets/fixwoman/review/fixwoman/FixWoman_Idle_three_quarter.png`),
95 under `--twice` (`a/`). So a `--keep` root longer than about 140 characters warns.

Stage times the manifests carry: pipeline_muscle `draft, 25.2 s: body 8.4, bake 3.8, hair 0.8, moves 8.0,
export 4.0`; pipeline_ponytail `final, 4.6 s: strand 0.2, export 4.2`; pipeline_woman `final, 11.6 s:
export 5.8, review 5.2`. These are the last build recorded in each manifest (a fixture that rebuilds or
re-exports overwrites it), so for pipeline_woman they are its second-Blender export, not the full build.
The full build's stages would need the fixture to report them, which is a fixture change (open).

Deliberately failing run with real Blender (`RA_SCRIPTS=C:/nonexistent`, three fixtures): each printed
`ERROR ... ModuleNotFoundError: No module named 'rig_analysis'`, then `full diff: ...fail.diff`, and the
last line `REGRESS DONE exit=1, 0 fixtures ok`. The mixed case (one CHANGED, two ok -> `exit=1, 2 fixtures
ok`) is covered by test_tools.py's fake Blender.

--quick control on a real branch: worktree `rrq-wardrobe-probe` off this branch with one commit that
appends a comment to `plugins/wardrobe/scripts/wardrobe/__init__.py`;
`regress.py --quick --base repo-regress-quick --dry-run` selected 11, skipped rabbit, cricket and 7
others. With `tests/fixtures/_harness.py` also touched (uncommitted) it selected 20 of 20.

## 08:57 a bug of my own, caught in review before the final run

Reading `_main` again: `judge` pops `_deepest` from the report before the loop that measured the deepest
path read it, so the after-run path warning could never fire. Moved the measurement before `judge`,
measure against `out_root` as given (not resolved), print `deepest output: N characters (path)` - the
free value - and write the diff file in `finally`, so a run that dies part-way still leaves one.
test_tools.py gained a `--keep` case: a 255-character output path must warn after the run, and a short
`--keep` (the control) must not. Stopped the `--twice` run started at 08:57 on the old code and restarted.

## 08:58-09:10 final `--twice --jobs 2` on 7eb67b9

`python tools/regress.py --twice --jobs 2 --keep <scratch>/tw`: 20 ok, last lines
`no change` / `REGRESS DONE exit=0, 20 fixtures ok`, 08:57:57-09:09:55 (12 min; tests/README.md said
about half an hour for this before). Rabbit and cricket started first and finished first; results
came in schedule order because the pool ran both builds of each fixture side by side. No golden moved
(`git diff main -- tests/golden` empty). Deepest output 154 characters under a 58-character --keep root.

Stage lines printed: pipeline_muscle `draft, 11.2s: body 3.8, bake 1.9, hair 0.3, moves 3.5, export 1.6`,
pipeline_woman `final, 5.0s: export 2.3, review 2.4`, pipeline_ponytail `final, 2.6s: strand 0.2, export 2.4`.

**The VOLATILE-dict warning found a real hole on its first run:** `mpfb_woman_curvy`'s `export.file` is
a dict of 9 entries - the glb read back: animation lengths for 8 clips, joints 53, meshes, node count,
size, skins - and because `file` is a volatile word none of it has ever been compared. Left as it is
here (renaming the key adds keys to a golden, which is a fixture change for a reviewed commit); open.

## Open

- `mpfb_woman_curvy` `export.file`: rename (e.g. `export.glb`) so the readback is compared; records new
  golden keys.
- Stage times are the last build each manifest records; pipeline_woman's full build is overwritten by
  its second-Blender export. A fixture could report `build.stage_seconds` of its first build under a
  non-volatile-free name - but seconds are volatile by design, so it would be a regress side channel,
  not a report key.
- DURATIONS is a static table. regress could keep the last run's times in a user cache and schedule
  from that; not done, since the order barely changes and a table is reviewable.
- Not done from 06's list: `--restamp` and refusing `--update` when HEAD is not a descendant of main.
  bump.py says it does not restamp goldens (no mechanism exists; the stamp is never compared).
- `--update` keeps a within-tolerance golden, so its `plugins` version stamp stays at the old version.
