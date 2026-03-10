import logging

import aiohttp

from broker.base_broker import BaseBroker


class OandaBroker(BaseBroker):
    GRANULARITY_MAP = {
        "1m": "M1",
        "5m": "M5",
        "15m": "M15",
        "30m": "M30",
        "1h": "H1",
        "4h": "H4",
        "1d": "D",
        "1w": "W",
    }

    def __init__(self, config):
        super().__init__()

        self.logger = logging.getLogger("OandaBroker")
        self.config = config

        self.token = getattr(config, "api_key", None) or getattr(config, "token", None)
        self.account_id = getattr(config, "account_id", None)
        self.mode = (getattr(config, "mode", "paper") or "paper").lower()
        self.base_url = (
            "https://api-fxpractice.oanda.com"
            if self.mode in {"paper", "practice", "sandbox"}
            else "https://api-fxtrade.oanda.com"
        )

        self.session = None
        self._connected = False

        if not self.token:
            raise ValueError("Oanda API token is required")
        if not self.account_id:
            raise ValueError("Oanda account_id is required")

    # ===============================
    # INTERNALS
    # ===============================

    @property
    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def _ensure_connected(self):
        if not self._connected:
            await self.connect()

    async def _request(self, method, path, params=None, payload=None):
        await self._ensure_connected()

        url = f"{self.base_url}{path}"
        async with self.session.request(
            method,
            url,
            headers=self._headers,
            params=params,
            json=payload,
        ) as response:
            response.raise_for_status()
            return await response.json()

    def _normalize_symbol(self, symbol):
        if not symbol:
            return symbol
        return str(symbol).replace("/", "_").upper()

    def _normalize_granularity(self, timeframe):
        key = str(timeframe or "1h").lower()
        return self.GRANULARITY_MAP.get(key, "H1")

    def _extract_price_entry(self, payload, symbol):
        prices = payload.get("prices", []) if isinstance(payload, dict) else []
        target = self._normalize_symbol(symbol)
        for price in prices:
            if price.get("instrument") == target:
                return price
        return prices[0] if prices else {}

    # ===============================
    # CONNECT
    # ===============================

    async def connect(self):
        if self._connected:
            return True

        self.session = aiohttp.ClientSession()
        self._connected = True
        return True

    async def close(self):
        if self.session is not None:
            await self.session.close()
        self.session = None
        self._connected = False

    # ===============================
    # MARKET DATA
    # ===============================

    async def fetch_ticker(self, symbol):
        instrument = self._normalize_symbol(symbol)
        payload = await self._request(
            "GET",
            f"/v3/accounts/{self.account_id}/pricing",
            params={"instruments": instrument},
        )
        entry = self._extract_price_entry(payload, instrument)
        bids = entry.get("bids", [])
        asks = entry.get("asks", [])
        bid = float(bids[0]["price"]) if bids else None
        ask = float(asks[0]["price"]) if asks else None

        return {
            "symbol": instrument,
            "bid": bid,
            "ask": ask,
            "last": ask or bid,
            "raw": entry,
        }

    async def fetch_orderbook(self, symbol, limit=50):
        ticker = await self.fetch_ticker(symbol)
        bids = []
        asks = []

        raw = ticker.get("raw", {})
        for level in raw.get("bids", [])[:limit]:
            bids.append([float(level["price"]), float(level.get("liquidity", 0) or 0)])
        for level in raw.get("asks", [])[:limit]:
            asks.append([float(level["price"]), float(level.get("liquidity", 0) or 0)])

        return {"symbol": self._normalize_symbol(symbol), "bids": bids, "asks": asks}

    async def fetch_ohlcv(self, symbol, timeframe="H1", limit=100):
        instrument = self._normalize_symbol(symbol)
        granularity = self._normalize_granularity(timeframe)
        payload = await self._request(
            "GET",
            f"/v3/instruments/{instrument}/candles",
            params={"granularity": granularity, "count": limit, "price": "M"},
        )

        candles = []
        for candle in payload.get("candles", []):
            mid = candle.get("mid", {})
            if not candle.get("complete"):
                continue
            candles.append(
                [
                    candle.get("time"),
                    float(mid.get("o", 0) or 0),
                    float(mid.get("h", 0) or 0),
                    float(mid.get("l", 0) or 0),
                    float(mid.get("c", 0) or 0),
                    float(candle.get("volume", 0) or 0),
                ]
            )
        return candles

    async def fetch_trades(self, symbol=None, limit=None):
        payload = await self._request("GET", f"/v3/accounts/{self.account_id}/trades")
        trades = payload.get("trades", [])
        target = self._normalize_symbol(symbol) if symbol else None
        filtered = [trade for trade in trades if target is None or trade.get("instrument") == target]
        return filtered[:limit] if limit else filtered

    async def fetch_symbol(self):
        payload = await self._request("GET", f"/v3/accounts/{self.account_id}/instruments")
        return [item.get("name") for item in payload.get("instruments", []) if item.get("name")]

    async def fetch_symbols(self):
        return await self.fetch_symbol()

    async def fetch_status(self):
        try:
            await self._request("GET", f"/v3/accounts/{self.account_id}/summary")
            return {"status": "ok", "broker": "oanda"}
        except Exception as exc:
            return {"status": "error", "broker": "oanda", "detail": str(exc)}

    # ===============================
    # ORDERS / ACCOUNT
    # ===============================

    async def fetch_balance(self):
        payload = await self._request("GET", f"/v3/accounts/{self.account_id}/summary")
        account = payload.get("account", {})
        currency = account.get("currency", "USD")
        balance = float(account.get("balance", 0) or 0)
        margin_used = float(account.get("marginUsed", 0) or 0)
        return {
            "free": {currency: balance - margin_used},
            "used": {currency: margin_used},
            "total": {currency: balance},
            "equity": float(account.get("NAV", balance) or balance),
            "currency": currency,
            "raw": account,
        }

    async def fetch_positions(self, symbols=None):
        payload = await self._request("GET", f"/v3/accounts/{self.account_id}/openPositions")
        positions = payload.get("positions", [])
        targets = {self._normalize_symbol(symbol) for symbol in (symbols or [])}
        normalized = []
        for position in positions:
            instrument = position.get("instrument")
            if targets and instrument not in targets:
                continue
            long_units = float(position.get("long", {}).get("units", 0) or 0)
            short_units = float(position.get("short", {}).get("units", 0) or 0)
            units = long_units if long_units else -short_units
            normalized.append(
                {
                    "symbol": instrument,
                    "amount": abs(units),
                    "side": "long" if units >= 0 else "short",
                    "entry_price": float(position.get("long", {}).get("averagePrice", 0) or position.get("short", {}).get("averagePrice", 0) or 0),
                    "raw": position,
                }
            )
        return normalized

    async def fetch_orders(self, symbol=None, limit=None):
        payload = await self._request("GET", f"/v3/accounts/{self.account_id}/orders")
        orders = payload.get("orders", [])
        target = self._normalize_symbol(symbol) if symbol else None
        filtered = [order for order in orders if target is None or order.get("instrument") == target]
        return filtered[:limit] if limit else filtered

    async def fetch_open_orders(self, symbol=None, limit=None):
        orders = await self.fetch_orders(symbol=symbol, limit=limit)
        return [order for order in orders if order.get("state") in {"PENDING", "OPEN"}]

    async def fetch_closed_orders(self, symbol=None, limit=None):
        orders = await self.fetch_orders(symbol=symbol, limit=limit)
        return [order for order in orders if order.get("state") in {"FILLED", "CANCELLED", "TRIGGERED"}]

    async def fetch_order(self, order_id, symbol=None):
        payload = await self._request("GET", f"/v3/accounts/{self.account_id}/orders/{order_id}")
        order = payload.get("order", payload)
        if symbol is None:
            return order
        return order if order.get("instrument") == self._normalize_symbol(symbol) else None

    async def create_order(self, symbol, side, amount, type="market", price=None, params=None):
        instrument = self._normalize_symbol(symbol)
        order_type = str(type).upper()
        units = float(amount)
        if str(side).lower() == "sell":
            units = -abs(units)
        else:
            units = abs(units)

        order = {
            "instrument": instrument,
            "units": str(units),
            "type": order_type,
            "positionFill": "DEFAULT",
        }
        if price is not None and order_type != "MARKET":
            order["price"] = str(price)

        extra = dict(params or {})
        stop_loss = extra.pop("stop_loss", None)
        take_profit = extra.pop("take_profit", None)
        if stop_loss is not None:
            order["stopLossOnFill"] = {"price": str(stop_loss)}
        if take_profit is not None:
            order["takeProfitOnFill"] = {"price": str(take_profit)}
        order.update(extra)

        payload = await self._request(
            "POST",
            f"/v3/accounts/{self.account_id}/orders",
            payload={"order": order},
        )
        return payload

    async def cancel_order(self, order_id, symbol=None):
        return await self._request(
            "PUT",
            f"/v3/accounts/{self.account_id}/orders/{order_id}/cancel",
        )

    async def cancel_all_orders(self, symbol=None):
        orders = await self.fetch_open_orders(symbol=symbol)
        canceled = []
        for order in orders:
            order_id = order.get("id")
            if order_id:
                canceled.append(await self.cancel_order(order_id, symbol=symbol))
        return canceled
