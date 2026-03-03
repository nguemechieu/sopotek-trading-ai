class DrawdownControl:

    def __init__(self, max_drawdown):
        self.max_drawdown = max_drawdown
        self.peak_equity = None

    def check(self, equity):
        if self.peak_equity is None:
            self.peak_equity = equity

        if equity > self.peak_equity:
            self.peak_equity = equity

        drawdown = (self.peak_equity - equity) / self.peak_equity

        return drawdown <= self.max_drawdown