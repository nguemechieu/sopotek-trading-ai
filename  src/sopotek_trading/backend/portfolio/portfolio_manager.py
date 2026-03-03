import logging


class PortfolioManager:

    def __init__(self, broker,portfolio, risk_engine):
        self.logger = logging.getLogger(__name__)
        self.positions = {}  # symbol -> {quantity, avg_price}
        self.realized_pnl = 0.0
        self.risk_engine = risk_engine
        self.broker = broker
        self.portfolio = portfolio

    # -------------------------------------------------
    # FILL UPDATE
    # -------------------------------------------------

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
            new_qty = pos["quantity"] + quantity

            if new_qty == 0:
                pos["avg_price"] = 0
            else:
                total_cost = pos["avg_price"] * pos["quantity"]
                total_cost += quantity * price
                pos["avg_price"] = total_cost / new_qty

            pos["quantity"] = new_qty

        elif side == "sell":

            # Realized PnL for closing long
            if pos["quantity"] > 0:
                realized = quantity * (price - pos["avg_price"])
                self.realized_pnl += realized

            pos["quantity"] -= quantity

            if pos["quantity"] == 0:
                pos["avg_price"] = 0.0

    # -------------------------------------------------
    # EXPOSURE METRICS
    # -------------------------------------------------

    def gross_exposure(self):
        return sum(abs(p["quantity"] * p["avg_price"])
                   for p in self.positions.values())

    def net_exposure(self):
        return sum(p["quantity"] * p["avg_price"]
                   for p in self.positions.values())

    # -------------------------------------------------
    # UNREALIZED PNL (ASYNC)
    # -------------------------------------------------

    async def unrealized_pnl(self, broker):

        total = 0.0

        for symbol, pos in self.positions.items():

            if pos["quantity"] == 0:
                continue

            current_price =  broker.get_price(symbol)

            pnl = pos["quantity"] * (current_price - pos["avg_price"])
            total += pnl

        return total

    # -------------------------------------------------
    # TOTAL EQUITY (ASYNC)
    # -------------------------------------------------

    async def total_equity(self)->float:

        balance = await self.broker.get_balance()
        self.logger.info(balance)

        if balance == 0 or balance is None:
            return 0.0

        unrealized = await self.unrealized_pnl(self.broker)
        if unrealized is None:
            return 0.0

        return balance + unrealized

    # -------------------------------------------------
    # GET POSITIONS
    # -------------------------------------------------

    async def get_positions(self):
        return self.positions

    # -------------------------------------------------
    # CLEAR (FOR KILL SWITCH)
    # -------------------------------------------------

    def clear(self):
        self.positions = {}
        self.realized_pnl = 0.0