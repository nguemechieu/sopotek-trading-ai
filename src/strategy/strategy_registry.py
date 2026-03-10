from strategy.strategy import Strategy


class StrategyRegistry:

    def __init__(self):
        self.strategies = {}
        self.active_name = None
        self.default_strategy = Strategy()

    # ===============================
    # REGISTER
    # ===============================

    def register(self, name, strategy):
        self.strategies[name] = strategy
        if self.active_name is None:
            self.active_name = name

    # ===============================
    # GET STRATEGY
    # ===============================

    def get(self, name):
        return self.strategies.get(name)

    # ===============================
    # LIST STRATEGIES
    # ===============================

    def list(self):
        return list(self.strategies.keys())

    def set_active(self, name):
        if name in self.strategies:
            self.active_name = name

    def _resolve_strategy(self, strategy_name=None):
        if strategy_name and strategy_name in self.strategies:
            selected = self.strategies[strategy_name]
            if selected is not self:
                return selected

        if self.active_name and self.active_name in self.strategies:
            selected = self.strategies[self.active_name]
            if selected is not self:
                return selected

        if self.strategies:
            first = next(iter(self.strategies.values()))
            if first is not self:
                return first

        return self.default_strategy

    def generate_ai_signal(self, candles, strategy_name=None):
        strategy = self._resolve_strategy(strategy_name)

        if hasattr(strategy, "generate_ai_signal"):
            signal = strategy.generate_ai_signal(candles)
            if signal:
                return signal

        if hasattr(strategy, "generate_signal"):
            return strategy.generate_signal(candles)

        return None

    def generate_signal(self, candles, strategy_name=None):
        # Prefer AI path when available; fallback to classical rule-based signal.
        return self.generate_ai_signal(candles, strategy_name=strategy_name)
