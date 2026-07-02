"""Read-only smoke test of the installed SDK + collector transforms. No sinks.

Run: uv run python scripts/smoke_vnstock.py --symbol FPT
An empty provider snapshot fails conservatively; inspect it before any sync.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.core.rate_limiter import RateLimiterRegistry  # noqa: E402
from app.plugins.processors.company_processor import CompanyPandasProcessor  # noqa: E402
from app.plugins.processors.market_data_processor import MarketDataPandasProcessor  # noqa: E402
from app.plugins.processors.pandas_processor import ListingPandasProcessor  # noqa: E402
from app.plugins.sources.vnstock_source import VnstockSource  # noqa: E402


async def run(symbol: str, operations: list[str]) -> int:
    settings = Settings(_env_file=None, vnstock_intraday_page_size=5)
    source = VnstockSource(settings, RateLimiterRegistry(settings))
    company, market, listing = CompanyPandasProcessor(), MarketDataPandasProcessor(), ListingPandasProcessor()
    transforms = {
        "industries_icb": listing.transform_industries,
        "symbols_by_exchange": lambda df: listing.transform_stocks(df, {}),
        "company_overview": lambda df: company.transform_profile(1, df, symbol=symbol),
        "company_shareholders": lambda df: company.transform_shareholders(1, df),
        "company_officers": lambda df: company.transform_officers(1, df),
        "company_subsidiaries": lambda df: company.transform_affiliations(1, df),
        "company_events": lambda df: company.transform_events(1, df),
        "company_news": lambda df: company.transform_news(1, df),
        "quote_history": lambda df: market.transform_price_history(1, df),
        "quote_intraday": lambda df: market.transform_intraday(1, df),
    }
    failures = 0
    for operation in operations:
        try:
            if operation not in transforms:
                raise ValueError(f"Unsupported operation: {operation}")
            df = await source.extract(operation=operation, symbol=symbol)
            payload = transforms[operation](df)
            models = payload if isinstance(payload, list) else [payload]
            # Validate JSON serialization as well as transformation.
            for model in models:
                model.model_dump_json(exclude_none=True)
            result = {"operation": operation, "rows": len(df), "models": len(models), "status": "ok"}
        except Exception as exc:
            failures += 1
            result = {"operation": operation, "status": "failed", "error": str(exc)}
        print(json.dumps(result, ensure_ascii=True), flush=True)
    return int(failures > 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="FPT")
    parser.add_argument("--operations", nargs="+", default=["symbols_by_exchange", "company_overview", "quote_history"])
    args = parser.parse_args()
    print(json.dumps({"vnstock_version": version("vnstock"), "mode": "read-only"}), flush=True)
    raise SystemExit(asyncio.run(run(args.symbol, args.operations)))
