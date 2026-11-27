"""Compare trading periods: active (Mar-Apr), low-activity (May - mid Sep), resumed (mid Sep onward).
python period_analysis.py  ->  output/period_comparison.md, output/period_*.csv, output/charts/20_period_*.png"""
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from tradelab import analytics as an
from tradelab import data
from tradelab.config import OUT

warnings.filterwarnings("ignore")

PERIODS = [("A 活跃期 3/2-5/1", "2026-03-01", "2026-05-03"),
           ("B 低频期 5/4-9/11", "2026-05-04", "2026-09-13"),
           ("C 恢复期 9/14-11/23", "2026-09-14", "2026-12-31")]
ORDER = [p[0] for p in PERIODS]


def period_of(day):
    for name, a, b in PERIODS:
        if a <= day <= b:
            return name
    return None


def fmt(df):
    df = df.copy()
    for c in df.columns:
        if df[c].dtype.kind == "f":
            df[c] = df[c].map(lambda v: "" if pd.isna(v) else (f"{v:.1%}" if c in run_pct else f"{v:,.2f}"))
    return df.to_markdown(index=False)


run_pct = {"胜率", "收益率中位", "≤-50%占比", "权利金效率", "ETF占比", "0-1DTE占比", "隔夜占比", "顺势占比",
           "入场后15m顺向>0", "Call占比", "-10%止损 胜率"}


def main():
    header, raw = data.read_raw()
    fills, issues = data.standardize(raw)
    matches, episodes = data.fifo(fills)
    ep = an.enrich(episodes, matches)
    ep, daily = an.behavior(ep, fills)
    ep["period"] = pd.Categorical(ep.day.map(period_of), ORDER, ordered=True)

    # ---- first-lot backtest: actual exit vs -10% hard stop, per trade
    bt = an.backtest(ep)
    pick = lambda tp, sl: bt[(bt.rule == "tp_sl") & (bt.variant == "actual/conservative")
                             & (bt.tp.fillna(0) == tp) & (bt.sl.fillna(0) == sl)].pnl_series.iloc[0]
    ep["bt_base"] = pick(0, 0)
    ep["bt_sl10"] = pick(0, .1)

    # ---- attribution per lot -> period by open day
    attr = an.attribution(matches, fills)
    attr["day"] = pd.to_datetime(attr.open_time, utc=True).dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    attr["period"] = pd.Categorical(attr.day.map(period_of), ORDER, ordered=True)

    L = ["# 分时期对比：活跃期 / 低频期 / 恢复期", "",
         "由 `period_analysis.py` 自动生成。时期按成交频率划分（见第 1 节），口径与主报告相同：",
         "FIFO 完整交易（episode），盈亏含手续费，期望 CI 为按交易日分块 bootstrap 95% 区间。", ""]

    # 1. activity by week
    f = fills[fills.code.isin(["BTO", "STC"])].copy()
    f["d"] = pd.to_datetime(f.date)
    wk = f.groupby(f.d.dt.to_period("W").dt.start_time).agg(成交=("row", "size"), 交易天数=("date", "nunique"))
    L += ["## 1. 时期划分依据（每周成交笔数）", "",
          "- 3–4 月每周 4–41 笔；5 月 4 日起降到每周 0–15 笔，持续约 19 周；9 月 14 日那周起回升到 20、43、72 笔。",
          "- 因此：A = 3/2–5/1，B = 5/4–9/11（低频），C = 9/14–11/23（恢复）。", ""]

    # 2. core per period
    core = an.group_table(ep, "period").rename(columns={"period": "时期"})
    per = ep.groupby("period", observed=True)
    extra = pd.DataFrame({
        "时期": ORDER,
        "日均笔数": per.size().values / per.day.nunique().values,
        "开仓成本中位$": per.cost.median().values,
        "最大单笔亏损$": per.pnl.min().values,
        "最大单笔盈利$": per.pnl.max().values,
    })
    L += ["## 2. 核心指标", "", fmt(core), "", fmt(extra), ""]

    # 3. what was traded
    mix = pd.DataFrame({
        "时期": ORDER,
        "ETF占比": per.etf.mean().values,
        "0-1DTE占比": per.dte.apply(lambda s: (s <= 1).mean()).values,
        "Call占比": per.type.apply(lambda s: (s == "Call").mean()).values,
        "隔夜占比": per.overnight.mean().values,
        "持仓分钟中位": per.hold_min.median().values,
        "摊平加仓笔数": per.add_type.apply(lambda s: (s == "加仓-价格更低(摊平)").sum()).values,
        "≤-50%离场笔数": per.ret.apply(lambda s: (s <= -.5).sum()).values,
    })
    L += ["## 3. 交易了什么、怎么持有", "", fmt(mix), ""]

    # 4. sub-groups within each period
    for col, title in [("etf", "ETF vs 个股"), ("dte_bucket", "DTE"), ("overnight", "是否隔夜"),
                       ("tod", "入场时段"), ("add_type", "加仓方式")]:
        rows = []
        for p, g in ep.groupby("period", observed=True):
            t = an.group_table(g, col)
            t.insert(0, "时期", p)
            rows.append(t)
        t = pd.concat(rows)[["时期", col, "n", "胜率", "净盈亏", "期望$", "期望CI"]]
        t.to_csv(OUT / f"period_by_{col}.csv", index=False)
        L += [f"## 4.{title} 分时期", "", fmt(t), ""]

    # 5. direction / entry quality on ETF trades
    e = ep[ep.etf & ep.d_fwd_15.notna()]
    pe = e.groupby("period", observed=True)
    dirq = pd.DataFrame({
        "时期": list(pe.groups.keys()),
        "ETF笔数(有分钟数据)": pe.size().values,
        "顺势占比": pe.trend_aligned.mean().values,
        "入场前15m顺向bp": (pe.d_ret_15.mean() * 1e4).values,
        "入场后15m顺向bp": (pe.d_fwd_15.mean() * 1e4).values,
        "入场后15m顺向>0": pe.d_fwd_15.apply(lambda s: (s > 0).mean()).values,
    })
    L += ["## 5. 入场方向质量（ETF）", "", fmt(dirq), ""]

    # 6. attribution
    a = attr[attr["underlying_$"].notna()]
    at = a.groupby("period", observed=True)[["pnl", "underlying_$", "time_$", "vol_$", "residual_$", "fees"]].sum()
    at = at.rename(columns={"pnl": "净盈亏", "underlying_$": "标的方向", "time_$": "时间损耗",
                            "vol_$": "IV变化", "residual_$": "残差", "fees": "手续费"}).reset_index()
    at = at.rename(columns={"period": "时期"})
    L += ["## 6. 盈亏归因（按成交批次，全价重估）", "", fmt(at), ""]

    # 7. stop rule per period
    sb = per[["bt_base", "bt_sl10"]].sum().reset_index().rename(
        columns={"period": "时期", "bt_base": "首笔·实际退出$", "bt_sl10": "首笔·-10%止损$"})
    sb["-10%止损 胜率"] = per.bt_sl10.apply(lambda s: (s > 0).mean()).values
    L += ["## 7. 首笔仓位回测：实际退出 vs −10% 硬止损（保守成交）", "", fmt(sb), ""]

    # 8. monthly inside C
    c = ep[ep.period == ORDER[2]].copy()
    c["半月"] = c.day.str[:7] + np.where(c.day.str[8:10].astype(int) <= 15, " 上", " 下")
    L += ["## 8. 恢复期内部（半月）", "", fmt(an.group_table(c, "半月")), ""]

    ep[["day", "period", "underlying", "occ", "pnl", "ret", "etf", "dte", "overnight", "add_type",
        "bt_base", "bt_sl10"]].to_csv(OUT / "period_episodes.csv", index=False)
    core.to_csv(OUT / "period_core.csv", index=False)
    (OUT / "period_comparison.md").write_text("\n".join(L), encoding="utf-8")
    chart(ep, wk)
    print("\n".join(L))


def chart(ep, wk):
    plt.rcParams["font.family"] = "Microsoft YaHei"
    BLUE, ORANGE, INK, MUTED, SURF = "#2a78d6", "#eb6834", "#1f1f1e", "#8a8a85", "#fcfcfb"
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, facecolor=SURF,
                                   gridspec_kw={"height_ratios": [1, 1.4]})
    for ax in (ax1, ax2):
        ax.set_facecolor(SURF)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(axis="y", color="#e6e6e3", lw=.8)
        for name, a, b in PERIODS[1:2]:
            ax.axvspan(pd.Timestamp(a), pd.Timestamp(b), color="#efefec", zorder=0)
    ax1.bar(wk.index, wk["成交"], width=5, color=BLUE, label="每周成交笔数")
    ax1.set_title("每周成交笔数（灰色背景 = 低频期 5/4–9/11）", loc="left", color=INK)
    o = ep.sort_values("exit_time")
    d = pd.to_datetime(o.exit_time, utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    ax2.plot(d, o.pnl.cumsum().values, color=BLUE, lw=2, label="累计净盈亏")
    ax2.axhline(0, color=MUTED, lw=1)
    ax2.set_title("累计已实现净盈亏 $", loc="left", color=INK)
    for name, a, b in PERIODS:
        ax2.text(pd.Timestamp(a) + pd.Timedelta(days=2), ax2.get_ylim()[0] * .97,
                 name.split(" ")[0] + " " + name.split(" ")[1], color=MUTED, fontsize=9, va="bottom")
    fig.tight_layout()
    fig.savefig(OUT / "charts" / "20_period_activity_pnl.png", dpi=130)


if __name__ == "__main__":
    main()
