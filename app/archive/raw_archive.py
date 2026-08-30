from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from io import StringIO
from typing import Any
from uuid import UUID, uuid4

import boto3
import pandas as pd
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import BaseModel

from app.control.context import get_pipeline_run_context
from app.control.store import PipelineStore
from app.core.config import Settings
from app.core.exceptions import ArchiveError

_LOG = structlog.get_logger(__name__)
_SAFE_KEY = re.compile(r"[^A-Za-z0-9_.=-]+")


@dataclass(frozen=True)
class RawArchiveObject:
    bucket: str
    key: str
    checksum_sha256: str
    row_count: int | None
    size_bytes: int


@dataclass(frozen=True)
class RawReplayObject:
    operation: str
    source: str | None
    parameters: dict[str, Any]
    payload: Any
    checksum_sha256: str


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        return _json_safe(item())
    return str(value)


def _serialize_payload(payload: Any) -> tuple[str, Any, int | None]:
    if isinstance(payload, pd.DataFrame):
        serialized = payload.to_json(orient="table", date_format="iso", date_unit="ms", force_ascii=False, index=False)
        if serialized is None:
            raise ArchiveError("Unable to serialize DataFrame for raw archive")
        value = json.loads(serialized)
        return "pandas.table", value, len(payload)
    if isinstance(payload, pd.Series):
        return "pandas.series", _json_safe(payload.tolist()), len(payload)
    row_count = len(payload) if isinstance(payload, (list, tuple, set)) else None
    return "json", _json_safe(payload), row_count


class RawArchive:
    def __init__(
        self,
        settings: Settings,
        *,
        store: PipelineStore | None = None,
        client: Any | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._client = client or boto3.client(
            "s3",
            endpoint_url=settings.raw_archive_endpoint_url,
            aws_access_key_id=settings.raw_archive_access_key,
            aws_secret_access_key=settings.raw_archive_secret_key,
            region_name=settings.raw_archive_region,
            config=Config(s3={"addressing_style": "path"}),
        )

    async def ensure_bucket(self) -> None:
        def ensure() -> None:
            try:
                self._client.head_bucket(Bucket=self._settings.raw_archive_bucket)
                return
            except ClientError as exc:
                code = str(exc.response.get("Error", {}).get("Code", ""))
                if code not in {"404", "NoSuchBucket", "NotFound"}:
                    raise
            kwargs: dict[str, Any] = {"Bucket": self._settings.raw_archive_bucket}
            if self._settings.raw_archive_region != "us-east-1" and self._settings.raw_archive_endpoint_url is None:
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self._settings.raw_archive_region}
            self._client.create_bucket(**kwargs)

        try:
            await asyncio.to_thread(ensure)
        except Exception as exc:
            raise ArchiveError(f"Unable to initialize raw archive bucket: {exc}") from exc

    async def ping(self) -> None:
        """Verify that the configured archive bucket is reachable."""

        try:
            await asyncio.to_thread(
                self._client.head_bucket,
                Bucket=self._settings.raw_archive_bucket,
            )
        except Exception as exc:
            raise ArchiveError(f"Raw archive bucket is unavailable: {exc}") from exc

    async def capture(
        self,
        operation: str,
        payload: Any,
        *,
        source: str | None,
        parameters: Mapping[str, Any] | None = None,
    ) -> RawArchiveObject:
        context = get_pipeline_run_context()
        if context is None:
            raise ArchiveError("Raw archive capture requires an active pipeline run context")

        captured_at = datetime.now(UTC)
        safe_parameters = _json_safe(dict(parameters or {}))
        payload_format, value, row_count = _serialize_payload(payload)
        envelope = {
            "metadata": {
                "run_id": str(context.run_id),
                "pipeline": context.pipeline,
                "operation": operation,
                "source": source,
                "schema_version": self._settings.raw_archive_schema_version,
                "captured_at": captured_at.isoformat(),
                "parameters": safe_parameters,
                "payload_format": payload_format,
                "state": "empty" if row_count == 0 else "data",
            },
            "payload": value,
        }
        body = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        checksum = hashlib.sha256(body).hexdigest()
        compressed = gzip.compress(body, mtime=0)
        operation_key = _SAFE_KEY.sub("_", operation.strip())
        prefix = self._settings.raw_archive_prefix.strip("/")
        key = (
            f"{prefix}/pipeline={context.pipeline}/operation={operation_key}/"
            f"date={captured_at.date().isoformat()}/run_id={context.run_id}/"
            f"capture={captured_at.strftime('%H%M%S%f')}-{uuid4().hex[:8]}.json.gz"
        )

        def upload() -> None:
            self._client.put_object(
                Bucket=self._settings.raw_archive_bucket,
                Key=key,
                Body=compressed,
                ContentType="application/json",
                ContentEncoding="gzip",
                Metadata={
                    "run-id": str(context.run_id),
                    "pipeline": context.pipeline,
                    "operation": operation_key,
                    "sha256": checksum,
                    "schema-version": self._settings.raw_archive_schema_version,
                },
            )

        try:
            await asyncio.to_thread(upload)
            if self._store is not None:
                await self._store.record_raw_object(
                    run_id=context.run_id,
                    pipeline=context.pipeline,
                    operation=operation,
                    object_key=key,
                    checksum_sha256=checksum,
                    row_count=row_count,
                    source=source,
                    schema_version=self._settings.raw_archive_schema_version,
                    parameters=safe_parameters,
                )
        except Exception as exc:
            raise ArchiveError(f"Raw archive capture failed for {operation}: {exc}") from exc

        _LOG.info(
            "RAW_ARCHIVE_CAPTURED",
            run_id=str(context.run_id),
            pipeline=context.pipeline,
            operation=operation,
            object_key=key,
            row_count=row_count,
            checksum_sha256=checksum,
        )
        return RawArchiveObject(
            bucket=self._settings.raw_archive_bucket,
            key=key,
            checksum_sha256=checksum,
            row_count=row_count,
            size_bytes=len(compressed),
        )

    async def load(self, key: str, *, expected_checksum: str | None = None) -> RawReplayObject:
        """Load and verify an archived source response for deterministic replay."""

        def download() -> bytes:
            response = self._client.get_object(Bucket=self._settings.raw_archive_bucket, Key=key)
            body = response["Body"]
            return body.read() if hasattr(body, "read") else bytes(body)

        try:
            compressed = await asyncio.to_thread(download)
            body = gzip.decompress(compressed)
            checksum = hashlib.sha256(body).hexdigest()
            if expected_checksum is not None and checksum != expected_checksum:
                raise ArchiveError(f"Raw archive checksum mismatch for {key}")
            envelope = json.loads(body)
            metadata = envelope["metadata"]
            payload = envelope["payload"]
            if metadata["payload_format"] == "pandas.table":
                payload = pd.read_json(StringIO(json.dumps(payload)), orient="table")
            elif metadata["payload_format"] == "pandas.series":
                payload = pd.Series(payload)
            return RawReplayObject(
                operation=str(metadata["operation"]),
                source=metadata.get("source"),
                parameters=dict(metadata.get("parameters", {})),
                payload=payload,
                checksum_sha256=checksum,
            )
        except ArchiveError:
            raise
        except Exception as exc:
            raise ArchiveError(f"Unable to load raw archive object {key}: {exc}") from exc
