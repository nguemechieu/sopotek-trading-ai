import datetime
from datetime import timedelta
from celery import shared_task
import logging

from sopotek_trading.models.database import SessionLocal
from sopotek_trading.models.order_states import OrderState
from sopotek_trading.repositories.order_repository import OrderRepository
from sopotek_trading.executions.broker_factory import BrokerFactory

logger = logging.getLogger(__name__)


# -------------------------------------------------
# Secure Key Decryption (Stub)
# -------------------------------------------------
def decrypt_api_key(user_id):
    # TODO: integrate real vault / encryption
    raise NotImplementedError("Vault integration required")


def decrypt_secret(user_id):
    # TODO: integrate real vault / encryption
    raise NotImplementedError("Vault integration required")


# -------------------------------------------------
# Stale Order Detection
# -------------------------------------------------
def is_stale(order):
    if not order.timeout_seconds:
        return False

    expiration_time = order.created_at + timedelta(seconds=order.timeout_seconds)
    return datetime.datetime.utcnow() > expiration_time


# -------------------------------------------------
# Reconciliation Task
# -------------------------------------------------
@shared_task(bind=True, max_retries=3)
def reconcile_orders(self):

    db = SessionLocal()
    repo = OrderRepository(db)

    try:
        active_orders = repo.get_active_orders()

        for order in active_orders:

            try:
                broker = BrokerFactory.create(
                    exchange_name=order.exchange_name,
                    api_key=decrypt_api_key(order.user_id),
                    secret=decrypt_secret(order.user_id)
                )

                exchange_data = BrokerFactory.safe_execute(
                    lambda: broker.fetch_order(order.id, order.symbol)
                )

                status = exchange_data["status"]
                filled = float(exchange_data.get("filled", 0))

                # -------------------------------------------------
                # Incremental Fill Handling
                # -------------------------------------------------
                incremental_fill = filled - (order.processed_fill or 0)

                if incremental_fill > 0:

                    # TODO: call portfolio.update_fill() here

                    repo.update_state(
                        order.id,
                        OrderState.PARTIALLY_FILLED if filled < order.requested_amount else OrderState.FILLED,
                        filled=filled,
                        avg_price=exchange_data.get("price"),
                        raw=exchange_data
                    )

                    order.processed_fill = filled

                # -------------------------------------------------
                # Finalized
                # -------------------------------------------------
                if status == "closed":
                    repo.update_state(
                        order.id,
                        OrderState.FILLED,
                        filled=filled,
                        avg_price=exchange_data.get("price"),
                        raw=exchange_data
                    )

                    logger.info(f"[RECONCILE] Order {order.id} filled")

                # -------------------------------------------------
                # Canceled
                # -------------------------------------------------
                elif status == "canceled":
                    repo.update_state(
                        order.id,
                        OrderState.CANCELED,
                        raw=exchange_data
                    )

                # -------------------------------------------------
                # Stale Auto-Cancel
                # -------------------------------------------------
                elif is_stale(order):
                    try:
                        BrokerFactory.safe_execute(
                            lambda: broker.cancel_order(order.id, order.symbol)
                        )

                        repo.update_state(
                            order.id,
                            OrderState.CANCELED
                        )

                        logger.warning(f"[TIMEOUT] Order {order.id} auto-canceled")

                    except Exception as cancel_error:
                        logger.error(f"Cancel failed for {order.id}: {str(cancel_error)}")

            except Exception as e:
                logger.error(f"Reconciliation error for {order.id}: {str(e)}")
                db.rollback()

    finally:
        db.close()