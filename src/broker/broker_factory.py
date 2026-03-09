from broker.ccxt_broker import CCXTBroker
from broker.oanda_broker import OandaBroker
from broker.alpaca_broker import AlpacaBroker
from broker.paper_broker import PaperBroker
from config.config_validator import ConfigValidator


BROKER_REGISTRY = {
    "crypto": CCXTBroker,
    "forex": OandaBroker,
    "stocks": AlpacaBroker,
    "paper": PaperBroker
}


class BrokerFactory:

    @staticmethod
    def create(config):

        # Validate configuration
        ConfigValidator.validate(config)

        broker_cfg = config.broker

        # Special handling for paper trading
        if broker_cfg.exchange == "paper":
            return PaperBroker(broker_cfg)

        broker_class = BROKER_REGISTRY.get(broker_cfg.type)

        if broker_class is None:
            raise ValueError(
                f"Unsupported broker type: {broker_cfg.type}"
            )

        # Create broker instance
        broker = broker_class(broker_cfg)

        return broker