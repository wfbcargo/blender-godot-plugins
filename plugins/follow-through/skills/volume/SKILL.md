---
name: volume
description: Make soft volumes from Blender move in Godot 4.7 - jello, jelly, pudding, custard, slime, goo, clay, dough, putty, a water balloon, a squishy rubber ball - as a lattice shape-matching body that wobbles, squashes while keeping its volume, and for clay and slime deforms for good. Recognises what the volume is from the type registry, picks a material with physical frequencies (gelatin from its shear modulus), pins a mounted volume to its plate, writes the spec, exports and reads it back, builds the body at runtime, and runs a headless verifier measuring volume kept, penetration, settling and the wobble frequency. Use after follow-through routes a mesh to shape_matching, or directly when a jello, blob, clay ball or balloon needs to wobble, sag, flatten, roll or be poked - or when one sinks through the floor, collapses, jitters or never stops.
---

# volume

The volume library of `follow-through`. Recognition (and the type registry) is in the
`follow-through` skill; concepts in `${CLAUDE_PLUGIN_ROOT}/references/concepts.md`;
research, measurements and sources in `${CLAUDE_PLUGIN_ROOT}/references/volumes.md`.

A volume has an **inside** - that is what separates it from cloth. Godot's Jolt
`SoftBody3D` cannot hold one (4.7.2 builds no bend and no volume constraints: a closed
surface keeps only what pressure gives it), so volumes are simulated by **lattice
shape matching** (Mueller et al. 2005): the mesh is embedded in a few cells a side, each
lattice node pulls toward where its neighbourhood's best rigid fit says it should be,
and the render mesh follows its cell trilinearly.

## Blender

Load as in `follow-through` (reload every time), then:

**1. Prepare.**

```python
r = volume.prepare("Jello")                     # class, type and material recognised
r = volume.prepare("Thing07", type="slime")     # or say what it is
r = volume.prepare("Blob", type="clay_ball", resolution=3, overrides={"frequency_hz": 6})
print(volume.summarize(r))
```

```
Jello: volume / mounted_volume / jello -> shape_matching (confidence 0.75)
  - unskinned: a free body, resting on Plate
  - jello (gelatin) sticks to what it rests on: mounted on Plate
  - type name: jello -> jello
  pins: 49 from base touching Plate
  jello of gelatin: 0.002999 m3, 3.0894 kg
  godot: 4.5 Hz, damping 0.08, squash 0.4, global 0.3, friction 0.6, lattice 4
```

Classes: `loose_volume` (touches nothing, or rests and slides) and `mounted_volume`
(held at its base: pins from what it rests on, or a painted `ft_pin` group, following the
object's node). A type whose material is **sticky** (gelatin, custard) resting on
something is mounted - but only when the type has evidence (a name or a taught example):
a guessed type never changes the class.

Report `GUESSED: type` to the user. With no name and nothing taught, every volume is
guessed `jello`; look at the renders and pass `type=`, then **teach it** (see
`follow-through`) so the next one is recognised.

**2. Materials** (`types/builtin.json`, each with its derivation in `source`):

| material | Hz | damping | squash | global | plastic | used by |
|---|---|---|---|---|---|---|
| gelatin | 4.5 | 0.08 | 0.4 | 0.3 | - | jello |
| custard | 2.2 | 0.35 | 0.6 | 0.3 | 0.1 / 1 per s / 0.2 | pudding |
| slime | 2.5 | 0.9 | 0.9 | 0.3 | 0.02 / 5 per s / 0.6 | slime |
| clay | 8 | 1.0 | 0.6 | 0.3 | 0.03 / 10 per s / 0.5 | clay_ball |
| water_balloon | 3 | 0.25 | 0.8 | 0.5 | - | water_balloon |
| rubber | 10 | 0.1 | 0.2 | 0.5 | - | rubber_ball |
| rigid | - | - | - | - | - | rock: declined |

- **frequency_hz** - the wobble of the body held at its base and pushed. Physical: a
  nearly incompressible block of height H rings near c_s / 4H with c_s = sqrt(G / rho);
  gelatin G' 2-10 kPa gives an 8 cm jello 4.4 Hz.
- **damping_ratio** - of that wobble, applied only to motion that is not rigid.
- **squash** - 0 keeps the shape, 1 lets any volume-preserving deformation go free.
- **global_stiffness** - share of shape memory held by the whole body at once.
- **plastic** - yield (strain before it stays), creep (per second toward the held
  shape), max (fraction of its size the rest shape may drift). Rest volume is held.
- **friction**, **rolling_resistance** (1/s while touching), **resolution** (cells on the
  longest side; cost grows with its cube), **stiffness_gain** (what `tune` recommends).

A new material is `registry.define_material(name, "shape_matching", density, source=...,
shape_matching={...})`. Say where the numbers came from in `source`.

**3. Colliders.** Volumes are pushed by physics bodies. Give what they rest on **convex**
collision - `Plate-convcol` in Blender (see `blender-to-godot`), or
`mesh.create_convex_shape()` in Godot. A trimesh has no inside (see Rules).

**4. Export and read back.**

```python
m = export.export(r"C:/proj/assets/volumes/desserts.glb", ["Jello", "Plate", "Floor"])
print(export.summarize(m))       # PASSED; a mounted volume's pins 49/49 found
```

## Godot

**5. Install the runtime** once: copy `${CLAUDE_PLUGIN_ROOT}/godot/addons/follow_through`
into `<project>/addons/`.

**6. Build.**

```gdscript
const FollowThrough = preload("res://addons/follow_through/follow_through.gd")

func _ready() -> void:
    var props := preload("res://assets/volumes/desserts.glb").instantiate()
    add_child(props)
    for rep in FollowThrough.apply(props, {"routes": ["shape_matching"]}):
        if not rep["built"]:
            push_warning("%s: %s" % [rep["node"], rep["problems"]])
```

Each built report's `body` is a `ShapeMatchBody` (a `MeshInstance3D`):
`body.poke(point, impulse_Ns, radius)`, `body.teleport(Transform3D)`,
`body.centre_of_mass()`, `body.mesh_volume()`, `body.surface_positions()`. Set
`material_override` on it for the look - translucent with a rim for jello and slime.

**7. Verify - always.**

```bash
godot --headless --path <project> -s res://addons/follow_through/verify_volume.gd -- scene=res://assets/volumes/desserts.glb tune=true frames=600
```

| check | limit | failing means |
|---|---|---|
| `volume` | 0.85-1.15 (plastic 0.75-1.25) | collapsing: too soft for its weight - raise frequency_hz, lower squash |
| `not_inside` | 5% of vertices deeper than a contact radius | sinking: a trimesh collider, a sharp edge, or too few substeps |
| `settled` | 0.1 m/s of travel over half a second | rolling, rocking or a feedback cycle at a contact |
| `pins` | 0.005 m | the mounted body's pins do not follow its node |
| `frequency` | 35% (tune=true; not for plastic or damping >= 0.7) | write back `recommended_stiffness_gain` |

`tune=true` holds each body at its base, shears it in zero gravity and counts the wobble;
write the gain back with `volume.set_params("Jello", stiffness_gain=0.59)` and re-export.
`set=frequency_hz:6,squash:0.3` tries values without re-exporting. `ms_per_tick` is
reported: 1.3-3 ms for a resolution-4 jello, 7-10 ms for clay at 8 substeps.

## Rules

Measured in Godot 4.7.2 with Jolt; the numbers are in `references/volumes.md`.

**Small clusters alone forget the shape.** Each lattice node's 27-node cluster can turn
its own way; a cube poked in zero gravity at resolution 6 folded to 63% of its volume and
stayed. One cluster over the whole body, blended by `global_stiffness`, holds it (1.001).

**The body's frequency is not the node's.** Local clusters are springs in series: a
cube's measured wobble was 13-23% of the per-node spring's. The runtime converts with a
fitted model (stiffness ~ resolution^-1.73 locally, constant globally, blended; frequency
x (1 - 0.46 squash^2)) that held within 10% at resolutions 3-6 and 2-8 Hz.

**Substeps come from the angle, never from alpha.** Alpha = 2(1 - cos w dt) is periodic:
a clay ball whose node spring needed 6.39 rad per tick read alpha 0.01 at one substep,
ran nearly stiffness-free and flattened to 1% of its volume. `stiffness_limited` says when
8 substeps cannot give what a material asks.

**Damp what is not rigid.** Absolute damping capped a falling jello at 2.4 m/s. Damping
acts on motion relative to the body's own translation and rotation; a separate
`rolling_resistance` takes rigid energy only while touching - without it a round water
balloon rocked on a flat floor indefinitely.

**Contacts: rays first, every substep, and never as velocity.** Overlap cannot say which
side a vertex came from: a jello cube six ticks into a 10 cm slab was nearer its bottom
face and was pushed through. Each sample casts a ray from where it was; the push moves
positions only (turned into velocity it launched a clay ball at 7.5 m/s); resolved only
once per tick the goals pulled nodes back and a jello cube wandered 12 cm in 10 s.

**Samples are chosen every tick, per cell, from where the vertices are.** Fixed at rest, a
flat bottom face has no lowest vertex; tilted, the vertices between samples sank 2.6 cm.

**Convex colliders, not trimeshes.** A trimesh has no inside: a vertex that crossed a floor
slab's face in one tick was never in contact again, and every loose sample fell through at
59 m/s. Thin ramps: a thick one's end is a step a rolling ball wedges into, and a sharp
edge pushes into a volume between its samples.

**Squash below 1.** At squash 1 every volume-preserving shear is free: a water balloon
measured no wobble at all. 0.8 rings at 2.9 Hz for a 3 Hz target.

**A body too soft for its size collapses.** Sag is g / w^2: slime at 1 Hz sags 25 cm, more
than the 28 cm blob, and folded flat to 4% of its volume. Make it flow by creep, not by
softness.

**Hold the rest volume by the mesh, not the lattice.** Summed cell determinants stayed at
1.000 while a clay ball's embedded mesh lost half its volume; the plastic step rescales the
rest shape against the render mesh's own volume.

## Limits

- Volumes are pushed and do not push: no two-way coupling with RigidBody3D, no
  volume-volume collision (a rolling balloon passed into a pudding), nothing collides with
  them. `poke()` is the way in.
- GDScript cost: a few ms per body. A handful per scene, not a hundred.
- A sharp external edge can push between contact samples.
- No fracture, tearing or dripping: slime flows only by changing its rest shape.
- Frequencies of mounted, tapered bodies read up to 30% high - tune per asset.
