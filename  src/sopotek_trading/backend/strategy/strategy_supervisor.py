import asyncio


class StrategySupervisor:

    def __init__(self, logger):
        self.logger = logger
        self.tasks = {}
        self.running = True

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