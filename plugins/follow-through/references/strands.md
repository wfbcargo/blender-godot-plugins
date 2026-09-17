# Strands reference

Ponytails and long hair as sprung bone chains: `scripts/follow_through/strand.py` in Blender,
`godot/addons/follow_through/strand_modifier.gd` and `verify_strands.gd` in Godot. What was measured
is on the fixture `tests/fixtures/strand_ponytail.py` (follow-through's `Figure`, Rigify-fitted) and
on a scratch build of the MPFB woman from `mpfb_woman_curvy`'s brief (Idle and Run), each with
`samples.add_ponytail`.

## The input contract

A strand is a separate mesh object marked by whoever made it (humanform's hair layer):

| property | meaning |
|---|---|
| `ft_type = "strand"` | `classify` routes it: family `strand`, class `strand`, route `spring_bones` - nothing measured |
| `ft_root_bone` | the bone it grows from (the head) |
| `ft_centreline` | optional: root-to-tip points, object-local |
| `ft_centreline_world` | the same in world space |
| `ft_centrelines` | several chains in one mesh (object-local lists) |
| `ft_strand_type` | optional type (`ponytail`, `long_hair`); else the name, else `ponytail` |

Without a centreline, each loose part of the mesh is one chain, and its line is derived: surface
(edge) distance from the part's vertices nearest the root bone, and the centroid of each 1.5 cm band
of that distance. A principal axis cuts across the curl where a ponytail leaves the scalp; the bands
follow it. On the fixture's tube the derived line lands within 1.4 cm of the given one (tip 8 mm, root
7 mm).

## Blender

```python
from follow_through import strand, samples
pony = samples.add_ponytail("Figure", "Figure_metarig")     # a test tube, marked as above
r = strand.prepare(pony.name)                               # chain, weights, spec
print(strand.summarize(r))
# the body through rig-anything as usual - its rig now carries the strand bones
rx.export_character("Figure", "Figure_metarig", ".../figure.glb", reports=moves, forward="-Y")
m = strand.export(".../figure_ponytail.glb", [pony.name], "Figure_metarig")   # rig-anything's export_glb, read back
```

`prepare`:
- **Bones.** The centreline resampled at equal arc length into `round(length / segment_m)` bones
  (3-8), `ft_strand_<object>_NN`, the first parented to the root bone, the rest connected, each tagged
  `ft_role = "strand"` so rig-anything's body map leaves them out.
- **Weights.** Each vertex's nearest point on the chain, in bone lengths `u`: the root bone at `u = 0`,
  each strand bone full at its middle and shared linearly with its neighbours between middles, the
  last bone full past its middle. At most two influences. Every bone weight the mesh had is replaced
  (a hair shell rigid on the head); the mesh gets an Armature modifier and the rig as object parent.
- **Springs.** Per bone the frequency of the hair hanging below its head as a compound pendulum,
  `f = sqrt(3 g / 2 h) / 2 pi` (a 38 cm ponytail: 0.99 Hz at the root, 2.2 Hz for the last 7 cm),
  damping 0.5, 60 deg limit at the root and 40 deg after.
- **Colliders**, from the skin whose strongest weight is the head or a neck bone (rig-anything's
  `head` and `neck` roles, or bone names):
  - head: an **ellipsoid** on the head bone's axes, centred on the middle of that skin's bounds with
    half the bounds as radii;
  - each neck bone: a **capsule** along the bone through the middle of its skin's bounds, radius the
    95th percentile of that skin's distance from the axis.

`strand.set_params(obj, damping_ratio=0.6)` changes every bone without rebuilding.

## Godot

```gdscript
const FollowThrough = preload("res://addons/follow_through/follow_through.gd")
var body := preload("res://assets/figure.glb").instantiate()
add_child(body)
FollowThrough.attach(body, preload("res://assets/figure_ponytail.glb"))   # mesh onto the body's skeleton
for rep in FollowThrough.apply(body, {"routes": ["spring_bones"]}):
    var strands = rep["body"]          # a SkeletonModifier3D; strands.kick(Vector3(0, 2, 0))
```

Per chain, root to tip, in fixed steps of 1/120 s (as many as fit in a frame, the remainder carried,
the animated parent and colliders interpolated to each step's moment):

1. the tail's offset from where its parent (animated for the first bone, sprung for the rest) puts it
   is a damped spring solved exactly over the step, loaded by that target's acceleration and the
   change of gravity in the parent's frame (as `jiggle_modifier.gd`);
2. the tail goes back on the bone's length and within `max_angle_deg` of the parent's direction;
3. four points along the bone (1/4, 1/2, 3/4, tail) are pushed out of every collider in reach, grown
   by the strand's radius there and a 4 mm margin - or, where the strand sits closer at rest (its root
   grows out of the scalp), to its rest gap, so nothing moves at rest and nothing goes deeper than it
   started;
4. velocity along the bone, past a limit or into a collider is removed, and sliding in contact loses
   `collision_friction` (0.1) per step.

## Verifying

```
godot --headless --path <project> -s res://addons/follow_through/verify_strands.gd -- \
    scene=res://assets/figure.glb strands=res://assets/figure_ponytail.glb
```

Time is stepped by hand (AnimationPlayer and Skeleton3D both in manual mode) at 30, 60, 120 and 240
fps, each on a fresh body: 1 s at rest, a 1.5 m/s sideways knock, a 3 m/s knock that throws the
strands at the head, and 4 s of the run clip. Head penetration is measured against the body's own
skin, not the colliders: strand vertices are skinned on the CPU and compared with the head skin's
radius per direction (24 x 48 cells) in the head bone's frame, counting only depth beyond what the
vertex had at rest.

| check | limit |
|---|---|
| `rest_drift_deg` | 0.5 |
| kick: last 0.5 s of 4 s | under 10% of the peak (or 0.1 deg) and under 2 deg |
| `fling_head_penetration_m`, `run_head_penetration_m` | 0.005 |
| `swing_deg` (tip deflection in the root bone's frame, running) | at least 3 |
| finite | no non-finite state or pose |
| across rates | `swing_deg` max / min at most 1.25 |

`set=damping_ratio:0.3,...` overrides spring values; `dump=<file>` writes the joints per frame of the
fling and the run for rendering.

Measured (follow-through strands, Godot 4.7.2):

| body | rates | rest drift | kick settle (to 10%) | fling pen. | run pen. | swing peak / mean | spread |
|---|---|---|---|---|---|---|---|
| Figure (Rigify fit) | 30-240 | 0.02 deg | 1.47-1.50 s | 1.3 mm | 1.3 mm | 13.2-13.4 / 8.5-9.0 deg | 1.014 |
| MPFB woman | 30-240 | 0.02 deg | 2.23-2.25 s | 1.7-1.9 mm | 3.6-3.7 mm | 35.0-36.7 / 18.8-20.0 deg | 1.050 |

The checks fail when they should: with collisions off (`set=collision_margin_m:-1`) the fling puts a
strand 15-16 cm into the head on both bodies; with `max_angle_deg:0` the knock moves nothing.

## What the verifier found

| run | what it showed | now |
|---|---|---|
| modifiers stepped inside one script call | nothing moved: Skeleton3D applies modifiers in its deferred update, not in `advance()` | one engine frame per step |
| sprung poses read after the frame | 0.03 deg of swing: poses are restored after skinning | read in `modification_processed` |
| one integration step per frame | run swing 33 / 55 / 100 / 105 deg at 30 / 60 / 120 / 240 fps; thrown at the head at 30 fps, 6 cm in | fixed 1/120 s steps: 1.014 |
| substeps of at most 1/120 s | 240 fps (1/240 s steps) swung 24% further than 60 | fixed steps |
| head sphere of the median skin radius | thrown forward, 1.1 cm into the head-neck fillet | ellipsoid |
| MPFB, capsule round the skin's centroid | 6.7 cm into the back of the head: the dense face pulled the centroid 5 cm forward | bounds centre |
| MPFB, capsule of the 95th percentile radius | 7-9 mm into the back of the skull (a head is deeper than wide) | ellipsoid |
| no contact friction | a ponytail resting on the neck gained swing every stride: tip 22, 30, 41, 49, 66, 74, 95 deg | friction 0.1 |
| damping 0.3 | MPFB: still 4.9 deg four seconds after a knock, 94 deg of swing running | 0.5 |
| a script error in the verifier | `FT_SUMMARY ... PASSED` with nothing measured | a rate without a measured run fails |

## Limits

- The sample figure's ponytail curls 49 deg between its first two bones at rest; running, the root
  bone lifts and the curl reads as a kink in side view. The MPFB ponytail reads smoothly.
- The modifier costs roughly 0.2-0.8 ms a frame per 5-6 bone chain in GDScript (noisy on a shared
  machine); a crowd needs fewer steps or native code.
- Colliders are the head and neck only; long hair over the shoulders and back is held off them only by
  the neck capsules, and a neck bone that carries the shoulders' skin (the figure's `spine.004`) is a
  wide sphere.
- A strand is one chain per centreline: no strand-strand collision, no twist, no wind.
- `regress.py --godot` does not run `verify_strands.gd` yet.
