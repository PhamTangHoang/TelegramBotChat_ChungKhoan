from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from app.telegram.access_control import AccessDenied, RateLimiter, WhitelistAccessController
from app.telegram.commands import HELP_TEXT
from app.telegram.reliability import send_report_with_chart, send_text_chunks

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramReport:
    text: str
    chart: bytes | None = None


class TelegramAnalysisService(Protocol):
    async def analyze(self, symbol: str) -> TelegramReport: ...

    async def chart(self, symbol: str) -> bytes: ...

    async def market(self) -> str: ...

    async def chat(self, message: str) -> str: ...


def _fold_text(value: str) -> str:
    folded = "".join(
        character
        for character in unicodedata.normalize("NFD", value.lower())
        if unicodedata.category(character) != "Mn"
    )
    return folded.replace("đ", "d")


def _classify_text(value: str) -> tuple[str, str | None]:
    folded = _fold_text(value).strip()
    chart_match = re.search(
        r"\b(?:chart|bieu do|ve bieu do)\s+(?:ma\s+)?([a-z]{2,5})\b", folded
    )
    if chart_match:
        return "chart", chart_match.group(1).upper()

    analysis_match = re.search(
        r"\b(?:analyze|phan tich(?: ky thuat)?|danh gia)\s+(?:ma\s+)?([a-z]{2,5})\b",
        folded,
    )
    if analysis_match:
        return "analyze", analysis_match.group(1).upper()

    if "thi truong" in folded or folded in {"market", "trang thai thi truong"}:
        return "market", None

    if folded in {"xin chao", "chao", "hello", "hi", "help", "tro giup", "menu"}:
        return "help", None

    if re.fullmatch(r"[a-z]{2,5}", folded) and folded not in {
        "hello",
        "chao",
        "help",
        "market",
        "analyze",
    }:
        return "analyze", folded.upper()
    return "chat", None


def build_router(
    service: TelegramAnalysisService,
    *,
    allowed_chat_ids: tuple[int, ...],
    public_access: bool = False,
    rate_limit_per_minute: int,
):
    """Build aiogram handlers without importing aiogram during unit-only imports."""
    from aiogram import F, Router
    from aiogram.filters import Command, CommandObject, CommandStart
    from aiogram.types import Message

    router = Router()
    access = WhitelistAccessController(allowed_chat_ids, public_access=public_access)
    limiter = RateLimiter(rate_limit_per_minute)

    async def authorized(message: Message) -> bool:
        chat_id = message.chat.id
        try:
            access.check(chat_id)
            limiter.require(chat_id)
        except AccessDenied:
            await message.answer("Yêu cầu bị từ chối.")
            return False
        return True

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        if await authorized(message):
            await message.answer(
                "VN Stock Analyst Bot sẵn sàng.\n\n"
                "Dùng /analyze FPT để phân tích, /chart FPT để xem biểu đồ, "
                "/news FPT để xem tin tức hoặc /market để xem thị trường.\n\n"
                "Gõ /help để xem hướng dẫn đầy đủ."
            )

    @router.message(Command("help"))
    async def help_handler(message: Message) -> None:
        if await authorized(message):
            await send_text_chunks(message.answer, HELP_TEXT)

    @router.message(Command("analyze"))
    async def analyze_handler(message: Message, command: CommandObject) -> None:
        if not await authorized(message):
            return
        symbol = (command.args or "").strip().upper()
        if not symbol:
            await message.answer("Cú pháp: /analyze FPT")
            return
        await message.answer("⏳ Đang phân tích dữ liệu...")
        try:
            report = await service.analyze(symbol)
            await send_report_with_chart(message, report.text, chart=report.chart)
        except Exception:
            logger.exception("/analyze failed for symbol=%s", symbol)
            await message.answer("Không thể hoàn tất phân tích lúc này.")

    @router.message(Command("chart"))
    async def chart_handler(message: Message, command: CommandObject) -> None:
        if not await authorized(message):
            return
        symbol = (command.args or "").strip().upper()
        if not symbol:
            await message.answer("Cú pháp: /chart FPT")
            return
        try:
            chart = await service.chart(symbol)
            from aiogram.types import BufferedInputFile

            await message.answer_photo(BufferedInputFile(chart, filename=f"{symbol}.png"))
        except Exception:
            logger.exception("/chart failed for symbol=%s", symbol)
            await message.answer("Không thể tạo chart lúc này.")

    @router.message(Command("market"))
    async def market_handler(message: Message) -> None:
        if not await authorized(message):
            return
        try:
            await send_text_chunks(message.answer, await service.market())
        except Exception:
            logger.exception("/market failed")
            await message.answer("Không thể tải trạng thái thị trường lúc này.")

    @router.message(F.text)
    async def text_handler(message: Message) -> None:
        if not await authorized(message):
            return
        text = (message.text or "").strip()
        kind, symbol = _classify_text(text)
        if kind == "help":
            await send_text_chunks(message.answer, HELP_TEXT)
            return
        if kind == "market":
            await send_text_chunks(message.answer, await service.market())
            return
        if kind == "analyze" and symbol is not None:
            await message.answer("⏳ Đang phân tích dữ liệu...")
            try:
                report = await service.analyze(symbol)
                await send_report_with_chart(message, report.text, chart=report.chart)
            except Exception:
                logger.exception("natural analyze failed for symbol=%s", symbol)
                await message.answer("Không thể hoàn tất phân tích lúc này.")
            return
        if kind == "chart" and symbol is not None:
            try:
                from aiogram.types import BufferedInputFile

                chart = await service.chart(symbol)
                await message.answer_photo(BufferedInputFile(chart, filename=f"{symbol}.png"))
            except Exception:
                logger.exception("natural chart failed for symbol=%s", symbol)
                await message.answer("Không thể tạo chart lúc này.")
            return
        try:
            await send_text_chunks(message.answer, await service.chat(text))
        except Exception:
            logger.exception("natural chat failed")
            await message.answer("Tạm thời chưa thể trả lời tin nhắn này.")

    return router
