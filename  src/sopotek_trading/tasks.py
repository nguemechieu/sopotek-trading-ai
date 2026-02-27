from sopotek_trading.celery_app import celery_app

@celery_app.task
def execute_trade(symbol, side, quantity):
    print(f"Executing trade {symbol} {side} {quantity}")