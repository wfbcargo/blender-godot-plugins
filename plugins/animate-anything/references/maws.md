# Maws

How `rig-anything` finds a mouth on any skin, gives it a jaw, splits the skin
between head and jaw without tearing it, and opens it - a dragon breathing
fire, a whale engulfing a boat. Module: `maw`. Requires rig-anything 0.10.0.

```python
from rig_analysis import maw, bodymap
d = maw.detect("DragonTest_rig", kind="reptile")   # mouth found on the skin
print(maw.summarize_detection(d))
maw.build("DragonTest_rig", detection=d)           # jaw, throat, gular, tongue*, mouth socket
print(maw.skin("DragonTest_rig"))                  # weights split, relaxed, gape limit measured
res = maw.maw_set("DragonTest_rig")                # Gape Bite Roar Breath BreathStart BreathEnd Swallow
m = maw.engine_manifest(res, "DragonTest_rig")     # the .moves.json `maw` block
```

`kind` comes from looking at the creature, like an archetype: `reptile`
(dragons, theropods), `crocodilian`, `mammal`, `rorqual`, `anglerfish`.
Geometry cannot tell a whale's jaw from a dragon's.

## A mouth is a cavity entering the head

Rays cast up through the head at stations along it cross the skin twice where
the head is shut and four times where the mouth is; the gap is the mouth there,
and the rearmost station with one is the corner. Loose parts are set aside
first - a ray that clips a tooth sees a false wall.

| Finds | How |
|---|---|
| lip line | gap midpoints in front of the corner; a straight fit behind it |
| corner, width | rearmost gap station; rays across from the midline |
| lip tips | frontmost skin above / below the lip line |
| tongue | a loose part inside the cavity, along the mouth floor, longer than 30% of the mouth |
| rigid parts | every other loose part: teeth, baleen, horns |
| bridges | a column through the mouth with no gap while its neighbours have one: fused lips |

A head with no cavity is refused - there is nothing to open. Model a mouth, even
shut with separate lips. **Bridges are warned about, not fixed:** the first test
dragon's jaws came within two voxels and the remesh fused a pillar through the
mouth; at full gape the skin across it ran to 24x.

## Bones

| Bone | Parent | Deforms | Why |
|---|---|---|---|
| `jaw` | head | yes | hinge -> chin |
| `throat` | head | yes | pouch skin behind the hinge, moved down to swell |
| `gular` | jaw | yes | pouch skin under the jaw - a rorqual's pleats start at the chin |
| `tongue`* | jaw | yes | chain along a tongue part, when there is one |
| `mouth` | head | **no** | the engine socket, +Y along the bisector of the open jaws |

Hinge placement: 75-90% of head length back from the snout (the standard
ear-lobe placement in side view), never in front of the corner, slightly below
the lip line. The whale's sits 0.35 of the head depth below it: at the lip line,
skin a metre under the joint swung back into the chest as the jaw dropped.

`bodymap` leaves maw bones out of the axial chain and limbs - otherwise the jaw
is the far end of the spine and reads as the head. The measurements are stored
on the armature (`rig_anything_maw`); `bodymap` reports them as `maw`.

## Skinning: the head claims its mouth, then shares it

1. **Claim.** In front of the corner every bone's share of the skin moves to the
   head, fading out toward the hinge. Bone heat gave the whale's lower-jaw flanks
   a quarter of their weight from the chest, 1-2 m in front of the hinge; left
   there, 124 faces turned inside out.
2. **Label by the mesh, not by height.** Vertices well clear of the lip line are
   upper or lower by height; the rest take the label of the nearest seed along
   the surface, so an overhanging upper lip stays upper (research: some upper-lip
   vertices sit lower than lower-lip ones).
3. **Split.** Hard along the lips; at the corner 50/50 (Kangaroo, Ferrachat);
   a web widening toward the hinge; nothing behind it.
4. **Relax.** Between the pinned regions the jaw's share is smoothed with each
   edge weighted by its squared distance from the hinge. An edge's stretch is
   its change in share times the arc of the jaw there, so this spends the change
   where the arc is short. Tapers alone left a 0.17 step over 8 cm of the whale's
   lip; at 80 degrees that edge ran to 4.8x.
5. **Pouch.** The throat takes ventral skin along its span, divided between
   `gular` and `throat` on the same relaxed field - a separate blend about the
   hinge put 35% jaw rotation into skin under the joint.
6. **Loose parts.** Rigid on the bone that dominates the skin they sit on; a
   tongue along its own chain.

Original weights are kept in a text block (`rig_anything_maw_weights:<mesh>`) and
restored before every re-skin, so settings can be tried; `unbuild` restores them.

## The skin sets the gape

`skin` ends with `measure_limit`: the widest opening, by bisection on predicted
poses, with no face turned inside out and no edge past the kind's stretch limit.
`gape = 1` means the kind's maximum or that, whichever is smaller - the way a
crouch is limited by skin, not just reach.

| | kind max | skin allows | at the kind max |
|---|---|---|---|
| DragonTest (reptile) | 80 | **80** | stretch 2.34x, no folds |
| WhaleTest (rorqual) | 80 | **47** | 21 faces fold |

**Slivers are not faces.** A face whose area is under a tenth of its longest edge
squared - a decimated mesh is full of them - has no normal worth trusting; one
flipped at 40 degrees on the whale and first capped its gape at 15.

## Numbers and sources

| Quantity | Value | Source |
|---|---|---|
| theropod max gape | T. rex 70.5-80, Allosaurus 79-92 | Lautenschlager 2015, PMC4680622 |
| alligator | 43.5-49.5 | same |
| lion | ~65 (popular figures to 90, conflicting) | Britannica, summary |
| rorqual jaw drop | 78-80, jaws also roll outward | PMC8179629; Shadwick 2017 |
| rorqual pleats | ~162% around the body, tissue past 4x sideways | JEB 2013 216:2691 |
| snout lift | 4.1 degrees, adds 8.7% of gape, peaks with the jaw | gecko, PMC4521707 |
| muscle limit | 170% resting length sets max gape | Lautenschlager 2015 |
| bite cycle | 0.21-0.23 s, juvenile alligator | PMC5192416 |
| engulfment | 1.2 s at 8 m, 5.7 s at 22 m, 6.6 s at 27 m | PMC8179629; Goldbogen 2006 |
| purge | 27.5-61.9 s | same |
| fire breath | clear inhale before a sharp exhale; charge-up sells the blast | The Rookies; befores & afters (Monster Hunter) |

Derived here, labelled as such:

- **Bite timing** by dynamic similarity: cycle = 2.8 sqrt(mouth length / g). The
  2.8 assumes the juvenile alligator's mouth is ~6 cm.
- **Engulfment** = 0.065 L^1.4 s, a power law through the two ends of the data.
- **Stretch limit** 3.0x (4.0 rorqual). Skin is not muscle: the 170% figure is
  reported as `gape_at_muscle_stretch_deg` - where a real jaw of that shape
  would stop - not failed. A torn corner seam measured 14x; the relaxed dragon
  corner at 80 degrees is 2.3x and renders as a smooth cheek.
- **Fire aim.** Fire leaves along the socket - the jaws' bisector, half the gape
  below the skull. Left there the dragon's blast went 31 degrees into the ground
  two metres out, so the breath clips lift the head until the bisector is 12
  degrees below rest (`breath_pitch`).

## Clips

All pose only `maw.layer_bones` (head, jaw, throat, gular, tongue, mouth); every
other bone stays at the ground rest, legs planted, wings folded.

| Clip | Built as | Engine timing |
|---|---|---|
| `Gape` | rest -> full gape, held; play backwards to close | - |
| `Bite` | slow open (0.7) -> snap shut, head dipping -> settle; one size-scaled cycle, >= 12 frames | `open_s`, `contact_s` (first closing frame <= 15 deg), `end_s` |
| `Roar` | head back, jaws 0.95, throat pulsing, close | `peak_s` |
| `BreathStart` | inhale (throat 0.85, head back, jaws parted) -> exhale into Breath frame 1 | `fire_start_s` (jaws past half their opening) |
| `Breath` | loop: jaws 0.75, head aimed, throat working | - |
| `BreathEnd` | Breath frame 1 -> rest | - |
| `Swallow` | jaws shut, tongue up, throat bulge | - |
| `Engulf` | open to 1.0 over half the engulfment, throat balloons behind, close on a full pouch | `open_s`, `max_gape_s`, `close_s` |
| `Purge` | Engulf's last frame -> pouch empties through parted jaws; short, played slow | `purge.playback_speed_scale` |

`rorqual` defaults to Gape Engulf Purge Swallow; every other kind to the rest.
Order matters: BreathStart / BreathEnd measure seams against Breath, Purge
against Engulf.

Every clip gets the common checks (prediction vs playback, rest, planted feet,
floor - off for `aquatic`, a swimmer's jaw drops below its belly) plus, on
Blender's evaluated pose every frame:

| Check | Fails at |
|---|---|
| gape played vs asked | 0.5 degrees |
| worst edge stretch | kind limit |
| faces turned inside out (slivers excluded) | any more than rest |
| rigid parts bending | 0.1% |
| socket off the bisector | 0.5 degrees |
| jaw into neck or chest | 0.8 of body radius (or 0.9 of rest) |
| loop / clip seams | as elsewhere |

and reports aperture (m2), mouth volume (a pyramid from the aperture to the
corner - geometry, labelled) and throat volume gain (divergence theorem on the
skin that moves).

## Results

DragonTest: all 7 maw clips pass - gape error 0.0, stretch <= 2.34x, no folds,
socket error 0.0, seams 0.0; the 16 ground and flight clips regenerated on the
new head pass too, and walk / trot / run / crouch-walk speeds export identical to
before (0.5281 / 1.13 / 1.571 / 0.3601 m/s). WhaleTest: 4 clips pass at the
skin's 47 degrees; Engulf swells the pouch 8.9 m3 on top of 2.4 m3 of open mouth.

In Godot (`maw_demo.tscn -- --selftest`), measured from the skeleton after the
layer runs: dragon Breath peak 62.3 degrees (Blender 62.39), Roar 76.4 (76.78),
whale 47.0 (47.03), whale throat drop 1.03 m. Fire burns a post, a bite lands on
the dummy, the walk gait keeps playing under the fire, and the whale swallows
boats.

## Engine

`maw` block: `kind`, `gape_max_deg` (what gape 1 opens to), `gape_kind_max_deg`,
`bones`, `layer_bones`, `mouth_length_m`, `mouth_width_m`, `aperture_max_m2`,
`mouth_volume_m3`, `throat_volume_gain_m3`, `clips`, and `bite` / `breath` /
`roar` / `engulf` / `purge` timings.

GrungistCreek: `maw_layer.gd` (a `SkeletonModifier3D`) samples only the layer
bones' tracks after the AnimationPlayer and fades by `influence`, so maw clips
play over walking and flying. `creature_controller.gd` adds `bite()`, `roar()`,
`breathe(held)`, `bite_active()`, `breathing_fire()` and `mouth` (a
BoneAttachment3D on the socket); `fire_breath.gd` is a cone along the socket.

## Found on the way

- **Loose parts block bone heat.** Teeth as islands made both test meshes
  unbindable. Bind the body, join the parts, let `maw.skin` weight them.
- **`verify.check_clip` crashed on a body with no feet.** A whale or worm export
  raised on an empty `foot_bones`; it now tracks every bone for the seam and
  reports no stride.
- **A rebuild measured its own split.** `build` re-detected on skin already
  divided, and found the chin at the corner. It restores the bound weights first,
  and detection counts maw bones as head.
- **`views.render_clip(focus_bones=...)`** frames only the skin those bones hold -
  a jaw is a few pixels in a whole-dragon shot.

## Not done

- Split mandibles: rorqual jaws rolling outward, a snake's unfused chin and
  quadrate double hinge (130+ degrees). One midline hinge covers neither.
- Lip and cheek bones, lip roll, sticky lips / zipper.
- Rigid parts near the corner float slightly as the web around them stretches
  (the whale's rear baleen plate).
- A whale swim gait: `gait.undulate` is lateral; the demo's up-and-down fluke loop
  is authored in the test scene script, not the plugin.
- Hinge + slide is implemented for `mammal` but untested on a mammal mesh.
