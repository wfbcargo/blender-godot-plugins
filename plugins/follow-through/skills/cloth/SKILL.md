---
name: cloth
description: Make cloth and fabric from Blender move in Godot 4.7 with Jolt - flags, banners, curtains, capes, cloaks, skirts, robes, scarves, tablecloths - as a SoftBody3D pinned to what holds it. Picks a fabric (silk, cotton, wool, denim, canvas, leather, rubber), writes pins and Godot parameters into a spec glTF carries, previews it in Blender's cloth sim, exports and reads the file back, builds the SoftBody3D at runtime, and runs a headless verifier measuring pin error, stretch, seams and settling. Use after follow-through routes a mesh to soft_body, or directly when cloth needs setting up, exporting or debugging - cloth that falls, stretches like rubber, tears at a seam, jitters or never stops swinging.
---

# cloth

The cloth library of `follow-through`. Run `follow-through`'s recognition first
unless the class is already known; `prepare` runs it anyway. Concepts and why the
numbers are what they are: `${CLAUDE_PLUGIN_ROOT}/references/concepts.md` and
`${CLAUDE_PLUGIN_ROOT}/references/cloth.md`.

## Blender

Load as in `follow-through` (reload every time), then:

**1. Prepare.** Recognise, pin, choose a fabric, write the spec and the `ft_pin` group.

```python
r = cloth.prepare("Curtain")                       # fabric from the class
r = cloth.prepare("Cape", fabric="wool")           # or name one
r = cloth.prepare("Flag", cls="hanging_sheet", pins=[0, 1, 2, 3])   # overrides
print(cloth.summarize(r))
```

```
  fabric cotton (Blender preset Cotton), area 2.52 m2, 24 edges from pins to the farthest point
  godot: mass 0.3528 kg, stiffness 0.75, precision 12, damping 1.0
  pins: 21 anchored to node
```

Fabrics: `silk cotton wool denim canvas leather rubber`. Anchors, decided from the
class and skinning: `node` (follows the mesh node - static props, a flag on a
moving ship), `bone` (each pin follows its strongest bone - worn cloth), `none`.

Report `GUESSED` items to the user. Guessed pins on a sheet touching nothing are
the top edge by gravity - often right, never checked.

**2. Preview (optional).** Blender's own cloth sim with the fabric's Blender preset:

```python
print(cloth.summarize_preview(cloth.preview("Curtain", frames=90)))
```

It is a reference, not a prediction: Blender's solver has bending springs and
Godot's has none, so a leather cape that holds its shape here will hang limper in
Godot. It leaves a `FollowThrough Cloth` modifier, which export disables while writing.

**3. Colliders.** Godot needs collision for anything cloth should rest on or wrap.
Name those objects with the importer's suffixes (see the `blender-to-godot` skill):
`Table-col` (static, concave), `Pole-convcol` (convex, can move). A worn cape needs
capsule colliders on the body's bones, which you add in Godot.

**4. Export and read back.**

```python
m = export.export(r"C:/proj/assets/cloth/curtain.glb", ["Curtain", "CurtainRod-col"])
print(export.summarize(m))
```

```
curtain.glb: PASSED
  Curtain: hanging_sheet, 525 vertices in file, pins 21/21 found on 21 vertices (0 split by seams)
```

`PASSED` means every spec reached the file and every pin lands on a vertex in it.
**Do not ship a FAILED export** - in Godot it is cloth that falls.

## Godot

**5. Install the runtime** into the project once:

```bash
cp -r "${CLAUDE_PLUGIN_ROOT}/godot/addons/follow_through" <project>/addons/
```

**6. Build the cloth** where the imported scene is instanced, after it is in the tree:

```gdscript
const FollowThrough = preload("res://addons/follow_through/follow_through.gd")

func _ready() -> void:
    var curtain := preload("res://assets/cloth/curtain.glb").instantiate()
    add_child(curtain)
    for rep in FollowThrough.apply(curtain):
        if not rep["built"]:
            push_warning("%s: %s" % [rep["node"], rep["problems"]])
```

Each built report carries `body`, the `SoftBody3D`. `body.teleport(delta)` moves a
cloth without it swinging (respawns).

**7. Verify - always, before calling it done.**

```bash
godot --headless --path <project> --import
godot --headless --path <project> -s res://addons/follow_through/verify_cloth.gd -- scene=res://assets/cloth/curtain.glb tune=true
godot --headless --path <project> -s res://addons/follow_through/verify_cloth.gd -- scene=res://assets/cloth/curtain.glb move=1.5,0,0
godot --headless --path <project> -s res://addons/follow_through/verify_cloth.gd -- scene=res://assets/hero.glb bend=chest,x,40
```

One `FT_RESULT {json}` line per cloth, then `FT_SUMMARY ... PASSED|FAILED`; exit code
0 only when all pass. `colliders=auto` (default) gives every unskinned non-cloth mesh a
trimesh collider and lists the skinned ones it skipped (`FT_NOTE`); `colliders=none`
tests the cloth alone. `set=damping_coefficient:1.5,linear_stiffness:0.7`
tries values without re-exporting. `tune=true` doubles precision until stretch passes
and reports `recommended_simulation_precision` - write it back in Blender with
`cloth.set_params("Curtain", simulation_precision=24)` and re-export.

| check | limit | failing means |
|---|---|---|
| `pins` | all found | the spec does not match the imported mesh - re-export |
| `pin_error_m` | 0.005 | pins not holding once still |
| `pin_lag_m` | reported | one tick behind a moving anchor is expected: speed / 60 |
| `stretch_p95` / `stretch_max` | 1.10 / 1.35 | too few substeps - raise precision (`tune=true`) |
| `seams` | 0.001 m | seam twins not at identical positions - weld in Blender |
| `settled` | 0.25 m/s, or a quarter of the swing after a move | instability (stiffness too high) or too little damping |

## Rules

Every one of these was measured in Godot 4.7.2 with Jolt or in the exported file.

**Stiffness belongs in 0.7-0.8, not near 1.** Godot's Jolt cloth has no bending
constraints, and a near-rigid sheet with no way to bend has nowhere to put energy.
A pennant hanging from its top edge was still fluttering at 3.2 m/s after 8 s at
stiffness 0.9, and at 7.6 m/s after 5 s at 1.0, rising above its own pins; a curtain
at 0.95 with precision 30 reached 17 m/s. At 0.75, with cotton's damping of 1.0, it settled to 0.003 m/s. Below 0.5 it stretches: a banner's
worst edge reached 1.42x at 0.3.

**Damping is a rate per second, and it is the air.** Not a 0-1 fraction: values above
1 are accepted and work. A free sheet given 2 m/s kept 35% per second at 1.0 and
stopped within 2 s at 3.0. Godot's default 0.01 left a cape's hem swinging at 0.54
m/s after 8 s; 0.3 left a scarf at 3 m/s six seconds after its anchor stopped. It
also caps fall speed at gravity / damping - 4.9 m/s at 2.0 - which for cloth is
about right anyway.

**Precision is substeps, and stretch is its symptom.** Tension crosses about one
edge per pass, so `prepare` starts at ceil(edges from pins to the farthest point / 2),
which held stretch p95 at or under 1.03 on every sample. Stiffness does not fix
stretch that precision causes: at precision 1 a test sheet hung to 1.465 m against
0.527 m at 5, with the same stiffness.

**Set every property before the body enters the tree.** Under Jolt,
`linear_stiffness`, `simulation_precision` and `shrinking_factor` set afterwards are
silently ignored - three values of each gave the identical sag. The runtime
configures, then adds.

**Pins are driven, not attached.** `set_point_pinned(i, true, path)` attachments are
applied from `RenderingServer.frame_pre_draw`, which never fires headless: every
attached pin stood still in automated tests while its node moved away. The runtime
moves pinned points itself each physics tick with `soft_body_move_point`, headless or
not, one tick behind the anchor (measured lag = speed x 1/60 exactly).

**The body lives in world space.** The node's transform on entering the tree places
the points, then resets to identity; moving the node afterwards teleports every
point. The runtime bakes the mesh to world space, skinned through the current pose,
and makes the body `top_level` so a moving parent cannot drag it.

**Pins are positions, because indices do not survive.** Godot's editor importer
reordered a banner's vertices (5 of 182 kept their index) and UV seams split one
vertex into two. Every vertex within tolerance of a pin position is pinned, seam
twins included; Jolt welds vertices at identical positions, so seams do not tear
(gap 0.0000 m) - but twins even 0.5 mm apart tore 1.95 m apart.

**A skinned mesh is exported in world space.** glTF ignores a skinned node's own
transform, so Blender's exporter bakes the object's world matrix into the vertices:
a cape on a rig at x=11 was written at x=10.75. Mesh-local pin positions all missed
until `spec.pins_block` applied the same transform. The read-back is what caught it.

**Flat shading doubles the vertices.** A curved flat-shaded cape went from 209 Blender
vertices to 396 in the file; a skirt from 416 to 832. They weld and simulate the
same (a cape's hem settled 0.555 m/s smooth, 0.543 flat, at equal settings), but the cloth renders faceted.
Shade cloth smooth.

**One material, no shape keys.** `SoftBody3D` simulates surface 0 only - a second
material is a second surface that does not move; export flags it. A mesh with blend
shapes fails `add_surface_from_arrays`; the runtime strips them.

**A skinned body needs bone colliders, not a mesh collider.** A trimesh of a skinned
mesh is frozen in one pose. With `bend=chest,x,40` the test cape's pins followed the
chest forward into the rest-pose body it no longer matched, and its worst edge
stretched to 7.8x its length. The verifier skips skinned meshes; in a real scene put
capsules on the bones (`BoneAttachment3D` + `AnimatableBody3D` + `CapsuleShape3D`).

**Stand colliders about 2 cm proud of what is drawn.** Cloth collides at its points
but draws flat triangles between them, and those cut corners. On a collider matching
the visible table, the rim and top showed through the tablecloth in patches, and
capsules 2 cm inside a body hid a column of a cape so it looked torn. Grow convex
shapes along their normals and size capsules at body radius + 2 cm.

**Never push a pinned point.** `soft_body_apply_point_impulse` on a pinned point fails
with an error per point per tick. Check `PhysicsServer3D.soft_body_is_point_pinned`,
not the pin list: vertices at one position share a physics point, so a vertex
nobody pinned can be pinned through its twin (the skirt's were).

**A moved `StaticBody3D` teleports.** The verifier's own colliders are
`AnimatableBody3D`: with static ones, `move=` carried the table away and left the
tablecloth falling through where it had been.

**Headless GodotPhysics3D is not a test.** Its soft bodies fall through obstacles
headless and collide windowed. Verify on a Jolt project.

## Limits

- Godot cloth cannot bend-resist: leather and canvas differ from cotton in mass and
  damping only. For stiff cloth that must hold a shape, use bones (strands, not built).
- No self-collision and no cloth-on-cloth under Jolt: layered garments pass through.
- The render mesh is the sim mesh. Keep cloth under a few thousand vertices; there is
  no proxy yet.
- A worn cape needs body colliders added in Godot - Blender contacts are recorded in
  the spec (`collision.touching`) but not turned into shapes.
- `drag_coefficient` is written through untested; wind (`Area3D`) is untested.
