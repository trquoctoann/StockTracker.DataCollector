from datetime import datetime

import pandas as pd

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
    assert len(result) == 3  # 1200 / 500 = 2.4 → 3 chunks
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
