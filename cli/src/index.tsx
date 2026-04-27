import React from 'react';
import { render, AlternateScreen } from '@openprogram/ink';
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

// OSC 11 (background-color query) for the auto theme. The reply lands
// via setCachedSystemTheme whenever it arrives; ThemeProvider's
// subscriber bumps state and flips 'auto' from dark to light in place.
queryTerminalBg(200)
  .then((bg) => { if (bg) setCachedSystemTheme(bg); })
  .catch(() => { /* fall back to COLORFGBG / dark */ });

process.on('SIGINT', () => process.exit(0));
process.on('SIGTERM', () => process.exit(0));

// <AlternateScreen> tells hermes-ink to enter the terminal alt buffer
// and run as a fullscreen app. Resize / theme / state changes all go
// through hermes-ink's Frame model + cell-diff log-update — full
// frames written atomically inside BSU/ESU brackets, no ghost stacks
// from stale eraseLines accounting.
//
// hermes-ink's render() resolves to an Instance once mounted (async,
// unlike stock Ink's sync return), so we await it before subscribing
// to waitUntilExit.
async function main(): Promise<void> {
  const instance = await render(
    <AlternateScreen>
      <ThemeProvider>
        <REPL client={client} />
      </ThemeProvider>
    </AlternateScreen>,
    { exitOnCtrlC: false },
  );

  await instance.waitUntilExit();
  client.close();
  process.exit(0);
}

main().catch((err: unknown) => {
  // eslint-disable-next-line no-console
  console.error(err);
  process.exit(1);
});
