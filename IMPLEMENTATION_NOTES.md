# Implementation notes

This file records implementation details that are not allowed to silently change
the v1.5 business semantics.

## Confirmed choices

- Live MVP uses `RAW_OHLCV` for indicators, displayed price and chart.
- Relative Strength is 20-session stock return minus VNINDEX return.
- A missing mandatory VNINDEX/RS input returns `INSUFFICIENT_DATA`.
- `R6` is `NOT_EVALUATED` before 15 regular trading minutes.
- Real credentials are supplied by the user later through an untracked `.env`.
- External data and LLM output are untrusted and are validated at boundaries.
- Telegram access is private by default; `TELEGRAM_PUBLIC_ACCESS=true` explicitly
  enables all-chat access while retaining the per-chat rate limit.
- Natural-language Telegram shortcuts route analysis/chart/market requests to
  deterministic services; other plain text uses Gemini as a conversational layer
  and never owns a stock signal.
- `WATCHLIST_SYMBOLS` controls scheduled refreshes; on-demand Telegram analysis
  accepts additional listed symbols, resolves HOSE/HNX/UPCOM from vnstock when
  possible, and falls back to HOSE only when the listing lookup is unavailable.
- Gemini's Pydantic response schema is sanitized to remove unsupported
  `additionalProperties` fields before it is sent to the API.
- The vnstock adapter keeps the last row when the provider emits duplicate
  VNINDEX or equity dates and logs the event, so a duplicate provider row does
  not make an otherwise valid symbol unavailable.
- PP10Ulti evaluates every criterion deterministically when its required data is
  available. Criteria that require a market-universe RS ranking or sector
  valuation dataset remain explicitly `DATA_UNAVAILABLE` until those providers
  are added.
- Telegram exposes one analysis command, `/analyze SYMBOL`, which combines the
  v1.5 technical rules with the deterministic PP10Ulti evaluator. `/news SYMBOL`
  is a separate cached RSS report and never changes the analysis score.
- PP10 criteria that lack a validated data source are marked
  `DATA_UNAVAILABLE`; they do not count as passes or failures and never receive
  fabricated values.

## Explicit MVP policies

- Stale cache is disabled for new signals by default. If enabled explicitly,
  `data_freshness=stale_cache` is visible and contributes risk points.
- Volume projection uses the provider's regular-session cumulative matched volume.
  A provider that cannot establish this semantic must fail with
  `ProviderSemanticError` rather than silently mixing negotiated volume.
- ATR14 uses Wilder/RMA smoothing, matching the RSI smoothing convention.
- Historical bootstrap runs before live analysis and marks validated historical
  candles as finalized.
- `vnstock==4.0.7` is called through its v4 UI API:
  `Market().equity(symbol).ohlcv(..., source=...)` and
  `Market().index(symbol).ohlcv(..., source=...)`; the configured source is
  `kbs` or `vci`.
- `analysis_runs` keeps legitimate observations; scheduler execution identity is
  tracked separately in `scheduler_runs`.
- Docker is the supported runtime for the pinned dependency set (`python:3.12-slim`);
  host-only tests may use a different already-installed Python package set.
- `numpy==2.2.6` is pinned because `vnstock_ezchart` requires `numpy<2.3` and
  this keeps the Docker install on a compatible CPython 3.12 wheel.

If a future change conflicts with these choices, add an ADR and update the rule,
data and prompt versions together.
