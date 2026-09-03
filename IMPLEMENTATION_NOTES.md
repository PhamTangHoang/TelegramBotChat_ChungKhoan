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

If a future change conflicts with these choices, add an ADR and update the rule,
data and prompt versions together.
