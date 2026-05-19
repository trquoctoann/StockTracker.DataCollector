from __future__ import annotations

from pydantic import BaseModel, Field


class Stock(BaseModel):
    symbol: str = Field(..., max_length=20)
    name: str
    short_name: str | None = None
    exchange: str = Field(..., description="HOSE, HNX, UPCOM")
    type: str = Field(..., description="STOCK, ETF, FUND, ...")
    industry_ids: list[int] = Field(default_factory=list)
