# blender-godot-plugins

[Claude Code](https://claude.com/claude-code) plugins for making 3D characters and creatures in
Blender and putting them in a Godot 4.7 game, by [Paul Lovy](https://paullovy.com).

## Install the marketplace

```
/plugin marketplace add wfbcargo/blender-godot-plugins
```

Then install a plugin from it:

```
/plugin install rig-anything@blender-godot-plugins
```

> **Moved from `PaulClaudePlugins`.** These plugins used to be listed in the
> `paul-claude-plugins` marketplace. If you installed one from there, add this marketplace and
> reinstall it as `<plugin>@blender-godot-plugins`. `claude-architect` and `claude-boundaries`
> stay in [PaulClaudePlugins](https://github.com/wfbcargo/PaulClaudePlugins).

## How they fit together

```
humanform  ->  rig-anything / animate-anything  ->  follow-through  ->  wardrobe  ->  lookdev
                              character-pipeline: one spec, all of the above, in order
 a body         a rig and its moves                 flesh and cloth     clothes       light it
```

A body from `humanform` (or any mesh) is rigged and given moves by `rig-anything`;
`animate-anything` builds on its engine for actions beyond walking. `follow-through` adds what moves on its own -
jiggle bones, cloth, soft volumes - and `wardrobe` dresses the body on top of that flesh. Everything
exports to glTF, is read back to check it, and ships with Godot-side runtimes and headless
verifiers. `lookdev` lights the scene they end up in, and `godot-lsp` gives Claude code
intelligence on the GDScript that drives them.

## Plugins

### [`rig-anything`](./plugins/rig-anything/)

Rigs and animates an arbitrary Blender mesh — including shapes no template
covers.

Auto-rigging asks two questions and the literature mostly answers only the
first: *where are the joints*, and *what do they do*. This splits the work by
what each side is good at. Deterministic Python measures the geometry; **vision
classifies it from rendered silhouettes**, because geometry alone cannot tell a
dog from a table and counting ground contacts cannot tell front from back. A
skeleton is then fitted from a template where one fits, built from a discovered
Reeb graph where none does, bound with bone-heat weights, and given a looping
gait for any number of legs — or a travelling lateral wave for a body with none.

Walks, trots and sprints are **derived from ground contacts**: a plane is
fitted through the skin that touches the floor, one Froude number sets the
speed, and stride, time on the ground, footfall pattern and each leg's reach on
that plane follow from published animal-locomotion relationships. A quadruped
gallops with its legs at full stretch; a hexapod runs tripods with flight.

Most of the code is there because **generated rigs fail quietly**. A wrong
rotation sign still plays. A foot six millimetres through the floor still
renders. An action bound to no slot reports stride 0.0000 and a loop seam of
0.000000 — not a failure that looks like a failure, but one that looks like the
best clip the generator ever made. So bone axes are probed per bone, a stale rig
errors instead of returning zeros, and export reads the written glTF back to
check the duration it actually wrote. See the
[plugin README](./plugins/rig-anything/README.md).

### [`animate-anything`](./plugins/animate-anything/)

Whole-body actions beyond the walk cycle — crouch, crouch walk, slide, and the
ways out of a slide — plus a full playable move set of walk, trot and sprint —
for any rigged creature. Requires `rig-anything` 0.8.0.

A walk can let a foot slide a little. These cannot: they are defined by
**contacts**, so poses are built from where each foot and hand goes and the
joints are solved, never from rotation signs. Any rig is first mapped to one
body of spine, neck, head, tail, legs and arms — from structure, since four
naming schemes and a spine rooted at the neck turned up in one project — and
actions are written in fractions of that body. Poses are values that blend, so
a slide recovery is slide → deep crouch → stand, and each new clip is measured
to start exactly where the one before it ends. Every clip is played back through
Blender and checked for drift, skating, folding, skin through the floor and
balance. See the [plugin README](./plugins/animate-anything/README.md).

### [`lookdev`](./plugins/lookdev/)

Lighting and shading for Godot 4.7 scenes built with Blender assets.

An agent can't judge lighting from one screenshot, and Godot never reports a
scene as badly lit, because flat and washed-out is still valid. So lookdev
**renders a scene off-screen and measures it**: exposure percentiles, clipping,
colour cast, and the key-to-fill ratio in stops, read off an 18% grey probe by
surface normal. Frame-wide contrast turned out to measure composition, not
lighting. Scenes and Blender materials are linted for the mistakes that make 3D
look like CG. Five lighting presets were calibrated by that same measurement in
both light-unit modes. Variants are compared side by side in both orders,
because vision judges pick a side about a quarter of the time.

The Blender half finds what the glTF exporter silently drops (procedural
textures, ramps, bump) and what Godot ignores on import (clearcoat, sheen,
transmission). It bakes the former into the one texture layout both read, and
exports with settings checked by reading the file back. Several findings
are written up because the docs don't say them: `ambient_light_energy` does
nothing for sky ambient, and a minimized Godot window renders no frames. See
the [plugin README](./plugins/lookdev/README.md).

### [`follow-through`](./plugins/follow-through/)

Secondary motion for Blender assets headed to Godot 4.7: the parts nobody
keyframes, recognised, specified and made to move. Cloth ships first; strands and
soft volumes are next.

A router skill **measures a mesh and classifies it** by the dimension of what
moves (a strand, a shell, a volume) and by how it hangs: a flag on a pole, a cape
on a body, a skirt round a waist, a tablecloth on a table. It is scored on sample
bodies with known answers, and scores the same with every name stripped. The
cloth library pins the sheet from what holds it and writes one JSON-schema'd spec
that glTF carries as node extras. Pins travel as **positions**, because Godot's
importer reorders vertices and UV seams split them, and the export is read back
so a pin that misses fails before it reaches the engine. In Godot a runtime builds
the `SoftBody3D` and a headless verifier measures pin error, stretch, seams and
settling. Its fabric values were measured rather than borrowed from Blender,
whose presets don't convert: under Jolt the cloth has no bending, stiffness above
0.9 flutters indefinitely, and damping is a per-second rate standing in for the
air. See the [plugin README](./plugins/follow-through/README.md).

### [`humanform`](./plugins/humanform/)

Adult human bodies in Blender, built in layers with a measured gate between
every one — the body the other plugins start from.

A brief ("a 28-year-old woman, 1.70 m, curvy") is resolved against **ANSUR II**:
6,068 measured adults as a multivariate normal per sex over 65 variables,
conditioned on what the brief fixes, so every measurement it doesn't name is the
one people like that actually have. MPFB2 then builds the mesh, and a
Levenberg–Marquardt solve over its macros and sixteen fine targets fits it to
those landmarks — heights, segment lengths, widths, and girths *with* their
breadths and depths, because girth alone answered every waist with a pregnant
belly.

`humancheck` is the gate, and it is the reason the ladder works: it measures a
body in its rig's rest pose, renders a fixed orthographic contact sheet in clay,
normals and silhouette with target and measured landmark lines, and hands both
to a critic subagent that **writes its questions before it looks**. `humanlib`
makes the next body cheap: a library indexed by ANSUR z-scores and critic-written
tags, reuse in under a second, faces, hands, feet and eyes as parts that move
between bodies without stitching, and verdict statistics that steer later designs
away from what critics keep rejecting. See the
[plugin README](./plugins/humanform/README.md).

### [`wardrobe`](./plugins/wardrobe/)

Layered clothing for rigged Blender characters headed to Godot 4.7 — a garment
that fits, never shows the body through it, and swings where it hangs free.

A garment is **cut from the body it will be worn on**, so it inherits that
body's own skin weights — `follow-through`'s jiggle bones included, and a shirt
therefore follows the flesh under it with no extra work. It is then eased off
the skin by a relax-and-push loop that bridges hollows and lets cloth hang
straight from the widest point above rather than tucking under a buttock. What
hangs free is sprung: a ring of bones around the hem and each cuff, each with an
inward backstop measured from its rest gap.

The skin underneath is **not drawn** — but only where the cloth is skinned like
the skin under it, because a thigh under a hem hung from the torso swings out
from beneath it. In Godot one call adds the garment's bones to the body's
skeleton, rebuilds the body without the covered triangles and springs the hem;
a headless verifier skins every vertex from the final pose and ray-casts along
each body normal to count holes and skin through the cloth over a walk. See the
[plugin README](./plugins/wardrobe/README.md).


### [`character-pipeline`](./plugins/character-pipeline/)

A whole character from one TOML spec: a humanform body from a brief, baked, with hair, follow-through
flesh, rig-anything's move set and wardrobe garments, exported for Godot.

Each stage checks the file before it runs, so garments before moves or flesh after garments refuse
and name the order. Each stage records what it was built from in the .blend, so a rebuild skips what
has not changed and a fresh Blender session resumes from a saved file. Tuned numbers live in the
plugins that own them (gait styles, flesh limit shares, garment presets), so a new character is a
description, a style and an outfit. See the [plugin README](./plugins/character-pipeline/README.md).

### [`godot-lsp`](./plugins/godot-lsp/)

GDScript code intelligence — hover, go-to-definition, find-references, symbols
and diagnostics on `.gd` files, answered by Godot's own analyser.

Godot ships a real language server, but it only listens on **TCP**, while Claude
Code runs every LSP server over **stdio** — the `transport: "socket"` setting is
accepted and then ignored, so the two never meet on their own. This is the
missing pipe: 55 lines, no dependencies, no build step, since Godot already uses
the same `Content-Length` framing and the bytes need no translation.

The one requirement is that the **Godot editor be open** — the language server
lives in the editor, not the engine, so there is nothing headless to talk to.
Hovering `Node` then returns the entire engine class reference. See the
[plugin README](./plugins/godot-lsp/README.md).

## Developing these plugins

The repository copy is canonical, but Claude Code loads skills from
`~/.claude/skills/`. Install one, or every plugin already installed there:

```
python tools/install.py wardrobe
python tools/install.py --all --dry-run
```

The installer mirrors the repo over the installed copy and records a hash of
every file it wrote, so a copy that was edited in place is **refused** rather
than silently discarded — move the edit into the repo, or pass `--force`. An
installed copy that is itself a git checkout is never overwritten.

That covers this machine only. For the others: push, then
`/plugin marketplace update blender-godot-plugins`.

Before changing anything shared, and before calling it done, run the fixtures:

```
python tools/regress.py --jobs 2
python tools/regress.py --quick --jobs 2      # optional; never a merge gate (CLAUDE.md)
```

Eight bodies are rebuilt from nothing in headless Blender: a woman from a seeded brief, a Rigify
biped, a dog, a rabbit, a cricket, a starfish, two fleshed figures, and a shirt cut onto one of
them. Every number is compared to `tests/golden/`. `--twice` builds each one again and requires
the two builds to agree, and `--godot` plays the exports through the engine-side verifiers. A fix
moves numbers; the point is that the move is seen on every fixture, not only on whichever character
was being built at the time. See [`tests/README.md`](./tests/README.md) and [`CLAUDE.md`](./CLAUDE.md).

## Layout

```
.claude-plugin/marketplace.json     # marketplace manifest
tools/install.py                    # repo -> ~/.claude/skills, edits refused
tools/regress.py                    # rebuild the fixtures, compare to goldens
tests/fixtures/                     # bodies built from generators and seeds
tests/golden/                       # what a build produced when it was last reviewed
plugins/
  godot-lsp/
    .claude-plugin/plugin.json
    .lsp.json                       # the gdscript server registration
    godot-lsp-bridge.mjs            # stdio <-> TCP pipe, no dependencies
    README.md
  rig-anything/
    .claude-plugin/plugin.json
    SKILL.md                        # the procedure, and the rules
    scripts/rig_analysis/           # measure, classify, fit, bind, gait, export,
                                    # bodymap, motion, keyposes, actions,
                                    # locomotion
    references/                     # archetypes, and which way each joint bends
    README.md
  animate-anything/
    .claude-plugin/plugin.json
    SKILL.md                        # whole-body actions on rig-anything's engine
    references/motion-grammar.md    # key-pose vocabulary; slide and climb plans
    references/contact-locomotion.md  # walk to sprint from ground contacts
    README.md
  lookdev/
    .claude-plugin/plugin.json
    SKILL.md                        # staged workflow, gates, Godot traps
    bin/lookdev.mjs                 # capture | lint | preset | compare runner
    godot/                          # GDScript run against the project
    blender/lookdev_blender/        # material lint, bake, export, reference renders
    presets/                        # lighting recipes and capture thresholds
    references/                     # light levels, PBR values, recipes, judging
    README.md
  follow-through/
    .claude-plugin/plugin.json
    skills/follow-through/          # recognise and route: family, class, pins
    skills/cloth/                   # the cloth library: fabrics, export, runtime
    schema/                         # the spec glTF carries as node extras
    scripts/follow_through/         # Blender: measure, classify, spec, cloth, export
    godot/addons/follow_through/    # SoftBody3D runtime and headless verifier
    references/                     # concepts from zero; cloth research and measurements
    README.md
  humanform/
    .claude-plugin/plugin.json
    skills/humanform/               # the build ladder and its gates
    skills/humancheck/              # measure, contact sheet, critic
    skills/humanlib/                # the library, parts, the one-call pipeline
    scripts/humanform/              # Blender: body, measure, views, scaffold, library
    data/                           # ANSUR II public CSVs, presets, the seed library
    references/                     # proportions, and the critic's question bank
    README.md
  wardrobe/
    .claude-plugin/plugin.json
    skills/wardrobe/                # cut, fit, skin, hem bones, cover, export
    scripts/wardrobe/               # Blender: rigmap, tailor, fit, cover, hem, spec, export
    godot/addons/wardrobe/          # equip/unequip/hide, hem modifier, verifier
    references/garments.md          # how engines dress characters, and what was measured
    README.md
```

MIT licensed.
