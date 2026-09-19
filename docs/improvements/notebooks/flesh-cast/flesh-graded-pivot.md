# flesh-graded-pivot (research-flesh-jiggle.md items B and C)

2026-09-18, one agent in the main session. Scratch `%TEMP%/rw/fgp/` (game copy `game/` from this worktree with
cast_mei, cast_ruth, cast_marco, study_woman, study_man). Probe: `probe_bc.py <figure|blend>` (breast and butt .L
against a bust / seat point found as the research's land.py does: tail distance, pivot rise, weight at the point,
10 cm above it, on thigh-dominant vertices, and a vertical weight profile); `FT_FLESH_LEGACY_ATTACHMENT=1` for the
old placement.

## What changed (follow-through 0.8.0)

- Registry: breast and butt get `"attachment": "upper"`.
- `flesh._hang_from_above`, called from `_region` for such a type: tail = the apex (mean of the region's most
  outward 5 % among vertices weighted >= 0.5, along its mean normal); head = 2 cm under the lean surface at the
  apex, exactly `rise` above the apex (0.6 x the region's 90th-percentile height above it, clipped to 3-6 cm);
  weight = measured feathering x smoothstep((u - 0.3) / 0.7) along head -> tail x smoothstep((0.5 - leg) / 0.5)
  (leg = the vertex's skin share on a leg: rig-anything's leg `upper` bones and every bone under them),
  normalised so the 25th percentile of the apex's 2 cm is 1. Volume, mass and place still use the ungraded
  feathering (the mass is the whole pad; only how it is carried changed).
- `check_placement` for such a type: `pivot_rise_m` >= 0.03, `weight_at_apex` (mean within 2 cm of the tail)
  >= 0.9, `weight_10cm_above` (max 9-11 cm above the tail within 4 cm horizontally) <= 0.3, `weight_on_thigh`
  (max on vertices >= 0.5 leg-skinned) <= 0.05. Free values.

## Results (probe_bc.py, .L side; new vs legacy)

These re-run flesh on the real blends. **What ships** (the pipeline restores its unfleshed mesh first, the critic's
probe on the pipeline-built blends): breast tail to bust point Mei 3.8 cm, Ruth 3.2 cm, study_woman 0.5 cm - inside
the 4 cm line, with little margin on the cast; pivot 5.8-6.0 cm above the tail; 0.96-1.00 at the bust point, 0.00
10 cm above; butts 0 on the thigh.

| body | tail to landmark | pivot rise | w at landmark | w 10 cm above | w on thigh |
|---|---|---|---|---|---|
| sample Figure breast | 1.3 cm (5.8) | +5.4 (-0.6) | 0.99 (1.00) | 0.00 (0.85) | 0 |
| sample Figure butt | 1.4 (2.6) | +5.8 (+1.4) | 1.00 | 0.00 (0.38) | 0.00 (0.92) |
| study_woman breast | 0.5 (6.5) | +2.8 -> exact rise fix (-3.4) | 0.99 (1.00) | 0.00 (1.00) | 0 |
| study_woman butt | 1.6 (2.6) | +6.8 (+0.9) | 1.00 | 0.00 (0.87) | 0.00 (0.82) |
| Mei breast | 1.9 (5.7) | +4.6 (-1.4) | 1.00 (0.97) | 0.00 (0.87) | 0 |
| Mei butt | 1.3 (5.1) | +4.8 (+0.4) | 1.00 | 0.00 (0.30) | 0.00 (0.64) |
| Ruth breast | 1.6 (8.4) | +4.2 (-1.9) | 0.85 (0.78) | 0.00 (0.99) | 0 |
| Ruth butt | 2.0 (3.0) | +7.0 (+1.1) | 1.00 (0.95) | 0.02 (0.68) | 0 |

Item C's "tail within 4 cm of the bust point", unmet after A, is met on every body.

Pipeline builds in scratch (study_woman, study_man, Mei to=export, Ruth, Marco) pass the flesh stage and its
check. verify_flesh in Godot: full course PASSED on all five; walk/run/jump with `require=within_body` (the ship
step's form, since on_limit's line is drawn on the full course) 15/15 PASSED.

## Dead ends and fixes

1. `_leg_share` from the chains' `kind`: coordinates() names a chain leg by height alone, and on study_woman the
   root-to-spine chain and the fingers came out legs; every bone under `root` counted as leg and her breast and
   butt weights were all 0. Now from rig-anything's limb roles (fallback: thigh-named bones).
2. `w x (1 - leg)`: 0.51 left on the sample Figure's thigh-dominant vertices. Now a smoothstep to 0 at 0.5.
3. Pivot stepped in along a down-tilted normal: study_woman's rise 2.8 cm. Now set exactly.
4. Normalising on the apex's outermost vertices left the seat's 2 cm at 0.80-0.89 on study_man, Marco and
   study_woman's left side (the check failed the builds). Now the 25th percentile of the 2 cm is 1.

## Open

- **The plain jump course now FAILS for Mei, Ruth and Marco** (on_limit 10.6 / 10.9 / 10.2 % against its 10 % line;
  9.9 / 9.9 / 9.2 % before; free peak 0.398 -> 0.417 m on Mei: the tail further out on a raised pivot is a longer
  lever). The ship step runs one-motion courses with require=within_body, which passes, and the full course passes;
  but the jump course's own on_limit verdict flipped from pass to fail. study_man's butt already failed it on main (16.3 %,
  unchanged). D (a stiffer spring below rest) is the fix.
- The cleft: research B wants both sides about 0.5 there; each vertex still goes to one side.
- The fold's hinge is the measured feathering (Ruth's breast 1.00 at 3 cm below the apex, 0.06 at 6 cm); no
  check reads a fold landmark.
- Marked regions go through the same grading (marks.regions calls _region with the type's entry); no marked build
  was tried on this branch.

## Regress (--quick --godot, first run): one real failure, found to be wardrobe's

`verify_wardrobe traced_detail` FAILED (poke 0.532 %, 65 skin verts through the garment at frame 48; was 0.000 %)
and `top_compressed.passed` True -> False (`cover: 274 drawn body triangles still lie over the cloth after
lifting it`). Every other Godot check and control ok; 12 fixtures ok, 6 changed (all fleshed bodies).

Cause: traced_detail embosses its 12 mm test bump "at the vertex where its jiggle weight peaks" (ties to the
lowest index). Under the old plateau weights that vertex was breast.L 8843 at x = 0.024 m, in the cleavage,
4.5 cm from the apex (weight 0.84 now); graded weights move it to 8861, 1.9 cm from the apex. The compressed
sports top bridges the cleavage and hid the bump there; at the apex - where a nipple is - it does not. So the
fixture's "compressed keeps a fraction of the relief and passes" held only because the bump was misplaced: the
same wardrobe weakness as Ruth's nipples showing through her long-sleeve top (NEXT.md cast review). Butt bumps
moved 8 -> 9 cm from the tail; the shorts are unaffected.

**That diagnosis was wrong.** The user chose to fix wardrobe first (branch `wardrobe-apex-cover`, notebook
`wardrobe-apex-cover.md`): every skin vertex round both bumps was hidden. The flagged triangles were all at the
armholes, skin beside the rim that `cover.drawn_over_cloth` took for skin through the cloth; the graded weights
reached it by moving the shirt's sleeve cut (the plateau's breast weight had scaled the upper chest's arm weight
under the cut's 0.25). Fixed there (wardrobe 0.5.2); this branch is merged together with it.

## Controls in the suite

`pipeline_woman` records `flesh_placement.hanging` (breast and butt: pivot rise 0.06, weight at the apex 0.99,
0 at 10 cm above and on the thigh) and `control_attachment` (FT_FLESH_LEGACY_ATTACHMENT=1) with ok false on all
four regions: breast pivot -2.9 cm, butt 0.998 at 10 cm above and 0.44 on the thigh.

## Critic (independent, 2026-09-18): mergeable; pass = no on the descriptions (fixed above)

Open, most serious first:
1. **A second `flesh.prepare` on a 0.8.0-built body fails check_placement** (Ruth's butt: 0.57-0.59 at the apex, 0.47-0.50
   at 10 cm above), where a 0.7.0-built one passes. The pipeline restores its unfleshed mesh (`_preflesh`) and is not
   affected; a direct re-run is, loudly. Likely cause: graded weights clip to 1 over a wider patch, and
   add_jiggle_bones takes a w = 1 vertex's other weights entirely, so remove_jiggle_weights can only give it to the
   anchor bone - the leg share the grading reads is lost. Fix with D+E (cap the jiggle share below 1).
2. The plain jump course's on_limit verdict (above).
3. `FACING_MIN` 0.3 is stricter than compute's behind rules (0.0, and -0.2 in a cleft) at the crotch and gluteal
   folds drawn_over_cloth exists for; no case seen on shipped garments at rest (critic: study_woman and Mei in
   compression shorts, leggings, sports top), no fixture covers it.
4. The attachment measures read 0.0 when the tail is inside the body, so `weight_10cm_above` alone cannot catch
   plateau weights (the control still fails on pivot rise and apex weight).
5. pipeline_woman's new control never ran under `--godot` (only in `--update --twice`); low risk.
