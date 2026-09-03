from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import DataFreshness, Risk, RuleStatus, Signal
from app.domain.schemas import IndicatorSnapshot, RuleReason, RuleResult


@dataclass(frozen=True)
class _RuleEvaluation:
    rule_id: str
    label: str
    passed: bool
    value: float | Decimal
    threshold: str


class RuleEngine:
    """Deterministic seven-rule scoring engine from plan v1.5."""

    def __init__(
        self,
        *,
        rule_version: str = "1.5.0",
        volume_threshold: float = 1.5,
        volume_min_elapsed_minutes: int = 15,
    ) -> None:
        self.rule_version = rule_version
        self.volume_threshold = volume_threshold
        self.volume_min_elapsed_minutes = volume_min_elapsed_minutes

    def evaluate(
        self,
        indicators: IndicatorSnapshot,
        *,
        data_freshness: DataFreshness = DataFreshness.FRESH,
        previous_signal: Signal | None = None,
    ) -> RuleResult:
        volume_ready = indicators.elapsed_trading_minutes >= self.volume_min_elapsed_minutes
        if not self._has_mandatory_inputs(indicators, volume_ready=volume_ready):
            return RuleResult(
                score=0,
                max_score=0,
                signal=Signal.INSUFFICIENT_DATA,
                confidence_raw=None,
                reasons=[],
                risk=Risk.LOW,
                risk_points=0,
                risk_reasons=["mandatory_indicator_missing"],
                rule_version=self.rule_version,
            )

        evaluations = [
            _RuleEvaluation(
                "R1",
                "Price above MA20",
                indicators.price > Decimal(str(indicators.ma20)),
                indicators.price,
                f"> MA20 ({indicators.ma20:g})",
            ),
            _RuleEvaluation(
                "R2",
                "Price above MA50",
                indicators.price > Decimal(str(indicators.ma50)),
                indicators.price,
                f"> MA50 ({indicators.ma50:g})",
            ),
            _RuleEvaluation(
                "R3",
                "MA20 above MA50",
                indicators.ma20 > indicators.ma50,
                indicators.ma20,
                f"> MA50 ({indicators.ma50:g})",
            ),
            _RuleEvaluation(
                "R4",
                "RSI14 in the neutral-to-strong range",
                50 <= indicators.rsi14 <= 70,
                indicators.rsi14,
                "50-70 inclusive",
            ),
            _RuleEvaluation(
                "R5",
                "MACD histogram positive",
                indicators.macd_histogram > 0,
                indicators.macd_histogram,
                "> 0",
            ),
        ]

        if volume_ready:
            evaluations.append(
                _RuleEvaluation(
                    "R6",
                    "Projected volume ratio above threshold",
                    indicators.volume_ratio_projected > self.volume_threshold,
                    indicators.volume_ratio_projected,  # validated by _has_mandatory_inputs
                    f"> {self.volume_threshold:g}",
                )
            )
        else:
            evaluations.append(
                _RuleEvaluation(
                    "R6",
                    "Projected volume ratio above threshold",
                    False,
                    indicators.volume_ratio_projected or 0.0,
                    f"> {self.volume_threshold:g}",
                )
            )

        evaluations.append(
            _RuleEvaluation(
                "R7",
                "Relative strength versus VNINDEX positive",
                indicators.relative_return > 0,
                indicators.relative_return,
                "> 0",
            )
        )

        reasons = [
            RuleReason(
                rule_id=evaluation.rule_id,
                label=evaluation.label,
                status=(
                    RuleStatus.PASS
                    if evaluation.passed
                    else RuleStatus.FAIL
                    if evaluation.rule_id != "R6" or volume_ready
                    else RuleStatus.NOT_EVALUATED
                ),
                value=float(evaluation.value),
                threshold=evaluation.threshold,
            )
            for evaluation in evaluations
        ]
        scored = [reason for reason in reasons if reason.status != RuleStatus.NOT_EVALUATED]
        score = sum(reason.status == RuleStatus.PASS for reason in scored)
        max_score = len(scored)
        signal = self._map_signal(score)
        confidence_raw = score / max_score if max_score else None
        risk_points, risk_reasons = self._risk(
            indicators,
            signal=signal,
            data_freshness=data_freshness,
            previous_signal=previous_signal,
        )

        return RuleResult(
            score=score,
            max_score=max_score,
            signal=signal,
            confidence_raw=confidence_raw,
            reasons=reasons,
            risk=self._risk_level(risk_points),
            risk_points=risk_points,
            risk_reasons=risk_reasons,
            rule_version=self.rule_version,
        )

    @staticmethod
    def _has_mandatory_inputs(indicators: IndicatorSnapshot, *, volume_ready: bool) -> bool:
        required = (
            indicators.ma20,
            indicators.ma50,
            indicators.rsi14,
            indicators.macd_histogram,
            indicators.atr14,
            indicators.relative_return,
        )
        if not all(value is not None for value in required) or indicators.ma20 <= 0:
            return False
        return not volume_ready or indicators.volume_ratio_projected is not None

    @staticmethod
    def _map_signal(score: int) -> Signal:
        if score >= 5:
            return Signal.BULLISH
        if score >= 3:
            return Signal.NEUTRAL
        return Signal.BEARISH

    def _risk(
        self,
        indicators: IndicatorSnapshot,
        *,
        signal: Signal,
        data_freshness: DataFreshness,
        previous_signal: Signal | None,
    ) -> tuple[int, list[str]]:
        points = 0
        reasons: list[str] = []

        if indicators.rsi14 < 30:
            points += 1
            reasons.append("rsi_oversold")
        elif indicators.rsi14 >= 75:
            points += 2
            reasons.append("rsi_extreme_overbought")
        elif indicators.rsi14 > 70:
            points += 1
            reasons.append("rsi_overbought")

        atr_pct = indicators.atr14 / float(indicators.price)
        if atr_pct > 0.04:
            points += 2
            reasons.append("atr_over_4_percent")
        elif atr_pct > 0.02:
            points += 1
            reasons.append("atr_over_2_percent")

        distance_to_ma20 = abs(float(indicators.price) - indicators.ma20) / indicators.ma20
        if distance_to_ma20 > 0.10:
            points += 2
            reasons.append("price_ma20_distance_over_10_percent")
        elif distance_to_ma20 > 0.05:
            points += 1
            reasons.append("price_ma20_distance_over_5_percent")

        conflict = any(
            [
                (
                    indicators.price > Decimal(str(indicators.ma20))
                    and indicators.macd_histogram < 0
                ),
                (
                    indicators.price < Decimal(str(indicators.ma20))
                    and indicators.macd_histogram > 0
                ),
                indicators.ma20 > indicators.ma50 and indicators.relative_return <= 0,
                indicators.ma20 < indicators.ma50 and indicators.relative_return > 0,
            ]
        )
        if conflict:
            points += 1
            reasons.append("trend_momentum_conflict")

        if data_freshness == DataFreshness.STALE_CACHE:
            points += 2
            reasons.append("stale_cache")

        if (
            previous_signal is not None
            and previous_signal != signal
            and signal != Signal.INSUFFICIENT_DATA
        ):
            points += 1
            reasons.append("signal_transition")

        if indicators.volume_ratio_projected is not None and indicators.volume_ratio_projected >= 3:
            points += 1
            reasons.append("volume_ratio_at_least_3")

        return points, reasons

    @staticmethod
    def _risk_level(points: int) -> Risk:
        if points >= 4:
            return Risk.HIGH
        if points >= 2:
            return Risk.MEDIUM
        return Risk.LOW
