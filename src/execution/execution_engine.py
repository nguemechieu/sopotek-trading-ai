from __future__ import annotations

from uuid import uuid4

from core.config import ExecutionConfig
from execution.order_manager import ManagedOrder, OrderManager
from execution.smart_router import SmartRouter
from portfolio.capital_allocator import CapitalAllocationPlan


class ExecutionEngine:
    def __init__(
        self,
        broker,
        *,
        router: SmartRouter | None = None,
        order_manager: OrderManager | None = None,
        config: ExecutionConfig | None = None,
    ) -> None:
        self.broker = broker
        self.config = config or ExecutionConfig()
        self.router = router or SmartRouter(
            broker,
            twap_slices=self.config.twap_slices,
            vwap_buckets=self.config.vwap_default_buckets,
        )
        self.order_manager = order_manager or OrderManager()

    def _simulate_quality(self, plan: CapitalAllocationPlan) -> tuple[float, bool]:
        notional = float(plan.target_notional or 0.0)
        slippage_bps = min(self.config.max_slippage_bps, max(0.5, (notional / max(self.config.partial_fill_threshold_notional, 1.0)) * 6.0))
        partial = notional >= self.config.partial_fill_threshold_notional
        return slippage_bps, partial

    async def execute(self, plan: CapitalAllocationPlan, *, price: float, order_type: str = "market", paper_mode: bool = False) -> dict:
        order_id = uuid4().hex
        self.order_manager.register(
            ManagedOrder(
                order_id=order_id,
                symbol=plan.symbol,
                side=plan.side,
                quantity=plan.target_quantity,
                order_type=order_type,
                metadata=dict(plan.metadata or {}),
            )
        )
        slippage_bps, partial = self._simulate_quality(plan)
        expected_price = float(price or 0.0)
        fill_multiplier = (1.0 + (slippage_bps / 10000.0)) if plan.side == "buy" else (1.0 - (slippage_bps / 10000.0))
        fill_price = expected_price * fill_multiplier if expected_price > 0 else expected_price
        filled_quantity = float(plan.target_quantity or 0.0) * (0.7 if partial else 1.0)
        remaining_quantity = max(0.0, float(plan.target_quantity or 0.0) - filled_quantity)

        payload = {
            "id": order_id,
            "symbol": plan.symbol,
            "side": plan.side,
            "amount": float(plan.target_quantity or 0.0),
            "price": expected_price,
            "expected_price": expected_price,
            "type": order_type,
            "params": {},
            "liquidity_score": float((plan.metadata or {}).get("regime", {}).get("liquidity_score", 1.0) or 1.0),
            "strategy_name": plan.strategy_name,
            "metadata": dict(plan.metadata or {}),
        }

        if paper_mode:
            raw = {
                "id": order_id,
                "status": "partially_filled" if partial else "filled",
                "fill_price": fill_price,
                "filled_quantity": filled_quantity,
                "remaining_quantity": remaining_quantity,
                "partial": partial,
                "slippage_bps": slippage_bps,
                "latency_ms": self.config.base_latency_ms,
            }
        else:
            raw = await self.router.execute(payload)
            raw.setdefault("latency_ms", self.config.base_latency_ms)
            raw.setdefault("slippage_bps", slippage_bps)
            raw.setdefault("filled_quantity", raw.get("filled") or payload["amount"])
            raw.setdefault("remaining_quantity", max(0.0, payload["amount"] - float(raw.get("filled_quantity") or 0.0)))
            raw.setdefault("partial", bool(raw.get("remaining_quantity")))

        self.order_manager.update(
            order_id,
            status=str(raw.get("status") or "filled"),
            filled_quantity=float(raw.get("filled_quantity") or 0.0),
            average_price=float(raw.get("fill_price") or raw.get("price") or expected_price or 0.0),
        )
        return raw
