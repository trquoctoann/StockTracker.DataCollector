import pandas as pd
import pytest

from app.core.exceptions import SourceError
from app.plugins.processors.pandas_processor import ListingPandasProcessor
from app.plugins.sources.vnstock_source import IndexBasketRow


def test_transform_industries() -> None:
    df = pd.DataFrame(
        {
            "icb_code": ["8000", "9000"],
            "icb_name": ["Financials", "Technology"],
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
            "organ_name": ["Bank"],
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
            constituent_symbols=["VCB"],
        )
    ]
    out = proc.transform_market_indices(baskets, {"VCB": 1})
    assert out[0].stock_ids == [1]


def test_incomplete_index_mapping_is_not_sent() -> None:
    basket = IndexBasketRow("VN30", "VN30", None, None, ["VCB", "MISS"])
    with pytest.raises(SourceError, match="incomplete stock mapping"):
        ListingPandasProcessor().transform_market_indices([basket], {"VCB": 1})


def test_kbs_listing_has_no_icb_and_preserves_relationships() -> None:
    df = pd.DataFrame({"symbol": ["FPT"], "organ_name": ["FPT"], "exchange": ["HOSE"], "type": ["stock"]})
    item = ListingPandasProcessor().transform_stocks(df, {"8000": 1})[0]
    assert item.exchange == "HSX"
    assert item.type == "STOCK"
    assert item.industry_ids is None


def test_listing_schema_drift_fails_instead_of_empty_sync() -> None:
    with pytest.raises(SourceError, match="missing columns"):
        ListingPandasProcessor().transform_stocks(pd.DataFrame({"ticker": ["FPT"]}), {})
