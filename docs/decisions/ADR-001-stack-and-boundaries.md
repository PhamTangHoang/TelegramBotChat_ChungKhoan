# ADR-001: Deterministic analysis boundary and configurable deployment

## Status

Accepted

## Context

The bot handles external market data, news, a language model and a configurable
Telegram interface. A reproducible signal must remain independent of provider
format drift and LLM wording.

## Decision

Use PostgreSQL, a repository boundary, deterministic Python analysis, a separate
Gemini explanation boundary, Docker Compose and raw OHLCV consistently in live
MVP. Telegram uses whitelist access by default and supports an explicit public
access mode through configuration. Keep secrets outside the repository.

## Consequences

The first release prioritizes reproducibility and auditability over adjusted-price
research, public scale and strategy claims. Public mode is rate-limited per chat
but is not intended as a high-scale service. Backtest V2 remains separate.
