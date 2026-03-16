import numpy as np

from quant.analytics.metrics import Metrics
from quant.analytics.risk_metrics import RiskMetrics


class PerformanceEngine:

    def __init__(self):
        self.equity_curve = []
        self.equity_history = self.equity_curve
        self.trades = []

    # =====================================
    # UPDATE EQUITY
    # =====================================

    def update_equity(self, equity):
        self.equity_curve.append(equity)

    def load_equity_history(self, history):
        self.equity_curve.clear()
        for value in list(history or []):
            try:
                numeric = float(value)
            except Exception:
                continue
            if np.isfinite(numeric):
                self.equity_curve.append(numeric)

    def record_trade(self, trade):
        if trade is None:
            return
        payload = dict(trade)
        order_id = str(payload.get("order_id") or payload.get("id") or "").strip()
        if order_id:
            for index, existing in enumerate(self.trades):
                existing_order_id = str(existing.get("order_id") or existing.get("id") or "").strip()
                if existing_order_id == order_id:
                    merged = dict(existing)
                    for key, value in payload.items():
                        if value not in (None, ""):
                            merged[key] = value
                    self.trades[index] = merged
                    return
        self.trades.append(payload)

    def load_trades(self, trades):
        self.trades.clear()
        for trade in list(trades or []):
            if isinstance(trade, dict):
                self.record_trade(trade)

    # =====================================
    # REPORT
    # =====================================

    def report(self):
        if len(self.equity_curve) < 2:
            return {}

        equity = np.array(self.equity_curve)

        returns = Metrics.returns(equity)

        report = {

            "cumulative_return":
                Metrics.cumulative_return(equity),

            "volatility":
                Metrics.volatility(returns),

            "sharpe_ratio":
                Metrics.sharpe_ratio(returns),

            "sortino_ratio":
                Metrics.sortino_ratio(returns),

            "max_drawdown":
                RiskMetrics.max_drawdown(equity),

            "value_at_risk":
                RiskMetrics.var(returns),

            "conditional_var":
                RiskMetrics.cvar(returns),
        }

        return report
