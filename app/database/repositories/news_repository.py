from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import News
from app.domain.schemas import NewsItem


def upsert_news(session: Session, item: NewsItem) -> News:
    stored = session.scalar(select(News).where(News.url == item.url))
    if stored is None:
        stored = News(
            source=item.source,
            title=item.title,
            summary=item.summary,
            url=item.url,
            published_at=item.published_at,
            content_hash=item.content_hash,
            symbol=item.symbol,
            fetched_at=item.fetched_at,
        )
        session.add(stored)
    else:
        stored.source = item.source
        stored.title = item.title
        stored.summary = item.summary
        stored.published_at = item.published_at
        stored.content_hash = item.content_hash
        stored.fetched_at = item.fetched_at
    session.flush()
    return stored


def recent_news(
    session: Session,
    *,
    since: datetime,
    symbol: str | None = None,
    limit: int = 20,
) -> list[News]:
    query = (
        select(News)
        .where(News.fetched_at >= since)
        .order_by(News.published_at.desc())
        .limit(limit)
    )
    if symbol is not None:
        query = query.where((News.symbol == symbol) | (News.symbol.is_(None)))
    return list(session.scalars(query))
