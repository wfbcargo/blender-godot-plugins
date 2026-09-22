# Species design: from a description or a concept image to a body that builds

This is how to design **any** humanoid creature for humanform: a dwarf, a troll, or something nobody has named.
You never write a species' ratios by hand. You state what you can see or what you were told (the
**observables**), and `humanform.species_design` does the rest. It fills the gaps from laws, makes every
number agree with every other, and refuses what cannot be built. The seven catalogue species
(`references/species.md`) are worked examples of this method.

```
describe / measure  ->  solve(observables)  ->  design(knobs)  ->  build  ->  check  ->  look
   (this page)           knobs + report         preset JSON       pipeline   humancheck  Godot
```

## 1. Gather the observables

Collect only what you actually know. `solve()` accepts any subset, and **stature is the only one required**.
Where there is a picture, measure on it. A front view and a side view in a neutral standing pose are best. Put
horizontal lines at the floor and the top of the head, and read every height as a fraction of that span.

| observable | what to measure | how, on a picture |
|---|---|---|
| `stature` | floor to vertex, standing, hunch included (m; a number, `[lo, hi]` or per sex) | scale it against a door (2.0 m), a human beside it, or a stated height |
| `heads` | stature / head length (vertex to **chin**, not the jaw's back) | stack the head down the figure. Count fractions: 5.5, not "about 5" |
| `crotch_fraction` | inseam height / stature | the easiest leg landmark on any picture: where the legs part |
| `hip_fraction` | hip-joint height / stature | the widest point of the hips on a front view, about 0.03 H above the crotch |
| `upper_to_lower` | (H - crotch) / crotch, the clinical segment ratio | from the crotch. A human is 1.08, achondroplasia 1.9-2.1 |
| `trunk_to_leg` | (neck base - hip joint) / hip joint | from C7 (the bump at the neck's base) to the hip line |
| `fingertips_at` | where the hanging fingertips reach: `ankle`, `mid_shin`, `knee`, `mid_thigh`, `crotch`, `hip`, with an optional offset like `knee+0.05` | arms hanging straight at the sides. A human reaches mid-thigh (0.36 H) |
| `arm_to_leg` | shoulder-to-wrist over hip-to-ankle | joint to joint on a T or A pose. A human is 0.70 |
| `shoulder_to_hip` | shoulder (deltoid) breadth over hip breadth | the widest points across a front view. A human man is 1.48, a woman 1.28 |
| `shoulder_heads` | shoulder breadth in head lengths | lay the head sideways across the shoulders. A human is ~2.2 |
| `hunch_deg`, `sway_deg` | extra upper-back curve forward, and extra lower-back hollow | on the side view, the angle between the lower- and upper-back tangents, minus a human's |
| `build` | how fat or muscled it reads: `scrawny` ... `average` ... `massive` | an adult's BMI at *any* stature (`BUILDS`, the adult build law) |
| `bmi`, `mass_kg` | the finished body's, when stated | girth keeps its shape and is scaled to land it. Prefer `build`: a BMI that fights the stated girth is warned |
| `barrel_chest` | 0 a human's chest, 1 a barrel | side view: the ribcage as deep as it is broad |
| `chest_depth_to_breadth` | ribcage depth over breadth (a man 0.88, a woman 0.92 on ANSUR) | side-view depth over front-view breadth under the armpits |
| `forearms` | forearm thickness over the arm's (`heavy`, `thick`, a factor) | the forearm's widest against the upper arm's |
| `rhizomelic` | limbs shortened at the root (femur, humerus), 0-1 | the upper arm short against the forearm |
| `proportionate` | a scaled person: trunk and arms in a human's ratio to the legs | set when it "looks like a small person" |
| `hands`, `feet`, `neck`, `girth` | a factor, or a word (`big`, `long`, `short`, `slender`, `stout`...); `girth` also per region: legs, arms, neck, torso, forearm | hand against the face (~0.75 face length), foot against the head (~1.2) |

Anything that no observable expresses is given as a **knob** (`KNOBS`: `shoulder_scale`, `trunk_scale`,
`waist_to_hip`, `chest_depth`, `chest_breadth`, `girth_forearm`, ...). Each knob has a meaning, a unit, a human default and a range, and an explicit knob always
wins over an observable. Head shape, features, skin and moves are the `look` and are passed through as they are.

### Reach for a real analogue, and label every number

For each trait, ask whether some real body has it and has been measured. Then give each number one label:
**[measured]** (instrumented data), **[documented]** (game rules, engine docs), or **[folklore]** (artist or
literary convention). Folklore is fine as long as it is labelled as folklore.

| trait | real analogue | what it gives you |
|---|---|---|
| long trunk, short limbs | **achondroplasia** (Merker 2018; vosoritide trials) | legs ~50% and span ~35% short, rhizomelic shortening, sitting height mildly reduced, lumbar lordosis, high BMI, a larger head |
| small and proportionate | **pituitary / proportionate short stature, a child's body** | the human ratios, a bigger head by growth allometry |
| very tall | **gigantism** (Robert Wadlow: 2.72 m, 199 kg, BMI 27) | a tall *human* is slender. A body scaled up whole is not (square-cube) |
| big and heavy | **large-animal gait** (duty factor with size, no aerial phase above a few hundred kg) | straight legs, long ground contact, no true run |
| head size | **allometry** (ANSUR II within adults; growth canons 2-15 years) | the head a body of that size "should" have, so you know how far a stylised head departs from it |

## 2. Solve

```python
from humanform import species_design as sd
r = sd.solve({"stature": {"female": [1.15, 1.40], "male": [1.20, 1.45]}, "heads": 5.0,
              "upper_to_lower": 1.5, "rhizomelic": 0.35, "arm_to_leg": 0.74, "build": "stocky", "bmi": 33},
             trunk_scale=0.97, shoulder_scale=1.08)
r["knobs"]           # every knob, ready for design()
r["given"]           # what you stated
r["derived"]         # every other knob and where it came from: "solved from upper_to_lower 1.5", "the law: ..."
r["contradictions"]  # every stated observable the body misses, and which input pinned it instead
```

The laws fill whatever you leave out:

- **Head allometry.** Head length scales as `H^b`: b = 0.30 among adults (measured on ANSUR II here) and 0.55
  across growth (a 2-year-old is 5.6-5.7 heads, a 15-year-old 7.5-7.6). A small proportionate body is
  therefore big-headed by law: at 1.0 m it is about 5.8 heads. A giant is small-headed: at 2.65 m it is about
  9.9 heads. For a disproportionate body the head follows its trunk-matched human, since a dwarf's head is its
  trunk's. When a stated `heads` departs from the law by more than 10%, the report says so, and that number is
  folklore.
- **Mass and build.** Two different things, and the method keeps them apart.
  - *Mass* is volume, always: the pre-warp human's mass times each segment's share of body mass (de Leva 1996)
    times its length factor and its girth squared. It is what the gait and loads use, and square-cube by
    construction.
  - *Build* is how thick a body is for its length, and among adults it does not follow the square-cube law.
    BMI is stature-free in adults: on ANSUR II weight goes as H^2.00 in men (2.19 in women), corr(BMI, stature)
    +0.002 **[measured here, scripts/derive_girth_law.py]**, as in NHANES (Benn index 2.0-2.2, W/H^2 uncorrelated
    with height) **[measured]**; pygmy adults at 1.42-1.55 m (Baka, Efe) have BMI 20.5-21.3, over 85% in the
    normal range **[measured]**. It holds because every girth grows only as **H^a with a ~ 0.5** at a fixed BMI
    (ANSUR II: thigh 0.61, calf 0.52-0.58, biceps 0.47-0.51, forearm 0.55, chest depth and breadth 0.52-0.58,
    neck 0.33-0.38, bideltoid 0.51, hip breadth 0.66-0.69). So a short adult is thicker for his length than a
    tall one, never a geometric shrink: a 1 m geometric shrink of an average man has a four-year-old's BMI
    (~15) and stick limbs.
  - **The adult build law** (`GIRTH_LAW`, `WIDTH_LAW`): a body shrunk by s from its pre-warp human takes each
    girth and breadth by s^a, not s, so a `build` word means an adult of that build at any stature: the gnome at
    1 m and an average build is BMI 20-27, 25 kg. The hips carry the thighs: a hip breadth is never narrower
    than the thighs' girth, and the warp spreads the pelvis when the crotch still comes out low (a thick short
    thigh met below the crotch otherwise). The chest's depth follows its breadth when broad shoulders spread
    it (depth over breadth does not vary with stature: ANSUR II ~H^0.02, only BMI^0.34).
  - **Support girth, only for big bodies.** A body scaled *up* keeps its shape (BMI grows with H: square-cube),
    and its limbs thicken with the load: limb bone circumference goes as M^0.364 across tetrapods against a
    geometric M^0.333 (Campione & Evans 2012) and steeper in large mammals (Christiansen 1999; McMahon 1975's
    elastic similarity in ungulates) **[measured, bones; applied to the limb's girth: derived]**. A limb above
    a human of the build's mass takes (M / M_human)^0.06 (`SUPPORT_EXP`): the troll's limbs 1.07. Gigantism is
    the counter-example: Wadlow at 2.72 m kept a human's BMI 27, and his legs failed him.
  - **The clamp is part of the scale.** A pre-warp human outside ANSUR (1.45-1.95 m) is fitted at the limit and
    scaled whole by c = H_pre / limit (`species.prewarp_stature`). Everything above is taken against the human
    actually fitted: the whole scale is s x c, the adult build law and the support girth apply to that
    (`clamp_girth`; the warp does the same from the preset's `girth_law.scale`), and the mass is the fitted
    human's BMI x its stature^2 x the volume factor. Designed against built (male, BMI from the mesh volume over
    the pre-warp human's, at the brief's BMI): troll (stated bmi 45 then) 43.2 / 42.1, cyclops (3.1 m, c 1.8) 72.5 / 75.0, dwarf
    (1.32 m, c 0.93) 39.6 / 39.5, halfling 30.6 / 29.7, gnome 28.7 / 27.7.
  - **The look, as numbers.** `design` reports each limb's girth over its joint-to-joint length against the
    adult band for its stature and build (`limb_band`: ANSUR II's c/L ~ H^-0.5..-0.7 BMI^0.4..0.6 with its
    5th-95th percentile spread, extended below 1.45 m by the same law), and the chest's depth over breadth.
- **Proportionate or not.** If the trunk-to-leg and arm-to-leg ratios are within 12% of a human's, the body is
  proportionate. That choice picks the head law and the pre-warp basis.
- **Reach.** With nothing stated, the arms keep a human's arm-to-leg ratio. `fingertips_at` solves the arm so
  the hanging fingertips land on the named landmark of the species' own body.
- **Defaults.** Anything no law covers stays human.

Solving works by bisection on the body model, and a target out of reach is refused with the range it could
reach: `hip_fraction 0.9 is out of reach: leg_scale's range (0.4, 1.6) gives 0.329-0.597`.

## 3. Design

```python
preset = sd.design(id="dwarf", stature=..., look={"head": ..., "skin": ..., "moves": ...}, report=r, **r["knobs"])
# or both steps at once:
preset = sd.design_from(observables, id="dwarf", look=..., **explicit_knobs)
print(sd.explain(preset))
```

`design()` returns the `humanform-species/1` preset: graded `ratios` for all 14 realistic keys with their
tolerances, `derived`, `features`, the `pre_warp` human (basis, stature factor, BMI), the warp's `segments`,
`girth` and `widths`, the `spine`, the look, and a `design` block (the solve report, the heads the law gives,
the mass). It **refuses** with a `DesignError` if any knob is out of range (the range is in the message), or
if the numbers disagree: joints out of order, a chin below the shoulders, hands reaching the ankles, a thigh
that is not the hip minus the knee, and so on.

### Anatomy: every drawn part, always

A species body is a whole body. Every part a human body draws is kept and warped with the part it sits on
(`ANATOMY`): nipples and areolae, breasts, navel, genitals, buttocks, belly, lips, eyes, lashes, brows, teeth,
tongue, ears, nails, knuckles, palms, soles, knees, elbows and body hair. Each part follows its host's warp
factor (areolae with the chest breadth, genitals with the pelvis, nails with the hand), so a warped body keeps
plausible anatomy without a per-species rule. The eyes follow the head at an exponent of 0.53, because eyes grow
slower than heads (about 17 mm at birth and 24 mm in an adult, while the head roughly doubles). Head features such
as `ears_pointed` or `tusks` add to these parts and never replace them. Genitals stay opt-in in a build
(`[body] genitals`), as for humans.

The **description** is the only thing that changes this:

```python
anatomy = {"absent": [{"part": "nipples", "reason": "egg-laying reptile folk: no mammary glands"},
                      {"part": "navel", "reason": "hatched, no umbilicus"}],
           "scale": {"eyes": 1.3}}                 # relative to the size its host's law gives
sd.design_from(observables, id="lizardfolk", anatomy=anatomy, look=...)
```

`absent` needs a reason. It also turns off the part's skin region (`skin.regions_off`, derived and never
written by hand). **A region is never turned off because of its colour.** Region tints follow the tone
(`skin.species_skin`), so a green body's lips and areolae come out a deeper green. `design()` refuses a
`regions_off` that no absent part backs. `scale` takes a factor from 0.3 to 3, and `explain()` reports it. The
preset's `anatomy.parts` gives each part's host and its size factor per sex against the pre-warp human.

### Catch it before the build

`design()` warns (`preset["design"]["warnings"]`, printed by `explain`, and by character-pipeline before a
spec builds) when the build will not read as an adult:

- **stick limbs**: a limb's girth over its length under the adult band's 5th percentile for its stature and
  build (`stick limbs: shin girth/length 1.01 (male) against the adult band 1.11..1.50 at 1.04 m for a build of
  BMI 21-28 - state a heavier build, or drop a slender girth`). The first gnome, a geometric shrink, fires it;
- **child-light BMI**: a finished BMI under the build's band on a body that was not scaled up;
- **a stated BMI that thins the stated girth** by more than 8%: the girth says the build, so drop the BMI.

After the build, humancheck (species) reports `limb_build.<limb>` - the mesh's girth over length against the
same band (`MESH_CAL` converts humancheck's relaxed, joint-to-joint measures), warning under it - and
`chest_depth_to_breadth`. The warp's report (`species.build`) shows each girth it asked for against what
landed on the mesh.

To add the species to the catalogue, add its observables to `scripts/derive_species.py` and run it. Run
`--explain <id>` for the table and `--chart <scratch>/s.svg` for a picture.

## 4. Build, check, look

- **Build:** set `species = "<id>"` in a character spec (`[body]`) and build with `build_many`. humanform fits
  the pre-warp human and then warps it (layer 1 of `docs/improvements/08-fantasy-species.md`).
- **Check:** humancheck grades the body against the species preset. Every fail names a ratio and how many
  centimetres it is off.
- **Look:** first at the chart (`sd.chart`: front and side stick figures at true scale beside a human). Does it
  read as the thing described? Then in Godot, orbiting in close. Judge it there. When you find a mistake by
  eye, turn it into an observable or a check, so the next design catches it before a build.

## Worked example: the dwarf

1. **Description:** "short, stocky, long trunk, short limbs, broad, 1.2-1.45 m."
2. **Analogue:** achondroplasia [measured]. It has a sitting height near a human's (`trunk_scale` 0.97), and an
   upper-to-lower ratio of 1.9-2.1 that we soften to **1.5** so the dwarf reads heroic rather than clinical.
   The shortening is rhizomelic (**0.35**). The arm span loses ~35% where the legs lose ~50%, so the arms lose
   0.7 of the legs' share (`arm_to_leg` **0.74** against a human's 0.70). The build is carried by the trunk:
   `barrel_chest` **1** (the ribcage as deep as it is broad), `forearms` **heavy**, and a girth of legs 1.05,
   arms 1.12, neck 1.25, torso 1.12 over a stocky human. No BMI is stated: achondroplastic adults run ~30
   [measured], and this shape comes out at ~42 (74 kg at 1.32 m, near D&D's ~68 kg [documented]). A stated 33
   thinned every girth to 0.85 of itself, and the dwarf read as a short man.
3. **Heads:** art draws dwarves at 4-4.5 heads [folklore]. On a human-sized trunk that is a 0.29 m head, and the
   law gives 6.0. We state **5.0** (0.26 m), and the report labels it folklore.
4. **Solve:** `leg_scale` 0.77 from the segment ratio, `arm_scale` 0.83 from `arm_to_leg`, `chest_depth` 1.18
   from the barrel chest. There are no contradictions and no warnings.
5. **Result:** hip joint at 0.435 H (a human's is 0.510), trunk/leg 0.83 (0.69), disproportionate, so the
   pre-warp human is trunk-matched (below ANSUR's floor at the short end, which the warp handles by a uniform
   scale). Mass ~74 kg at 1.32 m. Built, its chest depth over breadth rose from the pre-warp human's 0.71 to
   0.84 on humancheck's measure (a barrel is ~0.87 there), its thighs 2.5 girths per length.

## Worked example: the troll

1. **Description:** "huge, 2.4-2.8 m, hunched, long arms with hands to the knee, heavy."
2. **Analogues:** square-cube scaling and large-animal gait [measured]. For contrast there is gigantism: Wadlow
   at 2.72 m was BMI 27 because a tall human is slender. A troll is a human scaled up whole: `build`
   **"average"**, fitted at 1.95 m and scaled 1.4x, comes out ~400 kg (BMI ~56) by square-cube, its limbs
   thickened by the support girth (1.07). No BMI is stated: a stated 45 thinned every girth to 0.69 once the
   clamp was counted, and the built arms read under the adult band. `girth` arms **1.15**, forearm **1.1**:
   arms to the knee as heavy as they are long.
3. **Reach:** `fingertips_at` **"knee"** solves `arm_scale` to 1.02 against legs shortened to 0.83 (from
   `trunk_to_leg` **0.77**). Arm-to-leg ends at 0.87, far outside a human's, so the body is disproportionate.
4. **Hunch:** `hunch_deg` **32**, applied over the thoracic span. Every ratio is measured on the bent body.
5. **Heads:** the law gives 9.9, because a giant is small-headed. We state **7.0** for the brute's big head, and
   it is labelled folklore.
6. **Result:** ~400 kg at 2.65 m. The pre-warp human (2.75-3.2 m) is above ANSUR, so it is fitted at 1.95 m and
   scaled up uniformly. `moves` notes the large-animal gait: straight legs and no aerial phase.

## A new creature, in five lines

```python
from humanform import species_design as sd
p = sd.design_from({"stature": 1.6, "heads": 6.5, "crotch_fraction": 0.40, "fingertips_at": "mid_shin",
                    "hunch_deg": 15, "build": "lean", "feet": "big"}, id="bog_hag",
                   look={"head": {"shape": "triangular", "shape_weight": 0.6, "features": {"nose_size": 0.9}},
                         "skin": {"palette": [[0.45, 0.50, 0.38], [0.36, 0.40, 0.30]], "regions_off": ["flush"]}})
print(sd.explain(p))            # read the derived knobs and any contradiction before building
```

## Past the human body plan: eyes, a tail, swimming

Three general mechanisms take a design past a person's layout. Each is data in the species (inline or a file),
never a species name, and each refuses what it cannot do with the range in its message. They were built for the
first user trials (a drow, a cyclops and a mermaid, 2026-09-21) and are how any creature with the same
differences is made.

**How many eyes, and where** - `head.eyes` (`humanform.eye_layout`). `{ count = 1, size = 1.5 }` is one median
eye 1.5x a person's; `{ count = 3 }` keeps the pair and adds one on the forehead; `at = [{ x, rise, size }, ...]`
places any set (`x` in human eye-offsets from the midline, `rise` metres up on the reference head). Sockets no eye
takes are closed to skin (a harmonic fill over the orbit), each new eye gets a carved socket (an almond
`aperture` in eyeball radii, lids hugging the ball), an eyeball, and the human lash cards carried onto its lids -
a median eye takes both, one per half. The eyes ride the head bone, as a person's do, so the gaze (rig-anything's
head hold) aims them. Analogue: cyclopia puts one median eye at the nasion [measured]; folklore puts it higher.

**A limb pair replaced** - `graft = { legs = { to = "tail", ... } }` (`humanform.graft`). A seam round the body
at the hip joints, the seam's own ring lofted down to a peduncle and a fluke (`fluke.span` in body lengths:
cetaceans 0.2-0.27 [measured], `chord`, `sweep`, `notch`, `plane` horizontal or vertical), the leg bones
swapped for a tail chain, the UVs in the atlas the legs freed. What a replacement takes must be in
`anatomy.absent`, each with the description's reason - legs to a tail take `knees`, `soles`, `nails.toes` and
`genitals` - and the design refuses a graft whose absences are not stated. The skin's pattern region `graft`
covers the tail and fades up over the seam (`fade`), so `pattern = { kind = "scales", regions = ["graft"] }` is
a skin-to-scales transition; the tone is held over the skin, not the tail.

**Moving by another mode** - `[moves] locomotion = "swim"` (character-pipeline): rig-anything's
`swim.upright_set` for a body that stands at rest and swims. Idle floats upright, treading water; Swim, Sprint,
Glide and the turns are worked out along the tail-to-head line and laid prone. The mode comes from the tail's
tip (flukes wider across than through swim up and down: cetacean), the wave rises from the waist as a person's
dolphin kick does, and speeds come from length (Strouhal 0.2-0.4 [measured, Rohr & Fish 2004]). No Froude
number, foot-drift or reach check is run on a swimmer: they are a walker's.

**Size.** A body past the tallest pre-warp human is fitted at the limit and scaled whole, so square-cube lifts
its BMI with the scale (a person's build at 3 m is BMI ~45). The BMI warning scales with it. At that size BMI
is the wrong observable for how heavy a body *looks*: a 3 m man at bmi 40 was solved to girth 0.91 and read as a
lean person scaled up. State the shape (`girth = "thick"`) and let the mass follow.

### Gaps (what the trials could not do yet)

- A tail longer than the legs (a curled or trailing tail at rest) is refused: `length` is at most 1.
- Only legs can be grafted, only to a tail. Arms to wings, a second pair of arms, a centaur's body: not made.
- The scales are albedo only (no normal relief), and there are no side fins on a graft (rig-anything's
  `fins` rigs fins it finds on a mesh; the graft makes none).
- An eye has no bone of its own: it aims with the head. Lashes on a carved eye stand straighter than a person's.
- Flesh zones on a heavy body (a thick-girthed giant's belly) fail follow-through's placement check - the same
  open problem as the BMI 38 smoke body.
- Genital geometry (`[body] genitals`) was not tried: fig-genital-anatomy was not merged into species-1.
