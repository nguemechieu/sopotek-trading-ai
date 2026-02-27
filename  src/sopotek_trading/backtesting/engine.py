class BacktestEngine:

    def __init__(self, strategy, historical_data):
        self.strategy = strategy
        self.data = historical_data
        self.balance = 10000
        self.positions = []

    def run(self):
        for candle in self.data:
            signal = self.strategy.generate_signal(candle)

            if signal == "BUY":
                self.positions.append(candle["close"])

        return self.balance