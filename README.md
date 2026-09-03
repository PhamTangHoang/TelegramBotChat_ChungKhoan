# VN Stock Analyst Bot

Private Telegram bot for deterministic technical analysis of Vietnamese stocks.
The Rule Engine owns the primary signal; Gemini is an explanation layer only.

## Quick start

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose exec app alembic upgrade head
docker compose exec app python -m pytest -q
```

The real `.env` is intentionally not committed. Add credentials only when you are
ready to run live provider, Gemini, Telegram and end-to-end tests.

## Environment variables

Copy `.env.example` to `.env`, then supply at least:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated numeric chat IDs)
- `GEMINI_API_KEY` (optional; technical report works without it)
- `NEWS_FEED_URLS` (optional comma-separated RSS URLs)

`DATABASE_URL`, `VNSTOCK_SOURCE` (`kbs` or `vci`), watchlist, schedule intervals,
version fields and risk/data policies are also configurable in `.env.example`.
Never put secrets in source files or commit `.env`.

Docker Desktop must be running before `docker compose up`. The app starts in
health-only mode when `TELEGRAM_BOT_TOKEN` is empty.

## Development commands

```powershell
python -m pytest -q
python -m ruff check .
docker compose up -d --build
docker compose logs --tail=200 app
```

## Scope

This is a private/personal analysis aid, not an investment recommendation service.
Reports must retain the disclaimer and must not present `confidence_raw` as a
probability before backtesting.

See `docs/SPEC.md`, `IMPLEMENTATION_NOTES.md` and `docs/decisions/` for the
implementation contract and rationale.
