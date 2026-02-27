import uuid
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class OrderState(str, Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    RECONCILED = "RECONCILED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class ExecutionManager:

    def __init__(self, broker, risk_engine, portfolio):
        self.order_repo = None
        self.broker = broker
        self.risk_engine = risk_engine
        self.portfolio = portfolio
        self.orders = {}  # order_id → ManagedOrder

    # -------------------------------------------------
    # Submit Trade
    # -------------------------------------------------
    def execute_trade(self, user_id, symbol, side, amount, order_type="market"):

     trade_id = str(uuid.uuid4())

    # ---- TEMPORARY RISK STATE ----
     risk_state = {
        "equity": 100000,
        "daily_pnl": 0,
        "positions": {},
        "max_correlation": 0,
        "forecast_vol": 0
    }

     if not self.risk_engine.validate(risk_state):
        print("Risk validation failed")
        return None

     order = self.broker.place_order(
        symbol=symbol,
        side=side,
        amount=amount,
        order_type=order_type
    )

     return order
    # -------------------------------------------------
    # Reconcile Order State
    # -------------------------------------------------
    def reconcile(self, exchange_order_id, symbol):

        if exchange_order_id not in self.orders:
            return None

        order = self.orders[exchange_order_id]

        exchange_data = self.broker.fetch_order(exchange_order_id, symbol)

        status = exchange_data["status"]
        filled = float(exchange_data["filled"] or 0)

        if status == "canceled":
            order.transition(OrderState.CANCELED)
            return order

        if 0 < filled < order.amount:
            order.filled = filled
            order.transition(OrderState.PARTIALLY_FILLED)

        if status == "closed":
            order.filled = filled
            order.avg_price = exchange_data["price"]
            order.transition(OrderState.FILLED)

            self._finalize(order)

        return order

    # -------------------------------------------------
    # Finalize
    # -------------------------------------------------
    def _finalize(self, order):

        if order.state != OrderState.FILLED:
            return

        # Update portfolio
        self.portfolio.update_position(
            symbol=order.symbol,
            side=order.side,
            quantity=order.filled,
            price=order.avg_price
        )

        order.transition(OrderState.RECONCILED)

        logger.info(f"Order {order.exchange_order_id} reconciled")

    # -------------------------------------------------
    # Archive
    # -------------------------------------------------
    def archive(self, exchange_order_id):

        if exchange_order_id in self.orders:
            order = self.orders[exchange_order_id]
            order.transition(OrderState.ARCHIVED)