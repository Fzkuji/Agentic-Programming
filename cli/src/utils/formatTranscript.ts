import type { Turn, ToolCall, TurnBlock } from '../components/Turn.js';
import type { WelcomeStats } from '../components/Welcome.js';
import { stringWidth } from '../runtime/index.js';

const RESET = '\x1b[0m';
const DIM = '\x1b[2m';
const ITALIC = '\x1b[3m';
const BOLD = '\x1b[1m';
const FG_GREEN = '\x1b[32m';
const FG_RED = '\x1b[31m';
const FG_GRAY = '\x1b[90m';
const FG_ORANGE = '\x1b[38;5;208m';
const BG_USER = '\x1b[48;5;225m';
const FG_USER = '\x1b[38;5;52m';

const truncate = (s: string, n = 80): string =>
  s.length > n ? s.slice(0, n - 1) + '...' : s;

const linesOf = (text: string): string[] => text.split('\n');

const truncateWidth = (text: string, width: number): string => {
  if (stringWidth(text) <= width) return text;
  const suffix = '...';
  const suffixWidth = stringWidth(suffix);
  let out = '';
  let used = 0;
  for (const ch of text) {
    const w = stringWidth(ch);
    if (used + w + suffixWidth > width) break;
    out += ch;
    used += w;
  }
  return out + suffix;
};

const ansiWidth = (text: string): number =>
  stringWidth(text.replace(/\x1b\[[0-9;]*m/g, ''));

const padAnsi = (text: string, width: number): string => {
  const missing = Math.max(0, width - ansiWidth(text));
  return text + ' '.repeat(missing);
};

const boxLine = (content: string, width: number): string =>
  `${FG_ORANGE}│${RESET} ${padAnsi(content, width)} ${FG_ORANGE}│${RESET}`;

const joinCells = (cells: string[], width: number, gap: number): string =>
  cells.map((cell) => padAnsi(cell, width)).join(' '.repeat(gap));

const formatToolCall = (call: ToolCall): string[] => {
  const marker =
    call.status === 'running' ? 'o' : call.status === 'error' ? 'x' : '*';
  const markerColor =
    call.status === 'running'
      ? FG_GRAY
      : call.status === 'error'
        ? FG_RED
        : FG_GREEN;
  const head =
    `  ${markerColor}${marker}${RESET} ${BOLD}${call.tool}${RESET}` +
    (call.input ? `${FG_GRAY} · ${truncate(call.input.split('\n')[0] ?? '')}${RESET}` : '');
  const out = [head];
  if (call.result) {
    const resultLines = call.result.split('\n');
    const firstLine = resultLines[0] ?? '';
    const moreLines = resultLines.length - 1;
    const suffix = moreLines > 0 ? `  (+${moreLines} lines)` : '';
    out.push(`    ${FG_GRAY}| ${truncate(firstLine)}${suffix}${RESET}`);
  }
  return out;
};

const formatUserTurn = (turn: Turn): string => {
  const out: string[] = [];
  for (const [index, line] of linesOf(turn.text).entries()) {
    const prefix = index === 0 ? '> ' : '  ';
    out.push(`${BG_USER}${FG_USER} ${prefix}${line || ' '} ${RESET}`);
  }
  out.push('');
  return out.join('\n');
};

const formatAssistantTurn = (turn: Turn): string => {
  const blocks: TurnBlock[] =
    turn.blocks && turn.blocks.length > 0
      ? turn.blocks
      : [
          ...(turn.text ? [{ kind: 'text' as const, text: turn.text }] : []),
          ...((turn.tools ?? []).map((call) => ({ kind: 'tool' as const, call }))),
        ];
  const firstTextIndex = blocks.findIndex((block) => block.kind === 'text');
  const out: string[] = [];

  for (const [blockIndex, block] of blocks.entries()) {
    if (block.kind === 'tool') {
      out.push(...formatToolCall(block.call));
      continue;
    }
    for (const [lineIndex, line] of linesOf(block.text).entries()) {
      const showGlyph = blockIndex === firstTextIndex && lineIndex === 0;
      out.push(`${showGlyph ? `${FG_GREEN}* ${RESET}` : '  '}${line || ' '}`);
    }
  }
  out.push('');
  return out.join('\n');
};

const formatSystemTurn = (turn: Turn): string => {
  const out = linesOf(turn.text).map((line) => `${FG_GRAY}${ITALIC} ${line || ' '}${RESET}`);
  out.push('');
  return out.join('\n');
};

export function formatTurnText(turn: Turn): string {
  if (turn.role === 'user') return formatUserTurn(turn);
  if (turn.role === 'assistant') return formatAssistantTurn(turn);
  return formatSystemTurn(turn);
}

const fmtCount = (n?: number): string => (typeof n === 'number' ? String(n) : '-');

const pickCount = (explicit?: number, listLen?: number): number | undefined => {
  if (typeof explicit === 'number') return explicit;
  if (typeof listLen === 'number') return listLen;
  return undefined;
};

interface WelcomeSection {
  label: string;
  count: string;
  items: string[];
}

const section = (
  label: string,
  count: number | undefined,
  items: Array<string | undefined>,
): WelcomeSection => ({
  label,
  count: fmtCount(count),
  items: items.filter((item): item is string => Boolean(item)).slice(0, 6),
});

export function formatWelcomeText(stats: WelcomeStats): string {
  const agentName = stats.agent?.name ?? stats.agent?.id ?? '-';
  const model = stats.agent?.model ?? '-';
  const fallbackPrograms = stats.top_programs ?? [];
  const fallbackFunctions = fallbackPrograms.filter((p) => p.category && p.category !== 'app');
  const fallbackApplications = fallbackPrograms.filter((p) => p.category === 'app');
  const functions = stats.top_functions ?? fallbackFunctions;
  const applications = stats.top_applications ?? fallbackApplications;
  const sections: WelcomeSection[] = [
    section(
      'skills',
      pickCount(stats.skills_count, stats.top_skills?.length),
      (stats.top_skills ?? []).map((s) => s.name ?? s.slug),
    ),
    section(
      'agents',
      pickCount(stats.agents_count, stats.top_agents?.length),
      (stats.top_agents ?? []).map((a) => a.name ?? a.id),
    ),
    section(
      'sessions',
      pickCount(stats.conversations_count, stats.top_sessions?.length),
      (stats.top_sessions ?? []).map((s) => s.title ?? s.id),
    ),
    section(
      'tools',
      pickCount(stats.tools_count, stats.top_tools?.length),
      stats.top_tools ?? [],
    ),
    section(
      'providers',
      pickCount(stats.providers_count, stats.top_providers?.length),
      stats.top_providers ?? [],
    ),
    section(
      'channels',
      pickCount(stats.channels_count, stats.top_channels?.length),
      (stats.top_channels ?? []).map((c) =>
        c.channel && c.id ? `${c.channel}:${c.id}` : c.channel ?? c.id,
      ),
    ),
    section(
      'functions',
      pickCount(stats.functions_count, functions.length),
      functions.map((p) => p.name),
    ),
    section(
      'applications',
      pickCount(stats.applications_count, applications.length),
      applications.map((p) => p.name),
    ),
  ];

  const fullWidth = Math.max(48, Math.min(process.stdout.columns ?? 80, 100));
  const contentWidth = fullWidth - 4;
  const columns = contentWidth >= 76 ? 4 : 2;
  const gap = 2;
  const colWidth = Math.max(10, Math.floor((contentWidth - gap * (columns - 1)) / columns));
  const top = `${FG_ORANGE}╭${'─'.repeat(fullWidth - 2)}╮${RESET}`;
  const bottom = `${FG_ORANGE}╰${'─'.repeat(fullWidth - 2)}╯${RESET}`;
  const out: string[] = [top];

  out.push(boxLine(`${BOLD}${FG_ORANGE}OpenProgram${RESET} ${DIM}· ${agentName} · ${model}${RESET}`, contentWidth));
  out.push(boxLine('', contentWidth));

  for (let offset = 0; offset < sections.length; offset += columns) {
    const row = sections.slice(offset, offset + columns);
    while (row.length < columns) {
      row.push({ label: '', count: '', items: [] });
    }

    const headers = row.map((item) =>
      item.label
        ? `${BOLD}${FG_ORANGE}${item.count}${RESET} ${BOLD}${item.label}${RESET}`
        : '',
    );
    out.push(boxLine(joinCells(headers, colWidth, gap), contentWidth));

    const maxItems = Math.max(1, ...row.map((item) => item.items.length || 1));
    for (let itemIndex = 0; itemIndex < maxItems; itemIndex++) {
      const cells = row.map((item) => {
        if (!item.label) return '';
        const value = item.items[itemIndex] ?? (itemIndex === 0 ? '(empty)' : '');
        return value ? `${FG_GRAY}${truncateWidth(value, colWidth)}${RESET}` : '';
      });
      out.push(boxLine(joinCells(cells, colWidth, gap), contentWidth));
    }

    if (offset + columns < sections.length) {
      out.push(boxLine('', contentWidth));
    }
  }

  out.push(bottom);
  out.push('');
  return out.join('\n');
}
