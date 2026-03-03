class ExecutionSimulator:

    def __init__(self, slippage=0.0005, commission=0.0007):
        self.slippage = slippage
        self.commission = commission

    def execute(self, signal, price, size):

        if signal == "BUY":
            fill_price = price * (1 + self.slippage)
        else:
            fill_price = price * (1 - self.slippage)

        cost = fill_price * size
        commission_cost = cost * self.commission

        return fill_price, commission_cost