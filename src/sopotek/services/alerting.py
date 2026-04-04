from __future__ import annotations

import asyncio
import logging
import smtplib
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any
from uuid import uuid4

import aiohttp

from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import AlertEvent, ExecutionReport, ModelDecision, ProfitProtectionDecision, TraderDecision


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


def _severity_rank(severity: str) -> int:
    return {"debug": 10, "info": 20, "warning": 30, "critical": 40}.get(str(severity or "info").lower(), 20)


class BaseAlertChannel:
    name = "base"

    @property
    def enabled(self) -> bool:
        return True

    async def send(self, alert: AlertEvent) -> bool:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class EmailAlertChannel(BaseAlertChannel):
    name = "email"

    def __init__(
        self,
        *,
        host: str = "",
        port: int = 587,
        username: str = "",
        password: str = "",
        from_addr: str = "",
        to_addrs: list[str] | None = None,
        use_starttls: bool = True,
        timeout: float = 15.0,
    ) -> None:
        self.host = str(host or "").strip()
        self.port = int(port)
        self.username = str(username or "").strip()
        self.password = str(password or "")
        self.from_addr = str(from_addr or "").strip()
        self.to_addrs = [str(addr).strip() for addr in list(to_addrs or []) if str(addr).strip()]
        self.use_starttls = bool(use_starttls)
        self.timeout = float(timeout)

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.from_addr and self.to_addrs)

    async def send(self, alert: AlertEvent) -> bool:
        if not self.enabled:
            return False
        await asyncio.to_thread(self._send_sync, alert)
        return True

    def _send_sync(self, alert: AlertEvent) -> None:
        message = EmailMessage()
        message["Subject"] = f"[Sopotek][{str(alert.severity).upper()}] {alert.title}"
        message["From"] = self.from_addr
        message["To"] = ", ".join(self.to_addrs)
        message.set_content(
            "\n".join(
                [
                    f"Severity: {alert.severity}",
                    f"Category: {alert.category}",
                    f"Event Type: {alert.event_type}",
                    f"Symbol: {alert.symbol or '-'}",
                    f"Action: {alert.action or '-'}",
                    "",
                    alert.message,
                ]
            )
        )
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
            if self.use_starttls:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(message)


class WebhookPushChannel(BaseAlertChannel):
    name = "push"

    def __init__(
        self,
        *,
        endpoint_url: str = "",
        auth_token: str = "",
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.endpoint_url = str(endpoint_url or "").strip()
        self.auth_token = str(auth_token or "").strip()
        self.headers = {str(key): str(value) for key, value in dict(headers or {}).items()}
        self.timeout = float(timeout)
        self._session: aiohttp.ClientSession | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint_url)

    async def send(self, alert: AlertEvent) -> bool:
        if not self.enabled:
            return False
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        headers = dict(self.headers)
        if self.auth_token:
            headers.setdefault("Authorization", f"Bearer {self.auth_token}")
        payload = {
            "alert_id": alert.alert_id,
            "title": alert.title,
            "message": alert.message,
            "severity": alert.severity,
            "category": alert.category,
            "event_type": alert.event_type,
            "symbol": alert.symbol,
            "action": alert.action,
            "metadata": _serialize(alert.metadata),
            "timestamp": alert.timestamp.astimezone(timezone.utc).isoformat(),
        }
        async with self._session.post(self.endpoint_url, json=payload, headers=headers) as response:
            return 200 <= response.status < 300

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None


class AlertingEngine:
    """Normalizes runtime events into actionable alerts and dispatches them."""

    def __init__(
        self,
        event_bus: AsyncEventBus,
        *,
        email_config: dict[str, Any] | None = None,
        push_config: dict[str, Any] | None = None,
        external_channels: list[BaseAlertChannel] | None = None,
        minimum_severity: str = "info",
        alert_cooldown_seconds: float = 30.0,
        logger: logging.Logger | None = None,
    ) -> None:
        self.bus = event_bus
        self.logger = logger or logging.getLogger("AlertingEngine")
        self.minimum_severity = str(minimum_severity or "info").lower()
        self.alert_cooldown_seconds = max(0.0, float(alert_cooldown_seconds))
        self._last_alert_at: dict[str, datetime] = {}
        self.channels: list[BaseAlertChannel] = []
        if email_config:
            self.channels.append(EmailAlertChannel(**dict(email_config)))
        if push_config:
            self.channels.append(WebhookPushChannel(**dict(push_config)))
        self.channels.extend(list(external_channels or []))

        self.bus.subscribe(EventType.EXECUTION_REPORT, self._on_execution_report)
        self.bus.subscribe(EventType.DECISION_EVENT, self._on_decision_event)
        self.bus.subscribe(EventType.RISK_ALERT, self._on_risk_alert)
        self.bus.subscribe(EventType.PROFIT_PROTECTION_DECISION, self._on_profit_protection_decision)
        self.bus.subscribe(EventType.MODEL_REJECTED, self._on_model_rejected)

    async def close(self) -> None:
        await asyncio.gather(*(channel.close() for channel in self.channels), return_exceptions=True)

    async def _on_execution_report(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        if not isinstance(payload, ExecutionReport):
            payload = ExecutionReport(**dict(payload))
        alert = self._build_execution_alert(payload)
        if alert is not None:
            await self._emit(alert)

    async def _on_decision_event(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        if not isinstance(payload, TraderDecision):
            payload = TraderDecision(**dict(payload))
        alert = self._build_decision_alert(payload)
        if alert is not None:
            await self._emit(alert)

    async def _on_risk_alert(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        data = dict(payload if isinstance(payload, dict) else {})
        alert = AlertEvent(
            alert_id=uuid4().hex,
            title="Risk alert",
            message=str(data.get("message") or data.get("reason") or "Risk controls raised an alert."),
            severity=str(data.get("severity") or "warning").lower(),
            category="risk",
            event_type=EventType.RISK_ALERT,
            symbol=str(data.get("symbol") or "").strip() or None,
            action=str(data.get("action") or "").strip() or None,
            metadata=data,
        )
        await self._emit(alert)

    async def _on_profit_protection_decision(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        if not isinstance(payload, ProfitProtectionDecision):
            payload = ProfitProtectionDecision(**dict(payload))
        if str(payload.action or "").upper() not in {"REDUCE", "EXIT"}:
            return
        severity = "warning" if str(payload.action).upper() == "REDUCE" else "critical"
        alert = AlertEvent(
            alert_id=uuid4().hex,
            title=f"Profit protection {str(payload.action).upper()}",
            message=str(payload.reason or "Profit protection adjusted the open position."),
            severity=severity,
            category="profit_protection",
            event_type=EventType.PROFIT_PROTECTION_DECISION,
            symbol=payload.symbol,
            action=str(payload.action).upper(),
            metadata=_serialize(payload),
        )
        await self._emit(alert)

    async def _on_model_rejected(self, event) -> None:
        payload = getattr(event, "data", None)
        if payload is None:
            return
        if not isinstance(payload, ModelDecision):
            payload = ModelDecision(**dict(payload))
        alert = AlertEvent(
            alert_id=uuid4().hex,
            title="ML filter rejected trade",
            message=(
                f"{payload.strategy_name} rejected on {payload.symbol}: "
                f"probability={payload.probability:.2f}, threshold={payload.threshold:.2f}."
            ),
            severity="warning",
            category="model",
            event_type=EventType.MODEL_REJECTED,
            symbol=payload.symbol,
            strategy_name=payload.strategy_name,
            metadata=_serialize(payload),
        )
        await self._emit(alert)

    def _build_execution_alert(self, report: ExecutionReport) -> AlertEvent | None:
        status = str(report.status or "").strip().lower()
        if not status:
            return None
        if status == "filled":
            title = "Order filled"
            severity = "info"
        elif status in {"partial", "partially_filled"} or report.partial:
            title = "Order partially filled"
            severity = "warning"
        elif status in {"failed", "rejected_market_hours"}:
            title = "Order failed"
            severity = "critical"
        else:
            title = f"Order {status.replace('_', ' ')}"
            severity = "info"
        message = (
            f"{report.side.upper()} {report.symbol} {report.quantity:.4f} status={report.status} "
            f"requested_price={report.requested_price} fill_price={report.fill_price}."
        )
        if report.metadata.get("error"):
            message += f" Reason: {report.metadata['error']}"
        return AlertEvent(
            alert_id=uuid4().hex,
            title=title,
            message=message,
            severity=severity,
            category="execution",
            event_type=EventType.EXECUTION_REPORT,
            symbol=report.symbol,
            strategy_name=report.strategy_name,
            action=str(report.side).upper(),
            metadata=_serialize(report),
        )

    def _build_decision_alert(self, decision: TraderDecision) -> AlertEvent | None:
        action = str(decision.action or "").upper()
        if action == "HOLD":
            return None
        if action == "SKIP" and not any(
            marker in set(decision.applied_constraints)
            for marker in {"max_drawdown", "market_hours", "ml_skip", "trade_frequency"}
        ):
            return None
        severity = "info"
        if action == "SKIP":
            severity = "warning"
        title = f"Trader decision {action}"
        message = (
            f"{action} {decision.symbol} via {decision.selected_strategy or 'n/a'} "
            f"(confidence={decision.confidence:.2f}, quantity={decision.quantity:.4f}). {decision.reasoning}"
        )
        return AlertEvent(
            alert_id=uuid4().hex,
            title=title,
            message=message,
            severity=severity,
            category="decision",
            event_type=EventType.DECISION_EVENT,
            symbol=decision.symbol,
            strategy_name=decision.selected_strategy,
            action=action,
            metadata=_serialize(decision),
        )

    async def _emit(self, alert: AlertEvent) -> None:
        if _severity_rank(alert.severity) < _severity_rank(self.minimum_severity):
            return
        if self._is_suppressed(alert):
            return

        self.logger.info(
            "Alert emitted severity=%s category=%s symbol=%s title=%s",
            alert.severity,
            alert.category,
            alert.symbol or "-",
            alert.title,
        )
        await self.bus.publish(EventType.ALERT_EVENT, alert, priority=86, source="alerting_engine")
        if self.channels:
            results = await asyncio.gather(*(self._send_via_channel(channel, alert) for channel in self.channels), return_exceptions=True)
            for channel, result in zip(self.channels, results):
                if isinstance(result, Exception):
                    self.logger.warning("Alert channel %s failed: %s", channel.name, result)

    def _is_suppressed(self, alert: AlertEvent) -> bool:
        if self.alert_cooldown_seconds <= 0 or _severity_rank(alert.severity) >= _severity_rank("critical"):
            return False
        key = "|".join(
            [
                str(alert.category),
                str(alert.symbol or ""),
                str(alert.action or ""),
                str(alert.title),
            ]
        )
        now = _utc_now()
        previous = self._last_alert_at.get(key)
        self._last_alert_at[key] = now
        if previous is None:
            return False
        return (now - previous).total_seconds() < self.alert_cooldown_seconds

    async def _send_via_channel(self, channel: BaseAlertChannel, alert: AlertEvent) -> bool:
        if not channel.enabled:
            return False
        delivered = await channel.send(alert)
        self.logger.info(
            "Alert dispatch channel=%s delivered=%s alert_id=%s",
            channel.name,
            delivered,
            alert.alert_id,
        )
        return delivered
