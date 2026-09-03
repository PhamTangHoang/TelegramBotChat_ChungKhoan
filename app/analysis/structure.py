from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from math import sqrt
from statistics import mean

from app.domain.schemas import MarketCandle


@dataclass(frozen=True)
class StructureSnapshot:
    wyckoff_phase: str | None = None
    pattern_name: str | None = None
    pattern_quality: float | None = None
    pivot_price: float | None = None
    support_price: float | None = None
    resistance_price: float | None = None
    vpvr_poc: float | None = None
    vpvr_hvn: float | None = None
    vpvr_breakout: bool | None = None
    cpr_weekly_top: float | None = None
    cpr_weekly_bottom: float | None = None
    cpr_monthly_top: float | None = None
    cpr_monthly_bottom: float | None = None
    cpr_weekly_bullish: bool | None = None
    cpr_monthly_bullish: bool | None = None


def analyze_structure(
    history: Sequence[MarketCandle], current: MarketCandle
) -> StructureSnapshot:
    candles = [*history, current]
    if len(candles) < 30:
        return StructureSnapshot()

    historical = candles[:-1]
    recent = historical[-20:]
    closes = [float(candle.close) for candle in candles]
    volumes = [float(candle.volume) for candle in candles]
    support = min(float(candle.low) for candle in recent)
    resistance = max(float(candle.high) for candle in recent)
    pattern, quality, pivot = _detect_pattern(candles)
    vpvr_poc, vpvr_hvn, vpvr_breakout = _calculate_vpvr(candles[-60:])
    weekly = _calculate_cpr(historical, current.trading_date, period="week")
    monthly = _calculate_cpr(historical, current.trading_date, period="month")
    return StructureSnapshot(
        wyckoff_phase=_detect_wyckoff(closes, volumes),
        pattern_name=pattern,
        pattern_quality=quality,
        pivot_price=pivot,
        support_price=support,
        resistance_price=resistance,
        vpvr_poc=vpvr_poc,
        vpvr_hvn=vpvr_hvn,
        vpvr_breakout=vpvr_breakout,
        cpr_weekly_top=weekly[0] if weekly else None,
        cpr_weekly_bottom=weekly[1] if weekly else None,
        cpr_weekly_bullish=weekly[2] if weekly else None,
        cpr_monthly_top=monthly[0] if monthly else None,
        cpr_monthly_bottom=monthly[1] if monthly else None,
        cpr_monthly_bullish=monthly[2] if monthly else None,
    )


def _detect_wyckoff(closes: Sequence[float], volumes: Sequence[float]) -> str | None:
    if len(closes) < 30:
        return None
    recent_price = mean(closes[-10:])
    prior_price = mean(closes[-30:-10])
    recent_volume = mean(volumes[-10:])
    prior_volume = mean(volumes[-30:-10])
    if recent_price >= prior_price * 1.05:
        return "Markup"
    if recent_price <= prior_price * 0.95:
        return "Markdown"
    if prior_volume > 0 and recent_volume <= prior_volume * 0.85:
        return "Accumulation"
    if prior_volume > 0 and recent_volume >= prior_volume * 1.15:
        return "Distribution"
    return "Neutral"


def _detect_pattern(
    candles: Sequence[MarketCandle],
) -> tuple[str | None, float | None, float | None]:
    if len(candles) < 30:
        return None, None, None
    historical = candles[:-1]
    current = candles[-1]
    prior = historical[-20:]
    prior_high = max(float(candle.high) for candle in prior)
    pivot = prior_high
    current_close = float(current.close)
    prior_volume = mean(float(candle.volume) for candle in prior)
    breakout = (
        current.is_final
        and current_close > prior_high * 1.005
        and float(current.volume) >= prior_volume * 1.5
    )
    if breakout:
        return "Breakout Base", 0.85, pivot

    ranges = [float(candle.high - candle.low) for candle in candles]
    early_range = mean(ranges[-30:-10])
    recent_range = mean(ranges[-10:])
    volumes = [float(candle.volume) for candle in candles]
    early_volume = mean(volumes[-30:-10])
    recent_volume = mean(volumes[-10:])
    if early_range > 0 and recent_range <= early_range * 0.75 and recent_volume <= early_volume:
        return "VCP", 0.80, pivot

    if float(candles[-11].close) > 0 and current_close / float(candles[-11].close) >= 1.08:
        return "Bull Flag", 0.75, pivot

    recent_closes = [float(candle.close) for candle in prior]
    average_close = mean(recent_closes)
    if average_close > 0 and (max(recent_closes) - min(recent_closes)) / average_close <= 0.15:
        return "Flat Base", 0.65, pivot

    return "No clear pattern", 0.0, pivot


def _calculate_vpvr(
    candles: Sequence[MarketCandle],
) -> tuple[float, float, bool] | tuple[None, None, None]:
    if len(candles) < 20:
        return None, None, None
    low = min(float(candle.low) for candle in candles)
    high = max(float(candle.high) for candle in candles)
    if high <= low:
        return low, low, False
    bin_count = min(24, max(8, int(sqrt(len(candles)) * 2)))
    width = (high - low) / bin_count
    volumes = [0.0] * bin_count
    for candle in candles:
        index = min(bin_count - 1, int((float(candle.close) - low) / width))
        volumes[index] += float(candle.volume)
    poc_index = max(range(bin_count), key=volumes.__getitem__)
    poc = low + (poc_index + 0.5) * width
    hvn = low + (poc_index + 1) * width
    return poc, hvn, float(candles[-1].close) > max(poc, hvn)


def _calculate_cpr(
    candles: Sequence[MarketCandle], current_date: date, *, period: str
) -> tuple[float, float, bool] | None:
    groups: defaultdict[object, list[MarketCandle]] = defaultdict(list)
    for candle in candles:
        key = _period_key(candle.trading_date, period)
        groups[key].append(candle)
    current_key = _period_key(current_date, period)
    completed = sorted((key, rows) for key, rows in groups.items() if key < current_key)
    if len(completed) < 2:
        return None
    previous_levels = _period_levels(completed[-2][1])
    current_levels = _period_levels(completed[-1][1])
    return current_levels[0], current_levels[1], current_levels[2] > previous_levels[2]


def _period_key(value: date, period: str) -> object:
    if period == "week":
        return value - timedelta(days=value.weekday())
    if period == "month":
        return value.year, value.month
    raise ValueError("unsupported CPR period")


def _period_levels(candles: Sequence[MarketCandle]) -> tuple[float, float, float]:
    high = max(float(candle.high) for candle in candles)
    low = min(float(candle.low) for candle in candles)
    close = float(max(candles, key=lambda candle: candle.trading_date).close)
    pivot = (high + low + close) / 3
    bottom = min((high + low) / 2, 2 * pivot - (high + low) / 2)
    top = max((high + low) / 2, 2 * pivot - (high + low) / 2)
    return top, bottom, pivot
