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

Presets: `ears_pointed`, `ear_size`, `ears_large`, `brow_ridge`, `nose_size`, `jaw_heavy`, `cheek_gaunt`,
`tusks`, `horn_nubs`, `horns`, `ram_horns`.

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
