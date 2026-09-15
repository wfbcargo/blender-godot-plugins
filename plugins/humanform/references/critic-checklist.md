# Critic checklist

The critic is a subagent that did **not** write the body. It judges from `body.png`,
`closeups.png` and `humancheck.json`, never from the builder's description of what it
meant to make. Vision judges from agents agree with humans far less often than humans agree with
each other (BlenderGym: 0.66 vs 0.79), so the protocol is built to lean on numbers, fixed views,
explicit questions and pairwise comparison.

## Protocol

1. **Questions before looking.** From the brief and the layer being judged, write 8-15 yes/no
   questions, each naming the tile that answers it. **Phrase every question so `yes` is good.**
   Every `fail` in `humancheck.json` becomes a question of its own, and so does anything the brief
   asks for that a number measures ("average build" -> "Is the waist-to-hip ratio within the
   preset's range?"). Draw on the bank below and add questions the
   brief implies ("broad-shouldered" -> "Is the shoulder width clearly wider than the hips in the
   front silhouette?").
2. **Answer from the evidence.** For each: `yes` / `no` / `unclear`, the tile, and one sentence
   of evidence. A number in `humancheck.json` outranks an impression from a picture; say so when
   they disagree.
3. **Classify every `no`.**
   - `structural` - proportion, silhouette, primary masses, missing parts (L1-L3). Blocks progress.
   - `secondary` - muscle and bony landmarks, part shape (L4).
   - `detail` - surface, symmetry noise, shading (L5-L6).
   - `brief` - the body is well made but is not what was asked for (build, age, style).
   Name the region (`torso`, `pelvis`, `thigh.L`, `hand.R`, `face`, ...) so a fix can be masked to it.
4. **Pairwise, when there is a previous version.** Compare A (previous) and B (current) per
   question: `A`, `B` or `same`. Then an overall preference. Never score in absolute terms. Check
   both `views.json` files first: sheets with `standard_frame: true` share one scale (2.0 m by
   1.4 m a tile) and compare tile for tile; if either is not standard, compare numbers, not
   pixel heights.
5. **Return JSON** (below) and nothing that reads as encouragement.

```json
{
  "layer": "L3",
  "questions": [
    {"q": "Does the wrist reach the crotch line with the arms hanging?", "tile": "body.png clay front",
     "answer": "no", "evidence": "wrist tick sits 6 cm above the crotch target", "severity": "structural",
     "region": "arm", "compare": "B"}
  ],
  "structural_issues": ["..."],
  "preferred": "B",
  "confidence": "medium"
}
```

## Reading the sheet

`body.png`: rows are clay, normals, silhouette; columns are front, front_left, left, back (the
side of the body the camera sees; the body's left is +X). Every tile is orthographic at the same
scale. Orange dashes are the preset's target heights - from the top: chin, shoulder joint, hip
joint, crotch, knee. Cyan ticks at each tile's left edge are the same landmarks as measured, in
the same order. `closeups.png`: face front, face left, left hand from its back, left foot from above and in front
(hand and foot clipped to themselves, so the thigh and shin cannot hide them).

## Question bank

### L1 proportions (silhouette row, front and left)
- Is the head roughly one of 7.5 (realistic) / 8 (stylized) equal parts of the height?
- Does the crotch sit near half height (stylized) or just below it (realistic)?
- Are the cyan ticks within a tick's width of the orange dashes?
- With the arms down 45 deg, would the fingertips reach mid-thigh if hanging straight?
- Is the neck as wide as roughly half the head's width, not a stalk?
- Female: are the hips at least as wide as the shoulders? Male: shoulders clearly wider?

### L2 scaffold and pose
- Are the legs visibly separate below the crotch in the front silhouette?
- Are the arms about 45 deg down, clear of the torso?
- Do both feet stand flat on the same floor line?

### L3 primary forms (clay row)
- In the left view, do the ribcage and pelvis read as two masses tilted against each other (chest
  forward-up, pelvis tipped), not one tube?
- Is there a visible waist between them from the front?
- Do the buttocks sit below the hip joints and above the crotch line in the left view?
- Do the thighs taper to the knee and the calves bulge high on the back of the shin?
- Is the surface free of stuck-on shapes - balls, ridges where two shapes meet, pointed domes?

### L4 secondary forms and parts (clay row, close-ups)
- Does the upper arm have a deltoid cap at the shoulder, not a cylinder joining a box?
- Are the clavicles, sternum notch, kneecaps and ankle bones readable?
- Normals row: is the surface free of lumps, dents and ridges that are not anatomy?
- Face: nose, lips, eye sockets and brow readable; eyes on a line at about half the head height;
  ears between brow and nose base?
- Hand: four fingers and a thumb, separate, with knuckles; hand about the face's length?
- Foot: heel, arch and toes; inner ankle bone higher than the outer?

### L5-L6 surface and look
- Normals row: is the shading smooth across the body, with no faceting or seams?
- After the asymmetry pass, is the face and body free of mirror-perfect symmetry?

## Keep or revert

**Locked numbers** are the L1 findings (joint heights, crotch, chin, segment lengths, widths) in
the `humancheck.json` saved when L1 was frozen. A later version holds them if each is within its
preset tolerance of the frozen value. A baseline review of an existing body has no locked numbers.

Keep the new version only if the locked numbers held **and** the critic prefers it or calls it
`same` with fewer structural issues. Otherwise revert to the saved `.blend` and try a different fix.

## Known blind spots of the sheet

- In the `left` column a 45 deg arm covers the side of the chest and bust; judge those from
  `front_left`.
- A body's own rest pose shows: an MPFB arm angled forward changes the `front_left` silhouette.
  Compare poses only when both bodies share a rest pose.

## Batch design critique (parts)

Used when many designs of one region are rendered on the same body as one grid
(`views.variant_grid`): one critic call judges all of them, which costs one image and one answer
instead of one per design. Panels run left to right, top to bottom, numbered from 0; panel 0 is the
undesigned base, for reference. Each panel shows the region from fixed views, in clay:

| region | views in each panel (left to right) |
|---|---|
| face | front, left |
| hands | the left hand from its back; from the front (thumb in profile). Clipped to the hand |
| feet | the left foot from above and in front; its outer side; the front. Clipped to the foot |

1. **Before looking**, write the questions every panel must answer yes to, for the region. For a face:
   - Does it read as a plausible adult of the brief's sex, not a caricature?
   - Is it free of artefacts - lips crossing or pinched, a nostril collapsed, a dent or ridge, a jaw
     or cheek that bulges unevenly, ears that look stuck on?
   - Is it recognisably a different person from panel 0 (else it adds nothing to a library)?

   For hands: plausible adult hand of the brief's sex and build; fingers separate, tapering, none
   swollen, webbed past the first knuckle or thinner than the nail; knuckles and nails in place; thumb
   attached at the palm's side, not the wrist; palm and fingers in proportion (fingers about as long
   as the palm); visibly different from panel 0 - broader or narrower palm, longer or shorter,
   thicker or slimmer fingers, wider spread, a heavier or lighter wrist.

   For feet: plausible adult foot; toes in order, separate, the big toe largest; sole flat, heel
   rounded, an arch or instep line on the outer view; ankle bones readable and the ankle joining the
   shin without a step or pinch; different from panel 0 - broader or narrower, a higher or flatter
   instep, a heavier or slimmer ankle.

   Hands and feet vary less than faces: MPFB has few free targets there. Call a design distinct only
   when the difference is visible without comparing pixel by pixel; say `slight` otherwise.
2. **Judge every panel** against them, from what is visible, in one line of evidence each.
3. **Tag every kept panel** with 2-4 plain descriptive tags a person would search by - features,
   not verdicts: `broad nose`, `strong jaw`, `full lips`, `narrow face`, `hooded eyes`. For hands and
   feet, tags on sizes a design measurably moved (palm breadth, finger thickness and spread, wrist,
   foot breadth, instep height, ankle) are replaced by measured words when the part is stored
   (`parts.size_tags`): in the first batch critics tagged three of eleven kept feet broad or narrow
   against their measured breadth. Tag what you see anyway; the other axes (toes, heel, thumb) are yours.
4. **Return JSON** only:

```json
{"region": "face", "panels": [
  {"panel": 3, "keep": true, "plausible": "yes", "artefacts": "none", "distinct": "yes",
   "evidence": "higher nose bridge and fuller lower lip than 0; clean profile", "tags": ["high nose bridge", "full lower lip"]},
  {"panel": 5, "keep": false, "plausible": "yes", "artefacts": "upper lip pinched at the corners", "distinct": "yes",
   "evidence": "...", "tags": []}
], "best": [3, 7]}
```
