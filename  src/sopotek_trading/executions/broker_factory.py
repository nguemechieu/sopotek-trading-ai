from time import sleep
import ccxt
from sopotek_trading.executions.ccxt_adapter import CCXTAdapter


class BrokerFactory:

    @staticmethod
    def create(exchange_name, api_key, secret, password=None):
        return CCXTAdapter(
            exchange_name=exchange_name,
            api_key=api_key,
            secret=secret,
            password=password
        )

    @staticmethod
    def safe_execute(func, retries=3, base_delay=1):
        """
        Executes a function with retry logic and exponential backoff.
        Designed for CCXT exchange calls.
        """

        for attempt in range(retries):
            try:
                return func()

            except ccxt.RateLimitExceeded as e:
                # Rate limit → longer wait
                if attempt == retries - 1:
                    raise
                sleep(base_delay * (2 ** attempt) * 2)
            except ccxt.NetworkError as e:
                # Network issues → retry
                if attempt == retries - 1:
                    raise
                sleep(base_delay * (2 ** attempt))

            except ccxt.AuthenticationError:
                # Do NOT retry auth errors
                raise

            except ccxt.ExchangeError as e:
                # Exchange rejected request (invalid order, etc.)
                raise

            except Exception:
                # Unknown exception
                if attempt == retries - 1:
                    raise
                sleep(base_delay * (2 ** attempt))

        return None