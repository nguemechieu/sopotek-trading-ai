class RiskEngine:

    def __init__(
            self,
            account_equity,
            max_portfolio_risk=0.1,
            max_risk_per_trade=0.02,
            max_position_size_pct=0.1,
            max_gross_exposure_pct=2.0
    ):

        self.account_equity = account_equity

        self.max_portfolio_risk = max_portfolio_risk
        self.max_risk_per_trade = max_risk_per_trade
        self.max_position_size_pct = max_position_size_pct
        self.max_gross_exposure_pct = max_gross_exposure_pct

    # =====================================
    # VALIDATE TRADE
    # =====================================

    def validate_trade(self, price, quantity):

        trade_value = price * quantity

        # max position size
        if trade_value > self.account_equity * self.max_position_size_pct:
            return False, "Position size too large"

        return True, "Approved"

    # =====================================
    # POSITION SIZE
    # =====================================

    def position_size(self, entry_price, stop_price):

        risk_amount = self.account_equity * self.max_risk_per_trade

        risk_per_unit = abs(entry_price - stop_price)

        if risk_per_unit == 0:
            return 0

        size = risk_amount / risk_per_unit

        return size
