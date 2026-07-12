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
before every squash-merge. Ships eight role-pinned subagents and the methodology
that ties them together.

Model tier follows role, not depth: orchestration and architecture integrity run
on the top tier, bounded leaf work on a cheaper one — and if you only have one
model, point every agent at it and keep the whole structure. See the
[plugin README](./plugins/claude-architect/README.md) and
[`ORCHESTRATION.md`](./plugins/claude-architect/ORCHESTRATION.md).

## Layout

```
.claude-plugin/marketplace.json     # marketplace manifest
plugins/
  claude-architect/
    .claude-plugin/plugin.json      # plugin manifest
    agents/                         # the eight subagents
    ORCHESTRATION.md                # the methodology
    docs/model-routing.md           # tiering, fallback, remapping
    wiki-template/                  # a .wiki/ starter skeleton
    README.md
```

MIT licensed.
