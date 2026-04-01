from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sopotek.core.event_types import EventType
from sopotek.core.models import Candle, PerformanceMetrics, PortfolioSnapshot, TradeFeedback


def _normalize_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1e11:
            numeric = numeric / 1000.0
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _timeframe_to_seconds(timeframe: str) -> int:
    text = str(timeframe or "1m").strip().lower()
    value = int(text[:-1] or 1)
    suffix = text[-1]
    if suffix == "s":
        return value
    if suffix == "m":
        return value * 60
    if suffix == "h":
        return value * 3600
    if suffix == "d":
        return value * 86400
    return 60


@dataclass(slots=True)
class BacktestRunResult:
    final_snapshot: PortfolioSnapshot
    performance: PerformanceMetrics
    feedback_count: int
    processed_events: int
    symbol_count: int


class EventDrivenBacktestEngine:
    def __init__(self, runtime) -> None:
        self.runtime = runtime
        self.performance = PerformanceMetrics()
        self.feedback: list[TradeFeedback] = []
        self.runtime.bus.subscribe(EventType.PERFORMANCE_METRICS, self._on_performance)
        self.runtime.bus.subscribe(EventType.TRADE_FEEDBACK, self._on_feedback)

    async def _on_performance(self, event) -> None:
        metrics = getattr(event, "data", None)
        if metrics is None:
            return
        if not isinstance(metrics, PerformanceMetrics):
            metrics = PerformanceMetrics(**dict(metrics))
        self.performance = metrics

    async def _on_feedback(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        if not isinstance(payload, TradeFeedback):
            payload = TradeFeedback(**dict(payload))
        self.feedback.append(payload)

    async def run(self, candles_by_symbol: dict[str, list[Candle | dict | list | tuple]], *, timeframe: str = "1m") -> BacktestRunResult:
        await self.runtime.bus.publish(
            EventType.BACKTEST_STARTED,
            {"symbols": sorted(candles_by_symbol.keys()), "timeframe": timeframe},
            priority=5,
            source="backtest_engine",
        )
        await self._drain_bus()

        merged: list[Candle] = []
        for symbol, rows in candles_by_symbol.items():
            merged.extend(self._coerce_candles(symbol, rows, timeframe=timeframe))
        merged.sort(key=lambda candle: (candle.end, candle.symbol))

        processed_events = 0
        for candle in merged:
            if hasattr(self.runtime.broker, "update_market_price"):
                self.runtime.broker.update_market_price(candle.symbol, candle.close, timestamp=candle.end)
            await self.runtime.bus.publish(EventType.CANDLE, candle, priority=40, source="backtest_engine")
            await self.runtime.bus.publish(
                EventType.MARKET_TICK,
                {"symbol": candle.symbol, "price": candle.close, "timestamp": candle.end},
                priority=20,
                source="backtest_engine",
            )
            await self._drain_bus()
            processed_events += 2

        await self.runtime.bus.publish(
            EventType.BACKTEST_COMPLETED,
            {"processed_events": processed_events, "symbols": sorted(candles_by_symbol.keys())},
            priority=95,
            source="backtest_engine",
        )
        await self._drain_bus()
        return BacktestRunResult(
            final_snapshot=self.runtime.portfolio_engine.latest_snapshot,
            performance=self.performance,
            feedback_count=len(self.feedback),
            processed_events=processed_events,
            symbol_count=len(candles_by_symbol),
        )

    async def _drain_bus(self) -> None:
        while not self.runtime.bus.queue.empty():
            await self.runtime.bus.dispatch_once()

    def _coerce_candles(self, symbol: str, rows, *, timeframe: str) -> list[Candle]:
        candles: list[Candle] = []
        seconds = _timeframe_to_seconds(timeframe)
        for row in rows or []:
            if isinstance(row, Candle):
                candles.append(row)
                continue
            if isinstance(row, dict):
                timestamp = _normalize_timestamp(row.get("timestamp") or row.get("start") or row.get("end"))
                candles.append(
                    Candle(
                        symbol=str(row.get("symbol") or symbol),
                        timeframe=str(row.get("timeframe") or timeframe),
                        open=float(row.get("open") or 0.0),
                        high=float(row.get("high") or 0.0),
                        low=float(row.get("low") or 0.0),
                        close=float(row.get("close") or 0.0),
                        volume=float(row.get("volume") or 0.0),
                        start=timestamp,
                        end=timestamp + timedelta(seconds=seconds),
                    )
                )
                continue
            timestamp, open_, high, low, close, volume = row[:6]
            start = _normalize_timestamp(timestamp)
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open=float(open_),
                    high=float(high),
                    low=float(low),
                    close=float(close),
                    volume=float(volume),
                    start=start,
                    end=start + timedelta(seconds=seconds),
                )
            )
        return candles

