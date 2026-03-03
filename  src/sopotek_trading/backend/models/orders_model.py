from sqlalchemy import (
    Column,
    String,
    Float,
    DateTime
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

from  order_states import OrderState

timeout_seconds = Column(Float, nullable=True)

class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String(64), primary_key=True)  # exchange_order_id

    trade_id = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False)

    symbol = Column(String(32), nullable=False)
    side = Column(String(16), nullable=False)

    requested_amount = Column(Float, nullable=False)
    filled_amount = Column(Float, default=0.0)

    avg_price = Column(Float, nullable=True)

    state = Column(OrderState.name, nullable=False)

    exchange_name = Column(String(32), nullable=False)

    raw_response = Column(JSON)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())