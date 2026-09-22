# wardrobe-apex-cover (found by flesh-graded-pivot)

2026-09-18, one agent in the main session; branched from `flesh-graded-pivot` (the flesh change that exposed it).
Scratch `%TEMP%/rw/wac/`: `repro.py` builds traced_detail's setup (sample Figure, flesh.prepare, the fixture's
own `emboss`, the shipped sports_top) and dresses it; earlier versions traced cover and each lift round.

## The failure

With graded breast weights (flesh-graded-pivot), `traced_detail` failed: `top_compressed.passed` False, "cover: 274
drawn body triangles still lie over the cloth after lifting it", and in Godot `verify_wardrobe traced_detail`
poke 0.532 % (65 skin verts through the garment at frame 48; was 0.000 %).

## What it was not (three wrong turns, 40 min)

1. **The bump at the apex.** traced_detail embosses at "the vertex where its jiggle weight peaks"; graded weights
   moved it from the cleavage (x = 0.024 m) to 1.9 cm from the apex. The hypothesis "a compressed top cannot hide
   a bump at the apex" was wrong: every vertex within 3 cm of both bumps was hidden (24/24 on the left).
2. **Skin disagreeing with the cloth's weights** round the apex: 22 disagreeing vertices, fewer than legacy's 39.
3. **`settle` sinking the cloth inside drawn skin at the armhole** (a post-settle floor hold): no change at all.

## What it was

Tracing each lift round: every flagged triangle sat at the shoulders (z 1.30-1.42, x +-0.2), none at the bumps;
18 -> 30 -> 61 -> 192 -> 274 over four lifts, corners 14-28 mm "over" the cloth. Each flagged skin vertex faced
forward and down; the cloth face it was measured against was the armhole's rim, 0-1 cm from the garment's edge,
facing sideways - normals 120-130 deg apart. Skin beside an opening, not skin through the cloth. `cover.compute`
already refuses cloth turned against the skin (`hit[1].dot(n) < 0` for cloth under it); `drawn_over_cloth` did not
ask, so each lift turned more rim toward more skin.

Why the flesh change reached it: the shirt's sleeve cut drops skin whose arm-bone weight is over 0.25. The old
plateau breast weight (0.4-0.6 up to the collarbone) had scaled that skin's arm weight down; with graded weights
the armhole sits where the arm starts, beside that skin. Legacy flesh had the same false positive in miniature (4
triangles, 6-9 mm), which one lift happened to clear.

## Fix (wardrobe 0.5.2)

`cover.drawn_over_cloth` counts a corner only where the cloth's face and the skin's normal have a dot of at least
`FACING_MIN` = 0.3 (compute's rule for cloth it reaches ahead of the skin). 0 was tried first: top_compressed
passed, but top_pressed still ran away at the right armhole, whose rim faced its skin at dots 0.01-0.22, while
genuine corners through the cloth over the pressed bumps measured 0.72-0.93. `WD_LEGACY_OVER_CLOTH=1` drops the
test; traced_detail records `control_top_no_facing_test` (passed False, 4 lifts, 274 triangles).

| repro | passed | lifts | folded faces | sharp edges |
|---|---|---|---|---|
| graded flesh, fix | True | none | 0 | 10 |
| graded flesh, control | False (274) | 4 | 4 | 64 |
| legacy flesh, fix | True | none | 0 | 7 |

top_pressed with 0.3: 8 -> 5 -> 0 triangles, all at the bump, two lifts, no folded faces.

## Regress

`--quick --jobs 4 --godot` on this branch (flesh-graded-pivot + this): 12 fixtures ok, every Godot check and
control ok, `verify_wardrobe traced_detail` poke back under its line. Six fixtures changed (every fleshed body);
goldens re-recorded with `--update --twice`. Pass/fail flips, all reviewed:
- top_compressed: lifts gone (it needed none; the 4 legacy triangles were the same false positive).
- top_pressed_cone_lift fails its detail limit (breast 0.224 mm, limit 0.1): the per-corner cone lift, kept in
  the fixture to show why the smooth lift ships, traces the bump now that it sits at the apex. Not shipped.
- pipeline_woman's placement control now also names the chin (the legacy tail went to 1.498 m).

## Open

- **lookdev selftest flake**: one `--jobs 4` run had `close-shot --label inside ... LABEL_OVER_HEAD` pass (20/21);
  two runs of pipeline_woman alone and the next full run passed 21/21. Marginal under load; not this branch.
- Ruth's nipples through her long-sleeve top (NEXT.md cast review) is a different mechanism (a loose top cut
  from the skin) and is not addressed here.
