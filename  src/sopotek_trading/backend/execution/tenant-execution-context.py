import uuid
import datetime
import logging

logger = logging.getLogger(__name__)


class TenantExecutionContext:

    def __init__(self, user_id, broker, execution_manager, risk_engine, portfolio):
        self.user_id = user_id
        self.broker = broker
        self.execution_manager = execution_manager
        self.risk_engine = risk_engine
        self.portfolio = portfolio

    # -------------------------------------------------
    # Submit Trade
    # -------------------------------------------------
    def submit_trade(self, symbol, side, quantity, strategy_id):

        trade_id = str(uuid.uuid4())
        timestamp = datetime.datetime.utcnow()

        log = {
            "trade_id": trade_id,
            "user_id": self.user_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "strategy_id": strategy_id,
            "timestamp": timestamp
        }

        logger.info(f"[{self.user_id}] Trade request: {log}")

        return self.execution_manager.execute_trade(
            user_id=self.user_id,
            symbol=symbol,
            side=side,
            amount=quantity
        )

    # -------------------------------------------------
    # Fetch Account Info
    # -------------------------------------------------
    def get_account(self):
        return self.broker.get_balance()

    # -------------------------------------------------
    # Fetch Open Orders
    # -------------------------------------------------
    def get_open_orders(self):
        return self.broker.get_open_orders()

    # -------------------------------------------------
    # Cancel Order
    # -------------------------------------------------
    def cancel_order(self, order_id, symbol):
        return self.broker.cancel_order(order_id, symbol)