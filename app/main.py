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
            from app.data.providers.fundamentals import VnstockFundamentalProvider
            from app.data.providers.rss import RssProvider
            from app.data.providers.vnstock import VnstockProvider
            from app.database.connection import SessionLocal
            from app.llm.gemini import GeminiExplainer
            from app.llm.openrouter import HybridReportGenerator, OpenRouterDebateExplainer
            from app.scheduler.scheduler import SchedulerService
            from app.services.analysis_service import MarketAnalysisService
            from app.services.news_service import NewsService
            from app.telegram.bot import configure_bot_commands, create_dispatcher

            calendar = HOSECalendar()
            news_service = NewsService(
                provider=RssProvider(allowed_domains=settings.news_allowed_domains),
                session_factory=SessionLocal,
                settings=settings,
            )
            gemini = (
                GeminiExplainer(
                    api_key=settings.gemini_api_key,
                    model=settings.gemini_model,
                    timeout_seconds=settings.gemini_timeout_seconds,
                )
                if settings.gemini_api_key
                else None
            )
            openrouter = (
                OpenRouterDebateExplainer(
                    api_key=settings.openrouter_api_key,
                    analyst_models=settings.openrouter_analyst_models,
                    judge_model=settings.openrouter_judge_model,
                    fallback_models=settings.openrouter_fallback_models,
                    base_url=settings.openrouter_base_url,
                    timeout_seconds=settings.openrouter_timeout_seconds,
                    max_parallel=settings.openrouter_max_parallel,
                    data_collection=settings.openrouter_data_collection,
                    judge_generator=gemini,
                )
                if settings.openrouter_api_key
                else None
            )
            if settings.llm_provider == "gemini":
                report_generator = gemini
            elif settings.llm_provider == "openrouter":
                report_generator = openrouter
            elif openrouter is not None and gemini is not None:
                report_generator = HybridReportGenerator(primary=openrouter, fallback=gemini)
            else:
                report_generator = openrouter or gemini
            logger.info(
                "AI report backend configured provider=%s openrouter=%s gemini=%s",
                settings.llm_provider,
                openrouter is not None,
                gemini is not None,
            )
            service = MarketAnalysisService(
                provider=VnstockProvider(source=settings.vnstock_source),
                session_factory=SessionLocal,
                calendar=calendar,
                settings=settings,
                fundamental_provider=VnstockFundamentalProvider(source=settings.vnstock_source),
                gemini=gemini,
                report_generator=report_generator,
            )
            scheduler_service = SchedulerService(
                settings=settings,
                analysis_service=service,
                calendar=calendar,
                session_factory=SessionLocal,
                clock=lambda: datetime.now(calendar.timezone),
                news_service=news_service,
            )
            scheduler = scheduler_service.build_scheduler()
            scheduler.start()
            bot, dispatcher = create_dispatcher(settings, service, news_service)
            await configure_bot_commands(bot)
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


app = FastAPI(title="VN Stock Analyst Bot", version="1.6.0", lifespan=lifespan)


@app.api_route("/", methods=["GET", "HEAD"])
def root() -> dict[str, str]:
    return {"status": "ok", "service": "vn-stock-analyst-bot"}


@app.api_route("/health", methods=["GET", "HEAD"])
def health() -> dict[str, str]:
    return {"status": "ok"}
