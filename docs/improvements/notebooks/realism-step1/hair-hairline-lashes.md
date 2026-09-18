# hair-hairline-lashes - lab notebook

Branch `hair-hairline-lashes` (plugins and grungist-creek), round realism-step1. Started 14:18, 2026-09-18, cut
from main 9d44ece (after hair-godot-transfer merged) and master c92107f. Scratch: `%TEMP%/rw/hhl/`
(`g/` = `tools/scratch_project.py` copy with study_man, study_woman and belle; `shot.sh <who> <out>` = `--import`
then `lookdev.mjs close-shot` face/eyes/head_side/face_3q, clear_midday + overcast, paired with the Blender close
set; `crop.mjs` = side-by-side crops for this notebook). Crops referenced below are in
[hair-hairline-lashes/](hair-hairline-lashes/).

## Setup (14:18-14:30)

- `scratch_project.py --who study_man,study_woman,belle --game <game worktree>`: 4.4 s, import clean.
- Baseline: study_man rebuilt on main's plugins (resumed from the real blend's copy; 34 s), Godot close-shot.
  The hairline is a hard line with a comb of dark spikes hanging from it onto the forehead (every strand's
  root zone is the same 13 mm band of V, and the opaque middle starts on one straight line of V); the lashes
  are a few thick dark streaks on the upper lid, sparse and clumped.

## Lashes

1. **Turning the upper card up (dead end, 8 min).** Guess: MPFB's upper card is near horizontal (mean normal
   (-0.02, -0.39, -0.92)) and so edge-on from the front. A `_lift_lashes` that turned each vertex up about the
   root line by 40 deg x t^0.8 measured the card first: its tips already rise 15.9 deg, and the lift ran 24 of
   48 lifted vertices into the lid (-1.8 mm), pushed back onto it - the lashes became a comb painted on the lid.
   Reverted. The card's angle is not what makes them read sparse.
2. **Anisotropic filtering on the cards (kept).** `CARD_GODOT.texture_filter = 5` (linear, mipmaps,
   anisotropic): the upper card is seen at a grazing angle, so plain trilinear takes a mip chosen by the squashed
   V axis and merges hairs. Slightly finer lashes and brow hairs; not enough alone.
3. **Density at the root (kept).** `brows.LASHES`: upper lid 260 long lashes (was 170) gathered 0.25 (was 0.6),
   1.3-1.9 texels at the root (was 1.6-2.3), plus 160 short lashes (0.1-0.3 of the card) packed at the root -
   the lash line. Lean scales with length. Face tile at 0.6 m: a continuous dark lash line with fine hairs over
   it instead of a few black blocks; the Step 0 clump over the left pupil is gone
   (`z_lashes_face_clear_midday.png`, `z_lashes_face_overcast.png`: Step 0 left, this branch right). Measured:
   the upper lid's root band (V 0.02-0.1) covered at alpha >= 0.5 - see the fixture numbers below.

## The man's hairline (14:30-14:40)

The cap texture near the line (lookdev `strand_texture`) had every strand rooted in `root_zone` [0.004, 0.07]
and an opaque middle from V 0.07 on one straight line: a ruled edge with a comb of dark spikes in front.

1. lookdev strand settings, off at the defaults and on their own random stream (a preset without them draws
   the identical texture): `root_ragged` (the dense start wanders across U), `root_power`, `root_width`,
   `fine_per_tile`. humanform's `short_crop` passes them as a `look` block; `edge_wobble_m` wobbles the cap's V
   near the line so the tile's ragged edge does not repeat every 4 cm.
2. First values (zone to 0.09, ragged 0.05 as sum-of-sines, power 0.6): a receding, scalloped, wet-looking band
   2 cm deep - too much, and the scallops (two per tile) read as blobs.
3. Ragged as a per-strand value blurred over three plus a weaker slow wave, zone 0.075, ragged 0.03, power 0.8,
   root width 0.45: uneven at the scale of a few hairs; but the root-zone strands were still full-dark spikes.
4. `root_fade` [0, 0.1] power 0.8 for short_crop (lookdev's is [0, 0.11] ^ 0.25, nearly flat): the strands in
   front of the dense line fade instead of ending in dark points. Kept (`z_hairline_eyes.png`: Step 0, then
   this branch, eyes tile 0.4 m clear_midday).

Measured on the exported textures (`feather.mjs`, `wander.mjs` in scratch): mean-alpha 10-90% ramp is 9.2 mm on
the default texture and 10.5 mm on short_crop's - the mean hardly moves, the comb was never about the mean.
What moves is where each few strands turn dense: p10..p90 across U 0.00 mm (default, a ruled line) against
2.15 mm (short_crop), before the 3 mm geometric wobble. That is the check in the fixture.

Seen, not fixed: a pale line along the hair edge at the temples seen from the front (eyes tile), in Blender and
Godot, present at Step 0 and a little wider now the root zone is sparser - the sparse strands seen edge-on.

## Brow shape (14:40-14:50)

`brows.BROW_SHAPES` natural (None: MPFB's card untouched, the default), straight, arched, soft, as offsets
along the skin against t along the brow; each vertex moves up the skin's tangent plane and back onto the skin at
its old height. Reported per side as `shape_profile_mm` / `moved_mm`. Through the brief (`hair.brow_shape`,
`sheet.validate`), `hair.add(brow_shape=)` and the spec (`[hair] brow_shape`, refused if unknown; absent or
"natural" hashes as before). Built study_man with each (`z_brow_shapes.png`).

Fixture numbers (`hair_presets`, curvy woman): natural moves every brow vertex 0.000 mm from the default call;
arched lifts the outer third (t 0.7) 2.05 mm (max 2.62 mm), control (arched with flat keys) -0.01 mm, must fail
the 1 mm floor and does; soft moves at most 0.89 mm. Natural brow profile along t 0.1..0.9: 0, 1.76, 1.59,
0.04, -2.72 mm. Crops `z_brow_shapes.png` (study_man face tile, clear_midday: natural, straight, arched, soft,
top to bottom): arched's peak and dropped tail and straight's flatter line show at 0.6 m; soft is subtle.
**Specs not changed**: on study_man straight is a little more level and arched visibly peaked, but neither is
clearly better than his natural brow, and study_woman's natural brow already reads; the default stays.

## Belle's brows

Not the same cause as anything above: `belle.toml`'s `[hair]` never turned `brows`/`lashes` on (they are off by
default). Turned on in the game worktree (`characters/belle.toml`); built in scratch (64.6 s, resumed from the
real blend's copy, dressed flesh path unchanged) - brows and lashes present in Blender and Godot
(`z_belle_brows.png`: before, after; eyes tile, clear_midday).

## Proof on the real figures (14:40-14:55)

Scratch builds (final) of study_man (every brow shape, natural last), study_woman and belle with this branch;
close-shot at 1 m unpaired (`new1m/`) and paired with the Blender close set (`new/`, `shape/`), clear_midday and
overcast. `z_man_1m_face.png`, `z_man_1m_side.png` (study_man at 1 m, clear_midday and overcast),
`z_woman_lashes.png` (study_woman face tile, Step 0 glb left, this branch right: no clump over the pupil, a
fine continuous lash line). humancheck on the built blends: StudyMan 0 fail, 2 warn (pieces, open edges -
the eyes, hair and cards), 30 pass; StudyWoman 0 fail, 2 warn, 30 pass.

Honest read at 1 m: the hairline is no longer a ruled edge with a comb; it thins out unevenly over about a
centimetre and reads as hair at the edge. The cap as a whole is still a smooth, uniformly dark dome (short
hair's volume and colour variation are not this branch's). Lashes read as a dark lash line with fine hairs on
both figures from the front; no clump crosses a pupil.

## Regress

- `--quick --jobs 2` (9 fixtures): 8 ok, `hair_presets` CHANGED on exactly the intended keys (lash texture hash,
  lash coverage 0.1236 -> 0.1437, new keys). The lash control did not fail at the first floor (0.3; Step 0's
  lashes 0.513) - the floor was set above the control (0.65; now 0.736), a new check, not a widened one.
- Golden updated with `--only hair_presets --update`, read, committed on its own (dcc76eb).
- Godot: no addon or export code changed (lookdev's Godot addon is untouched; the cards' new `texture_filter`
  goes through the existing `set_properties`), so no `--godot` run; the scratch game's close-shots are the
  Godot check.

Final `--quick --jobs 2` after the golden (14:55-14:57): `REGRESS DONE exit=0, 9 fixtures ok`. Full output:
`%TEMP%/rw/hhl/regress_quick_final.log`. Ended 14:58 (40 min).

## Open

- A pale line along the hair edge at the temples seen from the front (Blender and Godot, Step 0 too, a little
  wider now).
- The cap is still a smooth dark shell overall at 1 m; short hair would want colour and sheen variation.
- The brow shapes move the card, not the texture: straight and soft are subtle at 1 m.
- The game's committed glbs are not rebuilt (ship step: study_man, study_woman, belle).

## What worked first time / what cost time

- First time: the lookdev settings on their own random stream (defaults pixel-identical: `hair_presets`' bob
  and ponytail keys did not move); brow shapes along the skin.
- Cost: the lash lift (8 min, reverted); the scalloped first hairline (one build); a bash heredoc with nested
  quotes failed to parse (use Write for Python edit scripts); pipeline builds took 60-80 s each under load
  (hair changes restart from body).

## Fix round after critic 1 (15:01-)

Critic 1: Q1 not met. At 1 m study_man's hairline was still a band of dark comb-like spikes over a smooth dark
cap, and from the side a helmet with a spiky rim. Minor points: `sheet.validate` reported only the first of a bad
colour and a bad brow_shape; `edge_wobble_m` had no check of its own. Scratch for this round: `%TEMP%/rw/hhl2/`
(`preview.py` draws the cap texture near the line over skin, at 0.1 mm/px and at 1 m pixel size, pure numpy
under Blender's Python; `uvshear.py` measures the angle between U and V on the exported cap; `shot1m.sh` =
close-shot at 1 m unpaired).

1. **The front: edge hairs (kept).** `preview.py` of round 1's look reproduced the comb. The long strands rooted
   up to 1.5 cm in front of the dense start, all parallel and full dark. New lookdev settings (off at the
   defaults, own random stream seed + 15485): `edge_hairs` short thin hairs per tile scattered in front of the
   dense start, denser nearer it (`edge_power`), up to `edge_depth` in front with that reach itself wandering
   (0.4-1.6 x), each leaning off a slowly turning direction (`edge_lean`), lighter toward the front
   (`edge_tone`). short_crop: 900 per tile, width 0.2-0.4 pitch, lean 9 texels, and the long strands rooted
   close to the dense start (`root_power` 0.15, so no long spikes left). A little more lock and strand variation
   on the dome (`lock_jitter` 0.5, `strand_jitter` 0.25, `gap_mult` 0.6). Iterated in `preview.py` (e1-e6), and
   `z_r2_texture_preview.png` is the kept look. The first scatter (500 hairs, thick) read as dark stubble or a
   band of grass with a ruled lower edge. Thinner, denser, lighter hairs with a wandering reach fixed that.
   In Godot at 1 m (`z_r2_front_1m.png`, round 1 left, now right) the comb is gone. The hairline thins through
   scattered fine hairs.
2. **The side: the UVs, not the texture.** The temples and sideburns still showed long diagonal spikes after
   step 1. `uvshear.py` on the exported cap found the cause. Near the line on the sides (|x| > 7 cm, V < 0.12),
   U and V met at a median of 26 degrees (front: 82). U runs round the strand axis (azimuth 180, elevation 70),
   and where the hairline runs steeply the axis's U lines cross it at a slant, so the root zone sheared into
   spikes. New humanform `line_u_m` (off at the defaults; short_crop 3 cm): within it, U is the axis angle at the
   foot of the vertex on the line (one Newton step down the tangent-plane gradient of `d`), eased back to the
   axis's U by 3 cm.
   - First build: side median 26 -> 63 degrees and the spikes gone. But faceted blotches appeared behind the
     temple, because `d`'s gradient jumps where the ear distance takes over.
   - Relaxed the turn over the mesh (8 passes, then 16): the blotches went, but the shear came back partly (side
     median 45).
   - Held the relaxation at the line (weight 0 at d = 0, full from 0.9 cm in). Kept: no facets
     (`z_r2_side_1m.png`: round 1, edge hairs only, both), and near-line median on study_man 61 degrees.
3. **Checks (each with a control that must fail, and does).** In the fixture, on the curvy woman:
   - `hairline_feather.*.fringe_ratio`: in the thinning band, the mean |d alpha / d mm| along V over across U.
     short_crop 0.161; the control (round 1's comb look) 0.050; bob 0.048. Floor 0.1.
   - `hairline_feather.line_u`: the median U-V angle on cap faces within 8 mm of the line at |x| > 4 cm. 57.7
     degrees, against 35.5 with `line_u_m` 0 (the control). Floor 50. I first guessed 60 before measuring; that
     was never committed, and the floor was set once from these numbers.
   - `hairline_feather.edge_wobble`: `edge_wobble_m` moves the cap's V by at most 3.0 mm near the line; the
     control, off against off, moves 0.0 mm. Floor 1 mm.
   - `sheet.validate` now checks brow_shape on its own. The fixture's brief with a bad colour and a bad
     brow_shape reports both.
4. **What moved in the golden** (its own commit, 9567dc5):
   - short_crop edge wander 2.21 -> 2.34 mm, feather 10.55 -> 10.94 mm.
   - The new keys, plus `cap.line_u` (null on every other preset).
   - short_crop `uv_tangent_turn.hair.over_35_deg` 83 -> 246 (max 80.9 -> 86.2). This is the cost of the line-U
     turn: more per-face tangent turn. Godot's `strand_tangents` averages tangents, and the 1 m sheet shows no
     dark facets in the sheen under clear_midday or overcast. It is recorded here and left open.
   - No other preset's numbers moved.

Honest read at 1 m (`%TEMP%/rw/hhl2/r6/sheet.png`):
- Front and 3/4: the hairline is feathered. Fine hairs thin out unevenly over about 1 cm, with no comb.
- Side: the temple and sideburn edge now thins out in fine hairs instead of long diagonal spikes.
- Still open: the cap as a whole is a smooth, dark, slicked shape (its volume, and colour variation beyond the
  locks). Short hair also needs a shape that is not a shell 3.5 mm thick.
- A small patch just above the ear still shows a few crossing hairs.
