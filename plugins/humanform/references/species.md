# Species: what each fantasy body is, its numbers and why

A species is a human with its segments stretched or shrunk, its head resized and reshaped, its spine bent and its
skin recoloured (design: `docs/improvements/08-fantasy-species.md`). Each is a file,
`data/species/<id>.json` (schema `humanform-species/1`), **generated** by `scripts/derive_species.py` from the
realistic preset and a handful of knobs. Edit the knobs, never the JSON.

## Labels

Every knob's reason in `derive_species.py` (and the `notes.knobs` of each file) carries one of the design's labels:

| label | means | examples here |
|---|---|---|
| **[measured]** | instrumented human data | achondroplasia: legs ~50% and span ~35% short, sitting height mildly reduced, rhizomelic shortening, lumbar lordosis, high BMI; square-cube mass and large-animal gait |
| **[documented]** | game rules or engine docs | D&D 5e heights for dwarf, halfling, gnome, half-orc, goblin |
| **[folklore]** | artist or literary convention, no data | elf 8.3 heads and long neck, orc breadth, goblin hunch and ears, troll 7 heads, hands to the knee |

Only the dwarf (from achondroplasia) and the troll's mass (from scaling) rest on measurements. Everything else
is a considered convention: treat it as a starting point, not a fact.

## The species (male; female within a few thousandths)

| species | stature m (f / m) | heads | hip joint H | trunk/leg | upper/lower seg | fingertip above knee H | pre-warp basis | why it reads |
|---|---|---|---|---|---|---|---|---|
| human | ANSUR | 7.7 | 0.510 | 0.69 | 1.08 | 0.080 | - | the baseline |
| elf | 1.65-1.85 / 1.75-1.95 | 8.3 | 0.523 | 0.63 | 1.01 | 0.071 | trunk | long legs, long neck (1.35x), slender girth 0.86, narrow shoulders |
| halfling | 0.85-1.05 / 0.88-1.10 | 5.5 | 0.484 | 0.73 | 1.20 | 0.080 | head | proportionate and small, a child's head fraction, big feet (1.22x) |
| gnome | 0.92-1.08 / 0.95-1.12 | 4.3 | 0.463 | 0.75 | 1.30 | 0.070 | head | proportionate, a big head (0.23 m at 1 m) and a big nose |
| dwarf | 1.15-1.40 / 1.20-1.45 | 5.0 | 0.436 | 0.91 | 1.50 | 0.078 | trunk | human trunk on legs 28% short (femur most), broad, lordotic |
| orc | 1.70-1.90 / 1.80-2.05 | 7.5 | 0.504 | 0.74 | 1.11 | 0.063 | trunk | tall, broad (1.18x shoulders), heavy girth, tusks and brow |
| goblin | 0.95-1.15 / 1.00-1.20 | 5.0 | 0.485 | 0.71 | 1.18 | 0.050 | head | small, 26 deg hunch, big head and ears, big hands and feet, scrawny |
| troll | 2.35-2.70 / 2.45-2.85 | 7.0 | 0.496 | 0.77 | 1.16 | 0.010 | trunk | huge, 32 deg hunch, hands to the knee, square-cube heavy (BMI 36-50) |

- **trunk/leg** is (neck base - hip joint) / hip joint, measured on the bent body.
- **upper/lower segment** is (H - crotch) / crotch, the clinical ratio: about 1.0 in average adults and 1.9-2.1
  in achondroplasia. The dwarf's knob `leg = 0.56` reproduces achondroplasia (1.9); 0.72 softens it to 1.5.
- **Dwarf heads 5.0, not the art canon's 4-4.5.** With a human-sized trunk, 4.5 heads is a 0.29 m head on a
  1.3 m body, larger than any human head. 5.0 gives 0.26 m: achondroplasia's macrocephaly without a cartoon.
- **Gnome 4.3, not 4.2**: already a 0.23 m head at 1.0 m.
- **Proportionate vs disproportionate**: the halfling and gnome keep a human's trunk-to-leg ratio within 12%
  (asserted); the dwarf's is 1.3x a human's. That is the difference between a small person and a dwarf.
- **Skin**: human tones for elf, halfling, gnome and dwarf, every region on. Orc and goblin are greens with the
  red lips and flush off; the troll is grey-green with every red-shifted region off (lips, flush, nipple, genital,
  knee, elbow, knuckle) and the paler palms, soles and nails kept. The red regions are blood under thin human
  skin, and on green they read as mud.

## What a file holds

| block | graded by humancheck | what it is |
|---|---|---|
| `stature`, `bmi` | refused outside | per sex, final standing height with the spine bent |
| `heads`, `ratios` | yes | exactly the realistic preset's 14 keys, `[target, tol]` per sex (chin `any`), fractions of H |
| `derived`, `features.hip_above_crotch` | yes | overrides of the human shoulder/hip width, waist/hip and hip-above-crotch ranges |
| `proportion` | no | trunk, trunk/leg, upper/lower segment, sitting height, reach, beside the human's |
| `pre_warp` | - | `basis` (trunk or head), `stature_factor` per sex (H_pre / H), the H_pre range, and the `min_stature`/`max_stature` it is clamped to (the warp then scales uniformly) |
| `segments`, `girth`, `widths` | - | the warp's start factors, absolute, against the pre-warp human |
| `spine` | - | extra kyphosis (thoracic, upper 60% of the spine) and lordosis (lumbar, lower 40%) in degrees |
| `head` | - | `shape` (one of `sheet.FACE_SHAPES`), `shape_weight`, `features` (`ears_pointed`, `ear_size`, `brow_ridge`, `nose_size`, `tusks`; 0 is human) |
| `skin` | - | 2-4 sRGB tones spanning the species, and `regions_off` (names from `skin.REGIONS`) |
| `moves` | - | a named style (none yet) and what `derive_style` should produce |
| `knobs`, `notes`, `sources` | - | the design choices and their reasons |

## How the numbers are made

`derive_species.py` stacks the realistic mean body (per sex, stature 1) segment by segment - ankle height, shin,
thigh, the spine arc (bent by the spine knobs), the neck, then a head scaled so the stack is `heads` heads
tall - and divides by the total. Joint heights, segment lengths, the trunk and the head count therefore agree by
construction, and `check()` asserts it for every file: joints ordered, thigh = hip - knee, shin = knee - ankle,
chin = 1 - 1/heads, trunk = neck base - hip, hip above crotch inside its own range, every key covered, skin
regions and face shape known, and the species' own claims (dwarf upper/lower 1.3-1.6, troll fingertips at the
knee, halfling and gnome proportionate). Tolerances are the realistic preset's, scaled with the value and by 1.3.

## Adding or changing a species

1. Add an entry to `SPECIES` in `scripts/derive_species.py`: stature and BMI ranges, `basis`, and the knobs
   (`heads`, `trunk`, `leg` + `leg_rhizo`, `arm` + `arm_rhizo` or `reach`, `hand`, `foot`, `neck`,
   `shoulder_width`, `hip_width`, `girth`, `kyphosis_deg`, `lordosis_deg`), each with its reason and label;
   `waist_to_hip`, `head`, `skin`, `moves`. 1.0 is a human for every length knob.
2. Pick the basis: `trunk` for a body whose trunk is human-like (dwarf, orc, troll), `head` for a proportionate
   small one (halfling, gnome).
3. Run it and read the table (and `--chart <scratch>/species.svg` to see every species beside a human at true
   scale, front and side):

   ```bash
   python scripts/derive_species.py --chart <scratch>/species.svg
   ```

   It refuses to write when any assert fails, naming the species, the sex and what disagrees.
4. Add a claim the species must keep to `check()` if its look depends on one (as the troll's reach).
