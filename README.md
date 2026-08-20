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
```

MIT licensed.
