from __future__ import annotations

import importlib
import logging
from datetime import datetime, timezone

from derivatives.core.config import StrategyConfig
from derivatives.core.event_bus import EventBus
from derivatives.core.models import TradingSignal
from derivatives.data.live_cache.cache import LiveMarketCache
from derivatives.engine.strategies import BaseStrategy, MLStrategy
from derivatives.ml.feature_engineering.features import build_feature_vector


class StrategyEngine:
    def __init__(
        self,
        event_bus: EventBus,
        cache: LiveMarketCache,
        *,
        config: StrategyConfig | None = None,
        inference_engine=None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.bus = event_bus
        self.cache = cache
        self.config = config or StrategyConfig()
        self.inference_engine = inference_engine
        self.logger = logger or logging.getLogger("DerivativesStrategyEngine")
        self.strategies: list[BaseStrategy] = []
        self._cooldowns: dict[tuple[str, str], datetime] = {}
        self.bus.subscribe("market.ticker", self._on_market_ticker)

    def register_strategy(self, strategy: BaseStrategy) -> BaseStrategy:
        self.strategies.append(strategy)
        return strategy

    def load_plugins(self, class_paths: list[str] | None = None) -> list[BaseStrategy]:
        loaded: list[BaseStrategy] = []
        for class_path in list(class_paths or self.config.strategy_classes):
            module_name, class_name = class_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            strategy_class = getattr(module, class_name)
            params = dict(
                self.config.strategy_params.get(class_name)
                or self.config.strategy_params.get(getattr(strategy_class, "name", ""), {})
                or {}
            )
            if issubclass(strategy_class, MLStrategy):
                params.setdefault("inference_engine", self.inference_engine)
            loaded.append(self.register_strategy(strategy_class(**params)))
        return loaded

    async def _on_market_ticker(self, event) -> None:
        payload = dict(event.data or {})
        symbol = str(payload.get("symbol") or "").strip()
        if not symbol:
            return
        if self.config.symbols and symbol not in set(self.config.symbols):
            return

        price = float(payload.get("price") or 0.0)
        if price <= 0:
            return

        features = build_feature_vector(symbol, self.cache)
        history = self.cache.price_series(symbol)
        now = datetime.now(timezone.utc)
        for strategy in self.strategies:
            if len(history) < strategy.min_history:
                continue
            last_signal_at = self._cooldowns.get((strategy.name, symbol))
            if last_signal_at is not None:
                elapsed = (now - last_signal_at).total_seconds()
                if elapsed < float(self.config.signal_cooldown_seconds):
                    continue
            signal = strategy.evaluate(
                symbol=symbol,
                price=price,
                features=features,
                history=history,
                route=None,
                now=now,
            )
            if signal is None or signal.confidence < float(self.config.min_confidence):
                continue
            self._cooldowns[(strategy.name, symbol)] = now
            await self.bus.publish("signal.generated", signal.to_dict(), source=f"strategy:{strategy.name}")

    async def evaluate_symbol(self, symbol: str) -> list[TradingSignal]:
        price = self.cache.latest_price(symbol)
        if price is None:
            return []
        features = build_feature_vector(symbol, self.cache)
        history = self.cache.price_series(symbol)
        now = datetime.now(timezone.utc)
        signals = []
        for strategy in self.strategies:
            if len(history) < strategy.min_history:
                continue
            signal = strategy.evaluate(symbol=symbol, price=price, features=features, history=history, route=None, now=now)
            if signal is not None:
                signals.append(signal)
        return signals
