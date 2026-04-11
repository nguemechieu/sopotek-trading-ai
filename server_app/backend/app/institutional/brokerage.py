from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    FX = "fx"
    EQUITY = "equity"


class BrokerVenue(str, Enum):
    CCXT = "ccxt"
    OANDA = "oanda"
    ALPACA = "alpaca"


@dataclass(frozen=True, slots=True)
class AccountContext:
    account_id: str
    venue: BrokerVenue
    asset_classes: tuple[AssetClass, ...]
    base_currency: str
    buying_power: float
    status: str


@dataclass(frozen=True, slots=True)
class ExecutionIntent:
    account_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    asset_class: AssetClass
    preferred_venue: BrokerVenue | None = None


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    venue: BrokerVenue
    account_id: str
    estimated_latency_ms: float
    fees_bps: float
    expected_slippage_bps: float

    @property
    def composite_cost(self) -> float:
        return self.fees_bps + self.expected_slippage_bps + (self.estimated_latency_ms / 50.0)


class BrokerAdapter(ABC):
    venue: BrokerVenue

    @abstractmethod
    async def submit_order(self, intent: ExecutionIntent) -> str:
        raise NotImplementedError

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def fetch_order(self, broker_order_id: str) -> dict[str, str]:
        raise NotImplementedError


class CCXTBrokerAdapter(BrokerAdapter):
    venue = BrokerVenue.CCXT

    async def submit_order(self, intent: ExecutionIntent) -> str:
        raise NotImplementedError("Wire CCXT order submission here.")

    async def cancel_order(self, broker_order_id: str) -> None:
        raise NotImplementedError("Wire CCXT cancel flow here.")

    async def fetch_order(self, broker_order_id: str) -> dict[str, str]:
        raise NotImplementedError("Wire CCXT order lookup here.")


class OandaBrokerAdapter(BrokerAdapter):
    venue = BrokerVenue.OANDA

    async def submit_order(self, intent: ExecutionIntent) -> str:
        raise NotImplementedError("Wire OANDA order submission here.")

    async def cancel_order(self, broker_order_id: str) -> None:
        raise NotImplementedError("Wire OANDA cancel flow here.")

    async def fetch_order(self, broker_order_id: str) -> dict[str, str]:
        raise NotImplementedError("Wire OANDA order lookup here.")


class AlpacaBrokerAdapter(BrokerAdapter):
    venue = BrokerVenue.ALPACA

    async def submit_order(self, intent: ExecutionIntent) -> str:
        raise NotImplementedError("Wire Alpaca order submission here.")

    async def cancel_order(self, broker_order_id: str) -> None:
        raise NotImplementedError("Wire Alpaca cancel flow here.")

    async def fetch_order(self, broker_order_id: str) -> dict[str, str]:
        raise NotImplementedError("Wire Alpaca order lookup here.")


class SmartOrderRouter:
    """Score venue candidates by latency, fees, and slippage."""

    def build_candidates(
        self,
        intent: ExecutionIntent,
        accounts: tuple[AccountContext, ...],
    ) -> list[RouteCandidate]:
        candidates: list[RouteCandidate] = []
        for account in accounts:
            if account.account_id != intent.account_id:
                continue
            if intent.asset_class not in account.asset_classes:
                continue
            if intent.preferred_venue and account.venue != intent.preferred_venue:
                continue
            baseline = {
                BrokerVenue.CCXT: RouteCandidate(account.venue, account.account_id, 45.0, 9.0, 11.0),
                BrokerVenue.OANDA: RouteCandidate(account.venue, account.account_id, 18.0, 4.0, 5.0),
                BrokerVenue.ALPACA: RouteCandidate(account.venue, account.account_id, 25.0, 2.0, 6.0),
            }
            candidates.append(baseline[account.venue])
        return sorted(candidates, key=lambda candidate: candidate.composite_cost)

    def select_route(
        self,
        intent: ExecutionIntent,
        accounts: tuple[AccountContext, ...],
    ) -> RouteCandidate:
        candidates = self.build_candidates(intent, accounts)
        if not candidates:
            raise ValueError(f"No connected venue supports {intent.asset_class.value} for account {intent.account_id}.")
        return candidates[0]
