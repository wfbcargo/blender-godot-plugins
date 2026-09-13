# Judging renders

How to look at a capture and choose between variants without fooling yourself.
Built on BlenderAlchemy (ECCV 2024), BlenderGym (CVPR 2025), SEIG (2026), LL3M
(2025) and work on de-biased VLM judges. What those found:

- Vision models rank reliably and score unreliably. Absolute ratings bunch in
  the middle.
- Position bias: about a quarter of pairwise verdicts flip when the two images
  swap sides.
- Showing many images at once makes judges answer by position.
- Without a reference, judges reward "clean-looking" over correct.
- Loops that don't keep the best-so-far drift away from the goal.
- Common failures: missing subtle differences, and making edits unrelated to
  the problem that was named.
- Lighting edits are easier to judge than material edits; brightness and colour
  shifts are visible.

## The loop

```
capture (with --probes)
  → read the numbers, then the sheet
  → name ONE problem in the image's own terms
  → propose 2-4 candidate fixes as --set overrides
  → capture each (same shots)
  → compare each against the current best, both orders
  → keep the winner only if it wins both orders AND its numbers didn't regress
  → verify the named problem is actually gone in the winner
```

Structure, from the research: small parameter tweaks alternating with bigger
structural changes (swap GI method, add a fill light); ~4 rounds of 4-8
candidates is plenty. The current best is always in the comparison, so a bad
round changes nothing.

## Pairwise protocol

`lookdev.mjs compare --a best --b candidate` writes `_ab.png` (A left) and
`_ba.png` (B left). For each:

1. Read the image. Decide left or right, with the reason in one sentence.
2. Read the other order and decide again, independently.
3. Agree → verdict. Disagree → no verdict: treat them as equal and keep the
   current best.

Ask a narrow question: "which reads more like a photograph of a real place?" or
"in which do the objects sit on the ground?". A broad "which is better" asks for
a taste judgement.

## What to look at, per view

**`lit`**
- Is there a clear light direction? Can you point at the sun?
- Do shadows have colour, cooler than lit areas in daylight? Pure grey shadows
  mean fill without colour; black ones mean no fill.
- Do objects touch the ground? Look for a thin dark contact line and soft AO
  under them. Floating = bias too high or no AO.
- Distance: do far things lose contrast toward the sky colour?
- Highlights: bright spots roll off (AgX), not flat white plateaus.
- Specular: do surfaces at grazing angles brighten (Fresnel)? A shiny floor
  should reflect the sky or room, not glow uniformly.
- Uniformity: large surfaces with no variation read as plastic.

**`unshaded`** (albedo)
- No baked lighting: no shadows, AO or highlights painted in.
- Plausible paint: nothing near pure white or pure black, except metals (black
  here) and emissives.
- Relative values right: snow brighter than concrete brighter than asphalt.

**`lighting`** (light only, white albedo)
- A readable key, with its shadow shapes.
- Fill that varies with direction (sky above, bounce below), not flat.
- Light leaks: bright bands where walls meet floors indoors.

**Grey and chrome probes**
- Grey ball: distinct lit side, terminator and shadow side. A ball lit almost
  evenly all round = flat ambient.
- Chrome ball: reflects the environment you expect. A bright sky reflected
  indoors = missing ReflectionProbe.

**`<shot>_probe_keyfill.png`**: the side-on probe view the key/fill number came
from. If the number looks odd, check this image first.

## "CG tells" checklist

Name these when you see them; each maps to a fix.

| Tell | Usually |
|---|---|
| Flat, even lighting; no clear sun direction | ambient drowning key → lower sky energy |
| Pitch-black shadows | no sky ambient / GI → ambient source Sky, SDFGI |
| Grey, colourless shadows under a blue sky | constant-colour ambient → sky ambient |
| Objects floating | shadow bias too high; SSAO off |
| Blown-out bright areas with hard edges | Linear/Reinhard tonemap, exposure high |
| Everything mid-grey, low contrast | exposure/fill too high, fog too dense, albedo too bright |
| Bloom on everything | `glow_hdr_threshold` < 1 |
| Surfaces look like plastic | uniform roughness; no normal/detail maps; albedo too saturated |
| Glowing interiors | no ReflectionProbe (`interior`), sky leaking via SDFGI |
| Distant objects as crisp as near ones | no fog / aerial perspective |
| Light pools with a hard circular edge | short `omni_range`, linear attenuation |
| Everything the same white light | no warm/cool contrast between key and fill |
| Wrong scale feel | objects not 1 unit = 1 m |

## When the numbers and your eyes disagree

- Numbers in range but it looks wrong: say exactly what looks wrong. The
  numbers cover exposure and ratios; they are blind to composition, colour
  harmony, scale, and whether a material reads as what it's meant to be.
- Looks right but numbers out of range: check the probe placement and
  `--kind` first. Then, if the look is deliberate, say which threshold you're
  overriding and why.
