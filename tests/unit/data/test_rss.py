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
