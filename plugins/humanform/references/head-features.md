# Head features: designing one from a description

`humanform.features` puts a creature's head on an unbaked MPFB body before any proportion warp:

```python
from humanform import features
spec = {"shape": "square", "shape_weight": 0.7,
        "features": {"brow_ridge": 0.6, "tusks": 0.7, "nose_size": -0.3,
                     "horn_nubs": {"weight": 0.8, "attach": {"length": 0.03}}}}
problems = features.validate(spec)        # [] or messages that name the fix
rep = features.apply(human, spec)         # keys, parts, warnings; `unknown` lists names it skipped
```

A weight is in [-1, 1] and 0 is human. A negative weight is the opposite change: it loads the opposite
MPFB target (incr/decr, in/out, up/down, forward/backward, or the preset's `neg_targets`), presses a
displacement in instead of out, and drops attached parts.

## What a feature is

Every feature, preset or new, is one definition with up to three parts. The presets (`features.PRESETS`) are
definitions like any other, so the quickest way to design a new one is to copy the closest preset.

| part | what it does | when to use it |
|---|---|---|
| `targets` | MPFB targets by file stem and gain, `{"nose-volume-incr": 0.7}`. l-/r- pairs are found by themselves. | MPFB already has the change: ears, nose, jaw, cheeks, eyebrows, chin, mouth, head shape. Look in `mpfb/data/targets/<group>/`. |
| `displace` | moves a region of skin: `region`, `direction`, `falloff`, `amount`, `smooth` | the change is a form MPFB has no target for: a ridge, a bump, a hollow, a snout, a crest |
| `attach` | a rigid part: a cone, horn or tusk, skinned 100% to a bone | the change is not skin: horns, tusks, spikes, a unicorn's horn |
| `muzzle` | a snout: the face carried forward along the jaw's axis and gathered into a tube | the change is the whole front of the head, not a region of it |

Presets: `ears_pointed`, `ear_size`, `ears_large`, `brow_ridge`, `nose_size`, `jaw_heavy`, `cheek_gaunt`,
`tusks`, `horn_nubs`, `horns`, `ram_horns`, `muzzle`.

## A muzzle

`muzzle` is the one feature a displacement cannot make, because a snout is not a bump on a face: it is the
face itself carried forward, with the mouth, the teeth and the tongue riding in it. Its numbers (metres are on
the reference head and scale with this one), and the canine preset's values:

| key | what it does | preset |
|---|---|---|
| `length` | how far the snout's tip travels along the jaw's axis (the mandible's angle to the mouth) | 0.085 |
| `width` | the snout's breadth at the tip as a share of the face it grows from | 0.46 |
| `bridge` | the dorsum's rise over the middle of the snout (negative dishes it) | 0.005 |
| `pad` | the nose pad's radius at the tip; it stands 0.45 of that out of the snout | 0.020 |
| `pad_tilt` | degrees the pad's face turns down from the axis | 40 |
| `lip` | how far the front of the lip line runs out along the snout, as a share of `length` | 0.35 |
| `lip_back` | how far the mouth's corners run back under the eye, as a share of `length` | 0.35 |
| `stop` | the notch at the bridge between snout and forehead (m); a person has none | 0.008 |
| `eye_set_back` | how far the orbits are drawn back out of the growing face | 0.025 |
| `cheek` | how broadly the gathering fairs back into the cheeks | 0.7 |
| `smooth` | Laplacian passes over the field | 6 |


The preset also carries the MPFB targets for what a skull does and a field cannot:
`head-back-scale-depth-decr` (a dog's braincase is 0.55 of its skull against a person's 0.81), both
lip-volume targets and `mouth-scale-vert-decr` (a dog's lips are thin and pigmented, not everted),
`cheek-volume-decr`, and `eye-trans-out` (a bear's eyes sit 0.43 of the head's breadth apart, a person's
0.21).

## What a muzzle is measured against

`features.MUZZLE_PLAN` holds a canine skull's published proportions and `features.muzzle_measure` measures
the built head in the same ratios, so "it still reads human" is a number before it is an opinion:

| ratio | plan | a person | hm08 reaches |
|---|---|---|---|
| muzzle / head length | 0.39 (dog 69.84/177.72, bear 111.55/289.31) | 0.19 | 0.26 shipped, 0.32 pushed |
| muzzle length / its own breadth | 1.39 (dog 69.84/50.08) | 0.49 | 0.98 shipped, 1.21 pushed |
| lip line / muzzle length | 0.75 (the dog's tooth row ends under the orbit) | 0.24 | 0.36 shipped, 0.44 pushed |
| the stop | +12 deg over the person's own (dog craniofacial angle 19-21 deg, brachycephalic 9-14) | 0 | +29 |

Sources: [mesaticephalic dog skulls, n=25](https://revistas.usp.br/bjvras/en/article/view/55818);
[Iranian brown bear skulls](https://ijvm.ut.ac.ir/article_58686_d97fd9c1490f99afe25c9d0b8c134767.pdf);
[craniofacial angle by cephalic type](https://www.sciencedirect.com/science/article/abs/pii/S0940960211800439).

**hm08 cannot reach the plan**, and that is the finding a grafted head has to answer. Pushed to its limit -
130 mm of carry with the eyes held 60 mm back - it reaches 0.32 of the head's length (82% of a dog's) and
0.44 of its lip line (59%), and pays 2.5x at its worst edge, 2.3x over its worst hundredth and 4.4 mm of eye
socket out of round. The length ratio saturates because the field that keeps the skin whole carries the eyes
forward with the face; the lip line saturates because hm08 has one loop of lip, ending at the commissure, so
there is nothing to make a long mouth out of. What `muzzle_problems` refuses is the other end - a head not
measurably past the person's own (`READS_HUMAN`) - and the distance from the plan is reported on every build
(`plan_reach`).

How it is shaped, and why - each line was measured, not guessed:

- **The carry falls off over the whole head, not over the snout alone.** hm08's face is a fine mesh (1.6 mm
  edges round the nostrils) and its texture rides its own UVs, so a snout grown over a short ramp stretched
  the pores 7x where the ramp crossed the nose. Spread over the head's 190 mm of depth the worst edge grows
  by about a third instead; `CROWN_FOLLOW` keeps the skull from following the face all the way.
- **The gathering is what makes it a snout.** Carried forward alone the face keeps its own shape - the nose
  still stands out in front of the lips - and reads as a long face. Round the jaw's axis the front of the
  face draws in toward it (`width`), most at the tip, so the nose comes down and the chin comes up.
- **`lip` closes the last step.** A person's lips sit 25 mm behind the nose: the front of the mouth is
  carried further than the rest so the lip line runs out to the end while the corners stay - the long lip
  line a muzzle has.
- **The teeth and the tongue ride the lip line** (rigid, not sheared), and each eyeball rides its socket.
- **What it may not do**: `report["features"][<name>]["muzzle"]["skin"]` is `features.surface_strain` - how
  far the skin's edges grew (`stretch_max`, `stretch_p99`), how far they pinched (`squash_min`) and what
  became of the triangles (`quality_keep_min`). Past `STRETCH_MAX`, `SQUASH_MIN` or `QUALITY_KEEP` the build
  stops with the number and the fix in the message; `eyes` says how far the sockets moved and whether the
  balls still fit them (`socket_radius_mm`).
- **The mouth still works.** The closed-mouth check (`features.closed_mouth`) passes on a muzzled head, and
  `humanform.jaw` opens it: the muzzle's lower half is the part of the jaw's own region the snout carried
  forward.

## Regions

- **Named regions** (`"region": "brow"`): `brow`, `forehead`, `crown`, `temple`, `nose`, `ear`, `ear_tip`,
  `cheek`, `jaw`, `chin`, `lips`. Most are the reach of an MPFB target (the vertices it moves, normalised to 1),
  so a region is where MPFB itself thinks that part of the face is. `{"name": "ear", "side": "L"}` restricts
  one to a side.
- **Anchored regions** (`{"anchor": "forehead", "offset": [0.024, 0, 0.004], "radius": 0.016}`): 1 at a
  landmark (plus `offset`), falling to 0 at `radius`. A sided landmark (`temple`) gives a pair; a central one
  (`forehead`) with an offset out of the midline gives a mirrored pair too, unless `"mirror": false`.
- **Cuts** on either kind: `"facing": "forward"` keeps only skin that faces that way, and
  `"above"`/`"below": "mouth"` (or `["mouth", 0.0015]`, a margin in metres) keeps only skin above or below a
  landmark. **Anything near the lips should be cut at the lip line.** A bump that reaches both lips pushes one
  through the other. The tusks' lip bump did this (62 faces) until it was cut `below` the mouth.

Landmarks: `eye`, `brow`, `temple`, `cheek`, `jaw`, `ear`, `ear_tip`, `mouth_corner`, `tusk_root` (sided:
bare for both sides, `.L`/`.R` for one), and `glabella`, `nose_bridge`, `nose_tip`, `forehead`, `crown`,
`occiput`, `lip_upper`, `lip_lower`, `chin`, `mouth` (central). They are found on this body each time
(eye helpers, MPFB target reaches, ray casts on the face), so they follow the fit and every target.

## Displacement

- `direction`: `normal` (the default: out of the skin), `up`, `down`, `forward`, `back`, `out` (away from the
  midline), `in`, a vector `[out, forward, up]`, `{"toward": landmark}`, `{"away": landmark}` or
  `{"axis": [from, to]}`.
- `falloff` over the region's 0..1: `smooth` (default), `linear`, `gauss`, `sharp`, `dome`, `flat`.
- `amount`: metres at the region's peak **on the reference head** (crown to lip line `REF_HEAD`, 0.175 m). It is
  scaled by this head's size and by the weight. 3-6 mm is a clear form on a face; 10-20 mm changes the
  silhouette (a snout, a crest).
- `smooth`: Laplacian passes over the weights (default 2). The result is despiked to what hm08's ~15 mm edges
  can show, and the report gives `spike_um`.

## Attached parts

`kind` sets the defaults (`features.KINDS`): `cone` (straight), `horn` (curved, dark, 9 rings), `tusk` (up
from the lower lip, tilted forward until it rests on the upper lip). The keys are:

- `anchor` and `offset` place the part. An offset part is re-seated on the skin.
- `direction` is `normal` or a vector `[out, forward, up]`.
- `length` and `base_radius` are in metres on the reference head. `tip_radius` is a fraction of the base when
  under 1.
- `curve` is the tip's bend in lengths, `[out, forward, up]`. It is parabolic: use it for a gentle sweep.
- `curl` is degrees about `curl_axis` (default `[1, 0, 0]`, out), for a spiral like a ram's.
- `sink` is how many base radii are buried along the skin normal, so the root never floats.
- `clear` and `clear_above` hold the part above a landmark this far in front of the face (negative presses in).
- `color` (sRGB), `roughness`, `bone` (`"head"` or a bone name), `rings`, `segments`, and `grow` (its size at a
  small weight, as a fraction of weight 1's).

All parts go in one object, `<human>_headparts`, one material per feature. character-pipeline's bake joins it
into the body beside the eyes and the teeth.

## Designing one from a description

1. **Name what changes and what kind of change it is.** "Goat horns curling back from the temples" is an
   attach (`horn`, anchor `temple`, `curl`). "A heavy snout" is a displace (region `nose`, direction
   `forward`) plus MPFB nose targets. "Pointed ears" is a target.
2. **Start from the closest preset.** `{"preset": "horns", "attach": {...}}` changes only what differs.
   Giving a preset's own name with a table (`"tusks": {"attach": {"length": 0.03}}`) also merges over it.
3. **Size it against the face.** Ear to ear is about 150 mm, eye to eye 64 mm, a nose 50 mm long and a lip
   height about 10 mm. A tusk 24 mm long reads from across a room; a horn nub is 20 mm.
4. **Validate, then apply and look.** Render the face front, three-quarter, side and from below (the
   scratch scripts in this round used an orthographic camera 0.30 m wide on the head bone, workbench with
   cavity). Zoom on anything near the mouth, and render it again with the body hidden to see the teeth.
5. **Read the report.** `warnings` and `intersections` catch skin pushed through skin: `{region: faces}`, and a
   human head has none. `displace.spike_um` catches facets. `parts[].tilt` shows how far a `clear` part had to
   lean. `eyes_moved_mm` shows whether the targets moved the sockets (the eyes follow them).
6. **Build an extreme body too.** Sizes scale with the head, so check a 1.48 m body beside a 1.80 m one.

## What is never lost

- **Teeth and tongue** are `<human>_teeth`, from MPFB's helpers. They sit where every target put the mouth,
  with the body's skin weights. Tusks are added in front of them, never in place of them. MPFB's teeth
  helpers are two bands, not individual teeth.
- **Eyes** follow the eye helpers if a target moves the sockets.
- **Brows and lashes** are laid on the baked body later from its own triangles.
- **Ears** keep their canal and helix: the ear presets are MPFB's own ear targets, not displacements. One
  quad in the concha folds at `ear_size = -1` (MPFB's ear-scale-decr at full).
- **Lips, nostrils and the mouth interior:** `chin-prognathism` is left out of `jaw_heavy` because on a
  closed mouth it drives the lower lip through the upper (16 faces at 0.35). `intersections` would report any
  new feature that does the same.
