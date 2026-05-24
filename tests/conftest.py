"""Root conftest: patch environment variables needed by Settings() during tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure Settings() can be instantiated without a real .env file."""
    defaults: dict[str, str] = {
        "STOCKTRACKER_API_BASE_URL": "http://localhost:5000",
        "KEYCLOAK_BASE_URL": "http://localhost:8080",
        "KEYCLOAK_REALM": "stocktracker",
        "KEYCLOAK_CLIENT_ID": "data-collector-service",
        "KEYCLOAK_CLIENT_SECRET": "test-secret",
        "RABBITMQ_URL": "amqp://guest:guest@localhost:5672/",
        "RABBITMQ_ENABLED": "false",
        "SCHEDULER_ENABLED": "false",
        "LOG_JSON": "false",
    }
    for key, value in defaults.items():
        if key not in os.environ:
            monkeypatch.setenv(key, value)
