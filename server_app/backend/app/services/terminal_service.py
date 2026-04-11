from __future__ import annotations

import shlex
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LogLevel, StrategyStatus, UserRole
from app.models.strategy import Strategy
from app.models.user import User
from app.models.workspace_config import WorkspaceConfig
from app.schemas.orders import OrderCreateRequest
from app.schemas.strategies import StrategyUpdateRequest
from app.schemas.terminal import (
    TerminalAssistantResponse,
    TerminalCommandResponse,
    TerminalCommandParameterSpec,
    TerminalCommandSpec,
    TerminalManifestResponse,
    TerminalSessionSpec,
)
from app.schemas.workspace import WorkspaceSettings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


TRADE_OPTION_ALIASES = {
    "type": "order_type",
    "price": "limit_price",
    "limit": "limit_price",
    "limit_price": "limit_price",
    "stop": "stop_price",
    "stop_price": "stop_price",
    "sl": "stop_loss",
    "stop_loss": "stop_loss",
    "tp": "take_profit",
    "take_profit": "take_profit",
    "tf": "timeframe",
    "timeframe": "timeframe",
    "strategy": "strategy",
}
TRADE_OPTION_NAMES = set(TRADE_OPTION_ALIASES.values())
BACKTEST_OPTION_ALIASES = {"tf": "timeframe", "timeframe": "timeframe", "strategy": "strategy"}
BACKTEST_OPTION_NAMES = set(BACKTEST_OPTION_ALIASES.values())
DEFAULT_TERMINAL_KIND = "execution"
TERMINAL_KIND_SPECS: tuple[tuple[str, str, str], ...] = (
    ("control", "Control", "Session posture, launch controls, and broker guardrails."),
    ("execution", "Execution", "Orders, markets, and intervention flow for the active broker desk."),
    ("review", "Review", "Risk readback, positions, and agent reasoning for the desk."),
)


class TerminalService:
    def __init__(self, *, settings, state_store, control_service, runtime_service) -> None:
        self.settings = settings
        self.state_store = state_store
        self.control_service = control_service
        self.runtime_service = runtime_service
        self._history: dict[str, deque[TerminalCommandResponse]] = defaultdict(lambda: deque(maxlen=120))
        default_settings = WorkspaceSettings()
        self._manifest = TerminalManifestResponse(
            active_terminal_id="",
            active_terminal_label="",
            workspace_key="",
            broker_label="",
            account_label="",
            mode=default_settings.mode,
            banners=[
                "Integrated trading terminal for market discovery, risk checks, strategy control, and guided execution.",
                "Desktop and server terminal defaults now share the same timeframe, order-type, risk, and strategy parameter surface.",
            ],
            examples=[
                "/markets",
                "/params",
                "/trade BTCUSDT long 0.01 order_type=limit limit_price=102500 timeframe=4h",
                "/positions",
                "/risk",
                "/strategy start adaptive_trend",
                "/backtest BTCUSDT 1y timeframe=4h strategy=adaptive_trend",
                "/agents status",
                "/assist Summarize the current desk risk",
            ],
            commands=[
                TerminalCommandSpec(
                    command="/help",
                    summary="List supported commands and example workflows.",
                    example="/help",
                    permission="viewer",
                ),
                TerminalCommandSpec(
                    command="/markets",
                    summary="Inspect the current watchlist or a specific symbol feed.",
                    example="/markets BTCUSDT",
                    permission="viewer",
                ),
                TerminalCommandSpec(
                    command="/positions",
                    summary="Show active positions and unrealized PnL.",
                    example="/positions",
                    permission="viewer",
                ),
                TerminalCommandSpec(
                    command="/risk",
                    summary="Summarize drawdown, exposure, limits, and trading state.",
                    example="/risk",
                    permission="viewer",
                ),
                TerminalCommandSpec(
                    command="/trade",
                    summary="Submit a guided order through the execution stack using the same default order settings as desktop.",
                    example="/trade BTCUSDT long 0.01 order_type=limit limit_price=102500 timeframe=4h",
                    permission="trader",
                    parameters=[
                        TerminalCommandParameterSpec(name="symbol", summary="Instrument or market symbol.", required=True),
                        TerminalCommandParameterSpec(name="side", summary="long, short, buy, or sell.", required=True),
                        TerminalCommandParameterSpec(name="quantity", summary="Requested order quantity.", required=True),
                        TerminalCommandParameterSpec(
                            name="order_type",
                            summary="Execution type when omitted from the command.",
                            default=default_settings.order_type,
                            choices=["market", "limit", "stop_limit", "stop"],
                        ),
                        TerminalCommandParameterSpec(name="limit_price", summary="Required for limit orders."),
                        TerminalCommandParameterSpec(name="stop_price", summary="Required for stop or stop_limit orders."),
                        TerminalCommandParameterSpec(name="stop_loss", summary="Protective stop reference."),
                        TerminalCommandParameterSpec(name="take_profit", summary="Profit target reference."),
                        TerminalCommandParameterSpec(name="timeframe", summary="Market and risk context timeframe.", default=default_settings.timeframe),
                        TerminalCommandParameterSpec(name="strategy", summary="Strategy code or name override.", default=default_settings.strategy_name),
                    ],
                ),
                TerminalCommandSpec(
                    command="/strategy",
                    summary="Start, pause, or inspect strategy state by code or name.",
                    example="/strategy start adaptive_trend",
                    permission="trader",
                ),
                TerminalCommandSpec(
                    command="/backtest",
                    summary="Queue a research-style backtest request using the desktop-aligned strategy and timeframe defaults.",
                    example="/backtest BTCUSDT 1y timeframe=4h strategy=adaptive_trend",
                    permission="trader",
                    parameters=[
                        TerminalCommandParameterSpec(name="symbol", summary="Instrument or market symbol.", required=True),
                        TerminalCommandParameterSpec(name="horizon", summary="Research horizon such as 90d, 6m, or 1y.", required=True),
                        TerminalCommandParameterSpec(name="timeframe", summary="Backtest candle timeframe.", default=default_settings.timeframe),
                        TerminalCommandParameterSpec(name="strategy", summary="Strategy code or display name.", default=default_settings.strategy_name),
                    ],
                ),
                TerminalCommandSpec(
                    command="/params",
                    summary="Show the current server terminal defaults, risk controls, and strategy parameters mirrored from desktop.",
                    example="/params",
                    permission="viewer",
                ),
                TerminalCommandSpec(
                    command="/agents",
                    summary="Check signal, risk, execution, and monitoring agent health.",
                    example="/agents status",
                    permission="viewer",
                ),
                TerminalCommandSpec(
                    command="/assist",
                    summary="Ask the server runtime or ChatGPT-backed assistant for help using live context.",
                    example="/assist Summarize the current desk risk",
                    permission="viewer",
                ),
            ],
            desktop_defaults=self._desktop_defaults_payload(default_settings),
        )

    @staticmethod
    def _slugify(value: str | None, *, fallback: str) -> str:
        normalized = str(value or "").strip().lower()
        slug_parts: list[str] = []
        current: list[str] = []
        for character in normalized:
            if character.isalnum():
                current.append(character)
                continue
            if current:
                slug_parts.append("".join(current))
                current = []
        if current:
            slug_parts.append("".join(current))
        return "-".join(part for part in slug_parts if part) or fallback

    def _broker_label(self, settings: WorkspaceSettings) -> str:
        return str(settings.exchange or settings.broker_type or "paper").strip().upper() or "PAPER"

    def _account_label(self, settings: WorkspaceSettings) -> str:
        return (
            str(settings.profile_name or "").strip()
            or str(settings.account_id or "").strip()
            or str(settings.desktop_device_name or "").strip()
            or ("paper-profile" if str(settings.exchange or "").strip().lower() == "paper" else "workspace")
        )

    def _workspace_key(self, settings: WorkspaceSettings) -> str:
        broker_slug = self._slugify(settings.exchange or settings.broker_type, fallback="paper")
        account_slug = self._slugify(self._account_label(settings), fallback="desk")
        return f"{broker_slug}-{account_slug}"

    def _default_terminal_id(self, settings: WorkspaceSettings) -> str:
        return f"{self._workspace_key(settings)}--{DEFAULT_TERMINAL_KIND}"

    @staticmethod
    def _sanitize_terminal_id(value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return ""
        allowed: list[str] = []
        for character in normalized:
            if character.isalnum():
                allowed.append(character)
                continue
            if character == "-":
                allowed.append("-")
                continue
            if character in {"_", "/", " ", ":"}:
                if allowed and allowed[-1] != "-":
                    allowed.append("-")
        sanitized = "".join(allowed).strip("-")
        return sanitized[:160]

    def _resolve_terminal_id(self, settings: WorkspaceSettings, requested_terminal_id: str | None = None) -> str:
        workspace_key = self._workspace_key(settings)
        default_terminal_id = self._default_terminal_id(settings)
        sanitized = self._sanitize_terminal_id(requested_terminal_id)
        if not sanitized:
            return default_terminal_id
        if sanitized.startswith(f"{workspace_key}--"):
            return sanitized
        return default_terminal_id

    def _terminal_key(self, user_id: str, terminal_id: str | None = None) -> str:
        normalized_terminal_id = self._sanitize_terminal_id(terminal_id) or "default"
        return f"{str(user_id)}::{normalized_terminal_id}"

    def _terminal_kind(self, terminal_id: str) -> str:
        _, _, suffix = str(terminal_id or "").partition("--")
        normalized_suffix = str(suffix or "").strip().lower()
        return normalized_suffix or DEFAULT_TERMINAL_KIND

    def _terminal_label(self, settings: WorkspaceSettings, terminal_id: str) -> str:
        broker_label = self._broker_label(settings)
        account_label = self._account_label(settings)
        kind = self._terminal_kind(terminal_id)
        kind_label = next((label for slug, label, _summary in TERMINAL_KIND_SPECS if slug == kind), "")
        if kind.startswith("desk-"):
            session_number = kind.removeprefix("desk-").strip() or "x"
            return f"{broker_label} {account_label} Terminal {session_number}"
        if kind_label:
            return f"{broker_label} {account_label} {kind_label}"
        fallback_label = str(kind or "desk").replace("-", " ").strip().title()
        return f"{broker_label} {account_label} {fallback_label}"

    def _terminal_summary(self, terminal_id: str) -> str:
        kind = self._terminal_kind(terminal_id)
        summary = next((value for slug, _label, value in TERMINAL_KIND_SPECS if slug == kind), "")
        if summary:
            return summary
        if kind.startswith("desk-"):
            return "Additional launched terminal for the current broker profile."
        return "Broker-scoped server terminal session."

    def _terminal_session_spec(
        self,
        settings: WorkspaceSettings,
        terminal_id: str,
        *,
        primary: bool = False,
    ) -> TerminalSessionSpec:
        normalized_terminal_id = self._resolve_terminal_id(settings, terminal_id)
        return TerminalSessionSpec(
            terminal_id=normalized_terminal_id,
            label=self._terminal_label(settings, normalized_terminal_id),
            summary=self._terminal_summary(normalized_terminal_id),
            kind=self._terminal_kind(normalized_terminal_id),
            broker_label=self._broker_label(settings),
            account_label=self._account_label(settings),
            mode=str(settings.mode or "paper"),
            launch_href=f"/terminal?terminal={normalized_terminal_id}",
            primary=primary,
        )

    def _terminal_sessions(self, settings: WorkspaceSettings, *, active_terminal_id: str | None = None) -> list[TerminalSessionSpec]:
        workspace_key = self._workspace_key(settings)
        active_id = self._resolve_terminal_id(settings, active_terminal_id)
        sessions = [
            self._terminal_session_spec(
                settings,
                f"{workspace_key}--{kind}",
                primary=(kind == DEFAULT_TERMINAL_KIND),
            )
            for kind, _label, _summary in TERMINAL_KIND_SPECS
        ]
        session_ids = {item.terminal_id for item in sessions}
        if active_id not in session_ids:
            sessions.append(self._terminal_session_spec(settings, active_id, primary=False))
        return sessions

    def _terminal_examples(self, settings: WorkspaceSettings, terminal_id: str) -> list[str]:
        kind = self._terminal_kind(terminal_id)
        if kind == "control":
            return ["/params", "/risk", "/agents status", "/markets", "/assist Summarize the current desk risk", "/help"]
        if kind == "review":
            return ["/positions", "/risk", "/agents status", "/assist Summarize the current desk risk", "/params", "/help"]
        return [
            "/markets",
            "/params",
            f"/trade BTCUSDT long 0.01 order_type={settings.order_type} timeframe={settings.timeframe}",
            "/positions",
            "/risk",
            "/strategy start adaptive_trend",
            "/backtest BTCUSDT 1y timeframe=4h strategy=adaptive_trend",
            "/agents status",
            "/assist Summarize the current desk risk",
        ]

    def _manifest_banners(self, settings: WorkspaceSettings, terminal: TerminalSessionSpec) -> list[str]:
        mode_label = str(settings.mode or "paper").upper()
        return [
            (
                f"{terminal.label} loaded for {mode_label} routing on {terminal.broker_label} "
                f"with profile {terminal.account_label}."
            ),
            terminal.summary,
        ]

    async def get_manifest(
        self,
        session: AsyncSession | None = None,
        *,
        user: User | None = None,
        terminal_id: str | None = None,
    ) -> TerminalManifestResponse:
        if session is None or user is None:
            return self._manifest
        settings = await self._workspace_settings(session, user_id=user.id)
        active_terminal_id = self._resolve_terminal_id(settings, terminal_id)
        sessions = self._terminal_sessions(settings, active_terminal_id=active_terminal_id)
        active_terminal = next(
            (item for item in sessions if item.terminal_id == active_terminal_id),
            self._terminal_session_spec(settings, active_terminal_id, primary=True),
        )
        return self._manifest.model_copy(
            update={
                "active_terminal_id": active_terminal.terminal_id,
                "active_terminal_label": active_terminal.label,
                "workspace_key": self._workspace_key(settings),
                "broker_label": active_terminal.broker_label,
                "account_label": active_terminal.account_label,
                "mode": str(settings.mode or "paper"),
                "terminals": sessions,
                "banners": self._manifest_banners(settings, active_terminal),
                "examples": self._terminal_examples(settings, active_terminal.terminal_id),
                "desktop_defaults": self._desktop_defaults_payload(settings),
            }
        )

    @staticmethod
    def _desktop_defaults_payload(settings: WorkspaceSettings) -> dict[str, Any]:
        return {
            "timeframe": settings.timeframe,
            "order_type": settings.order_type,
            "strategy_name": settings.strategy_name,
            "risk_profile_name": settings.risk_profile_name,
            "max_portfolio_risk": settings.max_portfolio_risk,
            "max_risk_per_trade": settings.max_risk_per_trade,
            "max_position_size_pct": settings.max_position_size_pct,
            "max_gross_exposure_pct": settings.max_gross_exposure_pct,
            "hedging_enabled": settings.hedging_enabled,
            "margin_closeout_guard_enabled": settings.margin_closeout_guard_enabled,
            "max_margin_closeout_pct": settings.max_margin_closeout_pct,
            "strategy_params": {
                "rsi_period": settings.strategy_rsi_period,
                "ema_fast": settings.strategy_ema_fast,
                "ema_slow": settings.strategy_ema_slow,
                "atr_period": settings.strategy_atr_period,
                "oversold_threshold": settings.strategy_oversold_threshold,
                "overbought_threshold": settings.strategy_overbought_threshold,
                "breakout_lookback": settings.strategy_breakout_lookback,
                "min_confidence": settings.strategy_min_confidence,
                "signal_amount": settings.strategy_signal_amount,
            },
        }

    async def _workspace_settings(self, session: AsyncSession, *, user_id: str) -> WorkspaceSettings:
        config = await session.scalar(select(WorkspaceConfig).where(WorkspaceConfig.user_id == str(user_id)))
        payload = (config.settings_json if config is not None else {}) or {}
        return WorkspaceSettings.model_validate(payload)

    @staticmethod
    def _parse_keyed_args(
        args: list[str],
        *,
        aliases: dict[str, str],
        allowed: set[str],
    ) -> tuple[list[str], dict[str, str], list[str]]:
        positional: list[str] = []
        options: dict[str, str] = {}
        unknown: list[str] = []
        for item in list(args or []):
            token = str(item or "").strip()
            if not token or "=" not in token:
                if token:
                    positional.append(token)
                continue
            raw_key, raw_value = token.split("=", 1)
            normalized_input_key = str(raw_key or "").strip().lower().replace("-", "_")
            normalized_key = aliases.get(normalized_input_key, normalized_input_key if normalized_input_key in allowed else "")
            if not normalized_key or normalized_key not in allowed:
                unknown.append(str(raw_key or "").strip())
                continue
            options[normalized_key] = str(raw_value or "").strip()
        return positional, options, unknown

    @staticmethod
    def _float_option(options: dict[str, str], key: str) -> float | None:
        if key not in options:
            return None
        value = str(options.get(key) or "").strip()
        if not value:
            return None
        return float(value)

    @staticmethod
    def _strategy_params_payload(settings: WorkspaceSettings) -> dict[str, Any]:
        return {
            "rsi_period": settings.strategy_rsi_period,
            "ema_fast": settings.strategy_ema_fast,
            "ema_slow": settings.strategy_ema_slow,
            "atr_period": settings.strategy_atr_period,
            "oversold_threshold": settings.strategy_oversold_threshold,
            "overbought_threshold": settings.strategy_overbought_threshold,
            "breakout_lookback": settings.strategy_breakout_lookback,
            "min_confidence": settings.strategy_min_confidence,
            "signal_amount": settings.strategy_signal_amount,
        }

    @staticmethod
    def _match_strategy(strategies: list[Strategy], identifier: str) -> Strategy | None:
        normalized = str(identifier or "").strip().lower()
        if not normalized:
            return None
        return next(
            (
                row
                for row in strategies
                if row.code.lower() == normalized or row.name.lower() == normalized or normalized in row.code.lower()
            ),
            None,
        )

    def get_history(self, user_id: str, limit: int = 25, *, terminal_id: str | None = None) -> list[TerminalCommandResponse]:
        rows = list(self._history.get(self._terminal_key(user_id, terminal_id), deque()))
        rows.sort(key=lambda item: item.timestamp, reverse=True)
        return rows[: max(1, min(limit, 100))]

    async def execute(
        self,
        session: AsyncSession,
        *,
        user: User,
        command: str,
        terminal_id: str | None = None,
    ) -> TerminalCommandResponse:
        normalized_terminal_id = self._sanitize_terminal_id(terminal_id) or "default"
        raw_command = str(command or "").strip()
        if not raw_command:
            return self._record(
                user.id,
                normalized_terminal_id,
                self._response(
                    terminal_id=normalized_terminal_id,
                    command="/help",
                    status="error",
                    message="Command cannot be empty.",
                    suggestions=["/help", "/markets", "/agents status"],
                ),
            )
        normalized = raw_command if raw_command.startswith("/") else f"/{raw_command}"
        try:
            parts = shlex.split(normalized[1:])
        except ValueError as exc:
            return self._record(
                user.id,
                normalized_terminal_id,
                self._response(
                    terminal_id=normalized_terminal_id,
                    command=normalized,
                    status="error",
                    message=f"Unable to parse command: {exc}",
                    suggestions=["/help"],
                    assistant=self._assistant(
                        headline="Command parsing failed",
                        confidence="low",
                        reason="The terminal could not tokenize the command cleanly. Check quote usage and spacing.",
                        risk_level="none",
                        expected_duration="instant",
                    ),
                ),
            )
        if not parts:
            return self._record(
                user.id,
                normalized_terminal_id,
                self._response(
                    terminal_id=normalized_terminal_id,
                    command="/help",
                    status="error",
                    message="Command cannot be empty.",
                    suggestions=["/help"],
                ),
            )

        head = parts[0].lower()
        args = parts[1:]
        if head == "help":
            return self._record(user.id, normalized_terminal_id, self._handle_help(terminal_id=normalized_terminal_id))
        if head == "markets":
            response = await self._handle_markets(user=user, args=args)
            return self._record(user.id, normalized_terminal_id, self._with_terminal_id(response, normalized_terminal_id))
        if head == "positions":
            response = await self._handle_positions(user=user)
            return self._record(user.id, normalized_terminal_id, self._with_terminal_id(response, normalized_terminal_id))
        if head == "risk":
            response = await self._handle_risk(user=user)
            return self._record(user.id, normalized_terminal_id, self._with_terminal_id(response, normalized_terminal_id))
        if head == "params":
            response = await self._handle_params(session=session, user=user)
            return self._record(user.id, normalized_terminal_id, self._with_terminal_id(response, normalized_terminal_id))
        if head == "trade":
            response = await self._handle_trade(session=session, user=user, args=args)
            return self._record(user.id, normalized_terminal_id, self._with_terminal_id(response, normalized_terminal_id))
        if head == "strategy":
            response = await self._handle_strategy(session=session, user=user, args=args)
            return self._record(user.id, normalized_terminal_id, self._with_terminal_id(response, normalized_terminal_id))
        if head == "backtest":
            response = await self._handle_backtest(session=session, user=user, args=args)
            return self._record(user.id, normalized_terminal_id, self._with_terminal_id(response, normalized_terminal_id))
        if head == "agents":
            response = await self._handle_agents(user=user, args=args)
            return self._record(user.id, normalized_terminal_id, self._with_terminal_id(response, normalized_terminal_id))
        if head == "assist":
            response = await self._handle_assist(user=user, args=args)
            return self._record(user.id, normalized_terminal_id, self._with_terminal_id(response, normalized_terminal_id))

        return self._record(
            user.id,
            normalized_terminal_id,
            self._response(
                terminal_id=normalized_terminal_id,
                command=normalized,
                status="error",
                message=f"Unknown command: {normalized}",
                suggestions=self._manifest.examples[:5],
                assistant=self._assistant(
                    headline="Unknown terminal command",
                    confidence="low",
                    reason="The terminal command surface is explicit so operators can audit every action path.",
                    risk_level="none",
                    expected_duration="instant",
                ),
            ),
        )

    def _record(self, user_id: str, terminal_id: str, response: TerminalCommandResponse) -> TerminalCommandResponse:
        self._history[self._terminal_key(user_id, terminal_id)].appendleft(response)
        return response

    def _with_terminal_id(self, response: TerminalCommandResponse, terminal_id: str) -> TerminalCommandResponse:
        if response.terminal_id == terminal_id:
            return response
        return response.model_copy(update={"terminal_id": terminal_id})

    def _response(
        self,
        *,
        terminal_id: str = "default",
        command: str,
        status: str,
        message: str,
        lines: list[str] | None = None,
        suggestions: list[str] | None = None,
        data: dict[str, Any] | None = None,
        assistant: TerminalAssistantResponse | None = None,
    ) -> TerminalCommandResponse:
        return TerminalCommandResponse(
            command_id=str(uuid4()),
            terminal_id=terminal_id,
            command=command,
            status=status,
            message=message,
            lines=list(lines or []),
            suggestions=list(suggestions or []),
            data=dict(data or {}),
            assistant=assistant,
            timestamp=utc_now(),
        )

    def _assistant(
        self,
        *,
        headline: str,
        confidence: str,
        reason: str,
        risk_level: str,
        expected_duration: str,
    ) -> TerminalAssistantResponse:
        return TerminalAssistantResponse(
            headline=headline,
            confidence=confidence,
            reason=reason,
            risk_level=risk_level,
            expected_duration=expected_duration,
        )

    def _require_trading_role(self, user: User) -> bool:
        return user.role in {UserRole.ADMIN, UserRole.TRADER}

    def _handle_help(self, *, terminal_id: str) -> TerminalCommandResponse:
        lines = [f"{spec.command} :: {spec.summary} :: {spec.example}" for spec in self._manifest.commands]
        return self._response(
            terminal_id=terminal_id,
            command="/help",
            status="ok",
            message="Terminal command surface loaded.",
            lines=lines,
            suggestions=self._manifest.examples,
            assistant=self._assistant(
                headline="Guided operator terminal ready",
                confidence="high",
                reason="This command surface is intentionally narrow so orders, risk actions, and strategy controls stay auditable.",
                risk_level="none",
                expected_duration="instant",
            ),
        )

    async def _handle_markets(self, *, user: User, args: list[str]) -> TerminalCommandResponse:
        requested_symbols = [str(arg).strip().upper() for arg in args if str(arg).strip()]
        control_state = await self.state_store.get_control_state(user.id)
        symbols = requested_symbols or list(control_state.get("selected_symbols") or [])
        snapshots = await self.state_store.get_market_snapshot(symbols if symbols else None)
        lines: list[str] = []
        if snapshots:
            for row in snapshots[:12]:
                lines.append(
                    f"{str(row.get('symbol') or '').upper()} | last {float(row.get('last', 0.0) or 0.0):,.4f} | "
                    f"chg {float(row.get('change_pct', 0.0) or 0.0):+.2f}% | vol {float(row.get('volume', 0.0) or 0.0):,.0f}"
                )
        elif symbols:
            lines = [f"{symbol} | feed pending | market snapshot has not populated yet" for symbol in symbols[:12]]
        else:
            lines = ["No selected symbols yet. Save a watchlist from the control panel first."]
        return self._response(
            command="/markets" if not args else f"/markets {' '.join(args)}",
            status="ok",
            message="Market watchlist snapshot prepared.",
            lines=lines,
            suggestions=["/positions", "/risk", "/agents status"],
            data={"symbols": symbols, "count": len(lines)},
            assistant=self._assistant(
                headline="Market context refreshed",
                confidence="medium",
                reason="The terminal is reading the same symbol universe that the portfolio and risk surfaces use.",
                risk_level="low",
                expected_duration="intraday",
            ),
        )

    async def _handle_positions(self, *, user: User) -> TerminalCommandResponse:
        positions = await self.state_store.get_positions_snapshot(user.id)
        if not positions:
            return self._response(
                command="/positions",
                status="ok",
                message="No active positions.",
                lines=["The portfolio is flat right now."],
                suggestions=["/markets", "/strategy start adaptive_trend"],
                assistant=self._assistant(
                    headline="Portfolio is flat",
                    confidence="high",
                    reason="There are no open positions in the realtime state store for this account.",
                    risk_level="none",
                    expected_duration="instant",
                ),
            )
        lines = [
            f"{str(row.get('symbol') or '').upper()} | {str(row.get('side') or '').upper()} | "
            f"qty {float(row.get('quantity', 0.0) or 0.0):,.4f} | "
            f"uPnL {float(row.get('unrealized_pnl', 0.0) or 0.0):+,.2f}"
            for row in positions[:20]
        ]
        total_unrealized = sum(float(row.get("unrealized_pnl", 0.0) or 0.0) for row in positions)
        return self._response(
            command="/positions",
            status="ok",
            message=f"{len(positions)} active positions loaded.",
            lines=lines,
            suggestions=["/risk", "/agents status"],
            data={"position_count": len(positions), "unrealized_pnl": total_unrealized},
            assistant=self._assistant(
                headline="Position book loaded",
                confidence="high",
                reason="The terminal is reading live positions from the same state store that powers the portfolio dashboard.",
                risk_level="medium",
                expected_duration="session",
            ),
        )

    async def _handle_risk(self, *, user: User) -> TerminalCommandResponse:
        risk = await self.state_store.get_risk_snapshot(user.id)
        control = await self.state_store.get_control_state(user.id)
        lines = [
            f"Trading enabled :: {'YES' if bool(control.get('trading_enabled')) else 'NO'}",
            f"Selected symbols :: {', '.join(list(control.get('selected_symbols') or [])[:8]) or 'none'}",
            f"Gross exposure :: {float(risk.get('gross_exposure', 0.0) or 0.0):,.2f}",
            f"Net exposure :: {float(risk.get('net_exposure', 0.0) or 0.0):,.2f}",
            f"Drawdown :: {float(risk.get('drawdown', 0.0) or 0.0):.2f}",
        ]
        return self._response(
            command="/risk",
            status="ok",
            message="Risk snapshot prepared.",
            lines=lines,
            suggestions=["/positions", "/agents status", "/markets"],
            data={"risk": risk, "control": control},
            assistant=self._assistant(
                headline="Risk guardrails loaded",
                confidence="high",
                reason="This summarizes the realtime risk snapshot together with operator trading-state controls.",
                risk_level="medium",
                expected_duration="session",
            ),
        )

    async def _handle_params(self, *, session: AsyncSession, user: User) -> TerminalCommandResponse:
        settings = await self._workspace_settings(session, user_id=user.id)
        lines = [
            f"Profile :: {settings.profile_name or '-'}",
            f"Risk profile :: {settings.risk_profile_name}",
            f"Timeframe :: {settings.timeframe}",
            f"Order type :: {settings.order_type}",
            f"Strategy default :: {settings.strategy_name}",
            f"Max portfolio risk :: {settings.max_portfolio_risk:.2%}",
            f"Max risk per trade :: {settings.max_risk_per_trade:.2%}",
            f"Max position size :: {settings.max_position_size_pct:.2%}",
            f"Max gross exposure :: {settings.max_gross_exposure_pct:.2f}x",
            f"Hedging :: {'ENABLED' if settings.hedging_enabled else 'DISABLED'}",
            (
                f"Margin closeout guard :: {'ENABLED' if settings.margin_closeout_guard_enabled else 'DISABLED'}"
                f" @ {settings.max_margin_closeout_pct:.2%}"
            ),
            (
                "Strategy params :: "
                f"RSI {settings.strategy_rsi_period} | EMA {settings.strategy_ema_fast}/{settings.strategy_ema_slow} | "
                f"ATR {settings.strategy_atr_period} | Oversold {settings.strategy_oversold_threshold:.1f} | "
                f"Overbought {settings.strategy_overbought_threshold:.1f} | "
                f"Breakout {settings.strategy_breakout_lookback} | "
                f"Min confidence {settings.strategy_min_confidence:.2f} | "
                f"Signal amount {settings.strategy_signal_amount:.4f}"
            ),
        ]
        return self._response(
            command="/params",
            status="ok",
            message="Server terminal defaults loaded.",
            lines=lines,
            suggestions=[
                f"/trade BTCUSDT long 0.01 order_type={settings.order_type} timeframe={settings.timeframe}",
                "/risk",
                "/strategy",
            ],
            data={"desktop_defaults": self._desktop_defaults_payload(settings)},
            assistant=self._assistant(
                headline="Desktop-matched terminal defaults ready",
                confidence="high",
                reason="The server terminal is reading the same execution, risk, and strategy defaults that the desktop terminal uses.",
                risk_level="low",
                expected_duration="session",
            ),
        )

    async def _handle_trade(
        self,
        *,
        session: AsyncSession,
        user: User,
        args: list[str],
    ) -> TerminalCommandResponse:
        if not self._require_trading_role(user):
            return self._response(
                command="/trade",
                status="error",
                message="Only trader or admin accounts can place orders from the terminal.",
                suggestions=["/positions", "/markets"],
                assistant=self._assistant(
                    headline="Permission blocked",
                    confidence="high",
                    reason="Viewer accounts are deliberately read-only in the terminal.",
                    risk_level="none",
                    expected_duration="instant",
                ),
            )
        settings = await self._workspace_settings(session, user_id=user.id)
        positional, options, unknown = self._parse_keyed_args(
            args,
            aliases=TRADE_OPTION_ALIASES,
            allowed=TRADE_OPTION_NAMES,
        )
        if unknown:
            return self._response(
                command=f"/trade {' '.join(args)}",
                status="error",
                message=f"Unknown trade parameter(s): {', '.join(sorted(set(unknown)))}",
                suggestions=[self._manifest.commands[4].example, "/params"],
            )
        if len(positional) < 3:
            return self._response(
                command="/trade",
                status="error",
                message=(
                    "Usage: /trade SYMBOL long|short|buy|sell QUANTITY "
                    "[order_type=market|limit|stop|stop_limit] [limit_price=123.45] "
                    "[stop_price=123.00] [stop_loss=120.00] [take_profit=130.00] "
                    "[timeframe=1h] [strategy=adaptive_trend]"
                ),
                suggestions=[self._manifest.commands[4].example, "/params"],
            )
        symbol = str(positional[0]).strip().upper()
        side_alias = str(positional[1]).strip().lower()
        try:
            quantity = float(positional[2])
        except (TypeError, ValueError):
            return self._response(
                command=f"/trade {' '.join(args)}",
                status="error",
                message="Quantity must be numeric.",
                suggestions=[self._manifest.commands[4].example],
            )
        side = "buy" if side_alias in {"buy", "long"} else "sell" if side_alias in {"sell", "short"} else ""
        if not side:
            return self._response(
                command=f"/trade {' '.join(args)}",
                status="error",
                message="Side must be long, short, buy, or sell.",
                suggestions=[self._manifest.commands[4].example],
            )
        order_type = str(options.get("order_type") or settings.order_type or "limit").strip().lower() or "limit"
        if order_type not in {"market", "limit", "stop", "stop_limit"}:
            return self._response(
                command=f"/trade {' '.join(args)}",
                status="error",
                message="order_type must be market, limit, stop, or stop_limit.",
                suggestions=[self._manifest.commands[4].example],
            )
        try:
            limit_price = self._float_option(options, "limit_price")
            stop_price = self._float_option(options, "stop_price")
            stop_loss = self._float_option(options, "stop_loss")
            take_profit = self._float_option(options, "take_profit")
        except ValueError:
            return self._response(
                command=f"/trade {' '.join(args)}",
                status="error",
                message="limit_price, stop_price, stop_loss, and take_profit must be numeric when provided.",
                suggestions=[self._manifest.commands[4].example],
            )
        if order_type == "limit" and limit_price is None:
            return self._response(
                command=f"/trade {' '.join(args)}",
                status="error",
                message="limit_price is required when order_type=limit.",
                suggestions=[self._manifest.commands[4].example],
            )
        if order_type == "stop" and stop_price is None:
            return self._response(
                command=f"/trade {' '.join(args)}",
                status="error",
                message="stop_price is required when order_type=stop.",
                suggestions=[self._manifest.commands[4].example],
            )
        if order_type == "stop_limit" and (limit_price is None or stop_price is None):
            return self._response(
                command=f"/trade {' '.join(args)}",
                status="error",
                message="limit_price and stop_price are both required when order_type=stop_limit.",
                suggestions=[self._manifest.commands[4].example],
            )
        timeframe = str(options.get("timeframe") or settings.timeframe or "1h").strip().lower() or "1h"
        strategy_identifier = str(options.get("strategy") or settings.strategy_name or "").strip()
        strategies = await session.scalars(
            select(Strategy).where(Strategy.user_id == user.id).order_by(Strategy.created_at.asc())
        )
        strategy_rows = list(strategies)
        selected_strategy = self._match_strategy(strategy_rows, strategy_identifier)
        if selected_strategy is None:
            selected_strategy = next((row for row in strategy_rows if symbol in list(row.assigned_symbols or [])), None)
        order = await self.control_service.submit_order(
            session,
            user=user,
            payload=OrderCreateRequest(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                timeframe=timeframe,
                strategy_id=selected_strategy.id if selected_strategy is not None else None,
                venue="terminal",
                reason=f"Terminal command {side_alias}",
                metadata={
                    "source": "integrated-terminal",
                    "strategy_name": selected_strategy.code if selected_strategy is not None else strategy_identifier or settings.strategy_name,
                    "strategy_defaults": self._strategy_params_payload(settings),
                },
            ),
        )
        lines = [
            f"Order ID :: {order.order_id}",
            f"Side :: {side.upper()}",
            f"Quantity :: {quantity:,.4f}",
            f"Order type :: {order_type}",
            f"Timeframe :: {timeframe}",
            f"Strategy binding :: {selected_strategy.code if selected_strategy is not None else (strategy_identifier or 'unassigned')}",
        ]
        if limit_price is not None:
            lines.append(f"Limit price :: {limit_price:,.6f}")
        if stop_price is not None:
            lines.append(f"Stop price :: {stop_price:,.6f}")
        if stop_loss is not None:
            lines.append(f"Stop loss :: {stop_loss:,.6f}")
        if take_profit is not None:
            lines.append(f"Take profit :: {take_profit:,.6f}")
        return self._response(
            command=f"/trade {' '.join(args)}",
            status="ok",
            message=f"Order accepted for {symbol}.",
            lines=lines,
            suggestions=["/positions", "/risk", "/agents status"],
            data={
                "order_id": order.order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "order_type": order_type,
                "limit_price": limit_price,
                "stop_price": stop_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "timeframe": timeframe,
                "strategy_code": selected_strategy.code if selected_strategy is not None else None,
            },
            assistant=self._assistant(
                headline=f"{side.upper()} {symbol}",
                confidence="medium",
                reason="The execution request was normalized through the same control service used by the web order entry flow, while preserving the desktop-matched terminal defaults and risk parameters.",
                risk_level="medium",
                expected_duration="intraday",
            ),
        )

    async def _handle_strategy(
        self,
        *,
        session: AsyncSession,
        user: User,
        args: list[str],
    ) -> TerminalCommandResponse:
        if not args:
            rows = await session.scalars(
                select(Strategy).where(Strategy.user_id == user.id).order_by(Strategy.created_at.asc())
            )
            strategies = list(rows)
            return self._response(
                command="/strategy",
                status="ok",
                message="Strategy inventory loaded.",
                lines=[
                    f"{row.code} | {row.status.value.upper()} | {len(list(row.assigned_symbols or []))} symbols"
                    for row in strategies
                ],
                suggestions=["/strategy start adaptive_trend", "/strategy pause event_breakout"],
                assistant=self._assistant(
                    headline="Strategy inventory ready",
                    confidence="high",
                    reason="This is the current strategy registry for the authenticated account.",
                    risk_level="low",
                    expected_duration="session",
                ),
            )
        action = str(args[0]).strip().lower()
        if action not in {"start", "pause", "stop"}:
            return self._response(
                command=f"/strategy {' '.join(args)}",
                status="error",
                message="Usage: /strategy start|pause|stop STRATEGY_CODE",
                suggestions=["/strategy start adaptive_trend"],
            )
        if not self._require_trading_role(user):
            return self._response(
                command=f"/strategy {' '.join(args)}",
                status="error",
                message="Only trader or admin accounts can change strategy state.",
            )
        if len(args) < 2:
            return self._response(
                command=f"/strategy {action}",
                status="error",
                message="Provide a strategy code or name.",
                suggestions=["/strategy start adaptive_trend"],
            )
        identifier = str(" ".join(args[1:])).strip().lower()
        rows = await session.scalars(select(Strategy).where(Strategy.user_id == user.id))
        strategies = list(rows)
        strategy = self._match_strategy(strategies, identifier)
        if strategy is None:
            return self._response(
                command=f"/strategy {' '.join(args)}",
                status="error",
                message=f"Strategy not found: {identifier}",
                suggestions=[f"/strategy start {row.code}" for row in strategies[:4]],
            )
        next_status = StrategyStatus.ENABLED if action == "start" else StrategyStatus.PAUSED
        updated = await self.control_service.update_strategy(
            session,
            user=user,
            strategy_id=strategy.id,
            payload=StrategyUpdateRequest(status=next_status),
        )
        return self._response(
            command=f"/strategy {' '.join(args)}",
            status="ok",
            message=f"Strategy {updated.code} is now {updated.status.value}.",
            lines=[
                f"Strategy :: {updated.name}",
                f"Status :: {updated.status.value.upper()}",
                f"Assigned symbols :: {', '.join(list(updated.assigned_symbols or [])) or 'none'}",
            ],
            suggestions=["/agents status", "/markets"],
            assistant=self._assistant(
                headline=f"Strategy {updated.code} updated",
                confidence="high",
                reason="The strategy state change is persisted and forwarded through the same strategy command channel as the main control panel.",
                risk_level="medium",
                expected_duration="session",
            ),
        )

    async def _handle_backtest(
        self,
        *,
        session: AsyncSession,
        user: User,
        args: list[str],
    ) -> TerminalCommandResponse:
        settings = await self._workspace_settings(session, user_id=user.id)
        positional, options, unknown = self._parse_keyed_args(
            args,
            aliases=BACKTEST_OPTION_ALIASES,
            allowed=BACKTEST_OPTION_NAMES,
        )
        if unknown:
            return self._response(
                command=f"/backtest {' '.join(args)}",
                status="error",
                message=f"Unknown backtest parameter(s): {', '.join(sorted(set(unknown)))}",
                suggestions=[self._manifest.commands[6].example, "/params"],
            )
        if len(positional) < 2:
            return self._response(
                command="/backtest",
                status="error",
                message="Usage: /backtest SYMBOL HORIZON [timeframe=1h] [strategy=adaptive_trend]",
                suggestions=[self._manifest.commands[6].example, "/params"],
            )
        if not self._require_trading_role(user):
            return self._response(
                command=f"/backtest {' '.join(args)}",
                status="error",
                message="Only trader or admin accounts can queue backtests from the terminal.",
            )
        symbol = str(positional[0]).strip().upper()
        horizon = str(positional[1]).strip().lower()
        timeframe = str(options.get("timeframe") or settings.timeframe or "1h").strip().lower() or "1h"
        strategy_name = str(options.get("strategy") or settings.strategy_name or "").strip() or settings.strategy_name
        await self.control_service.create_log(
            session,
            user_id=user.id,
            category="backtest",
            level=LogLevel.INFO,
            message=f"Queued terminal backtest for {symbol}",
            payload={
                "symbol": symbol,
                "horizon": horizon,
                "timeframe": timeframe,
                "strategy": strategy_name,
                "source": "integrated-terminal",
                "strategy_defaults": self._strategy_params_payload(settings),
            },
            source="terminal",
        )
        return self._response(
            command=f"/backtest {' '.join(args)}",
            status="ok",
            message=f"Backtest request recorded for {symbol}.",
            lines=[
                f"Symbol :: {symbol}",
                f"Horizon :: {horizon}",
                f"Timeframe :: {timeframe}",
                f"Strategy :: {strategy_name}",
                "Mode :: research queue",
            ],
            suggestions=["/markets", "/strategy", "/agents status"],
            data={"symbol": symbol, "horizon": horizon, "timeframe": timeframe, "strategy": strategy_name},
            assistant=self._assistant(
                headline=f"Backtest queued for {symbol}",
                confidence="medium",
                reason="The request is logged for the research pipeline using the same timeframe and strategy defaults the desktop terminal advertises.",
                risk_level="low",
                expected_duration="multi-session",
            ),
        )

    async def _handle_agents(self, *, user: User, args: list[str]) -> TerminalCommandResponse:
        subcommand = str(args[0]).strip().lower() if args else "status"
        if subcommand != "status":
            return self._response(
                command=f"/agents {' '.join(args)}",
                status="error",
                message="Only /agents status is supported right now.",
                suggestions=["/agents status"],
            )
        control = await self.state_store.get_control_state(user.id)
        alerts = await self.state_store.get_alerts(user.id)
        positions = await self.state_store.get_positions_snapshot(user.id)
        selected_symbols = list(control.get("selected_symbols") or [])
        runtime_status = self.runtime_service.runtime_status(user.id)
        signal_state = "online" if selected_symbols else "idle"
        risk_state = "armed" if bool(control.get("trading_enabled")) else "watching"
        execution_state = "ready" if self._require_trading_role(user) else "read-only"
        monitoring_state = "active" if alerts or positions else "watching"
        ai_state = "available" if runtime_status.get("ai_enabled") else "heuristic"
        learning_summary = dict(runtime_status.get("learning_summary") or {})
        lines = [
            f"Signal Agent :: {signal_state} | symbols {len(selected_symbols)}",
            f"Risk Agent :: {risk_state} | alerts {len(alerts)}",
            f"Execution Agent :: {execution_state} | positions {len(positions)}",
            f"Monitoring Agent :: {monitoring_state}",
            f"AI Assistant :: {ai_state} | runtime {'active' if runtime_status.get('active') else 'idle'}",
            f"Learning Engine :: {'adaptive' if runtime_status.get('auto_improve_enabled') else 'passive'} | trades {int(learning_summary.get('trade_count', 0) or 0)}",
        ]
        return self._response(
            command="/agents status",
            status="ok",
            message="Agent mesh health prepared.",
            lines=lines + ([str(learning_summary.get("summary"))] if learning_summary.get("summary") else []),
            suggestions=["/risk", "/positions", "/markets", "/assist Summarize the current desk risk"],
            data={
                "signal_agent": signal_state,
                "risk_agent": risk_state,
                "execution_agent": execution_state,
                "monitoring_agent": monitoring_state,
                "runtime": runtime_status,
            },
            assistant=self._assistant(
                headline="Agent runtime health checked",
                confidence="high",
                reason="The terminal is correlating trading controls, alerts, and open positions to expose the current agent posture.",
                risk_level="low",
                expected_duration="session",
            ),
        )

    async def _handle_assist(self, *, user: User, args: list[str]) -> TerminalCommandResponse:
        question = str(" ".join(args)).strip()
        if not question:
            return self._response(
                command="/assist",
                status="error",
                message="Usage: /assist YOUR QUESTION",
                suggestions=["/assist Summarize the current desk risk"],
            )
        result = await self.runtime_service.assist(user.id, question)
        answer = str(result.get("answer") or "The assistant did not return a response.").strip()
        provider = str(result.get("provider") or "runtime").strip()
        lines = [line.strip() for line in answer.splitlines() if line.strip()]
        return self._response(
            command=f"/assist {question}",
            status="ok",
            message=f"Assistant response ready via {provider}.",
            lines=lines or [answer],
            suggestions=["/agents status", "/risk", "/markets"],
            data={"provider": provider, "model": result.get("model")},
            assistant=self._assistant(
                headline="Assistant guidance prepared",
                confidence="medium" if provider == "runtime" else "high",
                reason="The assistant used the active server runtime context, and upgraded to OpenAI when credentials were available.",
                risk_level="low",
                expected_duration="instant",
            ),
        )
