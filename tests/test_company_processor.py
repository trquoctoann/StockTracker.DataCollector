from datetime import date, datetime

import pandas as pd

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
    assert result.records[0].public_date == datetime(2026, 3, 15, 9, 0, 0)
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
