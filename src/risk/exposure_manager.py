class ExposureManager:

    def __init__(self):
        self.positions = {}

    # =====================================
    # UPDATE POSITION
    # =====================================

    def update(self, symbol, value):
        self.positions[symbol] = value

    # =====================================
    # TOTAL EXPOSURE
    # =====================================

    def total_exposure(self):
        return sum(abs(v) for v in self.positions.values())

    # =====================================
    # CHECK EXPOSURE LIMIT
    # =====================================

    def check(self, equity, max_exposure_pct):
        exposure = self.total_exposure()

        limit = equity * max_exposure_pct

        return exposure <= limit
