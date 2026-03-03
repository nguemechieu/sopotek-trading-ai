import logging

logger = logging.getLogger(__name__)


class InstitutionalRiskEngine:

    def __init__(
            self,
            account_equity: float,
            max_risk_per_trade: float = 0.01,
            max_portfolio_risk: float = 0.05,
            max_daily_drawdown: float = 0.03,
            max_position_size_pct: float = 0.20,
            max_gross_exposure_pct: float = 1.5,
    ):
        self.account_equity = account_equity
        self.max_risk_per_trade = max_risk_per_trade
        self.max_portfolio_risk = max_portfolio_risk
        self.max_daily_drawdown = max_daily_drawdown
        self.max_position_size_pct = max_position_size_pct
        self.max_gross_exposure_pct = max_gross_exposure_pct

        self.daily_loss = 0

    # -------------------------------------------------
    # POSITION SIZING
    # -------------------------------------------------
    def position_size(self, entry_price, stop_price, confidence=1.0, volatility=None):
        """
        Volatility-adjusted risk sizing with confidence scaling.
        """

        risk_capital = self.account_equity * self.max_risk_per_trade

        stop_distance = abs(entry_price - stop_price)

        if stop_distance <= 0:
            return 0

        # Base position size
        base_size = risk_capital / stop_distance

        # Volatility scaling (optional)
        if volatility:
            base_size = base_size / max(volatility, 1e-8)

        # Confidence scaling (0–1)
        adjusted_size = base_size * confidence

        # Hard cap on single position size
        max_position_value = self.account_equity * self.max_position_size_pct
        max_size_allowed = max_position_value / entry_price

        final_size = min(adjusted_size, max_size_allowed)

        return max(final_size, 0)

    # -------------------------------------------------
    # TRADE VALIDATION
    # -------------------------------------------------
    def validate_trade(self, signal, portfolio):
        """
        Checks exposure, concentration, and risk budget.
        """

        entry = signal["entry"]
        stop = signal["stop"]

        # 1️⃣ Per-trade risk check
        stop_distance = abs(entry - stop)
        if stop_distance <= 0:
            return False, "Invalid stop distance"

        potential_loss = stop_distance
        max_allowed_loss = self.account_equity * self.max_risk_per_trade

        if potential_loss > max_allowed_loss:
            return False, "Trade exceeds max per-trade risk"

        # 2️⃣ Portfolio exposure check
        gross_exposure = self._gross_exposure(portfolio)

        if gross_exposure > self.account_equity * self.max_gross_exposure_pct:
            return False, "Gross exposure limit exceeded"

        return True, "Approved"

    # -------------------------------------------------
    # PORTFOLIO METRICS
    # -------------------------------------------------
    def _gross_exposure(self, portfolio):
        return sum(abs(p["value"]) for p in portfolio)

    def net_exposure(self, portfolio):
        return sum(p["value"] for p in portfolio)

    # -------------------------------------------------
    # DAILY DRAWDOWN CONTROL
    # -------------------------------------------------
    def update_daily_pnl(self, pnl):
        self.daily_loss += pnl

        if self.daily_loss < -self.account_equity * self.max_daily_drawdown:
            logger.critical("Daily drawdown breached.")
            return False

        return True

    # -------------------------------------------------
    # KELLY FRACTION (Optional Institutional Scaling)
    # -------------------------------------------------
    def kelly_fraction(self, win_rate, win_loss_ratio):
        """
        Kelly formula:
        f = (bp - q) / b
        """
        b = win_loss_ratio
        p = win_rate
        q = 1 - p

        kelly = (b * p - q) / b
        return max(min(kelly, 1), 0)