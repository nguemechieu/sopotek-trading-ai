from time import sleep
import ccxt
import logging
from ccxt_adapter import CCXTAdapter


logger = logging.getLogger(__name__)


class BrokerFactory:

    # ----------------------------------------
    # Create Broker Instance
    # ----------------------------------------
    @staticmethod
    def create(exchange_name, api_key, secret, password=None, sandbox=False):

        if not hasattr(ccxt, exchange_name):
            raise ValueError(f"Exchange '{exchange_name}' not supported by CCXT")

        broker = CCXTAdapter(
            exchange_name=exchange_name,
            api_key=api_key,
            secret=secret,
            password=password,
            sandbox=sandbox
        )

        # Validate connection immediately
        BrokerFactory.safe_execute(lambda: broker.exchange.load_markets())

        return broker

    # ----------------------------------------
    # Safe Execution Wrapper
    # ----------------------------------------
    @staticmethod
    def safe_execute(func, retries=3, base_delay=1):

        for attempt in range(retries):
            try:
                return func()

            except ccxt.RateLimitExceeded as e:
                logger.warning(f"Rate limit hit. Retry {attempt+1}/{retries}")
                if attempt == retries - 1:
                    raise
                sleep(base_delay * (2 ** attempt) * 2)

            except ccxt.NetworkError as e:
                logger.warning(f"Network error. Retry {attempt+1}/{retries}")
                if attempt == retries - 1:
                    raise
                sleep(base_delay * (2 ** attempt))

            except ccxt.AuthenticationError:
                logger.error("Authentication failed. Check API credentials.")
                raise

            except ccxt.ExchangeError as e:
                logger.error(f"Exchange rejected request: {str(e)}")
                raise

            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                if attempt == retries - 1:
                    raise
                sleep(base_delay * (2 ** attempt))

        return None

    # ----------------------------------------
    # Health Check Utility
    # ----------------------------------------
    @staticmethod
    def ping(broker):
        try:
            BrokerFactory.safe_execute(lambda: broker.exchange.fetch_time())
            return True
        except Exception:
            return False

    # ----------------------------------------
    # Unified Order Wrapper
    # ----------------------------------------
    @staticmethod
    def place_order_safe(broker, symbol, side, amount, order_type="market", price=None):
        return BrokerFactory.safe_execute(
            lambda: broker.place_order(
                symbol=symbol,
                side=side,
                amount=amount,
                order_type=order_type,
                price=price
            )
        )

    # ----------------------------------------
    # Unified Balance Wrapper
    # ----------------------------------------
    @staticmethod
    def get_balance_safe(broker):
        return BrokerFactory.safe_execute(
            lambda: broker.get_balance()
        )

    # ----------------------------------------
    # Unified Order Fetch Wrapper
    # ----------------------------------------
    @staticmethod
    def fetch_order_safe(broker, order_id, symbol):
        return BrokerFactory.safe_execute(
            lambda: broker.fetch_order(order_id, symbol)
        )