# brokers/base.py

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class BaseBroker(ABC):
    """
    Unified broker interface.
    All brokers MUST normalize outputs to these formats.
    """

    # -------------------------------------------------
    # CONNECTION
    # -------------------------------------------------

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection to broker."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Gracefully close broker connection."""
        pass

    # -------------------------------------------------
    # ACCOUNT
    # -------------------------------------------------

    @abstractmethod
    async def fetch_balance(self) -> Dict:
        """
        Must return:
        {
            "equity": float,
            "free": float,
            "used": float,
            "currency": str
        }
        """
        pass

    @abstractmethod
    async def fetch_positions(self) -> List[Dict]:
        """
        Must return list of:
        {
            "symbol": str,
            "side": "long" | "short",
            "size": float,
            "entry_price": float,
            "unrealized_pnl": float
        }
        """
        pass

    # -------------------------------------------------
    # MARKET DATA
    # -------------------------------------------------

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> Dict:
        """
        Must return:
        {
            "bid": float,
            "ask": float,
            "last": Optional[float]
        }
        """
        pass

    @abstractmethod
    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Dict:
        """Return OHLCV candles in unified format."""
        pass

    # -------------------------------------------------
    # EXECUTION
    # -------------------------------------------------

    @abstractmethod
    async def create_order(
            self,
            symbol: str,
            side: str,
            order_type: str,
            amount: float,
            price: Optional[float] = None,
    ) -> Dict:
        """
        Must return normalized order:

        {
            "id": str,
            "symbol": str,
            "side": str,
            "status": str,
            "filled": float,
            "price": float
        }
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """Cancel order and return normalized response."""
        pass

    # -------------------------------------------------
    # PERFORMANCE
    # -------------------------------------------------

    @abstractmethod
    async def fetch_realized_pnl(self) -> float:
        """Return total realized PnL."""
        pass

    @abstractmethod
    async def fetch_unrealized_pnl(self) -> float:
        """Return total unrealized PnL."""
        pass


    @abstractmethod
    async def fetch_order_book(self, symbol: str) -> Dict:
        """Return order book data."""
        pass


    @abstractmethod
    async def fetch_symbols(self) -> Dict:

        """Return symbols """
        pass