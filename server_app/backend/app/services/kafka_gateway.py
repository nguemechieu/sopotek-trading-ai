from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any


KafkaHandler = Callable[[str, dict[str, Any]], Awaitable[None]]
logger = logging.getLogger(__name__)


class BaseKafkaGateway(ABC):
    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def publish(self, topic: str, payload: dict[str, Any], *, key: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, topic: str, handler: KafkaHandler) -> None:
        raise NotImplementedError


class InMemoryKafkaGateway(BaseKafkaGateway):
    def __init__(self) -> None:
        self._handlers: dict[str, list[KafkaHandler]] = defaultdict(list)
        self.published_messages: list[dict[str, Any]] = []
        self.runtime_mode = "memory"
        self.startup_error: str | None = None
        self.is_degraded = False

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def subscribe(self, topic: str, handler: KafkaHandler) -> None:
        self._handlers[str(topic)].append(handler)

    async def publish(self, topic: str, payload: dict[str, Any], *, key: str | None = None) -> None:
        message = {"topic": str(topic), "key": key, "payload": payload}
        self.published_messages.append(message)
        for handler in list(self._handlers.get(str(topic), [])):
            await handler(str(topic), dict(payload))


class AioKafkaGateway(BaseKafkaGateway):
    def __init__(self, settings) -> None:
        self.settings = settings
        self._handlers: dict[str, list[KafkaHandler]] = defaultdict(list)
        self._consumer_task: asyncio.Task | None = None
        self._producer = None
        self._consumer = None
        self._fallback_gateway: InMemoryKafkaGateway | None = None
        self.runtime_mode = "kafka"
        self.startup_error: str | None = None
        self.is_degraded = False

    @property
    def published_messages(self) -> list[dict[str, Any]]:
        if self._fallback_gateway is not None:
            return self._fallback_gateway.published_messages
        return []

    async def start(self) -> None:
        try:
            from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
        except ImportError as exc:
            if self.settings.kafka_required:
                raise RuntimeError("aiokafka is required for Kafka-backed deployment") from exc
            await self._activate_fallback(exc)
            return

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            client_id=self.settings.kafka_client_id,
            value_serializer=lambda value: json.dumps(value, default=str).encode("utf-8"),
            key_serializer=lambda value: value.encode("utf-8") if value else None,
        )
        self._consumer = AIOKafkaConsumer(
            self.settings.kafka_market_topic,
            self.settings.kafka_execution_topic,
            self.settings.kafka_portfolio_topic,
            self.settings.kafka_risk_topic,
            self.settings.kafka_strategy_state_topic,
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            client_id=self.settings.kafka_client_id,
            group_id=self.settings.kafka_group_id,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )
        try:
            await self._producer.start()
            await self._consumer.start()
        except Exception as exc:
            await self._shutdown_clients()
            if self.settings.kafka_required:
                raise
            await self._activate_fallback(exc)
            return
        self.runtime_mode = "kafka"
        self.startup_error = None
        self.is_degraded = False
        self._consumer_task = asyncio.create_task(self._consume_loop())

    async def stop(self) -> None:
        if self._fallback_gateway is not None:
            await self._fallback_gateway.stop()
            self._fallback_gateway = None
        await self._shutdown_clients()

    async def _shutdown_clients(self) -> None:
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._consumer_task = None
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    def subscribe(self, topic: str, handler: KafkaHandler) -> None:
        self._handlers[str(topic)].append(handler)
        if self._fallback_gateway is not None:
            self._fallback_gateway.subscribe(str(topic), handler)

    async def publish(self, topic: str, payload: dict[str, Any], *, key: str | None = None) -> None:
        if self._fallback_gateway is not None:
            await self._fallback_gateway.publish(str(topic), dict(payload), key=key)
            return
        if self._producer is None:
            raise RuntimeError("Kafka producer has not been started")
        await self._producer.send_and_wait(str(topic), dict(payload), key=key)

    async def _consume_loop(self) -> None:
        if self._consumer is None:
            return
        async for message in self._consumer:
            handlers = list(self._handlers.get(str(message.topic), []))
            for handler in handlers:
                await handler(str(message.topic), dict(message.value or {}))

    async def _activate_fallback(self, exc: Exception) -> None:
        self.runtime_mode = "memory-fallback"
        self.startup_error = f"{type(exc).__name__}: {exc}"
        self.is_degraded = True
        logger.warning(
            "Kafka unavailable at startup; switching backend messaging to in-memory fallback. bootstrap_servers=%s error=%s",
            self.settings.kafka_bootstrap_servers,
            self.startup_error,
        )
        fallback = InMemoryKafkaGateway()
        fallback.runtime_mode = self.runtime_mode
        fallback.startup_error = self.startup_error
        fallback.is_degraded = True
        for topic, handlers in self._handlers.items():
            for handler in handlers:
                fallback.subscribe(topic, handler)
        await fallback.start()
        self._fallback_gateway = fallback


def build_kafka_gateway(settings):
    if settings.is_memory_kafka:
        return InMemoryKafkaGateway()
    return AioKafkaGateway(settings)
