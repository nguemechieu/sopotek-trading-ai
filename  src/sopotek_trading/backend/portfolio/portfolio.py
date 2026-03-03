import logging
from typing import Dict

logger = logging.getLogger(__name__)


class Portfolio:

    def __init__(self,broker):
        self.broker = broker
        self.positions: Dict[str, Dict[str, float]] = {}

    async def get_available_balance(self) :
        available_balance = await self.broker.get_balance()
        logger.debug(f"Available balance: {available_balance}")
        return available_balance





    # -------------------------------------------------
    # UPDATE POSITION FROM FILL
    # -------------------------------------------------
    def update_position(self, symbol, side, quantity, price):

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

            if pos["quantity"] != 0:
                pos["avg_price"] = total_cost / pos["quantity"]

        elif side == "sell":

            pos["quantity"] -= quantity

            if pos["quantity"] == 0:
                pos["avg_price"] = 0.0

    # -------------------------------------------------
    # GET POSITIONS (SYNC)
    # -------------------------------------------------
    def get_positions(self):
        return [
            {
                "symbol": symbol,
                "quantity": data["quantity"],
                "avg_price": data["avg_price"]
            }
            for symbol, data in self.positions.items()
            if data["quantity"] != 0
        ]

    # -------------------------------------------------
    # CALCULATE UNREALIZED PNL
    # -------------------------------------------------
    def unrealized_pnl(self, prices: Dict[str, float]) -> float:

        pnl = 0.0

        for symbol, data in self.positions.items():

            if symbol not in prices:
                continue

            current_price = prices[symbol]
            quantity = data["quantity"]
            avg_price = data["avg_price"]

            pnl += (current_price - avg_price) * quantity

        return pnl

    # -------------------------------------------------
    # TOTAL EQUITY (SYNC)
    # -------------------------------------------------
    def total_equity(self, cash_balance: float, prices: Dict[str, float]) -> float:

        return cash_balance + self.unrealized_pnl(prices)

    def has_position(self, symbol):
        if symbol not in self.positions:
            return False
        return True
