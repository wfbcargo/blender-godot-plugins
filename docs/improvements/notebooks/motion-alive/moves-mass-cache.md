# moves-mass-cache: the body is measured once, not once per clip

The `moves` regression the 2026-09-20 benchmark caught, fixed. That benchmark is the reason
this branch exists: three cold builds came in at 93.3 / 73.1 / 90.8 s against a 30 s goal and a
42.2 / ~41 / 41.7 s baseline, and the agent that ran it located the cost rather than guessing at
it - a per-role probe gave Idle 6.12 s, Walk 5.27, Run 4.92, TurnL 4.85, TurnR 4.82, but Crouch
0.88 and Jump 0.86. The five expensive roles are exactly the ones that reach the upper chain.

## What it was

`mass.body_mass` caches on the `motion.Body` it is handed:

    got = body.__dict__.get("_mass_data")

and that is a correct cache for one clip. But **every role builds its own Body** - `actions.py`
constructs one in five places and `locomotion.py` in two - so the cache was empty every time, and
`body_mass` fell through to:

    got = load(body.rig.name) or measure(body.rig.name)

`load` reads the stamp `mass.stamp` writes. **Nothing in the repo calls `stamp`** - checked with
a grep across all plugins - so `load` always returned None and `measure` ran: the 300k-voxel
solve, seconds each time, on a skin and a skeleton that had not changed between roles.

## Measured, before and after

`probe_measure_calls.py` opens `belle_realistic.blend`, wraps `mass.measure` in a counter, and
authors Belle's real seven-role set. The count is the honest number here - it is the same on
every machine, where seconds are not.

| | main | this branch |
|---|---|---|
| `measure()` calls | 4 | **1** |
| seconds inside `measure()` | 7.32 | **1.69** |
| `move_set` total | 18.42 s | **12.28 s** |
| bodies cached | 0 | 1 |

Four, not seven, because Belle's Crouch, CrouchWalk and Jump never reach the upper chain - which
is the same split the benchmark's per-role probe found from the other direction.

**5.6 s off one character's `moves` stage, 33% of it.** A benchmark body with TurnL and TurnR has
five upper-chain roles rather than four, so it should gain more.

## Why a process cache and not the stamp

The stamp exists, is designed for exactly this, and would survive into the saved .blend - so it
looks like the obvious answer. It is not, because of one line in `export.py`:

    "export_extras": True,

Object custom properties become glTF node extras, which is deliberate and load-bearing -
follow-through's spec rides that channel, and "a mesh exported without extras arrives in Godot
with nothing to make it move". Stamping would therefore write a per-bone mass, centre-of-mass and
inertia table for ~57 bones into **every glb the pipeline ships**. A process-level memo costs
nothing on disk, cannot go stale inside a file somebody opens next month, and a build is one
Blender process authoring all of a character's roles, which is exactly the lifetime wanted.

## The key, and the control

A cache is only as good as its invalidation, so that is what the fixture checks - not the speed,
which would be a different number on every machine.

`_fingerprint` hashes what `measure` actually reads: the rig's bone count and world scale, and
for every deforming mesh its name, vertex and polygon counts, **every vertex coordinate**, and its
vertex group names. The coordinates are in there deliberately. The flesh stage moves a body
without changing a single count, and a mass model taken before that move would be wrong in a way
nothing downstream would notice - a silently stale inertia tensor is worse than a slow build.

`rigify_human`'s `mass_cache` block runs two cases that move the SAME vertex by the same 5 cm and
differ only in whether the key may notice:

- `keyed_on_the_body` - measures once for two unchanged bodies, and measures again after the edit.
- `control_pinned_key` - **the control that must fail.** `_fingerprint` is held at a constant,
  which is precisely the bug a careless key would have, and it serves the stale mass for a body
  that has changed. Its verdicts are False in the golden, so the check fails both if invalidation
  breaks and if the control ever stops working.

## What it did not change

Nothing. This is a pure cache: `regress --quick --jobs 4` on the cache alone, before the fixture
check was added, left every golden where it was, `rigify_human` included - the fixture that
carries the head rung, the asymmetry draw and the mass model itself.

## Open

- The `moves` stage is still the most expensive one. Two of the benchmark's three suggestions are
  untouched here: a draft quality for the move set (`quality.py` says outright that rig-anything's
  move set "is not yet cheaper in draft", so a preview build pays the full final price), and not
  charging an Idle or a turn for the gait report's Fourier phase and angular-momentum pass, which
  is most of what those roles cost.
- The cache is keyed per process. Two characters in one process each measure once, which is
  correct; nothing is shared between builds, which is also correct, since the stamp is the only
  thing that could persist and it may not.
- `_fingerprint` reads vertex group NAMES but not their weights. Within a build the weights are
  settled before `moves` runs, so this cannot bite today; a stage that rewrote weights without
  moving a vertex would need the key widened.
