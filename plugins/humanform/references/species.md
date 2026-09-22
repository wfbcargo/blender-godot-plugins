# Species catalogue

**To design a species, read `species-design.md`, which is the method.** This page lists the seven species that
ship in `data/species/`. Each one is a worked example of that method, stated as observables in
`scripts/derive_species.py` and made by `humanform.species_design`. Do not edit the JSON: change the entry and
run `python scripts/derive_species.py` (`--explain <id>` prints the table, `--chart <file>.svg` draws them all).

Labels: **[measured]** instrumented data, **[documented]** game rules, **[folklore]** convention. Only the
dwarf's proportions (achondroplasia), every body's mass (square-cube, de Leva) and the head law (ANSUR II,
growth canons) rest on measurements. The rest are labelled conventions.

## The seven (male columns; female within a few thousandths)

| species | stature m (f / m) | heads (law) | hip H | trunk/leg | upper/lower | fingertips above knee H | BMI | basis | stated as |
|---|---|---|---|---|---|---|---|---|---|
| human | ANSUR | 7.7 | 0.510 | 0.69 | 1.08 | 0.080 | ANSUR | - | - |
| elf | 1.65-1.85 / 1.75-1.95 | 8.3 (8.0) | 0.522 | 0.64 | 1.01 | 0.063 | 17-22 | head | `hip_fraction` 0.525, neck long, lean, narrow |
| halfling | 0.85-1.05 / 0.88-1.10 | 5.5 (5.7) | 0.482 | 0.74 | 1.21 | 0.088 | 22-28 | head | `trunk_to_leg` 0.72, feet 1.22, stocky |
| gnome | 0.92-1.08 / 0.95-1.12 | 4.3 (5.8) | 0.460 | 0.76 | 1.32 | 0.082 | 15-20 | head | `trunk_to_leg` 0.74, a big head, big nose |
| dwarf | 1.15-1.40 / 1.20-1.45 | 5.0 (6.0) | 0.437 | 0.91 | 1.49 | 0.081 | 29-37 | trunk | `upper_to_lower` 1.5, rhizomelic 0.35, `arm_to_leg` 0.74, bmi 33 |
| orc | 1.70-1.90 / 1.80-2.05 | 7.5 (8.2) | 0.501 | 0.75 | 1.13 | 0.070 | 28-36 | head | `trunk_to_leg` 0.73, `shoulder_to_hip` 1.65, bmi 32, tusks |
| goblin | 0.95-1.15 / 1.00-1.20 | 5.0 (5.9) | 0.483 | 0.72 | 1.19 | 0.052 | 13-16 | head | `fingertips_at` knee+0.05, hunch 26, big hands, feet and ears |
| troll | 2.35-2.70 / 2.45-2.85 | 7.0 (9.9) | 0.489 | 0.79 | 1.21 | 0.002 | 39-51 | trunk | `fingertips_at` knee, hunch 32, bmi 45 (~310 kg) |

- **heads (law)** is what head allometry gives a body of that size. Wherever the stated count departs from it,
  the head is a stylised one [folklore]: bigger on the small species and the troll, smaller on the elf.
- **BMI** comes from the square-cube volume law, from the pre-warp human's build. The small species come out
  child-light (a 1 m body is ~15-20), and the dwarf and troll come out heavy.
- **basis** is the pre-warp human: head-matched for a proportionate body, trunk-matched otherwise. Several fall
  outside ANSUR's 1.45-1.95 m (halfling, gnome, orc, troll, the short dwarves). The warp fits at the limit and
  scales uniformly.
- **Skin:** elf, halfling, gnome and dwarf have human tones. Orc and goblin are greens, and the troll is
  grey-green. Every region is kept on all seven, tinted along the tone's own hue by `skin.species_skin`.
- **Anatomy:** full on all seven. No description removes a part, so `anatomy.absent` is empty and every part
  scales with its host (`species-design.md`, "Anatomy").
- **Head features** (`head.features`, 0 = human): `ears_pointed`, `ear_size`, `brow_ridge`, `nose_size`, `tusks`.

## Judgement calls, and why

- **Dwarf at 5.0 heads, not the art canon's 4-4.5.** On a human-sized trunk, 4.5 heads is a 0.29 m head, larger
  than any human's. 5.0 heads is 0.26 m.
- **Dwarf segment ratio 1.5, not achondroplasia's 1.9-2.1.** `upper_to_lower` 1.9 reproduces the condition;
  1.5 softens it into the design's 1.3-1.6.
- **Gnome at 4.3 heads, not 4.2.** Its head is already 0.23 m at 1.0 m.
- **Elf is Tolkien-tall**, not D&D-short.
- **Troll BMI 45.** A heavy human scaled whole to 2.65 m would be ~48, and a gigantic human (Wadlow) was 27.
  The troll sits near the scaled shape.

## What a file holds

See `species_design.design()`. In short:

| block | what it is |
|---|---|
| `stature`, `bmi`, `heads`, `ratios`, `derived`, `features` | graded by humancheck, in presets.json's format |
| `pre_warp` | basis, stature factor and H_pre range per sex, BMI, min/max stature |
| `segments`, `girth`, `widths`, `spine` | the warp's start factors, absolute against the pre-warp human |
| `head`, `skin`, `moves` | the look (`skin.regions_off` only from `anatomy.absent`) |
| `anatomy` | every part kept (`parts`: host and size factor per sex) unless `absent` with a reason |
| `knobs`, `design`, `proportion`, `notes`, `sources` | the knobs, the solve report (given, derived, contradictions, heads law, mass), the observables shown, the reasons |
