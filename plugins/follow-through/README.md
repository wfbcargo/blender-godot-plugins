# follow-through

Secondary motion for **Blender 5.x** assets headed to **Godot 4.7** (Jolt). This is
the motion nobody keyframes: cloth now, strands and soft volumes next. The plugin
recognises it, writes a spec that survives glTF, and makes it move in Godot.

Named after the animation principle *follow-through and overlapping action*.

## What's in it

| | |
|---|---|
| skill `follow-through` | Recognition and routing. Measures a mesh (boundary loops, thickness, curvature, extents, contacts, skinning) and classifies it by **family** (strand 1D, shell 2D, volume 3D) and **class** (hanging sheet, worn sheet, worn tube, loose sheet, strap, tensioned; solid sheets and volumes declined). Renders let vision decide what the numbers can't. |
| skill `cloth` | The cloth library: fabric choice, pins, Blender preview, export with read-back, Godot runtime and verifier. |
| `schema/follow-through.schema.json` | The contract: one custom property, `follow_through`, carried by glTF as node extras. |
| `scripts/follow_through/` | Blender Python: `measure`, `classify`, `views`, `spec`, `cloth`, `export`, `samples`. |
| `godot/addons/follow_through/` | `follow_through.gd` (reads specs, builds bodies), `cloth_body.gd` (the SoftBody3D), `verify_cloth.gd` (headless measurement). |
| `references/` | `concepts.md` (the ideas, from zero) and `cloth.md` (research, measurements, sources). |

## Requirements

- Blender 5.x with the [blender-mcp](https://github.com/ahujasid/blender-mcp) addon.
- Godot 4.7 with **Jolt Physics** as the 3D engine. GodotPhysics3D soft bodies don't
  collide headless, so they can't be verified.

## Install

```
/plugin marketplace add wfbcargo/PaulClaudePlugins
/plugin install follow-through@paul-claude-plugins
```

Then copy `godot/addons/follow_through` into each Godot project.

## Things it found along the way

Each of these was measured in Godot 4.7.2 with Jolt, or read back from an exported file:

- **Stiffness.** `SoftBody3D` cloth under Jolt has no bending constraints. At
  `linear_stiffness` 0.9–1.0 a hanging sheet flutters at metres per second
  indefinitely. Keep it at 0.7–0.8.
- **Damping.** `damping_coefficient` is a decay rate per second, and values above 1
  work. Godot's default of 0.01 never lets a swing settle.
- **Property timing.** `linear_stiffness`, `simulation_precision` and
  `shrinking_factor` set after the body enters the tree are silently ignored.
- **Pins.** Attachment-path pins never move in a headless run, so pins have to be
  driven with `soft_body_move_point`.
- **Transforms.** A soft body's node transform places its points once, then resets
  to identity. Moving the node afterwards teleports the cloth.
- **Vertex order.** Godot's importer reorders vertices, and UV seams split them, so
  pins must be positions, not indices.
- **Seams.** Jolt welds vertices at identical positions, so seams hold. A gap of
  0.5 mm tears.
- **Skinned export.** Blender's glTF exporter bakes a skinned mesh's world
  transform into its vertices; unskinned meshes stay mesh-local.
- **Custom attributes.** Blender exports `_attributes`, and Godot's importer drops
  them. Vertex groups never export at all.

## Limits

- **No bending.** Leather and canvas differ from cotton only in mass and damping.
- **No self-collision** and no cloth-on-cloth collision.
- **No proxy mesh.** The render mesh is what gets simulated.
- **Not built yet:** strands (spring bones), volumes, wind.
