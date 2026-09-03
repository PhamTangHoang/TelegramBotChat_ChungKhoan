from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import (
    AnalysisKind,
    EvaluationStatus,
    PriceBasis,
    Risk,
    RuleStatus,
    Signal,
)


class MarketCandle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=16)
    exchange: str = Field(min_length=1, max_length=16)
    trading_date: date
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(ge=0)
    adjusted_close: Decimal | None = Field(default=None, gt=0)
    price_basis: PriceBasis = PriceBasis.RAW_OHLCV
    source: str = Field(min_length=1, max_length=64)
    provider_timestamp: datetime | None = None
    is_final: bool = False

    @field_validator("symbol", "exchange")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("identity cannot be empty")
        return normalized

    @model_validator(mode="after")
    def validate_ohlc_relationship(self) -> "MarketCandle":
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be >= open, close and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be <= open, close and high")
        return self


class IndexCandle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index_code: str = Field(min_length=1, max_length=32)
    trading_date: date
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    source: str = Field(min_length=1, max_length=64)
    provider_timestamp: datetime | None = None
    is_final: bool = False

    @field_validator("index_code")
    @classmethod
    def normalize_index_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("index_code cannot be empty")
        return normalized

    @model_validator(mode="after")
    def validate_ohlc_relationship(self) -> "IndexCandle":
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be >= open, close and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be <= open, close and high")
        return self


class AnalysisContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    exchange: str
    as_of: datetime
    analysis_kind: AnalysisKind
    data_freshness: str
    price_basis: PriceBasis = PriceBasis.RAW_OHLCV

    @field_validator("symbol", "exchange")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        return value.strip().upper()


class IndicatorSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: Decimal = Field(gt=0)
    ma20: float | None = None
    ma50: float | None = None
    ma150: float | None = None
    ma200: float | None = None
    rsi14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    atr14: float | None = None
    volume_ratio_projected: float | None = None
    volume_dry_up: bool | None = None
    volume_breakout: bool | None = None
    adx14: float | None = None
    plus_di14: float | None = None
    minus_di14: float | None = None
    stoch_rsi14: float | None = None
    obv: float | None = None
    obv_change_5: float | None = None
    cmf20: float | None = None
    elapsed_trading_minutes: int = Field(ge=0)
    relative_return: float | None = None
    rs_rating: float | None = Field(default=None, ge=0, le=100)
    rs_line_new_high: bool | None = None
    wyckoff_phase: str | None = None
    pattern_name: str | None = None
    pattern_quality: float | None = Field(default=None, ge=0, le=1)
    pivot_price: float | None = None
    support_price: float | None = None
    resistance_price: float | None = None
    vpvr_poc: float | None = None
    vpvr_hvn: float | None = None
    vpvr_breakout: bool | None = None
    cpr_weekly_top: float | None = None
    cpr_weekly_bottom: float | None = None
    cpr_monthly_top: float | None = None
    cpr_monthly_bottom: float | None = None
    cpr_weekly_bullish: bool | None = None
    cpr_monthly_bullish: bool | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    eps_growth: float | None = None
    roe: float | None = None
    nim: float | None = None
    casa: float | None = None
    asset_quality: float | None = None
    pe: float | None = Field(default=None, gt=0)
    pb: float | None = Field(default=None, gt=0)
    sector_pe: float | None = Field(default=None, gt=0)
    sector_pb: float | None = Field(default=None, gt=0)
    historical_pe: float | None = Field(default=None, gt=0)
    historical_pb: float | None = Field(default=None, gt=0)
    market_price: float | None = None
    market_ma20: float | None = None
    market_ma50: float | None = None
    as_of: datetime
    is_final: bool
    price_basis: PriceBasis = PriceBasis.RAW_OHLCV


class RuleReason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1, max_length=16)
    message: str = Field(min_length=1, max_length=128)
    status: RuleStatus
    value: float | None = None
    threshold: str = Field(min_length=1, max_length=128)


class RuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0)
    max_score: int = Field(ge=0)
    signal: Signal
    confidence_raw: float | None = Field(default=None, ge=0, le=1)
    reasons: list[RuleReason]
    risk: Risk
    risk_points: int = Field(ge=0)
    risk_reasons: list[str]
    rule_version: str = Field(min_length=1, max_length=32)


class PP10Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(min_length=1, max_length=8)
    name: str = Field(min_length=1, max_length=160)
    status: EvaluationStatus
    score: int = Field(ge=0, le=1)
    value: Any = None
    threshold: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=500)
    data_source: str = Field(min_length=1, max_length=128)


class PP10RiskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_zone: str
    add_zone: str
    stop_loss: str
    target: str
    risk_reward: str


class PP10Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0)
    max_score: int = Field(ge=0)
    evaluated_count: int = Field(ge=0, le=16)
    total_criteria: int = Field(default=16, ge=16, le=16)
    grade: str = Field(pattern=r"^(A\+|A|B|C)$")
    confidence: str = Field(pattern=r"^(High|Medium|Low)$")
    version: str = Field(min_length=1, max_length=32)
    criteria: list[PP10Criterion] = Field(min_length=16, max_length=16)
    risk_plan: PP10RiskPlan


class NewsItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=500)
    summary: str | None = Field(default=None, max_length=10000)
    url: str = Field(min_length=1, max_length=2048)
    published_at: datetime | None = None
    content_hash: str = Field(min_length=64, max_length=64)
    symbol: str | None = Field(default=None, max_length=16)
    fetched_at: datetime
