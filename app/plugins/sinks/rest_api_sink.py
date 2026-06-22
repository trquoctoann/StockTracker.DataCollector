from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx
import structlog
from pydantic import BaseModel

from app.core.config import Settings
from app.core.exceptions import SinkError
from app.core.rate_limiter import RateLimiterRegistry
from app.engine.keycloak_auth import KeycloakAuthManager
from app.engine.retry import http_retry
from app.interfaces.base_sink import BaseSink

_LOG = structlog.get_logger(__name__)


class RestApiSink(BaseSink):
    def __init__(
        self,
        settings: Settings,
        auth: KeycloakAuthManager,
        rate_limiter: RateLimiterRegistry,
        client: httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        self._auth = auth
        self._rate_limiter = rate_limiter
        self._client = client
        self._paths: dict[str, str] = {
            "industries": settings.api_path_industries_ingest,
            "stocks": settings.api_path_stocks_ingest,
            "market_indices": settings.api_path_market_indices_ingest,
        }

    def _base(self) -> str:
        return str(self._settings.stocktracker_api_base_url).rstrip("/")

    @http_retry
    async def _post(self, path: str, body: list[dict[str, Any]]) -> None:
        token = await self._auth.get_access_token()
        await self._rate_limiter.acquire("http")
        url = f"{self._base()}{path}"
        resp = await self._client.post(
            url,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=self._settings.http_timeout_seconds,
        )
        resp.raise_for_status()

    async def send_batch(self, entity: str, items: Sequence[BaseModel]) -> None:
        path = self._paths.get(entity)
        if not path:
            raise SinkError(f"Unknown entity for RestApiSink: {entity}")
        if not items:
            _LOG.info("REST_SINK_SKIP_EMPTY", entity=entity)
            return
        payload = [m.model_dump(mode="json", exclude_none=True) for m in items]
        await self._post(path, payload)
        _LOG.info("REST_SINK_SENT", entity=entity, count=len(items))

    @http_retry
    async def _put(self, path: str, body: dict[str, Any]) -> None:
        token = await self._auth.get_access_token()
        await self._rate_limiter.acquire("http")
        url = f"{self._base()}{path}"
        resp = await self._client.put(
            url,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=self._settings.http_timeout_seconds,
        )
        resp.raise_for_status()

    async def send_put(self, path: str, payload: BaseModel) -> None:
        """Send a PUT request with a Pydantic model body to the given path."""
        # Missing provider fields must not overwrite existing API values with null.
        body = payload.model_dump(mode="json", exclude_none=True)
        await self._put(path, body)
        _LOG.info("REST_SINK_PUT_SENT", path=path)

    async def close(self) -> None:
        pass
