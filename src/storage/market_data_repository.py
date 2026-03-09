from sqlalchemy import Column, Integer, String, Float, DateTime

from storage.database import Base, SessionLocal


class Candle(Base):
    __tablename__ = "candles"

    id = Column(Integer, primary_key=True)

    symbol = Column(String)

    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)

    volume = Column(Float)

    timestamp = Column(DateTime)


class MarketDataRepository:

    def __init__(self):
        self.session = SessionLocal()

    # ===================================
    # SAVE CANDLE
    # ===================================

    def save_candle(self, candle):
        c = Candle(**candle)

        self.session.add(c)

        self.session.commit()

    # ===================================
    # GET CANDLES
    # ===================================

    def get_candles(self, symbol):
        return self.session.query(Candle).filter(
            Candle.symbol == symbol
        ).all()
