import React from 'react';
import { Box, Text } from 'ink';
import { colors } from '../theme/colors.js';

export interface BottomBarProps {
  agent?: string;
  model?: string;
  conversationId?: string;
  busy?: boolean;
  /** When true, the input is in slash-command mode. */
  slashMode?: boolean;
  /** Last context stats (input/output tokens). */
  tokens?: { input?: number; output?: number };
}

const formatTokens = (n?: number): string | null => {
  if (typeof n !== 'number' || n <= 0) return null;
  if (n >= 10000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
};

export const BottomBar: React.FC<BottomBarProps> = ({
  agent,
  model,
  conversationId,
  busy,
  slashMode,
  tokens,
}) => {
  const leftHint = slashMode
    ? '↑↓ choose · enter run · tab fill · esc cancel'
    : '/ commands · enter send · ctrl+c quit';

  const inTokens = formatTokens(tokens?.input);
  const outTokens = formatTokens(tokens?.output);

  return (
    <Box paddingX={1} justifyContent="space-between">
      <Text color={colors.muted}>{leftHint}</Text>
      <Text color={colors.muted}>
        {agent ?? '—'}
        <Text color={colors.border}> · </Text>
        {model ?? '—'}
        <Text color={colors.border}> · </Text>
        {(conversationId ?? '(new)').slice(0, 14)}
        {inTokens || outTokens ? (
          <>
            <Text color={colors.border}> · </Text>
            {inTokens ? <Text color={colors.muted}>↓{inTokens}</Text> : null}
            {inTokens && outTokens ? <Text color={colors.border}> </Text> : null}
            {outTokens ? <Text color={colors.muted}>↑{outTokens}</Text> : null}
          </>
        ) : null}
        {busy ? (
          <>
            <Text color={colors.border}> · </Text>
            <Text color={colors.warning}>working</Text>
          </>
        ) : null}
      </Text>
    </Box>
  );
};
