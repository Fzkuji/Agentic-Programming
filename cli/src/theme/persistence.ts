import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { homedir } from 'os';
import { join, dirname } from 'path';
import { DEFAULT_THEME, isThemeName, ThemeName } from './themes.js';

const CONFIG_PATH = join(homedir(), '.openprogram', 'cli-config.json');

interface CliConfig {
  theme?: string;
}

const readConfig = (): CliConfig => {
  if (!existsSync(CONFIG_PATH)) return {};
  try {
    const raw = readFileSync(CONFIG_PATH, 'utf8');
    const parsed = JSON.parse(raw);
    return typeof parsed === 'object' && parsed ? (parsed as CliConfig) : {};
  } catch {
    return {};
  }
};

const writeConfig = (cfg: CliConfig): void => {
  const dir = dirname(CONFIG_PATH);
  if (!existsSync(dir)) {
    try { mkdirSync(dir, { recursive: true }); } catch { /* best effort */ }
  }
  try {
    writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2) + '\n');
  } catch { /* best effort */ }
};

export function loadThemeName(): ThemeName {
  const cfg = readConfig();
  if (cfg.theme && isThemeName(cfg.theme)) return cfg.theme;
  return DEFAULT_THEME;
}

export function saveThemeName(name: ThemeName): void {
  const cfg = readConfig();
  cfg.theme = name;
  writeConfig(cfg);
}
