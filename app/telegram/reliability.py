from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from app.chart.chart_engine import ChartAttachment
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
    charts: Sequence[ChartAttachment] = (),
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> None:
    attachments = list(charts)
    if chart is not None:
        attachments.append(
            ChartAttachment(
                filename="technical-chart.png",
                caption="Biểu đồ kỹ thuật",
                content=chart,
            )
        )
    for attachment in attachments:
        try:
            from aiogram.types import BufferedInputFile

            await message.answer_photo(
                BufferedInputFile(attachment.content, filename=attachment.filename),
                caption=attachment.caption,
            )
        except Exception:
            # Chart failure must not erase the text report or the remaining images.
            logger.exception("Telegram chart upload failed filename=%s", attachment.filename)
    await send_text_chunks(message.answer, text, sleep=sleep)
