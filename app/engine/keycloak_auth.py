from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.core.rate_limiter import RateLimiterRegistry
from app.engine.retry import http_retry

_LOG = structlog.get_logger(__name__)


class KeycloakAuthManager:
    def __init__(
        self,
        settings: Settings,
        rate_limiter: RateLimiterRegistry,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=settings.http_timeout_seconds)
        self._token: str | None = None
        self._expires_at_monotonic: float = 0.0

    def _token_url(self) -> str:
        base = str(self._settings.keycloak_base_url).rstrip("/")
        realm = self._settings.keycloak_realm
        return f"{base}/realms/{realm}/protocol/openid-connect/token"

    def _introspection_url(self) -> str:
        return f"{self._token_url()}/introspect"

    @http_retry
    async def _fetch_token(self) -> dict[str, Any]:
        if not self._settings.keycloak_client_secret:
            raise ConfigurationError("keycloak_client_secret is required for M2M")
        await self._rate_limiter.acquire("http")
        resp = await self._client.post(
            self._token_url(),
            data={
                "grant_type": "client_credentials",
                "client_id": self._settings.keycloak_client_id,
                "client_secret": self._settings.keycloak_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_access_token(self) -> str:
        skew = self._settings.keycloak_token_skew_seconds
        if self._token and time.monotonic() < self._expires_at_monotonic - skew:
            return self._token

        payload = await self._fetch_token()
        access = payload.get("access_token")
        if not access or not isinstance(access, str):
            raise ConfigurationError("Keycloak response missing access_token")
        expires_in = payload.get("expires_in", 300)
        try:
            ttl = float(expires_in)
        except (TypeError, ValueError):
            ttl = 300.0
        self._token = access
        self._expires_at_monotonic = time.monotonic() + ttl
        _LOG.info("KEYCLOAK_TOKEN_REFRESHED", expires_in=ttl)
        return self._token

    async def introspect(self, token: str) -> dict[str, Any]:
        if not self._settings.keycloak_client_secret:
            raise ConfigurationError("keycloak_client_secret is required for token introspection")
        await self._rate_limiter.acquire("http")
        response = await self._client.post(
            self._introspection_url(),
            data={
                "token": token,
                "client_id": self._settings.keycloak_client_id,
                "client_secret": self._settings.keycloak_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ConfigurationError("Keycloak introspection response must be an object")
        return payload

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
