# Tentacles and the octopus

How `rig-anything` rigs arms with no skeleton in them and makes an octopus crawl,
turn, reach, swim and jet. Modules: `tentacles` (recognition, rig, weights, arm
posing) and `octopus` (numbers, clips, checks, manifest). Unreleased - not yet in
`reload_all`; import with `importlib.import_module("rig_analysis.tentacles")`.

```python
tn = importlib.import_module("rig_analysis.tentacles")
oc = importlib.import_module("rig_analysis.octopus")
tn.make_test_octopus("OctoTest")          # O. vulgaris proportions, one closed skin
d = tn.detect("OctoTest"); print(tn.summary(d))
tn.build("OctoTest", detection=d)         # body, head, mantle, funnel, 12 bones per arm
print(tn.skin("OctoTest_rig"))            # weights from centrelines, not bone heat
res = oc.octopus_set("OctoTest_rig")      # 12 clips, each checked on Blender's playback
m = oc.engine_manifest("OctoTest_rig", res)
```

## An arm is a chain that can get longer

Octopus arms bend anywhere and elongate 66% on average, 80% at most (arm L2), and
stretch past 2x passively (JEMBE 2013). So arm bones are **not connected**: a bone's
head may leave its parent's tail, and keyed positions carry the elongation. A pose
is joint positions turned into matrices by parallel transport from the body
(`Tentacles.chain`) - no roll, no sign, no flips. Nothing uses constraints; glTF
cannot carry them.

`detect` clusters the far skin by azimuth about the hub, walks shells of distance
from the tip inward for a centreline and radius, and names arms L1-L4 / R1-R4 from
the front (pairs I-IV from the dorsal midline). The head and mantle are the skin
no arm claims. DML (eyes to apex) puts the eyes a head radius below the neck: a
smooth skin shows no eye bulge a slice can find. Override with `Octopus(dml_m=)`.

`skin` scores every vertex against each arm and the body by distance over local
radius, shares it by soft minimum, splits along the arm by a tent over bone
midpoints, and **smooths the weights over the surface**.

| Found on OctoTest | Fix |
|---|---|
| 1 cm web: its two faces scored differently, the underside turned over at every arm base once arms moved out of phase | 6 iterations of surface smoothing |
| the oral disc belonged to `body`, stayed flat while arm bases turned back to jet: 680 folds | body radius narrows to the mouth; arms own the crown |

## Clips

| Clip | Built as | Source |
|---|---|---|
| `Idle` | ventilation, tips sway and lift | 0.4 Hz UNVERIFIED |
| `CrawlF/B/L/R` | push by elongation: grips planted 55% out, sweeping back at the crawl speed; six of eight down, pairs {L1,R3} {R2,L4} {R1,L3} {L2,R4} | Levy, Flash & Hochner 2015; 1.54 DML/s, Huffard 2006 |
| `TurnL/R` | same schedule, grips sweep round the hub | rate = crawl speed / grip radius (design) |
| `Swim` | all arms open slow, close fast (2:1), lagging down the arm; mantle first | Sfakiotakis / Kazakidi; 1.27 BL/s |
| `Jet` | arms straight and together, mantle squeezes 25% (1/3 of the cycle) | "fully stretched, arms held tightly together", 1.73 BL/s, Huffard 2006; 1.4 Hz from cuttlefish, UNVERIFIED |
| `Glide` | jet shape coasting | - |
| `Launch` | push-off hop, turns mantle first, arms follow tips last; backwards lands | design |
| `Reach` | a bend travels base to tip on minimum jerk; straight behind, curled beyond | Gutfreund 1996; Yekutieli 2005 |

BL / DML = 2.48, from Huffard's mean crawl quoted both ways. A 0.18 m DML is far
bigger than A. aculeatus: the speeds are extrapolated.

A crawl is a DIRECTION: body orientation is controlled apart from travel (Levy
2015). Real arm choice is not rhythmic; a loop has to be.

## What went wrong first

| Symptom | Cause | Now |
|---|---|---|
| web folded at every arm base in a crawl | Hermite span from base to grip re-spaced the base joints | rest shape displaced toward the grip, `(j/k)^2` |
| web between two side arms wrinkled | grip at 40%, inside the web | grip at 55%, past it |
| jet folded ~800 faces at the crown | each arm turned 70 deg at its first joint | arms leave at their rest angle, turn over 10% of length |
| launch and reach shortened segments to 0.1x | joints lerped between two shapes | `blend_shapes`: slerp segment directions, keep lengths |
| launch tore the crown (5.9x) | shapes blended in the world while the body turned over | blended in the body's frame, carried |
| reach tip folded | 80 deg per joint in a tight coil | curl no tighter than ~40 deg a segment |
| turning the body in Godot dragged suckers | the engine rotated planted arms | `TurnL/R` clips |

A closing umbrella must pleat: faces turned over in skin that is neither arm nor
body are reported as `web_pleats` (26 at most, in Jet), not failed.

## Checks

On Blender's playback: prediction (1e-6 m on every clip), loop seam, skin stretch
(99.9th percentile edge), folded faces outside the web, skin under the floor,
segment length against 0.45-1.80x, **planted suckers moving exactly as the grip
does** (crawl 1e-5 m/s, turn 0.006 m/s), measured crawl speed and turn rate,
reach bend travelling outward and tip speed peaking mid-reach.

OctoTest: all 12 pass. Crawl 0.2777 m/s measured against 0.2777 planned in all
four directions; turn 0.6362 against 0.6363 rad/s.

## Engine

`octopus` block: DML, BL, arm length, mass, speeds, jet (hz, squeeze, range),
`crawl` (directions in Godot axes, grip travel, anchor joint, playback scale),
`turn`, `swim`, `idle`, `launch`, `reach`, arms and their bones, sockets.

GrungistCreek: `octopus_controller.gd` - a BlendSpace2D of the crawl clips
weighted to sum to one (full speed on an axis, 0.71 on a diagonal), turn clips on
the spot, jet for `range_m` then swim. `octopus_demo.tscn -- --selftest`: 15
checks on Godot's skeleton, including six of eight suckers planted while crawling
and turning, mantle squeeze 25% at 1.32 Hz, reach within 10% of Blender's.

## Not done

- Bipedal walking on arms IV (1.34 BL/s, Huffard 2005/2006), fetching with a
  three-segment arm (Sumbre 2005), grabbing on real terrain at runtime.
- Suckers, colour and skin texture change; the funnel is a socket, not skin.
- Crawl grips are baked on a flat floor - a runtime SkeletonModifier3D would
  plant them on terrain.
- Turning while crawling has no clip: the engine turns at half rate and suckers slip.
- Arm choice is a fixed loop; octopuses choose arms moment to moment.
