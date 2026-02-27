import ccxt
import uuid
import logging

logger = logging.getLogger(__name__)


class CCXTAdapter:

    def __init__(self, exchange_name, api_key, secret, password=None, sandbox=False):

        if not hasattr(ccxt, exchange_name):
            raise ValueError(f"Exchange {exchange_name} not supported")

        exchange_class = getattr(ccxt, exchange_name)

        config = {
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
            }
        }

        if password:
            config["password"] = password

        self.exchange = exchange_class(config)

        if sandbox and hasattr(self.exchange, "set_sandbox_mode"):
            self.exchange.set_sandbox_mode(True)

        # ❌ DO NOT load markets here
        # Lazy load instead

    # -----------------------------------------
    # Lazy Market Loader
    # -----------------------------------------
    def _ensure_markets(self):
        if not self.exchange.markets:
            self.exchange.load_markets()

    # -----------------------------------------
    # Place Order
    # -----------------------------------------
    def place_order(self, symbol, side, amount, order_type="market", price=None):

        self._ensure_markets()

        client_order_id = str(uuid.uuid4())

        order = self.exchange.create_order(
            symbol=symbol,
            type=order_type,
            side=side.lower(),
            amount=amount,
            price=price,
            params={"newClientOrderId": client_order_id}
        )

        return self._normalize_order(order)

    # -----------------------------------------
    # Cancel Order
    # -----------------------------------------
    def cancel_order(self, order_id, symbol):
        return self.exchange.cancel_order(order_id, symbol)

    # -----------------------------------------
    # Fetch Order
    # -----------------------------------------
    def fetch_order(self, order_id, symbol):
        return self._normalize_order(
            self.exchange.fetch_order(order_id, symbol)
        )

    # -----------------------------------------
    # Fetch Balance
    # -----------------------------------------
    def get_balance(self):
        return self.exchange.fetch_balance()

    # -----------------------------------------
    # Fetch Open Orders
    # -----------------------------------------
    def get_open_orders(self, symbol=None):
        return self.exchange.fetch_open_orders(symbol)

    # -----------------------------------------
    # Normalize
    # -----------------------------------------
    def _normalize_order(self, order):
        return {
            "id": order.get("id"),
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "type": order.get("type"),
            "amount": order.get("amount"),
            "filled": order.get("filled"),
            "remaining": order.get("remaining"),
            "price": order.get("price"),
            "status": order.get("status"),
            "timestamp": order.get("timestamp"),
            "raw": order,
        }