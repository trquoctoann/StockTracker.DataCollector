import pandas as pd

from app.plugins.processors.pandas_processor import ListingPandasProcessor
from app.plugins.sources.vnstock_source import IndexBasketRow


def test_transform_industries() -> None:
    df = pd.DataFrame(
        {
            "icb_code": ["8000", "9000"],
            "icb_name": ["Tài chính", "Công nghệ"],
            "level": [1, 2],
        }
    )
    proc = ListingPandasProcessor()
    out = proc.transform_industries(df)
    assert len(out) == 2
    assert out[0].code == "8000"
    assert out[0].level == 1


def test_transform_stocks_maps_industry() -> None:
    df = pd.DataFrame(
        {
            "symbol": ["VCB"],
            "organ_name": ["Ngân hàng"],
            "organ_short_name": ["Vietcombank"],
            "exchange": ["HOSE"],
            "type": ["STOCK"],
            "icb_code2": ["8000"],
        }
    )
    proc = ListingPandasProcessor()
    out = proc.transform_stocks(df, {"8000": 42})
    assert len(out) == 1
    assert out[0].symbol == "VCB"
    assert out[0].industry_ids == [42]


def test_transform_market_indices() -> None:
    proc = ListingPandasProcessor()
    baskets = [
        IndexBasketRow(
            symbol="VN30",
            name="VN30",
            description="d",
            group="HOSE Indices",
            constituent_symbols=["VCB", "MISS"],
        )
    ]
    out = proc.transform_market_indices(baskets, {"VCB": 1})
    assert out[0].stock_ids == [1]
