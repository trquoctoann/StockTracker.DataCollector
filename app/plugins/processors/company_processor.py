from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import pandas as pd

from app.interfaces.base_processor import BaseProcessor
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


def _clean_str(v: object) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v).strip()
    return s or None


def _clean_float(v: object) -> float | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _clean_int(v: object) -> int | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    try:
        return int(float(v))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _clean_date(v: object) -> date | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _clean_datetime(v: object) -> datetime | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime.combine(v, datetime.min.time())
    s = str(v).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _safe_get(row: Any, col: str) -> Any:
    """Safely get a value from a pandas row, returning None if column missing."""
    try:
        return row.get(col)
    except AttributeError:
        return getattr(row, col, None)


class CompanyPandasProcessor(BaseProcessor):
    """Transform vnstock Company DataFrames into sync payloads."""

    def process(self, raw: object, **kwargs: Any) -> object:
        raise NotImplementedError("Use transform_profile / transform_shareholders / transform_officers / etc.")

    def transform_profile(self, stock_id: int, df: pd.DataFrame) -> CompanyProfileSync:
        if df.empty:
            return CompanyProfileSync(stock_id=stock_id)
        row = df.iloc[0]
        return CompanyProfileSync(
            stock_id=stock_id,
            symbol=_clean_str(_safe_get(row, "symbol")),
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
            branches=_clean_str(_safe_get(row, "branches")),
            history=_clean_str(_safe_get(row, "history")),
        )

    def transform_shareholders(self, stock_id: int, df: pd.DataFrame) -> CompanyShareholderSync:
        if df.empty:
            return CompanyShareholderSync(stock_id=stock_id)
        records: list[CompanyShareholderRecord] = []
        for _, row in df.iterrows():
            name = _clean_str(row.get("name"))
            if name is None:
                continue
            records.append(
                CompanyShareholderRecord(
                    name=name,
                    quantity=_clean_int(row.get("quantity")),
                    ownership_percent=_clean_float(row.get("ownership_percent")),
                    updated_date=_clean_date(row.get("updated_date")),
                )
            )
        return CompanyShareholderSync(stock_id=stock_id, records=records)

    def transform_officers(self, stock_id: int, df: pd.DataFrame) -> CompanyOfficerSync:
        if df.empty:
            return CompanyOfficerSync(stock_id=stock_id)
        records: list[CompanyOfficerRecord] = []
        for _, row in df.iterrows():
            name = _clean_str(row.get("name"))
            if name is None:
                continue
            records.append(
                CompanyOfficerRecord(
                    name=name,
                    position=_clean_str(row.get("position")),
                    ownership_percent=_clean_float(row.get("ownership_percent")),
                    quantity=_clean_int(row.get("quantity")),
                    updated_date=_clean_date(row.get("updated_date")),
                )
            )
        return CompanyOfficerSync(stock_id=stock_id, records=records)

    def transform_affiliations(self, stock_id: int, df: pd.DataFrame) -> CompanyAffiliationSync:
        if df.empty:
            return CompanyAffiliationSync(stock_id=stock_id)
        records: list[CompanyAffiliationRecord] = []
        for _, row in df.iterrows():
            name = _clean_str(row.get("name"))
            if name is None:
                continue
            records.append(
                CompanyAffiliationRecord(
                    code=_clean_str(row.get("code")),
                    name=name,
                    type=_clean_str(row.get("type")),
                    ownership_percent=_clean_float(row.get("ownership_percent")),
                )
            )
        return CompanyAffiliationSync(stock_id=stock_id, records=records)

    def transform_events(self, stock_id: int, df: pd.DataFrame) -> CompanyEventSync:
        if df.empty:
            return CompanyEventSync(stock_id=stock_id)
        records: list[CompanyEventRecord] = []
        for _, row in df.iterrows():
            title = _clean_str(row.get("title"))
            if title is None:
                continue
            records.append(
                CompanyEventRecord(
                    title=title,
                    public_date=_clean_datetime(row.get("public_date")),
                    issue_date=_clean_datetime(row.get("issue_date")),
                    source_url=_clean_str(row.get("source_url")),
                    record_date=_clean_date(row.get("record_date")),
                    exright_date=_clean_date(row.get("exright_date")),
                )
            )
        return CompanyEventSync(stock_id=stock_id, records=records)

    def transform_news(self, stock_id: int, df: pd.DataFrame) -> CompanyNewsSync:
        if df.empty:
            return CompanyNewsSync(stock_id=stock_id)
        records: list[CompanyNewsRecord] = []
        for _, row in df.iterrows():
            title = _clean_str(row.get("title"))
            if title is None:
                continue
            records.append(
                CompanyNewsRecord(
                    title=title,
                    image_url=_clean_str(row.get("image_url")),
                    source_url=_clean_str(row.get("source_url")),
                    public_date=_clean_datetime(row.get("public_date")),
                    language=_clean_str(row.get("language")),
                    price_change_percent=_clean_float(row.get("price_change_percent")),
                )
            )
        return CompanyNewsSync(stock_id=stock_id, records=records)
