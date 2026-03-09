import asyncio
import numpy as np


class SmartExecution:

    def __init__(self, broker):

        self.broker = broker

    # ========================================
    # SIMPLE MARKET ORDER
    # ========================================

    async def market(self, symbol, side, amount):

        return await self.broker.create_order(
            symbol=symbol,
            side=side,
            amount=amount,
            type="market"
        )

    # ========================================
    # LIMIT ORDER
    # ========================================

    async def limit(self, symbol, side, amount, price):

        return await self.broker.create_order(
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            type="limit"
        )

    # ========================================
    # TWAP EXECUTION
    # ========================================

    async def twap(self, symbol, side, amount, duration=60, slices=5):

        qty_per_slice = amount / slices
        interval = duration / slices

        results = []

        for _ in range(slices):
            order = await self.market(symbol, side, qty_per_slice)

            results.append(order)

            await asyncio.sleep(interval)

        return results

    # ========================================
    # VWAP EXECUTION
    # ========================================

    async def vwap(self, symbol, side, amount, market_volumes):

        total_volume = sum(market_volumes)

        results = []

        for v in market_volumes:
            weight = v / total_volume

            qty = amount * weight

            order = await self.market(symbol, side, qty)

            results.append(order)

        return results

    # ========================================
    # ICEBERG ORDER
    # ========================================

    async def iceberg(self, symbol, side, amount, visible_size):

        remaining = amount

        results = []

        while remaining > 0:
            qty = min(visible_size, remaining)

            order = await self.limit(symbol, side, qty)

            results.append(order)

            remaining -= qty

            await asyncio.sleep(2)

        return results

    # ========================================
    # SMART LIMIT
    # ========================================

    async def smart_limit(self, symbol, side, amount, price, retries=5):

        for _ in range(retries):

            order = await self.limit(symbol, side, amount, price)

            await asyncio.sleep(2)

            status = await self.broker.fetch_order(order["id"], symbol)

            if status["status"] == "closed":
                return order

            await self.broker.cancel_order(order["id"], symbol)

        return None

    # ========================================
    # MARKET SWEEP
    # ========================================

    async def market_sweep(self, symbol, side, amount):

        orderbook = await self.broker.fetch_order_book(symbol)

        remaining = amount

        results = []

        levels = orderbook["asks"] if side == "BUY" else orderbook["bids"]

        for price, volume in levels:

            qty = min(volume, remaining)

            order = await self.limit(symbol, side, qty, price)

            results.append(order)

            remaining -= qty

            if remaining <= 0:
                break

        return results

    # ========================================
    # POV EXECUTION
    # ========================================

    async def pov(self, symbol, side, amount, participation_rate=0.1):

        traded = 0

        results = []

        while traded < amount:
            ticker = await self.broker.fetch_ticker(symbol)

            market_volume = ticker.get("baseVolume", 0)

            qty = market_volume * participation_rate

            qty = min(qty, amount - traded)

            order = await self.market(symbol, side, qty)

            results.append(order)

            traded += qty

            await asyncio.sleep(5)

        return results

    # ========================================
    # SNIPER ORDER
    # ========================================

    async def sniper(self, symbol, side, amount, trigger_price):

        while True:

            ticker = await self.broker.fetch_ticker(symbol)

            price = ticker["last"]

            if side == "BUY" and price <= trigger_price:
                return await self.market(symbol, side, amount)

            if side == "SELL" and price >= trigger_price:
                return await self.market(symbol, side, amount)

            await asyncio.sleep(0.5)

    # ========================================
    # STOP ORDER
    # ========================================

    async def stop(self, symbol, side, amount, stop_price):

        while True:

            ticker = await self.broker.fetch_ticker(symbol)

            price = ticker["last"]

            if side == "BUY" and price >= stop_price:
                return await self.market(symbol, side, amount)

            if side == "SELL" and price <= stop_price:
                return await self.market(symbol, side, amount)

            await asyncio.sleep(0.5)
