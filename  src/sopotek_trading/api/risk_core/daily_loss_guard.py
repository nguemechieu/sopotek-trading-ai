from datetime import date

class DailyLossGuard:

    def __init__(self, max_daily_loss):
        self.limit = max_daily_loss
        self.current_day = date.today()
        self.pnl_today = 0

    def update(self, pnl):
        if date.today() != self.current_day:
            self.current_day = date.today()
            self.pnl_today = 0

        self.pnl_today += pnl

        if self.pnl_today <= -abs(self.limit):
            return False

        return True