from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Company Profile (1:1 with stock)
# ---------------------------------------------------------------------------
class CompanyProfileSync(BaseModel):
    stock_id: int
    symbol: str | None = None  # Required by API when sent to StockTracker.API
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
    branches: int | None = None  # API expects int (number of branches)
    history: str | None = None


# ---------------------------------------------------------------------------
# Company Shareholder
# ---------------------------------------------------------------------------
class CompanyShareholderRecord(BaseModel):
    data_source_id: str | None = None
    name: str
    quantity: int | None = None
    ownership_percent: float | None = None
    updated_date: date | None = None


class CompanyShareholderSync(BaseModel):
    stock_id: int
    items: list[CompanyShareholderRecord] = Field(default_factory=list)

    @property
    def records(self) -> list[CompanyShareholderRecord]:
        return self.items


# ---------------------------------------------------------------------------
# Company Officer
# ---------------------------------------------------------------------------
class CompanyOfficerRecord(BaseModel):
    data_source_id: str | None = None
    name: str
    position: str | None = None
    ownership_percent: float | None = None
    quantity: int | None = None
    updated_date: date | None = None


class CompanyOfficerSync(BaseModel):
    stock_id: int
    items: list[CompanyOfficerRecord] = Field(default_factory=list)

    @property
    def records(self) -> list[CompanyOfficerRecord]:
        return self.items


# ---------------------------------------------------------------------------
# Company Affiliation (subsidiaries)
# ---------------------------------------------------------------------------
class CompanyAffiliationRecord(BaseModel):
    data_source_id: str | None = None
    code: str | None = None
    name: str
    type: str | None = Field(None, description="SUBSIDIARY, AFFILIATED, JOINT_VENTURE")
    ownership_percent: float | None = None


class CompanyAffiliationSync(BaseModel):
    stock_id: int
    items: list[CompanyAffiliationRecord] = Field(default_factory=list)

    @property
    def records(self) -> list[CompanyAffiliationRecord]:
        return self.items


# ---------------------------------------------------------------------------
# Company Event
# ---------------------------------------------------------------------------
class CompanyEventRecord(BaseModel):
    data_source_id: str | None = None
    title: str
    public_date: date | None = None
    issue_date: date | None = None
    source_url: str | None = None
    record_date: date | None = None
    exright_date: date | None = None


class CompanyEventSync(BaseModel):
    stock_id: int
    items: list[CompanyEventRecord] = Field(default_factory=list)

    @property
    def records(self) -> list[CompanyEventRecord]:
        return self.items


# ---------------------------------------------------------------------------
# Company News
# ---------------------------------------------------------------------------
class CompanyNewsRecord(BaseModel):
    data_source_id: str | None = None
    title: str
    image_url: str | None = None
    source_url: str | None = None
    public_date: date | None = None
    language: str | None = None
    price_change_percent: float | None = None


class CompanyNewsSync(BaseModel):
    stock_id: int
    items: list[CompanyNewsRecord] = Field(default_factory=list)

    @property
    def records(self) -> list[CompanyNewsRecord]:
        return self.items
