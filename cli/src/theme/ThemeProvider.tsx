import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import { ColorTheme, getTheme, ThemeName } from './themes.js';
import { loadThemeName, saveThemeName } from './persistence.js';

interface ThemeContextShape {
  themeName: ThemeName;
  colors: ColorTheme;
  setTheme: (name: ThemeName) => void;
}

const ThemeContext = createContext<ThemeContextShape | null>(null);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [themeName, setThemeName] = useState<ThemeName>(() => loadThemeName());
  const setTheme = useCallback((name: ThemeName) => {
    setThemeName(name);
    saveThemeName(name);
  }, []);
  const value = useMemo<ThemeContextShape>(
    () => ({ themeName, colors: getTheme(themeName), setTheme }),
    [themeName, setTheme],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export function useTheme(): ThemeContextShape {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    // Fallback so a stray <Component /> render outside the provider (e.g.
    // ink-testing-library) still gets a usable palette.
    return { themeName: 'dark', colors: getTheme('dark'), setTheme: () => {} };
  }
  return ctx;
}

export function useColors(): ColorTheme {
  return useTheme().colors;
}
