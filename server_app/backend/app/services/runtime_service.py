from __future__ import annotations

import asyncio
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx


DEFAULT_RUNTIME_SYMBOLS: dict[str, list[str]] = {
    "oanda": ["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD"],
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _ensure_src_on_path() -> Path:
    repo_root = Path(__file__).resolve().parents[4]
    src_root = repo_root / "src"
    src_value = str(src_root)
    if src_value not in sys.path:
        sys.path.insert(0, src_value)
    return src_root


def _normalize_symbol(symbol: str | None) -> str:
    return str(symbol or "").strip().upper().replace("-", "_").replace("/", "_")


def _normalize_symbols(symbols: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for symbol in list(symbols or []):
        value = _normalize_symbol(symbol)
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _extract_numeric_from_mapping(payload: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key not in payload:
            continue
        try:
            return float(payload.get(key) or 0.0)
        except Exception:
            continue
    return float(default)


def _extract_balance_total(balance: dict[str, Any]) -> float:
    if not isinstance(balance, dict):
        return 0.0
    direct_value = _extract_numeric_from_mapping(balance, "equity", "total_equity", "net_liquidation", default=-1.0)
    if direct_value >= 0.0:
        return direct_value
    total = balance.get("total")
    if isinstance(total, dict):
        values = [_coerce_float(value) for value in total.values()]
        if values:
            return max(values)
    free = balance.get("free")
    if isinstance(free, dict):
        values = [_coerce_float(value) for value in free.values()]
        if values:
            return max(values)
    return 0.0


def _extract_balance_cash(balance: dict[str, Any], *, fallback: float) -> float:
    if not isinstance(balance, dict):
        return float(fallback)
    cash = _extract_numeric_from_mapping(balance, "cash", "buying_power", default=-1.0)
    if cash >= 0.0:
        return cash
    free = balance.get("free")
    if isinstance(free, dict):
        preferred = ("USD", "USDT", "USDC", "EUR", "GBP")
        for key in preferred:
            if key in free:
                return _coerce_float(free.get(key), fallback)
        values = [_coerce_float(value) for value in free.values()]
        if values:
            return max(values)
    return float(fallback)


def _asset_class_from_settings(settings: dict[str, Any]) -> str:
    broker_type = str(settings.get("broker_type") or "").strip().lower()
    exchange = str(settings.get("exchange") or "").strip().lower()
    if broker_type:
        return broker_type
    if exchange in {"oanda"}:
        return "forex"
    if exchange in {"alpaca", "schwab"}:
        return "stocks"
    if exchange in {"amp", "tradovate", "ibkr"}:
        return "futures"
    return "crypto"


def _normalize_order_status(status: str | None) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"filled", "closed"}:
        return "filled"
    if normalized in {"partially_filled", "partial", "working"}:
        return "partial"
    if normalized in {"canceled", "cancelled"}:
        return "canceled"
    if normalized.startswith("reject") or normalized in {"failed", "error"}:
        return "rejected"
    if normalized:
        return normalized
    return "pending"


@dataclass(slots=True)
class PaperPositionState:
    symbol: str
    asset_class: str
    quantity: float = 0.0
    average_price: float = 0.0
    last_price: float = 0.0
    realized_pnl: float = 0.0

    @property
    def side(self) -> str:
        if self.quantity < 0:
            return "short"
        return "long"

    @property
    def market_value(self) -> float:
        return abs(float(self.quantity) * float(self.last_price))

    @property
    def unrealized_pnl(self) -> float:
        if abs(self.quantity) <= 1e-12:
            return 0.0
        direction = 1.0 if self.quantity >= 0 else -1.0
        return (float(self.last_price) - float(self.average_price)) * abs(self.quantity) * direction

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": abs(float(self.quantity)),
            "side": self.side,
            "avg_price": float(self.average_price),
            "mark_price": float(self.last_price),
            "unrealized_pnl": float(self.unrealized_pnl),
            "realized_pnl": float(self.realized_pnl),
            "market_value": float(self.market_value),
            "notional_exposure": float(self.market_value),
            "asset_class": self.asset_class,
        }


@dataclass(slots=True)
class RuntimeSession:
    user_id: str
    settings: dict[str, Any]
    selected_symbols: list[str]
    initial_equity: float = 100000.0
    running: bool = False
    broker: Any | None = None
    market_data_broker: Any | None = None
    polling_task: asyncio.Task[Any] | None = None
    paper_cash: float = 100000.0
    paper_positions: dict[str, PaperPositionState] = field(default_factory=dict)
    closed_trades: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=100))
    learning_summary: dict[str, Any] = field(default_factory=dict)
    latest_market: dict[str, dict[str, Any]] = field(default_factory=dict)
    peak_equity: float = 100000.0
    last_error: str = ""
    last_refresh_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)


class RuntimeHostService:
    """Owns per-user trading runtimes for the web control plane."""

    def __init__(
        self,
        *,
        settings,
        state_store,
        poll_interval_seconds: float = 4.0,
    ) -> None:
        self.settings = settings
        self.state_store = state_store
        self.poll_interval_seconds = max(1.0, float(poll_interval_seconds or 4.0))
        self._sessions: dict[str, RuntimeSession] = {}
        self._lock = asyncio.Lock()

    async def shutdown(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            await self._close_session(session)

    def get_session(self, user_id: str) -> RuntimeSession | None:
        return self._sessions.get(str(user_id))

    def runtime_status(self, user_id: str) -> dict[str, Any]:
        session = self.get_session(user_id)
        if session is None:
            return {
                "active": False,
                "mode": "idle",
                "exchange": "",
                "selected_symbols": [],
                "ai_enabled": False,
                "auto_improve_enabled": False,
                "learning_summary": {"summary": "Runtime is idle."},
                "last_error": "",
            }
        settings = dict(session.settings or {})
        learning = dict(session.learning_summary or {})
        return {
            "active": bool(session.running),
            "mode": str(settings.get("mode") or "paper"),
            "exchange": str(settings.get("exchange") or settings.get("broker_type") or "paper"),
            "selected_symbols": list(session.selected_symbols),
            "ai_enabled": bool(settings.get("ai_assistance_enabled")) and bool(str(settings.get("openai_api_key") or "").strip()),
            "auto_improve_enabled": bool(settings.get("auto_improve_enabled")),
            "learning_summary": learning or {"summary": "Learning engine is waiting for closed trades."},
            "last_error": str(session.last_error or "").strip(),
        }

    def resolve_selected_symbols(
        self,
        workspace_settings: dict[str, Any],
        *,
        selected_symbols: list[str] | None = None,
    ) -> list[str]:
        explicit_symbols = _normalize_symbols(selected_symbols or [])
        if explicit_symbols:
            return explicit_symbols

        settings = dict(workspace_settings or {})
        watchlist_symbols = _normalize_symbols(settings.get("watchlist_symbols") or [])
        if watchlist_symbols:
            return watchlist_symbols

        exchange = str(settings.get("exchange") or "").strip().lower()
        broker_type = str(settings.get("broker_type") or "").strip().lower()
        if not exchange and broker_type == "forex":
            exchange = "oanda"
        return list(DEFAULT_RUNTIME_SYMBOLS.get(exchange) or [])

    async def start(
        self,
        user_id: str,
        workspace_settings: dict[str, Any],
        *,
        selected_symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_user_id = str(user_id)
        settings = dict(workspace_settings or {})
        symbols = self.resolve_selected_symbols(settings, selected_symbols=selected_symbols)
        initial_equity = max(1000.0, _coerce_float(settings.get("paper_starting_equity"), 100000.0))
        session = RuntimeSession(
            user_id=normalized_user_id,
            settings=settings,
            selected_symbols=symbols,
            initial_equity=initial_equity,
            paper_cash=initial_equity,
            peak_equity=initial_equity,
        )
        session.learning_summary = self._build_learning_summary(session)

        try:
            await self._bind_brokers(session)
            session.running = True
            await self.refresh_session(session)
        except Exception as exc:
            session.last_error = str(exc)
            await self._publish_runtime_alert(
                normalized_user_id,
                category="runtime",
                severity="warning",
                message=f"Runtime could not start cleanly: {exc}",
            )

        async with self._lock:
            previous = self._sessions.pop(normalized_user_id, None)
            self._sessions[normalized_user_id] = session
        if previous is not None:
            await self._close_session(previous)
        if session.running:
            session.polling_task = asyncio.create_task(self._poll_loop(session), name=f"runtime:{normalized_user_id}")
        return self.runtime_status(normalized_user_id)

    async def stop(self, user_id: str) -> dict[str, Any]:
        normalized_user_id = str(user_id)
        async with self._lock:
            session = self._sessions.pop(normalized_user_id, None)
        if session is not None:
            await self._close_session(session)
        return self.runtime_status(normalized_user_id)

    async def refresh(self, user_id: str) -> dict[str, Any]:
        session = self.get_session(user_id)
        if session is None:
            return self.runtime_status(user_id)
        await self.refresh_session(session)
        return self.runtime_status(user_id)

    async def submit_order(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        session = self.get_session(user_id)
        if session is None:
            return None
        if not session.running and session.broker is None and session.market_data_broker is None:
            return None

        if str(session.settings.get("mode") or "paper").strip().lower() == "live":
            result = await self._submit_live_order(session, payload)
        else:
            result = await self._submit_paper_order(session, payload)
        await self.refresh_session(session)
        return result

    async def assist(self, user_id: str, question: str) -> dict[str, Any]:
        session = self.get_session(user_id)
        prompt = str(question or "").strip()
        if not prompt:
            return {"provider": "runtime", "answer": "Ask a trading, risk, or performance question to use the assistant."}

        if session is None:
            return {
                "provider": "runtime",
                "answer": "The runtime is idle. Start trading with a real or paper workspace first so the assistant has live context.",
            }

        settings = dict(session.settings or {})
        api_key = str(settings.get("openai_api_key") or "").strip()
        model = str(settings.get("openai_model") or "gpt-5-mini").strip() or "gpt-5-mini"
        if bool(settings.get("ai_assistance_enabled")) and api_key:
            try:
                answer = await self._ask_openai(api_key=api_key, model=model, session=session, question=prompt)
                return {"provider": "openai", "answer": answer, "model": model}
            except Exception as exc:
                session.last_error = str(exc)
        return {"provider": "runtime", "answer": self._heuristic_assistant_reply(session, prompt)}

    async def _bind_brokers(self, session: RuntimeSession) -> None:
        settings = dict(session.settings or {})
        mode = str(settings.get("mode") or "paper").strip().lower() or "paper"
        exchange = str(settings.get("exchange") or settings.get("broker_type") or "paper").strip().lower() or "paper"
        if mode == "live":
            session.broker = await self._create_broker(settings)
            return
        if exchange != "paper":
            session.market_data_broker = await self._create_broker(settings)

    async def _create_broker(self, settings: dict[str, Any]) -> Any:
        _ensure_src_on_path()
        from broker.broker_factory import BrokerFactory

        broker_settings = self._build_broker_settings(settings)
        broker = BrokerFactory.create(SimpleNamespace(broker=broker_settings))
        connect = getattr(broker, "connect", None)
        if callable(connect):
            await connect()
        return broker

    def _build_broker_settings(self, settings: dict[str, Any]) -> SimpleNamespace:
        exchange = str(settings.get("exchange") or settings.get("broker_type") or "paper").strip().lower() or "paper"
        mode = str(settings.get("mode") or "paper").strip().lower() or "paper"
        broker_type = str(settings.get("broker_type") or "").strip().lower() or ("paper" if exchange == "paper" else "crypto")
        options = {
            "market_type": str(settings.get("market_type") or "auto").strip().lower() or "auto",
            "customer_region": str(settings.get("customer_region") or "us").strip().lower() or "us",
        }
        params = {
            "customer_region": options["customer_region"],
        }
        if settings.get("ibkr_connection_mode"):
            options["connection_mode"] = settings.get("ibkr_connection_mode")
            params["connection_mode"] = settings.get("ibkr_connection_mode")
        if settings.get("ibkr_environment"):
            options["environment"] = settings.get("ibkr_environment")
            params["environment"] = settings.get("ibkr_environment")
        if settings.get("ibkr_base_url"):
            params["base_url"] = settings.get("ibkr_base_url")
        if settings.get("ibkr_websocket_url"):
            params["websocket_url"] = settings.get("ibkr_websocket_url")
        if settings.get("ibkr_host"):
            params["host"] = settings.get("ibkr_host")
        if settings.get("ibkr_port"):
            params["port"] = settings.get("ibkr_port")
        if settings.get("ibkr_client_id"):
            params["client_id"] = settings.get("ibkr_client_id")
        if settings.get("schwab_environment"):
            options["schwab_environment"] = settings.get("schwab_environment")
            params["schwab_environment"] = settings.get("schwab_environment")

        token_value = str(settings.get("secret") or settings.get("api_key") or "").strip()
        api_key_value = str(settings.get("api_key") or settings.get("secret") or "").strip()

        return SimpleNamespace(
            type=broker_type,
            exchange=exchange,
            api_key=api_key_value,
            token=token_value,
            secret=str(settings.get("secret") or "").strip(),
            password=str(settings.get("password") or "").strip(),
            passphrase=str(settings.get("password") or "").strip(),
            account_id=str(settings.get("account_id") or "").strip(),
            mode=mode,
            sandbox=mode in {"paper", "sandbox", "practice"},
            customer_region=str(settings.get("customer_region") or "us").strip().lower() or "us",
            options=options,
            params=params,
            timeout=30000,
        )

    async def refresh_session(self, session: RuntimeSession) -> None:
        symbols = list(session.selected_symbols)
        for symbol in symbols:
            market_payload = await self._market_snapshot(session, symbol)
            if market_payload:
                session.latest_market[symbol] = market_payload
                await self.state_store.publish_market(symbol, market_payload)

        if str(session.settings.get("mode") or "paper").strip().lower() == "live":
            positions, portfolio_payload, risk_payload = await self._refresh_live_account_state(session)
        else:
            positions, portfolio_payload, risk_payload = self._refresh_paper_account_state(session)

        await self.state_store.publish_positions(session.user_id, positions)
        await self.state_store.publish_portfolio(session.user_id, portfolio_payload)
        await self.state_store.publish_risk(session.user_id, risk_payload)
        session.last_refresh_at = utc_now()

    async def _market_snapshot(self, session: RuntimeSession, symbol: str) -> dict[str, Any]:
        broker = session.broker if str(session.settings.get("mode") or "paper").strip().lower() == "live" else session.market_data_broker
        if broker is None:
            return dict(session.latest_market.get(symbol) or {})

        ticker = await self._safe_call(broker, "fetch_ticker", symbol)
        candles = await self._safe_call(broker, "fetch_ohlcv", symbol, timeframe="1m", limit=48)
        order_book = await self._safe_call(broker, "fetch_orderbook", symbol, limit=12)

        normalized_symbol = _normalize_symbol(symbol)
        last_price = self._extract_last_price(normalized_symbol, ticker, candles, session.latest_market.get(normalized_symbol))
        bid = self._extract_market_value(ticker, "bid", "best_bid", fallback=last_price)
        ask = self._extract_market_value(ticker, "ask", "best_ask", fallback=last_price)
        change_pct = self._extract_market_value(ticker, "percentage", "change_pct", "changePercent", default=0.0)
        volume = self._extract_market_value(ticker, "baseVolume", "quoteVolume", "volume", default=0.0)

        return {
            "symbol": normalized_symbol,
            "last": last_price,
            "change_pct": change_pct,
            "bid": bid,
            "ask": ask,
            "volume": volume,
            "candle_timeframe": "1m",
            "candles": self._normalize_candles(normalized_symbol, candles),
            "order_book": self._normalize_order_book(order_book),
            "updated_at": utc_now(),
        }

    async def _refresh_live_account_state(
        self,
        session: RuntimeSession,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        broker = session.broker
        if broker is None:
            raise RuntimeError("Live runtime does not have an active broker session.")

        balance = await self._safe_call(broker, "fetch_balance") or {}
        raw_positions = await self._safe_call(broker, "fetch_positions") or []
        positions = [self._normalize_live_position(session, row) for row in list(raw_positions or [])]
        positions = [row for row in positions if row["quantity"] > 0]

        total_equity = _extract_balance_total(balance)
        if total_equity <= 0.0:
            total_equity = sum(float(row["market_value"]) for row in positions) or session.initial_equity
        cash = _extract_balance_cash(balance, fallback=total_equity)
        gross_exposure = sum(float(row["notional_exposure"]) for row in positions)
        net_exposure = sum(
            float(row["notional_exposure"]) if row["side"] == "long" else -float(row["notional_exposure"])
            for row in positions
        )
        session.peak_equity = max(session.peak_equity, total_equity)
        drawdown = 0.0 if session.peak_equity <= 0 else max(0.0, (session.peak_equity - total_equity) / session.peak_equity)

        portfolio_payload = {
            "account_id": str(session.settings.get("account_id") or "primary"),
            "broker": str(session.settings.get("exchange") or session.settings.get("broker_type") or "paper"),
            "total_equity": total_equity,
            "cash": cash,
            "buying_power": _extract_numeric_from_mapping(balance, "buying_power", "available_funds", default=cash),
            "daily_pnl": total_equity - session.initial_equity,
            "weekly_pnl": total_equity - session.initial_equity,
            "monthly_pnl": total_equity - session.initial_equity,
            "gross_exposure": gross_exposure,
            "net_exposure": net_exposure,
            "max_drawdown": drawdown,
            "var_95": 0.0,
            "margin_usage": 0.0 if total_equity <= 0 else min(1.0, gross_exposure / max(total_equity, 1.0)),
            "risk_limits": {
                "risk_percent": int(session.settings.get("risk_percent") or 2),
                "mode": str(session.settings.get("mode") or "live"),
            },
            "updated_at": utc_now(),
        }
        risk_payload = {
            "drawdown": drawdown,
            "gross_exposure": gross_exposure,
            "net_exposure": net_exposure,
            "risk_limits": dict(portfolio_payload["risk_limits"]),
            "trading_enabled": True,
            "selected_symbols": list(session.selected_symbols),
            "updated_at": utc_now(),
        }
        return positions, portfolio_payload, risk_payload

    def _refresh_paper_account_state(
        self,
        session: RuntimeSession,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        positions: list[dict[str, Any]] = []
        for symbol, position in list(session.paper_positions.items()):
            if symbol in session.latest_market:
                position.last_price = _coerce_float(session.latest_market[symbol].get("last"), position.last_price)
            if abs(position.quantity) <= 1e-12:
                continue
            positions.append(position.to_payload())

        total_equity = float(session.paper_cash) + sum(
            (position.last_price - position.average_price) * abs(position.quantity) * (1.0 if position.quantity >= 0 else -1.0)
            + (position.average_price * position.quantity)
            for position in session.paper_positions.values()
        )
        if total_equity <= 0.0:
            total_equity = session.paper_cash
        gross_exposure = sum(float(row["notional_exposure"]) for row in positions)
        net_exposure = sum(
            float(row["notional_exposure"]) if row["side"] == "long" else -float(row["notional_exposure"])
            for row in positions
        )
        session.peak_equity = max(session.peak_equity, total_equity)
        drawdown = 0.0 if session.peak_equity <= 0 else max(0.0, (session.peak_equity - total_equity) / session.peak_equity)
        portfolio_payload = {
            "account_id": str(session.settings.get("account_id") or "paper"),
            "broker": f"{str(session.settings.get('exchange') or session.settings.get('broker_type') or 'paper')}:paper",
            "total_equity": total_equity,
            "cash": float(session.paper_cash),
            "buying_power": float(session.paper_cash),
            "daily_pnl": total_equity - session.initial_equity,
            "weekly_pnl": total_equity - session.initial_equity,
            "monthly_pnl": total_equity - session.initial_equity,
            "gross_exposure": gross_exposure,
            "net_exposure": net_exposure,
            "max_drawdown": drawdown,
            "var_95": 0.0,
            "margin_usage": 0.0 if total_equity <= 0 else min(1.0, gross_exposure / max(total_equity, 1.0)),
            "risk_limits": {
                "risk_percent": int(session.settings.get("risk_percent") or 2),
                "mode": "paper",
                "auto_improve_enabled": bool(session.settings.get("auto_improve_enabled")),
            },
            "learning_summary": dict(session.learning_summary or {}),
            "updated_at": utc_now(),
        }
        risk_payload = {
            "drawdown": drawdown,
            "gross_exposure": gross_exposure,
            "net_exposure": net_exposure,
            "risk_limits": dict(portfolio_payload["risk_limits"]),
            "trading_enabled": True,
            "selected_symbols": list(session.selected_symbols),
            "updated_at": utc_now(),
        }
        return positions, portfolio_payload, risk_payload

    async def _submit_live_order(self, session: RuntimeSession, payload: dict[str, Any]) -> dict[str, Any] | None:
        broker = session.broker
        if broker is None:
            return None
        side = str(payload.get("side") or "").strip().lower()
        quantity = _coerce_float(payload.get("quantity"), 0.0)
        symbol = _normalize_symbol(payload.get("symbol"))
        execution = await broker.place_order(
            {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "amount": quantity,
                "order_type": str(payload.get("order_type") or "market").strip().lower() or "market",
                "type": str(payload.get("order_type") or "market").strip().lower() or "market",
                "price": payload.get("limit_price"),
                "stop_price": payload.get("stop_price"),
                "stop_loss": payload.get("stop_loss"),
                "take_profit": payload.get("take_profit"),
                "timeframe": payload.get("timeframe"),
            }
        )
        result = dict(execution or {})
        status = _normalize_order_status(result.get("status"))
        return {
            "order_id": str(result.get("id") or result.get("order_id") or payload.get("order_id") or uuid4()),
            "status": status,
            "average_price": _coerce_float(result.get("fill_price", result.get("price")), 0.0) or None,
            "filled_quantity": _coerce_float(result.get("filled_quantity", result.get("filled")), quantity if status == "filled" else 0.0),
            "venue": str(session.settings.get("exchange") or session.settings.get("broker_type") or "broker"),
            "details": {
                "runtime": "live",
                "raw_execution": result,
                "timeframe": payload.get("timeframe"),
                "stop_price": payload.get("stop_price"),
                "stop_loss": payload.get("stop_loss"),
                "take_profit": payload.get("take_profit"),
            },
        }

    async def _submit_paper_order(self, session: RuntimeSession, payload: dict[str, Any]) -> dict[str, Any] | None:
        symbol = _normalize_symbol(payload.get("symbol"))
        market = dict(session.latest_market.get(symbol) or {})
        if not market:
            market = await self._market_snapshot(session, symbol)
            if market:
                session.latest_market[symbol] = market
                await self.state_store.publish_market(symbol, market)
        fill_price = _coerce_float(market.get("ask" if str(payload.get("side") or "").strip().lower() == "buy" else "bid"), 0.0)
        if fill_price <= 0.0:
            fill_price = _coerce_float(market.get("last"), 0.0)
        if fill_price <= 0.0:
            return None

        quantity = max(0.0, _coerce_float(payload.get("quantity"), 0.0))
        side = str(payload.get("side") or "").strip().lower() or "buy"
        direction = 1.0 if side == "buy" else -1.0
        signed_quantity = quantity * direction
        asset_class = _asset_class_from_settings(session.settings)

        position = session.paper_positions.get(symbol)
        if position is None:
            position = PaperPositionState(symbol=symbol, asset_class=asset_class, last_price=fill_price)
            session.paper_positions[symbol] = position
        original_average_price = float(position.average_price)
        original_quantity = float(position.quantity)
        position.last_price = fill_price

        realized_pnl = 0.0
        if abs(original_quantity) > 1e-12 and (original_quantity > 0 > signed_quantity or original_quantity < 0 < signed_quantity):
            closing_quantity = min(abs(original_quantity), quantity)
            if original_quantity > 0:
                realized_pnl += (fill_price - original_average_price) * closing_quantity
            else:
                realized_pnl += (original_average_price - fill_price) * closing_quantity

        new_quantity = original_quantity + signed_quantity
        if abs(original_quantity) <= 1e-12 or original_quantity * signed_quantity > 0:
            gross_quantity = abs(original_quantity) + quantity
            if gross_quantity > 0:
                weighted_cost = (abs(original_quantity) * original_average_price) + (quantity * fill_price)
                position.average_price = weighted_cost / gross_quantity
            position.quantity = new_quantity
        elif abs(new_quantity) <= 1e-12:
            position.quantity = 0.0
            position.average_price = 0.0
        else:
            if abs(quantity) > abs(original_quantity):
                position.quantity = new_quantity
                position.average_price = fill_price
            else:
                position.quantity = new_quantity

        session.paper_cash -= fill_price * signed_quantity
        position.realized_pnl += realized_pnl
        position.last_price = fill_price

        if abs(original_quantity) > 1e-12 and abs(position.quantity) <= 1e-12:
            closed_side = "long" if original_quantity > 0 else "short"
            session.closed_trades.appendleft(
                {
                    "symbol": symbol,
                    "pnl": realized_pnl,
                    "entry_side": closed_side,
                    "exit_side": side,
                    "quantity": min(abs(original_quantity), quantity),
                    "entry_price": original_average_price or fill_price,
                    "exit_price": fill_price,
                    "timestamp": utc_now().isoformat(),
                }
            )
            session.learning_summary = self._build_learning_summary(session)

        result = {
            "order_id": str(payload.get("order_id") or f"paper-{uuid4().hex[:12]}"),
            "status": "filled",
            "average_price": fill_price,
            "filled_quantity": quantity,
            "venue": f"{str(session.settings.get('exchange') or session.settings.get('broker_type') or 'paper')}:paper",
            "details": {
                "runtime": "paper",
                "cash_after_fill": session.paper_cash,
                "realized_pnl": realized_pnl,
                "timeframe": payload.get("timeframe"),
                "stop_price": payload.get("stop_price"),
                "stop_loss": payload.get("stop_loss"),
                "take_profit": payload.get("take_profit"),
            },
        }
        return result

    def _build_learning_summary(self, session: RuntimeSession) -> dict[str, Any]:
        rows = list(session.closed_trades)
        if not rows:
            return {
                "summary": "Learning engine is waiting for closed paper trades.",
                "trade_count": 0,
                "win_rate": 0.0,
                "average_pnl": 0.0,
            }
        wins = sum(1 for row in rows if _coerce_float(row.get("pnl")) > 0)
        total = len(rows)
        average_pnl = sum(_coerce_float(row.get("pnl")) for row in rows) / max(total, 1)
        latest = rows[0]
        if average_pnl >= 0:
            headline = "Paper learning is improving the playbook."
            next_step = "Keep the same setups, but scale a little slower after back-to-back losses."
        else:
            headline = "Paper learning found recurring execution drag."
            next_step = "Trim position size and wait for stronger confirmation before re-entering."
        latest_label = f"Latest closed trade {str(latest.get('symbol') or '').upper()} PnL {float(_coerce_float(latest.get('pnl'))):+,.2f}."
        return {
            "summary": f"{headline} {latest_label} {next_step}",
            "trade_count": total,
            "win_rate": wins / max(total, 1),
            "average_pnl": average_pnl,
        }

    async def _ask_openai(self, *, api_key: str, model: str, session: RuntimeSession, question: str) -> str:
        runtime_state = self.runtime_status(session.user_id)
        market_lines = []
        for symbol in list(session.selected_symbols)[:4]:
            market = dict(session.latest_market.get(symbol) or {})
            if not market:
                continue
            market_lines.append(
                f"{symbol}: last={_coerce_float(market.get('last')):.4f} change_pct={_coerce_float(market.get('change_pct')):+.2f} "
                f"volume={_coerce_float(market.get('volume')):,.0f}"
            )
        learning_summary = dict(runtime_state.get("learning_summary") or {})
        prompt = [
            {"role": "system", "content": "You are Sopotek's web trading assistant. Give concise, practical guidance using only the provided runtime context."},
            {
                "role": "user",
                "content": (
                    f"Runtime mode: {runtime_state.get('mode')}\n"
                    f"Exchange: {runtime_state.get('exchange')}\n"
                    f"Selected symbols: {', '.join(runtime_state.get('selected_symbols') or []) or 'none'}\n"
                    f"Learning summary: {learning_summary.get('summary') or 'none'}\n"
                    f"Market context:\n" + ("\n".join(market_lines) if market_lines else "No live market snapshot available.") + "\n\n"
                    f"Question: {question}"
                ),
            },
        ]
        payload = {"model": model, "input": prompt}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        timeout = httpx.Timeout(12.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post("https://api.openai.com/v1/responses", json=payload, headers=headers)
            data = response.json()
            if response.status_code >= 400:
                message = data.get("error", {}).get("message") or str(data)
                raise RuntimeError(f"OpenAI assistant request failed: {message}")
        output_text = str(data.get("output_text") or "").strip()
        if output_text:
            return output_text
        lines: list[str] = []
        for item in list(data.get("output") or []):
            for content in list(item.get("content") or []):
                text = str(content.get("text") or "").strip()
                if text:
                    lines.append(text)
        if lines:
            return "\n".join(lines)
        raise RuntimeError("OpenAI assistant returned an empty response.")

    def _heuristic_assistant_reply(self, session: RuntimeSession, question: str) -> str:
        status = self.runtime_status(session.user_id)
        learning = dict(status.get("learning_summary") or {})
        market_bits: list[str] = []
        for symbol in list(session.selected_symbols)[:3]:
            market = dict(session.latest_market.get(symbol) or {})
            if not market:
                continue
            market_bits.append(
                f"{symbol} last {_coerce_float(market.get('last')):.4f} and change {_coerce_float(market.get('change_pct')):+.2f}%."
            )
        question_text = str(question or "").strip()
        if "risk" in question_text.lower():
            return (
                f"Runtime is {status.get('mode')} on {status.get('exchange')}. "
                f"Selected symbols: {', '.join(status.get('selected_symbols') or []) or 'none'}. "
                f"{learning.get('summary') or 'Learning feedback is not available yet.'}"
            )
        return " ".join(
            bit
            for bit in [
                f"Runtime is {status.get('mode')} on {status.get('exchange')}.",
                " ".join(market_bits),
                str(learning.get("summary") or "").strip(),
            ]
            if bit
        ).strip() or "The runtime does not have enough live context yet."

    async def _poll_loop(self, session: RuntimeSession) -> None:
        try:
            while session.running:
                try:
                    await self.refresh_session(session)
                except Exception as exc:
                    session.last_error = str(exc)
                    await self._publish_runtime_alert(
                        session.user_id,
                        category="runtime",
                        severity="warning",
                        message=f"Runtime refresh failed: {exc}",
                    )
                await asyncio.sleep(self.poll_interval_seconds)
        except asyncio.CancelledError:
            raise

    async def _close_session(self, session: RuntimeSession) -> None:
        session.running = False
        if session.polling_task is not None:
            session.polling_task.cancel()
            try:
                await session.polling_task
            except asyncio.CancelledError:
                pass
            session.polling_task = None
        for broker in (session.broker, session.market_data_broker):
            close = getattr(broker, "close", None)
            if callable(close):
                try:
                    await close()
                except Exception:
                    pass

    async def _publish_runtime_alert(self, user_id: str, *, category: str, severity: str, message: str) -> None:
        await self.state_store.publish_alert(
            str(user_id),
            {
                "category": category,
                "severity": severity,
                "message": message,
                "created_at": utc_now(),
            },
        )

    async def _safe_call(self, target: Any, method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(target, method_name, None)
        if not callable(method):
            return None
        try:
            return await method(*args, **kwargs)
        except NotImplementedError:
            return None

    def _extract_market_value(self, payload: Any, *keys: str, default: float = 0.0, fallback: float | None = None) -> float:
        if isinstance(payload, dict):
            for key in keys:
                if key not in payload:
                    continue
                try:
                    return float(payload.get(key) or 0.0)
                except Exception:
                    continue
        if fallback is not None:
            return float(fallback)
        return float(default)

    def _extract_last_price(
        self,
        symbol: str,
        ticker: Any,
        candles: Any,
        previous_market: dict[str, Any] | None,
    ) -> float:
        _ = symbol
        if isinstance(ticker, dict):
            for key in ("last", "close", "price", "bid", "ask"):
                value = ticker.get(key)
                try:
                    if value is not None:
                        return float(value)
                except Exception:
                    continue
        for candle in reversed(list(candles or [])):
            try:
                if isinstance(candle, dict):
                    return float(candle.get("close") or candle.get("price") or 0.0)
                return float(candle[4])
            except Exception:
                continue
        if isinstance(previous_market, dict):
            return _coerce_float(previous_market.get("last"), 0.0)
        return 0.0

    def _normalize_candles(self, symbol: str, candles: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for row in list(candles or [])[-48:]:
            try:
                if isinstance(row, dict):
                    normalized.append(
                        {
                            "time": row.get("time") or row.get("timestamp") or row.get("datetime"),
                            "open": _coerce_float(row.get("open")),
                            "high": _coerce_float(row.get("high")),
                            "low": _coerce_float(row.get("low")),
                            "close": _coerce_float(row.get("close")),
                            "volume": _coerce_float(row.get("volume")),
                        }
                    )
                    continue
                timestamp_ms, open_, high, low, close, volume = row[:6]
                normalized.append(
                    {
                        "time": timestamp_ms,
                        "open": _coerce_float(open_),
                        "high": _coerce_float(high),
                        "low": _coerce_float(low),
                        "close": _coerce_float(close),
                        "volume": _coerce_float(volume),
                    }
                )
            except Exception:
                continue
        return normalized

    def _normalize_order_book(self, payload: Any) -> dict[str, list[dict[str, float]]]:
        if not isinstance(payload, dict):
            return {"bids": [], "asks": []}
        bids = []
        asks = []
        for side_name, bucket in (("bids", bids), ("asks", asks)):
            for row in list(payload.get(side_name) or [])[:12]:
                try:
                    if isinstance(row, dict):
                        bucket.append({"price": _coerce_float(row.get("price")), "size": _coerce_float(row.get("size"))})
                    else:
                        bucket.append({"price": _coerce_float(row[0]), "size": _coerce_float(row[1])})
                except Exception:
                    continue
        return {"bids": bids, "asks": asks}

    def _normalize_live_position(self, session: RuntimeSession, payload: Any) -> dict[str, Any]:
        row = dict(payload or {}) if isinstance(payload, dict) else {}
        symbol = _normalize_symbol(row.get("symbol") or row.get("instrument") or "")
        quantity = abs(
            _coerce_float(
                row.get("quantity")
                or row.get("amount")
                or row.get("contracts")
                or row.get("positionAmt"),
                0.0,
            )
        )
        if quantity <= 0.0:
            return {
                "symbol": symbol,
                "quantity": 0.0,
                "side": "long",
                "avg_price": 0.0,
                "mark_price": 0.0,
                "unrealized_pnl": 0.0,
                "realized_pnl": 0.0,
                "market_value": 0.0,
                "notional_exposure": 0.0,
                "asset_class": _asset_class_from_settings(session.settings),
            }
        side_value = str(row.get("side") or "").strip().lower()
        if not side_value:
            signed_quantity = _coerce_float(row.get("contracts") or row.get("positionAmt") or row.get("quantity") or row.get("amount"), 0.0)
            side_value = "short" if signed_quantity < 0 else "long"
        avg_price = _coerce_float(row.get("avg_price") or row.get("average_price") or row.get("entry_price"), 0.0)
        mark_price = _coerce_float(
            row.get("mark_price") or row.get("current_price") or row.get("price") or row.get("last"),
            avg_price,
        )
        unrealized_pnl = _coerce_float(row.get("unrealized_pnl") or row.get("pnl"), 0.0)
        market_value = abs(quantity * mark_price)
        return {
            "symbol": symbol,
            "quantity": quantity,
            "side": "short" if side_value == "short" else "long",
            "avg_price": avg_price,
            "mark_price": mark_price,
            "unrealized_pnl": unrealized_pnl,
            "realized_pnl": _coerce_float(row.get("realized_pnl"), 0.0),
            "market_value": market_value,
            "notional_exposure": market_value,
            "asset_class": _asset_class_from_settings(session.settings),
        }
