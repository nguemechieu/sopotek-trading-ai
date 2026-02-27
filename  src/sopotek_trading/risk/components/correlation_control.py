class CorrelationControl:

    def __init__(self, correlation_limit):
        self.correlation_limit = correlation_limit

    def check(self, max_corr):
        return max_corr <= self.correlation_limit