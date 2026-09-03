from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, time
from typing import Any

from app.database.repositories.scheduler_repository import (
    finish_scheduler_run,
    start_scheduler_run,
)
from app.services.analysis_service import AnalysisUnavailable, MarketAnalysisService

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(
        self,
        *,
        settings: Any,
        analysis_service: MarketAnalysisService,
        calendar: Any,
        session_factory: Callable[[], Any],
        clock: Callable[[], datetime],
    ) -> None:
        self.settings = settings
        self.analysis_service = analysis_service
        self.calendar = calendar
        self.session_factory = session_factory
        self.clock = clock

    def market_hourly(self, *, scheduled_at: datetime | None = None) -> str:
        now = self.clock()
        run, session = self._start("market_hourly", scheduled_at or now, now)
        try:
            trading_time = self.calendar.is_regular_trading_time(now)
            if not self.calendar.is_trading_day(now.date()) or not trading_time:
                self._finish(session, run, "SKIPPED", now)
                return "SKIPPED"
            for symbol in self.settings.watchlist_symbols:
                self.analysis_service.run_sync(symbol, now=now, force_refresh=True)
            self._finish(session, run, "SUCCESS", self.clock())
            return "SUCCESS"
        except Exception as exc:
            logger.exception("market_hourly failed")
            self._finish(session, run, "FAILED", self.clock(), error=str(exc))
            return "FAILED"
        finally:
            session.close()

    def eod_settle(self, *, scheduled_at: datetime | None = None) -> str:
        now = self.clock()
        run, session = self._start("eod_settle", scheduled_at or now, now)
        try:
            in_settlement_window = time(15, 15) <= now.time() < time(15, 45)
            if not self.calendar.is_trading_day(now.date()) or not in_settlement_window:
                self._finish(session, run, "SKIPPED", now)
                return "SKIPPED"
            failures = 0
            for symbol in self.settings.watchlist_symbols:
                try:
                    self.analysis_service.run_sync(symbol, now=now, is_final=True)
                except AnalysisUnavailable:
                    failures += 1
                    logger.warning("EOD final data unavailable for %s", symbol, exc_info=True)
            status = "FAILED" if failures else "SUCCESS"
            self._finish(
                session,
                run,
                status,
                self.clock(),
                error=f"{failures} symbol(s) unavailable" if failures else None,
            )
            return status
        except Exception as exc:
            logger.exception("eod_settle failed")
            self._finish(session, run, "FAILED", self.clock(), error=str(exc))
            return "FAILED"
        finally:
            session.close()

    def news_refresh(self, *, scheduled_at: datetime | None = None) -> str:
        now = self.clock()
        run, session = self._start("news_refresh", scheduled_at or now, now)
        try:
            self.analysis_service.refresh_news_sync(session, now=now)
            self._finish(session, run, "SUCCESS", self.clock())
            return "SUCCESS"
        except Exception as exc:
            logger.exception("news_refresh failed")
            self._finish(session, run, "FAILED", self.clock(), error=str(exc))
            return "FAILED"
        finally:
            session.close()

    def build_scheduler(self) -> Any:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError as exc:
            raise RuntimeError("APScheduler is required to build the scheduler") from exc

        scheduler = BackgroundScheduler(timezone=self.settings.telegram_timezone)
        scheduler.add_job(
            self.market_hourly,
            "interval",
            minutes=self.settings.market_job_interval_minutes,
            id="market_hourly",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
        scheduler.add_job(
            self.news_refresh,
            "interval",
            minutes=self.settings.news_job_interval_minutes,
            id="news_refresh",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=900,
        )
        hour, minute = self.settings.eod_settle_job_time.split(":")
        scheduler.add_job(
            self.eod_settle,
            CronTrigger(
                hour=int(hour),
                minute=int(minute),
                timezone=self.settings.telegram_timezone,
            ),
            id="eod_settle",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=1800,
        )
        return scheduler

    def _start(self, job_name: str, scheduled_at: datetime, started_at: datetime):
        session = self.session_factory()
        run = start_scheduler_run(
            session,
            job_name=job_name,
            scheduled_at=scheduled_at,
            started_at=started_at,
        )
        session.commit()
        return run, session

    @staticmethod
    def _finish(
        session: Any,
        run: Any,
        status: str,
        finished_at: datetime,
        error: str | None = None,
    ) -> None:
        finish_scheduler_run(
            session,
            run,
            status=status,
            finished_at=finished_at,
            error=error,
        )
        session.commit()
