from __future__ import annotations

from pydantic import BaseModel, Field


class Industry(BaseModel):
    code: str = Field(..., max_length=20)
    name: str = Field(..., max_length=255)
    level: int = Field(..., ge=0)
