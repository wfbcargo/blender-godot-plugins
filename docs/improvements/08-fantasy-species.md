# 08 - Fantasy species: dwarves, elves, gnomes, trolls, gnolls and whatever the user describes

Category: **6 feature gaps**, but every layer leans on work that already exists. A species is data, and the
code that turns data into a body, a rig and a gait is shared by every species, including the human one.

> **Picking this up?** Step 1 (species presets and the proportion warp) is the round this was written for
> (branch `species-1`, 2026-09-21). The rest is in order below.

> **The goal (the user's rule, 2026-09-21): tools that make *any* creature, not recipes for a dwarf.** A
> preset for a dwarf is worth little on its own. What we build is (1) a **method** for working out what any
> described creature's numbers should be, (2) a **general parameter space** those numbers live in, with
> general laws (allometry, square-cube, Froude) filling in what a description leaves out, and (3) **tools** that
> turn the parameters into a consistent body, head, surface and gait, and check it. The named species are
> worked examples and test cases for the method. Code never branches on a species name; everything is driven
> by the numbers, so a species invented inline in one character spec needs no file and no code.

## The method: from a description to a creature

This is the procedure the tools support, and what `humanform/references/species-design.md` teaches in full.
Each step has a tool, and each tool refuses what it cannot do with the range in its message.

1. **Read the description into observables.** Only things a person can state or measure on a concept image:
   stature, head count, where the hanging fingertips land (hip, mid-thigh, knee), crotch height or leg
   fraction, trunk-to-leg ratio, shoulder and hip width against a human's, spine angle (hunch), build words,
   skin tone and pattern, head features. How to measure each on an image, and how to pick a real-world
   analogue for what is not given (achondroplasia for short limbs on a normal trunk, proportionate short
   stature for a scaled-down body, gigantism and large-animal data for size, the Froude law for gait), is
   the method's reference. Each number is labelled given, derived or folklore.
2. **Solve the observables into the parameter space** (`humanform.species_design.solve`). Any subset may be
   given. What is missing comes from general laws, not from per-species rules:
   - **allometry**: head size grows slower than stature, so a short creature is big-headed without being
     told (the exponent from human and cross-species data);
   - **square-cube**: a creature of the same build is heavier per unit height as it grows (BMI scales with
     stature), which drives girth, stockiness and the gait;
   - **proportionate against disproportionate**: short limbs on a full trunk is a different body from a
     scaled-down one, and the solver says which it read;
   - **reach landmarks** set arm length from where the hands hang.

   Contradictions (5 heads and 2.5 m and a human head size) are reported, not silently resolved.
3. **Design the preset** (`species_design.design(**params)`): every joint height, segment, width and the head
   count, in `presets.json`'s format, consistent by construction (joints ordered, heads = 1/(1 - chin),
   segments sum to the joint heights). `explain(preset)` prints it as a table a person can check.
4. **Build**: the nearest human is fitted, then warped to the preset (layer 1); head features, surface and
   gait follow the other layers. Each is a general mechanism with named presets on top: a head feature is a
   region, a displacement and an optional attached part; a skin is a tone, derived region shifts and a pattern;
   a gait style comes from what is measured on the built body.
5. **Check, then look**: humancheck grades the body against its own preset; rig-anything checks the Froude
   number, foot drift and reach; then the body is looked at in Godot, beside a human at true scale.

---

## The problem

humanform builds adult humans and nothing else. Everything outside that is refused or clamped:

- An adult under 1.3 m is refused (`sheet.STATURE`), so a 1.2 m dwarf or a 1.0 m gnome cannot be built.
- The chin is fixed at 0.87 H (`landmarks.from_measurements`), which locks the head at about 7.7 heads.
  A dwarf is drawn at 4-4.5 heads and a gnome at about 4.
- The only presets are `realistic` (ANSUR II) and `stylized` (Loomis). humancheck fails anything outside
  7.0-8.8 heads.
- Every MPFB lever is clamped to [-1, 1] (`scaffold.py:374`), and there is no bone scaling. A dwarf's legs
  are about 50% shorter than a human's relative to the trunk. No MPFB target reaches that.
- Skin is a human tone: `skin.py`'s regions and contrast checks assume human palms, lips and areolae.
- There is no fur, no muzzle, no tail and no digitigrade leg on a humanform body.
- Nothing checks that a changed body still has all of its anatomy (nipples, genitals, navel, nails, teeth).

The rest of the pipeline is already species-agnostic:

- **rig-anything's gait is dynamic similarity.** `locomotion.py` measures hip height on the rig and derives
  stride (Alexander 1976: `stride/h = 2.3 Fr^0.3`), speed `sqrt(Fr g h)`, cadence, duty factor and swing lift
  from the Froude number. Clips are built for each rig, never retargeted, so there is no foot sliding to patch.
  Give it a body with 0.55 m legs at Fr 0.25 and it walks at 1.16 m/s with about 1.28x a human's cadence,
  which is what a dwarf should do.
- **Gait styles are data** (`GAIT_STYLES`, a dict of `STYLE_KEYS`), the same mechanism as `elderly_shuffle`.
- **`bodymap` finds limbs by structure** (a grounded chain is a leg), so a warped body is still read right.
- **follow-through, wardrobe and lookdev read the mesh and the rig they are given.** A warped body is just a
  body to them.

## What we know (research, 2026-09-21)

Labels: **[measured]** instrumented data; **[documented]** vendor or engine docs; **[community]** modders;
**[folklore]** artist convention with no data.

**How games do races.** Race is data on a shared skeleton, not a new rig. WoW moved every player race onto one
stretchable skeleton so one animation serves all of them **[community, citing Blizzard]**
(mmo-champion.com/threads/2351275). Skyrim scales one skeleton 0.95-1.08 per race **[community]**
(nexusmods skyrimspecialedition 52057). Baldur's Gate 3 gives dwarf, halfling and gnome their own body rigs
with a shared bone layout **[community]**. Character Creator 4 moves the skeleton to fit a pushed-past-range
morph ("Adjust Bones to Fit Morph") **[documented]** (wiki.reallusion.com/Content_Dev:CC_Morph_Creation).

**Retargeting breaks on proportion.** Godot's `SkeletonProfileHumanoid` keeps only Root and Hips translation
and scales them by hip height; its docs say it cannot handle very different proportions **[documented]**
(docs.godotengine.org, retargeting_3d_skeletons). A retargeted dwarf keeps the human's timing, walks at a lower
Froude number, and reads as a shrunken human. This is why we do not retarget.

**Proportions.**

- Human: about 7.5 heads average, 8 ideal, 8.5 heroic **[folklore, art canon]**.
- Dwarf: 4-4.5 heads, barrel chest, broad shoulders, thick neck, heavy forearms, wide jaw **[folklore]**.
  The real-world model is achondroplasia: legs about 50% shorter and arm span about 35% shorter than
  average, sitting height only mildly reduced **[measured]**; the upper-to-lower segment ratio is about
  1.9-2.1 against about 1.0 for average adults **[measured, children, BMN 111 trials]**. The shortening is
  rhizomelic: femur and humerus most **[measured]**. A fantasy dwarf is a softened version: aim for a ratio
  of 1.3-1.6.
- Halfling and gnome: a *proportionate* short body with a larger head fraction, a different thing from a
  dwarf **[measured, the distinction; folklore, the races]**.
- D&D 5e heights, the only hard numbers in any canon **[documented, game rules]**: hill dwarf 3'8"+2d4,
  mountain dwarf 4'0"+2d4, halfling 2'7"+2d4, gnome 2'11"+2d4.
- Elf, orc, troll: no published segment ratios anywhere. Convention only **[folklore]**.

**Movement.**

- Froude number `Fr = v^2 / (g L)`. Humans walk at preferred speed near Fr 0.25, switch to a run near 0.5 and
  cannot walk above 1. At equal Fr, stride relative to leg length and duty factor match, and stride frequency
  scales as `1/sqrt(L)` **[measured]** (Alexander & Jayes 1983).
- Short-statured adults walk with higher cadence and shorter stride, at the same *normalised* speed. People
  with achondroplasia show more hip flexion and abduction, more anterior pelvic tilt, more pelvic obliquity and
  lumbar rotation, and less knee flexion **[measured]** (researchsquare rs-7363037). That is the rolling
  "dwarf" walk. Walking also costs them 29-35% more oxygen **[measured]** (PMC5915563).
- Large bodies (square-cube law: double the height is 8x the weight on 4x the bone section): straighter limbs,
  duty factor rising with size (giraffe 0.23, rhino 0.39, elephant 0.48), and no aerial phase above a few
  hundred kilograms **[measured]** (PMC8214834). A troll or giant has straight legs, long ground contact and
  no true run.
- Weta slowed the performance for the 9-foot Goblin King and the Hobbit trolls **[documented]**
  (fxguide.com/fxfeatured/the-hobbit-weta): Froude time scaling done by eye.

**Generic methods.** Spore (Hecker et al., SIGGRAPH 2008) authors motion once in a morphology-independent form
and solves it per creature with IK. Wampler & Popovic 2009 derive a gait from morphology by optimisation.
Both confirm the approach rig-anything already takes. Learned retargeting (Skeleton-Aware Networks, Neural
Kinematic Networks) needs training and is out of scope.

## The design

A **species** is a set of changes from a baseline body, in five layers. Each layer feeds a stage the pipeline
already has, and each has a check that runs before a build.

| layer | what it holds | where it runs | its check |
|---|---|---|---|
| 1. **Proportion** | stature range, heads, joint heights, segment ratios, widths, spine curve | humanform: fit the nearest human, then warp | humancheck against the species preset |
| 2. **Head** | head size and shape, ears, brow, nose, jaw, tusks; a muzzle (graft) | humanform: MPFB targets, `delta.py` shapes, later a head graft | head count, feature measures |
| 3. **Surface** | skin palette and pattern, subsurface tint, fur coverage and length | humanform `skin.py`, a new fur pass, lookdev | albedo range, the species' region contrast |
| 4. **Movement** | gait traits derived from the measured body, plus a style | rig-anything `locomotion.py` / `upper.py` | Fr of every baked walk in range, foot drift, reach |
| 5. **Anatomy** | digitigrade legs, tails, extra digits (later) | rig-anything archetypes | bodymap roles, joint folding |

A human is the species with no changes. Every species preset names its baseline (`human`, and later others
such as `canine_biped` for a gnoll), so a centaur or a satyr is a different baseline with the same five layers.

### Layer 1: proportion, by fitting the nearest human and then warping it

MPFB cannot reach a dwarf, and we should not try to push it past its range: its targets are human shape
deltas and extrapolate into broken geometry. Instead:

1. **The pre-warp human.** Work out the human that shares the species body's trunk and build. For a dwarf of
   stature `H`, the human has the dwarf's trunk (neck base to hip joint, in metres) at human proportions:
   `H_pre = H * trunk_frac_species / trunk_frac_human`. A 1.35 m dwarf becomes a human of about 1.75 m with the
   dwarf's BMI and build. It is inside ANSUR, so the existing fit, the library and humancheck all apply to it.
   A proportionate species (gnome, halfling) takes `H_pre` from the species' head size instead.
2. **Fit it** with the existing pipeline (`pipeline.make`), up to and including the rig. The library is used
   and stored as normal, since the pre-warp body is a real human.
3. **Warp it** (`humanform.species.warp`). Each bone gets a new rest transform:
   - **length** along the bone (femur and humerus shortened most for a dwarf, all segments for a gnome);
   - **girth** across the bone, kept by default so a short thigh stays as thick (a dwarf's heavy limbs) or
     scaled for a slender elf;
   - **head** a uniform scale about the neck joint;
   - **widths** shoulder and hip spread by moving the clavicle and hip roots out;
   - **spine curve** a rest-pose bend of the spine bones: kyphosis for a troll's hunch, a straighter back for an
     elf.

   Vertices follow by linear blend skinning with the body's own weights, computed in numpy
   (`v' = sum_i w_i M'_i M_i^-1 v`), applied to the base mesh, every shape key, and every object skinned to the
   rig (eyes, brows, lashes, teeth). Then the bones' rest heads and tails are moved to match. There are no
   Blender operators, so it runs the same headless, and there is no applied modifier to lose shape keys to.
   The same warp is how WoW's single skeleton serves every race.
4. **Keep the individual.** Like the `stylized` branch, each target is the fitted human's own measure shifted by
   `species - realistic mean`, not snapped to one canon, so two dwarves from different briefs still differ.
5. **Check it** against the species preset (humancheck with `preset=<species>`). Measure-based checks that are
   human-only (`hip_above_crotch`, face relief limits) take their species' ranges from the preset.

The spine curve lives in the rest pose, not only in a posture, because it is a body shape: garments are cut to
it and flesh sits on it. rig-anything reads "upright" from head-over-hips, which a hunch keeps. The troll's
forward lean while walking is still a `posture` on top.

### Layer 2: head

- **Size** is in layer 1 (the head scale). A preset gives `heads`, and the warp derives the scale.
- **Shape**: MPFB's whole-head shape targets (`FACE_SHAPES`) and face levers, at weights past a human's typical
  ones but inside [-1, 1]. A dwarf takes a square, wide jaw; an elf an inverted triangle, a narrow nose and a
  long neck.
- **Features**: MPFB ships `ears/l|r-ear-shape-pointed.target.gz`, loadable through `scaffold._load_targets`
  (it is a single file, not an incr/decr pair, so it needs its own suffix). Brow ridges, heavy noses and tusk
  bumps are `delta.py` shapes (per-vertex normal displacements on the shared hm08 mesh), stored in the library
  like any part. Tusks themselves are small rigid meshes parented to the jaw bone.
- **Non-human heads (later)**: a gnoll's hyena muzzle cannot come from deforming a human face. It is a **head
  graft**: a library head mesh (sculpted, or generated and cleaned) joined at the neck seam to the body, its
  weights transferred from the neck and head bones, with a jaw bone for rig-anything's jaw support. The seam is
  a fixed vertex loop on hm08 so any graft fits any body.

### Layer 3: surface

- **Skin palette**: a species gives a range of tones (a troll's grey-green, an orc's olive-green, a gnoll's
  tawny), and a brief's `skin` inside it or a draw from it by seed. `skin.py`'s regional tints are relative to
  the mean tone, so they carry over. Its contrast floors (palms paler, lips redder) are human; a species can
  turn a region off or give it its own direction.
- **Pattern**: mottling already exists in `skin.py`. Species add spots (gnoll), stripes and blotches as
  procedural masks in the same bake.
- **Subsurface**: the scatter colour follows the tone. A green troll scatters green-red, not a human red.
- **Fur (later)**: two tools, chosen by length.
  - **Short fur and body hair**: shell texturing in Godot, the games standard: N offset shells of the skin
    mesh with a strand mask texture, density and length from a painted map. Cheap, animates with the skin.
  - **Manes, beards, tails**: `hair.py`'s strand cards, which already grow from painted regions for beards.
  Fur coverage is a map on hm08 (face, back, arms), so it transfers between bodies. Its check is the same as
  hair's: the skin under dense fur is not drawn (the wardrobe `covered` mechanism).

### Layer 4: movement

The Froude scaling already gives each species its scale. What a species adds is **style from the build**,
derived rather than hand-picked, so a user-described species moves plausibly without anyone choosing a gait:

| measured on the warped body | drives | direction, from the research |
|---|---|---|
| trunk-to-leg ratio above human | hip abduction, pelvic list and obliquity, lumbar rotation, anterior tilt | up (achondroplasia **[measured]**) |
| trunk-to-leg ratio above human | knee flexion in stance | down **[measured]** |
| mass per stature^3 (stockiness) | duty factor, stance width, bounce | longer contact, wider, less bounce |
| total mass above ~300 kg | knee straightening, aerial phase | straighter; no flight phase (runs become fast walks) **[measured, animals]** |
| arm length to hip height | arm swing amplitude and its frequency | from the pendulum (`limb_frequencies`, already measured) |

These go in rig-anything as `derive_style(bodymap, mass)`, which returns a `STYLE_KEYS` dict, merged under the
spec's own `[moves] style` (the user's words win). A species may add named styles too (`dwarf_stomp`,
`elf_light`) for the parts no measure implies: an elf's lightness is convention, not physics.

**Checks**: every baked walk's Fr lies between 0.18 and 0.35; planted feet drift under the existing limit;
the hands reach the hips and the top of the head (a dwarf with a helmet, drinking), warned if not.

### Every drawn part of the body: full anatomy on every species

A species body is a whole body, with the same anatomical coverage as a human one, never a simplified doll
(the user's rule, 2026-09-21). Everything the human work draws is carried through every layer:

| part | where it comes from for a human | what a species must do with it |
|---|---|---|
| nipples and areolae | MPFB's `nipple`/`nippleTip` groups; skin region `nipple` | kept, warped with the chest, tinted relative to the species tone |
| genitals, male and female | skin region `genital`; geometry from `humanform.genitals` (branch `fig-genital-anatomy`, opt-in via `[body] genitals`), thigh-clearance corrective bones | kept, warped with the pelvis; genital skin tone-relative; the clearance correctives run on the warped legs (a short-legged body crowds the crotch more, so it is a test case) |
| breasts, butt, belly, other flesh | follow-through flesh zones and jiggle bones | the zones are anatomical, read off the skeleton, so they follow the warp; species builds run `[flesh]` like humans |
| navel, nails, knuckles, knees, elbows, palms and soles | MPFB groups; skin regions | kept and tone-relative |
| eyes, lashes, brows, teeth, tongue, ears | MPFB proxies and humanform eyes, brows, hair | kept, skinned to the rig, moved by the warp; head features (tusks, pointed ears) add to them, never replace them |
| body hair, beards | humanform hair | kept; fur (layer 3) is added over the same coverage maps |

Rules that follow from this:

- **A skin region is never turned off because of its colour.** Region shifts are relative to the tone
  (layer 3), so a green body's nipples, lips and genital skin are darker and more saturated in green, not
  removed. `regions_off` exists only for anatomy the *description* says the creature does not have. A reptile
  folk with no nipples, or an egg-layer with no navel, is stated as `anatomy.absent` with a reason, and the
  report says so.
- **Anatomy scales with the body by the same general laws.** Sizes are relative to the part they sit on
  (areola to chest breadth, genitals to pelvis), so a warped body keeps plausible anatomy without a
  per-species rule. A description may override a size (`anatomy.scale`), and the check reports it.
- **An inventory check.** After the warp, the bake and the export, every expected part is present, skinned
  and not inside another part (genitals against the thighs, nipples against a garment's backstop), for every
  species. A part that is missing and not declared absent fails the build.
- **Non-human baselines** (layer 5: a gnoll's canine body) need their own anatomy designed with the same
  coverage before they ship. A grafted head or leg never leaves the body's anatomy out.
- The conventions of the human work carry over. Genitals stay opt-in, never in a default build. The
  likeness rules (no jiggle, no revealing garment) are for real people's likenesses and do not apply to
  invented creatures.

### Layer 5: anatomy (later)

Digitigrade legs (gnoll, satyr) add a segment: rig-anything already rigs the hopper leg (rabbit, cricket) and
reads its joints. Tails are rig-anything tails. Both need the head-graft style of mesh work on the body and are
their own round.

## The spec

A species preset is a file, `humanform/data/species/<id>.json`:

```json
{
  "schema": "humanform-species/1",
  "id": "dwarf",
  "label": "Dwarf: short, stocky, long trunk, short limbs (softened achondroplasia)",
  "baseline": "human",
  "sources": ["D&D 5e PHB heights", "achondroplasia anthropometry (ResearchGate 327266038)"],
  "stature": {"female": [1.15, 1.40], "male": [1.20, 1.45]},
  "bmi": [24, 34],
  "heads": [4.6, 0.35],
  "ratios": { "hip_joint": {"any": [0.38, 0.02]}, "knee_joint": {"any": [0.20, 0.015]}, "...": "..." },
  "segments": { "femur": 0.62, "tibia": 0.78, "humerus": 0.66, "forearm": 0.80, "hand": 0.95, "foot": 0.95 },
  "girth": { "legs": 1.0, "arms": 1.05, "neck": 1.25 },
  "widths": { "shoulder_width": 1.10, "hip_width": 1.05 },
  "spine": { "kyphosis_deg": 0, "lordosis_deg": 6 },
  "head": { "shape": "square", "shape_weight": 0.7, "features": {"brow_ridge": 0.4} },
  "skin": { "palette": [[0.62, 0.45, 0.35], [0.80, 0.62, 0.50]], "regions_off": [] },
  "moves": { "style": null, "notes": "derive_style gives the roll; no named style needed" }
}
```

`ratios` uses `presets.json`'s format (`[target, tol]` as a fraction of H, keyed `female`/`male`/`any`), so
humancheck grades a species exactly as it grades the realistic preset. `segments`, `girth` and `widths` are the
warp's factors against the fitted human; the warp solves the final factors so the measured joints land on
`ratios`, and these are its starting point and the shape of the change.

In a brief and a character spec, a species is a named preset **or an inline description**. A name is a shortcut
for a worked example; an inline table is how a user's own creature is made, with no file and no code:

```toml
[body]
species = "dwarf"          # a worked example: humanform/data/species/dwarf.json; omitted is "human"
sex = "male"
stature = 1.32
build = "muscular"
```

```toml
[body]                     # a creature nobody wrote a preset for
sex = "female"
stature = 1.15
build = "stocky"

[body.species]             # observables, solved by species_design.solve; anything left out is derived
heads = 5.0
fingertips_at = "knee"
trunk_to_leg = 0.85
hunch_deg = 15
skin = { tone = [0.46, 0.50, 0.40], pattern = { kind = "blotches", colour = [0.30, 0.34, 0.26], amount = 0.5 } }
head = { shape = "square", features = { brow_ridge = 0.6, ears_large = 0.8 } }
```

`style` (realistic, stylized) still chooses how the pre-warp human is drawn.

**Worked examples**, chosen because each exercises a different part of the method (they are test cases, not
the product):

| example | heads | what it exercises | layers |
|---|---|---|---|
| elf | 8.3 | a small warp past the human range: long legs, slender girth, long neck | 1, 2 |
| halfling | 5.5 | proportionate short stature; allometry makes the head big | 1 |
| gnome | 4.3 | the same at its limit (1.0 m) | 1, 2 |
| dwarf | 5.0 | disproportionate: short limbs (femur, humerus most) on a full trunk | 1, 2, 4 |
| orc | 7.5 | widths and girth; a non-human tone; attached parts (tusks) | 1, 2, 3 |
| goblin | 5.0 | short and hunched: the spine curve with a big-headed body | 1, 2, 3 |
| troll | 7.0 at 2.6 m | large: square-cube mass, kyphosis, reach to the knee, the heavy gait | 1, 2, 3, 4 |
| gnoll | - | past the human baseline: a grafted head, fur, digitigrade legs | 2 (graft), 3 (fur), 5 |

## Steps

1. **Species presets and the proportion warp** (humanform). `species.py` (load, validate, the pre-warp human,
   the warp, spine curve), `sheet.new(species=...)`, `pipeline.make` warps after the rig, humancheck grades
   against the species, presets for the first seven species. Species smoke bodies in grungist-creek
   (`characters/species_*.toml`). *This round.*
2. **Head features** (humanform): pointed ears, brow ridge, heavy nose, tusk bumps as parts; tusks as meshes.
3. **Movement from the build** (rig-anything): `derive_style`, the Fr and reach checks.
4. **Surface** (humanform, lookdev): species palettes, patterns, subsurface tint; turn off human-only regions.
5. **The method end to end**: `species_design.solve` / `design` / `explain`, inline `[body.species]`, and
   `references/species-design.md` (how to read a description or a concept image into observables). *Pulled
   into this round (the user's direction): it is the product, the presets are its examples.*
6. **Fur**: Godot shell fur plus strand cards; coverage maps on hm08.
7. **Head grafts and digitigrade legs**: the gnoll round.

## Done when

- `build_many` builds a dwarf, elf, gnome and troll fresh from their specs; each passes humancheck against its
  species with no fails, and rig-anything's clips export with every playback check passing.
- In Godot (`people_demo` or a species demo), orbiting in close, each reads as its species at a glance, and the
  dwarf's walk is visibly quicker and shorter-stepped than the human beside it.
- The human smoke bodies build unchanged (a species of `human` takes no new code path).
- Every species build passes the anatomy inventory: nipples, genital skin (and genital geometry when opted in),
  navel, nails, eyes, teeth and tongue present, skinned, tone-relative and not interpenetrating. A dwarf and a
  troll build with `[flesh]` and, once `fig-genital-anatomy` is merged, with `genitals = true` as smoke cases.
- A spec asking for something the warp cannot do (a 0.5 m dwarf, heads out of the species' range, an unknown
  species) is refused before a build, with the range in the message.

## Polish after the first creatures (species-1-polish, 2026-09-22)

Four defects seen in Godot on the drow, cyclops and mermaid, each now with a check that fails before a build ships:

- **Teeth at the lip crack, on every body.** MPFB's closed lips do not seal (0.3-2.8 mm apart), and its teeth bite
  edge to edge right at the crack, so a pale dashed line showed at the slit (Godot's subsurface blur banded it on a
  dark skin). `features.mouth` now gives every mouth a seal - a dark strip of membrane just behind the lip line,
  inside the lips' flesh, with their weights - and keeps the teeth behind it. Check: `features.closed_mouth` casts
  rays at the lips from the front, 3/4 and near profile, above and below; the bake stage fails if one reaches a tooth
  (2739 of 158k rays did on the first drow; 0 now).
- **The cyclops' eye bulged and stared.** Its ball stood 0.35 radii ahead of the nose bridge and a fixed almond left
  half of it bare. `eye_layout` now holds any new eye to the person's eye on the same head, measured
  (`eye_layout.exposure`): the ball as flush with the face around it, the lids' opening the same share of the ball.
  Check: `exposure_problems` fails a new eye more bare (+25%), more open or further out of its face than that.
- **The mermaid's waist read as dirty blotches.** Scales on a graft now stand in staggered, overlapping rows along
  the body (`skin.SCALE_ROWS`, a 3D lattice), shrinking by halves across the fade, each scale whole and on or off by
  the fade at its own centre.
- **A thick-thighed body's crotch read low** (cyclops 0.423 H against 0.490): the measure took the thighs pressing
  across the midline for the crotch. The crotch loop must now reach round both legs' axes (`measure`).

Also: the palest species tone cap is 0.55 linear luma (the elf clipped past white at 0.59), and deep regions have
a chroma ceiling in the skin contrast check (`skin.DEEP_CHROMA_MAX`).

Round 2 (the coordinator's follow-ups):

- **The cyclops eye read as a slit** once held to its own pre-warp man (a squinting 40-year-old: 15% bare, lids 0.24
  as high as wide). A new eye is now held to the more open of that person's eye and `eye_layout.EYE_NORM` (a person's
  eye as the game shows it, measured on baked MPFB bodies: 19% bare, 0.32), matching the bare share and the lid
  shape (height over width), both relative, so the opening scales with the eye. The check fails a slit (too little
  bare, too flat) as well as a stare. A single median eye under two separate brows looks odd; a continuous brow
  arch over it is the next step (brows, not done here). Its upper lash cards stand up like a picket; also open.
- **The dwarf's orange genitals** were the tint, not the light through the shell: rendered in Godot with
  transmittance off, the pixels were identical (158, 110, 83 both). The species genital tint's saturation exponent
  is 0.3 (was 0.7: 1.36x skin chroma, now 1.04x) and the contrast check caps genital chroma at 1.25x skin's.
- **The mermaid's waist band at 4 m** was not albedo (the baked albedo's bands run monotonic from scales to skin) but
  the shape: the belly curved in under itself onto the seam ring, and the tail bulged out below it - a crease facing
  down (normal z -0.5 at the front). `graft` now fairs the band over the seam, the seam ring included, radially
  (`FAIR`) and reports the band's facing (`seam_band_nz`, warned under `FAIR_NZ_MIN`); the scales' shading is
  normalised to a mean of 1 (`_scale_mean_shade`), and `skin.seam_tone` checks the albedo's mean across the seam
  (the bake stage fails when a band leaves the skin-to-scales range).
