class ExposureControl:

    def __init__(self, max_exposure):
        self.max_exposure = max_exposure

    def check(self, positions, equity):
        for symbol, value in positions.items():
            if abs(value) > equity * self.max_exposure:
                return False
        return True