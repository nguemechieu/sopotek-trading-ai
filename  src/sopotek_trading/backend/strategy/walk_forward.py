from sopotek_trading.backend.strategy.backtest_engine import BacktestEngine


class WalkForwardValidator:

    def __init__(self, strategy_class, data, split_ratio=0.7):
        self.strategy_class = strategy_class
        self.data = data
        self.split_ratio = split_ratio

    def run(self):

        split_index = int(len(self.data) * self.split_ratio)

        train_data = self.data.iloc[:split_index]
        test_data = self.data.iloc[split_index:]

        strategy = self.strategy_class()
        strategy.train(train_data)

        from .backtest_engine import BacktestEngine

        engine = BacktestEngine(strategy, test_data)

        return engine.run()
def compare_strategies(strategies, data):

     results = {}

     for strategy in strategies:
        engine = BacktestEngine(strategy, data)
        output = engine.run()

        final_equity = output["equity_curve"][-1]

        results[strategy.name] = final_equity

     return results