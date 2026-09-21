# cloth-bust-hang (NEXT "Cloth that hugs the skin", the open item after branch A) - 2026-09-21

**Result:** loose tops hang straight down from a bust's apex instead of following the breast back in
to the fold beneath. `fit.tuck` is a new check that measures it, `tuck_limit` is a new preset gate, and
`dressed_loose` is a new fixture, the first one that dresses `tshirt` or `longsleeve`. wardrobe 0.6.0 ->
0.7.0.

| | tuck, max mm (0.6.0 -> 0.7.0) |
|---|---|
| Ruth longsleeve | 17.2 -> 2.9 |
| Marco tshirt | 7.1 -> 1.4 |
| Belle in a tee (stress) | 7.8 -> 4.4 |
| sample Figure longsleeve (fixture) | 34.1 (the control) -> 3.7 |

## The cause

`fit._hang` already hangs cloth from the widest point above it: a per-sector running max of the
radius around the spine's root. It never reached the bust. `_hang_setup` fades hanging in from
`shoulder_z - 0.3 * (shoulder_z - hip_z)`. On Ruth that line is at z 1.160 and her apex is at 1.177,
so the apex was above the line and not hanging, and the fold at about 1.10 had half a mask. On Belle
the apex is just below the line (mask 0.24). The field is built only from vertices that hang, so the
apex never became a source.

## Attempts, in order

Harness as in `cloth-span-loose.md`, plus `tuck.py`: the same measure as `fit.tuck`, run on the
saved blend. `zoom.py` is a 0.3 m orthographic close-up of the right breast from 3/4, side and low.

1. **Start hanging higher** (`hang_top` 0.3 -> 0.1, fade 0.25 -> 0.15). Tuck 17.2 -> 4.6 mm, and the
   side view hangs straight. But **each apex became a small cone** that read as a nipple from the
   front, which was the user's original complaint. Breast `traced` 0.006 -> 0.116.
2. **More blur in the field** (sectors, cells) (2,2) / (3,4) / (2,6) / (4,6): cone softer at
   (2,6), no fix.
3. **`settle` after**, 0.05 / 0.1: traced back to ~0, cone still there. The close-up showed a
   **crescent crease just under the apex** that the front views had hidden.
4. **Rows made convex** (`_hull_rows`: each height's ring of radii replaced by its convex hull, so the
   cloth spans between the two breasts): no ridge down from each apex, crescent unchanged.
5. **Hang the blurred field again** (so the blur cannot dip under the apex): crescent unchanged.
   Dropped.
6. **48 relax iterations instead of 16**: crescent smaller, a crimp still there. That was the clue:
   the crescent was the mesh folding, not the field.
7. **Columns made concave too** (`_hull_columns`: the string over each sector's profile, collarbone
   to apex to belly): kept, but the crimp was still there.
8. **Evening heights** (`_even_heights`, kept). Hanging moves cloth straight out and never up or down.
   The underside of a breast runs DOWN from the apex and back UP into the fold, so once pushed out
   onto the hung sheet those vertices sat in the wrong order in height and folded over each other
   just under the apex. A height-only relax between pushes (4 passes, weighted by the hang mask)
   unfolds it. **The crease is gone in the close-up**, and a soft apex is left.

Then the relax budget was checked with the height relax in place: 16 iterations and no settle
brought the crimp back (breast traced 0.155); 24 iterations with settle 0.05 was nearly clean; 48 with
settle 0.05 was clean. The preset takes 48.

9. **Settle, then hang again** (4 more hang + even + push passes after `_settle`): faceted, breast
   traced 0.22-0.46. Reverted.
10. **Taller blur** [2, 8] / [4, 10]: no better than [2, 4]. Not taken.

**What is left: a small crease at each apex.** The hull makes the profile two straight lines meeting at
the apex (the collarbone chord above, the hung sheet below). The blur rounds that corner over a few cm.
In Blender Workbench it barely shows. **In Godot under clear_midday at 1 m it reads as a small
horizontal mark at each apex on Ruth** (`%TEMP%/rw/hang/look/bust_godot.png`). Marco is clean. The user
saw it and chose to ship: the fold under the bust was the larger problem. Rounding it properly is
cloth bending stiffness, which these offsets only approximate.

## Skin weights

With the cut's weights kept vertex for vertex, `verify_wardrobe` on Ruth passed but with poke up to
0.33 % (crouch), 13-21 vertices at a time, all on `ft_jiggle_breast.L/R`. Hanging moves the cloth under
the bust centimetres from the skin it was cut from, and `_even_heights` slides it vertically, so a
vertex carried the weights of skin that is no longer under it. The presets now take `"skin":
{"transfer": true}` (a new preset key: `presets.dress` passes it to `fit.skin`), which takes the weights
from the body's surface under the cloth. Ruth: walk / run / crouch / jump poke 0.064 / 0.064 / 0.095 /
0.064 %, all `spine.003`, and no breast. Marco: 0.19 / 0.16 / 0.04 / 0.05 %, against 0.09 / 0.09 /
0.02 / 0.03 % on 0.6.0 (mostly upper_arm, near the armpit, where hanging now starts). All pass the
0.5 % limit. Holes are unchanged or lower.

## What shipped

- `fit._hang_setup(top, fade)` and `fit._hang(hull, blur)` take arguments, and `ease` exposes them as
  `hang_top`, `hang_fade`, `hang_hull` and `hang_blur`. **Every default is the old value**, so
  every garment and every golden that does not opt in is unchanged. `dressed_presets`,
  `dressed_figure` and `dressed_skirts` pass unmoved.
- `_hull_rows`, `_hull_columns` and `_even_heights` run only when `hang_hull` is set.
- `fit.tuck(garment, body, limit=)` measures the front within +-50 deg, between the hips and 5 cm
  under the shoulders: the widest cloth in the same 5 deg wedge within 15 cm above each vertex,
  less its own radius. `ease(tuck_limit=)` reports it, and `presets.dress` fails on it the way it
  fails on `detail_limit`.
- `tshirt` and `longsleeve`: `hang_top` 0.1, `hang_fade` 0.15, `hang_hull`, `hang_blur` [2, 4],
  `iterations` 48, `settle` 0.05, `tuck_limit` 8 mm.
- **The control that must fail:** in `dressed_loose` the longsleeve is eased with 0.6.0's hang, and
  it fails at 34.1 mm against 8, with the verdict in the golden. On Ruth the same settings reproduce
  0.6.0 to the digit (tuck 17.2, traced 0.011) and fail too.

## Cost

The garments stage goes from 5.3 to 9.2 s on Marco and from 5.2 to 10.3 s on Ruth, because of the
48 iterations. That is about 4 s on the benchmark's cold build, which is still over its 30 s goal.
The cheaper fixes (16 or 24 iterations) left the crease.

## Open

- **The apex crease** (above), and Marco's poke doubled while staying under the limit.
- Belle in a tee still tucks 4.4 mm, the most of the three. It is under the limit, but her bust is
  the heaviest and is not a character that wears these presets.
- The hang axis is the spine's root, so "radius" is taken from the pelvis. A body leaning well
  forward or back would read tuck against the wrong axis. Nothing in the cast does.

## Regress

`regress.py --quick --jobs 3 --godot <scratch game>` on the final tree: `REGRESS DONE exit=1, 25
fixtures ok`. The one FAILED row is the known `verify_strands pipeline_ponytail`, with NEXT.md's numbers.
`dressed_presets`, `dressed_figure` and `dressed_skirts` are unmoved; `dressed_loose` is new and its
`verify_wardrobe` row is ok (poke 0.133 %). Log: `%TEMP%/rw/hang/regress_clean.log`.
