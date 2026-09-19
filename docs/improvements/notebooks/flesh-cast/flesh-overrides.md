# flesh-overrides (research-flesh-jiggle.md item F; the belly)

2026-09-19, one agent in the main session. Scratch `%TEMP%/rw/fov/`: game copy `game/` (cast_marco, study_man),
`belly.py` (the belly region on a saved blend: extent, weight above the nipple line, check_placement; with
`BELLY_UPPER=1 BELLY_H=lo,hi` it patches the registry's belly to hang from above with that zone).

## F: `[flesh] overrides` (character-pipeline 0.14.0)

`[flesh] overrides = { <type or region> = { <jiggle parameter> = <number>, ... } }` - spec.Flesh.overrides, checked
by `_check_overrides` (the key a type in `types` or one of its sides; the parameters from FLESH_OVERRIDE_KEYS,
finite numbers 0 or more, a frequency over 0; anything else a SpecError - a value that is not a table first
crashed the parser with a TypeError, and nan, inf and frequency 0 got through (critic; fixed, and pipeline_woman
records those refusals too), passed to `flesh.prepare(overrides=)`, which `jiggle_block` already
applied over the material. The flesh stage's hash covers the raw `[flesh]` section, so an override edit reruns flesh.
pipeline_woman's spec carries `butt = { frequency_hz = 3.0, damping_ratio = 0.3 }` (its manifest shows 3.0 / 0.3 on
both butt regions) and four must-refuse parses: a type the spec does not ask for, a key that is no parameter, a
value that is not a table, a number that is not finite.

## The belly was the real blocker

Overrides alone would not give Marco a belly: probing it, his belly region still ran 0.92-1.31 m with weight over
0.5 up to 1.305 m, 85 vertices above the nipple line (research cause 2, "chest and stomach as one slab"). study_man's
was the same, its bone at chest height (tail 1.225 m) - NEXT.md Step 4's "peak_m on an athletic belly".

Probe (`belly.py`, patched registry):

| belly | Marco: weight above nipple line | Marco: check | study_man: tail z | study_man: above nipple line |
|---|---|---|---|---|
| zone 0.2-0.75 (shipped), plateau | 1.0 | - | 1.225 (chest) | 0.92 |
| same zone, hangs from above (breast distances) | 0.07 | fails: 0.79 at 10 cm above | 1.225 | 0.92 |
| zone 0.05-0.6, from above, rise to 12 cm, read 15 cm above | 0.00 | ok | 1.036 (abdomen) | 0.00 |
| zone 0.05-0.55, same | 0.00 | ok | 1.036 | 0.00 |

(Row 1 was probed after taking the jiggle weights off rather than restoring the pipeline's saved unfleshed mesh;
the critic, restoring it, reads study_man's tail at 1.209 m and weight 1.0 above the line - the same conclusion.)
Note what made the check pass: at 10 cm above the apex Marco's belly reads 0.79, at 15 cm 0.24 (limit 0.3); the
belly's own `attach_above_m` 15 cm is that choice.

So (follow-through 0.10.0) belly: zone 0.05-0.6 (pubis to lower ribs), `"attachment": "upper"`, and two new per-type
keys - `attach_rise_m` [0.03, 0.12] (the pivot's rise clip; breast and butt keep ATTACH_UP_M, 3-6 cm) and
`attach_above_m` 0.15 (where check_placement reads the weight above the apex; ATTACH_ABOVE_M 0.10 otherwise). A
belly is 25 cm tall: 10 cm above its apex is still belly.

## The belly's limit

The control run (soft_fat defaults via `set=`) failed the jump course's `within_body`: the belly's limit was the
material's 1.2 x peak_m (0.193 m) against a 0.161 m stand-out, so a jump carried it through the body. Belly now ships
`limit_share` 0.6 (0.097 m on Marco).

## Marco's belly, at 4.5 Hz / 0.6 (research F's values), verify_flesh

| | walk peak | run peak | jump peak | in phase walk / run |
|---|---|---|---|---|
| override | 1.2 cm | 1.3 cm | 8.5 cm (limit 9.7) | 0.99 / 0.97 |
| soft_fat default (control) | 4.6 cm | 6.2 cm | 19.3 cm, FAILED within_body (old limit) | 0.84 / 0.73 |
| research F target / control | 1.2 / 4.1 cm | 1.9 / 5.3 cm | - | - |

Running is under research F's 1.9 cm: the overridden belly also has D's stiffer lower half. All four courses pass on
Marco and on study_man (whose belly, now on his abdomen, runs 0.57 in phase walking).

## Regress

`--quick --jobs 4 --godot`: 12 ok, every Godot check and control ok; six goldens moved and were re-recorded with
`--update --twice`: pipeline_woman (its override and refusals), the sample Figure's belly (new zone: its limit
suggestion tightens under the 0.6 share), the Bloater's belly miss counts (zone size), and the compression shorts and
leggings now measure a `belly` detail region (72 cloth vertices: the lower zone reaches their waistband). Also, all from
the new belly weights (critic): dressed_figure's shirt belly detail 140 -> 199 cloth vertices; small hem, pelvis and
thigh shifts in dressed_skirts; the sports top's cover counts in dressed_presets (hidden 2605 -> 2614, edge 693 ->
684, disagree 18 -> 16); traced_detail's hidden counts (+4 to +6). No pass/fail flips.

## Open

- study_man's spec still carries `limit_share = { belly = 0.4 }`: the critic ran him on the shipped 0.6 and every
  course passes (5.4 % on the limit jumping) - the ship step drops it. study_woman's and Ruth's `may_miss = ["belly"]`
  stay: their bellies are still missed, now for "peak below threshold" rather than "claimed by breast" (study_woman
  by 0.0001 m - a knife edge); the game specs' comments saying the breast claims it are out of date.
- Belly weight stays full below the apex down to the pubis (Marco 0.845 m, below the hip joints, with a 0.61 step
  across one edge at 0.83 m) - no worse than before, unexamined.
- Every `[flesh]` spec's hash changes once (the parsed section now carries `overrides`, empty or not); this release
  reruns flesh anyway.
- `registry.define` (teaching a type) takes no `attachment` / `attach_*` keys, so a taught type cannot hang from above.
- The belly's frequency default is still soft_fat's (a breast's tissue); a belly material, or override guidance by
  build, is not done - a spec chooses.
- The zone 0.05-0.6 was chosen on two men; a woman's belly under the breast zone (breast is looked for first) is
  unmeasured beyond the missed-and-allowed cases.
