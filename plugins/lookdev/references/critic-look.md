# Look critic checklist

Questions a round's done-when and its look critic **pick** from, instead of writing them from scratch. Each is
a yes/no question phrased so `yes` is good, and each names the picture or the number that answers it. The
protocol - questions written before any image is opened, `A`/`B`/`same` against the previous version, both
orders of a pair - is `judging.md`'s and humanform's `references/critic-checklist.md`'s; this file is only the
bank. Copy a question with its id and its source; a critic answers `unclear` when the source named is missing,
never from another picture.

## Sources

| name | what | how to make it |
|---|---|---|
| **G:`<view>`** | lookdev's Godot close-shot tile, lookdev materials, a preset's sky | `node <skill>/bin/lookdev.mjs close-shot --project . --glb res://.../x.glb --presets clear_midday,overcast --views head,hands,feet,bust,crotch,full --pair-blender <export dir>/review/<id>/close --out <scratch>` -> `<preset>_<view>.png`, `sheet.png` (one row per view, one column per preset, the Blender tile first with `--pair-blender`), `close.json`. Views: `face`, `face_3q`, `eyes`, `head_side`, `head_back` (`head` = these five), `hand_palm.L/.R`, `hand_back.L/.R` (`hands` = all four), `feet`, `bust`, `crotch`, `full` (at `--full-distance`, 4 m), `bone:<name>`; with `--pair-blender` a paired view is shot at the Blender tile's distance. `--garments a.glb,b.glb` dresses it, `--clip Run --time 0.3` poses it |
| **B:`<view>`** | the Blender close set, the file's own materials, EEVEE | written by character-pipeline's review stage to `<export dir>/review/<id>/close/<view>.png` (+ `sheet.png`, `close.json`); rig-anything `closeups.look_set` elsewhere. Views: `face`, `face_3q`, `eyes`, `head_side`, `head_back`, `hand_palm.L/.R`, `hand_back.L/.R`, `bust`, `under_bust` (a spec wearing a top), `crotch`, `knees`, `feet`, `foot_inner.L`, `foot_outer.L` |
| **hair.png** | humancheck's lit head sheet (1 m row, close row) | humanform `views.hair_sheet(body, out_dir)`, or `humancheck_cli.py ... views=1` on a haired body |
| **tone** | mean albedo per material, `ok` 0.01-0.9 linear | `lookdev.mjs tone --project . --glb res://.../x.glb --material skin` (study_woman's lashes read 0.0073 with no `--material`: name the skin) |
| **capture** | a scene's numbers: clipped %, key-to-fill and key exposure stops, albedo too dark/bright, against `presets/thresholds.json` | `lookdev.mjs capture --project . --scene res://figure_study.tscn --probes --kind day` (`overcast` for overcast) |
| **manifest `skin`** | the bake's `map_px`, `tone_ok`, per-region tones | `<id>.moves.json` beside the glb |

A question marked **G+B** is answered from both tiles of the same view side by side: a defect in G and not
in B was lost between Blender and Godot (the Step 0 baseline found the hair and the brows lost there).

## Question bank

### Hair (the baseline's rank 1)
- **LOOK-H1** At 1 m, does the hair read as hair on a head rather than a helmet - strands and a root-to-tip
  change of tone, not one smooth shell? *G:face* at 1 m, *G:full*; the Blender side *hair.png* top row. G+B.
- **LOOK-H2** Does the hairline read as hair, not a cap edge - tips of uneven length with skin between them,
  no hard cut, spiky fringe or smeared radial gradient? *G:eyes*, *G:face*; *B:face_3q*, *B:eyes*. G+B.
- **LOOK-H3** Is there no hard dark band in front of each ear? *G:face*, *G:head_side*; *B:head_side*. G+B.
- **LOOK-H4** Is the neck under the ear free of a dithered, stippled shadow under clear_midday? *G:face* and
  *G:bust*, clear_midday row (absent under overcast is expected).
- **LOOK-H5** Is a bun, tie or tail attached and shaped like what it is, with no seam at the cap? *G:head_back*,
  *G:head_side*; *B:head_back*, *B:head_side*. G+B.

### Brows, lashes, eyes (rank 2)
- **LOOK-E1** Do the brows read as hair - soft-edged, not hard pixelated black cut-outs - and no darker or
  heavier in Godot than in Blender? *G:eyes* against *B:eyes*. G+B.
- **LOOK-E2** Do the lashes read at 1 m from the front as a fringe, not a few black blocks, with no clump
  spiking over a pupil? *G:eyes*, *G:face*.
- **LOOK-E3** Do the irises have depth - a limbal ring and a pupil that is not a flat black disc? *G:eyes*.

### Skin (ranks 3, 4, 6, 7)
- **LOOK-S1** At 1 m and at full body, does the skin vary in tone by region (redder knees, knuckles and lips;
  paler palms and soles) rather than one uniform colour? *G:face*, *G:hand_palm.L*, *G:full*; the numbers
  in *manifest `skin`* `regions`.
- **LOOK-S2** Under overcast, are the forehead, nose and lips free of hard, mirror-like specular patches (a
  vertical band on the forehead)? *G:face* and *G:eyes*, overcast row.
- **LOOK-S3** Is clear_midday's sheen soft - highlights that roll off, no flat white plateaus? *G:face*,
  clear_midday row.
- **LOOK-S4** Are the finger edges and the thumb web free of coloured lines (orange-red under clear_midday, pale
  under overcast)? *G:hand_palm.L/.R*, *G:hand_back.L/.R*, both rows.
- **LOOK-S5** Are shadowed fingers free of the dither stipple under clear_midday? *G:hand_back.L/.R*.
- **LOOK-S6** Under overcast, does each figure keep its skin tone - not muddy brown (study_man) or grey
  (study_woman)? *G:full* overcast against clear_midday; *capture* with `--kind overcast`.
- **LOOK-S7** Is the skin albedo inside the plausible range and on the brief's tone? *tone* `ok` for the skin
  material; *manifest `skin`* `tone_ok`.
- **LOOK-S8** Does the pore detail still show at 1 m - grain across the skin, not only in highlights?
  *G:face*, *G:eyes*.

### Form seen in the look (with humanform's bank)
- **LOOK-F1** Is the crotch as the spec asks (smooth today; anatomy when Step 3 lands), with no seam or
  stretched texture? *G:crotch*, *B:crotch*.
- **LOOK-F2** Is the surface free of faceting, lumps and seams in every tile? every *G* and *B* tile.
- **LOOK-F3** Is the under-bust free of a shelf bridging under a top? *B:under_bust*, *G:bust* with
  `--garments`.

### The stage and the preset
- **LOOK-P1** Is every tile a picture of its subject - close-shot exited 0, no `EMPTY_TILE`, `SUBJECT_SMALL`
  or `OFF_TARGET` in `close.json` `failures`? *G* `close.json`; Blender set: the review stage passed
  (`close.json` has no `failed`).
- **LOOK-P2** Are exposure, clipping and key-to-fill inside the preset's thresholds? *capture* findings.
- **LOOK-P3** Under golden_hour, is the pale figure not overexposed and the floor free of stripes? *G:full*
  with `--presets golden_hour`.

## Not answerable from these today

- An automatic stipple detector (Step 0.5): LOOK-H4 and LOOK-S5 are eye questions until then.
- Motion (`animate-anything/references/critic-motion.md`), fit (`wardrobe/references/critic-fit.md`), flesh
  (`follow-through/references/critic-flesh.md`), body proportions (`humanform/references/critic-body.md`).
