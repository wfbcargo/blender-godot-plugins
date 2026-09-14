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
| **volume** | 3D | a bendable solid | jello, belly, slime, a squishy ball, clay | stretching in every direction, and keeping its volume |

So fabric really is a bendable plane and jello a bendable 3D object. The
simulation reflects that directly:

- Cloth has **no inside**. It can fold flat onto itself, and nothing wants it to
  keep a volume.
- Jello's defining property is that it **keeps its volume**. Squash it down and it
  bulges out sideways. A cloth simulation has no idea how to do that.
- A strand is in between: a line has no area to stretch, only length, bend and twist.

In the field these are called **rods** (strands), **shells** or **cloth** (surfaces)
and **soft bodies** or **FEM volumes** (solids). The same engine can host all three,
but the constraints differ. Sections 3-7 are cloth; 9 is volumes, 10 flesh.

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

## 9. Volumes: shape memory instead of constraints

A volume has an inside, and what makes jello jello is that it **remembers its shape and
keeps its volume**. Cloth's recipe - particles joined by distance constraints - cannot do
that without bending and volume constraints, and Godot's Jolt soft body builds neither. So
volumes use **shape matching**:

1. Embed the mesh in a coarse **lattice** - a few cells a side. The lattice nodes are the
   particles; the render mesh just follows its cell (trilinear interpolation).
2. Each node has a **cluster**: itself and its neighbours. Every tick, each cluster asks
   "what rigid rotation best maps my rest shape onto where my nodes are now?" (a polar
   decomposition) and proposes a **goal** for each node: where the rest shape would put it.
3. Nodes move a fraction **alpha** of the way to the average of their goals. That fraction
   is the stiffness: a spring of frequency w corrected once per step has
   alpha = 2(1 - cos w dt).
4. One more cluster covers the whole body. Small clusters alone can each turn their own way
   and the body folds; the whole-body goal holds the form (`global_stiffness`).

Three extras give three materials:

- **squash** blends the best *linear* fit, normalised so its determinant is 1, into the
  goal. The body can squash and bulge sideways while keeping its volume - a water balloon.
- **plasticity** moves the rest shape itself toward the shape the body is held in, once the
  strain passes a yield - clay flattens where it lands and stays flat; slime flows.
- **mounting** pins the nodes at a volume's base to whatever holds it - a jello stuck to its
  plate.

A volume is pushed by physics bodies through **contact samples** - surface vertices that
test the world - and does not push back.

## 10. Flesh: a spring per mass

A body's soft parts are not free volumes: they ride on bones, and the animation moves them.
Games give each mass a **jiggle bone**, parented to the bone it rides on, with the mass's
vertices weighted to it. Every frame, after the animation, the bone's tail is a point on a
**damped spring** whose rest position is where the animated skeleton puts it:

- **frequency** (Hz) - how fast it bounces. Soft fat 2-4 Hz, firm muscle 5-10.
- **damping ratio** - 0 bounces forever, 1 settles without overshoot. Flesh 0.2-0.35.
- the spring is driven by the **anchor's acceleration** - a footfall, a turn, a stop - and
  by gravity *relative to the rest pose*, because flesh modelled standing already sags.

The bone swings toward the tail (**aim**), its head follows part of the way (**translate**),
and it stretches along its length while its cross-section narrows by 1/sqrt, so the mass
keeps its volume (**squash**).

Finding the masses is the hard part: skinning says which bone moves a vertex, not which
vertices are soft. The body's **lean envelope** - the radius the surface would have without
bulges, estimated along each limb and the spine - says how far each vertex **stands out**.
Standing out alone cannot tell a belly from wide hips, so each kind of flesh also names a
**zone** of the body.

## 11. Types: what a thing is, and teaching

Recognition has three levels:

| level | answers | decides | example |
|---|---|---|---|
| family | what dimension moves | the kind of simulation | volume |
| class | how it is held | the runtime | mounted_volume |
| type | what it is | the material | jello |

Classes need code - a runtime each. **Types are data**: a JSON entry with the words that
name it, the classes it can take, its material, and for flesh its zone. So a new kind of
thing needs an entry, not a program.

Evidence for a type comes from **names** and from **taught examples**: an example is one
object's measured shape features, stored with the type someone said it was. A new object
is compared with every example; the nearest of each type votes. This is the same thing
vision does in the loop - look, decide - except that the decision is kept, so the second
slime is recognised without looking.

## 12. Looking in 2D, mapping to 3D

Deciding *what* a bulge is is easy to see and hard to measure. Deciding *exactly which
vertices, and how far out* is the reverse. So they are split: render labelled views (a
lettered grid, numbered candidates), mark zones on the picture, then map the marks back
through each view's camera onto the vertices that camera could see. The geometry then
places the bone and feathers the weights inside what was marked.
