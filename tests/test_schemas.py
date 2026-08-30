"""Unit tests for Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.industry import Industry
from app.schemas.market_data import PriceHistoryInterval, StockIntradaySync, StockPriceHistorySync
from app.schemas.market_index import MarketIndex
from app.schemas.stock import Stock

# ---------------------------------------------------------------------------
# Industry schema
# ---------------------------------------------------------------------------


def test_industry_valid() -> None:
    ind = Industry(code="8000", name="Financials", level=1)
    assert ind.code == "8000"
    assert ind.name == "Financials"
    assert ind.level == 1


def test_industry_code_max_length() -> None:
    """Code longer than 20 chars should fail validation."""
    with pytest.raises(ValidationError):
        Industry(code="X" * 21, name="Test", level=1)


def test_industry_name_max_length() -> None:
    """Name longer than 255 chars should fail validation."""
    with pytest.raises(ValidationError):
        Industry(code="0000", name="N" * 256, level=1)


def test_industry_level_non_negative() -> None:
    """Level must be >= 0."""
    with pytest.raises(ValidationError):
        Industry(code="0000", name="Test", level=-1)


# ---------------------------------------------------------------------------
# Stock schema
# ---------------------------------------------------------------------------


def test_stock_valid() -> None:
    s = Stock(symbol="VCB", name="Vietcombank", exchange="HOSE", type="STOCK", industry_ids=[1, 2])
    assert s.symbol == "VCB"
    assert s.industry_ids == [1, 2]
    assert s.short_name is None


def test_stock_symbol_max_length() -> None:
    """Symbol longer than 20 chars should fail validation."""
    with pytest.raises(ValidationError):
        Stock(symbol="V" * 21, name="Test", exchange="HOSE", type="STOCK")


def test_stock_industry_ids_default_preserves_existing() -> None:
    s = Stock(symbol="VCB", name="Test", exchange="HOSE", type="STOCK")
    assert s.industry_ids is None


# ---------------------------------------------------------------------------
# MarketIndex schema
# ---------------------------------------------------------------------------


def test_market_index_valid() -> None:
    idx = MarketIndex(symbol="VN30", name="VN30 Index", stock_ids=[1, 2, 3])
    assert idx.symbol == "VN30"
    assert len(idx.stock_ids) == 3
    assert idx.description is None
    assert idx.group is None


def test_market_index_stock_ids_default_empty() -> None:
    idx = MarketIndex(symbol="HNX30", name="HNX30 Index")
    assert idx.stock_ids == []


# ---------------------------------------------------------------------------
# PriceHistoryInterval enum
# ---------------------------------------------------------------------------


def test_price_history_interval_values() -> None:
    """All interval values should match expected strings."""
    assert PriceHistoryInterval.ONE_MINUTE == "1m"
    assert PriceHistoryInterval.FIVE_MINUTES == "5m"
    assert PriceHistoryInterval.FIFTEEN_MINUTES == "15m"
    assert PriceHistoryInterval.THIRTY_MINUTES == "30m"
    assert PriceHistoryInterval.ONE_HOUR == "1h"
    assert PriceHistoryInterval.ONE_DAY == "1D"
    assert PriceHistoryInterval.ONE_WEEK == "1W"
    assert PriceHistoryInterval.ONE_MONTH == "1M"


def test_price_history_interval_from_string() -> None:
    """Should be constructable from string value."""
    interval = PriceHistoryInterval("1D")
    assert interval == PriceHistoryInterval.ONE_DAY


def test_price_history_interval_invalid_raises() -> None:
    """Invalid interval string should raise ValueError."""
    with pytest.raises(ValueError):
        PriceHistoryInterval("99X")


# ---------------------------------------------------------------------------
# StockPriceHistorySync schema
# ---------------------------------------------------------------------------


def test_stock_price_history_sync_defaults() -> None:
    sync = StockPriceHistorySync(stock_id=1)
    assert sync.interval == PriceHistoryInterval.ONE_DAY
    assert sync.records == []


def test_stock_price_history_sync_model_dump_json() -> None:
    """model_dump(mode='json') should serialize datetime to ISO string."""
    from app.schemas.market_data import StockPriceHistoryRecord

    record = StockPriceHistoryRecord(
        time=datetime(2026, 5, 8, 0, 0, 0),
        open=100.0,
        high=110.0,
        low=90.0,
        close=105.0,
        volume=1000,
        stock_id=1,
    )
    sync = StockPriceHistorySync(stock_id=1, interval=PriceHistoryInterval.ONE_DAY, records=[record])
    data = sync.model_dump(mode="json")
    assert isinstance(data["records"][0]["time"], str)


# ---------------------------------------------------------------------------
# StockIntradaySync schema
# ---------------------------------------------------------------------------


def test_stock_intraday_sync_defaults() -> None:
    sync = StockIntradaySync(stock_id=5)
    assert sync.records == []
