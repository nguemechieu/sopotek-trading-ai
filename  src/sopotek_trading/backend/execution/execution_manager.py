import asyncio


class ExecutionManager:

    def __init__(self, broker, logger):
        self.broker = broker
        self.logger = logger
        self.queue = asyncio.Queue()
        self.running = False
        self.worker_task = None

    # -------------------------------------------------
    # START
    # -------------------------------------------------

    async def start(self):
        if self.running:
            return

        self.running = True
        self.worker_task = asyncio.create_task(self._worker())

    # -------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------

    async def execute_trade(
            self,
            user_id,
            symbol,
            side,
            amount,
            order_type,
            price,
            stop_loss=None,
            take_profit=None,
    ):

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        order_request = {
            "user_id": user_id,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "order_type": order_type,
            "price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "future": future,
        }

        await self.queue.put(order_request)

        return await future

    # -------------------------------------------------
    # WORKER
    # -------------------------------------------------

    async def _worker(self):

        future=None
        while self.running:

            try:
                order = await self.queue.get()

                if order is None:
                    self.queue.task_done()
                    break

                future = order.pop("future")

                result = await self.broker.create_order(
                    symbol=order["symbol"],
                    side=order["side"],
                    order_type=order["order_type"],
                    amount=order["amount"],
                    price=order["price"],
                    stop_loss=order.get("stop_loss"),
                    take_profit=order.get("take_profit"),
                )

                if not future.done():
                    future.set_result(result)

                self.logger.info(
                    f"Order executed: {order['symbol']} {order['side']}"
                )

            except Exception as e:
                self.logger.exception("Execution failure")

                if "future" in locals() and not future.done():
                    future.set_exception(e)

            finally:
                self.queue.task_done()

    # -------------------------------------------------
    # SHUTDOWN
    # -------------------------------------------------

    async def shutdown(self):

        self.running = False

        await self.queue.put(None)

        if self.worker_task:
            await self.worker_task