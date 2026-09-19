# flesh-spring (research-flesh-jiggle.md items D and E, and the re-run open item from B+C)

2026-09-18/19, one agent in the main session. Scratch `%TEMP%/rw/fsp/`: game copy `game/` (study_woman, study_man,
the cast, Belle); `courses.sh <game> <tag>` (walk/run/full/jump on five figures, breast and butt .L, with an
`--import` first), `cmp.py` (two runs side by side), `sweep.sh <game> <label> set=k:v` (walk/run/jump on three
figures with jiggle overrides), `twice.py <cap>` (flesh.prepare three times on a saved blend).

## Measuring first (verify_flesh: vertical range and phase)

`_measure_motion`: per region, the offset's range along up (relative to the trunk) and the share of moving ticks
(both faster than 2 cm/s) in which the mass - anchor velocity plus offset velocity - goes up or down with the
anchor. Baseline after B+C, breast .L:

| | walk range | walk in phase | run range | run in phase |
|---|---|---|---|---|
| study_woman, Mei, Ruth | 3.9-4.3 cm | 0.81-0.88 | 7.8-9.8 cm | 0.50-0.55 |
| people (Scurr, Williams) | about 4.2 cm | about 0.66 unbraced | about 15 cm | - |

So the research's "4-5 mm walking" (E's premise and its control) was out of date: after B+C walking matches in
amplitude. What was off is the phase: walking 0.81-0.88 reads braced.

## D: the asymmetric spring

`JiggleModifier.step`: with `down_ratio`/`ap_ratio` at 1 it is `spring_step` (isotropic, unchanged). Else each axis
- up against gravity, front-back along the bone's rest direction made horizontal, the side - is one exact 1D
step with its own frequency, substepped to 1/240 s (the vertical stiffness changes where the offset crosses rest).
The main spring, the free and ladder shadow springs all use it. soft_fat: 2.4 Hz above rest, x2.8 below
(6.7 Hz), x1.4 front to back; damping ratio 0.25 on every axis.

`jiggle_selftest.gd` (in `regress --godot`): kick up at 1 m/s, time the half-period above and below rest at 30,
60, 144 fps. Below/above 0.345, 0.360, 0.357 (1/2.8 = 0.357); ap/side 0.715 (1/1.4); control `down_ratio=1`:
0.991-1.000, fails `down_up` at every rate. A research check met: "down half-period / up half-period about 1/3".

Dead end, 20 min: the first D run matched the baseline to the last digit. The glbs carried the new keys; the
scratch game had not been re-imported, so Godot played the old import. `courses.sh` now imports first.

What D did (courses, breast .L, before -> after):
- walking: range about the same; in phase Mei 0.81 -> 0.69 (people 0.66), others 0.84-0.85.
- running: range 7.8-9.8 -> 5.6-5.9 cm, in phase 0.50-0.55 -> 0.72-0.78. The stiff lower half shortens the whole
  cycle (2.4 up and 6.7 down is about 3.5 Hz, against the old symmetric 2.7).
- jump-only course: still over its 10 % line for Mei (10.2), Ruth (11.4), Marco's butt (10.9).

## E: mass scaling - built, measured, shipped off

Sweep of the up-frequency (`set=frequency_hz:x`, down 2.8, ap 1.4), breast .L on study_woman / Mei / Ruth:

| up Hz | walk on-limit | walk in phase | run range | run in phase | jump on-limit |
|---|---|---|---|---|---|
| 1.6 | 3.1-4.2 % | 0.83-0.88 | 7.5-8.6 cm | 0.50-0.53 | 31 % |
| 1.8 | 1.5-1.9 % | 0.87-0.92 | 7.5-8.5 | 0.55-0.58 | 31-33 % |
| 2.0 | 0.2-0.6 % | 0.84-0.91 | 7.3-8.5 | 0.58-0.64 | 32 % |
| 2.2 | 0 | 0.79-0.89 | 7.0-7.1 | 0.63-0.70 | 13.5-15 % |
| 2.4 (shipped) | 0 | 0.69-0.85 | 5.6-5.9 | 0.72-0.78 | 9.7-11.4 % |
| 2.6 | 0 | 0.66-0.80 | 5.2 | 0.77-0.84 | 9.2-10.2 % |

Belle (the heaviest breast, mass_kg 5.0 against 2.2-2.6) at 1.9 Hz, what mass scaling would give her: walking on
the limit 4.0 -> 7.4 %, jumping 8.0 -> 15 %. On these bodies the swing limit (limit_share x peak_m, set so skin
cannot pass through the chest) bounds the amplitude, not the spring: a slower, heavier mass only sits on its limit
longer. And `mass_kg` is the region's stand-out volume x 950 (2.2-5 kg a breast), not tissue mass.
So `jiggle_block` scales frequency by (mass_ref_kg / mass_kg)^mass_exponent clipped to 0.75-1.33 when a material
asks, and soft_fat ships mass_exponent 0. E's own check - running breasts moving several cm, in phase under
about 80 % - is met by D at 2.4 Hz (5.6-5.9 cm, 0.72-0.78), not by mass scaling.

## The re-run open item (from B+C)

`add_jiggle_bones` let a jiggle bone take all of a vertex (w = 1), leaving no proportion to give back: a second
prepare gave that weight to the anchor bone and read the lost thigh share - the game's 0.8.0-built Ruth fails
check_placement on the first direct prepare (butt 0.59 at the apex, 0.47 at 10 cm above), whatever cap the
re-run uses: the stored weights decide. `JIGGLE_SHARE_MAX` 0.98 caps it. The same body built by this branch (through
the pipeline) passes three direct prepares in a row, weights within 0.003 of the first. There is no in-process
control: the 0.8.0-built blend is it.

## Regress

`--quick --jobs 4 --godot`: 17 fixtures ok, every Godot check and control ok (the new `jiggle spring selftest` and
its `down_ratio=1` control among them); six fleshed fixtures changed (new spring keys and 2.4 Hz in every spec, the
0.98 cap in the weights), re-recorded with `--update --twice`. Two controls lost their teeth to the cap:
- flesh_figure `prepare_again.control_without_giving_back`: `unweighted` 18 -> 0 (no vertex is ever fully taken
  now); its weight error, 0.96, still shows what it is for. Kept.
- traced_detail's wardrobe control (dress with `FACING_MIN` off) stopped failing: whether its lifts ran away hung
  on the shoulder's exact weights. Replaced by the mechanism itself: `drawn_over_cloth` on the shipped top before
  any lift, flagged 10 triangles without the facing test and 0 with it (`control_facing_test`).

Final scratch rebuilds (study figures, cast, Belle) pass their flesh stage; the course numbers equal D's above.

## Open

- Walking in phase stays 0.69-0.85 against people's 0.66: no up-frequency in the sweep reached it without pinning
  the jump course.
- The jump-only course still exceeds its 10 % line for Mei, Ruth and Marco (D did not fix it, contrary to the
  B+C notebook's "D is the fix"); advisory on that course, the full course passes.
- Running amplitude (5.6-5.9 cm) is well under people's 15 cm, bounded by the limits.
- Damping is the same ratio on every axis; Cai's damping (1.83 / 2.07 N s/m) would lower the ratio below rest.
