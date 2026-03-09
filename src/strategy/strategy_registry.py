class StrategyRegistry:

    def __init__(self):
        self.strategies = {}

    # ===============================
    # REGISTER
    # ===============================

    def register(self, name, strategy):
        self.strategies[name] = strategy

    # ===============================
    # GET STRATEGY
    # ===============================

    def get(self, name):
        return self.strategies.get(name)

    # ===============================
    # LIST STRATEGIES
    # ===============================

    def list(self):
        return list(self.strategies.keys())
