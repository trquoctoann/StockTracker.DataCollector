from typing import Any

from app.core.config import Settings


def make_settings(**overrides: Any) -> Settings:
    """Do not read the developer's .env; retain BaseSettings env validation."""
    options: dict[str, Any] = {"_env_file": None, **overrides}
    return Settings(**options)
