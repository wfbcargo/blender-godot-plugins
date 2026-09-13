# Wings

How `rig-anything` finds a wing on any rig, poses it, and derives flight from
the body's size. Modules: `wings` (recognition and posing) and `flight` (numbers,
clips, checks). Requires rig-anything 0.9.0.

## A wing is a limb in a third role

`bodymap` calls a grounded limb a leg and a free one an arm. A free limb whose
skin is a **sheet** is a wing - role `"wing"` - and nothing that reaches,
counter-swings or balances with arms touches it.

| Evidence | Measured as | Arm | Wing |
|---|---|---|---|
| thickness | smallest / middle principal spread of the skin the limb's bones dominate | tube, ~0.7-1 | 0.11 dragon, 0.18-0.23 bird |
| planform | that skin's faces projected on the sheet plane, halved (a closed sheet counts twice) / reach^2 | ~0.13 | 0.37 dragon, 0.24 bird |
| name | wing, feather, primary, secondary, alula, patagium, pteroid | - | taken at its word |

A wing is `thickness <= 0.35 and planform/reach^2 >= 0.12`, or named. Names are
what let a **bare Rigify bird metarig** (no skin) be read at all; the skin is
what finds a dragon whose bones are called `upperarm.L`.

Kind, from structure:

| Kind | Structure | Folds |
|---|---|---|
| `membrane` | 2+ long chains fanning off the hand (bat, dragon) | Z-fold, fingers collapse into a bundle |
| `feathered` | a hand with one primary chain; feather bones branching off any segment | Z-fold, feathers close along their bone |
| `simple` | no hand segment | one hinge back |

A wing that reaches the ground stays a leg and is reported (a bat or pterosaur
walking on its wrists). A wing modelled folded is reported `rests_folded`; a
negative fold spreads it.

Validated: DragonTest (membrane, by skin, areas 0.746 / 0.753 m2, 3 fingers),
BirdTest (feathered, by name and skin), Rigify `bird` metarig (feathered, by name,
3 feather bones each). Humanoid, Rigify human, quadruped, hexapod (whose small
arm is a tube) and rat are unchanged.

**Feathers are not fingers.** Rigify hangs two `w_feather` bones off the bird's
hand, and counted as fingers they made it a bat.

## Posing: one fold, the avian linkage

No IK - nothing a wing does is a contact. Each wing gets a frame measured from
its rest shape: `o` outward along the span in the sheet plane, `b` backward in
it, `k = o x b`. A positive angle about `k` swings any segment toward the tail
on either side, whatever the bone roll.

Every segment's rest angle in that plane is measured; a pose asks for absolute
angles, and **one number, `fold`, moves them all together**. That is how birds
work: the radius slides along the ulna, so elbow and wrist flex as one (Vazquez
1994; refined to a 6-bar linkage by Stowers, Matloff & Lentink 2017, J. R. Soc.
Interface, doi:10.1098/rsif.2017.0224). Feathers follow wrist and finger angles
through near-linear transfer functions (Chang et al. 2020, Science Robotics,
doi:10.1126/scirobotics.aay1246) - so feathers close by a share of their offset.

Then about the shoulder: `tuck` (a folded wing rolls against the flank, ground
only), `stroke` (+ up), `tilt` (stroke plane; + sends the downstroke forward),
`sweep` (+ tip forward), `twist` (+ leading edge down, 35% at the humerus, 70%
forearm, 100% hand - washout). `fan` opens or closes fingers and feathers.

    wings.state(fold=0, stroke=0, sweep=0, twist=0, fan=1, tilt=0, tuck=0)

A `keyposes.Key` carries it as `wings=` (both sides) or `{"L": ..., "R": ...}`
(banking, roll corrections). A key that says nothing about wings means the
**ground pose, folded and tucked** - so every ground action carries its wings
folded without being told, and `body.ground_rest` is what "frame one is rest"
is measured against.

Folded angles (degrees from outward toward the tail) - no measured table was
found; these give a bird elbow of ~43 and wrist of ~30 degrees included:

| Kind | humerus | forearm | hand | digits |
|---|---|---|---|---|
| feathered | 72 | -65 | 85 | 90 |
| membrane | 70 | -70 | 90 | 95 + 4 per finger |

Rest is reproduced to 6e-8 m, and Blender's playback matches the prediction to
1e-5 m on both test rigs.

## Flight numbers from size

| Quantity | Rule | Source |
|---|---|---|
| wing area S | both planforms + shoulder separation x mean chord | measured |
| span b | shoulder separation + 2 x reach | measured |
| mass | body volume x 850 kg/m3 + wing-skin volume at 25% of that | assumption - override `mass_kg` |
| wingbeat f | 1.08 m^(1/3) g^(1/2) b^-1 S^(-1/4) rho^(-1/3) | Pennycuick 1990, J. exp. Biol. 150:171 |
| cross-check | m^(3/8) g^(1/2) b^(-23/24) S^(-1/3) rho^(-3/8) | Pennycuick 1996, JEB 199:1613 (exponents reconstructed) |
| stroke, peak to peak | 67 b^-0.24 degrees | Nudds, Taylor & Thomas 2004, Proc. R. Soc. B |
| cruise speed | U = f b sin(theta/2) / St, St = 0.21 | Taylor, Nudds & Thomas 2003, Nature 425:707; Nudds 2004 |
| glide speed | sqrt(2 m g / (rho S 0.7)) | C_L from jackdaw best glide 8.3 m/s, Rosen & Hedenstrom 2001 |
| stall speed | same at C_L 1.6 | Harris' hawk, Tucker & Heine 1990 |
| L/D | 4.6 sqrt(AR), clamped 4-20 | a fit through jackdaw 12.6, condor ~12, albatross ~18 |
| downstroke | 55% of the beat | 48-53% hummingbird (Tobalske 2007), ~60% slow flight (Crandell & Tobalske 2015) |
| upstroke span | 75% of the downstroke's, solved on the posed bones | 65% zebra finch, 80% dove, 93% hummingbird |
| legs' share of take-off | 93% at 30 g falling to 25% at 400 g, log-interpolated | Earls 2000; Provini 2012; Berg & Biewener 2010 (pigeon) |

Wing loading above ~250 N/m2 (the heaviest flying birds - not from the sourced
research) is reported as a body that could not really fly. Both test bodies are
past it - DragonTest 94 kg on 1.65 m2 (563 N/m2), BirdTest 14.6 kg on 0.41 m2 -
and the clips are authored anyway, because a game may want the dragon.

**Do not count a modelled wing as body.** A wing sheet is centimetres thick; a
membrane or feather vane is not. The first mass had the 1.9 m test bird at 22 kg.
Wing-skin volume is integrated about the shoulder, which lies on the open cut
where wing meets body, so the missing cap adds nothing.

## Clips

| Clip | Built as | Checked |
|---|---|---|
| `WingSpread` | ground rest -> spread, stroke +20, feet planted; play backwards to fold | feet drift, wing clearance |
| `Flap` | loop, one beat at `f`, never under 12 frames - the engine plays it at `playback_speed_scale` | loop seam, down/up area ratio >= 1.1, measured stroke within 25% of the plan |
| `Glide` | loop, fold 0.05, dihedral 6, a slow counter-rolling drift | >= 85% of spread area |
| `Dive` | loop, fold 0.6, swept back, nose down | area reported |
| `TakeOff` | load (crouch, wings opening) -> leap (heels up, first stroke 1.25x - Berg & Biewener 2010) -> bottom of first beat -> Flap frame 1 | feet planted to the leap, seam to Flap |
| `Land` | Glide frame 1 -> flare (pitched up, wings raised, forward, supinated, legs reaching) -> touchdown (planted, knees giving) -> ground rest | seam from Glide, seam to ground rest, feet planted after touchdown |

Every clip also gets the common checks (prediction vs playback, floor, skin,
reach, fold, bend direction) plus two wing checks on Blender's evaluated pose:

- **clearance** - every wing point past the shoulder stays at least 0.8 of the
  body's radius (80th-percentile skin distance per axial bone) from the axial
  chain. The allowance comes from the **bind pose**, never the ground rest: the
  ground rest is posed by the same fold under test, and measured against itself
  a fold driven into the chest passed.
- **midline** - no wing point crosses to the other side.

Forced failures, all caught: a tuck of 150 degrees (wing at 0.08 of the body
radius), a humerus folded 150 degrees over the back (midline 0.06 m), no
upstroke flex (area ratio 1.00), a 3.4x stroke (floor, skin, midline, amplitude).

Results: DragonTest and BirdTest pass all 16 clips each - the ten ground moves
with wings folded and the six flight clips. Dragon flap: 4.06 Hz, stroke asked 51
measured 49.6, down/up area 1.21, seam 0.0; takeoff and landing seams 0.0.

## Engine

`flight.engine_manifest(reports)` is the `flight` block of `.moves.json`: mass,
span, area, loading, wingbeat, stroke, cruise, glide, stall and sink speeds,
glide ratio, take-off leg share, `flap.playback_speed_scale`,
`takeoff_leap_s` and `land_touchdown_s`.

GrungistCreek's `creature_controller.gd` flies any body that has one: jump then
jump again to flap (hold to climb at 12% of cruise), release to glide - waiting
for the top of the stroke, where the beat passes the Glide pose - crouch to dive,
and a downward ray starts `Land` so its touchdown frame meets the ground. Turns
steer the path at 1.5 g rather than blending velocity, which cut corners and
dropped a 26 m/s dragon under its 24 m/s stall speed.

## Found on the way

- **PASSED with failures listed.** Every action's extra checks - loop seams,
  skating feet, seams, wing clearance - appended failures after `_check_common`
  had written `passed`. `_author_samples` now decides it last.
- **A toeless foot is its own toe.** Unplanted, a foot with no toe bones
  followed the shin and put the dragon's toes 2.5 cm into the floor in its jump
  and slide recoveries. It drapes now - but only in the air: draping a planted
  foot slid a walking bird's toes 1-2 cm. Quadruped, hexapod and rat clips
  regenerate identically.
- **Push off over the toe.** Aimed from hips still low, a leap drove the hind
  feet through the floor; the take-off holds them planted with the heel up.
- **Pitching up lifts the front hips.** A 22 degree flare left a quadruped's
  front feet 102% from the ground; horizontal bodies flare 10.
- **A default argument is frozen at import.** The forced no-flex test first
  "passed" because `UPSTROKE_SPAN` had been bound into the signature.

## Not done

- Hover (horizontal stroke plane, body upright) and insect-style single-bone
  wings, which the body map skips as one-bone chains.
- Tail fan spread with speed (jackdaws furl above 9 m/s).
- Upright winged bodies (an angel) fly pitched 70 degrees but are untested.
- Membrane tension, the bat's plagiopatagiales, would be a shape key, not a bone.
