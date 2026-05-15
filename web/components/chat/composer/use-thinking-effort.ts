"use client";

/**
 * Thinking-effort selector state.
 *
 * The legacy `providers.js` writes `window._thinkingConfig = { options,
 * default }` whenever the chat-agent provider changes. We poll for that
 * (500ms is plenty since it only changes on agent switch) and re-pick a
 * default if the previously-selected effort isn't valid for the new
 * provider.
 */

import { useCallback, useEffect, useState } from "react";

const DEFAULT_THINKING: ThinkingEffort = "medium";
const FALLBACK_LEVELS = ["low", "medium", "high", "xhigh"] as const;
const STORAGE_KEY = "thinkingEffort";

/** Last picked effort, persisted so a page refresh keeps the choice. */
function readPersistedEffort(): ThinkingEffort | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writePersistedEffort(level: ThinkingEffort): void {
  try {
    localStorage.setItem(STORAGE_KEY, level);
  } catch {
    /* ignore */
  }
}

export type ThinkingEffort = string;

export interface ThinkingOption {
  value: string;
  desc?: string;
}

function readThinkingOptions(): ThinkingOption[] {
  const w = window as unknown as {
    _thinkingConfig?: { options?: ThinkingOption[] };
  };
  const opts = w._thinkingConfig?.options;
  if (Array.isArray(opts) && opts.length > 0) return opts;
  return FALLBACK_LEVELS.map((v) => ({ value: v }));
}

function readBackendDefault(): string | undefined {
  const w = window as unknown as { _thinkingConfig?: { default?: string } };
  return w._thinkingConfig?.default;
}

export interface ThinkingEffortHook {
  thinking: ThinkingEffort;
  options: ThinkingOption[];
  menuOpen: boolean;
  setMenuOpen: (v: boolean | ((prev: boolean) => boolean)) => void;
  /** Update the selection without closing the popover (slider drag). */
  set: (level: ThinkingEffort) => void;
}

export function useThinkingEffort(): ThinkingEffortHook {
  // Seed from localStorage so a page refresh keeps the last pick;
  // fall back to `medium` for a first-ever visit.
  const [thinking, setThinking] = useState<ThinkingEffort>(
    () => readPersistedEffort() ?? DEFAULT_THINKING,
  );
  const [menuOpen, setMenuOpen] = useState(false);
  const [options, setOptions] = useState<ThinkingOption[]>(() =>
    readThinkingOptions(),
  );

  useEffect(() => {
    let prevSig = "";
    function tick() {
      const opts = readThinkingOptions();
      const sig = opts.map((o) => o.value).join("|");
      if (sig === prevSig) return;
      prevSig = sig;
      setOptions(opts);
      // Snap the selection back to a valid value ONLY if the current
      // pick isn't part of the new option list (e.g. the agent
      // switched to a provider that doesn't offer it). A valid
      // persisted pick is left untouched — refresh keeps the choice.
      setThinking((cur) =>
        opts.some((o) => o.value === cur)
          ? cur
          : readBackendDefault() ?? opts[0]?.value ?? cur,
      );
    }
    tick();
    const id = setInterval(tick, 500);
    return () => clearInterval(id);
  }, []);

  const set = useCallback((level: ThinkingEffort) => {
    setThinking(level);
    writePersistedEffort(level);
  }, []);

  return { thinking, options, menuOpen, setMenuOpen, set };
}
