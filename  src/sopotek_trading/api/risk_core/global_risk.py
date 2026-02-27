class GlobalRisk:

    def __init__(self, max_system_drawdown):
        self.max_system_drawdown = max_system_drawdown

    def validate(self, total_equity, peak_equity):
        dd = (peak_equity - total_equity) / peak_equity * 100
        return dd < self.max_system_drawdown