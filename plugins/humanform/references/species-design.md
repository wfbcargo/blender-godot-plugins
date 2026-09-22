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
| `build` | how fat or muscled it reads: `scrawny` ... `average` ... `massive` | the pre-warp human's BMI (`BUILDS`) |
| `bmi`, `mass_kg` | the finished body's, when stated | girth keeps its shape and is scaled to land it |
| `rhizomelic` | limbs shortened at the root (femur, humerus), 0-1 | the upper arm short against the forearm |
| `proportionate` | a scaled person: trunk and arms in a human's ratio to the legs | set when it "looks like a small person" |
| `hands`, `feet`, `neck`, `girth` | a factor, or a word (`big`, `long`, `short`, `slender`, `stout`...) | hand against the face (~0.75 face length), foot against the head (~1.2) |

Anything that no observable expresses is given as a **knob** (`KNOBS`: `shoulder_scale`, `trunk_scale`,
`waist_to_hip`, ...). Each knob has a meaning, a unit, a human default and a range, and an explicit knob always
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
- **Square-cube mass.** Mass is volume: the pre-warp human's mass times each segment's share of body mass
  (de Leva 1996) times its length factor and its girth squared. A body scaled up whole gains BMI in proportion
  to height. A small one loses it, so a 1 m proportionate body at a human's build has a child's BMI (~15).
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
   0.7 of the legs' share (`arm_to_leg` **0.74** against a human's 0.70). Achondroplastic adults' BMI runs
   around 30, so a fantasy dwarf gets **bmi 33**.
3. **Heads:** art draws dwarves at 4-4.5 heads [folklore]. On a human-sized trunk that is a 0.29 m head, and the
   law gives 6.0. We state **5.0** (0.26 m), and the report labels it folklore.
4. **Solve:** `leg_scale` 0.727 from the segment ratio, `arm_scale` 0.779 from `arm_to_leg`, and girth scaled to
   BMI 33. There are no contradictions.
5. **Result:** hip joint at 0.437 H (a human's is 0.510), trunk/leg 0.91 (0.69), disproportionate, so the
   pre-warp human is trunk-matched (1.35-1.64 m, below ANSUR's floor at the short end, which the warp handles
   by a uniform scale). Mass ~57 kg at 1.32 m. On the chart it reads stocky and long-trunked.

## Worked example: the troll

1. **Description:** "huge, 2.4-2.8 m, hunched, long arms with hands to the knee, heavy."
2. **Analogues:** square-cube scaling and large-animal gait [measured]. For contrast there is gigantism: Wadlow
   at 2.72 m was BMI 27 because a tall human is slender. A troll is a heavy human scaled up whole: `build`
   "heavy" (BMI 32) would reach ~48 at 2.65 m, and we state **bmi 45**, so girth is solved (1.05).
3. **Reach:** `fingertips_at` **"knee"** solves `arm_scale` to 1.02 against legs shortened to 0.83 (from
   `trunk_to_leg` **0.77**). Arm-to-leg ends at 0.87, far outside a human's, so the body is disproportionate.
4. **Hunch:** `hunch_deg` **32**, applied over the thoracic span. Every ratio is measured on the bent body.
5. **Heads:** the law gives 9.9, because a giant is small-headed. We state **7.0** for the brute's big head, and
   it is labelled folklore.
6. **Result:** ~310 kg at 2.65 m. The pre-warp human (2.75-3.2 m) is above ANSUR, so it is fitted at 1.95 m and
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
