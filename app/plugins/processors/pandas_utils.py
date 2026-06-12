from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from numbers import Real
from typing import Any

import pandas as pd

from app.core.exceptions import SourceError


def clean_str(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value).strip() or None


def clean_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def clean_int(value: Any) -> int | None:
    result = clean_float(value)
    return int(result) if result is not None else None


def clean_datetime(value: Any) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    try:
        if isinstance(value, Real):
            # VCI company endpoints can return Unix timestamps in milliseconds.
            numeric = float(value)
            unit = "ms" if abs(numeric) >= 100_000_000_000 else "s"
            timestamp: Any = pd.to_datetime(numeric, unit=unit, utc=True)
        elif isinstance(value, str) and "/" in value:
            timestamp = pd.Timestamp(datetime.strptime(value, "%d/%m/%Y"))
        else:
            timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            return None
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("Asia/Ho_Chi_Minh").tz_localize(None)
        return timestamp.to_pydatetime()
    except (ValueError, TypeError, OverflowError):
        # The KBS profile also uses DD/MM/YYYY.
        try:
            return datetime.strptime(str(value), "%d/%m/%Y")
        except ValueError:
            return None


def clean_date(value: Any) -> date | None:
    result = clean_datetime(value)
    return result.date() if result is not None else None


def normalize_columns(df: pd.DataFrame, aliases: dict[str, str], required: set[str]) -> pd.DataFrame:
    work = df.copy()
    for alias, canonical in aliases.items():
        if alias not in work:
            continue
        if canonical not in work:
            work[canonical] = work[alias]
        else:
            work[canonical] = work[canonical].fillna(work[alias])
    if missing := required - set(work.columns):
        raise SourceError(f"Provider schema missing columns: {sorted(missing)}")
    return work


def record_id(row: Any, df: pd.DataFrame, entity: str, *identity: Any) -> str:
    source = str(df.attrs.get("source", "vnstock")).lower()
    for field in ("data_source_id", "id", "article_id", "news_id", "event_id"):
        if existing := clean_str(row.get(field)):
            return existing if field == "data_source_id" else f"{source}:{entity}:{existing}"
    # Never key a snapshot row by mutable quantity/percentage/update_date.
    canonical = json.dumps(identity, ensure_ascii=False, default=str, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{source}:{entity}:{digest}"
