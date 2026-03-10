import asyncio
import logging
import time

from event_bus.event import Event
from event_bus.event_types import EventType


class ExecutionManager:

    def __init__(self, broker, event_bus, router):

        self.broker = broker
        self.bus = event_bus
        self.router = router
        self.logger = logging.getLogger("ExecutionManager")

        self.running = False
        self._symbol_cooldowns = {}
        self._execution_lock = asyncio.Lock()
        self._balance_buffer = 0.98

        # Subscribe to ORDER events
        self.bus.subscribe(EventType.ORDER, self.on_order)

    async def start(self):

        self.running = True

    async def stop(self):

        self.running = False

    async def on_order(self, event):

        if not self.running:
            return

        try:
            await self.execute(event.data)

        except Exception as e:

            print("Execution error:", e)

    def _cooldown_remaining(self, symbol):
        expires_at = self._symbol_cooldowns.get(symbol)
        if expires_at is None:
            return 0.0

        remaining = expires_at - time.monotonic()
        if remaining <= 0:
            self._symbol_cooldowns.pop(symbol, None)
            return 0.0

        return remaining

    def _set_cooldown(self, symbol, seconds, reason):
        self._symbol_cooldowns[symbol] = time.monotonic() + seconds
        self.logger.warning(
            "Skipping %s for %.0fs: %s",
            symbol,
            seconds,
            reason,
        )

    async def _fetch_reference_price(self, symbol, side, requested_price=None):
        if requested_price is not None:
            return float(requested_price)

        if not hasattr(self.broker, "fetch_ticker"):
            return None

        ticker = await self.broker.fetch_ticker(symbol)
        if not isinstance(ticker, dict):
            return None

        if str(side).lower() == "buy":
            candidates = ("ask", "askPrice", "price", "last", "close")
        else:
            candidates = ("bid", "bidPrice", "price", "last", "close")

        for key in candidates:
            value = ticker.get(key)
            if value is None:
                continue
            try:
                price = float(value)
            except (TypeError, ValueError):
                continue
            if price > 0:
                return price

        return None

    def _extract_free_balances(self, balance):
        if not isinstance(balance, dict):
            return {}

        if isinstance(balance.get("free"), dict):
            return balance["free"]

        skip = {"free", "used", "total", "info", "raw", "equity", "cash", "currency"}
        return {k: v for k, v in balance.items() if k not in skip}

    def _get_market(self, symbol):
        exchange = getattr(self.broker, "exchange", None)
        markets = getattr(exchange, "markets", None)
        if isinstance(markets, dict):
            return markets.get(symbol)
        return None

    def _apply_amount_precision(self, symbol, amount):
        exchange = getattr(self.broker, "exchange", None)
        if exchange and hasattr(exchange, "amount_to_precision"):
            try:
                return float(exchange.amount_to_precision(symbol, amount))
            except Exception:
                pass

        return float(amount)

    async def _prepare_order(self, order):
        symbol = order["symbol"]
        side = order["side"]

        if self._cooldown_remaining(symbol) > 0:
            return None

        market = self._get_market(symbol)
        if market is not None and market.get("active") is False:
            self._set_cooldown(symbol, 300, "market is inactive")
            return None

        price = await self._fetch_reference_price(symbol, side, order.get("price"))

        amount = float(order["amount"])
        base_currency, quote_currency = (symbol.split("/", 1) + [None])[:2]

        balance = {}
        if hasattr(self.broker, "fetch_balance"):
            try:
                balance = self._extract_free_balances(await self.broker.fetch_balance())
            except Exception as exc:
                self.logger.debug("Balance fetch failed for %s: %s", symbol, exc)

        available_quote = None
        available_base = None
        if quote_currency:
            available_quote = float(balance.get(quote_currency, 0) or 0)
        if base_currency:
            available_base = float(balance.get(base_currency, 0) or 0)

        if side == "buy" and price and available_quote is not None:
            spendable_quote = available_quote * self._balance_buffer
            if spendable_quote <= 0:
                self._set_cooldown(symbol, 120, f"no available {quote_currency} balance")
                return None
            affordable_amount = spendable_quote / price
            amount = min(amount, affordable_amount)

        if side == "sell" and available_base is not None:
            liquid_base = available_base * self._balance_buffer
            if liquid_base <= 0:
                self._set_cooldown(symbol, 120, f"no available {base_currency} balance")
                return None
            amount = min(amount, liquid_base)

        limits = market.get("limits", {}) if isinstance(market, dict) else {}
        min_amount = ((limits.get("amount") or {}).get("min"))
        min_cost = ((limits.get("cost") or {}).get("min"))

        if price and min_cost:
            min_cost_amount = float(min_cost) / price
            amount = max(amount, min_cost_amount)

        if min_amount:
            amount = max(amount, float(min_amount))

        amount = self._apply_amount_precision(symbol, amount)

        if amount <= 0:
            self._set_cooldown(symbol, 120, "computed order amount is zero")
            return None

        if (
            side == "buy"
            and price
            and available_quote is not None
            and amount * price > (available_quote * self._balance_buffer) + 1e-12
        ):
            self._set_cooldown(symbol, 120, f"insufficient {quote_currency} balance")
            return None

        if (
            side == "sell"
            and available_base is not None
            and amount > (available_base * self._balance_buffer) + 1e-12
        ):
            self._set_cooldown(symbol, 120, f"insufficient {base_currency} balance")
            return None

        prepared = dict(order)
        prepared["amount"] = amount
        if order.get("price") is not None:
            prepared["price"] = order["price"]

        return prepared


    async def execute(self, signal=None, **kwargs):
        if signal is None:
            signal = {}
        elif not isinstance(signal, dict):
            raise TypeError("signal must be a dict when provided")

        order = {**signal, **kwargs}

        symbol = order.get("symbol")
        side = order.get("side") or order.get("signal")
        amount = order.get("amount")
        if amount is None:
            amount = order.get("size")
        price = order.get("price")
        order_type = order.get("type", "market")

        if not symbol:
            raise ValueError("Order symbol is required")
        if not side:
            raise ValueError("Order side is required")
        if amount is None:
            raise ValueError("Order amount is required")

        normalized_order = {
            "symbol": symbol,
            "side": str(side).lower(),
            "amount": amount,
            "type": order_type,
        }

        if price is not None:
            normalized_order["price"] = price

        async with self._execution_lock:
            prepared_order = await self._prepare_order(normalized_order)
            if prepared_order is None:
                return None

            try:
                execution = await self.router.route(prepared_order)
            except Exception as exc:
                message = str(exc)
                lowered = message.lower()
                if any(
                    token in lowered
                    for token in ("market is closed", "min_notional", "insufficient balance")
                ):
                    self._set_cooldown(symbol, 300, message)
                    return None
                raise

            fill_event = Event(
                EventType.FILL,
                {
                    "symbol": symbol,
                    "side": prepared_order["side"],
                    "qty": prepared_order["amount"],
                    "price": execution.get("price", price),
                },
            )
            await self.bus.publish(fill_event)

        return execution
