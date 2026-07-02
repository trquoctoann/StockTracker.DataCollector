"""Cross-repository contract check against the real API DTOs, without services.

Separate Python processes keep the two projects' `app` packages isolated. This
test skips when the sibling API checkout/environment is unavailable in CI.
"""

import json
import os
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from app.plugins.processors.company_processor import CompanyPandasProcessor
from app.plugins.processors.market_data_processor import MarketDataPandasProcessor
from app.schemas.industry import Industry
from app.schemas.market_index import MarketIndex
from app.schemas.stock import Stock


def test_collector_json_validates_against_actual_api_commands():
    api_dir = Path(os.environ.get("STOCKTRACKER_API_DIR", Path(__file__).resolve().parents[2] / "StockTracker.API"))
    python = api_dir / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        pytest.skip("Sibling StockTracker.API .venv required for cross-repository contract test")
    company, market = CompanyPandasProcessor(), MarketDataPandasProcessor()
    person = pd.DataFrame({"name": ["Example"], "shares_owned": [100], "ownership_percentage": [5.5]})
    news = pd.DataFrame({"title": ["Example"], "article_id": [123], "publish_time": ["2026-08-27T12:00:00"]})
    models = {
        "industry": Industry(code="8000", name="Finance", level=1),
        "stock": Stock(symbol="FPT", name="FPT", exchange="HSX", type="STOCK"),
        "index": MarketIndex(symbol="VN30", name="VN30", stock_ids=[1]),
        "profile": company.transform_profile(1, pd.DataFrame({"symbol": ["FPT"]})),
        "shareholder": company.transform_shareholders(1, person),
        "officer": company.transform_officers(1, person),
        "affiliation": company.transform_affiliations(1, person),
        "event": company.transform_events(1, news),
        "news": company.transform_news(1, news),
        "history": market.transform_price_history(
            1,
            pd.DataFrame(
                {
                    "time": ["2026-08-27"],
                    "open": [70],
                    "high": [73],
                    "low": [69],
                    "close": [72.5],
                    "volume": [100],
                }
            ),
        )[0],
        "intraday": market.transform_intraday(
            1,
            pd.DataFrame(
                {
                    "time": ["2026-08-27T14:30:00"],
                    "price": [72.5],
                    "volume": [100],
                    "match_type": ["atc"],
                    "id": [123],
                }
            ),
        )[0],
    }
    payload = {key: model.model_dump(mode="json", exclude_none=True) for key, model in models.items()}
    program = """
import importlib, json, sys
data = json.load(sys.stdin)
direct = {
    "industry": ("industry", "CreateIndustryCommand"),
    "stock": ("stock", "CreateStockCommand"),
    "index": ("market_index", "CreateMarketIndexCommand"),
    "profile": ("company_profile", "UpsertCompanyProfileCommand"),
}
for key, (module, name) in direct.items():
    cls = getattr(importlib.import_module(f"app.modules.{module}.application.command.{module}_command"), name)
    cls.model_validate(data[key])
for key in ("shareholder", "officer", "affiliation", "event", "news"):
    module = f"company_{key}"
    name = "CreateCompany" + key.title() + "Command"
    cls = getattr(importlib.import_module(f"app.modules.{module}.application.command.{module}_command"), name)
    for record in data[key]["items"]:
        cls.model_validate(record)
from app.modules.stock_price_history.application.command.stock_price_history_command import (
    UpsertStockPriceHistoryCommand,
)
from app.modules.stock_intraday.application.command.stock_intraday_command import UpsertStockIntradayCommand
for record in data["history"]["records"]:
    UpsertStockPriceHistoryCommand.model_validate({**record, "interval": data["history"]["interval"]})
for record in data["intraday"]["records"]:
    UpsertStockIntradayCommand.model_validate(record)
"""
    result = subprocess.run(
        [str(python), "-c", program],
        input=json.dumps(payload),
        text=True,
        cwd=api_dir,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
