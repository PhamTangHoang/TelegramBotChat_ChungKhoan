from __future__ import annotations

from typing import Any

from app.domain.enums import EvaluationStatus
from app.domain.schemas import (
    IndicatorSnapshot,
    PP10Criterion,
    PP10Result,
    PP10RiskPlan,
)

_CRITERIA = (
    ("1", "Xu hướng MA tổng thể"),
    ("2", "Pha Wyckoff"),
    ("3", "Mẫu hình Dan Zanger"),
    ("4", "Chất lượng mẫu hình theo Peter Brandt"),
    ("5", "RS Rating và RS Line"),
    ("6", "Khối lượng và breakout"),
    ("7", "Volume Profile / VPVR"),
    ("8", "CPR tuần và tháng"),
    ("9", "OBV và CMF"),
    ("10", "MACD"),
    ("11", "RSI và ADX"),
    ("12", "Stochastic RSI"),
    ("13", "Cơ bản doanh nghiệp"),
    ("14", "Định giá"),
    ("15", "Xu hướng thị trường chung"),
    ("16", "Quản trị vị thế"),
)


class PP10Evaluator:
    """Deterministic PP10 score using only validated data available to the bot."""

    def __init__(self, *, version: str = "1.0.0") -> None:
        self.version = version

    def evaluate(self, indicators: IndicatorSnapshot) -> PP10Result:
        criteria = [
            self._unsupported(criterion_id, name) for criterion_id, name in _CRITERIA
        ]
        criteria[0] = self._trend(indicators)
        criteria[5] = self._volume(indicators)
        criteria[8] = self._money_flow(indicators)
        criteria[9] = self._macd(indicators)
        criteria[10] = self._rsi_adx(indicators)
        criteria[11] = self._stoch_rsi(indicators)
        criteria[14] = self._market(indicators)

        evaluated = [
            item
            for item in criteria
            if item.status in {EvaluationStatus.PASS, EvaluationStatus.FAIL}
        ]
        score = sum(item.score for item in evaluated)
        evaluated_count = len(evaluated)
        ratio = score / evaluated_count if evaluated_count else 0.0
        confidence = (
            "High" if evaluated_count >= 14 else "Medium" if evaluated_count >= 10 else "Low"
        )
        return PP10Result(
            score=score,
            max_score=evaluated_count,
            evaluated_count=evaluated_count,
            grade=self._grade(ratio, evaluated_count),
            confidence=confidence,
            version=self.version,
            criteria=criteria,
            risk_plan=PP10RiskPlan(
                entry_zone="Chưa xác định — chưa có cấu trúc breakout được đánh giá",
                add_zone="Chưa xác định",
                stop_loss="Chưa xác định — cần swing low hoặc hỗ trợ hợp lệ",
                target="Chưa xác định — cần kháng cự/cấu trúc giá",
                risk_reward="Chưa xác định",
            ),
        )

    @staticmethod
    def _unsupported(criterion_id: str, name: str) -> PP10Criterion:
        return PP10Criterion(
            criterion_id=criterion_id,
            name=name,
            status=EvaluationStatus.DATA_UNAVAILABLE,
            score=0,
            threshold="Cần provider hoặc dữ liệu chuyên biệt",
            reason="Chưa có dữ liệu đủ tin cậy để đánh giá tiêu chí này.",
            data_source="not_available",
        )

    @staticmethod
    def _criterion(
        criterion_id: str,
        name: str,
        passed: bool,
        *,
        value: Any,
        threshold: str,
        reason: str,
        data_source: str = "validated_market_data",
    ) -> PP10Criterion:
        return PP10Criterion(
            criterion_id=criterion_id,
            name=name,
            status=EvaluationStatus.PASS if passed else EvaluationStatus.FAIL,
            score=1 if passed else 0,
            value=value,
            threshold=threshold,
            reason=reason,
            data_source=data_source,
        )

    def _trend(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        values = (indicators.ma20, indicators.ma50, indicators.ma150, indicators.ma200)
        if any(value is None for value in values):
            return self._unsupported("1", "Xu hướng MA tổng thể")
        assert all(value is not None for value in values)
        passed = (
            float(indicators.price)
            > indicators.ma20
            > indicators.ma50
            > indicators.ma150
            > indicators.ma200
        )
        return self._criterion(
            "1",
            "Xu hướng MA tổng thể",
            passed,
            value={
                "price": float(indicators.price),
                "ma20": indicators.ma20,
                "ma50": indicators.ma50,
                "ma150": indicators.ma150,
                "ma200": indicators.ma200,
            },
            threshold="Price > MA20 > MA50 > MA150 > MA200",
            reason=(
                "Giá và các đường MA đang xếp theo đúng thứ tự tăng trưởng."
                if passed
                else "Giá hoặc thứ tự MA chưa đáp ứng xu hướng tăng tổng thể."
            ),
        )

    def _volume(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        if indicators.volume_breakout is None:
            return self._unsupported("6", "Khối lượng và breakout")
        passed = indicators.volume_breakout
        return self._criterion(
            "6",
            "Khối lượng và breakout",
            passed,
            value={
                "breakout_volume": indicators.volume_breakout,
                "dry_up": indicators.volume_dry_up,
            },
            threshold="Volume phiên xác nhận >= 1.5 lần trung bình 20 phiên",
            reason=(
                "Đạt proxy khối lượng breakout."
                if passed
                else "Khối lượng chưa đạt proxy breakout."
            ),
        )

    def _money_flow(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        if indicators.cmf20 is None or indicators.obv_change_5 is None:
            return self._unsupported("9", "OBV và CMF")
        passed = indicators.cmf20 > 0 and indicators.obv_change_5 > 0
        return self._criterion(
            "9",
            "OBV và CMF",
            passed,
            value={"cmf20": indicators.cmf20, "obv_change_5": indicators.obv_change_5},
            threshold="CMF20 > 0 và OBV tăng trong 5 phiên",
            reason=(
                "Dòng tiền cho thấy xu hướng tích lũy."
                if passed
                else "Chưa có xác nhận đồng thời từ OBV và CMF."
            ),
        )

    def _macd(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        if indicators.macd is None or indicators.macd_signal is None:
            return self._unsupported("10", "MACD")
        passed = indicators.macd > indicators.macd_signal
        return self._criterion(
            "10",
            "MACD",
            passed,
            value={"macd": indicators.macd, "signal": indicators.macd_signal},
            threshold="MACD > Signal",
            reason=(
                "MACD đang nằm trên đường tín hiệu."
                if passed
                else "MACD chưa nằm trên đường tín hiệu."
            ),
        )

    def _rsi_adx(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        values = (indicators.rsi14, indicators.adx14, indicators.plus_di14, indicators.minus_di14)
        if any(value is None for value in values):
            return self._unsupported("11", "RSI và ADX")
        assert all(value is not None for value in values)
        passed = (
            indicators.rsi14 > 55
            and indicators.adx14 > 20
            and indicators.plus_di14 > indicators.minus_di14
        )
        return self._criterion(
            "11",
            "RSI và ADX",
            passed,
            value={
                "rsi14": indicators.rsi14,
                "adx14": indicators.adx14,
                "+di": indicators.plus_di14,
                "-di": indicators.minus_di14,
            },
            threshold="RSI > 55; ADX > 20; +DI > -DI",
            reason=(
                "Động lượng và xu hướng đạt ngưỡng."
                if passed
                else "RSI/ADX chưa đồng thời đạt ngưỡng."
            ),
        )

    def _stoch_rsi(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        if indicators.stoch_rsi14 is None:
            return self._unsupported("12", "Stochastic RSI")
        passed = indicators.stoch_rsi14 > 50
        return self._criterion(
            "12",
            "Stochastic RSI",
            passed,
            value=indicators.stoch_rsi14,
            threshold="Stoch RSI > 50",
            reason=(
                "Stochastic RSI duy trì động lượng tích cực."
                if passed
                else "Stochastic RSI chưa xác nhận động lượng tăng."
            ),
        )

    def _market(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        values = (indicators.market_price, indicators.market_ma20, indicators.market_ma50)
        if any(value is None for value in values):
            return self._unsupported("15", "Xu hướng thị trường chung")
        assert all(value is not None for value in values)
        passed = indicators.market_price > indicators.market_ma20 > indicators.market_ma50
        return self._criterion(
            "15",
            "Xu hướng thị trường chung",
            passed,
            value={
                "price": indicators.market_price,
                "ma20": indicators.market_ma20,
                "ma50": indicators.market_ma50,
            },
            threshold="VN-Index price > MA20 > MA50",
            reason=(
                "VN-Index đang trong xu hướng tăng."
                if passed
                else "VN-Index chưa xác nhận xu hướng tăng."
            ),
            data_source="VNINDEX_validated_market_data",
        )

    @staticmethod
    def _grade(ratio: float, evaluated_count: int) -> str:
        if evaluated_count >= 14 and ratio >= 0.875:
            return "A+"
        if evaluated_count >= 12 and ratio >= 0.75:
            return "A"
        if evaluated_count >= 10 and ratio >= 0.60:
            return "B"
        return "C"
