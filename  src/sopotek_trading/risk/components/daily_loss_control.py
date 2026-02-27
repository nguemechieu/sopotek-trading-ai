class DailyLossControl:

    def __init__(self, daily_limit):
        self.daily_limit = daily_limit

    def check(self, daily_pnl, equity):
        return abs(daily_pnl) <= equity * self.daily_limit