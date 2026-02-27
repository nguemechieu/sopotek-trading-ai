class PortfolioManager:

    def __init__(self):
        self.positions = {}
        self.realized_pnl = 0.0

    def update_fill(self, symbol, side, quantity, price):

        quantity = float(quantity)
        price = float(price)

        if symbol not in self.positions:
            self.positions[symbol] = {
                "quantity": 0.0,
                "avg_price": 0.0
            }

        pos = self.positions[symbol]

        if side == "buy":

            total_cost = pos["avg_price"] * pos["quantity"]
            total_cost += quantity * price

            pos["quantity"] += quantity
            pos["avg_price"] = total_cost / pos["quantity"]

        elif side == "sell":

            realized = quantity * (price - pos["avg_price"])
            self.realized_pnl += realized

            pos["quantity"] -= quantity

            if pos["quantity"] == 0:
                pos["avg_price"] = 0.0