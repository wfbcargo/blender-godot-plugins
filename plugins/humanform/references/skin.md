# Creature skin: from a description to `species_skin`

humanform's skin (`scripts/humanform/skin.py`) is a human skin by default. Pass `species_skin` to
`look.skin` (on both calls: the MPFB human's mark and the game mesh's bake) and the same regions, mottle,
subsurface and checks are worked out from the tone you give instead of from a human's. Nothing in the code
knows a species. A green lizard-man, a grey stone giant and a spotted hyena-man use the same parameters.

```python
look.skin(human, tone, species_skin=sp)              # mark: region tints along the tone, pattern mask
look.skin(game_mesh, tone, size=1024, species_skin=sp)   # bake: albedo, ORM, normal; checks
```

`species_skin=None` is the human skin, and its output is byte for byte what it was. `{}` is a creature skin
with no pattern: the tone-relative rules alone.

## The parameters

| key | what it is | default |
|---|---|---|
| tone (the `srgb` argument) | the skin's **mean** colour, sRGB. The bake holds the albedo's mean to it, pattern included | required |
| `regions_off` | names from `skin.REGIONS` (`lips`, `nipple`, `genital`, `knee`, `elbow`, `knuckle`, `palm`, `sole`, `flush`, `nail`) to leave as plain skin. They are not checked either | `[]` |
| `pattern.kind` | `spots` (Voronoi blots with ragged edges, each a different size and darkness, about one cell in six empty), `stripes` (warped bands around the body, along Z), `blotches` (large irregular patches with fairly hard edges), `mottle` (soft, even variation) | none |
| `pattern.colour` | sRGB. It multiplies in as colour / tone, so the skin's own mottle stays inside the pattern | - |
| `pattern.scale` | metres: spot spacing, stripe period, or blotch or mottle size | 0.1 |
| `pattern.amount` | 0..1, how strongly the mask applies | 0.5 |
| `pattern.regions` | where the pattern shows: the union of `head`, `torso`, `arms`, `legs`, `back`, `front` (from the joints and the surface normal). Palms, soles, lips and nails are never patterned, and borders fade over a few cm | the whole body |
| `subsurface_tint` | sRGB the scatter follows, when the flesh under the skin is not the skin's colour | the tone |

A species file's whole `skin` block may be passed. Its `palette` is ignored here, because choosing the tone
from it is the caller's job. Unknown keys, region names or kinds raise a ValueError that lists what is allowed.

## The rules (what you do not have to set)

The tone in linear RGB is `t`. Its chroma is `c = t / geomean(t)`: (1, 1, 1) for a grey, and `log c` points
the way the tone's hue does.

- **Darker regions** (lips, areolae, genital skin, knees, elbows, knuckles, the facial flush) get
  `tint = d * c^s`, normalised so the tone's luminance scales by `d`. `d` is the human table's darkening, and
  `s > 0` pushes the chroma further the way it already points (`SPECIES_DEEP`). A green skin's lips are a deeper
  green, a tawny one's lips a deeper warm brown. They never move towards a human red.
- **Palms and soles** get `pale_tint`'s CIELAB lightness step. It is sized from the tone's own L*, so a dark tone
  gets more lift. They also lose a little saturation along the tone.
- **Nails** get lighter and greyer.
- **Mottle** is stronger than a human's, and its colour shift follows `log c` rather than adding red.
- **Subsurface**: Blender's radii are the human radii (3.67, 1.37, 0.68 mm) blended half and half, in log, with
  radii proportional to `c^1.25` of the scatter colour. The scatter still has some red, but the tone decides
  which way it leans. In Godot, skin-mode transmittance is a red profile whatever the colour. Where the radii's
  R/G is under 1.8 (a human's is 2.7), transmittance is turned off, so a green ear does not glow red with the sun
  behind it.

## The checks, and what they mean on a creature

The bake still reports `tone_ok` (the albedo's mean against the tone, 0.03 sRGB) and `contrast_ok` /
`contrast_fail`. On a creature skin, `contrast` adds `dh` (CIELAB hue from plain skin, in degrees) and `C`
(chroma). The floors change as follows:

- a **red** floor becomes **deep**: the same dE, darker by 1 L*, and the hue within 15 degrees of plain skin's;
- a **pale** floor keeps its lightness step (3 L*) and the same hue test. It drops "no redder than skin", which
  only makes sense for a human red;
- `regions_off` regions are skipped. Plain skin is measured where the pattern cannot reach, if at least 5% of
  plain skin is out of the pattern's `regions`.

A human skin on a green tone fails the creature check: its lips turn brown, 25 degrees off hue. That is the
mistake the check exists to catch.

## From a description to parameters

1. **Pick the mean tone, not the base.** Pick the colour the skin averages to at arm's length, pattern
   included. Dark spots over 20% of the body pull the base lighter than the mean. If the description names
   the base ("tawny with dark spots"), choose a tone slightly darker than the base.
2. **Name the hue family and how grey it is.** "Mossy grey-green" is a low-chroma green (G about 0.07 over R and
   B). "Olive" is a green-yellow with blue well down. "Yellow-green" (a sickly goblin) has high chroma with blue
   very low. "Tawny" and "sandy" are warm, with R above G above B. Greyer tones read as heavier and older;
   saturated ones read as younger and more toy-like, so stay under about 0.30 sRGB between the highest and
   lowest channel unless the brief wants a cartoon.
3. **Choose the pattern from the words.**

   | words | kind | scale | amount |
   |---|---|---|---|
   | "spotted", "leopard", "hyena", "freckled hide" | `spots` | spacing 0.05-0.10 m | 0.7-0.9 |
   | "striped", "banded", "tiger" | `stripes` | period 0.08-0.15 m | 0.6-0.8 |
   | "blotchy", "patchy", "like a toad", "lichen" | `blotches` | 0.12-0.25 m | 0.5-0.7 |
   | "mottled", "weathered", "uneven" | `mottle` | 0.06-0.12 m | 0.5-0.7 |

   Make the pattern colour the same hue as the tone at about 0.7x its value for a natural look, or a
   different hue for markings (a hyena's brown on sand). Put markings on the `back`, `arms` and `legs`, and
   leave the belly and face lighter (countershading), unless the description says otherwise.
4. **Turn off what the creature does not have.** No visible genitals or areolae on a stylised brute:
   `regions_off: ["genital", "nipple"]`. Add `flush` for a face that should not blush.
5. **Set `subsurface_tint` only when the flesh is not the skin's colour**, for example a pale grey hide over
   red flesh (`[0.7, 0.4, 0.35]`) or a translucent blue skin.
6. **Build, then look.** Render front, three-quarter, face and a hand with a back light. In Godot, orbit in
   close with lookdev's `close-shot`. Look for a flat tint (raise the pattern `amount` or use `mottle`), stickers
   (spots too round: use a smaller `scale` so there are more of them), and a glow at the ears and fingers that
   is the wrong colour.

## Worked examples

One MPFB body (male, 1.76 m), baked at 1024 px and rendered in Cycles under a neutral key, fill and back light.
Each passed `tone_ok` (error 0.0) and `contrast_ok` with no fails.

| description | tone | `species_skin` | Godot transmittance |
|---|---|---|---|
| grey-green, heavy, darker blotches (a troll) | (0.45, 0.52, 0.42) | `regions_off ["genital"]`, `blotches` (0.33, 0.38, 0.30), 0.18 m, 0.6 | off (R/G 1.34) |
| olive, weathered (an orc) | (0.42, 0.50, 0.30) | `mottle` (0.34, 0.40, 0.22), 0.10 m, 0.7 | off (1.30) |
| sickly yellow-green (a goblin) | (0.55, 0.60, 0.30) | `{}` | off (1.45) |
| tawny with dark spots on back and limbs (a gnoll) | (0.72, 0.56, 0.36) | `spots` (0.36, 0.25, 0.16), 0.06 m, 0.85, `["back", "arms", "legs"]` | on (2.31) |
| orange with dark stripes (a tiger-man) | (0.70, 0.50, 0.32) | `stripes` (0.25, 0.18, 0.12), 0.12 m, 0.8, `["back", "arms", "legs", "torso"]` | on (2.59) |

In each, lips, knuckles and knees read darker in the skin's own hue (dh 0-2 degrees on the greens, up to -10
on the tawny tone). The palms read paler, and the back-lit ears glow yellow-green on the green skins, where
the human skin on the same olive tone glows orange.
