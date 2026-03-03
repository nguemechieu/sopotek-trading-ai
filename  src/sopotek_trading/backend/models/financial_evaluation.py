import numpy as np


def calculate_sharpe(returns, risk_free_rate=0.0):
    excess_returns = returns - risk_free_rate
    return np.mean(excess_returns) / np.std(excess_returns)

def calculate_max_drawdown(equity_curve):
    peak = equity_curve.cummax()
    drawdown = (equity_curve - peak) / peak
    return drawdown.min()

def evaluate_trading_performance(strategy_returns):

    sharpe = calculate_sharpe(strategy_returns)
    cumulative = (1 + strategy_returns).cumprod()
    max_dd = calculate_max_drawdown(cumulative)

    print("Sharpe Ratio:", sharpe)
    print("Max Drawdown:", max_dd)
    print("Total Return:", cumulative.iloc[-1] - 1)

    return {
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "total_return": cumulative.iloc[-1] - 1
    }