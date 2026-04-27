import React from 'react';
import { render } from 'ink';
import { REPL } from './screens/REPL.js';
import { BackendClient } from './ws/client.js';
import { ThemeProvider } from './theme/ThemeProvider.js';
import { queryTerminalBg } from './theme/oscQuery.js';
import { setCachedSystemTheme } from './theme/systemTheme.js';

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

// Fire OSC 11 (background-color query) BEFORE Ink renders so we have the
// real terminal bg in hand before stdin gets handed to Ink's input layer.
// Most terminals reply in <50ms; we cap at 200ms and proceed with whatever
// we have. The result lands via setCachedSystemTheme, and ThemeProvider's
// subscriber bumps state so any 'auto' resolution flips to the right
// palette as soon as the answer arrives.
queryTerminalBg(200)
  .then((bg) => { if (bg) setCachedSystemTheme(bg); })
  .catch(() => { /* fall back to COLORFGBG / dark */ });

// Enter the alternate screen buffer (vim / less / htop / tmux pattern).
// `\e[?1049h` saves the cursor + switches to a fresh canvas; `\e[?1049l`
// restores the cursor + the original primary-buffer contents on exit, so
// the user's previous shell output reappears untouched.
//
// Trade-off: altscreen has no native scrollback. Chat history scrolls past
// the top of the viewport and is lost — Ink's <Static> still reprints what
// fits on the next render (e.g. after resize) but the user can't mouse-
// wheel back to earlier turns. The vim-like overlay UX is the explicit
// goal here, accepted in exchange for that limitation.
const ENTER_ALT = '\x1b[?1049h';
const EXIT_ALT = '\x1b[?1049l';
process.stdout.write(ENTER_ALT);

let _altRestored = false;
const restoreScreen = (): void => {
  if (_altRestored) return;
  _altRestored = true;
  try { process.stdout.write(EXIT_ALT); } catch { /* nothing to do on a closed pipe */ }
};
process.on('exit', restoreScreen);
process.on('uncaughtException', (err) => {
  restoreScreen();
  // Re-throw so Node still surfaces the error and exits non-zero.
  throw err;
});

// On resize, repaint the visible viewport. `\e[3J` (clear scrollback) is
// meaningless inside altscreen so we drop it. Ink + Static (keyed on
// resizeNonce in REPL.tsx) re-mounts and re-prints every committed turn
// at the new width.
let _lastCols = process.stdout.columns ?? 0;
let _lastRows = process.stdout.rows ?? 0;
process.stdout.on('resize', () => {
  const cols = process.stdout.columns ?? 0;
  const rows = process.stdout.rows ?? 0;
  if (cols !== _lastCols || rows !== _lastRows) {
    _lastCols = cols;
    _lastRows = rows;
    process.stdout.write('\x1b[2J\x1b[H');
  }
});

process.on('SIGINT', () => process.exit(0));
process.on('SIGTERM', () => process.exit(0));

const { waitUntilExit } = render(
  <ThemeProvider>
    <REPL client={client} />
  </ThemeProvider>,
  { exitOnCtrlC: false },
);

waitUntilExit().then(() => {
  client.close();
  restoreScreen();
  process.exit(0);
});
