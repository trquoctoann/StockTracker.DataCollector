from __future__ import annotations

from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import Settings
from app.core.exceptions import SourceError
from app.core.rate_limiter import RateLimiterRegistry
from app.engine.keycloak_auth import KeycloakAuthManager
from app.engine.retry import http_retry

_LOG = structlog.get_logger(__name__)


class _IndustryApiRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    code: str = Field(..., description="Mã ngành ICB")

    @field_validator("code", mode="before")
    @classmethod
    def _code_as_str(cls, v: object) -> str:
        return str(v).strip()


class _StockApiRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    symbol: str
    type: str | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def _sym_upper(cls, v: object) -> str:
        return str(v).strip().upper()


def _unwrap_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "data", "results"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
    raise ValueError("Unexpected API response shape for list endpoint")


class StockTrackerApiClient:
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

    def _base(self) -> str:
        return str(self._settings.stocktracker_api_base_url).rstrip("/")

    @http_retry
    async def _get_json(self, path: str) -> Any:
        token = await self._auth.get_access_token()
        await self._rate_limiter.acquire("http")
        url = f"{self._base()}{path}"
        resp = await self._client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()

    async def fetch_industry_code_to_id(self) -> dict[str, int]:
        raw = await self._get_json(self._settings.api_path_industries_all)
        rows = [_IndustryApiRow.model_validate(x) for x in _unwrap_list(raw)]
        mapping = {r.code: r.id for r in rows}
        _LOG.info("INDUSTRY_MAP_LOADED", count=len(mapping))
        return mapping

    async def fetch_stock_symbol_to_id(self, *, stock_types: set[str] | None = None) -> dict[str, int]:
        raw = await self._get_json(self._settings.api_path_stocks_all)
        rows = [_StockApiRow.model_validate(x) for x in _unwrap_list(raw)]
        if stock_types is not None:
            if any(row.type is None for row in rows):
                raise SourceError("Stock API response is missing asset type; cannot select provider-compatible symbols")
            rows = [row for row in rows if row.type in stock_types]
        mapping = {r.symbol: r.id for r in rows}
        _LOG.info("STOCK_MAP_LOADED", count=len(mapping))
        return mapping

    @http_retry
    async def put_json(self, path: str, body: dict[str, Any]) -> Any:
        """Send an authenticated PUT request to the given path."""
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
        )
        resp.raise_for_status()
        return resp.json()
