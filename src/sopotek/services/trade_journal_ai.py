from __future__ import annotations

import logging
from collections import Counter, deque
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any

from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import TradeFeedback, TradeJournalEntry, TradeJournalSummary
from sopotek.storage.repository import QuantRepository
from storage.trade_repository import TradeRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(payload: Any) -> Any:
    if is_dataclass(payload):
        return _serialize(asdict(payload))
    if isinstance(payload, dict):
        return {str(key): _serialize(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple, deque)):
        return [_serialize(item) for item in payload]
    if isinstance(payload, datetime):
        return payload.astimezone(timezone.utc).isoformat()
    return payload


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


class TradeJournalAIEngine:
    """Auto-analyzes closed trades and produces actionable coaching summaries."""

    def __init__(
        self,
        event_bus: AsyncEventBus,
        *,
        quant_repository: QuantRepository | None = None,
        trade_repository: TradeRepository | None = None,
        exchange_name: str = "paper",
        summary_window: int = 50,
        publish_summary_every: int = 1,
        logger: logging.Logger | None = None,
    ) -> None:
        self.bus = event_bus
        self.quant_repository = quant_repository or QuantRepository()
        self.trade_repository = trade_repository or TradeRepository()
        self.exchange_name = str(exchange_name or "paper")
        self.summary_window = max(5, int(summary_window))
        self.publish_summary_every = max(1, int(publish_summary_every))
        self.logger = logger or logging.getLogger("TradeJournalAIEngine")
        self.entries: deque[TradeJournalEntry] = deque(maxlen=self.summary_window)
        self._feedback_count = 0
        self._rehydrate_recent_entries()

        self.bus.subscribe(EventType.TRADE_FEEDBACK, self._on_trade_feedback)

    async def _on_trade_feedback(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        if not isinstance(payload, TradeFeedback):
            payload = TradeFeedback(**dict(payload))

        entry = self.analyze_trade(payload)
        self.entries.append(entry)
        self.quant_repository.save_trade_journal_entry(entry)
        self._update_trade_repository(entry, payload)
        await self.bus.publish(EventType.TRADE_JOURNAL_ENTRY, entry, priority=92, source="trade_journal_ai")

        self._feedback_count += 1
        if self._feedback_count % self.publish_summary_every == 0:
            summary = self.build_summary()
            self.quant_repository.save_trade_journal_summary(summary)
            await self.bus.publish(EventType.TRADE_JOURNAL_SUMMARY, summary, priority=93, source="trade_journal_ai")

    def analyze_trade(self, feedback: TradeFeedback) -> TradeJournalEntry:
        features = dict(feedback.features or {})
        metadata = dict(feedback.metadata or {})
        side = str(feedback.side or "").lower()
        rsi = _safe_float(features.get("rsi"), 50.0)
        ema_gap = _safe_float(features.get("ema_gap", features.get("ema_fast", 0.0) - features.get("ema_slow", 0.0)))
        volatility = _safe_float(features.get("volatility"), 0.0)
        imbalance = _safe_float(features.get("order_book_imbalance"), 0.0)
        confidence = metadata.get("confidence")
        model_probability = feedback.model_probability
        if model_probability is None:
            model_probability = metadata.get("model_probability")
        market_session = str(metadata.get("market_session") or metadata.get("session") or "").strip().lower()
        high_liquidity = metadata.get("high_liquidity_session")
        close_reason = str(metadata.get("close_reason") or metadata.get("exit_reason") or "").strip()

        trend_aligned = (side == "buy" and ema_gap > 0) or (side == "sell" and ema_gap < 0)
        order_flow_supportive = (side == "buy" and imbalance > 0.1) or (side == "sell" and imbalance < -0.1)
        extended_entry = (side == "buy" and rsi >= 68.0) or (side == "sell" and rsi <= 32.0)
        low_liquidity = (high_liquidity is False) or market_session in {"inactive", "sydney", "tokyo", "closed"}
        high_volatility = volatility >= 0.02
        low_volatility = 0.0 <= volatility <= 0.012

        why_it_lost: list[str] = []
        what_worked: list[str] = []
        what_to_improve: list[str] = []
        tags: list[str] = []

        if feedback.success:
            if trend_aligned:
                what_worked.append("The trade aligned with the prevailing EMA trend.")
                tags.append("trend_aligned")
            if order_flow_supportive:
                what_worked.append("Order-book pressure confirmed the entry direction.")
                tags.append("order_flow_confirmation")
            if model_probability is not None and _safe_float(model_probability) >= 0.7:
                what_worked.append("ML confidence was strong before the trade was taken.")
                tags.append("high_ml_confidence")
            if market_session in {"overlap", "london", "new_york", "regular", "continuous"}:
                what_worked.append(f"The trade executed in a liquid {market_session} session.")
                tags.append(f"session_{market_session}")
            if low_volatility:
                what_worked.append("Volatility stayed controlled after entry.")
                tags.append("controlled_volatility")
            if close_reason:
                what_worked.append(f"Exit management helped preserve gains: {close_reason}.")
            if not what_worked:
                what_worked.append("The setup kept enough edge through entry, management, and exit.")
            if high_volatility:
                what_to_improve.append("Scale out faster when volatility expands, even on winning trades.")
            what_to_improve.append("Keep screening for this confluence and size it according to current volatility.")
        else:
            if not trend_aligned and abs(ema_gap) > 1e-9:
                why_it_lost.append("The trade fought the prevailing EMA trend.")
                what_to_improve.append("Favor setups where trade direction and EMA trend agree.")
                tags.append("counter_trend_loss")
            if extended_entry:
                why_it_lost.append("The entry was stretched on RSI and likely chased price.")
                what_to_improve.append("Wait for a pullback or confirmation instead of entering on extended RSI.")
                tags.append("extended_entry")
            if high_volatility:
                why_it_lost.append("Volatility was elevated and increased reversal risk.")
                what_to_improve.append("Reduce size or tighten filters during high-volatility regimes.")
                tags.append("high_volatility")
            if model_probability is not None and _safe_float(model_probability) < 0.5:
                why_it_lost.append("The trade was taken with weak ML confidence.")
                what_to_improve.append("Raise the ML approval threshold or skip low-probability setups.")
                tags.append("low_ml_confidence")
            if abs(imbalance) >= 0.1 and not order_flow_supportive:
                why_it_lost.append("Order-book imbalance leaned against the position.")
                what_to_improve.append("Require supportive order flow before entering short-term trades.")
                tags.append("adverse_order_flow")
            if low_liquidity:
                why_it_lost.append(f"Liquidity was weaker during the {market_session or 'current'} session.")
                what_to_improve.append("Prioritize regular or overlap sessions where liquidity is deeper.")
                tags.append("low_liquidity")
            if close_reason:
                why_it_lost.append(f"Exit logic flagged deterioration: {close_reason}.")
            if not why_it_lost:
                why_it_lost.append("The original trade thesis did not receive enough market confirmation after entry.")
            if not what_to_improve:
                what_to_improve.append("Tighten entry confirmation and review the thesis before re-entering the same setup.")
            if trend_aligned:
                what_worked.append("Trend context was not the main issue; the loss came from execution quality or confirmation.")
            if order_flow_supportive:
                what_worked.append("Initial order flow support existed, but the follow-through faded after entry.")

        if not feedback.success and not what_worked:
            what_worked.append("Risk containment limited further damage once the setup weakened.")
        if feedback.success and not why_it_lost:
            why_it_lost.append("Loss drivers were not present in this trade.")

        outcome = "Win" if feedback.success else "Loss"
        summary = self._compose_entry_summary(
            feedback=feedback,
            why_it_lost=why_it_lost,
            what_worked=what_worked,
            what_to_improve=what_to_improve,
        )

        return TradeJournalEntry(
            symbol=feedback.symbol,
            strategy_name=feedback.strategy_name,
            side=feedback.side,
            quantity=float(feedback.quantity),
            pnl=float(feedback.pnl),
            success=bool(feedback.success),
            outcome=outcome,
            summary=summary,
            why_it_lost=why_it_lost,
            what_worked=what_worked,
            what_to_improve=what_to_improve,
            tags=sorted(set(tags)),
            confidence=_safe_float(confidence) if confidence not in (None, "") else None,
            model_probability=_safe_float(model_probability) if model_probability not in (None, "") else None,
            metadata={
                **metadata,
                "features": _serialize(features),
                "market_session": market_session or None,
                "high_liquidity_session": high_liquidity,
            },
            timestamp=feedback.timestamp,
        )

    def build_summary(self) -> TradeJournalSummary:
        entries = list(self.entries)
        if not entries:
            return TradeJournalSummary(
                trades_analyzed=0,
                wins=0,
                losses=0,
                win_rate=0.0,
                average_pnl=0.0,
                average_win=0.0,
                average_loss=0.0,
                summary="No closed trades have been analyzed yet.",
                timestamp=_utc_now(),
            )

        wins = sum(1 for entry in entries if entry.success)
        losses = len(entries) - wins
        total_pnl = sum(float(entry.pnl) for entry in entries)
        avg_win = sum(float(entry.pnl) for entry in entries if entry.success) / max(wins, 1)
        avg_loss = sum(float(entry.pnl) for entry in entries if not entry.success) / max(losses, 1)
        loss_counter = Counter(bit for entry in entries if not entry.success for bit in entry.why_it_lost)
        strength_counter = Counter(bit for entry in entries for bit in entry.what_worked)
        improvement_counter = Counter(bit for entry in entries for bit in entry.what_to_improve)

        recurring_loss_patterns = [item for item, _ in loss_counter.most_common(3)]
        recurring_strengths = [item for item, _ in strength_counter.most_common(3)]
        improvement_priorities = [item for item, _ in improvement_counter.most_common(3)]

        summary_text = (
            f"Reviewed {len(entries)} trades with win rate {wins / max(len(entries), 1):.1%}. "
            f"Best edges: {self._format_list(recurring_strengths) or 'not enough winning evidence yet'}. "
            f"Main leaks: {self._format_list(recurring_loss_patterns) or 'no recurring loss pattern detected'}. "
            f"Improve next: {self._format_list(improvement_priorities) or 'keep gathering feedback'}."
        )

        return TradeJournalSummary(
            trades_analyzed=len(entries),
            wins=wins,
            losses=losses,
            win_rate=wins / max(len(entries), 1),
            average_pnl=total_pnl / max(len(entries), 1),
            average_win=avg_win,
            average_loss=avg_loss,
            recurring_loss_patterns=recurring_loss_patterns,
            recurring_strengths=recurring_strengths,
            improvement_priorities=improvement_priorities,
            summary=summary_text,
            metadata={
                "window": self.summary_window,
                "symbols": sorted({entry.symbol for entry in entries}),
                "strategies": sorted({entry.strategy_name for entry in entries}),
            },
            timestamp=_utc_now(),
        )

    def _update_trade_repository(self, entry: TradeJournalEntry, feedback: TradeFeedback) -> None:
        exit_order_id = str((feedback.metadata or {}).get("exit_order_id") or "").strip()
        if not exit_order_id:
            return
        try:
            self.trade_repository.update_trade_journal(
                order_id=exit_order_id,
                exchange=self.exchange_name,
                reason="; ".join(entry.why_it_lost[:2]) if entry.why_it_lost and entry.why_it_lost[0] != "Loss drivers were not present in this trade." else None,
                setup="; ".join(entry.what_worked[:2]) if entry.what_worked else None,
                outcome=entry.outcome,
                lessons="; ".join(entry.what_to_improve[:3]) if entry.what_to_improve else entry.summary,
            )
        except Exception:
            self.logger.exception("Trade journal AI could not update trade_repository for %s", feedback.symbol)

    def _compose_entry_summary(
        self,
        *,
        feedback: TradeFeedback,
        why_it_lost: list[str],
        what_worked: list[str],
        what_to_improve: list[str],
    ) -> str:
        if feedback.success:
            return (
                f"Win on {feedback.symbol}: {what_worked[0]} "
                f"Keep reinforcing this edge. Next improvement: {what_to_improve[0]}"
            )
        return (
            f"Loss on {feedback.symbol}: {why_it_lost[0]} "
            f"Next improvement: {what_to_improve[0]}"
        )

    def _rehydrate_recent_entries(self) -> None:
        try:
            existing = self.quant_repository.load_trade_journal_entries(limit=self.summary_window)
        except Exception:
            self.logger.debug("Trade journal AI could not hydrate previous entries.", exc_info=True)
            return
        for entry in reversed(existing):
            self.entries.append(entry)

    @staticmethod
    def _format_list(items: list[str], *, limit: int = 3) -> str:
        selected = [str(item).strip() for item in list(items or []) if str(item).strip()][:limit]
        return ", ".join(selected)
