from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.analysis.analyzer import TechnicalAnalyzer
from app.analysis.rule_engine import RuleEngine
from app.audit.snapshot import build_data_snapshot, canonicalize
from app.chart.chart_engine import ChartEngine
from app.data.providers.base import MarketDataProvider
from app.data.providers.rss import RssProvider
from app.database.repositories.analysis_repository import (
    create_analysis_run,
    latest_analysis_run,
)
from app.database.repositories.candle_repository import (
    finalize_candle,
    finalize_index_candle,
    get_finalized_history,
    get_index_candle_with_metadata,
    get_index_candles,
    get_market_candle_with_metadata,
    get_market_candles,
    upsert_index_candle,
    upsert_intraday_candle,
)
from app.database.repositories.news_repository import recent_news, upsert_news
from app.domain.enums import AnalysisKind, DataFreshness, Risk, Signal
from app.domain.schemas import IndexCandle, IndicatorSnapshot, MarketCandle, NewsItem, RuleResult
from app.llm.gemini import GeminiError, GeminiExplainer, explanation_conflicts_with_signal
from app.telegram.formatter import format_technical_report

logger = logging.getLogger(__name__)
VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class AnalysisUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class AnalysisOutput:
    symbol: str
    text: str
    chart: bytes | None
    indicators: IndicatorSnapshot
    rule_result: RuleResult
    analysis_run_id: int | None


class MarketAnalysisService:
    """Coordinates one analysis while keeping business rules in domain components."""

    def __init__(
        self,
        *,
        provider: MarketDataProvider,
        session_factory: Callable[[], Session],
        calendar: Any,
        settings: Any,
        analyzer: TechnicalAnalyzer | None = None,
        rule_engine: RuleEngine | None = None,
        gemini: GeminiExplainer | None = None,
        chart_engine: ChartEngine | None = None,
        news_provider: RssProvider | None = None,
    ) -> None:
        self.provider = provider
        self.session_factory = session_factory
        self.calendar = calendar
        self.settings = settings
        self.analyzer = analyzer or TechnicalAnalyzer(calendar)
        self.rule_engine = rule_engine or RuleEngine(
            rule_version=settings.rule_version,
            volume_threshold=settings.volume_ratio_threshold,
            volume_min_elapsed_minutes=settings.volume_min_elapsed_minutes,
        )
        self.gemini = gemini
        self.chart_engine = chart_engine or ChartEngine()
        self.news_provider = news_provider

    async def analyze(self, symbol: str) -> Any:
        output = await asyncio.to_thread(self.run_sync, symbol)
        from app.telegram.handlers import TelegramReport

        return TelegramReport(text=output.text, chart=output.chart)

    async def chat(self, message: str) -> str:
        if self.gemini is None:
            return (
                "T chưa bật Gemini để chat tự nhiên. Dùng /analyze FPT, /chart FPT "
                "hoặc /market để sử dụng các chức năng chính."
            )
        try:
            return await asyncio.to_thread(self.gemini.chat, message)
        except GeminiError:
            logger.warning("Gemini chat unavailable", exc_info=True)
            return (
                "Hiện chưa thể trả lời câu chat tự nhiên. Dùng /analyze FPT, "
                "/chart FPT hoặc /market nhé."
            )

    async def chart(self, symbol: str) -> bytes:
        output = await asyncio.to_thread(self.run_sync, symbol, include_gemini=False)
        if output.chart is None:
            raise AnalysisUnavailable("chart was not produced")
        return output.chart

    async def market(self) -> str:
        now = datetime.now(VIETNAM_TZ)
        return self.calendar.describe_session(now)

    def run_sync(
        self,
        symbol: str,
        *,
        now: datetime | None = None,
        is_final: bool = False,
        include_gemini: bool = True,
        force_refresh: bool = False,
    ) -> AnalysisOutput:
        symbol = symbol.strip().upper()
        exchange = self._exchange_for(symbol)
        as_of = now or datetime.now(VIETNAM_TZ)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=VIETNAM_TZ)
        trading_date = as_of.astimezone(VIETNAM_TZ).date()
        start = trading_date - timedelta(days=120)
        freshness = DataFreshness.FRESH
        started_at = perf_counter()

        session = self.session_factory()
        try:
            if not is_final and not force_refresh and self._cache_is_fresh(
                session,
                symbol=symbol,
                exchange=exchange,
                trading_date=trading_date,
                as_of=as_of,
            ):
                market_rows = get_market_candles(session, symbol=symbol, exchange=exchange)
                index_rows = get_index_candles(session, index_code="VNINDEX")
            else:
                try:
                    market_rows = list(
                        self.provider.get_ohlcv(symbol, start, trading_date, is_final=is_final)
                    )
                    index_rows = list(
                        self.provider.get_market_index(
                            "VNINDEX", start, trading_date, is_final=is_final
                        )
                    )
                    if is_final and not any(
                        row.trading_date == trading_date for row in market_rows
                    ):
                        raise AnalysisUnavailable("final market data is not available for today")
                    market_rows = self._mark_historical_final(market_rows, is_final=is_final)
                    index_rows = self._mark_index_historical_final(index_rows, is_final=is_final)
                    self._persist_market(session, market_rows, is_final=is_final)
                    self._persist_index(session, index_rows, is_final=is_final)
                    session.commit()
                except AnalysisUnavailable:
                    session.rollback()
                    raise
                except Exception:
                    session.rollback()
                    if not self.settings.allow_stale_signal:
                        logger.exception("market provider failed and stale fallback is disabled")
                        raise AnalysisUnavailable("market data is unavailable") from None
                    freshness = DataFreshness.STALE_CACHE
                    logger.warning("using stale market cache after provider failure", exc_info=True)
                    market_rows = get_market_candles(session, symbol=symbol, exchange=exchange)
                    index_rows = get_index_candles(session, index_code="VNINDEX")

            current = self._current_candle(market_rows, trading_date)
            if current is None:
                raise AnalysisUnavailable("provider returned no current market candle")
            if (
                not is_final
                and freshness == DataFreshness.FRESH
                and self.calendar.is_regular_trading_time(as_of)
                and current.trading_date != trading_date
            ):
                raise AnalysisUnavailable("provider returned no intraday candle for today")
            history = get_finalized_history(
                session,
                symbol=symbol,
                exchange=exchange,
                before=current.trading_date,
                limit=50,
            )
            stored_index_rows = get_index_candles(
                session,
                index_code="VNINDEX",
                end=current.trading_date,
            )
            index_history = [
                row for row in stored_index_rows if row.trading_date < current.trading_date
            ]
            current_index = next(
                (row for row in stored_index_rows if row.trading_date == current.trading_date),
                None,
            )

            if len(history) >= 50:
                elapsed = (
                    self.calendar.total_regular_trading_minutes(current.trading_date)
                    if is_final
                    else self.calendar.elapsed_trading_minutes(as_of)
                )
                indicators = self.analyzer.analyze(
                    history=history,
                    current=current,
                    index_history=index_history,
                    current_index=current_index,
                    elapsed_minutes=elapsed,
                    as_of=as_of,
                )
            else:
                indicators = self._insufficient_snapshot(current=current, as_of=as_of)

            rule_result = self.rule_engine.evaluate(
                indicators,
                data_freshness=freshness,
                previous_signal=self._previous_signal(
                    session,
                    symbol=symbol,
                    exchange=exchange,
                ),
            )
            if freshness == DataFreshness.STALE_CACHE and not self.settings.allow_stale_signal:
                rule_result = self._stale_disallowed_result(self.settings.rule_version)

            try:
                news = self._collect_news(session, symbol=symbol, as_of=as_of)
            except Exception:
                session.rollback()
                logger.warning(
                    "news context unavailable; continuing technical analysis",
                    exc_info=True,
                )
                news = []
            data_snapshot = build_data_snapshot(
                market_candles=[*history, current],
                index_candles=[*index_history, *([current_index] if current_index else [])],
                news=[self._news_snapshot(item) for item in news],
            )
            provenance = {
                "provider": type(self.provider).__name__,
                "provider_source": getattr(self.provider, "source", "unknown"),
                "provider_timestamp": current.provider_timestamp,
                "fetched_at": as_of,
                "data_freshness": freshness.value,
                "price_basis": indicators.price_basis.value,
                "calendar_version": self.settings.calendar_version,
                "exchange": exchange,
                "news_count": len(news),
                "index_provider_timestamp": (
                    current_index.provider_timestamp if current_index else None
                ),
            }
            run = create_analysis_run(
                session,
                symbol=symbol,
                exchange=exchange,
                trading_date=current.trading_date,
                as_of=as_of,
                data_snapshot=data_snapshot,
                indicator_snapshot=indicators.model_dump(mode="json"),
                rule_result=rule_result.model_dump(mode="json"),
                data_provenance=canonicalize(provenance),
                prompt_version=self.settings.prompt_version,
                rule_version=self.settings.rule_version,
                data_schema_version=self.settings.data_schema_version,
                analysis_kind=AnalysisKind.FINAL.value if is_final else AnalysisKind.INTRADAY.value,
                is_final=is_final,
            )
            session.commit()

            gemini_explanation = None
            explanation_conflict = False
            if include_gemini and self.gemini is not None:
                try:
                    gemini_explanation = self.gemini.explain(
                        quantitative_context=indicators.model_dump(mode="json"),
                        event_context=[self._news_context(item) for item in news],
                        decision_context=rule_result.model_dump(mode="json"),
                    )
                    explanation_conflict = explanation_conflicts_with_signal(
                        gemini_explanation, rule_result.signal
                    )
                    run.llm_response = gemini_explanation.model_dump(mode="json")
                    run.model = self.gemini.model
                    run.explanation_conflict = explanation_conflict
                    session.commit()
                except GeminiError:
                    session.rollback()
                    logger.warning("Gemini unavailable; keeping technical report", exc_info=True)

            chart = None
            try:
                chart = self.chart_engine.render(
                    [*history, current],
                    symbol=symbol,
                    as_of=as_of,
                    is_final=is_final,
                )
            except Exception:
                logger.warning("chart unavailable; keeping technical report", exc_info=True)

            text = format_technical_report(
                symbol=symbol,
                as_of=as_of,
                analysis_kind=AnalysisKind.FINAL if is_final else AnalysisKind.INTRADAY,
                is_final=is_final,
                indicators=indicators,
                rule_result=rule_result,
                data_freshness=freshness,
                gemini=gemini_explanation,
                news=news,
            )
            return AnalysisOutput(
                symbol=symbol,
                text=text,
                chart=chart,
                indicators=indicators,
                rule_result=rule_result,
                analysis_run_id=run.id,
            )
        finally:
            session.close()
            logger.info(
                "analysis finished symbol=%s duration_ms=%.1f",
                symbol,
                (perf_counter() - started_at) * 1000,
            )

    def _exchange_for(self, symbol: str) -> str:
        try:
            index = self.settings.watchlist_symbols.index(symbol)
        except ValueError:
            logger.info("symbol=%s is outside watchlist; using default HOSE exchange", symbol)
            return "HOSE"
        return self.settings.watchlist_exchanges[index]

    def _cache_is_fresh(
        self,
        session: Session,
        *,
        symbol: str,
        exchange: str,
        trading_date: date,
        as_of: datetime,
    ) -> bool:
        max_age_minutes = getattr(self.settings, "data_cache_max_age_minutes", 0)
        if max_age_minutes <= 0:
            return False
        market = get_market_candle_with_metadata(
            session,
            symbol=symbol,
            exchange=exchange,
            trading_date=trading_date,
        )
        index = get_index_candle_with_metadata(
            session,
            index_code="VNINDEX",
            trading_date=trading_date,
        )
        if market is None or index is None:
            return False
        return self._age_minutes(as_of, market[1]) <= max_age_minutes and self._age_minutes(
            as_of, index[1]
        ) <= max_age_minutes

    @staticmethod
    def _age_minutes(as_of: datetime, updated_at: object) -> float:
        if not isinstance(updated_at, datetime):
            return float("inf")
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=VIETNAM_TZ)
        return max(0.0, (as_of - updated_at.astimezone(as_of.tzinfo)).total_seconds() / 60)

    @staticmethod
    def _mark_historical_final(
        rows: Sequence[MarketCandle], *, is_final: bool
    ) -> list[MarketCandle]:
        if not rows:
            return []
        latest = max(row.trading_date for row in rows)
        return [
            row.model_copy(update={"is_final": is_final or row.trading_date < latest})
            for row in rows
        ]

    @staticmethod
    def _mark_index_historical_final(
        rows: Sequence[IndexCandle], *, is_final: bool
    ) -> list[IndexCandle]:
        if not rows:
            return []
        latest = max(row.trading_date for row in rows)
        return [
            row.model_copy(update={"is_final": is_final or row.trading_date < latest})
            for row in rows
        ]

    @staticmethod
    def _persist_market(session: Session, rows: Sequence[MarketCandle], *, is_final: bool) -> None:
        for row in rows:
            if is_final or row.is_final:
                finalize_candle(session, row)
            else:
                upsert_intraday_candle(session, row)

    @staticmethod
    def _persist_index(session: Session, rows: Sequence[IndexCandle], *, is_final: bool) -> None:
        for row in rows:
            if is_final or row.is_final:
                finalize_index_candle(session, row)
            else:
                upsert_index_candle(session, row)

    @staticmethod
    def _current_candle(rows: Sequence[MarketCandle], trading_date: date) -> MarketCandle | None:
        candidates = [row for row in rows if row.trading_date <= trading_date]
        return max(candidates, key=lambda row: row.trading_date) if candidates else None

    @staticmethod
    def _insufficient_snapshot(*, current: MarketCandle, as_of: datetime) -> IndicatorSnapshot:
        return IndicatorSnapshot(
            price=current.close,
            elapsed_trading_minutes=0,
            relative_return=None,
            as_of=as_of,
            is_final=current.is_final,
        )

    @staticmethod
    def _stale_disallowed_result(rule_version: str) -> RuleResult:
        return RuleResult(
            score=0,
            max_score=0,
            signal=Signal.INSUFFICIENT_DATA,
            confidence_raw=None,
            reasons=[],
            risk=Risk.LOW,
            risk_points=0,
            risk_reasons=["stale_cache_disallowed"],
            rule_version=rule_version,
        )

    def _collect_news(self, session: Session, *, symbol: str, as_of: datetime) -> list[Any]:
        self.refresh_news_sync(session, now=as_of)
        since = as_of - timedelta(days=1)
        return list(recent_news(session, since=since, symbol=symbol))

    @staticmethod
    def _previous_signal(session: Session, *, symbol: str, exchange: str) -> Signal | None:
        previous = latest_analysis_run(session, symbol=symbol, exchange=exchange)
        if previous is None:
            return None
        try:
            return Signal(previous.rule_signal)
        except ValueError:
            return None

    @staticmethod
    def _news_snapshot(item: Any) -> dict[str, Any]:
        return {
            "id": item.id,
            "source": item.source,
            "title": item.title,
            "summary": item.summary,
            "url": item.url,
            "published_at": item.published_at,
            "content_hash": item.content_hash,
            "fetched_at": item.fetched_at,
            "symbol": item.symbol,
        }

    @staticmethod
    def _news_context(item: Any) -> dict[str, Any]:
        return NewsItem(
            source=item.source,
            title=item.title,
            summary=item.summary,
            url=item.url,
            published_at=item.published_at,
            content_hash=item.content_hash,
            symbol=item.symbol,
            fetched_at=item.fetched_at,
        ).model_dump(mode="json")

    def refresh_news_sync(self, session: Session, *, now: datetime) -> int:
        if self.news_provider is None or not self.settings.news_feed_urls:
            return 0
        count = 0
        for item in self.news_provider.fetch(self.settings.news_feed_urls):
            upsert_news(session, item)
            count += 1
        session.commit()
        return count
