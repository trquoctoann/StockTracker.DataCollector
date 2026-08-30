from __future__ import annotations

from typing import Any

import pandas as pd

from app.plugins.processors.pandas_utils import (
    clean_date as _clean_date,
)
from app.plugins.processors.pandas_utils import (
    clean_float as _clean_float,
)
from app.plugins.processors.pandas_utils import (
    clean_int as _clean_int,
)
from app.plugins.processors.pandas_utils import (
    clean_str as _clean_str,
)
from app.plugins.processors.pandas_utils import (
    normalize_columns,
    record_id,
)
from app.schemas.company import (
    CompanyAffiliationRecord,
    CompanyAffiliationSync,
    CompanyEventRecord,
    CompanyEventSync,
    CompanyNewsRecord,
    CompanyNewsSync,
    CompanyOfficerRecord,
    CompanyOfficerSync,
    CompanyProfileSync,
    CompanyShareholderRecord,
    CompanyShareholderSync,
)


def _safe_get(row: Any, col: str) -> Any:
    """Safely get a value from a pandas row, returning None if column missing."""
    try:
        return row.get(col)
    except AttributeError:
        return getattr(row, col, None)


class CompanyPandasProcessor:
    """Transform vnstock Company DataFrames into sync payloads."""

    def transform_profile(self, stock_id: int, df: pd.DataFrame, symbol: str = "") -> CompanyProfileSync:
        if df.empty:
            return CompanyProfileSync(stock_id=stock_id, symbol=_clean_str(symbol))
        df = normalize_columns(
            df,
            {
                "listed_volume": "listing_volume",
                "num_employees": "number_of_employees",
                "company_profile": "business_model",
            },
            set(),
        )
        if str(df.attrs.get("source", "")).upper() == "KBS":
            # KBS CC/VL are rounded display units, not canonical VND/shares.
            # Omit until a verified unit contract exists; never guess scaling.
            df = df.drop(columns=["charter_capital", "listing_volume"], errors="ignore")
        row = df.iloc[0]
        # symbol from vnstock overview, fallback to the symbol passed from stock_map
        raw_symbol = _clean_str(_safe_get(row, "symbol")) or symbol
        return CompanyProfileSync(
            stock_id=stock_id,
            symbol=raw_symbol,
            business_model=_clean_str(_safe_get(row, "business_model")),
            founded_date=_clean_date(_safe_get(row, "founded_date")),
            charter_capital=_clean_float(_safe_get(row, "charter_capital")),
            number_of_employees=_clean_int(_safe_get(row, "number_of_employees")),
            listing_date=_clean_date(_safe_get(row, "listing_date")),
            par_value=_clean_float(_safe_get(row, "par_value")),
            listing_price=_clean_float(_safe_get(row, "listing_price")),
            listing_volume=_clean_int(_safe_get(row, "listing_volume")),
            ceo_name=_clean_str(_safe_get(row, "ceo_name")),
            ceo_position=_clean_str(_safe_get(row, "ceo_position")),
            inspector_name=_clean_str(_safe_get(row, "inspector_name")),
            inspector_position=_clean_str(_safe_get(row, "inspector_position")),
            establishment_license=_clean_str(_safe_get(row, "establishment_license")),
            business_code=_clean_str(_safe_get(row, "business_code")),
            tax_id=_clean_str(_safe_get(row, "tax_id")),
            auditor=_clean_str(_safe_get(row, "auditor")),
            company_type=_clean_str(_safe_get(row, "company_type")),
            address=_clean_str(_safe_get(row, "address")),
            phone=_clean_str(_safe_get(row, "phone")),
            fax=_clean_str(_safe_get(row, "fax")),
            email=_clean_str(_safe_get(row, "email")),
            website=_clean_str(_safe_get(row, "website")),
            branches=_clean_int(_safe_get(row, "branches")),
            history=_clean_str(_safe_get(row, "history")),
        )

    def transform_shareholders(self, stock_id: int, df: pd.DataFrame) -> CompanyShareholderSync:
        if df.empty:
            return CompanyShareholderSync(stock_id=stock_id)
        df = normalize_columns(
            df,
            {
                "share_holder": "name",
                "shares_owned": "quantity",
                "ownership_percentage": "ownership_percent",
                "share_own_percent": "ownership_percent",
                "update_date": "updated_date",
            },
            {"name"},
        )
        records: list[CompanyShareholderRecord] = []
        for _, row in df.iterrows():
            name = _clean_str(row.get("name"))
            if name is None:
                continue
            records.append(
                CompanyShareholderRecord(
                    data_source_id=record_id(row, df, "shareholder", name),
                    name=name,
                    quantity=_clean_int(row.get("quantity")),
                    ownership_percent=_clean_float(row.get("ownership_percent")),
                    updated_date=_clean_date(row.get("updated_date")),
                )
            )
        return CompanyShareholderSync(stock_id=stock_id, items=records)

    def transform_officers(self, stock_id: int, df: pd.DataFrame) -> CompanyOfficerSync:
        if df.empty:
            return CompanyOfficerSync(stock_id=stock_id)
        df = normalize_columns(
            df,
            {
                "officer_name": "name",
                "officer_position": "position",
                "officer_own_percent": "ownership_percent",
                "officer_own_quantity": "quantity",
                "update_date": "updated_date",
            },
            {"name"},
        )
        records: list[CompanyOfficerRecord] = []
        for _, row in df.iterrows():
            name = _clean_str(row.get("name"))
            if name is None:
                continue
            records.append(
                CompanyOfficerRecord(
                    data_source_id=record_id(row, df, "officer", name, _clean_str(row.get("position"))),
                    name=name,
                    position=_clean_str(row.get("position")),
                    ownership_percent=_clean_float(row.get("ownership_percent")),
                    quantity=_clean_int(row.get("quantity")),
                    updated_date=_clean_date(row.get("updated_date")),
                )
            )
        return CompanyOfficerSync(stock_id=stock_id, items=records)

    def transform_affiliations(self, stock_id: int, df: pd.DataFrame) -> CompanyAffiliationSync:
        if df.empty:
            return CompanyAffiliationSync(stock_id=stock_id)
        df = normalize_columns(df, {"organ_name": "name", "sub_organ_code": "code"}, {"name"})
        records: list[CompanyAffiliationRecord] = []
        for _, row in df.iterrows():
            name = _clean_str(row.get("name"))
            if name is None:
                continue
            records.append(
                CompanyAffiliationRecord(
                    data_source_id=record_id(row, df, "affiliation", _clean_str(row.get("code")) or name),
                    code=_clean_str(row.get("code")),
                    name=name,
                    type={"c\u00f4ng ty con": "SUBSIDIARY", "c\u00f4ng ty li\u00ean k\u1ebft": "AFFILIATED"}.get(
                        _clean_str(row.get("type")) or "", _clean_str(row.get("type"))
                    ),
                    ownership_percent=_clean_float(row.get("ownership_percent")),
                )
            )
        return CompanyAffiliationSync(stock_id=stock_id, items=records)

    def transform_events(self, stock_id: int, df: pd.DataFrame) -> CompanyEventSync:
        if df.empty:
            return CompanyEventSync(stock_id=stock_id)
        df = normalize_columns(
            df,
            {
                "event_name": "title",
                "event_title": "title",
                "event_list_name": "title",
                "ex_right_date": "exright_date",
            },
            {"title"},
        )
        records: list[CompanyEventRecord] = []
        for _, row in df.iterrows():
            title = _clean_str(row.get("title"))
            if title is None:
                continue
            records.append(
                CompanyEventRecord(
                    data_source_id=record_id(
                        row, df, "event", title, _clean_date(row.get("public_date")), _clean_str(row.get("source_url"))
                    ),
                    title=title,
                    public_date=_clean_date(row.get("public_date")),
                    issue_date=_clean_date(row.get("issue_date")),
                    source_url=_clean_str(row.get("source_url")),
                    record_date=_clean_date(row.get("record_date")),
                    exright_date=_clean_date(row.get("exright_date")),
                )
            )
        return CompanyEventSync(stock_id=stock_id, items=records)

    def transform_news(self, stock_id: int, df: pd.DataFrame) -> CompanyNewsSync:
        if df.empty:
            return CompanyNewsSync(stock_id=stock_id)
        df = normalize_columns(
            df,
            {
                "news_title": "title",
                "publish_date": "public_date",
                "publish_time": "public_date",
                "news_source_link": "source_url",
                "url": "source_url",
            },
            {"title"},
        )
        records: list[CompanyNewsRecord] = []
        for _, row in df.iterrows():
            title = _clean_str(row.get("title"))
            if title is None:
                continue
            records.append(
                CompanyNewsRecord(
                    data_source_id=record_id(
                        row, df, "news", title, _clean_date(row.get("public_date")), _clean_str(row.get("source_url"))
                    ),
                    title=title,
                    image_url=_clean_str(row.get("image_url")),
                    source_url=_clean_str(row.get("source_url")),
                    public_date=_clean_date(row.get("public_date")),
                    language=_clean_str(row.get("language")),
                    price_change_percent=_clean_float(row.get("price_change_percent")),
                )
            )
        return CompanyNewsSync(stock_id=stock_id, items=records)
