# VN Stock Analyst Bot — Implementation Specification

## Objective

Build a configurable Telegram bot with two separate analysis surfaces. The
`/analyze SYMBOL` command calls Gemini directly with a versioned PP10Ulti prompt and
returns an AI-generated report after collecting only basic OHLCV data. Data-backed
features such as `/chart`, `/market`, the scheduler and `/news` keep their existing
provider pipelines.

Telegram access is private whitelist mode by default and can be explicitly
switched to public mode with `TELEGRAM_PUBLIC_ACCESS=true`.

## Non-negotiable boundaries

- `/analyze` labels score, signal, risk and confidence as AI-generated references;
  they are not validated market signals or probabilities.
- The deterministic Rule Engine remains authoritative only for the data-backed
  pipeline used by scheduler and chart-related analysis.
- The PP10 AI prompt must not invent current prices, indicators, fundamentals,
  market-index values, news or links when they are not supplied.
- Provider responses, RSS content and LLM output are untrusted input.
- Raw OHLCV is the only live MVP price basis.
- Secrets live only in the user's untracked `.env`.
- No live external call is required for unit tests.

## Stack

Python 3.14-compatible runtime, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic,
PostgreSQL, pandas/numpy, feedparser, matplotlib/mplfinance, aiogram,
APScheduler, Google Gemini API.

Exact versions are pinned in `requirements.txt` after compatibility checks.

## Verification commands

```powershell
python -m pytest -q
python -m ruff check .
docker compose up -d --build
docker compose exec app alembic upgrade head
docker compose exec app python -m pytest -q
```

## Success criteria

- A clean database can be migrated and seeded with validated historical data.
- Calendar boundaries and OHLCV invariants are covered by deterministic tests.
- Same quantitative input and rule version always produce the same result.
- Missing mandatory data returns `INSUFFICIENT_DATA` without a fake signal.
- Gemini/Telegram failures return a user-readable error and do not affect the
  separate data-backed pipeline.
- Final candles cannot be overwritten by hourly ingestion.
- The user can later add `.env` and run live provider/Gemini/Telegram tests.

## Open decisions

Live provider credentials, provider source availability, RSS feed list and final
Telegram chat IDs are intentionally supplied later by the user.
