from __future__ import annotations

from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import ExecutionReport, FeatureVector, ModelDecision, PerformanceMetrics, TradeFeedback
from sopotek.storage.repository import QuantRepository
from storage.trade_repository import TradeRepository


class QuantPersistenceRecorder:
    """Persists institutional runtime artifacts into the shared SQL database."""

    def __init__(
        self,
        event_bus: AsyncEventBus,
        *,
        quant_repository: QuantRepository | None = None,
        trade_repository: TradeRepository | None = None,
        exchange_name: str = "paper",
    ) -> None:
        self.bus = event_bus
        self.quant_repository = quant_repository or QuantRepository()
        self.trade_repository = trade_repository or TradeRepository()
        self.exchange_name = str(exchange_name or "paper")

        self.bus.subscribe(EventType.FEATURE_VECTOR, self._on_feature_vector)
        self.bus.subscribe(EventType.MODEL_SCORE, self._on_model_score)
        self.bus.subscribe(EventType.PERFORMANCE_METRICS, self._on_performance_metrics)
        self.bus.subscribe(EventType.TRADE_FEEDBACK, self._on_trade_feedback)
        self.bus.subscribe(EventType.EXECUTION_REPORT, self._on_execution_report)

    async def _on_feature_vector(self, event) -> None:
        vector = getattr(event, "data", None)
        if vector is None:
            return
        if not isinstance(vector, FeatureVector):
            vector = FeatureVector(**dict(vector))
        self.quant_repository.save_feature_vector(vector)

    async def _on_model_score(self, event) -> None:
        decision = getattr(event, "data", None)
        if decision is None:
            return
        if not isinstance(decision, ModelDecision):
            decision = ModelDecision(**dict(decision))
        self.quant_repository.save_model_decision(decision)

    async def _on_performance_metrics(self, event) -> None:
        metrics = getattr(event, "data", None)
        if metrics is None:
            return
        if not isinstance(metrics, PerformanceMetrics):
            metrics = PerformanceMetrics(**dict(metrics))
        self.quant_repository.save_performance_metrics(metrics)

    async def _on_trade_feedback(self, event) -> None:
        feedback = getattr(event, "data", None)
        if feedback is None:
            return
        if not isinstance(feedback, TradeFeedback):
            feedback = TradeFeedback(**dict(feedback))
        self.quant_repository.save_trade_feedback(feedback)

    async def _on_execution_report(self, event) -> None:
        report = getattr(event, "data", None)
        if report is None:
            return
        if not isinstance(report, ExecutionReport):
            report = ExecutionReport(**dict(report))
        self.trade_repository.save_or_update_trade(
            symbol=report.symbol,
            side=report.side,
            quantity=report.filled_quantity if report.filled_quantity is not None else report.quantity,
            price=report.fill_price or report.requested_price,
            exchange=self.exchange_name,
            order_id=report.order_id,
            order_type="market",
            status=report.status,
            source="sopotek_v2",
            strategy_name=report.strategy_name,
            expected_price=report.requested_price,
            slippage_bps=report.slippage_bps,
            fee=report.fee,
            confidence=(report.metadata or {}).get("confidence"),
        )

