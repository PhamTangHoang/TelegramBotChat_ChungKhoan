from __future__ import annotations

from typing import Any

from app.config.settings import Settings
from app.telegram.commands import aiogram_command_menu
from app.telegram.handlers import TelegramAnalysisService, build_router


def create_dispatcher(settings: Settings, service: TelegramAnalysisService) -> tuple[Any, Any]:
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required to start Telegram polling")
    from aiogram import Bot, Dispatcher

    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(
        build_router(
            service,
            allowed_chat_ids=settings.telegram_allowed_chat_ids,
            public_access=settings.telegram_public_access,
            rate_limit_per_minute=settings.telegram_rate_limit_per_min,
        )
    )
    return bot, dispatcher


async def configure_bot_commands(bot: Any) -> None:
    """Publish the command menu so Telegram shows descriptions after typing '/'."""
    await bot.set_my_commands(aiogram_command_menu())


async def run_polling(settings: Settings, service: TelegramAnalysisService) -> None:
    bot, dispatcher = create_dispatcher(settings, service)
    try:
        await configure_bot_commands(bot)
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
