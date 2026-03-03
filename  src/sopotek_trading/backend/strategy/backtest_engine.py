import pandas as pd


class BacktestEngine:

    def __init__(
            self,
            strategy,
            data: pd.DataFrame,
            initial_capital=10000,
            slippage=0.0005,
            commission=0.0007
    ):

        from .data_handler import DataHandler
        from .execution_simulator import ExecutionSimulator
        from .portfolio_simulator import PortfolioSimulator

        self.strategy = strategy
        self.data_handler = DataHandler(data)
        self.execution = ExecutionSimulator(slippage, commission)
        self.portfolio = PortfolioSimulator(initial_capital)

    # ======================================================
    # RUN BACKTEST
    # ======================================================

    def run(self):

        while self.data_handler.has_next():

            bar = self.data_handler.next_bar()
            window = self.data_handler.current_window()

            if len(window) < 100:
                continue

            signal_data = self.strategy.generate_signal(window)

            signal = signal_data["signal"]

            if signal == "HOLD":
                continue

            price = bar["close"]
            size = 1  # Replace with risk engine logic

            fill_price, commission = self.execution.execute(
                signal,
                price,
                size
            )

            pnl = (
                      (fill_price - price) * size
                      if signal == "BUY"
                      else (price - fill_price) * size
                  ) - commission

            trade = {
                "price": price,
                "fill_price": fill_price,
                "pnl": pnl,
                "signal": signal,
                "strategy": self.strategy.name
            }

            self.portfolio.record_trade(trade)
            self.portfolio.update_equity(pnl)

        return {
            "trades": self.portfolio.trades,
            "equity_curve": self.portfolio.equity_curve
        }