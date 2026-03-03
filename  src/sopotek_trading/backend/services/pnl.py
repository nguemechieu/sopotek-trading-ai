class PnLService:

    @staticmethod
    def calculate_unrealized(position, current_price):
        return (current_price - position.average_price) * position.quantity

    @staticmethod
    def calculate_realized(entry_price, exit_price, quantity):
        return (exit_price - entry_price) * quantity