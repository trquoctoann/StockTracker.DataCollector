from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hmac import compare_digest
from typing import Annotated
from uuid import UUID

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import Settings
from app.core.exceptions import PipelineBusyError
from app.core.logger import configure_logging
from app.core.rate_limiter import RateLimiterRegistry
from app.engine.job_registry import JobRegistry, PipelineJob
from app.engine.keycloak_auth import KeycloakAuthManager
from app.engine.pipeline import PipelineEngine
from app.engine.scheduler import JobScheduler
from app.middleware.metrics import HttpMetrics, HttpMetricsMiddleware
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
_jobs = JobRegistry()
_bearer = HTTPBearer(auto_error=False)


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
    await _jobs.shutdown()
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
_metrics = HttpMetrics("DataCollector")
app.add_middleware(HttpMetricsMiddleware, metrics=_metrics)


class PipelineRunResponse(BaseModel):
    job_id: UUID
    pipeline: str
    status: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness() -> JSONResponse:
    ready = _auth is not None and _http_client is not None and not _http_client.is_closed
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if ready else "unavailable"},
    )


@app.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
async def metrics() -> str:
    return _metrics.render()


def _realm_roles(payload: dict[str, object]) -> set[str]:
    realm_access = payload.get("realm_access", {})
    if isinstance(realm_access, str):
        try:
            realm_access = json.loads(realm_access)
        except json.JSONDecodeError:
            return set()
    if not isinstance(realm_access, dict):
        return set()
    roles = realm_access.get("roles", [])
    return {role for role in roles if isinstance(role, str)} if isinstance(roles, list) else set()


async def require_pipeline_operator(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    if credentials is None or not compare_digest(credentials.scheme.lower(), "bearer"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Bearer"})
    payload = await get_auth().introspect(credentials.credentials)
    if payload.get("active") is not True:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Bearer"})
    if "pipeline_operator" not in _realm_roles(payload):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


def _submit_pipeline(name: str, factory) -> PipelineRunResponse:
    try:
        job = _jobs.submit(name, factory)
    except PipelineBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return PipelineRunResponse(job_id=job.id, pipeline=job.pipeline, status=job.status.value)


@app.post(
    "/run/vnstock-listing",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_pipeline_operator)],
)
async def run_vnstock_listing_endpoint() -> PipelineRunResponse:
    return _submit_pipeline("vnstock_listing", lambda: run_vnstock_listing(_build_listing_deps()))


@app.post(
    "/run/vnstock-company",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_pipeline_operator)],
)
async def run_vnstock_company_endpoint() -> PipelineRunResponse:
    return _submit_pipeline("vnstock_company", lambda: run_vnstock_company(_build_company_deps()))


@app.post(
    "/run/vnstock-market-data",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_pipeline_operator)],
)
async def run_vnstock_market_data_endpoint() -> PipelineRunResponse:
    return _submit_pipeline("vnstock_market_data", lambda: run_vnstock_market_data(_build_market_data_deps()))


@app.get(
    "/run/jobs/{job_id}",
    response_model=PipelineJob,
    dependencies=[Depends(require_pipeline_operator)],
)
async def get_pipeline_job(job_id: UUID) -> PipelineJob:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return job
