import numpy as np


class RiskMetrics:

    # =====================================
    # MAX DRAWDOWN
    # =====================================

    @staticmethod
    def max_drawdown(equity_curve):

        peak = equity_curve[0]

        max_dd = 0

        for value in equity_curve:

            if value > peak:
                peak = value

            dd = (peak - value) / peak

            if dd > max_dd:
                max_dd = dd

        return max_dd

    # =====================================
    # VALUE AT RISK
    # =====================================

    @staticmethod
    def var(returns, confidence=0.95):

        return np.percentile(returns, (1 - confidence) * 100)

    # =====================================
    # CONDITIONAL VAR
    # =====================================

    @staticmethod
    def cvar(returns, confidence=0.95):

        var = RiskMetrics.var(returns, confidence)

        losses = returns[returns <= var]

        return np.mean(losses)
