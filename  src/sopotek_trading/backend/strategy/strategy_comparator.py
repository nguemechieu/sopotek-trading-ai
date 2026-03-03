class StrategyComparator:

    def __init__(self):
        self.strategy_data = {}

    def register_trade(self, trade):

        strategy = trade.get("strategy", "default")

        if strategy not in self.strategy_data:
            self.strategy_data[strategy] = []

        self.strategy_data[strategy].append(trade)

    def summary(self):

        summary = {}

        for strategy, trades in self.strategy_data.items():

            pnl = sum(t["pnl"] for t in trades)
            total = len(trades)

            summary[strategy] = {
                "Trades": total,
                "Net PnL": pnl
            }

        return summary