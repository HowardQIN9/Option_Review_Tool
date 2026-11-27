"""Plotly figures for the single-trade replay."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PAD = timedelta(minutes=30)
BUY_COLOR, SELL_COLOR = "#3b82f6", "#ef4444"  # readable on both cream and deep-green themes


def _naive(ts):
    """Drop the timezone (already New York) so Plotly's hour-based rangebreaks use exchange time."""
    return ts.tz_localize(None) if getattr(ts, "tz", None) is not None else ts


def _window(bars: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    out = bars[(bars.index >= start - PAD) & (bars.index <= end + PAD)].copy()
    out.index = _naive(out.index)
    return out


def replay_figure(
    episode: pd.Series,
    fills: pd.DataFrame,
    option_bars: pd.DataFrame,
    underlying_bars: pd.DataFrame,
) -> go.Figure:
    """Option price (top) and underlying price (bottom) around the trade, with fills marked."""
    start, end = episode["entry_time"], episode["exit_time"]
    opt = _window(option_bars, start, end)
    und = _window(underlying_bars, start, end)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.6, 0.4],
        subplot_titles=(f"期权 {episode['occ']}（1 分钟成交价）", f"标的 {episode['underlying']}"),
    )
    if not opt.empty:
        fig.add_trace(
            go.Scatter(
                x=opt.index,
                y=opt["close"],
                mode="lines+markers",
                marker={"size": 3},
                name="期权价格",
                line={"width": 1.5},
            ),
            row=1,
            col=1,
        )
    if not und.empty:
        fig.add_trace(
            go.Scatter(x=und.index, y=und["close"], mode="lines", name="标的价格", line={"width": 1.5}),
            row=2,
            col=1,
        )

    markers = (("BTO", BUY_COLOR, "triangle-up", "买入"), ("STC", SELL_COLOR, "triangle-down", "卖出"))
    for code, color, symbol, label in markers:
        f = fills[fills["code"] == code]
        if f.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=f["exec_time"].dt.tz_localize(None),
                y=f["price"],
                mode="markers",
                name=label,
                marker={"color": color, "size": 12, "symbol": symbol, "line": {"color": "white", "width": 1}},
                customdata=f[["qty"]].to_numpy(),
                hovertemplate=(
                    f"{label} %{{x|%m-%d %H:%M:%S}}<br>价格 %{{y:.2f}} × %{{customdata[0]:.0f}} 张<extra></extra>"
                ),
            ),
            row=1,
            col=1,
        )

    fig.add_hline(
        y=episode["avg_entry"],
        line={"dash": "dot", "color": BUY_COLOR, "width": 1},
        annotation_text="买入均价",
        annotation_position="top left",
        row=1,
        col=1,
    )

    # Hide nights and weekends so multi-day holds read as one continuous session.
    fig.update_xaxes(rangebreaks=[{"bounds": ["sat", "mon"]}, {"bounds": [16.25, 9.5], "pattern": "hour"}])
    fig.update_layout(
        height=560,
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.08},
    )
    return fig
