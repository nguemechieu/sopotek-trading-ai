from datetime import date

class DailyLossLimiter:

    def __init__(self, max_daily_loss):
        self.max_daily_loss = max_daily_loss
        self.current_day = date.today()
        self.daily_pnl = 0

    def update(self, trade_pnl):
        if date.today() != self.current_day:
            self.current_day = date.today()
            self.daily_pnl = 0

        self.daily_pnl += trade_pnl

        if self.daily_pnl <= -abs(self.max_daily_loss):
            return False

        return True