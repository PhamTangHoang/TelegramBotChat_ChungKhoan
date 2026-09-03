from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import AnalysisKind, PriceBasis


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

    price: Decimal
    ma20: float | None = None
    ma50: float | None = None
    rsi14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    atr14: float | None = None
    volume_ratio_projected: float | None = None
    elapsed_trading_minutes: int
    relative_return: float | None = None
    as_of: datetime
    is_final: bool
    price_basis: PriceBasis = PriceBasis.RAW_OHLCV
