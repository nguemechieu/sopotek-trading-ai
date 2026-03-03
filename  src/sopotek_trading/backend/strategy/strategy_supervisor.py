import asyncio


class StrategySupervisor:

    def __init__(self, logger):
        self.logger = logger
        self.tasks = {}
        self.running = True
        debug_info = {
            "symbol": symbol,
            "index": current_index,
            "signal": signal,  # BUY / SELL / HOLD
            "rsi": current_rsi,
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "ml_probability": ml_prob,
            "risk_allowed": risk_ok,
            "position_size": size,
            "reason": "RSI oversold + EMA cross"
        }

    async def start_strategy(self, name, coro):
        async def wrapper():
            while self.running:
                try:
                    await coro()
                except Exception as ex:
                    self.logger.exception(f"Strategy {name} crashed. Restarting...",ex)
                    await asyncio.sleep(2)

        task = asyncio.create_task(wrapper())
        self.tasks[name] = task

    async def shutdown(self):
        self.running = False
        for task in self.tasks.values():
            task.cancel()