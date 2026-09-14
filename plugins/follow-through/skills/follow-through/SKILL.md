---
name: follow-through
description: Recognise secondary motion on a Blender asset - the parts that move on their own and are never keyframed - and route it to the library that builds it for Godot 4.7. Measures a mesh (open boundaries, thickness, curvature, extents, contacts, skinning), classifies it by family (strand 1D, shell 2D, volume 3D) and class (hanging sheet, worn sheet, worn tube, loose sheet, strap, tensioned), finds what holds it, and writes a spec that survives glTF export. Use when asked whether something should jiggle, sway, flap, drape or wobble, to make cloth, fabric, a flag, banner, curtain, cape, cloak, skirt, robe, scarf, tablecloth, towel, sail or tent move, to set up soft body or cloth physics from Blender for Godot, to tell cloth from a solid body, or when Godot cloth falls, stretches, tears at seams or jitters.
---

# follow-through

Primary motion is what an animator keys: a walk, a bite. **Follow-through** is what
trails behind it and settles - a cape after a turn, a flag in the wind, a belly
after a jump. Nobody keys it; something simulates it. This skill decides *what*
that something is for a given mesh, then hands off to a library that builds it.

The design is the one `rig-anything` uses: **deterministic Python measures,
vision classifies.** A flag on a pole and a poster on a pipe measure the same.
Looking at them does not.

Read `${CLAUDE_PLUGIN_ROOT}/references/concepts.md` once for the vocabulary - families, constraints,
pins, why Godot and Blender disagree. It is short and everything below assumes it.

## Running it

Inside Blender through the `blender` MCP server. Modules get edited between calls
in a long-lived session, so always reload:

```python
import sys, importlib
P = r"${CLAUDE_PLUGIN_ROOT}/scripts"
if P not in sys.path:
    sys.path.insert(0, P)
import follow_through
importlib.reload(follow_through)
follow_through.reload_all()
from follow_through import measure, classify, views, spec, cloth, export, samples
```

## Workflow

**1. Measure and classify.**

```python
r = classify.classify("MyObject")
print(classify.summarize(r))
```

```
Curtain: shell / hanging_sheet -> soft_body (confidence 0.9)
  - open surface: 1 boundary loop(s), Euler characteristic 1
  - hangs: vertical (verticality 1.0) and held near the top by CurtainRod
  - name agrees: Curtain -> hanging_sheet
  pins: 21 from touching CurtainRod
```

`classify.scene("SceneName")` does every mesh in a scene.

**2. Look.** Always when `confidence` is below 0.8 or `GUESSED` names the class:

```python
res = views.render_views("MyObject", r"C:/scratch/views")
```

Read the PNGs. The object is light grey, what it touches dark grey. If the class
is wrong, say what you see and re-run with `classify.classify(name, cls="draped_sheet")`.
If it is still unclear, **ask** - a cape and a banner want different pins.

**3. Route.** `r["route"]` names the library:

| route | library skill | status |
|---|---|---|
| `soft_body` | **`follow-through:cloth`** | built (0.1.0) |
| `spring_bones` | strands (tails, hair, straps as bone chains) | not built - cloth can still simulate a strap as a narrow sheet |
| `none` | - | nothing moves, or a volume library that does not exist yet |

Load the library skill and continue there. It writes the spec (step 4) as part
of its own workflow.

**4. The spec.** Whatever the library, the result is one custom property on the
object, `follow_through`, matching `${CLAUDE_PLUGIN_ROOT}/schema/follow-through.schema.json`:

```python
print(spec.read(bpy.data.objects["Curtain"]))
print(spec.validate(spec.read(bpy.data.objects["Curtain"])))   # [] when valid
```

The pins' editable source is the vertex group **`ft_pin`**. Paint it, then
`spec.sync(obj)`; `export` syncs anyway.

## Families and classes

| family | what moves | class | examples | held by |
|---|---|---|---|---|
| **strand** (1D) | a line | - | rope, tail, hair | its root |
| **shell** (2D) | a surface | `hanging_sheet` | flag, banner, curtain | an edge on a prop |
| | | `draped_sheet` | cape, cloak, tabard | its top edge, on a body |
| | | `draped_tube` | skirt, robe, sleeve | its upper ring |
| | | `loose_sheet` | tablecloth, towel, tarp | nothing - it rests |
| | | `strap` | scarf, ribbon, sash | one end |
| | | `tensioned` | sail, awning, tent | corners, pulled taut |
| | | `solid_sheet` | cloth modelled with thickness | declined - see rules |
| **volume** (3D) | a body with an inside | `volume` | jello, belly, slime | declined for now |

## What the numbers mean

| reading | meaning |
|---|---|
| `boundary_loops` | 0 closed, 1 a sheet, 2+ a tube. The strongest single cloth cue |
| `euler_characteristic` | V - E + F: 1 a disc-like sheet, 0 a tube open both ends, 2 a closed body |
| `thickness_over_size` | median inward ray hit / longest extent. A solidified blanket 0.007, a pole 0.02, a body 0.2+ |
| `curvature_over_sphere` | total absolute angle defect / 4 pi on interior vertices. Flat or folded sheet ~0; any closed mesh is 1 by Gauss-Bonnet, so it says nothing there |
| `aspect_long_over_mid` | a scarf 9.3, a pennant 2.25. 5+ is a strap |
| `verticality` | 1 - area-weighted mean abs(normal z). A hanging sheet 1.0, a tablecloth 0.0 |
| `contacts.by_object` | vertices within 1 cm or 1% of size of another mesh, or inside a closed one; `mean_height_fraction` says whether it is held from above or rests |

## Rules

**Measure the object's own scene, and evaluate it first.** A scene that is not the
active one keeps stale `matrix_world` values - identity, for new objects - so every
sample body read as piled up at the origin and a jello cube "touched" a skirt 14 m
away. `measure.analyze` updates the object's view layer before it measures.

**"Inside" only means something for a closed mesh.** The first contact test took
the side of the nearest face's normal as inside or outside, which is meaningless
for an open sheet and unreliable near edges. Inside is now a ray-parity test, run
only against closed meshes.

**A worn sheet hangs from its whole top edge, not from what touches.** Only the
middle vertices of a cape's shoulder line touch a narrow back; pinning just those
dropped the corners and scored 0.18 overlap with the right pins. Worn sheets pin
the top boundary edge.

**Names are evidence, never the decision.** Every sample body was renamed
`ThingNN` and classified again: 14/14 still right, every pin set identical, with
confidence lower where a name had agreed. A name that disagrees with the geometry
lowers confidence and asks for the renders.

**Cloth with modelled thickness is declined, not simulated.** A solidified sheet is
closed and thin: two skins millimetres apart joined round the rim, where a pin set
and a soft body both expect one surface. (Declined on that reasoning; simulating
one was not tried.) Simulate the single sheet and thicken it at render time.

**A strap routes to strands.** Until that library exists, `cloth.prepare` builds it
as a narrow soft body and says so in its warnings.

## Status

- **0.1.0** - recognition (families, six cloth classes, solid sheet and volume
  declined), the schema, the cloth library, export read-back, the Godot runtime and
  headless verifier. `samples.build_all()`: 14 meshes, 14/14 classes and every
  pin set exact, with and without names.
- Next: strands (spring bones for tails, hair, straps), volumes (jello, flesh),
  wind, proxy meshes for dense cloth.
