from datetime import date, datetime
from decimal import Decimal

from app.audit.snapshot import build_data_snapshot, build_input_hash, canonical_json
from app.domain.enums import Signal


def test_canonical_json_is_order_stable_and_preserves_decimal_text() -> None:
    left = {"b": Decimal("1.20"), "a": datetime(2026, 9, 3, 3, 0)}
    right = {"a": datetime(2026, 9, 3, 3, 0), "b": Decimal("1.20")}

    assert canonical_json(left) == canonical_json(right)
    assert '"1.20"' in canonical_json(left)


def test_input_hash_changes_when_quantitative_input_changes() -> None:
    base = {
        "data_snapshot": {"close": "100"},
        "indicator_snapshot": {"ma20": 99.0},
        "rule_result": {"signal": Signal.BULLISH.value},
        "rule_version": "1.5.0",
        "data_schema_version": "1.0.0",
    }

    assert build_input_hash(**base) != build_input_hash(
        **{**base, "data_snapshot": {"close": "101"}}
    )


def test_data_snapshot_serializes_pydantic_inputs() -> None:
    snapshot = build_data_snapshot(
        market_candles=[{"trading_date": date(2026, 9, 3), "close": Decimal("100")}],
        index_candles=[{"trading_date": date(2026, 9, 3), "close": Decimal("1300")}],
    )

    assert snapshot["market_candles"][0]["trading_date"] == "2026-09-03"
    assert snapshot["market_candles"][0]["close"] == "100"
    assert snapshot["news"] == []
