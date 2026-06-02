from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "StockTracker.DataCollector"
    log_json: bool = False

    stocktracker_api_base_url: str = Field(
        default="http://localhost:5000",
        description="Base URL StockTracker.API",
    )
    api_path_industries_all: str = "/api/industries/all"
    api_path_stocks_all: str = "/api/stocks/all"
    api_path_industries_ingest: str = "/api/industries/sync"
    api_path_stocks_ingest: str = "/api/stocks/sync"
    api_path_market_indices_ingest: str = "/api/market-indices/sync"
    # NOTE: API router prefix is /api (no /v1 segment)

    keycloak_base_url: str = Field(
        default="http://localhost:8080",
        description="Base URL Keycloak (realm path thêm sau)",
    )
    keycloak_realm: str = "stocktracker"
    keycloak_client_id: str = "data-collector-service"
    keycloak_client_secret: str = Field(default="", description="Client secret M2M")

    http_timeout_seconds: float = 60.0
    keycloak_token_skew_seconds: float = 30.0

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "stocktracker"
    rabbitmq_exchange_type: str = "topic"
    rabbitmq_enabled: bool = False

    rate_limit_vnstock_per_second: float = Field(default=0.25, gt=0)
    rate_limit_vnstock_burst: int = Field(default=1, ge=1)
    rate_limit_http_per_second: float = 10.0
    rate_limit_http_burst: int = 20
    rate_limit_rabbitmq_per_second: float = 50.0
    rate_limit_rabbitmq_burst: int = 100

    # vnstock 4.0.7 Unified UI; KBS sectors are NOT ICB classifications.
    vnstock_listing_source: Literal["KBS", "VCI"] = "KBS"
    vnstock_indices_source: Literal["KBS", "VCI"] = "VCI"
    vnstock_company_source: Literal["KBS", "VCI"] = "KBS"
    vnstock_quote_source: Literal["KBS", "VCI"] = "KBS"

    scheduler_enabled: bool = False
    scheduler_cron_hour: int = 6
    scheduler_cron_minute: int = 0
    scheduler_timezone: str = "Asia/Ho_Chi_Minh"

    # Company sync endpoints (Phase 2)
    api_path_company_profile_sync: str = "/api/stocks/{stock_id}/profile/sync"
    api_path_company_shareholders_sync: str = "/api/stocks/{stock_id}/shareholders/sync"
    api_path_company_officers_sync: str = "/api/stocks/{stock_id}/officers/sync"
    api_path_company_affiliations_sync: str = "/api/stocks/{stock_id}/affiliations/sync"
    api_path_company_events_sync: str = "/api/stocks/{stock_id}/events/sync"
    api_path_company_news_sync: str = "/api/stocks/{stock_id}/news/sync"

    # Market data settings (Phase 3)
    market_data_chunk_size: int = Field(default=500, ge=1)
    vnstock_price_history_interval: Literal["1m", "5m", "15m", "30m", "1h", "1D", "1W", "1M"] = "1D"
    vnstock_history_start: date | None = None
    vnstock_history_end: date | None = None
    vnstock_history_lookback_days: int = Field(default=30, ge=1)
    vnstock_intraday_page_size: int = Field(default=100, ge=1, le=1000)
    vnstock_intraday_max_pages: int = Field(default=1, ge=1)
    rabbitmq_routing_key_price_history: str = "stock_price_history.sync"
    rabbitmq_routing_key_intraday: str = "stock_intraday.sync"

    # Scheduler settings for additional pipelines
    scheduler_company_cron_hour: int = 7
    scheduler_company_cron_minute: int = 0
    scheduler_market_data_cron_hour: int = 18
    scheduler_market_data_cron_minute: int = 0

    vnstock_index_group_names: list[str] = Field(
        default_factory=lambda: [
            "HOSE Indices",
            "Sector Indices",
            "Investment Indices",
            "VNX Indices",
        ],
        description="Nhóm chỉ số (theo vnstock INDEX_GROUPS); thêm 'HNX30' qua extra index symbols.",
    )
    vnstock_extra_index_symbols: list[str] = Field(
        default_factory=lambda: ["HNX30"],
        description="Mã chỉ số bổ sung (vnstock Listing.indices_by_group có thể không có trên mọi phiên bản).",
    )

    @model_validator(mode="after")
    def validate_history_window(self) -> Settings:
        if self.vnstock_history_start and self.vnstock_history_end:
            if self.vnstock_history_start > self.vnstock_history_end:
                raise ValueError("VNSTOCK_HISTORY_START must not be after VNSTOCK_HISTORY_END")
        return self
