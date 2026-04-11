import { CandlestickCard } from "@/components/charts/candlestick-card";
import { OrderBookCard } from "@/components/charts/order-book-card";
import { TradingSessionControls } from "@/components/control-panel/trading-session-controls";
import { WorkspaceSettingsForm } from "@/components/control-panel/workspace-settings-form";
import { LiveStrip } from "@/components/panels/live-strip";
import { DataTable } from "@/components/panels/data-table";
import { MetricCard } from "@/components/panels/metric-card";
import { SectionCard } from "@/components/panels/section-card";
import { StatusPill } from "@/components/panels/status-pill";
import { loadDashboardData, loadMarketData, loadWorkspaceSettings } from "@/lib/api";
import { formatCompactCurrency, formatCompactNumber, formatCurrency, formatPercent } from "@/lib/format";
import { requireServerSession } from "@/lib/server-session";
import { normalizeWorkspaceSettings, workspaceBrokerHint, workspaceCredentialsReady } from "@/lib/workspace-config";

type AlertItem = {
  category?: string;
  severity?: string;
  message?: string;
  created_at?: string | null;
};

type PositionItem = {
  symbol?: string;
  side?: string;
  quantity?: number;
  mark_price?: number | null;
  markPrice?: number | null;
  avg_price?: number | null;
  avgPrice?: number | null;
  unrealized_pnl?: number;
  notionalExposure?: number;
  assetClass?: string;
};

type StrategyItem = {
  id: string;
  name: string;
  code: string;
  status: string;
  assigned_symbols: string[];
  performance?: {
    sharpe?: number;
    pnl?: number;
    win_rate?: number;
  };
};

export default async function DashboardPage() {
  const session = await requireServerSession();
  const [{ portfolio, strategies, risk, alerts, source }, workspaceSettingsResponse, market] = await Promise.all([
    loadDashboardData(session.accessToken),
    loadWorkspaceSettings(session.accessToken),
    loadMarketData(),
  ]);

  const workspaceSettings = normalizeWorkspaceSettings(workspaceSettingsResponse);
  const credentialsReady = workspaceCredentialsReady(workspaceSettings);
  const accountBinding =
    workspaceSettings.account_id ||
    workspaceSettings.solana.wallet_address ||
    (workspaceSettings.exchange === "paper" ? "paper-profile" : "not configured");
  const lastSaved = workspaceSettingsResponse.updated_at || workspaceSettingsResponse.created_at || null;
  const alertList = (alerts ?? []) as AlertItem[];
  const positions = (portfolio.positions ?? []) as PositionItem[];
  const strategyList = (strategies ?? []) as StrategyItem[];
  const exposureEntries = [...(Object.entries(risk.exposure_by_asset ?? {}) as Array<[string, number]>)].sort(
    (left, right) => right[1] - left[1],
  );
  const watchlist = workspaceSettings.watchlist_symbols.length
    ? workspaceSettings.watchlist_symbols
    : portfolio.selected_symbols;
  const leadAlert = alertList[0] ?? null;
  const readinessItems = [
    {
      label: "Credentials",
      detail: credentialsReady ? "Broker profile and account routing are present." : "Broker credentials still need to be completed.",
      ready: credentialsReady,
    },
    {
      label: "Execution",
      detail: risk.trading_enabled ? "Trading is armed for this workspace." : "Execution is paused until the desk is released.",
      ready: Boolean(risk.trading_enabled),
    },
    {
      label: "AI Assist",
      detail: workspaceSettings.ai_assistance_enabled ? "Command guidance is enabled for the workspace." : "AI assistance is disabled.",
      ready: workspaceSettings.ai_assistance_enabled,
    },
    {
      label: "Auto Improve",
      detail: workspaceSettings.auto_improve_enabled ? "Adaptive learning loop is enabled." : "Auto-improve is disabled.",
      ready: workspaceSettings.auto_improve_enabled,
    },
  ];
  const readinessScore = readinessItems.filter((item) => item.ready).length;
  const grossExposure = Math.max(risk.gross_exposure || portfolio.gross_exposure || 0, 1);

  return (
    <div className="space-y-4">
      <LiveStrip items={market.watchlist} />

      <div className="grid gap-4 xl:grid-cols-[1.18fr_0.82fr]">
        <SectionCard
          eyebrow="Command Center"
          title="Capital posture, launch readiness, and operator context for the active trading workspace."
          rightSlot={<StatusPill value={source === "live" ? "live" : "demo"} />}
        >
          <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
            <div className="desktop-window rounded-[28px] p-5">
              <div className="flex flex-wrap gap-2">
                <span className="utility-chip">desk online</span>
                <span className="utility-chip">{workspaceSettings.exchange.toUpperCase()}</span>
                <span className="utility-chip">{workspaceSettings.mode.toUpperCase()}</span>
              </div>

              <div className="mt-6">
                <p className="eyebrow">Active Operator</p>
                <h3 className="mt-3 text-[clamp(2.4rem,4vw,3.8rem)] font-semibold leading-[0.94] tracking-[-0.05em] text-sand">
                  {session.user.full_name || session.user.username}
                </h3>
                <p className="mt-4 max-w-3xl text-sm leading-7 text-mist/70">
                  {workspaceBrokerHint(workspaceSettings)} Capital, risk, and runtime controls are surfaced here so
                  the desk can move from configuration to execution without leaving the primary dashboard.
                </p>
              </div>

              <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <ContextTile label="Account Binding" value={accountBinding} detail="Primary desk route" />
                <ContextTile
                  label="Risk Profile"
                  value={workspaceSettings.risk_profile_name || "Balanced"}
                  detail={`${workspaceSettings.risk_percent}% budget`}
                />
                <ContextTile
                  label="Watchlist"
                  value={String(watchlist.length || portfolio.selected_symbols.length || 0)}
                  detail="Symbols active for runtime"
                />
                <ContextTile
                  label="Last Save"
                  value={lastSaved ? formatTimestamp(lastSaved) : "Not saved yet"}
                  detail="Workspace persistence"
                />
              </div>
            </div>

            <div className="space-y-4">
              <div className="rounded-[28px] border border-white/8 bg-white/[0.03] p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="eyebrow">Launch Readiness</p>
                    <h3 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-sand">
                      {credentialsReady ? "Desk is close to ready." : "Finish broker setup before launch."}
                    </h3>
                  </div>
                  <div className="text-right">
                    <StatusPill value={readinessScore === readinessItems.length ? "ready" : "standby"} />
                    <p className="mt-2 text-[11px] uppercase tracking-[0.24em] text-mist/42">
                      {readinessScore}/{readinessItems.length} checks
                    </p>
                  </div>
                </div>

                <TradingSessionControls
                  userRole={session.user.role}
                  tradingEnabled={Boolean(risk.trading_enabled)}
                  credentialsReady={credentialsReady}
                  selectedSymbols={watchlist.length ? watchlist : risk.selected_symbols ?? []}
                  terminalLabel={`Launch ${workspaceSettings.exchange.toUpperCase()} Terminal`}
                />

                <div className="mt-5 grid gap-3">
                  {readinessItems.map((item) => (
                    <div key={item.label} className="rounded-[20px] border border-white/8 bg-black/10 px-4 py-3">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <p className="text-sm font-semibold text-sand">{item.label}</p>
                          <p className="mt-1 text-sm leading-6 text-mist/62">{item.detail}</p>
                        </div>
                        <StatusPill value={item.ready ? "ready" : "standby"} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-[28px] border border-amber-300/20 bg-amber-300/8 p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="eyebrow">Priority Alert</p>
                    <p className="mt-3 text-lg font-semibold text-sand">
                      {leadAlert?.message || "No immediate intervention points right now."}
                    </p>
                  </div>
                  <StatusPill value={leadAlert?.severity || "standby"} />
                </div>
                <p className="mt-3 text-sm leading-6 text-mist/68">
                  {(leadAlert?.category || "system").toUpperCase()}
                  {leadAlert?.created_at ? ` | ${formatTimestamp(leadAlert.created_at)}` : ""}
                </p>
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard
          eyebrow="Runtime Focus"
          title="Lead market, spread, and desk posture beside the command center."
          rightSlot={<StatusPill value={market.source === "live" ? "live" : "preview"} />}
        >
          <div className="space-y-4">
            <div className="rounded-[26px] border border-white/8 bg-black/10 p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="eyebrow">Lead Symbol</p>
                  <h3 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-sand">{market.symbol}</h3>
                </div>
                <StatusPill value={market.changePct >= 0 ? "positive" : "warning"} />
              </div>
              <div className="mt-4 flex items-end justify-between gap-4">
                <p className="data-value text-[3rem] font-semibold leading-none text-sand">{market.last}</p>
                <p className={`text-lg font-semibold ${market.changePct >= 0 ? "text-lime-200" : "text-rose-200"}`}>
                  {formatPercent(market.changePct)}
                </p>
              </div>
              <div className="mt-5 grid grid-cols-3 gap-3 text-sm">
                <ContextTile label="Bid" value={String(market.bid)} detail="Top of book" compact />
                <ContextTile label="Ask" value={String(market.ask)} detail="Top of book" compact />
                <ContextTile
                  label="Volume"
                  value={formatCompactNumber(market.volume)}
                  detail="Session flow"
                  compact
                />
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <ContextTile
                label="Buying Power"
                value={formatCompactCurrency(portfolio.buying_power)}
                detail={`Cash ${formatCompactCurrency(portfolio.cash)}`}
              />
              <ContextTile
                label="Net Exposure"
                value={formatCompactCurrency(portfolio.net_exposure)}
                detail={`Margin ${formatPercent((portfolio.margin_usage ?? 0) * 100)}`}
              />
            </div>

            <div className="rounded-[26px] border border-white/8 bg-black/10 p-5">
              <p className="eyebrow">Symbol Universe</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {watchlist.length ? (
                  watchlist.map((symbol) => (
                    <span
                      key={symbol}
                      className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 font-[var(--font-mono)] text-xs text-mist/82"
                    >
                      {symbol}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-mist/55">No watchlist has been saved for this workspace yet.</span>
                )}
              </div>
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Total Equity" value={formatCurrency(portfolio.total_equity)} hint={`${source.toUpperCase()} account feed`} />
        <MetricCard
          label="Daily PnL"
          value={formatCompactCurrency(portfolio.daily_pnl)}
          tone={portfolio.daily_pnl >= 0 ? "good" : "warn"}
          hint={`Weekly ${formatCompactCurrency(portfolio.weekly_pnl)}`}
        />
        <MetricCard
          label="Monthly PnL"
          value={formatCompactCurrency(portfolio.monthly_pnl)}
          tone={portfolio.monthly_pnl >= 0 ? "good" : "warn"}
          hint={`Max drawdown ${formatPercent(portfolio.max_drawdown)}`}
        />
        <MetricCard
          label="Open Inventory"
          value={String(portfolio.active_positions)}
          hint={`Gross ${formatCompactCurrency(portfolio.gross_exposure)}`}
          footer={<span>VaR 95 {formatPercent(portfolio.var_95)}</span>}
        />
      </div>

      <SectionCard
        eyebrow="Market Pulse"
        title="Lead-market tape, order-book imbalance, and the flow picture the desk is trading into."
        rightSlot={<StatusPill value={market.changePct >= 0 ? "positive" : "warning"} />}
      >
        <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-[22px] border border-white/8 bg-black/10 p-4">
                <p className="eyebrow !tracking-[0.24em]">Lead Market</p>
                <p className="mt-3 text-lg font-semibold text-sand">{market.symbol}</p>
                <p className="mt-2 text-sm text-mist/62">{workspaceSettings.exchange.toUpperCase()} routing focus</p>
              </div>
              <div className="rounded-[22px] border border-white/8 bg-black/10 p-4">
                <p className="eyebrow !tracking-[0.24em]">Last</p>
                <p className="mt-3 text-lg font-semibold text-sand">{market.last}</p>
                <p className="mt-2 text-sm text-mist/62">Spread {(market.ask - market.bid).toFixed(4)}</p>
              </div>
              <div className="rounded-[22px] border border-white/8 bg-black/10 p-4">
                <p className="eyebrow !tracking-[0.24em]">Session Volume</p>
                <p className="mt-3 text-lg font-semibold text-sand">{formatCompactNumber(market.volume)}</p>
                <p className="mt-2 text-sm text-mist/62">{market.source.toUpperCase()} market source</p>
              </div>
            </div>
            <CandlestickCard candles={market.candles} />
          </div>

          <div className="space-y-4">
            <div className="rounded-[24px] border border-white/8 bg-black/10 p-4">
              <p className="eyebrow">Order Book</p>
              <h3 className="mt-3 text-xl font-semibold tracking-[-0.03em] text-sand">
                Top-of-book balance and liquidity ladder.
              </h3>
              <p className="mt-2 text-sm leading-6 text-mist/64">
                Use this view to sanity-check spread quality before staging orders from the terminal.
              </p>
            </div>
            <OrderBookCard bids={market.orderBook.bids} asks={market.orderBook.asks} />
          </div>
        </div>
      </SectionCard>

      <div className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
        <div className="space-y-4">
          <SectionCard
            eyebrow="Risk Surface"
            title="Exposure concentration, desk limits, and the alerts most likely to interrupt execution."
            rightSlot={<StatusPill value={risk.trading_enabled ? "enabled" : "paused"} />}
          >
            <div className="space-y-3">
              {exposureEntries.length ? (
                exposureEntries.map(([asset, exposure]) => (
                  <div key={asset} className="rounded-[22px] border border-white/8 bg-black/10 px-4 py-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sand/92">
                          {formatAssetLabel(asset)}
                        </p>
                        <p className="mt-1 text-sm text-mist/56">{shareOfGross(exposure, grossExposure)} of gross exposure</p>
                      </div>
                      <p className="font-[var(--font-mono)] text-sm text-mist">{formatCompactCurrency(exposure)}</p>
                    </div>
                    <div className="mt-3 h-2 rounded-full bg-white/5">
                      <div
                        className="h-2 rounded-full bg-[linear-gradient(90deg,rgba(214,164,108,0.9),rgba(115,197,231,0.75))]"
                        style={{ width: `${Math.min((exposure / grossExposure) * 100, 100)}%` }}
                      />
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[22px] border border-white/8 bg-black/10 p-4 text-sm text-mist/62">
                  Risk telemetry has not published exposure buckets yet.
                </div>
              )}
            </div>

            <div className="mt-5 grid gap-3 md:grid-cols-2">
              {Object.entries(risk.risk_limits ?? {}).map(([key, value]) => (
                <div key={key} className="rounded-[20px] border border-white/8 bg-white/[0.03] px-4 py-3">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-mist/44">{key.replace(/_/g, " ")}</p>
                  <p className="mt-2 font-[var(--font-mono)] text-sm text-sand">{formatLimitValue(value)}</p>
                </div>
              ))}
            </div>

            <div className="mt-5 space-y-3">
              {alertList.length ? (
                alertList.slice(0, 4).map((alert, index) => (
                  <div key={`${alert.category}-${index}`} className="rounded-[20px] border border-white/8 bg-black/10 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold text-sand">{alert.message || "Alert message unavailable"}</p>
                        <p className="mt-2 text-xs uppercase tracking-[0.24em] text-mist/44">
                          {alert.category || "system"}
                          {alert.created_at ? ` | ${formatTimestamp(alert.created_at)}` : ""}
                        </p>
                      </div>
                      <StatusPill value={alert.severity || "info"} />
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[20px] border border-white/8 bg-black/10 p-4 text-sm text-mist/62">
                  No active notifications right now.
                </div>
              )}
            </div>
          </SectionCard>

          <SectionCard
            eyebrow="Strategy Pressure"
            title="Model status, returns, and symbol coverage across the current strategy stack."
          >
            <div className="space-y-3">
              {strategyList.length ? (
                strategyList.map((strategy) => (
                  <div key={strategy.id} className="rounded-[24px] border border-white/8 bg-black/10 p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-lg font-semibold text-sand">{strategy.name}</p>
                        <p className="mt-1 font-[var(--font-mono)] text-xs uppercase tracking-[0.18em] text-mist/54">
                          {strategy.code}
                        </p>
                      </div>
                      <StatusPill value={strategy.status} />
                    </div>
                    <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
                      <MetricPair label="Sharpe" value={formatMetricValue(strategy.performance?.sharpe)} />
                      <MetricPair label="PnL" value={formatCompactCurrency(strategy.performance?.pnl ?? 0)} />
                      <MetricPair
                        label="Win Rate"
                        value={
                          typeof strategy.performance?.win_rate === "number"
                            ? `${strategy.performance.win_rate}%`
                            : "n/a"
                        }
                      />
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {strategy.assigned_symbols.map((symbol) => (
                        <span
                          key={`${strategy.id}-${symbol}`}
                          className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs uppercase tracking-[0.18em] text-mist/74"
                        >
                          {symbol}
                        </span>
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[20px] border border-white/8 bg-black/10 p-4 text-sm text-mist/62">
                  No strategies are registered for this workspace yet.
                </div>
              )}
            </div>
          </SectionCard>
        </div>

        <SectionCard
          eyebrow="Open Inventory"
          title="Positions carrying mark-to-market risk, with the desk data arranged for fast scanning."
          rightSlot={<StatusPill value={positions.length ? "active" : "standby"} />}
        >
          {positions.length ? (
            <DataTable
              rows={positions}
              columns={[
                {
                  key: "symbol",
                  header: "Instrument",
                  render: (position) => (
                    <div>
                      <p className="font-semibold text-sand">{position.symbol || "Unknown symbol"}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.24em] text-mist/44">
                        {position.assetClass || "unknown"}
                      </p>
                    </div>
                  ),
                },
                {
                  key: "side",
                  header: "Side",
                  render: (position) => <StatusPill value={position.side || "flat"} />,
                },
                {
                  key: "quantity",
                  header: "Quantity",
                  render: (position) => (
                    <span className="font-[var(--font-mono)] text-sm text-mist">{formatQuantity(position.quantity)}</span>
                  ),
                },
                {
                  key: "mark",
                  header: "Mark",
                  render: (position) => {
                    const mark = position.mark_price ?? position.markPrice ?? position.avg_price ?? position.avgPrice;
                    return <span className="font-[var(--font-mono)] text-sm text-mist">{mark ?? "n/a"}</span>;
                  },
                },
                {
                  key: "notional",
                  header: "Exposure",
                  render: (position) => (
                    <span className="font-[var(--font-mono)] text-sm text-mist">
                      {formatCompactCurrency(position.notionalExposure ?? 0)}
                    </span>
                  ),
                },
                {
                  key: "pnl",
                  header: "uPnL",
                  render: (position) => (
                    <span
                      className={`font-[var(--font-mono)] text-sm ${
                        (position.unrealized_pnl ?? 0) >= 0 ? "text-lime-200" : "text-rose-200"
                      }`}
                    >
                      {formatCompactCurrency(position.unrealized_pnl ?? 0)}
                    </span>
                  ),
                },
              ]}
            />
          ) : (
            <div className="rounded-[22px] border border-white/8 bg-black/10 p-4 text-sm text-mist/62">
              No live positions yet. Use the orders or terminal surfaces to stage trades.
            </div>
          )}
        </SectionCard>
      </div>

      <SectionCard
        eyebrow="Workspace Configuration"
        title="Broker routing, capital defaults, AI assistance, and runtime controls for the desktop workspace."
        rightSlot={<StatusPill value={credentialsReady ? "ready" : "needs input"} />}
      >
        <div className="grid gap-3 md:grid-cols-4">
          <ContextTile
            label="Broker Route"
            value={`${workspaceSettings.exchange.toUpperCase()} / ${workspaceSettings.broker_type.toUpperCase()}`}
            detail={`${workspaceSettings.mode.toUpperCase()} on ${workspaceSettings.market_type.toUpperCase()}`}
          />
          <ContextTile
            label="Paper Equity"
            value={formatCompactCurrency(workspaceSettings.paper_starting_equity)}
            detail={workspaceSettings.mode === "paper" ? "Simulation bankroll" : "Fallback reserve"}
          />
          <ContextTile
            label="Automation"
            value={workspaceSettings.auto_improve_enabled ? "Assisted" : "Manual"}
            detail={workspaceSettings.ai_assistance_enabled ? "AI assist enabled" : "Human-only workflow"}
          />
          <ContextTile
            label="Saved Watchlist"
            value={String(workspaceSettings.watchlist_symbols.length || portfolio.selected_symbols.length || 0)}
            detail="Symbols available to runtime startup"
          />
        </div>

        <div className="mt-6">
          <WorkspaceSettingsForm initialSettings={workspaceSettingsResponse} userRole={session.user.role} />
        </div>
      </SectionCard>
    </div>
  );
}

function ContextTile({
  label,
  value,
  detail,
  compact = false,
}: {
  label: string;
  value: string;
  detail: string;
  compact?: boolean;
}) {
  return (
    <div className={`rounded-[22px] border border-white/8 bg-black/10 px-4 ${compact ? "py-3" : "py-4"}`}>
      <p className="eyebrow !tracking-[0.24em]">{label}</p>
      <p className={`mt-3 font-semibold text-sand ${compact ? "text-base" : "text-lg"}`}>{value}</p>
      <p className="mt-2 text-sm leading-6 text-mist/58">{detail}</p>
    </div>
  );
}

function MetricPair({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.22em] text-mist/44">{label}</p>
      <p className="mt-1 font-semibold text-mist">{value}</p>
    </div>
  );
}

function formatTimestamp(value: string) {
  return new Date(value).toLocaleString();
}

function formatAssetLabel(value: string) {
  return value.replace(/_/g, " ");
}

function shareOfGross(exposure: number, grossExposure: number) {
  if (!grossExposure) {
    return "0%";
  }
  return `${Math.round((exposure / grossExposure) * 100)}%`;
}

function formatQuantity(value?: number) {
  if (typeof value !== "number") {
    return "n/a";
  }
  return value.toLocaleString();
}

function formatMetricValue(value?: number) {
  return typeof value === "number" ? value.toFixed(2) : "n/a";
}

function formatLimitValue(value: unknown) {
  if (typeof value !== "number") {
    return String(value);
  }
  if (value <= 5) {
    return `${(value * 100).toFixed(value < 1 ? 1 : 0)}%`;
  }
  return value.toLocaleString();
}
