class PortfolioSimulator:

    def __init__(self, starting_equity=10000):
        self.equity = starting_equity
        self.positions = {}
        self.equity_curve = [starting_equity]
        self.trades = []

    def update_equity(self, pnl):
        self.equity += pnl
        self.equity_curve.append(self.equity)

    def record_trade(self, trade):
        self.trades.append(trade)