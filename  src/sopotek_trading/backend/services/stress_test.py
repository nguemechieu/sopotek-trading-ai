class StressTester:

    @staticmethod
    def apply_shock(positions, shock_percent):
        shocked_values = []

        for p in positions:
            shocked_price = p.average_price * (1 - shock_percent / 100)
            pnl = (shocked_price - p.average_price) * p.quantity
            shocked_values.append(pnl)

        return sum(shocked_values)