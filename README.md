# Sopotek Trading AI

<p align="center">
  <img alt="Sopotek Trading AI logo" src="src/assets/logo.png" width="170" height="170">
</p>

Sopotek Trading AI is a next-generation trading workstation engineered by Sopotek Corporation to bridge the gap between retail platforms and institutional trading systems.

The platform combines real-time market connectivity, AI-driven decision support, execution infrastructure, and risk-aware automation into a single desktop environment.

With integrated backtesting, multi-asset support, and intelligent workflow automation, Sopotek empowers traders to scale from manual strategies to fully autonomous trading systems.

## Version And Status

- Package version: `1.0.0`
- Company: `Sopotek Corporation`
- Product state: first publishable desktop release with a menu-driven Telegram remote console
- Safety posture: live-capable, but still best validated through `paper`, `practice`, or `sandbox` sessions before any meaningful live capital use

## What The App Includes

- Dashboard for broker selection, mode, credentials, strategy choice, licensing, and launch control
- Terminal workspace with chart tabs, detachable charts, tiled/cascaded layouts, and layout restore
- MT4/MT5-style chart handling including candlesticks, indicators, orderbook heatmap, depth chart, market info, Fibonacci, and chart trading interactions
- Manual trade ticket with broker-aware formatting, suggested SL/TP, chart-linked entry, take-profit levels, and live preflight sizing from balance, margin, or equity
- Derivatives-ready broker layer for options and futures, including normalized instruments, multi-leg option structures, contract metadata, and broker-routed execution
- AI trading controls, AI signal monitor, recommendations, Sopotek Pilot, news overlays, and Telegram command handling
- Open orders, positions, trade log, closed journal, trade review, position analysis, performance analytics, system health tools, and Coinbase-style recent market trades in the Order Book dock
- Risk and behavior protection including risk profiles, a dedicated `Risk` menu, behavior guard, kill switch, drawdown-aware restrictions, and session health status
- Backtesting, strategy optimization, journaling, trade checklist workflow, and local persistence through SQLite and QSettings, including date-range selection, animated in-progress equity graphing, and user-selected report export folders

## Key Workflows

### Operator Workflow
1. Launch from the dashboard.
2. Select broker, mode, and strategy.
3. Open one or more charts.
4. Use the chart tabs to review `Candlestick`, `Depth Chart`, and `Market Info`, then inspect `Order Book` and `Recent Trades`.
5. Use the `Trade Checklist` and `Trade Recommendations` windows before placing risk.
6. Place a manual order or enable AI trading only after confirming status, balances, and data quality.
7. Monitor `Trade Log`, `Open Orders`, `Positions`, `System Status`, `Behavior Guard`, and `Performance`.
8. Review trades later in `Closed Journal`, `Trade Review`, and `Journal Review`.

### Remote Workflow
- Receive Telegram notifications for trade activity.
- Use the menu-driven Telegram console with `Overview`, `Portfolio`, `Market Intel`, `Performance`, `Workspace`, and `Controls` panels.
- Keep using slash commands when needed for compatibility, including status, balances, screenshots, chart captures, recommendations, and position analysis.
- Ask Sopotek Pilot questions inside the app or through Telegram.
- Runtime translation now reaches dynamic summaries and rich-text detail views in addition to static labels, so translated sessions stay consistent behind the scenes.

### Suggested First Validation Path
1. Launch in `paper`, `practice`, or `sandbox`.
2. Open one symbol and confirm candles, ticker, order book, recent trades, and depth behavior.
3. Place one very small manual order.
4. Confirm `Trade Log`, `Open Orders`, `Positions`, and `Closed Journal` update in a consistent way.
5. Test `Sopotek Pilot`, Telegram, and screenshots only after the broker session is healthy.
6. Enable AI trading only after manual execution and review workflows are behaving as expected.

### Backtesting Workflow
1. Open `Strategy Tester` from the terminal workspace.
2. Pick the symbol, strategy, timeframe, and the exact `Start Date` / `End Date` you want to test.
3. Start the run and watch the graph tab for the animated live-progress curve while the backtest is executing.
4. Review `Results`, `Graph`, `Report`, and `Journal` after completion.
5. Use `Generate Report` to choose the destination folder for the exported PDF and spreadsheet files.

## Architecture At A Glance

```mermaid
flowchart LR
    D["Dashboard"] --> C["AppController"]
    T["Terminal"] --> C
    C --> B["BrokerFactory / Broker Adapters"]
    C --> TS["SopotekTrading"]
    TS --> SR["StrategyRegistry / Strategy Engine"]
    TS --> EX["ExecutionManager / OrderRouter"]
    EX --> DB["TradeRepository / SQLite"]
    B --> MD["Ticker / Candle / Orderbook / Position Data"]
    MD --> BUF["Buffers + Repositories"]
    BUF --> T
    C --> TG["TelegramService"]
    C --> NS["NewsService"]
    C --> VS["Voice + OpenAI Speech / Chat"]
```

## Supported Modes And Brokers

### Modes
- `paper`: local simulation path
- `practice` or `sandbox`: broker-side test environments where supported
- `live`: real broker execution

### Broker Families
- `crypto` through `CCXTBroker`
- `forex` through `OandaBroker`
- `stocks` through `AlpacaBroker`
- `options` through `TDAmeritradeBroker` for Schwab-backed option routing
- `futures` and broader `derivatives` through `IBKRBroker`
- `futures` through `AMPFuturesBroker`
- `futures` through `TradovateBroker`
- `paper` through `PaperBroker`
- `stellar` through `StellarBroker`

### Derivatives Layer
- Common broker contract now includes `connect()`, `disconnect()`, `get_account_info()`, `get_positions()`, `place_order()`, `cancel_order()`, and `stream_market_data()`.
- Instrument modeling now supports `stock`, `option`, `future`, `forex`, and `crypto` with expiry, strike, option right, contract size, and multiplier metadata.
- `OptionsEngine` adds normalized option-chain access, Black-Scholes Greeks, and multi-leg builders for spreads, straddles, and iron condors.
- `FuturesEngine` adds normalized contract metadata, rollover checks, margin estimation, leverage tracking, and liquidation-threshold helpers.
- `ExecutionManager` and `OrderRouter` now preserve derivative-specific payloads such as instrument metadata, multi-leg orders, bracket instructions, and broker hints.
- `RiskEngine` now tracks derivatives-specific controls including margin usage, futures liquidation proximity, gamma exposure, and theta decay.

## Recent Reliability Updates

- Broker-backed balances, equity, and positions are favored over local fallbacks when the connected adapter can provide them directly.
- Coinbase runtime now treats venue selection more explicitly, keeping `spot` and `derivative` paths distinct while leaving stocks and options disabled there until a dedicated adapter path is added.
- Coinbase history loading now backfills candle requests in chunks, skips unsupported stale symbols safely, and avoids fabricating duplicate synthetic candles when real history is missing.
- Oanda history loading now retries empty latest-candle responses with an explicit recent time window and can fall back to midpoint candles when bid or ask candles come back empty.
- Charts now show a visible loading state, a `No data received.` background message for empty responses, and shorter-history notices when the broker returns fewer candles than requested.
- Malformed OHLCV rows are sanitized before they are cached or drawn so bad timestamps, duplicate rows, `NaN`, `inf`, and invalid high or low bounds do not corrupt the chart.
- Manual live orders now size from the latest available balance, free margin, or equity snapshot before submission, especially on leveraged FX paths such as Oanda.
- If a broker still rejects a manual order for insufficient funds, margin, or buying power, the app retries once with a smaller balance-sized amount and records the reason in the order feedback.
- `Settings` and `Risk` are separate top-level menu entries in the terminal so general preferences and risk controls are easier to reach independently.

## Recommended Local Setup

### 1. Create A Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Launch The Desktop App
```powershell
python main.py
```

The repository root `main.py` is the recommended launcher from the workspace root.
It bootstraps the desktop app and delegates to the real entry point at `src/main.py`.

For one-click launch on Windows, double-click `Launch Sopotek Trading AI.cmd`.
That launcher uses the repo's vendored desktop dependencies, starts the UI on the host machine, and writes timestamped startup logs under `logs/`. The newest log file paths are recorded in `logs/host-ui-latest.txt`.

### 3. Start Safely
1. Open the dashboard.
2. Choose broker type, exchange, and mode.
3. Start with `paper`, `practice`, or `sandbox`.
4. Confirm symbols, candles, balances, positions, and open orders.
5. Test the manual order flow before enabling AI trading.
6. Validate Telegram or OpenAI integration only after the core trading path is stable.
7. Use `live` only when the same workflow is already behaving correctly in a non-production session.

### 4. Integration Credentials
1. Create an OpenAI API key at `https://platform.openai.com/api-keys`, paste it into `Settings -> Integrations`, and run `Test OpenAI`.
2. Create a Telegram bot with `@BotFather` using `/newbot`, paste the bot token into `Settings -> Integrations`, then message the bot once.
3. Open `https://api.telegram.org/bot<token>/getUpdates`, copy `message.chat.id`, and paste it into `Settings -> Integrations -> Telegram chat ID`.
4. Use `/help` in Telegram for the built-in command list and setup reminders after the bot is connected.

## Documentation Map

- [Getting Started](docs/getting-started.md)
- [Full App Guide](docs/FULL_APP_GUIDE.md)
- [Release Notes](docs/release-notes.md)
- [Architecture](docs/architecture.md)
- [Strategies](docs/strategy_docs.md)
- [Brokers And Modes](docs/brokers-and-modes.md)
- [Derivatives Guide](docs/derivatives.md)
- [UI Workspace Guide](docs/ui-workspace.md)
- [Integrations](docs/integrations.md)
- [Internal API Notes](docs/api.md)
- [Refactor Roadmap](docs/refactor-roadmap.md)
- [Testing And Operations](docs/testing-and-operations.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Contributing Guide](docs/contributing.md)
- [Development Notes](docs/development.md)

## Built-In Command Surfaces

### Telegram
The bot can handle:

- status, balances, positions, and open orders
- screenshots and chart screenshots
- recommendation and performance summaries
- menu-driven inline navigation and confirmation-gated remote controls
- plain-text Sopotek Pilot conversations in addition to slash commands

### Sopotek Pilot
The in-app assistant can:

- answer questions about balances, positions, performance, journal state, and recommendations
- open windows such as `Settings`, `Position Analysis`, `Closed Journal`, and `Performance`
- manage Telegram state
- place, cancel, or close trades through confirmation-gated commands
- listen and speak when voice support is configured

## Testing

Run the full suite:

```powershell
python -m pytest src\tests -q
```

Run a focused subset:

```powershell
python -m pytest src\tests\test_execution.py src\tests\test_other_broker_adapters.py src\tests\test_storage_runtime.py -q
```

Run the suite with coverage output:

```powershell
python -m pytest src\tests -q --cov=src --cov-branch --cov-report=term-missing:skip-covered --cov-report=xml --cov-report=html
```

## Packaging And Docs

Build package artifacts:

```powershell
python -m build
```

Build documentation site:

```powershell
python -m mkdocs build -f docs\mkdocs.yml
```

Serve docs locally:

```powershell
python -m mkdocs serve -f docs\mkdocs.yml
```

## Docker

Build the container image:

```powershell
docker build -t sopotek-trading-ai .
```

Validate the compose stack:

```powershell
docker compose config
```

Run the local MySQL-backed stack:

```powershell
docker compose up -d mysql app
```

Run the desktop UI in your browser over local HTTP:

```powershell
docker compose --profile browser up app-http
```

Then open:

```text
http://localhost:6080/vnc.html?autoconnect=1&resize=scale
```

The browser UI is published only on `127.0.0.1` by default, so it is local-machine only unless you deliberately change the port binding.
The browser profile forces software rendering and disables embedded Qt WebEngine panels inside the container, so desk tools such as Trader TV fall back to browser-launch links instead of in-app TradingView or YouTube embeds. This avoids the common Vulkan / Chromium crashes that happen under Xvfb and noVNC.
The browser profile also starts an X11 clipboard bridge so copy and paste work more reliably inside the containerized Qt desktop. Because this is still running through noVNC in a browser tab, your browser may block direct `Ctrl+V` access to the system clipboard. If that happens, use the noVNC clipboard panel to paste text into the app.

Run the headless profile:

```powershell
docker compose --profile headless up app-headless
```

Compose defaults the app to the local `mysql` service using `mysql+pymysql://`. Override `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`, or `MYSQL_PORT` in your shell or `.env` before launch if you want different local credentials.

When you configure the database in the app Preferences, use one of these URLs:

- App running on Windows or directly on the host:
  `mysql+pymysql://sopotek:sopotek_local@localhost:3306/sopotek_trading?charset=utf8mb4`
- App running inside the same Docker Compose stack:
  `mysql+pymysql://sopotek:sopotek_local@mysql:3306/sopotek_trading?charset=utf8mb4`

If you changed `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, or `MYSQL_PORT` in `.env`, replace those values in the URL.

## CI And Release Workflows

- `CI`: runs flake8, full pytest coverage, package build validation, and Docker image smoke checks on pull requests and pushes to `master`.
- `Publish Docker Image`: builds and pushes multi-arch images to GitHub Container Registry for `master` and version tags.
- `Publish Python Package`: builds and validates wheel and sdist artifacts, then publishes them to PyPI on GitHub releases or manual dispatch.

## Storage And Runtime Files

- Local Docker database: MySQL persisted in the `mysql_data` volume
- Local non-Docker fallback database: `data/sopotek_trading.db`
- Logs: `logs/` and `src/logs/`
- Generated screenshots: `output/screenshots/`
- Detached chart layouts and most operator preferences: persisted through `QSettings`
- Generated reports and artifacts: `src/reports/`, `output/`, and other runtime output folders depending on workflow

## Safety Notes

- The application can route live orders when the broker session is configured for live execution.
- Behavior guard, risk profiles, and the kill switch are protection layers, not guarantees of profitability.
- Rejected broker orders, including low-margin or insufficient-funds cases, are surfaced back into the UI and logging paths.
- Manual order review can reduce requested size before submission when balances, margin, or equity do not support the full amount, and the operator sees the sizing reason in the feedback path.
- Always validate symbol precision, size rules, and venue permissions with the actual broker before risking live capital.

## License

`Proprietary - Sopotek Corporation` as declared in [pyproject.toml](pyproject.toml).
