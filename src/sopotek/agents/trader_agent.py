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
        self.strategy_signals: dict[str, dict[str, Signal]] = defaultdict(dict)
        self.recent_decisions: dict[str, deque[TraderDecision]] = defaultdict(lambda: deque(maxlen=self.decision_history_limit))
        self.performance_by_profile: dict[str, dict[str, float]] = defaultdict(
            lambda: {"trades": 0.0, "wins": 0.0, "losses": 0.0, "realized_pnl": 0.0}
        )
        self._pending_evaluations: set[str] = set()

    def attach(self, event_bus: AsyncEventBus) -> None:
        self.bus = event_bus
        event_bus.subscribe(EventType.MARKET_DATA_EVENT, self._on_market_data)
        event_bus.subscribe(EventType.SIGNAL_EVENT, self._on_signal_event)
        event_bus.subscribe(EventType.FEATURE_VECTOR, self._on_feature_vector)
        event_bus.subscribe(EventType.ANALYST_INSIGHT, self._on_analyst_insight)
        event_bus.subscribe(EventType.REASONING_DECISION, self._on_reasoning_decision)
        event_bus.subscribe(EventType.PORTFOLIO_SNAPSHOT, self._on_portfolio_snapshot)
        event_bus.subscribe(EventType.POSITION_UPDATE, self._on_position_update)
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

    async def _on_market_data(self, event) -> None:
        payload = dict(getattr(event, "data", {}) or {})
        symbol = str(payload.get("symbol") or "").strip()
        if not symbol:
            return
        self.latest_market[symbol] = payload

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
        if not isinstance(decision, ReasoningDecision):
            decision = ReasoningDecision(**dict(decision))
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
        if abs(_safe_float(update.quantity)) <= 1e-12:
            self.active_positions.pop(update.symbol, None)
            return
        self.active_positions[update.symbol] = update

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
        if feedback.success:
            bucket["wins"] += 1.0
        else:
            bucket["losses"] += 1.0

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
        if symbol in self._pending_evaluations:
            return
        self._pending_evaluations.add(symbol)
        await self.bus.publish(
            self._EVALUATE_EVENT,
            {"symbol": symbol, "profile_id": self.active_profile_id},
            priority=65,
            source=self.name,
        )

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
        if order_signal is not None and decision.action in {"BUY", "SELL"}:
            await self.bus.publish(EventType.ORDER_EVENT, order_signal, priority=63, source=self.name)

    def evaluate_symbol(self, symbol: str, *, profile_id: str | None = None) -> tuple[TraderDecision, Signal | None]:
        profile_key = str(profile_id or self.active_profile_id or "").strip() or self.active_profile_id
        profile = self.get_profile(profile_key)
        now = _utc_now()
        market_time = self._market_reference_time(symbol, fallback=now)
        latest_price = self._latest_price(symbol)
        features = dict((self.latest_features.get(symbol).values if self.latest_features.get(symbol) is not None else {}) or {})
        applied_constraints: list[str] = []
        market_hours = self._market_hours_decision(symbol, now=market_time)

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
                metadata={"profile": profile, "market_hours": market_hours.to_metadata()},
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
                metadata={"profile": profile},
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
                metadata={"profile": profile},
            )
            return decision, None

        if self._trade_cooldown_active(profile_key, symbol, now):
            applied_constraints.append("trade_frequency")
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
                    f"SKIP because the {profile.trade_frequency} frequency setting is enforcing a cooldown on {symbol}."
                ),
                applied_constraints=applied_constraints,
                votes={},
                features=features,
                model_probability=None,
                metadata={"profile": profile},
            )
            return decision, None

        valid_signals = self._fresh_signals(symbol, now=now)
        if not valid_signals:
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
                metadata={"profile": profile},
            )
            return decision, None

        confidence_threshold = self._min_confidence(profile)
        filtered_signals = [signal for signal in valid_signals if float(signal.confidence) >= confidence_threshold]
        if not filtered_signals:
            applied_constraints.append(f"confidence>={confidence_threshold:.2f}")
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
                metadata={"profile": profile},
            )
            return decision, None

        votes, best_by_side = self._weighted_vote(filtered_signals, profile)
        buy_score = votes.get("buy", 0.0)
        sell_score = votes.get("sell", 0.0)
        total_score = buy_score + sell_score
        if total_score <= 0.0 or abs(buy_score - sell_score) <= 0.05:
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
                metadata={"profile": profile},
            )
            return decision, None

        winning_side = "buy" if buy_score > sell_score else "sell"
        best_signal = best_by_side[winning_side]
        winning_score = buy_score if winning_side == "buy" else sell_score
        base_confidence = min(0.99, max(float(best_signal.confidence), winning_score / max(total_score, 1e-9)))
        selected_strategy = best_signal.strategy_name
        reasoning_seed = self.latest_reasoning.get((symbol, selected_strategy))

        existing_position = self.active_positions.get(symbol)
        if existing_position is not None:
            if existing_position.quantity > 0 and winning_side == "buy":
                applied_constraints.append("existing_position_same_side")
                decision = self._build_decision(
                    profile_key,
                    symbol,
                    action="SKIP",
                    side="buy",
                    quantity=0.0,
                    price=latest_price,
                    confidence=base_confidence,
                    selected_strategy=selected_strategy,
                    reasoning=f"SKIP because a long position is already open in {symbol}.",
                    applied_constraints=applied_constraints,
                    votes=votes,
                    features=features,
                    model_probability=None,
                    metadata={"profile": profile},
                )
                return decision, None
            if existing_position.quantity < 0 and winning_side == "sell":
                applied_constraints.append("existing_position_same_side")
                decision = self._build_decision(
                    profile_key,
                    symbol,
                    action="SKIP",
                    side="sell",
                    quantity=0.0,
                    price=latest_price,
                    confidence=base_confidence,
                    selected_strategy=selected_strategy,
                    reasoning=f"SKIP because a short position is already open in {symbol}.",
                    applied_constraints=applied_constraints,
                    votes=votes,
                    features=features,
                    model_probability=None,
                    metadata={"profile": profile},
                )
                return decision, None

        size_multiplier = self._size_multiplier(profile)
        quantity = max(0.0, _safe_float(best_signal.quantity, 0.0) * size_multiplier)
        model_probability = self._model_probability(symbol, features)
        if model_probability is not None:
            if model_probability < 0.4:
                applied_constraints.append("ml_skip")
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
                    metadata={"profile": profile},
                )
                return decision, None
            if model_probability < 0.7:
                applied_constraints.append("ml_reduce")
                quantity *= 0.5

        trade_price = latest_price or _safe_float(best_signal.price)
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
            market_hours=market_hours,
        )
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
                "profile": profile,
                "goal": profile.goal,
                "risk_level": profile.risk_level,
                "trade_frequency": profile.trade_frequency,
                "time_horizon": profile.time_horizon,
                "market_hours": market_hours.to_metadata(),
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
            },
            timestamp=now,
        )
        return decision, order_signal

    def _fresh_signals(self, symbol: str, *, now: datetime) -> list[Signal]:
        strategy_bucket = self.strategy_signals.get(symbol, {})
        cutoff = now - timedelta(seconds=self.signal_ttl)
        fresh: list[Signal] = []
        stale_strategies: list[str] = []
        for strategy_name, signal in strategy_bucket.items():
            timestamp = _coerce_datetime(getattr(signal, "timestamp", None))
            if timestamp < cutoff:
                stale_strategies.append(strategy_name)
                continue
            fresh.append(signal)
        for strategy_name in stale_strategies:
            strategy_bucket.pop(strategy_name, None)
        return fresh

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
        return _safe_float(payload.get("price") or payload.get("last") or payload.get("close"))

    def _risk_kill_switch_active(self) -> bool:
        return bool(getattr(self.risk_engine, "kill_switch_active", False))

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
        market_hours: MarketWindowDecision | None,
    ) -> str:
        rsi = _safe_float(features.get("rsi"), 50.0)
        ema_gap = _safe_float(features.get("ema_gap"), 0.0)
        volatility = _safe_float(features.get("volatility"), 0.0)
        imbalance = _safe_float(features.get("order_book_imbalance"), 0.0)
        direction_text = "bullish" if ema_gap >= 0 else "bearish"
        seed_text = ""
        if reasoning_seed is not None and reasoning_seed.reasoning:
            seed_text = f" {reasoning_seed.reasoning}"
        explanation = (
            f"{winning_side.upper()} because weighted voting favored {selected_strategy}, "
            f"trend is {direction_text}, RSI={rsi:.1f}, EMA gap={ema_gap:.4f}, volatility={volatility:.4f}, "
            f"order book imbalance={imbalance:.3f}, and it matches the {profile.goal} goal with {profile.risk_level} risk."
        )
        if market_hours is not None and market_hours.session:
            explanation += f" Market session={market_hours.session}."
        explanation += f" Vote score buy={votes.get('buy', 0.0):.2f}, sell={votes.get('sell', 0.0):.2f}."
        if model_probability is not None:
            explanation += f" ML probability={model_probability:.2f}."
        if applied_constraints:
            explanation += " Constraints applied: " + ", ".join(applied_constraints) + "."
        if seed_text:
            explanation += seed_text
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
