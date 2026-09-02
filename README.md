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
```

MIT licensed.
