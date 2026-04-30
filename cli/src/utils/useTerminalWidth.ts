import { useEffect, useState } from 'react';
import { useStdout } from '../runtime/index';

/** Floor so a transient resize (e.g. sliding the window narrow) doesn't
 * propagate negative widths into Ink and crash the layout. */
export const MIN_PANEL_WIDTH = 24;

/**
 * Returns the current terminal column count and re-renders when the
 * window resizes. Falls back to 80 if stdout can't report a size.
 */
export function useTerminalWidth(): number {
  const { stdout } = useStdout();
  const [cols, setCols] = useState<number>(stdout?.columns ?? 80);

  useEffect(() => {
    if (!stdout) return;
    const handler = () => setCols(stdout.columns ?? 80);
    stdout.on('resize', handler);
    return () => {
      stdout.off('resize', handler);
    };
  }, [stdout]);

  return cols;
}

/**
 * Width every top-level panel uses so Welcome / input box / bottom bar
 * line up edge-to-edge. Keep one terminal column free on the right so
 * bordered panels do not render into the terminal's last column, where
 * some emulators clip or wrap the final border cell.
 */
export function usePanelWidth(): number {
  const cols = useTerminalWidth();
  return Math.max(MIN_PANEL_WIDTH, cols - 1);
}

/** Returns the current terminal row count, re-renders on resize. */
export function useTerminalHeight(): number {
  const { stdout } = useStdout();
  const [rows, setRows] = useState<number>(stdout?.rows ?? 24);
  useEffect(() => {
    if (!stdout) return;
    const handler = () => setRows(stdout.rows ?? 24);
    stdout.on('resize', handler);
    return () => {
      stdout.off('resize', handler);
    };
  }, [stdout]);
  return rows;
}
