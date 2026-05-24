"""Unit tests for KeycloakAuthManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.core.rate_limiter import RateLimiterRegistry
from app.engine.keycloak_auth import KeycloakAuthManager


def _make_token_response(access_token: str = "test-token", expires_in: int = 300) -> dict[str, object]:
    return {"access_token": access_token, "expires_in": expires_in, "token_type": "Bearer"}


def _make_settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "keycloak_client_secret": "test-secret",
        "keycloak_token_skew_seconds": 30.0,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture()
def settings() -> Settings:
    return _make_settings()


@pytest.fixture()
def rate_limiter(settings: Settings) -> RateLimiterRegistry:
    return RateLimiterRegistry(settings)


@pytest.fixture()
def mock_http_client() -> AsyncMock:
    client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = _make_token_response()
    mock_resp.raise_for_status = MagicMock()
    client.post.return_value = mock_resp
    return client


@pytest.mark.asyncio
async def test_get_access_token_fetches_on_first_call(
    settings: Settings, rate_limiter: RateLimiterRegistry, mock_http_client: AsyncMock
) -> None:
    """First call to get_access_token should fetch from Keycloak."""
    manager = KeycloakAuthManager(settings, rate_limiter, client=mock_http_client)
    token = await manager.get_access_token()
    assert token == "test-token"
    mock_http_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_get_access_token_caches_token(
    settings: Settings, rate_limiter: RateLimiterRegistry, mock_http_client: AsyncMock
) -> None:
    """Subsequent calls within TTL should NOT re-fetch from Keycloak."""
    manager = KeycloakAuthManager(settings, rate_limiter, client=mock_http_client)
    token1 = await manager.get_access_token()
    token2 = await manager.get_access_token()
    assert token1 == token2
    # Should only call Keycloak once
    assert mock_http_client.post.call_count == 1


@pytest.mark.asyncio
async def test_get_access_token_refreshes_when_expired(
    settings: Settings, rate_limiter: RateLimiterRegistry, mock_http_client: AsyncMock
) -> None:
    """Token should be re-fetched when TTL is exceeded (skew)."""
    # expires_in=0 + skew=30 means token is always expired
    manager = KeycloakAuthManager(settings, rate_limiter, client=mock_http_client)
    manager._expires_at_monotonic = 0.0  # force expired
    manager._token = "old-token"

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = _make_token_response(access_token="new-token")
    mock_resp.raise_for_status = MagicMock()
    mock_http_client.post.return_value = mock_resp

    token = await manager.get_access_token()
    assert token == "new-token"
    mock_http_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_get_access_token_raises_when_no_secret(
    rate_limiter: RateLimiterRegistry, mock_http_client: AsyncMock
) -> None:
    """ConfigurationError should be raised when client secret is missing."""
    settings_no_secret = _make_settings(keycloak_client_secret="")
    manager = KeycloakAuthManager(settings_no_secret, rate_limiter, client=mock_http_client)
    with pytest.raises(ConfigurationError, match="keycloak_client_secret"):
        await manager.get_access_token()


@pytest.mark.asyncio
async def test_get_access_token_raises_on_missing_access_token(
    settings: Settings, rate_limiter: RateLimiterRegistry, mock_http_client: AsyncMock
) -> None:
    """ConfigurationError should be raised when response has no access_token."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = {"error": "invalid_client"}
    mock_resp.raise_for_status = MagicMock()
    mock_http_client.post.return_value = mock_resp

    manager = KeycloakAuthManager(settings, rate_limiter, client=mock_http_client)
    with pytest.raises(ConfigurationError, match="access_token"):
        await manager.get_access_token()


@pytest.mark.asyncio
async def test_token_url_format(settings: Settings, rate_limiter: RateLimiterRegistry) -> None:
    """Token URL should be constructed correctly from settings."""
    manager = KeycloakAuthManager(settings, rate_limiter, client=AsyncMock())
    url = manager._token_url()
    assert "stocktracker" in url
    assert "openid-connect/token" in url


@pytest.mark.asyncio
async def test_close_does_not_close_external_client(
    settings: Settings, rate_limiter: RateLimiterRegistry, mock_http_client: AsyncMock
) -> None:
    """When client is provided externally, close() should NOT close it."""
    manager = KeycloakAuthManager(settings, rate_limiter, client=mock_http_client)
    await manager.close()
    mock_http_client.aclose.assert_not_called()


@pytest.mark.asyncio
async def test_close_closes_owned_client(settings: Settings, rate_limiter: RateLimiterRegistry) -> None:
    """When client is owned (not provided), close() should close it."""
    mock_inner = AsyncMock()
    with patch("app.engine.keycloak_auth.httpx.AsyncClient", return_value=mock_inner):
        manager = KeycloakAuthManager(settings, rate_limiter)
        await manager.close()
        mock_inner.aclose.assert_called_once()
