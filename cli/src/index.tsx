import React from 'react';
import { render } from '@openprogram/ink';
import { REPL } from './screens/REPL.js';
import { Demo } from './screens/Demo.js';
import { BackendClient } from './ws/client.js';
import { ThemeProvider } from './theme/ThemeProvider.js';
import { queryTerminalBg } from './theme/oscQuery.js';
import { setCachedSystemTheme } from './theme/systemTheme.js';

function parseArgs(argv: string[]): { ws: string; demo: boolean } {
  let ws = process.env.OPENPROGRAM_WS ?? 'ws://127.0.0.1:8765/ws';
  let demo = false;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--ws' && argv[i + 1]) {
      ws = argv[i + 1]!;
      i++;
    }
    if (argv[i] === '--demo') {
      demo = true;
    }
  }
  return { ws, demo };
}

const { ws, demo } = parseArgs(process.argv.slice(2));
const client = new BackendClient(ws);
if (!demo) client.connect();

// OSC 11 (background-color query) for the auto theme. The reply lands
// via setCachedSystemTheme whenever it arrives; ThemeProvider's
// subscriber bumps state and flips 'auto' from dark to light in place.
queryTerminalBg(200)
  .then((bg) => { if (bg) setCachedSystemTheme(bg); })
  .catch(() => { /* fall back to COLORFGBG / dark */ });

process.on('SIGINT', () => process.exit(0));
process.on('SIGTERM', () => process.exit(0));

// REPL runs in main-buffer "inline" mode — Ink's live strip is the
// input + status only, finished turns flow into native scrollback
// via emitToScrollback. So the user's pre-existing shell output is
// still in scrollback (good — they wanted it there) but the visible
// screen needs to be wiped first so the welcome banner doesn't
// overlap their last shell prompts.
//
//  - \x1b[2J : erase entire screen (visible cells)
//  - \x1b[H  : home cursor to (1, 1)
//
// Notably we do NOT send \x1b[3J (erase scrollback). Killing the
// user's prior shell history would make them really mad — only
// what's currently on-screen needs to go.
//
// Demo uses Shell mode="alt" which enters alt-screen on its own;
// only inline-flow REPL needs this preamble.
async function main(): Promise<void> {
  if (!demo && process.stdout.isTTY) {
    process.stdout.write('\x1b[2J\x1b[H');
  }
  const root = demo
    ? <ThemeProvider><Demo /></ThemeProvider>
    : <ThemeProvider><REPL client={client} /></ThemeProvider>;
  const instance = await render(root, { exitOnCtrlC: false });
  await instance.waitUntilExit();
  client.close();
  process.exit(0);
}

main().catch((err: unknown) => {
  // eslint-disable-next-line no-console
  console.error(err);
  process.exit(1);
});
