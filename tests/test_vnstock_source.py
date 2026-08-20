import asyncio
import builtins
import threading
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

from app.core.exceptions import SourceError
from app.plugins.sources.vnstock_source import VnstockSource
from tests import make_settings


@pytest.fixture
def adapter():
    settings = make_settings(vnstock_history_end="2026-08-26")
    limiter = AsyncMock()
    source = VnstockSource(settings, limiter)
    reference, market = Mock(), Mock()
    source._reference = Mock(return_value=reference)
    source._market = Mock(return_value=market)
    return source, reference, market, limiter


async def test_listing_uses_unified_ui_and_one_rate_token(adapter):
    source, reference, _, limiter = adapter
    reference.equity.list_by_exchange.return_value = pd.DataFrame({"symbol": ["FPT"]})
    result = await source.extract(operation="symbols_by_exchange")
    reference.equity.list_by_exchange.assert_called_once_with(source="kbs")
    limiter.acquire.assert_awaited_once_with("vnstock")
    assert result.symbol.tolist() == ["FPT"]


async def test_icb_always_uses_vci(adapter):
    source, reference, _, _ = adapter
    reference.industry.list.return_value = pd.DataFrame({"icb_code": ["0001"]})
    await source.extract(operation="industries_icb")
    reference.industry.list.assert_called_once_with(source="vci")


@pytest.mark.parametrize(
    "operation,method",
    [
        ("company_overview", "info"),
        ("company_shareholders", "shareholders"),
        ("company_officers", "officers"),
        ("company_subsidiaries", "subsidiaries"),
        ("company_events", "events"),
        ("company_news", "news"),
    ],
)
async def test_company_unified_method_dispatch(adapter, operation, method):
    source, reference, _, _ = adapter
    target = getattr(reference.company.return_value, method)
    target.return_value = pd.DataFrame({"name": ["Example"]})
    result = await source.extract(operation=operation, symbol=" fpt ")
    reference.company.assert_called_once_with("FPT")
    target.assert_called_once_with(source="kbs")
    assert result.attrs["source"] == "KBS"


async def test_history_has_explicit_dates_and_no_100_bar_ui_cap(adapter):
    source, _, market, _ = adapter
    market.equity.return_value.ohlcv.return_value = pd.DataFrame({"close": [72.5]})
    await source.extract(operation="quote_history", symbol="fpt", interval="1h")
    market.equity.assert_called_once_with("FPT")
    market.equity.return_value.ohlcv.assert_called_once_with(
        start="2026-07-27", end="2026-08-26", interval="1h", count=None, source="kbs"
    )


async def test_explicit_backfill_overrides_default_window(adapter):
    source, _, market, _ = adapter
    market.equity.return_value.ohlcv.return_value = pd.DataFrame({"close": [72.5]})
    await source.extract(operation="quote_history", symbol="FPT", start="2026-01-01", end="2026-02-01")
    assert market.equity.return_value.ohlcv.call_args.kwargs["start"] == "2026-01-01"


async def test_vci_hourly_provider_alias_does_not_change_api_interval(adapter):
    source, _, market, _ = adapter
    source._settings.vnstock_quote_source = "VCI"
    market.equity.return_value.ohlcv.return_value = pd.DataFrame({"close": [72.5]})
    await source.extract(operation="quote_history", symbol="FPT", interval="1h")
    assert market.equity.return_value.ohlcv.call_args.kwargs["interval"] == "1H"


async def test_invalid_date_range_does_not_call_provider(adapter):
    source, _, market, limiter = adapter
    with pytest.raises(SourceError, match="start must not"):
        await source.extract(operation="quote_history", symbol="FPT", start="2026-09-01", end="2026-08-01")
    market.equity.assert_not_called()
    limiter.acquire.assert_not_awaited()


async def test_intraday_pages_are_bounded_and_individually_limited(adapter):
    source, _, market, limiter = adapter
    source._settings.vnstock_intraday_page_size = 2
    source._settings.vnstock_intraday_max_pages = 3
    market.equity.return_value.trades.side_effect = [pd.DataFrame({"id": [1, 2]}), pd.DataFrame({"id": [3]})]
    result = await source.extract(operation="quote_intraday", symbol="FPT")
    assert result.id.tolist() == [1, 2, 3]
    assert [call.kwargs["page"] for call in market.equity.return_value.trades.call_args_list] == [1, 2]
    assert limiter.acquire.await_count == 2


@pytest.mark.parametrize("raw", [None, {"data": []}, pd.DataFrame()])
async def test_invalid_snapshot_never_turns_into_empty_sync(adapter, raw):
    source, reference, _, _ = adapter
    reference.company.return_value.shareholders.return_value = raw
    with pytest.raises(SourceError):
        await source.extract(operation="company_shareholders", symbol="FPT")


async def test_failed_index_catalog_is_not_a_partial_snapshot(adapter):
    source, reference, _, _ = adapter
    source._settings.vnstock_index_group_names = ["test"]
    source._settings.vnstock_extra_index_symbols = []
    source._index_metadata = Mock(return_value=({"test": ["VN30", "VN100"]}, {}))
    reference.index.groups.return_value = pd.DataFrame({"group_name": ["VN30", "VN100"]})
    reference.equity.list_by_group.side_effect = [pd.Series(["FPT"]), ConnectionError("down")]
    with pytest.raises(SourceError, match="symbols_by_group failed"):
        await source.extract(operation="indices_catalog")


async def test_kbs_group_alias_and_duplicate_members(adapter):
    source, reference, _, _ = adapter
    reference.equity.list_by_group.return_value = pd.Series([" fpt ", "FPT"])
    result = await source.extract(operation="symbols_by_group", group="VNMID")
    reference.equity.list_by_group.assert_called_once_with(group="VNMidCap", source="kbs")
    assert result.tolist() == ["FPT"]


async def test_index_catalog_skips_groups_not_advertised_by_provider(adapter):
    source, reference, _, _ = adapter
    source._settings.vnstock_index_group_names = ["test"]
    source._settings.vnstock_extra_index_symbols = []
    source._index_metadata = Mock(
        return_value=(
            {"test": ["VN30", "VNIT"]},
            {
                "VN30": {"name": "VN30", "description": "Top 30"},
                "VNIT": {"name": "VNIT", "description": "Technology"},
            },
        )
    )
    reference.index.groups.return_value = pd.DataFrame({"group_name": ["VN30"]})
    reference.equity.list_by_group.return_value = pd.Series(["FPT"])

    result = await source.extract(operation="indices_catalog")

    assert [basket.symbol for basket in result] == ["VN30"]
    reference.equity.list_by_group.assert_called_once_with(group="VN30", source="kbs")


async def test_index_catalog_fails_when_no_requested_group_is_supported(adapter):
    source, reference, _, _ = adapter
    source._settings.vnstock_index_group_names = ["test"]
    source._settings.vnstock_extra_index_symbols = []
    source._index_metadata = Mock(return_value=({"test": ["VNIT"]}, {}))
    reference.index.groups.return_value = pd.DataFrame({"group_name": ["VN30"]})

    with pytest.raises(SourceError, match="none of the requested groups"):
        await source.extract(operation="indices_catalog")

    reference.equity.list_by_group.assert_not_called()


async def test_system_exit_is_converted_inside_worker_thread():
    main_thread = threading.get_ident()

    def sdk_call():
        assert threading.get_ident() != main_thread
        raise SystemExit("quota")

    with pytest.raises(SourceError, match="terminated"):
        await VnstockSource._run_in_thread(sdk_call)


async def test_cancellation_propagates(adapter):
    source, reference, _, _ = adapter
    reference.equity.list_by_exchange.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await source.extract(operation="symbols_by_exchange")


def test_collector_startup_does_not_import_vnstock(monkeypatch):
    original = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "vnstock" or name.startswith("vnstock."):
            raise AssertionError("Startup must not import the provider SDK")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    import importlib

    from app import main

    importlib.reload(main)
