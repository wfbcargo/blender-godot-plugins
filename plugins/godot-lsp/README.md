# godot-lsp

GDScript code intelligence for Claude Code — hover, go-to-definition,
find-references, document and workspace symbols, and diagnostics on `.gd` files,
answered by Godot's own analyser rather than by guesswork.

## Why this needs to exist

Godot ships a real GDScript language server, but it only listens on **TCP**
(`127.0.0.1:6005` by default). Claude Code runs every LSP server over **stdio**
— its `transport: "socket"` setting is accepted and then ignored. The two never
meet on their own.

This plugin is the missing pipe: 55 lines, no dependencies, no build step.
Godot's server already uses the same `Content-Length` JSON-RPC framing, so
nothing needs reframing — bytes go straight through in both directions.

## Install

```
/plugin marketplace add wfbcargo/blender-godot-plugins
/plugin install godot-lsp@blender-godot-plugins
```

Requires Node (any recent version) and Godot **4.x**. Nothing to configure.

## Using it

**The Godot editor must be open on your project.** The language server is part
of the editor, not the engine — there is no headless server to talk to.

That is the whole setup. With the editor open, `.gd` files gain:

| | |
|---|---|
| `hover` | Inferred types, and the full built-in class docs — hovering `Node` returns the entire engine reference for it |
| `goToDefinition` | Jump to a symbol's declaration, including into engine types |
| `findReferences` | Every use of a symbol across the project |
| `documentSymbol` | The functions and classes in a file, with line numbers |
| `workspaceSymbol` | Search symbols across the whole project |
| diagnostics | Parse and type errors pushed in after edits |

When the editor is closed the bridge exits and Claude Code restarts it three
times before giving up. That is intended: GDScript intelligence is simply
unavailable until the editor is reopened, and nothing else degrades. Reopening
Godot and starting a new Claude Code session picks it back up.

## Configuration

Two environment variables, both optional:

| Variable | Default | Purpose |
|---|---|---|
| `GODOT_LSP_HOST` | `127.0.0.1` | Host the editor's language server is on |
| `GODOT_LSP_PORT` | `6005` | Port, if changed from Godot's default |

Godot's own setting lives at **Editor Settings > Network > Language Server >
Remote Port**. If you change it there, change it here to match.

## Notes

- Diagnostics can be silenced while keeping navigation by setting
  `"diagnostics": false` in `.lsp.json`.
- If several LSP servers claim `.gd`, the first one registered wins and the rest
  never start — so remove any earlier hand-rolled GDScript server config.
- Everything the bridge logs goes to stderr. Claude Code parses stdout as
  protocol, so a stray `print` there would corrupt the stream.
