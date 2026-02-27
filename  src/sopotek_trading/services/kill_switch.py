class KillSwitch:

    def __init__(self, max_drawdown_percent=10):
        self.max_drawdown = max_drawdown_percent
        self.peak_equity = None
        self.trading_enabled = True

    def update_equity(self, current_equity):
        if self.peak_equity is None:
            self.peak_equity = current_equity

        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        drawdown = (
                           (self.peak_equity - current_equity)
                           / self.peak_equity
                   ) * 100

        if drawdown >= self.max_drawdown:
            self.trading_enabled = False

        return self.trading_enabled