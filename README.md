# PaulClaudePlugins

A [Claude Code](https://claude.com/claude-code) plugin marketplace by
[Paul Lovy](https://paullovy.com).

## Install the marketplace

```
/plugin marketplace add wfbcargo/PaulClaudePlugins
```

Then install a plugin from it:

```
/plugin install claude-architect@paul-claude-plugins
```

## Plugins

### [`claude-architect`](./plugins/claude-architect/)

A recursive multi-agent orchestration framework. One long-horizon orchestrator
decomposes work into epics / specs / implementations, runs each in an isolated git
worktree, and drives a review + spec-audit + architecture-audit + merge pipeline
before every squash-merge. Ships nine role-pinned subagents and the methodology
that ties them together.

Model and effort both follow role, not depth: model by whether a mistake is
*silent* (orchestration, architecture drift, merges, missed bugs stay top-tier),
effort by how much the agent must derive for itself (orchestrators `high`, leaves
`medium`). If you only have one model, point every agent at it and keep the
effort split — it applies to the highest-volume role, so most of the saving
survives. A `/architect` skill classifies each request and routes it, so
decomposition happens by default rather than by hope. See the
[plugin README](./plugins/claude-architect/README.md) and
[`ORCHESTRATION.md`](./plugins/claude-architect/ORCHESTRATION.md).

### [`claude-boundaries`](./plugins/claude-boundaries/)

Declare your architecture's layers, containers and contracts in one file; the
plugin turns it into a check that runs with **no project dependencies**, and
wires that check into hooks so every coding agent inherits the rules — stated at
session start, a violating edit handed straight back, and no turn allowed to end
while a violation stands.

Nine rules cover direction, layer skipping, declared edges, public surface,
purity, escaping relative imports, third-party imports, package-manifest
agreement and type-only edges, across two topologies (folders under one `src/`,
or workspace packages). A check that scanned zero files exits non-zero rather
than green, because a map pointing where the code isn't is a broken
configuration wearing a green tick. Projects with no map are unaffected: every
hook is a silent no-op.

The config is a strict superset of `claude-architect`'s `containers.yaml`, so
**one file serves both** — that plugin uses the map to *dispatch*, this one to
*enforce*. Neither requires the other. See the
[plugin README](./plugins/claude-boundaries/README.md).

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

## Layout

```
.claude-plugin/marketplace.json     # marketplace manifest
plugins/
  claude-architect/
    .claude-plugin/plugin.json      # plugin manifest
    agents/                         # the nine subagents
    skills/architect/               # the /architect entry point
    skills/seam/                    # designing contracts between parallel units
    ORCHESTRATION.md                # the methodology
    docs/                           # model routing + at-a-moment procedures
    scripts/                        # worktree recipes + container-map tooling
    wiki-template/                  # a .wiki/ starter skeleton
    README.md
  claude-boundaries/
    .claude-plugin/plugin.json
    hooks/                          # SessionStart brief, post-edit check, stop gate
    scripts/                        # the CLI and the dependency-free checker
    skills/boundaries/              # placement, and what to do about a violation
    agents/boundary-audit.md        # the judgement no checker can make
    commands/                       # /boundaries:init | :check | :map
    templates/                      # folders and packages starter maps
    tests/                          # 71 tests, no dependencies
    README.md
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
```

MIT licensed.
