# Volumes reference

Research behind the volume library and the measurements that set its numbers. Sources
are at the end. Anything marked *unverified* has no primary source or test behind it.

## How soft volumes are done

| method | what it is | good at | bad at |
|---|---|---|---|
| shape matching (Mueller et al. 2005) | particles pulled toward the best rigid (or linear) fit of their rest shape | unconditionally stable, cheap, plasticity is one line, no mesh needed | not physically derived; stiffness depends on the step; no damping of its own |
| clustered / lattice shape matching (Rivers & James 2007 FastLSM; NVIDIA FleX) | many overlapping clusters, averaged | local wobble, large deformation | clusters alone forget global shape; stiffness depends on cluster size |
| XPBD tetrahedra (Macklin & Mueller 2021, Ten Minute Physics) | edge and volume constraints on a tet mesh, substepped | physical parameters (E, nu), exact volume | needs a tet mesh; cost is tets x substeps |
| FEM flesh (Chaos Flesh, Ziva VFX, Houdini Vellum) | finite-element tissue, offline or low-res runtime | film-quality bulging, muscle and fat layers | far beyond GDScript in real time |
| pressure soft body (Matyka & Ollila 2004; Jolt `mPressure`) | a surface with a gas-pressure force P = nRT / V | balloons, inflation | no shape memory: without bend constraints it keeps volume, not form |
| vertex-shader wobble | a spring on the object's motion, displacing vertices | cheap background props | no contact, fixed modes |

## What Godot 4.7.2 gives

Read in `modules/jolt_physics/objects/jolt_soft_body_3d.cpp` at 4.7.2-stable:

- `settings->mPressure = pressure` - pressure is passed straight through, P = coef / V.
- Edges and shear get `mCompliance = mShearCompliance = inverse_stiffness`.
- `CreateConstraints(..., EBendType::None)` - **no bend constraints**.
- Volume constraints and long-range attachments are never populated.

So a closed `SoftBody3D` with pressure is a balloon with no shape of its own, and jello,
clay and slime need their own solver. This library is lattice shape matching in GDScript.

## The solver as built

Per physics tick, `n` substeps of `dt`:

1. Damp motion that is not rigid: estimate the body's linear and angular velocity (Mueller
   et al. 2007, PBD sec. 3.5) and scale only the rest by exp(-2 zeta w dt). While touching,
   rigid motion also decays at `rolling_resistance` per second.
2. Gravity and prediction: v += g dt, p = x + v dt.
3. Shape matching: every node owns a cluster (its lattice neighbours within
   `cluster_radius`); plus one cluster over the whole body. For each: centre, A_pq, the
   rotation R by Mueller et al. 2016's iteration warm-started from last tick; optionally
   the volume-normalised linear fit A / cbrt(det A) blended in by `squash`. Each node's goal
   is the average of its local clusters' goals, blended toward the whole-body goal by
   `global_stiffness`; p += alpha (goal - p).
4. v = (p - x) / dt, then contacts (below), then x = p.

After the substeps, plasticity (Mueller 2005 sec. 4.5): a cluster whose strain
||R^T A - I|| exceeds `yield` moves its nodes' rest positions toward the shape it is held
in at `creep` per second, scaled by (1 - yield / strain), capped at `max` of the body's size
from where they started; the rest shape is then rescaled to the render mesh's original
volume.

The render mesh follows its cell trilinearly, and normals transform by the cofactor of
each cell's deformation gradient.

### Contacts

Contact samples are chosen every tick from where the vertices are: in each lattice cell,
the vertices furthest along gravity and along the cell's outward axes. Each sample casts a
ray from its position at the start of the substep to where it is now; a hit places it back
on the surface it entered, plus a small radius. Samples that did not move into anything
fall back to a sphere overlap query. The push is shared to the cell's eight nodes by
trilinear weight (the largest per node, not the sum), moves positions only, removes
velocity into the surface (and small velocity out of it), and applies friction, static
below 5 cm/s. The full sweep runs on the first substep; later substeps re-test only the
samples that touched.

## Measured in Godot 4.7.2 with Jolt

A 0.3 m cube (8 subdivisions) unless noted, 60 Hz, headless.

**Frequency.** The body held at its base (bottom node layer pinned), top layer given 0.3
m/s sideways, zero gravity, no damping; zero crossings of the top-minus-bottom offset.

Before calibration, target 4 Hz on the node spring:

| resolution | global_stiffness | cluster radius | squash | measured |
|---|---|---|---|---|
| 2 | 0 | 1 | 0 | 0.93 Hz |
| 4 | 0 | 1 | 0 | 0.51 Hz |
| 4 | 0.3 | 1 | 0 | 0.63 Hz |
| 4 | 1 | 1 | 0 | 0.84 Hz |
| 6 | 0.3 | 1 | 0 | 0.50 Hz |
| 4 | 0 | 2 | 0 | 0.67 Hz |
| 4 | 0.3 | 1 | 0.5 | 0.54 Hz |
| 4 (target 8) | 0.3 | 1 | 0 | 1.26 Hz |

Linear in the target and independent of substeps, so alpha = 2(1 - cos w dt) is consistent
and the loss is geometric. Fitted: body stiffness k = (1 - g) 0.054 (2 / res)^1.73 + g 0.044,
frequency ratio sqrt(k) x (1 - 0.46 squash^2).

After calibration (target is the body's frequency):

| resolution | global | target | measured |
|---|---|---|---|
| 3 | 0.3 | 4 | 4.19 |
| 4 | 0.3 | 4 | 3.98 |
| 6 | 0.3 | 4 | 3.62 |
| 3 | 0.3 | 2 | 2.10 |
| 3 | 0.6 | 8 | 8.68 |
| 4 | 0 | 3 | 2.96 |

Sample assets with `verify_volume.gd tune=true`: jello cube 4.34 for 4.5; mounted jello
mould 5.88 for 4.5 (held by its whole base, tapered - recommended gain 0.59); water balloon
(squash 0.8) 2.93 for 3.0; before the squash term, 2.02.

**Shape memory.** Zero gravity, a poke: resolution 6 with small clusters only folded to
63% volume and stayed; with the whole-body cluster, 1.001.

**Contacts.**

| change | before | after |
|---|---|---|
| push into velocity -> position only | clay ball 7.5 m/s spikes, 6 cm into the floor | on the floor |
| fixed samples -> chosen per tick | cube's bottom 2.6 cm into the floor | 7-9 mm |
| overlap -> ray from the previous position | cube through a 10 cm convex slab | lands, rests 1 cm in |
| last substep only -> every substep | cube wanders 12 cm in 10 s, 0.5 m/s | rests at 6.07 cm for a 12 cm cube, 0 m/s |
| trimesh collider -> convex | every loose volume falls through the floor at 59 m/s | rests |
| no rolling resistance | balloon rocks on a flat floor | settles |

**Collapse.** Slime at 1 Hz, squash 0.9, global 0.15: sag g / w^2 = 25 cm on a 28 cm blob,
lattice folded to 4% of its volume. At 2.5 Hz with creep 5 /s: 0.98 after 10 s.

**Substep aliasing.** Clay at 8 Hz, squash 0.6: node spring 61 Hz, w dt = 6.39 rad at one
substep, alpha = 2(1 - cos 6.39) = 0.01 - the loop read "small enough" and stopped. 1% of its
volume. Choosing substeps from the angle: 8 substeps, 0.99.

**Plastic volume.** Summed cell determinants held at 1.000 while a clay ball's mesh lost half
its volume; rescaling against the embedded render mesh held 0.95.

**Final sample run** (`verify_volume.gd tune=true frames=600`, all PASSED):

| body | volume | inside | settle m/s | Hz / target | ms per tick | substeps |
|---|---|---|---|---|---|---|
| Jello (mounted) | 0.99 | 0 | 0 | 5.88 / 4.5 | 5.0 | 5 |
| JelloCube | 0.98 | 0 | 0 | 4.34 / 4.5 | 2.8 | 5 |
| ClayBall | 0.99 | 0.008 | 0.012 | 7.06 / 8 | 10.3 | 8 (limited) |
| SlimeBlob | 0.98 | 0 | 0.018 | 2.95 / 2.5 | 3.2 | 4 |
| WaterBalloon | 0.97 | 0 | 0.009 | 2.93 / 3 | 4.7 | 4 |
| Pudding (mounted) | 0.94 | 0 | 0 | 4.0 / 2.2 | 2.3 | 3 |

(ms per tick measured with all six running and the verifier's own sampling; alone, a
resolution-4 jello cube stepped in 0.8 ms plus 0.4 ms to rebuild its mesh.)

## Material data

| quantity | value | source |
|---|---|---|
| gelatin gel storage modulus G' | 2-10 kPa (5-10% w/v) | gelatin rheology, Int. J. Food Properties |
| gelatin loss factor | tan delta ~0.025-0.05, so zeta ~0.01-0.03 | derived from the same |
| fundamental of a block held at its base | f ~ c_s / 4H, c_s = sqrt(G / rho) | derived; an 8 cm cube at 2 kPa: 4.4 Hz |
| clay (plastic) | elastic 8-15 Hz, yield 2-5% strain, creep 5-20 /s | ranges from FleX plastic scenes and Houdini Vellum plasticity; *unverified* as clay |
| FleX plastic bunnies | plasticThreshold 0.0015, plasticCreep 0.15-0.30 per step | FleX demo scenes |
| water density | 1000 kg/m3 | - |
| clay density | 1800 kg/m3 | *unverified* |

## Sources

- Mueller, Heidelberger, Teschner, Gross 2005, Meshless Deformations Based on Shape Matching - https://matthias-research.github.io/pages/publications/MeshlessDeformations_SIG05.pdf
- Mueller, Bender, Chentanez, Macklin 2016, A Robust Method to Extract the Rotational Part of Deformations - https://matthias-research.github.io/pages/publications/stablePolarDecomp.pdf
- Mueller et al. 2007, Position Based Dynamics - https://dl.acm.org/doi/10.1016/j.jvcir.2007.01.005
- Rivers & James 2007, FastLSM - http://www.alecrivers.com/fastlsm/files/flsm.pdf
- Macklin & Mueller 2021, A Constraint-based Formulation of Stable Neo-Hookean Materials - https://mmacklin.com/neohookean.pdf
- Ten Minute Physics, soft bodies and skinning - https://matthias-research.github.io/pages/tenMinutePhysics/index.html
- Matyka & Ollila 2004, pressure model soft bodies - http://panoramx.ift.uni.wroc.pl/~maq/soft2d/howtosoftbody.pdf
- NVIDIA FleX API and demo scenes - https://github.com/NVIDIAGameWorks/FleX/blob/master/demo/scenes/softbody.h
- Coenen, FleX soft bodies - https://simoncoenen.com/downloads/flex_paper.pdf
- Houdini Vellum softbody plasticity - https://www.sidefx.com/docs/houdini/vellum/softbody_plasticity.html
- Unreal Chaos Flesh - https://dev.epicgames.com/documentation/en-us/unreal-engine/chaos-flesh-overview
- Jolt SoftBodyMotionProperties.cpp - https://github.com/jrouwe/JoltPhysics/blob/master/Jolt/Physics/SoftBody/SoftBodyMotionProperties.cpp
- Godot Jolt soft body, 4.7.2-stable - https://github.com/godotengine/godot/blob/4.7.2-stable/modules/jolt_physics/objects/jolt_soft_body_3d.cpp
- Gelatin rheology - https://www.tandfonline.com/doi/full/10.1080/10942910601128895
