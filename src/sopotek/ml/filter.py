from __future__ import annotations

from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import FeatureVector, ModelDecision, TradeReview
from sopotek.ml.pipeline import TradeOutcomeTrainingPipeline


class MLFilterEngine:
    """Scores approved trades before they reach execution."""

    def __init__(
        self,
        event_bus: AsyncEventBus,
        model_pipeline: TradeOutcomeTrainingPipeline | None = None,
        *,
        threshold: float = 0.55,
        allow_passthrough: bool = True,
    ) -> None:
        self.bus = event_bus
        self.model_pipeline = model_pipeline or TradeOutcomeTrainingPipeline()
        self.threshold = max(0.0, min(1.0, float(threshold)))
        self.allow_passthrough = bool(allow_passthrough)
        self.latest_features: dict[str, FeatureVector] = {}

        self.bus.subscribe(EventType.FEATURE_VECTOR, self._on_feature_vector)
        self.bus.subscribe(EventType.RISK_APPROVED, self._on_risk_approved)

    async def _on_feature_vector(self, event) -> None:
        vector = getattr(event, "data", None)
        if vector is None:
            return
        if not isinstance(vector, FeatureVector):
            vector = FeatureVector(**dict(vector))
        self.latest_features[vector.symbol] = vector

    async def _on_risk_approved(self, event) -> None:
        review = getattr(event, "data", None)
        if review is None:
            return
        if not isinstance(review, TradeReview):
            review = TradeReview(**dict(review))

        vector = self.latest_features.get(review.symbol)
        feature_values = dict((vector.values if vector is not None else {}) or {})
        if not self.model_pipeline.is_fitted:
            approved = self.allow_passthrough
            probability = 0.5
            reason = "passthrough_unfitted_model"
        elif not feature_values:
            approved = self.allow_passthrough
            probability = 0.5
            reason = "passthrough_missing_features" if approved else "missing_features"
        else:
            probability = float(self.model_pipeline.predict_probability(feature_values))
            approved = probability >= self.threshold
            reason = "model_probability_gate"

        decision = ModelDecision(
            symbol=review.symbol,
            strategy_name=review.strategy_name,
            model_name=self.model_pipeline.model_name,
            probability=probability,
            threshold=self.threshold,
            approved=approved,
            side=review.side,
            features=feature_values,
            metadata={"reason": reason},
        )
        await self.bus.publish(EventType.MODEL_SCORE, decision, priority=72, source="ml_filter_engine")

        enriched_review = TradeReview(
            approved=approved,
            symbol=review.symbol,
            side=review.side,
            quantity=review.quantity,
            price=review.price,
            reason=review.reason,
            risk_score=review.risk_score,
            stop_price=review.stop_price,
            take_profit=review.take_profit,
            strategy_name=review.strategy_name,
            metadata={
                **dict(review.metadata),
                "model_name": decision.model_name,
                "model_probability": probability,
                "model_threshold": self.threshold,
                "model_reason": reason,
                "features": feature_values,
            },
            timestamp=review.timestamp,
        )
        event_type = EventType.MODEL_APPROVED if approved else EventType.MODEL_REJECTED
        priority = 74 if approved else 9
        await self.bus.publish(event_type, enriched_review, priority=priority, source="ml_filter_engine")

