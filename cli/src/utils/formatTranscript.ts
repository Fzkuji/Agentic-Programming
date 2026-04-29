/**
 * Plain-text formatters for the inline-flow REPL.
 *
 * The chat REPL writes already-committed turns and the welcome banner
 * directly to ``stdout`` so the terminal's native scrollback owns
 * history. ink only redraws the dynamic strip at the bottom (input +
 * status + any in-flight picker/modal). These formatters produce ANSI
 * strings the REPL feeds into ``console.log``.
 *
 * Visual fidelity vs ink components:
 *
 *  - Turn rendering matches the ink Turn component closely (same
 *    glyphs, same role-keyed layout, no markdown re-render — already-
 *    committed turns don't reflow on resize, so a single render at
 *    print time is enough).
 *  - Welcome rendering is intentionally simpler than the ink card —
 *    no border box, no flex columns, just a few labeled lines. The
 *    card visual loses fidelity here in exchange for not needing a
 *    React-tree-to-string layout engine.
 */
import type { Turn, ToolCall, TurnBlock } from '../components/Turn.js';
import type { WelcomeStats } from '../components/Welcome.js';

const RESET = '\x1b[0m';
const DIM = '\x1b[2m';
const ITALIC = '\x1b[3m';
const BOLD = '\x1b[1m';

const FG_GREEN = '\x1b[32m';
const FG_RED = '\x1b[31m';
const FG_GRAY = '\x1b[90m';
const FG_ORANGE = '\x1b[38;5;208m';   // 256-color ≈ OpenProgram primary
const BG_USER = '\x1b[48;5;225m';     // pale pink (matches user.bg in light theme)
const FG_USER = '\x1b[38;5;52m';      // dark red text on the pale pink

const TRUNC = 80;

const truncate = (s: string, n = TRUNC): string =>
  s.length > n ? s.slice(0, n - 1) + '…' : s;

const wrapLines = (text: string): string[] =>
  text.split('\n');

const formatToolCall = (call: ToolCall): string[] => {
  const arrow =
    call.status === 'running' ? '◌'
    : call.status === 'error' ? '✗'
    : '●';
  const arrowColor =
    call.status === 'running' ? FG_GRAY
    : call.status === 'error' ? FG_RED
    : FG_GREEN;
  const head =
    `  ${arrowColor}${arrow}${RESET} ${BOLD}${call.tool}${RESET}` +
    (call.input ? `${FG_GRAY} · ${truncate(call.input.split('\n')[0] ?? '')}${RESET}` : '');
  const out = [head];
  if (call.result) {
    const firstLine = call.result.split('\n')[0] ?? '';
    const moreLines = call.result.split('\n').length - 1;
    const suffix = moreLines > 0 ? `  (+${moreLines} lines)` : '';
    out.push(`    ${FG_GRAY}└ ${truncate(firstLine)}${suffix}${RESET}`);
  }
  return out;
};

const formatUserTurn = (turn: Turn): string => {
  const lines = wrapLines(turn.text);
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const prefix = i === 0 ? '> ' : '  ';
    const body = lines[i] || ' ';
    out.push(`${BG_USER}${FG_USER} ${prefix}${body} ${RESET}`);
  }
  out.push('');   // blank trailing line — visually separates turns
  return out.join('\n');
};

const formatAssistantTurn = (turn: Turn): string => {
  const blocks: TurnBlock[] =
    turn.blocks && turn.blocks.length > 0
      ? turn.blocks
      : [
          ...(turn.text ? [{ kind: 'text' as const, text: turn.text }] : []),
          ...((turn.tools ?? []).map((t) => ({ kind: 'tool' as const, call: t }))),
        ];

  const firstTextIndex = blocks.findIndex((b) => b.kind === 'text');
  const out: string[] = [];

  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    if (!b) continue;
    if (b.kind === 'tool') {
      for (const line of formatToolCall(b.call)) out.push(line);
      continue;
    }
    const lines = wrapLines(b.text);
    for (let j = 0; j < lines.length; j++) {
      const isFirstLine = i === firstTextIndex && j === 0;
      const prefix = isFirstLine ? `${FG_GREEN}● ${RESET}` : '  ';
      out.push(`${prefix}${lines[j] || ' '}`);
    }
  }
  out.push('');
  return out.join('\n');
};

const formatSystemTurn = (turn: Turn): string => {
  const lines = wrapLines(turn.text);
  const styled = lines.map((l) => `${FG_GRAY}${ITALIC} ${l || ' '}${RESET}`);
  styled.push('');
  return styled.join('\n');
};

/**
 * Render a single committed turn to an ANSI string suitable for
 * ``console.log`` / ``process.stdout.write``. One trailing blank
 * line is included so consecutive turns are visually separated.
 */
export function formatTurnText(turn: Turn): string {
  if (turn.role === 'user') return formatUserTurn(turn);
  if (turn.role === 'assistant') return formatAssistantTurn(turn);
  return formatSystemTurn(turn);
}

const fmtCount = (n?: number): string => (typeof n === 'number' ? String(n) : '—');

interface WelcomeColumn {
  count: string;
  label: string;
  items: string[];
}

const buildColumns = (stats: WelcomeStats): WelcomeColumn[] => {
  const pickCount = (explicit?: number, listLen?: number): number | undefined => {
    if (typeof explicit === 'number') return explicit;
    if (typeof listLen === 'number') return listLen;
    return undefined;
  };

  return [
    {
      count: fmtCount(pickCount(stats.programs_count, stats.top_programs?.length)),
      label: 'programs',
      items: (stats.top_programs ?? []).map((p) => p.name ?? '?').slice(0, 4),
    },
    {
      count: fmtCount(pickCount(stats.agents_count, stats.top_agents?.length)),
      label: 'agents',
      items: (stats.top_agents ?? []).map((a) => a.name ?? a.id ?? '?').slice(0, 4),
    },
    {
      count: fmtCount(pickCount(stats.conversations_count, stats.top_sessions?.length)),
      label: 'sessions',
      items: (stats.top_sessions ?? []).map((s) => s.title ?? s.id ?? '?').slice(0, 4),
    },
    {
      count: fmtCount(pickCount(stats.tools_count, stats.top_tools?.length)),
      label: 'tools',
      items: (stats.top_tools ?? []).slice(0, 4),
    },
  ];
};

/**
 * Welcome banner for the inline REPL. Printed once at startup the
 * first time stats arrive. Lives in main-buffer / scrollback after
 * that — never reflows.
 */
export function formatWelcomeText(stats: WelcomeStats): string {
  const cols = buildColumns(stats);
  const agent = stats.agent;
  const out: string[] = [];

  out.push(`${BOLD}${FG_ORANGE}OpenProgram${RESET} ${DIM}· ${agent?.name ?? '—'} · ${agent?.model ?? '—'}${RESET}`);
  out.push('');

  for (const c of cols) {
    out.push(`${BOLD}${FG_ORANGE}${c.count}${RESET} ${BOLD}${c.label}${RESET}`);
    for (const item of c.items) {
      out.push(`  ${FG_GRAY}${truncate(item, 60)}${RESET}`);
    }
    if (c.items.length === 0) out.push(`  ${FG_GRAY}(empty)${RESET}`);
    out.push('');
  }

  out.push(`${DIM}Type a message and press enter, or type / to browse commands.${RESET}`);
  out.push('');
  return out.join('\n');
}
