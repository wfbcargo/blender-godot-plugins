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
  "on the limit %" back to follow-through as a suggested `max_offset_m`. **Done** (step 6, branch
  `flesh-limit-suggest`).

## Steps

1. **wardrobe coincident class.** Implement the nearest-point distance to the skinned garment
   triangles (per sampled frame, or only for hole candidates for speed), add
   `COINCIDENT_MAX` (default 0.003 m), and report `coincident` separately.
2. **Re-run Belle's verifier.** Crouch, crouch walk and jump should pass on holes if the
   screenshots are right. If not, the remaining holes are real: render them.
3. **Review sheets in export.** Add a `review=True` flag to rig-anything `export.export` (or to the
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

   **Done, flesh part (branch `flesh-limit-suggest`).** The buttock measure was already fixed in 05
   5.9, and that fix was confirmed rather than redone. `butt` has `"lean": "profile"`: the silhouette
   behind the hip joints, read from the side. Belle's seat reads 7.8 cm, not 3.7.

   What shipped:
   - **Godot measures.** `JiggleModifier.measure_limits()` / `limit_report()` /
     `print_limit_report()` report, per region:
     - the share of ticks within 1 mm of the limit (belle_demo's test);
     - contacts and the longest contact;
     - an unlimited shadow spring's peak and demand curve;
     - a **ladder**: the same share measured on 33 shadow springs at 2^(k/8) times the limit.

     The load comes from the skeleton, never the flesh, so a rung is exactly what that limit would
     do. The region's own rung matched its share to the tick. `verify_flesh.gd` drives a body round
     a fixed 13.6 s course and prints `FT_FLESH_LIMITS {json}`: walk, stop, turn, run, stop, two
     0.55 m jumps, at belle_controller's `ACCEL` and jump speed.
   - **Blender suggests.** `flesh.suggest_limits(report)` keeps a region inside 3-9% of ticks on the
     limit. Outside the band, it takes the measured rung nearest 6%. `.L`/`.R` pairs get one limit.
     A share that falls across the band between two neighbouring rungs takes the looser one
     (`cliff`), and a band past the ladder's end takes the end and says to run again. A type's
     `limit_max_share` caps a raise (breast 0.66) and is reported `capped`. `flesh.apply_limits`
     writes the result into the spec. Old `FLESH` self-test lines get an estimate.
   - **Band.** The 9% upper edge sits under the self-test's 10% failing line. At that line Belle's
     5.8 cm buttocks (11-12%) were rejected, and her accepted regions sit at 7.5-9.0%, about 0.3
     points apart between runs. The 3% lower edge comes from the course: below it, only the jumps
     touch the limit (the sample bodies' shipped limits: 0.5-1.2%, 4-7 contacts of 1-3 ticks, every
     one a jump). Belle's shipped limits read 4.4-4.9% on the course at her response of 1.5, inside
     the band, and are kept.
   - **Converged.** Suggestions were applied in Blender, exported and re-run with no override:
     - Figure: every region inside in one step. Arm flab went from 88-91% (held for 3 s) to
       5.6/4.8%, breasts from 1.1/1.2% to 5.4/3.4%.
     - Bloater: two steps, because its love handles started at 21 cm, past the ladder. Every region
       ended at 3.4-7.2%.
     - At response 1.5 both settle in one step. The Figure's breast.L stays at 11.9%, `capped` at
       0.66 x peak.

     Numbers are in `follow-through/references/flesh.md` "Swing limits from Godot".
   - **Golden:** `flesh_figure` gains `bodies.Figure.limit_suggestion`: a made-up ladder report for
     the Figure's regions that takes every branch, suggested and applied after the export. Nothing
     else moved.
   - **Not done:** belle_demo.gd's self-test (grungist-creek) does not call `measure_limits` yet. The
     registry's `limit_share` values are unchanged. `regress.py --godot` does not run
     `verify_flesh.gd`.

## Done when

- Belle's wardrobe verifier passes crouch, crouch walk and jump. Or it fails only on holes that a
  render shows as visible skin.
- Every character export writes a review sheet at a shared scale, with no extra calls.
- The motion critic, run on the pre-fix Walter and Tomas-run strips, flags the reaching arms and
  the neck-height hand. On the fixed versions it passes them.
- The sports top reads as compressed in close renders, and a detail check reports it.
