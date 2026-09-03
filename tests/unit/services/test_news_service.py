from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from app.domain.schemas import NewsItem
from app.services.news_service import NewsService


class FakeNewsProvider:
    def fetch(self, feed_urls: tuple[str, ...]) -> list[NewsItem]:
        return [
            NewsItem(
                source="Example Source",
                title="FPT test headline",
                summary="Test summary",
                url="https://example.test/fpt",
                published_at=datetime(2026, 9, 3, 3, tzinfo=UTC),
                content_hash="a" * 64,
                fetched_at=datetime(2026, 9, 3, 4, tzinfo=UTC),
            )
        ]


class MixedNewsProvider(FakeNewsProvider):
    def fetch(self, feed_urls: tuple[str, ...]) -> list[NewsItem]:
        return [
            *super().fetch(feed_urls),
            NewsItem(
                source="Example Source",
                title="Unrelated steel market headline",
                summary="A company without the requested ticker.",
                url="https://example.test/unrelated",
                published_at=datetime(2026, 9, 3, 3, tzinfo=UTC),
                content_hash="b" * 64,
                fetched_at=datetime(2026, 9, 3, 4, tzinfo=UTC),
            ),
        ]


def _service(provider: object | None = None) -> tuple[NewsService, sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = SimpleNamespace(
        news_feed_urls=("https://example.test/rss",),
        news_lookback_hours=24,
        news_max_items=10,
    )
    return (
        NewsService(
            provider=provider or FakeNewsProvider(), session_factory=factory, settings=settings
        ),
        factory,
    )


def test_news_service_refreshes_and_lists_news_without_analysis_service() -> None:
    service, factory = _service()
    now = datetime(2026, 9, 3, 5, tzinfo=UTC)

    with factory() as session:
        count = service.refresh_sync(session, now=now)

    result = service.list_recent_sync(symbol="FPT", now=now)

    assert count == 1
    assert result.status == "AVAILABLE"
    assert result.items[0].url == "https://example.test/fpt"
    assert result.items[0].title == "FPT test headline"


def test_news_service_returns_empty_when_no_feed_is_configured() -> None:
    service, factory = _service()
    service.settings.news_feed_urls = ()

    with factory() as session:
        assert service.refresh_sync(session, now=datetime.now(UTC)) == 0

    result = service.list_recent_sync(symbol=None, now=datetime(2026, 9, 3, 5, tzinfo=UTC))

    assert result.status == "EMPTY"
    assert result.items == ()


def test_news_report_refreshes_once_when_recent_cache_is_empty() -> None:
    service, factory = _service()
    now = datetime(2026, 9, 3, 5, tzinfo=UTC)

    report = service.report_sync("FPT", now=now)

    assert "FPT test headline" in report
    result = service.list_recent_sync(symbol="FPT", now=now)
    assert result.status == "AVAILABLE"
    assert len(result.items) == 1


def test_symbol_news_filters_unrelated_global_articles() -> None:
    service, _ = _service(MixedNewsProvider())
    now = datetime(2026, 9, 3, 5, tzinfo=UTC)

    report = service.report_sync("FPT", now=now)

    assert "FPT test headline" in report
    assert "Unrelated steel market headline" not in report
