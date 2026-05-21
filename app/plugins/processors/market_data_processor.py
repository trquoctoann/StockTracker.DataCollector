from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import pandas as pd

from app.interfaces.base_processor import BaseProcessor
from app.schemas.market_data import (
    PriceHistoryInterval,
    StockIntradayRecord,
    StockIntradaySync,
    StockPriceHistoryRecord,
    StockPriceHistorySync,
)

DEFAULT_CHUNK_SIZE = 500


def _clean_float(v: object) -> float:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return 0.0
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _clean_int(v: object) -> int:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return 0
    try:
        return int(float(v))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _parse_datetime(v: object) -> datetime:
    if isinstance(v, datetime):
        return v
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return datetime.min
    s = str(v).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.min


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class MarketDataPandasProcessor(BaseProcessor):
    """Transform vnstock Quote DataFrames into chunked sync payloads for RabbitMQ."""

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self._chunk_size = chunk_size

    def process(self, raw: object, **kwargs: Any) -> object:
        raise NotImplementedError("Use transform_price_history / transform_intraday")

    def transform_price_history(
        self,
        stock_id: int,
        df: pd.DataFrame,
        interval: str = "1D",
    ) -> list[StockPriceHistorySync]:
        if df.empty:
            return []
        parsed_interval = PriceHistoryInterval(interval)
        records: list[StockPriceHistoryRecord] = []
        for _, row in df.iterrows():
            records.append(
                StockPriceHistoryRecord(
                    time=_parse_datetime(row.get("time")),
                    open=_clean_float(row.get("open")),
                    high=_clean_float(row.get("high")),
                    low=_clean_float(row.get("low")),
                    close=_clean_float(row.get("close")),
                    volume=_clean_int(row.get("volume")),
                    stock_id=stock_id,
                )
            )
        chunked = _chunks(records, self._chunk_size)
        return [StockPriceHistorySync(stock_id=stock_id, interval=parsed_interval, records=chunk) for chunk in chunked]

    def transform_intraday(
        self,
        stock_id: int,
        df: pd.DataFrame,
    ) -> list[StockIntradaySync]:
        if df.empty:
            return []
        records: list[StockIntradayRecord] = []
        for _, row in df.iterrows():
            match_type_raw = row.get("match_type")
            match_type: str | None = None
            if match_type_raw is not None and not (isinstance(match_type_raw, float) and math.isnan(match_type_raw)):
                match_type = str(match_type_raw).strip().upper() or None
            data_source_raw = row.get("data_source_id") or row.get("id")
            data_source_id: str | None = None
            if data_source_raw is not None and not (isinstance(data_source_raw, float) and math.isnan(data_source_raw)):
                data_source_id = str(data_source_raw).strip() or None
            records.append(
                StockIntradayRecord(
                    time=_parse_datetime(row.get("time")),
                    price=_clean_float(row.get("price")),
                    volume=_clean_int(row.get("volume")),
                    match_type=match_type,
                    data_source_id=data_source_id,
                    stock_id=stock_id,
                )
            )
        chunked = _chunks(records, self._chunk_size)
        return [StockIntradaySync(stock_id=stock_id, records=chunk) for chunk in chunked]
