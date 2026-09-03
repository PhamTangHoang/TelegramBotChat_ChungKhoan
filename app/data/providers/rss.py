from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any

from app.domain.schemas import NewsItem

logger = logging.getLogger(__name__)


class NewsProviderError(RuntimeError):
    pass


class RssProvider:
    def __init__(
        self,
        *,
        parser: Callable[[str], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._parser = parser
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def parser(self) -> Callable[[str], Any]:
        if self._parser is None:
            try:
                import feedparser

                self._parser = feedparser.parse
            except Exception as exc:
                raise NewsProviderError("feedparser is not available") from exc
        return self._parser

    def fetch(self, feed_urls: Iterable[str]) -> list[NewsItem]:
        fetched_at = self.clock()
        items: list[NewsItem] = []
        for feed_url in feed_urls:
            try:
                parsed = self.parser(feed_url)
                source = str(getattr(parsed.feed, "title", "") or feed_url)[:128]
                for entry in getattr(parsed, "entries", []):
                    title = str(entry.get("title", "")).strip()
                    url = str(entry.get("link", "")).strip()
                    if not title or not url:
                        continue
                    summary = str(entry.get("summary", "")).strip() or None
                    published_at = _published_at(entry)
                    content_hash = hashlib.sha256(
                        f"{title}\n{summary or ''}\n{url}".encode("utf-8")
                    ).hexdigest()
                    items.append(
                        NewsItem(
                            source=source,
                            title=title,
                            summary=summary,
                            url=url,
                            published_at=published_at,
                            content_hash=content_hash,
                            fetched_at=fetched_at,
                        )
                    )
            except Exception:
                logger.exception("RSS feed failed: %s", feed_url)
        return items


def _published_at(entry: Any) -> datetime | None:
    struct_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if struct_time is None:
        return None
    return datetime(*struct_time[:6], tzinfo=timezone.utc)
