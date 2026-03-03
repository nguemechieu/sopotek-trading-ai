# brokers/factory.py

from .ccxt_broker import CCXTBroker
from .oanda_broker import OandaBroker
from .rate_limiter import RateLimiter


BROKER_REGISTRY = {
    "crypto": CCXTBroker,
    "oanda": OandaBroker,
}


class BrokerFactory:

    @staticmethod
    def create(config: dict, logger=None):

        broker_type = config.get("type")

        if not broker_type:
            raise ValueError("Broker type not specified in config")

        broker_class = BROKER_REGISTRY.get(broker_type)

        if not broker_class:
            raise ValueError(f"Unsupported broker type: {broker_type}")

        mode = config.get("mode", "paper")
        credentials = config.get("credentials") or {}
        options = config.get("options") or {}

        rate_limit = options.get("rate_limit", 5)
        rate_limiter = RateLimiter(rate_limit)

        # =============================
        # CRYPTO (CCXT)
        # =============================
        if broker_type == "crypto":

            exchange = options.get("exchange")
            if not exchange:
                raise ValueError("Missing exchange name for crypto broker")

            api_key = credentials.get("api_key")
            secret = credentials.get("secret")

            if not api_key or not secret:
                raise ValueError("Missing API credentials for crypto broker")

            broker_config = {
                "exchange_name": exchange,
                "api_key": api_key,
                "secret": secret,
                "mode": mode,
                "rate_limiter": rate_limiter,
                "exchange_options": options.get("exchange_options", "spot"),
                "logger": logger,
            }

            return broker_class(broker_config)

        # =============================
        # OANDA
        # =============================
        if broker_type == "oanda":

            api_key = credentials.get("api_key")
            account_id = credentials.get("account_id")

            if not api_key or not account_id:
                raise ValueError("Missing OANDA credentials")

            broker_config = {
                "api_key": api_key,
                "account_id": account_id,
                "mode": mode,
                "rate_limiter": rate_limiter,
                "logger": logger,
            }

            return broker_class(broker_config)

        raise RuntimeError("BrokerFactory reached unreachable state")