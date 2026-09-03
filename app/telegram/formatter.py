from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.data.news_text import sanitize_news_text
from app.domain.enums import AnalysisKind, DataFreshness, EvaluationStatus, RuleStatus, Signal

DISCLAIMER = (
    "Công cụ hỗ trợ phân tích cá nhân, không phải khuyến nghị đầu tư. "
    "Score không phải xác suất dự đoán."
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
    lines = [
        f"{symbol.upper()} — Technical Analysis",
        f"Tính đến: {as_of.isoformat()}",
        f"Status: {analysis_kind.value} / {'FINAL' if is_final else 'NOT FINAL'}",
        f"Data: {data_freshness.value}",
        "",
        f"Price: {indicators.price}",
        "",
        "TREND",
        _reason_line(rule_result, "R1"),
        _reason_line(rule_result, "R2"),
        _reason_line(rule_result, "R3"),
        "",
        "MOMENTUM",
        f"• RSI14: {_number(indicators.rsi14)}",
        f"• MACD Histogram: {_number(indicators.macd_histogram)}",
        f"• ATR14: {_number(indicators.atr14)}",
        "",
        "VOLUME",
        f"• Volume Ratio (projected): {_number(indicators.volume_ratio_projected)}",
        f"• Regular trading time elapsed: {indicators.elapsed_trading_minutes} min",
        "",
        "RELATIVE STRENGTH",
        f"• Relative performance vs VNINDEX: {_number(indicators.relative_return)}",
        "",
        "RULE ENGINE",
        f"Score: {rule_result.score}/{rule_result.max_score}",
        f"Signal: {rule_result.signal.value}",
        f"Risk: {rule_result.risk.value}",
    ]

    if rule_result.signal == Signal.INSUFFICIENT_DATA:
        lines.append("⚠️ Chưa đủ dữ liệu bắt buộc; không tạo signal giả.")
    if any(reason.status == RuleStatus.NOT_EVALUATED for reason in rule_result.reasons):
        lines.append("⚠️ R6 chưa đánh giá vì chưa đủ 15 phút giao dịch.")

    if pp10 is not None:
        lines.extend(
            [
                "",
                "PP10ULTI",
                f"Score: {pp10.score}/{pp10.max_score} "
                f"(đánh giá được {pp10.evaluated_count}/16 tiêu chí)",
                f"Grade: {pp10.grade}",
                f"Confidence: {pp10.confidence} (không phải xác suất)",
            ]
        )
        for criterion in pp10.criteria:
            lines.append(
                f"{criterion.criterion_id}. {_status_icon(criterion.status)} "
                f"{criterion.name}: {criterion.status.value} — {criterion.reason}"
            )
        lines.extend(
            [
                "",
                "POSITION PLAN",
                f"• Vùng mua: {pp10.risk_plan.entry_zone}",
                f"• Vùng gia tăng: {pp10.risk_plan.add_zone}",
                f"• Stop-loss: {pp10.risk_plan.stop_loss}",
                f"• Mục tiêu: {pp10.risk_plan.target}",
                f"• Risk/Reward: {pp10.risk_plan.risk_reward}",
            ]
        )

    if gemini is not None:
        lines.extend(
            [
                "",
                "GEMINI ANALYSIS",
                f"Technical Summary: {gemini.technical_explanation}",
                f"Bull Case: {gemini.bull_case}",
                f"Bear Case: {gemini.bear_case}",
                f"Risk: {gemini.risk}",
                f"Conclusion: {gemini.conclusion}",
            ]
        )

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
    return f"• {icon} {reason.message}: {reason.status.value} ({_number(reason.value)})"


def _number(value: Any) -> str:
    return "N/A" if value is None else str(value)


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
