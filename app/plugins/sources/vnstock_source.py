from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd
from vnstock import INDEX_GROUPS, INDICES_INFO, Company, Listing, Quote

from app.core.config import Settings
from app.core.rate_limiter import RateLimiterRegistry
from app.interfaces.base_source import BaseSource

VnstockOperation = Literal[
    "industries_icb",
    "symbols_by_exchange",
    "symbols_by_group",
    "indices_catalog",
    "company_overview",
    "company_shareholders",
    "company_officers",
    "company_subsidiaries",
    "company_events",
    "company_news",
    "quote_history",
    "quote_intraday",
]


@dataclass(frozen=True)
class IndexBasketRow:
    symbol: str
    name: str
    description: str | None
    group: str | None
    constituent_symbols: list[str]


class VnstockSource(BaseSource):
    def __init__(self, settings: Settings, rate_limiter: RateLimiterRegistry) -> None:
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._source_key = "vnstock"

    def _listing_vci(self) -> Listing:
        return Listing(source="VCI")

    def _company_vci(self, symbol: str) -> Company:
        return Company(symbol=symbol, source="VCI")

    def _quote_vci(self, symbol: str) -> Quote:
        return Quote(symbol=symbol, source="VCI")

    async def extract(self, **kwargs: Any) -> Any:
        operation: VnstockOperation = kwargs["operation"]
        if operation == "industries_icb":
            return await self._industries_icb()
        if operation == "symbols_by_exchange":
            return await self._symbols_by_exchange()
        if operation == "symbols_by_group":
            group = str(kwargs["group"])
            return await self._symbols_by_group(group)
        if operation == "indices_catalog":
            return await self._build_indices_catalog()
        if operation == "company_overview":
            return await self._company_overview(str(kwargs["symbol"]))
        if operation == "company_shareholders":
            return await self._company_shareholders(str(kwargs["symbol"]))
        if operation == "company_officers":
            return await self._company_officers(str(kwargs["symbol"]))
        if operation == "company_subsidiaries":
            return await self._company_subsidiaries(str(kwargs["symbol"]))
        if operation == "company_events":
            return await self._company_events(str(kwargs["symbol"]))
        if operation == "company_news":
            return await self._company_news(str(kwargs["symbol"]))
        if operation == "quote_history":
            return await self._quote_history(str(kwargs["symbol"]), str(kwargs.get("interval", "1D")))
        if operation == "quote_intraday":
            return await self._quote_intraday(str(kwargs["symbol"]))
        raise ValueError(f"Unknown operation: {operation}")

    # -----------------------------------------------------------------------
    # Listing operations (existing)
    # -----------------------------------------------------------------------

    async def _industries_icb(self) -> pd.DataFrame:
        await self._rate_limiter.acquire(self._source_key)

        def _load() -> pd.DataFrame:
            return self._listing_vci().industries_icb()

        return await asyncio.to_thread(_load)

    async def _symbols_by_exchange(self) -> pd.DataFrame:
        await self._rate_limiter.acquire(self._source_key)

        def _load() -> pd.DataFrame:
            return self._listing_vci().symbols_by_exchange()

        return await asyncio.to_thread(_load)

    async def _symbols_by_group(self, group: str) -> pd.Series:
        await self._rate_limiter.acquire(self._source_key)

        def _load() -> pd.Series:
            return self._listing_vci().symbols_by_group(group=group)

        return await asyncio.to_thread(_load)

    def _collect_index_symbols(self) -> list[tuple[str, str | None]]:
        seen: set[str] = set()
        ordered: list[tuple[str, str | None]] = []
        for gname in self._settings.vnstock_index_group_names:
            for sym in INDEX_GROUPS.get(gname, []):
                if sym not in seen:
                    seen.add(sym)
                    ordered.append((sym, gname))
        for sym in self._settings.vnstock_extra_index_symbols:
            if sym not in seen:
                seen.add(sym)
                ordered.append((sym, None))
        return ordered

    async def _build_indices_catalog(self) -> list[IndexBasketRow]:
        rows: list[IndexBasketRow] = []
        for sym, gname in self._collect_index_symbols():
            info = INDICES_INFO.get(sym, {})
            name = str(info.get("name", sym))
            desc = info.get("description")
            description = str(desc) if desc is not None else None
            group = str(info.get("group", gname)) if info.get("group") or gname else None
            series = await self._symbols_by_group(sym)
            constituents = [str(x).strip().upper() for x in series.tolist()]
            rows.append(
                IndexBasketRow(
                    symbol=sym,
                    name=name,
                    description=description,
                    group=group,
                    constituent_symbols=constituents,
                )
            )
        return rows

    # -----------------------------------------------------------------------
    # Company operations (Phase 2)
    # -----------------------------------------------------------------------

    async def _company_overview(self, symbol: str) -> pd.DataFrame:
        await self._rate_limiter.acquire(self._source_key)

        def _load() -> pd.DataFrame:
            return self._company_vci(symbol).overview()

        return await asyncio.to_thread(_load)

    async def _company_shareholders(self, symbol: str) -> pd.DataFrame:
        await self._rate_limiter.acquire(self._source_key)

        def _load() -> pd.DataFrame:
            return self._company_vci(symbol).shareholders()

        return await asyncio.to_thread(_load)

    async def _company_officers(self, symbol: str) -> pd.DataFrame:
        await self._rate_limiter.acquire(self._source_key)

        def _load() -> pd.DataFrame:
            return self._company_vci(symbol).officers()

        return await asyncio.to_thread(_load)

    async def _company_subsidiaries(self, symbol: str) -> pd.DataFrame:
        await self._rate_limiter.acquire(self._source_key)

        def _load() -> pd.DataFrame:
            return self._company_vci(symbol).subsidiaries()

        return await asyncio.to_thread(_load)

    async def _company_events(self, symbol: str) -> pd.DataFrame:
        await self._rate_limiter.acquire(self._source_key)

        def _load() -> pd.DataFrame:
            return self._company_vci(symbol).events()

        return await asyncio.to_thread(_load)

    async def _company_news(self, symbol: str) -> pd.DataFrame:
        await self._rate_limiter.acquire(self._source_key)

        def _load() -> pd.DataFrame:
            return self._company_vci(symbol).news()

        return await asyncio.to_thread(_load)

    # -----------------------------------------------------------------------
    # Quote operations (Phase 3)
    # -----------------------------------------------------------------------

    async def _quote_history(self, symbol: str, interval: str = "1D") -> pd.DataFrame:
        await self._rate_limiter.acquire(self._source_key)

        def _load() -> pd.DataFrame:
            return self._quote_vci(symbol).history(interval=interval)

        return await asyncio.to_thread(_load)

    async def _quote_intraday(self, symbol: str) -> pd.DataFrame:
        await self._rate_limiter.acquire(self._source_key)

        def _load() -> pd.DataFrame:
            return self._quote_vci(symbol).intraday()

        return await asyncio.to_thread(_load)
