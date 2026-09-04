from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.data.news_text import sanitize_news_text
from app.domain.enums import AnalysisKind, DataFreshness, EvaluationStatus, RuleStatus, Signal

DISCLAIMER = (
    "Công cụ hỗ trợ phân tích cá nhân, không phải khuyến nghị đầu tư. "
    "Score không phải xác suất dự đoán."
)

_PP10_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("NHÓM KỸ THUẬT", ("1", "2", "3", "4")),
    ("NHÓM DÒNG TIỀN", ("5", "6", "7", "8", "9")),
    ("NHÓM ĐỘNG LƯỢNG", ("10", "11", "12")),
    ("NHÓM CƠ BẢN", ("13",)),
    ("NHÓM ĐỊNH GIÁ & VĨ MÔ", ("14", "15")),
    ("NHÓM QUẢN TRỊ VỊ THẾ", ("16",)),
)


def _analysis_kind_label(analysis_kind: AnalysisKind, is_final: bool) -> str:
    if is_final or analysis_kind == AnalysisKind.FINAL:
        return "Cuối phiên"
    return "Trong phiên"


def _data_freshness_label(data_freshness: DataFreshness) -> str:
    if data_freshness == DataFreshness.STALE_CACHE:
        return "Cache cũ — cần thận trọng"
    return "Dữ liệu mới"


def _signal_label(signal: Signal) -> str:
    return {
        Signal.BULLISH: "TÍCH CỰC",
        Signal.NEUTRAL: "TRUNG TÍNH",
        Signal.BEARISH: "TIÊU CỰC",
        Signal.INSUFFICIENT_DATA: "CHƯA ĐỦ DỮ LIỆU",
    }.get(signal, str(signal))


def _risk_label(risk: Any) -> str:
    return {
        "LOW": "THẤP",
        "MEDIUM": "TRUNG BÌNH",
        "HIGH": "CAO",
    }.get(getattr(risk, "value", risk), str(risk))


def _confidence_label(confidence: str) -> str:
    return {"High": "Cao", "Medium": "Trung bình", "Low": "Thấp"}.get(
        confidence, confidence
    )


def _grade_stars(grade: str) -> str:
    return {"A+": "⭐⭐⭐⭐⭐", "A": "⭐⭐⭐⭐", "B": "⭐⭐⭐", "C": "⭐⭐"}.get(
        grade, ""
    )


def _criterion_status(status: EvaluationStatus) -> str:
    return {
        EvaluationStatus.PASS: "✅ ĐẠT",
        EvaluationStatus.FAIL: "❌ CHƯA ĐẠT",
        EvaluationStatus.NOT_EVALUATED: "⚠️ CHƯA ĐÁNH GIÁ",
        EvaluationStatus.DATA_UNAVAILABLE: "⚠️ CHƯA CÓ DỮ LIỆU",
    }.get(status, str(status))


def _criterion_score(criterion: Any) -> str:
    if criterion.status in {EvaluationStatus.PASS, EvaluationStatus.FAIL}:
        return f"{criterion.score}/1"
    return "—"


def _pp10_conclusion(pp10: Any, rule_result: Any) -> str:
    evaluated = [
        criterion
        for criterion in pp10.criteria
        if criterion.status in {EvaluationStatus.PASS, EvaluationStatus.FAIL}
    ]
    passed = [
        criterion.name for criterion in evaluated if criterion.status == EvaluationStatus.PASS
    ]
    failed = [
        criterion.name for criterion in evaluated if criterion.status == EvaluationStatus.FAIL
    ]
    unavailable = [
        criterion.name
        for criterion in pp10.criteria
        if criterion.status in {EvaluationStatus.DATA_UNAVAILABLE, EvaluationStatus.NOT_EVALUATED}
    ]

    if not evaluated:
        conclusion = (
            "Chưa thể kết luận xu hướng theo PP10Ulti vì hiện chưa có đủ dữ liệu "
            "để chấm các tiêu chí."
        )
    elif rule_result.signal == Signal.BULLISH:
        conclusion = "Tín hiệu định lượng đang nghiêng về chiều tích cực theo dữ liệu hiện có."
    elif rule_result.signal == Signal.BEARISH:
        conclusion = "Tín hiệu định lượng đang nghiêng về chiều tiêu cực theo dữ liệu hiện có."
    elif rule_result.signal == Signal.NEUTRAL:
        conclusion = "Tín hiệu định lượng chưa xác nhận một xu hướng rõ ràng."
    else:
        conclusion = "Chưa đủ dữ liệu bắt buộc để đưa ra kết luận định lượng."

    details: list[str] = []
    if passed:
        details.append(f"Điểm tích cực: {', '.join(passed[:3])}.")
    if failed:
        details.append(f"Điểm cần theo dõi: {', '.join(failed[:3])}.")
    if unavailable:
        details.append(f"Còn thiếu: {', '.join(unavailable[:3])}.")
    return " ".join([conclusion, *details])


def _pp10_action_plan(pp10: Any) -> list[str]:
    risk_plan = pp10.risk_plan
    return [
        "3. KẾ HOẠCH HÀNH ĐỘNG THAM KHẢO",
        "Kịch bản | Vùng giá | Chiến lược",
        (
            "Kịch bản 1 (Tích cực) | "
            f"{risk_plan.add_zone} | Chỉ cân nhắc gia tăng khi breakout được xác nhận."
        ),
        (
            "Kịch bản 2 (Trung tính) | "
            f"{risk_plan.entry_zone} | Theo dõi phản ứng giá trong vùng tham chiếu."
        ),
        (
            "Kịch bản 3 (Tiêu cực) | "
            f"{risk_plan.stop_loss} | Dừng mua mới và đánh giá lại cấu trúc."
        ),
        "",
        "Quản trị vị thế:",
        f"• Stop-loss tham chiếu: {risk_plan.stop_loss}",
        f"• Mục tiêu tham chiếu: {risk_plan.target}",
        f"• Risk/Reward tham chiếu: {risk_plan.risk_reward}",
    ]


def format_gemini_explanation(gemini: Any) -> str:
    return "\n".join(
        (
            "GIẢI THÍCH GEMINI",
            f"• Tóm tắt kỹ thuật: {gemini.technical_explanation}",
            f"• Kịch bản tích cực: {gemini.bull_case}",
            f"• Kịch bản tiêu cực: {gemini.bear_case}",
            f"• Rủi ro: {gemini.risk}",
            f"• Kết luận: {gemini.conclusion}",
        )
    )


def format_technical_report(
    *,
    symbol: str,
    as_of: datetime,
    analysis_kind: AnalysisKind,
    is_final: bool,
    indicators: Any,
    rule_result: Any,
    data_freshness: DataFreshness,
    gemini: Any | None = None,
    pp10: Any | None = None,
) -> str:
    if pp10 is None:
        lines = [
            f"BÁO CÁO PHÂN TÍCH — {symbol.upper()}",
            f"Giá tham chiếu: {_price_per_share(indicators.price)}",
            f"Ngày: {as_of.strftime('%d/%m/%Y')}",
            "Đơn vị giá: VND/cổ phiếu (vnstock trả dữ liệu theo nghìn VND)",
            (
                f"Tín hiệu kỹ thuật: {_signal_label(rule_result.signal)} | "
                f"Rủi ro: {_risk_label(rule_result.risk)}"
            ),
        ]
    else:
        criteria_by_id = {criterion.criterion_id: criterion for criterion in pp10.criteria}
        total_criteria = getattr(pp10, "total_criteria", 16)
        lines = [
            f"BÁO CÁO PP10ULTI 2.0 – {symbol.upper()}",
            (
                f"Giá tham chiếu: {_price_per_share(indicators.price)} | "
                f"Ngày: {as_of.strftime('%d/%m/%Y')}"
            ),
            (
                f"Kỳ phân tích: {_analysis_kind_label(analysis_kind, is_final)} | "
                f"Trạng thái dữ liệu: {_data_freshness_label(data_freshness)}"
            ),
            "Đơn vị giá: VND/cổ phiếu (vnstock trả dữ liệu theo nghìn VND)",
            "",
            "1. TỔNG ĐIỂM PP10ULTI 2.0",
            (
                f"Tổng điểm: {pp10.score}/{pp10.max_score} tiêu chí có dữ liệu"
                if pp10.max_score
                else "Tổng điểm: chưa chấm được tiêu chí nào"
            ),
            f"Độ phủ dữ liệu: {pp10.evaluated_count}/{total_criteria} tiêu chí",
            f"Xếp hạng: {_grade_stars(pp10.grade)} {pp10.grade}",
            f"Mức độ tin cậy: {_confidence_label(pp10.confidence)} (không phải xác suất)",
            (
                f"Tín hiệu kỹ thuật: {_signal_label(rule_result.signal)} | "
                f"Rủi ro: {_risk_label(rule_result.risk)}"
            ),
            f"Kết luận sơ bộ: {_pp10_conclusion(pp10, rule_result)}",
            "",
            "2. CHI TIẾT CÁC HẠNG MỤC",
            "Hạng mục | Điểm | Nhận xét chi tiết",
        ]

        for group_name, criterion_ids in _PP10_GROUPS:
            lines.extend(["", group_name])
            for criterion_id in criterion_ids:
                criterion = criteria_by_id.get(criterion_id)
                if criterion is None:
                    continue
                lines.append(
                    f"{criterion.criterion_id}. {criterion.name} | "
                    f"{_criterion_score(criterion)} | {_criterion_status(criterion.status)}"
                )
                lines.append(f"   Nhận xét: {criterion.reason}")
                value = getattr(criterion, "value", None)
                if value is not None:
                    lines.append(
                        f"   Dữ liệu: {_format_criterion_value(criterion.criterion_id, value)}"
                    )
                if criterion.status in {
                    EvaluationStatus.DATA_UNAVAILABLE,
                    EvaluationStatus.NOT_EVALUATED,
                }:
                    lines.append(f"   Điều kiện cần: {criterion.threshold}")

        lines.extend(_pp10_action_plan(pp10))
        lines.extend(
            [
                "",
                "🔔 KẾT LUẬN",
                (
                    f"Trạng thái kỹ thuật: {_signal_label(rule_result.signal)} — "
                    f"xếp hạng PP10Ulti {pp10.grade}."
                ),
                (
                    "Hành động tham khảo: theo dõi điều kiện xác nhận trong kế hoạch; "
                    "không xem đây là khuyến nghị mua/bán cá nhân."
                ),
            ]
        )

    if rule_result.signal == Signal.INSUFFICIENT_DATA:
        lines.append("⚠️ Chưa đủ dữ liệu bắt buộc; không tạo signal giả.")
    if any(reason.status == RuleStatus.NOT_EVALUATED for reason in rule_result.reasons):
        lines.append(
            "⚠️ Một số tiêu chí trong phiên chưa được đánh giá vì "
            "chưa đủ thời gian giao dịch."
        )

    if gemini is not None:
        lines.extend(["", format_gemini_explanation(gemini)])

    lines.extend(["", DISCLAIMER])
    return "\n".join(lines)


def format_news_report(
    *,
    symbol: str | None,
    as_of: datetime,
    items: Iterable[Any],
    status: str,
) -> str:
    news_items = list(items)
    subject = symbol.upper() if symbol else "thị trường"
    lines = [
        f"{subject} — News",
        f"Cập nhật đến: {_format_datetime(as_of)}",
        f"Trạng thái nguồn: {status}",
        "",
    ]
    if not news_items:
        lines.append("Chưa có tin tức phù hợp trong khoảng thời gian đã chọn.")
    else:
        for index, item in enumerate(news_items, start=1):
            title = sanitize_news_text(getattr(item, "title", ""), max_length=500)
            source = sanitize_news_text(getattr(item, "source", ""), max_length=128)
            lines.extend(
                [
                    f"{index}. {title or 'Không có tiêu đề'}",
                    f"Nguồn: {source or 'Không rõ'}",
                    f"Đăng lúc: {_format_datetime(getattr(item, 'published_at', None))}",
                    f"Bot lấy lúc: {_format_datetime(getattr(item, 'fetched_at', None))}",
                ]
            )
            summary = sanitize_news_text(getattr(item, "summary", ""), max_length=2000)
            if summary:
                lines.append(f"Tóm tắt: {summary}")
            url = getattr(item, "url", None)
            lines.append(f"Link bài viết: {url or 'Không có'}")
            lines.append("")

    lines.extend(
        [
            "Nguồn là dữ liệu tổng hợp từ RSS; nội dung chưa được bot xác minh độc lập.",
            "Tin tức chỉ mang tính tham khảo, không phải khuyến nghị đầu tư.",
        ]
    )
    return "\n".join(lines)


def chunk_message(text: str, *, max_length: int = 3800) -> list[str]:
    if max_length < 100:
        raise ValueError("max_length is too small for a safe Telegram message")
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n"):
        candidate = paragraph if not current else f"{current}\n{paragraph}"
        if len(candidate) <= max_length:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > max_length:
            chunks.append(paragraph[:max_length])
            paragraph = paragraph[max_length:]
        current = paragraph
    if current or not chunks:
        chunks.append(current)
    return chunks


def _reason_line(rule_result: Any, rule_id: str) -> str:
    reason = next((item for item in rule_result.reasons if item.rule_id == rule_id), None)
    if reason is None:
        return f"• {rule_id}: unavailable"
    icon = "✓" if reason.status == RuleStatus.PASS else "✗"
    value = (
        _price_per_share(reason.value)
        if rule_id in {"R1", "R2", "R3"}
        else _number(reason.value)
    )
    return f"• {icon} {reason.message}: {reason.status.value} ({value})"


def _number(value: Any) -> str:
    return "N/A" if value is None else str(value)


def _price_per_share(value: Any) -> str:
    formatted = _format_vnd(value)
    return "N/A" if formatted == "N/A" else f"{formatted}/cổ phiếu"


def _format_vnd(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        amount = (Decimal(str(value)) * Decimal("1000")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, TypeError, ValueError):
        return "N/A"
    return f"{amount:,.0f}".replace(",", ".") + " VND"


_PRICE_FIELDS_BY_CRITERION = {
    "1": {"price", "ma20", "ma50", "ma150", "ma200"},
    "4": {"pivot"},
    "7": {"poc", "hvn"},
    "8": {"weekly_top", "monthly_top"},
    "16": {"pivot", "support", "atr"},
}


def _format_criterion_value(criterion_id: str, value: Any) -> str:
    price_fields = _PRICE_FIELDS_BY_CRITERION.get(criterion_id, set())
    if not isinstance(value, Mapping):
        return _number(value)
    fields = []
    for key, item in value.items():
        display = _price_per_share(item) if key in price_fields else _number(item)
        fields.append(f"{key}: {display}")
    return ", ".join(fields)


def _status_icon(status: EvaluationStatus) -> str:
    if status == EvaluationStatus.PASS:
        return "✓"
    if status == EvaluationStatus.FAIL:
        return "✗"
    return "–"


def _format_datetime(value: Any) -> str:
    if not isinstance(value, datetime):
        return "Không rõ"
    return value.isoformat(sep=" ", timespec="minutes")
