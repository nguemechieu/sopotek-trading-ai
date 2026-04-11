export type BrokerType = "crypto" | "forex" | "stocks" | "options" | "futures" | "derivatives" | "paper";
export type CustomerRegion = "us" | "global";
export type MarketType = "auto" | "spot" | "derivative" | "option" | "otc";
export type UserWorkspaceRole = "admin" | "trader" | "viewer";

export type SolanaWorkspaceSettings = {
  wallet_address: string;
  private_key: string;
  rpc_url: string;
  jupiter_api_key: string;
  okx_api_key: string;
  okx_secret: string;
  okx_passphrase: string;
  okx_project_id: string;
};

export type WorkspaceSettings = {
  language: string;
  broker_type: BrokerType;
  exchange: string;
  customer_region: CustomerRegion;
  mode: "live" | "paper";
  market_type: MarketType;
  ibkr_connection_mode: "webapi" | "tws";
  ibkr_environment: "gateway" | "hosted";
  schwab_environment: "sandbox" | "production";
  api_key: string;
  secret: string;
  password: string;
  account_id: string;
  risk_percent: number;
  paper_starting_equity: number;
  remember_profile: boolean;
  profile_name: string;
  risk_profile_name: string;
  max_portfolio_risk: number;
  max_risk_per_trade: number;
  max_position_size_pct: number;
  max_gross_exposure_pct: number;
  hedging_enabled: boolean;
  margin_closeout_guard_enabled: boolean;
  max_margin_closeout_pct: number;
  timeframe: string;
  order_type: "market" | "limit" | "stop_limit" | "stop";
  strategy_name: string;
  strategy_rsi_period: number;
  strategy_ema_fast: number;
  strategy_ema_slow: number;
  strategy_atr_period: number;
  strategy_oversold_threshold: number;
  strategy_overbought_threshold: number;
  strategy_breakout_lookback: number;
  strategy_min_confidence: number;
  strategy_signal_amount: number;
  watchlist_symbols: string[];
  ai_assistance_enabled: boolean;
  auto_improve_enabled: boolean;
  openai_api_key: string;
  openai_model: string;
  solana: SolanaWorkspaceSettings;
};

export type WorkspaceSettingsResponse = WorkspaceSettings & {
  created_at: string | null;
  updated_at: string | null;
};

export const BROKER_TYPE_OPTIONS: { label: string; value: BrokerType }[] = [
  { label: "Crypto", value: "crypto" },
  { label: "Forex", value: "forex" },
  { label: "Stocks", value: "stocks" },
  { label: "Options", value: "options" },
  { label: "Futures", value: "futures" },
  { label: "Derivatives", value: "derivatives" },
  { label: "Paper", value: "paper" }
];

export const CUSTOMER_REGION_OPTIONS: { label: string; value: CustomerRegion }[] = [
  { label: "US", value: "us" },
  { label: "Outside US", value: "global" }
];

export const MARKET_VENUE_OPTIONS: { label: string; value: MarketType }[] = [
  { label: "Auto", value: "auto" },
  { label: "Spot", value: "spot" },
  { label: "Derivative", value: "derivative" },
  { label: "Options", value: "option" },
  { label: "OTC", value: "otc" }
];

export const IBKR_CONNECTION_OPTIONS = [
  { label: "Web API", value: "webapi" as const },
  { label: "TWS / IB Gateway", value: "tws" as const }
];

export const IBKR_ENVIRONMENT_OPTIONS = [
  { label: "Client Portal Gateway", value: "gateway" as const },
  { label: "Hosted Web API", value: "hosted" as const }
];

export const SCHWAB_ENVIRONMENT_OPTIONS = [
  { label: "Sandbox", value: "sandbox" as const },
  { label: "Production", value: "production" as const }
];

const CRYPTO_EXCHANGE_MAP: Record<CustomerRegion, string[]> = {
  us: ["binanceus", "coinbase", "solana", "stellar", "kraken", "kucoin", "bybit", "okx", "gateio", "bitget"],
  global: ["binance", "coinbase", "solana", "stellar", "kraken", "kucoin", "bybit", "okx", "gateio", "bitget"]
};

const EXCHANGE_MAP: Record<BrokerType, string[]> = {
  crypto: [],
  forex: ["oanda"],
  stocks: ["alpaca"],
  options: ["schwab"],
  futures: ["ibkr", "amp", "tradovate"],
  derivatives: ["ibkr", "schwab", "amp", "tradovate"],
  paper: ["paper"]
};

function numericOrDefault(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function defaultWorkspaceSettings(): WorkspaceSettings {
  return {
    language: "en",
    broker_type: "paper",
    exchange: "paper",
    customer_region: "us",
    mode: "paper",
    market_type: "auto",
    ibkr_connection_mode: "webapi",
    ibkr_environment: "gateway",
    schwab_environment: "sandbox",
    api_key: "",
    secret: "",
    password: "",
    account_id: "",
    risk_percent: 2,
    paper_starting_equity: 100000,
    remember_profile: true,
    profile_name: "",
    risk_profile_name: "Balanced",
    max_portfolio_risk: 0.1,
    max_risk_per_trade: 0.02,
    max_position_size_pct: 0.1,
    max_gross_exposure_pct: 2.0,
    hedging_enabled: true,
    margin_closeout_guard_enabled: true,
    max_margin_closeout_pct: 0.5,
    timeframe: "1h",
    order_type: "limit",
    strategy_name: "Trend Following",
    strategy_rsi_period: 14,
    strategy_ema_fast: 20,
    strategy_ema_slow: 50,
    strategy_atr_period: 14,
    strategy_oversold_threshold: 35,
    strategy_overbought_threshold: 65,
    strategy_breakout_lookback: 20,
    strategy_min_confidence: 0.55,
    strategy_signal_amount: 1.0,
    watchlist_symbols: [],
    ai_assistance_enabled: true,
    auto_improve_enabled: true,
    openai_api_key: "",
    openai_model: "gpt-5-mini",
    solana: {
      wallet_address: "",
      private_key: "",
      rpc_url: "",
      jupiter_api_key: "",
      okx_api_key: "",
      okx_secret: "",
      okx_passphrase: "",
      okx_project_id: ""
    }
  };
}

export function exchangeOptionsFor(brokerType: BrokerType, customerRegion: CustomerRegion): string[] {
  if (brokerType === "crypto") {
    return [...CRYPTO_EXCHANGE_MAP[customerRegion]];
  }
  return [...(EXCHANGE_MAP[brokerType] ?? [])];
}

export function marketVenueOptionsFor(brokerType: BrokerType, exchange: string): MarketType[] {
  const normalizedExchange = (exchange || "").trim().toLowerCase();

  if (normalizedExchange === "paper" || brokerType === "paper") {
    return ["auto", "spot", "derivative", "option", "otc"];
  }
  if (normalizedExchange === "coinbase") {
    return ["auto", "spot", "derivative"];
  }
  if (["stellar", "solana", "alpaca", "binanceus"].includes(normalizedExchange)) {
    return ["auto", "spot"];
  }
  if (normalizedExchange === "oanda" || brokerType === "forex") {
    return ["auto", "otc"];
  }
  if (normalizedExchange === "ibkr") {
    return ["auto", "derivative", "option"];
  }
  if (normalizedExchange === "schwab" || brokerType === "options") {
    return ["auto", "option"];
  }
  if (["amp", "tradovate"].includes(normalizedExchange) || brokerType === "futures") {
    return ["auto", "derivative"];
  }
  if (brokerType === "derivatives") {
    return ["auto", "derivative", "option"];
  }
  if (brokerType === "crypto") {
    return ["auto", "spot", "derivative", "option"];
  }
  return ["auto", "spot"];
}

export function normalizeWorkspaceSettings(input: Partial<WorkspaceSettings>): WorkspaceSettings {
  const defaults = defaultWorkspaceSettings();
  const merged: WorkspaceSettings = {
    ...defaults,
    ...input,
    exchange: String(input.exchange ?? defaults.exchange).trim().toLowerCase() || defaults.exchange,
    language: String(input.language ?? defaults.language).trim() || defaults.language,
    api_key: String(input.api_key ?? defaults.api_key).trim(),
    secret: String(input.secret ?? defaults.secret).trim(),
    password: String(input.password ?? defaults.password).trim(),
    account_id: String(input.account_id ?? defaults.account_id).trim(),
    risk_percent: Math.max(1, Math.min(100, numericOrDefault(input.risk_percent ?? defaults.risk_percent, defaults.risk_percent))),
    paper_starting_equity: Math.max(1000, numericOrDefault(input.paper_starting_equity ?? defaults.paper_starting_equity, defaults.paper_starting_equity)),
    profile_name: String(input.profile_name ?? defaults.profile_name).trim(),
    risk_profile_name: String(input.risk_profile_name ?? defaults.risk_profile_name).trim() || defaults.risk_profile_name,
    max_portfolio_risk: Math.max(0, Math.min(1, numericOrDefault(input.max_portfolio_risk ?? defaults.max_portfolio_risk, defaults.max_portfolio_risk))),
    max_risk_per_trade: Math.max(0, Math.min(1, numericOrDefault(input.max_risk_per_trade ?? defaults.max_risk_per_trade, defaults.max_risk_per_trade))),
    max_position_size_pct: Math.max(0, Math.min(1, numericOrDefault(input.max_position_size_pct ?? defaults.max_position_size_pct, defaults.max_position_size_pct))),
    max_gross_exposure_pct: Math.max(0, Math.min(10, numericOrDefault(input.max_gross_exposure_pct ?? defaults.max_gross_exposure_pct, defaults.max_gross_exposure_pct))),
    hedging_enabled: Boolean(input.hedging_enabled ?? defaults.hedging_enabled),
    margin_closeout_guard_enabled: Boolean(input.margin_closeout_guard_enabled ?? defaults.margin_closeout_guard_enabled),
    max_margin_closeout_pct: Math.max(0.01, Math.min(1, numericOrDefault(input.max_margin_closeout_pct ?? defaults.max_margin_closeout_pct, defaults.max_margin_closeout_pct))),
    timeframe: String(input.timeframe ?? defaults.timeframe).trim().toLowerCase() || defaults.timeframe,
    order_type: (String(input.order_type ?? defaults.order_type).trim().toLowerCase() || defaults.order_type) as WorkspaceSettings["order_type"],
    strategy_name: String(input.strategy_name ?? defaults.strategy_name).trim() || defaults.strategy_name,
    strategy_rsi_period: Math.max(2, numericOrDefault(input.strategy_rsi_period ?? defaults.strategy_rsi_period, defaults.strategy_rsi_period)),
    strategy_ema_fast: Math.max(2, numericOrDefault(input.strategy_ema_fast ?? defaults.strategy_ema_fast, defaults.strategy_ema_fast)),
    strategy_ema_slow: Math.max(3, numericOrDefault(input.strategy_ema_slow ?? defaults.strategy_ema_slow, defaults.strategy_ema_slow)),
    strategy_atr_period: Math.max(2, numericOrDefault(input.strategy_atr_period ?? defaults.strategy_atr_period, defaults.strategy_atr_period)),
    strategy_oversold_threshold: numericOrDefault(input.strategy_oversold_threshold ?? defaults.strategy_oversold_threshold, defaults.strategy_oversold_threshold),
    strategy_overbought_threshold: numericOrDefault(input.strategy_overbought_threshold ?? defaults.strategy_overbought_threshold, defaults.strategy_overbought_threshold),
    strategy_breakout_lookback: Math.max(2, numericOrDefault(input.strategy_breakout_lookback ?? defaults.strategy_breakout_lookback, defaults.strategy_breakout_lookback)),
    strategy_min_confidence: Math.max(0, Math.min(1, numericOrDefault(input.strategy_min_confidence ?? defaults.strategy_min_confidence, defaults.strategy_min_confidence))),
    strategy_signal_amount: Math.max(0.0001, numericOrDefault(input.strategy_signal_amount ?? defaults.strategy_signal_amount, defaults.strategy_signal_amount)),
    watchlist_symbols: Array.from(
      new Set((input.watchlist_symbols ?? defaults.watchlist_symbols).map((symbol) => String(symbol || "").trim().toUpperCase()).filter(Boolean))
    ),
    ai_assistance_enabled: Boolean(input.ai_assistance_enabled ?? defaults.ai_assistance_enabled),
    auto_improve_enabled: Boolean(input.auto_improve_enabled ?? defaults.auto_improve_enabled),
    openai_api_key: String(input.openai_api_key ?? defaults.openai_api_key).trim(),
    openai_model: String(input.openai_model ?? defaults.openai_model).trim() || defaults.openai_model,
    solana: {
      ...defaults.solana,
      ...(input.solana ?? {})
    }
  };

  const availableExchanges = exchangeOptionsFor(merged.broker_type, merged.customer_region);
  if (merged.broker_type === "paper") {
    merged.broker_type = "paper";
    merged.exchange = "paper";
    merged.mode = "paper";
  } else if (merged.exchange === "paper" || !availableExchanges.includes(merged.exchange)) {
    merged.exchange = availableExchanges[0] ?? "paper";
  }

  const allowedVenues = marketVenueOptionsFor(merged.broker_type, merged.exchange);
  if (!allowedVenues.includes(merged.market_type)) {
    merged.market_type = allowedVenues[0] ?? "auto";
  }

  if (!["market", "limit", "stop_limit", "stop"].includes(merged.order_type)) {
    merged.order_type = defaults.order_type;
  }
  if (merged.strategy_ema_fast >= merged.strategy_ema_slow) {
    merged.strategy_ema_fast = Math.max(2, merged.strategy_ema_slow - 1);
  }
  if (merged.strategy_oversold_threshold >= merged.strategy_overbought_threshold) {
    merged.strategy_oversold_threshold = Math.min(merged.strategy_oversold_threshold, merged.strategy_overbought_threshold - 1);
  }

  return merged;
}

export function workspaceCredentialsReady(settings: WorkspaceSettings): boolean {
  if (settings.broker_type === "paper" || settings.exchange === "paper") {
    return true;
  }
  if (settings.mode === "paper" && ["binance", "binanceus", "coinbase", "kraken", "kucoin", "bybit", "okx", "gateio", "bitget", "stellar"].includes(settings.exchange)) {
    return true;
  }
  if (settings.exchange === "solana") {
    const hasWallet = Boolean(settings.solana.wallet_address && settings.solana.private_key);
    const hasOkx = Boolean(settings.solana.okx_api_key && settings.solana.okx_secret && settings.solana.okx_passphrase);
    const hasLegacyJupiter = Boolean(settings.solana.jupiter_api_key);
    return hasWallet || hasOkx || hasLegacyJupiter;
  }
  if (settings.exchange === "oanda") {
    return Boolean(settings.account_id && settings.api_key);
  }
  if (settings.exchange === "schwab") {
    return Boolean(settings.api_key && settings.password);
  }
  if (settings.exchange === "ibkr") {
    return true;
  }
  return Boolean(settings.api_key && settings.secret);
}

export function applyWorkspacePreset(settings: WorkspaceSettings, preset: "paper" | "crypto" | "forex"): WorkspaceSettings {
  if (preset === "paper") {
    return normalizeWorkspaceSettings({
      ...settings,
      broker_type: "crypto",
      exchange: settings.customer_region === "global" ? "binance" : "coinbase",
      mode: "paper",
      market_type: "spot",
      watchlist_symbols: ["BTC_USDT", "ETH_USDT", "SOL_USDT"],
      risk_percent: 2
    });
  }
  if (preset === "crypto") {
    const preferredExchange = settings.customer_region === "global" ? "binance" : "binanceus";
    return normalizeWorkspaceSettings({
      ...settings,
      broker_type: "crypto",
      exchange: preferredExchange,
      mode: "live",
      market_type: "spot",
      risk_percent: 2
    });
  }
  return normalizeWorkspaceSettings({
    ...settings,
    broker_type: "forex",
    exchange: "oanda",
    mode: "live",
    market_type: "otc",
    risk_percent: 1,
    watchlist_symbols: ["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD"]
  });
}

export function workspaceBrokerHint(settings: WorkspaceSettings): string {
  if (settings.broker_type === "paper" || settings.exchange === "paper") {
    return "Paper mode keeps execution simulated while preserving the real exchange context for symbols and market data.";
  }
  if (settings.mode === "paper") {
    return `Paper mode on ${settings.exchange.toUpperCase()} keeps fills simulated while the server reads live market structure and learns from closed paper trades.`;
  }
  if (settings.exchange === "solana") {
    return "Use wallet signing for live swaps, and add Jupiter or OKX routing credentials when you want Solana quotes and route assembly.";
  }
  if (settings.exchange === "oanda") {
    return "OANDA live routing needs both the account id and API key before the platform can bind the desk to a real FX account.";
  }
  if (settings.exchange === "schwab") {
    return "Schwab requires an app key plus redirect URI, then the session can complete through the OAuth sign-in flow.";
  }
  if (settings.exchange === "ibkr") {
    return "IBKR can route through Web API or TWS/Gateway, so keep the connection mode aligned with the runtime you actually run.";
  }
  return `Configure ${settings.exchange.toUpperCase()} credentials and risk before the trading workspace starts using this account.`;
}
