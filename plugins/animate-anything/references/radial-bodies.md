# Radial bodies

How `rig-anything` recognises a body with no front or back - a jellyfish, a sea
star, a brittle star, an anemone - rigs it from a bare mesh, weights it without
bone heat, and moves it by the rules the animal uses. Modules: `radial`
(recognition, rig, weights, pose maths), `radial_moves` (numbers, clips, checks,
manifest, export) and `radial_samples` (procedural test bodies). Requires
rig-anything 0.12.0.

```python
from rig_analysis import measure, radial, radial_moves as rm
print(measure.rotational_symmetry(bpy.data.objects["JellyTest"]))   # 4-fold about Z
d = radial.detect("JellyTest")               # kind= medusa | polyp | asteroid | ophiuroid, from the renders
print(radial.summary(d))                     # hub, each appendage, its angle, root and direction
radial.build("JellyTest", detection=d)       # hub, bell ribs, a chain per appendage
print(radial.skin("JellyTest_rig"))          # weights written from the parts - coverage 1.0
p = rm.plan(radial.RadialRig("JellyTest_rig")); print(rm.summarize_plan(p))
res = rm.move_set("JellyTest_rig")           # Pulse Drift Turn | Crawl Idle | Row RowBack Idle | Sway Retract Extend
rm.export_creature("JellyTest", "JellyTest_rig", res, ".../jellyfish.glb", "jellyfish")   # glb + .moves.json
```

## Recognition: an axis the body turns onto itself about

A bilateral body has one mirror plane and `symmetry` names it. A radial body has
as many mirror planes as arms, so that test scores two axes alike and settles
nothing. `measure.rotational_symmetry` asks the right question instead: turn
every point by 360/k degrees about a candidate axis and measure how far it lands
from the skin. The ORDER is the largest k that passes; a body of revolution
passes every k and reads `continuous`. `measure.analyze` now carries it, and
`report.summarize` prints a BODY PLAN line - and a radial body's forward is
reported as none, since any choice would be arbitrary.

| Mesh | Order | Score | |
|---|---|---|---|
| JellyTest - 8 tentacles, 4 oral arms | 4 | 0.97 | tetraradial, like Aurelia |
| StarTest | 5 | 0.79 | |
| BrittleTest | 5 | 0.80 | |
| AnemoneTest | 10 | 0.72 | |
| FishTest, QuadTest, HexTest, BirdTest, DragonTest, WhaleTest, humanoid, rat | none | best 0.32 (whale) | pass mark 0.6 |

Three things the first version got wrong:

| Symptom | Cause | Rule now |
|---|---|---|
| a five-armed starfish scored no symmetry at all | the axis ran through the bounding box's centre; a box is centred on a body of even order only - one arm up, two down puts it 6 mm off | centre = the skin's area-weighted centroid |
| a 15 degree turn about a whale's long axis scored 0.51 | a small turn about a slender body moves nothing far, so it passes on size | points must also land far closer than the turn moved them |
| the tetraradial jellyfish read 8-fold | its oral arms are a small share of the skin; a 45 degree turn scored 0.72 against 0.90 for 90 | the order is the largest k scoring within 85% of the best |

## Recognition: hub and appendages on the skin

Geodesic distance from the hub's centre, in bands. Near the centre every band is
a ring round the axis; where an arm leaves, the band breaks into pieces, each in
the arm's own sliver of angle. Pieces that wrap the axis are HUB; linked band to
band, the rest are APPENDAGE chains. The seed is the vertex minimising its
largest distance to the appendage tips, found by farthest-point sampling and
kept only when they lie out from the axis.

| Found | How |
|---|---|
| hub | pieces wrapping the axis, or touching it - judged per ring, see below |
| appendage | a connected run of non-hub pieces that reaches the hub and ENDS - its tip is a local geodesic maximum |
| loose appendage | a separate loose part, elongated (PCA ratio > 3), rooted at the nearest body skin - a modelled jellyfish's tentacles |
| rigid part | a compact loose part (an eye, a gonad): copies the weights of the skin under it |
| oral side | where the appendages point; lying in the plane, the floor side - a sea star's mouth is underneath |
| kind | appendages in the plane: `ophiuroid` if slender (width < 0.12 length) on a small disc, else `asteroid`; pointing oral: `polyp` if the hub's fineness >= 0.8, else `medusa` |
| role | medusa: `tentacle` rooted past 55% of the hub radius, else `oral_arm`; polyp `tentacle`; stars `arm`. Numbered from the one nearest forward |

| Mesh | Found |
|---|---|
| JellyTest (loose parts) | medusa, fineness 0.39; 8 tentacles at 45 degree steps, 4 oral arms between them |
| StarTest | asteroid, 5 arms |
| BrittleTest | ophiuroid, 5 arms |
| AnemoneTest | polyp, 10 tentacles pointing oral (up) |

Two more the first version got wrong, both on the anemone:

- **A ring cut into arcs is still body.** The geodesic front runs further over
  each tentacle's root than between them, so it comes down the column in a
  ten-fold wave and each band cut the column into arcs - eight read as arms. Pieces
  of one band at the same radius and height are now judged together by the share
  of the circle they OCCUPY (72 bins, 55%): column arcs fill nearly all, ten
  tentacles a third, thirty-two thin ones a sixth. Not coverage - thirty-two
  tentacles leave no gap wider than 11 degrees.
- **Webbing is not a branch.** Two tentacles fused at the crown came out as one
  appendage with two tips; the second one's skin projected onto the first's bones
  and stretched 11x when they curled. A fork whose shared trunk is under 30% of
  its branches is split: each tip its own appendage, the stub body. A long trunk
  (a basket star) is kept as one arm with a warning.

## Rigging without bone heat

| Bone | Where |
|---|---|
| `hub` | on the axis at the hub's mid-height, pointing aboral; the root |
| `ribNN_1..3` | medusa only: down the bell's mid-shell meridian from 25% of the radius to the margin, one per symmetry sector (order if >= 6, else 2x; matched to the tentacle count when that divides) |
| `<role>NN_k` | along each appendage's band centroids, resampled to length / 1.2 widths bones (tentacles <= 12, oral arms <= 6, arms <= 8); tentacles hang from the nearest rib's tip, oral arms and star arms from the hub |

No `.L`/`.R`: nothing has a side. Every bone is tagged `radial_role`, and
`bodymap.build` leaves those bones out (as it does fin rays, and the octopus
`tentacle` chains); a rig that is only radial gets an error pointing here.

`radial.skin` writes weights directly, because every vertex already knows what
it belongs to and where along it:

- **bell and hub** - between the two ribs either side by angle, along them by
  radius, fading to the hub toward the apex;
- **appendage** - between the two bones either side of its projection on the
  chain, and at the root the weights the hub rule gives at the attachment point,
  so the junction is continuous;
- **rigid loose part** - the weights of the nearest body vertex.

Coverage is 1.0 by construction. Bone heat is not used: a bell is a thin shell
and a tentacle a loose tube, exactly where it fails or skips.

| Rig | Bones |
|---|---|
| JellyTest | 145 (hub, 8 ribs x 3, 8 tentacles x 12, 4 oral arms x 6) |
| StarTest | 20 |
| BrittleTest | 41 |
| AnemoneTest | 48 |

## Posing

`radial.RadialRig` takes rotations in the armature's REST frame about each bone's
head and carries them down the chain by forward kinematics, about two axes that
exist on every radial body:

- `q(theta) = radial x aboral` - + turns a radial bone toward aboral and an
  oral-pointing one outward: lift, splay, closing a bell;
- `a`, the symmetry axis - + sweeps round the body.

A bell's closing direction is probed once, not assumed; the rib bend that pulls
the margin in by a fraction is solved by bisection.

## Numbers

| Quantity | Rule | Source |
|---|---|---|
| swimmer class | fineness h/D < 0.5 rowing, < 0.9 jet-paddling, else jetting | Colin & Costello 2002 |
| pulse rate | 0.41 (D / 0.1 m)^-0.62 Hz | fit through Aurelia ephyrae (0.3 cm, 3.8 Hz), a 6 cm semaeostome (0.6 Hz), adult Aurelia (13 cm, 0.24 Hz), Cyanea (50 cm, 0.19 Hz) |
| contraction share | 37% rowing (32-42%), 34% jet-paddling, 35% jetting | review in Gemmell et al.; Catostylus 0.34 |
| coast | 15% of a rowing cycle, held closed | Cyanea: 2.0 s contract, 1.0 s coast, 2.4 s relax (one video) |
| margin in by | 18% rowing, 23% jet-paddling, 25% jetting (design) | Aurelia ~12% from its 1.3x area change; Catostylus 23% |
| distance a pulse | 0.42 D rowing, 0.47 D jet-paddling, 1.0 D jetting (design) | 6 cm semaeostome 1.5 cm/s at 0.6 Hz; Catostylus; Sarsia is reported near 2 D |
| surge | 51% of the distance while closing, 37% relaxing, 11% coasting | Catostylus |
| turn | 41 degrees a lopsided pulse | Aurelia model (one study) |
| sinking, fast pulse | 0.05 D/s; 2x the rate | design |
| sea star crawl | 1.0 mm/s, any heading, no leading arm | Asterias rubens 0.98 glass / 1.12 slate (bioRxiv 2025); Heydari et al. 2020 |
| sea star bounce | 0.27 Hz x (m / 50 g)^-0.14 | 0.14-0.40 Hz, ~mass^-0.14 over 54 animals (Heydari 2021); the 50 g anchor is assumed |
| brittle star stroke | 0.5 Hz; one arm leads, the pair beside it rows; 25% reversed | Astley 2012, Ophiocoma echinata |
| brittle star heading error | at most 180 / 2n degrees | picking the nearest arm forward or reversed; Wakita et al. measure +-29 degrees for five arms |
| anemone sway, retract | 4 s, 1.2 s | design |

## What "forward" means, and what the engine does with it

| Kind | Travels | Steers |
|---|---|---|
| medusa | along its axis, ABORAL END FIRST | tilts the axis by a lopsided pulse; `Turn` is authored closing harder toward rib 01, and the body is spun about its axis by a whole multiple of 360/order - invisible - to put that side toward the turn |
| asteroid | any direction, body unturned | does not: the heading is broadcast to the feet |
| ophiuroid | behind the arm nearest the heading | hands the lead to another arm: the body spins only by whole multiples of 360/order, and `Row` or `RowBack` is picked, whichever arm is nearer |
| polyp | nowhere | - |

Snapping spins to 360/order is the whole trick: a symmetric body turned by one
sector looks exactly as it did.

## The skin sets the limits

`radial_moves.measure_curl_limit` bisects the anemone's curl for no folded face
and no edge past 3x; `Retract` goes that far. The crown folded two faces at a full
curl; it curls to 0.78.

## Clips and checks

| Clip | Built as | Checked on Blender's playback |
|---|---|---|
| `Pulse` | loop, one pulse | margin closes as planned (15%), lopsided by under 2% of the radius, fully closed at the planned share, tentacles LAG the margin (Fourier phase), tentacle tips stay beyond 25% of their resting radius |
| `Drift` | loop, the bell barely breathing, tentacles swaying | stretch, folds, tentacles apart |
| `Turn` | one pulse closing harder toward rib 01 | the turning side closes more than the far side |
| `Crawl` | loop, one bounce; each arm's root angle SOLVED to keep its tip on the floor | tips off the floor < 25% of the bounce |
| `Row` / `RowBack` | loop, one stroke: rowers sweep back flat, recover lifted | power stroke pushes back, sideways travel < 1.2x back, rowers' tips stay down; stride measured |
| `Idle` | loop, arm tips lifting in turn | stretch, folds, floor |
| `Sway` | loop, a wave round the crown | stretch, folds |
| `Retract` / `Extend` | one-shot, curl to the clean limit and back | every tentacle tip ends closer to the axis |

Every clip also passes the shared checks: Blender's pose against the prediction,
loop seam, skin stretch and folded faces, and - except for a bell, which floats -
nothing through the floor.

Four more found on the way:

- **A tentacle hangs; it is not the rib's extension.** Carried rigidly from the
  rib tip, an 18 degree rib bend swung each 0.43 m tentacle's tip 13 cm inward -
  its whole resting radius - and all eight met under the bell. Every number passed;
  a render found it, and the tip-radius check exists since. The carried bend is now
  undone at the tentacle's root and 15% given back late.
- **Late, not in step.** Undone at 85% in step with the rib, the tips swung in
  ahead of the margin and led the pulse by 8 degrees - the tentacles pulling the
  bell. The give-back uses the lagged contraction; they trail by 13.
- **Rowing from near the heading pushes sideways.** A sweep round the body moves a
  tip along a circle, of which sin(angle from the heading) is backward. Reverse
  rowing's front pair, 36 degrees off, pushed 1.6x as far sideways as back. A rower
  near the heading swings out to 75 degrees first.
- **Solve, do not estimate.** A sea star's arms compensated for the bounce by
  asin(bob / reach) with a fixed counter-bend left their tips 1.2 mm up on a 3.8 mm
  bounce; bisecting each arm's root angle leaves them at 0.

## Results

| Clip | Result |
|---|---|
| JellyTest Pulse | margin 17.9% (plan 18%), asymmetry 0.2%, closed at 37.5% (37%), tentacles lag 13 deg, tips >= 58% of rest radius, stretch 1.14 |
| JellyTest Turn | turning side closes 24.8%, far side 11.4% |
| StarTest Crawl | tips on the floor through a 3.8 mm bounce |
| BrittleTest Row / RowBack | stride 0.075 / 0.071 m, 0.038 / 0.036 m/s, sideways 0.38 / 0.40 of back |
| AnemoneTest Retract | 10 of 10 tentacles in, curl 0.78, stretch 1.65 |

All eleven clips pass; all four exports read back with matching durations.

In Godot (`radial_demo.tscn -- --selftest`, 17 checks): the jellyfish averages
0.0254 m/s over its pulses against 0.0261 planned, pulses at 0.207 Hz, surges,
swims bell first, and **its margin closes 17.7% on Godot's skeleton against
Blender's 17.9%**; it tilts 90 degrees toward a target playing Turn, spinning
only by whole quarter turns, and drifts and sinks when let go. The sea star
crawls at 1.00 mm/s and changes direction without turning. The brittle star rows
at 0.0376 m/s, reverses by switching to RowBack with no spin, and its leading
arm is never more than 12.4 degrees off the heading (cap 18). The anemone sways,
retracts and extends.

## Engine

`radial` block: `kind`, `order`, `heading_quantum_deg`, `axis_aboral_model`,
`reference_model`, `body` (diameter, height, fineness, mass), `appendages` (name,
role, angle, `direction_model`, bones and bone lengths, parent, length, loose),
`ribs`, `plan` (the numbers above), `clips`, `loops`, `playback_speed_scale` per
clip, `measured` (the bell), `turn` (degrees, `toward_model`), `row` (per clip:
`heading_model`, stride, speed), `problems`. Model-space vectors are glTF / Godot:
Y up, Blender -Y forward as +Z.

GrungistCreek: `radial_controller.gd` plays any manifest with a `radial` block;
`radial_demo.tscn` has all four.

## Not done

- **Octopus and squid** are bilateral with a radial ring of arms; the identifier
  reads an eight-armed body as radial, but crawling by arm elongation and jetting
  from a mantle belong to their own module (`tentacles`).
- Comb jellies (ciliary rows), siphonophores and colonial forms.
- Branching arms (basket stars) rig along their longest branch.
- A thin bell with no inner surface: `_rib_profile` takes the middle of the
  shell it finds, which for a one-sided sheet is the sheet.
- Tentacle drag in the engine: clips bake a lagging wave; Godot 4.4+'s
  `SpringBoneSimulator3D` could add trailing on top, one chain per tentacle,
  `center_from` the hub bone. Not wired.
- A sea star's arm-tip lifting to sense, righting, and the brittle star's
  touch-escape (the lead is the touched arm's second neighbour).
