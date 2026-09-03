import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI

from app.config.settings import get_settings
from app.market.calendar import HOSECalendar

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    scheduler = None
    bot = None
    polling_task: asyncio.Task[Any] | None = None
    if settings.telegram_bot_token:
        try:
            from app.data.providers.rss import RssProvider
            from app.data.providers.vnstock import VnstockProvider
            from app.database.connection import SessionLocal
            from app.llm.gemini import GeminiExplainer
            from app.scheduler.scheduler import SchedulerService
            from app.services.analysis_service import MarketAnalysisService
            from app.telegram.bot import create_dispatcher

            calendar = HOSECalendar()
            service = MarketAnalysisService(
                provider=VnstockProvider(source=settings.vnstock_source),
                session_factory=SessionLocal,
                calendar=calendar,
                settings=settings,
                gemini=(
                    GeminiExplainer(
                        api_key=settings.gemini_api_key,
                        model=settings.gemini_model,
                    )
                    if settings.gemini_api_key
                    else None
                ),
                news_provider=RssProvider(),
            )
            scheduler_service = SchedulerService(
                settings=settings,
                analysis_service=service,
                calendar=calendar,
                session_factory=SessionLocal,
                clock=lambda: datetime.now(calendar.timezone),
            )
            scheduler = scheduler_service.build_scheduler()
            scheduler.start()
            bot, dispatcher = create_dispatcher(settings, service)
            polling_task = asyncio.create_task(dispatcher.start_polling(bot))
            logger.info("runtime started with Telegram and scheduler")
        except Exception:
            logger.exception("runtime components failed to start")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN is empty; running health-only mode")
    try:
        yield
    finally:
        if polling_task is not None:
            polling_task.cancel()
            await asyncio.gather(polling_task, return_exceptions=True)
        if bot is not None:
            await bot.session.close()
        if scheduler is not None:
            scheduler.shutdown(wait=False)


app = FastAPI(title="VN Stock Analyst Bot", version="1.5.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
