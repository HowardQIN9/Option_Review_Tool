"""A compact trading-day calendar (Mon–Fri) coloured by daily P&L, with days that have notes marked."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go

from .i18n import DEFAULT_LANG, Lang, t

WIN_COLOR = "rgba(34, 160, 90, {a})"
LOSS_COLOR = "rgba(220, 70, 60, {a})"
EMPTY_COLOR = "rgba(128, 128, 128, 0.12)"
SELECTED_OUTLINE = "#e3c25b"
CELL = 34  # marker size in px


def daily_summary(trades: pd.DataFrame) -> pd.DataFrame:
    """Trades and net P&L per day, indexed by date."""
    if trades.empty:
        return pd.DataFrame(columns=["n", "pnl"])
    return trades.groupby("day").agg(n=("pnl", "size"), pnl=("pnl", "sum"))


def month_weekdays(year: int, month: int) -> list[date]:
    """All Monday–Friday dates of a month."""
    days = calendar.Calendar().itermonthdates(year, month)
    return [d for d in days if d.month == month and d.weekday() < 5]


def shift_month(first: date, months: int) -> date:
    index = first.year * 12 + first.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def month_weeks(year: int, month: int) -> list[date]:
    """Monday of every week (row) shown for a month, top to bottom."""
    days = month_weekdays(year, month)
    first = days[0] - timedelta(days=days[0].weekday())
    return [first + timedelta(weeks=i) for i in range(_row(days[-1], first) + 1)]


def week_range(monday: date) -> tuple[date, date]:
    return monday, monday + timedelta(days=4)


def month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _row(d: date, first_monday: date) -> int:
    return (d - first_monday).days // 7


def _cell_color(pnl: float | None, scale: float) -> str:
    if pnl is None:
        return EMPTY_COLOR
    alpha = 0.35 + 0.6 * min(abs(pnl) / scale, 1.0) if scale else 0.6
    return (WIN_COLOR if pnl > 0 else LOSS_COLOR).format(a=round(alpha, 2))


def calendar_figure(
    year: int,
    month: int,
    daily: pd.DataFrame,
    note_days: set[date],
    selected: date | None = None,
    lang: Lang = DEFAULT_LANG,
    selected_week: date | None = None,
) -> go.Figure:
    """Trace 0: one square per weekday. Trace 1: one square per week (left column), for week filters."""
    days = month_weekdays(year, month)
    weeks = month_weeks(year, month)
    first_monday = weeks[0]
    scale = float(daily["pnl"].abs().max()) if not daily.empty else 1.0
    clear = "rgba(0,0,0,0)"

    xs, ys, colors, outlines, texts, hovers = [], [], [], [], [], []
    for d in days:
        xs.append(d.weekday())
        ys.append(-_row(d, first_monday))
        row = daily.loc[d] if d in daily.index else None
        colors.append(_cell_color(None if row is None else row["pnl"], scale))
        if row is None:
            hover = f"{d:%Y-%m-%d}<br>{t('cal_no_trades', lang)}"
        else:
            hover = f"{d:%Y-%m-%d}<br>{t('cal_trades', lang, n=int(row['n']))}<br>${row['pnl']:,.0f}"
        has_note = d in note_days
        if has_note:
            hover += f"<br>📝 {t('cal_has_note', lang)}"
        texts.append(f"{d.day}{'•' if has_note else ''}")
        outlines.append(SELECTED_OUTLINE if d == selected else clear)
        hovers.append(hover)

    w_colors, w_outlines, w_texts, w_hovers = [], [], [], []
    for monday in weeks:
        start, end = week_range(monday)
        in_week = daily[(daily.index >= start) & (daily.index <= end)] if not daily.empty else daily
        w_scale = scale * 3  # a week sums several days, so compare on a wider scale
        if in_week.empty:
            w_colors.append(EMPTY_COLOR)
            hover = f"{start:%m-%d} ~ {end:%m-%d}<br>{t('cal_no_trades', lang)}"
        else:
            pnl = float(in_week["pnl"].sum())
            w_colors.append(_cell_color(pnl, w_scale))
            hover = f"{start:%m-%d} ~ {end:%m-%d}<br>{t('cal_trades', lang, n=int(in_week['n'].sum()))}<br>${pnl:,.0f}"
        w_texts.append(f"W{monday.isocalendar().week}")
        w_outlines.append(SELECTED_OUTLINE if monday == selected_week else clear)
        w_hovers.append(hover + f"<br>{t('cal_week_hint', lang)}")

    def trace(x, y, text, color, outline, hover, symbol, size):
        return go.Scatter(
            x=x,
            y=y,
            mode="markers+text",
            text=text,
            textfont={"size": 11},
            hovertext=hover,
            hoverinfo="text",
            marker={"symbol": symbol, "size": size, "color": color, "line": {"color": outline, "width": 2.5}},
        )

    fig = go.Figure(
        [
            trace(xs, ys, texts, colors, outlines, hovers, "square", CELL),
            trace(
                [-1.15] * len(weeks),
                [-i for i in range(len(weeks))],
                w_texts,
                w_colors,
                w_outlines,
                w_hovers,
                "square",
                CELL,
            ),
        ]
    )
    n_rows = len(weeks)
    fig.update_xaxes(
        range=[-1.75, 4.6],
        tickvals=[-1.15, *range(5)],
        ticktext=[t("cal_week", lang), *t("cal_weekdays", lang).split(",")],
        side="top",
        showgrid=False,
        zeroline=False,
        fixedrange=True,
    )
    fig.update_yaxes(visible=False, range=[-n_rows + 0.4, 0.6], fixedrange=True)
    fig.update_layout(
        width=6 * (CELL + 10) + 28,
        height=n_rows * (CELL + 8) + 40,
        margin={"l": 4, "r": 4, "t": 24, "b": 4},
        showlegend=False,
        dragmode=False,
        clickmode="event+select",
    )
    return fig
