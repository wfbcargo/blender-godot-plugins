---
name: follow-through
description: Recognise secondary motion on a Blender asset - the parts that move on their own and are never keyframed - type it, and route it to the library that builds it for Godot 4.7. Measures a mesh (open boundaries, thickness, curvature, extents, contacts, skinning), classifies it by family (strand 1D, shell 2D, volume 3D) and class (hanging, worn or loose sheets, straps, sails; loose and mounted volumes; flesh on a skinned body), types it from a registry of names, taught examples and anatomical zones (jello, slime, clay, a breast, a bloater's belly), and teaches that registry new types from objects, painted groups or zones marked on 2D renders. Use when asked whether something should jiggle, wobble, sway, flap, drape, sag or squash; to make cloth, a flag, curtain, cape, skirt, jello, slime, clay, a water balloon or flesh move; to set up soft body, cloth or jiggle physics from Blender for Godot; to tell cloth from a solid body; or to teach Claude what a new kind of object is.
---

# follow-through

Primary motion is what an animator keys: a walk, a bite. **Follow-through** is what
trails behind it and settles - a cape after a turn, a jello after it is set down, a belly
after a footfall. Nobody keys it; something simulates it. This skill decides *what* that
something is for a given mesh, then hands off to a library that builds it.

The design is the one `rig-anything` uses: **deterministic Python measures, vision
classifies.** A flag on a pole and a poster on a pipe measure the same; a jello and a rock
measure the same. Looking at them does not - and what was once looked at can be **taught**.

Read `${CLAUDE_PLUGIN_ROOT}/references/concepts.md` once for the vocabulary - families,
classes, types, constraints, pins, why Godot and Blender disagree. Everything below
assumes it.

## Running it

Inside Blender through the `blender` MCP server. Modules get edited between calls in a
long-lived session, so always reload:

```python
import sys, importlib
P = r"${CLAUDE_PLUGIN_ROOT}/scripts"
if P not in sys.path:
    sys.path.insert(0, P)
import follow_through
importlib.reload(follow_through)
follow_through.reload_all()
from follow_through import (measure, classify, registry, views, spec, cloth, volume, flesh,
                            marks, export, samples)
```

## Workflow

**1. Measure, classify and type.**

```python
r = classify.classify("MyObject")
print(classify.summarize(r))
```

```
Jello: volume / mounted_volume / jello -> shape_matching (confidence 0.75)
  - closed with depth: thickness/size 0.886, compactness 0.07436 (sphere 0.094)
  - unskinned: a free body, resting on Plate
  - jello (gelatin) sticks to what it rests on: mounted on Plate
  - type name: jello -> jello
  pins: 49 from base touching Plate
```

`classify.scene("SceneName")` does every mesh in a scene.

**2. Look.** Always when `confidence` is below 0.8 or `GUESSED` names the class or type:

```python
res = views.render_views("MyObject", r"C:/scratch/views")
```

Read the PNGs. The object is light grey, what it touches dark grey. If the class is
wrong, re-run with `classify.classify(name, cls="draped_sheet")`; if the type is wrong,
pass `type=` to the library. If it is still unclear, **ask** - a cape and a banner want
different pins, a jello and a clay ball different materials.

**3. Route.** `r["route"]` names the library:

| route | library skill | builds |
|---|---|---|
| `soft_body` | **`follow-through:cloth`** | sheets: flags, curtains, capes, skirts, tablecloths |
| `shape_matching` | **`follow-through:volume`** | volumes: jello, pudding, slime, clay, water balloons |
| `jiggle_bones` | **`follow-through:flesh`** | flesh on a skinned body: breasts, bellies, buttocks, bloaters |
| `spring_bones` | strands (tails, hair, straps as bone chains) | not built - cloth can still simulate a strap |
| `none` | - | nothing moves (a rock, a rigid prop) |

Load the library skill and continue there. It writes the spec as part of its workflow.

**4. Teach what you had to look at.** When the renders decided something the measures
could not - this unnamed blob is slime, this bulge is a double chin - record it, so the
next one is recognised without looking:

```python
registry.teach("Thing05", "slime")                                        # an object is a known type
registry.teach("Boulder", "boulder", material="rigid", note="big rock")   # a new type from an object
registry.teach("Figure", "double_chin", group="chin_fat", material="soft_fat")   # a new flesh type
print(registry.summary())
```

See **Types and teaching** below.

**5. The spec.** Whatever the library, the result is one custom property on the object,
`follow_through`, matching `${CLAUDE_PLUGIN_ROOT}/schema/follow-through.schema.json`:

```python
print(spec.read(bpy.data.objects["Curtain"]))
print(spec.validate(spec.read(bpy.data.objects["Curtain"])))   # [] when valid
```

Pins' editable source is the vertex group **`ft_pin`** (cloth, mounted volumes). Paint it,
then `spec.sync(obj)`; `export` syncs anyway. Flesh's editable source is its `ft_jiggle_*`
bones and groups.

## Families and classes

| family | what moves | class | examples | held by | route |
|---|---|---|---|---|---|
| **strand** (1D) | a line | - | rope, tail, hair | its root | - |
| **shell** (2D) | a surface | `hanging_sheet` | flag, banner, curtain | an edge on a prop | soft_body |
| | | `draped_sheet` | cape, cloak, tabard | its top edge, on a body | soft_body |
| | | `draped_tube` | skirt, robe, sleeve | its upper ring | soft_body |
| | | `loose_sheet` | tablecloth, towel, tarp | nothing - it rests | soft_body |
| | | `strap` | scarf, ribbon, sash | one end | spring_bones |
| | | `tensioned` | sail, awning, tent | corners, pulled taut | soft_body |
| | | `solid_sheet` | cloth modelled with thickness | declined | none |
| **volume** (3D) | a body with an inside | `loose_volume` | jello cube, clay ball, balloon | nothing - it rests or falls | shape_matching |
| | | `mounted_volume` | jello on a plate, pudding | its base, on a prop | shape_matching |
| | | `flesh` | a body's breasts, belly, buttocks | the bones it rides on | jiggle_bones |

A closed mesh with depth is a volume; skinned, it is `flesh`; unskinned, `loose_volume` -
or `mounted_volume` when it rests on something and its type's material is sticky.

## Types and teaching

The **type** is what a thing is, and picks the material (or fabric). Types are data, not
code: `types/builtin.json` ships them, and everything taught goes to the user registry
`~/.claude/follow-through/types.json` (override with `FOLLOW_THROUGH_TYPES`), read on top
and kept across plugin updates.

| type | family | classes | material | zone (flesh) |
|---|---|---|---|---|
| jello | volume | loose, mounted | gelatin | |
| pudding | volume | mounted, loose | custard | |
| slime | volume | loose, mounted | slime | |
| clay_ball | volume | loose | clay | |
| water_balloon | volume | loose | water_balloon | |
| rubber_ball | volume | loose | rubber | |
| rock | volume | loose, mounted | rigid - nothing moves | |
| breast (paired) | volume | flesh | soft_fat | spine, height 0.5-1.45, front |
| belly | volume | flesh | soft_fat | spine, height 0.2-0.75, front |
| bloater_belly | volume | flesh | bloated | a belly named so, or 20% of the body and 8% of its height out |
| butt (paired) | volume | flesh | soft_fat | hips, back |
| love_handle (paired) | volume | flesh | soft_fat | waist, sides |
| arm_flab (paired) | volume | flesh | soft_fat | upper arm, beyond the torso |
| thigh (paired) | volume | flesh | firm_flesh | legs |
| flag, curtain, cape, skirt, tablecloth, scarf, sail | shell | their cloth class | a fabric | |

`registry.recognise` weighs, per type: words in the object's name, and the nearest taught
example of that type by scale-free shape features (closed, loops, thickness, compactness,
aspect, verticality, size, skinned, resting, held from above). With neither, the class's
default is **guessed** and says so - and a guessed type never changes the class.

**Teaching** records an example. A type that does not exist yet is created from it: family
and class from `classify`, the material you name, and for a flesh region taught from a
painted group, a zone around where it sits on the body. `registry.define(...)` and
`registry.define_material(...)` add types and materials by hand (a flesh type's `anchor=` names the
rig-anything bone role its jiggle bone hangs from, e.g. `"pelvis"`); `registry.forget(type)`
removes one.

Measured on the sample volumes: named, 7/7 classes and 7/7 types. The same seven things
reshaped and renamed `Thing02..09`, untaught: 5/7 and 2/7. After teaching the named set:
7/7 and 7/7. Each type counts only its nearest example - summed, two jello examples
outvoted a clay ball's own example 0.007 away.

For flesh, looking has its own path: zones marked on `marks.render` sheets become regions
(see `follow-through:flesh`), and `registry.teach(obj, type, group=...)` turns a painted
group into a new zone.

## What the numbers mean

| reading | meaning |
|---|---|
| `boundary_loops` | 0 closed, 1 a sheet, 2+ a tube. The strongest single cloth cue |
| `euler_characteristic` | V - E + F: 1 a disc-like sheet, 0 a tube open both ends, 2 a closed body |
| `thickness_over_size` | median inward ray hit / longest extent. A solidified blanket 0.007, a pole 0.02, a body 0.2+ |
| `compactness` | volume / area^1.5: a sphere 0.094, a jello mould 0.074, a clay ball 0.094 |
| `curvature_over_sphere` | total absolute angle defect / 4 pi on interior vertices. Flat or folded sheet ~0 |
| `aspect_long_over_mid` | a scarf 9.3, a pennant 2.25. 5+ is a strap |
| `verticality` | 1 - area-weighted mean abs(normal z). A hanging sheet 1.0, a tablecloth 0.0 |
| `contacts.by_object` | vertices within 1 cm or 1% of size of another mesh, or inside a closed one; `mean_height_fraction` says whether it is held from above or rests |

## Rules

**Measure the object's own scene, and evaluate it first.** A scene that is not the active
one keeps stale `matrix_world` values - identity, for new objects - so every sample body
read as piled up at the origin. `measure.analyze` updates the object's view layer first.

**"Inside" only means something for a closed mesh.** Inside is a ray-parity test, run only
against closed meshes.

**A worn sheet hangs from its whole top edge, not from what touches.** Pinning just the
touching middle of a cape's shoulder line dropped its corners.

**Names are evidence, never the decision.** Renamed `ThingNN`, the cloth samples still
classified 14/14 with identical pins. A name that disagrees with the geometry lowers
confidence and asks for the renders.

**Cloth with modelled thickness is declined, not simulated.** Simulate the single sheet and
thicken it at render time.

**A strap routes to strands.** Until that library exists, `cloth.prepare` builds it as a
narrow soft body and says so.

**Selection is per scene.** An exporter run without `use_active_scene` takes objects
selected in other scenes: a body exported after a volume export carried eleven meshes it
had never seen. `export.export` deselects its scene, rig-anything's export passes
`use_active_scene`, and `export.verify(path, expect_meshes=[...])` fails on strays.

## Status

- **0.2.0** - volumes and flesh. Classes `loose_volume`, `mounted_volume`, `flesh`; routes
  `shape_matching` and `jiggle_bones`; the type registry and teaching; the `volume` and
  `flesh` libraries, 2D zone marking, Godot runtimes and `verify_volume.gd`. Sample volumes
  7/7 typed and 6/6 verified; both sample bodies (rigged and walking with rig-anything)
  verified; cloth still 14/14.
- **0.1.0** - recognition, the schema, the cloth library, export read-back, the cloth
  runtime and verifier.
- Next: strands (spring bones for tails, hair, straps), volume-volume and two-way
  collision, wind, proxy meshes for dense cloth.
