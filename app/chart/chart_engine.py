from __future__ import annotations

import io
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

try:
    import matplotlib

    matplotlib.use("Agg")
except ImportError:
    matplotlib = None

from app.analysis.indicators import adx, cmf, macd, obv, rsi_wilder, sma, stoch_rsi
from app.domain.schemas import MarketCandle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChartAttachment:
    filename: str
    caption: str
    content: bytes


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
            return self._render_daily_trend(
                _build_frame(candles),
                symbol=symbol,
                as_of=as_of,
                is_final=is_final,
            ).content
        except ChartError:
            raise
        except Exception as exc:
            raise ChartError("unable to render technical chart") from exc

    def render_bundle(
        self,
        candles: Sequence[MarketCandle],
        *,
        symbol: str,
        as_of: datetime,
        is_final: bool,
    ) -> tuple[ChartAttachment, ...]:
        """Render the verified OHLCV views used by the AI report and Telegram output."""
        if len(candles) < 2:
            raise ChartError("at least two candles are required for a chart bundle")
        try:
            frame = _build_frame(candles)
        except Exception as exc:
            raise ChartError("unable to prepare chart data") from exc

        renderers = (
            self._render_daily_trend,
            self._render_daily_indicators,
            self._render_vpvr,
            self._render_weekly_trend,
        )
        attachments: list[ChartAttachment] = []
        for renderer in renderers:
            try:
                attachments.append(
                    renderer(frame, symbol=symbol, as_of=as_of, is_final=is_final)
                )
            except Exception:
                logger.warning(
                    "chart bundle item failed renderer=%s symbol=%s",
                    renderer.__name__,
                    symbol.upper(),
                    exc_info=True,
                )
        if not attachments:
            raise ChartError("unable to render chart bundle")
        return tuple(attachments)

    @staticmethod
    def _render_daily_trend(
        frame: Any, *, symbol: str, as_of: datetime, is_final: bool
    ) -> ChartAttachment:
        import matplotlib.pyplot as plt

        fig, (price_ax, volume_ax) = plt.subplots(
            2,
            1,
            sharex=True,
            figsize=(14, 9),
            gridspec_kw={"height_ratios": (3, 1)},
        )
        try:
            x = list(range(len(frame)))
            _draw_candles(price_ax, frame)
            price_ax.plot(x, frame["Close"], color="#202124", linewidth=1.0, label="Giá đóng cửa")
            ma_lines = (
                (20, "#2388ff"),
                (50, "#ef5350"),
                (150, "#f0a22e"),
                (200, "#39a852"),
            )
            for period, color in ma_lines:
                price_ax.plot(
                    x,
                    frame["Close"].rolling(period).mean(),
                    linewidth=1.3,
                    color=color,
                    label=f"MA{period}",
                )
            price_ax.set_title(_title(symbol, "Xu hướng ngày · MA20/50/150/200", as_of, is_final))
            price_ax.set_ylabel("Giá (nghìn VND/cổ phiếu)")
            price_ax.legend(loc="upper left", ncol=5, fontsize=8)
            price_ax.grid(alpha=0.2)

            volume_colors = [
                "#2ca25f" if close >= opening else "#de6b73"
                for opening, close in zip(frame["Open"], frame["Close"], strict=True)
            ]
            volume_ax.bar(x, frame["Volume"], color=volume_colors, width=0.7)
            volume_ax.plot(x, frame["Volume"].rolling(20).mean(), color="#2478d1", linewidth=1.2)
            volume_ax.set_ylabel("KL")
            volume_ax.grid(alpha=0.2)
            _set_time_axis(volume_ax, frame.index)
            return _attachment(fig, f"{symbol.upper()}-daily-trend.png", "Xu hướng ngày và MA")
        finally:
            plt.close(fig)

    @staticmethod
    def _render_daily_indicators(
        frame: Any, *, symbol: str, as_of: datetime, is_final: bool
    ) -> ChartAttachment:
        import matplotlib.pyplot as plt

        closes = frame["Close"].tolist()
        highs = frame["High"].tolist()
        lows = frame["Low"].tolist()
        volumes = frame["Volume"].tolist()
        rsi_values = rsi_wilder(closes, 14)
        stoch_values = stoch_rsi(closes, 14)
        macd_values, signal_values, histogram_values = macd(closes)
        adx_values, plus_di, minus_di = adx(highs, lows, closes, 14)
        obv_values = obv(closes, volumes)
        cmf_values = cmf(highs, lows, closes, volumes, 20)
        fig, axes = plt.subplots(
            6,
            1,
            sharex=True,
            figsize=(14, 18),
            gridspec_kw={"height_ratios": (2.4, 1, 1, 1, 1, 1)},
        )
        try:
            x = list(range(len(frame)))
            _draw_candles(axes[0], frame)
            axes[0].plot(x, frame["Close"], color="#202124", linewidth=1.0)
            axes[0].set_ylabel("Giá")
            axes[0].set_title(_title(symbol, "Bộ chỉ báo kỹ thuật ngày", as_of, is_final))
            axes[0].grid(alpha=0.2)

            axes[1].bar(x, volumes, color="#5c8fcf", width=0.7)
            axes[1].plot(x, sma(volumes, 20), color="#ef9b32", linewidth=1.1)
            axes[1].set_ylabel("KL")
            axes[1].grid(alpha=0.2)

            _plot(axes[2], rsi_values, "RSI14", "#8e5bd9")
            _plot(axes[2], stoch_values, "Stoch RSI", "#f08a24")
            axes[2].axhline(70, color="#888", linestyle="--", linewidth=0.8)
            axes[2].axhline(30, color="#888", linestyle="--", linewidth=0.8)
            axes[2].set_ylim(0, 100)
            axes[2].set_ylabel("RSI")
            axes[2].grid(alpha=0.2)

            axes[3].bar(
                x,
                [value if value is not None else 0.0 for value in histogram_values],
                color="#aaa",
                width=0.7,
            )
            _plot(axes[3], macd_values, "MACD", "#2679cf")
            _plot(axes[3], signal_values, "Signal", "#e85d75")
            axes[3].axhline(0, color="#888", linewidth=0.8)
            axes[3].set_ylabel("MACD")
            _legend_if_available(axes[3])
            axes[3].grid(alpha=0.2)

            _plot(axes[4], adx_values, "ADX", "#df6b74")
            _plot(axes[4], plus_di, "+DI", "#2584d7")
            _plot(axes[4], minus_di, "-DI", "#f08a24")
            axes[4].axhline(20, color="#888", linestyle="--", linewidth=0.8)
            axes[4].set_ylabel("ADX/DI")
            _legend_if_available(axes[4])
            axes[4].grid(alpha=0.2)

            _plot(axes[5], obv_values, "OBV", "#3489db")
            _plot(axes[5], cmf_values, "CMF20", "#39a852")
            axes[5].axhline(0, color="#888", linestyle="--", linewidth=0.8)
            axes[5].set_ylabel("Dòng tiền")
            _legend_if_available(axes[5])
            axes[5].grid(alpha=0.2)
            _set_time_axis(axes[5], frame.index)
            return _attachment(
                fig,
                f"{symbol.upper()}-daily-indicators.png",
                "Bộ chỉ báo RSI, Stoch RSI, MACD, ADX, OBV và CMF",
            )
        finally:
            plt.close(fig)

    @staticmethod
    def _render_vpvr(
        frame: Any, *, symbol: str, as_of: datetime, is_final: bool
    ) -> ChartAttachment:
        import matplotlib.pyplot as plt
        import numpy as np

        fig, (price_ax, profile_ax) = plt.subplots(
            1,
            2,
            figsize=(15, 8),
            gridspec_kw={"width_ratios": (4, 1)},
        )
        try:
            x = list(range(len(frame)))
            _draw_candles(price_ax, frame)
            price_ax.plot(x, frame["Close"], color="#202124", linewidth=1.0)
            price_ax.set_title(_title(symbol, "VPVR · Volume Profile", as_of, is_final))
            price_ax.set_ylabel("Giá (nghìn VND/cổ phiếu)")
            price_ax.grid(alpha=0.2)

            typical = ((frame["High"] + frame["Low"] + frame["Close"]) / 3).to_numpy()
            volumes = frame["Volume"].to_numpy()
            low = float(frame["Low"].min())
            high = float(frame["High"].max())
            if low == high:
                low -= 0.5
                high += 0.5
            profile, edges = np.histogram(typical, bins=24, range=(low, high), weights=volumes)
            centers = (edges[:-1] + edges[1:]) / 2
            profile_ax.barh(centers, profile, height=edges[1] - edges[0], color="#d7a92c")
            poc = float(centers[int(profile.argmax())]) if len(profile) else low
            price_ax.axhline(
                poc,
                color="#d12f2f",
                linestyle="--",
                linewidth=1.2,
                label=f"POC {poc:.2f}",
            )
            price_ax.legend(loc="upper left", fontsize=8)
            profile_ax.axhline(poc, color="#d12f2f", linestyle="--", linewidth=1.0)
            profile_ax.set_xlabel("Khối lượng")
            profile_ax.set_yticks([])
            profile_ax.grid(axis="x", alpha=0.2)
            return _attachment(fig, f"{symbol.upper()}-vpvr.png", "VPVR và vùng POC")
        finally:
            plt.close(fig)

    @staticmethod
    def _render_weekly_trend(
        frame: Any, *, symbol: str, as_of: datetime, is_final: bool
    ) -> ChartAttachment:
        import matplotlib.pyplot as plt

        weekly = frame.resample("W-FRI").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        ).dropna()
        fig, (price_ax, volume_ax) = plt.subplots(
            2,
            1,
            sharex=True,
            figsize=(14, 9),
            gridspec_kw={"height_ratios": (3, 1)},
        )
        try:
            x = list(range(len(weekly)))
            _draw_candles(price_ax, weekly)
            price_ax.plot(x, weekly["Close"], color="#202124", linewidth=1.0, label="Giá đóng cửa")
            price_ax.plot(x, weekly["Close"].rolling(30).mean(), color="#2388ff", label="MA30 tuần")
            price_ax.plot(x, weekly["Close"].rolling(40).mean(), color="#ef5350", label="MA40 tuần")
            price_ax.set_title(_title(symbol, "Xu hướng tuần · MA30/MA40", as_of, is_final))
            price_ax.set_ylabel("Giá (nghìn VND/cổ phiếu)")
            price_ax.legend(loc="upper left", fontsize=8)
            price_ax.grid(alpha=0.2)
            volume_ax.bar(x, weekly["Volume"], color="#5c8fcf", width=0.7)
            volume_ax.set_ylabel("KL tuần")
            volume_ax.grid(alpha=0.2)
            _set_time_axis(volume_ax, weekly.index)
            return _attachment(
                fig,
                f"{symbol.upper()}-weekly-trend.png",
                "Xu hướng tuần và MA30/MA40",
            )
        finally:
            plt.close(fig)


def _build_frame(candles: Sequence[MarketCandle]) -> Any:
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
    return frame.sort_index()


def _draw_candles(axis: Any, frame: Any) -> None:
    from matplotlib.patches import Rectangle

    for index, (_, row) in enumerate(frame.iterrows()):
        opening = float(row["Open"])
        close = float(row["Close"])
        high = float(row["High"])
        low = float(row["Low"])
        color = "#2ca25f" if close >= opening else "#de6b73"
        axis.vlines(index, low, high, color=color, linewidth=0.8)
        body_low = min(opening, close)
        body_height = max(abs(close - opening), max(abs(close) * 0.001, 0.01))
        axis.add_patch(
            Rectangle((index - 0.32, body_low), 0.64, body_height, facecolor=color, edgecolor=color)
        )


def _plot(axis: Any, values: Sequence[float | None], label: str, color: str) -> None:
    points = [(index, value) for index, value in enumerate(values) if value is not None]
    if points:
        axis.plot(
            [point[0] for point in points],
            [point[1] for point in points],
            label=label,
            color=color,
            linewidth=1.1,
        )


def _legend_if_available(axis: Any) -> None:
    handles, labels = axis.get_legend_handles_labels()
    if handles:
        axis.legend(handles, labels, loc="upper left", fontsize=8)


def _set_time_axis(axis: Any, index: Sequence[Any]) -> None:
    if len(index) == 0:
        return
    count = len(index)
    tick_count = min(8, count)
    ticks = sorted(
        {
            round(item * (count - 1) / max(tick_count - 1, 1))
            for item in range(tick_count)
        }
    )
    labels = [index[tick].strftime("%m/%Y") for tick in ticks]
    axis.set_xticks(ticks)
    axis.set_xticklabels(labels)


def _title(symbol: str, name: str, as_of: datetime, is_final: bool) -> str:
    status = "FINAL" if is_final else "INTRADAY"
    return f"{symbol.upper()} · {name} · {as_of.strftime('%Y-%m-%d %H:%M')} · {status}"


def _attachment(fig: Any, filename: str, caption: str) -> ChartAttachment:
    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", dpi=120, bbox_inches="tight")
    return ChartAttachment(filename=filename, caption=caption, content=buffer.getvalue())
