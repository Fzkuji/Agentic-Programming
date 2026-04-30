import { describe, expect, it } from 'vitest';
import { readFileSync } from 'fs';
import { themeFromRgb } from '../src/theme/oscQuery.js';
import { getTheme } from '../src/theme/themes.js';

describe('theme palettes', () => {
  it('uses balanced semantic accents for dark and light modes', () => {
    expect(getTheme('dark')).toMatchObject({
      primary: '#f97316',
      accent: '#38bdf8',
      text: '#e5e7eb',
      appTitle: '#c2412d',
      welcomeTitle: 'ansi:cyanBright',
    });
    expect(getTheme('light')).toMatchObject({
      primary: '#c44a17',
      accent: '#a13b13',
      muted: '#5e5e5e',
      text: '#1a1a1a',
      appTitle: '#c2412d',
      welcomeTitle: 'ansi:black',
    });
  });

  it('resolves auto to dim variants on non-extreme terminal backgrounds', () => {
    expect(themeFromRgb({ r: 0, g: 0, b: 0 })).toBe('dark');
    expect(themeFromRgb({ r: 0.25, g: 0.25, b: 0.25 })).toBe('dark-dim');
    expect(themeFromRgb({ r: 0.7, g: 0.7, b: 0.7 })).toBe('light-dim');
    expect(themeFromRgb({ r: 1, g: 1, b: 1 })).toBe('light');
  });

  it('refreshes the resolved auto theme after startup', () => {
    const source = readFileSync('src/theme/ThemeProvider.tsx', 'utf8');
    expect(source).toContain("activeSetting !== 'auto'");
    expect(source).toContain('AUTO_THEME_REFRESH_MS');
    expect(source).toContain('queryTerminalBg(250)');
    expect(source).toContain('setCachedSystemTheme(bg)');
  });
});
