

class BacktestEngine:

    def __init__(self, strategy_func, initial_capital=10000):
        self.strategy = strategy_func
        self.initial_capital = initial_capital

    def run(self, df):

        capital = self.initial_capital
        position = 0
        trades = []

        for i in range(200, len(df)):

            slice_df = df.iloc[:i]
            signal = self.strategy(slice_df)

            price = df["close"].iloc[i]

            if signal == "buy" and position == 0:
                position = capital / price
                capital = 0
                trades.append(("BUY", price))

            elif signal == "sell" and position > 0:
                capital = position * price
                position = 0
                trades.append(("SELL", price))

        final_value = capital if position == 0 else position * df["close"].iloc[-1]

        return {
            "final_value": final_value,
            "return_pct": (final_value / self.initial_capital - 1) * 100,
            "trades": trades
        }

