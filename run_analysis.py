"""Run the whole analysis: python run_analysis.py
Outputs go to output/ (the raw Robinhood CSV is only read, never written)."""
import json
import warnings

import numpy as np
import pandas as pd

from tradelab import analytics as an
from tradelab import data
from tradelab.config import OUT

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 50)


def md_table(df):
    df = df.copy()
    for c in df.columns:
        if df[c].dtype.kind == "f":
            df[c] = df[c].map(lambda v: "" if pd.isna(v) else (f"{v:.1%}" if c in PCT else f"{v:,.2f}"))
    return df.to_markdown(index=False)


PCT = {"胜率", "收益率中位", "≤-50%占比", "权利金效率", "win%", "hit"}


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "charts").mkdir(exist_ok=True)
    R = {}

    # ---- Level 1: statement -> standardized fills, quality, FIFO, episodes
    header, raw = data.read_raw()
    fills, issues = data.standardize(raw)
    dq_text, issues = data.quality_report(header, raw, fills, issues)
    matches, episodes = data.fifo(fills)
    fills.to_csv(OUT / "fills_standardized.csv", index=False)
    matches.to_csv(OUT / "fifo_lot_matches.csv", index=False)
    issues.to_csv(OUT / "data_issues.csv", index=False)
    (OUT / "data_quality.md").write_text("# 数据质量检查\n\n" + dq_text + "\n", encoding="utf-8")
    print(dq_text)

    # ---- Level 2/3 enrichment
    ep = an.enrich(episodes, matches)
    ep, daily = an.behavior(ep, fills)
    ep.to_csv(OUT / "episodes.csv", index=False)

    core, ordered = an.core_metrics(ep, fills, matches)
    R["core"] = core
    groups = {}
    for col in ["dte_bucket", "type", "underlying", "etf", "tod", "hold_bucket", "delta_bucket", "direction_class",
                "trend_aligned", "htf_aligned", "add_type", "seq_in_day", "day_n_bucket", "reentry_same_contract",
                "prev_win", "cost_q", "overnight"]:
        groups[col] = an.group_table(ep, col)
    ep["type_dte"] = ep.type + " " + ep.dte_bucket.astype(str)
    groups["type_dte"] = an.group_table(ep, "type_dte")
    late = ep[(ep.dte == 0) & (ep.min_to_expiry <= 60)]
    groups["0dte_last_hour"] = an.group_table(late.assign(g="0DTE 最后一小时入场"), "g")
    ep["otm_bucket"] = pd.cut(ep.otm_pct, [-1, -.005, -.001, .001, .005, .01, 1],
                              labels=["价内>0.5%", "价内0.1-0.5%", "平值±0.1%", "价外0.1-0.5%", "价外0.5-1%", "价外>1%"])
    groups["otm_bucket"] = an.group_table(ep, "otm_bucket")
    ep["premium_bucket"] = pd.cut(ep.first_entry_price, [0, .5, 1, 2, 4, 1e9],
                                  labels=["<$0.5", "$0.5-1", "$1-2", "$2-4", ">$4"])
    groups["premium_bucket"] = an.group_table(ep, "premium_bucket")
    etf = ep[ep.etf & ep.rvol_5.notna()].copy()
    etf["rvol_bucket"] = pd.cut(etf.rvol_5, [0, 1, 1.5, 2.5, 100], labels=["<1x", "1-1.5x", "1.5-2.5x", ">2.5x"])
    etf["mom_bucket"] = pd.cut(etf.d_ret_5, [-1, -.001, 0, .001, .002, 1],
                               labels=["逆势>0.1%", "逆势0-0.1%", "顺势0-0.1%", "顺势0.1-0.2%", "顺势>0.2%"])
    etf["chase_bucket"] = pd.cut(etf.d_ret_15, [-1, 0, .001, .003, 1],
                                 labels=["前15m逆向", "前15m顺向0-0.1%", "0.1-0.3%", ">0.3%"])
    etf["range_bucket"] = pd.cut(etf.d_range_pos, [-.01, .25, .5, .75, .9, 1.01],
                                 labels=["<25%", "25-50%", "50-75%", "75-90%", ">90%(接近日内极值)"])
    for c in ["rvol_bucket", "mom_bucket", "chase_bucket", "range_bucket"]:
        groups[c] = an.group_table(etf, c)
    for k, v in groups.items():
        v.to_csv(OUT / f"group_{k}.csv", index=False)

    # ---- exits
    ex = ep[ep.mfe.notna()]
    w, l = ex[ex.win], ex[~ex.win]
    R["exit"] = {
        "有持仓期间分钟数据的交易": len(ex),
        "盈利交易 MFE 中位 / 实际收益率中位": f"{w.mfe.median():.0%} / {w.ret.median():.0%}",
        "盈利交易 兑现比例中位 (实际收益/MFE)": (w.ret / w.mfe).replace([np.inf, -np.inf], np.nan).median(),
        "盈利交易 从浮盈高点回撤到卖出 (中位, 占MFE)": (1 - (w.avg_exit / w.avg_entry - 1) / w.mfe).median(),
        "亏损交易 MAE 中位 / 实际收益率中位": f"{l.mae.median():.0%} / {l.ret.median():.0%}",
        "亏损交易中 曾浮盈≥20% 的笔数 / 亏损": f"{(l.mfe >= .2).sum()} / {len(l)}  (${l[l.mfe >= .2].pnl.sum():,.0f})",
        "亏损交易中 曾浮盈≥10% 的笔数": int((l.mfe >= .1).sum()),
        "盈利交易中 曾浮亏≤-20% 的笔数": f"{(w.mae <= -.2).sum()} / {len(w)}",
        "亏损交易 MAE≤-50% (止损过晚)": f"{(l.mae <= -.5).sum()} 笔, ${l[l.mae <= -.5].pnl.sum():,.0f}",
        "亏损平仓后30分钟内价格回到开仓价之上 (止损后恢复)":
            f"{int(l.post_back_above_entry_30.fillna(False).sum())} / {int(l.post_back_above_entry_30.notna().sum())}",
        "盈利平仓后15分钟内最高再涨≥20% (可能过早止盈)":
            f"{int((w.post15_high >= .2).sum())} / {int(w.post15_high.notna().sum())}",
        "盈利平仓后15分钟内最低再跌≥20% (卖得及时)":
            f"{int((w.post15_low <= -.2).sum())} / {int(w.post15_low.notna().sum())}",
    }
    post = ep[ep.post1_close.notna()].groupby("win")[[f"post{k}_close" for k in (1, 3, 5, 15)]].median()
    post.index = post.index.map({True: "盈利平仓", False: "亏损平仓"})
    R["post_exit_table"] = post
    slip = ep[["entry_vs_vwap", "exit_vs_vwap"]].median()
    R["slippage"] = {"买入成交价 vs 当分钟VWAP 中位": slip.entry_vs_vwap,
                     "卖出成交价 vs 当分钟VWAP 中位": slip.exit_vs_vwap}

    bt = an.backtest(ep)
    bt.drop(columns="pnl_series").to_csv(OUT / "backtest_exit_rules.csv", index=False)
    R["oos"] = an.oos_tp_sl(ep, bt)

    # ---- attribution
    attr = an.attribution(matches, fills)
    attr.to_csv(OUT / "attribution_lots.csv", index=False)
    a = attr[attr["underlying_$"].notna()]
    R["attribution"] = {
        "可归因的成交批次 (lot)": f"{len(a)} / {len(attr)}",
        "这些批次的实际净盈亏 $": a.pnl.sum(),
        "标的价格变动 (Delta+Gamma, 全价重估) $": a["underlying_$"].sum(),
        "时间流逝 (Theta) $": a["time_$"].sum(),
        "隐含波动率变化 (Vega) $": a["vol_$"].sum(),
        "无法解释残差 (成交价低于模型值/到期) $": a["residual_$"].sum(),
        "手续费 $": -a.fees.sum(),
        "Greeks 线性近似 的误差合计 $ (|误差|中位)":
            f"{a['greek_approx_err_$'].sum():,.0f} ({a['greek_approx_err_$'].abs().median():,.1f})",
    }

    # ---- behavior & robustness
    R["loss_conc"] = an.loss_concentration(ep)
    R["robust"], sims, dds = an.robustness(ep)
    nxt = ep.dropna(subset=["prev_win"])
    R["after_loss"] = nxt.groupby("prev_win").agg(
        n=("pnl", "size"), gap_min_median=("gap_after_prev_min", "median"),
        size_vs_median=("cost_vs_median20", "median"), next_pnl=("pnl", "mean"),
        next_win=("win", "mean")).rename(index={True: "上一笔盈利", False: "上一笔亏损"})

    # ---- signal study
    panel, grid, etf_sig, rules, sig_meta = an.signal_study(ep)
    grid.to_csv(OUT / "signal_grid_all_minutes.csv", index=False)
    rules.to_csv(OUT / "signal_rules_is_oos.csv", index=False)
    etf_sig.to_csv(OUT / "etf_entries_with_control.csv", index=False)
    R["signal_meta"] = sig_meta
    R["entries_vs_control"] = {
        "ETF 入场笔数": len(etf_sig),
        "入场时 |5分钟涨跌| 在全部分钟中的分位 (中位)": etf_sig.mom_pct.median(),
        "入场时 RVOL(5m) 在全部分钟中的分位 (中位)": etf_sig.rvol_pct.median(),
        "入场时 RVOL(5m) 中位": etf_sig.rvol_5.median(),
        "顺势入场占比 (方向=前5分钟方向)": etf_sig.trend_aligned.mean(),
        "我的入场后15分钟标的顺向变动 (均值, bp)": etf_sig.d_fwd_15.mean() * 1e4,
        "同日同条件未交易分钟 (对照) 15分钟顺向变动 (均值, bp)": etf_sig.ctrl_dfwd_15.mean() * 1e4,
        "入场前15分钟顺向变动 (均值, bp)": etf_sig.d_ret_15.mean() * 1e4,
        "入场后15分钟顺向变动 > 0 的比例": (etf_sig.d_fwd_15 > 0).mean(),
    }

    # ---- save
    import pickle
    with open(OUT / "results.pkl", "wb") as f:
        pickle.dump(dict(R=R, groups=groups, ordered=ordered, daily=daily, bt=bt.drop(columns="pnl_series"),
                         sims=sims, dds=dds, grid=grid, rules=rules, attr=attr), f)
    from tradelab import charts
    charts.make_all(ep, ordered, daily, bt, grid, etf_sig, panel)
    write_tables(R, groups, bt, rules, grid)
    print("done ->", OUT)


def write_tables(R, groups, bt, rules, grid):
    L = ["# 自动生成的分析表（run_analysis.py）", ""]
    for name, d in R.items():
        L.append(f"## {name}")
        if isinstance(d, dict):
            for k, v in d.items():
                L.append(f"- {k}: {v:,.4g}" if isinstance(v, (int, float, np.floating, np.integer)) else f"- {k}: {v}")
        else:
            L.append(d.to_markdown())
        L.append("")
    for k, g in groups.items():
        L += [f"## 分组: {k}", md_table(g), ""]
    for v in ("actual/conservative", "actual/optimistic", "actual/conservative/strict3%", "eod/conservative"):
        sub = bt[(bt.rule == "tp_sl") & (bt.variant == v)]
        piv = sub.pivot_table(index=sub.tp.fillna(0), columns=sub.sl.fillna(0), values="total")
        L += [f"## 止盈止损回测 总盈亏 ({v}; 行=止盈, 列=止损, 0=不设)", piv.round(0).to_markdown(), ""]
    L += ["## 其他退出规则", bt[bt.rule != "tp_sl"][["rule", "trail", "tstop", "und_stop", "total", "expectancy", "win%"]]
          .round(3).to_markdown(index=False), ""]
    L += ["## 趋势×放量 信号（全部分钟, 15分钟延续 bp）", grid.round(2).to_markdown(index=False), ""]
    L += ["## 客观规则 样本内/样本外", rules.round(3).to_markdown(index=False), ""]
    (OUT / "analysis_tables.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
