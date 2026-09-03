# VN Stock Analyst Bot — Implementation Specification

## Objective

Build a private, whitelist-only Telegram bot that collects Vietnamese market data,
validates and stores it, computes deterministic technical indicators, produces a
versioned signal/risk result, audits the exact inputs, optionally asks Gemini for
explanation, and delivers a technical report and chart.

## Non-negotiable boundaries

- Rule Engine is the only owner of `signal`, `score` and `confidence_raw`.
- Gemini cannot calculate, override or reinterpret the primary signal.
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
- Gemini/Telegram/provider failures never destroy the saved technical result.
- Final candles cannot be overwritten by hourly ingestion.
- The user can later add `.env` and run live provider/Gemini/Telegram tests.

## Open decisions

Live provider credentials, provider source availability, RSS feed list and final
Telegram chat IDs are intentionally supplied later by the user.
