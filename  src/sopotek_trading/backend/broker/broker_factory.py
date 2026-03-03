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
    def create(config, logger=None):

        broker_type = config.get("type",  "crypto")
        if not broker_type:
            raise ValueError("Broker type not specified")

        broker_class = BROKER_REGISTRY.get(broker_type)
        if not broker_class:
            raise ValueError(f"Unsupported broker type: {broker_type}")

        mode = config.get("mode", 'paper')
        credentials = config.get("credentials", {})
        options = config.get("options", {})

        rate_limit = options.get("rate_limit", 5)
        rate_limiter = RateLimiter(rate_limit)

        # Build common kwargs
        common_kwargs = {
            "mode": mode,
            "rate_limiter": rate_limiter,
            "logger": logger,
        }

        if broker_type == "crypto":

            exchange = options.get("exchange", "binanceus")
            if not exchange:
                raise ValueError("Missing exchange name for crypto broker")

            return broker_class(
                exchange_name=exchange,
                api_key=credentials.get("api_key", "ert"),
                secret=credentials.get("secret", "4u9io"),
                **common_kwargs
            )

        if broker_type == "oanda":

            return broker_class(
                api_key=credentials.get("api_key", "ert"),
                account_id=credentials.get("account_id", "2345"),
                **common_kwargs
            )
        return None