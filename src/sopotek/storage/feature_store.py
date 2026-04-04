from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(payload: Any) -> Any:
    if is_dataclass(payload):
        return _serialize(asdict(payload))
    if isinstance(payload, dict):
        return {str(key): _serialize(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_serialize(item) for item in payload]
    if isinstance(payload, datetime):
        return payload.astimezone(timezone.utc).isoformat()
    return payload


class FeatureStore:
    """File-backed JSONL store for runtime features, context, and outcomes."""

    STREAM_MAP = {
        EventType.FEATURE_VECTOR: "feature_vectors",
        EventType.ORDER_BOOK: "order_book",
        EventType.TRADE_FEEDBACK: "trade_feedback",
        EventType.MODEL_SCORE: "model_scores",
        EventType.REGIME: "regime",
        EventType.REASONING_DECISION: "reasoning",
        EventType.DECISION_EVENT: "trader_decisions",
        EventType.ALERT_EVENT: "alerts",
        EventType.MOBILE_DASHBOARD_UPDATE: "mobile_dashboard",
        EventType.TRADE_JOURNAL_ENTRY: "trade_journal_entries",
        EventType.TRADE_JOURNAL_SUMMARY: "trade_journal_summaries",
    }

    def __init__(self, event_bus: AsyncEventBus, *, base_dir: str | Path = "data/feature_store") -> None:
        self.bus = event_bus
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        for event_type, stream_name in self.STREAM_MAP.items():
            self.bus.subscribe(event_type, self._build_handler(event_type, stream_name))

    def _build_handler(self, event_type: str, stream_name: str):
        async def handler(event) -> None:
            self.append(stream_name, getattr(event, "data", None), event_type=event_type, source=getattr(event, "source", None))

        return handler

    def append(self, stream_name: str, payload: Any, *, event_type: str, source: str | None = None) -> Path:
        target = self.base_dir / f"{stream_name}.jsonl"
        envelope = {
            "recorded_at": _utc_now().isoformat(),
            "event_type": str(event_type),
            "source": str(source or ""),
            "data": _serialize(payload),
        }
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, sort_keys=True, ensure_ascii=True))
            handle.write("\n")
        return target

    def read(self, stream_name: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        target = self.base_dir / f"{stream_name}.jsonl"
        if not target.exists():
            return []
        rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
        if limit is None:
            return rows
        return rows[-int(limit):]
