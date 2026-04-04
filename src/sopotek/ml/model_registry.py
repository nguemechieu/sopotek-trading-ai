from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class RegisteredModel:
    name: str
    path: str
    created_at: str = field(default_factory=_utcnow_iso)
    feature_columns: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelRegistry:
    """File-backed registry for trained Sopotek ML models."""

    def __init__(self, root: str | Path = "data/models", *, index_name: str = "registry.json") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / index_name

    def register(
        self,
        name: str,
        model_path: str | Path,
        *,
        feature_columns: list[str] | None = None,
        metrics: dict[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
        set_active: bool = True,
    ) -> RegisteredModel:
        entry = RegisteredModel(
            name=str(name or "").strip() or "trade_success_model",
            path=str(Path(model_path).resolve()),
            feature_columns=list(feature_columns or []),
            metrics=dict(metrics or {}),
            metadata=dict(metadata or {}),
        )
        index = self._load_index()
        index.setdefault("models", {})
        index["models"][entry.name] = asdict(entry)
        if set_active:
            index["active"] = entry.name
        self._write_index(index)
        return entry

    def get(self, name: str = "latest") -> RegisteredModel | None:
        index = self._load_index()
        models = dict(index.get("models") or {})
        lookup = str(name or "latest").strip() or "latest"
        if lookup == "latest":
            lookup = str(index.get("active") or "").strip()
        payload = models.get(lookup)
        return RegisteredModel(**payload) if isinstance(payload, dict) else None

    def activate(self, name: str) -> RegisteredModel | None:
        entry = self.get(name)
        if entry is None:
            return None
        index = self._load_index()
        index["active"] = entry.name
        self._write_index(index)
        return entry

    def list(self) -> list[RegisteredModel]:
        index = self._load_index()
        models = dict(index.get("models") or {})
        return [RegisteredModel(**payload) for payload in models.values() if isinstance(payload, dict)]

    def resolve_path(self, name: str = "latest") -> Path | None:
        entry = self.get(name)
        return Path(entry.path) if entry is not None else None

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"active": None, "models": {}}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {"active": None, "models": {}}
        if not isinstance(payload, dict):
            return {"active": None, "models": {}}
        payload.setdefault("active", None)
        payload.setdefault("models", {})
        return payload

    def _write_index(self, payload: dict[str, Any]) -> None:
        self.index_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
