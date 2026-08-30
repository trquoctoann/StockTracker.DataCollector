from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PriceHistoryInterval(StrEnum):
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"  # Must match API PriceInterval.ONE_HOUR = "1h" (lowercase)
    ONE_DAY = "1D"
    ONE_WEEK = "1W"
    ONE_MONTH = "1M"


# ---------------------------------------------------------------------------
# Stock Price History
# ---------------------------------------------------------------------------
class StockPriceHistoryRecord(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float  # API UpsertStockPriceHistoryCommand uses float
    stock_id: int


class StockPriceHistorySync(BaseModel):
    stock_id: int
    interval: PriceHistoryInterval = PriceHistoryInterval.ONE_DAY
    records: list[StockPriceHistoryRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stock Intraday
# ---------------------------------------------------------------------------
class StockIntradayRecord(BaseModel):
    time: datetime
    price: float
    volume: float  # API UpsertStockIntradayCommand uses float
    match_type: str | None = Field(None, description="BUY or SELL; must match the API MatchType enum")
    data_source_id: str
    stock_id: int


class StockIntradaySync(BaseModel):
    stock_id: int
    records: list[StockIntradayRecord] = Field(default_factory=list)
