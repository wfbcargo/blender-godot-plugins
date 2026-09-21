# Ship step - "Where to pick up" item 2, a left/right asymmetry metric

2026-09-21, 05:13-06:05 CDT, in the main checkouts (no other agent running). Merged this round:
`asym-godot-meter` (rig-anything 0.38.0) and `asym-motion-demo` (notebook in plugins; `motion_demo.gd` and
the 0.38.0 addon sync in grungist-creek). The change is an instrument, not the characters, so **no figure
was rebuilt and no look render was made** (steps 2 and 5 skipped by the round's plan).

## 1. Install and addon sync (05:13)

`python tools/install.py --all`: `rig-anything 0.37.0 -> 0.38.0: 4 changed, 2 added, 0 removed`; the other
seven up to date. The game's four addons (`follow_through`, `lookdev`, `rig_anything`, `wardrobe`) against
`plugins/*/godot/addons/*`, `diff -r --strip-trailing-cr -x '*.uid'`: identical, so nothing to sync -
`asym-motion-demo` had already brought 0.38.0 into `master`.

## 2. Godot on the game (05:14-05:25)

`--headless --import`: exit 0, **0 ERROR lines**. Script `%TEMP%/rw/ship/checks.sh`, logs in
`%TEMP%/rw/ship/checks/`:

    figure_study   exit 0  FIGURE_STUDY SELFTEST PASSED (0 failures)
    belle_demo     exit 0  BELLE_SELFTEST PASSED
    people_demo    exit 0  PEOPLE SELFTEST PASSED
    motion_demo    exit 0  MOTION_DEMO ok, 0 failures (72 ok rows incl. the 8 asymmetry rows)
    verify_moves   exit 0  MOVES VERIFY PASSED (six manifests: study_man, study_woman, belle,
                           cast_marco, cast_mei, cast_ruth)
    verify_flesh   course walk/run/jump, require=within_body, --fixed-fps 60: 18/18 exit 0,
                   "FT_SUMMARY 1 fleshed bodies, course <c>, PASSED" on all six figures

No error lines in any of the logs. The first time `verify_moves` and `verify_flesh` have been run on all
six in one ship step since the cast went onto `[variability]`.

## 3. The round's one full regress (05:14-06:03, 49 min)

`python tools/regress.py --twice --jobs 4 --godot C:/Users/pauli/Code/GoDot/grungist-creek`
(log `%TEMP%/rw/ship/regress.log`, diff `%TEMP%/regress-diffs/regress-20260921-051447-40864.diff`):

**`REGRESS DONE exit=1, 24 fixtures ok`**. All 24 Blender fixtures ok on both runs, including `asym_meter`
(93 s + 93 s); no golden moved, so nothing was re-recorded. Every Godot row green except one:

    FAILED  verify_strands pipeline_ponytail: swing_spread=1.050 start_spread=1.048
            a strand went 0.0060 / 0.0065 / 0.0067 / 0.0067 m into the head at 30 / 60 / 120 / 240 fps

That is the red row NEXT.md already carries ("The one red row the round ships with"), to the tenth of a
millimetre, so nothing this round did moved it. Its two must-fail controls still fail. All the
`verify_asymmetry asym_meter` rows pass as the merged branch left them: asym PASSED at its keys and at the
game's 60 Hz import, zero and mirror FAIL 2 checks each, swap inverts the ratios and flips the stance,
poison leaves the report hash unchanged. The game's default import still cannot tell the Run shoulder dip
apart (asym 0.043 against the controls' worst 0.050), which is why that channel stays ungated.

The regress staged into `grungist-creek/_regress/` and removed it; `git status` is clean in both repos
afterwards.

Time: the Godot selftests and the regress ran in parallel (the regress's Godot half starts after its
~30 min of Blender fixtures, so they did not contend for the import).
