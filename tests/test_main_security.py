from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.main import require_pipeline_operator


@pytest.mark.asyncio
async def test_pipeline_operator_role_is_required(monkeypatch) -> None:
    auth = AsyncMock()
    auth.introspect.return_value = {
        "active": True,
        "realm_access": {"roles": ["pipeline_operator"]},
    }
    monkeypatch.setattr("app.main.get_auth", lambda: auth)

    await require_pipeline_operator(HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"))


@pytest.mark.asyncio
async def test_system_admin_without_pipeline_role_is_rejected(monkeypatch) -> None:
    auth = AsyncMock()
    auth.introspect.return_value = {
        "active": True,
        "realm_access": {"roles": ["system_admin"]},
    }
    monkeypatch.setattr("app.main.get_auth", lambda: auth)

    with pytest.raises(HTTPException) as exc_info:
        await require_pipeline_operator(HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"))

    assert exc_info.value.status_code == 403
