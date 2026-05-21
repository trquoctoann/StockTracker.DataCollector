from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.interfaces.base_processor import BaseProcessor
from app.plugins.sources.vnstock_source import IndexBasketRow
from app.schemas.industry import Industry
from app.schemas.market_index import MarketIndex
from app.schemas.stock import Stock


def _clean_str(v: object) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v).strip()
    return s or None


def _normalize_exchange(raw: object) -> str:
    s = str(raw).strip().upper()
    if s in {"HOSE", "HNX", "UPCOM"}:
        return s
    return s


def _normalize_type(raw: object) -> str:
    s = str(raw).strip().upper()
    mapping = {
        "STOCK": "STOCK",
        "ETF": "ETF",
        "UNIT_TRUST": "FUND",
    }
    return mapping.get(s, s)


class ListingPandasProcessor(BaseProcessor):
    def process(self, raw: object, **kwargs: Any) -> object:
        raise NotImplementedError("Dùng transform_industries / transform_stocks / transform_market_indices")

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
        allowed_types = ["STOCK", "ETF", "UNIT_TRUST"]
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
            if icb_raw is None or (isinstance(icb_raw, float) and math.isnan(icb_raw)):
                icb = None
            else:
                icb = _clean_str(icb_raw)
            industry_ids: list[int] = []
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
