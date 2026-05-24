"""Unit tests for StockTrackerApiClient."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.core.config import Settings
from app.core.rate_limiter import RateLimiterRegistry
from app.engine.keycloak_auth import KeycloakAuthManager
from app.engine.stocktracker_api import StockTrackerApiClient, _unwrap_list

# ---------------------------------------------------------------------------
# _unwrap_list helper
# ---------------------------------------------------------------------------


def test_unwrap_list_with_plain_list() -> None:
    data: list[Any] = [{"id": 1}, {"id": 2}]
    assert _unwrap_list(data) == data


def test_unwrap_list_with_items_key() -> None:
    payload = {"items": [{"id": 1}], "total": 1}
    assert _unwrap_list(payload) == [{"id": 1}]


def test_unwrap_list_with_data_key() -> None:
    payload = {"data": [{"id": 2}]}
    assert _unwrap_list(payload) == [{"id": 2}]


def test_unwrap_list_with_results_key() -> None:
    payload = {"results": [{"id": 3}]}
    assert _unwrap_list(payload) == [{"id": 3}]


def test_unwrap_list_raises_on_unknown_shape() -> None:
    with pytest.raises(ValueError, match="Unexpected API response"):
        _unwrap_list({"unknown_key": "value"})


def test_unwrap_list_raises_on_non_list_non_dict() -> None:
    with pytest.raises(ValueError, match="Unexpected API response"):
        _unwrap_list("raw string")


# ---------------------------------------------------------------------------
# StockTrackerApiClient fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings() -> Settings:
    return Settings()


@pytest.fixture()
def rate_limiter(settings: Settings) -> RateLimiterRegistry:
    return RateLimiterRegistry(settings)


@pytest.fixture()
def mock_auth() -> AsyncMock:
    auth = AsyncMock(spec=KeycloakAuthManager)
    auth.get_access_token.return_value = "bearer-token"
    return auth


def _make_client(response_json: Any) -> AsyncMock:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = response_json
    mock_resp.raise_for_status = MagicMock()
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = mock_resp
    client.put.return_value = mock_resp
    return client


# ---------------------------------------------------------------------------
# fetch_industry_code_to_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_industry_code_to_id_plain_list(
    settings: Settings, rate_limiter: RateLimiterRegistry, mock_auth: AsyncMock
) -> None:
    """Should parse a plain list of {id, code} rows into a code→id mapping."""
    http_client = _make_client([{"id": 1, "code": "8000"}, {"id": 2, "code": "9000"}])
    api = StockTrackerApiClient(settings, mock_auth, rate_limiter, http_client)
    mapping = await api.fetch_industry_code_to_id()
    assert mapping == {"8000": 1, "9000": 2}


@pytest.mark.asyncio
async def test_fetch_industry_code_to_id_items_wrapper(
    settings: Settings, rate_limiter: RateLimiterRegistry, mock_auth: AsyncMock
) -> None:
    """Should handle paginated response with items wrapper."""
    http_client = _make_client({"items": [{"id": 5, "code": "4000"}], "total": 1})
    api = StockTrackerApiClient(settings, mock_auth, rate_limiter, http_client)
    mapping = await api.fetch_industry_code_to_id()
    assert mapping == {"4000": 5}


@pytest.mark.asyncio
async def test_fetch_industry_code_strips_whitespace(
    settings: Settings, rate_limiter: RateLimiterRegistry, mock_auth: AsyncMock
) -> None:
    """code field validator should strip whitespace and convert to str."""
    http_client = _make_client([{"id": 3, "code": "  8000  "}])
    api = StockTrackerApiClient(settings, mock_auth, rate_limiter, http_client)
    mapping = await api.fetch_industry_code_to_id()
    assert "8000" in mapping


# ---------------------------------------------------------------------------
# fetch_stock_symbol_to_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_stock_symbol_to_id(
    settings: Settings, rate_limiter: RateLimiterRegistry, mock_auth: AsyncMock
) -> None:
    """Should parse stock list into symbol→id mapping with uppercased symbols."""
    http_client = _make_client([{"id": 10, "symbol": "vcb"}, {"id": 20, "symbol": "VIC"}])
    api = StockTrackerApiClient(settings, mock_auth, rate_limiter, http_client)
    mapping = await api.fetch_stock_symbol_to_id()
    assert mapping == {"VCB": 10, "VIC": 20}


@pytest.mark.asyncio
async def test_fetch_stock_symbol_strips_whitespace(
    settings: Settings, rate_limiter: RateLimiterRegistry, mock_auth: AsyncMock
) -> None:
    """symbol field validator should strip whitespace."""
    http_client = _make_client([{"id": 1, "symbol": " VCB "}])
    api = StockTrackerApiClient(settings, mock_auth, rate_limiter, http_client)
    mapping = await api.fetch_stock_symbol_to_id()
    assert "VCB" in mapping


# ---------------------------------------------------------------------------
# put_json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_json_sends_auth_header(
    settings: Settings, rate_limiter: RateLimiterRegistry, mock_auth: AsyncMock
) -> None:
    """put_json should attach Bearer token to Authorization header."""
    http_client = _make_client({"ok": True})
    api = StockTrackerApiClient(settings, mock_auth, rate_limiter, http_client)
    await api.put_json("/api/test", {"key": "value"})
    call_kwargs = http_client.put.call_args.kwargs
    assert "Authorization" in call_kwargs["headers"]
    assert call_kwargs["headers"]["Authorization"] == "Bearer bearer-token"
