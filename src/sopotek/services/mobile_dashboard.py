from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import (
    AlertEvent,
    ExecutionReport,
    MobileDashboardSnapshot,
    PerformanceMetrics,
    PortfolioSnapshot,
    PositionUpdate,
    TradeJournalSummary,
    TraderDecision,
)


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


class MobileDashboardService:
    """Maintains a mobile-friendly runtime snapshot and alert feed on disk."""

    def __init__(
        self,
        event_bus: AsyncEventBus,
        *,
        base_dir: str | Path = "data/mobile_dashboard",
        max_alerts: int = 100,
    ) -> None:
        self.bus = event_bus
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_alerts = max(10, int(max_alerts))
        self._temp_write_token = f"{id(self):x}"
        self.positions: dict[str, dict[str, Any]] = {}
        self.recent_alerts: deque[dict[str, Any]] = deque(maxlen=self.max_alerts)
        self.snapshot = MobileDashboardSnapshot()

        self.bus.subscribe(EventType.ALERT_EVENT, self._on_alert)
        self.bus.subscribe(EventType.PORTFOLIO_SNAPSHOT, self._on_portfolio_snapshot)
        self.bus.subscribe(EventType.POSITION_UPDATE, self._on_position_update)
        self.bus.subscribe(EventType.PERFORMANCE_METRICS, self._on_performance_metrics)
        self.bus.subscribe(EventType.DECISION_EVENT, self._on_decision_event)
        self.bus.subscribe(EventType.EXECUTION_REPORT, self._on_execution_report)
        self.bus.subscribe(EventType.TRADE_JOURNAL_SUMMARY, self._on_trade_journal_summary)
        self._persist_snapshot()

    async def _on_alert(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        if not isinstance(payload, AlertEvent):
            payload = AlertEvent(**dict(payload))
        serialized = _serialize(payload)
        self.recent_alerts.appendleft(serialized)
        self.snapshot.latest_alert = serialized
        self.snapshot.alerts = list(self.recent_alerts)
        self.snapshot.updated_at = _utc_now()
        self._append_jsonl("alerts.jsonl", serialized)
        self._persist_snapshot()
        await self._publish_update()

    async def _on_portfolio_snapshot(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        if not isinstance(payload, PortfolioSnapshot):
            payload = PortfolioSnapshot(**dict(payload))
        self.snapshot.cash = float(payload.cash)
        self.snapshot.equity = float(payload.equity)
        self.snapshot.realized_pnl = float(payload.realized_pnl)
        self.snapshot.unrealized_pnl = float(payload.unrealized_pnl)
        self.snapshot.drawdown_pct = float(payload.drawdown_pct)
        self.positions = {
            str(symbol): _serialize(position)
            for symbol, position in dict(payload.positions).items()
            if abs(float(getattr(position, "quantity", 0.0))) > 1e-12
        }
        self.snapshot.positions = list(self.positions.values())
        self.snapshot.open_positions = len(self.snapshot.positions)
        self.snapshot.updated_at = _utc_now()
        self._persist_snapshot()
        await self._publish_update()

    async def _on_position_update(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        if not isinstance(payload, PositionUpdate):
            payload = PositionUpdate(**dict(payload))
        if abs(float(payload.quantity)) <= 1e-12:
            self.positions.pop(payload.symbol, None)
        else:
            self.positions[payload.symbol] = _serialize(payload)
        self.snapshot.positions = list(self.positions.values())
        self.snapshot.open_positions = len(self.snapshot.positions)
        self.snapshot.updated_at = _utc_now()
        self._persist_snapshot()
        await self._publish_update()

    async def _on_performance_metrics(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        if not isinstance(payload, PerformanceMetrics):
            payload = PerformanceMetrics(**dict(payload))
        self.snapshot.latest_performance = _serialize(payload)
        self.snapshot.equity = float(payload.equity)
        self.snapshot.realized_pnl = float(payload.realized_pnl)
        self.snapshot.unrealized_pnl = float(payload.unrealized_pnl)
        self.snapshot.updated_at = _utc_now()
        self._persist_snapshot()
        await self._publish_update()

    async def _on_decision_event(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        if not isinstance(payload, TraderDecision):
            payload = TraderDecision(**dict(payload))
        self.snapshot.latest_decision = _serialize(payload)
        self.snapshot.updated_at = _utc_now()
        self._persist_snapshot()
        await self._publish_update()

    async def _on_execution_report(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        if not isinstance(payload, ExecutionReport):
            payload = ExecutionReport(**dict(payload))
        self.snapshot.latest_execution = _serialize(payload)
        self.snapshot.updated_at = _utc_now()
        self._persist_snapshot()
        await self._publish_update()

    async def _on_trade_journal_summary(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        if not isinstance(payload, TradeJournalSummary):
            payload = TradeJournalSummary(**dict(payload))
        self.snapshot.latest_trade_journal_summary = _serialize(payload)
        self.snapshot.updated_at = _utc_now()
        self._persist_snapshot()
        await self._publish_update()

    def read_snapshot(self) -> dict[str, Any]:
        return _serialize(self.snapshot)

    def _persist_snapshot(self) -> None:
        payload = self.read_snapshot()
        self._write_json("snapshot.json", payload)
        self._write_json(
            "summary.json",
            {
                "status": payload["status"],
                "cash": payload["cash"],
                "equity": payload["equity"],
                "realized_pnl": payload["realized_pnl"],
                "unrealized_pnl": payload["unrealized_pnl"],
                "drawdown_pct": payload["drawdown_pct"],
                "open_positions": payload["open_positions"],
                "latest_alert": payload["latest_alert"],
                "latest_decision": payload["latest_decision"],
                "latest_execution": payload["latest_execution"],
                "latest_trade_journal_summary": payload["latest_trade_journal_summary"],
                "updated_at": payload["updated_at"],
            },
        )

    def _write_json(self, filename: str, payload: dict[str, Any]) -> Path:
        target = self.base_dir / filename
        temp = target.with_name(f"{target.name}.{self._temp_write_token}.tmp")
        serialized = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
        last_error: PermissionError | None = None
        for attempt in range(5):
            try:
                temp.write_text(serialized, encoding="utf-8")
                temp.replace(target)
                return target
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.05 * (attempt + 1))
            finally:
                try:
                    if temp.exists():
                        temp.unlink()
                except OSError:
                    pass
        try:
            target.write_text(serialized, encoding="utf-8")
        except PermissionError:
            if last_error is not None:
                raise last_error
            raise
        return target

    def _append_jsonl(self, filename: str, payload: dict[str, Any]) -> Path:
        target = self.base_dir / filename
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=True))
            handle.write("\n")
        return target

    async def _publish_update(self) -> None:
        await self.bus.publish(EventType.MOBILE_DASHBOARD_UPDATE, self.snapshot, priority=88, source="mobile_dashboard")
