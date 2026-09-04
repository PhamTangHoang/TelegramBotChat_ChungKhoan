from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import AnalysisRun, Base
from app.domain.schemas import IndexCandle, MarketCandle
from app.market.calendar import HOSECalendar
from app.services.analysis_service import MarketAnalysisService


class FakeProvider:
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


def test_provider_to_audit_pipeline_persists_reconstructable_result() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = SimpleNamespace(
        watchlist_symbols=("FPT",),
        watchlist_exchanges=("HOSE",),
        rule_version="1.5.0",
        volume_ratio_threshold=1.5,
        volume_min_elapsed_minutes=15,
        prompt_version="1.0.0",
        data_schema_version="1.0.0",
        calendar_version="HOSE_2026",
        allow_stale_signal=False,
        news_feed_urls=(),
    )
    service = MarketAnalysisService(
        provider=FakeProvider(),
        session_factory=factory,
        calendar=HOSECalendar(),
        settings=settings,
    )

    output = service.run_sync(
        "FPT",
        now=datetime(2026, 8, 20, 10, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
    )

    with Session(engine) as db:
        run = db.scalar(select(AnalysisRun).where(AnalysisRun.id == output.analysis_run_id))

    assert output.rule_result.signal.value in {"BULLISH", "NEUTRAL", "BEARISH"}
    assert run is not None
    assert len(run.input_hash) == 64
    assert run.data_provenance["provider_source"] == "FAKE"
    assert run.rule_result["signal"] == output.rule_result.signal.value
    assert len(output.pp10_result.criteria) == 16
    assert run.rule_result["pp10"]["version"] == "2.0.0"
