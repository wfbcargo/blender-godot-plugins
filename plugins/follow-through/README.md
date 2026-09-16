# follow-through

Secondary motion for **Blender 5.x** assets headed to **Godot 4.7** (Jolt). This is the
motion nobody keyframes: cloth, soft volumes - jello, slime, clay, water balloons - and
flesh on a body. The plugin recognises it, **types** it, writes a spec that survives glTF,
and makes it move in Godot.

Named after the animation principle *follow-through and overlapping action*.

## What's in it

| | |
|---|---|
| skill `follow-through` | Recognition, typing and routing. Measures a mesh and classifies it by **family** (strand, shell, volume) and **class** (six cloth classes, `loose_volume`, `mounted_volume`, `flesh`), types it from the **registry**, and teaches the registry new types. |
| skill `cloth` | Sheets as a `SoftBody3D`: fabric, pins, Blender preview, export with read-back, runtime and verifier. |
| skill `volume` | Jello, pudding, slime, clay, water balloons as **lattice shape matching**: materials, mounting, runtime, verifier. |
| skill `flesh` | Breasts, bellies, buttocks, a bloater's torso as **jiggle bones**: finding the masses (by measure or by 2D marks), rigging, export with the walk, runtime. |
| `types/builtin.json` | The type registry: types (names, classes, material, flesh zone) and materials (with where their numbers came from). Taught types go to `~/.claude/follow-through/types.json`. |
| `schema/follow-through.schema.json` | The contract: one custom property, `follow_through`, carried by glTF as node extras. |
| `scripts/follow_through/` | Blender Python: `measure`, `classify`, `registry`, `views`, `spec`, `cloth`, `volume`, `flesh`, `marks`, `export`, `samples`. |
| `godot/addons/follow_through/` | `follow_through.gd` (reads specs, builds bodies), `cloth_body.gd`, `shape_match_body.gd`, `jiggle_modifier.gd`, `verify_cloth.gd`, `verify_volume.gd`. |
| `references/` | `concepts.md` (the ideas, from zero), `cloth.md`, `volumes.md`, `flesh.md` (research, measurements, sources). |

## Requirements

- Blender 5.x with the [blender-mcp](https://github.com/ahujasid/blender-mcp) addon.
- Godot 4.7 with **Jolt Physics** as the 3D engine.
- For flesh: a rigged body - `rig-anything` (0.13.1+, which exports custom properties) rigs
  and walks one.

## Install

```
/plugin marketplace add wfbcargo/blender-godot-plugins
/plugin install follow-through@blender-godot-plugins
```

Then copy `godot/addons/follow_through` into each Godot project.

## Teaching it

Types are data. When Claude has to look at renders to decide what something is, it records
the answer, and the next one is recognised without looking:

```python
registry.teach("Thing05", "slime")                                         # an example of a known type
registry.teach("Figure", "double_chin", group="chin_fat", material="soft_fat")   # a new flesh type from a painted group
found = marks.regions("Bloater", [{"type": "breast", "view": "front", "ellipse": ["H5", 0.9, 0.9]}], sheet)
```

On the sample volumes, renamed and reshaped copies were typed 2/7 untaught and 7/7 after
teaching the originals. On the sample bloater, moob bones placed 19 cm off by the measure
alone landed 7.6 cm off from a 2D mark.

## Things it found along the way

Measured in Godot 4.7.2 with Jolt, in Blender 5.2, or read back from an exported file.

**Cloth**

- **Stiffness.** Jolt cloth has no bending constraints; at `linear_stiffness` 0.9-1.0 a
  hanging sheet flutters at metres per second indefinitely. Keep it at 0.7-0.8.
- **Damping** is a decay rate per second, and values above 1 work.
- **Property timing.** `linear_stiffness`, `simulation_precision` and `shrinking_factor` set
  after the body enters the tree are silently ignored.
- **Pins** have to be driven with `soft_body_move_point`; attachment pins never move headless.
- **Vertex order.** Godot's importer reorders vertices and UV seams split them: pins are positions.

**Volumes**

- **Jolt's soft body has no volume.** 4.7.2 builds no bend and no volume constraints: a closed
  surface keeps only what pressure gives it. Volumes need their own solver.
- **Small clusters forget the shape.** Poked at resolution 6 a cube folded to 63% of its volume;
  one whole-body cluster blended in holds 1.001.
- **The body's frequency is not the node's.** Measured at 13-23% of the per-node spring; a fitted
  model converts it to within 10% across resolutions 3-6 and 2-8 Hz.
- **Stiffness from alpha aliases.** alpha = 2(1 - cos w dt) is periodic: a clay ball read 0.01 at
  6.39 rad and flattened to 1%. Substeps come from the angle.
- **Contacts need rays, every substep, and must not become velocity.** Overlap pushed a cube
  through a 10 cm slab from inside; pushes turned into velocity launched a ball at 7.5 m/s;
  resolved once per tick a cube wandered 12 cm in 10 s.
- **Trimeshes have no inside.** Every loose volume fell through a trimesh floor at 59 m/s.
- **Squash 1 frees shear.** A water balloon at squash 1 did not wobble at all.

**Flesh**

- **Skinning does not say what is soft.** Bone heat spread breasts over shoulder and neck bones;
  basic_human's breast bones sat 14 cm below them. Masses come from the surface: how far it
  stands out of the body's lean envelope.
- **Excess cannot tell hips from a waist.** Zones from the registry decide what; the measure
  decides where.
- **Nearest bone lies about wide bodies.** A bloater's torso sides were closer to its arms than
  its spine; chains come from skin weights.
- **SpringBoneSimulator3D is rotation-only and frame-rate dependent.** Flesh uses a
  `SkeletonModifier3D` with an exact damped oscillator: measured frequencies within 1%.
- **Bones stay Y-along through glTF.** Jiggle bone heads matched the spec to 0.0000 m in Godot,
  tails exactly on local Y.

**Pipeline**

- **Selection is per scene.** Exported without `use_active_scene`, a body carried eleven meshes
  selected in another scene. `export.verify(..., expect_meshes=[...])` catches strays.
- **Custom attributes** are dropped by Godot's importer; **object custom properties** survive as
  node extras - but only if the exporter is told `export_extras`.

## Limits

- **Cloth:** no bending, no self-collision, no proxy mesh.
- **Volumes:** pushed by physics bodies but do not push back; no volume-volume collision; a few
  ms of GDScript each; a sharp external edge can press between contact samples.
- **Flesh:** one spring per mass (no ripple across a big belly), no collision with the body;
  the head, hands and feet are not searched.
- **Not built yet:** strands (spring bones), wind, two-way coupling.
