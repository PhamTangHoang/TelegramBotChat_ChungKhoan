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
        criteria[1] = self._wyckoff(indicators)
        criteria[2] = self._pattern(indicators)
        criteria[3] = self._pattern_quality(indicators)
        criteria[4] = self._relative_strength(indicators)
        criteria[5] = self._volume(indicators)
        criteria[6] = self._vpvr(indicators)
        criteria[7] = self._cpr(indicators)
        criteria[8] = self._money_flow(indicators)
        criteria[9] = self._macd(indicators)
        criteria[10] = self._rsi_adx(indicators)
        criteria[11] = self._stoch_rsi(indicators)
        criteria[12] = self._fundamentals(indicators)
        criteria[13] = self._valuation(indicators)
        criteria[14] = self._market(indicators)
        criteria[15], risk_plan = self._position(indicators)

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
            risk_plan=risk_plan,
        )

    @staticmethod
    def _unsupported(
        criterion_id: str,
        name: str,
        *,
        reason: str = "Chưa có dữ liệu đủ tin cậy để đánh giá tiêu chí này.",
        threshold: str = "Cần provider hoặc dữ liệu chuyên biệt",
        data_source: str = "not_available",
    ) -> PP10Criterion:
        return PP10Criterion(
            criterion_id=criterion_id,
            name=name,
            status=EvaluationStatus.DATA_UNAVAILABLE,
            score=0,
            threshold=threshold,
            reason=reason,
            data_source=data_source,
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
            names = ("MA20", "MA50", "MA150", "MA200")
            missing = [name for name, value in zip(names, values, strict=True) if value is None]
            return self._unsupported(
                "1",
                "Xu hướng MA tổng thể",
                reason=f"Thiếu {', '.join(missing)}; cần tối thiểu 200 phiên lịch sử.",
                threshold="Price > MA20 > MA50 > MA150 > MA200",
                data_source="validated_market_data",
            )
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
            reason = (
                "Nến hiện tại chưa chốt phiên; volume breakout chỉ chấm khi có dữ liệu final."
                if not indicators.is_final
                else "Thiếu dữ liệu volume hợp lệ để xác nhận breakout."
            )
            return self._unsupported(
                "6",
                "Khối lượng và breakout",
                reason=reason,
                threshold="Volume phiên xác nhận >= 1.5 lần trung bình 20 phiên",
                data_source="validated_market_data",
            )
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

    def _wyckoff(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        phase = indicators.wyckoff_phase
        if phase is None:
            return self._unsupported(
                "2",
                "Pha Wyckoff",
                reason="Thiếu tối thiểu 30 phiên OHLCV để tạo heuristic Wyckoff.",
                threshold="Accumulation hoặc Markup",
                data_source="validated_ohlcv_heuristic",
            )
        passed = phase in {"Accumulation", "Markup"}
        return self._criterion(
            "2",
            "Pha Wyckoff",
            passed,
            value=phase,
            threshold="Accumulation hoặc Markup",
            reason=(
                "Heuristic xác định pha tích lũy/markup."
                if passed
                else "Heuristic chưa xác định pha thuận lợi."
            ),
            data_source="validated_ohlcv_heuristic",
        )

    def _pattern(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        pattern = indicators.pattern_name
        quality = indicators.pattern_quality
        if pattern is None or quality is None:
            return self._unsupported(
                "3",
                "Mẫu hình Dan Zanger",
                reason="Thiếu tối thiểu 30 phiên OHLCV để nhận diện mẫu hình heuristic.",
                threshold="Mẫu hình rõ ràng và quality >= 0.70",
                data_source="validated_ohlcv_heuristic",
            )
        passed = pattern != "No clear pattern" and quality >= 0.7
        return self._criterion(
            "3",
            "Mẫu hình Dan Zanger",
            passed,
            value={"pattern": pattern, "quality": quality},
            threshold="Mẫu hình rõ ràng và quality >= 0.70",
            reason=(
                f"Đã nhận diện heuristic mẫu hình {pattern}."
                if passed
                else "Chưa có mẫu hình đủ rõ theo ngưỡng heuristic."
            ),
            data_source="validated_ohlcv_heuristic",
        )

    def _pattern_quality(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        quality = indicators.pattern_quality
        if quality is None:
            return self._unsupported(
                "4",
                "Chất lượng mẫu hình theo Peter Brandt",
                reason="Thiếu dữ liệu mẫu hình heuristic để chấm chất lượng.",
                threshold="Quality >= 0.70 và có pivot",
                data_source="validated_ohlcv_heuristic",
            )
        passed = quality >= 0.7 and indicators.pivot_price is not None
        return self._criterion(
            "4",
            "Chất lượng mẫu hình theo Peter Brandt",
            passed,
            value={"quality": quality, "pivot": indicators.pivot_price},
            threshold="Quality >= 0.70 và có pivot",
            reason=(
                "Mẫu hình có pivot và chất lượng heuristic đạt ngưỡng."
                if passed
                else "Mẫu hình chưa đạt chất lượng hoặc thiếu pivot."
            ),
            data_source="validated_ohlcv_heuristic",
        )

    def _relative_strength(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        if indicators.rs_rating is None or indicators.rs_line_new_high is None:
            missing = []
            if indicators.rs_rating is None:
                missing.append("RS Rating theo toàn bộ universe")
            if indicators.rs_line_new_high is None:
                missing.append("RS Line")
            return self._unsupported(
                "5",
                "RS Rating và RS Line",
                reason=f"Thiếu {', '.join(missing)}.",
                threshold="RS Rating >= 80 và RS Line tạo đỉnh mới",
                data_source="market_universe_relative_strength",
            )
        passed = indicators.rs_rating >= 80 and indicators.rs_line_new_high
        return self._criterion(
            "5",
            "RS Rating và RS Line",
            passed,
            value={
                "rating": indicators.rs_rating,
                "new_high": indicators.rs_line_new_high,
            },
            threshold="RS Rating >= 80 và RS Line tạo đỉnh mới",
            reason=(
                "RS Rating và RS Line cùng xác nhận."
                if passed
                else "RS Rating hoặc RS Line chưa đạt ngưỡng."
            ),
            data_source="market_universe_relative_strength",
        )

    def _vpvr(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        values = (indicators.vpvr_poc, indicators.vpvr_hvn, indicators.vpvr_breakout)
        if any(value is None for value in values):
            return self._unsupported(
                "7",
                "Volume Profile / VPVR",
                reason="Thiếu tối thiểu 20 phiên OHLCV để dựng VPVR xấp xỉ.",
                threshold="Giá vượt vùng POC/HVN",
                data_source="validated_ohlcv_vpvr_approximation",
            )
        passed = indicators.vpvr_breakout is True
        return self._criterion(
            "7",
            "Volume Profile / VPVR",
            passed,
            value={"poc": indicators.vpvr_poc, "hvn": indicators.vpvr_hvn},
            threshold="Giá vượt vùng POC/HVN",
            reason=(
                "Giá đã vượt vùng volume node heuristic."
                if passed
                else "Giá chưa vượt vùng volume node heuristic."
            ),
            data_source="validated_ohlcv_vpvr_approximation",
        )

    def _cpr(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        values = (
            indicators.cpr_weekly_top,
            indicators.cpr_weekly_bottom,
            indicators.cpr_monthly_top,
            indicators.cpr_monthly_bottom,
            indicators.cpr_weekly_bullish,
            indicators.cpr_monthly_bullish,
        )
        if any(value is None for value in values):
            return self._unsupported(
                "8",
                "CPR tuần và tháng",
                reason="Thiếu dữ liệu của ít nhất hai tuần và hai tháng đã hoàn tất để tính CPR.",
                threshold="Giá trên CPR tuần/tháng và CPR hướng tăng",
                data_source="validated_ohlcv_cpr",
            )
        price = float(indicators.price)
        passed = (
            price > indicators.cpr_weekly_top
            and price > indicators.cpr_monthly_top
            and indicators.cpr_weekly_bullish
            and indicators.cpr_monthly_bullish
        )
        return self._criterion(
            "8",
            "CPR tuần và tháng",
            passed,
            value={
                "weekly_top": indicators.cpr_weekly_top,
                "monthly_top": indicators.cpr_monthly_top,
            },
            threshold="Giá trên CPR tuần/tháng và CPR hướng tăng",
            reason=(
                "Giá và hướng CPR cùng xác nhận tăng."
                if passed
                else "CPR chưa đồng thời xác nhận tăng."
            ),
            data_source="validated_ohlcv_cpr",
        )

    def _money_flow(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        if indicators.cmf20 is None or indicators.obv_change_5 is None:
            return self._unsupported(
                "9",
                "OBV và CMF",
                reason="Thiếu đủ OHLCV và volume để tính CMF20 hoặc biến động OBV 5 phiên.",
                threshold="CMF20 > 0 và OBV tăng trong 5 phiên",
                data_source="validated_market_data",
            )
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
            return self._unsupported(
                "10",
                "MACD",
                reason="Thiếu đủ lịch sử giá để tính MACD và đường tín hiệu.",
                threshold="MACD > Signal",
                data_source="validated_market_data",
            )
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
            return self._unsupported(
                "11",
                "RSI và ADX",
                reason="Thiếu đủ lịch sử giá để tính RSI14, ADX14 và DI.",
                threshold="RSI > 55; ADX > 20; +DI > -DI",
                data_source="validated_market_data",
            )
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
            return self._unsupported(
                "12",
                "Stochastic RSI",
                reason="Thiếu đủ lịch sử giá để tính Stochastic RSI14.",
                threshold="Stoch RSI > 50",
                data_source="validated_market_data",
            )
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

    def _fundamentals(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        values = (
            indicators.revenue_growth,
            indicators.earnings_growth,
            indicators.eps_growth,
            indicators.roe,
        )
        if any(value is None for value in values):
            names = ("doanh thu", "lợi nhuận", "EPS", "ROE")
            missing = [name for name, value in zip(names, values, strict=True) if value is None]
            return self._unsupported(
                "13",
                "Cơ bản doanh nghiệp",
                reason=f"Fundamental provider chưa trả về: {', '.join(missing)}.",
                threshold="Doanh thu, lợi nhuận, EPS và ROE tăng",
                data_source="fundamental_provider",
            )
        passed = all(value > 0 for value in values)
        return self._criterion(
            "13",
            "Cơ bản doanh nghiệp",
            passed,
            value={
                "revenue": indicators.revenue_growth,
                "earnings": indicators.earnings_growth,
                "eps": indicators.eps_growth,
                "roe": indicators.roe,
            },
            threshold="Doanh thu, lợi nhuận, EPS và ROE tăng",
            reason=(
                "Các chỉ số cơ bản chính cùng tăng."
                if passed
                else "Một hoặc nhiều chỉ số cơ bản chưa tăng."
            ),
            data_source="fundamental_provider",
        )

    def _valuation(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        values = (
            indicators.pe,
            indicators.pb,
            indicators.sector_pe,
            indicators.sector_pb,
            indicators.historical_pe,
            indicators.historical_pb,
        )
        if any(value is None for value in values):
            names = ("P/E", "P/B", "P/E ngành", "P/B ngành", "P/E lịch sử", "P/B lịch sử")
            missing = [name for name, value in zip(names, values, strict=True) if value is None]
            return self._unsupported(
                "14",
                "Định giá",
                reason=f"Thiếu dữ liệu so sánh: {', '.join(missing)}.",
                threshold="P/E và P/B không cao hơn ngành/lịch sử quá 20%",
                data_source="fundamental_provider",
            )
        passed = (
            indicators.pe <= indicators.sector_pe
            and indicators.pb <= indicators.sector_pb
            and indicators.pe <= indicators.historical_pe * 1.2
            and indicators.pb <= indicators.historical_pb * 1.2
        )
        return self._criterion(
            "14",
            "Định giá",
            passed,
            value={"pe": indicators.pe, "pb": indicators.pb},
            threshold="P/E và P/B không cao hơn ngành/lịch sử quá 20%",
            reason=(
                "Định giá nằm trong ngưỡng so sánh."
                if passed
                else "Định giá đang cao hơn ngưỡng so sánh."
            ),
            data_source="fundamental_provider",
        )

    def _position(self, indicators: IndicatorSnapshot) -> tuple[PP10Criterion, PP10RiskPlan]:
        pivot = indicators.pivot_price
        support = indicators.support_price
        atr = indicators.atr14
        if pivot is None or support is None or atr is None or indicators.pattern_quality is None:
            missing = []
            if pivot is None:
                missing.append("pivot")
            if support is None:
                missing.append("hỗ trợ")
            if atr is None:
                missing.append("ATR14")
            if indicators.pattern_quality is None:
                missing.append("pattern quality")
            return (
                self._unsupported(
                    "16",
                    "Quản trị vị thế",
                    reason=f"Thiếu dữ liệu để lập kế hoạch: {', '.join(missing)}.",
                    threshold="Có pivot, hỗ trợ và ATR để lập kế hoạch",
                    data_source="validated_ohlcv_structure",
                ),
                _unavailable_risk_plan(),
            )
        stop = max(0.01, support - atr * 0.5)
        target = pivot + (pivot - stop) * 2
        risk = max(0.01, pivot - stop)
        plan = PP10RiskPlan(
            entry_zone=f"{pivot * 0.98:.2f}–{pivot * 1.02:.2f} (tham chiếu)",
            add_zone=f"Trên {pivot * 1.02:.2f} khi breakout được xác nhận",
            stop_loss=f"Dưới {stop:.2f} hoặc dưới cấu trúc hỗ trợ",
            target=f"Khoảng {target:.2f} theo R:R 2:1",
            risk_reward=f"1:{(target - pivot) / risk:.1f}",
        )
        return self._criterion(
            "16",
            "Quản trị vị thế",
            True,
            value={"pivot": pivot, "support": support, "atr": atr},
            threshold="Có pivot, hỗ trợ và ATR để lập kế hoạch",
            reason="Đã lập kế hoạch tham chiếu theo cấu trúc và ATR.",
            data_source="validated_ohlcv_structure",
        ), plan

    def _market(self, indicators: IndicatorSnapshot) -> PP10Criterion:
        values = (indicators.market_price, indicators.market_ma20, indicators.market_ma50)
        if any(value is None for value in values):
            names = ("VN-Index price", "VN-Index MA20", "VN-Index MA50")
            missing = [name for name, value in zip(names, values, strict=True) if value is None]
            return self._unsupported(
                "15",
                "Xu hướng thị trường chung",
                reason=f"Thiếu {', '.join(missing)}.",
                threshold="VN-Index price > MA20 > MA50",
                data_source="VNINDEX_validated_market_data",
            )
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


def _unavailable_risk_plan() -> PP10RiskPlan:
    return PP10RiskPlan(
        entry_zone="Chưa xác định — chưa có cấu trúc breakout được đánh giá",
        add_zone="Chưa xác định",
        stop_loss="Chưa xác định — cần swing low hoặc hỗ trợ hợp lệ",
        target="Chưa xác định — cần kháng cự/cấu trúc giá",
        risk_reward="Chưa xác định",
    )
