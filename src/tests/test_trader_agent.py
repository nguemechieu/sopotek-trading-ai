import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sopotek.agents.trader_agent import InvestorProfile, TraderAgent
from sopotek.core.event_bus import AsyncEventBus, InMemoryEventStore
from sopotek.core.event_types import EventType
from sopotek.core.models import FeatureVector, Signal
from sopotek.core.orchestrator import SopotekRuntime
from sopotek.engines.strategy import BaseStrategy


async def _drain(bus: AsyncEventBus) -> None:
    while not bus.queue.empty():
        await bus.dispatch_once()


class ConstantPredictor:
    def __init__(self, probability: float, *, is_fitted: bool = True) -> None:
        self.probability = float(probability)
        self.is_fitted = bool(is_fitted)

    def predict_probability(self, _features) -> float:
        return self.probability


class DummyBroker:
    def __init__(self):
        self.orders = []

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200):
        return []

    async def place_order(self, order):
        self.orders.append(order)
        return {
            "id": f"order-{len(self.orders)}",
            "status": "filled",
            "price": order.price,
            "fill_price": order.price,
            "filled_quantity": order.quantity,
        }

    async def stream_ticks(self, symbol: str):
        if False:
            yield {"symbol": symbol, "price": 0.0}


class TrendStrategy(BaseStrategy):
    name = "trend"

    async def generate_signal(self, *, symbol: str, trigger: str, payload):
        if trigger != EventType.MARKET_TICK:
            return None
        price = float(payload["price"])
        return Signal(
            symbol=symbol,
            side="buy",
            quantity=1.0,
            price=price,
            confidence=0.82,
            strategy_name=self.name,
            reason="trend continuation",
        )


def test_trader_agent_conservative_profile_skips_low_confidence_signal():
    async def scenario():
        bus = AsyncEventBus(store=InMemoryEventStore(), enable_persistence=True)
        agent = TraderAgent(
            profiles={
                "income": InvestorProfile(
                    risk_level="low",
                    goal="income",
                    max_drawdown=0.05,
                    trade_frequency="low",
                    preferred_assets=["BTC/USDT"],
                    time_horizon="long",
                )
            },
            active_profile_id="income",
        )
        agent.attach(bus)
        decisions = []
        orders = []
        bus.subscribe(EventType.DECISION_EVENT, lambda event: decisions.append(event.data))
        bus.subscribe(EventType.ORDER_EVENT, lambda event: orders.append(event.data))

        await bus.publish(EventType.MARKET_DATA_EVENT, {"symbol": "BTC/USDT", "price": 100.0}, priority=19)
        await bus.publish(
            EventType.SIGNAL_EVENT,
            Signal(
                symbol="BTC/USDT",
                side="buy",
                quantity=1.0,
                price=100.0,
                confidence=0.65,
                strategy_name="trend_following",
                reason="marginal setup",
            ),
            priority=61,
        )
        await _drain(bus)
        return decisions[-1], orders

    decision, orders = asyncio.run(scenario())

    assert decision.action == "SKIP"
    assert "confidence" in decision.reasoning.lower()
    assert orders == []


def test_trader_agent_weighted_vote_and_ml_reduce_order_size():
    async def scenario():
        bus = AsyncEventBus(store=InMemoryEventStore(), enable_persistence=True)
        agent = TraderAgent(
            profiles={
                "growth": InvestorProfile(
                    risk_level="high",
                    goal="growth",
                    max_drawdown=0.12,
                    trade_frequency="high",
                    preferred_assets=["ETH/USDT"],
                    time_horizon="medium",
                )
            },
            active_profile_id="growth",
            predictor=ConstantPredictor(0.55),
        )
        agent.attach(bus)
        decisions = []
        orders = []
        bus.subscribe(EventType.DECISION_EVENT, lambda event: decisions.append(event.data))
        bus.subscribe(EventType.ORDER_EVENT, lambda event: orders.append(event.data))

        await bus.publish(EventType.MARKET_DATA_EVENT, {"symbol": "ETH/USDT", "price": 101.0}, priority=19)
        await bus.publish(
            EventType.FEATURE_VECTOR,
            FeatureVector(
                symbol="ETH/USDT",
                timeframe="1m",
                values={"rsi": 33.0, "ema_gap": 0.02, "volatility": 0.012, "order_book_imbalance": 0.18},
            ),
            priority=45,
        )
        await bus.publish(
            EventType.SIGNAL_EVENT,
            Signal(symbol="ETH/USDT", side="buy", quantity=2.0, price=101.0, confidence=0.62, strategy_name="trend_following", reason="trend"),
            priority=61,
        )
        await bus.publish(
            EventType.SIGNAL_EVENT,
            Signal(symbol="ETH/USDT", side="buy", quantity=1.5, price=101.0, confidence=0.58, strategy_name="breakout", reason="breakout"),
            priority=61,
        )
        await bus.publish(
            EventType.SIGNAL_EVENT,
            Signal(symbol="ETH/USDT", side="sell", quantity=1.0, price=101.0, confidence=0.51, strategy_name="mean_reversion", reason="fade"),
            priority=61,
        )
        await _drain(bus)
        return decisions[-1], orders[-1]

    decision, order = asyncio.run(scenario())

    assert decision.action == "BUY"
    assert decision.selected_strategy == "trend_following"
    assert decision.model_probability == pytest.approx(0.55)
    assert order.quantity == pytest.approx(1.5)
    assert order.metadata["profile_id"] == "growth"
    assert "growth" in decision.reasoning


def test_runtime_trader_agent_routes_orders_through_risk_and_execution():
    async def scenario():
        runtime = SopotekRuntime(
            broker=DummyBroker(),
            starting_equity=100000.0,
            enable_default_agents=False,
            enable_trader_agent=True,
            trader_profiles={
                "growth": InvestorProfile(
                    risk_level="medium",
                    goal="growth",
                    max_drawdown=0.10,
                    trade_frequency="medium",
                    preferred_assets=["BTC/USDT"],
                    time_horizon="medium",
                )
            },
            active_trader_profile="growth",
        )
        runtime.register_strategy(TrendStrategy(), active=True)

        await runtime.market_data.publish_tick("BTC/USDT", {"symbol": "BTC/USDT", "price": 100.0})
        await _drain(runtime.bus)

        return runtime

    runtime = asyncio.run(scenario())

    assert runtime.trader_agent is not None
    assert runtime.broker.orders
    order = runtime.broker.orders[0]
    assert order.metadata["profile_id"] == "growth"
    assert runtime.execution_monitor.reports
    assert runtime.trader_agent.recent_decisions["growth"][-1].action == "BUY"
