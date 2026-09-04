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
from app.analysis.indicators import sma
from app.analysis.pp10 import PP10Evaluator
from app.analysis.rule_engine import RuleEngine
from app.audit.snapshot import build_data_snapshot, canonicalize
from app.chart.chart_engine import ChartEngine
from app.data.errors import NoMarketDataError
from app.data.providers.base import MarketDataProvider
from app.database.models import AnalysisRun
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
from app.domain.enums import AnalysisKind, DataFreshness, Risk, Signal
from app.domain.schemas import IndexCandle, IndicatorSnapshot, MarketCandle, PP10Result, RuleResult
from app.llm.gemini import GeminiError, GeminiExplainer, explanation_conflicts_with_signal
from app.llm.openrouter import OpenRouterError
from app.telegram.formatter import (
    format_ai_pp10_report,
    format_gemini_explanation,
    format_technical_report,
)

logger = logging.getLogger(__name__)
VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class AnalysisUnavailable(RuntimeError):
    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message


@dataclass(frozen=True)
class AnalysisOutput:
    symbol: str
    text: str
    chart: bytes | None
    indicators: IndicatorSnapshot
    rule_result: RuleResult
    pp10_result: PP10Result
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
        pp10_evaluator: PP10Evaluator | None = None,
        fundamental_provider: Any | None = None,
        gemini: GeminiExplainer | None = None,
        report_generator: Any | None = None,
        chart_engine: ChartEngine | None = None,
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
        self.pp10_evaluator = pp10_evaluator or PP10Evaluator(
            version=getattr(settings, "pp10_version", "2.0.0")
        )
        self.fundamental_provider = fundamental_provider
        self.gemini = gemini
        self.report_generator = report_generator or gemini
        self.chart_engine = chart_engine or ChartEngine()

    async def analyze(self, symbol: str) -> Any:
        from app.telegram.handlers import TelegramReport

        if self.report_generator is None:
            raise AnalysisUnavailable(
                "An AI report generator is required for AI-only analysis",
                user_message=(
                    "Lệnh /analyze cần GEMINI_API_KEY hoặc OPENROUTER_API_KEY vì báo cáo được "
                    "tạo trực tiếp "
                    "bởi AI. Dùng /chart SYMBOL để xem biểu đồ dữ liệu."
                ),
            )

        normalized_symbol = symbol.strip().upper()
        analysis_time = datetime.now(VIETNAM_TZ)
        analysis_date = analysis_time.strftime("%Y-%m-%d %H:%M:%S%z")
        report_generator_name = (
            getattr(self.report_generator, "display_name", None)
            or getattr(self.report_generator, "model", None)
            or type(self.report_generator).__name__
        )
        logger.info(
            "AI-only analysis started symbol=%s engine=%s",
            normalized_symbol,
            report_generator_name,
        )
        try:
            quantitative_context, latest_candle = await asyncio.to_thread(
                self._fetch_ai_ohlcv,
                normalized_symbol,
                analysis_time,
            )
            logger.info(
                "AI-only OHLCV ready symbol=%s candles=%s latest_date=%s",
                normalized_symbol,
                len(quantitative_context.get("ohlcv_daily", [])),
                latest_candle.trading_date,
            )
            logger.info("AI-only report generation started symbol=%s", normalized_symbol)
            report = await asyncio.to_thread(
                self.report_generator.generate_pp10_report,
                symbol=normalized_symbol,
                analysis_date=analysis_date,
                quantitative_context=quantitative_context,
            )
            logger.info("AI-only report generation completed symbol=%s", normalized_symbol)
        except NoMarketDataError as exc:
            logger.warning("AI-only OHLCV data unavailable for symbol=%s", normalized_symbol)
            raise AnalysisUnavailable(
                "OHLCV data is unavailable for AI analysis",
                user_message=f"Mã {normalized_symbol} hiện không có dữ liệu OHLCV.",
            ) from exc
        except (GeminiError, OpenRouterError) as exc:
            logger.warning(
                "AI-only PP10 analysis failed for symbol=%s error=%s",
                normalized_symbol,
                exc,
                exc_info=True,
            )
            raise AnalysisUnavailable(
                "AI-only PP10 analysis is unavailable",
                user_message=(
                    "AI chưa trả được báo cáo lúc này. Thử lại sau hoặc dùng "
                    "/chart SYMBOL để xem biểu đồ."
                ),
            ) from exc
        except Exception as exc:
            logger.exception("AI-only analysis pipeline failed for symbol=%s", normalized_symbol)
            raise AnalysisUnavailable(
                "AI-only analysis pipeline is unavailable",
                user_message="Không thể lấy dữ liệu OHLCV hoặc tạo báo cáo AI lúc này.",
            ) from exc

        return TelegramReport(
            text=format_ai_pp10_report(
                symbol=normalized_symbol,
                as_of=analysis_time,
                report=report,
                latest_price=latest_candle.close,
                data_source=getattr(self.provider, "source", "market provider"),
                ai_engine=(
                    getattr(self.report_generator, "display_name", None)
                    or getattr(self.report_generator, "model", None)
                ),
            ),
            chart=None,
        )

    def _fetch_ai_ohlcv(
        self, symbol: str, as_of: datetime
    ) -> tuple[dict[str, Any], MarketCandle]:
        try:
            symbol_index = self.settings.watchlist_symbols.index(symbol)
            exchange = self.settings.watchlist_exchanges[symbol_index]
        except (AttributeError, IndexError, ValueError):
            exchange = "HOSE"

        rows = list(
            self.provider.get_ohlcv(
                symbol,
                as_of.date() - timedelta(days=400),
                as_of.date(),
                exchange=exchange,
                is_final=False,
            )
        )
        rows = sorted(
            (row for row in rows if row.trading_date <= as_of.date()),
            key=lambda row: row.trading_date,
        )
        if not rows:
            raise NoMarketDataError(f"No market data for {symbol}")

        latest_candle = rows[-1]
        context = {
            "symbol": symbol,
            "exchange": exchange,
            "as_of": as_of,
            "data_source": getattr(self.provider, "source", type(self.provider).__name__),
            "price_unit": (
                "provider trả giá theo nghìn VND; khi hiển thị, quy đổi thành VND/cổ phiếu"
            ),
            "latest_candle": self._ai_candle_payload(latest_candle),
            "ohlcv_daily": [self._ai_candle_payload(row) for row in rows[-220:]],
            "not_provided": [
                "VN-Index",
                "RS Rating toàn universe",
                "fundamentals và valuation",
                "khối ngoại/tự doanh",
                "news",
            ],
        }
        return canonicalize(context), latest_candle

    @staticmethod
    def _ai_candle_payload(candle: MarketCandle) -> dict[str, Any]:
        return {
            "trading_date": candle.trading_date,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "is_final": candle.is_final,
        }

    async def _gemini_follow_up(self, output: AnalysisOutput) -> str | None:
        try:
            explanation = await asyncio.to_thread(self._explain_output_sync, output)
        except GeminiError:
            logger.warning("Gemini follow-up unavailable; technical report was sent", exc_info=True)
            return None
        return format_gemini_explanation(explanation)

    def _explain_output_sync(self, output: AnalysisOutput) -> Any:
        if self.gemini is None:
            return None
        decision_context = output.rule_result.model_dump(mode="json")
        decision_context["pp10"] = output.pp10_result.model_dump(mode="json")
        explanation = self.gemini.explain(
            quantitative_context=output.indicators.model_dump(mode="json"),
            event_context=[],
            decision_context=decision_context,
        )
        if output.analysis_run_id is None:
            return explanation

        session = self.session_factory()
        try:
            run = session.get(AnalysisRun, output.analysis_run_id)
            if run is not None:
                run.llm_response = explanation.model_dump(mode="json")
                run.model = self.gemini.model
                run.explanation_conflict = explanation_conflicts_with_signal(
                    explanation, output.rule_result.signal
                )
                session.commit()
        except Exception:
            session.rollback()
            logger.exception("Could not persist Gemini follow-up")
        finally:
            session.close()
        return explanation

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
        return await asyncio.to_thread(self.market_sync)

    def market_sync(self, *, now: datetime | None = None) -> str:
        as_of = now or datetime.now(VIETNAM_TZ)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=VIETNAM_TZ)
        as_of = as_of.astimezone(VIETNAM_TZ)
        session_report = self.calendar.describe_session(as_of)
        try:
            rows = list(
                self.provider.get_market_index(
                    "VNINDEX",
                    as_of.date() - timedelta(days=400),
                    as_of.date(),
                    is_final=not self.calendar.is_regular_trading_time(as_of),
                )
            )
        except Exception:
            logger.warning("market snapshot unavailable", exc_info=True)
            return f"{session_report}\n\nVN-Index: chưa lấy được dữ liệu hiện tại."
        if not rows:
            return f"{session_report}\n\nVN-Index: chưa có dữ liệu."

        rows.sort(key=lambda row: row.trading_date)
        closes = [float(row.close) for row in rows]
        latest = rows[-1]
        ma20 = sma(closes, 20)[-1]
        ma50 = sma(closes, 50)[-1]
        if ma20 is None or ma50 is None:
            trend = "Chưa đủ lịch sử để xác định"
        elif closes[-1] > ma20 > ma50:
            trend = "Tăng"
        elif closes[-1] < ma20 < ma50:
            trend = "Giảm"
        else:
            trend = "Chưa xác nhận"
        latest_line = (
            f"VN-Index — Phiên gần nhất ({latest.trading_date.isoformat()}): "
            f"{latest.close:.2f}"
        )
        return "\n".join(
            (
                session_report,
                "",
                latest_line,
                f"MA20: {ma20:.2f}" if ma20 is not None else "MA20: N/A",
                f"MA50: {ma50:.2f}" if ma50 is not None else "MA50: N/A",
                f"Xu hướng: {trend}",
                "Lưu ý: snapshot theo dữ liệu provider, không phải realtime.",
            )
        )

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
        start = trading_date - timedelta(days=400)
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
                    if callable(getattr(self.provider, "resolve_exchange", None)):
                        market_rows = list(
                            self.provider.get_ohlcv(
                                symbol,
                                start,
                                trading_date,
                                exchange=exchange,
                                is_final=is_final,
                            )
                        )
                    else:
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
                except NoMarketDataError:
                    session.rollback()
                    raise AnalysisUnavailable(
                        f"No market data for {symbol}",
                        user_message=f"Mã {symbol} hiện không có dữ liệu giá từ nguồn dữ liệu.",
                    ) from None
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
                limit=260,
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
            indicators = self._add_fundamentals(indicators, symbol)

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
            pp10_result = self.pp10_evaluator.evaluate(indicators)
            rule_result_snapshot = rule_result.model_dump(mode="json")
            rule_result_snapshot["pp10"] = pp10_result.model_dump(mode="json")

            data_snapshot = build_data_snapshot(
                market_candles=[*history, current],
                index_candles=[*index_history, *([current_index] if current_index else [])],
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
                rule_result=rule_result_snapshot,
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
                        event_context=[],
                        decision_context=rule_result_snapshot,
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
                pp10=pp10_result,
            )
            return AnalysisOutput(
                symbol=symbol,
                text=text,
                chart=chart,
                indicators=indicators,
                rule_result=rule_result,
                pp10_result=pp10_result,
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
            resolver = getattr(self.provider, "resolve_exchange", None)
            if callable(resolver):
                try:
                    exchange = resolver(symbol)
                except Exception:
                    logger.warning("exchange lookup failed for symbol=%s", symbol, exc_info=True)
                else:
                    if exchange:
                        logger.info("symbol=%s resolved to exchange=%s", symbol, exchange)
                        return exchange
            logger.info("symbol=%s is outside watchlist; using default HOSE exchange", symbol)
            return "HOSE"
        return self.settings.watchlist_exchanges[index]

    def _add_fundamentals(
        self, indicators: IndicatorSnapshot, symbol: str
    ) -> IndicatorSnapshot:
        if self.fundamental_provider is None:
            return indicators
        try:
            snapshot = self.fundamental_provider.get_snapshot(symbol)
        except Exception:
            logger.warning("fundamental data unavailable for %s", symbol, exc_info=True)
            return indicators
        fields = (
            "revenue_growth",
            "earnings_growth",
            "eps_growth",
            "roe",
            "pe",
            "pb",
            "historical_pe",
            "historical_pb",
        )
        return indicators.model_copy(
            update={field: getattr(snapshot, field, None) for field in fields}
        )

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

    @staticmethod
    def _previous_signal(session: Session, *, symbol: str, exchange: str) -> Signal | None:
        previous = latest_analysis_run(session, symbol=symbol, exchange=exchange)
        if previous is None:
            return None
        try:
            return Signal(previous.rule_signal)
        except ValueError:
            return None
