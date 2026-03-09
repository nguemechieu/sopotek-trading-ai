import pandas as pd


class BacktestEngine:

    def __init__(self, strategy, simulator):

        self.strategy = strategy
        self.simulator = simulator

        self.results = []

    # ====================================
    # RUN BACKTEST
    # ====================================

    def run(self, df):

        for i in range(len(df)):

            row = df.iloc[i]

            signal = self.strategy.on_bar(row)

            if signal:

                trade = self.simulator.execute(signal, row)

                if trade:
                    self.results.append(trade)

        return pd.DataFrame(self.results)
