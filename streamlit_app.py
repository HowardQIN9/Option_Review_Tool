"""Trade-review dashboard (local).

Run:  streamlit run streamlit_app.py
Needs the outputs of `python run_analysis.py` (output/episodes.csv, output/fills_standardized.csv)
and the minute bars under data/.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import config, data
from dashboard.charts import replay_figure
from dashboard.export_dialog import export_dialog
from dashboard.filters import TradeFilter
from dashboard.stats import Summary, summarize

st.set_page_config(page_title="期权交易复盘", page_icon="📈", layout="wide")


# ---------------------------------------------------------------- data


@st.cache_data(show_spinner="读取交易数据…")
def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    return data.load_episodes(), data.load_fills()


def ordered(values: pd.Series, column: str) -> list[str]:
    present = set(values.dropna())
    order = config.CATEGORY_ORDER.get(column, sorted(present))
    return [v for v in order if v in present] + sorted(present - set(order))


# ---------------------------------------------------------------- sidebar

OUTCOME_CHOICES: dict[str, str | None] = {"全部": None, "盈利": "win", "亏损": "loss"}
OVERNIGHT_CHOICES: dict[str, bool | None] = {"全部": None, "是": True, "否": False}


def sidebar_filter(trades: pd.DataFrame) -> TradeFilter:
    sb = st.sidebar
    sb.header("筛选")

    first, last = trades["day"].min(), trades["day"].max()
    mode = sb.radio("时间", ["时间段", "单日"], horizontal=True)
    if mode == "单日":
        day = sb.date_input("日期", value=last, min_value=first, max_value=last)
        start = end = day
    else:
        picked = sb.date_input("日期范围", value=(first, last), min_value=first, max_value=last)
        start, end = (picked[0], picked[-1]) if isinstance(picked, tuple) and picked else (first, last)

    counts = trades["underlying"].value_counts()
    underlyings = sb.multiselect(
        "标的（可输入搜索）",
        options=list(counts.index),
        format_func=lambda s: f"{s}（{counts[s]} 笔）",
        placeholder="全部标的",
    )

    box = sb.expander("更多条件", expanded=False)

    def multi(label: str, column: str) -> tuple[str, ...]:
        return tuple(box.multiselect(label, ordered(trades[column], column), placeholder="全部"))

    option_types = multi("Call / Put", "type")
    dte_buckets = multi("到期周期（DTE）", "dte_bucket")
    times_of_day = multi("入场时段", "tod")
    hold_buckets = multi("持仓时长", "hold_bucket")
    add_types = multi("建仓方式", "add_type")
    outcome = OUTCOME_CHOICES[box.radio("结果", list(OUTCOME_CHOICES), horizontal=True)]
    overnight = OVERNIGHT_CHOICES[box.radio("隔夜", list(OVERNIGHT_CHOICES), horizontal=True)]

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


# ---------------------------------------------------------------- sections


def fmt_ci(ci: tuple[float, float], fmt: str) -> str:
    return "—" if any(pd.isna(v) for v in ci) else f"{ci[0]:{fmt}} ~ {ci[1]:{fmt}}"


def fmt(value: float, spec: str) -> str:
    return "—" if pd.isna(value) else format(value, spec)


def metric(col, label: str, value: str, note: str = "") -> None:
    """A metric with a neutral note underneath (st.metric's delta would add a misleading arrow)."""
    col.metric(label, value)
    if note:
        col.caption(note)


def fmt_hold(minutes: float) -> str:
    if minutes < 60:
        return f"{minutes:.0f} 分钟"
    if minutes < 24 * 60:
        return f"{minutes / 60:.1f} 小时"
    return f"{minutes / (24 * 60):.1f} 天"


def show_summary(s: Summary) -> None:
    cols = st.columns(6)
    metric(cols[0], "交易笔数", f"{s.n}", f"{s.days} 个交易日")
    metric(cols[1], "胜率", fmt(s.win_rate, ".1%"), f"95% CI {fmt_ci(s.win_rate_ci, '.0%')}")
    metric(cols[2], "净盈亏", f"${s.total_pnl:,.0f}")
    metric(cols[3], "单笔期望", f"${fmt(s.expectancy, ',.1f')}", f"95% CI ${fmt_ci(s.expectancy_ci, ',.0f')}")
    metric(cols[4], "Profit Factor", fmt(s.profit_factor, ".2f"), f"盈亏比 {fmt(s.payoff_ratio, '.2f')}")
    metric(cols[5], "收益率中位数", fmt(s.median_return, ".1%"))
    if s.n < config.SMALL_SAMPLE:
        st.warning(f"只有 {s.n} 笔交易，样本太少，以上统计仅供参考，不能当作结论。", icon="⚠️")
    st.caption("CI 为 95% 置信区间。单笔期望的区间按交易日重抽样计算，保留同一天内交易之间的相关性。")


TABLE_COLUMNS = {
    "trade_id": st.column_config.NumberColumn("编号", format="%d"),
    "entry_time": st.column_config.DatetimeColumn("入场时间", format="YYYY-MM-DD HH:mm"),
    "underlying": "标的",
    "type": "类型",
    "strike": st.column_config.NumberColumn("行权价"),
    "dte_bucket": "DTE",
    "tod": "入场时段",
    "hold_min": st.column_config.NumberColumn("持仓(分钟)", format="%.0f"),
    "overnight": st.column_config.CheckboxColumn("隔夜"),
    "add_type": "建仓方式",
    "contracts": st.column_config.NumberColumn("张数", format="%.0f"),
    "pnl": st.column_config.NumberColumn("净盈亏", format="$%.2f"),
    "ret": st.column_config.NumberColumn("收益率", format="%.1f%%"),
    "mfe": st.column_config.NumberColumn("最大浮盈", format="%.1f%%"),
    "mae": st.column_config.NumberColumn("最大浮亏", format="%.1f%%"),
}
PERCENT_COLUMNS = ["ret", "mfe", "mae"]


def show_table(trades: pd.DataFrame) -> None:
    view = trades[list(TABLE_COLUMNS)].copy()
    view["entry_time"] = view["entry_time"].dt.tz_localize(None)
    view[PERCENT_COLUMNS] = view[PERCENT_COLUMNS] * 100
    st.dataframe(view, column_config=TABLE_COLUMNS, hide_index=True, height=520)


def trade_label(t: pd.Series) -> str:
    return (
        f"#{t['trade_id']} · {t['entry_time']:%Y-%m-%d %H:%M} · {t['underlying']} "
        f"{t['strike']:g}{t['type'][0]} {t['expiry']:%m/%d} · {t['ret']:+.1%}"
    )


def show_replay(trades: pd.DataFrame, fills: pd.DataFrame) -> None:
    if trades.empty:
        st.info("没有符合条件的交易。")
        return
    rows = {int(r.trade_id): r for _, r in trades.iterrows()}
    trade_id = st.selectbox("选择一笔交易", list(rows), format_func=lambda i: trade_label(rows[i]))
    t = rows[trade_id]
    t_fills = data.fills_for(t, fills)

    cols = st.columns(5)
    metric(cols[0], "收益率", f"{t['ret']:+.1%}", f"净盈亏 ${t['pnl']:,.2f}")
    metric(cols[1], "最大浮盈 MFE", fmt(t["mfe"], "+.1%"), f"入场后 {fmt_hold(t['mfe_min'])}")
    metric(cols[2], "最大浮亏 MAE", fmt(t["mae"], "+.1%"))
    metric(cols[3], "持仓", fmt_hold(t["hold_min"]), "隔夜" if t["overnight"] else "当日平仓")
    metric(cols[4], "卖出后 15 分钟最高", fmt(t.get("post15_high"), "+.1%"), "相对卖出价")

    opt, und = data.option_bars(t), data.underlying_bars(t)
    if opt.empty:
        st.info("这笔交易没有期权分钟数据（可能还没下载，或合约当时没有成交）。")
    st.plotly_chart(replay_figure(t, t_fills, opt, und))

    with st.expander("成交明细"):
        view = t_fills[["exec_time", "code", "qty", "price", "amount", "order_type"]].copy()
        view["exec_time"] = view["exec_time"].dt.tz_localize(None)
        st.dataframe(view, hide_index=True)


def sidebar_llm(trades: pd.DataFrame, fills: pd.DataFrame, flt: TradeFilter) -> None:
    sb = st.sidebar
    sb.divider()
    sb.header("LLM 分析")
    sb.caption(f"把当前筛选的 {len(trades)} 笔交易导出，交给 Claude Code 或 Codex 分析。")
    if sb.button("导出给 LLM 分析…", type="primary", width="stretch"):
        export_dialog(trades, fills, flt)


# ---------------------------------------------------------------- page


def main() -> None:
    st.title("期权交易复盘")
    try:
        trades, fills = load()
    except data.MissingDataError as exc:
        st.error(f"找不到分析结果：{exc}")
        st.stop()

    flt = sidebar_filter(trades)
    selected = flt.apply(trades)
    st.caption("筛选条件：" + "；".join(flt.describe()))

    if selected.empty:
        st.info("没有符合条件的交易，试试放宽筛选条件。")
        st.stop()

    sidebar_llm(selected, fills, flt)
    show_summary(summarize(selected))
    tab_list, tab_replay = st.tabs(["交易列表", "单笔复盘"])
    with tab_list:
        show_table(selected)
    with tab_replay:
        show_replay(selected, fills)


if __name__ == "__main__":
    main()
