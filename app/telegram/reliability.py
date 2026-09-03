from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.telegram.formatter import chunk_message

logger = logging.getLogger(__name__)


async def send_text_chunks(
    sender: Callable[[str], Awaitable[Any]],
    text: str,
    *,
    max_length: int = 3800,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> None:
    for chunk in chunk_message(text, max_length=max_length):
        try:
            await sender(chunk)
        except Exception as exc:
            retry_after = getattr(exc, "retry_after", None)
            if retry_after is None:
                raise
            await sleep(float(retry_after))
            await sender(chunk)


async def send_report_with_chart(
    message: Any,
    text: str,
    *,
    chart: bytes | None = None,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> None:
    await send_text_chunks(message.answer, text, sleep=sleep)
    if chart is None:
        return
    try:
        from aiogram.types import BufferedInputFile

        await message.answer_photo(BufferedInputFile(chart, filename="technical-chart.png"))
    except Exception:
        # Text report has already been delivered; chart failure must not erase it.
        logger.exception("Telegram chart upload failed")
