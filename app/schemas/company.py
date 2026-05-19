from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Company Profile (1:1 with stock)
# ---------------------------------------------------------------------------
class CompanyProfileSync(BaseModel):
    stock_id: int
    symbol: str | None = None
    business_model: str | None = None
    founded_date: date | None = None
    charter_capital: float | None = None
    number_of_employees: int | None = None
    listing_date: date | None = None
    par_value: float | None = None
    listing_price: float | None = None
    listing_volume: int | None = None
    ceo_name: str | None = None
    ceo_position: str | None = None
    inspector_name: str | None = None
    inspector_position: str | None = None
    establishment_license: str | None = None
    business_code: str | None = None
    tax_id: str | None = None
    auditor: str | None = None
    company_type: str | None = None
    address: str | None = None
    phone: str | None = None
    fax: str | None = None
    email: str | None = None
    website: str | None = None
    branches: str | None = None
    history: str | None = None


# ---------------------------------------------------------------------------
# Company Shareholder
# ---------------------------------------------------------------------------
class CompanyShareholderRecord(BaseModel):
    name: str
    quantity: int | None = None
    ownership_percent: float | None = None
    updated_date: date | None = None


class CompanyShareholderSync(BaseModel):
    stock_id: int
    records: list[CompanyShareholderRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Company Officer
# ---------------------------------------------------------------------------
class CompanyOfficerRecord(BaseModel):
    name: str
    position: str | None = None
    ownership_percent: float | None = None
    quantity: int | None = None
    updated_date: date | None = None


class CompanyOfficerSync(BaseModel):
    stock_id: int
    records: list[CompanyOfficerRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Company Affiliation (subsidiaries)
# ---------------------------------------------------------------------------
class CompanyAffiliationRecord(BaseModel):
    code: str | None = None
    name: str
    type: str | None = Field(None, description="SUBSIDIARY, AFFILIATED, JOINT_VENTURE")
    ownership_percent: float | None = None


class CompanyAffiliationSync(BaseModel):
    stock_id: int
    records: list[CompanyAffiliationRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Company Event
# ---------------------------------------------------------------------------
class CompanyEventRecord(BaseModel):
    title: str
    public_date: datetime | None = None
    issue_date: datetime | None = None
    source_url: str | None = None
    record_date: date | None = None
    exright_date: date | None = None


class CompanyEventSync(BaseModel):
    stock_id: int
    records: list[CompanyEventRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Company News
# ---------------------------------------------------------------------------
class CompanyNewsRecord(BaseModel):
    title: str
    image_url: str | None = None
    source_url: str | None = None
    public_date: datetime | None = None
    language: str | None = None
    price_change_percent: float | None = None


class CompanyNewsSync(BaseModel):
    stock_id: int
    records: list[CompanyNewsRecord] = Field(default_factory=list)
