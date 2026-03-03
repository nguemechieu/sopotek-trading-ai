class CapitalAllocator:

    def __init__(self, total_equity):
        self.total_equity = total_equity
        self.allocations = {}

    def allocate(self, strategy_name, weight):
        self.allocations[strategy_name] = weight

    def get_allocation(self, strategy_name):
        weight = self.allocations.get(strategy_name, 0)
        return self.total_equity * weight
    def rebalance(self, performance_dict):
        total_score = sum(performance_dict.values())
        for strategy, score in performance_dict.items():
         self.allocations[strategy] = score / total_score