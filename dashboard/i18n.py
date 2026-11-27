"""User-facing text in Chinese and English.

UI strings live in `STRINGS` (looked up with `t`), and the categorical values produced by
run_analysis.py (which are stored in Chinese) are translated for display with `label`.
"""

from __future__ import annotations

from typing import Literal

Lang = Literal["zh", "en"]
LANGUAGES: dict[Lang, str] = {"zh": "中文", "en": "English"}
DEFAULT_LANG: Lang = "zh"

STRINGS: dict[str, dict[Lang, str]] = {
    # page
    "page_title": {"zh": "期权交易复盘", "en": "Option Trade Review"},
    "loading": {"zh": "读取交易数据…", "en": "Loading trades…"},
    "missing_data": {"zh": "找不到分析结果：{error}", "en": "Analysis results not found: {error}"},
    "filters_caption": {"zh": "筛选条件：", "en": "Filters: "},
    "list_sep": {"zh": "；", "en": "; "},
    "no_match": {"zh": "没有符合条件的交易，试试放宽筛选条件。", "en": "No trades match. Try loosening the filters."},
    "tab_list": {"zh": "交易列表", "en": "Trades"},
    "tab_replay": {"zh": "单笔复盘", "en": "Trade replay"},
    # sidebar: filters
    "language": {"zh": "语言 / Language", "en": "Language / 语言"},
    "filters": {"zh": "筛选", "en": "Filters"},
    "date_mode": {"zh": "时间", "en": "Dates"},
    "mode_range": {"zh": "时间段", "en": "Range"},
    "mode_day": {"zh": "单日", "en": "Single day"},
    "date": {"zh": "日期", "en": "Date"},
    "date_range": {"zh": "日期范围", "en": "Date range"},
    "ticker": {"zh": "标的（可输入搜索）", "en": "Ticker (type to search)"},
    "ticker_count": {"zh": "{symbol}（{n} 笔）", "en": "{symbol} ({n} trades)"},
    "all_tickers": {"zh": "全部标的", "en": "All tickers"},
    "more_filters": {"zh": "更多条件", "en": "More filters"},
    "all": {"zh": "全部", "en": "All"},
    "f_type": {"zh": "Call / Put", "en": "Call / Put"},
    "f_dte": {"zh": "到期周期（DTE）", "en": "Days to expiry (DTE)"},
    "f_tod": {"zh": "入场时段", "en": "Entry time of day"},
    "f_hold": {"zh": "持仓时长", "en": "Holding time"},
    "f_add": {"zh": "建仓方式", "en": "Position building"},
    "f_outcome": {"zh": "结果", "en": "Outcome"},
    "f_overnight": {"zh": "隔夜", "en": "Overnight"},
    "win": {"zh": "盈利", "en": "Win"},
    "loss": {"zh": "亏损", "en": "Loss"},
    "yes": {"zh": "是", "en": "Yes"},
    "no": {"zh": "否", "en": "No"},
    # sidebar: LLM
    "llm_header": {"zh": "LLM 分析", "en": "LLM analysis"},
    "llm_caption": {
        "zh": "把当前筛选的 {n} 笔交易导出，交给 Claude Code 或 Codex 分析。",
        "en": "Export the {n} filtered trades for Claude Code or Codex to analyse.",
    },
    "llm_button": {"zh": "导出给 LLM 分析…", "en": "Export for LLM analysis…"},
    # summary
    "m_trades": {"zh": "交易笔数", "en": "Trades"},
    "m_days": {"zh": "{n} 个交易日", "en": "{n} trading days"},
    "m_win_rate": {"zh": "胜率", "en": "Win rate"},
    "m_net_pnl": {"zh": "净盈亏", "en": "Net P&L"},
    "m_expectancy": {"zh": "单笔期望", "en": "Expectancy / trade"},
    "m_payoff": {"zh": "盈亏比 {value}", "en": "Payoff ratio {value}"},
    "m_median_ret": {"zh": "收益率中位数", "en": "Median return"},
    "small_sample": {
        "zh": "只有 {n} 笔交易，样本太少，以上统计仅供参考，不能当作结论。",
        "en": "Only {n} trades: the sample is too small, so treat these statistics as indicative, not conclusive.",
    },
    "ci_caption": {
        "zh": "CI 为 95% 置信区间。单笔期望的区间按交易日重抽样计算，保留同一天内交易之间的相关性。",
        "en": "CI = 95% confidence interval. The expectancy interval resamples whole trading days, "
        "keeping the correlation between trades on the same day.",
    },
    # table
    "c_id": {"zh": "编号", "en": "ID"},
    "c_entry": {"zh": "入场时间", "en": "Entry time"},
    "c_ticker": {"zh": "标的", "en": "Ticker"},
    "c_type": {"zh": "类型", "en": "Type"},
    "c_strike": {"zh": "行权价", "en": "Strike"},
    "c_dte": {"zh": "DTE", "en": "DTE"},
    "c_tod": {"zh": "入场时段", "en": "Time of day"},
    "c_hold": {"zh": "持仓(分钟)", "en": "Hold (min)"},
    "c_overnight": {"zh": "隔夜", "en": "Overnight"},
    "c_add": {"zh": "建仓方式", "en": "Building"},
    "c_contracts": {"zh": "张数", "en": "Contracts"},
    "c_pnl": {"zh": "净盈亏", "en": "Net P&L"},
    "c_ret": {"zh": "收益率", "en": "Return"},
    "c_mfe": {"zh": "最大浮盈", "en": "MFE"},
    "c_mae": {"zh": "最大浮亏", "en": "MAE"},
    "c_time": {"zh": "成交时间", "en": "Time"},
    "c_side": {"zh": "方向", "en": "Side"},
    "c_price": {"zh": "价格", "en": "Price"},
    "c_amount": {"zh": "金额", "en": "Amount"},
    "c_order_type": {"zh": "下单方式", "en": "Order type"},
    # replay
    "no_trades": {"zh": "没有符合条件的交易。", "en": "No matching trades."},
    "pick_trade": {"zh": "选择一笔交易", "en": "Pick a trade"},
    "r_return": {"zh": "收益率", "en": "Return"},
    "r_pnl": {"zh": "净盈亏 {value}", "en": "Net P&L {value}"},
    "r_mfe": {"zh": "最大浮盈 MFE", "en": "Max favourable (MFE)"},
    "r_mfe_note": {"zh": "入场后 {value}", "en": "{value} after entry"},
    "r_mae": {"zh": "最大浮亏 MAE", "en": "Max adverse (MAE)"},
    "r_hold": {"zh": "持仓", "en": "Held"},
    "r_overnight": {"zh": "隔夜", "en": "Overnight"},
    "r_same_day": {"zh": "当日平仓", "en": "Closed same day"},
    "r_post15": {"zh": "卖出后 15 分钟最高", "en": "Best in 15 min after exit"},
    "r_post15_note": {"zh": "相对卖出价", "en": "vs. exit price"},
    "no_option_bars": {
        "zh": "这笔交易没有期权分钟数据（可能还没下载，或合约当时没有成交）。",
        "en": "No option minute bars for this trade (not downloaded yet, or the contract did not trade).",
    },
    "fills_detail": {"zh": "成交明细", "en": "Fills"},
    "minutes": {"zh": "{value:.0f} 分钟", "en": "{value:.0f} min"},
    "hours": {"zh": "{value:.1f} 小时", "en": "{value:.1f} h"},
    "days": {"zh": "{value:.1f} 天", "en": "{value:.1f} days"},
    # chart
    "chart_option": {"zh": "期权 {occ}（1 分钟成交价）", "en": "Option {occ} (1-min trade price)"},
    "chart_underlying": {"zh": "标的 {symbol}", "en": "Underlying {symbol}"},
    "chart_option_price": {"zh": "期权价格", "en": "Option price"},
    "chart_underlying_price": {"zh": "标的价格", "en": "Underlying price"},
    "chart_buy": {"zh": "买入", "en": "Buy"},
    "chart_sell": {"zh": "卖出", "en": "Sell"},
    "chart_qty": {"zh": "张", "en": "contracts"},
    "chart_price": {"zh": "价格", "en": "Price"},
    "chart_avg_entry": {"zh": "买入均价", "en": "Avg entry"},
    # export dialog
    "x_title": {"zh": "导出给 LLM 分析", "en": "Export for LLM analysis"},
    "x_intro": {
        "zh": "把当前筛选出的 **{n} 笔交易**导出成一个分析包文件夹，再用 **Claude Code** 或 **Codex** "
        "打开这个文件夹，对它说：**“读 PROMPT.md，按要求开始分析。”**",
        "en": "Export the **{n} filtered trades** as an analysis-pack folder, open the folder in "
        '**Claude Code** or **Codex**, and say: **"Read PROMPT.md and start the analysis."**',
    },
    "x_amounts": {"zh": "包含美元金额和仓位张数", "en": "Include dollar amounts and position size"},
    "x_amounts_help": {
        "zh": "关闭时，盈亏金额、成本、手续费、张数都会被移除，只保留收益率、比例和每股价格。",
        "en": "When off, P&L, cost, fees and contract counts are removed; "
        "only returns, ratios and per-share prices remain.",
    },
    "x_amounts_on": {
        "zh": "分析包会包含你的真实盈亏金额。用 LLM 分析时，这些数据会发送给 Anthropic 或 OpenAI。",
        "en": "The pack will contain your real P&L. When an LLM analyses it, this data is sent to Anthropic or OpenAI.",
    },
    "x_amounts_off": {
        "zh": "不包含金额：只发送收益率、比例、价格和行情数据。",
        "en": "No amounts: only returns, ratios, prices and market data are included.",
    },
    "x_template": {"zh": "Prompt 模板", "en": "Prompt template"},
    "x_question": {"zh": "你的问题（可修改）", "en": "Your question (editable)"},
    "x_preview": {"zh": "预览将导出的内容", "en": "Preview the export"},
    "x_write": {"zh": "生成分析包文件夹", "en": "Create pack folder"},
    "x_zip": {"zh": "下载为 ZIP", "en": "Download ZIP"},
    "x_done": {"zh": "已生成：`{folder}`", "en": "Created: `{folder}`"},
    "x_open": {"zh": "在资源管理器中打开", "en": "Open in Explorer"},
    # notes
    "notes_header": {"zh": "笔记", "en": "Journal"},
    "notes_caption": {
        "zh": "写当日笔记，或当前选中交易的笔记。",
        "en": "Write a note for the day, or for the selected trade.",
    },
    "notes_button": {"zh": "写笔记…", "en": "Write a note…"},
    "n_title": {"zh": "交易笔记", "en": "Journal"},
    "n_tab_day": {"zh": "当日笔记 · {day}", "en": "Day · {day}"},
    "n_tab_trade": {"zh": "单笔笔记 · #{trade_id}", "en": "Trade · #{trade_id}"},
    "n_day_hint": {"zh": "当天的市场情况、心态、计划…", "en": "Market conditions, mindset, plan for the day…"},
    "n_trade_hint": {
        "zh": "入场理由、执行得怎么样、学到了什么…",
        "en": "Why I entered, how I executed, what I learned…",
    },
    "n_tags": {"zh": "标签", "en": "Tags"},
    "n_save": {"zh": "保存", "en": "Save"},
    "n_saved": {"zh": "已保存", "en": "Saved"},
    "n_no_trade": {
        "zh": "在交易列表里选中一行，或在单笔复盘里选择一笔交易，就可以写单笔笔记。",
        "en": "Select a row in the trade list, or pick a trade in the replay, to write a trade note.",
    },
    "n_updated": {"zh": "上次保存：{when}", "en": "Last saved: {when}"},
    "n_selected": {"zh": "已选中 #{trade_id} · {label}", "en": "Selected #{trade_id} · {label}"},
    "n_write_trade": {"zh": "写这笔交易的笔记", "en": "Note on this trade"},
    "n_note_label": {"zh": "笔记", "en": "Note"},
    "n_none": {"zh": "还没有笔记。", "en": "No note yet."},
    "c_note": {"zh": "笔记", "en": "Note"},
    "show_columns": {"zh": "显示列", "en": "Columns"},
    "select_hint": {
        "zh": "点击左侧勾选框选中一笔交易，可以写笔记。",
        "en": "Tick a row to select a trade and write a note.",
    },
    # calendar
    "cal_weekdays": {"zh": "一,二,三,四,五", "en": "Mon,Tue,Wed,Thu,Fri"},
    "cal_trades": {"zh": "{n} 笔交易", "en": "{n} trades"},
    "cal_no_trades": {"zh": "无交易", "en": "No trades"},
    "cal_has_note": {"zh": "有笔记", "en": "Has a note"},
    "cal_hint": {
        "zh": "点击日期看当天，点击左侧 W 看整周，点击月份看整月。",
        "en": "Click a day, a week (W, left) or the month name to filter.",
    },
    "cal_week": {"zh": "周", "en": "Wk"},
    "cal_week_hint": {"zh": "点击查看整周", "en": "Click to see the week"},
    "cal_all": {"zh": "全部", "en": "All"},
    "cal_month_help": {"zh": "查看整月的交易", "en": "Show the whole month"},
    "cal_all_help": {"zh": "查看全部日期的交易", "en": "Show all dates"},
    "x_notes": {"zh": "包含我的笔记", "en": "Include my journal notes"},
    "x_notes_help": {
        "zh": "打开后，单笔笔记和标签会加到 trades.csv，当日笔记写入 daily_notes.md。",
        "en": "When on, trade notes and tags are added to trades.csv and day notes go into daily_notes.md.",
    },
    # filter descriptions
    "d_date": {"zh": "日期：{start} 至 {end}", "en": "Date: {start} to {end}"},
    "d_earliest": {"zh": "最早", "en": "earliest"},
    "d_latest": {"zh": "最新", "en": "latest"},
    "d_ticker": {"zh": "标的", "en": "Ticker"},
    "d_item": {"zh": "{name}：{values}", "en": "{name}: {values}"},
    "d_join": {"zh": "、", "en": ", "},
    "d_none": {"zh": "无筛选（全部交易）", "en": "No filters (all trades)"},
}

# Categorical values written by run_analysis.py, translated for display.
VALUE_LABELS: dict[str, dict[Lang, str]] = {
    "09:30前(盘前)": {"zh": "09:30前(盘前)", "en": "Before 09:30 (pre-market)"},
    "16:00后(收盘后)": {"zh": "16:00后(收盘后)", "en": "After 16:00 (post-close)"},
    "单次建仓": {"zh": "单次建仓", "en": "Single entry"},
    "加仓-价格更低(摊平)": {"zh": "加仓-价格更低(摊平)", "en": "Added lower (averaging down)"},
    "加仓-价格更高(加码)": {"zh": "加仓-价格更高(加码)", "en": "Added higher (pyramiding)"},
    "方向对·盈利": {"zh": "方向对·盈利", "en": "Right direction · win"},
    "方向对·亏损": {"zh": "方向对·亏损", "en": "Right direction · loss"},
    "方向错·盈利": {"zh": "方向错·盈利", "en": "Wrong direction · win"},
    "方向错·亏损": {"zh": "方向错·亏损", "en": "Wrong direction · loss"},
}


def t(key: str, lang: Lang, **kwargs: object) -> str:
    """Translate a UI string and fill in its placeholders."""
    text = STRINGS[key][lang]
    return text.format(**kwargs) if kwargs else text


def label(value: object, lang: Lang) -> str:
    """Display label for a categorical value; values without a translation are shown as-is."""
    return VALUE_LABELS.get(str(value), {}).get(lang, str(value))


# Journal tag ids (see notes.TAGS) -> display labels.
TAG_LABELS: dict[str, dict[Lang, str]] = {
    "planned": {"zh": "计划内", "en": "Planned"},
    "impulsive": {"zh": "冲动", "en": "Impulsive"},
    "chased": {"zh": "追涨杀跌", "en": "Chased"},
    "fomo": {"zh": "FOMO", "en": "FOMO"},
    "revenge": {"zh": "报复性交易", "en": "Revenge trade"},
    "followed_rules": {"zh": "遵守规则", "en": "Followed rules"},
    "broke_rules": {"zh": "违反规则", "en": "Broke rules"},
    "cut_loss_in_time": {"zh": "止损及时", "en": "Cut loss in time"},
    "cut_loss_late": {"zh": "止损太晚", "en": "Cut loss late"},
    "took_profit_early": {"zh": "止盈过早", "en": "Took profit early"},
}


def tag_label(tag: str, lang: Lang) -> str:
    return TAG_LABELS.get(tag, {}).get(lang, tag)


def month_title(year: int, month: int, lang: Lang) -> str:
    if lang == "zh":
        return f"{year} 年 {month} 月"
    return f"{_EN_MONTHS[month - 1]} {year}"


_EN_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
