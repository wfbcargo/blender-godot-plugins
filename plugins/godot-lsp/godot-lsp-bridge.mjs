#!/usr/bin/env node
// stdio <-> TCP bridge for Godot's GDScript language server.
//
// Claude Code speaks LSP over stdio only (its `transport: "socket"` setting is
// accepted but ignored), while Godot exposes its language server as a TCP
// listener. This pipes one onto the other, unchanged: Godot uses the same
// Content-Length JSON-RPC framing, so no reframing is needed.
//
// The listener only exists while the Godot editor is open with the project
// loaded. When it is closed the bridge exits non-zero and Claude Code restarts
// it (up to maxRestarts) until the editor comes back.
//
// Everything logged here goes to stderr. Claude Code parses stdout as protocol.

import net from 'node:net';

const HOST = process.env.GODOT_LSP_HOST ?? '127.0.0.1';
const PORT = Number(process.env.GODOT_LSP_PORT ?? 6005);

const log = (msg) => process.stderr.write(`[godot-lsp-bridge] ${msg}\n`);

const socket = net.connect({ host: HOST, port: PORT });
socket.setNoDelay(true);

socket.on('connect', () => {
  log(`connected to Godot language server at ${HOST}:${PORT}`);
  process.stdin.pipe(socket);
  socket.pipe(process.stdout);
});

socket.on('error', (err) => {
  if (err.code === 'ECONNREFUSED') {
    log(
      `no language server at ${HOST}:${PORT}. Open the project in the Godot ` +
        `editor (Editor Settings > Network > Language Server) and it will connect.`,
    );
  } else {
    log(`socket error: ${err.message}`);
  }
  process.exit(1);
});

socket.on('close', () => {
  log('Godot closed the connection');
  process.exit(1);
});

// Godot going away should not leave a stranded bridge holding stdio open.
process.stdin.on('end', () => socket.end());
for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    socket.destroy();
    process.exit(0);
  });
}
