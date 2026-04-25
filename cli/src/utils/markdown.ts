import { marked } from 'marked';
import { markedTerminal } from 'marked-terminal';

let configured = false;

const ensureConfigured = (): void => {
  if (configured) return;
  // The terminal renderer takes over heading/list/code/link handling.
  // No options needed for the defaults we want (cyan headings, dim quotes,
  // colored code fences). Cast keeps types happy across renderer versions.
  marked.use(markedTerminal() as Parameters<typeof marked.use>[0]);
  configured = true;
};

/**
 * Convert a markdown string into ANSI text for terminal display.
 *
 * Falls back to the raw input if marked throws — we never want a bad
 * fence to swallow the assistant's reply.
 */
export const renderMarkdown = (text: string): string => {
  ensureConfigured();
  try {
    const out = marked.parse(text) as string;
    return out.replace(/\n+$/, '');
  } catch {
    return text;
  }
};
