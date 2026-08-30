from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd

from app.core.exceptions import SourceError
from app.plugins.processors.pandas_utils import clean_datetime, clean_float, clean_str, normalize_columns, record_id
from app.schemas.market_data import (
    PriceHistoryInterval,
    StockIntradayRecord,
    StockIntradaySync,
    StockPriceHistoryRecord,
    StockPriceHistorySync,
)

DEFAULT_CHUNK_SIZE = 500


def _clean_float(v: object) -> float:
    result = clean_float(v)
    if result is None or result < 0:
        raise SourceError(f"Invalid market numeric value: {v!r}")
    return result


def _parse_datetime(v: object) -> datetime:
    if isinstance(v, str) and not re.match(r"^\d{4}-\d{2}-\d{2}", v):
        raise SourceError(f"Invalid market timestamp: {v!r}")
    result = clean_datetime(v)
    if result is None or result.year < 1900:
        raise SourceError(f"Invalid market timestamp: {v!r}")
    return result


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class MarketDataPandasProcessor:
    """Transform vnstock Quote DataFrames into chunked sync payloads for RabbitMQ."""

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        self._chunk_size = chunk_size

    def transform_price_history(
        self,
        stock_id: int,
        df: pd.DataFrame,
        interval: str = "1D",
    ) -> list[StockPriceHistorySync]:
        if df.empty:
            return []
        df = normalize_columns(df, {}, {"time", "open", "high", "low", "close", "volume"})
        parsed_interval = PriceHistoryInterval(interval)
        records: list[StockPriceHistoryRecord] = []
        for _, row in df.iterrows():
            timestamp = _parse_datetime(row.get("time"))
            if interval in {"1D", "1W", "1M"}:
                # KBS daily candles use 07:00, VCI uses midnight. The natural
                # key must be the same when switching the equity provider.
                timestamp = datetime.combine(timestamp.date(), datetime.min.time())
            records.append(
                StockPriceHistoryRecord(
                    time=timestamp,
                    open=_clean_float(row.get("open")),
                    high=_clean_float(row.get("high")),
                    low=_clean_float(row.get("low")),
                    close=_clean_float(row.get("close")),
                    volume=_clean_float(row.get("volume")),
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
        df = normalize_columns(df, {}, {"time", "price", "volume"})
        records: list[StockIntradayRecord] = []
        for _, row in df.iterrows():
            timestamp = _parse_datetime(row.get("time"))
            price = _clean_float(row.get("price"))
            volume = _clean_float(row.get("volume"))
            side = (clean_str(row.get("match_type")) or "").upper()
            # API supports only directional BUY/SELL. Auction/unknown side is
            # unknown, not a buy or sell; do not poison the consumer with ATO/ATC.
            match_type = {"B": "BUY", "BUY": "BUY", "S": "SELL", "SELL": "SELL"}.get(side)
            data_source_id = record_id(row, df, "trade", timestamp, price, volume, match_type)
            records.append(
                StockIntradayRecord(
                    time=timestamp,
                    price=price,
                    volume=volume,
                    match_type=match_type,
                    data_source_id=data_source_id,
                    stock_id=stock_id,
                )
            )
        chunked = _chunks(records, self._chunk_size)
        return [StockIntradaySync(stock_id=stock_id, records=chunk) for chunk in chunked]
