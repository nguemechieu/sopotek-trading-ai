class RiskManager:

    def __init__(self, max_total_exposure=50000):
        self.max_total_exposure = max_total_exposure

    def validate_portfolio(self, positions):
        exposure = sum(abs(p.quantity * p.average_price) for p in positions)

        if exposure > self.max_total_exposure:
            return False, "Portfolio exposure too high"

        return True, "Portfolio OK"