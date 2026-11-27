"""Build an "analysis pack": a folder an LLM coding agent (Claude Code, Codex) can open and analyse.

The pack contains the filtered trades, their fills, a data dictionary and the user's prompt.
With `include_amounts=False` every column that reveals dollar amounts or position size is dropped,
so only percentages, ratios, prices per contract and market context leave the machine.
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
from .stats import Summary, summarize

# column -> (description, reveals dollar amount or position size)
TRADE_COLUMNS: dict[str, tuple[str, bool]] = {
    "trade_id": ("交易编号（本次导出内唯一）", False),
    "day": ("开仓日期", False),
    "entry_time": ("首次买入时间（美东）", False),
    "exit_time": ("最后卖出时间（美东）；到期作废为到期日 16:00", False),
    "underlying": ("标的代码", False),
    "type": ("Call 或 Put", False),
    "strike": ("行权价", False),
    "expiry": ("到期日", False),
    "dte": ("开仓时距离到期的交易日数", False),
    "dte_bucket": ("DTE 分组", False),
    "tod": ("入场时段（美东）", False),
    "hold_min": ("持仓时长（分钟）", False),
    "hold_bucket": ("持仓时长分组", False),
    "overnight": ("是否持仓过夜", False),
    "add_type": ("建仓方式：单次建仓 / 价格更低时加仓（摊平）/ 价格更高时加仓（加码）", False),
    "n_buys": ("买入成交次数", False),
    "n_sells": ("卖出成交次数", False),
    "expired": ("是否到期作废", False),
    "avg_entry": ("平均买入价（每股期权价格，1 张 = 100 股）", False),
    "avg_exit": ("平均卖出价（每股期权价格）", False),
    "ret": ("收益率 = 净盈亏 / 买入成本（含手续费）；-0.5 表示 -50%", False),
    "win": ("是否盈利", False),
    "mfe": ("最大浮盈：持仓期间期权最高价相对买入均价的涨幅", False),
    "mae": ("最大浮亏：持仓期间期权最低价相对买入均价的跌幅", False),
    "mfe_min": ("入场后多少分钟达到最大浮盈", False),
    "post15_high": ("卖出后 15 分钟内期权最高价相对卖出价的涨幅（判断是否卖早）", False),
    "post15_low": ("卖出后 15 分钟内期权最低价相对卖出价的跌幅（判断是否卖得及时）", False),
    "post30_high": ("卖出后 30 分钟内期权最高价相对卖出价的涨幅", False),
    "direction_class": ("方向判断 × 结果：方向对/错 · 盈利/亏损", False),
    "d_und_move": ("持仓期间标的朝有利方向的涨跌幅（Call 看涨、Put 看跌为正）", False),
    "d_ret_15": ("入场前 15 分钟标的朝交易方向的涨跌幅", False),
    "d_fwd_15": ("入场后 15 分钟标的朝交易方向的涨跌幅", False),
    "d_range_pos": ("入场时标的在当日区间中的位置（按交易方向；1 = 当日最有利的极端位置）", False),
    "rvol_5": ("入场前 5 分钟成交量相对同时段平常水平的倍数", False),
    "trend_aligned": ("是否顺着前 5 分钟的走势入场", False),
    "iv_entry": ("入场时隐含波动率（Black-Scholes 反推，0.30 = 30%）", False),
    "delta_entry": ("入场时 Delta", False),
    "extrinsic_share": ("入场时外在价值占权利金的比例", False),
    "cost_vs_median20": ("本笔仓位金额相对最近 20 笔中位数的倍数", False),
    "contracts": ("买入总张数", True),
    "max_position": ("最大同时持有张数", True),
    "cost": ("买入总成本（美元，含手续费）", True),
    "proceeds": ("卖出总收入（美元，扣手续费）", True),
    "fees": ("手续费合计（美元）", True),
    "pnl": ("净盈亏（美元）", True),
}

FILL_COLUMNS: dict[str, tuple[str, bool]] = {
    "trade_id": ("所属交易编号", False),
    "exec_time": ("成交时间（美东，精确到毫秒）", False),
    "code": ("BTO = 买入开仓，STC = 卖出平仓", False),
    "price": ("成交价（每股期权价格）", False),
    "order_type": ("下单方式：limit 限价 / market 市价", False),
    "qty": ("成交张数", True),
    "amount": ("成交金额（美元，含手续费）", True),
}

PROMPT_TEMPLATES: dict[str, str] = {
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
        "请分析入场时机：入场前后标的怎么走？我是在走势启动时入场，还是追在末端？放量、顺势、入场时段和结果有没有关系？"
    ),
    "复盘单日": (
        "请按时间顺序逐笔复盘这一天的交易：每笔的入场理由可能是什么，执行得怎么样，"
        "交易之间有没有情绪化的迹象（例如亏损后很快再入场、放大仓位）。"
    ),
}

AGENT_INSTRUCTIONS = """\
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
"""

AMOUNT_NOTE_HIDDEN = (
    "5. 为了保护隐私，**美元金额和仓位张数已被移除**。请只用收益率、比例和价格进行分析，不要试图反推金额。"
)


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


def export_columns(spec: dict[str, tuple[str, bool]], include_amounts: bool) -> list[str]:
    """Columns to export; dollar/size columns are dropped unless `include_amounts`."""
    return [c for c, (_, sensitive) in spec.items() if include_amounts or not sensitive]


def _fmt_pct(x: float) -> str:
    return "—" if math.isnan(x) else f"{x:.1%}"


def _fmt_ci(ci: tuple[float, float], fmt: str) -> str:
    return "—" if any(math.isnan(v) for v in ci) else f"{ci[0]:{fmt}} ~ {ci[1]:{fmt}}"


def summary_markdown(s: Summary, flt: TradeFilter, include_amounts: bool) -> str:
    lines = ["# 筛选条件与整体统计", "", "## 筛选条件", ""]
    lines += [f"- {c}" for c in flt.describe()]
    lines += [
        "",
        "## 整体统计",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 交易笔数 / 交易天数 | {s.n} / {s.days} |",
        f"| 胜率（95% CI） | {_fmt_pct(s.win_rate)}（{_fmt_ci(s.win_rate_ci, '.0%')}） |",
        f"| 单笔收益率中位数 | {_fmt_pct(s.median_return)} |",
        f"| Profit Factor | {s.profit_factor:.2f} |",
        f"| 盈亏比（平均盈利 / 平均亏损） | {s.payoff_ratio:.2f} |",
    ]
    if include_amounts:
        lines += [
            f"| 净盈亏 | ${s.total_pnl:,.0f} |",
            f"| 单笔期望（95% CI，按交易日重抽样） | ${s.expectancy:,.1f}（{_fmt_ci(s.expectancy_ci, ',.0f')}） |",
        ]
    if s.n < config.SMALL_SAMPLE:
        lines += ["", f"> 注意：只有 {s.n} 笔交易，样本太少，统计结论不可靠。"]
    return "\n".join(lines) + "\n"


def dictionary_markdown(include_amounts: bool) -> str:
    out = ["# 数据字典", ""]
    for title, spec in (("trades.csv", TRADE_COLUMNS), ("fills.csv", FILL_COLUMNS)):
        out += [f"## {title}", "", "| 列 | 含义 |", "|---|---|"]
        out += [f"| `{c}` | {spec[c][0]} |" for c in export_columns(spec, include_amounts)]
        out.append("")
    return "\n".join(out)


def build_pack(
    trades: pd.DataFrame,
    fills: pd.DataFrame,
    flt: TradeFilter,
    prompt: str,
    include_amounts: bool,
    export_dir: Path = config.EXPORT_DIR,
    now: datetime | None = None,
) -> ExportPack:
    """Assemble the pack's file contents (nothing is written to disk here)."""
    from .data import fills_for  # local import keeps this module importable without data files

    trade_cols = export_columns(TRADE_COLUMNS, include_amounts)
    fill_cols = export_columns(FILL_COLUMNS, include_amounts)

    fill_parts = [fills_for(t, fills).assign(trade_id=t["trade_id"]) for _, t in trades.iterrows()]
    trade_fills = pd.concat(fill_parts) if fill_parts else pd.DataFrame(columns=fill_cols)

    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    amount_note = "" if include_amounts else AMOUNT_NOTE_HIDDEN
    files = {
        "PROMPT.md": AGENT_INSTRUCTIONS.format(amount_note=amount_note, prompt=prompt.strip() or "（请自由分析）"),
        "summary.md": summary_markdown(summarize(trades), flt, include_amounts),
        "DATA_DICTIONARY.md": dictionary_markdown(include_amounts),
        "trades.csv": trades[trade_cols].to_csv(index=False),
        "fills.csv": trade_fills[fill_cols].to_csv(index=False),
    }
    return ExportPack(folder=export_dir / f"pack_{stamp}", files=files)


def write_pack(pack: ExportPack) -> Path:
    pack.folder.mkdir(parents=True, exist_ok=False)
    for name, text in pack.files.items():
        (pack.folder / name).write_text(text, encoding="utf-8")
    return pack.folder
