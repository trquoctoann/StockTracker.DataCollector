from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import structlog

from app.archive.raw_archive import RawArchive
from app.core.config import Settings
from app.core.rate_limiter import RateLimiterRegistry
from app.engine.keycloak_auth import KeycloakAuthManager
from app.engine.pipeline import PipelineEngine
from app.engine.stocktracker_api import StockTrackerApiClient
from app.plugins.processors.pandas_processor import ListingPandasProcessor
from app.plugins.sinks.rest_api_sink import RestApiSink
from app.plugins.sources.vnstock_source import VnstockSource

_LOG = structlog.get_logger(__name__)


@dataclass
class VnstockListingDeps:
    settings: Settings
    rate_limiter: RateLimiterRegistry
    auth: KeycloakAuthManager
    http_client: httpx.AsyncClient
    archive: RawArchive | None = None


async def run_vnstock_listing(deps: VnstockListingDeps) -> None:
    """Fetch listing data from vnstock, transform it, and send it to StockTracker.API."""
    settings = deps.settings
    source = VnstockSource(settings, deps.rate_limiter, archive=deps.archive)
    processor = ListingPandasProcessor()
    api = StockTrackerApiClient(settings, deps.auth, deps.rate_limiter, deps.http_client)
    rest = RestApiSink(settings, deps.auth, deps.rate_limiter, deps.http_client)

    async with PipelineEngine.step("industries.sync") as should_run:
        if should_run:
            _LOG.info("VNSTOCK_LISTING_STEP", step="industries_extract")
            df_ind = await source.extract(operation="industries_icb")
            industries = processor.transform_industries(df_ind)
            await rest.send_batch("industries", industries)
            await PipelineEngine.put_watermark(
                "industries",
                "catalog",
                {"completed_at": datetime.now(UTC).isoformat(), "count": len(industries), "state": "data"},
                source="VCI",
            )

    _LOG.info("VNSTOCK_LISTING_STEP", step="industry_map_from_api")
    industry_map = await api.fetch_industry_code_to_id()

    async with PipelineEngine.step("stocks.sync") as should_run:
        if should_run:
            _LOG.info("VNSTOCK_LISTING_STEP", step="stocks_extract")
            df_sym = await source.extract(operation="symbols_by_exchange")
            stocks = processor.transform_stocks(df_sym, industry_map)
            await rest.send_batch("stocks", stocks)
            await PipelineEngine.put_watermark(
                "stocks",
                "catalog",
                {"completed_at": datetime.now(UTC).isoformat(), "count": len(stocks), "state": "data"},
                source=settings.vnstock_listing_source,
            )

    _LOG.info("VNSTOCK_LISTING_STEP", step="stock_map_from_api")
    stock_map = await api.fetch_stock_symbol_to_id()

    async with PipelineEngine.step("market_indices.sync") as should_run:
        if should_run:
            _LOG.info("VNSTOCK_LISTING_STEP", step="indices_catalog")
            baskets = await source.extract(operation="indices_catalog")
            indices = processor.transform_market_indices(baskets, stock_map)
            await rest.send_batch("market_indices", indices)
            await PipelineEngine.put_watermark(
                "market_indices",
                "catalog",
                {"completed_at": datetime.now(UTC).isoformat(), "count": len(indices), "state": "data"},
                source=settings.vnstock_indices_source,
            )
