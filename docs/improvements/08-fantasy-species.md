# 08 - Fantasy species: dwarves, elves, gnomes, trolls, gnolls and whatever the user describes

Category: **6 feature gaps**, but every layer leans on work that already exists. A species is data, and the
code that turns data into a body, a rig and a gait is shared by every species, including the human one.

> **Picking this up?** Steps 1-5 shipped in the `species-1` round (2026-09-22), with a legs-to-tail graft and
> eye layouts from the step 7 list: see NEXT.md, "Fantasy species round", for what shipped and what is open.
> Next: fur (step 6), then head grafts and digitigrade legs (step 7, the gnoll).

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

## Round 2: fur, a muzzle, digitigrade legs - the gnoll (2026-09-22)

The same rule: a general mechanism with named presets over it, driven by numbers, never a gnoll branch in the
code. A gnoll is the worked example, as the dwarf was for the warp: canine head, fur, digitigrade legs, a tail.

**Fur** is two tools, chosen by length, the way games do it:
- **Shell fur** for anything short (a pelt, a muzzle's nap, a forearm's hair): N offset copies of the skin
  shell drawn in Godot with a strand mask, density and length from a coverage map painted on hm08, so it
  transfers between bodies. Cheap, and it follows the skin with no extra rig.
- **Strand cards** (humanform's hair) for what hangs and moves: a mane, a ruff, a tail's brush, a beard.
  follow-through springs them.
The coverage map is the same object for both: a region, a length in metres, a density and a direction. It says
which skin the fur covers, so the skin under dense fur can be left undrawn the way wardrobe does it.
Its checks are hair's: the mip check (a fur mask must not tile into patches), a silhouette check at 4 m, and
the coverage map against the anatomy inventory (fur is a part, so a body that should have it and does not
fails).

**Fur shipped (species-2-fur, 2026-09-22).** Shell fur, the coverage map and its checks; strand cards for a
mane or a tail's brush did not, and want an API hair.py does not have (see "Open" below).

- **The coverage map is per vertex of hm08, not a texture.** hm08's shipping UV atlas *overlaps itself* -
  about a fifth of its texels are claimed by two different parts of the body (`fur.atlas_overlap` measures
  it), so which value a texel ends up with depends on the order the triangles happen to be rasterised in.
  The first map came back with furred hands, furred feet and a furred scalp, and raising the resolution did
  not help because it is not a resolution problem. Density, length and the flow's direction now travel as
  the `hf_fur` colour attribute (glTF COLOR_0, exported by name: `rig_analysis.export.VERTEX_COLOUR_MAPS`);
  they vary over centimetres, which hm08's 8-15 mm quads carry easily. Only colour and the tiled strand
  mask stay textures - colour survives the overlap because the furred triangles are drawn last, and the
  strand mask is tiled and never touches the atlas.
- **Three things a join does that cost a rebuild each**, now handled and worth knowing:
  Blender's join fills a *colour* attribute's missing values with **white**, not zero, so the hair cap, the
  brows and the lashes joined into the body after the map was written came out at full density and full
  length (`fur.refresh_vcol` writes the map again at bake time, masked by `hf_fur_skin`); Godot's glTF
  importer turns "albedo from vertex colour" on for every material on a mesh that has one, and the fur
  runtime strips the colour off the body mesh once the shells have their copy; and a shell built from a
  surface that carries no map is not skin - kept, the hair cap was drawn seventeen times over as fur.
- **A region is solid inside and feathered at its rim**, and lengths blend across the rim. Taken as raw
  area weights, a ruff whose mask peaked at 0.5 put half the upper body in the band where the skin is still
  drawn under the fur, and a 45 mm ruff beside a 12 mm pelt stood off the neck as a collar of sheets.
- **An area may not grow past where it reached.** Smoothing alone carried "the face" over the crown, and a
  3 mm nap at density 0.7 drew a black skull cap over the hair in Godot.
- **Cost, measured** (Godot 4.7, one 1.78 m body at 900x900): 23 -> 59 draw calls, 59k -> 358k primitives,
  4.2 -> 6.2 ms a frame for 17 shells. The shells are the furred skin only, and only the base coat casts a
  shadow.
- **A coat, not a speckle (the coordinator's review).** At 900 strands a square centimetre and 0.45 mm
  across, a texel was a strand and the pelt read at 2 m as dirt on skin: per-texel noise is what dirt looks
  like. Fur reads as fur by its **clumps**. The mask is now 230 strands a square centimetre at 0.95 mm,
  gathered into clumps 4.2 mm apart (`CLUMP_PULL`, `CLUMP_SHARE`), and carries a second channel - each
  strand's own tone, held along its whole length, so a clump lies together. The base coat sits close in
  tone to the strands over it (`root_shade` 0.70 -> 0.86, `rim` 0.22 -> 0.12, AO floor 0.72 -> 0.86), or
  every gap between strands reads as a dark fleck.
- **The fur ends into the skin, not against it.** Its colour and its length are feathered over EDGE_RINGS
  rings of the mesh from where the skin still shows through (COVER_DENSITY, not bare skin: a vertex at
  density 0.03 is furred by the map and bare to the eye). Colour blends between regions with its own,
  gentler weighting than length (BLEND_COLOUR against BLEND_SHARP): a 45 mm ruff must keep its length
  against a 12 mm pelt, and must not keep its tone against it.
  Check: **`fur.edge_tone`**, `skin.seam_tone`'s question asked of a fur boundary - the step in the fur's
  tone across one edge of the mesh near where the fur ends, 99th percentile, against EDGE_TOL. It is
  measured locally and not by binning the body: binned, the bands mix regions and a face nap's own paler
  colour read as a step that was not there. It caught the dark rings at 0.071 and they now measure 0.005
  (fur_pelt) and 0.013 (fur_dwarf).
- **Black gloves and socks (the coordinator's second review).** At 2 m both furred bodies had black patches
  at the wrists, the hands, the ankles and the hairline - worse than a tone step, and the edge check said
  they were fine, because they were not a step in the *data*. The colour map was filled with **black** where
  no triangle reached it and grown only two texels; round the small islands - the hands, the wrists, the
  feet - a bilinear sample pulled that black straight into the coat. It is now filled with the body's own
  skin tone and grown `DILATE_PASSES` (16) texels, and the patches are gone, the hairline band with them.
  Check: **`fur.dark_patches`** - any patch of furred body more than `DARK_TOL` in luma below *its own
  surface colour*, measured on the colour map as Godot samples it, mip by mip, at 0.6 m and 4 m. Against a
  global coat mean it failed the pattern's own spots, which are meant to be dark; against the surface it
  sits on, a spot passes and a bled black does not. 2.4% of the body failed it before, 0.0% after.
- **Open**: strand cards for a mane,
  a ruff past 8 cm or a tail's brush need an entry point `hair.py` does not have: it grows scalp hair from
  a landmark hairline, with no way to hand it a painted region. What fur needs from it is
  `hair.cards(body, field, length_m, volume, colour, root_bone)` where `field` is a per-vertex weight -
  `brows.beard_field` is the shape of it.

**Beards become strands.** Today they are layered textured shells: a flat decal with a smooth outline. A beard
is hair, so it should be the same strand cards as scalp hair, rooted on the beard field, with length and
volume driving the cards, and follow-through sway on the long ones. The shell stays for stubble, where it is
right.

### Beards as strand cards (done, `species-2-hair`)

A beard is now a **root mat plus strand cards** (`humanform.brows._beard_cards`), and the layered shells are
gone. One shell of the body's own faces stays as the mat under the hairs - the thing that hides skin, as a
scalp's cap does - and everything above it is cards:

- **Roots** are scattered over `beard_field` at the style's `density` (cards per square metre), per body face,
  by area and by how far inside the fade that face is, so the edge thins instead of stopping.
- **A card** is a ribbon of three columns bowed out of its own chord (a flat card vanishes edge-on). It starts
  along the skin's own downhill direction - world down projected onto the tangent plane, straight down where
  the skin faces down, as under the chin - turns toward gravity by `droop` at each step, and is held
  `BEARD_CARD_CLEAR_M` off the body all the way; below the chin that clearance grows to `BEARD_HANG_CLEAR_M`,
  so it hangs in front of the chest and the shirt on it rather than through them.
- **Length** is the style's at the chin, less toward the moustache on the same ramp the layers used, jittered
  per card; a moustache card is capped (`BEARD_MOUSTACHE_MAX_M`, jittered) or a long beard buries the mouth.
- **Clumps.** Each clump grows a spine and its members bend into it over their second half: locks, not a pelt.
  `braids` winds the hanging clumps round their spine instead, on a radius that pulses down the rope - a
  dwarf's plait, for the price of re-placing points that were already there.
- **The texture is the beard's own**, in a second material with no under-layer (a card must show gaps), and
  the UVs are arc length across and along the card over the tile, so texels stay square and the mip check
  still passes. The fade falls from the root's value to `BEARD_CARD_TIP_FADE` over the last of the card,
  which drops the texture's hairs one by one by rank: the end is a scatter of tips, not a cut across the
  texture. That is what the silhouette check measures.
- **The hanging part is its own mesh** (`<name>_beard_strand`) with follow-through's strand contract, one
  chain per lock (`ft_centrelines`: a single chain down a sheet as wide as a jaw twists it, which is why the
  long_loose curtain is not chained). The pipeline keeps it loose exactly as it keeps a ponytail, and the
  strand stage springs it.

**Three checks that catch what the eye caught before:**

- `brows._coverage_check` - for every point well inside each of the field's own regions (`moustache`,
  `corners`, `chin`, `jaw`), the distance to the nearest card root against the spacing the density asks for.
  It names the bald region: the notch under the lower lip and the corners of the mouth are where the field is
  narrowest and are the first places a face-by-face sampler leaves bare.
- `hairtex.silhouette_check` - rasterises the part's own geometry with the fade's vertex alpha at the screen
  resolution of 0.6 m and 4 m, front and side, and measures how far its lower outline wanders from a smoothed
  copy of itself. A shell's outline is the fade's zero line, a curve, and measures near nothing; the cards
  measure 2-5 px close up and still a fraction of one across a room. It also fails a beard whose area
  collapses between the two distances - cards too thin to hold the shape at a distance.
- `verify_strands.gd` now measures penetration against **every collider bone the strand must clear**, the
  chest included (`torso_*`), not the head alone, and `follow_through.strand.colliders(torso=True)` measures
  those capsules for a beard. It earned its keep at once: on the hair material's own limits the dwarf's beard
  swung 70-75 degrees on a run and went 4 cm into his own face, so the registry's `beard` type stiffens and
  damps it (16/22 degrees, damping 0.85).

`hair.beard_braids` (0..6) is the spec dial; `stubble` stays a pure shell and says why in the code.

**A non-human head** is a **parametric muzzle**, not an imported mesh: the head features mechanism (regions,
landmarks, displacement, attached parts) already reshapes a head, so a snout is a general feature with a
length, a width, a bridge height, a nose pad and a lip line, growing the human face forward along the jaw's
axis; ears are attached parts, already there. This keeps every body on hm08, so skin, teeth, eyes, the warp,
wardrobe and the library all keep working. A grafted mesh head stays the fallback for a head no amount of
reshaping reaches (a beak, a horse's skull), and it is the harder, later path.
A muzzle needs a **jaw bone** so the mouth opens - rig-anything has jaw support for dragons and whales, and
humanform's bodies have never had one. That unlocks bites, roars and speech for every body, not just creatures.

**Digitigrade legs** add a segment: the foot becomes a third leg bone (the metatarsals stand up), and the
ankle sits high, where a dog's hock is. rig-anything already rigs and walks a hopper's leg (rabbit, cricket),
so this is a leg plan, not new maths: the plan says how many segments a leg has and where they fold, the
gait's IK and the Froude scaling follow. The checks are the existing ones (foot drift, floor penetration,
joint folding, balance) plus the knee/hock direction.

**Open from round 1 to fix here:** the cyclops' square pupil, the shadow band across his face at eye height,
and the pale specks where the brow cards meet.

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

Round 3 (the cyclops' face):

- **Brows follow the eyes** (`eye_layout._brow_cards`, `brows._side_cards`): every new eye gets a brow arch, the
  person's brow carried from their eye and scaled with the new one; a median eye takes both halves, heads meeting on
  the midline (`BROW_GAP` apart) - one continuous arch. A body without an eye layout takes the human pair unchanged.
- **Lashes lie along the lid.** The picket fence had a plain cause: MPFB's lash UVs are an atlas, and `V < 0.2` taken
  as the root row called half of each card roots, all laid on the lid margin with the rest standing off it. Roots are
  now the points nearest the ball (`_lash_roots`), and the rest keep their offset in the lid's own frame
  (`_lid_frames`). Check: `lash_angles` - the mean angle out of the lid, against the person's (60 deg; the new eye's
  63 / 61), fails past `LASH_ANGLE_TOL`.
- **The socket is the person's, scaled** (`_socket`): the skin's depth round a new eye - lid fold, brow ridge
  overhang and height, the rim - read off the person's eye in its radii and laid round the new eye in its radii
  (their outer half on both sides of a median eye), before the lids are carved. The exposed share holds (19%).
- Open: a band of shadow still runs across the face at the eye's height under the midday sun, from the closed
  orbits either side under the brow ridge; the brow cards' heads show pale specks where the card texture's head
  lies on skin.

## Round 2, step 7: digitigrade legs and a tail on a biped (species-2-legs, 2026-09-22)

A **leg plan** is now a thing the pipeline has, not a special case anyone branches on.

- **`humanform/legs.py`** (a new module, not `graft.py`: a graft REPLACES a pair - it cuts at the hips and lofts
  something else - while a digitigrade leg is a RESHAPE of the leg the body already has, so it borrows the warp's
  machinery instead and every UV, vertex index, toe and toenail comes through untouched). Knobs: `stand` (how much
  of the metatarsus is vertical; a person's foot already reads 0.43, a dog's cannon 0.85-0.95), `metatarsal`,
  `toe`, `girth`, `knee` (the stifle's included angle) and `fold` (only knee forward / hock back is built).
  The solve holds the hip where it stands and lays the toes flat from the ball, so **stature and hip height are
  untouched**: the shank is scaled by the one factor that puts the hip back at its height and the leg folds under
  the body. Refused before a vertex moves when the shank scale (0.55-1.15), the hock over the hip (0.10-0.45), the
  metatarsus over the shank (0.10-0.60) or the toes over the metatarsus (0.10-0.85) leave their ranges.
- **`humanform/tail.py`**: a tail BESIDE the legs (a tail instead of them is still the graft; both is refused).
  A patch of skin at the sacrum goes and its boundary loop is lofted along an arc (`droop`, `curve`), rounded at
  the tip, UVs in the atlas's free rectangle, a `tail.000...` chain off the pelvis - which `bodymap` already reads
  as a tail, so every gait curls and swings it with no new code. Lengths are fractions of hip height.
- **rig-anything reads the plan off the geometry**: `bodymap` calls an end bone within 30 degrees of the leg's
  standing axis a standing segment and one past 60 a plate on the ground (pro rata between), and gives each leg
  `plan`, `stand` and `ground` - the effective leg, `a + b` plantigrade (exactly as before) and `a + b + stand`
  digitigrade. `Poser.leg_len` and the swing lift are that; `Reach` widens the end bone's roll when it stands.
  The gait needed no new maths: Froude scales by hip height above the contact plane, which a leg plan preserves.
- **Checks upfront**: the leg-plan solve above; `bodymap` warnings for a hock out of range; `verify.tail_gap` on
  every clip (the tail's skin against the legs', failing a clip that closes the gap - the limit is the smaller of
  0.008 of body height and half the rest gap, so a rabbit's resting scut is not failed for walking); the anatomy
  inventory knows a tail; `species_design` and character-pipeline's spec check refuse `legs`/`tail` out of range.
- **`satyr`** is the worked example preset (digitigrade legs, a short tail, ram horns).

Measured, on one 1.80 m body built both ways at Froude 0.2: hip height 0.900 (plantigrade) against 0.904
(digitigrade), stride 1.277 / 1.283 m, cadence 1.04 Hz both - **the Froude scaling holds**, because the plan
preserves hip height by construction. What the longer effective leg (0.841 -> 1.009 m) changes is the posture and
the swing: the stance knee folds to 89 degrees against 116, the swing foot lifts 0.126 m against 0.105, and the
stroke is 0.76 of the leg against 0.92.

Open:

- The leg still reads as a long-footed person at four metres unless `stand`/`metatarsal` are pushed (the satyr
  ships at 0.95 / 2.2). The toes are still five human toes; a hoof or a paw is a mesh job, not a plan.
- The tail's root has a slight ridge where it leaves the sacrum: `graft` fairs its seam band radially and this
  does not. A tuft at the tip (`tuft` is reserved in `tail.KEYS`) is not made.
- A tail is skinned but has no follow-through spec of its own yet: its sway is the gait's, not sprung.

### Round 2b: a foot plan (species-2-legs, 2026-09-22)

The flaw the first digitigrade body showed in Godot: a raised hock over a human foot with five long toes lying
flat reads as **a person on tiptoe, not a paw**. `humanform/feet.py` is the other half of the leg plan, and it
is parameters rather than names - `foot = "paw"`, `"hoof"`, or a table of either (the key is `foot`, not
`feet`: `feet` is already the observable for foot LENGTH). `human` is the setting that changes nothing.

- **`toes`**: the five hm08 toes are never deleted (the vertex order is what the skin regions and the brow fits
  index). Each vertex is assigned to its own toe by **MPFB's own joint helpers** (`joint-l-toe-N-K`) and the
  toes are **fused** onto `toes` contiguous groups, fully at the tips and not at all at the ball. `splay`
  spreads the groups, `width` fattens one across the foot - and only a third of that through it, because
  scaling the whole offset doubled the toes' depth and put the sole 3 cm through the floor.
- **The pads** (`pad`, `toe_pad`, `heel_pad`) are domes pressed into the sole in toe lengths, under the
  standing ball, under each toe group and at the back of the foot; the body is re-stood afterwards, so a pad
  adds its own thickness under the foot as an animal's does (11-13 mm on these bodies).
- **A claw and a hoof are the head's own attached-part mechanism** (`features._part`, read-only from here),
  anchored on the **distal flesh of each toe group** - a nail grows out of the TOP of the toe's end, and
  centred its base ring dipped below the pads whatever its length was - and skinned 100% to the toe bone in
  `<human>_footparts`. A hoof is that mechanism blunt: short, nearly as wide at the tip as the base, curved
  down hard, sunk deep enough to cap the toe. A claw is data, not a mesh.
- **The nail's length is solved, not guessed.** Which length works depends on the leg plan's toe, the fuse and
  the pads: the fraction that put a paw's claws 13 mm through the floor left the satyr's hoof 11 mm in the air.
  The build lays the nails, measures what carries with the contact check, corrects and lays them again; a
  solved length outside 0.15-1.6 toe lengths is refused ("it is reaching for the ground sideways"), and an
  explicit `claw.length` is taken as given and held to the same check.
- **The check that matters** (`feet.contact`): what the plan nominates must be the lowest thing on the foot.
  The paw's claws stand 3.5 mm ABOVE the pads and the satyr's hooves 6 mm BELOW the flesh; a claw that would
  walk the creature on its nails and a hoof left in the air are each refused with the millimetres measured.
  Both controls were seen to fail before the defaults landed.
- The plan measures what it did to hm08's toenails against the foot they sit on, before and after the whole
  body plan, and hands that to the anatomy inventory as `expected` - as the eyes hand it their allometry - so a
  fused, shortened set of nails is graded against the plan rather than against a human's foot.
  `species.inventory` now looks `expected` up by a sub-part's full name first, so that credit cannot excuse the
  fingernails.

The satyr is the hoof example (and its digits are now 0.95 of a human's: a goat's length is in the cannon, not
the toes). Both it and a paw-footed digitigrade body build fresh, pass 13 anatomy parts with no fails, pass all
eight clips' playback checks and export with verified durations.

**In Godot at 4 m and close**: the satyr now reads as a goat leg - hock high, a long cannon, a short cloven toe
capped in dark horn - where the same body a round ago read as a long-footed person. The paw's four fused toes
spread on the ground with small claws clear of them, and mid-swing the whole foot folds back under the leg. In
the walk the contact is a short patch under the toe pads: the hoof sets the horn down first and rolls over it,
and the paw lands and leaves on its pads with the claw tips visibly off the floor.

Open: the paw's toes are still long, because the leg plan's `toe` default is 1.7 and a paw wants less; there is
no hand plan yet; the pads are a smooth dome rather than separate lobes, and nothing paints them a darker tone.

### Round 2c: the silhouette (species-2-legs, 2026-09-22)

The parts were right and the leg still read wrong: a hock, pads, claws and a hoof over a femur, tibia,
metatarsus and digits that were still a human's, and at four metres the figure read as a person walking on
their toes. **The leg plan's input is now the silhouette** - a ratio set - and the per-segment scales are
solved to reach it.

| ratio set | femur : tibia : metatarsus : digits | stifle | stand | taper (thigh/shank/cannon/digits) |
|---|---|---|---|---|
| `human` | 0.394 : 0.398 : 0.137 : 0.070 | 175 deg | 0.43 | 1.0 / 1.0 / 1.0 / 1.0 |
| `canine` | 0.317 : 0.343 : 0.270 : 0.070 | 116 deg | 0.90 | 1.20 / 0.80 / 0.50 / 0.85 |
| `caprine` | 0.299 : 0.352 : 0.313 : 0.036 | 120 deg | 0.95 | 1.14 / 0.68 / 0.38 / 0.85 |

Sources (measured over folklore; `legs.RATIOS` carries them in the code): **Fischer & Blickhan 2006**, the
tri-segmented therian limb - femur, shank and tarsus+metatarsus near-equal (1:1:1) in a crouched mammal;
**Croft & Lorente 2021** (PLoS ONE 16(8):e0256371), the metatarsal-femur ratio - cursorial carnivorans at Mt:F
0.38-0.65, cursorial ungulates (pecoran ruminants, Caprinae among them) at Mt:F >= 0.65; and the comparative
rule that a cursor lengthens the distal limb and stands on SHORT digits, an unguligrade one shortest of all.
The crural indices (1.08, 1.18) are conventional and the weakest numbers here. `toe`'s old default of 1.7 was
the main offender and is gone: the canine solve now scales the digits by about 1.0 and the metatarsus by 2.0.

Three things beyond the lengths turned out to matter as much:

- **The taper.** A person's leg is nearly one girth from hip to ankle; an animal's is a heavy thigh over a thin
  shank over a bare cannon. `girth` is now a table per segment and carried by the ratio set.
- **The stifle.** A dog stands its stifle near 116 degrees, not 130. The ratio set carries that too.
- **Where the foot stands.** A plantigrade foot's ball sits 0.17 hip heights ahead of the hip with the ankle
  under it; a digitigrade one stands on its TOES and they take the sole's place under the body, which is what
  puts the hock behind the hip and deepens the zig-zag. `stance` is that offset, and its floor is set by
  BALANCE rather than anatomy - at 0.02 the paw body's crouch put its centre 3.6 mm outside its feet and
  rig-anything refused the clip, which is how 0.05 (canine) and 0.04 (caprine) were arrived at.

**The silhouette check**: the built shares against the plan's, per segment, failing past 0.025 of the limb with
both numbers in the message, so "it still reads human" is caught before a build. `bodymap` measures the same
four shares off any rig and prints them in its summary. A `toe = 2.0` override is refused by it (digits 0.131
against 0.070), which is the control.

Each foot preset names the leg ratios its own silhouette needs (`feet.LEG_RATIOS`: paw -> canine, hoof ->
caprine), taken as the leg plan's default when a species names a foot and leaves the leg's ratios unsaid.

Built and hit: satyr 0.299/0.352/0.313/0.036 (caprine, exactly), paw body 0.317/0.343/0.270/0.070 (canine,
exactly); both pass all eight clips and export with verified durations, anatomy 0 fails.

**In Godot at 4 m beside the plantigrade body**: the satyr reads as a goat-legged figure - a short heavy
thigh, a thin shank, a bare cannon, the hock high on the trailing leg, a small hoof - and the paw body as a
dog-legged one, where both a round ago read as a person on tiptoe. The paw from the front is a thin cannon
flaring into a short, wide, splayed foot with distinct toe lobes.

Open: the lead leg at mid-stance is still nearly straight, which flattens the read at that one phase; the torso
and pelvis above the hips are still a person's (that is what a gnoll or a satyr is, but a quadruped's would
need its own baseline); `human` ratios on a digitigrade plan are refused rather than clamped.
