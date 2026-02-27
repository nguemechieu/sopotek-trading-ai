class ExposureGuard:

    def __init__(self, max_exposure):
        self.max_exposure = max_exposure

    def check(self, positions):
        exposure = sum(abs(p.quantity * p.average_price) for p in positions)

        if exposure > self.max_exposure:
            return False

        return True