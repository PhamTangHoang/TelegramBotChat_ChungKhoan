from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.market.calendar import HOSECalendar
from app.scheduler.scheduler import SchedulerService


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.closed = False

    def add(self, item: object) -> None:
        pass

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


class FakeAnalysis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def run_sync(
        self,
        symbol: str,
        *,
        now: datetime,
        is_final: bool = False,
        force_refresh: bool = False,
    ):
        self.calls.append((symbol, is_final))

    def refresh_news_sync(self, session: object, *, now: datetime) -> int:
        return 0


def settings() -> SimpleNamespace:
    return SimpleNamespace(
        watchlist_symbols=("FPT", "VNM"),
        telegram_timezone="Asia/Ho_Chi_Minh",
        market_job_interval_minutes=60,
        news_job_interval_minutes=45,
        eod_settle_job_time="15:20",
    )


def test_market_job_skips_outside_regular_session() -> None:
    now = datetime(2026, 9, 3, 8, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    analysis = FakeAnalysis()
    scheduler = SchedulerService(
        settings=settings(),
        analysis_service=analysis,
        calendar=HOSECalendar(),
        session_factory=FakeSession,
        clock=lambda: now,
    )

    assert scheduler.market_hourly() == "SKIPPED"
    assert analysis.calls == []


def test_eod_job_runs_each_watchlist_symbol_as_final() -> None:
    now = datetime(2026, 9, 3, 15, 20, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    analysis = FakeAnalysis()
    scheduler = SchedulerService(
        settings=settings(),
        analysis_service=analysis,
        calendar=HOSECalendar(),
        session_factory=FakeSession,
        clock=lambda: now,
    )

    assert scheduler.eod_settle() == "SUCCESS"
    assert analysis.calls == [("FPT", True), ("VNM", True)]
