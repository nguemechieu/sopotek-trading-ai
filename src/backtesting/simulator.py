class Simulator:
    def __init__(self, initial_balance=10000):
        self.initial_balance = float(initial_balance)
        self.balance = float(initial_balance)
        self.position_qty = 0.0
        self.entry_price = None
        self.symbol = None
        self.trades = []

    def _candle_value(self, candle, key, default=None):
        if hasattr(candle, "get"):
            value = candle.get(key, default)
            if value is not None:
                return value
        try:
            return candle[key]
        except Exception:
            return default

    def current_equity(self, market_price=None):
        if self.position_qty > 0 and market_price is not None and self.entry_price is not None:
            return self.balance + (self.position_qty * market_price)
        return self.balance

    def execute(self, signal, candle, symbol="BACKTEST"):
        if not isinstance(signal, dict):
            return None

        side = str(signal.get("side", "")).lower()
        if side not in {"buy", "sell"}:
            return None

        amount = float(signal.get("amount", signal.get("size", 1)) or 0)
        if amount <= 0:
            return None

        price = float(self._candle_value(candle, "close", 0) or 0)
        timestamp = self._candle_value(candle, "timestamp")
        if price <= 0:
            return None

        if side == "buy":
            if self.position_qty > 0:
                return None

            affordable_amount = min(amount, self.balance / price)
            if affordable_amount <= 0:
                return None

            self.balance -= affordable_amount * price
            self.position_qty = affordable_amount
            self.entry_price = price
            self.symbol = symbol

            trade = {
                "timestamp": timestamp,
                "symbol": symbol,
                "side": "BUY",
                "type": "ENTRY",
                "price": price,
                "amount": affordable_amount,
                "pnl": 0.0,
                "equity": self.current_equity(price),
                "reason": signal.get("reason", ""),
            }
            self.trades.append(trade)
            return trade

        if self.position_qty <= 0:
            return None

        amount = min(amount, self.position_qty)
        pnl = (price - float(self.entry_price or price)) * amount
        self.balance += amount * price
        self.position_qty -= amount

        trade = {
            "timestamp": timestamp,
            "symbol": symbol,
            "side": "SELL",
            "type": "EXIT",
            "price": price,
            "amount": amount,
            "pnl": pnl,
            "equity": self.current_equity(price),
            "reason": signal.get("reason", ""),
        }

        if self.position_qty <= 0:
            self.position_qty = 0.0
            self.entry_price = None
            self.symbol = None

        self.trades.append(trade)
        return trade

    def close_open_position(self, candle, symbol="BACKTEST", reason="end_of_test"):
        if self.position_qty <= 0:
            return None

        return self.execute(
            {"side": "sell", "amount": self.position_qty, "reason": reason},
            candle,
            symbol=symbol,
        )
