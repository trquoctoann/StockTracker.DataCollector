from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import structlog

from app.archive.raw_archive import RawArchive
from app.core.config import Settings
from app.core.exceptions import PipelineError, SinkError
from app.core.rate_limiter import RateLimiterRegistry
from app.engine.keycloak_auth import KeycloakAuthManager
from app.engine.pipeline import PipelineEngine
from app.engine.stocktracker_api import StockTrackerApiClient
from app.plugins.processors.market_data_processor import MarketDataPandasProcessor
from app.plugins.sinks.rabbitmq_sink import RabbitMQSink
from app.plugins.sources.vnstock_source import VnstockSource

_LOG = structlog.get_logger(__name__)


@dataclass
class VnstockMarketDataDeps:
    settings: Settings
    rate_limiter: RateLimiterRegistry
    auth: KeycloakAuthManager
    http_client: httpx.AsyncClient
    archive: RawArchive | None = None


async def run_vnstock_market_data(deps: VnstockMarketDataDeps) -> None:
    """Fetch market data from vnstock, split it into chunks, and publish it to RabbitMQ."""
    settings = deps.settings

    if not settings.rabbitmq_enabled:
        raise SinkError("Market data pipeline requires rabbitmq_enabled=True")

    source = VnstockSource(settings, deps.rate_limiter, archive=deps.archive)
    processor = MarketDataPandasProcessor(chunk_size=settings.market_data_chunk_size)
    api = StockTrackerApiClient(settings, deps.auth, deps.rate_limiter, deps.http_client)
    rabbit = RabbitMQSink(settings, deps.rate_limiter)

    try:
        _LOG.info("VNSTOCK_MARKET_DATA_STEP", step="stock_map_from_api")
        stock_map = await api.fetch_stock_symbol_to_id(stock_types={"STOCK", "ETF"})

        failures = 0
        for symbol, stock_id in stock_map.items():
            _LOG.info("VNSTOCK_MARKET_DATA_STEP", step="processing_stock", symbol=symbol, stock_id=stock_id)
            for operation in (_sync_price_history, _sync_intraday):
                stream = operation.__name__.removeprefix("_sync_")
                try:
                    async with PipelineEngine.step(
                        f"{stream}:{symbol}", metadata={"symbol": symbol, "stock_id": stock_id, "stream": stream}
                    ) as should_run:
                        if should_run:
                            row_count = await operation(source, processor, rabbit, settings, symbol, stock_id)
                            await PipelineEngine.put_watermark(
                                stream,
                                symbol,
                                {
                                    "completed_at": datetime.now(UTC).isoformat(),
                                    "count": row_count,
                                    "state": "data" if row_count else "empty",
                                },
                                source=settings.vnstock_quote_source,
                            )
                except Exception:
                    failures += 1
                    _LOG.exception("VNSTOCK_MARKET_DATA_STOCK_FAILED", symbol=symbol, operation=operation.__name__)

        if failures:
            raise PipelineError(f"Market data pipeline incomplete: {failures} operations failed")

        _LOG.info("VNSTOCK_MARKET_DATA_PIPELINE_COMPLETE", total_stocks=len(stock_map))
    finally:
        await rabbit.close()


async def _sync_price_history(
    source: VnstockSource,
    processor: MarketDataPandasProcessor,
    rabbit: RabbitMQSink,
    settings: Settings,
    symbol: str,
    stock_id: int,
) -> int:
    interval = settings.vnstock_price_history_interval
    df = await source.extract(operation="quote_history", symbol=symbol, interval=interval)
    chunks = processor.transform_price_history(stock_id, df, interval=interval)
    routing_key = settings.rabbitmq_routing_key_price_history
    for chunk in chunks:
        await rabbit.publish_message(routing_key, chunk)
    _LOG.info(
        "MARKET_DATA_SYNC_SENT",
        entity="price_history",
        symbol=symbol,
        chunks=len(chunks),
        interval=interval,
    )
    return len(df)


async def _sync_intraday(
    source: VnstockSource,
    processor: MarketDataPandasProcessor,
    rabbit: RabbitMQSink,
    settings: Settings,
    symbol: str,
    stock_id: int,
) -> int:
    df = await source.extract(operation="quote_intraday", symbol=symbol)
    chunks = processor.transform_intraday(stock_id, df)
    routing_key = settings.rabbitmq_routing_key_intraday
    for chunk in chunks:
        await rabbit.publish_message(routing_key, chunk)
    _LOG.info(
        "MARKET_DATA_SYNC_SENT",
        entity="intraday",
        symbol=symbol,
        chunks=len(chunks),
    )
    return len(df)
