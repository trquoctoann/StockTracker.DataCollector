from datetime import date

import pandas as pd
import pytest

from app.core.exceptions import SourceError
from app.plugins.processors.company_processor import CompanyPandasProcessor


def test_transform_profile_basic() -> None:
    df = pd.DataFrame(
        {
            "symbol": ["VCB"],
            "business_model": ["Ngân hàng thương mại"],
            "founded_date": ["2009-06-15"],
            "charter_capital": [47_325_000_000_000],
            "number_of_employees": [20_000],
            "listing_date": ["2009-06-30"],
            "ceo_name": ["Nguyen Van A"],
            "website": ["https://vcb.com.vn"],
        }
    )
    proc = CompanyPandasProcessor()
    result = proc.transform_profile(1, df)
    assert result.stock_id == 1
    assert result.symbol == "VCB"
    assert result.business_model == "Ngân hàng thương mại"
    assert result.founded_date == date(2009, 6, 15)
    assert result.charter_capital == 47_325_000_000_000
    assert result.number_of_employees == 20_000
    assert result.ceo_name == "Nguyen Van A"
    assert result.website == "https://vcb.com.vn"


def test_transform_profile_empty() -> None:
    proc = CompanyPandasProcessor()
    result = proc.transform_profile(99, pd.DataFrame())
    assert result.stock_id == 99
    assert result.symbol is None


def test_transform_shareholders() -> None:
    df = pd.DataFrame(
        {
            "name": ["Nguyen Van A", "Tran Van B"],
            "quantity": [1_500_000, 2_000_000],
            "ownership_percent": [5.2, 7.1],
            "updated_date": ["2026-01-15", "2026-02-20"],
        }
    )
    proc = CompanyPandasProcessor()
    result = proc.transform_shareholders(1, df)
    assert result.stock_id == 1
    assert len(result.records) == 2
    assert result.records[0].name == "Nguyen Van A"
    assert result.records[0].quantity == 1_500_000
    assert result.records[0].ownership_percent == 5.2
    assert result.records[0].updated_date == date(2026, 1, 15)


def test_transform_shareholders_skips_null_name() -> None:
    df = pd.DataFrame(
        {
            "name": [None, "Valid Name"],
            "quantity": [100, 200],
            "ownership_percent": [1.0, 2.0],
        }
    )
    proc = CompanyPandasProcessor()
    result = proc.transform_shareholders(1, df)
    assert len(result.records) == 1
    assert result.records[0].name == "Valid Name"


def test_transform_officers() -> None:
    df = pd.DataFrame(
        {
            "name": ["Nguyen CEO"],
            "position": ["Chủ tịch HĐQT"],
            "ownership_percent": [3.5],
            "quantity": [500_000],
        }
    )
    proc = CompanyPandasProcessor()
    result = proc.transform_officers(1, df)
    assert len(result.records) == 1
    assert result.records[0].name == "Nguyen CEO"
    assert result.records[0].position == "Chủ tịch HĐQT"
    assert result.records[0].ownership_percent == 3.5


def test_transform_affiliations() -> None:
    df = pd.DataFrame(
        {
            "code": ["VCBS"],
            "name": ["CTCP Chứng khoán Vietcombank"],
            "type": ["SUBSIDIARY"],
            "ownership_percent": [95.0],
        }
    )
    proc = CompanyPandasProcessor()
    result = proc.transform_affiliations(1, df)
    assert len(result.records) == 1
    assert result.records[0].code == "VCBS"
    assert result.records[0].type == "SUBSIDIARY"


def test_transform_events() -> None:
    df = pd.DataFrame(
        {
            "title": ["Đại hội cổ đông"],
            "public_date": ["2026-03-15 09:00:00"],
            "issue_date": [None],
            "source_url": ["https://example.com"],
            "record_date": ["2026-03-01"],
            "exright_date": [None],
        }
    )
    proc = CompanyPandasProcessor()
    result = proc.transform_events(1, df)
    assert len(result.records) == 1
    assert result.records[0].title == "Đại hội cổ đông"
    assert result.records[0].public_date == date(2026, 3, 15)
    assert result.records[0].record_date == date(2026, 3, 1)


def test_transform_news() -> None:
    df = pd.DataFrame(
        {
            "title": ["VCB tăng vốn"],
            "image_url": ["https://img.com/a.jpg"],
            "source_url": ["https://news.com/vcb"],
            "public_date": ["2026-04-01"],
            "language": ["vi"],
            "price_change_percent": [2.5],
        }
    )
    proc = CompanyPandasProcessor()
    result = proc.transform_news(1, df)
    assert len(result.records) == 1
    assert result.records[0].title == "VCB tăng vốn"
    assert result.records[0].language == "vi"
    assert result.records[0].price_change_percent == 2.5


def test_transform_news_empty() -> None:
    proc = CompanyPandasProcessor()
    result = proc.transform_news(1, pd.DataFrame())
    assert result.stock_id == 1
    assert len(result.records) == 0


def test_kbs_shareholder_mapping_and_stable_identity():
    df = pd.DataFrame(
        {
            "name": ["Example"],
            "shares_owned": [100],
            "ownership_percentage": [6.89],
            "update_date": ["2026-08-27T00:00:00"],
        }
    )
    df.attrs["source"] = "KBS"
    proc = CompanyPandasProcessor()
    first = proc.transform_shareholders(1, df).items[0]
    df.loc[0, "shares_owned"] = 200
    second = proc.transform_shareholders(1, df).items[0]
    assert first.quantity == 100
    assert first.ownership_percent == 6.89
    assert first.updated_date == date(2026, 8, 27)
    assert first.data_source_id == second.data_source_id


def test_vci_officers_aliases():
    df = pd.DataFrame(
        {
            "officer_name": ["Example"],
            "officer_position": ["CEO"],
            "officer_own_percent": [3.5],
            "officer_own_quantity": [100],
            "update_date": [pd.NaT],
        }
    )
    item = CompanyPandasProcessor().transform_officers(1, df).items[0]
    assert (item.name, item.position, item.quantity) == ("Example", "CEO", 100)
    assert item.updated_date is None


def test_kbs_profile_ambiguous_units_are_omitted():
    df = pd.DataFrame(
        {
            "symbol": ["FPT"],
            "founded_date": ["03/04/2002"],
            "listed_volume": [1714],
            "charter_capital": [17413],
            "branches": ["Two representative offices"],
            "number_of_employees": [pd.NA],
        }
    )
    df.attrs["source"] = "KBS"
    item = CompanyPandasProcessor().transform_profile(1, df)
    assert item.founded_date == date(2002, 4, 3)
    assert item.listing_volume is None
    assert item.charter_capital is None
    assert item.branches is None
    assert item.number_of_employees is None


def test_kbs_news_uses_article_id_and_publish_time():
    df = pd.DataFrame(
        {
            "article_id": [123],
            "title": ["Example"],
            "publish_time": ["2026-08-08T11:50:00"],
            "url": ["/2026/08/example.htm"],
        }
    )
    df.attrs["source"] = "KBS"
    item = CompanyPandasProcessor().transform_news(1, df).items[0]
    assert item.data_source_id == "kbs:news:123"
    assert item.public_date == date(2026, 8, 8)
    assert item.source_url == "/2026/08/example.htm"


def test_company_schema_drift_is_not_an_empty_snapshot():
    with pytest.raises(SourceError, match="missing columns"):
        CompanyPandasProcessor().transform_shareholders(1, pd.DataFrame({"unexpected": ["Example"]}))
