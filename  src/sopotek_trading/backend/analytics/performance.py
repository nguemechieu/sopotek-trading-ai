import numpy as np

class PerformanceAnalytics:

    @staticmethod
    def sharpe_ratio(returns, risk_free=0):
        excess = returns - risk_free
        return np.mean(excess) / np.std(excess)

    @staticmethod
    def max_drawdown(equity_curve):
        peak = equity_curve[0]
        max_dd = 0

        for value in equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            max_dd = max(max_dd, dd)

        return max_dd