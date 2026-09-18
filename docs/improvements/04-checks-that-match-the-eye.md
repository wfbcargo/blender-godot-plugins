# 04 - Checks that match the eye

Category: **3 checks that disagree with the eye**.

## Problem

Numeric checks and renders disagreed in both directions, and each disagreement cost a round of
rebuilds and manual image review.

- **Passed, but looked wrong.**
  - Walter's arms reached forward with near-straight elbows. Tomas's run hand sat at neck height.
    Every clip passed floor, slide, balance and clearance until a person looked at 8-frame strips.
    (Fixed after the fact with `verify.arm_pose`: `hand_rise`, elbow range, upper-arm angle.)
  - The realistic Belle's sports top is skin-tight and shows anatomical detail.
- **Failed, but looked right.** wardrobe's `verify_wardrobe.gd` failed Belle's crouch, crouch walk
  and jump on holes (0.64%, 0.64%, 1.07% against a 0.5% limit). The screenshots show no gap. The
  cloth is pressed flat into the front hip crease, so the ray from a hidden body vertex finds no
  cloth within reach. More ease (12 mm) made it worse.
- **Measured wrong.** follow-through measured Belle's seat at 3.7 cm out, so the buttocks limit had
  to be tuned by running the Godot self-test repeatedly.
- **No standard review material.** Renders were ad hoc per session: different scales, frames and
  views, taken only when someone thought to.

## Design

### a. wardrobe hole precision

In `godot/addons/wardrobe/verify_wardrobe.gd`, a **hole** is currently a hidden body vertex whose
outward ray (`UP_REACH` 0.12 m) finds no cloth and that has no cloth within `BEHIND_HIDDEN` 0.06 m
behind it. A fold is excused only if a second ray hits the body.

Add a **coincident** class: cloth whose surface lies within a small distance of the skin (for
example 3 mm, or within the garment's ease) in *either* direction, measured by nearest-point
distance to the skinned garment rather than by a ray along the body normal. A ray at a crease runs
tangent to the pressed cloth and misses it.

Report three counts: `holes` (skin visible), `coincident` (cloth pressed onto skin; a z-fighting
risk, not a hole) and `poke`. Only `holes` and `poke` count against the limits.

To confirm a real hole, render the flagged vertex from outside with the garment drawn. If skin
pixels show, it is a hole.

**Done in wardrobe 0.2.1, not as designed above.** Measured before building: the tangent-ray
crease was not the cause. Of the 9 holes in Belle's worst crouch frame, the normal line crossed
cloth at 0.01-0.4 mm for 1 (rays started 0.5 mm off the skin, both ways, and stepped over it), and
not at all within 15 cm for 8 - belly under the waistband, shut in by the raised thighs 13-25 cm
off, beyond the 12 cm body test. Two more a frame slipped between faces at a fold (a 1e-3
barycentric edge tolerance). A nearest-point `coincident` class would have fixed only the first.
What shipped:
- lines start at the skin, with a 1 mm edge tolerance;
- `coincident` (cloth within 3 mm, either side) is reported, not limited;
- hidden skin with no cloth on its normal is looked at from 48 directions within 80 degrees, 50 cm
  out. It is a hole only if a view reaches it past drawn skin and outward-facing cloth and past it
  sees the inside of the body or nothing; otherwise it is `occluded` (reported). Skin in front of
  cloth shows the cloth: 3 breast vertices on the jump were that until the look-back was added;
- `cut=` removes a patch of the garment as a control (in the harness on `dressed_figure`), and
  `shot=` renders a frame's holes in the frame that was measured, body back faces magenta.

Belle, 7 clips x shorts, top and both, 240 frames: all pass at 0.5% (worst 0.38%, shorts walk).
The holes left were rendered and are real: a waistband gap on the walk (magenta through it) and the
top's hem standing off the breast on the jump (background through it). Cutting 6 triangles from
the shorts fails at 0.57%.

### b. Automatic review strips

Every export also writes a **review sheet**: `views.render_clip(..., frame_height_m=<shared>)`
strips of 8 evenly spaced frames per clip, from the front, right and three-quarter views. It is
workbench-lit and the same scale for every character. It goes to
`<out_dir>/review/<clip>_<view>.png` plus one `contact.png` montage.

Characters then line up, regressions can be diffed visually, and the critic below has a fixed input.

**Done (rig-anything `review.py`, character-pipeline `review` stage), branch `review-strips`.**
- `export.export` writes the sheet after the glb is verified unless `review=False`, so
  `export_character`, `hop.export_creature` and `radial_moves.export_creature` all do. It goes to
  `<glb folder>/review/<glb name>/`, not `review/` itself: `flesh_figure` exports two bodies into one
  folder and their `contact.png` would collide. `review/` gets the `.gdignore`. A failed sheet is
  `review.error` in the manifest (and a `problems` line), not a refused export.
- The pipeline's export stage turns rig-anything's sheet off, and the `review` stage renders the
  character dressed: every mesh bound to the rig, garments in their own colours, into
  `<export dir>/review/<id>/`. Spec `[review] enabled / frame_height_m`, hashed on its own. It raises if
  a cell shows no body.
- One render per strip: the 8 frozen poses stand side by side along the ortho camera's right axis.
  Seconds added per export, measured in the fixtures with two Blenders running at once: 4.2-4.7 s
  for one clip (mostly the first render's start-up), 2.1 s (Bloater, 2 clips), 6.6 s (pipeline woman,
  3 clips, dressed), 8.1 s (mpfb woman, 6), 9.0 s (cricket, 5), 9.6 s (dog, 5), 10.4 s (rabbit, 6),
  15.6 s (Rigify figure, 10). A full `regress.py --twice --jobs 2` with the sheets took 17 minutes on the shared machine.
- Scale: 2.1 m for an upright body (taller than twice its depth along `forward`); otherwise the smallest
  rung of `0.05 ... 12 m` holding 1.15 x its size: cricket 0.05, starfish 0.35, rabbit 0.75, dog 1.5.
  Cells are 320 px tall plus a label band (14%) and a ground band under the floor (4% at rest, grown
  by what the poses need), at least 0.6 as wide as tall. A flat body's three-quarter view is from
  above (`three_quarter_above`): the starfish and the cricket.
- Goldens record, per fixture, the png names, that they match the reported count, the `.gdignore`,
  `review.json`, scale, cell, band and contact sizes, the frames drawn, and per strip `cells_with_body`,
  `distinct_cells`, `edge_cells` and `centred` - not pixel hashes.
- **Review fixes.** `distinct_cells` first hashed each cell's bytes, and Blender's default render dither
  (1.0) changed ~43k pixels per cell by up to 2/255, so a clip of 8 identical poses reported 8/8: the
  check could not fail. The sheet now renders with `dither_intensity = 0` and counts cells unlike every
  earlier one by more than 12 pixels over 10/255. The new `review_sheet` fixture (a box on one bone)
  records a `Static` clip at 1 in every view, a `Tilt` at 8, and a `Travel` clip at 8 with 4 `edge_cells`
  drawn in place but 1 and 0 centred. On the export fixtures the honest counts are lower where frames
  barely differ: cricket Idle front and JumpLaunch (all views) 5, dog Idle front/right 5, rabbit Idle
  front 4 and JumpLaunch 5, starfish Crawl 5; the humans stay 8.
  Travelling or stretching clips spilled into the next cell (cricket JumpLaunch right, f10 over f9).
  Every clip is now evaluated before rendering; a strip whose poses leave the rest body's cell has each
  frame's extent centred in its cell (`centred`, `(each frame centred)` in the heading, `centre_poses=False`
  to turn it off) and the cells widen to the widest centred pose. `edge_cells` (a body touching its cell's
  side) is 0 in every strip of every fixture. Centred: cricket JumpAir right/above, JumpLand right,
  JumpLaunch right/above; rabbit JumpLaunch right; Rigify Slide, SlideRecover and SlideToCrouch right.
  Cricket cells 265 -> 294 px wide; no other fixture's cell moved. Labels and floor now sit in front of
  the nearest pose, so a clip travelling toward the camera cannot cover them. Sheet seconds did not rise
  (cricket 10.4 -> 7.9, Rigify 18.1 -> 12.9 on a shared machine).
- **Review fixes, second round.** The same bug as the horizontal one, downwards, and it had been
  measured as clean. The frame's height came from the rest pose alone plus a fixed 4% ground band
  (13 px of a 320 px cell), and `edge_cells` looked only at each cell's left and right columns. So the
  rabbit's `JumpAir` (front, right, three-quarter) and the cricket's (front, right) drew 28-51 body
  pixels on image row 0 - the legs that go through the floor, clipped by the frame edge, in the very
  clips whose purpose is to show a foot through the floor - and the goldens recorded `edge_cells` 0.
  Now every view carries a screen-up axis (world Z when level, tilted for `three_quarter_above`), each
  evaluated pose's reach past the cell is measured along it, and the bands above and below the cell
  grow in whole pixels at the same metres-per-pixel: the shared scale, the cell and the floor line do
  not move, the picture is taller, and the rest ground band is left over as the margin. `bands_px`
  [label, above, below] is in `review.json`, the manifest and the goldens: rabbit [45, 0, 46] (strips
  378 -> 411 px tall, contact 1162 -> 1258), cricket [45, 0, 58] (378 -> 423, contact 969 -> 1079),
  every human and the dog unchanged at [45, 0, 13]. A band grows to at most 2 cell heights
  (`GROW_MAX`), so a runaway root cannot render a picture thousands of pixels tall; past that the pose
  really is outside and `edge_cells` says so. `edge_cells` now counts a body touching any edge of the
  strip, bottom and top included, and is 0 in every strip of every fixture; the pipeline's `review`
  stage raises on it, as it already did on a cell with no body. Re-measured from the pixels over both
  passes of the whole run, 0 strips touch an edge, against 8 before (rabbit `JumpAir` front/right/
  three-quarter in each of its two sheets, cricket `JumpAir` front/right) carrying 28-51 body pixels
  on row 0. The `review_sheet` fixture gains a `Dip` clip - the box sinks 0.35 m through the floor,
  then rises 0.9 m above where it stands - rendered as its own `spill` sheet, because the bands are
  one height for a whole sheet: `bands_px` [45, 81, 57] against the resting [45, 0, 13], strips 503 px
  tall, `edge_cells` 0. The fixture's `centred` sheet goes to [45, 0, 23] (388 px): `Tilt` leans a
  bottom corner 0.059 m below the floor, which the rest frame's 0.042 m did not hold.
- For 04 c, scratch strips of Walter's walk and Tomas' run: the committed glbs from grungist-creek
  `5379d5e` (before the upper body moved into rig-anything) and `ed654b0` (now), and Walter and Tomas
  re-authored on today's baked bodies with rig-anything `bc1ef67^` (pre-fix) and `bc1ef67` (the arm
  fix) and `2e451d9`'s build options. The pre-fix rebuild reproduces the finding: today's
  `verify.arm_pose` fails Tomas' run at hand_rise 0.72 (the commit's number) and Walter's walk
  reaches forward with straight arms; the `bc1ef67` builds pass (0.47). The `5379d5e` glbs do not
  show the reaching arms - that state was never committed as a glb.

### c. Motion critic

Model it on humancheck's critic: `humanform/references/critic-checklist.md`, invoked from
`humanform/skills/humancheck/SKILL.md:74-89` as a subagent that writes its questions before opening
the images and returns JSON. Add `animate-anything/references/motion-critic-checklist.md` with yes/no
questions per clip type.

- **Walk and run:**
  - Do the arms swing opposite the legs?
  - Are the hands between hip and chest?
  - Are the elbows bent more when running?
  - Is the head level?
  - Do the feet land under the body?
- **Idle:** do the arms hang with gravity, relaxed and not reaching?
- **Posture:** does the stoop read in the direction the brief says?
- **Crouch and jump:** are the feet flat, knees over the feet, no body part through the floor?
- **Outfit:** is the covered area covered in every frame? Is there no skin-through-cloth, and no
  cloth reading as painted skin?

The critic compares against the previous version's sheet. Keep a change only if the numeric checks
held and the critic prefers it.

**Done (animate-anything, branch `motion-critic`).**
`animate-anything/references/motion-critic-checklist.md` is humancheck's protocol pointed at motion,
and SKILL.md's "The motion critic" has the Agent call, the keep-or-revert rule and the
flagged-twice-becomes-a-check rule. What the checklist adds beyond the questions above:

- **Severities that aim a fix**: `gross` (floor, skating, a limb through the torso), `carriage`
  (arms, head, spine held wrong), `timing` (contacts, swing, flight), `outfit`, `brief`.
- **Locked numbers for keep-or-revert** are the manifest's `clip_checks` and `arm_pose`, and a
  critic that prefers B while a check that passed now fails does not carry. The rule is pairwise, so
  everything it locks has to outlive the run that produced it: `export_character` now writes
  `arm_pose` (per clip, per arm) into `.moves.json` beside `clip_checks`, where it previously
  reached only the in-memory build report and died with it. Nothing outside those two files is
  lockable, and the checklist says so.
- **Three blind spots written down**, because each produces a confident wrong answer: a side view
  cannot tell the near arm from the far one, 8 samples alias against a 24-frame run's flight phase,
  and `centred: true` makes travel unreadable from cell positions. Alternation is a front-view
  question with **no** numeric fallback - `arm_pose` keeps each arm's range over the whole clip, not
  per-frame angles, and two arms in opposite phase sweep the same range (the export fixtures'
  `arm_carry_deg` comes out identical for L and R on `mpfb_woman_curvy`'s three clips and within
  1.1 degrees on `rigify_human`'s four, all of them alternating) - so the checklist says answer it
  from `front` or answer `unclear`.
- **Pairwise only when the sheets line up**: same `ortho_scale_m`, `cell_px` and `frames`.

**Validated on the four sheets, questions first.** This session had no Agent tool, so the protocol
was run by hand in its own order: the 32 questions were written from the two character specs and
`review.json` alone and saved to disk before a single png was opened
(`scratchpad/wf2/critic/questions.md`), then the strips were read in the recorded order. Verdicts in
`scratchpad/wf2/critic/verdicts.json`.

- **Pre-fix Walter walk and idle: flagged.** Five `carriage` answers - the arms are held out in
  front through all 8 cells, on near-straight elbows, hands past the leading knee, at rest too.
  Worth noting for step d: the critic *also* read `hand_rise` (-0.35 to -0.20, nothing like the 0.7
  limit) and reported it as passing. The eye and the number disagreed, and the eye was right.
- **Pre-fix Tomas run: flagged.** The forward hand at armpit height at f10 and f13, `hand_rise`
  0.715 against the 0.65 limit agreeing.
- **Both fixed versions: passed**, `preferred: B` on both pairs, no `gross` or `carriage` answers
  left. The committed `ed654b0` glbs match their arm-fix rebuilds cell for cell.
- The elbow question came back `yes` on the pre-fix run (flexion 67-83 degrees): the arm was raised,
  not thrown straight, so `RUN_ELBOW_OPEN` is not what that clip trips. The protocol reporting a
  number that passes is the point, not a miss.

Comparison images at the fixed camera, pre-fix over fixed:
`scratchpad/wf2/critic/renders/{walter_walk_right,walter_idle_right,walter_walk_front,tomas_run_right,tomas_run_front,tomas_walk_right}_prefix_over_fix.png`,
plus `{walter_walk_right,tomas_run_right}_fix_over_current.png`.

### d. Numeric guards distilled from critic findings

Whenever the critic catches something twice, turn it into a check, as `arm_pose` was. Candidates
already known:

- `hand_rise` above the chest during a walk. **Done.**
- **An arm carried out in front instead of swung. Done (`verify.arm_swing`, branch
  `motion-critic`).** This is the one the critic found twice - Walter's pre-fix walk and his idle -
  and the one `hand_rise` cannot see, because those hands were at hip height, not chest height.
  `arm_pose` now also reports `arm_carry_deg`, the whole arm's angle from gravity (the palm seen
  from the shoulder), which reads the same on a stooped body as on an upright one; the upper arm's
  own angle does not. `verify.arm_swing(carry, running)` fails a **non-running** clip whose arm
  swings `SWING_MIN_DEG` = 8 degrees or more and still never comes back within
  `SWING_RETURN_DEG` = 2 degrees of hanging.

  Both lines were measured, not chosen. Over the 49 clips of the 17 committed characters
  (`assets/humans/*`, Belle), with `running` taken from each gait's `duty_factor`:

  | | swing (degrees) | nearest hanging |
  |---|---|---|
  | 17 idles | 2.0 - 2.1 | +0.1 to +11.8 |
  | 17 walks (checked) | 13.6 - 63.5 | **-17.5 to -3.9** |
  | 11 runs and Belle's trot (not checked) | 46.7 - 53.7 | +1.2 to +6.7 |
  | pre-fix Walter walk (flagged) | 16.7 | **+8.8** |

  So the swing gate at 8 sits between an idle's 2.1 and the tightest walk's 13.6, and the return
  line at 2 sits between the tightest shipped walk (Margaret's elderly shuffle, -3.9) and the
  pre-fix walk (+8.8) - 5.9 and 6.8 degrees of margin. Every shipped walk passes; the pre-fix walk
  fails on both arms. A run keeps both arms in front by design (1.2 at the back of the stroke) and
  is guarded by `hand_rise` and the elbow instead, which is why `running` clips are left out.

  `arm_pose` is reached only from `upper.author_clear`, so only idles and gait clips are ever
  checked: a crouch or a jump, whose arms legitimately come forward, is never seen by it.
- **Proposed, not added: an idle's forward carry.** The critic flagged Walter's pre-fix *idle* too,
  and the swing gate leaves it out (2.0 degrees of motion). The numbers do not support a line yet:
  the 17 shipped idles sit in two tight clusters - 0.1-2.6 degrees (the three stooped elderly) and
  9.2-11.8 (everyone else) - against the pre-fix idle's 13.8-15.8. A threshold would have 2 degrees
  of margin and would be fitted to one generator's output. What would settle it: idles from a
  character whose arms were authored some other way, or a hand-posed reach at a known angle.
- Garment *detail*: the curvature of cloth over a region against the curvature of the skin under
  it. A compression garment should smooth, not trace.
- Flesh limits from self-test time-on-limit. Feed the Godot self-test's per-region
  "on the limit %" back to follow-through as a suggested `max_offset_m`. **Done** (step 6, branch
  `flesh-limit-suggest`).

## Steps

1. **wardrobe coincident class.** Implement the nearest-point distance to the skinned garment
   triangles (per sampled frame, or only for hole candidates for speed), add
   `COINCIDENT_MAX` (default 0.003 m), and report `coincident` separately.
2. **Re-run Belle's verifier.** Crouch, crouch walk and jump should pass on holes if the
   screenshots are right. If not, the remaining holes are real: render them.
3. **Review sheets in export.** *Done - see b.* Add a `review=True` flag to rig-anything `export.export` (or to the
   01 pipeline's `review` stage). Use a shared `frame_height_m` default of 2.1 m for humans, or the
   body size for creatures.
4. **Motion critic checklist** in animate-anything's `references/`, plus a SKILL.md section on how
   to invoke it, copying humancheck's protocol (questions first, JSON verdict, keep-or-revert).
   **Done - see c.** Regression: `rigify_human` drives `verify.arm_swing` over carry angles taken
   from real clips (`ARM_SWING_CASES` - a walk through hanging, Margaret's shuffle as the tightest
   pass, the pre-fix Walter walk, a run, an idle, and the limit itself either side), so the failing
   branch is exercised without a body built wrong. `rigify_human` and `mpfb_woman_curvy` goldens
   gain `arm_carry_deg` and `arm_swing_deg` per arm; no number already in them moved.

   Round 2, from review: `export_character` writes `arm_pose` into `.moves.json` beside
   `clip_checks`, because the keep-or-revert rule is pairwise and every export fixture's golden now
   carries `moves_json.arm_pose_on_disk`, read back from the written file rather than from the
   returned dict - the one thing that would have caught the field never reaching disk. The guard's
   own population was stated as 20 walks in three shipped files against the 17 this table measured;
   it is 17 everywhere now (16 of `assets/humans/*` plus Belle - the other six shipped walks are
   armless creatures).
5. **Garment detail check** in wardrobe. Compare mean-curvature variance of the cloth against the
   skin under it, per region. Add a `smooth` option to `fit.ease` (Laplacian smoothing of the cloth
   offset over the bust and seat) so a sports top reads compressed. Presets opt in (see 05).

   **Done** (wardrobe, with 05 5.3). `fit.detail(garment, body, regions=None, limit=None)` is in
   every `fit.ease` report: per region (`all`, and each follow-through flesh type the garment carries
   weights of), leaving out 3 cm next to each opening,

   - `skin_relief_mm` - how much *relief* the skin under the cloth has (met along its normal 10 cm
     out or 3 cm in, or nearest cloth over its face). `fit.relief` is a surface's height over the
     same surface Taubin-smoothed across 3 cm: a nipple, a navel, the fold under a buttock. A
     breast's or a thigh's own curve survives that reference, so the body's *form* is not counted
     as detail - a fitted garment follows the form by definition.
   - `traced` - the area-weighted slope of the cloth's relief regressed on the skin's relief under
     it, and `relief_mm = traced x skin_relief_mm`, the millimetres a preset's `ease.detail_limit`
     holds; over it, `dress` fails.

   Mean-curvature variance, which this step originally asked for, was tried first and dropped. As a
   *ratio* of cloth variance to skin variance it measures the cloth's own faceting - a few
   hundredths of a millimetre left by the nearest-point projection, at the same scale as the detail
   - divided by however much relief the body happens to have, so on a smooth body it reports noise
   against nothing: the sample figure's nipple-less breasts read 0.82 eased and 0.74 compressed
   against a 0.35 limit, and every preset's limit had to be waived by a `quiet` rule for the only
   bodies the fixtures measure. A regression does not have that failure: faceting is uncorrelated
   with the skin, so it does not move the slope, and millimetres do not divide by the body.

   Measured: on the sample figure `shorts_mid_thigh` carries 0.054 mm over the buttocks and
   `compression_shorts` 0.008. On the curvy MPFB woman the sports top went from 0.13 mm (skin
   relief 0.49 mm) to 0.00 mm. The `traced_detail` fixture embosses that figure with 12 mm bumps so
   the limits bite: the sports top carries 0.192 mm uncompressed and 0.025 mm compressed, the
   shorts 0.258 mm and 0.004 mm. That fixture is where the enforcement is exercised - a limit that
   passes for a real reason, two that fail, and one that is `unmeasured`.

   A limited region that could not be measured is `unmeasured` **and a failure**: a limit nothing
   was measured against has not been held (wardrobe 0.2.2 said the same of `verify`). The check is
   only as good as the flesh it is given, and that is now loud rather than quiet - on a
   character-pipeline MPFB woman a `breast` limit would measure nothing at all, because
   follow-through's breast search lands on the jaw (see 05 5.3).
6. **Flesh limit suggestion.** The Godot self-test prints time-on-limit; add
   `follow_through.flesh.suggest_limits(report)` that maps it to `max_offset_m`. Also fix the
   buttock peak measure: it read 3.7 cm on a clearly full seat. Measure it against the lean
   envelope from behind, not along the region normal.

   **Done, flesh part (branch `flesh-limit-suggest`).** The buttock measure was already fixed in 05
   5.9, and that fix was confirmed rather than redone. `butt` has `"lean": "profile"`: the silhouette
   behind the hip joints, read from the side. Belle's seat reads 7.8 cm, not 3.7.

   What shipped:
   - **Godot measures.** `JiggleModifier.measure_limits()` / `limit_report()` /
     `print_limit_report()` report, per region:
     - the share of ticks within 1 mm of the limit (belle_demo's test);
     - contacts and the longest contact;
     - an unlimited shadow spring's peak and demand curve;
     - a **ladder**: the same share measured on 33 shadow springs, on one grid of limits for every
       region (1 cm x 2^(k/8), the 33 around the region's limit).

     The load comes from the skeleton, never the flesh, so a rung is exactly what that limit would
     do. The grid is shared because paired sides export limits 0.1-0.4 mm apart: on ladders of
     their own, a pair's limit was chosen on shares read between rungs, and across a cliff that read
     was made up (the golden's thigh.R expected 2.7% where its share function gave 1%, and a
     reviewer's pair expected 2.7% at a limit that really sat at 20%). `verify_flesh.gd` drives a body round
     a fixed 13.6 s course and prints `FT_FLESH_LIMITS {json}`: walk, stop, turn, run, stop, two
     0.55 m jumps, at belle_controller's `ACCEL` and jump speed.
   - **Blender suggests.** `flesh.suggest_limits(report)` keeps a region inside 3-9% of ticks on the
     limit. Outside the band, it takes the measured rung nearest 6%. `.L`/`.R` pairs get one limit,
     chosen only on rungs measured on both sides; a report from before the grid gets `interpolated`
     rows that say to run again, and never reads across a step larger than the band.
     A share that falls across the band between two neighbouring rungs takes the looser one
     (`cliff`), and a band past the ladder's end takes the end and says to run again.
     `flesh.apply_limits` writes the result into the spec. Old `FLESH` self-test lines get an estimate.
   - **Never past the body.** The jiggle bone's tip moves by the whole offset, so a limit larger than
     the region's stand-out puts its skin inside the surface it sits on. Every flesh type has a
     `limit_max_share` - `breast` 0.66, `butt` 0.9, the other five 1.0 - and a type the registry does
     not name is capped at `limits.DEFAULT_MAX_SHARE` = 1.0, so none is left unguarded. Over the cap
     the limit is tightened onto the loosest measured rung inside it, but only when that rung still
     keeps the region out of the band's top; otherwise the region keeps its limit, the row is
     `capped`, and it names what to change instead (`response`, `gravity_scale`, `frequency_hz`,
     `damping_ratio`, with the g/(2 pi f)^2 sag spelled out when that is the cause). A pair is chosen
     among the rungs inside the tighter of its two caps whenever one of those puts both sides in the
     band. `verify_flesh.gd` gains `within_body`: a region whose peak offset passed its own stand-out
     fails. Before this, the Figure's 2.2 cm arm flab was raised to 5.66 cm at response 1.0 and
     6.73 cm at 1.5 - 2.6 and 3.1 x - every run, and the run reported PASSED.
   - **A run that measured nothing fails**, as wardrobe's verifier does since 74af7a9.
     `limit_report()` leaves out a region `measure_limits()` never touched, so a self-test that
     prints without starting it emits a report with no regions, and that used to read as
     `in_band: true, settled: true`. The report now carries `measuring`, `regions_total`,
     `regions_measured` and `problems` (never measured) apart from `failures` (measured and wrong);
     `verify_flesh.gd` fails the body on a problem; `limits.suggest` turns a body with no regions or
     a region with 0 ticks into its own `problems` with `in_band` and `settled` false; and
     `flesh.apply_limits` refuses such a suggestion.
   - **Band.** The 9% upper edge sits under the self-test's 10% failing line. At that line Belle's
     5.8 cm buttocks (11-12%) were rejected, and her accepted regions sit at 7.5-9.0%, about 0.3
     points apart between runs. The 3% lower edge comes from the course: below it, only the jumps
     touch the limit (the sample bodies' shipped limits: 0.5-1.2%, 4-7 contacts of 1-3 ticks, every
     one a jump). Belle's shipped limits read 4.4-4.9% on the course at her response of 1.5, inside
     the band, and are kept.
   - **Converged**, with run 2 and run 3 identical (a fixed point, not a walk):
     - Figure at response 1: 7 of 9 regions inside after one suggestion (breasts 1.1/1.2% -> 5.4/3.2,
       butts 0.7 -> 3.3/3.7, belly 1.0 -> 4.9). The arm flab is `capped` - it needs 3.7 cm and stands
       2.2 cm out.
     - Bloater at response 1: 9 of 11 at 3.4-5.5% after two, its love handles having started at
       21 cm, past the ladder. Its arm flab is `capped` too.
     - Following the capped rows' own advice (response 0.3, `gravity_scale` 0.3) the Figure settles
       whole in two runs: every region 4.2-6.5%, `in_band`, `settled`, `FT_SUMMARY PASSED` with
       `within_body` included.

     Numbers are in `follow-through/references/flesh.md` "Swing limits from Godot".
   - **Golden:** `flesh_figure` gains `bodies.Figure.limit_suggestion`: a made-up ladder report for
     the Figure's regions that takes every branch, suggested and applied after the export, with
     `expected_is_true` checking every measured row's expected share against the share function, a
     second body of own-limit ladders for `interpolated` and a third of one region shipped at
     1.2 x peak_m for the tighten-onto-the-cap branch. `bodies.Figure.no_measurement` holds the
     refusals: an empty report and a 0-tick one, and the `ValueError` `apply_limits` raises.
   - **Not done:** belle_demo.gd's self-test (grungist-creek) does not call `measure_limits` yet. The
     registry's `limit_share` values are unchanged, and so is the material default a type without one
     gets, `max_offset x 2 x peak_m` = 1.2 x peak_m - looser than the 1.0 cap, so an uncapped type's
     shipped limit can only be lowered by a suggestion, never raised. Both sample bodies' arm flab
     fails `within_body` at that shipped limit and needs its material retuned (at `soft_fat`'s 2.7 Hz
     it hangs 3.4 cm off a 2.2 cm flab), not its limit. `regress.py --godot` does not run
     `verify_flesh.gd`.

## Done when

- Belle's wardrobe verifier passes crouch, crouch walk and jump. Or it fails only on holes that a
  render shows as visible skin.
- Every character export writes a review sheet at a shared scale, with no extra calls.
- The motion critic, run on the pre-fix Walter and Tomas-run strips, flags the reaching arms and
  the neck-height hand. On the fixed versions it passes them. **Met** - see c.
- The sports top reads as compressed in close renders, and a detail check reports it.
