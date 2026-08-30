from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

import app.main as main_module
from app.archive.raw_archive import RawArchive
from app.core.exceptions import ArchiveError
from tests import make_settings


class FakeHttpClient:
    def __init__(self, **_kwargs: Any) -> None:
        self.is_closed = False

    async def __aenter__(self) -> FakeHttpClient:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        self.is_closed = True


@pytest.mark.asyncio
async def test_readiness_checks_raw_archive(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(
        raw_archive_enabled=True,
        raw_archive_access_key="local",
        raw_archive_secret_key="local-secret",
    )
    archive = AsyncMock(spec=RawArchive)
    monkeypatch.setattr(main_module, "_settings", settings)
    monkeypatch.setattr(main_module, "_auth", object())
    monkeypatch.setattr(main_module, "_http_client", FakeHttpClient())
    monkeypatch.setattr(main_module, "_raw_archive", archive)

    response = await main_module.readiness()

    assert response.status_code == 200
    assert json.loads(bytes(response.body))["checks"]["raw_archive"] == "ok"
    archive.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_readiness_fails_when_raw_archive_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(
        raw_archive_enabled=True,
        raw_archive_access_key="local",
        raw_archive_secret_key="local-secret",
    )
    archive = AsyncMock(spec=RawArchive)
    archive.ping.side_effect = ArchiveError("storage unavailable")
    monkeypatch.setattr(main_module, "_settings", settings)
    monkeypatch.setattr(main_module, "_auth", object())
    monkeypatch.setattr(main_module, "_http_client", FakeHttpClient())
    monkeypatch.setattr(main_module, "_raw_archive", archive)

    response = await main_module.readiness()

    assert response.status_code == 503
    assert json.loads(bytes(response.body))["checks"]["raw_archive"] == "unavailable"


@pytest.mark.asyncio
async def test_lifespan_releases_resources_when_application_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings()
    client = FakeHttpClient()
    monkeypatch.setattr(main_module, "Settings", lambda: settings)
    monkeypatch.setattr(main_module.httpx, "AsyncClient", lambda **_kwargs: client)

    with pytest.raises(RuntimeError, match="application failure"):
        async with main_module.lifespan(main_module.app):
            raise RuntimeError("application failure")

    assert client.is_closed is True
    assert main_module._http_client is None
    assert main_module._auth is None
    assert main_module._settings is None
