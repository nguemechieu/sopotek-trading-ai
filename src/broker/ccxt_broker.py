import logging
import re
import socket
import time

import aiohttp
import ccxt.async_support as ccxt

from broker.base_broker import BaseBroker
from broker.market_venues import (
    SPOT_ONLY_EXCHANGES,
    normalize_market_venue,
    supported_market_venues_for_profile,
)


class CCXTBroker(BaseBroker):
    DEFAULT_TIMEOUT_MS = 30000
    CAPABILITY_MAP = {
        "fetch_ticker": "fetchTicker",
        "fetch_tickers": "fetchTickers",
        "fetch_order_book": "fetchOrderBook",
        "fetch_ohlcv": "fetchOHLCV",
        "fetch_trades": "fetchTrades",
        "fetch_my_trades": "fetchMyTrades",
        "fetch_markets": "fetchMarkets",
        "fetch_currencies": "fetchCurrencies",
        "fetch_status": "fetchStatus",
        "create_order": "createOrder",
        "cancel_order": "cancelOrder",
        "cancel_all_orders": "cancelAllOrders",
        "fetch_balance": "fetchBalance",
        "fetch_positions": "fetchPositions",
        "fetch_order": "fetchOrder",
        "fetch_orders": "fetchOrders",
        "fetch_open_orders": "fetchOpenOrders",
        "fetch_closed_orders": "fetchClosedOrders",
        "withdraw": "withdraw",
        "fetch_deposit_address": "fetchDepositAddress",
    }

    def __init__(self, config):
        super().__init__()

        self.logger = logging.getLogger("CCXTBroker")

        self.config = config
        self.exchange_name = getattr(config, "exchange", None)
        self.api_key = getattr(config, "api_key", None)
        self.secret = getattr(config, "secret", None)
        self.password = getattr(config, "password", None) or getattr(config, "passphrase", None)
        self.uid = getattr(config, "uid", None)
        self.account_id = getattr(config, "account_id", None)
        self.wallet = getattr(config, "wallet", None)
        self.mode = (getattr(config, "mode", "live") or "live").lower()
        self.sandbox = bool(getattr(config, "sandbox", False) or self.mode in {"paper", "sandbox", "testnet"})
        self.timeout = int(getattr(config, "timeout", self.DEFAULT_TIMEOUT_MS) or self.DEFAULT_TIMEOUT_MS)
        self.extra_options = dict(getattr(config, "options", None) or {})
        self.extra_params = dict(getattr(config, "params", None) or {})
        self.market_preference = normalize_market_venue(self.extra_options.get("market_type", "auto"))
        self.resolved_market_preference = self.market_preference

        self.exchange = None
        self.session = None
        self.symbols = []
        self._connected = False
        self._open_orders_snapshot_cache = {}

        if not self.exchange_name:
            raise ValueError("CCXT exchange name is required")

        self.logger.info("Initializing broker %s", self.exchange_name)

    @staticmethod
    def _normalized_credential(value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    # ==========================================================
    # INTERNALS
    # ==========================================================

    def _exchange_class(self):
        try:
            return getattr(ccxt, self.exchange_name)
        except AttributeError as exc:
            raise ValueError(f"Unsupported CCXT exchange: {self.exchange_name}") from exc

    def _build_exchange_options(self):
        options = {"adjustForTimeDifference": True}
        default_type = self._default_type_for_market_preference()
        if default_type:
            options.setdefault("defaultType", default_type)
        options.update(self.extra_options)
        if self._exchange_code() == "binanceus":
            options["defaultType"] = "spot"
            options.pop("defaultSubType", None)
            options["warnOnFetchOpenOrdersWithoutSymbol"] = False
        return options

    def _exchange_code(self):
        return str(self.exchange_name or "").strip().lower()

    def _normalize_credentials(self):
        self.exchange_name = self._normalized_credential(self.exchange_name)
        self.api_key = self._normalized_credential(self.api_key)
        self.secret = self._normalized_credential(self.secret)
        self.password = self._normalized_credential(self.password)
        self.uid = self._normalized_credential(self.uid)
        self.account_id = self._normalized_credential(self.account_id)
        self.wallet = self._normalized_credential(self.wallet)
        if self._exchange_code() == "coinbase" and self.secret:
            self.api_key = self._normalize_coinbase_api_key(self.api_key)
            self.secret = self._normalize_coinbase_secret(self.secret)

    @staticmethod
    def _strip_wrapped_quotes(value):
        text = str(value or "").strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
            return text[1:-1].strip()
        return text

    @classmethod
    def _normalize_coinbase_api_key(cls, value):
        normalized = cls._strip_wrapped_quotes(value)
        return normalized or None

    @classmethod
    def _normalize_coinbase_secret(cls, value):
        secret = cls._strip_wrapped_quotes(value)
        if not secret:
            return None
        if "\\n" in secret:
            secret = secret.replace("\\r\\n", "\n").replace("\\n", "\n")

        if "-----BEGIN" in secret and "-----END" in secret:
            header_match = re.search(r"-----BEGIN [A-Z ]+-----", secret)
            footer_match = re.search(r"-----END [A-Z ]+-----", secret)
            if header_match and footer_match and header_match.start() < footer_match.start():
                header = header_match.group(0)
                footer = footer_match.group(0)
                middle = secret[header_match.end():footer_match.start()]
                if "\n" not in secret and "\r" not in secret:
                    middle = re.sub(r"\s+", "", middle)
                    secret = f"{header}\n{middle}\n{footer}\n" if middle else f"{header}\n{footer}\n"

        return secret

    def _validate_credentials(self):
        exchange_code = self._exchange_code()
        if exchange_code in {"binance", "binanceus"}:
            if self.api_key and any(ch.isspace() for ch in self.api_key):
                raise ValueError(
                    f"{exchange_code.upper()} API key contains whitespace. Paste the key exactly as issued by the exchange."
                )
            if self.secret and any(ch.isspace() for ch in self.secret):
                raise ValueError(
                    f"{exchange_code.upper()} API secret contains whitespace. Paste the secret exactly as issued by the exchange."
                )

    def _default_open_orders_symbol(self, symbol=None):
        if symbol:
            return symbol

        configured = (
            getattr(self.config, "symbol", None)
            or self.extra_options.get("open_orders_symbol")
            or self.extra_options.get("symbol")
        )
        if configured:
            return str(configured).strip() or None

        if len(self.symbols) == 1:
            return self.symbols[0]

        return None

    @staticmethod
    def _dedupe_orders_snapshot(orders):
        unique = []
        seen = set()
        for order in orders or []:
            if isinstance(order, dict):
                key = (
                    str(order.get("id") or ""),
                    str(order.get("clientOrderId") or ""),
                    str(order.get("symbol") or ""),
                    str(order.get("status") or ""),
                )
            else:
                key = (str(order), "", "", "")
            if key in seen:
                continue
            seen.add(key)
            unique.append(order)
        return unique

    def _monitored_symbols(self, symbols=None):
        normalized = []
        default_symbol = self._default_open_orders_symbol()
        if default_symbol:
            normalized.append(default_symbol)

        for symbol in symbols or self.symbols or []:
            candidate = str(symbol or "").strip()
            if candidate:
                normalized.append(candidate)

        return list(dict.fromkeys(normalized))

    async def _fetch_open_orders_without_symbol(self, limit=None):
        kwargs = {}
        if limit is not None:
            kwargs["limit"] = limit
        return await self._call_unified("fetch_open_orders", None, default=[], **kwargs)

    async def _fetch_open_orders_by_symbols(self, symbols, limit=None):
        snapshot = []
        for symbol in symbols or []:
            try:
                orders = await self.fetch_open_orders(symbol=symbol, limit=limit)
            except TypeError:
                orders = await self.fetch_open_orders(symbol)
            snapshot.extend(orders or [])
        return self._dedupe_orders_snapshot(snapshot)

    def _market_matches_preference(self, market):
        if self.market_preference == "auto":
            return True
        if not isinstance(market, dict):
            return False
        if self.market_preference == "spot":
            return bool(market.get("spot"))
        if self.market_preference == "derivative":
            return self._market_is_derivative(market)
        if self.market_preference == "option":
            return bool(market.get("option"))
        if self.market_preference == "otc":
            return self._market_is_otc(market)
        return True

    def _default_type_for_market_preference(self):
        if self.market_preference == "spot":
            return "spot"
        if self.market_preference == "option":
            return "option"
        if self.market_preference == "derivative":
            subtype = str(self.extra_options.get("defaultSubType", "") or "").strip().lower()
            return "future" if subtype == "future" else "swap"
        return None

    @staticmethod
    def _market_is_derivative(market):
        if not isinstance(market, dict):
            return False
        if bool(market.get("option")):
            return False
        return any(bool(market.get(key)) for key in ("contract", "swap", "future"))

    @staticmethod
    def _market_is_otc(market):
        if not isinstance(market, dict):
            return False
        if bool(market.get("otc")):
            return True
        for key in ("type", "marketType", "subType", "category"):
            if str(market.get(key) or "").strip().lower() == "otc":
                return True
        return False

    def _filtered_symbols_from_markets(self, markets):
        if not isinstance(markets, dict):
            return []

        matched = []
        fallback = []
        for symbol, market in markets.items():
            candidate = str((market or {}).get("symbol") or symbol or "").strip()
            if not candidate:
                continue
            fallback.append(candidate)
            if self._market_matches_preference(market):
                matched.append(candidate)

        if self.market_preference == "auto" or matched:
            self.resolved_market_preference = self.market_preference if self.market_preference != "auto" else "auto"
            return sorted(dict.fromkeys(matched or fallback))

        self.resolved_market_preference = "auto"
        self.logger.warning(
            "Requested market preference %s was not available on %s; falling back to auto symbols",
            self.market_preference,
            self.exchange_name,
        )
        return sorted(dict.fromkeys(fallback))

    def _supports_positions_endpoint(self):
        if self._exchange_code() in SPOT_ONLY_EXCHANGES:
            return False

        markets = getattr(self.exchange, "markets", None)
        if not isinstance(markets, dict) or not markets:
            return True

        market_flags_detected = False
        for market in markets.values():
            if not isinstance(market, dict):
                continue
            if any(key in market for key in ("spot", "contract", "swap", "future", "option")):
                market_flags_detected = True
            if any(bool(market.get(key)) for key in ("contract", "swap", "future", "option")):
                return True

        if market_flags_detected:
            return False

        return True

    def apply_market_preference(self, preference=None):
        if preference is not None:
            normalized = normalize_market_venue(preference)
            self.market_preference = normalized
            self.extra_options["market_type"] = normalized
        markets = getattr(self.exchange, "markets", {}) if self.exchange is not None else {}
        self.symbols = self._filtered_symbols_from_markets(markets)
        return list(self.symbols)

    def supported_market_venues(self):
        exchange_code = self._exchange_code()
        if exchange_code in SPOT_ONLY_EXCHANGES:
            return ["auto", "spot"]

        markets = getattr(getattr(self, "exchange", None), "markets", None)
        if isinstance(markets, dict) and markets:
            venues = ["auto"]
            if any(bool((market or {}).get("spot")) for market in markets.values()):
                venues.append("spot")
            if any(self._market_is_derivative(market) for market in markets.values()):
                venues.append("derivative")
            if any(bool((market or {}).get("option")) for market in markets.values()):
                venues.append("option")
            if any(self._market_is_otc(market) for market in markets.values()):
                venues.append("otc")
            return list(dict.fromkeys(venues))

        return supported_market_venues_for_profile("crypto", exchange_code)

    def _build_exchange_config(self):
        cfg = {
            "enableRateLimit": True,
            "timeout": self.timeout,
            "options": self._build_exchange_options(),
        }

        if self.session is not None:
            cfg["session"] = self.session

        if self.api_key:
            cfg["apiKey"] = self.api_key
        if self.secret:
            cfg["secret"] = self.secret
        if self.password:
            cfg["password"] = self.password
        if self.uid:
            cfg["uid"] = self.uid
        if self.wallet:
            cfg["walletAddress"] = self.wallet

        if self.exchange_name.startswith("binance"):
            cfg["recvWindow"] = int(self.extra_options.get("recvWindow", 10000))

        return cfg

    async def _ensure_connected(self):
        if not self._connected:
            await self.connect()

    def _exchange_has(self, capability):
        exchange = self.exchange
        if exchange is None:
            return False

        if capability == "fetch_positions" and not self._supports_positions_endpoint():
            return False

        has_key = self.CAPABILITY_MAP.get(capability, capability)
        has_map = getattr(exchange, "has", None)
        if isinstance(has_map, dict):
            supported = has_map.get(has_key)
            if supported in (True, "emulated"):
                return True
            if supported is False:
                return False

        return callable(getattr(exchange, capability, None))

    def _maybe_precision_amount(self, symbol, amount):
        if self.exchange is None or amount is None:
            return amount

        converter = getattr(self.exchange, "amount_to_precision", None)
        if callable(converter):
            try:
                return float(converter(symbol, amount))
            except Exception:
                return amount
        return amount

    def _maybe_precision_price(self, symbol, price):
        if self.exchange is None or price is None:
            return price

        converter = getattr(self.exchange, "price_to_precision", None)
        if callable(converter):
            try:
                return float(converter(symbol, price))
            except Exception:
                return price
        return price

    async def _call_unified(self, method_name, *args, default=None, **kwargs):
        await self._ensure_connected()

        method = getattr(self.exchange, method_name, None)
        if not callable(method):
            if default is not None:
                return default
            raise NotImplementedError(
                f"{self.exchange_name} does not expose {method_name}"
            )

        if not self._exchange_has(method_name):
            if default is not None:
                return default
            raise NotImplementedError(
                f"{self.exchange_name} does not support {method_name}"
            )

        return await method(*args, **kwargs)

    # ==========================================================
    # CONNECT
    # ==========================================================

    async def connect(self):
        if self._connected:
            return

        self._normalize_credentials()
        self._validate_credentials()

        exchange_class = self._exchange_class()

        resolver = aiohttp.ThreadedResolver()
        connector = aiohttp.TCPConnector(
            resolver=resolver,
            family=socket.AF_INET,
            ttl_dns_cache=300,
        )
        self.session = aiohttp.ClientSession(connector=connector)
        self.exchange = exchange_class(self._build_exchange_config())

        try:
            if hasattr(self.exchange, "set_sandbox_mode"):
                self.exchange.set_sandbox_mode(self.sandbox)

            if callable(getattr(self.exchange, "load_time_difference", None)):
                await self.exchange.load_time_difference()

            await self.exchange.load_markets()
            self.symbols = self._filtered_symbols_from_markets(getattr(self.exchange, "markets", {}) or {})
            self._connected = True
        except Exception:
            await self.close()
            raise

    async def close(self):
        errors = []

        if self.exchange is not None:
            try:
                await self.exchange.close()
            except Exception as exc:
                errors.append(exc)

        if self.session is not None:
            try:
                await self.session.close()
            except Exception as exc:
                errors.append(exc)

        self.exchange = None
        self.session = None
        self.symbols = []
        self._connected = False

        if errors:
            self.logger.warning("Broker close encountered %s issue(s)", len(errors))

    # ==========================================================
    # DISCOVERY
    # ==========================================================

    async def fetch_symbol(self):
        await self._ensure_connected()
        return list(self.symbols)

    async def fetch_symbols(self):
        return await self.fetch_symbol()

    async def fetch_markets(self):
        await self._ensure_connected()
        markets = getattr(self.exchange, "markets", None)
        if isinstance(markets, dict) and markets:
            return markets
        return await self._call_unified("fetch_markets", default={})

    async def fetch_currencies(self):
        await self._ensure_connected()
        currencies = getattr(self.exchange, "currencies", None)
        if isinstance(currencies, dict) and currencies:
            return currencies
        return await self._call_unified("fetch_currencies", default={})

    async def fetch_status(self):
        if not self._connected:
            return {"status": "disconnected"}

        if self._exchange_has("fetchStatus"):
            return await self._call_unified("fetch_status")

        return {"status": "ok", "exchange": self.exchange_name}

    # ==========================================================
    # MARKET DATA
    # ==========================================================

    async def fetch_ticker(self, symbol):
        return await self._call_unified("fetch_ticker", symbol)

    async def fetch_tickers(self, symbols=None):
        return await self._call_unified("fetch_tickers", symbols, default={})

    async def fetch_orderbook(self, symbol, limit=100):
        return await self._call_unified("fetch_order_book", symbol, limit)

    async def fetch_order_book(self, symbol, limit=100):
        return await self.fetch_orderbook(symbol, limit=limit)

    async def fetch_ohlcv(self, symbol, timeframe="1h", limit=100):
        self.logger.info("Fetching OHLCV for %s", symbol)
        return await self._call_unified(
            "fetch_ohlcv",
            symbol,
            timeframe=timeframe,
            limit=limit,
            default=[],
        )

    async def fetch_trades(self, symbol, limit=None):
        kwargs = {}
        if limit is not None:
            kwargs["limit"] = limit
        return await self._call_unified("fetch_trades", symbol, default=[], **kwargs)

    async def fetch_my_trades(self, symbol=None, limit=None):
        kwargs = {}
        if limit is not None:
            kwargs["limit"] = limit
        return await self._call_unified("fetch_my_trades", symbol, default=[], **kwargs)

    # ==========================================================
    # TRADING
    # ==========================================================

    async def create_order(
        self,
        symbol,
        side,
        amount,
        type="market",
        price=None,
        stop_price=None,
        params=None,
        stop_loss=None,
        take_profit=None,
    ):
        await self._ensure_connected()

        normalized_type = str(type or "market").strip().lower() or "market"
        trigger_price = stop_price
        if trigger_price is None and isinstance(params, dict):
            trigger_price = params.get("stop_price", params.get("stopPrice"))
        if normalized_type == "stop_limit":
            if price is None or float(price) <= 0:
                raise ValueError("stop_limit orders require a positive limit price")
            if trigger_price is None or float(trigger_price) <= 0:
                raise ValueError("stop_limit orders require a positive stop_price trigger")

        normalized_amount = self._maybe_precision_amount(symbol, float(amount))
        normalized_price = self._maybe_precision_price(symbol, price)
        order_params = dict(self.extra_params)
        if params:
            order_params.update(params)
        if trigger_price is not None:
            order_params.setdefault("stopPrice", float(trigger_price))
            order_params.setdefault("stop_price", float(trigger_price))
        if stop_loss is not None:
            order_params.setdefault("stopLossPrice", stop_loss)
        if take_profit is not None:
            order_params.setdefault("takeProfitPrice", take_profit)

        if not self._exchange_has("create_order"):
            raise NotImplementedError(f"{self.exchange_name} does not support create_order")

        created = await self.exchange.create_order(
            symbol,
            normalized_type,
            str(side).lower(),
            normalized_amount,
            normalized_price,
            order_params,
        )
        if isinstance(created, dict) and trigger_price is not None:
            created.setdefault("stop_price", float(trigger_price))
        return created

    async def cancel_order(self, order_id, symbol=None):
        if symbol is None:
            return await self._call_unified("cancel_order", order_id)
        return await self._call_unified("cancel_order", order_id, symbol)

    async def cancel_all_orders(self, symbol=None):
        if symbol is None:
            return await self._call_unified("cancel_all_orders", default=[])
        return await self._call_unified("cancel_all_orders", symbol, default=[])

    # ==========================================================
    # ACCOUNT
    # ==========================================================

    async def fetch_balance(self):
        return await self._call_unified("fetch_balance")

    async def fetch_positions(self, symbols=None):
        return await self._call_unified("fetch_positions", symbols, default=[])

    async def fetch_order(self, order_id, symbol=None):
        if symbol is None:
            return await self._call_unified("fetch_order", order_id)
        return await self._call_unified("fetch_order", order_id, symbol)

    async def fetch_orders(self, symbol=None, limit=None):
        kwargs = {}
        if limit is not None:
            kwargs["limit"] = limit
        return await self._call_unified("fetch_orders", symbol, default=[], **kwargs)

    async def fetch_open_orders(self, symbol=None, limit=None):
        kwargs = {}
        if limit is not None:
            kwargs["limit"] = limit
        target_symbol = self._default_open_orders_symbol(symbol)
        return await self._call_unified("fetch_open_orders", target_symbol, default=[], **kwargs)

    async def fetch_open_orders_snapshot(self, symbols=None, limit=None):
        monitored_symbols = self._monitored_symbols(symbols)
        exchange_code = str(self.exchange_name or "").strip().lower()
        cache_key = ("snapshot", tuple(monitored_symbols), limit)
        now = time.monotonic()

        if exchange_code == "binanceus":
            if len(monitored_symbols) <= 8 and monitored_symbols:
                ttl_seconds = 15.0
                fetcher = lambda: self._fetch_open_orders_by_symbols(monitored_symbols, limit=limit)
            else:
                cache_key = ("snapshot-global", limit)
                ttl_seconds = 310.0
                fetcher = lambda: self._fetch_open_orders_without_symbol(limit=limit)

            cached = self._open_orders_snapshot_cache.get(cache_key)
            if cached and now < cached["expires_at"]:
                return list(cached["orders"])

            orders = self._dedupe_orders_snapshot(await fetcher())
            self._open_orders_snapshot_cache[cache_key] = {
                "orders": list(orders),
                "expires_at": now + ttl_seconds,
            }
            return orders

        try:
            return self._dedupe_orders_snapshot(await self._fetch_open_orders_without_symbol(limit=limit))
        except Exception:
            if monitored_symbols:
                return await self._fetch_open_orders_by_symbols(monitored_symbols, limit=limit)
            raise

    async def fetch_closed_orders(self, symbol=None, limit=None):
        kwargs = {}
        if limit is not None:
            kwargs["limit"] = limit
        return await self._call_unified("fetch_closed_orders", symbol, default=[], **kwargs)

    async def withdraw(self, code, amount, address, tag=None, params=None):
        order_params = dict(self.extra_params)
        if params:
            order_params.update(params)
        if tag is not None:
            order_params.setdefault("tag", tag)
        return await self._call_unified(
            "withdraw",
            code,
            amount,
            address,
            tag,
            order_params,
        )

    async def fetch_deposit_address(self, code, params=None):
        order_params = dict(self.extra_params)
        if params:
            order_params.update(params)
        return await self._call_unified(
            "fetch_deposit_address",
            code,
            order_params,
        )
