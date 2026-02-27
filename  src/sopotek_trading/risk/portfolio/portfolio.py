class Portfolio:

    def __init__(self):
        self.positions = {}

    def update_position(self, symbol, side, quantity, price):

        if symbol not in self.positions:
            self.positions[symbol] = 0

        if side == "buy":
            self.positions[symbol] += float(quantity)
        elif side == "sell":
            self.positions[symbol] -= float(quantity)