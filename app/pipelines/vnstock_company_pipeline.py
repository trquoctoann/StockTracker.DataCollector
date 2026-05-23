from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

from app.core.config import Settings
from app.core.rate_limiter import RateLimiterRegistry
from app.engine.keycloak_auth import KeycloakAuthManager
from app.engine.stocktracker_api import StockTrackerApiClient
from app.plugins.processors.company_processor import CompanyPandasProcessor
from app.plugins.sinks.rest_api_sink import RestApiSink
from app.plugins.sources.vnstock_source import VnstockSource

_LOG = structlog.get_logger(__name__)


@dataclass
class VnstockCompanyDeps:
    settings: Settings
    rate_limiter: RateLimiterRegistry
    auth: KeycloakAuthManager
    http_client: httpx.AsyncClient


async def run_vnstock_company(deps: VnstockCompanyDeps) -> None:
    """Pipeline: fetch company data from vnstock → transform → PUT to StockTracker.API sync endpoints."""
    settings = deps.settings
    source = VnstockSource(settings, deps.rate_limiter)
    processor = CompanyPandasProcessor()
    api = StockTrackerApiClient(settings, deps.auth, deps.rate_limiter, deps.http_client)
    rest = RestApiSink(settings, deps.auth, deps.rate_limiter, deps.http_client)

    _LOG.info("VNSTOCK_COMPANY_STEP", step="stock_map_from_api")
    stock_map = await api.fetch_stock_symbol_to_id()

    for symbol, stock_id in stock_map.items():
        _LOG.info("VNSTOCK_COMPANY_STEP", step="processing_stock", symbol=symbol, stock_id=stock_id)
        try:
            await _sync_company_profile(source, processor, rest, settings, symbol, stock_id)
            await _sync_company_shareholders(source, processor, rest, settings, symbol, stock_id)
            await _sync_company_officers(source, processor, rest, settings, symbol, stock_id)
            await _sync_company_affiliations(source, processor, rest, settings, symbol, stock_id)
            await _sync_company_events(source, processor, rest, settings, symbol, stock_id)
            await _sync_company_news(source, processor, rest, settings, symbol, stock_id)
        except Exception:
            _LOG.exception("VNSTOCK_COMPANY_STOCK_FAILED", symbol=symbol, stock_id=stock_id)
            continue

    _LOG.info("VNSTOCK_COMPANY_PIPELINE_COMPLETE", total_stocks=len(stock_map))


async def _sync_company_profile(
    source: VnstockSource,
    processor: CompanyPandasProcessor,
    rest: RestApiSink,
    settings: Settings,
    symbol: str,
    stock_id: int,
) -> None:
    df = await source.extract(operation="company_overview", symbol=symbol)
    payload = processor.transform_profile(stock_id, df)
    path = settings.api_path_company_profile_sync.format(stock_id=stock_id)
    await rest.send_put(path, payload)
    _LOG.info("COMPANY_SYNC_SENT", entity="profile", symbol=symbol)


async def _sync_company_shareholders(
    source: VnstockSource,
    processor: CompanyPandasProcessor,
    rest: RestApiSink,
    settings: Settings,
    symbol: str,
    stock_id: int,
) -> None:
    df = await source.extract(operation="company_shareholders", symbol=symbol)
    payload = processor.transform_shareholders(stock_id, df)
    path = settings.api_path_company_shareholders_sync.format(stock_id=stock_id)
    await rest.send_put(path, payload)
    _LOG.info("COMPANY_SYNC_SENT", entity="shareholders", symbol=symbol, count=len(payload.records))


async def _sync_company_officers(
    source: VnstockSource,
    processor: CompanyPandasProcessor,
    rest: RestApiSink,
    settings: Settings,
    symbol: str,
    stock_id: int,
) -> None:
    df = await source.extract(operation="company_officers", symbol=symbol)
    payload = processor.transform_officers(stock_id, df)
    path = settings.api_path_company_officers_sync.format(stock_id=stock_id)
    await rest.send_put(path, payload)
    _LOG.info("COMPANY_SYNC_SENT", entity="officers", symbol=symbol, count=len(payload.records))


async def _sync_company_affiliations(
    source: VnstockSource,
    processor: CompanyPandasProcessor,
    rest: RestApiSink,
    settings: Settings,
    symbol: str,
    stock_id: int,
) -> None:
    df = await source.extract(operation="company_subsidiaries", symbol=symbol)
    payload = processor.transform_affiliations(stock_id, df)
    path = settings.api_path_company_affiliations_sync.format(stock_id=stock_id)
    await rest.send_put(path, payload)
    _LOG.info("COMPANY_SYNC_SENT", entity="affiliations", symbol=symbol, count=len(payload.records))


async def _sync_company_events(
    source: VnstockSource,
    processor: CompanyPandasProcessor,
    rest: RestApiSink,
    settings: Settings,
    symbol: str,
    stock_id: int,
) -> None:
    df = await source.extract(operation="company_events", symbol=symbol)
    payload = processor.transform_events(stock_id, df)
    path = settings.api_path_company_events_sync.format(stock_id=stock_id)
    await rest.send_put(path, payload)
    _LOG.info("COMPANY_SYNC_SENT", entity="events", symbol=symbol, count=len(payload.records))


async def _sync_company_news(
    source: VnstockSource,
    processor: CompanyPandasProcessor,
    rest: RestApiSink,
    settings: Settings,
    symbol: str,
    stock_id: int,
) -> None:
    df = await source.extract(operation="company_news", symbol=symbol)
    payload = processor.transform_news(stock_id, df)
    path = settings.api_path_company_news_sync.format(stock_id=stock_id)
    await rest.send_put(path, payload)
    _LOG.info("COMPANY_SYNC_SENT", entity="news", symbol=symbol, count=len(payload.records))
