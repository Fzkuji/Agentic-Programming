import React, { useState } from 'react';
import { Box, Text, useInput } from '@openprogram/ink';
import { useColors } from '../theme/ThemeProvider.js';
import { usePanelWidth } from '../utils/useTerminalWidth.js';

export interface LineInputProps {
  /** Label shown above the input box. */
  label: string;
  /** Optional helper line under the label. */
  hint?: string;
  /** When true, each typed char renders as `•`. For tokens / passwords. */
  mask?: boolean;
  /** Initial value. */
  initial?: string;
  /** Called on Enter with the final value. */
  onSubmit: (value: string) => void;
  /** Called on Esc. */
  onCancel: () => void;
}

/**
 * Single-line text input. Used by the channel-account register flow
 * (`/channel` → register → account_id → token).
 */
export const LineInput: React.FC<LineInputProps> = ({
  label, hint, mask, initial, onSubmit, onCancel,
}) => {
  const colors = useColors();
  const width = usePanelWidth();
  const [value, setValue] = useState<string>(initial ?? '');

  useInput((input, key) => {
    if (key.escape) {
      onCancel();
      return;
    }
    if (key.return) {
      onSubmit(value);
      return;
    }
    if (key.backspace || key.delete) {
      setValue((v) => v.slice(0, -1));
      return;
    }
    if (input && !key.ctrl && !key.meta && input.length === 1 && input >= ' ') {
      setValue((v) => v + input);
    }
  });

  const display = mask ? '•'.repeat(value.length) : value;

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={colors.primary}
      paddingX={1}
      marginBottom={1}
      width={width}
    >
      <Text bold color={colors.primary}>{label}</Text>
      {hint ? <Text color={colors.muted}>{hint}</Text> : null}
      <Box>
        <Text color={colors.primary}>{'> '}</Text>
        <Text color={colors.text}>{display}</Text>
        <Text color={colors.primary}>█</Text>
      </Box>
      <Text color={colors.muted}>enter submit · esc cancel</Text>
    </Box>
  );
};
