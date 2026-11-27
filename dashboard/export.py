"""Build an "analysis pack": a folder an LLM coding agent (Claude Code, Codex) can open and analyse.

The pack contains the filtered trades, their fills, a data dictionary and the user's prompt, written
in the chosen language. With `include_amounts=False` every column that reveals dollar amounts or
position size is dropped, so only percentages, ratios, per-share prices and market context leave
the machine.
"""

from __future__ import annotations

import io
import math
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config
from .filters import TradeFilter
from .i18n import DEFAULT_LANG, Lang, label, tag_label
from .notes import NoteStore
from .stats import Summary, summarize


@dataclass(frozen=True)
class Column:
    zh: str
    en: str
    sensitive: bool = False  # reveals a dollar amount or position size

    def describe(self, lang: Lang) -> str:
        return self.zh if lang == "zh" else self.en


TRADE_COLUMNS: dict[str, Column] = {
    "trade_id": Column("交易编号（本次导出内唯一）", "Trade ID (unique within this export)"),
    "day": Column("开仓日期", "Entry date"),
    "entry_time": Column("首次买入时间（美东）", "First buy time (US Eastern)"),
    "exit_time": Column(
        "最后卖出时间（美东）；到期作废为到期日 16:00", "Last sell time (US Eastern); 16:00 on expiry if it expired"
    ),
    "underlying": Column("标的代码", "Underlying ticker"),
    "type": Column("Call 或 Put", "Call or Put"),
    "strike": Column("行权价", "Strike price"),
    "expiry": Column("到期日", "Expiry date"),
    "dte": Column("开仓时距离到期的交易日数", "Trading days to expiry at entry"),
    "dte_bucket": Column("DTE 分组", "DTE bucket"),
    "tod": Column("入场时段（美东）", "Entry time-of-day bucket (US Eastern)"),
    "hold_min": Column("持仓时长（分钟）", "Holding time (minutes)"),
    "hold_bucket": Column("持仓时长分组", "Holding-time bucket"),
    "overnight": Column("是否持仓过夜", "Held overnight"),
    "add_type": Column(
        "建仓方式：单次建仓 / 价格更低时加仓（摊平）/ 价格更高时加仓（加码）",
        "Position building: single entry / added at a lower price (averaging down) / added higher (pyramiding)",
    ),
    "n_buys": Column("买入成交次数", "Number of buy fills"),
    "n_sells": Column("卖出成交次数", "Number of sell fills"),
    "expired": Column("是否到期作废", "Expired worthless"),
    "avg_entry": Column(
        "平均买入价（每股期权价格，1 张 = 100 股）", "Average entry price (per share; 1 contract = 100)"
    ),
    "avg_exit": Column("平均卖出价（每股期权价格）", "Average exit price (per share)"),
    "ret": Column(
        "收益率 = 净盈亏 / 买入成本（含手续费）；-0.5 表示 -50%", "Return = net P&L / cost incl. fees; -0.5 = -50%"
    ),
    "win": Column("是否盈利", "Winning trade"),
    "mfe": Column(
        "最大浮盈：持仓期间期权最高价相对买入均价的涨幅", "MFE: best option high during the hold vs. avg entry"
    ),
    "mae": Column(
        "最大浮亏：持仓期间期权最低价相对买入均价的跌幅", "MAE: worst option low during the hold vs. avg entry"
    ),
    "mfe_min": Column("入场后多少分钟达到最大浮盈", "Minutes after entry when MFE was reached"),
    "post15_high": Column(
        "卖出后 15 分钟内期权最高价相对卖出价的涨幅（判断是否卖早）",
        "Best option high within 15 min after exit vs. exit price (sold too early?)",
    ),
    "post15_low": Column(
        "卖出后 15 分钟内期权最低价相对卖出价的跌幅（判断是否卖得及时）",
        "Worst option low within 15 min after exit vs. exit price (sold in time?)",
    ),
    "post30_high": Column("卖出后 30 分钟内期权最高价相对卖出价的涨幅", "Best option high within 30 min after exit"),
    "direction_class": Column("方向判断 × 结果：方向对/错 · 盈利/亏损", "Direction × outcome: right/wrong · win/loss"),
    "d_und_move": Column(
        "持仓期间标的朝有利方向的涨跌幅（Call 看涨、Put 看跌为正）",
        "Underlying move during the hold in the trade's favour (positive = up for calls, down for puts)",
    ),
    "d_ret_15": Column(
        "入场前 15 分钟标的朝交易方向的涨跌幅", "Underlying move in the trade direction, 15 min before entry"
    ),
    "d_fwd_15": Column(
        "入场后 15 分钟标的朝交易方向的涨跌幅", "Underlying move in the trade direction, 15 min after entry"
    ),
    "d_range_pos": Column(
        "入场时标的在当日区间中的位置（按交易方向；1 = 当日最有利的极端位置）",
        "Underlying position in the day's range at entry, in trade direction (1 = the extreme in the trade's favour)",
    ),
    "rvol_5": Column(
        "入场前 5 分钟成交量相对同时段平常水平的倍数", "Volume in the 5 min before entry vs. normal for that time"
    ),
    "trend_aligned": Column("是否顺着前 5 分钟的走势入场", "Entered in the direction of the prior 5-min move"),
    "iv_entry": Column(
        "入场时隐含波动率（Black-Scholes 反推，0.30 = 30%）", "Implied volatility at entry (BS; 0.30 = 30%)"
    ),
    "delta_entry": Column("入场时 Delta", "Delta at entry"),
    "extrinsic_share": Column("入场时外在价值占权利金的比例", "Extrinsic value as a share of premium at entry"),
    "cost_vs_median20": Column(
        "本笔仓位金额相对最近 20 笔中位数的倍数", "Position size vs. the median of the previous 20 trades"
    ),
    "contracts": Column("买入总张数", "Total contracts bought", sensitive=True),
    "max_position": Column("最大同时持有张数", "Max contracts held at once", sensitive=True),
    "cost": Column("买入总成本（美元，含手续费）", "Total cost (USD, incl. fees)", sensitive=True),
    "proceeds": Column("卖出总收入（美元，扣手续费）", "Total proceeds (USD, net of fees)", sensitive=True),
    "fees": Column("手续费合计（美元）", "Total fees (USD)", sensitive=True),
    "pnl": Column("净盈亏（美元）", "Net P&L (USD)", sensitive=True),
}

FILL_COLUMNS: dict[str, Column] = {
    "trade_id": Column("所属交易编号", "Trade ID"),
    "exec_time": Column("成交时间（美东，精确到毫秒）", "Execution time (US Eastern, millisecond precision)"),
    "code": Column("BTO = 买入开仓，STC = 卖出平仓", "BTO = buy to open, STC = sell to close"),
    "price": Column("成交价（每股期权价格）", "Fill price (per share)"),
    "order_type": Column("下单方式：limit 限价 / market 市价", "Order type: limit / market"),
    "qty": Column("成交张数", "Contracts filled", sensitive=True),
    "amount": Column("成交金额（美元，含手续费）", "Fill amount (USD, incl. fees)", sensitive=True),
}

NOTE_COLUMNS: dict[str, Column] = {
    "note": Column("我写的单笔笔记（入场理由、执行、反思）", "My note on the trade (reasoning, execution, lessons)"),
    "note_tags": Column("我给这笔交易打的标签，用 ; 分隔", "Tags I gave the trade, separated by ;"),
}

# Categorical columns whose (Chinese) values are translated in English exports.
TRANSLATED_VALUES = ["tod", "add_type", "direction_class"]

PROMPT_TEMPLATES: dict[Lang, dict[str, str]] = {
    "zh": {
        "自由提问": "",
        "复盘这些交易": (
            "请复盘这些交易：整体表现如何？盈利和亏损主要来自哪些类型的交易？"
            "入场、持仓、出场各有什么问题？给出 3 条最值得改进的地方，每条都要有数据支持。"
        ),
        "亏损来源": (
            "这些交易的亏损主要来自哪里？请从方向判断、持仓时长与隔夜、建仓方式（是否摊平）、"
            "出场时机（MFE/MAE、卖出后走势）几个角度拆解，并说明每个结论的样本量。"
        ),
        "出场时机": (
            "请分析出场时机：盈利交易兑现了多少最大浮盈？亏损交易里有多少曾经浮盈？"
            "卖出后价格通常怎么走？我更常卖早还是卖晚？"
        ),
        "入场时机": (
            "请分析入场时机：入场前后标的怎么走？我是在走势启动时入场，还是追在末端？"
            "放量、顺势、入场时段和结果有没有关系？"
        ),
        "复盘单日": (
            "请按时间顺序逐笔复盘这一天的交易：每笔的入场理由可能是什么，执行得怎么样，"
            "交易之间有没有情绪化的迹象（例如亏损后很快再入场、放大仓位）。"
        ),
    },
    "en": {
        "Ask anything": "",
        "Review these trades": (
            "Review these trades: how did they perform overall? Which kinds of trades drove the wins and the losses? "
            "What went wrong at entry, during the hold and at exit? Give the 3 most valuable improvements, "
            "each backed by data."
        ),
        "Where the losses come from": (
            "Where do the losses come from? Break them down by direction calls, holding time and overnight holds, "
            "position building (averaging down or not) and exit timing (MFE/MAE, price after exit), "
            "and state the sample size behind each conclusion."
        ),
        "Exit timing": (
            "Analyse exit timing: how much of the maximum open profit did winning trades capture? How many losing "
            "trades were in profit at some point? What does the price usually do after I sell? "
            "Do I tend to sell too early or too late?"
        ),
        "Entry timing": (
            "Analyse entry timing: how does the underlying move before and after entry? Do I enter as a move starts, "
            "or chase it near the end? Do volume, trend alignment and time of day relate to the outcome?"
        ),
        "Review one day": (
            "Review this day's trades one by one in time order: what was the likely reason for each entry, how well "
            "was it executed, and are there signs of emotional trading between trades (e.g. re-entering quickly "
            "after a loss, increasing size)?"
        ),
    },
}

AGENT_INSTRUCTIONS: dict[Lang, str] = {
    "zh": """\
你是一位严谨的交易复盘分析师。这个文件夹里是我的一部分期权交易记录（已按条件筛选），请按下面的要求分析。

## 文件
- `trades.csv`：每行一笔完整交易（同一合约从开仓到平仓）
- `fills.csv`：每行一次成交，用 `trade_id` 关联到交易
- `DATA_DICTIONARY.md`：每一列的含义
- `summary.md`：筛选条件和整体统计

## 要求
1. **用代码计算**（例如 Python + pandas），不要凭印象估计数字。给出结论时附上计算依据。
2. **注意样本量**：分组后少于 30 笔的结论要明确标为"初步、不可靠"。能给置信区间就给。
3. **区分相关和因果**：例如持仓时间长往往是亏损的结果，而不是原因。
4. 全部交易都是买入期权（没有卖出开仓）。
{amount_note}

## 我的问题
{prompt}
""",
    "en": """\
You are a rigorous trading-review analyst. This folder contains part of my options trading history \
(already filtered). Please analyse it as follows.

## Files
- `trades.csv`: one row per round-trip trade (one contract, from opening to closing)
- `fills.csv`: one row per fill, linked to trades by `trade_id`
- `DATA_DICTIONARY.md`: what every column means
- `summary.md`: the filters used and the headline statistics

## Requirements
1. **Compute with code** (e.g. Python + pandas); do not estimate numbers by eye. Show how each conclusion was computed.
2. **Mind the sample size**: label any conclusion drawn from fewer than 30 trades as "preliminary, unreliable". \
Give confidence intervals where you can.
3. **Separate correlation from causation**: e.g. long holding times are often a result of losing, not a cause.
4. All trades are long options (no option selling).
{amount_note}

## My question
{prompt}
""",
}

AMOUNT_NOTE_HIDDEN: dict[Lang, str] = {
    "zh": "5. 为了保护隐私，**美元金额和仓位张数已被移除**。请只用收益率、比例和价格进行分析，不要试图反推金额。",
    "en": "5. For privacy, **dollar amounts and position sizes have been removed**. Use only returns, ratios and "
    "prices, and do not try to reconstruct the amounts.",
}

EMPTY_PROMPT: dict[Lang, str] = {"zh": "（请自由分析）", "en": "(Analyse freely.)"}

SUMMARY_TEXT: dict[Lang, dict[str, str]] = {
    "zh": {
        "title": "筛选条件与整体统计",
        "filters": "筛选条件",
        "stats": "整体统计",
        "header": "| 指标 | 数值 |",
        "n": "交易笔数 / 交易天数",
        "win": "胜率（95% CI）",
        "median": "单笔收益率中位数",
        "payoff": "盈亏比（平均盈利 / 平均亏损）",
        "pnl": "净盈亏",
        "exp": "单笔期望（95% CI，按交易日重抽样）",
        "small": "> 注意：只有 {n} 笔交易，样本太少，统计结论不可靠。",
        "dict_title": "数据字典",
        "dict_header": "| 列 | 含义 |",
        "daily_title": "当日笔记",
        "daily_file": "- `daily_notes.md`：我写的当日笔记（市场情况、心态、计划）",
    },
    "en": {
        "title": "Filters and headline statistics",
        "filters": "Filters",
        "stats": "Headline statistics",
        "header": "| Metric | Value |",
        "n": "Trades / trading days",
        "win": "Win rate (95% CI)",
        "median": "Median return per trade",
        "payoff": "Payoff ratio (avg win / avg loss)",
        "pnl": "Net P&L",
        "exp": "Expectancy per trade (95% CI, day-block bootstrap)",
        "small": "> Note: only {n} trades. The sample is too small for reliable conclusions.",
        "dict_title": "Data dictionary",
        "dict_header": "| Column | Meaning |",
        "daily_title": "Day notes",
        "daily_file": "- `daily_notes.md`: my notes for each day (market conditions, mindset, plan)",
    },
}


@dataclass(frozen=True)
class ExportPack:
    folder: Path
    files: dict[str, str]  # filename -> text content

    def zip_bytes(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, text in self.files.items():
                zf.writestr(name, text)
        return buf.getvalue()


def export_columns(spec: dict[str, Column], include_amounts: bool) -> list[str]:
    """Columns to export; dollar/size columns are dropped unless `include_amounts`."""
    return [name for name, col in spec.items() if include_amounts or not col.sensitive]


def _fmt(x: float, spec: str) -> str:
    return "—" if math.isnan(x) else format(x, spec)


def _fmt_ci(ci: tuple[float, float], spec: str) -> str:
    return "—" if any(math.isnan(v) for v in ci) else f"{ci[0]:{spec}} ~ {ci[1]:{spec}}"


def summary_markdown(s: Summary, flt: TradeFilter, include_amounts: bool, lang: Lang = DEFAULT_LANG) -> str:
    tx = SUMMARY_TEXT[lang]
    lines = [f"# {tx['title']}", "", f"## {tx['filters']}", ""]
    lines += [f"- {c}" for c in flt.describe(lang)]
    lines += [
        "",
        f"## {tx['stats']}",
        "",
        tx["header"],
        "|---|---|",
        f"| {tx['n']} | {s.n} / {s.days} |",
        f"| {tx['win']} | {_fmt(s.win_rate, '.1%')} ({_fmt_ci(s.win_rate_ci, '.0%')}) |",
        f"| {tx['median']} | {_fmt(s.median_return, '.1%')} |",
        f"| Profit Factor | {_fmt(s.profit_factor, '.2f')} |",
        f"| {tx['payoff']} | {_fmt(s.payoff_ratio, '.2f')} |",
    ]
    if include_amounts:
        lines += [
            f"| {tx['pnl']} | ${s.total_pnl:,.0f} |",
            f"| {tx['exp']} | ${_fmt(s.expectancy, ',.1f')} ({_fmt_ci(s.expectancy_ci, ',.0f')}) |",
        ]
    if s.n < config.SMALL_SAMPLE:
        lines += ["", tx["small"].format(n=s.n)]
    return "\n".join(lines) + "\n"


def dictionary_markdown(include_amounts: bool, lang: Lang = DEFAULT_LANG, include_notes: bool = False) -> str:
    tx = SUMMARY_TEXT[lang]
    out = [f"# {tx['dict_title']}", ""]
    trade_spec = {**TRADE_COLUMNS, **NOTE_COLUMNS} if include_notes else TRADE_COLUMNS
    for title, spec in (("trades.csv", trade_spec), ("fills.csv", FILL_COLUMNS)):
        out += [f"## {title}", "", tx["dict_header"], "|---|---|"]
        out += [f"| `{c}` | {spec[c].describe(lang)} |" for c in export_columns(spec, include_amounts)]
        out.append("")
    return "\n".join(out)


def _with_notes(trades: pd.DataFrame, source: pd.DataFrame, store: NoteStore, lang: Lang) -> pd.DataFrame:
    notes = store.trade_notes(source["trade_key"])
    out = trades.copy()
    out["note"] = notes["note"].to_numpy()
    out["note_tags"] = [";".join(tag_label(tag, lang) for tag in tags) for tags in notes["note_tags"]]
    return out


def daily_notes_markdown(days: list, store: NoteStore, lang: Lang) -> str:
    out = [f"# {SUMMARY_TEXT[lang]['daily_title']}", ""]
    for day in sorted(days):
        note = store.day(day)
        if note.is_empty:
            continue
        out += [f"## {day}", ""]
        if note.tags:
            out += ["`" + "` `".join(tag_label(tag, lang) for tag in note.tags) + "`", ""]
        if note.text:
            out += [note.text, ""]
    return "\n".join(out)


def _localize_values(trades: pd.DataFrame, lang: Lang) -> pd.DataFrame:
    if lang == "zh":
        return trades
    out = trades.copy()
    for col in TRANSLATED_VALUES:
        if col in out:
            out[col] = out[col].map(lambda v: label(v, lang))
    return out


def build_pack(
    trades: pd.DataFrame,
    fills: pd.DataFrame,
    flt: TradeFilter,
    prompt: str,
    include_amounts: bool,
    lang: Lang = DEFAULT_LANG,
    notes: NoteStore | None = None,
    export_dir: Path = config.EXPORT_DIR,
    now: datetime | None = None,
) -> ExportPack:
    """Assemble the pack's file contents (nothing is written to disk here).

    Journal notes are included only when a `notes` store is passed.
    """
    from .data import fills_for  # local import keeps this module importable without data files

    trade_cols = export_columns(TRADE_COLUMNS, include_amounts)
    fill_cols = export_columns(FILL_COLUMNS, include_amounts)

    fill_parts = [fills_for(t, fills).assign(trade_id=t["trade_id"]) for _, t in trades.iterrows()]
    trade_fills = pd.concat(fill_parts) if fill_parts else pd.DataFrame(columns=fill_cols)

    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    amount_note = "" if include_amounts else AMOUNT_NOTE_HIDDEN[lang]
    instructions = AGENT_INSTRUCTIONS[lang]
    if notes is not None:
        instructions = instructions.replace("- `summary.md`", SUMMARY_TEXT[lang]["daily_file"] + "\n- `summary.md`")
    trade_table = _localize_values(trades[trade_cols], lang)
    if notes is not None:
        trade_table = _with_notes(trade_table, trades, notes, lang)
    files = {
        "PROMPT.md": instructions.format(amount_note=amount_note, prompt=prompt.strip() or EMPTY_PROMPT[lang]),
        "summary.md": summary_markdown(summarize(trades), flt, include_amounts, lang),
        "DATA_DICTIONARY.md": dictionary_markdown(include_amounts, lang, include_notes=notes is not None),
        "trades.csv": trade_table.to_csv(index=False),
        "fills.csv": trade_fills[fill_cols].to_csv(index=False),
    }
    if notes is not None:
        files["daily_notes.md"] = daily_notes_markdown(list(trades["day"].unique()), notes, lang)
    return ExportPack(folder=export_dir / f"pack_{stamp}", files=files)


def write_pack(pack: ExportPack) -> Path:
    pack.folder.mkdir(parents=True, exist_ok=False)
    for name, text in pack.files.items():
        (pack.folder / name).write_text(text, encoding="utf-8")
    return pack.folder
