from __future__ import annotations

import logging
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import (
    Candle,
    ClosePositionRequest,
    ExecutionReport,
    FeatureVector,
    PositionUpdate,
    ProfitProtectionDecision,
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


def _position_side(quantity: float) -> str:
    return "long" if float(quantity) >= 0.0 else "short"


def _close_side(quantity: float) -> str:
    return "sell" if float(quantity) > 0.0 else "buy"


def _direction_from_side(side: str) -> float:
    return 1.0 if str(side).lower() == "long" else -1.0


def _profit_pct(entry_price: float, current_price: float, side: str) -> float:
    if entry_price <= 0:
        return 0.0
    direction = _direction_from_side(side)
    return ((current_price - entry_price) / entry_price) * direction


def _unrealized_pnl(entry_price: float, current_price: float, quantity: float) -> float:
    return (current_price - entry_price) * quantity


class ProbabilityPredictor(Protocol):
    def predict_probability(self, features: dict[str, float]) -> float:
        ...


@dataclass(slots=True)
class PartialProfitLevel:
    profit_pct: float
    close_fraction: float
    label: str = ""

    def normalized_label(self) -> str:
        if self.label:
            return self.label
        return f"partial_{self.profit_pct:.4f}_{self.close_fraction:.4f}"


@dataclass(slots=True)
class ProtectedPositionState:
    symbol: str
    quantity: float
    initial_quantity: float
    entry_price: float
    current_price: float
    stop_loss: float | None
    take_profit: float | None
    unrealized_pnl: float
    opened_at: datetime
    updated_at: datetime
    side: str
    highest_price: float
    lowest_price: float
    partial_closed: bool = False
    break_even_active: bool = False
    volatility_reduced: bool = False
    ai_reduced: bool = False
    pending_close_quantity: float = 0.0
    pending_reason: str | None = None
    last_model_probability: float | None = None
    last_features: dict[str, float] = field(default_factory=dict)
    last_volatility: float | None = None
    partial_levels_hit: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_open(self) -> timedelta:
        return max(timedelta(0), self.updated_at - self.opened_at)

    def favorable_excursion_pct(self) -> float:
        if self.side == "long":
            return _profit_pct(self.entry_price, self.highest_price, self.side)
        return _profit_pct(self.entry_price, self.lowest_price, self.side)

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "unrealized_pnl": self.unrealized_pnl,
            "duration_open_seconds": self.duration_open.total_seconds(),
            "partial_closed": self.partial_closed,
            "highest_price": self.highest_price,
            "lowest_price": self.lowest_price,
            "last_model_probability": self.last_model_probability,
            "last_volatility": self.last_volatility,
            "metadata": dict(self.metadata),
        }


class ProfitProtectionEngine:
    """
    Protects open profits by trailing stops, break-even promotion, partial exits,
    time-based exits, volatility exits, and ML-guided reductions.

    Example:
        engine = ProfitProtectionEngine(
            event_bus,
            predictor=runtime.ml_pipeline,
            trailing_stop_mode="hybrid",
            partial_profit_levels=[(0.02, 0.5)],
        )
    """

    def __init__(
        self,
        event_bus: AsyncEventBus,
        *,
        predictor: ProbabilityPredictor | None = None,
        risk_engine: Any | None = None,
        portfolio_engine: Any | None = None,
        trailing_stop_mode: str = "hybrid",
        trailing_stop_pct: float = 0.045,
        atr_period: int = 14,
        atr_multiplier: float = 2.0,
        break_even_profit_pct: float = 0.01,
        partial_profit_levels: list[PartialProfitLevel | tuple[float, float]] | None = None,
        time_exit_seconds: float = 3600.0,
        time_exit_min_progress_pct: float = 0.0025,
        volatility_reduce_threshold: float = 0.03,
        volatility_exit_threshold: float = 0.06,
        volatility_reduce_fraction: float = 0.5,
        ai_exit_threshold: float = 0.4,
        ai_reduce_threshold: float = 0.7,
        ai_reduce_fraction: float = 0.5,
        min_quantity: float = 1e-8,
        logger: logging.Logger | None = None,
    ) -> None:
        self.bus = event_bus
        self.predictor = predictor
        self.risk_engine = risk_engine
        self.portfolio_engine = portfolio_engine
        self.trailing_stop_mode = str(trailing_stop_mode or "hybrid").strip().lower()
        self.trailing_stop_pct = max(0.0, float(trailing_stop_pct))
        self.atr_period = max(2, int(atr_period))
        self.atr_multiplier = max(0.0, float(atr_multiplier))
        self.break_even_profit_pct = max(0.0, float(break_even_profit_pct))
        self.partial_profit_levels = self._normalize_partial_levels(partial_profit_levels)
        self.time_exit_seconds = max(1.0, float(time_exit_seconds))
        self.time_exit_min_progress_pct = max(0.0, float(time_exit_min_progress_pct))
        self.volatility_reduce_threshold = max(0.0, float(volatility_reduce_threshold))
        self.volatility_exit_threshold = max(self.volatility_reduce_threshold, float(volatility_exit_threshold))
        self.volatility_reduce_fraction = min(1.0, max(0.0, float(volatility_reduce_fraction)))
        self.ai_exit_threshold = min(1.0, max(0.0, float(ai_exit_threshold)))
        self.ai_reduce_threshold = min(1.0, max(self.ai_exit_threshold, float(ai_reduce_threshold)))
        self.ai_reduce_fraction = min(1.0, max(0.0, float(ai_reduce_fraction)))
        self.min_quantity = max(1e-12, float(min_quantity))
        self.logger = logger or logging.getLogger("ProfitProtectionEngine")
        self.positions: dict[str, ProtectedPositionState] = {}
        self.latest_features: dict[str, FeatureVector] = {}
        self.latest_execution_reports: dict[str, ExecutionReport] = {}
        self.latest_atr: dict[str, float] = {}
        self._atr_windows: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=self.atr_period))
        self._previous_close: dict[str, float] = {}
        self._last_tick_price: dict[str, float] = {}
        self._tick_returns: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=64))

        self.bus.subscribe(EventType.PRICE_UPDATE, self._on_price_update)
        self.bus.subscribe(EventType.POSITION_UPDATE, self._on_position_update)
        self.bus.subscribe(EventType.EXECUTION_REPORT, self._on_execution_report)
        self.bus.subscribe(EventType.FEATURE_VECTOR, self._on_feature_vector)
        self.bus.subscribe(EventType.CANDLE, self._on_candle)

    def get_state(self, symbol: str) -> ProtectedPositionState | None:
        return self.positions.get(str(symbol))

    def _normalize_partial_levels(
        self,
        levels: list[PartialProfitLevel | tuple[float, float]] | None,
    ) -> list[PartialProfitLevel]:
        if levels is None:
            levels = [(0.02, 0.5)]
        normalized: list[PartialProfitLevel] = []
        for level in levels:
            if isinstance(level, PartialProfitLevel):
                candidate = level
            else:
                profit_pct, close_fraction = level
                candidate = PartialProfitLevel(profit_pct=float(profit_pct), close_fraction=float(close_fraction))
            candidate.profit_pct = max(0.0, float(candidate.profit_pct))
            candidate.close_fraction = min(1.0, max(0.0, float(candidate.close_fraction)))
            if candidate.close_fraction <= 0.0:
                continue
            normalized.append(candidate)
        normalized.sort(key=lambda item: item.profit_pct)
        return normalized

    async def _on_feature_vector(self, event) -> None:
        vector = getattr(event, "data", None)
        if vector is None:
            return
        if not isinstance(vector, FeatureVector):
            vector = FeatureVector(**dict(vector))
        self.latest_features[vector.symbol] = vector
        state = self.positions.get(vector.symbol)
        if state is not None:
            state.last_features = {key: _safe_float(value) for key, value in dict(vector.values or {}).items()}

    async def _on_candle(self, event) -> None:
        candle = getattr(event, "data", None)
        if candle is None:
            return
        if not isinstance(candle, Candle):
            candle = Candle(**dict(candle))
        previous_close = _safe_float(self._previous_close.get(candle.symbol), _safe_float(candle.close))
        true_range = max(
            _safe_float(candle.high) - _safe_float(candle.low),
            abs(_safe_float(candle.high) - previous_close),
            abs(_safe_float(candle.low) - previous_close),
        )
        bucket = self._atr_windows[candle.symbol]
        bucket.append(true_range)
        if bucket:
            self.latest_atr[candle.symbol] = sum(bucket) / len(bucket)
        self._previous_close[candle.symbol] = _safe_float(candle.close)

    async def _on_execution_report(self, event) -> None:
        report = getattr(event, "data", None)
        if report is None:
            return
        if not isinstance(report, ExecutionReport):
            report = ExecutionReport(**dict(report))
        self.latest_execution_reports[report.symbol] = report
        state = self.positions.get(report.symbol)
        if state is None:
            return

        if str(report.status).lower() == "failed" and bool((report.metadata or {}).get("close_position")):
            state.pending_close_quantity = 0.0
            state.pending_reason = None
            self.logger.warning(
                "Protective close failed for %s reason=%s",
                report.symbol,
                (report.metadata or {}).get("error") or state.metadata.get("last_protection_reason"),
            )
            return

        report_side = str(report.side).lower()
        is_entry_side = (state.side == "long" and report_side == "buy") or (state.side == "short" and report_side == "sell")
        if is_entry_side:
            if report.stop_price is not None:
                state.stop_loss = float(report.stop_price)
            if report.take_profit is not None:
                state.take_profit = float(report.take_profit)
            state.metadata.update(
                {
                    "entry_order_id": report.order_id,
                    "entry_strategy_name": report.strategy_name,
                    "entry_latency_ms": report.latency_ms,
                }
            )

    async def _on_position_update(self, event) -> None:
        update = getattr(event, "data", None)
        if update is None:
            return
        if not isinstance(update, PositionUpdate):
            update = PositionUpdate(**dict(update))
        symbol = str(update.symbol or "").strip()
        if not symbol:
            return

        timestamp = _coerce_datetime(getattr(update, "timestamp", None))
        quantity = _safe_float(update.quantity)
        current_price = _safe_float(update.current_price)
        if abs(quantity) <= self.min_quantity:
            if symbol in self.positions:
                self.logger.info("Position closed for %s; clearing profit protection state", symbol)
                self.positions.pop(symbol, None)
            return

        side = _position_side(quantity)
        existing = self.positions.get(symbol)
        latest_execution = self.latest_execution_reports.get(symbol)
        default_stop = None if latest_execution is None or latest_execution.stop_price is None else float(latest_execution.stop_price)
        default_take_profit = None if latest_execution is None or latest_execution.take_profit is None else float(latest_execution.take_profit)
        opened_at = _coerce_datetime(getattr(latest_execution, "timestamp", None)) if latest_execution is not None else timestamp

        if existing is None or existing.side != side:
            state = ProtectedPositionState(
                symbol=symbol,
                quantity=quantity,
                initial_quantity=abs(quantity),
                entry_price=_safe_float(update.average_price, current_price),
                current_price=current_price,
                stop_loss=default_stop,
                take_profit=default_take_profit,
                unrealized_pnl=_safe_float(update.unrealized_pnl, _unrealized_pnl(_safe_float(update.average_price, current_price), current_price, quantity)),
                opened_at=opened_at,
                updated_at=timestamp,
                side=side,
                highest_price=current_price,
                lowest_price=current_price,
                last_features=self._extract_feature_values(symbol),
                metadata={"position_source": "portfolio_engine"},
            )
            state.last_volatility = self._current_volatility(symbol, state)
            self.positions[symbol] = state
            self.logger.info(
                "Started profit protection for %s side=%s entry=%.4f quantity=%.6f",
                symbol,
                side,
                state.entry_price,
                quantity,
            )
            return

        increased = abs(quantity) > abs(existing.quantity) + self.min_quantity
        decreased = abs(quantity) + self.min_quantity < abs(existing.quantity)
        existing.quantity = quantity
        existing.entry_price = _safe_float(update.average_price, existing.entry_price)
        existing.current_price = current_price or existing.current_price
        existing.unrealized_pnl = _safe_float(update.unrealized_pnl, _unrealized_pnl(existing.entry_price, existing.current_price, quantity))
        existing.updated_at = timestamp
        existing.last_features = self._extract_feature_values(symbol)
        existing.last_volatility = self._current_volatility(symbol, existing)
        if existing.side == "long":
            existing.highest_price = max(existing.highest_price, existing.current_price)
            existing.lowest_price = min(existing.lowest_price, existing.current_price)
        else:
            existing.highest_price = max(existing.highest_price, existing.current_price)
            existing.lowest_price = min(existing.lowest_price, existing.current_price)

        if decreased:
            existing.partial_closed = True
            existing.pending_close_quantity = 0.0
            existing.pending_reason = None
        if increased:
            existing.initial_quantity = abs(quantity)
            existing.partial_closed = False
            existing.break_even_active = False
            existing.volatility_reduced = False
            existing.ai_reduced = False
            existing.partial_levels_hit.clear()
            existing.pending_close_quantity = 0.0
            existing.pending_reason = None
            existing.opened_at = opened_at
            existing.highest_price = existing.current_price
            existing.lowest_price = existing.current_price
            if default_stop is not None:
                existing.stop_loss = default_stop
            if default_take_profit is not None:
                existing.take_profit = default_take_profit

    async def _on_price_update(self, event) -> None:
        payload = dict(getattr(event, "data", {}) or {})
        symbol = str(payload.get("symbol") or "").strip()
        if not symbol:
            return
        state = self.positions.get(symbol)
        if state is None:
            return
        price = _safe_float(payload.get("price") or payload.get("last") or payload.get("close"))
        if price <= 0:
            return

        timestamp = _coerce_datetime(payload.get("timestamp"))
        previous_price = self._last_tick_price.get(symbol)
        if previous_price and previous_price > 0:
            self._tick_returns[symbol].append((price - previous_price) / previous_price)
        self._last_tick_price[symbol] = price

        state.current_price = price
        state.updated_at = timestamp
        state.unrealized_pnl = _unrealized_pnl(state.entry_price, state.current_price, state.quantity)
        state.last_features = self._extract_feature_values(symbol)
        if state.side == "long":
            state.highest_price = max(state.highest_price, price)
            state.lowest_price = min(state.lowest_price, price)
        else:
            state.highest_price = max(state.highest_price, price)
            state.lowest_price = min(state.lowest_price, price)
        state.last_volatility = self._current_volatility(symbol, state)

        if state.pending_close_quantity > self.min_quantity:
            return

        stop_changed, stop_reason = self._refresh_protective_levels(state)
        if stop_changed:
            await self._publish_order_update(state, stop_reason, action="update_stop")

        if self._risk_kill_switch_active():
            await self._emit_close_request(state, abs(state.quantity), "Risk kill switch active", action="exit")
            return

        if self._take_profit_hit(state):
            await self._emit_close_request(state, abs(state.quantity), "Take profit reached", action="exit")
            return

        if self._stop_hit(state):
            await self._emit_close_request(state, abs(state.quantity), "Protective stop triggered", action="exit")
            return

        if self._time_exit_due(state):
            await self._emit_close_request(state, abs(state.quantity), "Time-based stale trade exit", action="exit")
            return

        volatility = state.last_volatility
        if volatility is not None and volatility >= self.volatility_exit_threshold:
            await self._emit_close_request(
                state,
                abs(state.quantity),
                f"Volatility spike exit ({volatility:.4f})",
                action="exit",
                probability=state.last_model_probability,
            )
            return
        if (
            volatility is not None
            and volatility >= self.volatility_reduce_threshold
            and not state.volatility_reduced
            and abs(state.quantity) > self.min_quantity
        ):
            state.volatility_reduced = True
            state.partial_closed = True
            await self._emit_close_request(
                state,
                abs(state.quantity) * self.volatility_reduce_fraction,
                f"Volatility spike reduction ({volatility:.4f})",
                action="reduce",
                probability=state.last_model_probability,
            )
            return

        probability = self._predict_exit_probability(state)
        if probability is not None:
            state.last_model_probability = probability
            if probability < self.ai_exit_threshold:
                await self._emit_close_request(
                    state,
                    abs(state.quantity),
                    f"AI exit probability={probability:.3f}",
                    action="exit",
                    probability=probability,
                )
                return
            if probability < self.ai_reduce_threshold and not state.ai_reduced:
                state.ai_reduced = True
                state.partial_closed = True
                await self._emit_close_request(
                    state,
                    abs(state.quantity) * self.ai_reduce_fraction,
                    f"AI reduce probability={probability:.3f}",
                    action="reduce",
                    probability=probability,
                )
                return

        profit_pct = _profit_pct(state.entry_price, state.current_price, state.side)
        for level in self.partial_profit_levels:
            label = level.normalized_label()
            if label in state.partial_levels_hit:
                continue
            if profit_pct + 1e-12 < level.profit_pct:
                continue
            state.partial_levels_hit.add(label)
            state.partial_closed = True
            await self._emit_close_request(
                state,
                abs(state.quantity) * level.close_fraction,
                f"Partial profit target reached ({level.profit_pct:.2%})",
                action="reduce",
                probability=state.last_model_probability,
                metadata={"partial_level": label, "target_profit_pct": level.profit_pct},
            )
            return

    def _extract_feature_values(self, symbol: str) -> dict[str, float]:
        vector = self.latest_features.get(symbol)
        if vector is None:
            return {}
        return {key: _safe_float(value) for key, value in dict(vector.values or {}).items()}

    def _refresh_protective_levels(self, state: ProtectedPositionState) -> tuple[bool, str]:
        changed = False
        reasons: list[str] = []
        profit_pct = _profit_pct(state.entry_price, state.current_price, state.side)
        if profit_pct >= self.break_even_profit_pct:
            break_even_stop = state.entry_price
            if self._move_stop_in_profit_direction(state, break_even_stop):
                state.break_even_active = True
                changed = True
                reasons.append("break_even")

        candidate = self._trailing_stop_candidate(state)
        if candidate is not None and self._move_stop_in_profit_direction(state, candidate):
            changed = True
            reasons.append("trailing_stop")
        return changed, ",".join(reasons) if reasons else "no_change"

    def _move_stop_in_profit_direction(self, state: ProtectedPositionState, candidate: float | None) -> bool:
        if candidate is None:
            return False
        value = float(candidate)
        if state.side == "long":
            if value >= state.current_price:
                value = state.current_price * (1.0 - 1e-6)
            if state.stop_loss is None or value > state.stop_loss + 1e-12:
                state.stop_loss = value
                return True
            return False
        if value <= state.current_price:
            value = state.current_price * (1.0 + 1e-6)
        if state.stop_loss is None or value < state.stop_loss - 1e-12:
            state.stop_loss = value
            return True
        return False

    def _trailing_stop_candidate(self, state: ProtectedPositionState) -> float | None:
        candidates: list[float] = []
        if self.trailing_stop_pct > 0.0:
            if state.side == "long":
                candidates.append(state.highest_price * (1.0 - self.trailing_stop_pct))
            else:
                candidates.append(state.lowest_price * (1.0 + self.trailing_stop_pct))

        atr = self.latest_atr.get(state.symbol)
        if atr is not None and atr > 0.0 and self.atr_multiplier > 0.0:
            if state.side == "long":
                candidates.append(state.highest_price - (atr * self.atr_multiplier))
            else:
                candidates.append(state.lowest_price + (atr * self.atr_multiplier))

        if not candidates:
            return None
        if self.trailing_stop_mode == "atr":
            return candidates[-1] if atr is not None else candidates[0]
        if self.trailing_stop_mode == "percent":
            return candidates[0]
        if state.side == "long":
            return max(candidates)
        return min(candidates)

    def _take_profit_hit(self, state: ProtectedPositionState) -> bool:
        if state.take_profit is None:
            return False
        if state.side == "long":
            return state.current_price >= state.take_profit
        return state.current_price <= state.take_profit

    def _stop_hit(self, state: ProtectedPositionState) -> bool:
        if state.stop_loss is None:
            return False
        if state.side == "long":
            return state.current_price <= state.stop_loss
        return state.current_price >= state.stop_loss

    def _time_exit_due(self, state: ProtectedPositionState) -> bool:
        if state.duration_open.total_seconds() < self.time_exit_seconds:
            return False
        return state.favorable_excursion_pct() < self.time_exit_min_progress_pct

    def _current_volatility(self, symbol: str, state: ProtectedPositionState | None = None) -> float | None:
        vector = self.latest_features.get(symbol)
        if vector is not None:
            volatility = vector.values.get("volatility")
            if volatility is not None:
                return max(0.0, _safe_float(volatility))
        returns = self._tick_returns.get(symbol)
        if returns and len(returns) >= 4:
            try:
                return max(0.0, float(statistics.pstdev(returns)))
            except statistics.StatisticsError:
                pass
        atr = self.latest_atr.get(symbol)
        if atr is not None:
            reference_price = state.current_price if state is not None and state.current_price > 0 else self._last_tick_price.get(symbol, 0.0)
            if reference_price > 0:
                return max(0.0, atr / reference_price)
        return None

    def _predict_exit_probability(self, state: ProtectedPositionState) -> float | None:
        predictor = self.predictor
        if predictor is None:
            return None
        is_ready = getattr(predictor, "is_fitted", getattr(predictor, "is_ready", True))
        if not bool(is_ready):
            return None
        features = dict(state.last_features or {})
        if not features:
            return None
        try:
            probability = float(predictor.predict_probability(features))
        except Exception:
            self.logger.exception("ML exit scoring failed for %s", state.symbol)
            return None
        return max(0.0, min(1.0, probability))

    def _risk_kill_switch_active(self) -> bool:
        return bool(getattr(self.risk_engine, "kill_switch_active", False))

    async def _publish_order_update(self, state: ProtectedPositionState, reason: str, *, action: str) -> None:
        payload = {
            "symbol": state.symbol,
            "action": action,
            "reason": reason,
            "entry_price": state.entry_price,
            "current_price": state.current_price,
            "stop_loss": state.stop_loss,
            "take_profit": state.take_profit,
            "unrealized_pnl": state.unrealized_pnl,
            "duration_open_seconds": state.duration_open.total_seconds(),
            "partial_closed": state.partial_closed,
            "side": state.side,
            "quantity": state.quantity,
        }
        await self.bus.publish(EventType.ORDER_UPDATE, payload, priority=76, source="profit_protection_engine")
        self.logger.info(
            "Profit protection update %s action=%s reason=%s stop=%.4f current=%.4f",
            state.symbol,
            action,
            reason,
            _safe_float(state.stop_loss),
            state.current_price,
        )

    async def _emit_close_request(
        self,
        state: ProtectedPositionState,
        requested_quantity: float,
        reason: str,
        *,
        action: str,
        probability: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        quantity = min(abs(state.quantity), max(self.min_quantity, float(requested_quantity)))
        if quantity <= self.min_quantity:
            return
        state.pending_close_quantity = quantity
        state.pending_reason = reason
        state.metadata["last_protection_reason"] = reason
        profit_pct = _profit_pct(state.entry_price, state.current_price, state.side)
        decision = ProfitProtectionDecision(
            symbol=state.symbol,
            action=action,
            reason=reason,
            quantity=quantity,
            stop_loss=state.stop_loss,
            take_profit=state.take_profit,
            unrealized_pnl=state.unrealized_pnl,
            profit_pct=profit_pct,
            model_probability=probability,
            metadata={
                **state.to_payload(),
                **dict(metadata or {}),
            },
        )
        request = ClosePositionRequest(
            symbol=state.symbol,
            side=_close_side(state.quantity),
            quantity=quantity,
            reason=reason,
            price=state.current_price,
            stop_price=state.stop_loss,
            take_profit=state.take_profit,
            strategy_name="profit_protection_engine",
            metadata={
                "action": action,
                "profit_pct": profit_pct,
                "model_probability": probability,
                **dict(metadata or {}),
            },
        )
        await self.bus.publish(EventType.PROFIT_PROTECTION_DECISION, decision, priority=76, source="profit_protection_engine")
        await self.bus.publish(EventType.CLOSE_POSITION, request, priority=77, source="profit_protection_engine")
        self.logger.info(
            "Profit protection %s action=%s quantity=%.6f reason=%s profit_pct=%.2f%%",
            state.symbol,
            action,
            quantity,
            reason,
            profit_pct * 100.0,
        )
