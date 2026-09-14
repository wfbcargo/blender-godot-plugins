# Secondary motion: the concepts

The vocabulary behind follow-through, in the order it builds up.

## 1. Primary and secondary motion

**Primary motion** is authored: the animator keys a walk, a bite, a jump. It is
*intent*.

**Secondary motion** is the consequence: the cape that swings out after the turn,
the ears that flop after the landing, the jello that wobbles after it is set down.
Nobody keys it, because it is not a decision - it is physics reacting to the primary
motion. The animation principle is called **follow-through and overlapping action**,
which is where the plugin's name comes from.

Because it reacts, secondary motion is usually **simulated at runtime** rather than
baked into clips. A baked cape swings the same way on every turn; a simulated one
swings harder on a sharper turn.

## 2. Three families, by dimension

The first question about anything that jiggles or flows: **what is the shape of the
thing that moves?**

| family | dimension | intuition | examples | what resists deformation |
|---|---|---|---|---|
| **strand** | 1D | a bendable line | rope, hair, tail, antenna, chain | stretching along it, bending, twisting |
| **shell** | 2D | a bendable plane | cloth, flag, sail, paper, leaf | stretching and shearing within the surface, bending out of it |
| **volume** | 3D | a bendable solid | jello, belly, slime, a squishy ball | stretching in every direction, and keeping its volume |

So fabric really is a bendable plane and jello a bendable 3D object. The
simulation reflects that directly:

- Cloth has **no inside**. It can fold flat onto itself, and nothing wants it to
  keep a volume.
- Jello's defining property is that it **keeps its volume**. Squash it down and it
  bulges out sideways. A cloth simulation has no idea how to do that.
- A strand is in between: a line has no area to stretch, only length, bend and twist.

In the field these are called **rods** (strands), **shells** or **cloth** (surfaces)
and **soft bodies** or **FEM volumes** (solids). The same engine can host all three,
but the constraints differ.

## 3. How cloth is simulated: particles and constraints

Almost every real-time cloth solver works the same way underneath:

1. **Particles.** Every mesh vertex is a point with a mass.
2. **Constraints.** Rules connect the particles. The rules *are* the fabric:
   - **stretch**: two vertices sharing an edge want to stay that far apart. This is
     the main thing that makes cloth cloth and not rubber.
   - **shear**: vertices across a quad's diagonal want to stay that far apart, so the
     weave doesn't skew into a diamond.
   - **bend**: two triangles sharing an edge want to keep the angle between them.
     This separates silk (weak bend, drapes into many small folds) from leather
     (strong bend, few big folds).
3. **Each tick**: gravity and velocity move every particle, then the solver pushes
   particles back until the constraints are roughly satisfied, then velocity is
   whatever that movement was.

Pushing particles back is only ever approximate. Each **iteration** or **substep**
lets a correction travel about one edge. A curtain whose hem is 24 edges below the
rod needs many passes per tick; otherwise the hem is effectively still falling while
the top has already stopped, and the curtain stretches like rubber. That is why:

- **precision / substeps** controls stretch, and
- **tethers** (long-range attachments) exist in engines like Unreal's Chaos Cloth: a
  shortcut constraint straight from each particle to its nearest pin, so the hem
  can't sag further than the cloth's length.

The solver families - mass-spring, Verlet, PBD, XPBD - are different recipes for
step 3. They matter here only because Blender and Godot use different ones (§6).

## 4. Pins: what holds the cloth

Without pins cloth just falls. **Pinned** vertices don't simulate; they are placed
exactly where something else says, and the rest hangs from them.

- A flag's pole-side edge is pinned **to the pole**.
- A cape's shoulder line is pinned **to the chest bone**, so it moves with the body.
- A tablecloth has no pins; it rests on the table through **collision**.

What a pin follows is its **anchor**. follow-through has three: `node` (the object's
own transform, which is static for a curtain or moving for a flag on a ship), `bone`
(worn cloth) and `none`.

Pins and collision are different things. A pin says "be exactly here"; collision says
"don't be inside that". A cape needs both: pins at the shoulders, and colliders on
the body so it doesn't pass through the back when the character turns.

## 5. Damping: the missing air

Real cloth stops swinging quickly because it is pushing air around. Most simulations
don't model air per triangle, so **damping** stands in for it: every tick every
particle loses a fraction of its velocity. With too little damping a cape swings like
it's in a vacuum; with too much it moves like it's underwater. In Godot damping is a
rate per second, so 1.0 means roughly "lose two thirds of the speed each second".

## 6. Why Blender and Godot disagree

|  | Blender | Godot 4.7 (Jolt) |
|---|---|---|
| solver | implicit mass-spring | substepped XPBD |
| stretch / shear | separate spring strengths, 0-10000 | one `linear_stiffness`, 0-1 |
| bend | yes, a spring strength | **none**: Godot doesn't create bend constraints |
| mass | kg per vertex | kg for the whole body |
| quality | steps per frame | `simulation_precision` = substeps per tick |

The numbers don't convert. Blender's "Leather" preset gets its character from strong
bending, and Godot has no bending to give it. So each fabric in follow-through
carries **two parameter sets**: Blender's preset for previewing in Blender, and
Godot values chosen by measurement for the one thing Godot can express, which is how
the fabric stretches, swings and settles.

## 7. Getting data across: the spec

Blender knows which vertices are pinned (a vertex group) and what the fabric is.
Godot needs both. What survives the trip, tested end to end:

| channel | reaches Godot? |
|---|---|
| vertex groups | **no**: glTF has no such thing |
| custom `_attributes` | written to the file, then **dropped** by Godot's importer |
| vertex colour | yes, 8-bit, but it's often already used for colour |
| **object custom properties** | **yes**: exported as node *extras*, read as `get_meta("extras")` |
| vertex order | **no**: the importer reorders, and UV seams split vertices |

So the spec is one custom property, and pins are stored as **positions**, not vertex
numbers. A position names the same point in both programs; a number does not.

## 8. The pipeline

```
 Blender                                   glTF                Godot 4.7
 ───────                                   ────                ─────────
 mesh ─ measure ─ classify ─ route         node extras         import ─ FollowThrough.apply()
                  (renders   │               │                            │
                   decide)   ▼               │                            ▼
                  cloth.prepare ─ spec ──────┘──────────────────► SoftBody3D, pins driven
                  (pins, fabric) + ft_pin     export reads         to node / bone each tick
                                              the file back                │
                                              and checks pins              ▼
                                                                  verify_cloth.gd measures
                                                                  pins, stretch, seams, settling
```

Every arrow has a check: classification against sample bodies with known answers, the
export against the file it wrote, the runtime against a physics run. Each check
exists because the step it guards once failed without an error message.
