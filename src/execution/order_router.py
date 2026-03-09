class OrderRouter:

    def __init__(self, broker):

        self.broker = broker

    async def route(self, order):

        symbol = order["symbol"]
        side = order["side"]
        amount = order["amount"]

        order_type = order.get("type", "market")

        if order_type == "market":

            execution = await self.broker.create_order(
                symbol=symbol,
                side=side,
                amount=amount,
                type="market"
            )

        else:

            price = order.get("price")

            execution = await self.broker.create_order(
                symbol=symbol,
                side=side,
                amount=amount,
                price=price,
                type="limit"
            )

        return execution
