from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, select

from sopotek.core.models import FeatureVector, ModelDecision, PerformanceMetrics, TradeFeedback
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
    return json.dumps(payload or {}, sort_keys=True)


def _load_json(payload) -> dict:
    if not payload:
        return {}
    if isinstance(payload, dict):
        return dict(payload)
    return dict(json.loads(payload))


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

