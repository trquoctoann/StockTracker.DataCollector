from __future__ import annotations

import gzip
import hashlib
import json
from io import BytesIO
from typing import Any, cast
from uuid import uuid4

import pandas as pd
import pytest

from app.archive.raw_archive import RawArchive
from app.control.context import PipelineRunContext, reset_pipeline_run_context, set_pipeline_run_context
from app.control.store import PipelineStore
from app.core.exceptions import ArchiveError
from tests import make_settings


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> None:
        self.objects.append(kwargs)

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        uploaded = next(item for item in self.objects if item["Bucket"] == Bucket and item["Key"] == Key)
        return {"Body": BytesIO(uploaded["Body"])}

    def head_bucket(self, *, Bucket: str) -> None:
        if Bucket != "stocktracker-raw":
            raise RuntimeError("bucket not found")


class FakeManifestStore:
    def __init__(self) -> None:
        self.objects: list[dict[str, Any]] = []

    async def record_raw_object(self, **kwargs: Any) -> None:
        self.objects.append(kwargs)


@pytest.mark.asyncio
async def test_raw_archive_captures_dataframe_and_manifest() -> None:
    client = FakeS3Client()
    store = FakeManifestStore()
    settings = make_settings(
        raw_archive_enabled=True,
        raw_archive_access_key="local",
        raw_archive_secret_key="local-secret",
        raw_archive_bucket="stocktracker-raw",
    )
    archive = RawArchive(settings, store=cast(PipelineStore, store), client=client)
    run_id = uuid4()
    token = set_pipeline_run_context(PipelineRunContext(run_id=run_id, pipeline="market"))
    try:
        result = await archive.capture(
            "quote_history",
            pd.DataFrame({"symbol": ["FPT"], "close": [123.5]}),
            source="KBS",
            parameters={"symbol": "FPT", "interval": "1D"},
        )
    finally:
        reset_pipeline_run_context(token)

    assert result.row_count == 1
    assert len(client.objects) == 1
    uploaded = client.objects[0]
    body = gzip.decompress(uploaded["Body"])
    envelope = json.loads(body)
    assert envelope["metadata"]["run_id"] == str(run_id)
    assert envelope["metadata"]["payload_format"] == "pandas.table"
    assert envelope["payload"]["data"] == [{"symbol": "FPT", "close": 123.5}]
    assert hashlib.sha256(body).hexdigest() == result.checksum_sha256
    assert store.objects[0]["object_key"] == result.key
    assert store.objects[0]["parameters"] == {"symbol": "FPT", "interval": "1D"}

    replay = await archive.load(result.key, expected_checksum=result.checksum_sha256)
    assert replay.operation == "quote_history"
    assert replay.source == "KBS"
    assert replay.parameters == {"symbol": "FPT", "interval": "1D"}
    pd.testing.assert_frame_equal(replay.payload, pd.DataFrame({"symbol": ["FPT"], "close": [123.5]}))


@pytest.mark.asyncio
async def test_raw_archive_requires_pipeline_context() -> None:
    archive = RawArchive(make_settings(), client=FakeS3Client())

    with pytest.raises(ArchiveError, match="active pipeline run context"):
        await archive.capture("quote_history", [], source="KBS")


@pytest.mark.asyncio
async def test_raw_archive_ping_checks_configured_bucket() -> None:
    archive = RawArchive(make_settings(raw_archive_bucket="stocktracker-raw"), client=FakeS3Client())

    await archive.ping()


@pytest.mark.asyncio
async def test_raw_archive_ping_wraps_storage_failure() -> None:
    archive = RawArchive(make_settings(raw_archive_bucket="missing"), client=FakeS3Client())

    with pytest.raises(ArchiveError, match="bucket is unavailable"):
        await archive.ping()
