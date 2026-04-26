import React from 'react';
import { render } from 'ink';
import { REPL } from './screens/REPL.js';
import { BackendClient } from './ws/client.js';

function parseArgs(argv: string[]): { ws: string } {
  let ws = process.env.OPENPROGRAM_WS ?? 'ws://127.0.0.1:8765/ws';
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--ws' && argv[i + 1]) {
      ws = argv[i + 1]!;
      i++;
    }
  }
  return { ws };
}

const { ws } = parseArgs(process.argv.slice(2));
const client = new BackendClient(ws);
client.connect();

// We deliberately do NOT enter the alternate screen buffer. altscreen
// gives a clean canvas at startup but loses native scrollback — once
// Ink scrolls past the visible viewport the early turns vanish, and
// the terminal's mouse-wheel scrollback returns the OS shell history
// instead of the chat. Streaming into the primary buffer keeps the
// whole transcript scrollable like a normal terminal app.
//
// Resize quirks: on resize Ink may stack a frame or two of ghost
// prompt boxes. Static items (committed turns + welcome) re-mount via
// resizeNonce in REPL.tsx so their content is preserved at the new
// width — see Messages.tsx.

const restoreScreen = (): void => { /* no-op (altscreen disabled) */ };

process.on('SIGINT', () => process.exit(0));
process.on('SIGTERM', () => process.exit(0));

const { waitUntilExit } = render(<REPL client={client} />, {
  exitOnCtrlC: false,
});

waitUntilExit().then(() => {
  client.close();
  restoreScreen();
  process.exit(0);
});
