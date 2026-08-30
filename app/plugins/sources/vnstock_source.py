from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import structlog

from app.archive.raw_archive import RawArchive
from app.core.config import Settings
from app.core.exceptions import SourceError
from app.core.rate_limiter import RateLimiterRegistry
from app.interfaces.base_source import BaseSource

_LOG = structlog.get_logger(__name__)
_COMPANY_METHODS = {
    "company_overview": "info",
    "company_shareholders": "shareholders",
    "company_officers": "officers",
    "company_subsidiaries": "subsidiaries",
    "company_events": "events",
    "company_news": "news",
}
_KBS_INDEX_ALIASES = {"VNMID": "VNMidCap", "VNSML": "VNSmallCap", "VNINDEX": "HOSE"}


@dataclass(frozen=True)
class IndexBasketRow:
    symbol: str
    name: str
    description: str | None
    group: str | None
    constituent_symbols: list[str]


class VnstockSource(BaseSource):
    """Adapter for the pinned vnstock Unified UI, isolated from pipeline contracts.

    Import and construct the SDK in a worker: vnstock import itself can do I/O.
    Unit tests and the health endpoint must not initialize the provider.
    """

    def __init__(
        self,
        settings: Settings,
        rate_limiter: RateLimiterRegistry,
        *,
        archive: RawArchive | None = None,
    ) -> None:
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._archive = archive

    @staticmethod
    def _prepare_sdk_environment() -> None:
        # The provider package starts a background agent-config writer during import.
        # A data service must never mutate the project or user-level AI configuration.
        os.environ["VNSTOCK_DISABLE_AGENT_SETUP"] = "1"
        os.environ["VNSTOCK_DISABLE_GLOBAL_AGENT"] = "1"

    @staticmethod
    def _reference() -> Any:
        VnstockSource._prepare_sdk_environment()
        from vnstock import Reference

        return Reference()

    @staticmethod
    def _market() -> Any:
        VnstockSource._prepare_sdk_environment()
        from vnstock import Market

        return Market()

    @staticmethod
    def _index_metadata() -> tuple[dict[str, list[str]], dict[str, Any]]:
        VnstockSource._prepare_sdk_environment()
        from vnstock import INDEX_GROUPS, INDICES_INFO

        return INDEX_GROUPS, INDICES_INFO

    @staticmethod
    async def _run_in_thread(func: Callable[[], Any]) -> Any:
        def invoke() -> Any:
            # Convert SystemExit inside the thread before asyncio sees it.
            # Cancellation and KeyboardInterrupt must still propagate.
            try:
                return func()
            except SystemExit as exc:
                raise SourceError(f"vnstock terminated the request: {exc}") from exc

        return await asyncio.to_thread(invoke)

    async def _call(self, operation: str, func: Callable[[], Any]) -> Any:
        await self._rate_limiter.acquire("vnstock")
        try:
            return await self._run_in_thread(func)
        except SourceError:
            raise
        except Exception as exc:
            raise SourceError(f"vnstock {operation} failed: {exc}") from exc

    @staticmethod
    def _frame(raw: Any, operation: str, *, allow_empty: bool = True) -> pd.DataFrame:
        if not isinstance(raw, pd.DataFrame):
            raise SourceError(f"vnstock {operation}: expected DataFrame, got {type(raw).__name__}")
        if not allow_empty and raw.empty:
            raise SourceError(f"vnstock {operation}: empty snapshot; refusing destructive sync")
        return raw

    async def extract(self, **kwargs: Any) -> Any:
        result = await self._extract(**kwargs)
        if self._archive is not None:
            operation = str(kwargs["operation"])
            await self._archive.capture(
                operation,
                result,
                source=self._source_for_operation(operation),
                parameters={key: value for key, value in kwargs.items() if key != "operation"},
            )
        return result

    async def _extract(self, **kwargs: Any) -> Any:
        operation = kwargs["operation"]
        if operation == "indices_catalog":
            return await self._build_indices_catalog()
        if operation == "symbols_by_group":
            return await self._symbols_by_group(str(kwargs["group"]))
        if operation == "industries_icb":
            raw = await self._call(operation, lambda: self._reference().industry.list(source="vci"))
            return self._frame(raw, operation, allow_empty=False)
        if operation == "symbols_by_exchange":
            raw = await self._call(
                operation,
                lambda: self._reference().equity.list_by_exchange(source=self._settings.vnstock_listing_source.lower()),
            )
            return self._frame(raw, operation, allow_empty=False)
        if operation in _COMPANY_METHODS:
            symbol = str(kwargs["symbol"]).strip().upper()
            raw = await self._call(
                operation,
                lambda: getattr(self._reference().company(symbol), _COMPANY_METHODS[operation])(
                    source=self._settings.vnstock_company_source.lower()
                ),
            )
            # Snapshot sync can delete records. Empty may mean a swallowed SDK
            # error; it is never authority to clear previously stored data.
            frame = self._frame(raw, operation, allow_empty=False)
            frame.attrs["source"] = self._settings.vnstock_company_source
            return frame
        if operation == "quote_history":
            return await self._quote_history(
                str(kwargs["symbol"]),
                str(kwargs.get("interval", self._settings.vnstock_price_history_interval)),
                kwargs.get("start"),
                kwargs.get("end"),
            )
        if operation == "quote_intraday":
            return await self._quote_intraday(str(kwargs["symbol"]))
        raise SourceError(f"Unknown vnstock operation: {operation}")

    def _source_for_operation(self, operation: str) -> str | None:
        if operation == "industries_icb":
            return "VCI"
        if operation == "symbols_by_exchange":
            return self._settings.vnstock_listing_source
        if operation in {"indices_catalog", "symbols_by_group"}:
            return self._settings.vnstock_indices_source
        if operation in _COMPANY_METHODS:
            return self._settings.vnstock_company_source
        if operation in {"quote_history", "quote_intraday"}:
            return self._settings.vnstock_quote_source
        return None

    async def _symbols_by_group(self, group: str) -> pd.Series:
        provider = self._settings.vnstock_indices_source.lower()
        provider_group = _KBS_INDEX_ALIASES.get(group, group)
        raw = await self._call(
            "symbols_by_group",
            lambda: self._reference().equity.list_by_group(group=provider_group, source=provider),
        )
        if isinstance(raw, pd.DataFrame) and "symbol" in raw:
            raw = raw["symbol"]
        if not isinstance(raw, pd.Series) or raw.empty or raw.isna().any():
            raise SourceError(f"vnstock index {group}: invalid or empty constituents")
        result = raw.astype(str).str.strip().str.upper()
        if result.eq("").any():
            raise SourceError(f"vnstock index {group}: blank constituent symbol")
        return result.drop_duplicates().reset_index(drop=True)

    async def _supported_index_groups(self) -> set[str]:
        raw = await self._call(
            "index_groups",
            lambda: self._reference().index.groups(source=self._settings.vnstock_indices_source.lower()),
        )
        frame = self._frame(raw, "index_groups", allow_empty=False)
        if "group_name" not in frame:
            raise SourceError("vnstock index_groups: missing group_name column")
        groups = frame["group_name"].dropna().astype(str).str.strip()
        supported = {group for group in groups if group}
        if not supported:
            raise SourceError("vnstock index_groups: no supported index groups")
        return supported

    async def _build_indices_catalog(self) -> list[IndexBasketRow]:
        groups, metadata = await self._run_in_thread(self._index_metadata)
        supported = await self._supported_index_groups()
        symbols: dict[str, str | None] = {}
        for group in self._settings.vnstock_index_group_names:
            if group not in groups:
                raise SourceError(f"Unknown vnstock index group: {group}")
            for symbol in groups[group]:
                symbols.setdefault(symbol, group)
        for symbol in self._settings.vnstock_extra_index_symbols:
            symbols.setdefault(symbol, None)
        rows = []
        unsupported = []
        for symbol, group in symbols.items():
            provider_group = _KBS_INDEX_ALIASES.get(symbol, symbol)
            if provider_group not in supported:
                unsupported.append(symbol)
                continue
            info = metadata.get(symbol, {})
            # Fail atomically instead of publishing an empty/partial basket.
            members = await self._symbols_by_group(symbol)
            rows.append(
                IndexBasketRow(
                    symbol=symbol,
                    name=str(info.get("name", symbol)),
                    description=info.get("description"),
                    group=info.get("group", group),
                    constituent_symbols=members.tolist(),
                )
            )
        if unsupported:
            _LOG.warning(
                "VNSTOCK_INDEX_GROUPS_UNSUPPORTED",
                source=self._settings.vnstock_indices_source,
                symbols=unsupported,
            )
        if not rows:
            raise SourceError("vnstock index catalog: none of the requested groups are supported")
        return rows

    async def _quote_history(
        self, symbol: str, interval: str, start: str | date | None, end: str | date | None
    ) -> pd.DataFrame:
        today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        end_date = date.fromisoformat(str(end or self._settings.vnstock_history_end or today))
        default_start = end_date - timedelta(days=self._settings.vnstock_history_lookback_days)
        start_date = date.fromisoformat(str(start or self._settings.vnstock_history_start or default_start))
        if start_date > end_date:
            raise SourceError("vnstock history start must not be after end")
        provider_interval = "1H" if interval == "1h" and self._settings.vnstock_quote_source == "VCI" else interval
        raw = await self._call(
            "quote_history",
            lambda: (
                self._market()
                .equity(symbol.strip().upper())
                .ohlcv(
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                    interval=provider_interval,
                    count=None,
                    source=self._settings.vnstock_quote_source.lower(),
                )
            ),
        )
        return self._frame(raw, "quote_history", allow_empty=False)

    async def _quote_intraday(self, symbol: str) -> pd.DataFrame:
        frames = []
        page_size = self._settings.vnstock_intraday_page_size
        for page in range(1, self._settings.vnstock_intraday_max_pages + 1):
            raw = await self._call(
                "quote_intraday",
                lambda page=page: (
                    self._market()
                    .equity(symbol.strip().upper())
                    .trades(page=page, page_size=page_size, source=self._settings.vnstock_quote_source.lower())
                ),
            )
            frame = self._frame(raw, "quote_intraday")
            if frame.empty:
                break
            frames.append(frame)
            if len(frame) < page_size:
                break
        else:
            _LOG.warning("VNSTOCK_INTRADAY_WINDOW_LIMIT", symbol=symbol, max_pages=len(frames))
        if not frames:
            return pd.DataFrame()
        result = pd.concat(frames, ignore_index=True)
        result.attrs = dict(frames[0].attrs)
        return result
