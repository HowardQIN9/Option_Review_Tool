"""Trade-review dashboard (local).

Run:  streamlit run streamlit_app.py
Needs the outputs of `python run_analysis.py` (output/episodes.csv, output/fills_standardized.csv)
and the minute bars under data/.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pandas as pd
import streamlit as st

from dashboard import config, data
from dashboard.calendar_view import (
    calendar_figure,
    daily_summary,
    month_range,
    month_weekdays,
    month_weeks,
    shift_month,
    week_range,
)
from dashboard.charts import replay_figure
from dashboard.export_dialog import open_export_dialog
from dashboard.filters import TradeFilter
from dashboard.i18n import DEFAULT_LANG, LANGUAGES, Lang, label, month_title, t, tag_label
from dashboard.notes import Note, NoteStore
from dashboard.notes_dialog import open_notes_dialog
from dashboard.stats import Summary, summarize


def current_lang() -> Lang:
    """Language from the sidebar switch, remembered in the URL (?lang=en) across reloads."""
    if "lang" not in st.session_state:
        requested = st.query_params.get("lang", DEFAULT_LANG)
        st.session_state["lang"] = requested if requested in LANGUAGES else DEFAULT_LANG
    return st.session_state["lang"]


LANG = current_lang()
st.set_page_config(page_title=t("page_title", LANG), page_icon="📈", layout="wide")

# Session-state keys
DATE_MODE, SINGLE_DATE, DATE_RANGE, PENDING_RANGE = "date_mode", "single_date", "date_range", "pending_range"
SELECTED_TRADE, REPLAY_PICK, TABLE_LAST = "selected_trade_key", "replay_pick", "table_last_selection"
CAL_MONTH, CAL_NONCE, CAL_SYNCED = "calendar_month", "calendar_nonce", "calendar_synced_to"


# ---------------------------------------------------------------- data


@st.cache_data(show_spinner=False)
def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    return data.load_episodes(), data.load_fills()


def ordered(values: pd.Series, column: str) -> list[str]:
    present = set(values.dropna())
    order = config.CATEGORY_ORDER.get(column, sorted(present))
    return [v for v in order if v in present] + sorted(present - set(order))


def selected_trade(trades: pd.DataFrame) -> pd.Series | None:
    key = st.session_state.get(SELECTED_TRADE)
    match = trades[trades["trade_key"] == key]
    return None if match.empty else match.iloc[0]


# ---------------------------------------------------------------- sidebar


def language_switch() -> None:
    choice = st.sidebar.radio(
        t("language", LANG),
        list(LANGUAGES),
        format_func=LANGUAGES.get,
        index=list(LANGUAGES).index(LANG),
        horizontal=True,
    )
    if choice != LANG:
        st.session_state["lang"] = choice
        st.query_params["lang"] = choice
        st.rerun()


def sidebar_filter(trades: pd.DataFrame) -> TradeFilter:
    sb = st.sidebar
    sb.header(t("filters", LANG))

    first, last = trades["day"].min(), trades["day"].max()
    # The calendar asks for a day, week, month or all dates by leaving a pending (start, end) range;
    # apply it here, before the date widgets are created.
    st.session_state.setdefault(DATE_MODE, False)
    st.session_state.setdefault(SINGLE_DATE, last)
    st.session_state.setdefault(DATE_RANGE, (first, last))
    if (pending := st.session_state.pop(PENDING_RANGE, None)) is not None:
        start, end = (min(max(d, first), last) for d in pending)
        st.session_state[DATE_MODE] = start == end
        if start == end:
            st.session_state[SINGLE_DATE] = start
        else:
            st.session_state[DATE_RANGE] = (start, end)

    single_day = sb.radio(
        t("date_mode", LANG),
        [False, True],
        format_func=lambda single: t("mode_day" if single else "mode_range", LANG),
        horizontal=True,
        key=DATE_MODE,
    )
    if single_day:
        start = end = sb.date_input(t("date", LANG), min_value=first, max_value=last, key=SINGLE_DATE)
    else:
        picked = sb.date_input(t("date_range", LANG), min_value=first, max_value=last, key=DATE_RANGE)
        start, end = (picked[0], picked[-1]) if isinstance(picked, tuple) and picked else (first, last)

    counts = trades["underlying"].value_counts()
    underlyings = sb.multiselect(
        t("ticker", LANG),
        options=list(counts.index),
        format_func=lambda s: t("ticker_count", LANG, symbol=s, n=counts[s]),
        placeholder=t("all_tickers", LANG),
    )

    box = sb.expander(t("more_filters", LANG), expanded=False)

    def multi(key: str, column: str) -> tuple[str, ...]:
        options = ordered(trades[column], column)
        picked = box.multiselect(
            t(key, LANG), options, format_func=lambda v: label(v, LANG), placeholder=t("all", LANG)
        )
        return tuple(picked)

    def choice(key: str, options: dict[str, object]) -> object:
        picked = box.radio(t(key, LANG), list(options), format_func=lambda k: t(k, LANG), horizontal=True)
        return options[picked]

    option_types = multi("f_type", "type")
    dte_buckets = multi("f_dte", "dte_bucket")
    times_of_day = multi("f_tod", "tod")
    hold_buckets = multi("f_hold", "hold_bucket")
    add_types = multi("f_add", "add_type")
    outcome = choice("f_outcome", {"all": None, "win": "win", "loss": "loss"})
    overnight = choice("f_overnight", {"all": None, "yes": True, "no": False})

    return TradeFilter(
        start=start,
        end=end,
        underlyings=tuple(underlyings),
        option_types=option_types,
        dte_buckets=dte_buckets,
        times_of_day=times_of_day,
        hold_buckets=hold_buckets,
        add_types=add_types,
        outcome=outcome,
        overnight=overnight,
    )


def sidebar_actions(trades: pd.DataFrame, fills: pd.DataFrame, flt: TradeFilter, notes: NoteStore) -> None:
    sb = st.sidebar
    sb.divider()
    sb.header(t("notes_header", LANG))
    sb.caption(t("notes_caption", LANG))
    if sb.button(t("notes_button", LANG), width="stretch"):
        trade = selected_trade(trades)
        day = flt.start if flt.start == flt.end else (trade["day"] if trade is not None else None)
        open_notes_dialog(notes, day, trade, LANG)

    sb.divider()
    sb.header(t("llm_header", LANG))
    sb.caption(t("llm_caption", LANG, n=len(trades)))
    if sb.button(t("llm_button", LANG), type="primary", width="stretch"):
        open_export_dialog(trades, fills, flt, notes, LANG)


# ---------------------------------------------------------------- formatting


def fmt_ci(ci: tuple[float, float], spec: str, prefix: str = "") -> str:
    return "—" if any(pd.isna(v) for v in ci) else f"{prefix}{ci[0]:{spec}} ~ {prefix}{ci[1]:{spec}}"


def fmt(value: float, spec: str) -> str:
    return "—" if pd.isna(value) else format(value, spec)


def fmt_hold(minutes: float) -> str:
    if minutes < 60:
        return t("minutes", LANG, value=minutes)
    if minutes < 24 * 60:
        return t("hours", LANG, value=minutes / 60)
    return t("days", LANG, value=minutes / (24 * 60))


def metric(col, label_text: str, value: str, note: str = "") -> None:
    """A metric with a neutral note underneath (st.metric's delta would add a misleading arrow)."""
    col.metric(label_text, value)
    if note:
        col.caption(note)


def note_badge(note: Note) -> str:
    if note.is_empty:
        return ""
    tags = "·".join(tag_label(tag, LANG) for tag in note.tags)
    return f"📝 {tags}".strip()


# ---------------------------------------------------------------- top: stats + calendar


def show_summary(s: Summary) -> None:
    """Headline statistics as a compact vertical list."""
    rows = [
        (t("m_trades", LANG), f"{s.n}", t("m_days", LANG, n=s.days)),
        (t("m_win_rate", LANG), fmt(s.win_rate, ".1%"), f"95% CI {fmt_ci(s.win_rate_ci, '.0%')}"),
        (t("m_net_pnl", LANG), f"${s.total_pnl:,.0f}", ""),
        (t("m_expectancy", LANG), f"${fmt(s.expectancy, ',.1f')}", f"95% CI {fmt_ci(s.expectancy_ci, ',.0f', '$')}"),
        ("Profit Factor", fmt(s.profit_factor, ".2f"), t("m_payoff", LANG, value=fmt(s.payoff_ratio, ".2f"))),
        (t("m_median_ret", LANG), fmt(s.median_return, ".1%"), ""),
    ]
    html = "".join(f"<tr><td class='k'>{k}</td><td class='v'>{v}</td><td class='n'>{n}</td></tr>" for k, v, n in rows)
    st.html(
        "<style>"
        "table.stats{border-collapse:collapse;width:100%;font-family:inherit;color:inherit}"
        "table.stats td{border:none;padding:6px 10px 6px 0;vertical-align:baseline}"
        "table.stats td.k{opacity:.75;font-size:.9rem;white-space:nowrap}"
        "table.stats td.v{font-size:1.5rem;font-weight:600;white-space:nowrap}"
        "table.stats td.n{opacity:.6;font-size:.8rem}"
        "</style>"
        f"<table class='stats'>{html}</table>"
    )
    if s.n < config.SMALL_SAMPLE:
        st.warning(t("small_sample", LANG, n=s.n), icon="⚠️")
    st.caption(t("ci_caption", LANG))


def request_range(start: date, end: date) -> None:
    """Ask the sidebar filter to switch to [start, end] on the next run."""
    st.session_state[PENDING_RANGE] = (start, end)
    st.session_state[CAL_NONCE] = st.session_state.get(CAL_NONCE, 0) + 1  # clear the chart selection
    st.rerun()


def show_calendar(trades: pd.DataFrame, flt: TradeFilter, notes: NoteStore) -> None:
    """Small Mon–Fri calendar. Click a day, a week (left column), the month name, or "All" to filter."""
    # Ignore the date filter so the calendar always shows whole months, but keep the other filters.
    scoped = replace(flt, start=None, end=None).apply(trades)
    daily = daily_summary(scoped)
    first, last = trades["day"].min(), trades["day"].max()

    def clipped(start: date, end: date) -> tuple[date, date]:
        return max(start, first), min(end, last)

    # Follow the filter to its month when the filter changes; otherwise let ◀ ▶ browse freely.
    if st.session_state.get(CAL_SYNCED) != (flt.start, flt.end):
        st.session_state[CAL_SYNCED] = (flt.start, flt.end)
        anchor = flt.end or last
        st.session_state[CAL_MONTH] = date(anchor.year, anchor.month, 1)
    month = st.session_state[CAL_MONTH]

    current = (flt.start, flt.end)
    selected_day = flt.start if flt.start == flt.end else None
    selected_week = next(
        (m for m in month_weeks(month.year, month.month) if current == clipped(*week_range(m)) and not selected_day),
        None,
    )
    month_selected = current == clipped(*month_range(month.year, month.month)) and not selected_day
    all_selected = current == (first, last)

    prev_col, title_col, next_col, all_col = st.columns([1, 3, 1, 1.6], vertical_alignment="center")
    if prev_col.button("◀", key="cal_prev"):
        st.session_state[CAL_MONTH] = shift_month(month, -1)
        st.rerun()
    if title_col.button(
        month_title(month.year, month.month, LANG),
        key="cal_month_filter",
        type="primary" if month_selected else "tertiary",
        help=t("cal_month_help", LANG),
        width="stretch",
    ):
        request_range(*month_range(month.year, month.month))
    if next_col.button("▶", key="cal_next"):
        st.session_state[CAL_MONTH] = shift_month(month, 1)
        st.rerun()
    if all_col.button(
        t("cal_all", LANG),
        key="cal_all_filter",
        type="primary" if all_selected else "secondary",
        help=t("cal_all_help", LANG),
        width="stretch",
    ):
        request_range(first, last)

    fig = calendar_figure(
        month.year, month.month, daily, notes.days_with_notes(), selected_day, LANG, selected_week=selected_week
    )
    event = st.plotly_chart(
        fig,
        key=f"calendar_{st.session_state.get(CAL_NONCE, 0)}",
        on_select="rerun",
        selection_mode="points",
        width="content",
        config={"displayModeBar": False},
    )
    points = event.selection.points if event else []
    if points:
        point = points[0]
        if point["curve_number"] == 0:  # a day
            day = month_weekdays(month.year, month.month)[point["point_index"]]
            request_range(day, day)
        else:  # a week
            request_range(*week_range(month_weeks(month.year, month.month)[point["point_index"]]))
    st.caption(t("cal_hint", LANG))


# ---------------------------------------------------------------- trade list


def table_columns() -> dict[str, object]:
    cc = st.column_config
    return {
        "trade_id": cc.NumberColumn(t("c_id", LANG), format="%d"),
        "entry_time": cc.DatetimeColumn(t("c_entry", LANG), format="YYYY-MM-DD HH:mm"),
        "underlying": t("c_ticker", LANG),
        "type": t("c_type", LANG),
        "strike": cc.NumberColumn(t("c_strike", LANG)),
        "dte_bucket": t("c_dte", LANG),
        "tod": t("c_tod", LANG),
        "hold_min": cc.NumberColumn(t("c_hold", LANG), format="%.0f"),
        "overnight": cc.CheckboxColumn(t("c_overnight", LANG)),
        "add_type": t("c_add", LANG),
        "contracts": cc.NumberColumn(t("c_contracts", LANG), format="%.0f"),
        "pnl": cc.NumberColumn(t("c_pnl", LANG), format="$%.2f"),
        "ret": cc.NumberColumn(t("c_ret", LANG), format="%.1f%%"),
        "mfe": cc.NumberColumn(t("c_mfe", LANG), format="%.1f%%"),
        "mae": cc.NumberColumn(t("c_mae", LANG), format="%.1f%%"),
        "note": t("c_note", LANG),
    }


DEFAULT_COLUMNS = [
    "trade_id",
    "entry_time",
    "underlying",
    "type",
    "strike",
    "dte_bucket",
    "hold_min",
    "pnl",
    "ret",
    "note",
]
ALWAYS_SHOWN = ["trade_id"]
PERCENT_COLUMNS = ["ret", "mfe", "mae"]
LABELLED_COLUMNS = ["tod", "add_type"]


def show_table(trades: pd.DataFrame, notes: NoteStore) -> None:
    columns = table_columns()
    visible = st.multiselect(
        t("show_columns", LANG),
        [c for c in columns if c not in ALWAYS_SHOWN],
        default=[c for c in DEFAULT_COLUMNS if c not in ALWAYS_SHOWN],
        format_func=lambda c: columns[c] if isinstance(columns[c], str) else columns[c]["label"],
        key="visible_columns",
    )
    shown = ALWAYS_SHOWN + [c for c in columns if c in visible]

    view = trades[[c for c in columns if c != "note"]].copy()
    view["note"] = [note_badge(notes.trade(k)) for k in trades["trade_key"]]
    view["entry_time"] = view["entry_time"].dt.tz_localize(None)
    view[PERCENT_COLUMNS] = view[PERCENT_COLUMNS] * 100
    for col in LABELLED_COLUMNS:
        view[col] = view[col].map(lambda v: label(v, LANG))

    event = st.dataframe(
        view[shown],
        column_config={c: columns[c] for c in shown},
        hide_index=True,
        height=min(480, 38 + 35 * len(view)),  # shrink for short lists
        on_select="rerun",
        selection_mode="single-row",
        key="trade_table",
    )
    rows = event.selection.rows if event else []
    if not rows:
        st.caption(t("select_hint", LANG))
        return
    trade = trades.iloc[rows[0]]
    if st.session_state.get(TABLE_LAST) != trade["trade_key"]:
        # A new row was picked: make it the selected trade everywhere (sidebar notes, replay).
        st.session_state[TABLE_LAST] = st.session_state[SELECTED_TRADE] = trade["trade_key"]
        st.session_state[REPLAY_PICK] = trade["trade_key"]
    left, right = st.columns([3, 1], vertical_alignment="center")
    left.markdown(t("n_selected", LANG, trade_id=trade["trade_id"], label=trade_label(trade)))
    if right.button(t("n_write_trade", LANG), key="note_from_table", width="stretch"):
        open_notes_dialog(notes, trade["day"], trade, LANG)


# ---------------------------------------------------------------- replay


def trade_label(tr: pd.Series) -> str:
    return (
        f"{tr['entry_time']:%Y-%m-%d %H:%M} · {tr['underlying']} "
        f"{tr['strike']:g}{tr['type'][0]} {tr['expiry']:%m/%d} · {tr['ret']:+.1%}"
    )


def show_replay(trades: pd.DataFrame, fills: pd.DataFrame, notes: NoteStore) -> None:
    if trades.empty:
        st.info(t("no_trades", LANG))
        return
    rows = {r.trade_key: r for _, r in trades.iterrows()}
    if st.session_state.get(REPLAY_PICK) not in rows:
        st.session_state.pop(REPLAY_PICK, None)
    key = st.selectbox(
        t("pick_trade", LANG),
        list(rows),
        format_func=lambda k: f"#{rows[k]['trade_id']} · {trade_label(rows[k])}",
        key=REPLAY_PICK,
    )
    st.session_state[SELECTED_TRADE] = key
    tr = rows[key]
    tr_fills = data.fills_for(tr, fills)

    cols = st.columns(5)
    metric(cols[0], t("r_return", LANG), f"{tr['ret']:+.1%}", t("r_pnl", LANG, value=f"${tr['pnl']:,.2f}"))
    metric(cols[1], t("r_mfe", LANG), fmt(tr["mfe"], "+.1%"), t("r_mfe_note", LANG, value=fmt_hold(tr["mfe_min"])))
    metric(cols[2], t("r_mae", LANG), fmt(tr["mae"], "+.1%"))
    held_note = t("r_overnight" if tr["overnight"] else "r_same_day", LANG)
    metric(cols[3], t("r_hold", LANG), fmt_hold(tr["hold_min"]), held_note)
    metric(cols[4], t("r_post15", LANG), fmt(tr.get("post15_high"), "+.1%"), t("r_post15_note", LANG))

    opt, und = data.option_bars(tr), data.underlying_bars(tr)
    if opt.empty:
        st.info(t("no_option_bars", LANG))
    st.plotly_chart(replay_figure(tr, tr_fills, opt, und, LANG))

    note = notes.trade(key)
    with st.container(border=True):
        head, button = st.columns([3, 1], vertical_alignment="center")
        head.markdown(f"**{t('n_note_label', LANG)}** {note_badge(note)}")
        if button.button(t("n_write_trade", LANG), key="note_from_replay", width="stretch"):
            open_notes_dialog(notes, tr["day"], tr, LANG)
        st.markdown(note.text or f"_{t('n_none', LANG)}_")

    with st.expander(t("fills_detail", LANG)):
        view = tr_fills[["exec_time", "code", "qty", "price", "amount", "order_type"]].copy()
        view["exec_time"] = view["exec_time"].dt.tz_localize(None)
        headers = ["c_time", "c_side", "c_contracts", "c_price", "c_amount", "c_order_type"]
        view.columns = [t(h, LANG) for h in headers]
        st.dataframe(view, hide_index=True)


# ---------------------------------------------------------------- page


def main() -> None:
    language_switch()
    st.title(t("page_title", LANG))
    try:
        with st.spinner(t("loading", LANG)):
            trades, fills = load()
    except data.MissingDataError as exc:
        st.error(t("missing_data", LANG, error=exc))
        st.stop()
    notes = NoteStore()

    flt = sidebar_filter(trades)
    selected = flt.apply(trades)
    st.caption(t("filters_caption", LANG) + t("list_sep", LANG).join(flt.describe(LANG)))

    stats_col, _, calendar_col = st.columns([5, 1, 3])
    with calendar_col:
        show_calendar(trades, flt, notes)
    if selected.empty:
        with stats_col:
            st.info(t("no_match", LANG))
        st.stop()
    with stats_col:
        show_summary(summarize(selected))

    sidebar_actions(selected, fills, flt, notes)
    tab_list, tab_replay = st.tabs([t("tab_list", LANG), t("tab_replay", LANG)])
    with tab_list:
        show_table(selected, notes)
    with tab_replay:
        show_replay(selected, fills, notes)


if __name__ == "__main__":
    main()
