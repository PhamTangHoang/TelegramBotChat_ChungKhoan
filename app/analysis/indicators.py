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


def adx(
    highs: Sequence[Number],
    lows: Sequence[Number],
    closes: Sequence[Number],
    period: int = 14,
) -> tuple[list[MaybeFloat], list[MaybeFloat], list[MaybeFloat]]:
    """Return ADX, +DI and -DI using Wilder smoothing."""
    _validate_period(period)
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows and closes must have the same length")
    adx_values: list[MaybeFloat] = [None] * len(closes)
    plus_di: list[MaybeFloat] = [None] * len(closes)
    minus_di: list[MaybeFloat] = [None] * len(closes)
    if len(closes) < period:
        return adx_values, plus_di, minus_di

    true_ranges: list[float] = []
    positive_dm: list[float] = []
    negative_dm: list[float] = []
    for index in range(len(closes)):
        high = float(highs[index])
        low = float(lows[index])
        if index == 0:
            true_ranges.append(high - low)
            positive_dm.append(0.0)
            negative_dm.append(0.0)
            continue
        previous_high = float(highs[index - 1])
        previous_low = float(lows[index - 1])
        previous_close = float(closes[index - 1])
        up_move = high - previous_high
        down_move = previous_low - low
        positive_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        negative_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        true_ranges.append(
            max(high - low, abs(high - previous_close), abs(low - previous_close))
        )

    average_tr = sum(true_ranges[:period]) / period
    average_positive = sum(positive_dm[:period]) / period
    average_negative = sum(negative_dm[:period]) / period
    dx_values: list[float] = []
    for index in range(period - 1, len(closes)):
        if index >= period:
            average_tr = ((average_tr * (period - 1)) + true_ranges[index]) / period
            average_positive = (
                (average_positive * (period - 1)) + positive_dm[index]
            ) / period
            average_negative = (
                (average_negative * (period - 1)) + negative_dm[index]
            ) / period
        if average_tr == 0:
            positive = negative = 0.0
        else:
            positive = 100.0 * average_positive / average_tr
            negative = 100.0 * average_negative / average_tr
        plus_di[index] = positive
        minus_di[index] = negative
        denominator = positive + negative
        dx = 0.0 if denominator == 0 else 100.0 * abs(positive - negative) / denominator
        dx_values.append(dx)
        if len(dx_values) == period:
            adx_values[index] = sum(dx_values) / period
        elif len(dx_values) > period:
            previous = adx_values[index - 1]
            assert previous is not None
            adx_values[index] = ((previous * (period - 1)) + dx) / period
    return adx_values, plus_di, minus_di


def stoch_rsi(values: Sequence[Number], period: int = 14) -> list[MaybeFloat]:
    _validate_period(period)
    rsi_values = rsi_wilder(values, period)
    result: list[MaybeFloat] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = rsi_values[index - period + 1 : index + 1]
        if any(value is None for value in window):
            continue
        numeric = [float(value) for value in window if value is not None]
        minimum = min(numeric)
        maximum = max(numeric)
        result[index] = (
            50.0
            if maximum == minimum
            else (numeric[-1] - minimum) / (maximum - minimum) * 100
        )
    return result


def obv(closes: Sequence[Number], volumes: Sequence[Number]) -> list[float]:
    if len(closes) != len(volumes):
        raise ValueError("closes and volumes must have the same length")
    if not closes:
        return []
    result = [float(volumes[0])]
    for index in range(1, len(closes)):
        previous = result[-1]
        volume = float(volumes[index])
        if float(closes[index]) > float(closes[index - 1]):
            result.append(previous + volume)
        elif float(closes[index]) < float(closes[index - 1]):
            result.append(previous - volume)
        else:
            result.append(previous)
    return result


def cmf(
    highs: Sequence[Number],
    lows: Sequence[Number],
    closes: Sequence[Number],
    volumes: Sequence[Number],
    period: int = 20,
) -> list[MaybeFloat]:
    _validate_period(period)
    if not (len(highs) == len(lows) == len(closes) == len(volumes)):
        raise ValueError("OHLCV inputs must have the same length")
    result: list[MaybeFloat] = [None] * len(closes)
    money_flow: list[float] = []
    for high, low, close, volume in zip(highs, lows, closes, volumes, strict=True):
        high_value = float(high)
        low_value = float(low)
        close_value = float(close)
        if high_value == low_value:
            multiplier = 0.0
        else:
            multiplier = (
                ((close_value - low_value) - (high_value - close_value))
                / (high_value - low_value)
            )
        money_flow.append(multiplier * float(volume))
    for index in range(period - 1, len(closes)):
        volume_window = sum(float(value) for value in volumes[index - period + 1 : index + 1])
        result[index] = (
            sum(money_flow[index - period + 1 : index + 1]) / volume_window
            if volume_window
            else 0.0
        )
    return result
