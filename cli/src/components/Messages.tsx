import React from 'react';
import { Static } from 'ink';
import { TurnRow, Turn } from './Turn.js';
import { Welcome, WelcomeStats } from './Welcome.js';

export interface MessagesProps {
  /** Frozen committed turns — printed once into the static region. */
  committed: Turn[];
  /** Currently-streaming assistant turn, if any. Re-renders every delta. */
  streaming?: Turn | null;
  /**
   * Welcome stats. Shown ONLY while no committed turns exist; once the
   * user sends the first message the panel unmounts. Crucially, Welcome
   * sits OUTSIDE <Static> so Ink can dynamically erase it on unmount —
   * Static commits its items to the terminal's scrollback permanently,
   * which means a Welcome inside Static can't be repositioned and would
   * get scroll-pushed off the top whenever Static re-prints (resize,
   * theme switch).
   */
  welcome?: WelcomeStats;
  /**
   * Bumps when the terminal resizes or the active theme changes. Used as
   * the React key on <Static> so Ink's "we already printed these" memo
   * is invalidated and the whole transcript re-prints fresh — at the new
   * width or in the new palette.
   */
  resizeNonce?: number;
}

export const Messages: React.FC<MessagesProps> = ({
  committed, streaming, welcome, resizeNonce = 0,
}) => {
  const showWelcome = welcome && committed.length === 0 && !streaming;

  return (
    <>
      {showWelcome ? <Welcome stats={welcome} /> : null}
      <Static key={`static-${resizeNonce}`} items={committed}>
        {(turn) => <TurnRow key={turn.id} turn={turn} />}
      </Static>
      {streaming ? <TurnRow turn={streaming} /> : null}
    </>
  );
};
