from datetime import datetime, timezone
from types import SimpleNamespace

from app.data.providers.rss import RssProvider


def test_rss_provider_normalizes_entries_and_hashes_content() -> None:
    parsed = SimpleNamespace(
        feed=SimpleNamespace(title="Example Source"),
        entries=[
            {
                "title": " FPT publishes results ",
                "summary": "Revenue grew.",
                "link": "https://example.test/fpt",
                "published_parsed": (2026, 9, 3, 3, 0, 0, 0, 0, 0),
            }
        ],
    )
    provider = RssProvider(
        parser=lambda _: parsed,
        clock=lambda: datetime(2026, 9, 3, 4, tzinfo=timezone.utc),
    )

    result = provider.fetch(["https://example.test/rss"])

    assert len(result) == 1
    assert result[0].source == "Example Source"
    assert result[0].title == "FPT publishes results"
    assert result[0].published_at == datetime(2026, 9, 3, 3, tzinfo=timezone.utc)
    assert len(result[0].content_hash) == 64


def test_rss_provider_sanitizes_html_summary_before_storage() -> None:
    parsed = SimpleNamespace(
        feed=SimpleNamespace(title="Example Source"),
        entries=[
            {
                "title": "<b>FPT</b> publishes results",
                "summary": "<div>Revenue grew &amp; margins improved.<br>Read more</div>",
                "link": "https://example.test/fpt",
            }
        ],
    )
    provider = RssProvider(parser=lambda _: parsed)

    result = provider.fetch(["https://example.test/rss"])

    assert result[0].title == "FPT publishes results"
    assert result[0].summary == "Revenue grew & margins improved.\nRead more"


def test_rss_provider_skips_invalid_article_links() -> None:
    parsed = SimpleNamespace(
        feed=SimpleNamespace(title="Example Source"),
        entries=[
            {"title": "Bad", "link": "javascript:alert(1)"},
            {"title": "Good", "link": "https://example.test/good"},
        ],
    )
    provider = RssProvider(parser=lambda _: parsed)

    result = provider.fetch(["https://example.test/rss"])

    assert [item.url for item in result] == ["https://example.test/good"]


def test_rss_provider_skips_invalid_feed_urls_without_calling_parser() -> None:
    calls: list[str] = []

    def parser(url: str):
        calls.append(url)
        return SimpleNamespace(feed=SimpleNamespace(title="Example"), entries=[])

    provider = RssProvider(parser=parser)

    assert provider.fetch(["ftp://example.test/rss", "not-a-url"]) == []
    assert calls == []
