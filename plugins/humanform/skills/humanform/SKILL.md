---
name: humanform
description: Build adult human bodies in Blender that look right and work downstream in Godot 4.7 - layer by layer from a character brief through proportions and landmarks, a clean MPFB2 base mesh (quads, UVs, rig), primary and secondary anatomical forms, face, hands and feet, surface detail and skin, to a rig handed to rig-anything, follow-through, wardrobe and lookdev - with a measured gate and a critic between every layer so a detail pass never hides a structural mistake. Use when asked to make, model, sculpt, generate or improve a human, person, man, woman, character body, base mesh or figure in Blender; to choose realistic or stylized proportions; to use MPFB or MakeHuman from a script; or to plan how a character should be built before modelling starts.
---

# humanform

> **Building a whole character?** Write a spec and let `character-pipeline` run this plugin in the right order with the others - see that plugin's SKILL.md.

People are built in layers, coarse to fine, and a layer is only built on top of one that has
been **measured**. The research behind this plugin, and the full plan, are in
`grungist-creek/docs/humanform-plan.md`.

## Status

| layer | what | state |
|---|---|---|
| gate | `humancheck`: measure, contact sheet, critic | **built** (0.1.0) - use it on every body now |
| L0 | character sheet (brief -> data) | **built** (0.2.0) - `sheet` |
| L1 | proportions and landmarks from ANSUR II, `realistic` / `stylized`; a rig on them | **built** (0.2.0) - `landmarks`, `skeleton` |
| L2 | MPFB2 base driven to the landmarks, rig renamed | **built** (0.3.0) - `scaffold` |
| L4 | face stage (ANSUR head measures), face design parts, eyes; library and pipeline | **built** (0.4.0) - `scaffold.fit_face`, `parts`, `eyes`, `library`, `pipeline` - see the `humanlib` skill |
| L4 | hands-and-feet stage (ANSUR hand and foot sizes), hand and foot design parts | **built** (0.5.0) - `scaffold.fit_extremities`, `parts.design` / `screen` - see `humanlib` |
| L6 | hair from a preset: feathered scalp cap, bun / tie / fall volumes, strand objects for follow-through | **built** - `hair`, see *Hair* |
| L3-L4 | muscle definition: sculpted delta parts weighted by muscle and body fat, as geometry or a baked normal map | **built** - `muscle`, `delta`, `sdf` - see "Muscle definition" below and `humanlib` |
| L3-L4 | stylized exaggeration (SDF forms) | next |
| L5-L6 | reproject onto base topology, micro-detail, bake, skin | Phase 5 |
| L7 | rig from landmarks, flesh regions, export | Phase 6 |

Until a layer is built, build it by hand the old way, but **gate it with humancheck**.

## The ladder

| layer | gate before moving up |
|---|---|
| L0 character sheet | values in range; unspecified fields marked guessed |
| L1 proportions (frozen) | every proportion finding passes for the preset and sex |
| L2 scaffold (frozen) | one component, scale applied, legs parted, arms 35-55 deg down, feet on Z = 0 |
| L3 primary forms | numbers pass; critic reports no structural issues |
| L4 parts (frozen) | fingers, face relief; nothing outside a part's mask moved more than 1 mm |
| L5 surface | quads >= 90%, UVs, reprojection p99 < 2 mm |
| L6 look | lookdev `material_lint` clean |
| L7 handoff | joints centred in the limbs; export read back |

A frozen layer may be added to, never moved: re-run humancheck after every change and compare
the L1 numbers with the frozen ones. Round budgets: L1 3, L3 5, L4 4 per part, L5 2, L6 3. When a
budget runs out, stop and show the user the sheet and the findings still failing.

## L0-L1: brief -> sheet -> landmarks -> rig

```python
from humanform import sheet, landmarks, skeleton, measure   # after the reload bootstrap in humancheck

s = sheet.new(name="Mara", sex="female", age=34, stature=1.72, build="athletic", style="realistic")
r = sheet.resolve(s)          # r["values"]: all 65 ANSUR II variables in metres; r["guessed"], r["notes"]
lm = landmarks.from_measurements(r["values"], s["sex"], s["style"], name=s["name"])
findings = measure.check(landmarks.as_measurements(lm), s["style"], s["sex"], s["build"])   # all pass
rig = skeleton.build(lm, s["name"])    # "Mara_rig": rig-anything bone names, landmarks stored on it
sheet.save(r["sheet"], r"C:/proj/assets/people/mara.sheet.json")
```

**Turning a brief into a sheet.** Write down only what the brief says; leave the rest `None` so
`resolve` fills it from the population and lists it in `guessed` - tell the user what was guessed.

| field | values |
|---|---|
| `sex` | `female`, `male` - required; the measurement data is per sex |
| `age` | years, 1-90; ANSUR II covers 17-58 - see *Ages ANSUR did not measure* |
| `stature` | metres, 1.3-2.2 for an adult, 0.6-2.0 for a child; `None` for the population mean |
| `weight` or `bmi` | overrides the build's BMI |
| `build` | `slim` (BMI 20.5), `average` (population), `athletic` (24, narrow waist, broad shoulders), `muscular` (27.5), `curvy` (25.5, wide hips and seat), `soft` (27), `heavy` (31) - or a dict `{"bmi": .., "z": {variable: sd}}` |
| `style` | `realistic`, `stylized` |
| `measurements` | any ANSUR II variable fixed, in metres (`{"hipbreadth": 0.40}`) |
| `seed`, `variation` | `None` for the conditional mean; a seed draws a person, `variation` 0.5 by default (1.0 is full population spread) |
| `firmness`, `proportions` | MPFB macros 0..1 (soft .. firm; regular .. idealised) - nothing ANSUR measures; `None` is MPFB's 0.5. Set at creation, so the fit measures the body with them |
| `cupsize` | MPFB macro 0..1, a woman's bust (small .. full); `None` is MPFB's 0.5. Never fitted, like firmness: ANSUR's chest girth is fitted around it |
| `muscle` | MPFB macro 0..1; `None` takes the build's. Given outright, the fit holds it (Dante's 1.0 ends at 0.95, not the muscular prior's 0.72) |
| `skin`, `iris` | screen (sRGB) colours `(r, g, b)`, 0..1 - see *Colour* |

**Ages ANSUR did not measure.** `sheet.resolve` returns `ansur`: `"measured"` for 17-58, `"aged"`
above, `"child"` below, and for the last two a note containing `sheet.NOT_MEASURED` ("not measured
against ANSUR"). `pipeline.make` makes both:

| `ansur` | how | stature |
|---|---|---|
| `aged` | resolved and fitted at 58 (`values["Age"]`, the sheet keeps the real age), then MPFB's age macro set to the real age | ageing shortens the body (Walter 1.700 -> 1.688 m), so the height macro is bisected back to the brief (`scaffold.fit_stature`, 1.6995 m) |
| `child` | no ANSUR at all: MPFB's body at that age; weight from BMI read against the median BMI for the age (`scaffold.child_weight_macro`), muscle from the brief or build | MPFB's children are short (its 8-year-old is 1.15 m): height macro bisected to the stature (Milo 1.270 m) |

Neither is ever stored in the library, and a child gets no humancheck (its presets are adult). An aged
body's humancheck still runs, but what it measures is MPFB's ageing, not data - say so when showing it.

**Colour.** Briefs and every humanform API take screen (sRGB) colours - what a picker, a photo or a
person means by a colour - and `look.srgb_to_linear` converts them with the exact piecewise curve for
Blender's linear Base Color (and glTF's). `c ** 2.2` is 2% off at mid-grey but a third of the true
value at 0.05, where dark irises and deep skin tones sit. `look.skin(human, srgb)` gives a body one flat
Principled material (`<name>_skin`, roughness 0.55); `pipeline.make` applies the brief's `skin` and
`iris`. Flat colour only - lookdev owns real skin.

**How it resolves.** ANSUR II per sex is a multivariate normal over 65 variables. What the sheet
fixes is conditioned on, and a build's leanings are applied in conditional standard deviations,
so a tall woman gets the crotch height, arm length and hip breadth tall women have (Mara at
1.72 m: crotch 0.488 H against the 0.480 mean) rather than an average body scaled up.

**Stylized** shifts each joint height by the canon's distance from the population mean and warps
everything between, and scales arm, hand, foot and widths by canon over mean - the person keeps
their own deviations, so two stylized people still differ.

**The rig** is Nora's proven layout (spine .. spine.005, shoulder / upper_arm / forearm / hand,
thigh / shin / foot / toe) placed exactly on the landmarks; rig-anything's bodymap reads it as a
spine, two arms and two legs. No fingers yet - they come with the MPFB rig in Phase 3.

**Verify:** `blender -b --factory-startup --python ${CLAUDE_PLUGIN_ROOT}/scripts/tests/phase2_briefs.py`
(five briefs, preset self-consistency, five broken-landmark controls that must fail, 200 seeded
draws that must not). `scripts/tests/lineup.py -- out=<png>` renders the briefs as mannequins.

## L2: the base body

```python
from humanform import scaffold
human, rep = scaffold.build(r["sheet"], lm)     # create from macros, fit, stand on the floor, rig, rename
print(scaffold.summarize(rep))                  # every fitted measurement: value, target, error in cm and tolerances
rep_hc = measure.run(human.name, preset=s["style"], sex=s["sex"], build=s["build"], out_dir=...)
```

`fit` is Levenberg-Marquardt over MPFB's `height`, `weight` and `muscle` macros and 20 of its own
targets (`measure-upperarm-length`, `hand-scale`, `foot-scale-vert`, `measure-napetowaist-dist`,
`hip-scale-vert`, `measure-waist-circ`, `stomach-pregnant`, `measure-thigh-circ`, ...), with 23 residuals measured the way
humancheck measures (joints from MPFB's `joint-*` groups, which is where its rig puts them) in
units of each measurement's tolerance. Targets load as shape keys prefixed `hf:`. The rig is
MPFB's `game_engine` with its weights, bones and groups renamed: `pelvis` -> `spine` ..
`head` -> `spine.005`, `clavicle_l` -> `shoulder.L`, `calf_l` -> `shin.L`, `ball_l` -> `toe.L`,
`index_01_l` -> `f_index.01.L`, `thumb_01_l` -> `thumb.01.L`, `Root` -> `root`.

**Start with `pipeline.make`** (the `humanlib` skill): it checks the library first and is the fast path. Build by hand only to debug a stage.

**Verify:** `blender -b --factory-startup --python ${CLAUDE_PLUGIN_ROOT}/scripts/tests/phase3_scaffold.py -- out=<dir> views=1 [only=Mara] [save=<file.blend>]`.
Measured (0.3.0): Mara 0.31, Otto 0.36, Juno 0.27, Kade 0.83, Wren 0.23 rms tolerances, 13-30 s
each; humancheck 0 fail on all five, one warn (Mara 8.05 heads); wardrobe's rigmap and
rig-anything's bodymap read every rig. Always look at the contact sheet as well - see the rules.

### Rules the fit taught

**Girth has a shape.** Fitted to circumferences alone, every body - an athletic woman, a muscular
man - answered the waist with MPFB's belly target pushed to its limit and came out looking
pregnant, while every number passed. The fit now also matches ANSUR's waist breadth and depth,
buttock depth and chest girth, and penalises local girth targets (waist 3, belly 6) far more than
the weight macro (0.3). Numbers alone did not catch this; the contact sheet did.

**A build word constrains the solve, not just the start.** A muscular man's muscle macro fell from
0.9 to 0.34 because fat hit the girth as well - he read as average. `muscular` and `athletic`
now hold muscle with a strong prior; `heavy` and `soft` make the belly cheap, because that is where
their weight really sits.

**Limbs need girths too.** With only torso girths constrained, a slim 58-year-old's fit pushed
the muscle macro to 0.86 to shape her torso and gave her bulky arms and legs. Thigh, calf,
upper-arm and neck girths are residuals now, each with its own MPFB target.

**Measure where the data was measured.** The first neck section, halfway between shoulder joint
and chin, cut the trapezius and read up to 37 cm too thick; the solver crushed the neck and head to
answer it. It is now taken 2.5% of H below the chin, rejecting anything wider than a neck.

**Measure where the data was measured (hips).** Hip breadth taken at the widest section above the crotch
read 3-5 cm wide on every MPFB body (its legs stand apart and the thighs splay there); taken at
ANSUR's buttock height, as ANSUR takes it, it matches.

### Limits

- MPFB's weight macro tops out: a 1.88 m muscular man stays ~6 cm under ANSUR's chest girth.
- MPFB has no finger-length target per finger, no lateral hip-joint spacing, and one head height;
  faces and hands are MPFB's (Phase 4 refines them).
- follow-through's flesh side-bone filter has not been tested with `f_index.01.L` finger names.

## Hair

```python
from humanform import hair          # lookdev's `blender` folder on sys.path too, for the material
rep = hair.add("Belle_body", preset="bun", colour=(0.17, 0.10, 0.06))   # a screen (sRGB) colour
rep["objects"]     # {"hair": "Belle_hair"} - plus "strand": "Belle_hair_strand" for ponytail and long_loose
hair.add(body, sheet=s)             # the brief's hair = {"preset": ..., "colour": ...}
hair.contract("Belle_hair_strand")  # the strand contract below, read back: {passed, problems, points, length_m}
```

On a **baked** body (no Mask modifier), and on a **bare** one: the cap is cut from the body's own faces and
the landmarks are measured off its surface, so hair already joined into the body is read as scalp - the crown
comes out high, the head unit `h` grows and the whole hairline shifts. `views.hair_objects(body)` says whether
there is hair there already; `character-pipeline`'s hair stage checks it and refuses, since to change a preset
the character is rebuilt from its body stage. That stage calls `hair.add` from a spec's `[hair] preset = ...`
and joins the result into the body; the brief field is `sheet.new(hair={"preset", "colour"})`, validated
against `sheet.HAIR_PRESETS`, and `pipeline.make` does not build it.

| preset | parts |
|---|---|
| `short_crop` | the feathered cap alone, 3.5 mm, a little fuller at the crown |
| `bob` | cap and a fall from the crown over the ears and nape to below the jaw: it lies on the cap at the crown with no edge, hangs from the widest part of the head in locks, and turns under at uneven ends |
| `bun` | a snug cap whose strands run to a coiled bun (a tube wound 1.6 turns) high at the back |
| `ponytail` | cap, a hair-wrapped tie at the back, and a tapered tube tail - the **strand** |
| `long_loose` | cap, a fall to the neck, and a curtain 16 cm wide down the back from inside the fall - the **strand** |

Numbers live in `data/hair_presets.json`: the hairline curve (height in head units against azimuth, warped so
the measured ear sits at 90 degrees), feather widths, thicknesses and each part's placement.

**The hairline's path.** Rounded across the forehead (0.55 h above the eye centre), down at the temples
(0.33 h at 47 degrees), then a sideburn in front of the ear down to 0.36 h *below* the eye, round the ear
(an ellipse the measured ear's half extent scaled by `ear_scale` [0.55, 0.95] plus 2 mm), and down to the
nape at -0.78 h. The distance across it is measured perpendicular to the curve, not straight up, so the
feather keeps its width down the near-vertical front edge of a sideburn. A curve that stops above the ear
(a diagonal from the forehead to behind the ear, bare temples) outlines a skullcap however soft its edge.

**Placed from the head, measured on the mesh:** the head bone (`eyes.head_bone`, the rig profile's `head`),
its vertices, the crown top, the eyeballs, the head's front-back centre above the brows, and each ear (what
stands out sideways past the skull). Heights are in head units h = crown - eye centre (Belle: 0.100 m).

**The hairline is not an edge.** The cap is the body's own faces inside the curve (and outside an ellipse
round each ear), smooth-subdivided (a new vertex that falls inside the skin goes back onto it), offset by a
thickness that rises from 0.6 mm at the boundary to full over `feather_in_m` (40 mm), and its full-thickness
part relaxed four times and kept half its thickness off the skin: an offset surface turns the skin's concave
crease at the base of the skull into a ridge that a rim light draws as a line across the nape, and the body's
coarse quads into a faceted outline. Its UV V is ~0.003 at the boundary and 0.045 on the
curve, so the boundary sits in the lookdev hair texture's transparent root zone and what shows is strand tips
of uneven length with skin between them. The report says so in numbers: `cap.boundary_offset_mm_max` (0.6)
and `cap.boundary_v_max` (0.003). U runs round an axis toward the bun, the tie or the crown, a whole number of
texture tiles per turn, so there is no seam.

**V never goes flat and runs toward the pole.** Near the line V is the distance across the curve; from about
3 cm in it becomes the distance along the axis's meridian from where that meridian crosses the hairline
(found by casting rays at the skin along it), easing on to `cap_v_max`. V used to be the height over the
curve clamped at 0.6: over the top of the head the clamp left runs of faces with no V change (no tangent
at all) and the height's gradient lay along U, so the UV frame flipped in patches - Godot drew both as bright
glint streaks on the crown. `cap.uv_handedness` counts the faces more than 3 cm inside the line by their UV
frame (Belle's bun: 602 same, 6 flipped, 0 flat; before, 144 flat faces on the hair, 68 of them on the
crown). Round an ear and at the feather the frame still turns, since V runs away from the line on both sides
of a hole; Godot's `LookdevMaterials.apply` gives hair tangents from U alone for that - per face, then
averaged mod 180 degrees over the faces meeting at each position, which is what keeps the strands running to
the bun's axis from faceting into dark polygons.

**Material:** `lookdev_blender.hair.material` (see lookdev's `references/hair.md`): strand texture with a
root-to-tip gradient and alpha-thinned ends (MASK), a strand normal map, anisotropy, and `lookdev` extras
that `LookdevMaterials.apply` turns into anisotropy, backlight and rim in Godot. Without lookdev importable
the hair gets a flat material and the report says `"source": "flat ..."`.

### The strand contract (for follow-through)

Ponytail and long_loose put their moving part on its own mesh object, `<base>_hair_strand`:

| on the object | what |
|---|---|
| `ft_type` | `"strand"` |
| `ft_root_bone` | the rig's head bone name - the bone role `head`, resolved (`spine.005` on humanform rigs) |
| `ft_centreline` | flat `[x, y, z, x, y, z, ...]`, 12 points, object-local, **root first**, evenly spaced by arc length |
| `ft_length_m` | the centreline's length |
| `ft_radius_m` | per centreline point: the tube's half width, the curtain's half thickness |
| vertex group `ft_strand` | each vertex's share of the length, 0 at the root to 1 at the tip - the order survives a join |
| `humanform_hair` | `{"preset", "part": "strand", "kind": "tube" or "curtain"}` |

Object custom properties export as glTF node extras when the object is exported on its own. Until
follow-through builds a chain from it the strand is skinned as a rigid fallback: head bone at the root,
blending to its parent (neck) and grandparent (chest) toward the tip. `hair.contract(obj)` checks all of it,
including that the `ft_strand` weights run from the first centreline point to the last. The pipeline joins the
strand into the body (rig-anything exports one mesh), after checking the contract; the `ft_strand` group and
weights survive the join, the object properties do not.

The bun's coil starts almost on its axis, a quarter of its tube's width, and sinks below the first turn, so
the middle of the coil shows no tube end (an open end there read as a dark hole with a glint in it).

**Measured on Belle (bun):** cap from 1054 body faces (the sideburns, the ring round each ear and the lower
nape added 640), 4383 vertices after subdivision, 0.6 mm at its boundary rising to 14 mm at the crown,
0.27 mm closest to the skin; coil bun 15.5 cm of tube, 730 faces; 5105 hair vertices; 0.9 s. On the
`hair_presets` fixture woman the ponytail keeps 8.5 mm and the long_loose curtain 1.9 mm off the skin below
15% of their length.

**Limits.** Bob and long_loose are still shells: at 1 m they read as a smooth, heavy hairstyle more than as
loose hair (locks are a 4-5 mm wave, the ends ragged by up to 1-2 cm), and a faint line can show close up
where a fall comes out past the cap below the widest part of the head. Hair does not collide with garments
or the shoulders once animated - the strand is the part meant to move. In Godot the hair wants
`LookdevMaterials.apply` (soft hairline, per-face tangents); without it the edge is alpha scissor and there
is no anisotropy (see lookdev's `references/hair.md`).

## Muscle definition

MPFB's mesh is smooth: its muscle macro makes a body bigger, not defined, so Dante read average until the
macro was forced to 1.0. Definition is a humanlib **delta part** (per-vertex heights along the normal, in
groups) put on after the fit:

```python
from humanform import pipeline, muscle, delta
res = pipeline.make(brief, ...)                          # muscle left to the build and the fit
rep = muscle.define(human, brief)                        # shape key hfd:muscle at 1: geometry
rep = muscle.define(human, brief, geometry=False)        # hfd:muscle at 0: bake it instead (below)
rep["weights"], rep["body_fat_pct"], rep["applied"]["groups"]    # per group: weight, vertices, max mm
rep["fitted_muscle"], rep["applied_bulk"]                # the macro the fit left, and hfd:muscle-bulk (always 1)
```

- **The set** (`muscle.seed`, stored as `muscle/definition-v2` on first use): authored on MPFB's default male.
  Eight groups are SDF sculpts - deltoids, upper arms, pectorals, abdominals, obliques (with the serratus and
  the inguinal line), quadriceps, calves, forearms: ellipsoid bellies anchored by rays from the joints,
  trimmed to a plateau, smoothly unioned, minus grooves - polylines on the skin, sunk with a smooth section
  and tapered at both ends: the sternum, the linea alba (ending above the navel), the tendinous intersections,
  rectus femoris from vastus lateralis, the sartorius line to the knee, above the patella, between the calf
  heads and where they meet the Achilles, biceps from triceps, the deltoid's borders, the forearm's. Pads are
  mirrored with |x| rounded within 15 mm of the midline, so the sides meet in a valley, not a crease. Limb
  groups are x1.2-1.5 taller than the trunk's (`GROUP_GAIN`): at the trunk's heights they did not read at
  full-body scale.
- **A form must be wider than an edge.** hm08 has about 15 mm between vertices, so anything narrower comes out
  as one vertex standing off its neighbours - a bright facet stuck through the skin, which is how two wedges
  appeared on Dante's outer thigh. Three limits keep every form resolvable: a groove is sunk at most
  `GROOVE_SLOPE` (0.3) of its own radius; `despike` pulls back any vertex more than `SPIKE_LIMIT` (4 mm) off
  its neighbours' mean as each group is authored; and `muscle.facet_guard`, a `delta.apply` `refine`, does it
  again in `define` on the **sum** of the groups at the wearer's scale. `muscle.spikes(heights, faces)` is the
  measure throughout. Raising a gain past this point does not make a muscle read, it makes a facet - widen the
  pad instead.
- **Per group is not what the mesh carries.** Both keys land on one surface and the groups overlap, so they
  add: `relief` and the sculpted limb groups spike on the same vertices - v4579 on the front-outer thigh
  (relief 3.4 mm + quadriceps 3.0), v4735 on the back of the calf (2.9 + 3.8) - and Dante carried a 7.62 mm
  composite while no group was over 4. That is why the guard runs on the sum and why the fixture records the
  composite at a real body's weights (`geometry.spike`: unguarded 7617 um and 6 vertices over 1.5x the limit,
  applied 4521 um and none), not only `stored.spike_um` per group. `define` returns the same as
  `rep["spike_um"]`; `muscle.applied_spikes(body)` reads it back off any body's `hfd:` keys.
- **Derived groups.** `relief` is MPFB's own muscle sculpt high-passed (muscle 1.0 minus 0.5 along the normal,
  less its 6-iteration Laplacian smooth; head, hands, feet, nails, genitals masked, and the front midline of
  the trunk, where MPFB's own crease came out as a knife cut down the sternum into a navel notch): the back,
  arms and neck. `bulk` is the same shape low-passed, on the limbs and shoulders only (the trunk inside the
  shoulders and above the hips, whose girths the fit reached, is masked), weighted by the fit's shortfall:
  `(brief muscle - fitted macro) / 0.5`. The fit spends the muscle macro on girths - Dante's brief says 0.9,
  the fit lands on 0.66 - and without `bulk` his arms and shoulders came out thinner than the forced-macro
  body's. It is mass, not definition: fat does not scale it, and it stays in the geometry on the game path.
- **How much shows** (`muscle.weights`): muscle term `smoothstep(0.3, 1.0, muscle)` - the brief's muscle or
  its build's, never the fitted macro - times a per-group leanness from estimated body fat (Deurenberg on BMI
  less 10 BMI points per unit of muscle above 0.5, 6 points leaner per unit of firmness above 0.5): abdominals
  and obliques full at 12% and gone at 22%, pectorals and quadriceps 13-25, deltoids and upper arms 14-28,
  relief 13-27, calves and forearms 15-30; women +8 points and pectorals x0.35. Dante (BMI 27.5, firmness
  0.9, build muscle 0.9): 15.8%, weights 0.64-0.94, definition total 7.42, bulk 0.48. The same muscle value
  at BMI 30 and firmness 0.25: 22.7%, total 1.90 (0.26 of Dante's), abdominals 0. Freya: 24.9%, total 3.98.
- **Geometry or a map.** `delta.high_copy(human, "hfd:muscle")` before `bake_for_game` gives the high
  source (bulk included); lookdev's `detail.bake_normal_from_high(body, high, out_dir, material="<name>_skin")`
  bakes it onto the game mesh - by the matched method, no rays, since the high copy is the body's own
  topology - and wires the map into the skin material (glTF normalTexture). A re-bake re-points the same
  material. At strength 1 the map shows the pectorals, abdominals and deltoids up close but reads faint at
  full-body scale; strength 1.6 (the Normal Map node, `strength=`) reads at that distance. The card also
  applies to a baked mesh (`mode="mesh"`): hm08's body is its first 13380 vertices at every stage.
- **Proportions hold:** humancheck on Dante before and after is 32 pass, 0 warn, 0 fail (heights up to 23 mm,
  bulk 7 mm); Freya 32/0/0 both; the soft body 29/1/0 (2 info) before, 30/1/0 (1 info) after. Dante after
  against the forced-macro body (which humancheck gives 31/1/0): upper arm 44.7 vs 38.0 cm, calf 44.1 vs 40.2,
  thigh 64.3 vs 64.1, bideltoid 60.5 vs 57.3; chest 116.9 vs 114.7, waist 95.1 vs 94.0.
- **Resolution:** heights live on hm08's vertices (about 15 mm apart), so edges are soft; a normal map baked
  from the same mesh carries no finer detail than the geometry.

Verify: `python tools/regress.py --only muscle_definition` (repo), renders in its design doc (05 5.5).

## MPFB2 from a script

Installed as the extension `bl_ext.user_default.mpfb` (2.0.17, GPL-3.0 code, CC0 assets). Call
its services; never copy its code into this plugin.

```python
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.targetservice import TargetService

macro = TargetService.get_default_macro_info_dict()   # gender, age, muscle, weight, proportions,
macro["gender"] = 0.0                                 # height, cupsize, firmness: 0..1; race dict
                                                      # age: 0 is 1 year, 0.1875 11, 0.5 25, 1.0 90
human = HumanService.create_human(macro_detail_dict=macro)       # 0.08 s, 18.5k quads, UVMap
rig = HumanService.add_builtin_rig(human, "game_engine")          # 0.09 s, 53 bones, weights
```

- The body faces -Y with its left at +X and feet on Z = 0 - the same contract as rig-anything,
  follow-through and wardrobe. A default male is 1.729 m, a default female 1.591 m.
- Helper geometry (eyes, teeth, tongue, tights, skirt, hair proxies) is hidden by a `Hide helpers`
  Mask modifier on vertex group `body`. `joint-*` vertex groups mark every joint.
- Fine targets live in `mpfb/data/targets/<group>/` (`measure-upperarm-length-incr`,
  `hip-scale-horiz-decr`, `stomach-pregnant-incr`, ...) and load with
  `TargetService.load_target(human, path, weight=...)`.
- Rigs: `game_engine`, `game_engine_with_breast`, `default`, `default_no_toes`, `mixamo`,
  `cmu_mb`, `openpose`, and `rigify.human` / `rigify.human_toes` (need Rigify enabled).
- In `blender -b --factory-startup`, enable it with
  `addon_utils.enable("bl_ext.user_default.mpfb", default_set=True)` - with `default_set=False`
  MPFB fails to register because it reads its own preferences entry.

## Rules

**Fix the lowest failing layer first.** A body with fused thighs or low shoulders will pass its
problems to every garment, jiggle zone and animation built on it; face detail does not help.

**Numbers outrank pictures, pictures outrank intentions.** What the builder meant to make is not
evidence. Measure, render, then ask a critic that did not build it.

**Keep the rest pose games rig in:** arms about 45 deg down, legs apart below the crotch (wardrobe
measured shirts folding into spikes at a T-posed armpit).
