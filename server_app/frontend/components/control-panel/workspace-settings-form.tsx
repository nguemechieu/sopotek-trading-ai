"use client";

import type { ReactNode } from "react";
import { FormEvent, useState, useTransition } from "react";

import { readAuthToken } from "@/lib/auth";
import {
  BROKER_TYPE_OPTIONS,
  CUSTOMER_REGION_OPTIONS,
  IBKR_CONNECTION_OPTIONS,
  IBKR_ENVIRONMENT_OPTIONS,
  MARKET_VENUE_OPTIONS,
  SCHWAB_ENVIRONMENT_OPTIONS,
  applyWorkspacePreset,
  exchangeOptionsFor,
  marketVenueOptionsFor,
  normalizeWorkspaceSettings,
  workspaceBrokerHint,
  workspaceCredentialsReady,
  type UserWorkspaceRole,
  type WorkspaceSettingsResponse
} from "@/lib/workspace-config";

const apiBaseUrl = process.env.NEXT_PUBLIC_SOPOTEK_API_BASE_URL ?? "http://127.0.0.1:8000";

function Field({
  label,
  children
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="auth-label">{label}</span>
      <div className="mt-2">{children}</div>
    </label>
  );
}

function Input({
  value,
  onChange,
  type = "text",
  placeholder,
  disabled = false
}: {
  value: string | number;
  onChange: (value: string) => void;
  type?: string;
  placeholder: string;
  disabled?: boolean;
}) {
  return (
    <input
      className="auth-input"
      type={type}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      disabled={disabled}
    />
  );
}

function Select({
  value,
  onChange,
  disabled = false,
  options
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  options: { label: string; value: string }[];
}) {
  return (
    <select
      className="auth-input"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

export function WorkspaceSettingsForm({
  initialSettings,
  userRole
}: {
  initialSettings: WorkspaceSettingsResponse;
  userRole: UserWorkspaceRole;
}) {
  const [settings, setSettings] = useState(() => normalizeWorkspaceSettings(initialSettings));
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const readOnly = userRole === "viewer";
  const isPaper = settings.broker_type === "paper" || settings.exchange === "paper";
  const isSolana = settings.exchange === "solana" && !isPaper;
  const exchangeOptions = exchangeOptionsFor(settings.broker_type, settings.customer_region).map((value) => ({
    label: value.toUpperCase(),
    value
  }));
  const marketVenueOptions = marketVenueOptionsFor(settings.broker_type, settings.exchange).map((value) => {
    const label = MARKET_VENUE_OPTIONS.find((option) => option.value === value)?.label ?? value;
    return { label, value };
  });
  const credentialsReady = workspaceCredentialsReady(settings);

  function updateSettings(nextPartial: Partial<WorkspaceSettingsResponse>) {
    setSettings((current) =>
      normalizeWorkspaceSettings({
        ...current,
        ...nextPartial,
        solana: {
          ...current.solana,
          ...(nextPartial.solana ?? {})
        }
      })
    );
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);

    if (readOnly) {
      setErrorMessage("Viewer accounts can inspect the control panel, but only trader or admin accounts can save it.");
      return;
    }

    startTransition(async () => {
      try {
        const accessToken = readAuthToken();
        if (!accessToken) {
          throw new Error("Your session expired. Sign in again to save your control panel settings.");
        }

        const response = await fetch(`${apiBaseUrl}/workspace/settings`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`
          },
          body: JSON.stringify(settings)
        });

        const payload = (await response.json().catch(() => null)) as WorkspaceSettingsResponse | { detail?: string } | null;
        if (!response.ok) {
          throw new Error((payload as { detail?: string } | null)?.detail || "Unable to save the control panel settings.");
        }

        setSettings(normalizeWorkspaceSettings(payload as WorkspaceSettingsResponse));
        setSuccessMessage("Control panel settings saved to your account.");
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : "Unable to save the control panel settings.");
      }
    });
  }

  return (
    <form className="space-y-6" onSubmit={handleSubmit}>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => updateSettings(applyWorkspacePreset(settings, "paper"))}
          disabled={isPending}
          className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-mist/80 transition hover:border-white/20 hover:text-mist disabled:opacity-60"
        >
          Paper Warmup
        </button>
        <button
          type="button"
          onClick={() => updateSettings(applyWorkspacePreset(settings, "crypto"))}
          disabled={isPending}
          className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-mist/80 transition hover:border-white/20 hover:text-mist disabled:opacity-60"
        >
          Crypto Live
        </button>
        <button
          type="button"
          onClick={() => updateSettings(applyWorkspacePreset(settings, "forex"))}
          disabled={isPending}
          className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-mist/80 transition hover:border-white/20 hover:text-mist disabled:opacity-60"
        >
          FX Live
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Language">
          <Input value={settings.language} onChange={(value) => updateSettings({ language: value })} placeholder="en" disabled={readOnly || isPending} />
        </Field>
        <Field label="Risk Budget">
          <Input
            value={settings.risk_percent}
            onChange={(value) => updateSettings({ risk_percent: Number(value) || 1 })}
            type="number"
            placeholder="2"
            disabled={readOnly || isPending}
          />
        </Field>
        <Field label="Paper Starting Equity">
          <Input
            value={settings.paper_starting_equity}
            onChange={(value) => updateSettings({ paper_starting_equity: Number(value) || 100000 })}
            type="number"
            placeholder="100000"
            disabled={readOnly || isPending}
          />
        </Field>
      </div>

      <div className="rounded-[24px] border border-white/10 bg-white/5 p-5">
        <p className="text-xs uppercase tracking-[0.3em] text-mist/45">Market Access</p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="Broker Type">
            <Select
              value={settings.broker_type}
              onChange={(value) => updateSettings({ broker_type: value as WorkspaceSettingsResponse["broker_type"] })}
              disabled={readOnly || isPending}
              options={BROKER_TYPE_OPTIONS}
            />
          </Field>
          <Field label="Exchange">
            <Select
              value={settings.exchange}
              onChange={(value) => updateSettings({ exchange: value })}
              disabled={readOnly || isPending}
              options={exchangeOptions}
            />
          </Field>
          {settings.broker_type === "crypto" && !isPaper ? (
            <Field label="Customer Region">
              <Select
                value={settings.customer_region}
                onChange={(value) => updateSettings({ customer_region: value as WorkspaceSettingsResponse["customer_region"] })}
                disabled={readOnly || isPending}
                options={CUSTOMER_REGION_OPTIONS}
              />
            </Field>
          ) : null}
          <Field label="Mode">
            <Select
              value={settings.mode}
              onChange={(value) => updateSettings({ mode: value as WorkspaceSettingsResponse["mode"] })}
              disabled={readOnly || isPending || isPaper}
              options={[
                { label: "Live", value: "live" },
                { label: "Paper", value: "paper" }
              ]}
            />
          </Field>
          <Field label="Venue">
            <Select
              value={settings.market_type}
              onChange={(value) => updateSettings({ market_type: value as WorkspaceSettingsResponse["market_type"] })}
              disabled={readOnly || isPending}
              options={marketVenueOptions}
            />
          </Field>
          <Field label="Watchlist Symbols">
            <Input
              value={settings.watchlist_symbols.join(", ")}
              onChange={(value) =>
                updateSettings({
                  watchlist_symbols: value
                    .split(",")
                    .map((item) => item.trim().toUpperCase())
                    .filter(Boolean)
                })
              }
              placeholder="BTC_USDT, ETH_USDT, SOL_USDT"
              disabled={readOnly || isPending}
            />
          </Field>
        </div>

        {settings.exchange === "ibkr" && !isPaper ? (
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Field label="IBKR Connection">
              <Select
                value={settings.ibkr_connection_mode}
                onChange={(value) => updateSettings({ ibkr_connection_mode: value as WorkspaceSettingsResponse["ibkr_connection_mode"] })}
                disabled={readOnly || isPending}
                options={IBKR_CONNECTION_OPTIONS}
              />
            </Field>
            <Field label="IBKR Environment">
              <Select
                value={settings.ibkr_environment}
                onChange={(value) => updateSettings({ ibkr_environment: value as WorkspaceSettingsResponse["ibkr_environment"] })}
                disabled={readOnly || isPending}
                options={IBKR_ENVIRONMENT_OPTIONS}
              />
            </Field>
          </div>
        ) : null}

        {settings.exchange === "schwab" && !isPaper ? (
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Field label="Schwab Environment">
              <Select
                value={settings.schwab_environment}
                onChange={(value) => updateSettings({ schwab_environment: value as WorkspaceSettingsResponse["schwab_environment"] })}
                disabled={readOnly || isPending}
                options={SCHWAB_ENVIRONMENT_OPTIONS}
              />
            </Field>
          </div>
        ) : null}

        <p className="mt-4 text-sm leading-6 text-mist/68">{workspaceBrokerHint(settings)}</p>
      </div>

      <div className="rounded-[24px] border border-white/10 bg-black/10 p-5">
        <p className="text-xs uppercase tracking-[0.3em] text-mist/45">Terminal Defaults</p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="Profile Name">
            <Input value={settings.profile_name} onChange={(value) => updateSettings({ profile_name: value })} placeholder="paper_coinbase" disabled={readOnly || isPending} />
          </Field>
          <Field label="Risk Profile">
            <Input value={settings.risk_profile_name} onChange={(value) => updateSettings({ risk_profile_name: value })} placeholder="Balanced" disabled={readOnly || isPending} />
          </Field>
          <Field label="Default Timeframe">
            <Select
              value={settings.timeframe}
              onChange={(value) => updateSettings({ timeframe: value })}
              disabled={readOnly || isPending}
              options={[
                { label: "1m", value: "1m" },
                { label: "5m", value: "5m" },
                { label: "15m", value: "15m" },
                { label: "1h", value: "1h" },
                { label: "4h", value: "4h" },
                { label: "1d", value: "1d" }
              ]}
            />
          </Field>
          <Field label="Default Order Type">
            <Select
              value={settings.order_type}
              onChange={(value) => updateSettings({ order_type: value as WorkspaceSettingsResponse["order_type"] })}
              disabled={readOnly || isPending}
              options={[
                { label: "Limit", value: "limit" },
                { label: "Market", value: "market" },
                { label: "Stop Limit", value: "stop_limit" },
                { label: "Stop", value: "stop" }
              ]}
            />
          </Field>
          <Field label="Default Strategy">
            <Input value={settings.strategy_name} onChange={(value) => updateSettings({ strategy_name: value })} placeholder="Trend Following" disabled={readOnly || isPending} />
          </Field>
        </div>
      </div>

      <div className="rounded-[24px] border border-white/10 bg-black/10 p-5">
        <p className="text-xs uppercase tracking-[0.3em] text-mist/45">Risk Controls</p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="Max Portfolio Risk">
            <Input value={settings.max_portfolio_risk} onChange={(value) => updateSettings({ max_portfolio_risk: Number(value) || 0.1 })} type="number" placeholder="0.10" disabled={readOnly || isPending} />
          </Field>
          <Field label="Max Risk Per Trade">
            <Input value={settings.max_risk_per_trade} onChange={(value) => updateSettings({ max_risk_per_trade: Number(value) || 0.02 })} type="number" placeholder="0.02" disabled={readOnly || isPending} />
          </Field>
          <Field label="Max Position Size %">
            <Input value={settings.max_position_size_pct} onChange={(value) => updateSettings({ max_position_size_pct: Number(value) || 0.1 })} type="number" placeholder="0.10" disabled={readOnly || isPending} />
          </Field>
          <Field label="Max Gross Exposure">
            <Input value={settings.max_gross_exposure_pct} onChange={(value) => updateSettings({ max_gross_exposure_pct: Number(value) || 2 })} type="number" placeholder="2.0" disabled={readOnly || isPending} />
          </Field>
          <Field label="Max Margin Closeout %">
            <Input value={settings.max_margin_closeout_pct} onChange={(value) => updateSettings({ max_margin_closeout_pct: Number(value) || 0.5 })} type="number" placeholder="0.50" disabled={readOnly || isPending} />
          </Field>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="flex items-center gap-3 rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm text-mist/78">
            <input
              type="checkbox"
              checked={settings.hedging_enabled}
              onChange={(event) => updateSettings({ hedging_enabled: event.target.checked })}
              disabled={readOnly || isPending}
            />
            Allow hedging in the same symbol when the broker supports it
          </label>
          <label className="flex items-center gap-3 rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm text-mist/78">
            <input
              type="checkbox"
              checked={settings.margin_closeout_guard_enabled}
              onChange={(event) => updateSettings({ margin_closeout_guard_enabled: event.target.checked })}
              disabled={readOnly || isPending}
            />
            Block fresh trades when margin closeout pressure is too high
          </label>
        </div>
      </div>

      <div className="rounded-[24px] border border-white/10 bg-black/10 p-5">
        <p className="text-xs uppercase tracking-[0.3em] text-mist/45">Strategy Defaults</p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="RSI Period">
            <Input value={settings.strategy_rsi_period} onChange={(value) => updateSettings({ strategy_rsi_period: Number(value) || 14 })} type="number" placeholder="14" disabled={readOnly || isPending} />
          </Field>
          <Field label="EMA Fast">
            <Input value={settings.strategy_ema_fast} onChange={(value) => updateSettings({ strategy_ema_fast: Number(value) || 20 })} type="number" placeholder="20" disabled={readOnly || isPending} />
          </Field>
          <Field label="EMA Slow">
            <Input value={settings.strategy_ema_slow} onChange={(value) => updateSettings({ strategy_ema_slow: Number(value) || 50 })} type="number" placeholder="50" disabled={readOnly || isPending} />
          </Field>
          <Field label="ATR Period">
            <Input value={settings.strategy_atr_period} onChange={(value) => updateSettings({ strategy_atr_period: Number(value) || 14 })} type="number" placeholder="14" disabled={readOnly || isPending} />
          </Field>
          <Field label="Oversold Threshold">
            <Input value={settings.strategy_oversold_threshold} onChange={(value) => updateSettings({ strategy_oversold_threshold: Number(value) || 35 })} type="number" placeholder="35" disabled={readOnly || isPending} />
          </Field>
          <Field label="Overbought Threshold">
            <Input value={settings.strategy_overbought_threshold} onChange={(value) => updateSettings({ strategy_overbought_threshold: Number(value) || 65 })} type="number" placeholder="65" disabled={readOnly || isPending} />
          </Field>
          <Field label="Breakout Lookback">
            <Input value={settings.strategy_breakout_lookback} onChange={(value) => updateSettings({ strategy_breakout_lookback: Number(value) || 20 })} type="number" placeholder="20" disabled={readOnly || isPending} />
          </Field>
          <Field label="Min Confidence">
            <Input value={settings.strategy_min_confidence} onChange={(value) => updateSettings({ strategy_min_confidence: Number(value) || 0.55 })} type="number" placeholder="0.55" disabled={readOnly || isPending} />
          </Field>
          <Field label="Signal Amount">
            <Input value={settings.strategy_signal_amount} onChange={(value) => updateSettings({ strategy_signal_amount: Number(value) || 1.0 })} type="number" placeholder="1.0" disabled={readOnly || isPending} />
          </Field>
        </div>
      </div>

      {!isPaper && !isSolana ? (
        <div className="rounded-[24px] border border-white/10 bg-black/10 p-5">
          <p className="text-xs uppercase tracking-[0.3em] text-mist/45">Credentials</p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Field label={settings.exchange === "oanda" ? "API Key" : "API Key / Client ID"}>
              <Input value={settings.api_key} onChange={(value) => updateSettings({ api_key: value })} placeholder="Credential value" disabled={readOnly || isPending} />
            </Field>
            <Field label={settings.exchange === "oanda" ? "Secret / Token" : "Secret"}>
              <Input value={settings.secret} onChange={(value) => updateSettings({ secret: value })} type="password" placeholder="Secret value" disabled={readOnly || isPending} />
            </Field>
            <Field label="Passphrase / Redirect URI">
              <Input value={settings.password} onChange={(value) => updateSettings({ password: value })} type={settings.exchange === "schwab" ? "text" : "password"} placeholder="Optional when supported" disabled={readOnly || isPending} />
            </Field>
            <Field label="Account ID">
              <Input value={settings.account_id} onChange={(value) => updateSettings({ account_id: value })} placeholder="Account or profile identifier" disabled={readOnly || isPending} />
            </Field>
          </div>
        </div>
      ) : null}

      <div className="rounded-[24px] border border-white/10 bg-black/10 p-5">
        <p className="text-xs uppercase tracking-[0.3em] text-mist/45">AI & Improvement</p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="OpenAI API Key">
            <Input
              value={settings.openai_api_key}
              onChange={(value) => updateSettings({ openai_api_key: value })}
              type="password"
              placeholder="Optional for ChatGPT help"
              disabled={readOnly || isPending}
            />
          </Field>
          <Field label="OpenAI Model">
            <Input
              value={settings.openai_model}
              onChange={(value) => updateSettings({ openai_model: value })}
              placeholder="gpt-5-mini"
              disabled={readOnly || isPending}
            />
          </Field>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="flex items-center gap-3 rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm text-mist/78">
            <input
              type="checkbox"
              checked={settings.ai_assistance_enabled}
              onChange={(event) => updateSettings({ ai_assistance_enabled: event.target.checked })}
              disabled={readOnly || isPending}
            />
            Let the server use ChatGPT for runtime help when credentials are available
          </label>
          <label className="flex items-center gap-3 rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm text-mist/78">
            <input
              type="checkbox"
              checked={settings.auto_improve_enabled}
              onChange={(event) => updateSettings({ auto_improve_enabled: event.target.checked })}
              disabled={readOnly || isPending}
            />
            Keep an adaptive paper-learning summary from closed trades
          </label>
        </div>
      </div>

      {isSolana ? (
        <div className="rounded-[24px] border border-white/10 bg-black/10 p-5">
          <p className="text-xs uppercase tracking-[0.3em] text-mist/45">Solana Routing</p>
          <div className="mt-4 space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Wallet Address">
                <Input value={settings.solana.wallet_address} onChange={(value) => updateSettings({ solana: { ...settings.solana, wallet_address: value } })} placeholder="Wallet for balances and signing" disabled={readOnly || isPending} />
              </Field>
              <Field label="Private Key">
                <Input value={settings.solana.private_key} onChange={(value) => updateSettings({ solana: { ...settings.solana, private_key: value } })} type="password" placeholder="Private key for live swaps" disabled={readOnly || isPending} />
              </Field>
              <Field label="RPC URL">
                <Input value={settings.solana.rpc_url} onChange={(value) => updateSettings({ solana: { ...settings.solana, rpc_url: value } })} placeholder="Optional custom Solana RPC" disabled={readOnly || isPending} />
              </Field>
              <Field label="Legacy Jupiter API Key">
                <Input value={settings.solana.jupiter_api_key} onChange={(value) => updateSettings({ solana: { ...settings.solana, jupiter_api_key: value } })} type="password" placeholder="Optional Jupiter key fallback" disabled={readOnly || isPending} />
              </Field>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <Field label="OKX API Key">
                <Input value={settings.solana.okx_api_key} onChange={(value) => updateSettings({ solana: { ...settings.solana, okx_api_key: value } })} placeholder="OKX API key" disabled={readOnly || isPending} />
              </Field>
              <Field label="OKX Secret">
                <Input value={settings.solana.okx_secret} onChange={(value) => updateSettings({ solana: { ...settings.solana, okx_secret: value } })} type="password" placeholder="OKX secret" disabled={readOnly || isPending} />
              </Field>
              <Field label="OKX Passphrase">
                <Input value={settings.solana.okx_passphrase} onChange={(value) => updateSettings({ solana: { ...settings.solana, okx_passphrase: value } })} type="password" placeholder="OKX passphrase" disabled={readOnly || isPending} />
              </Field>
              <Field label="OKX Project ID">
                <Input value={settings.solana.okx_project_id} onChange={(value) => updateSettings({ solana: { ...settings.solana, okx_project_id: value } })} placeholder="Optional OKX project id" disabled={readOnly || isPending} />
              </Field>
            </div>
          </div>
        </div>
      ) : null}

      <label className="flex items-center gap-3 rounded-[22px] border border-white/10 bg-white/5 px-4 py-3 text-sm text-mist/78">
        <input
          type="checkbox"
          checked={settings.remember_profile}
          onChange={(event) => updateSettings({ remember_profile: event.target.checked })}
          disabled={readOnly || isPending}
        />
        Save this broker profile to the account-level control panel
      </label>

      <div className="rounded-[24px] border border-white/10 bg-white/5 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-mist/45">Readiness Snapshot</p>
            <p className="mt-2 text-lg font-semibold text-sand">
              {credentialsReady ? "Credentials and route look usable." : "Some required broker fields are still missing."}
            </p>
          </div>
          <div className={`rounded-full border px-4 py-2 text-xs uppercase tracking-[0.24em] ${credentialsReady ? "border-lime-400/35 bg-lime-400/10 text-lime-200" : "border-amber-300/35 bg-amber-300/10 text-amber-100"}`}>
            {credentialsReady ? "Ready" : "Needs Input"}
          </div>
        </div>
        <p className="mt-3 text-sm leading-6 text-mist/68">
          {settings.exchange.toUpperCase()} in {settings.mode.toUpperCase()} mode, venue {settings.market_type.toUpperCase()}, risk budget {settings.risk_percent}%, paper equity ${settings.paper_starting_equity.toLocaleString()}.
        </p>
        {readOnly ? (
          <p className="mt-3 text-sm text-amber-100/85">
            This account is in viewer mode, so the control panel is read-only.
          </p>
        ) : null}
      </div>

      {errorMessage ? (
        <div className="rounded-[24px] border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
          {errorMessage}
        </div>
      ) : null}

      {successMessage ? (
        <div className="rounded-[24px] border border-lime-400/30 bg-lime-400/10 px-4 py-3 text-sm text-lime-100">
          {successMessage}
        </div>
      ) : null}

      <button type="submit" disabled={readOnly || isPending} className="auth-submit">
        {isPending ? "Saving..." : "Save Control Panel"}
      </button>
    </form>
  );
}
