# ADR-001: Deterministic analysis boundary and private deployment

## Status

Accepted

## Context

The bot handles external market data, news, a language model and a private
Telegram interface. A reproducible signal must remain independent of provider
format drift and LLM wording.

## Decision

Use PostgreSQL, a repository boundary, deterministic Python analysis, a separate
Gemini explanation boundary, whitelist-only Telegram access and Docker Compose.
Keep secrets outside the repository and use raw OHLCV consistently in live MVP.

## Consequences

The first release prioritizes reproducibility and auditability over adjusted-price
research, public scale and strategy claims. Backtest V2 remains separate.
