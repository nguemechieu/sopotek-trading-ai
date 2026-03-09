class Simulator:

    def __init__(self, initial_balance=10000):

        self.balance = initial_balance
        self.position = 0
        self.entry_price = None

        self.trades = []

    # ====================================
    # EXECUTE TRADE
    # ====================================

    def execute(self, signal, candle):

        side = signal["side"]
        price = candle["close"]

        if side == "BUY" and self.position == 0:
            self.position = 1
            self.entry_price = price

            trade = {
                "type": "BUY",
                "price": price
            }

            self.trades.append(trade)

            return trade

        elif side == "SELL" and self.position == 1:
            pnl = price - self.entry_price

            self.balance += pnl

            trade = {
                "type": "SELL",
                "price": price,
                "pnl": pnl
            }

            self.trades.append(trade)

            self.position = 0

            return trade
