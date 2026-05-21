from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import aio_pika
import structlog
from pydantic import BaseModel

from app.core.config import Settings
from app.core.exceptions import SinkError
from app.core.rate_limiter import RateLimiterRegistry
from app.interfaces.base_sink import BaseSink

_LOG = structlog.get_logger(__name__)


class RabbitMQSink(BaseSink):
    def __init__(self, settings: Settings, rate_limiter: RateLimiterRegistry) -> None:
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._connection: Any = None
        self._channel: Any = None
        self._exchange: Any = None

    async def _ensure_connected(self) -> None:
        if self._exchange is not None:
            return
        await self._rate_limiter.acquire("rabbitmq")
        self._connection = await aio_pika.connect_robust(self._settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        ex_map = {
            "topic": aio_pika.ExchangeType.TOPIC,
            "direct": aio_pika.ExchangeType.DIRECT,
            "fanout": aio_pika.ExchangeType.FANOUT,
            "headers": aio_pika.ExchangeType.HEADERS,
        }
        ex_type = ex_map.get(self._settings.rabbitmq_exchange_type.lower(), aio_pika.ExchangeType.TOPIC)
        self._exchange = await self._channel.declare_exchange(
            self._settings.rabbitmq_exchange,
            ex_type,
            durable=True,
        )

    async def send_batch(self, entity: str, items: Sequence[BaseModel]) -> None:
        if not self._settings.rabbitmq_enabled:
            raise SinkError("RabbitMQSink called while rabbitmq_enabled is False")
        if not items:
            _LOG.info("RABBIT_SINK_SKIP_EMPTY", entity=entity)
            return
        await self._ensure_connected()
        assert self._exchange is not None
        await self._rate_limiter.acquire("rabbitmq")
        body = json.dumps(
            [m.model_dump(mode="json") for m in items],
            ensure_ascii=False,
        ).encode("utf-8")
        routing_key = f"datacollector.{entity}"
        await self._exchange.publish(
            aio_pika.Message(body=body, content_type="application/json"),
            routing_key=routing_key,
        )
        _LOG.info("RABBIT_SINK_PUBLISHED", entity=entity, count=len(items), routing_key=routing_key)

    async def publish_message(self, routing_key: str, message: BaseModel) -> None:
        """Publish a single Pydantic model to the given routing key."""
        if not self._settings.rabbitmq_enabled:
            raise SinkError("RabbitMQSink called while rabbitmq_enabled is False")
        await self._ensure_connected()
        assert self._exchange is not None
        await self._rate_limiter.acquire("rabbitmq")
        body = json.dumps(
            message.model_dump(mode="json"),
            ensure_ascii=False,
        ).encode("utf-8")
        await self._exchange.publish(
            aio_pika.Message(body=body, content_type="application/json"),
            routing_key=routing_key,
        )
        _LOG.info("RABBIT_SINK_MESSAGE_PUBLISHED", routing_key=routing_key)

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
        self._exchange = None
