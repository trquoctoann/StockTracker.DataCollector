from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

from app.core.config import Settings
from app.core.exceptions import SinkError
from app.core.rate_limiter import RateLimiterRegistry
from app.engine.keycloak_auth import KeycloakAuthManager
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


async def run_vnstock_market_data(deps: VnstockMarketDataDeps) -> None:
    """Pipeline: fetch market data from vnstock → chunk → publish to RabbitMQ."""
    settings = deps.settings

    if not settings.rabbitmq_enabled:
        raise SinkError("Market data pipeline requires rabbitmq_enabled=True")

    source = VnstockSource(settings, deps.rate_limiter)
    processor = MarketDataPandasProcessor(chunk_size=settings.market_data_chunk_size)
    api = StockTrackerApiClient(settings, deps.auth, deps.rate_limiter, deps.http_client)
    rabbit = RabbitMQSink(settings, deps.rate_limiter)

    try:
        _LOG.info("VNSTOCK_MARKET_DATA_STEP", step="stock_map_from_api")
        stock_map = await api.fetch_stock_symbol_to_id()

        for symbol, stock_id in stock_map.items():
            _LOG.info("VNSTOCK_MARKET_DATA_STEP", step="processing_stock", symbol=symbol, stock_id=stock_id)
            try:
                await _sync_price_history(source, processor, rabbit, settings, symbol, stock_id)
                await _sync_intraday(source, processor, rabbit, settings, symbol, stock_id)
            except Exception:
                _LOG.exception("VNSTOCK_MARKET_DATA_STOCK_FAILED", symbol=symbol, stock_id=stock_id)
                continue

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
) -> None:
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


async def _sync_intraday(
    source: VnstockSource,
    processor: MarketDataPandasProcessor,
    rabbit: RabbitMQSink,
    settings: Settings,
    symbol: str,
    stock_id: int,
) -> None:
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
