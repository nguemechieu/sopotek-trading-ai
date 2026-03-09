import numpy as np


class Metrics:

    # =====================================
    # RETURNS
    # =====================================

    @staticmethod
    def returns(equity_curve):
        returns = np.diff(equity_curve) / equity_curve[:-1]

        return returns

    # =====================================
    # CUMULATIVE RETURN
    # =====================================

    @staticmethod
    def cumulative_return(equity_curve):
        return (equity_curve[-1] / equity_curve[0]) - 1

    # =====================================
    # VOLATILITY
    # =====================================

    @staticmethod
    def volatility(returns):
        return np.std(returns) * np.sqrt(252)

    # =====================================
    # SHARPE RATIO
    # =====================================

    @staticmethod
    def sharpe_ratio(returns, risk_free_rate=0):
        excess = returns - risk_free_rate

        return np.mean(excess) / np.std(excess)

    # =====================================
    # SORTINO RATIO
    # =====================================

    @staticmethod
    def sortino_ratio(returns):
        negative_returns = returns[returns < 0]

        downside_std = np.std(negative_returns)

        return np.mean(returns) / downside_std
