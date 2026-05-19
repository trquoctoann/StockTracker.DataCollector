from __future__ import annotations

from pydantic import BaseModel, Field


class MarketIndex(BaseModel):
    symbol: str = Field(..., max_length=32)
    name: str
    description: str | None = None
    group: str | None = None
    stock_ids: list[int] = Field(default_factory=list)
