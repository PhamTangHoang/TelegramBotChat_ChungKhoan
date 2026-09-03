import pytest

from app.analysis.indicators import (
    atr,
    ema,
    macd,
    project_volume_ratio,
    rsi_wilder,
    sma,
)
from app.analysis.relative_strength import relative_return


def test_sma_uses_simple_rolling_window() -> None:
    assert sma([1, 2, 3, 4], 3) == [None, None, 2.0, 3.0]


def test_ema_is_seeded_by_first_period_mean() -> None:
    assert ema([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_wilder_rsi_is_100_for_continuous_gains() -> None:
    values = list(range(1, 17))

    result = rsi_wilder(values, 14)

    assert result[13] is None
    assert result[14] == pytest.approx(100.0)
    assert result[15] == pytest.approx(100.0)


def test_atr_wilder_is_constant_for_constant_range() -> None:
    highs = [11.0] * 15
    lows = [9.0] * 15
    closes = [10.0] * 15

    result = atr(highs, lows, closes, 14)

    assert result[13] == pytest.approx(2.0)
    assert result[14] == pytest.approx(2.0)


def test_macd_histogram_is_macd_minus_signal() -> None:
    values = [100 + i for i in range(50)]

    macd_line, signal_line, histogram = macd(values)

    assert macd_line[24] is None
    assert macd_line[33] is not None
    assert signal_line[33] is not None
    assert signal_line[41] is not None
    assert histogram[41] == pytest.approx(macd_line[41] - signal_line[41])


def test_relative_return_is_stock_minus_index_return() -> None:
    assert relative_return([100.0, 110.0], [1000.0, 1050.0], 1) == pytest.approx(0.05)


def test_projected_volume_ratio_uses_regular_elapsed_minutes() -> None:
    assert project_volume_ratio(
        100, elapsed_minutes=50, total_minutes=255, average_volume=510
    ) == pytest.approx(1.0)
    assert (
        project_volume_ratio(
            100,
            elapsed_minutes=10,
            total_minutes=255,
            average_volume=510,
            minimum_elapsed_minutes=15,
        )
        is None
    )
