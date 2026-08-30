from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from hmac import compare_digest
from typing import Annotated
from uuid import UUID

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.archive.raw_archive import RawArchive
from app.control.store import PipelineStore
from app.core.config import Settings
from app.core.exceptions import PipelineBusyError
from app.core.logger import configure_logging
from app.core.rate_limiter import RateLimiterRegistry
from app.engine.job_registry import JobRegistry, JobStatus, PipelineJob
from app.engine.keycloak_auth import KeycloakAuthManager
from app.engine.pipeline import PipelineEngine
from app.engine.scheduler import JobScheduler
from app.middleware.metrics import HttpMetrics, HttpMetricsMiddleware
from app.pipelines.vnstock_company_pipeline import VnstockCompanyDeps, run_vnstock_company
from app.pipelines.vnstock_listing_pipeline import VnstockListingDeps, run_vnstock_listing
from app.pipelines.vnstock_market_data_pipeline import VnstockMarketDataDeps, run_vnstock_market_data

# Configure logging early; it must run before any logger is used.
configure_logging(json_logs=Settings().log_json)  # noqa: E402

_LOG = structlog.get_logger(__name__)

_settings: Settings | None = None
_rate_limiter: RateLimiterRegistry | None = None
_auth: KeycloakAuthManager | None = None
_http_client: httpx.AsyncClient | None = None
_scheduler: JobScheduler | None = None
_pipeline_store: PipelineStore | None = None
_raw_archive: RawArchive | None = None
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
        raise RuntimeError("Auth manager is not initialized; the application lifespan has not started")
    return _auth


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        raise RuntimeError("HTTP client is not initialized; the application lifespan has not started")
    return _http_client


def _build_listing_deps() -> VnstockListingDeps:
    return VnstockListingDeps(
        settings=get_settings(),
        rate_limiter=get_rate_limiter(),
        auth=get_auth(),
        http_client=get_http_client(),
        archive=_raw_archive,
    )


def _build_company_deps() -> VnstockCompanyDeps:
    return VnstockCompanyDeps(
        settings=get_settings(),
        rate_limiter=get_rate_limiter(),
        auth=get_auth(),
        http_client=get_http_client(),
        archive=_raw_archive,
    )


def _build_market_data_deps() -> VnstockMarketDataDeps:
    return VnstockMarketDataDeps(
        settings=get_settings(),
        rate_limiter=get_rate_limiter(),
        auth=get_auth(),
        http_client=get_http_client(),
        archive=_raw_archive,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _settings, _rate_limiter, _auth, _http_client, _scheduler, _pipeline_store, _raw_archive, _jobs
    _settings = Settings()
    _rate_limiter = RateLimiterRegistry(_settings)
    _jobs = JobRegistry(_settings.job_history_limit)
    try:
        async with AsyncExitStack() as stack:
            _http_client = await stack.enter_async_context(httpx.AsyncClient(timeout=_settings.http_timeout_seconds))
            _auth = KeycloakAuthManager(_settings, _rate_limiter, client=_http_client)

            if _settings.control_plane_enabled:
                _pipeline_store = PipelineStore(_settings.control_database_url)
                await _pipeline_store.connect()
                stack.push_async_callback(_pipeline_store.close)
                recovered = await _pipeline_store.recover_stale_runs(_settings.pipeline_stale_after_seconds)
                if recovered:
                    _LOG.warning("PIPELINE_STALE_RUNS_RECOVERED", count=recovered)
            PipelineEngine.configure(
                _pipeline_store,
                heartbeat_seconds=_settings.pipeline_heartbeat_seconds,
                metrics=_metrics,
            )
            stack.callback(PipelineEngine.configure, None, metrics=_metrics)
            stack.push_async_callback(_jobs.shutdown)

            if _settings.raw_archive_enabled:
                _raw_archive = RawArchive(_settings, store=_pipeline_store)
                await _raw_archive.ensure_bucket()

            if _settings.scheduler_enabled:
                _scheduler = JobScheduler(_settings)

                async def _scheduled_listing() -> None:
                    await PipelineEngine.run(
                        "vnstock_listing", lambda: run_vnstock_listing(_build_listing_deps()), trigger="schedule"
                    )

                async def _scheduled_company() -> None:
                    await PipelineEngine.run(
                        "vnstock_company", lambda: run_vnstock_company(_build_company_deps()), trigger="schedule"
                    )

                async def _scheduled_market_data() -> None:
                    await PipelineEngine.run(
                        "vnstock_market_data",
                        lambda: run_vnstock_market_data(_build_market_data_deps()),
                        trigger="schedule",
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
                stack.callback(_scheduler.shutdown, wait=False)

            _LOG.info("APP_STARTUP_COMPLETE", scheduler=_settings.scheduler_enabled)
            yield
    finally:
        _scheduler = None
        _raw_archive = None
        _pipeline_store = None
        _auth = None
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


class PipelineRunRequest(BaseModel):
    resume_from: UUID | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness() -> JSONResponse:
    ready = _auth is not None and _http_client is not None and not _http_client.is_closed
    checks = {"http_client": "ok" if ready else "unavailable"}
    if get_settings().control_plane_enabled:
        try:
            if _pipeline_store is None:
                raise RuntimeError("pipeline store is not initialized")
            await _pipeline_store.ping()
            checks["control_database"] = "ok"
        except Exception:
            checks["control_database"] = "unavailable"
            ready = False
    if get_settings().raw_archive_enabled:
        try:
            if _raw_archive is None:
                raise RuntimeError("raw archive is not initialized")
            await _raw_archive.ping()
            checks["raw_archive"] = "ok"
        except Exception:
            checks["raw_archive"] = "unavailable"
            ready = False
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if ready else "unavailable", "checks": checks},
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


async def _submit_pipeline(
    name: str,
    factory,
    request: PipelineRunRequest | None,
) -> PipelineRunResponse:
    resume_from = request.resume_from if request is not None else None
    if resume_from is not None:
        if _pipeline_store is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Pipeline resume requires the durable control plane",
            )
        previous = await _pipeline_store.get_run(resume_from)
        if previous is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume source run was not found")
        if previous.pipeline != name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Run {resume_from} belongs to pipeline {previous.pipeline}",
            )
        if previous.status not in {"failed", "cancelled", "abandoned"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Run {resume_from} has status {previous.status} and cannot be resumed",
            )
    try:
        job = _jobs.submit(name, factory, resume_of=resume_from)
    except PipelineBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return PipelineRunResponse(job_id=job.id, pipeline=job.pipeline, status=job.status.value)


@app.post(
    "/run/vnstock-listing",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_pipeline_operator)],
)
async def run_vnstock_listing_endpoint(request: PipelineRunRequest | None = None) -> PipelineRunResponse:
    return await _submit_pipeline(
        "vnstock_listing",
        lambda: run_vnstock_listing(_build_listing_deps()),
        request,
    )


@app.post(
    "/run/vnstock-company",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_pipeline_operator)],
)
async def run_vnstock_company_endpoint(request: PipelineRunRequest | None = None) -> PipelineRunResponse:
    return await _submit_pipeline(
        "vnstock_company",
        lambda: run_vnstock_company(_build_company_deps()),
        request,
    )


@app.post(
    "/run/vnstock-market-data",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_pipeline_operator)],
)
async def run_vnstock_market_data_endpoint(request: PipelineRunRequest | None = None) -> PipelineRunResponse:
    return await _submit_pipeline(
        "vnstock_market_data",
        lambda: run_vnstock_market_data(_build_market_data_deps()),
        request,
    )


@app.get(
    "/run/jobs/{job_id}",
    response_model=PipelineJob,
    dependencies=[Depends(require_pipeline_operator)],
)
async def get_pipeline_job(job_id: UUID) -> PipelineJob:
    job = _jobs.get(job_id)
    if job is None and _pipeline_store is not None:
        record = await _pipeline_store.get_run(job_id)
        if record is not None:
            return PipelineJob(
                id=record.id,
                pipeline=record.pipeline,
                status=JobStatus(record.status),
                submitted_at=record.submitted_at,
                started_at=record.started_at,
                finished_at=record.finished_at,
                error=record.error,
            )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return job
