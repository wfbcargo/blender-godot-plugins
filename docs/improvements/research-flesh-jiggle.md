# Flesh jiggle: what is wrong and what correct looks like

**Status 2026-09-19: A-G are all done, merged and shipped** (follow-through 0.7.0-0.10.0, character-pipeline
0.13.0-0.14.0, wardrobe 0.5.2). What each became, what the critics found and what is still open: NEXT.md "The cast
demo" and the notebooks in [notebooks/flesh-cast/](notebooks/flesh-cast/). Two findings changed the plan: E's premise
("4-5 mm walking") was out of date after B+C, and mass scaling ships off because the swing limit, not the spring,
bounds amplitude; F needed the belly's zone and attachment fixed before an override could help Marco.

2026-09-18, from the user's review of `grungist-creek/cast_demo.tscn` ("jiggle on their mouths", "Marco's chest and
stomach jiggle together, way too much", "breasts and butts don't feel correctly weighted - attachment point and weight
distribution"). Two subagents: a research pass (web sources, and measurements in the built blends and glbs) and a
diagnosis pass (scratch copy of the game, `%TEMP%/rw/diag-cast`, rebuilds and verify_flesh). Scratch scripts:
`%TEMP%/rw/research-jiggle/land.py` (bust and seat points from the mesh), `%TEMP%/rw/diag-cast/diag/headcut.py`.

## Causes found

1. **Breast bones on the face (Mei, Ruth).** The breast zone reaches 1.45 x the hip-to-shoulder span and the
   spine search stops at shoulder height + 0.1 x body height - both above the chin. The chin stands well out of the
   neck's lean envelope, `find_regions` merges every bulging patch in the zone into one region, and the bone goes
   where excess^2 is largest: the chin. Mei's breast bones sat at 1.66-1.71 m with left and right swapped and 131 lip
   vertices weighted 100 % to them (so her lips rode the chest bone even with flesh off); Ruth's heavy weights were at
   1.425-1.47 m. Their breasts did not jiggle at all. study_woman has the same exposure; her larger breasts won.
   No check tests where a bone sits anatomically.
2. **Marco's belly is his whole front torso.** `ft_jiggle_belly` weighted 586 vertices, 0.92-1.31 m, pectorals
   included (514 above 0.5), parented to `spine.003`, 22 cm long; `peak_m` 0.162 m is not a real bulge (the whole
   torso stands out of the lean envelope). It swung 3.9 cm walking, 5.5 cm running: chest and stomach as one slab.
3. **Every region swings 4-6 cm running whatever its size**, and a stomach marked alone still swings 4.1 / 5.3 cm:
   all three bodies use `soft_fat` (2.7 Hz, damping 0.25) regardless of mass, and a spec cannot override it.

**Applied in the game (spec level, commit `72effe5`):** hand-marked `[[flesh.zones]]` on all three (breasts on the
chest: Mei 1.32 m, Ruth 1.19 m; butts marked too, since zones replace the measure); Marco's belly off until the
material can be tuned. Side effect: marked butt regions come out about half the size (Ruth 57 vertices vs 150).

## What correct looks like (cited; inference marked)

- Unbraced D-cup breast displacement relative to the trunk: 4.2 cm walking, 15.2 cm running; vertical is 50-56 %,
  medio-lateral exceeds antero-posterior ([Scurr 2011](https://pubmed.ncbi.nlm.nih.gov/21077006/),
  [Scurr 2009](https://pubmed.ncbi.nlm.nih.gov/20095453/)).
- The nipple traces a figure-of-eight and lags the trunk; unbraced it is in phase only about 66 % of the gait cycle
  against over 90 % braced ([Williams 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11392946/)).
- The spring is asymmetric: 73.5 N/m above rest, 658 N/m below, damping 1.83 / 2.07 N s/m
  ([Cai 2018](https://pubmed.ncbi.nlm.nih.gov/29276070/)). *Inference* (mass 0.3-0.5 kg assumed): about 2-2.5 Hz up
  (damping ratio about 0.17), 6-7.5 Hz down - the breast floats up and stops hard at the bottom.
- Natural frequencies sit in the 1.5-5 Hz band of step rates
  ([FE study](https://www.researchgate.net/figure/The-first-10-natural-frequencies-of-subject-As-breast-determined-with-and-without_tbl1_236066359));
  100 g to 700 g adds 70 % vertical motion running
  ([Haake & Scurr 2010](https://researchportal.port.ac.uk/en/publications/a-dynamic-model-of-the-breast-during-exercise)).
- Buttocks: no gait measurements found; [Dyna](https://is.mpg.de/ps/publications/dyna-siggraph-2015) drives soft tissue
  from body acceleration and limb rotation. Everything below on buttocks is inference.
- Rig practice: physics bones swing about their head toward a tail at the tip
  ([VRChat PhysBones](https://creators.vrchat.com/common-components/physbones/)); Source jigglebones separate a base
  spring (translates the mass) from tip flex
  ([Source SDK](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/public/jigglebones.cpp)).
  *Inference:* breast pivot on the chest wall at the upper pole, bone forward-down to the nipple, weight 0 at the
  upper/inner attachment rising to its maximum at the nipple and lower pole, falling to 0 at the inframammary fold;
  buttock pivot at the upper origin (iliac crest, sacrum), bone back-down to the lower mass, weight 0 at the lower
  back, maximum just above the gluteal fold, 0 at the fold and on the thigh.

## What follow-through does (measured)

- `flesh._region`: tail at the excess^2-weighted surface point; head straight inward by mean excess + half the peak;
  anchor `chest`/`spine.003` (breast), `pelvis`/`spine` (butt).
- study_woman breast: tail 6.5 cm from the bust point, head at bust height 15 cm deep, bone 16 deg up and 32 deg out.
  Weight is a plateau (142 of 259 vertices at >= 0.9), >= 0.92 from 14 cm above the nipple to 4 cm below, then 0 by
  10 cm below.
- Butt (Ruth, study_woman, Mei): tail 2.6-5.6 cm from the seat point, head 13 cm forward at hip-joint height, bone
  straight back; >= 0.9 from 10-12 cm above the seat to 6 cm below; 0.10-0.26 spills 12-16 cm below, onto the back of
  the thigh; the cleft goes 0.96 to 0 within 2 cm. Marco's butt tail sits 8 cm above his seat point.
- `jiggle_modifier.gd`: one isotropic linear spring on the tail's rest-point acceleration, solved exactly; pose aim 1,
  translate 0.35, squash 0.5; `soft_fat` 2.7 Hz, damping 0.25 for every mass; walking moves flesh 4-5 mm.

## Mismatches, ranked by how much each makes it feel wrong

1. Breast bones on the chin (above): rigid breasts and a wobbling chin.
2. Rigid-block weights: upper pole, upper chest and lower back at full weight, so each mass moves as one lump rather
   than deforming from a fixed attachment; butt weight on the thigh creases the fold as the leg swings.
3. Wrong pivot: both bones swing about a point at the mass's own height, so a vertical bounce rocks the upper pole and
   the lower back.
4. Symmetric linear spring: an even rubber bob, where breasts float up and stop hard (Cai); antero-posterior should be
   stiffer than vertical.
5. Amplitude too small walking (4-5 mm against about 4 cm real) and independent of mass.

## Plugin change list (each check measures a bust or seat point from the mesh, as `land.py` does)

| # | Change | Check that proves it | Control that must fail |
|---|---|---|---|
| A | Breast zone top to about 1.0 of the span; `find_regions` keeps the patch nearest the zone centre instead of merging all; `flesh.tissue()` stops at vertices whose strongest non-`ft_` bone is the rig's `head` role (verified by monkeypatch: Ruth 1.09-1.39 m, Mei 1.17-1.47 m, face clean, checks pass) | Breast tail within 4 cm of the bust point, weight there >= 0.8 (Ruth, Mei, study_woman) | Today: 28 cm and 0.00 |
| B | `_region` weights graded along attachment to apex: 0 at the upper/inner edge, 1 only at the apex, a 1-2 cm hinge at the fold; butt weight x (1 - thigh weight), both sides about 0.5 at the cleft | <= 0.3 at 10 cm above the apex, >= 0.9 at the apex, <= 0.05 3 cm past the fold and on thigh-dominant vertices | study_woman today: 0.92 at 10 cm above |
| C | Head on the lean chest wall / sacrum, 3-6 cm above the apex; tail at the apex | Head >= 3 cm above the tail and 1-3 cm under the lean surface | Today: breast head 3 cm below its tail |
| D | `jiggle_modifier.gd` `spring_step`/`_setup`: stiffness split above/below rest along gravity (down about 3x up), antero-posterior about 2x; new `soft_fat` keys in `types/builtin.json` | Kick test: down half-period / up half-period about 1/3 (+-20 %) | Linear spring: 1.0 |
| E | `soft_fat` frequency and response scaled by region `mass_kg`; breast lag in `verify_flesh.gd` | Running course: breast vertical motion several cm relative to the trunk, peaking after it, in phase under about 80 % of the cycle | Today: 4-5 mm walking |
| F | Spec `[flesh] overrides` passed through to `flesh.prepare()` (key in `spec.Flesh`, parser, `stages.run_flesh`), or a belly material | Marco's belly at 4.5 Hz / damping 0.6: 1.2 cm walking, 1.9 cm running (measured with verify_flesh `set=`) | Default: 4.1 / 5.3 cm |
| G | A check that each region's bone and weight centre lie inside its anatomical zone (below the chin, above the fold) | Fails the Step 1 cast builds of Mei and Ruth | - |

Do A and G first: until the bone is on the breast, no tuning of B-E shows.
