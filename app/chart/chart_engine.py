from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import datetime

try:
    import matplotlib

    matplotlib.use("Agg")
except ImportError:
    matplotlib = None

from app.domain.schemas import MarketCandle


class ChartError(RuntimeError):
    """A chart could not be rendered from validated market data."""


class ChartEngine:
    def render(
        self,
        candles: Sequence[MarketCandle],
        *,
        symbol: str,
        as_of: datetime,
        is_final: bool,
    ) -> bytes:
        if len(candles) < 2:
            raise ChartError("at least two candles are required for a chart")

        try:
            import matplotlib.pyplot as plt
            import mplfinance as mpf
            import pandas as pd

            frame = pd.DataFrame(
                [
                    {
                        "Open": float(candle.open),
                        "High": float(candle.high),
                        "Low": float(candle.low),
                        "Close": float(candle.close),
                        "Volume": float(candle.volume),
                    }
                    for candle in candles
                ],
                index=pd.DatetimeIndex([candle.trading_date for candle in candles]),
            )
            frame.index.name = "Date"
            addplots = []
            if len(frame) >= 20:
                addplots.append(mpf.make_addplot(frame["Close"].rolling(20).mean(), color="blue"))
            if len(frame) >= 50:
                addplots.append(mpf.make_addplot(frame["Close"].rolling(50).mean(), color="orange"))

            buffer = io.BytesIO()
            status = "FINAL" if is_final else "INTRADAY"
            mpf.plot(
                frame,
                type="candle",
                volume=True,
                addplot=addplots or None,
                title=f"{symbol.upper()} | as_of {as_of.isoformat()} | {status}",
                style="yahoo",
                figsize=(12, 8),
                savefig=dict(fname=buffer, dpi=120, bbox_inches="tight"),
            )
            return buffer.getvalue()
        except ChartError:
            raise
        except Exception as exc:
            raise ChartError("unable to render technical chart") from exc
        finally:
            try:
                import matplotlib.pyplot as plt

                plt.close("all")
            except ImportError:
                pass
