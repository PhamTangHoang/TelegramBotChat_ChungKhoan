from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel


def canonicalize(value: Any) -> Any:
    """Convert supported values to a deterministic, JSON-compatible structure."""
    if isinstance(value, BaseModel):
        return canonicalize(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return canonicalize(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return {str(key): canonicalize(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [canonicalize(item) for item in value]
    raise TypeError(f"unsupported value for canonical JSON: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_input_hash(
    *,
    data_snapshot: Any,
    indicator_snapshot: Any,
    rule_result: Any,
    rule_version: str,
    data_schema_version: str,
) -> str:
    """Hash quantitative inputs and the rule/schema versions used to evaluate them."""
    return sha256_hex(
        {
            "data_snapshot": data_snapshot,
            "indicator_snapshot": indicator_snapshot,
            "rule_result": rule_result,
            "rule_version": rule_version,
            "data_schema_version": data_schema_version,
        }
    )


def build_data_snapshot(
    *,
    market_candles: Sequence[Any],
    index_candles: Sequence[Any],
) -> dict[str, list[Any]]:
    """Serialize the exact market and index observations consumed by an analysis."""
    return {
        "market_candles": [canonicalize(candle) for candle in market_candles],
        "index_candles": [canonicalize(candle) for candle in index_candles],
    }
