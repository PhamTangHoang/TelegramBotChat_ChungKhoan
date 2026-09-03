from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


JsonType = JSON().with_variant(JSONB, "postgresql")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Symbol(TimestampMixin, Base):
    __tablename__ = "symbols"
    __table_args__ = (UniqueConstraint("symbol", "exchange", name="uq_symbols_symbol_exchange"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    candles: Mapped[list["MarketCandle"]] = relationship(back_populates="symbol")


class MarketCandle(TimestampMixin, Base):
    __tablename__ = "market_candles"
    __table_args__ = (
        UniqueConstraint("symbol_id", "trading_date", name="uq_market_candles_symbol_date"),
        Index("ix_market_candles_symbol_date", "symbol_id", "trading_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    price_basis: Mapped[str] = mapped_column(String(32), nullable=False, default="RAW_OHLCV")
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    symbol: Mapped[Symbol] = relationship(back_populates="candles")


class MarketIndex(TimestampMixin, Base):
    __tablename__ = "market_indices"
    __table_args__ = (
        UniqueConstraint("index_code", "trading_date", name="uq_market_indices_code_date"),
        Index("ix_market_indices_code_date", "index_code", "trading_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    index_code: Mapped[str] = mapped_column(String(32), nullable=False)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class News(TimestampMixin, Base):
    __tablename__ = "news"
    __table_args__ = (
        UniqueConstraint("url", name="uq_news_url"),
        Index("ix_news_published_at", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(16))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        Index("ix_analysis_runs_symbol_as_of", "symbol", "exchange", "as_of"),
        Index("ix_analysis_runs_final", "symbol", "trading_date", "is_final"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_snapshot: Mapped[dict] = mapped_column(JsonType, nullable=False)
    indicator_snapshot: Mapped[dict] = mapped_column(JsonType, nullable=False)
    rule_result: Mapped[dict] = mapped_column(JsonType, nullable=False)
    data_provenance: Mapped[dict] = mapped_column(JsonType, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    data_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    llm_response: Mapped[dict | None] = mapped_column(JsonType)
    rule_signal: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SchedulerRun(Base):
    __tablename__ = "scheduler_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
