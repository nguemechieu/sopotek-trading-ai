from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, select

from sopotek.core.models import (
    FeatureVector,
    ModelDecision,
    PerformanceMetrics,
    TradeFeedback,
    TradeJournalEntry,
    TradeJournalSummary,
)
from storage import database as storage_db


def _utc_naive(value=None):
    timestamp = value or datetime.now(timezone.utc)
    if isinstance(timestamp, str):
        if timestamp.endswith("Z"):
            timestamp = f"{timestamp[:-1]}+00:00"
        timestamp = datetime.fromisoformat(timestamp)
    if isinstance(timestamp, datetime) and timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
    return timestamp


def _dump_json(payload) -> str:
    if payload is None:
        payload = {}
    return json.dumps(payload, sort_keys=True)


def _load_json(payload):
    if not payload:
        return {}
    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, list):
        return list(payload)
    return json.loads(payload)


class QuantFeatureRecord(storage_db.Base):
    __tablename__ = "quant_feature_vectors"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    timeframe = Column(String, index=True)
    strategy_name = Column(String, index=True)
    close = Column(Float)
    values_json = Column(Text)
    metadata_json = Column(Text)
    timestamp = Column(DateTime, default=_utc_naive, index=True)


class ModelScoreRecord(storage_db.Base):
    __tablename__ = "quant_model_scores"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    strategy_name = Column(String, index=True)
    model_name = Column(String, index=True)
    side = Column(String)
    probability = Column(Float)
    threshold = Column(Float)
    approved = Column(Boolean, default=False)
    features_json = Column(Text)
    metadata_json = Column(Text)
    timestamp = Column(DateTime, default=_utc_naive, index=True)


class PerformanceMetricRecord(storage_db.Base):
    __tablename__ = "quant_performance_metrics"

    id = Column(Integer, primary_key=True, index=True)
    total_trades = Column(Integer)
    closed_trades = Column(Integer)
    win_rate = Column(Float)
    realized_pnl = Column(Float)
    unrealized_pnl = Column(Float)
    equity = Column(Float)
    gross_exposure = Column(Float)
    net_exposure = Column(Float)
    max_drawdown_pct = Column(Float)
    sharpe_like = Column(Float)
    symbols_json = Column(Text)
    metadata_json = Column(Text)
    timestamp = Column(DateTime, default=_utc_naive, index=True)


class TradeFeedbackRecord(storage_db.Base):
    __tablename__ = "quant_trade_feedback"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    strategy_name = Column(String, index=True)
    side = Column(String)
    quantity = Column(Float)
    entry_price = Column(Float)
    exit_price = Column(Float)
    pnl = Column(Float)
    success = Column(Boolean, default=False)
    timeframe = Column(String, index=True)
    model_name = Column(String, index=True)
    model_probability = Column(Float)
    features_json = Column(Text)
    metadata_json = Column(Text)
    timestamp = Column(DateTime, default=_utc_naive, index=True)


class TradeJournalEntryRecord(storage_db.Base):
    __tablename__ = "quant_trade_journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    strategy_name = Column(String, index=True)
    side = Column(String)
    quantity = Column(Float)
    pnl = Column(Float)
    success = Column(Boolean, default=False, index=True)
    outcome = Column(String, index=True)
    summary = Column(Text)
    why_it_lost_json = Column(Text)
    what_worked_json = Column(Text)
    what_to_improve_json = Column(Text)
    tags_json = Column(Text)
    confidence = Column(Float)
    model_probability = Column(Float)
    metadata_json = Column(Text)
    timestamp = Column(DateTime, default=_utc_naive, index=True)


class TradeJournalSummaryRecord(storage_db.Base):
    __tablename__ = "quant_trade_journal_summaries"

    id = Column(Integer, primary_key=True, index=True)
    trades_analyzed = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)
    win_rate = Column(Float)
    average_pnl = Column(Float)
    average_win = Column(Float)
    average_loss = Column(Float)
    recurring_loss_patterns_json = Column(Text)
    recurring_strengths_json = Column(Text)
    improvement_priorities_json = Column(Text)
    summary = Column(Text)
    metadata_json = Column(Text)
    timestamp = Column(DateTime, default=_utc_naive, index=True)


class QuantRepository:
    def save_feature_vector(self, feature: FeatureVector | dict) -> QuantFeatureRecord:
        vector = feature if isinstance(feature, FeatureVector) else FeatureVector(**dict(feature))
        row = QuantFeatureRecord(
            symbol=vector.symbol,
            timeframe=vector.timeframe,
            strategy_name=vector.strategy_name,
            close=vector.close,
            values_json=_dump_json(vector.values),
            metadata_json=_dump_json(vector.metadata),
            timestamp=_utc_naive(vector.timestamp),
        )
        with storage_db.SessionLocal() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def save_model_decision(self, decision: ModelDecision | dict) -> ModelScoreRecord:
        score = decision if isinstance(decision, ModelDecision) else ModelDecision(**dict(decision))
        row = ModelScoreRecord(
            symbol=score.symbol,
            strategy_name=score.strategy_name,
            model_name=score.model_name,
            side=score.side,
            probability=score.probability,
            threshold=score.threshold,
            approved=bool(score.approved),
            features_json=_dump_json(score.features),
            metadata_json=_dump_json(score.metadata),
            timestamp=_utc_naive(score.timestamp),
        )
        with storage_db.SessionLocal() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def save_performance_metrics(self, metrics: PerformanceMetrics | dict) -> PerformanceMetricRecord:
        snapshot = metrics if isinstance(metrics, PerformanceMetrics) else PerformanceMetrics(**dict(metrics))
        row = PerformanceMetricRecord(
            total_trades=snapshot.total_trades,
            closed_trades=snapshot.closed_trades,
            win_rate=snapshot.win_rate,
            realized_pnl=snapshot.realized_pnl,
            unrealized_pnl=snapshot.unrealized_pnl,
            equity=snapshot.equity,
            gross_exposure=snapshot.gross_exposure,
            net_exposure=snapshot.net_exposure,
            max_drawdown_pct=snapshot.max_drawdown_pct,
            sharpe_like=snapshot.sharpe_like,
            symbols_json=_dump_json(snapshot.symbols),
            metadata_json=_dump_json(snapshot.metadata),
            timestamp=_utc_naive(snapshot.timestamp),
        )
        with storage_db.SessionLocal() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def save_trade_feedback(self, feedback: TradeFeedback | dict) -> TradeFeedbackRecord:
        trade = feedback if isinstance(feedback, TradeFeedback) else TradeFeedback(**dict(feedback))
        row = TradeFeedbackRecord(
            symbol=trade.symbol,
            strategy_name=trade.strategy_name,
            side=trade.side,
            quantity=trade.quantity,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            pnl=trade.pnl,
            success=bool(trade.success),
            timeframe=trade.timeframe,
            model_name=trade.model_name,
            model_probability=trade.model_probability,
            features_json=_dump_json(trade.features),
            metadata_json=_dump_json(trade.metadata),
            timestamp=_utc_naive(trade.timestamp),
        )
        with storage_db.SessionLocal() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def save_trade_journal_entry(self, entry: TradeJournalEntry | dict) -> TradeJournalEntryRecord:
        journal = entry if isinstance(entry, TradeJournalEntry) else TradeJournalEntry(**dict(entry))
        row = TradeJournalEntryRecord(
            symbol=journal.symbol,
            strategy_name=journal.strategy_name,
            side=journal.side,
            quantity=journal.quantity,
            pnl=journal.pnl,
            success=bool(journal.success),
            outcome=journal.outcome,
            summary=journal.summary,
            why_it_lost_json=_dump_json(journal.why_it_lost),
            what_worked_json=_dump_json(journal.what_worked),
            what_to_improve_json=_dump_json(journal.what_to_improve),
            tags_json=_dump_json(journal.tags),
            confidence=journal.confidence,
            model_probability=journal.model_probability,
            metadata_json=_dump_json(journal.metadata),
            timestamp=_utc_naive(journal.timestamp),
        )
        with storage_db.SessionLocal() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def save_trade_journal_summary(self, summary: TradeJournalSummary | dict) -> TradeJournalSummaryRecord:
        journal = summary if isinstance(summary, TradeJournalSummary) else TradeJournalSummary(**dict(summary))
        row = TradeJournalSummaryRecord(
            trades_analyzed=journal.trades_analyzed,
            wins=journal.wins,
            losses=journal.losses,
            win_rate=journal.win_rate,
            average_pnl=journal.average_pnl,
            average_win=journal.average_win,
            average_loss=journal.average_loss,
            recurring_loss_patterns_json=_dump_json(journal.recurring_loss_patterns),
            recurring_strengths_json=_dump_json(journal.recurring_strengths),
            improvement_priorities_json=_dump_json(journal.improvement_priorities),
            summary=journal.summary,
            metadata_json=_dump_json(journal.metadata),
            timestamp=_utc_naive(journal.timestamp),
        )
        with storage_db.SessionLocal() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def load_feedback(self, *, limit: int | None = None, symbol: str | None = None) -> list[TradeFeedback]:
        with storage_db.SessionLocal() as session:
            stmt = select(TradeFeedbackRecord).order_by(TradeFeedbackRecord.timestamp.asc(), TradeFeedbackRecord.id.asc())
            if symbol:
                stmt = stmt.where(TradeFeedbackRecord.symbol == str(symbol))
            if limit is not None:
                stmt = stmt.limit(int(limit))
            rows = list(session.execute(stmt).scalars().all())
        return [
            TradeFeedback(
                symbol=row.symbol,
                strategy_name=row.strategy_name,
                side=row.side,
                quantity=float(row.quantity or 0.0),
                entry_price=float(row.entry_price or 0.0),
                exit_price=float(row.exit_price or 0.0),
                pnl=float(row.pnl or 0.0),
                success=bool(row.success),
                timeframe=row.timeframe or "1m",
                model_name=row.model_name,
                model_probability=row.model_probability,
                features=_load_json(row.features_json),
                metadata=_load_json(row.metadata_json),
                timestamp=row.timestamp.replace(tzinfo=timezone.utc) if row.timestamp and row.timestamp.tzinfo is None else row.timestamp,
            )
            for row in rows
        ]

    def list_feature_vectors(self, *, limit: int = 100) -> list[QuantFeatureRecord]:
        with storage_db.SessionLocal() as session:
            stmt = select(QuantFeatureRecord).order_by(QuantFeatureRecord.timestamp.desc(), QuantFeatureRecord.id.desc()).limit(int(limit))
            return list(session.execute(stmt).scalars().all())

    def list_model_scores(self, *, limit: int = 100) -> list[ModelScoreRecord]:
        with storage_db.SessionLocal() as session:
            stmt = select(ModelScoreRecord).order_by(ModelScoreRecord.timestamp.desc(), ModelScoreRecord.id.desc()).limit(int(limit))
            return list(session.execute(stmt).scalars().all())

    def list_performance_metrics(self, *, limit: int = 100) -> list[PerformanceMetricRecord]:
        with storage_db.SessionLocal() as session:
            stmt = select(PerformanceMetricRecord).order_by(PerformanceMetricRecord.timestamp.desc(), PerformanceMetricRecord.id.desc()).limit(int(limit))
            return list(session.execute(stmt).scalars().all())

    def load_trade_journal_entries(self, *, limit: int = 100, symbol: str | None = None) -> list[TradeJournalEntry]:
        with storage_db.SessionLocal() as session:
            stmt = select(TradeJournalEntryRecord).order_by(
                TradeJournalEntryRecord.timestamp.desc(),
                TradeJournalEntryRecord.id.desc(),
            )
            if symbol:
                stmt = stmt.where(TradeJournalEntryRecord.symbol == str(symbol))
            stmt = stmt.limit(int(limit))
            rows = list(session.execute(stmt).scalars().all())
        return [
            TradeJournalEntry(
                symbol=row.symbol,
                strategy_name=row.strategy_name,
                side=row.side,
                quantity=float(row.quantity or 0.0),
                pnl=float(row.pnl or 0.0),
                success=bool(row.success),
                outcome=row.outcome or ("Win" if row.success else "Loss"),
                summary=row.summary or "",
                why_it_lost=list(_load_json(row.why_it_lost_json) or []),
                what_worked=list(_load_json(row.what_worked_json) or []),
                what_to_improve=list(_load_json(row.what_to_improve_json) or []),
                tags=list(_load_json(row.tags_json) or []),
                confidence=row.confidence,
                model_probability=row.model_probability,
                metadata=_load_json(row.metadata_json),
                timestamp=row.timestamp.replace(tzinfo=timezone.utc) if row.timestamp and row.timestamp.tzinfo is None else row.timestamp,
            )
            for row in rows
        ]

    def load_trade_journal_summaries(self, *, limit: int = 20) -> list[TradeJournalSummary]:
        with storage_db.SessionLocal() as session:
            stmt = select(TradeJournalSummaryRecord).order_by(
                TradeJournalSummaryRecord.timestamp.desc(),
                TradeJournalSummaryRecord.id.desc(),
            ).limit(int(limit))
            rows = list(session.execute(stmt).scalars().all())
        return [
            TradeJournalSummary(
                trades_analyzed=int(row.trades_analyzed or 0),
                wins=int(row.wins or 0),
                losses=int(row.losses or 0),
                win_rate=float(row.win_rate or 0.0),
                average_pnl=float(row.average_pnl or 0.0),
                average_win=float(row.average_win or 0.0),
                average_loss=float(row.average_loss or 0.0),
                recurring_loss_patterns=list(_load_json(row.recurring_loss_patterns_json) or []),
                recurring_strengths=list(_load_json(row.recurring_strengths_json) or []),
                improvement_priorities=list(_load_json(row.improvement_priorities_json) or []),
                summary=row.summary or "",
                metadata=_load_json(row.metadata_json),
                timestamp=row.timestamp.replace(tzinfo=timezone.utc) if row.timestamp and row.timestamp.tzinfo is None else row.timestamp,
            )
            for row in rows
        ]

