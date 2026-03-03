import asyncio
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class RiskEngine:

    def __init__(
            self,broker,
            account_equity: float=0.00,
            max_risk_per_trade: float = 0.01,
            max_daily_drawdown: float = 0.03,
            max_position_size_pct: float = 0.20,
            max_gross_exposure_pct: float = 1.5,
    ):

        if not isinstance(account_equity, (int, float)):
            raise TypeError("account_equity must be a float")
        self.broker = broker

        self.account_equity = account_equity
        self.max_risk_per_trade = max_risk_per_trade
        self.max_daily_drawdown = max_daily_drawdown
        self.max_position_size_pct = max_position_size_pct
        self.max_gross_exposure_pct = max_gross_exposure_pct

        self.daily_pnl = 0.0

    # -------------------------------------------------
    # POSITION SIZING
    # -------------------------------------------------
    def position_size(
            self,
            entry_price: float,
            stop_price: float,
            confidence: float = 1.0,
            volatility: float = None,
    ) -> float:

        if self.account_equity <= 0:
            return 0.0

        stop_distance = abs(entry_price - stop_price)
        if stop_distance <= 0:
            return 0.0

        # Capital at risk
        risk_capital = self.account_equity * self.max_risk_per_trade

        base_size = risk_capital / stop_distance

        # Optional volatility scaling
        if volatility and volatility > 0:
            base_size /= volatility

        # Confidence scaling
        confidence = max(0.0, min(confidence, 1.0))
        adjusted_size = base_size * confidence

        # Position cap
        max_position_value = self.account_equity * self.max_position_size_pct
        max_size_allowed = max_position_value / entry_price

        final_size = min(adjusted_size, max_size_allowed)

        return max(float(final_size), 0.0)

    # -------------------------------------------------
    # PRE-SIZE VALIDATION
    # -------------------------------------------------
    def validate_trade(self, signal: Dict, portfolio: List[Dict]):

        # Defensive: detect coroutine contamination
        if asyncio.iscoroutine(self.account_equity):
            raise TypeError(
                "RiskEngine.account_equity is coroutine. "
                "You forgot to await broker.total_equity()"
            )

        if signal is None or len(signal.values()) == 0:
            logger.critical("RiskEngine.validate_trade received None.")
            return False, "None"

        entry = signal.get("entry_price",0)
        stop = signal.get("stop_price",0)


        if entry is None or stop is None:
            return False, "Missing entry or stop"

        if entry <= 0 or stop <= 0:
            return False, "Invalid price"

        if entry == stop:
            return False, "Stop distance zero"

        gross_exposure = self._gross_exposure(portfolio)

        if gross_exposure > self.account_equity * self.max_gross_exposure_pct:
            return False, "Gross exposure exceeded"
        return True, "Approved"

    # -------------------------------------------------
    # POST-SIZE IMPACT VALIDATION
    # -------------------------------------------------
    def validate_position_impact(
            self,
            signal: Dict,
            portfolio: List[Dict],
            size: float,
    ):

        projected_value = signal["entry_price"] * size
        gross_exposure = self._gross_exposure(portfolio)
        projected_gross = gross_exposure + abs(projected_value)

        if projected_gross > self.account_equity * self.max_gross_exposure_pct:
            return False, "Projected gross exposure too high"
        stop_distance = abs(signal["entry_price"] - signal["stop_price"])
        potential_loss = stop_distance * size

        if potential_loss > self.account_equity * self.max_risk_per_trade:
            return False, "Projected trade risk too large"

        return True, "Approved"

    # -------------------------------------------------
    # EXPOSURE METRICS
    # -------------------------------------------------
    def _gross_exposure(self, portfolio: List[Dict]) -> float:
        return sum(
            abs(p.get("quantity", 0.0) * p.get("avg_price", 0.0))
            for p in portfolio
        )

    def net_exposure(self, portfolio: List[Dict]) -> float:
        return sum(
            p.get("quantity", 0.0) * p.get("avg_price", 0.0)
            for p in portfolio
        )

    # -------------------------------------------------
    # DAILY DRAWDOWN CONTROL
    # -------------------------------------------------
    def update_daily_pnl(self, pnl: float) -> bool:
        self.daily_pnl += pnl

        if self.daily_pnl < -self.account_equity * self.max_daily_drawdown:
            logger.critical("Daily drawdown limit breached.")
            return False

        return True

    # -------------------------------------------------
    # EQUITY UPDATE
    # -------------------------------------------------
    async def update_equity(self, new_equity: float):

        if asyncio.iscoroutine(new_equity):
            raise TypeError(
                "update_equity received coroutine. "
                "You forgot to await broker.total_equity()."
            )

        if not isinstance(new_equity, (int, float)):
            raise TypeError("Equity must be numeric")

        self.account_equity = float(new_equity)

    async def get_lot_size(
            self,
            symbol: str,
            entry_price: float,
            stop_price: float,
            confidence: float = 1.0,
            volatility: float = None,
    ):
        """
        Calculate institutional position size safely.
        """

        try:
        # 1️⃣ Get current equity
         balance = await self.broker.get_balance()
         equity = balance.get("total", ohlcv).get("USDT", ohlcv)

         if equity <= 0:
            return 0.0

        # 2️⃣ Update risk engine equity
         await self.update_equity(float(equity))

        # 3️⃣ Use RiskEngine position sizing
         size = self.position_size(
            entry_price=entry_price,
            stop_price=stop_price,
            confidence=confidence,
            volatility=volatility,
        )

         if size <= 0:
            return 0.0

        # 4️⃣ Exchange precision enforcement
         size = float(self.broker.exchange.amount_to_precision(symbol, size))

         return size

        except Exception:
         logger.exception("Lot size calculation failed")
         return 0.0