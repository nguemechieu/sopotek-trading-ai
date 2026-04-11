from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sopotek.agents.base import BaseAgent
from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.market_hours_engine import MarketHoursEngine, MarketWindowDecision
from sopotek.core.models import (
    AnalystInsight,
    ClosePositionRequest,
    ExecutionReport,
    FeatureVector,
    PortfolioSnapshot,
    PositionUpdate,
    ReasoningDecision,
    Signal,
    TradeFeedback,
    TraderDecision,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return _utc_now()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _timeframe_to_seconds(value: Any, default: int = 60) -> int:
    text = str(value or "").strip().lower()
    if not text:
        return int(default)
    try:
        amount = int(text[:-1] or 1)
    except Exception:
        return int(default)
    suffix = text[-1]
    if suffix == "s":
        return amount
    if suffix == "m":
        return amount * 60
    if suffix == "h":
        return amount * 3600
    if suffix == "d":
        return amount * 86400
    return int(default)


def _normalize_feature_map(payload: Any) -> dict[str, float]:
    if not isinstance(payload, dict):
        return {}
    return {str(key): _safe_float(value) for key, value in payload.items() if str(key).strip()}


def _position_side(quantity: float) -> str:
    return "buy" if _safe_float(quantity) >= 0.0 else "sell"


def _inverse_side(side: str) -> str:
    return "sell" if str(side or "").strip().lower() == "buy" else "buy"


def _position_profit_pct(entry_price: float, current_price: float, quantity: float) -> float:
    if entry_price <= 0:
        return 0.0
    direction = 1.0 if _safe_float(quantity) >= 0.0 else -1.0
    return ((current_price - entry_price) / entry_price) * direction


@dataclass(slots=True)
class InvestorProfile:
    risk_level: str
    goal: str
    max_drawdown: float
    trade_frequency: str
    preferred_assets: list[str] = field(default_factory=list)
    time_horizon: str = "medium"

    def __post_init__(self) -> None:
        self.risk_level = str(self.risk_level or "medium").strip().lower() or "medium"
        self.goal = str(self.goal or "growth").strip().lower() or "growth"
        self.max_drawdown = max(0.001, float(self.max_drawdown))
        self.trade_frequency = str(self.trade_frequency or "medium").strip().lower() or "medium"
        self.preferred_assets = [str(asset).strip() for asset in list(self.preferred_assets or []) if str(asset).strip()]
        self.time_horizon = str(self.time_horizon or "medium").strip().lower() or "medium"


class TraderAgent(BaseAgent):
    """Profile-aware trade aggregator that behaves like a digital portfolio trader."""

    name = "trader_agent"
    _EVALUATE_EVENT = "__trader_agent_evaluate__"

    def __init__(
        self,
        *,
        profiles: dict[str, InvestorProfile] | None = None,
        active_profile_id: str | None = None,
        predictor: Any | None = None,
        risk_engine: Any | None = None,
        market_hours_engine: MarketHoursEngine | None = None,
        default_asset_type: str = "crypto",
        require_high_liquidity_for_forex: bool = False,
        signal_ttl_seconds: float = 900.0,
        decision_history_limit: int = 200,
        position_management_cooldown_seconds: float = 5.0,
        position_management_action_cooldown_seconds: float = 15.0,
        bad_trade_loss_threshold_pct: float = 0.005,
        bad_trade_reverse_confidence: float = 0.72,
        bad_trade_reverse_vote_margin: float = 0.18,
        bad_trade_reduce_fraction: float = 0.5,
        strategy_weights: dict[str, float] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.bus: AsyncEventBus | None = None
        self.predictor = predictor
        self.risk_engine = risk_engine
        self.market_hours_engine = market_hours_engine or MarketHoursEngine(
            default_asset_type=default_asset_type,
            logger=logger,
        )
        self.require_high_liquidity_for_forex = bool(require_high_liquidity_for_forex)
        self.signal_ttl = max(30.0, float(signal_ttl_seconds))
        self.decision_history_limit = max(20, int(decision_history_limit))
        self.position_management_cooldown_seconds = max(1.0, float(position_management_cooldown_seconds))
        self.position_management_action_cooldown_seconds = max(
            self.position_management_cooldown_seconds,
            float(position_management_action_cooldown_seconds),
        )
        self.bad_trade_loss_threshold_pct = max(0.001, float(bad_trade_loss_threshold_pct))
        self.bad_trade_reverse_confidence = min(0.99, max(0.50, float(bad_trade_reverse_confidence)))
        self.bad_trade_reverse_vote_margin = min(0.95, max(0.05, float(bad_trade_reverse_vote_margin)))
        self.bad_trade_reduce_fraction = min(0.95, max(0.10, float(bad_trade_reduce_fraction)))
        self.logger = logger or logging.getLogger("TraderAgent")
        self.strategy_weights = {
            "trend": 1.0,
            "trend_following": 1.05,
            "mean_reversion": 0.95,
            "breakout": 1.1,
            "ml": 1.15,
            "ml_agent": 1.2,
            "defensive": 0.8,
            **dict(strategy_weights or {}),
        }

        self.profiles: dict[str, InvestorProfile] = {}
        for profile_id, profile in dict(profiles or {}).items():
            self.register_profile(profile_id, profile)
        if not self.profiles:
            self.register_profile(
                "default",
                InvestorProfile(
                    risk_level="medium",
                    goal="growth",
                    max_drawdown=0.10,
                    trade_frequency="medium",
                    preferred_assets=[],
                    time_horizon="medium",
                ),
            )
        self.active_profile_id = str(active_profile_id or next(iter(self.profiles))).strip() or next(iter(self.profiles))

        self.latest_market: dict[str, dict[str, Any]] = {}
        self.latest_features: dict[str, FeatureVector] = {}
        self.latest_insights: dict[str, AnalystInsight] = {}
        self.latest_reasoning: dict[tuple[str, str], ReasoningDecision] = {}
        self.latest_snapshot = PortfolioSnapshot(cash=0.0, equity=0.0)
        self.active_positions: dict[str, PositionUpdate] = {}
        self.active_orders: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self.strategy_signals: dict[str, dict[str, Signal]] = defaultdict(dict)
        self.recent_decisions: dict[str, deque[TraderDecision]] = defaultdict(lambda: deque(maxlen=self.decision_history_limit))
        self.performance_by_profile: dict[str, dict[str, float]] = defaultdict(
            lambda: {"trades": 0.0, "wins": 0.0, "losses": 0.0, "realized_pnl": 0.0}
        )
        self.loss_streak_by_profile: dict[str, int] = defaultdict(int)
        self.loss_streak_by_symbol: dict[tuple[str, str], int] = defaultdict(int)
        self._pending_evaluations: set[str] = set()
        self._evaluation_suspended = False
        self._last_management_check: dict[str, datetime] = {}
        self._management_lock_until: dict[str, datetime] = {}

    def attach(self, event_bus: AsyncEventBus) -> None:
        self.bus = event_bus
        event_bus.subscribe(EventType.MARKET_DATA_EVENT, self._on_market_data)
        event_bus.subscribe(EventType.SIGNAL_EVENT, self._on_signal_event)
        event_bus.subscribe(EventType.FEATURE_VECTOR, self._on_feature_vector)
        event_bus.subscribe(EventType.ANALYST_INSIGHT, self._on_analyst_insight)
        event_bus.subscribe(EventType.REASONING_DECISION, self._on_reasoning_decision)
        event_bus.subscribe(EventType.PORTFOLIO_SNAPSHOT, self._on_portfolio_snapshot)
        event_bus.subscribe(EventType.POSITION_UPDATE, self._on_position_update)
        event_bus.subscribe(EventType.ORDER_SUBMITTED, self._on_order_submitted)
        event_bus.subscribe(EventType.ORDER_UPDATE, self._on_order_update)
        event_bus.subscribe(EventType.TRADE_FEEDBACK, self._on_trade_feedback)
        event_bus.subscribe(self._EVALUATE_EVENT, self._on_evaluate)

    def register_profile(self, profile_id: str, profile: InvestorProfile | dict[str, Any]) -> InvestorProfile:
        normalized = profile if isinstance(profile, InvestorProfile) else InvestorProfile(**dict(profile))
        key = str(profile_id or f"profile_{len(self.profiles) + 1}").strip() or f"profile_{len(self.profiles) + 1}"
        self.profiles[key] = normalized
        if not getattr(self, "active_profile_id", None):
            self.active_profile_id = key
        return normalized

    def set_active_profile(self, profile_id: str) -> InvestorProfile:
        key = str(profile_id or "").strip()
        if key not in self.profiles:
            raise KeyError(f"Unknown investor profile '{profile_id}'")
        self.active_profile_id = key
        return self.profiles[key]

    def get_profile(self, profile_id: str | None = None) -> InvestorProfile:
        key = str(profile_id or self.active_profile_id or "").strip()
        if key not in self.profiles:
            raise KeyError(f"Unknown investor profile '{profile_id}'")
        return self.profiles[key]

    def suspend_evaluations(self) -> None:
        self._evaluation_suspended = True

    def resume_evaluations(self) -> None:
        self._evaluation_suspended = False

    async def _on_market_data(self, event) -> None:
        payload = dict(getattr(event, "data", {}) or {})
        symbol = str(payload.get("symbol") or "").strip()
        if not symbol:
            return
        self.latest_market[symbol] = payload
        await self._maybe_queue_position_management(symbol)

    async def _on_feature_vector(self, event) -> None:
        vector = getattr(event, "data", None)
        if vector is None:
            return
        if not isinstance(vector, FeatureVector):
            vector = FeatureVector(**dict(vector))
        self.latest_features[vector.symbol] = vector

    async def _on_analyst_insight(self, event) -> None:
        insight = getattr(event, "data", None)
        if insight is None:
            return
        if not isinstance(insight, AnalystInsight):
            insight = AnalystInsight(**dict(insight))
        self.latest_insights[insight.symbol] = insight

    async def _on_reasoning_decision(self, event) -> None:
        decision = getattr(event, "data", None)
        if decision is None:
            return
        decision = self._normalize_reasoning_decision(decision)
        if decision is None:
            return
        self.latest_reasoning[(decision.symbol, decision.strategy_name)] = decision

    async def _on_portfolio_snapshot(self, event) -> None:
        snapshot = getattr(event, "data", None)
        if snapshot is None:
            return
        if not isinstance(snapshot, PortfolioSnapshot):
            snapshot = PortfolioSnapshot(**dict(snapshot))
        self.latest_snapshot = snapshot

    async def _on_position_update(self, event) -> None:
        update = getattr(event, "data", None)
        if update is None:
            return
        if not isinstance(update, PositionUpdate):
            update = PositionUpdate(**dict(update))
        previous = self.active_positions.get(update.symbol)
        if abs(_safe_float(update.quantity)) <= 1e-12:
            self.active_positions.pop(update.symbol, None)
            self._management_lock_until.pop(update.symbol, None)
            self._last_management_check.pop(update.symbol, None)
            return
        self.active_positions[update.symbol] = update
        if previous is None or abs(_safe_float(previous.quantity) - _safe_float(update.quantity)) > 1e-12:
            self._management_lock_until.pop(update.symbol, None)

    async def _on_order_submitted(self, event) -> None:
        payload = dict(getattr(event, "data", {}) or {})
        symbol = str(payload.get("symbol") or "").strip()
        order_id = str(payload.get("order_id") or "").strip()
        side = str(payload.get("side") or "").strip().lower()
        quantity = max(
            0.0,
            _safe_float(
                payload.get("remaining_quantity", payload.get("quantity", payload.get("filled_quantity", 0.0))),
                0.0,
            ),
        )
        if not symbol or not order_id or side not in {"buy", "sell"} or quantity <= 1e-12:
            return
        self.active_orders[symbol][order_id] = {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "remaining_quantity": quantity,
            "status": str(payload.get("status") or "submitted").strip().lower() or "submitted",
            "strategy_name": str(payload.get("strategy_name") or "").strip(),
        }

    async def _on_order_update(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return

        if isinstance(payload, ExecutionReport):
            report = payload
            symbol = str(report.symbol or "").strip()
            order_id = str(report.order_id or "").strip()
            side = str(report.side or "").strip().lower()
            quantity = max(0.0, _safe_float(report.quantity, 0.0))
            filled_quantity = max(0.0, _safe_float(report.filled_quantity, 0.0))
            remaining_quantity = max(
                0.0,
                _safe_float(
                    report.remaining_quantity,
                    max(0.0, quantity - filled_quantity),
                ),
            )
            status = str(report.status or "").strip().lower()
            strategy_name = str(report.strategy_name or "").strip()
        else:
            raw = dict(payload)
            symbol = str(raw.get("symbol") or "").strip()
            order_id = str(raw.get("order_id") or raw.get("id") or "").strip()
            side = str(raw.get("side") or "").strip().lower()
            quantity = max(0.0, _safe_float(raw.get("quantity"), 0.0))
            filled_quantity = max(0.0, _safe_float(raw.get("filled_quantity"), 0.0))
            remaining_quantity = max(
                0.0,
                _safe_float(raw.get("remaining_quantity"), max(0.0, quantity - filled_quantity)),
            )
            status = str(raw.get("status") or raw.get("action") or "").strip().lower()
            strategy_name = str(raw.get("strategy_name") or "").strip()

        if not symbol or not order_id:
            return

        symbol_orders = self.active_orders.get(symbol)
        if symbol_orders is None:
            if status in {"new", "submitted", "accepted", "open", "pending", "partially_filled"} and side in {"buy", "sell"}:
                tracked_quantity = remaining_quantity if remaining_quantity > 1e-12 else quantity
                if tracked_quantity > 1e-12:
                    self.active_orders[symbol][order_id] = {
                        "order_id": order_id,
                        "symbol": symbol,
                        "side": side,
                        "quantity": quantity if quantity > 1e-12 else tracked_quantity,
                        "remaining_quantity": tracked_quantity,
                        "status": status,
                        "strategy_name": strategy_name,
                    }
            return

        terminal = (
            not status
            or status in {"filled", "failed", "cancelled", "canceled", "rejected", "closed"}
            or status.startswith("rejected")
            or remaining_quantity <= 1e-12
        )
        if terminal:
            symbol_orders.pop(order_id, None)
            if not symbol_orders:
                self.active_orders.pop(symbol, None)
            return

        tracked = dict(symbol_orders.get(order_id) or {})
        tracked.update(
            {
                "order_id": order_id,
                "symbol": symbol,
                "side": side or str(tracked.get("side") or "").strip().lower(),
                "quantity": quantity if quantity > 1e-12 else max(remaining_quantity, _safe_float(tracked.get("quantity"), 0.0)),
                "remaining_quantity": remaining_quantity if remaining_quantity > 1e-12 else max(quantity, _safe_float(tracked.get("remaining_quantity"), 0.0)),
                "status": status,
                "strategy_name": strategy_name or str(tracked.get("strategy_name") or "").strip(),
            }
        )
        if tracked["side"] in {"buy", "sell"} and _safe_float(tracked.get("remaining_quantity"), 0.0) > 1e-12:
            symbol_orders[order_id] = tracked

    async def _on_trade_feedback(self, event) -> None:
        feedback = getattr(event, "data", None)
        if feedback is None:
            return
        if not isinstance(feedback, TradeFeedback):
            feedback = TradeFeedback(**dict(feedback))
        profile_id = str((feedback.metadata or {}).get("profile_id") or self.active_profile_id or "default")
        bucket = self.performance_by_profile[profile_id]
        bucket["trades"] += 1.0
        bucket["realized_pnl"] += float(feedback.pnl or 0.0)
        self._management_lock_until.pop(feedback.symbol, None)
        if feedback.success:
            bucket["wins"] += 1.0
            self.loss_streak_by_profile[profile_id] = 0
            self.loss_streak_by_symbol[(profile_id, feedback.symbol)] = 0
        else:
            bucket["losses"] += 1.0
            self.loss_streak_by_profile[profile_id] += 1
            self.loss_streak_by_symbol[(profile_id, feedback.symbol)] += 1

    async def _on_signal_event(self, event) -> None:
        signal = getattr(event, "data", None)
        if signal is None or self.bus is None:
            return
        if not isinstance(signal, Signal):
            signal = Signal(**dict(signal))
        symbol = str(signal.symbol or "").strip()
        if not symbol:
            return
        self.strategy_signals[symbol][signal.strategy_name] = signal
        await self.queue_evaluation(symbol, profile_id=self.active_profile_id)

    async def queue_evaluation(
        self,
        symbol: str,
        *,
        profile_id: str | None = None,
        force: bool = False,
        source: str | None = None,
    ) -> bool:
        symbol_key = str(symbol or "").strip()
        if not symbol_key or self.bus is None:
            return False
        if self._evaluation_suspended and not force:
            return False
        if not force:
            if symbol_key in self._pending_evaluations:
                return False
            self._pending_evaluations.add(symbol_key)
        await self.bus.publish(
            self._EVALUATE_EVENT,
            {"symbol": symbol_key, "profile_id": profile_id or self.active_profile_id},
            priority=65,
            source=source or self.name,
        )
        return True

    async def _maybe_queue_position_management(self, symbol: str) -> bool:
        symbol_key = str(symbol or "").strip()
        if (
            not symbol_key
            or symbol_key not in self.active_positions
            or self.bus is None
            or self._evaluation_suspended
        ):
            return False
        now = _utc_now()
        last_check = self._last_management_check.get(symbol_key)
        if last_check is not None:
            elapsed = (now - last_check).total_seconds()
            if elapsed < self.position_management_cooldown_seconds:
                return False
        self._last_management_check[symbol_key] = now
        return await self.queue_evaluation(
            symbol_key,
            profile_id=self.active_profile_id,
            source=f"{self.name}:position_management",
        )

    def _management_locked(self, symbol: str, *, now: datetime | None = None) -> bool:
        symbol_key = str(symbol or "").strip()
        if not symbol_key:
            return False
        current_time = now or _utc_now()
        locked_until = self._management_lock_until.get(symbol_key)
        if locked_until is None:
            return False
        if locked_until <= current_time:
            self._management_lock_until.pop(symbol_key, None)
            return False
        return True

    def _lock_position_management(self, symbol: str, *, now: datetime | None = None) -> None:
        symbol_key = str(symbol or "").strip()
        if not symbol_key:
            return
        current_time = now or _utc_now()
        self._management_lock_until[symbol_key] = current_time + timedelta(
            seconds=self.position_management_action_cooldown_seconds
        )

    def _active_order_quantity(self, symbol: str, *, side: str | None = None) -> float:
        symbol_key = str(symbol or "").strip()
        if not symbol_key:
            return 0.0
        target_side = str(side or "").strip().lower()
        total = 0.0
        for order in dict(self.active_orders.get(symbol_key, {}) or {}).values():
            order_side = str((order or {}).get("side") or "").strip().lower()
            if target_side and order_side != target_side:
                continue
            total += max(
                0.0,
                _safe_float(
                    (order or {}).get("remaining_quantity"),
                    _safe_float((order or {}).get("quantity"), 0.0),
                ),
            )
        return total

    def _build_position_management_plan(
        self,
        *,
        symbol: str,
        profile: InvestorProfile,
        position: PositionUpdate | None,
        latest_price: float,
        features: dict[str, float],
        winning_side: str | None,
        base_confidence: float,
        votes: dict[str, float],
        model_probability: float | None,
    ) -> dict[str, Any] | None:
        if position is None or self._management_locked(symbol):
            return None

        quantity = abs(_safe_float(position.quantity))
        if quantity <= 1e-12:
            return None

        current_price = _safe_float(latest_price)
        if current_price <= 0:
            current_price = _safe_float(position.current_price)
        if current_price <= 0:
            current_price = _safe_float(position.average_price)
        entry_price = max(0.0, _safe_float(position.average_price, current_price))
        position_side = _position_side(position.quantity)
        profit_pct = _position_profit_pct(entry_price, current_price, position.quantity)
        volatility = abs(_safe_float(features.get("volatility"), 0.0))
        base_loss_threshold = {
            "low": self.bad_trade_loss_threshold_pct * 0.75,
            "medium": self.bad_trade_loss_threshold_pct,
            "high": self.bad_trade_loss_threshold_pct * 1.35,
        }.get(profile.risk_level, self.bad_trade_loss_threshold_pct)
        loss_threshold = max(
            0.0015,
            min(
                max(base_loss_threshold, volatility * 0.8),
                max(profile.max_drawdown * 0.6, base_loss_threshold),
            ),
        )
        same_side_reduce_threshold = max(loss_threshold * 1.75, self.bad_trade_loss_threshold_pct * 2.5)
        emergency_close_threshold = max(
            loss_threshold * 2.25,
            min(profile.max_drawdown, max(0.01, profile.max_drawdown * 0.85)),
        )

        ema_gap = _safe_float(features.get("ema_gap"), 0.0)
        imbalance = _safe_float(features.get("order_book_imbalance"), 0.0)
        rsi = _safe_float(features.get("rsi"), 50.0)
        vote_total = votes.get("buy", 0.0) + votes.get("sell", 0.0)
        vote_margin = abs(votes.get("buy", 0.0) - votes.get("sell", 0.0)) / max(vote_total, 1e-9)

        opposing_pressure = 0
        if position_side == "buy":
            if ema_gap < 0:
                opposing_pressure += 1
            if imbalance < -0.05:
                opposing_pressure += 1
            if rsi >= 68.0:
                opposing_pressure += 1
        else:
            if ema_gap > 0:
                opposing_pressure += 1
            if imbalance > 0.05:
                opposing_pressure += 1
            if rsi <= 32.0:
                opposing_pressure += 1

        low_model_support = model_probability is not None and model_probability < 0.55
        strong_reverse = (
            winning_side in {"buy", "sell"}
            and winning_side != position_side
            and base_confidence >= self.bad_trade_reverse_confidence
            and vote_margin >= self.bad_trade_reverse_vote_margin
            and (model_probability is None or model_probability >= 0.50)
        )

        base_plan = {
            "symbol": symbol,
            "existing_side": position_side,
            "price": current_price,
            "profit_pct": profit_pct,
            "loss_threshold_pct": loss_threshold,
            "metadata": {
                "vote_margin": vote_margin,
                "ema_gap": ema_gap,
                "order_book_imbalance": imbalance,
                "rsi": rsi,
                "model_probability": model_probability,
            },
        }

        if winning_side in {"buy", "sell"} and winning_side != position_side:
            if strong_reverse and (profit_pct <= loss_threshold * 0.25 or low_model_support or opposing_pressure >= 2):
                position_label = "long" if position_side == "buy" else "short"
                return {
                    **base_plan,
                    "action": "reverse",
                    "quantity": quantity,
                    "target_side": winning_side,
                    "reason": (
                        f"Reverse {symbol}: the {position_label} is at {profit_pct:.2%} and the new "
                        f"{winning_side.upper()} thesis is stronger, so close and reopen in the winning direction."
                    ),
                }

            if profit_pct <= -(loss_threshold * 0.6) or opposing_pressure >= 2:
                trim_quantity = quantity * self.bad_trade_reduce_fraction
                action = "close" if trim_quantity >= quantity * 0.999 else "reduce"
                return {
                    **base_plan,
                    "action": action,
                    "quantity": quantity if action == "close" else trim_quantity,
                    "target_side": winning_side,
                    "reason": (
                        f"Reduce risk on {symbol}: the open {('long' if position_side == 'buy' else 'short')} "
                        f"now fights the winning {winning_side.upper()} bias while PnL is {profit_pct:.2%}."
                    ),
                }

        weak_same_side_conviction = (
            winning_side is None
            or base_confidence < max(self._min_confidence(profile) + 0.05, 0.65)
            or low_model_support
        )
        if profit_pct <= -emergency_close_threshold and (weak_same_side_conviction or opposing_pressure >= 2):
            return {
                **base_plan,
                "action": "close",
                "quantity": quantity,
                "target_side": winning_side,
                "reason": (
                    f"Close {symbol}: the trade is down {profit_pct:.2%}, which breaches the emergency "
                    f"loss threshold of {emergency_close_threshold:.2%}."
                ),
            }

        if profit_pct <= -same_side_reduce_threshold and (weak_same_side_conviction or opposing_pressure >= 2):
            return {
                **base_plan,
                "action": "reduce",
                "quantity": quantity * self.bad_trade_reduce_fraction,
                "target_side": winning_side,
                "reason": (
                    f"Reduce {symbol}: the trade is down {profit_pct:.2%} and the current setup is weakening, "
                    f"so cut risk automatically."
                ),
            }

        return None

    async def _on_evaluate(self, event) -> None:
        payload = dict(getattr(event, "data", {}) or {})
        symbol = str(payload.get("symbol") or "").strip()
        profile_id = str(payload.get("profile_id") or self.active_profile_id or "").strip() or self.active_profile_id
        if not symbol or self.bus is None:
            return
        self._pending_evaluations.discard(symbol)
        decision, order_signal = self.evaluate_symbol(symbol, profile_id=profile_id)
        self.recent_decisions[decision.profile_id].append(decision)
        await self.bus.publish(EventType.DECISION_EVENT, decision, priority=62, source=self.name)
        management_plan = dict((decision.metadata or {}).get("position_management") or {})
        if management_plan:
            self._lock_position_management(symbol, now=_utc_now())
            close_request = ClosePositionRequest(
                symbol=symbol,
                side=_inverse_side(management_plan.get("existing_side")),
                quantity=float(management_plan.get("quantity") or 0.0),
                reason=str(management_plan.get("reason") or "Trader agent position management"),
                price=_safe_float(management_plan.get("price") or decision.price, decision.price),
                strategy_name=decision.selected_strategy or self.name,
                metadata={
                    "profile_id": decision.profile_id,
                    "management_action": management_plan.get("action"),
                    "target_side": management_plan.get("target_side"),
                    "existing_side": management_plan.get("existing_side"),
                    "profit_pct": management_plan.get("profit_pct"),
                    "loss_threshold_pct": management_plan.get("loss_threshold_pct"),
                    **dict(management_plan.get("metadata") or {}),
                },
                timestamp=decision.timestamp,
            )
            await self.bus.publish(EventType.CLOSE_POSITION, close_request, priority=63, source=self.name)
        if order_signal is not None and decision.action in {"BUY", "SELL"}:
            order_priority = 81 if str(management_plan.get("action") or "").strip().lower() == "reverse" else 64
            await self.bus.publish(EventType.ORDER_EVENT, order_signal, priority=order_priority, source=self.name)

    def evaluate_symbol(self, symbol: str, *, profile_id: str | None = None) -> tuple[TraderDecision, Signal | None]:
        profile_key = str(profile_id or self.active_profile_id or "").strip() or self.active_profile_id
        profile = self.get_profile(profile_key)
        now = _utc_now()
        market_time = self._market_reference_time(symbol, fallback=now)
        latest_price = self._latest_price(symbol)
        valid_signals = self._fresh_signals(symbol, now=now)
        features = self._resolve_feature_context(symbol, signals=valid_signals)
        applied_constraints: list[str] = []
        market_hours = self._market_hours_decision(symbol, now=market_time)
        existing_position = self.active_positions.get(symbol)
        profile_metadata = {
            "profile": profile,
            "goal": profile.goal,
            "risk_level": profile.risk_level,
            "trade_frequency": profile.trade_frequency,
            "time_horizon": profile.time_horizon,
            "market_hours": market_hours.to_metadata(),
        }

        if not market_hours.trade_allowed:
            applied_constraints.append("market_hours")
            decision = self._build_decision(
                profile_key,
                symbol,
                action="SKIP",
                side="",
                quantity=0.0,
                price=latest_price,
                confidence=0.0,
                selected_strategy="none",
                reasoning=f"SKIP because {market_hours.reason}",
                applied_constraints=applied_constraints,
                votes={},
                features=features,
                model_probability=None,
                metadata=profile_metadata,
            )
            return decision, None

        if profile.preferred_assets and symbol not in profile.preferred_assets:
            decision = self._build_decision(
                profile_key,
                symbol,
                action="SKIP",
                side="",
                quantity=0.0,
                price=latest_price,
                confidence=0.0,
                selected_strategy="none",
                reasoning=f"SKIP because {symbol} is outside the investor's preferred assets.",
                applied_constraints=["preferred_assets"],
                votes={},
                features=features,
                model_probability=None,
                metadata=profile_metadata,
            )
            return decision, None

        if self._risk_kill_switch_active() or self.latest_snapshot.drawdown_pct >= profile.max_drawdown:
            applied_constraints.append("max_drawdown")
            decision = self._build_decision(
                profile_key,
                symbol,
                action="SKIP",
                side="",
                quantity=0.0,
                price=latest_price,
                confidence=0.0,
                selected_strategy="none",
                reasoning=(
                    f"SKIP because drawdown protection is active for profile {profile.goal}: "
                    f"current drawdown {self.latest_snapshot.drawdown_pct:.2%}, max allowed {profile.max_drawdown:.2%}."
                ),
                applied_constraints=applied_constraints,
                votes={},
                features=features,
                model_probability=None,
                metadata=profile_metadata,
            )
            return decision, None

        if not valid_signals:
            management_plan = self._build_position_management_plan(
                symbol=symbol,
                profile=profile,
                position=existing_position,
                latest_price=latest_price,
                features=features,
                winning_side=None,
                base_confidence=0.0,
                votes={},
                model_probability=None,
            )
            if management_plan is not None:
                plan_action = str(management_plan.get("action") or "").strip().lower()
                management_constraints = [*applied_constraints, f"position_management:{plan_action}"]
                decision = self._build_decision(
                    profile_key,
                    symbol,
                    action=plan_action.upper(),
                    side=str(management_plan.get("target_side") or management_plan.get("existing_side") or ""),
                    quantity=float(management_plan.get("quantity") or 0.0),
                    price=_safe_float(management_plan.get("price") or latest_price, latest_price),
                    confidence=0.0,
                    selected_strategy="position_management",
                    reasoning=str(management_plan.get("reason") or f"Manage the open {symbol} position."),
                    applied_constraints=management_constraints,
                    votes={},
                    features=features,
                    model_probability=None,
                    metadata={**profile_metadata, "position_management": management_plan},
                )
                return decision, None
            decision = self._build_decision(
                profile_key,
                symbol,
                action="HOLD",
                side="",
                quantity=0.0,
                price=latest_price,
                confidence=0.0,
                selected_strategy="none",
                reasoning=f"HOLD because there are no recent strategy signals for {symbol}.",
                applied_constraints=applied_constraints,
                votes={},
                features=features,
                model_probability=None,
                metadata=profile_metadata,
            )
            return decision, None

        confidence_threshold = self._min_confidence(profile)
        filtered_signals = [signal for signal in valid_signals if float(signal.confidence) >= confidence_threshold]
        if not filtered_signals:
            applied_constraints.append(f"confidence>={confidence_threshold:.2f}")
            management_plan = self._build_position_management_plan(
                symbol=symbol,
                profile=profile,
                position=existing_position,
                latest_price=latest_price,
                features=features,
                winning_side=None,
                base_confidence=0.0,
                votes={},
                model_probability=None,
            )
            if management_plan is not None:
                plan_action = str(management_plan.get("action") or "").strip().lower()
                management_constraints = [*applied_constraints, f"position_management:{plan_action}"]
                decision = self._build_decision(
                    profile_key,
                    symbol,
                    action=plan_action.upper(),
                    side=str(management_plan.get("target_side") or management_plan.get("existing_side") or ""),
                    quantity=float(management_plan.get("quantity") or 0.0),
                    price=_safe_float(management_plan.get("price") or latest_price, latest_price),
                    confidence=0.0,
                    selected_strategy="position_management",
                    reasoning=str(management_plan.get("reason") or f"Manage the open {symbol} position."),
                    applied_constraints=management_constraints,
                    votes={},
                    features=features,
                    model_probability=None,
                    metadata={**profile_metadata, "position_management": management_plan},
                )
                return decision, None
            decision = self._build_decision(
                profile_key,
                symbol,
                action="SKIP",
                side="",
                quantity=0.0,
                price=latest_price,
                confidence=0.0,
                selected_strategy="none",
                reasoning=(
                    f"SKIP because the {profile.risk_level} risk profile requires confidence >= {confidence_threshold:.2f}."
                ),
                applied_constraints=applied_constraints,
                votes={},
                features=features,
                model_probability=None,
                metadata=profile_metadata,
            )
            return decision, None

        votes, best_by_side = self._weighted_vote(filtered_signals, profile)
        buy_score = votes.get("buy", 0.0)
        sell_score = votes.get("sell", 0.0)
        total_score = buy_score + sell_score
        if total_score <= 0.0 or abs(buy_score - sell_score) <= 0.05:
            management_plan = self._build_position_management_plan(
                symbol=symbol,
                profile=profile,
                position=existing_position,
                latest_price=latest_price,
                features=features,
                winning_side=None,
                base_confidence=0.0,
                votes=votes,
                model_probability=None,
            )
            if management_plan is not None:
                plan_action = str(management_plan.get("action") or "").strip().lower()
                management_constraints = [*applied_constraints, f"position_management:{plan_action}"]
                decision = self._build_decision(
                    profile_key,
                    symbol,
                    action=plan_action.upper(),
                    side=str(management_plan.get("target_side") or management_plan.get("existing_side") or ""),
                    quantity=float(management_plan.get("quantity") or 0.0),
                    price=_safe_float(management_plan.get("price") or latest_price, latest_price),
                    confidence=0.0,
                    selected_strategy="position_management",
                    reasoning=str(management_plan.get("reason") or f"Manage the open {symbol} position."),
                    applied_constraints=management_constraints,
                    votes=votes,
                    features=features,
                    model_probability=None,
                    metadata={**profile_metadata, "position_management": management_plan},
                )
                return decision, None
            decision = self._build_decision(
                profile_key,
                symbol,
                action="HOLD",
                side="",
                quantity=0.0,
                price=latest_price,
                confidence=0.0,
                selected_strategy="none",
                reasoning=(
                    f"HOLD because weighted voting is inconclusive for {symbol} (buy={buy_score:.2f}, sell={sell_score:.2f})."
                ),
                applied_constraints=applied_constraints,
                votes=votes,
                features=features,
                model_probability=None,
                metadata=profile_metadata,
            )
            return decision, None

        winning_side = "buy" if buy_score > sell_score else "sell"
        best_signal = best_by_side[winning_side]
        winning_score = buy_score if winning_side == "buy" else sell_score
        base_confidence = min(0.99, max(float(best_signal.confidence), winning_score / max(total_score, 1e-9)))
        selected_strategy = best_signal.strategy_name
        reasoning_seed = self.latest_reasoning.get((symbol, selected_strategy))

        size_multiplier = self._size_multiplier(profile)
        quantity = max(0.0, _safe_float(best_signal.quantity, 0.0) * size_multiplier)
        model_probability = self._model_probability(symbol, features)
        if model_probability is not None:
            if model_probability < 0.4:
                applied_constraints.append("ml_skip")
                management_plan = self._build_position_management_plan(
                    symbol=symbol,
                    profile=profile,
                    position=existing_position,
                    latest_price=latest_price or _safe_float(best_signal.price),
                    features=features,
                    winning_side=winning_side,
                    base_confidence=base_confidence,
                    votes=votes,
                    model_probability=model_probability,
                )
                if management_plan is not None:
                    plan_action = str(management_plan.get("action") or "").strip().lower()
                    management_constraints = [*applied_constraints, f"position_management:{plan_action}"]
                    decision = self._build_decision(
                        profile_key,
                        symbol,
                        action=plan_action.upper(),
                        side=str(management_plan.get("target_side") or management_plan.get("existing_side") or winning_side),
                        quantity=float(management_plan.get("quantity") or 0.0),
                        price=_safe_float(management_plan.get("price") or latest_price or _safe_float(best_signal.price)),
                        confidence=min(base_confidence, model_probability),
                        selected_strategy=selected_strategy,
                        reasoning=str(management_plan.get("reason") or f"Manage the open {symbol} position."),
                        applied_constraints=management_constraints,
                        votes=votes,
                        features=features,
                        model_probability=model_probability,
                        metadata={**profile_metadata, "position_management": management_plan},
                    )
                    return decision, None
                decision = self._build_decision(
                    profile_key,
                    symbol,
                    action="SKIP",
                    side=winning_side,
                    quantity=0.0,
                    price=latest_price or _safe_float(best_signal.price),
                    confidence=min(base_confidence, model_probability),
                    selected_strategy=selected_strategy,
                    reasoning=(
                        f"SKIP because ML success probability is only {model_probability:.2f}, below the 0.40 threshold."
                    ),
                    applied_constraints=applied_constraints,
                    votes=votes,
                    features=features,
                    model_probability=model_probability,
                    metadata=profile_metadata,
                )
                return decision, None
            if model_probability < 0.7:
                applied_constraints.append("ml_reduce")
                quantity *= 0.5

        reasoning_influence = self._openai_reasoning_contribution(
            symbol=symbol,
            selected_strategy=selected_strategy,
            winning_side=winning_side,
            reasoning_seed=reasoning_seed,
        )
        reasoning_metadata = self._reasoning_contribution_metadata(reasoning_seed, reasoning_influence)
        decision_metadata = {
            **profile_metadata,
            **({"reasoning_contribution": reasoning_metadata} if reasoning_metadata is not None else {}),
        }
        reasoning_constraint = str(reasoning_influence.get("constraint") or "").strip()
        if reasoning_constraint:
            applied_constraints.append(reasoning_constraint)
        base_confidence = min(
            0.99,
            max(0.0, base_confidence + float(reasoning_influence.get("confidence_delta") or 0.0)),
        )
        quantity *= float(reasoning_influence.get("quantity_multiplier") or 1.0)

        trade_price = latest_price or _safe_float(best_signal.price)
        management_plan = self._build_position_management_plan(
            symbol=symbol,
            profile=profile,
            position=existing_position,
            latest_price=trade_price,
            features=features,
            winning_side=winning_side,
            base_confidence=base_confidence,
            votes=votes,
            model_probability=model_probability,
        )
        if existing_position is None and self._trade_cooldown_active(profile_key, symbol, now):
            applied_constraints.append("trade_frequency")
            decision = self._build_decision(
                profile_key,
                symbol,
                action="SKIP",
                side="",
                quantity=0.0,
                price=trade_price,
                confidence=0.0,
                selected_strategy="none",
                reasoning=(
                    f"SKIP because the {profile.trade_frequency} frequency setting is enforcing a cooldown on {symbol}."
                ),
                applied_constraints=applied_constraints,
                votes=votes,
                features=features,
                model_probability=model_probability,
                metadata=profile_metadata,
            )
            return decision, None

        if existing_position is not None and management_plan is None:
            existing_side = _position_side(existing_position.quantity)
            if existing_side == winning_side:
                existing_quantity = abs(_safe_float(existing_position.quantity))
                if existing_quantity > 1e-12:
                    quantity = max(0.0, quantity - existing_quantity)
                    applied_constraints.append("existing_position_reduce")
            else:
                if len(valid_signals) == 1:
                    management_plan = {
                        "action": "reverse",
                        "quantity": abs(_safe_float(existing_position.quantity)),
                        "existing_side": existing_side,
                        "target_side": winning_side,
                        "price": trade_price,
                        "reason": (
                            f"{winning_side.upper()} because {selected_strategy} explicitly flipped against the open "
                            f"{'long' if existing_side == 'buy' else 'short'} position in {symbol}."
                        ),
                        "metadata": {"explicit_signal_flip": True},
                    }
                else:
                    applied_constraints.append("existing_position_opposite_side")
                    existing_label = "long" if existing_side == "buy" else "short"
                    decision = self._build_decision(
                        profile_key,
                        symbol,
                        action="HOLD",
                        side=winning_side,
                        quantity=0.0,
                        price=trade_price,
                        confidence=base_confidence,
                        selected_strategy=selected_strategy,
                        reasoning=(
                            f"HOLD because an open {existing_label} position in {symbol} has not met the reversal threshold yet."
                        ),
                        applied_constraints=applied_constraints,
                        votes=votes,
                        features=features,
                        model_probability=model_probability,
                        metadata=decision_metadata,
                    )
                    return decision, None

        aligned_active_order_quantity = self._active_order_quantity(symbol, side=winning_side)
        if aligned_active_order_quantity > 1e-12:
            quantity = max(0.0, quantity - aligned_active_order_quantity)
            applied_constraints.append("active_order_reduce")

        if management_plan is not None and str(management_plan.get("action") or "").strip().lower() in {"reduce", "close"}:
            plan_action = str(management_plan.get("action") or "").strip().lower()
            management_constraints = [*applied_constraints, f"position_management:{plan_action}"]
            decision = self._build_decision(
                profile_key,
                symbol,
                action=plan_action.upper(),
                side=str(management_plan.get("target_side") or management_plan.get("existing_side") or winning_side),
                quantity=float(management_plan.get("quantity") or 0.0),
                price=_safe_float(management_plan.get("price") or trade_price, trade_price),
                confidence=base_confidence,
                selected_strategy=selected_strategy,
                reasoning=str(management_plan.get("reason") or f"Manage the open {symbol} position."),
                applied_constraints=management_constraints,
                votes=votes,
                features=features,
                model_probability=model_probability,
                metadata={**decision_metadata, "position_management": management_plan},
            )
            return decision, None

        if reasoning_influence.get("skip_reason"):
            if str((management_plan or {}).get("action") or "").strip().lower() == "reverse":
                return self._reverse_close_only_decision(
                    profile_id=profile_key,
                    symbol=symbol,
                    trade_price=trade_price,
                    confidence=base_confidence,
                    selected_strategy=selected_strategy,
                    skip_reason=str(reasoning_influence["skip_reason"]),
                    applied_constraints=applied_constraints,
                    votes=votes,
                    features=features,
                    model_probability=model_probability,
                    metadata=decision_metadata,
                    management_plan=management_plan,
                )
            decision = self._build_decision(
                profile_key,
                symbol,
                action="SKIP",
                side=winning_side,
                quantity=0.0,
                price=trade_price,
                confidence=base_confidence,
                selected_strategy=selected_strategy,
                reasoning=str(reasoning_influence["skip_reason"]),
                applied_constraints=applied_constraints,
                votes=votes,
                features=features,
                model_probability=model_probability,
                metadata=decision_metadata,
            )
            return decision, None

        entry_guardrail = self._entry_guardrail(
            symbol=symbol,
            profile=profile,
            winning_side=winning_side,
            base_confidence=base_confidence,
            votes=votes,
            features=features,
            model_probability=model_probability,
            market_hours=market_hours,
        )
        if entry_guardrail["skip_reason"]:
            applied_constraints.extend(entry_guardrail["constraints"])
            if str((management_plan or {}).get("action") or "").strip().lower() == "reverse":
                return self._reverse_close_only_decision(
                    profile_id=profile_key,
                    symbol=symbol,
                    trade_price=trade_price,
                    confidence=base_confidence,
                    selected_strategy=selected_strategy,
                    skip_reason=str(entry_guardrail["skip_reason"]),
                    applied_constraints=applied_constraints,
                    votes=votes,
                    features=features,
                    model_probability=model_probability,
                    metadata=decision_metadata,
                    management_plan=management_plan,
                )
            decision = self._build_decision(
                profile_key,
                symbol,
                action="SKIP",
                side=winning_side,
                quantity=0.0,
                price=trade_price,
                confidence=min(base_confidence, model_probability) if model_probability is not None else base_confidence,
                selected_strategy=selected_strategy,
                reasoning=str(entry_guardrail["skip_reason"]),
                applied_constraints=applied_constraints,
                votes=votes,
                features=features,
                model_probability=model_probability,
                metadata=decision_metadata,
            )
            return decision, None
        quantity *= float(entry_guardrail["quantity_multiplier"])
        applied_constraints.extend(entry_guardrail["constraints"])

        performance_guardrail = self._performance_guardrail(profile_id=profile_key, symbol=symbol)
        if performance_guardrail["skip_reason"]:
            applied_constraints.extend(performance_guardrail["constraints"])
            if str((management_plan or {}).get("action") or "").strip().lower() == "reverse":
                return self._reverse_close_only_decision(
                    profile_id=profile_key,
                    symbol=symbol,
                    trade_price=trade_price,
                    confidence=base_confidence,
                    selected_strategy=selected_strategy,
                    skip_reason=str(performance_guardrail["skip_reason"]),
                    applied_constraints=applied_constraints,
                    votes=votes,
                    features=features,
                    model_probability=model_probability,
                    metadata=decision_metadata,
                    management_plan=management_plan,
                )
            decision = self._build_decision(
                profile_key,
                symbol,
                action="SKIP",
                side=winning_side,
                quantity=0.0,
                price=trade_price,
                confidence=base_confidence,
                selected_strategy=selected_strategy,
                reasoning=str(performance_guardrail["skip_reason"]),
                applied_constraints=applied_constraints,
                votes=votes,
                features=features,
                model_probability=model_probability,
                metadata=decision_metadata,
            )
            return decision, None
        quantity *= float(performance_guardrail["quantity_multiplier"])
        applied_constraints.extend(performance_guardrail["constraints"])

        portfolio_guardrail = self._portfolio_guardrail(
            profile=profile,
            symbol=symbol,
            trade_price=trade_price,
            quantity=quantity,
            management_plan=management_plan,
        )
        if portfolio_guardrail["skip_reason"]:
            applied_constraints.extend(portfolio_guardrail["constraints"])
            if str((management_plan or {}).get("action") or "").strip().lower() == "reverse":
                return self._reverse_close_only_decision(
                    profile_id=profile_key,
                    symbol=symbol,
                    trade_price=trade_price,
                    confidence=base_confidence,
                    selected_strategy=selected_strategy,
                    skip_reason=str(portfolio_guardrail["skip_reason"]),
                    applied_constraints=applied_constraints,
                    votes=votes,
                    features=features,
                    model_probability=model_probability,
                    metadata=decision_metadata,
                    management_plan=management_plan,
                )
            decision = self._build_decision(
                profile_key,
                symbol,
                action="SKIP",
                side=winning_side,
                quantity=0.0,
                price=trade_price,
                confidence=base_confidence,
                selected_strategy=selected_strategy,
                reasoning=str(portfolio_guardrail["skip_reason"]),
                applied_constraints=applied_constraints,
                votes=votes,
                features=features,
                model_probability=model_probability,
                metadata=decision_metadata,
            )
            return decision, None
        quantity = float(portfolio_guardrail["quantity"])
        applied_constraints.extend(portfolio_guardrail["constraints"])

        quantity = max(0.0, quantity)
        if quantity <= 1e-12:
            active_coverage = self._active_order_quantity(symbol, side=winning_side)
            existing_coverage = (
                abs(_safe_float(existing_position.quantity))
                if existing_position is not None and _position_side(existing_position.quantity) == winning_side
                else 0.0
            )
            if active_coverage > 1e-12 or existing_coverage > 1e-12:
                coverage_reasons: list[str] = []
                if existing_coverage > 1e-12:
                    position_label = "long" if winning_side == "buy" else "short"
                    coverage_reasons.append(
                        f"an existing {position_label} position already covers {existing_coverage:.4f}"
                    )
                if active_coverage > 1e-12:
                    coverage_reasons.append(
                        f"active {winning_side.upper()} orders already cover {active_coverage:.4f}"
                    )
                decision = self._build_decision(
                    profile_key,
                    symbol,
                    action="HOLD",
                    side=winning_side,
                    quantity=0.0,
                    price=trade_price,
                    confidence=base_confidence,
                    selected_strategy=selected_strategy,
                    reasoning=(
                        f"HOLD because {' and '.join(coverage_reasons)} for {symbol}, so no additional order size is needed."
                    ),
                    applied_constraints=applied_constraints,
                    votes=votes,
                    features=features,
                    model_probability=model_probability,
                    metadata={
                        **decision_metadata,
                        "covered_exposure": {
                            "position_quantity": existing_coverage,
                            "active_order_quantity": active_coverage,
                        },
                    },
                )
                return decision, None
            decision = self._build_decision(
                profile_key,
                symbol,
                action="SKIP",
                side=winning_side,
                quantity=0.0,
                price=trade_price,
                confidence=base_confidence,
                selected_strategy=selected_strategy,
                reasoning=f"SKIP because the final position size for {symbol} was reduced to zero by trader discipline rules.",
                    applied_constraints=[*applied_constraints, "quantity_zero"],
                votes=votes,
                features=features,
                model_probability=model_probability,
                metadata=decision_metadata,
            )
            return decision, None

        stop_price, take_profit = self._protective_prices(trade_price, winning_side, profile, features)
        reasoning = self._compose_reasoning(
            symbol=symbol,
            profile=profile,
            selected_strategy=selected_strategy,
            winning_side=winning_side,
            features=features,
            votes=votes,
            applied_constraints=applied_constraints,
            model_probability=model_probability,
            reasoning_seed=reasoning_seed,
            reasoning_contribution=reasoning_influence,
            market_hours=market_hours,
        )
        if management_plan is not None:
            plan_action = str(management_plan.get("action") or "").strip().lower()
            applied_constraints.append(f"position_management:{plan_action}")
            reasoning = f"{management_plan.get('reason')} {reasoning}".strip()
        action = "BUY" if winning_side == "buy" else "SELL"
        decision = self._build_decision(
            profile_key,
            symbol,
            action=action,
            side=winning_side,
            quantity=quantity,
            price=trade_price,
            confidence=base_confidence,
            selected_strategy=selected_strategy,
            reasoning=reasoning,
            applied_constraints=applied_constraints,
            votes=votes,
            features=features,
            model_probability=model_probability,
            metadata={
                **decision_metadata,
                **({"position_management": management_plan} if management_plan is not None else {}),
            },
        )
        order_signal = Signal(
            symbol=symbol,
            side=winning_side,
            quantity=quantity,
            price=trade_price,
            confidence=base_confidence,
            strategy_name=selected_strategy,
            reason=reasoning,
            stop_price=stop_price,
            take_profit=take_profit,
            metadata={
                "profile_id": profile_key,
                "profile_goal": profile.goal,
                "risk_level": profile.risk_level,
                "trade_frequency": profile.trade_frequency,
                "selected_strategy": selected_strategy,
                "applied_constraints": list(applied_constraints),
                "votes": dict(votes),
                "model_probability": model_probability,
                "profit_protection_enabled": True,
                "asset_type": market_hours.asset_type,
                "market_session": market_hours.session,
                "high_liquidity_session": market_hours.high_liquidity,
                "market_hours": market_hours.to_metadata(),
                **({"reasoning_contribution": reasoning_metadata} if reasoning_metadata is not None else {}),
                **({"position_management": management_plan} if management_plan is not None else {}),
            },
            timestamp=now,
        )
        return decision, order_signal

    def _fresh_signals(self, symbol: str, *, now: datetime) -> list[Signal]:
        strategy_bucket = self.strategy_signals.get(symbol, {})
        fresh: list[Signal] = []
        stale_strategies: list[str] = []
        for strategy_name, signal in strategy_bucket.items():
            timestamp = _coerce_datetime(getattr(signal, "timestamp", None))
            freshness_window = timedelta(seconds=self._signal_ttl_seconds(signal))
            if now - timestamp > freshness_window:
                stale_strategies.append(strategy_name)
                continue
            fresh.append(signal)
        for strategy_name in stale_strategies:
            strategy_bucket.pop(strategy_name, None)
        return fresh

    def _signal_ttl_seconds(self, signal: Signal) -> float:
        metadata = dict(getattr(signal, "metadata", {}) or {})
        timeframe = metadata.get("timeframe")
        timeframe_seconds = _timeframe_to_seconds(timeframe, default=0)
        if timeframe_seconds > 0:
            return max(self.signal_ttl, float(timeframe_seconds) * 1.5)
        return self.signal_ttl

    def _resolve_feature_context(self, symbol: str, *, signals: Iterable[Signal] | None = None) -> dict[str, float]:
        merged: dict[str, float] = {}
        for signal in list(signals or self.strategy_signals.get(symbol, {}).values()):
            metadata = dict(getattr(signal, "metadata", {}) or {})
            merged.update(_normalize_feature_map(metadata.get("features")))
        feature_vector = self.latest_features.get(symbol)
        if feature_vector is not None:
            merged.update(_normalize_feature_map(feature_vector.values))
        return merged

    def _weighted_vote(self, signals: list[Signal], profile: InvestorProfile) -> tuple[dict[str, float], dict[str, Signal]]:
        votes = {"buy": 0.0, "sell": 0.0}
        best_by_side: dict[str, Signal] = {}
        best_scores = {"buy": -1.0, "sell": -1.0}
        for signal in signals:
            side = str(signal.side).lower()
            if side not in votes:
                continue
            weight = self._strategy_weight(profile, signal.strategy_name)
            score = max(0.0, float(signal.confidence) * weight)
            votes[side] += score
            if score > best_scores[side]:
                best_scores[side] = score
                best_by_side[side] = signal
        return votes, best_by_side

    def _vote_margin(self, votes: dict[str, float]) -> float:
        buy_score = max(0.0, _safe_float(votes.get("buy"), 0.0))
        sell_score = max(0.0, _safe_float(votes.get("sell"), 0.0))
        total_score = buy_score + sell_score
        if total_score <= 1e-12:
            return 0.0
        return abs(buy_score - sell_score) / total_score

    def _entry_guardrail(
        self,
        *,
        symbol: str,
        profile: InvestorProfile,
        winning_side: str,
        base_confidence: float,
        votes: dict[str, float],
        features: dict[str, float],
        model_probability: float | None,
        market_hours: MarketWindowDecision,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"skip_reason": None, "quantity_multiplier": 1.0, "constraints": []}
        vote_margin = self._vote_margin(votes)
        rsi = _safe_float(features.get("rsi"), 50.0)
        ema_gap = _safe_float(features.get("ema_gap"), 0.0)
        imbalance = _safe_float(features.get("order_book_imbalance"), 0.0)
        spread_bps = max(0.0, _safe_float(features.get("order_book_spread_bps"), 0.0))
        volume_ratio = _safe_float(features.get("volume_ratio"), 1.0)

        trend_supportive = (winning_side == "buy" and ema_gap > 1e-9) or (winning_side == "sell" and ema_gap < -1e-9)
        trend_adverse = (winning_side == "buy" and ema_gap < -1e-9) or (winning_side == "sell" and ema_gap > 1e-9)
        flow_supportive = (winning_side == "buy" and imbalance >= 0.08) or (winning_side == "sell" and imbalance <= -0.08)
        flow_adverse = (winning_side == "buy" and imbalance <= -0.08) or (winning_side == "sell" and imbalance >= 0.08)
        regime = str(getattr(self.latest_insights.get(symbol), "regime", "") or "").strip().lower()
        regime_adverse = (winning_side == "buy" and regime == "bearish") or (winning_side == "sell" and regime == "bullish")
        overextended = (winning_side == "buy" and rsi >= 74.0) or (winning_side == "sell" and rsi <= 26.0)
        min_vote_margin = {"low": 0.22, "medium": 0.16, "high": 0.12}.get(profile.risk_level, 0.16)
        spread_limit = {"low": 18.0, "medium": 26.0, "high": 36.0}.get(profile.risk_level, 26.0)
        strong_ml_support = model_probability is not None and model_probability >= 0.75
        strong_context = trend_supportive and flow_supportive

        if vote_margin < min_vote_margin and not (strong_context and base_confidence >= self._min_confidence(profile) + 0.08):
            result["skip_reason"] = (
                f"SKIP because the setup edge is too thin for {symbol}: vote margin {vote_margin:.2f} "
                f"is below the {profile.risk_level} profile requirement of {min_vote_margin:.2f}."
            )
            result["constraints"].append("thin_edge")
            return result

        if trend_adverse and flow_adverse and base_confidence < 0.86 and not strong_ml_support:
            result["skip_reason"] = (
                f"SKIP because {symbol} is fighting both trend and order flow: EMA gap {ema_gap:.4f} and "
                f"order-book imbalance {imbalance:.3f} both lean against the proposed {winning_side.upper()} trade."
            )
            result["constraints"].append("countertrend_flow")
            return result

        if regime_adverse and vote_margin < 0.32 and not strong_ml_support:
            result["skip_reason"] = (
                f"SKIP because market regime is {regime or 'adverse'} for {symbol}, and the signal does not have "
                f"enough extra edge to override that backdrop."
            )
            result["constraints"].append("regime_mismatch")
            return result

        if overextended and vote_margin < 0.35 and not (model_probability is not None and model_probability >= 0.80):
            result["skip_reason"] = (
                f"SKIP because {symbol} looks stretched for a fresh {winning_side.upper()} entry with RSI at {rsi:.1f}; "
                "a disciplined trader should avoid chasing extended moves without exceptional confirmation."
            )
            result["constraints"].append("overextended_entry")
            return result

        if spread_bps > 0.0:
            if spread_bps >= spread_limit or (market_hours.high_liquidity is False and spread_bps >= spread_limit * 0.7):
                result["skip_reason"] = (
                    f"SKIP because execution quality is poor for {symbol}: order-book spread is {spread_bps:.1f} bps, "
                    "which is too wide for a clean entry."
                )
                result["constraints"].append("wide_spread")
                return result
            if spread_bps >= spread_limit * 0.6:
                result["constraints"].append("execution_reduce")
                result["quantity_multiplier"] *= 0.7

        if 0.0 < volume_ratio < 0.80 and not (strong_context and vote_margin >= 0.25):
            result["skip_reason"] = (
                f"SKIP because participation is too thin for {symbol}: volume ratio is only {volume_ratio:.2f}, "
                "so the move is not confirmed well enough for entry."
            )
            result["constraints"].append("thin_volume")
            return result

        if 0.0 < volume_ratio < 0.95:
            result["constraints"].append("thin_volume_reduce")
            result["quantity_multiplier"] *= 0.85

        if market_hours.high_liquidity is False and (spread_bps > 0.0 or (0.0 < volume_ratio < 1.0)):
            result["constraints"].append("session_liquidity_reduce")
            result["quantity_multiplier"] *= 0.85

        return result

    def _position_notional(self, position: PositionUpdate | None, fallback_price: float) -> float:
        if position is None:
            return 0.0
        market_value = abs(_safe_float(position.market_value, 0.0))
        if market_value > 0.0:
            return market_value
        current_price = _safe_float(position.current_price, fallback_price)
        if current_price <= 0.0:
            current_price = _safe_float(position.average_price, fallback_price)
        return abs(_safe_float(position.quantity, 0.0) * max(current_price, 0.0))

    def _snapshot_position_notional(self, symbol: str, fallback_price: float) -> float:
        position = dict(self.latest_snapshot.positions or {}).get(symbol)
        if position is None:
            return 0.0
        market_value = abs(_safe_float(getattr(position, "market_value", 0.0), 0.0))
        if market_value > 0.0:
            return market_value
        last_price = _safe_float(getattr(position, "last_price", 0.0), fallback_price)
        if last_price <= 0.0:
            last_price = _safe_float(getattr(position, "average_price", 0.0), fallback_price)
        return abs(_safe_float(getattr(position, "quantity", 0.0), 0.0) * max(last_price, 0.0))

    def _portfolio_guardrail(
        self,
        *,
        profile: InvestorProfile,
        symbol: str,
        trade_price: float,
        quantity: float,
        management_plan: dict[str, Any] | None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"skip_reason": None, "constraints": [], "quantity": max(0.0, _safe_float(quantity))}
        trade_price = max(0.0, _safe_float(trade_price))
        if trade_price <= 0.0 or result["quantity"] <= 1e-12:
            return result

        equity = max(0.0, _safe_float(self.latest_snapshot.equity), _safe_float(self.latest_snapshot.cash))
        if equity <= 0.0:
            return result

        existing_notional = max(
            self._position_notional(self.active_positions.get(symbol), trade_price),
            self._snapshot_position_notional(symbol, trade_price),
        )
        gross_exposure = max(0.0, _safe_float(self.latest_snapshot.gross_exposure, 0.0))
        reversing = str((management_plan or {}).get("action") or "").strip().lower() == "reverse"
        gross_base = max(0.0, gross_exposure - existing_notional) if reversing else gross_exposure
        symbol_base = 0.0 if reversing else existing_notional

        symbol_cap_pct = {"low": 0.12, "medium": 0.18, "high": 0.25}.get(profile.risk_level, 0.18)
        gross_cap_pct = {"low": 0.55, "medium": 0.80, "high": 1.00}.get(profile.risk_level, 0.80)
        symbol_cap = equity * symbol_cap_pct
        gross_cap = equity * gross_cap_pct

        requested_notional = result["quantity"] * trade_price
        symbol_room = max(0.0, symbol_cap - symbol_base)
        gross_room = max(0.0, gross_cap - gross_base)

        if symbol_room <= 1e-9:
            result["skip_reason"] = (
                f"SKIP because {symbol} is already at the portfolio concentration limit of {symbol_cap_pct:.0%} of equity."
            )
            result["constraints"].append("symbol_concentration")
            return result

        if gross_room <= 1e-9:
            result["skip_reason"] = (
                f"SKIP because portfolio gross exposure is already at the internal trader limit of {gross_cap_pct:.0%} of equity."
            )
            result["constraints"].append("portfolio_exposure")
            return result

        allowed_notional = min(requested_notional, symbol_room, gross_room)
        if allowed_notional <= 1e-9:
            result["skip_reason"] = f"SKIP because there is no remaining position budget for a new {symbol} entry."
            result["constraints"].append("portfolio_budget")
            return result

        if allowed_notional < requested_notional * 0.35:
            result["skip_reason"] = (
                f"SKIP because only {allowed_notional / max(requested_notional, 1e-9):.0%} of the requested risk budget "
                f"remains available for {symbol}, which is too small for a clean trade."
            )
            result["constraints"].append("portfolio_budget")
            return result

        if allowed_notional < requested_notional:
            result["quantity"] = allowed_notional / trade_price
            result["constraints"].append("portfolio_reduce")

        return result

    def _performance_guardrail(self, *, profile_id: str, symbol: str) -> dict[str, Any]:
        result: dict[str, Any] = {"skip_reason": None, "quantity_multiplier": 1.0, "constraints": []}
        profile_streak = int(self.loss_streak_by_profile.get(profile_id, 0))
        symbol_streak = int(self.loss_streak_by_symbol.get((profile_id, symbol), 0))
        loss_streak = max(profile_streak, symbol_streak)
        bucket = self.performance_by_profile[profile_id]
        trades = max(0.0, _safe_float(bucket.get("trades"), 0.0))
        losses = max(0.0, _safe_float(bucket.get("losses"), 0.0))
        realized_pnl = _safe_float(bucket.get("realized_pnl"), 0.0)

        if loss_streak >= 3:
            result["skip_reason"] = (
                f"SKIP because the trader profile is on a {loss_streak}-trade losing streak and should cool off "
                "before opening fresh risk."
            )
            result["constraints"].append("loss_streak_pause")
            return result

        if loss_streak >= 2:
            result["constraints"].append("loss_streak_reduce")
            result["quantity_multiplier"] *= 0.5

        if trades >= 5.0 and realized_pnl < 0.0 and (losses / max(trades, 1.0)) >= 0.60:
            result["constraints"].append("performance_reduce")
            result["quantity_multiplier"] *= 0.75

        return result

    def _reverse_close_only_decision(
        self,
        *,
        profile_id: str,
        symbol: str,
        trade_price: float,
        confidence: float,
        selected_strategy: str,
        skip_reason: str,
        applied_constraints: list[str],
        votes: dict[str, float],
        features: dict[str, float],
        model_probability: float | None,
        metadata: dict[str, Any],
        management_plan: dict[str, Any],
    ) -> tuple[TraderDecision, None]:
        normalized_reason = str(skip_reason or "").strip()
        if normalized_reason.lower().startswith("skip because "):
            normalized_reason = normalized_reason[13:]
        close_plan = {
            **dict(management_plan or {}),
            "action": "close",
            "target_side": None,
            "reason": f"Close {symbol} but do not reopen because {normalized_reason.rstrip('.')}.",
        }
        decision = self._build_decision(
            profile_id,
            symbol,
            action="CLOSE",
            side=str(close_plan.get("existing_side") or ""),
            quantity=float(close_plan.get("quantity") or 0.0),
            price=_safe_float(close_plan.get("price") or trade_price, trade_price),
            confidence=confidence,
            selected_strategy=selected_strategy,
            reasoning=str(close_plan.get("reason")),
            applied_constraints=[*applied_constraints, "position_management:close"],
            votes=votes,
            features=features,
            model_probability=model_probability,
            metadata={**metadata, "position_management": close_plan},
        )
        return decision, None

    def _strategy_weight(self, profile: InvestorProfile, strategy_name: str) -> float:
        name = str(strategy_name or "").strip().lower()
        weight = float(self.strategy_weights.get(name, 1.0))
        if profile.goal == "income":
            if "mean_reversion" in name or "defensive" in name:
                weight *= 1.15
            if "breakout" in name:
                weight *= 0.9
        elif profile.goal == "growth":
            if "trend" in name:
                weight *= 1.1
        elif profile.goal == "aggressive":
            if "breakout" in name or "ml" in name:
                weight *= 1.2

        if profile.time_horizon == "short":
            if "breakout" in name or "ml" in name:
                weight *= 1.1
        elif profile.time_horizon == "long":
            if "trend" in name:
                weight *= 1.15
            if "mean_reversion" in name:
                weight *= 0.9
        return weight

    def _min_confidence(self, profile: InvestorProfile) -> float:
        return {"low": 0.70, "medium": 0.60, "high": 0.50}.get(profile.risk_level, 0.60)

    def _size_multiplier(self, profile: InvestorProfile) -> float:
        base = {"low": 0.50, "medium": 1.00, "high": 1.50}.get(profile.risk_level, 1.00)
        goal = {"income": 0.90, "growth": 1.00, "aggressive": 1.15}.get(profile.goal, 1.00)
        horizon = {"short": 0.90, "medium": 1.00, "long": 1.05}.get(profile.time_horizon, 1.00)
        return max(0.1, min(2.5, base * goal * horizon))

    def _trade_cooldown_active(self, profile_id: str, symbol: str, now: datetime) -> bool:
        cooldown = {
            "low": timedelta(minutes=30),
            "medium": timedelta(minutes=10),
            "high": timedelta(minutes=2),
        }.get(self.get_profile(profile_id).trade_frequency, timedelta(minutes=10))
        for decision in reversed(self.recent_decisions[profile_id]):
            if decision.symbol != symbol or decision.action not in {"BUY", "SELL"}:
                continue
            if now - _coerce_datetime(decision.timestamp) < cooldown:
                return True
            break
        return False

    def _model_probability(self, symbol: str, features: dict[str, float]) -> float | None:
        predictor = self.predictor
        if predictor is None or not features:
            return None
        is_ready = getattr(predictor, "is_fitted", getattr(predictor, "is_ready", False))
        if not bool(is_ready):
            return None
        try:
            probability = float(predictor.predict_probability(features))
        except Exception:
            self.logger.exception("TraderAgent ML inference failed for %s", symbol)
            return None
        return max(0.0, min(1.0, probability))

    def _latest_price(self, symbol: str) -> float:
        payload = self.latest_market.get(symbol, {})
        latest_price = _safe_float(payload.get("price") or payload.get("last") or payload.get("close"))
        if latest_price > 0:
            return latest_price
        strategy_bucket = self.strategy_signals.get(symbol, {})
        newest_signal = None
        newest_timestamp = datetime.min.replace(tzinfo=timezone.utc)
        for signal in strategy_bucket.values():
            timestamp = _coerce_datetime(getattr(signal, "timestamp", None))
            if timestamp >= newest_timestamp:
                newest_signal = signal
                newest_timestamp = timestamp
        if newest_signal is not None:
            return _safe_float(getattr(newest_signal, "price", 0.0))
        return 0.0

    def _risk_kill_switch_active(self) -> bool:
        return bool(getattr(self.risk_engine, "kill_switch_active", False))

    def _normalize_reasoning_decision(self, payload: Any) -> ReasoningDecision | None:
        if payload is None:
            return None
        if isinstance(payload, ReasoningDecision):
            return payload
        try:
            data = dict(payload)
        except Exception:
            return None

        symbol = str(data.get("symbol") or "").strip()
        strategy_name = str(data.get("strategy_name") or "unknown").strip() or "unknown"
        side = str(data.get("side") or "").strip().lower()
        decision_text = str(data.get("decision") or side or "NEUTRAL").strip() or "NEUTRAL"
        if not side and decision_text.upper() in {"BUY", "SELL"}:
            side = decision_text.lower()

        metadata = dict(data.get("metadata") or {})
        for key in (
            "provider",
            "mode",
            "decision_id",
            "timeframe",
            "amount",
            "price",
            "latency_ms",
            "fallback_used",
            "prompt_version",
        ):
            value = data.get(key)
            if value not in (None, ""):
                metadata.setdefault(key, value)

        warnings = [str(item).strip() for item in list(data.get("warnings") or []) if str(item).strip()]
        features = _normalize_feature_map(data.get("features"))
        raw_model_probability = data.get("model_probability")
        model_probability = None if raw_model_probability in (None, "") else _safe_float(raw_model_probability, 0.0)

        return ReasoningDecision(
            symbol=symbol,
            strategy_name=strategy_name,
            side=side,
            decision=decision_text,
            confidence=_safe_float(data.get("confidence"), 0.0),
            reasoning=str(data.get("reasoning") or data.get("reason") or "").strip(),
            risk=str(data.get("risk") or "medium").strip() or "medium",
            regime=str(data.get("regime") or "unknown").strip() or "unknown",
            model_probability=model_probability,
            warnings=warnings,
            features=features,
            metadata=metadata,
            timestamp=_coerce_datetime(data.get("timestamp")),
        )

    def _openai_reasoning_contribution(
        self,
        *,
        symbol: str,
        selected_strategy: str,
        winning_side: str,
        reasoning_seed: ReasoningDecision | None,
    ) -> dict[str, Any]:
        contribution: dict[str, Any] = {
            "provider": "",
            "decision": "",
            "confidence": 0.0,
            "side": "",
            "risk": "",
            "warnings": [],
            "available": False,
            "valid": False,
            "applied": False,
            "constraint": "",
            "quantity_multiplier": 1.0,
            "confidence_delta": 0.0,
            "skip_reason": None,
            "summary": "",
            "strategy_name": selected_strategy,
        }
        if reasoning_seed is None:
            return contribution

        metadata = dict(getattr(reasoning_seed, "metadata", {}) or {})
        provider = str(metadata.get("provider") or "").strip().lower()
        contribution["provider"] = provider
        contribution["decision"] = str(reasoning_seed.decision or "").strip().upper()
        contribution["confidence"] = _safe_float(getattr(reasoning_seed, "confidence", 0.0), 0.0)
        contribution["side"] = str(reasoning_seed.side or "").strip().lower()
        contribution["risk"] = str(reasoning_seed.risk or "").strip().lower()
        contribution["warnings"] = list(getattr(reasoning_seed, "warnings", []) or [])

        if provider not in {"openai", "chatgpt"}:
            return contribution
        contribution["available"] = True

        if bool(metadata.get("fallback_used")):
            contribution["summary"] = "OpenAI reasoning fell back to a non-OpenAI provider, so it did not change execution."
            return contribution

        decision = str(contribution["decision"] or "").strip().upper()
        confidence = float(contribution["confidence"])
        side = str(contribution["side"] or "").strip().lower()
        risk = str(contribution["risk"] or "").strip().lower()
        warnings = list(contribution["warnings"])

        if decision not in {"APPROVE", "REJECT", "NEUTRAL", "BUY", "SELL", "HOLD"}:
            return contribution
        contribution["valid"] = True

        supportive = False
        contradictory = False
        if decision == "APPROVE":
            supportive = side in {"", winning_side}
            contradictory = side in {"buy", "sell"} and side != winning_side
        elif decision == "REJECT":
            contradictory = side in {"", winning_side}
        elif decision in {"BUY", "SELL"}:
            recommended_side = decision.lower()
            supportive = recommended_side == winning_side
            contradictory = recommended_side != winning_side
        else:
            contribution["summary"] = "OpenAI returned a neutral review, so the quant decision stayed unchanged."
            return contribution

        high_risk = risk == "high" or len(warnings) >= 2
        if supportive and confidence >= 0.60:
            contribution["applied"] = True
            contribution["constraint"] = "openai_reasoning_confirmed"
            contribution["confidence_delta"] = 0.05 if confidence >= 0.80 else 0.03
            if not high_risk:
                contribution["quantity_multiplier"] = 1.10 if confidence >= 0.80 else 1.05
            contribution["summary"] = (
                f"OpenAI confirmed the {winning_side.upper()} thesis for {symbol}, "
                "so the trader applied a bounded conviction boost."
            )
            return contribution

        if contradictory and confidence >= 0.85:
            contribution["applied"] = True
            contribution["constraint"] = "openai_reasoning_reject"
            contribution["skip_reason"] = (
                f"SKIP because OpenAI rejected the {selected_strategy} {winning_side.upper()} thesis for {symbol} "
                f"with confidence {confidence:.2f}."
            )
            contribution["summary"] = (
                "OpenAI issued a high-conviction rejection, so the trader refused to add fresh risk."
            )
            return contribution

        if contradictory and confidence >= 0.60:
            contribution["applied"] = True
            contribution["constraint"] = "openai_reasoning_reduce"
            contribution["quantity_multiplier"] = 0.50
            contribution["confidence_delta"] = -0.10
            contribution["summary"] = (
                f"OpenAI pushed back on the {winning_side.upper()} thesis for {symbol}, "
                "so the trader cut size and conviction before execution."
            )
            return contribution

        return contribution

    def _reasoning_contribution_metadata(
        self,
        reasoning_seed: ReasoningDecision | None,
        contribution: dict[str, Any],
    ) -> dict[str, Any] | None:
        if reasoning_seed is None and not contribution.get("available"):
            return None
        metadata = dict(getattr(reasoning_seed, "metadata", {}) or {})
        return {
            "provider": str(contribution.get("provider") or metadata.get("provider") or "").strip().lower(),
            "decision": str(contribution.get("decision") or "").strip().upper(),
            "confidence": _safe_float(contribution.get("confidence"), 0.0),
            "side": str(contribution.get("side") or getattr(reasoning_seed, "side", "") or "").strip().lower(),
            "risk": str(contribution.get("risk") or getattr(reasoning_seed, "risk", "") or "").strip().lower(),
            "warnings": list(contribution.get("warnings") or getattr(reasoning_seed, "warnings", []) or []),
            "available": bool(contribution.get("available")),
            "valid": bool(contribution.get("valid")),
            "applied": bool(contribution.get("applied")),
            "constraint": str(contribution.get("constraint") or "").strip(),
            "quantity_multiplier": float(contribution.get("quantity_multiplier") or 1.0),
            "confidence_delta": float(contribution.get("confidence_delta") or 0.0),
            "summary": str(contribution.get("summary") or "").strip(),
            "skip_reason": contribution.get("skip_reason"),
            "reasoning": str(getattr(reasoning_seed, "reasoning", "") or "").strip(),
            "strategy_name": str(contribution.get("strategy_name") or getattr(reasoning_seed, "strategy_name", "") or "").strip(),
            "mode": str(metadata.get("mode") or "").strip().lower(),
            "fallback_used": bool(metadata.get("fallback_used")),
        }

    def _protective_prices(
        self,
        price: float,
        side: str,
        profile: InvestorProfile,
        features: dict[str, float],
    ) -> tuple[float | None, float | None]:
        if price <= 0:
            return None, None
        base_stop = {"low": 0.012, "medium": 0.020, "high": 0.032}.get(profile.risk_level, 0.020)
        volatility = max(0.0, _safe_float(features.get("volatility"), 0.0))
        stop_pct = min(max(base_stop, volatility * 1.5), max(0.005, profile.max_drawdown / 2.0))
        reward_multiple = {"income": 1.6, "growth": 2.1, "aggressive": 2.5}.get(profile.goal, 2.0)
        target_pct = stop_pct * reward_multiple
        if side == "buy":
            return price * (1.0 - stop_pct), price * (1.0 + target_pct)
        return price * (1.0 + stop_pct), price * (1.0 - target_pct)

    def _compose_reasoning(
        self,
        *,
        symbol: str,
        profile: InvestorProfile,
        selected_strategy: str,
        winning_side: str,
        features: dict[str, float],
        votes: dict[str, float],
        applied_constraints: list[str],
        model_probability: float | None,
        reasoning_seed: ReasoningDecision | None,
        reasoning_contribution: dict[str, Any] | None,
        market_hours: MarketWindowDecision | None,
    ) -> str:
        rsi = _safe_float(features.get("rsi"), 50.0)
        ema_gap = _safe_float(features.get("ema_gap"), 0.0)
        volatility = _safe_float(features.get("volatility"), 0.0)
        imbalance = _safe_float(features.get("order_book_imbalance"), 0.0)
        volume_ratio = _safe_float(features.get("volume_ratio"), 1.0)
        spread_bps = max(0.0, _safe_float(features.get("order_book_spread_bps"), 0.0))
        direction_text = "bullish" if ema_gap >= 0 else "bearish"
        seed_text = ""
        if reasoning_seed is not None and reasoning_seed.reasoning:
            seed_text = f" {reasoning_seed.reasoning}"
        contribution_text = str((reasoning_contribution or {}).get("summary") or "").strip()
        explanation = (
            f"{winning_side.upper()} because weighted voting favored {selected_strategy}, "
            f"trend is {direction_text}, RSI={rsi:.1f}, EMA gap={ema_gap:.4f}, volatility={volatility:.4f}, "
            f"order book imbalance={imbalance:.3f}, and it matches the {profile.goal} goal with {profile.risk_level} risk."
        )
        if spread_bps > 0.0:
            explanation += f" Spread={spread_bps:.1f}bps."
        if volume_ratio > 0.0 and abs(volume_ratio - 1.0) > 1e-9:
            explanation += f" Volume ratio={volume_ratio:.2f}."
        if market_hours is not None and market_hours.session:
            explanation += f" Market session={market_hours.session}."
        explanation += f" Vote score buy={votes.get('buy', 0.0):.2f}, sell={votes.get('sell', 0.0):.2f}."
        if model_probability is not None:
            explanation += f" ML probability={model_probability:.2f}."
        if applied_constraints:
            explanation += " Constraints applied: " + ", ".join(applied_constraints) + "."
        if seed_text:
            explanation += seed_text
        if contribution_text:
            explanation += f" {contribution_text}"
        return explanation.strip()

    def _market_reference_time(self, symbol: str, *, fallback: datetime) -> datetime:
        payload = self.latest_market.get(symbol, {})
        if "timestamp" not in payload:
            return fallback
        return _coerce_datetime(payload.get("timestamp"))

    def _market_hours_decision(self, symbol: str, *, now: datetime) -> MarketWindowDecision:
        market_payload = dict(self.latest_market.get(symbol, {}) or {})
        feature_vector = self.latest_features.get(symbol)
        feature_metadata = dict(feature_vector.metadata or {}) if feature_vector is not None else {}
        metadata = {**market_payload, **feature_metadata}
        return self.market_hours_engine.evaluate_trade_window(
            symbol=symbol,
            metadata=metadata,
            now=now,
            require_high_liquidity=self.require_high_liquidity_for_forex,
        )

    def _build_decision(
        self,
        profile_id: str,
        symbol: str,
        *,
        action: str,
        side: str,
        quantity: float,
        price: float,
        confidence: float,
        selected_strategy: str,
        reasoning: str,
        applied_constraints: list[str],
        votes: dict[str, float],
        features: dict[str, float],
        model_probability: float | None,
        metadata: dict[str, Any],
    ) -> TraderDecision:
        profile = metadata.get("profile")
        serialized_profile = None
        if isinstance(profile, InvestorProfile):
            serialized_profile = {
                "risk_level": profile.risk_level,
                "goal": profile.goal,
                "max_drawdown": profile.max_drawdown,
                "trade_frequency": profile.trade_frequency,
                "preferred_assets": list(profile.preferred_assets),
                "time_horizon": profile.time_horizon,
            }
        return TraderDecision(
            profile_id=profile_id,
            symbol=symbol,
            action=action,
            side=side,
            quantity=float(quantity),
            price=float(price),
            confidence=float(confidence),
            selected_strategy=selected_strategy,
            reasoning=reasoning,
            model_probability=model_probability,
            applied_constraints=list(applied_constraints),
            votes={str(key): float(value) for key, value in dict(votes).items()},
            features={str(key): _safe_float(value) for key, value in dict(features).items()},
            metadata={**dict(metadata), "profile": serialized_profile},
        )
