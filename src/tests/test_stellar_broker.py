import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from broker.broker_factory import BrokerFactory
from broker.stellar_broker import StellarBroker
from config.config import AppConfig, BrokerConfig, RiskConfig, SystemConfig


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    async def json(self):
        return self.payload


class FakeStellarSession:
    def __init__(self):
        self.closed = False

    def request(self, method, url, params=None, json=None):
        if url.endswith("/accounts/GPUB"):
            return FakeResponse(
                {
                    "id": "GPUB",
                    "balances": [
                        {"asset_type": "native", "balance": "100.0", "selling_liabilities": "10.0"},
                        {
                            "asset_type": "credit_alphanum4",
                            "asset_code": "USDC",
                            "asset_issuer": "GUSDC",
                            "balance": "250.0",
                            "selling_liabilities": "25.0",
                        },
                    ],
                }
            )

        if url.endswith("/order_book"):
            return FakeResponse(
                {
                    "bids": [{"price": "0.0990", "amount": "120.0"}],
                    "asks": [{"price": "0.1010", "amount": "100.0"}],
                }
            )

        if url.endswith("/trades"):
            return FakeResponse(
                {
                    "_embedded": {
                        "records": [
                            {
                                "price": {"n": 101, "d": 1000},
                                "base_amount": "10.0",
                                "counter_amount": "1.01",
                                "base_asset_type": "native",
                                "counter_asset_type": "credit_alphanum4",
                                "counter_asset_code": "USDC",
                            }
                        ]
                    }
                }
            )

        if url.endswith("/trade_aggregations"):
            return FakeResponse(
                {
                    "_embedded": {
                        "records": [
                            {
                                "timestamp": 1700000000000,
                                "open": "0.098",
                                "high": "0.102",
                                "low": "0.097",
                                "close": "0.101",
                                "base_volume": "500.0",
                            }
                        ]
                    }
                }
            )

        if url.endswith("/accounts/GPUB/offers"):
            return FakeResponse(
                {
                    "_embedded": {
                        "records": [
                            {
                                "id": "777",
                                "price": "0.1000000",
                                "amount": "10.0",
                                "selling": {
                                    "asset_type": "credit_alphanum4",
                                    "asset_code": "USDC",
                                    "asset_issuer": "GUSDC",
                                },
                                "buying": {"asset_type": "native"},
                            }
                        ]
                    }
                }
            )

        if url.endswith("/accounts/GPUB/trades"):
            return FakeResponse({"_embedded": {"records": []}})

        if url.rstrip("/") == "https://horizon-testnet.stellar.org":
            return FakeResponse({"core_latest_ledger": 1})

        raise AssertionError(f"Unhandled Stellar URL: {method} {url}")

    async def close(self):
        self.closed = True


class FakeSdkAsset:
    def __init__(self, code, issuer=None):
        self.code = code
        self.issuer = issuer

    @classmethod
    def native(cls):
        return cls("XLM", None)


class FakeKeypair:
    @classmethod
    def from_secret(cls, secret):
        instance = cls()
        instance.secret = secret
        return instance


class FakeNetwork:
    TESTNET_NETWORK_PASSPHRASE = "TESTNET"
    PUBLIC_NETWORK_PASSPHRASE = "PUBLIC"


class FakeBuiltTransaction:
    def __init__(self, operations):
        self.operations = operations
        self.signed_with = None

    def sign(self, signer):
        self.signed_with = signer


class FakeTransactionBuilder:
    def __init__(self, source_account, network_passphrase, base_fee):
        self.source_account = source_account
        self.network_passphrase = network_passphrase
        self.base_fee = base_fee
        self.operations = []

    def append_manage_buy_offer_op(self, **kwargs):
        self.operations.append({"kind": "manage_buy", **kwargs})
        return self

    def append_manage_sell_offer_op(self, **kwargs):
        self.operations.append({"kind": "manage_sell", **kwargs})
        return self

    def set_timeout(self, seconds):
        self.timeout = seconds
        return self

    def build(self):
        return FakeBuiltTransaction(self.operations)


class FakeServerAsync:
    last_transaction = None

    def __init__(self, horizon_url=None, client=None):
        self.horizon_url = horizon_url
        self.client = client

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def load_account(self, public_key):
        return {"account_id": public_key}

    async def submit_transaction(self, transaction):
        FakeServerAsync.last_transaction = transaction
        return {"hash": "stellar-tx"}


def test_broker_factory_routes_stellar_exchange(monkeypatch):
    import broker.broker_factory as broker_factory_module

    monkeypatch.setattr(broker_factory_module, "StellarBroker", lambda cfg: ("stellar", cfg.exchange))

    config = AppConfig(
        broker=BrokerConfig(type="crypto", exchange="stellar", api_key="GPUB", secret="SSEC"),
        risk=RiskConfig(),
        system=SystemConfig(),
        strategy="LSTM",
    )

    broker = BrokerFactory.create(config)
    assert broker == ("stellar", "stellar")


def test_stellar_broker_normalizes_market_data_and_orders(monkeypatch):
    import broker.stellar_broker as stellar_module

    monkeypatch.setattr(stellar_module.aiohttp, "ClientSession", FakeStellarSession)
    monkeypatch.setattr(stellar_module, "Asset", FakeSdkAsset)
    monkeypatch.setattr(stellar_module, "Keypair", FakeKeypair)
    monkeypatch.setattr(stellar_module, "Network", FakeNetwork)
    monkeypatch.setattr(stellar_module, "TransactionBuilder", FakeTransactionBuilder)
    monkeypatch.setattr(stellar_module, "ServerAsync", FakeServerAsync)
    monkeypatch.setattr(stellar_module, "AiohttpClient", lambda: object())

    async def scenario():
        broker = StellarBroker(
            SimpleNamespace(
                api_key="GPUB",
                secret="SSEC",
                mode="paper",
                params={"quote_assets": ["USDC", "XLM"]},
            )
        )

        await broker.connect()

        symbols = await broker.fetch_symbols()
        assert "XLM/USDC" in symbols
        assert "USDC/XLM" not in symbols

        ticker = await broker.fetch_ticker("XLM/USDC")
        assert ticker["bid"] == 0.099
        assert ticker["ask"] == 0.101
        assert round(ticker["last"], 3) == 0.101

        candles = await broker.fetch_ohlcv("XLM/USDC", timeframe="1h", limit=1)
        assert candles[0][1:5] == [0.098, 0.102, 0.097, 0.101]

        balances = await broker.fetch_balance()
        assert balances["free"]["XLM"] == 90.0
        assert balances["free"]["USDC"] == 225.0

        orders = await broker.fetch_open_orders()
        assert orders[0]["symbol"] == "XLM/USDC"
        assert orders[0]["side"] == "buy"

        created = await broker.create_order("XLM/USDC", "buy", 15, type="limit", price=0.11)
        assert created["id"] == "stellar-tx"
        assert FakeServerAsync.last_transaction.operations[0]["kind"] == "manage_buy"
        assert FakeServerAsync.last_transaction.operations[0]["price"] == "0.1100000"

        canceled = await broker.cancel_order("777")
        assert canceled["status"] == "canceled"
        assert FakeServerAsync.last_transaction.operations[0]["kind"] == "manage_sell"
        assert FakeServerAsync.last_transaction.operations[0]["amount"] == "0"

        await broker.close()

    asyncio.run(scenario())
