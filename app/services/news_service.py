from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.data.providers.rss import RssProvider
from app.database.repositories.news_repository import recent_news, upsert_news
from app.telegram.formatter import format_news_report

VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewsRecord:
    source: str
    title: str
    summary: str | None
    url: str
    published_at: datetime | None
    fetched_at: datetime
    symbol: str | None = None


@dataclass(frozen=True)
class NewsQueryResult:
    items: tuple[NewsRecord, ...]
    status: str


class NewsService:
    """Owns RSS refresh and read-only Telegram news reports."""

    def __init__(
        self,
        *,
        provider: RssProvider,
        session_factory: Callable[[], Session],
        settings: Any,
    ) -> None:
        self.provider = provider
        self.session_factory = session_factory
        self.settings = settings

    def refresh_sync(self, session: Session, *, now: datetime) -> int:
        del now  # Provider timestamps are authoritative for fetched_at.
        feed_urls = tuple(getattr(self.settings, "news_feed_urls", ()))
        if not feed_urls:
            return 0
        count = 0
        for item in self.provider.fetch(feed_urls):
            upsert_news(session, item)
            count += 1
        session.commit()
        return count

    def list_recent_sync(
        self,
        *,
        symbol: str | None,
        now: datetime,
    ) -> NewsQueryResult:
        lookback_hours = int(getattr(self.settings, "news_lookback_hours", 24))
        max_items = int(getattr(self.settings, "news_max_items", 10))
        since = now - timedelta(hours=lookback_hours)
        session = self.session_factory()
        try:
            items = list(recent_news(session, since=since, symbol=symbol, limit=max_items))
            if symbol is not None:
                items = [item for item in items if _mentions_symbol(item, symbol)]
            status = "AVAILABLE" if items else "EMPTY"
            return NewsQueryResult(
                items=tuple(_to_record(item) for item in items),
                status=status,
            )
        finally:
            session.close()

    def report_sync(self, symbol: str | None = None, *, now: datetime | None = None) -> str:
        as_of = now or datetime.now(VIETNAM_TZ)
        result = self.list_recent_sync(symbol=symbol, now=as_of)
        if result.status == "EMPTY" and tuple(getattr(self.settings, "news_feed_urls", ())):
            session = self.session_factory()
            try:
                self.refresh_sync(session, now=as_of)
            except Exception:
                logger.warning("on-demand news refresh failed", exc_info=True)
            finally:
                session.close()
            result = self.list_recent_sync(symbol=symbol, now=as_of)
        return format_news_report(
            symbol=symbol,
            as_of=as_of,
            items=result.items,
            status=result.status,
        )

    async def report(self, symbol: str | None = None) -> str:
        return await asyncio.to_thread(self.report_sync, symbol)


def _to_record(item: Any) -> NewsRecord:
    return NewsRecord(
        source=item.source,
        title=item.title,
        summary=item.summary,
        url=item.url,
        published_at=item.published_at,
        fetched_at=item.fetched_at,
        symbol=item.symbol,
    )


def _mentions_symbol(item: Any, symbol: str) -> bool:
    if getattr(item, "symbol", None) and item.symbol.strip().upper() == symbol:
        return True
    content = " ".join(
        str(getattr(item, field, "") or "")
        for field in ("title", "summary")
    ).upper()
    return re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", content) is not None
