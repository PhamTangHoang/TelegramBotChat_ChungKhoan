from datetime import datetime
from decimal import Decimal

from app.analysis.pp10 import PP10Evaluator
from app.domain.enums import EvaluationStatus
from app.domain.schemas import IndicatorSnapshot


def snapshot(**overrides: object) -> IndicatorSnapshot:
    values: dict[str, object] = {
        "price": Decimal("110"),
        "ma20": 105.0,
        "ma50": 100.0,
        "ma150": 95.0,
        "ma200": 90.0,
        "rsi14": 60.0,
        "macd": 3.0,
        "macd_signal": 2.0,
        "macd_histogram": 1.0,
        "atr14": 2.0,
        "volume_ratio_projected": 2.0,
        "volume_breakout": True,
        "volume_dry_up": False,
        "adx14": 30.0,
        "plus_di14": 25.0,
        "minus_di14": 15.0,
        "stoch_rsi14": 70.0,
        "obv": 1000.0,
        "obv_change_5": 100.0,
        "cmf20": 0.2,
        "elapsed_trading_minutes": 60,
        "relative_return": 0.05,
        "market_price": 1300.0,
        "market_ma20": 1280.0,
        "market_ma50": 1250.0,
        "as_of": datetime(2026, 9, 3, 3),
        "is_final": True,
    }
    values.update(overrides)
    return IndicatorSnapshot(**values)


def test_pp10_scores_available_deterministic_criteria_and_keeps_unknowns_explicit() -> None:
    result = PP10Evaluator().evaluate(snapshot())

    assert len(result.criteria) == 16
    assert result.score == 7
    assert result.max_score == 7
    assert result.evaluated_count == 7
    assert result.criteria[0].status == EvaluationStatus.PASS
    assert result.criteria[1].status == EvaluationStatus.DATA_UNAVAILABLE
    assert result.grade == "C"
    assert result.confidence == "Low"
    assert "Chưa xác định" in result.risk_plan.entry_zone
