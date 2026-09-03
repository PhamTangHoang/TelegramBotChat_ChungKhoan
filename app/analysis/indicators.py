from collections.abc import Sequence

Number = int | float
MaybeFloat = float | None


def _validate_period(period: int) -> None:
    if period < 1:
        raise ValueError("period must be positive")


def sma(values: Sequence[Number], period: int) -> list[MaybeFloat]:
    _validate_period(period)
    result: list[MaybeFloat] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        result[index] = sum(float(value) for value in window) / period
    return result


def ema(values: Sequence[Number], period: int) -> list[MaybeFloat]:
    _validate_period(period)
    result: list[MaybeFloat] = [None] * len(values)
    if len(values) < period:
        return result
    seed_index = period - 1
    result[seed_index] = sum(float(value) for value in values[:period]) / period
    multiplier = 2.0 / (period + 1)
    for index in range(period, len(values)):
        previous = result[index - 1]
        assert previous is not None
        result[index] = (float(values[index]) - previous) * multiplier + previous
    return result


def rsi_wilder(values: Sequence[Number], period: int = 14) -> list[MaybeFloat]:
    _validate_period(period)
    result: list[MaybeFloat] = [None] * len(values)
    if len(values) <= period:
        return result
    gains = [max(float(values[i]) - float(values[i - 1]), 0.0) for i in range(1, len(values))]
    losses = [max(float(values[i - 1]) - float(values[i]), 0.0) for i in range(1, len(values))]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    result[period] = _rsi_value(average_gain, average_loss)
    for index in range(period + 1, len(values)):
        gain = gains[index - 1]
        loss = losses[index - 1]
        average_gain = ((average_gain * (period - 1)) + gain) / period
        average_loss = ((average_loss * (period - 1)) + loss) / period
        result[index] = _rsi_value(average_gain, average_loss)
    return result


def _rsi_value(average_gain: float, average_loss: float) -> float:
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    if average_gain == 0:
        return 0.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def macd(
    values: Sequence[Number], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
) -> tuple[list[MaybeFloat], list[MaybeFloat], list[MaybeFloat]]:
    _validate_period(fast_period)
    _validate_period(slow_period)
    _validate_period(signal_period)
    if fast_period >= slow_period:
        raise ValueError("fast_period must be less than slow_period")
    fast = ema(values, fast_period)
    slow = ema(values, slow_period)
    macd_line: list[MaybeFloat] = [None] * len(values)
    compact: list[float] = []
    compact_indices: list[int] = []
    for index, (fast_value, slow_value) in enumerate(zip(fast, slow, strict=True)):
        if fast_value is not None and slow_value is not None:
            value = fast_value - slow_value
            macd_line[index] = value
            compact.append(value)
            compact_indices.append(index)
    compact_signal = ema(compact, signal_period)
    signal_line: list[MaybeFloat] = [None] * len(values)
    histogram: list[MaybeFloat] = [None] * len(values)
    for compact_index, original_index in enumerate(compact_indices):
        signal_value = compact_signal[compact_index]
        signal_line[original_index] = signal_value
        if signal_value is not None:
            assert macd_line[original_index] is not None
            histogram[original_index] = macd_line[original_index] - signal_value
    return macd_line, signal_line, histogram


def atr(
    highs: Sequence[Number], lows: Sequence[Number], closes: Sequence[Number], period: int = 14
) -> list[MaybeFloat]:
    _validate_period(period)
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows and closes must have the same length")
    result: list[MaybeFloat] = [None] * len(closes)
    if len(closes) < period:
        return result
    true_ranges: list[float] = []
    for index, (high, low) in enumerate(zip(highs, lows, strict=True)):
        high_value = float(high)
        low_value = float(low)
        if index == 0:
            true_ranges.append(high_value - low_value)
            continue
        previous_close = float(closes[index - 1])
        true_ranges.append(
            max(
                high_value - low_value,
                abs(high_value - previous_close),
                abs(low_value - previous_close),
            )
        )
    average = sum(true_ranges[:period]) / period
    result[period - 1] = average
    for index in range(period, len(true_ranges)):
        average = ((average * (period - 1)) + true_ranges[index]) / period
        result[index] = average
    return result


def project_volume_ratio(
    current_cumulative_volume: Number,
    *,
    elapsed_minutes: int,
    total_minutes: int,
    average_volume: Number,
    minimum_elapsed_minutes: int = 15,
) -> float | None:
    if elapsed_minutes < minimum_elapsed_minutes:
        return None
    if total_minutes <= 0 or average_volume <= 0 or current_cumulative_volume < 0:
        raise ValueError("volume projection inputs are invalid")
    projected_volume = float(current_cumulative_volume) / elapsed_minutes * total_minutes
    return projected_volume / float(average_volume)
