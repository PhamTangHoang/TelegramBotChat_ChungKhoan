from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from app.telegram.access_control import AccessDenied, RateLimiter, WhitelistAccessController
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


def build_router(
    service: TelegramAnalysisService,
    *,
    allowed_chat_ids: tuple[int, ...],
    public_access: bool = False,
    rate_limit_per_minute: int,
):
    """Build aiogram handlers without importing aiogram during unit-only imports."""
    from aiogram import Router
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
                "VN Stock Analyst Bot sẵn sàng. Dùng /pt FPT, /chart FPT hoặc /market."
            )

    @router.message(Command("pt"))
    async def pt_handler(message: Message, command: CommandObject) -> None:
        if not await authorized(message):
            return
        symbol = (command.args or "").strip().upper()
        if not symbol:
            await message.answer("Cú pháp: /pt FPT")
            return
        await message.answer("⏳ Đang phân tích dữ liệu...")
        try:
            report = await service.analyze(symbol)
            await send_report_with_chart(message, report.text, chart=report.chart)
        except Exception:
            logger.exception("/pt failed for symbol=%s", symbol)
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

    return router
