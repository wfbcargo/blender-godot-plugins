# Cloth reference

Research behind the cloth library and the measurements that set its numbers.
Sources are listed at the end. Anything marked *unverified* has no primary source or
test behind it.

## How engines do cloth

| product | solver | notes |
|---|---|---|
| Blender | implicit mass-spring (Baraff & Witkin 1998) | `SIM_mass_spring.cc`; tension, compression, shear, bend springs; mass per vertex |
| Godot 4.7, GodotPhysics3D | port of Bullet `btSoftBody` | headless: soft bodies fall through obstacles (measured) |
| Godot 4.7, Jolt | substepped XPBD | `linear_stiffness` becomes compliance dt²(1/k-1)(w1+w2) for stretch and shear; `EBendType::None`, so no bend, no long-range attachments and no skinned constraints; `simulation_precision` becomes Jolt iterations, which are substeps; no soft-soft or self collision |
| Unreal Chaos Cloth | PBD, XPBD optional (experimental) | painted Max Distance, Backstop, Anim Drive; tethers; separate iteration and substep counts |
| NVIDIA PhysX cloth / NvCloth | position-based | per-phase stiffness, stretch limits, tethers, capsule, convex and triangle colliders |
| Unity Cloth | PhysX family | per-vertex max distance; sphere and capsule colliders only; tethers |
| Houdini Vellum | PBD | cloth, hair, grains and soft bodies in one solver |
| VRM spring bone / Godot `SpringBoneSimulator3D` | Verlet on bone chains | not physics, per the VRM spec; the cheap route for straps, hair and tails |

Godot 4.7 changed soft bodies incompatibly (PR #116041): `total_mass` now defaults
to 1 kg spread over the vertices, and the stiffness conversion was fixed. Tuning
values from 4.6 or earlier don't carry over.

## Authoring patterns in shipped games

- **Painted masks.** Artists paint per vertex how far each point may leave its
  animated position: Unreal's Max Distance, Unity's coefficients, Magica Cloth's
  fixed or move. follow-through's `ft_pin` is the binary form, since Godot pins
  are on or off.
- **Sim mesh vs render mesh.** Games usually simulate a low-poly proxy and skin the
  detailed mesh to it. Godot has no built-in proxy deformer, so follow-through
  simulates the render mesh and keeps it light.
- **Collision proxies.** Cloth collides with capsules and spheres on the body, not
  with the body mesh.
- **Teleport and reset.** Engines let you move cloth without it whipping
  (`ClothTeleportDistanceThreshold` in Unreal). Godot documents no such API; the
  runtime's `teleport()` moves every point.
- **Layers.** Stacked garments are constrained to each other instead of colliding,
  because cloth-to-cloth collision is expensive, and absent in Jolt.

## Classes and the usual choice

| class | usual pins | usual collision | usual runtime |
|---|---|---|---|
| hanging sheet | edge on prop | none or the pole | soft body; vertex shader in the background |
| draped sheet | shoulder line | body capsules plus backstop | soft body on a proxy, or a bone grid |
| draped tube | waist ring | leg capsules | soft body on a proxy, or radial bone chains |
| loose sheet | none | world | often baked; simulated here |
| strap | root | capsules | bone chain |
| tensioned | corners | little | stiff sheet plus wind; closed shapes use pressure |

No vendor publishes a formal taxonomy. This one is a synthesis of the engine docs.

## Fabric weights

Areal density in grams per square metre. These come from textile trade guides,
which are secondary sources.

| fabric | g/m² | follow-through uses |
|---|---|---|
| silk (chiffon to charmeuse) | 40-130 | 70 |
| cotton (lawn to poplin) | 60-160 | 140 |
| wool (suiting to coating) | 200-500 | 300 |
| canvas | 200-400 | 300 |
| denim (jeans) | 405-680 | 450 |
| leather | *unverified* | 900 |
| rubber sheet | *unverified* | 1000 |

Blender's shipped presets, read from `scripts/presets/cloth`:

| preset | quality | mass per vertex | tension = compression = shear | bending | damping | air |
|---|---|---|---|---|---|---|
| Silk | 5 | 0.15 | 5 | 0.05 | 0 | 1 |
| Cotton | 5 | 0.3 | 15 | 0.5 | 5 | 1 |
| Denim | 12 | 1 | 40 | 10 | 25 | 1 |
| Leather | 15 | 0.4 | 80 | 150 | 25 | 1 |
| Rubber | 7 | 3 | 15 | 25 | 25 | 1 |

There are no Wool or Canvas presets. follow-through interpolates both and says so.

## Measured in Godot 4.7.2 with Jolt

All runs used the sample bodies at 60 Hz, headless unless noted.

**Stiffness.** A pennant pinned along its top edge, damping 0.01, fastest point after 5 s (1.0 and 0.95 runs) or 8 s (the rest):

| linear_stiffness | fastest point at the end | note |
|---|---|---|
| 0.3 | 0.06 m/s | banner's worst edge stretched 1.42× |
| 0.5-0.8 | 0.06-0.08 m/s at damping 0.01 | stable |
| 0.9 | 3.2 m/s | fluttering |
| 1.0 | 7.6 m/s | rose above its pins |
| 0.95 at precision 30 | 17 m/s | curtain |

**Damping** (free sheet, zero gravity, 2 m/s impulse; velocity of the centre point):

| damping_coefficient | after 1 s | after 2 s | after 3 s |
|---|---|---|---|
| 0.3 | 1.10 | 0.76 | 0.62 |
| 1.0 | 0.58 | 0.20 | 0.07 |
| 3.0 | 0.08 | 0.00 | 0.00 |

**Sag vs precision** (1 m sheet, two corners pinned, lowest point; 0.5 unstretched):
precision 1 gave 1.465, 5 gave 0.527, 20 gave 0.503. Mass 1 kg or 10 kg gave
identical sag.

**Pins.** Attachment-path pins never moved headless, and lagged one tick windowed.
`soft_body_move_point` every tick tracked exactly, with a lag of speed / 60.

**Seams.** Vertices at identical positions stayed welded (gap 0.0000 m). Vertices
0.5 mm apart tore up to 1.95 m apart.

**Import.** The editor importer reordered vertices: 5 of 182 kept their glTF index.
Node extras arrived as `get_meta("extras")`, with nested dictionaries intact and
integers as floats. Custom `_` attributes were dropped. Blend shapes break
`SoftBody3D`.

**Export.** A skinned mesh is written with its world matrix baked in; an unskinned
mesh is written mesh-local. Flat shading splits vertices: a curved 209-vertex cape
became 396 in the file.

## Sources

- Baraff & Witkin 1998, Large Steps in Cloth Simulation - https://dl.acm.org/doi/10.1145/280814.280821
- Müller et al. 2007, Position Based Dynamics - https://dl.acm.org/doi/10.1016/j.jvcir.2007.01.005
- Macklin et al. 2016, XPBD - https://dl.acm.org/doi/10.1145/2994258.2994272
- Macklin et al. 2019, Small Steps in Physics Simulation - https://mmacklin.com/smallsteps.pdf
- Kim, Chentanez & Müller-Fischer 2012, Long Range Attachments - https://dl.acm.org/doi/10.5555/2422356.2422399
- Jakobsen, Advanced Character Physics - https://www.cs.cmu.edu/afs/cs/academic/class/15462-s13/www/lec_slides/Jakobsen.pdf
- Godot Jolt soft body, 4.7.2-stable - https://github.com/godotengine/godot/blob/4.7.2-stable/modules/jolt_physics/objects/jolt_soft_body_3d.cpp
- Godot PR #116041 - https://github.com/godotengine/godot/pull/116041
- Godot, Using SoftBody3D - https://docs.godotengine.org/en/stable/tutorials/physics/soft_body.html
- Jolt SoftBodySharedSettings.h - https://github.com/jrouwe/JoltPhysics/blob/master/Jolt/Physics/SoftBody/SoftBodySharedSettings.h
- Blender cloth RNA and presets - https://github.com/blender/blender/blob/main/source/blender/makesrna/intern/rna_cloth.cc, https://github.com/blender/blender/tree/main/scripts/presets/cloth
- Unreal Clothing Tool - https://dev.epicgames.com/documentation/en-us/unreal-engine/clothing-tool-in-unreal-engine
- Unity Cloth - https://docs.unity3d.com/Manual/class-Cloth.html
- PhysX 3.3.4 Cloth - https://archive.docs.nvidia.com/gameworks/content/gameworkslibrary/physx/guide/3.3.4/Manual/Cloth.html
- VRMC_springBone - https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_springBone-1.0/README.md
- Houdini Vellum - https://www.sidefx.com/docs/houdini/vellum/
- Proxy Asset Generation for Cloth Simulation in Games (SIGGRAPH 2024) - https://dl.acm.org/doi/10.1145/3658177
- Fabric weight guides (secondary) - https://minervapatterns.com/blog/fabric-weight-gsm-and-what-it-means-for-garments
