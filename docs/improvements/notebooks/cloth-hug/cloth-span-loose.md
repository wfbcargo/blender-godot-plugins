# cloth-span-loose (NEXT "Cloth that hugs the skin", branch A) - 2026-09-21

**Result: the branch ships as a preset change, not the code change NEXT.md specified.** Ungating `span`
was built, measured and rendered, and it made the loose tops worse. What fixes them is `smooth`, which
already existed: `tshirt` and `longsleeve` now ease off the body smoothed over 20 cm (`smooth` 1.0)
and carry the sports top's `detail_limit` of 0.06 mm. wardrobe 0.5.2 -> 0.6.0. No code in `fit.py` moved.

## Harness

Copies of the real blends in `%TEMP%/rw/cloth/` (never the originals). `redress.py` deletes one garment
and runs `presets.dress` again with the worktree's wardrobe, optionally overriding the preset's `ease`,
and prints `fit.detail`, the gap statistics, folds and cover. `shots.py` renders the chest front, 3/4 and
side in Workbench. A re-dress takes 1.6-2.5 s.

The harness reproduces NEXT.md's before table exactly: Ruth's longsleeve re-dressed on main reads
traced 0.191, relief 0.143 mm, breast 0.096 mm, as in the file.

## Attempt 1 - ungate span, as specified (dead end)

`span` was gated by `compressing` because it is weighted by compression's fade (`1 - floor`). For a loose
garment I gave it the same shape measured on the cloth: 1 at the openings, falling to 0 over
`COMPRESS_FADE` along the cloth.

Ruth, longsleeve, span 0.5 / 0.8 / 1.0, span_radius 0.1: traced 0.27 / -0.03 / -0.06, **but gap_min
-5.6 / -12.3 / -18.9 mm (cloth inside the skin), gap_max up to 14.6 cm, 13-18 folded faces.** The hull is
the convex hull of the whole garment, sleeves included: it runs from the arm to the ribs, `_hollows`
reads the gap under the arm as a hollow, and the torso's side is pushed out into it.

## Attempt 2 - span over the torso only (dead end)

Hull and hollows taken over the torso's cloth only (arm-chain weight under 0.2, `_hang_setup`'s test),
each vertex spanning by that weight. The folds went (4) and the cloth stayed outside the skin, but:

| Ruth longsleeve | traced all | breast traced | breast mm |
|---|---|---|---|
| before | 0.191 | 0.160 | 0.096 |
| span 0.8, r 0.05 | 0.205 | 0.544 | 0.325 |
| span 0.8, r 0.10 | 0.182 | 0.236 | 0.141 |
| span 0.8, r 0.20 | 0.125 | 0.234 | 0.139 |
| span 0.8, no radius | 0.087 | 0.247 | 0.147 |

**Spanning never touched the breast's own relief and made it worse.** `detail` measures relief at 3 cm
(`DETAIL_REACH`): a nipple, a navel, the underbust fold's edge. The cleft between the breasts is broader
than that and is the body's form, which the metric deliberately does not count. Span moves the cloth
across hollows; it has nothing to say about a bump on a convex surface. The render agreed: a ridge under
the bust and the nipples back.

## Attempt 3 - `smooth` on the loose presets (kept)

| | traced all | relief mm | region |
|---|---|---|---|
| Ruth longsleeve, smooth 0.5 | 0.016 | 0.012 | breast -0.003 / 0.000 mm |
| **Ruth longsleeve, smooth 1.0** | **0.011** | **0.009** | **breast 0.006 / 0.004 mm** |
| Ruth, smooth 1.0 + span 0.8 r 0.1 (torso) | 0.032 | 0.024 | breast 0.078 / 0.046 mm, 4 folds |
| **Marco tshirt, smooth 1.0** (before 0.189 / 0.164) | **-0.005** | **0.000** | belly 0.001 / 0.001 mm |
| Belle in a tshirt (stress: heaviest bust), before | 0.059 | 0.056 | breast 0.130 / 0.134 mm |
| Belle in a tshirt, smooth 1.0 | -0.015 | 0.000 | breast 0.019 / 0.019 mm |

NEXT's target was traced below ~0.05 on a loose garment; this lands at ~0.01. Rendered in Blender
(Workbench, front / 3/4 / side), smooth 0.5 still shows the nipples and 1.0 does not; the bust still
shapes the outline, which was the chosen target ("span the hollows, keep the silhouette").

Why this is physically right rather than a trick: woven or knit cloth has bending stiffness, so it
cannot follow relief a few centimetres across; it rests on the high points. Easing 11 mm off the raw
skin makes the cloth a copy of the skin offset outward - every nipple and rib included - which is what
the user saw. `smooth` eases off the body's form instead.

Side effect worth knowing: `smooth` makes `ease` take its compression path (`compressing` is
`bool(smooth) or bool(flatten)`), so the report has a `compression` block for these tops. gap_min falls
from 6.9 to 1.1 mm on Ruth and 9.5 to 6.3 mm on Marco - the cloth now rests near the bust's peak, as a
real tee does. `cover` is unchanged (no `behind`), so nothing is hidden differently.

**The control that must fail:** the same presets with `smooth` 0 fail their new limit -
Ruth "detail all: the cloth carries 0.143 mm of the skin's relief, limit 0.060 mm", Marco 0.164 mm.

## Through the pipeline and in Godot

`tools/scratch_project.py %TEMP%/rw/cloth/game --who cast_marco,cast_ruth`, then `build.sh` for both
(exit 0; Marco 72.7 s, Ruth 82.7 s, every stage ran). The real game's current assets were copied beside
them as `assets/base/` for the before.

`verify_wardrobe` (frames 240, every 8, 29 samples), all 16 runs PASS:

| | Walk | Run | Crouch | Jump |
|---|---|---|---|---|
| Marco tshirt poke, before -> after | 0.124 -> 0.093 % | 0.101 -> 0.093 % | 0.023 -> 0.023 % | 0.046 -> 0.031 % |
| Ruth longsleeve poke, before -> after | 0.016 -> 0.024 % | 0.055 -> 0.071 % | 0.063 -> 0.079 % | 0.016 -> 0.008 % |

Holes identical before and after on every clip (Marco 0.063 / 0.126 / 0 / 0 %, Ruth 0 / 0 / 0 / 0.053 %).
Ruth's poke rises by one or two vertices on the right breast (worst 9 of 559 candidates at a run), still
seven times under the 0.5 % limit; the cloth now rests closer to the bust's peak, which is where that
comes from. Marco's falls.

lookdev close-shot `bust` at 1 m, clear_midday, before and after (`%TEMP%/rw/cloth/look/`): Ruth's
nipples read clearly through the longsleeve before and are gone after; Marco's chest detail softens.

## Open - not done here

- **The cloth still tucks under the bust.** Side view in Blender and the Godot bust shot both show the
  cloth following the breast's underside into the fold. A real tee hangs straight down from the apex.
  `hang` should do this and does not reach: `_hang_setup` fades hanging in only below
  `shoulder_z - 0.3 * (shoulder_z - hip_z)`, and the bust sits at about that line. That is NEXT's
  branch B territory (`cloth-torso-ease`) or its own branch; it moves every hanging garment, so it needs
  the dressed fixtures re-recorded.
- **Span for sleeved garments is broken if anyone asks for it.** A compression preset with sleeves and
  a `span` would push the torso into the gap under the arm (attempt 1). No such preset exists. The
  torso-only hull from attempt 2 is the fix if one ever does; it is not shipped because nothing uses it.
- **Branch C** (is `flatten`'s "breast search lands on the jaw" note stale?) was not needed and not checked.
- The six figures in the game were not rebuilt; Marco and Ruth are the two whose outfits change.

## Regress

`python tools/regress.py --quick --jobs 3` on the branch: `REGRESS DONE exit=0, 13 fixtures ok`
(log `%TEMP%/rw/cloth/regress_quick.log`), including `dressed_presets`, `dressed_figure` and
`traced_detail`. Those passing unmoved means **no fixture dresses the tshirt or longsleeve presets**:
the only gate on this change today is the preset's own `detail_limit` when a character builds. A
fixture that dresses both on a body with a bust is worth adding with the tuck-under-the-bust branch.
