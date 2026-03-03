from sqlalchemy.orm import Session

from sopotek_trading.backend.models.order_states import OrderState
from sopotek_trading.backend.models.orders_model import OrderModel


class OrderRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, order_data: dict):
        order = OrderModel(**order_data)
        self.db.add(order)
        self.db.commit()
        return order

    def update_state(self, order_id, new_state, filled=None, avg_price=None, raw=None):
        order = self.db.query(OrderModel).filter_by(id=order_id).first()

        if not order:
            return None

        order.state = new_state

        if filled is not None:
            order.filled_amount = filled

        if avg_price is not None:
            order.avg_price = avg_price

        if raw is not None:
            order.raw_response = raw

        self.db.commit()
        return order

    def get(self, order_id):
        return self.db.query(OrderModel).filter_by(id=order_id).first()

    def get_active_orders(self):
        return (
            self.db.query(OrderModel)
            .filter(OrderModel.state.in_([
                OrderState.SUBMITTED,
                OrderState.ACKNOWLEDGED,
                OrderState.PARTIALLY_FILLED
            ]))
            .all()
        )
