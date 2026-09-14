# Fins and swimming

How `rig-anything` finds fins on a skin, rigs a fish from a bare mesh, and swims
any body with a spine - a fish side to side, a whale up and down - from its
length. Modules: `fins` (recognition, rays, weights, posing) and `swim`
(numbers, clips, checks). Requires rig-anything 0.11.0.

```python
from rig_analysis import fins, swim
d = fins.detect("FishTest")                   # fins found on the skin
print(fins.summary(d))
fins.build_fish("FishTest", detection=d)      # head, spine, a fan of rays per fin
print(fins.bind("FishTest", "FishTest_rig"))  # bone heat for the body, fins weighted to rays
print(swim.measure_fin_limits("FishTest_rig"))  # how far each fin folds, the body bends, a brake goes
sw = swim.Swimmer("FishTest_rig")             # mode guessed; pass mode= from the renders
print(swim.summarize_plan(swim.plan(sw)))
res = swim.swim_set("FishTest_rig")           # Swim Sprint Glide Hover TurnL TurnR Escape Brake
m = swim.engine_manifest(res)                 # the .moves.json `swim` block

# an existing rig with a body already (the whale): rays only
fins.build_rays("WhaleTest_rig", "WhaleTest"); fins.skin("WhaleTest_rig")
```

Run `fins.detect` on swimmers. A dragon's wings are left to `wings` and its jaw
skin to `maw`, but a thin tail tip still reads as a small caudal fin.

## A fin is skin that is a sheet

Thickness per vertex: a ray inward along the normal crosses the body where the
skin is body and a few millimetres where it is fin - the Shape Diameter Function
(Shapira et al. 2008). The fin/body threshold is Otsu's split of log thickness,
not a constant.

| Step | Why |
|---|---|
| **rim growth** along the sheet's own normal | a vertex on a fin's edge has its normal IN the sheet, so its inward ray runs the fin's length and reads as body. Missed, the test fish's spine ran into its tail fin and its fin edges stayed on the spine and folded |
| ...never into the body's cross-section | unguarded, growth crept across the belly and joined both pelvic fins to the anal fin |
| **body = largest connected non-fin skin** | leftover rim vertices are cut off from the body by fin; counted, they carried the core's end into the tail |
| **base = fin skin touching body skin** | any non-fin neighbour counted, and a lobe's rim made the tail fin's base run round its outline - its rays stood along the edge |
| loose parts, wing and maw skin, tiny sheets, median sheets at the snout | a tongue is thin, lips are thin, a snout tip is thin |

Classification, by base and sheet normal: **caudal** (median, rear of the core),
**flukes** (a horizontal caudal - the body then swims up and down), **dorsal**
(median, above the axis), **anal** / **keel** (median, below, behind / in front
of mid-body), **pectoral** (the frontmost pair), **pelvic** (behind, below).

| Mesh | Found |
|---|---|
| FishTest, 1.1 m, no rig | caudal, dorsal, anal, pectoral L/R, pelvic L/R; the snout tip rejected |
| WhaleTest, 15 m, rigged | flukes, pectoral L/R (flippers); lips rejected |
| DragonTest | wings and jaw left out; a 13 cm tail tip reads as caudal |

## Rays

Each fin gets a fan of ray bones - the lepidotrichia a real fin folds and spreads
on (two bony halves sliding past each other; UMich). A short base (caudal,
pectoral) fans rays by angle from its centre; a long base (dorsal) stands them
along it. Rays are tagged `fin_role` and kept out of the body map's spine.

Weights: the body is bound by bone heat with the rays held out (a centimetre-
thick sheet is where bone heat is least reliable), then each fin vertex is shared
between **the two rays either side of it**, by angle or by position along the
base, fading in from the base over 30% of the fin. The two *nearest* rays
flipped between neighbours and the pectoral membrane stretched 10x.

## Posing

Fin state, like a wing's: `fold` (1 = as folded as the skin allows), `fan`,
`stroke` (out of the sheet; + away from the body), `cup` (outer rays lead - the
caudal cupping), `twist`.

The body is laid along a travelling wave:

    y(z, t) = A(z) L sin(2 pi (z / lambda - f t))

| Mode | Envelope A(z), body lengths | Wavelength | Source |
|---|---|---|---|
| anguilliform | 0.1 e^(z-1) | 0.64 L | Tytell & Lauder 2004 |
| subcarangiform | mean of the two | 0.80 L | interpolated |
| carangiform | 0.02 - 0.08 z + 0.16 z^2 | 0.95 L | Videler & Hess 1984 via Borazjani & Sotiropoulos 2010 |
| thunniform | 0.012 + 0.088 z^5 (design) | 1.25 L | Donley & Dickson 2000 |
| cetacean, **up and down** | 0.015 + 0.085 z^3 (design) | 1.0 L | fluke p-p 0.15-0.25 L, Rohr & Fish 2004 |

Rigid segments along that curve, anchored a third of the way back, with the
body's mass-weighted recoil removed. A turn's C-bend is laid into the **same
rotation per segment** - built as two whole poses and multiplied, the whale's
joints came apart and Blender's playback missed the prediction by 9.5 cm. The
tail fin is turned so its tip lands on the envelope, solved on the wave alone
and held within 45 degrees of the peduncle - against a bend it counter-rotated
80 degrees and folded 96 faces.

## Numbers from length

| Quantity | Rule | Source |
|---|---|---|
| stride | 0.7 L per tail beat, constant with speed | Videler; Wardle (0.6-0.8) |
| tail-beat frequency | speed / stride | follows from the stride; Bainbridge 1958 |
| critical speed | 3.22 (L/0.15)^-0.5 L/s | bull trout, 3.22 L/s at 15 cm, 2.05 at 37 cm (USGS) - a fit |
| cruise | half the critical speed | design |
| burst | 25 (L/0.1)^-0.8 L/s | Wardle 1975: 25 L/s at 0.1 m, ~4 at 1 m - a fit |
| whale cruise | 2 m/s at any size | Gough et al. 2019 |
| whale critical / burst | 1.5x / 3x cruise | design |
| Strouhal | f 2A / U = 0.29 for every mode | inside 0.2-0.4 (Taylor et al. 2003) |
| pectoral sculling | 2.79 Hz x (m / 0.1 kg)^-0.12 | bluegill; mass exponent Drucker & Jensen 1996; 0.1 kg assumed |
| turning radius | 0.06-0.1 L flexible, 0.47 L tuna, 0.3 L whale (design) | JEB 2000 |
| C-start stage 1 | 30 ms, head turns 70 degrees | 15-40 ms, 30-100 degrees (Domenici & Blake) |
| coast | 60% of a kick-and-glide cycle | bluegill kick 0.11 s, glide 0.16 s (JEB 2009) |
| median fins | erect below ~1 L/s, folding toward 2.5 L/s | bluegill; tuna fold at speed (JEB 2005; Pavlov 2017) |
| caudal fin in a glide | 70% of its spread | bluegill 6.4 -> 4.5 cm (JEB 2009) |
| hover stroke | abduction 60% of it | wrasse (Walker & Westneat 1997); faster adduction (Hove 2001) |

## The skin sets the limits

`measure_fin_limits` bisects predicted poses for no face turned inside out and
no edge past 3x, and stores: each fin's clean fold, the widest C-bend either way,
and how far the whole braking pose goes. Measured one fin at a time the brake's
parts each passed and together folded 3 faces, so the brake is measured whole.

| | FishTest | WhaleTest |
|---|---|---|
| fold | pectorals 0.66 / 0.74, pelvics 0.86 / 0.82, dorsal 0.50, anal 0.54 | flippers 0.82 / 0.84 |
| C-bend | 150 | 150 |
| brake | 0.90 | 0.83 |

## Clips

| Clip | Built as | Engine |
|---|---|---|
| `Swim` | loop, one beat at cruise | `speed / (stride_m * clip_beat_hz.Swim)` |
| `Sprint` | loop, one beat at burst (>= 12 frames) | same, `.Sprint` |
| `Glide` | loop, wave at 8%, fins folded, tail at 70% | x1 |
| `Hover` | loop, one pectoral stroke, body still | `hover.playback_speed_scale` |
| `TurnL` / `TurnR` | a cruise beat bent into the turn and out | turn by `turn.<role>.turn_deg` over it |
| `Escape` | C-bend, counter-bend, a burst beat | `escape.playback_speed_scale` (stage 1 is under a frame at 24 fps) |
| `Brake` | pectorals and pelvics out, tail flared, held | - |

A cetacean gets Swim, Sprint, Glide and the turns.

Checks on Blender's playback: prediction, loop seam, **tail sweep against the
envelope at the tip of the ray reaching furthest back** (the middle ray of a
forked tail ends in the notch), **the wave travels tailward** (Fourier phase along
the body - a standing wave swims nowhere, a headward one swims backward), skin
stretch and folded faces (slivers excluded), paired fins clear of the body.

## Results

FishTest: all 8 pass - tail 0.202 m peak to peak against 0.216 planned, measured
wavelength 0.79 L, stretch <= 1.72x, no folds; cruise 0.65 m/s at 0.85 Hz, burst
4.07 m/s at 5.31 Hz, St 0.29. WhaleTest: all 5 pass - flukes 3.18 m (a humpback's
2.63 m), 0.19 Hz (baleen whales 0.1-1 Hz, mean 0.23); its 4 maw clips re-authored
and passing.

In Godot (`swim_demo.tscn -- --selftest`, 13 checks): the fish cruises at 0.65
m/s beating 0.85 Hz and sprints at 4.07 m/s beating 5.31 Hz; **its tail sweeps
0.202 m on Godot's skeleton against Blender's 0.2024**; it glides, hovers, turns
with the turn clip, brakes inside a body length and escapes. The whale cruises at
2.00 m/s beating 0.19 Hz, flukes sweeping 3.06 m against 3.18, and turns.

## Engine

`swim` block: `mode`, `plane`, `length_m`, `mass_kg`, `stride_m`,
`tail_amplitude_m`, `wavelength_body_lengths`, `ucrit_mps`, `cruise_speed_mps`,
`burst_speed_mps`, `tailbeat_cruise_hz`, `tailbeat_burst_hz`, `strouhal`,
`slip_ratio`, `pectoral_hz`, `turn_radius_m`, `coast_share`, `clips`, `loops`,
`clip_beat_hz`, `tail_pp_m`, `hover`, `turn`, `escape`. `fins` lists each fin's
kind, side, parent, rays and ray lengths.

GrungistCreek: `swim_controller.gd` swims any manifest with a `swim` block -
steering at the turning radius, Swim or Sprint by speed at the beat the stride
implies, Glide when let go, Hover once slow, Brake and Escape on command.
`swim_demo.tscn` has both; `maw_demo.tscn`'s whale now swims on these clips.

## Not done

- Rajiform / mobuliform rays (fin waves), labriform pectoral flight at speed,
  eel-like bodies beyond the envelope, a manta's 0.31 Hz flap.
- Rays are one bone each; real rays curl (2-3 segments would).
- Dorsal and anal fins do not undulate for balistiform or amiiform swimming.
- Buoyancy, pitch trim and burst-and-coast timing are the engine's, not clips.
- A thin non-fin sheet on a swimmer (a crest, a frill) would read as a fin.
