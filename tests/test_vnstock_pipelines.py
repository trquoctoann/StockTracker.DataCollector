from unittest.mock import AsyncMock, Mock

import aio_pika
import httpx
import pandas as pd
import pytest

from app.core.exceptions import PipelineError, SourceError
from app.pipelines import vnstock_company_pipeline as company
from app.pipelines import vnstock_market_data_pipeline as market
from app.plugins.processors.company_processor import CompanyPandasProcessor
from app.plugins.sinks.rabbitmq_sink import RabbitMQSink
from app.schemas.market_data import StockIntradaySync
from tests import make_settings


async def test_market_failure_does_not_skip_intraday_and_is_reported(monkeypatch):
    settings = make_settings(rabbitmq_enabled=True)
    api = AsyncMock()
    api.fetch_stock_symbol_to_id.return_value = {"FPT": 1}
    monkeypatch.setattr(market, "StockTrackerApiClient", Mock(return_value=api))
    rabbit = AsyncMock()
    monkeypatch.setattr(market, "RabbitMQSink", Mock(return_value=rabbit))
    history = AsyncMock(side_effect=SourceError("history down"))
    intraday = AsyncMock(return_value=0)
    monkeypatch.setattr(market, "_sync_price_history", history)
    monkeypatch.setattr(market, "_sync_intraday", intraday)
    async with httpx.AsyncClient() as client:
        deps = market.VnstockMarketDataDeps(settings, AsyncMock(), AsyncMock(), client)
        with pytest.raises(PipelineError, match="1 operations failed"):
            await market.run_vnstock_market_data(deps)
    intraday.assert_awaited_once()
    rabbit.close.assert_awaited_once()
    api.fetch_stock_symbol_to_id.assert_awaited_once_with(stock_types={"STOCK", "ETF"})


async def test_company_failure_does_not_skip_remaining_operations(monkeypatch):
    settings = make_settings()
    api = AsyncMock()
    api.fetch_stock_symbol_to_id.return_value = {"FPT": 1}
    monkeypatch.setattr(company, "StockTrackerApiClient", Mock(return_value=api))
    operations = []
    for name in ("profile", "shareholders", "officers", "affiliations", "events", "news"):
        mock = AsyncMock(side_effect=SourceError("unavailable") if name == "profile" else None)
        monkeypatch.setattr(company, f"_sync_company_{name}", mock)
        operations.append(mock)
    async with httpx.AsyncClient() as client:
        deps = company.VnstockCompanyDeps(settings, AsyncMock(), AsyncMock(), client)
        with pytest.raises(PipelineError, match="1 operations failed"):
            await company.run_vnstock_company(deps)
    for operation in operations:
        operation.assert_awaited_once()
    api.fetch_stock_symbol_to_id.assert_awaited_once_with(stock_types={"STOCK"})


@pytest.mark.parametrize("names", [[None], ["Valid", None]])
async def test_invalid_company_snapshot_never_reaches_sink(names):
    source = AsyncMock()
    source.extract.return_value = pd.DataFrame({"name": names})
    sink = AsyncMock()
    with pytest.raises(SourceError, match="no valid rows"):
        await company._sync_company_shareholders(source, CompanyPandasProcessor(), sink, make_settings(), "FPT", 1)
    sink.send_put.assert_not_awaited()


async def test_rabbit_messages_are_persistent_and_unroutable_is_an_error(monkeypatch):
    connection = AsyncMock()
    channel = connection.channel.return_value
    exchange = channel.declare_exchange.return_value
    monkeypatch.setattr(aio_pika, "connect_robust", AsyncMock(return_value=connection))
    sink = RabbitMQSink(make_settings(rabbitmq_enabled=True), AsyncMock())
    await sink.publish_message("stock_intraday.sync", StockIntradaySync(stock_id=1))
    connection.channel.assert_awaited_once_with(publisher_confirms=True, on_return_raises=True)
    message = exchange.publish.call_args.args[0]
    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert exchange.publish.call_args.kwargs["routing_key"] == "stock_intraday.sync"
    await sink.close()
