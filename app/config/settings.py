from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _csv_strings(value: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip().upper() for item in value.split(",") if item.strip())
    return tuple(str(item).strip().upper() for item in value if str(item).strip())


def _csv_ints(value: str | tuple[int, ...] | list[int]) -> tuple[int, ...]:
    if isinstance(value, str):
        return tuple(int(item.strip()) for item in value.split(",") if item.strip())
    return tuple(int(item) for item in value)


CsvStrings = Annotated[tuple[str, ...], BeforeValidator(_csv_strings)]
CsvInts = Annotated[tuple[int, ...], BeforeValidator(_csv_ints)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "postgresql+psycopg://postgres:postgres@postgres:5432/vn_stock"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    telegram_bot_token: str | None = None
    telegram_allowed_chat_ids: CsvInts = Field(default_factory=tuple)
    telegram_rate_limit_per_min: int = Field(default=5, ge=1, le=1000)

    watchlist_symbols: CsvStrings = ("FPT", "VNM", "HPG")
    watchlist_exchanges: CsvStrings = ("HOSE", "HOSE", "HOSE")
    market_job_interval_minutes: int = Field(default=60, ge=1, le=1440)
    news_job_interval_minutes: int = Field(default=45, ge=1, le=1440)
    eod_settle_job_time: str = "15:20"
    telegram_timezone: str = "Asia/Ho_Chi_Minh"

    volume_lookback_days: int = Field(default=20, ge=1)
    volume_ratio_threshold: float = Field(default=1.5, gt=0)
    volume_min_elapsed_minutes: int = Field(default=15, ge=1)
    rs_lookback_days: int = Field(default=20, ge=1)
    data_cache_max_age_minutes: int = Field(default=60, ge=0)
    allow_stale_signal: bool = False

    rule_version: str = "1.5.0"
    prompt_version: str = "1.0.0"
    data_schema_version: str = "1.0.0"
    calendar_version: str = "HOSE_2026"
    log_level: str = "INFO"

    @field_validator("eod_settle_job_time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("eod_settle_job_time must use HH:MM")
        hour, minute = map(int, parts)
        if hour not in range(24) or minute not in range(60):
            raise ValueError("eod_settle_job_time must use a valid time")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("unsupported log level")
        return normalized

    @model_validator(mode="after")
    def validate_watchlist(self) -> "Settings":
        if len(self.watchlist_symbols) != len(self.watchlist_exchanges):
            raise ValueError("watchlist_symbols and watchlist_exchanges must have equal length")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
