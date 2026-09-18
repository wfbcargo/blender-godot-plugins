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
| `ft_strand_type` | optional type (`ponytail`, `long_hair`) - humanform writes the preset's; else the name, else `ponytail` |

Without a centreline, each loose part of the mesh is one chain, and its line is derived: surface
(edge) distance from the part's vertices nearest the root bone, and the centroid of each 1.5 cm band
of that distance. A principal axis cuts across the curl where a ponytail leaves the scalp; the bands
follow it. On the fixture's tube the derived line lands within 1.4 cm of the given one (tip 8 mm, root
7 mm).

A line that carries no chain - fewer than two points, or a whole line shorter than a micron - is
warned about and skipped. If that leaves no chain at all, `prepare` returns `{"error": "<obj>: no
usable centreline - ..."}` carrying those warnings, **before** it touches the rig: the chains the
object already has, its spec and its vertex groups stay exactly as the last good run left them, and a
good line afterwards rebuilds the same bones. A malformed `ft_centreline` is a failed call like every
other `prepare` failure, never a stripped rig and never a traceback.

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
  `ft_role = "strand"` so rig-anything's body map leaves them out and `ft_strand_owner = <object>`.
  Re-running `prepare` removes only the bones that object owns (or, for a renamed object, the ones its
  old spec lists and no other object owns), so re-preparing `Pigtail` leaves `Pigtail.001`'s chain alone.
  A name another object's chain already holds - `Pigtail.001` and `Pigtail_001` both make
  `ft_strand_Pigtail_001`, chain 0 of a two-chain `Hair` is `ft_strand_Hair_0` like the one chain of
  `Hair_0` - is not taken over: the later object gets `_v2` (`_v3`...) and a warning. Fixture
  `strand_ponytail` prepares all five and re-prepares them: 30 strand bones, unchanged, each object
  owning every bone its spec names.
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

A character built by character-pipeline names its strand file in its `.moves.json`, so a controller
needs no path of its own: `FollowThrough.attach(body, load(manifest["strands"][0]))`. Its chain bones
are already on the body's rig (`bones_added` 0), because the body was exported from the rig that
carries them.

Per chain, root to tip, in fixed steps of 1/120 s (as many as fit in a frame - at most 16, so a
stalled frame drops the time it cannot afford instead of costing 90 steps and stalling the next one -
the remainder carried, the animated parent and colliders interpolated to each step's moment):

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
strands at the head, 4 s of the run clip, and one stalled 0.75 s frame in the middle of the run
followed by half a second at the rate again. Head penetration is measured against the body's own
skin, not the colliders: strand vertices are skinned on the CPU and compared with the head skin's
radius per direction (24 x 48 cells) in the head bone's frame, counting only depth beyond what the
vertex had at rest.

| check | limit |
|---|---|
| `rest_drift_deg` | 0.5 |
| kick: last 0.5 s of 4 s | under 10% of the peak (or 0.1 deg) and under 2 deg |
| `fling_head_penetration_m`, `run_head_penetration_m`, `hitch_head_penetration_m` | 0.005 |
| `swing_deg` (tip deflection in the root bone's frame, running) | at least 3 |
| `hitch_steps` (the substeps a 0.75 s frame simulated) | at most `MAX_STEPS`, 16, with the rest dropped |
| finite | no non-finite state or pose |
| across rates | `swing_deg` max / min at most 1.25 |

`set=damping_ratio:0.3,...` overrides spring values; `dump=<file>` writes the joints per frame of the
fling and the run for rendering.

Measured (follow-through strands, Godot 4.7.2):

| body | rates | rest drift | kick settle (to 10%) | fling pen. | run pen. | hitch pen. / peak | swing peak / mean | spread |
|---|---|---|---|---|---|---|---|---|
| Figure (Rigify fit) | 30-240 | 0.02 deg | 1.47-1.50 s | 1.3 mm | 1.3 mm | 1.3 mm / 22 deg | 13.2-13.4 / 8.5-9.0 deg | 1.014 |
| MPFB woman | 30-240 | 0.02 deg | 2.23-2.25 s | 1.7-1.9 mm | 3.6-3.7 mm | 3.8-3.9 mm / 32-33 deg | 35.0-36.7 / 18.8-20.0 deg | 1.050 |
| Nadia, `preset = "ponytail"` | 30-240 | 0.02 deg | 1.87-1.88 s | 0.2 mm | 1.1-1.2 mm | 0.4-0.5 mm / 24-25 deg | 32.6-35.2 / 19.4-21.6 deg | 1.079 |

The last row is the first ponytail the *hair layer* grew rather than `samples.add_ponytail`: a crowd
woman from `grungist-creek/characters/nadia.toml` given `[hair] preset = "ponytail"` and a Run, built
through character-pipeline in scratch (0.32 m, 5 bones, 1.08-2.42 Hz) and played from the pipeline's
own two glbs. It costs 85-354 us a frame (240 down to 30 fps).

The 0.75 s hitch frame is 90 steps' worth of time; 16 are simulated and 74 dropped on both bodies, and
no other number moves, because the cap only engages on a frame longer than 0.13 s.

The checks fail when they should: with collisions off (`set=collision_margin_m:-1`) the fling puts a
strand 15-16 cm into the head on both bodies (11.9 cm on Nadia); with `max_angle_deg:0` the knock moves
nothing; without the seed the hitch frame puts the MPFB strand 6.0-6.2 mm into the head (below).

**The head's surface is read between cells.** `_depths` compares each strand vertex with the head
skin's radius in its own direction, and that radius used to be the nearest cell's. The map is built
from everything weighted to the head bone, which on a haired character includes the hair - and where
the tie a ponytail is gathered in stands off the skull, one cell holds the tie (15.3 cm from the head's
centre) and the next the bare skull (13.3 cm). The ponytail's own root sits on that step: running,
Nadia's worst vertex moved 3 mm in the head's frame and the verdict moved 20 mm, from 12 mm outside her
head to 8.6 mm inside it, and the run failed. That is the step, not a penetration - nothing about the
runtime changed the number (a collider margin from 0 to 30 mm, and the strand's own radius from 2 to
60 mm, left it at 8.6 mm to four decimals). Read between the four cells round the direction, the same
run measures 1.1-1.2 mm and the collisions-off control still reports 11.9 cm.

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
| a 0.75 s frame, steps uncapped | 90 substeps in one frame: a stall pays for itself twice | at most `MAX_STEPS` (16), the rest dropped |
| a 0.75 s frame, steps capped | the first kept step read the whole stall's motion of the body as one 1/120 s step: the MPFB strand hit its 60 deg root limit and went 6.0-6.2 mm into the head | the skipped time seeds each bone's target (`_seed`) instead of pushing it: 32-33 deg, 3.8-3.9 mm |
| the hair layer's own ponytail, run | 8.6 mm "into the head", unmoved by any collider or radius change: the head's surface was read from the nearest cell of a map that includes the hair tie, and the root sits on the 2 cm step between the tie's cell and the skull's | the surface is read between the four cells round the direction: 1.1-1.2 mm |

## Limits

- The sample figure's ponytail curls 49 deg between its first two bones at rest; running, the root
  bone lifts and the curl reads as a kink in side view. The MPFB ponytail reads smoothly.
- **A chain is a line.** humanform's `long_loose` curtain is a sheet 16 cm wide, and one chain down its
  middle twists it, running, into a wedge standing out of the shoulder: 2.9 cm into the head on the same
  woman whose ponytail measures 1.2 mm (`renders/loose_sprung.png` on the `hair-strands-integration`
  hand-off). character-pipeline therefore does not chain a curtain at all; it wants several chains across
  the sheet, or typing as the shell it is and routing to cloth.
- The verifier's 3 m/s knock throws the chain to its 60 deg root limit, where the first bone stands
  almost straight out of the tie and the hair reads as a wire with a gap under it. Nothing an animation
  does gets near it, and the run frames read as hair (`renders` on the `hair-strands-integration`
  hand-off), but a cut scene that whips a head that hard would show it.
- The modifier costs roughly 0.2-0.8 ms a frame per 5-6 bone chain in GDScript (noisy on a shared
  machine); a crowd needs fewer steps or native code.
- Colliders are the head and neck only; long hair over the shoulders and back is held off them only by
  the neck capsules, and a neck bone that carries the shoulders' skin (the figure's `spine.004`) is a
  wide sphere.
- A strand is one chain per centreline: no strand-strand collision, no twist, no wind.
- `regress.py --godot` does not run `verify_strands.gd` yet.
