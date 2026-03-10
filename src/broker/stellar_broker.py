import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import aiohttp

from broker.base_broker import BaseBroker

try:  # pragma: no cover - optional dependency at runtime
    from stellar_sdk import AiohttpClient, Asset, Keypair, Network, ServerAsync, TransactionBuilder
except Exception:  # pragma: no cover - optional dependency at runtime
    AiohttpClient = None
    Asset = None
    Keypair = None
    Network = None
    ServerAsync = None
    TransactionBuilder = None


@dataclass
class StellarAssetDescriptor:
    code: str
    issuer: Optional[str] = None

    @property
    def is_native(self) -> bool:
        return self.issuer is None and self.code.upper() == "XLM"

    @property
    def asset_type(self) -> str:
        if self.is_native:
            return "native"
        return "credit_alphanum4" if len(self.code) <= 4 else "credit_alphanum12"

    def to_horizon(self, prefix: str) -> Dict[str, str]:
        if self.is_native:
            return {f"{prefix}_asset_type": "native"}
        return {
            f"{prefix}_asset_type": self.asset_type,
            f"{prefix}_asset_code": self.code,
            f"{prefix}_asset_issuer": self.issuer,
        }

    def to_sdk(self):
        if Asset is None:
            raise RuntimeError("stellar-sdk is required for live Stellar order execution")
        if self.is_native:
            return Asset.native()
        return Asset(self.code, self.issuer)


class StellarBroker(BaseBroker):
    HORIZON_PUBLIC_URL = "https://horizon.stellar.org"
    HORIZON_TESTNET_URL = "https://horizon-testnet.stellar.org"
    BASE_FEE = 100
    RESOLUTION_MAP = {
        "1m": 60000,
        "5m": 300000,
        "15m": 900000,
        "1h": 3600000,
        "1d": 86400000,
        "1w": 604800000,
    }
    DEFAULT_QUOTE_PRIORITY = ("USDC", "USDT", "EURC", "XLM")

    def __init__(self, config):
        super().__init__()

        self.logger = logging.getLogger("StellarBroker")
        self.config = config
        self.public_key = getattr(config, "api_key", None) or getattr(config, "account_id", None)
        self.secret = getattr(config, "secret", None)
        self.mode = (getattr(config, "mode", "live") or "live").lower()
        self.sandbox = bool(getattr(config, "sandbox", False) or self.mode in {"paper", "sandbox", "testnet"})
        self.params = dict(getattr(config, "params", None) or {})
        self.options = dict(getattr(config, "options", None) or {})
        self.horizon_url = self.params.get(
            "horizon_url",
            self.HORIZON_TESTNET_URL if self.sandbox else self.HORIZON_PUBLIC_URL,
        )
        self.base_fee = int(self.params.get("base_fee", self.BASE_FEE))
        self.default_slippage_pct = float(self.params.get("slippage_pct", 0.02))
        self.network_passphrase = self.params.get(
            "network_passphrase",
            self._default_network_passphrase(),
        )

        self.session = None
        self._connected = False
        self.asset_registry: Dict[str, StellarAssetDescriptor] = {"XLM": StellarAssetDescriptor("XLM", None)}

        if not self.public_key:
            raise ValueError("Stellar public key is required")

        self._load_config_assets()

    def _default_network_passphrase(self) -> str:
        if Network is None:
            return "Test SDF Network ; September 2015" if self.sandbox else "Public Global Stellar Network ; September 2015"
        return (
            Network.TESTNET_NETWORK_PASSPHRASE
            if self.sandbox
            else Network.PUBLIC_NETWORK_PASSPHRASE
        )

    def _load_config_assets(self):
        raw_assets = self.params.get("assets") or self.params.get("asset_map") or {}
        parsed_assets = self._parse_assets_input(raw_assets)
        for descriptor in parsed_assets.values():
            self.asset_registry[descriptor.code] = descriptor

    def _parse_assets_input(self, raw_assets) -> Dict[str, StellarAssetDescriptor]:
        parsed = {}

        if isinstance(raw_assets, dict):
            iterable = []
            for code, value in raw_assets.items():
                if isinstance(value, dict):
                    item = dict(value)
                    item.setdefault("code", code)
                elif value in (None, "", "native"):
                    item = {"code": code}
                else:
                    item = {"code": code, "issuer": value}
                iterable.append(item)
        elif isinstance(raw_assets, list):
            iterable = raw_assets
        else:
            iterable = []

        for item in iterable:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or item.get("asset_code") or "").upper().strip()
            issuer = item.get("issuer") or item.get("asset_issuer")
            if not code:
                continue
            if code == "XLM":
                parsed["XLM"] = StellarAssetDescriptor("XLM", None)
            elif issuer:
                parsed[code] = StellarAssetDescriptor(code, str(issuer))

        return parsed

    async def _ensure_connected(self):
        if not self._connected:
            await self.connect()

    async def _request_connected(self, method: str, path: str, params=None, payload=None):
        if self.session is None:
            raise RuntimeError("Stellar broker is not connected")
        url = f"{self.horizon_url}{path}"
        async with self.session.request(method, url, params=params, json=payload) as response:
            response.raise_for_status()
            return await response.json()

    async def _request(self, method: str, path: str, params=None, payload=None):
        await self._ensure_connected()
        return await self._request_connected(method, path, params=params, payload=payload)

    async def _load_account(self):
        account = await self._request_connected("GET", f"/accounts/{self.public_key}")
        self._register_assets_from_account(account)
        return account

    def _register_assets_from_account(self, account: dict):
        balances = account.get("balances", []) if isinstance(account, dict) else []
        for balance in balances:
            code = self._asset_code_from_balance(balance)
            issuer = self._asset_issuer_from_balance(balance)
            if code:
                self.asset_registry[code] = StellarAssetDescriptor(code, issuer)

    def _asset_code_from_balance(self, balance: dict) -> Optional[str]:
        asset_type = balance.get("asset_type")
        if asset_type == "native":
            return "XLM"
        code = balance.get("asset_code")
        return str(code).upper() if code else None

    def _asset_issuer_from_balance(self, balance: dict) -> Optional[str]:
        if balance.get("asset_type") == "native":
            return None
        issuer = balance.get("asset_issuer")
        return str(issuer) if issuer else None

    def _symbol_parts(self, symbol: str) -> Tuple[str, str]:
        if not symbol or "/" not in symbol:
            raise ValueError(f"Invalid Stellar symbol: {symbol}")
        base, quote = str(symbol).split("/", 1)
        return base.strip(), quote.strip()

    def _parse_asset_text(self, text: str) -> StellarAssetDescriptor:
        raw = str(text or "").strip()
        if not raw:
            raise ValueError("Asset code is required")

        if raw.upper() == "XLM":
            return StellarAssetDescriptor("XLM", None)

        if ":" in raw:
            code, issuer = raw.split(":", 1)
            code = code.strip().upper()
            issuer = issuer.strip()
            if not code or not issuer:
                raise ValueError(f"Invalid Stellar asset identifier: {raw}")
            descriptor = StellarAssetDescriptor(code, issuer)
            self.asset_registry[descriptor.code] = descriptor
            return descriptor

        lookup = self.asset_registry.get(raw.upper())
        if lookup is None:
            raise ValueError(
                f"Unknown Stellar asset '{raw}'. Provide it via broker params['assets'] or use CODE:ISSUER in the symbol."
            )
        return lookup

    def _resolve_symbol_assets(self, symbol: str) -> Tuple[StellarAssetDescriptor, StellarAssetDescriptor]:
        base_text, quote_text = self._symbol_parts(symbol)
        return self._parse_asset_text(base_text), self._parse_asset_text(quote_text)

    def _symbol_from_assets(self, base: StellarAssetDescriptor, quote: StellarAssetDescriptor) -> str:
        return f"{base.code}/{quote.code}"

    def _build_tradable_symbols(self) -> List[str]:
        explicit_symbols = self.params.get("symbols")
        if isinstance(explicit_symbols, list) and explicit_symbols:
            return [str(symbol) for symbol in explicit_symbols if symbol]

        codes = list(self.asset_registry.keys())
        quote_assets = [
            str(code).upper()
            for code in (self.params.get("quote_assets") or self.DEFAULT_QUOTE_PRIORITY)
            if str(code).upper() in self.asset_registry
        ]

        if not quote_assets:
            quote_assets = codes[:]

        symbols = []
        seen_pairs = set()
        for quote in quote_assets:
            for base in codes:
                if base == quote:
                    continue
                pair_key = tuple(sorted((base, quote)))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                symbols.append(f"{base}/{quote}")

        unique_symbols = []
        seen = set()
        for symbol in symbols:
            if symbol not in seen:
                seen.add(symbol)
                unique_symbols.append(symbol)
        return unique_symbols

    def _float(self, value, default=0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    def _horizon_price(self, payload: dict) -> float:
        price = payload.get("price")
        if isinstance(price, dict):
            n = self._float(price.get("n"), 0.0)
            d = self._float(price.get("d"), 0.0)
            return n / d if d else 0.0
        if price is not None:
            return self._float(price, 0.0)

        base_amount = self._float(payload.get("base_amount"), 0.0)
        counter_amount = self._float(payload.get("counter_amount"), 0.0)
        if base_amount > 0:
            return counter_amount / base_amount
        return 0.0

    def _normalize_offer(self, offer: dict) -> dict:
        selling = offer.get("selling", {}) if isinstance(offer, dict) else {}
        buying = offer.get("buying", {}) if isinstance(offer, dict) else {}
        selling_code = "XLM" if selling.get("asset_type") == "native" else str(selling.get("asset_code") or "").upper()
        buying_code = "XLM" if buying.get("asset_type") == "native" else str(buying.get("asset_code") or "").upper()
        raw_price = self._float(offer.get("price"), 0.0)
        raw_amount = self._float(offer.get("amount"), 0.0)
        quote_priority = {str(code).upper() for code in (self.params.get("quote_assets") or self.DEFAULT_QUOTE_PRIORITY)}

        side = "sell"
        symbol = f"{selling_code}/{buying_code}" if selling_code and buying_code else ""
        amount = raw_amount
        standard_price = raw_price

        if selling_code in quote_priority and buying_code and (buying_code not in quote_priority or buying_code == "XLM"):
            side = "buy"
            symbol = f"{buying_code}/{selling_code}"
            amount = raw_amount / raw_price if raw_price else 0.0
            standard_price = raw_price
        elif buying_code in quote_priority and selling_code:
            side = "sell"
            symbol = f"{selling_code}/{buying_code}"
            standard_price = (1.0 / raw_price) if raw_price else 0.0

        return {
            "id": str(offer.get("id")),
            "symbol": symbol,
            "side": side,
            "type": "limit",
            "status": "open",
            "amount": amount,
            "price": standard_price,
            "raw": offer,
        }

    async def _submit_transaction(self, build_transaction):
        if ServerAsync is None or TransactionBuilder is None or Keypair is None:
            raise RuntimeError(
                "stellar-sdk[aiohttp] is required for Stellar order execution. "
                "Install the dependency from requirements.txt."
            )
        if not self.secret:
            raise ValueError("Stellar secret seed is required for order execution")

        async with ServerAsync(horizon_url=self.horizon_url, client=AiohttpClient()) as server:
            source_account = await server.load_account(self.public_key)
            builder = TransactionBuilder(
                source_account=source_account,
                network_passphrase=self.network_passphrase,
                base_fee=self.base_fee,
            )
            build_transaction(builder)
            transaction = builder.set_timeout(30).build()
            transaction.sign(Keypair.from_secret(self.secret))
            return await server.submit_transaction(transaction)

    async def connect(self):
        if self._connected:
            return True

        self.session = aiohttp.ClientSession()
        await self._load_account()
        self._connected = True
        self.logger.info("Connected to Stellar Horizon (%s)", self.horizon_url)
        return True

    async def close(self):
        if self.session is not None:
            await self.session.close()
        self.session = None
        self._connected = False

    async def fetch_symbol(self):
        await self._ensure_connected()
        if not any(code != "XLM" for code in self.asset_registry):
            await self._load_account()
        return self._build_tradable_symbols()

    async def fetch_symbols(self):
        return await self.fetch_symbol()

    async def fetch_markets(self):
        symbols = await self.fetch_symbols()
        return {symbol: {"symbol": symbol, "active": True, "spot": True} for symbol in symbols}

    async def fetch_status(self):
        try:
            await self._request("GET", "/")
            return {"status": "ok", "broker": "stellar", "horizon_url": self.horizon_url}
        except Exception as exc:
            return {"status": "error", "broker": "stellar", "detail": str(exc)}

    async def fetch_ticker(self, symbol):
        book = await self.fetch_orderbook(symbol, limit=1)
        trades = await self.fetch_trades(symbol, limit=1)

        bid = book["bids"][0][0] if book["bids"] else 0.0
        ask = book["asks"][0][0] if book["asks"] else 0.0
        last = self._horizon_price(trades[0]) if trades else 0.0
        if last <= 0:
            if bid and ask:
                last = (bid + ask) / 2
            else:
                last = ask or bid

        return {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "last": last,
        }

    async def fetch_orderbook(self, symbol, limit=20):
        base_asset, quote_asset = self._resolve_symbol_assets(symbol)
        params = {}
        params.update(base_asset.to_horizon("selling"))
        params.update(quote_asset.to_horizon("buying"))
        params["limit"] = limit

        payload = await self._request("GET", "/order_book", params=params)
        bids = [
            [self._float(level.get("price"), 0.0), self._float(level.get("amount"), 0.0)]
            for level in payload.get("bids", [])[:limit]
        ]
        asks = [
            [self._float(level.get("price"), 0.0), self._float(level.get("amount"), 0.0)]
            for level in payload.get("asks", [])[:limit]
        ]
        return {"symbol": self._symbol_from_assets(base_asset, quote_asset), "bids": bids, "asks": asks}

    async def fetch_trades(self, symbol, limit=None):
        base_asset, quote_asset = self._resolve_symbol_assets(symbol)
        params = {}
        params.update(base_asset.to_horizon("base"))
        params.update(quote_asset.to_horizon("counter"))
        params["order"] = "desc"
        if limit is not None:
            params["limit"] = limit

        payload = await self._request("GET", "/trades", params=params)
        records = ((payload.get("_embedded") or {}).get("records")) or payload.get("records") or []
        return records[:limit] if limit else records

    async def fetch_my_trades(self, symbol=None, limit=None):
        payload = await self._request("GET", f"/accounts/{self.public_key}/trades", params={"order": "desc", "limit": limit or 50})
        records = ((payload.get("_embedded") or {}).get("records")) or payload.get("records") or []
        if symbol is None:
            return records[:limit] if limit else records

        base_asset, quote_asset = self._resolve_symbol_assets(symbol)
        filtered = []
        for record in records:
            base_code = "XLM" if record.get("base_asset_type") == "native" else str(record.get("base_asset_code") or "").upper()
            counter_code = "XLM" if record.get("counter_asset_type") == "native" else str(record.get("counter_asset_code") or "").upper()
            if base_code == base_asset.code and counter_code == quote_asset.code:
                filtered.append(record)
        return filtered[:limit] if limit else filtered

    async def fetch_ohlcv(self, symbol, timeframe="1h", limit=100):
        base_asset, quote_asset = self._resolve_symbol_assets(symbol)
        resolution = self.RESOLUTION_MAP.get(str(timeframe or "1h").lower(), 3600000)
        end_time = int(time.time() * 1000)
        start_time = end_time - (resolution * max(limit, 1))

        params = {}
        params.update(base_asset.to_horizon("base"))
        params.update(quote_asset.to_horizon("counter"))
        params.update(
            {
                "resolution": resolution,
                "startTime": start_time,
                "endTime": end_time,
                "order": "asc",
                "limit": limit,
            }
        )

        payload = await self._request("GET", "/trade_aggregations", params=params)
        records = ((payload.get("_embedded") or {}).get("records")) or payload.get("records") or []

        candles = []
        for record in records:
            candles.append(
                [
                    int(record.get("timestamp") or 0),
                    self._float(record.get("open"), 0.0),
                    self._float(record.get("high"), 0.0),
                    self._float(record.get("low"), 0.0),
                    self._float(record.get("close"), 0.0),
                    self._float(record.get("base_volume"), 0.0),
                ]
            )
        return candles[-limit:]

    async def fetch_balance(self):
        account = await self._load_account()

        free = {}
        used = {}
        total = {}

        for balance in account.get("balances", []):
            code = self._asset_code_from_balance(balance)
            if not code:
                continue

            total_value = self._float(balance.get("balance"), 0.0)
            locked_value = self._float(balance.get("selling_liabilities"), 0.0)
            free_value = max(total_value - locked_value, 0.0)

            free[code] = free_value
            used[code] = locked_value
            total[code] = total_value

        return {
            "free": free,
            "used": used,
            "total": total,
            "raw": account,
        }

    async def fetch_positions(self, symbols=None):
        return []

    async def fetch_orders(self, symbol=None, limit=None):
        payload = await self._request(
            "GET",
            f"/accounts/{self.public_key}/offers",
            params={"order": "desc", "limit": limit or 50},
        )
        records = ((payload.get("_embedded") or {}).get("records")) or payload.get("records") or []
        orders = []
        for offer in records:
            normalized = self._normalize_offer(offer)
            if symbol and symbol != normalized["symbol"]:
                continue
            orders.append(normalized)
        return orders[:limit] if limit else orders

    async def fetch_open_orders(self, symbol=None, limit=None):
        return await self.fetch_orders(symbol=symbol, limit=limit)

    async def fetch_closed_orders(self, symbol=None, limit=None):
        return await self.fetch_my_trades(symbol=symbol, limit=limit)

    async def fetch_order(self, order_id, symbol=None):
        orders = await self.fetch_orders(symbol=symbol, limit=200)
        for order in orders:
            if str(order.get("id")) == str(order_id):
                return order
        return None

    async def create_order(self, symbol, side, amount, type="market", price=None, params=None):
        base_asset, quote_asset = self._resolve_symbol_assets(symbol)
        order_side = str(side).lower()
        order_type = str(type or "market").lower()
        params = dict(params or {})
        slippage_pct = float(params.pop("slippage_pct", self.default_slippage_pct))

        ticker = await self.fetch_ticker(symbol)
        if order_side == "buy":
            reference_price = self._float(price, ticker.get("ask") or ticker.get("last") or 0.0)
            if reference_price <= 0:
                raise ValueError(f"Unable to determine Stellar buy price for {symbol}")
            effective_price = reference_price * (1 + slippage_pct) if order_type == "market" else reference_price

            def _build(builder):
                builder.append_manage_buy_offer_op(
                    selling=quote_asset.to_sdk(),
                    buying=base_asset.to_sdk(),
                    buy_amount=f"{float(amount):.7f}",
                    price=f"{effective_price:.7f}",
                    offer_id=int(params.pop("offer_id", 0)),
                )

            response = await self._submit_transaction(_build)
            return {
                "id": response.get("hash"),
                "symbol": self._symbol_from_assets(base_asset, quote_asset),
                "side": "buy",
                "type": order_type,
                "amount": float(amount),
                "price": effective_price,
                "status": "submitted",
                "raw": response,
            }

        reference_price = self._float(price, ticker.get("bid") or ticker.get("last") or 0.0)
        if reference_price <= 0:
            raise ValueError(f"Unable to determine Stellar sell price for {symbol}")
        effective_price = reference_price * max(1 - slippage_pct, 0.0001) if order_type == "market" else reference_price
        stellar_price = 1.0 / effective_price if effective_price else 0.0

        def _build(builder):
            builder.append_manage_sell_offer_op(
                selling=base_asset.to_sdk(),
                buying=quote_asset.to_sdk(),
                amount=f"{float(amount):.7f}",
                price=f"{stellar_price:.7f}",
                offer_id=int(params.pop("offer_id", 0)),
            )

        response = await self._submit_transaction(_build)
        return {
            "id": response.get("hash"),
            "symbol": self._symbol_from_assets(base_asset, quote_asset),
            "side": "sell",
            "type": order_type,
            "amount": float(amount),
            "price": effective_price,
            "status": "submitted",
            "raw": response,
        }

    async def cancel_order(self, order_id, symbol=None):
        order = await self.fetch_order(order_id, symbol=symbol)
        if order is None:
            raise ValueError(f"Unknown Stellar offer id: {order_id}")

        raw_offer = order.get("raw", {})
        selling = raw_offer.get("selling", {}) if isinstance(raw_offer, dict) else {}
        buying = raw_offer.get("buying", {}) if isinstance(raw_offer, dict) else {}
        selling_text = "XLM" if selling.get("asset_type") == "native" else f"{selling.get('asset_code')}:{selling.get('asset_issuer')}"
        buying_text = "XLM" if buying.get("asset_type") == "native" else f"{buying.get('asset_code')}:{buying.get('asset_issuer')}"
        selling_asset = self._parse_asset_text(selling_text)
        buying_asset = self._parse_asset_text(buying_text)
        stellar_price = self._float(raw_offer.get("price"), 1.0) or 1.0

        def _build(builder):
            builder.append_manage_sell_offer_op(
                selling=selling_asset.to_sdk(),
                buying=buying_asset.to_sdk(),
                amount="0",
                price=f"{stellar_price:.7f}",
                offer_id=int(order_id),
            )

        response = await self._submit_transaction(_build)
        return {"id": str(order_id), "status": "canceled", "raw": response}
