from datetime import datetime
from decimal import Decimal

import pytest

from app.analysis.rule_engine import RuleEngine
from app.domain.enums import DataFreshness, Risk, RuleStatus, Signal
from app.domain.schemas import IndicatorSnapshot


def snapshot(**overrides: object) -> IndicatorSnapshot:
    values: dict[str, object] = {
        "price": Decimal("110"),
        "ma20": 100.0,
        "ma50": 90.0,
        "rsi14": 60.0,
        "macd": 2.0,
        "macd_signal": 1.0,
        "macd_histogram": 1.0,
        "atr14": 2.0,
        "volume_ratio_projected": 2.0,
        "elapsed_trading_minutes": 60,
        "relative_return": 0.05,
        "as_of": datetime(2026, 9, 3, 3, 0),
        "is_final": False,
    }
    values.update(overrides)
    return IndicatorSnapshot.model_validate(values)


@pytest.mark.parametrize(
    ("score", "signal", "overrides"),
    [
        (7, Signal.BULLISH, {}),
        (5, Signal.BULLISH, {"volume_ratio_projected": 1.0, "relative_return": -0.01}),
        (
            4,
            Signal.NEUTRAL,
            {"macd_histogram": -1.0, "volume_ratio_projected": 1.0, "relative_return": -0.01},
        ),
        (
            3,
            Signal.NEUTRAL,
            {
                "rsi14": 40.0,
                "macd_histogram": -1.0,
                "volume_ratio_projected": 1.0,
                "relative_return": -0.01,
            },
        ),
        (
            2,
            Signal.BEARISH,
            {
                "ma20": 80.0,
                "rsi14": 40.0,
                "macd_histogram": -1.0,
                "volume_ratio_projected": 1.0,
                "relative_return": -0.01,
            },
        ),
        (
            0,
            Signal.BEARISH,
            {
                "price": Decimal("70"),
                "ma20": 100.0,
                "ma50": 110.0,
                "rsi14": 40.0,
                "macd_histogram": -1.0,
                "volume_ratio_projected": 1.0,
                "relative_return": -0.01,
            },
        ),
    ],
)
def test_signal_mapping_for_score(score: int, signal: Signal, overrides: dict[str, object]) -> None:
    values = snapshot(**overrides)
    rules = RuleEngine(rule_version="1.5.0").evaluate(values)

    assert rules.score == score
    assert rules.max_score == 7
    assert rules.signal == signal
    assert rules.confidence_raw == pytest.approx(score / 7)


def test_early_session_excludes_volume_from_score_and_maximum() -> None:
    values = snapshot(elapsed_trading_minutes=10, volume_ratio_projected=None)

    result = RuleEngine().evaluate(values)

    assert result.score == 6
    assert result.max_score == 6
    assert result.signal == Signal.BULLISH
    volume_reason = next(reason for reason in result.reasons if reason.rule_id == "R6")
    assert volume_reason.status == RuleStatus.NOT_EVALUATED


def test_missing_relative_strength_returns_insufficient_data() -> None:
    result = RuleEngine().evaluate(snapshot(relative_return=None))

    assert result.signal == Signal.INSUFFICIENT_DATA
    assert result.score == 0
    assert result.max_score == 0
    assert result.confidence_raw is None


def test_risk_is_independent_from_signal_and_score() -> None:
    result = RuleEngine().evaluate(
        snapshot(
            rsi14=80,
            atr14=5,
            price=Decimal("120"),
            ma20=100,
            volume_ratio_projected=3,
            relative_return=-0.01,
        ),
        data_freshness=DataFreshness.STALE_CACHE,
        previous_signal=Signal.NEUTRAL,
    )

    assert result.signal == Signal.BULLISH
    assert result.score == 6
    assert result.risk == Risk.HIGH
    assert result.risk_points >= 4
