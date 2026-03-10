import copy
import itertools

import pandas as pd

from backtesting.backtest_engine import BacktestEngine
from backtesting.report_generator import ReportGenerator
from backtesting.simulator import Simulator


class StrategyOptimizer:
    def __init__(self, strategy, initial_balance=10000):
        self.strategy = strategy
        self.initial_balance = float(initial_balance)

    def _resolve_strategy(self, strategy_name=None):
        if hasattr(self.strategy, "_resolve_strategy"):
            return self.strategy._resolve_strategy(strategy_name)
        return self.strategy

    def _clone_strategy(self, base_strategy):
        try:
            return copy.deepcopy(base_strategy)
        except Exception:
            model = getattr(base_strategy, "model", None)
            try:
                clone = base_strategy.__class__(model=model)
            except TypeError:
                clone = base_strategy.__class__()
                if model is not None and hasattr(clone, "model"):
                    clone.model = model
            return clone

    def default_param_grid(self, strategy_name=None):
        base = self._resolve_strategy(strategy_name)

        def around(value, offsets, minimum):
            candidates = []
            for offset in offsets:
                candidate = int(value + offset)
                if candidate >= minimum and candidate not in candidates:
                    candidates.append(candidate)
            return candidates or [int(max(value, minimum))]

        rsi_period = int(getattr(base, "rsi_period", 14) or 14)
        ema_fast = int(getattr(base, "ema_fast", 20) or 20)
        ema_slow = int(getattr(base, "ema_slow", 50) or 50)
        atr_period = int(getattr(base, "atr_period", 14) or 14)

        return {
            "rsi_period": around(rsi_period, (-4, 0, 4), 2),
            "ema_fast": around(ema_fast, (-5, 0, 5), 2),
            "ema_slow": around(ema_slow, (-10, 0, 10), 3),
            "atr_period": around(atr_period, (-4, 0, 4), 2),
        }

    def _param_rows(self, param_grid):
        keys = list(param_grid.keys())
        values = [list(param_grid[key]) for key in keys]
        for combo in itertools.product(*values):
            params = dict(zip(keys, combo))
            if params.get("ema_fast", 0) >= params.get("ema_slow", 0):
                continue
            yield params

    def optimize(self, data, symbol="BACKTEST", strategy_name=None, param_grid=None):
        grid = param_grid or self.default_param_grid(strategy_name)
        rows = []

        for params in self._param_rows(grid):
            strategy_instance = self._clone_strategy(self._resolve_strategy(strategy_name))
            for key, value in params.items():
                setattr(strategy_instance, key, value)

            engine = BacktestEngine(
                strategy=strategy_instance,
                simulator=Simulator(initial_balance=self.initial_balance),
            )
            trades = engine.run(data, symbol=symbol)
            report = ReportGenerator(
                trades=trades,
                equity_history=engine.equity_curve,
            ).generate()

            row = dict(params)
            row.update(report)
            rows.append(row)

        if not rows:
            return pd.DataFrame()

        results = pd.DataFrame(rows)
        sort_columns = [
            column
            for column in ["total_profit", "sharpe_ratio", "final_equity", "win_rate"]
            if column in results.columns
        ]
        if sort_columns:
            results = results.sort_values(sort_columns, ascending=False).reset_index(drop=True)
        return results
