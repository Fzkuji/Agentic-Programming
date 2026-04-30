import { describe, expect, it } from 'vitest';
import { themeFromRgb } from '../src/theme/oscQuery.js';
import { getTheme } from '../src/theme/themes.js';

describe('theme palettes', () => {
  it('uses balanced semantic accents for dark and light modes', () => {
    expect(getTheme('dark')).toMatchObject({
      primary: '#f97316',
      accent: '#38bdf8',
      text: '#e5e7eb',
      welcomeTitle: '#bae6fd',
    });
    expect(getTheme('light')).toMatchObject({
      primary: '#8f2f0b',
      accent: '#2563eb',
      text: '#111827',
      welcomeTitle: '#111827',
    });
  });

  it('resolves auto to dim variants on non-extreme terminal backgrounds', () => {
    expect(themeFromRgb({ r: 0, g: 0, b: 0 })).toBe('dark');
    expect(themeFromRgb({ r: 0.25, g: 0.25, b: 0.25 })).toBe('dark-dim');
    expect(themeFromRgb({ r: 0.7, g: 0.7, b: 0.7 })).toBe('light-dim');
    expect(themeFromRgb({ r: 1, g: 1, b: 1 })).toBe('light');
  });
});
