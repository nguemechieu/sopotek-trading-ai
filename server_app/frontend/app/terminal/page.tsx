import { TerminalWorkspace } from "@/components/terminal/terminal-workspace";
import { loadDashboardData, loadMarketData, loadWorkspaceSettings } from "@/lib/api";
import { requireServerSession } from "@/lib/server-session";
import { normalizeWorkspaceSettings, workspaceCredentialsReady } from "@/lib/workspace-config";

export default async function TerminalPage({
  searchParams,
}: {
  searchParams: Promise<{ terminal?: string }>;
}) {
  const resolvedSearchParams = await searchParams;
  const session = await requireServerSession();
  const [dashboard, workspaceSettingsResponse, market] = await Promise.all([
    loadDashboardData(session.accessToken),
    loadWorkspaceSettings(session.accessToken),
    loadMarketData(),
  ]);
  const workspaceSettings = normalizeWorkspaceSettings(workspaceSettingsResponse);
  const watchlist = workspaceSettings.watchlist_symbols.length
    ? workspaceSettings.watchlist_symbols
    : dashboard.portfolio.selected_symbols;

  return (
    <TerminalWorkspace
      initialTerminalId={resolvedSearchParams.terminal}
      userRole={session.user.role}
      initialDashboard={{
        portfolio: {
          total_equity: dashboard.portfolio.total_equity,
          active_positions: dashboard.portfolio.active_positions,
          selected_symbols: watchlist,
        },
        risk: {
          trading_enabled: dashboard.risk.trading_enabled,
          alerts: dashboard.alerts,
        },
        strategies: dashboard.strategies,
        source: dashboard.source,
      }}
      workspaceProfile={{
        broker_type: workspaceSettings.broker_type,
        exchange: workspaceSettings.exchange,
        mode: workspaceSettings.mode,
        account_id: workspaceSettings.account_id,
        profile_name: workspaceSettings.profile_name,
        risk_profile_name: workspaceSettings.risk_profile_name,
        watchlist_symbols: watchlist,
        credentials_ready: workspaceCredentialsReady(workspaceSettings),
      }}
      marketContext={{
        symbol: market.symbol,
        last: market.last,
        changePct: market.changePct,
        bid: market.bid,
        ask: market.ask,
        volume: market.volume,
        source: market.source,
        watchlist: market.watchlist,
        orderBook: market.orderBook,
      }}
    />
  );
}
