# Fit critic checklist

Questions a round's done-when and its critic **pick** from when a character wears garments. Each is yes/no
with `yes` good, and names the number or picture that answers it. Numbers come first: a critic who sees skin
through a shirt in a tile and a verifier that reads 0% says both, and the number is re-run before the tile is
believed or dismissed. The protocol (questions before images, one line of evidence, `A`/`B`/`same` against
the previous version) is humanform's `references/critic-checklist.md` and animate-anything's
`references/motion-critic-checklist.md`; this file is only the bank. `unclear` when the source is missing.

## Sources

| name | what | how |
|---|---|---|
| **verify_wardrobe** | the body dressed in Godot, walked, every sampled frame skinned: `holes_frac`, `poke_frac`, `thighs_frac` (limits 0.5% each, worst frame), `samples`, `hidden_verts`, `holes_by_bone`, `poke_by_bone`, `thighs_by_bone`, `hem_stats`, `equip`, `passed`, `problems`; one `WD_RESULT {json}` line | `godot --headless --fixed-fps 60 --path <project> -s res://addons/wardrobe/verify_wardrobe.gd -- body=<glb> garment=<a.glb,b.glb> clip=<Name>_Walk frames=240 every=8 hem=true jiggle=true` - **one run per clip**, full clip names |
| **controls** | the same run that must fail: `cut=0.04` (a 4 cm hole), `rigid=spine` (a skirt on one bone, in a crouch), `colliders=false` (a skirt with no thigh colliders) | as above, plus the argument |
| **dress report** | `wardrobe.dress(...)`: `passed`, `problems`, `ease` (`compression`, `detail` with `relief_mm` against `detail_limit`), `cover` (covered and kept-drawn counts), `lifted`, `hem`, `export` | returned by `dress`; in a pipeline build, the `garments` stage report |
| **B:`<view>`** | the Blender close set of the dressed character | `<export dir>/review/<id>/close/`: `bust`, `under_bust` (only for a spec wearing a top), `crotch`, `knees` |
| **G:`<view>`** | lookdev's Godot close-shot with the garments equipped | `lookdev.mjs close-shot ... --garments <a.glb>,<b.glb> --views bust,crotch,full --presets clear_midday,overcast` |
| **strip** | the dressed body's review strips, garments in their own colours | `<glb dir>/review/<id>/<Name>_<Clip>_<view>.png` |

## Question bank

### Covered and closed (verify_wardrobe, every clip the character has: a crouch opens what a walk never does)
- **FIT-V1** Did every run measure something - `samples` > 0 and `problems` free of "no frame sampled", an
  unknown clip or a missing garment? *verify_wardrobe*.
- **FIT-V2** Is no hole open - `holes_frac` <= 0.005 in the worst frame of every clip? *verify_wardrobe*
  (`holes_by_bone` names where).
- **FIT-V3** Does no skin poke through the cloth - `poke_frac` <= 0.005 in every clip? *verify_wardrobe*
  (`poke_by_bone`).
- **FIT-V4** On a skirt or dress, does no leg pass through it - `thighs_frac` <= 0.005 in every clip,
  crouch and run included? *verify_wardrobe* (`thighs_by_bone`, `thighs_frame`).
- **FIT-V5** Is the body in Godot the one the garment was fitted to - no "hidden positions matched no body
  vertex" in `problems` (`hide_unmatched` 0)? *verify_wardrobe*.
- **FIT-V6** Does the hem swing and stay finite, inside its `max_offset_m`? *verify_wardrobe* `hem_stats`.
- **FIT-V7** Does each check still see a real failure - the `cut=0.04` run fails `holes`, and on a skirt
  `rigid=spine` and `colliders=false` fail `thighs` in a crouch? *controls*.

### Cut and eased (Blender)
- **FIT-B1** Did the garment build pass - `dress` `passed` true and `problems` empty? *dress report*.
- **FIT-B2** On a compression garment, is the carried relief under its limit - `ease.detail` `passed`, each
  region's `relief_mm` <= its `detail_limit`? *dress report*.
- **FIT-B3** Is the underside of the bust free of a shelf or a dark wedge between the breasts under a top?
  *B:under_bust*, *B:bust*; in Godot *G:bust*.
- **FIT-B4** Does the garment follow the body's form without tracing its detail - no nipple, navel or crease
  drawn through a garment the brief calls loose? *B:bust*, *B:crotch*, *G:bust*.
- **FIT-B5** Does the waistband or hem sit where the preset puts it, with no skin showing at the waist or the
  leg openings at rest? *B:crotch*, *B:knees* (shorts), *G:full*.

### Moving (the strips, with the numbers above)
- **FIT-M1** Is every covered area still covered in every cell, no skin appearing at a hem, the waist or an
  armhole? *strip `<Clip>_three_quarter`* and `_front` of each clip (animate-anything's "Outfit" bank).
- **FIT-M2** Does a loose hem or cuff move across the eight cells and lag the body? *strip `Walk_right`,
  `Run_right`*; *verify_wardrobe* `hem_stats` peak swing.
- **FIT-M3** Does no garment pass through the body or another garment in any cell? *strip* every view.

## Not answerable from these today

- A raised thigh through a skirt's front panel is counted (`thighs`) but has no tile: the close sets pose the
  Idle's first frame.
- Cloth sim garments (follow-through `cloth`) are judged by `verify_cloth.gd`, not by this list.
- How the fabric looks (weave, sheen): no garment material check exists; lookdev's LOOK-F questions cover
  only the skin under it.
