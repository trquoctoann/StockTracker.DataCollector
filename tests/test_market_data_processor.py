from datetime import datetime

import pandas as pd
import pytest

from app.core.exceptions import SourceError
from app.plugins.processors.market_data_processor import MarketDataPandasProcessor
from app.schemas.market_data import PriceHistoryInterval


def test_transform_price_history_basic() -> None:
    df = pd.DataFrame(
        {
            "time": ["2026-05-08", "2026-05-09"],
            "open": [15000, 15300],
            "high": [15500, 15600],
            "low": [14900, 15100],
            "close": [15300, 15400],
            "volume": [2500000, 3000000],
        }
    )
    proc = MarketDataPandasProcessor(chunk_size=500)
    result = proc.transform_price_history(1, df, interval="1D")
    assert len(result) == 1
    assert result[0].stock_id == 1
    assert result[0].interval == PriceHistoryInterval.ONE_DAY
    assert len(result[0].records) == 2
    assert result[0].records[0].open == 15000
    assert result[0].records[0].close == 15300
    assert result[0].records[0].volume == 2500000
    assert result[0].records[0].stock_id == 1


def test_transform_price_history_empty() -> None:
    proc = MarketDataPandasProcessor()
    result = proc.transform_price_history(1, pd.DataFrame())
    assert result == []


def test_transform_price_history_chunking() -> None:
    n = 1200
    df = pd.DataFrame(
        {
            "time": [f"2026-01-{(i % 28) + 1:02d}" for i in range(n)],
            "open": [100.0] * n,
            "high": [110.0] * n,
            "low": [90.0] * n,
            "close": [105.0] * n,
            "volume": [1000] * n,
        }
    )
    proc = MarketDataPandasProcessor(chunk_size=500)
    result = proc.transform_price_history(1, df)
    assert len(result) == 3  # 1200 / 500 = 2.4, rounded up to 3 chunks
    assert len(result[0].records) == 500
    assert len(result[1].records) == 500
    assert len(result[2].records) == 200


def test_transform_intraday_basic() -> None:
    df = pd.DataFrame(
        {
            "time": ["2026-05-09T10:15:23"],
            "price": [15200],
            "volume": [5000],
            "match_type": ["BUY"],
            "data_source_id": ["vci_trade_12345"],
        }
    )
    proc = MarketDataPandasProcessor()
    result = proc.transform_intraday(1, df)
    assert len(result) == 1
    assert result[0].stock_id == 1
    assert len(result[0].records) == 1
    rec = result[0].records[0]
    assert rec.price == 15200
    assert rec.volume == 5000
    assert rec.match_type == "BUY"
    assert rec.data_source_id == "vci_trade_12345"
    assert rec.time == datetime(2026, 5, 9, 10, 15, 23)


def test_transform_intraday_empty() -> None:
    proc = MarketDataPandasProcessor()
    result = proc.transform_intraday(1, pd.DataFrame())
    assert result == []


def test_transform_intraday_chunking() -> None:
    n = 1500
    df = pd.DataFrame(
        {
            "time": ["2026-05-09T10:00:00"] * n,
            "price": [100.0] * n,
            "volume": [10] * n,
            "match_type": ["BUY"] * n,
        }
    )
    proc = MarketDataPandasProcessor(chunk_size=500)
    result = proc.transform_intraday(1, df)
    assert len(result) == 3  # 1500 / 500 = 3 chunks
    assert all(len(chunk.records) == 500 for chunk in result)


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), pd.NA, "bad", -1])
def test_invalid_price_is_rejected_not_zero(value):
    df = pd.DataFrame({"time": ["2026-08-27"], "price": [value], "volume": [10]})
    with pytest.raises(SourceError, match="numeric"):
        MarketDataPandasProcessor().transform_intraday(1, df)


@pytest.mark.parametrize("value", [None, pd.NaT, "bad", "0001-01-01", "10:30:00"])
def test_invalid_timestamp_is_not_fabricated(value):
    df = pd.DataFrame({"time": [value], "price": [72.5], "volume": [10]})
    with pytest.raises(SourceError, match="timestamp"):
        MarketDataPandasProcessor().transform_intraday(1, df)


@pytest.mark.parametrize("side,expected", [("buy", "BUY"), ("S", "SELL"), ("ato", None), ("atc", None), (pd.NA, None)])
def test_intraday_side_and_nullable_source_id(side, expected):
    df = pd.DataFrame(
        {
            "time": ["2026-08-27T03:15:23.123Z"],
            "price": [72.5],
            "volume": [10],
            "match_type": [side],
            "data_source_id": [pd.NA],
            "id": [0],
        }
    )
    record = MarketDataPandasProcessor().transform_intraday(1, df)[0].records[0]
    assert record.match_type == expected
    assert record.data_source_id.startswith("vnstock:trade:")
    assert record.time == datetime(2026, 8, 27, 10, 15, 23, 123000)
    assert record.price == 72.5  # vnstock equity prices are already in thousands of VND


def test_missing_market_columns_raise_schema_error():
    with pytest.raises(SourceError, match="missing columns"):
        MarketDataPandasProcessor().transform_price_history(1, pd.DataFrame({"time": ["2026-08-27"]}))


def test_daily_candle_key_is_provider_independent():
    df = pd.DataFrame(
        {"time": ["2026-08-27T07:00:00"], "open": [70], "high": [73], "low": [69], "close": [72.5], "volume": [10]}
    )
    record = MarketDataPandasProcessor().transform_price_history(1, df)[0].records[0]
    assert record.time == datetime(2026, 8, 27)
