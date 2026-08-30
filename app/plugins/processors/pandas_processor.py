from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.exceptions import SourceError
from app.interfaces.base_processor import BaseProcessor
from app.plugins.processors.pandas_utils import clean_str as _clean_str
from app.plugins.sources.vnstock_source import IndexBasketRow
from app.schemas.industry import Industry
from app.schemas.market_index import MarketIndex
from app.schemas.stock import Stock


def _normalize_exchange(raw: object) -> str:
    s = str(raw).strip().upper()
    # KBS uses "HOSE" for the HSX exchange; map to canonical enum value "HSX"
    if s == "HOSE":
        return "HSX"
    if s in {"HSX", "HNX", "UPCOM", "DELISTED", "BOND"}:
        return s
    return s


def _normalize_type(raw: object) -> str:
    s = str(raw).strip().upper()
    mapping = {
        "STOCK": "STOCK",
        "ETF": "ETF",
        "UNIT_TRUST": "FUND",
        "FUND": "FUND",
    }
    return mapping.get(s, s)


class ListingPandasProcessor(BaseProcessor):
    def process(self, raw: object, **kwargs: Any) -> object:
        raise NotImplementedError("Use transform_industries, transform_stocks, or transform_market_indices")

    def transform_industries(self, df: pd.DataFrame) -> list[Industry]:
        if df.empty:
            return []
        work = df.dropna(how="all").copy()
        work = work.dropna(subset=["icb_code", "icb_name", "level"], how="any")
        items: list[Industry] = []
        for _, row in work.iterrows():
            code = _clean_str(row.get("icb_code"))
            name = _clean_str(row.get("icb_name"))
            if code is None or name is None:
                continue
            level_raw = row.get("level")
            try:
                level = int(float(level_raw))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            items.append(Industry(code=code[:20], name=name[:255], level=level))
        return items

    def transform_stocks(self, df: pd.DataFrame, industry_code_to_id: dict[str, int]) -> list[Stock]:
        if df.empty:
            return []
        required = {"symbol", "organ_name", "exchange", "type"}
        if missing := required - set(df.columns):
            raise SourceError(f"Listing schema missing columns: {sorted(missing)}")
        # Normalize type to uppercase to handle both VCI and KBS source conventions
        df = df.copy()
        df["type"] = df["type"].str.upper()
        allowed_types = ["STOCK", "ETF", "UNIT_TRUST", "FUND"]
        work = df.loc[df["type"].isin(allowed_types)].dropna(subset=["symbol", "organ_name"], how="any").copy()
        items: list[Stock] = []
        for _, row in work.iterrows():
            sym = _clean_str(row.get("symbol"))
            name = _clean_str(row.get("organ_name"))
            if sym is None or name is None:
                continue
            short = _clean_str(row.get("organ_short_name"))
            exchange = _normalize_exchange(row.get("exchange"))
            typ = _normalize_type(row.get("type"))
            icb_raw = row.get("icb_code2")
            icb: str | None
            if icb_raw is None or pd.isna(icb_raw):
                icb = None
            else:
                icb = str(int(icb_raw)) if isinstance(icb_raw, float) and icb_raw.is_integer() else _clean_str(icb_raw)
            industry_ids: list[int] | None = None
            if icb is not None and icb in industry_code_to_id:
                industry_ids = [industry_code_to_id[icb]]
            items.append(
                Stock(
                    symbol=sym[:20].upper(),
                    name=name,
                    short_name=short,
                    exchange=exchange,
                    type=typ,
                    industry_ids=industry_ids,
                )
            )
        return items

    def transform_market_indices(
        self,
        baskets: list[IndexBasketRow],
        stock_symbol_to_id: dict[str, int],
    ) -> list[MarketIndex]:
        out: list[MarketIndex] = []
        for b in baskets:
            missing = set(b.constituent_symbols) - stock_symbol_to_id.keys()
            if missing or not b.constituent_symbols:
                raise SourceError(f"Index {b.symbol}: incomplete stock mapping: {sorted(missing)}")
            stock_ids: list[int] = []
            for s in b.constituent_symbols:
                sid = stock_symbol_to_id.get(s)
                if sid is not None:
                    stock_ids.append(sid)
            out.append(
                MarketIndex(
                    symbol=b.symbol,
                    name=b.name,
                    description=b.description,
                    group=b.group,
                    stock_ids=stock_ids,
                )
            )
        return out
