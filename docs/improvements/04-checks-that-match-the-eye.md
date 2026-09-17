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
  Cells are 320 px tall plus a label band (14%) and a ground band under the floor (4%), at least 0.6
  as wide as tall. A flat body's three-quarter view is from above (`three_quarter_above`): the starfish and the cricket.
- Goldens record, per fixture, the png names, that they match the reported count, the `.gdignore`,
  `review.json`, scale, cell and contact sizes, the frames drawn, and per strip `cells_with_body` and
  `distinct_cells` - not pixel hashes. All 8 of 8 in every strip of every fixture, stable under
  `--twice`.
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

### d. Numeric guards distilled from critic findings

Whenever the critic catches something twice, turn it into a check, as `arm_pose` was. Candidates
already known:

- `hand_rise` above the chest during a walk. **Done.**
- Garment *detail*: the curvature of cloth over a region against the curvature of the skin under
  it. A compression garment should smooth, not trace.
- Flesh limits from self-test time-on-limit. Feed the Godot self-test's per-region
  "on the limit %" back to follow-through as a suggested `max_offset_m`.

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
5. **Garment detail check** in wardrobe. Compare mean-curvature variance of the cloth against the
   skin under it, per region. Add a `smooth` option to `fit.ease` (Laplacian smoothing of the cloth
   offset over the bust and seat) so a sports top reads compressed. Presets opt in (see 05).
6. **Flesh limit suggestion.** The Godot self-test prints time-on-limit; add
   `follow_through.flesh.suggest_limits(report)` that maps it to `max_offset_m`. Also fix the
   buttock peak measure: it read 3.7 cm on a clearly full seat. Measure it against the lean
   envelope from behind, not along the region normal.

## Done when

- Belle's wardrobe verifier passes crouch, crouch walk and jump. Or it fails only on holes that a
  render shows as visible skin.
- Every character export writes a review sheet at a shared scale, with no extra calls.
- The motion critic, run on the pre-fix Walter and Tomas-run strips, flags the reaching arms and
  the neck-height hand. On the fixed versions it passes them.
- The sports top reads as compressed in close renders, and a detail check reports it.
