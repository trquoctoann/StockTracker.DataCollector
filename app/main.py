from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI
from pydantic import BaseModel

from app.core.config import Settings
from app.core.logger import configure_logging
from app.core.rate_limiter import RateLimiterRegistry
from app.engine.keycloak_auth import KeycloakAuthManager
from app.engine.pipeline import PipelineEngine
from app.engine.scheduler import JobScheduler
from app.pipelines.vnstock_company_pipeline import VnstockCompanyDeps, run_vnstock_company
from app.pipelines.vnstock_listing_pipeline import VnstockListingDeps, run_vnstock_listing
from app.pipelines.vnstock_market_data_pipeline import VnstockMarketDataDeps, run_vnstock_market_data

# Configure logging early – must run before any logger is used
configure_logging(json_logs=Settings().log_json)  # noqa: E402

_LOG = structlog.get_logger(__name__)

_settings: Settings | None = None
_rate_limiter: RateLimiterRegistry | None = None
_auth: KeycloakAuthManager | None = None
_http_client: httpx.AsyncClient | None = None
_scheduler: JobScheduler | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_rate_limiter() -> RateLimiterRegistry:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiterRegistry(get_settings())
    return _rate_limiter


def get_auth() -> KeycloakAuthManager:
    global _auth
    if _auth is None:
        raise RuntimeError("Auth manager not initialized (app lifespan chưa chạy)")
    return _auth


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        raise RuntimeError("HTTP client not initialized (app lifespan chưa chạy)")
    return _http_client


def _build_listing_deps() -> VnstockListingDeps:
    return VnstockListingDeps(
        settings=get_settings(),
        rate_limiter=get_rate_limiter(),
        auth=get_auth(),
        http_client=get_http_client(),
    )


def _build_company_deps() -> VnstockCompanyDeps:
    return VnstockCompanyDeps(
        settings=get_settings(),
        rate_limiter=get_rate_limiter(),
        auth=get_auth(),
        http_client=get_http_client(),
    )


def _build_market_data_deps() -> VnstockMarketDataDeps:
    return VnstockMarketDataDeps(
        settings=get_settings(),
        rate_limiter=get_rate_limiter(),
        auth=get_auth(),
        http_client=get_http_client(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _settings, _rate_limiter, _auth, _http_client, _scheduler
    _settings = Settings()
    _rate_limiter = RateLimiterRegistry(_settings)
    _http_client = httpx.AsyncClient(timeout=_settings.http_timeout_seconds)
    _auth = KeycloakAuthManager(_settings, _rate_limiter, client=_http_client)

    if _settings.scheduler_enabled:
        _scheduler = JobScheduler(_settings)

        async def _scheduled_listing() -> None:
            await PipelineEngine.run("vnstock_listing", lambda: run_vnstock_listing(_build_listing_deps()))

        async def _scheduled_company() -> None:
            await PipelineEngine.run("vnstock_company", lambda: run_vnstock_company(_build_company_deps()))

        async def _scheduled_market_data() -> None:
            await PipelineEngine.run(
                "vnstock_market_data",
                lambda: run_vnstock_market_data(_build_market_data_deps()),
            )

        _scheduler.add_cron_job(
            "vnstock_listing",
            _scheduled_listing,
            hour=_settings.scheduler_cron_hour,
            minute=_settings.scheduler_cron_minute,
        )
        _scheduler.add_cron_job(
            "vnstock_company",
            _scheduled_company,
            hour=_settings.scheduler_company_cron_hour,
            minute=_settings.scheduler_company_cron_minute,
        )
        _scheduler.add_cron_job(
            "vnstock_market_data",
            _scheduled_market_data,
            hour=_settings.scheduler_market_data_cron_hour,
            minute=_settings.scheduler_market_data_cron_minute,
        )
        _scheduler.start()

    _LOG.info("APP_STARTUP_COMPLETE", scheduler=_settings.scheduler_enabled)
    yield

    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _auth is not None:
        await _auth.close()
        _auth = None
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
    _rate_limiter = None
    _settings = None
    _LOG.info("APP_SHUTDOWN_COMPLETE")


app = FastAPI(title="StockTracker.DataCollector", lifespan=lifespan)


class PipelineRunResponse(BaseModel):
    pipeline: str
    status: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run/vnstock-listing", response_model=PipelineRunResponse)
async def run_vnstock_listing_endpoint() -> PipelineRunResponse:
    await PipelineEngine.run("vnstock_listing", lambda: run_vnstock_listing(_build_listing_deps()))
    return PipelineRunResponse(pipeline="vnstock_listing", status="completed")


@app.post("/run/vnstock-company", response_model=PipelineRunResponse)
async def run_vnstock_company_endpoint() -> PipelineRunResponse:
    await PipelineEngine.run("vnstock_company", lambda: run_vnstock_company(_build_company_deps()))
    return PipelineRunResponse(pipeline="vnstock_company", status="completed")


@app.post("/run/vnstock-market-data", response_model=PipelineRunResponse)
async def run_vnstock_market_data_endpoint() -> PipelineRunResponse:
    await PipelineEngine.run(
        "vnstock_market_data",
        lambda: run_vnstock_market_data(_build_market_data_deps()),
    )
    return PipelineRunResponse(pipeline="vnstock_market_data", status="completed")
