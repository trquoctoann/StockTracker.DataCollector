from __future__ import annotations

from pydantic import Field
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
    rabbitmq_exchange: str = "stocktracker.datacollector"
    rabbitmq_exchange_type: str = "topic"
    rabbitmq_enabled: bool = False

    rate_limit_vnstock_per_second: float = 2.0
    rate_limit_vnstock_burst: int = 5
    rate_limit_http_per_second: float = 10.0
    rate_limit_http_burst: int = 20
    rate_limit_rabbitmq_per_second: float = 50.0
    rate_limit_rabbitmq_burst: int = 100

    scheduler_enabled: bool = False
    scheduler_cron_hour: int = 6
    scheduler_cron_minute: int = 0

    # Company sync endpoints (Phase 2)
    api_path_company_profile_sync: str = "/api/v1/stocks/{stock_id}/profile/sync"
    api_path_company_shareholders_sync: str = "/api/v1/stocks/{stock_id}/shareholders/sync"
    api_path_company_officers_sync: str = "/api/v1/stocks/{stock_id}/officers/sync"
    api_path_company_affiliations_sync: str = "/api/v1/stocks/{stock_id}/affiliations/sync"
    api_path_company_events_sync: str = "/api/v1/stocks/{stock_id}/events/sync"
    api_path_company_news_sync: str = "/api/v1/stocks/{stock_id}/news/sync"

    # Market data settings (Phase 3)
    market_data_chunk_size: int = 500
    vnstock_price_history_interval: str = "1D"
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
