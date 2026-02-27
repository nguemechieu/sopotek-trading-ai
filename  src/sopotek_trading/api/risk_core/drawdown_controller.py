class DrawdownController:

    def __init__(self, max_drawdown_percent=15):
        self.max_dd = max_drawdown_percent
        self.peak_equity = None

    def check(self, current_equity):
        if self.peak_equity is None:
            self.peak_equity = current_equity

        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        dd = (self.peak_equity - current_equity) / self.peak_equity * 100

        if dd >= self.max_dd:
            return False  # halt trading

        return True