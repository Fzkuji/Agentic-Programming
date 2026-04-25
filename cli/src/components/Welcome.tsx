import React from 'react';
import { Box, Text } from 'ink';
import { colors } from '../theme/colors.js';

export interface WelcomeStats {
  agent?: { id?: string; name?: string; model?: string } | null;
  agents_count?: number;
  programs_count?: number;
  skills_count?: number;
  conversations_count?: number;
  top_programs?: Array<{ name?: string; category?: string }>;
  top_skills?: Array<{ name?: string; slug?: string }>;
}

export interface WelcomeProps {
  stats?: WelcomeStats;
}

const fmt = (n?: number): string => (typeof n === 'number' ? String(n) : '—');

const Tile: React.FC<{ value: string; label: string }> = ({ value, label }) => (
  <Box flexDirection="column" flexGrow={1} alignItems="center" paddingX={1}>
    <Text bold color={colors.primary}>
      {value}
    </Text>
    <Text color={colors.muted}>{label}</Text>
  </Box>
);

export const Welcome: React.FC<WelcomeProps> = ({ stats }) => {
  const agentName = stats?.agent?.name ?? stats?.agent?.id ?? '—';
  const model = stats?.agent?.model ?? '—';

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={colors.primary}
      paddingX={2}
      paddingY={0}
      marginBottom={1}
    >
      {/* Title row + agent / model on the right */}
      <Box justifyContent="space-between">
        <Text bold color={colors.primary}>
          OpenProgram
        </Text>
        <Text color={colors.muted}>
          {agentName} <Text color={colors.border}>·</Text> {model}
        </Text>
      </Box>

      {/* 4 stat tiles, evenly distributed across the panel */}
      <Box marginTop={1}>
        <Tile value={fmt(stats?.programs_count)} label="programs" />
        <Tile value={fmt(stats?.skills_count)} label="skills" />
        <Tile value={fmt(stats?.agents_count)} label="agents" />
        <Tile value={fmt(stats?.conversations_count)} label="sessions" />
      </Box>

      {/* A peek at what's installed — first few names of each kind. */}
      {stats?.top_programs?.length || stats?.top_skills?.length ? (
        <Box marginTop={1} flexDirection="column">
          {stats?.top_programs?.length ? (
            <Text color={colors.muted}>
              programs:{' '}
              <Text color={colors.text}>
                {stats.top_programs
                  .map((p) => p.name)
                  .filter(Boolean)
                  .join(' · ')}
              </Text>
            </Text>
          ) : null}
          {stats?.top_skills?.length ? (
            <Text color={colors.muted}>
              skills:{' '}
              <Text color={colors.text}>
                {stats.top_skills
                  .map((s) => s.name)
                  .filter(Boolean)
                  .join(' · ')}
              </Text>
            </Text>
          ) : null}
        </Box>
      ) : null}

      <Box marginTop={1}>
        <Text color={colors.muted}>
          Type a message and press <Text color={colors.primary}>enter</Text>, or type{' '}
          <Text color={colors.primary}>/</Text> to browse commands.
        </Text>
      </Box>
    </Box>
  );
};
