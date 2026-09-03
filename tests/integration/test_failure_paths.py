from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import AnalysisRun, Base
from app.domain.schemas import IndexCandle, MarketCandle
from app.llm.gemini import GeminiError
from app.market.calendar import HOSECalendar
from app.services.analysis_service import AnalysisUnavailable, MarketAnalysisService


class CompleteProvider:
    source = "FAKE"

    def get_ohlcv(self, symbol: str, start: date, end: date, *, is_final: bool = False):
        return [
            MarketCandle(
                symbol=symbol,
                exchange="HOSE",
                trading_date=date(2026, 7, 1) + timedelta(days=i),
                open=Decimal(str(100 + i)),
                high=Decimal(str(102 + i)),
                low=Decimal(str(99 + i)),
                close=Decimal(str(101 + i)),
                volume=1000 + i,
                source="fake",
            )
            for i in range(51)
        ]

    def get_market_index(self, index_code: str, start: date, end: date, *, is_final: bool = False):
        return [
            IndexCandle(
                index_code=index_code,
                trading_date=date(2026, 7, 1) + timedelta(days=i),
                open=Decimal(str(1200 + i)),
                high=Decimal(str(1202 + i)),
                low=Decimal(str(1199 + i)),
                close=Decimal(str(1201 + i)),
                source="fake",
            )
            for i in range(51)
        ]


class FailingProvider:
    def get_ohlcv(self, *args: object, **kwargs: object):
        raise TimeoutError("provider timeout")

    def get_market_index(self, *args: object, **kwargs: object):
        raise TimeoutError("provider timeout")


class FailingGemini:
    model = "test-model"

    def explain(self, **kwargs: object):
        raise GeminiError("timeout")


class FailingChart:
    def render(self, *args: object, **kwargs: object):
        raise RuntimeError("renderer unavailable")


def settings(*, allow_stale_signal: bool) -> SimpleNamespace:
    return SimpleNamespace(
        watchlist_symbols=("FPT",),
        watchlist_exchanges=("HOSE",),
        rule_version="1.5.0",
        volume_ratio_threshold=1.5,
        volume_min_elapsed_minutes=15,
        prompt_version="1.0.0",
        data_schema_version="1.0.0",
        calendar_version="HOSE_2026",
        allow_stale_signal=allow_stale_signal,
        news_feed_urls=(),
    )


def database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def run_at(service: MarketAnalysisService):
    return service.run_sync(
        "FPT",
        now=datetime(2026, 8, 20, 10, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        include_gemini=False,
    )


def test_provider_failure_without_stale_policy_does_not_create_analysis() -> None:
    engine, factory = database()
    service = MarketAnalysisService(
        provider=FailingProvider(),
        session_factory=factory,
        calendar=HOSECalendar(),
        settings=settings(allow_stale_signal=False),
    )

    with pytest.raises(AnalysisUnavailable):
        run_at(service)

    with Session(engine) as db:
        assert db.scalar(select(AnalysisRun)) is None


def test_gemini_and_chart_failures_keep_saved_technical_result() -> None:
    engine, factory = database()
    service = MarketAnalysisService(
        provider=CompleteProvider(),
        session_factory=factory,
        calendar=HOSECalendar(),
        settings=settings(allow_stale_signal=False),
        gemini=FailingGemini(),
        chart_engine=FailingChart(),
    )

    output = run_at(service)

    with Session(engine) as db:
        run = db.scalar(select(AnalysisRun).where(AnalysisRun.id == output.analysis_run_id))
    assert output.rule_result.signal.value != "INSUFFICIENT_DATA"
    assert run is not None
    assert run.llm_response is None
    assert output.chart is None


def test_final_run_rejects_provider_data_without_today() -> None:
    engine, factory = database()
    service = MarketAnalysisService(
        provider=CompleteProvider(),
        session_factory=factory,
        calendar=HOSECalendar(),
        settings=settings(allow_stale_signal=False),
    )

    with pytest.raises(AnalysisUnavailable):
        service.run_sync(
            "FPT",
            now=datetime(2026, 8, 21, 15, 20, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
            is_final=True,
            include_gemini=False,
        )

    with Session(engine) as db:
        assert db.scalar(select(AnalysisRun)) is None
