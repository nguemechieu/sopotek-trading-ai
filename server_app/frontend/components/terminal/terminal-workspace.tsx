"use client";

import { FormEvent, useDeferredValue, useEffect, useMemo, useState, useTransition } from "react";

import { OrderBookCard } from "@/components/charts/order-book-card";
import { TradingSessionControls } from "@/components/control-panel/trading-session-controls";
import { LiveStrip } from "@/components/panels/live-strip";
import { StatusPill } from "@/components/panels/status-pill";
import { formatCompactCurrency, formatCompactNumber, formatPercent } from "@/lib/format";
import {
  executeTerminalCommand,
  loadTerminalHistory,
  loadTerminalManifest,
  type TerminalCommandSpec,
  type TerminalManifest,
  type TerminalResponse,
  type TerminalSessionSpec,
} from "@/lib/terminal";
import type { UserRole } from "@/lib/auth-shared";

type TerminalWorkspaceProps = {
  initialTerminalId?: string;
  userRole: UserRole;
  initialDashboard: {
    portfolio: {
      total_equity: number;
      active_positions: number;
      selected_symbols: string[];
    };
    risk: {
      trading_enabled: boolean;
      alerts?: { category: string; severity: string; message: string }[];
    };
    strategies: { id: string; code: string; status: string }[];
    source: string;
  };
  workspaceProfile: {
    broker_type: string;
    exchange: string;
    mode: string;
    account_id: string;
    profile_name: string;
    risk_profile_name: string;
    watchlist_symbols: string[];
    credentials_ready: boolean;
  };
  marketContext: {
    symbol: string;
    last: number;
    changePct: number;
    bid: number;
    ask: number;
    volume: number;
    source: string;
    watchlist: { symbol: string; last: number; changePct: number }[];
    orderBook: {
      bids: { price: number; size: number }[];
      asks: { price: number; size: number }[];
    };
  };
};

function formatTimestamp(timestamp: string) {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return timestamp;
  }
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function mergeTerminalSessions(
  manifestSessions: TerminalSessionSpec[],
  customSessions: TerminalSessionSpec[],
) {
  const merged: TerminalSessionSpec[] = [...manifestSessions];
  const seen = new Set(manifestSessions.map((item) => item.terminal_id));
  for (const item of customSessions) {
    if (seen.has(item.terminal_id)) {
      continue;
    }
    merged.push(item);
    seen.add(item.terminal_id);
  }
  return merged;
}

function nextCustomSessionId(terminals: TerminalSessionSpec[], workspaceKey: string) {
  let highest = 1;
  for (const terminal of terminals) {
    const match = terminal.kind.match(/^desk-(\d+)$/);
    if (!match) {
      continue;
    }
    highest = Math.max(highest, Number(match[1]));
  }
  return `${workspaceKey}--desk-${highest + 1}`;
}

function createCustomSession(
  baseTerminal: TerminalSessionSpec,
  workspaceKey: string,
  terminals: TerminalSessionSpec[],
): TerminalSessionSpec {
  const terminalId = nextCustomSessionId(terminals, workspaceKey);
  const sessionNumber = terminalId.split("--").at(-1)?.replace("desk-", "") || "2";
  return {
    ...baseTerminal,
    terminal_id: terminalId,
    label: `${baseTerminal.broker_label} ${baseTerminal.account_label} Terminal ${sessionNumber}`,
    summary: "Additional launched server terminal for the active broker desk.",
    kind: `desk-${sessionNumber}`,
    launch_href: `/terminal?terminal=${terminalId}`,
    primary: false,
  };
}

function summarizeDataPreview(data: Record<string, unknown>) {
  return Object.entries(data)
    .slice(0, 4)
    .map(([key, value]) => ({ key, value: formatRuntimeValue(value) }));
}

function formatRuntimeValue(value: unknown): string {
  if (value == null) {
    return "null";
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.slice(0, 4).map((item) => formatRuntimeValue(item)).join(", ");
  }
  return JSON.stringify(value);
}

function commandPermissionLabel(permission?: string) {
  if (!permission) {
    return "workspace";
  }
  return permission.replace(/_/g, " ");
}

export function TerminalWorkspace({
  initialTerminalId,
  userRole,
  initialDashboard,
  workspaceProfile,
  marketContext,
}: TerminalWorkspaceProps) {
  const [isPending, startTransition] = useTransition();
  const [manifest, setManifest] = useState<TerminalManifest | null>(null);
  const [history, setHistory] = useState<TerminalResponse[]>([]);
  const [command, setCommand] = useState("/help");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeTerminalId, setActiveTerminalId] = useState(initialTerminalId || "");
  const [customTerminals, setCustomTerminals] = useState<TerminalSessionSpec[]>([]);
  const deferredCommand = useDeferredValue(command);

  useEffect(() => {
    let active = true;

    async function loadTerminalState() {
      setErrorMessage(null);
      setHistory([]);
      try {
        if (activeTerminalId) {
          const [manifestPayload, historyPayload] = await Promise.all([
            loadTerminalManifest(activeTerminalId),
            loadTerminalHistory(20, activeTerminalId),
          ]);
          if (!active) {
            return;
          }
          setManifest(manifestPayload);
          setHistory(historyPayload);
          return;
        }

        const manifestPayload = await loadTerminalManifest();
        if (!active) {
          return;
        }
        setManifest(manifestPayload);
        setActiveTerminalId((current) => current || manifestPayload.active_terminal_id);
        const historyPayload = await loadTerminalHistory(20, manifestPayload.active_terminal_id);
        if (!active) {
          return;
        }
        setHistory(historyPayload);
      } catch (error) {
        if (!active) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Unable to load the integrated terminal.");
      }
    }

    void loadTerminalState();
    return () => {
      active = false;
    };
  }, [activeTerminalId]);

  useEffect(() => {
    if (!activeTerminalId || typeof window === "undefined") {
      return;
    }
    const url = new URL(window.location.href);
    url.searchParams.set("terminal", activeTerminalId);
    window.history.replaceState({}, "", url);
  }, [activeTerminalId]);

  const terminalSessions = useMemo(
    () => mergeTerminalSessions(manifest?.terminals ?? [], customTerminals),
    [customTerminals, manifest?.terminals],
  );
  const activeTerminal =
    terminalSessions.find((item) => item.terminal_id === activeTerminalId) ||
    terminalSessions.find((item) => item.primary) ||
    terminalSessions[0] ||
    null;
  const currentResponse = history[0] ?? null;
  const desktopDefaults = (manifest?.desktop_defaults ?? null) as Record<string, unknown> | null;
  const brokerLabel = activeTerminal?.broker_label || manifest?.broker_label || workspaceProfile.exchange.toUpperCase();
  const accountLabel = activeTerminal?.account_label || manifest?.account_label || workspaceProfile.profile_name || workspaceProfile.account_id || "workspace";
  const sessionMode = activeTerminal?.mode || manifest?.mode || workspaceProfile.mode;
  const commandCatalog = manifest?.commands ?? [];

  const suggestions = useMemo(() => {
    const query = deferredCommand.trim().toLowerCase();
    if (!manifest) {
      return [];
    }
    if (!query) {
      return manifest.examples.slice(0, 6);
    }
    return manifest.commands
      .map((item) => item.example)
      .filter((item) => item.toLowerCase().includes(query))
      .slice(0, 6);
  }, [deferredCommand, manifest]);

  const activeCommandSpec = useMemo(() => {
    if (!commandCatalog.length) {
      return null;
    }
    const query = deferredCommand.trim().toLowerCase();
    if (!query) {
      return commandCatalog[0];
    }
    return (
      commandCatalog.find((item) => query.startsWith(item.command.toLowerCase())) ||
      commandCatalog.find((item) => item.example.toLowerCase().includes(query)) ||
      null
    );
  }, [commandCatalog, deferredCommand]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    if (!command.trim() || !activeTerminalId) {
      return;
    }
    startTransition(async () => {
      try {
        const response = await executeTerminalCommand(command, activeTerminalId);
        setHistory((current) =>
          [response, ...current.filter((item) => item.command_id !== response.command_id)].slice(0, 40),
        );
        setCommand("");
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : "Unable to execute terminal command.");
      }
    });
  }

  function handleLaunchTerminal() {
    if (!manifest || !activeTerminal) {
      return;
    }
    const launched = createCustomSession(activeTerminal, manifest.workspace_key || "desk", terminalSessions);
    setCustomTerminals((current) => [...current, launched]);
    setActiveTerminalId(launched.terminal_id);
    setHistory([]);
  }

  const agentCards = [
    {
      label: "Signal Agent",
      value: initialDashboard.portfolio.selected_symbols.length ? "online" : "idle",
      hint: `${initialDashboard.portfolio.selected_symbols.length} symbols in active watchlist`,
    },
    {
      label: "Risk Agent",
      value: initialDashboard.risk.trading_enabled ? "armed" : "watching",
      hint: `${(initialDashboard.risk.alerts ?? []).length} current alerts`,
    },
    {
      label: "Execution Agent",
      value: initialDashboard.source === "live" ? "connected" : "paper",
      hint: `${initialDashboard.portfolio.active_positions} active positions`,
    },
    {
      label: "Monitoring Agent",
      value: currentResponse?.status === "error" ? "degraded" : "healthy",
      hint: currentResponse ? `Last command ${formatTimestamp(currentResponse.timestamp)}` : "Awaiting terminal activity",
    },
  ];

  return (
    <div className="space-y-4">
      <LiveStrip items={marketContext.watchlist} />

      <section className="panel rounded-[30px] p-5">
        <div className="desktop-window rounded-[28px] p-5">
          <div className="flex flex-col gap-5 border-b border-white/8 pb-5 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full bg-rose-300/80" />
                <span className="h-3 w-3 rounded-full bg-amber-300/80" />
                <span className="h-3 w-3 rounded-full bg-lime-300/80" />
              </div>
              <p className="eyebrow mt-4">Desktop Terminal</p>
              <h1 className="mt-3 text-[clamp(2.2rem,3vw,3.8rem)] font-semibold leading-[0.94] tracking-[-0.05em] text-sand">
                {activeTerminal?.label || "Server Trading Terminal"}
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-7 text-mist/68">
                Guided execution for market, strategy, risk, and order flow, arranged to feel like a workstation
                rather than a stacked web console.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <StatusPill value={currentResponse?.status || sessionMode} />
              <button
                type="button"
                onClick={handleLaunchTerminal}
                disabled={!manifest || !activeTerminal}
                className="action-button-primary"
              >
                Launch Terminal
              </button>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            <span className="utility-chip">{String(sessionMode || "paper").toUpperCase()}</span>
            <span className="utility-chip">{brokerLabel}</span>
            <span className="utility-chip">{accountLabel}</span>
            <span className="utility-chip">{workspaceProfile.risk_profile_name}</span>
            <span className="utility-chip">{marketContext.source.toUpperCase()} market feed</span>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <TerminalStat
              label="Total Equity"
              value={formatCompactCurrency(initialDashboard.portfolio.total_equity)}
              detail="Workspace account equity"
            />
            <TerminalStat
              label="Open Positions"
              value={String(initialDashboard.portfolio.active_positions)}
              detail="Positions currently carrying risk"
            />
            <TerminalStat
              label="Lead Market"
              value={marketContext.symbol}
              detail={formatPercent(marketContext.changePct)}
            />
            <TerminalStat
              label="Session Rail"
              value={String(terminalSessions.length || 1)}
              detail="Terminal instances available in this desktop"
            />
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.28fr_0.72fr]">
        <section className="panel rounded-[30px] p-6">
          <div className="flex flex-col gap-4 border-b border-white/10 pb-5 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="eyebrow">Integrated Console</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight text-sand">
                Command surface for trade, market, risk, and strategy actions.
              </h2>
            </div>
            <StatusPill value={currentResponse?.status || "watching"} />
          </div>

          {manifest?.banners?.length ? (
            <div className="mt-5 grid gap-3 md:grid-cols-2">
              {manifest.banners.map((banner) => (
                <div key={banner} className="rounded-[20px] border border-white/8 bg-white/[0.03] px-4 py-3 text-sm leading-6 text-mist/74">
                  {banner}
                </div>
              ))}
            </div>
          ) : null}

          <form className="mt-6" onSubmit={handleSubmit}>
            <div className="terminal-frame rounded-[26px] p-4">
              <div className="flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.26em] text-cyan-100/68">
                <span>{activeTerminal?.kind || "execution"}</span>
                <span className="h-1.5 w-1.5 rounded-full bg-cyan-200/80" />
                <span>{brokerLabel}</span>
                <span className="h-1.5 w-1.5 rounded-full bg-cyan-200/55" />
                <span>{commandPermissionLabel(activeCommandSpec?.permission)}</span>
              </div>
              <div className="mt-4 flex items-center gap-3">
                <span className="font-[var(--font-mono)] text-lg text-cyan-200">$</span>
                <input
                  value={command}
                  onChange={(event) => setCommand(event.target.value)}
                  placeholder="/help"
                  className="w-full bg-transparent font-[var(--font-mono)] text-base text-sand outline-none placeholder:text-mist/30"
                />
                <button
                  type="submit"
                  disabled={isPending || !activeTerminalId}
                  className="action-button-primary"
                >
                  {isPending ? "Running..." : "Execute"}
                </button>
              </div>

              {activeCommandSpec ? (
                <div className="mt-4 rounded-[18px] border border-white/8 bg-black/20 px-4 py-3">
                  <p className="text-sm font-semibold text-sand">{activeCommandSpec.command}</p>
                  <p className="mt-1 text-sm leading-6 text-mist/62">{activeCommandSpec.summary}</p>
                </div>
              ) : null}
            </div>

            {suggestions.length ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {suggestions.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setCommand(item)}
                    className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 font-[var(--font-mono)] text-xs text-mist/80 transition hover:border-white/20 hover:text-mist"
                  >
                    {item}
                  </button>
                ))}
              </div>
            ) : null}
          </form>

          {errorMessage ? (
            <div className="mt-4 rounded-[22px] border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
              {errorMessage}
            </div>
          ) : null}

          {currentResponse?.suggestions?.length ? (
            <div className="mt-4 rounded-[22px] border border-white/8 bg-white/[0.03] p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm font-semibold text-sand">Suggested next actions</p>
                <span className="text-[10px] uppercase tracking-[0.24em] text-mist/40">Last response</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {currentResponse.suggestions.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setCommand(item)}
                    className="rounded-full border border-white/10 bg-black/10 px-3 py-1.5 font-[var(--font-mono)] text-xs text-mist/82 transition hover:border-white/20"
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <div className="mt-6 grid gap-4">
            {history.length ? (
              history.map((entry) => {
                const dataPreview = summarizeDataPreview(entry.data ?? {});
                return (
                  <article key={entry.command_id} className="terminal-screen rounded-[24px] p-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div>
                        <p className="font-[var(--font-mono)] text-sm text-cyan-100">{entry.command}</p>
                        <p className="mt-2 text-lg font-semibold text-sand">{entry.message}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <StatusPill value={entry.status} />
                        <span className="text-xs uppercase tracking-[0.24em] text-mist/40">
                          {formatTimestamp(entry.timestamp)}
                        </span>
                      </div>
                    </div>

                    {entry.lines.length ? (
                      <div className="mt-4 space-y-2 rounded-[18px] border border-white/8 bg-black/25 p-4 font-[var(--font-mono)] text-sm text-mist/78">
                        {entry.lines.map((line, index) => (
                          <p key={`${entry.command_id}-${index}`}>{line}</p>
                        ))}
                      </div>
                    ) : null}

                    {dataPreview.length ? (
                      <div className="mt-4 grid gap-3 md:grid-cols-2">
                        {dataPreview.map((item) => (
                          <div
                            key={`${entry.command_id}-${item.key}`}
                            className="rounded-[18px] border border-white/8 bg-white/[0.03] px-4 py-3"
                          >
                            <p className="text-[10px] uppercase tracking-[0.22em] text-mist/42">{item.key}</p>
                            <p className="mt-2 font-[var(--font-mono)] text-sm text-sand">{item.value}</p>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </article>
                );
              })
            ) : (
              <div className="rounded-[24px] border border-white/10 bg-black/10 p-5 text-sm text-mist/65">
                Run `/help` or click one of the suggested commands to start the terminal session.
              </div>
            )}
          </div>
        </section>

        <div className="space-y-6">
          <section className="panel rounded-[28px] p-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="eyebrow">Session Rail</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-sand">Terminal instances.</h2>
              </div>
              <StatusPill value={activeTerminal ? "connected" : "standby"} />
            </div>

            <div className="mt-5 grid gap-3">
              {terminalSessions.map((terminal) => {
                const selected = terminal.terminal_id === activeTerminal?.terminal_id;
                return (
                  <button
                    key={terminal.terminal_id}
                    type="button"
                    onClick={() => {
                      setActiveTerminalId(terminal.terminal_id);
                      setErrorMessage(null);
                    }}
                    className={`rounded-[22px] border p-4 text-left transition ${
                      selected
                        ? "border-[rgba(214,164,108,0.34)] bg-[linear-gradient(135deg,rgba(214,164,108,0.12),rgba(115,197,231,0.08))]"
                        : "border-white/10 bg-white/[0.03] hover:border-white/20 hover:bg-white/[0.05]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-semibold text-sand">{terminal.label}</p>
                      <StatusPill value={terminal.mode} />
                    </div>
                    <p className="mt-2 text-sm leading-6 text-mist/68">{terminal.summary}</p>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="panel rounded-[28px] border border-white/10 p-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.32em] text-mist/45">Control Panel</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-sand">
                  Broker launch posture and runtime controls on the terminal rail.
                </h2>
              </div>
              <StatusPill value={workspaceProfile.credentials_ready ? "ready" : "standby"} />
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-[22px] border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Broker Desk</p>
                <p className="mt-2 font-[var(--font-mono)] text-sm text-sand">{brokerLabel}</p>
                <p className="mt-2 text-sm text-mist/68">{accountLabel}</p>
              </div>
              <div className="rounded-[22px] border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Watchlist</p>
                <p className="mt-2 font-[var(--font-mono)] text-sm text-sand">
                  {workspaceProfile.watchlist_symbols.length
                    ? workspaceProfile.watchlist_symbols.slice(0, 4).join(", ")
                    : "runtime defaults"}
                </p>
                <p className="mt-2 text-sm text-mist/68">
                  {workspaceProfile.watchlist_symbols.length} symbols loaded for this terminal desk
                </p>
              </div>
            </div>

            <TradingSessionControls
              userRole={userRole}
              tradingEnabled={Boolean(initialDashboard.risk.trading_enabled)}
              credentialsReady={workspaceProfile.credentials_ready}
              selectedSymbols={workspaceProfile.watchlist_symbols}
              showTerminalLink={false}
            />
          </section>

          <section className="panel rounded-[28px] border border-white/10 p-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.32em] text-mist/45">AI Assistant</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-sand">
                  Trade explanation and runtime reasoning.
                </h2>
              </div>
              <StatusPill value={currentResponse?.assistant?.confidence || "watching"} />
            </div>

            <div className="mt-5 rounded-[24px] border border-amber-300/16 bg-amber-300/5 p-5">
              <p className="text-lg font-semibold text-sand">
                {currentResponse?.assistant?.headline || "Awaiting command context"}
              </p>
              <p className="mt-3 text-sm leading-7 text-mist/76">
                {currentResponse?.assistant?.reason ||
                  "Execute a command or trade request and the terminal will explain confidence, risk posture, and expected duration here."}
              </p>
              <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-[18px] border border-white/8 bg-white/[0.03] px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Risk Level</p>
                  <p className="mt-2 font-semibold text-sand">{currentResponse?.assistant?.risk_level || "pending"}</p>
                </div>
                <div className="rounded-[18px] border border-white/8 bg-white/[0.03] px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Expected Duration</p>
                  <p className="mt-2 font-semibold text-sand">
                    {currentResponse?.assistant?.expected_duration || "pending"}
                  </p>
                </div>
              </div>
            </div>
          </section>

          <section className="panel rounded-[28px] p-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="eyebrow">Market Microstructure</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-sand">
                  Spread, price, and order-book context.
                </h2>
              </div>
              <StatusPill value={marketContext.changePct >= 0 ? "positive" : "warning"} />
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <TerminalStat label="Lead Symbol" value={marketContext.symbol} detail="Primary market focus" />
              <TerminalStat label="Last" value={String(marketContext.last)} detail={formatPercent(marketContext.changePct)} />
              <TerminalStat label="Bid" value={String(marketContext.bid)} detail="Top of book" />
              <TerminalStat label="Ask" value={String(marketContext.ask)} detail="Top of book" />
              <TerminalStat
                label="Spread"
                value={(marketContext.ask - marketContext.bid).toFixed(4)}
                detail="Inside market"
              />
              <TerminalStat
                label="Volume"
                value={formatCompactNumber(marketContext.volume)}
                detail={`${marketContext.source.toUpperCase()} source`}
              />
            </div>

            <div className="mt-5">
              <OrderBookCard bids={marketContext.orderBook.bids} asks={marketContext.orderBook.asks} />
            </div>
          </section>

          <section className="panel rounded-[28px] border border-white/10 p-6">
            <p className="text-xs uppercase tracking-[0.32em] text-mist/45">Execution Defaults</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-sand">
              Desktop-matched server terminal parameters.
            </h2>
            <div className="mt-5 grid gap-3">
              {[
                { label: "Timeframe", value: String(desktopDefaults?.timeframe ?? "1h") },
                { label: "Order Type", value: String(desktopDefaults?.order_type ?? "limit") },
                { label: "Strategy", value: String(desktopDefaults?.strategy_name ?? "Trend Following") },
                { label: "Risk Profile", value: String(desktopDefaults?.risk_profile_name ?? "Balanced") },
              ].map((item) => (
                <div key={item.label} className="rounded-[22px] border border-white/10 bg-white/5 p-4">
                  <p className="text-xs uppercase tracking-[0.24em] text-mist/45">{item.label}</p>
                  <p className="mt-2 font-[var(--font-mono)] text-sm text-sand">{item.value}</p>
                </div>
              ))}
            </div>
            <p className="mt-4 text-sm leading-6 text-mist/68">
              Run <span className="font-[var(--font-mono)] text-mist">/params</span> to inspect the full risk and
              strategy parameter set mirrored into the server workspace.
            </p>
          </section>

          <section className="panel rounded-[28px] border border-white/10 p-6">
            <p className="text-xs uppercase tracking-[0.32em] text-mist/45">Agent Mesh</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-sand">
              Signal, risk, execution, and monitoring posture.
            </h2>
            <div className="mt-5 grid gap-3">
              {agentCards.map((card) => (
                <div key={card.label} className="rounded-[22px] border border-white/10 bg-white/5 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-semibold text-sand">{card.label}</p>
                    <StatusPill value={card.value} />
                  </div>
                  <p className="mt-2 text-sm text-mist/68">{card.hint}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="panel rounded-[28px] border border-white/10 p-6">
            <p className="text-xs uppercase tracking-[0.32em] text-mist/45">Command Catalog</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-sand">Operator-ready commands.</h2>
            <div className="mt-5 space-y-3">
              {(commandCatalog.length ? commandCatalog.slice(0, 6) : ([] as TerminalCommandSpec[])).map((item) => (
                <button
                  key={item.command}
                  type="button"
                  onClick={() => setCommand(item.example)}
                  className="w-full rounded-[20px] border border-white/10 bg-black/10 px-4 py-3 text-left transition hover:border-white/20"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-[var(--font-mono)] text-sm text-mist">{item.example}</span>
                    <span className="text-[10px] uppercase tracking-[0.22em] text-mist/40">
                      {commandPermissionLabel(item.permission)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-mist/62">{item.summary}</p>
                </button>
              ))}

              {!commandCatalog.length
                ? (manifest?.examples || ["/help", "/markets", "/risk", "/agents status"]).map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => setCommand(item)}
                      className="flex w-full items-center justify-between rounded-[20px] border border-white/10 bg-black/10 px-4 py-3 text-left transition hover:border-white/20"
                    >
                      <span className="font-[var(--font-mono)] text-sm text-mist">{item}</span>
                      <span className="text-xs uppercase tracking-[0.24em] text-mist/40">Load</span>
                    </button>
                  ))
                : null}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function TerminalStat({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-[22px] border border-white/10 bg-white/[0.03] px-4 py-4">
      <p className="text-[10px] uppercase tracking-[0.22em] text-mist/42">{label}</p>
      <p className="mt-2 font-[var(--font-mono)] text-sm text-sand">{value}</p>
      <p className="mt-2 text-sm text-mist/62">{detail}</p>
    </div>
  );
}
