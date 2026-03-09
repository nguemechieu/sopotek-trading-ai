import pandas as pd
import numpy as np


class ReportGenerator:

    # ====================================
    # PERFORMANCE REPORT
    # ====================================

    def generate(self, trades):
        if trades.empty:
            return {}

        pnl = trades["pnl"].dropna()

        total_profit = pnl.sum()

        win_rate = (pnl > 0).mean()

        avg_profit = pnl.mean()

        sharpe = pnl.mean() / pnl.std() if pnl.std() != 0 else 0

        max_drawdown = self._max_drawdown(pnl)

        return {
            "total_profit": total_profit,
            "win_rate": win_rate,
            "avg_profit": avg_profit,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_drawdown
        }

    # ====================================
    # MAX DRAWDOWN
    # ====================================

    def _max_drawdown(self, pnl):
        cumulative = pnl.cumsum()

        peak = cumulative.cummax()

        drawdown = peak - cumulative

        return drawdown.max()
