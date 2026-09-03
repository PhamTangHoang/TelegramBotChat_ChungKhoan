from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

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
        allowed_domains: Iterable[str] = (),
    ) -> None:
        self._parser = parser
        self.clock = clock or (lambda: datetime.now(UTC))
        self.allowed_domains = {
            domain.strip().lower().lstrip(".")
            for domain in allowed_domains
            if domain.strip()
        }

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
        seen_urls: set[str] = set()
        for feed_url in feed_urls:
            normalized_feed_url = _normalize_url(feed_url)
            if normalized_feed_url is None or not self._domain_allowed(normalized_feed_url):
                logger.warning("RSS feed skipped invalid or disallowed URL: %s", feed_url)
                continue
            try:
                parsed = self.parser(normalized_feed_url)
                source = str(getattr(parsed.feed, "title", "") or normalized_feed_url)[:128]
                for entry in getattr(parsed, "entries", []):
                    title = str(entry.get("title", "")).strip()
                    url = _normalize_url(str(entry.get("link", "")).strip())
                    if not title or url is None or not self._domain_allowed(url):
                        if title and url is None:
                            logger.warning("RSS entry skipped without a valid link: %s", title)
                        continue
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    summary = str(entry.get("summary", "")).strip() or None
                    published_at = _published_at(entry)
                    content_hash = hashlib.sha256(
                        f"{title}\n{summary or ''}\n{url}".encode()
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

    def _domain_allowed(self, url: str) -> bool:
        if not self.allowed_domains:
            return True
        hostname = (urlsplit(url).hostname or "").lower()
        return any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in self.allowed_domains
        )


def _normalize_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            parsed.path,
            parsed.query,
            "",
        )
    )


def _published_at(entry: Any) -> datetime | None:
    struct_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if struct_time is None:
        return None
    return datetime(*struct_time[:6], tzinfo=UTC)
