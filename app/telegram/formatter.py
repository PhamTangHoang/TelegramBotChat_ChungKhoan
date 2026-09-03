from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.domain.enums import AnalysisKind, DataFreshness, RuleStatus, Signal

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
    news: Iterable[Any] = (),
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

    news_items = list(news)
    if news_items:
        lines.extend(["", "NEWS"])
        for item in news_items:
            lines.append(f"• {getattr(item, 'title', item)}")

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
    return f"• {icon} {reason.label}: {reason.status.value} ({_number(reason.value)})"


def _number(value: Any) -> str:
    return "N/A" if value is None else str(value)
