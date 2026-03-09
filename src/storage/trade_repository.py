import sqlalchemy
from datetime import datetime

from storage.database import Base, SessionLocal


class Trade(Base):
    __tablename__ = "trades"

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, index=True)

    symbol = sqlalchemy.Column(sqlalchemy.String)
    side = sqlalchemy.Column(sqlalchemy.String)

    quantity = sqlalchemy.Column(sqlalchemy.Float)
    price = sqlalchemy.Column(sqlalchemy.Float)

    timestamp = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.utcnow)


class TradeRepository:

    def __init__(self):
        self.session = SessionLocal()

    # ===================================
    # SAVE TRADE
    # ===================================

    def save_trade(self, symbol, side, quantity, price):
        trade = Trade(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price
        )

        self.session.add(trade)

        self.session.commit()

    # ===================================
    # GET TRADES
    # ===================================

    def get_trades(self):
        return self.session.query(Trade).all()

    # ===================================
    # GET TRADES BY SYMBOL
    # ===================================

    def get_by_symbol(self, symbol):
        return self.session.query(Trade).filter(
            Trade.symbol == symbol
        ).all()
