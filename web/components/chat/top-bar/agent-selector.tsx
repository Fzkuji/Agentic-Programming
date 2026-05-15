"use client";

/**
 * Agent selector popover — React port of `providers.js::openAgentSelector`.
 *
 * Opened by the chat / exec `<AgentBadge />` in the topbar. Lists every
 * model the user enabled in Settings, grouped by provider, and on pick
 * writes the agent's default via `/api/agent_settings` (and, for the
 * chat agent on an active conversation, also pins it on that conv via
 * `/api/model` — the per-conv override otherwise wins and the pick
 * would silently no-op).
 *
 * Portal'd into `document.body`: the topbar's `.topbar-left` has
 * `overflow: hidden` and `.topbar` sets `container-type: inline-size`
 * (which makes it a containing block even for `position: fixed`), so
 * an in-tree popover would be clipped. Rendering at the document root
 * with `position: fixed` + a measured offset sidesteps both.
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";

import { useSessionStore } from "@/lib/session-store";
import { api } from "@/lib/api";

export function AgentSelector({
  kind,
  anchorRef,
  currentProvider,
  currentModel,
  onClose,
}: {
  kind: "chat" | "exec";
  anchorRef: React.RefObject<HTMLElement | null>;
  currentProvider?: string;
  currentModel?: string;
  onClose: () => void;
}) {
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const { data: models } = useQuery({
    queryKey: ["models-enabled"],
    queryFn: api.listEnabledModels,
  });

  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Measure the badge once on open to anchor the fixed-position panel
  // just below it. `left - 50` mirrors the legacy offset so the wider
  // panel stays roughly centred under the narrow badge.
  useLayoutEffect(() => {
    const a = anchorRef.current;
    if (!a) return;
    const r = a.getBoundingClientRect();
    setPos({ left: Math.max(r.left - 50, 10), top: r.bottom + 4 });
  }, [anchorRef]);

  // Close on any click outside the panel or its anchor badge.
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      const t = e.target as Node | null;
      if (!t) return;
      if (panelRef.current?.contains(t)) return;
      if (anchorRef.current?.contains(t)) return;
      onClose();
    }
    document.addEventListener("click", onDoc);
    return () => document.removeEventListener("click", onDoc);
  }, [anchorRef, onClose]);

  async function pick(provider: string, model: string) {
    onClose();
    try {
      await api.setAgentSettings({ [kind]: { provider, model } });
      // The agent-settings write only sets the agent DEFAULT. The
      // active conversation has a per-conv provider/model override
      // that takes priority, so the chat pick must also go through
      // `/api/model` or it has zero effect on the current chat.
      if (kind === "chat" && currentSessionId) {
        await api.switchModel(provider, model, currentSessionId);
      }
    } catch (e) {
      alert("Agent switch failed: " + String(e));
    }
  }

  // Group enabled models by provider, preserving first-seen order.
  const byProvider: { provider: string; models: typeof models }[] = [];
  for (const m of models ?? []) {
    let group = byProvider.find((g) => g.provider === m.provider);
    if (!group) {
      group = { provider: m.provider, models: [] };
      byProvider.push(group);
    }
    group.models!.push(m);
  }

  if (!pos || typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={panelRef}
      className={[
        "fixed z-[200] max-h-[60vh] w-[300px] overflow-y-auto",
        "rounded-[10px] border border-[var(--border)] bg-bg-tertiary",
        "p-[6px]",
        "shadow-[0_1px_2px_rgba(0,0,0,0.04),0_4px_6px_-2px_rgba(0,0,0,0.06),0_12px_24px_-8px_rgba(0,0,0,0.1)]",
      ].join(" ")}
      style={{ left: pos.left, top: pos.top }}
    >
      <div className="px-[10px] pb-[4px] pt-[6px] text-[12px] font-semibold text-text-muted">
        {kind === "chat" ? "Chat Agent" : "Execution Agent"}
      </div>

      {(models ?? []).length === 0 ? (
        <div className="px-[10px] py-[8px] text-[12px] text-text-muted">
          No enabled models —{" "}
          <a
            href="/settings"
            className="text-[var(--accent-blue)] no-underline"
          >
            enable some in Settings →
          </a>
        </div>
      ) : (
        byProvider.map((group) => (
          <div key={group.provider}>
            <div className="px-[10px] pb-[2px] pt-[8px] text-[11px] uppercase tracking-[0.04em] text-text-muted">
              {group.provider}
            </div>
            {group.models!.map((m) => {
              const active =
                currentProvider === m.provider &&
                (currentModel === m.id ||
                  currentModel === `${m.provider}:${m.id}`);
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => pick(m.provider, m.id)}
                  className={[
                    "flex w-full items-center gap-[8px] rounded-[8px]",
                    "px-[8px] py-[6px] text-left text-[14px]",
                    "transition-colors duration-75",
                    active
                      ? "bg-bg-hover text-text-bright"
                      : "text-text-primary hover:bg-bg-hover hover:text-text-bright",
                  ].join(" ")}
                >
                  <span className="flex-1 truncate">{m.name}</span>
                  {m.capabilities.length > 0 ? (
                    <span className="shrink-0 font-mono text-[11px] uppercase text-text-muted">
                      {m.capabilities
                        .filter((c) => c !== "ctx")
                        .map((c) => c[0])
                        .join("")}
                    </span>
                  ) : null}
                  {m.context ? (
                    <span className="shrink-0 font-mono text-[11px] text-text-muted">
                      {fmtCtx(m.context)}
                    </span>
                  ) : null}
                  {active ? (
                    <span className="shrink-0 text-[var(--accent-blue)]">
                      ✓
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        ))
      )}

      <div className="px-[10px] pb-[4px] pt-[8px] text-[11px]">
        <a
          href="/settings"
          className="text-[var(--accent-blue)] no-underline"
        >
          Manage models in Settings →
        </a>
      </div>
    </div>,
    document.body,
  );
}

/** Compact context-window label: 200000 → "200k", 1048576 → "1M". */
function fmtCtx(n: number): string {
  if (n >= 1_000_000) return `${Math.round(n / 1_000_000)}M`;
  if (n >= 1000) return `${Math.round(n / 1000)}k`;
  return String(n);
}
