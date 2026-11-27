"""Static PNG charts for the Markdown report (light theme, validated reference palette)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

from .config import OUT

SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
GAIN, LOSS = BLUE, ORANGE          # diverging poles (CVD-safe pair); neutral midpoint below
NEUTRAL = "#f0efec"
DIV = LinearSegmentedColormap.from_list("div", [LOSS, NEUTRAL, GAIN])
SEQ = LinearSegmentedColormap.from_list("seq", ["#cde2fb", "#86b6ef", "#2a78d6", "#184f95", "#0d366b"])

plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"], "axes.unicode_minus": False,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "text.color": INK, "axes.titlecolor": INK, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.grid": True, "grid.color": GRID, "grid.linewidth": .6,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10, "lines.linewidth": 2,
    "figure.dpi": 110,
})
D = OUT / "charts"


def save(fig, name):
    fig.tight_layout()
    fig.savefig(D / name, bbox_inches="tight")
    plt.close(fig)


def money_axis(ax, axis="y"):
    f = matplotlib.ticker.FuncFormatter(lambda v, _: f"${v:,.0f}")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(f)


def signed_bars(ax, labels, vals, ns=None):
    x = np.arange(len(vals))
    ax.bar(x, vals, color=[GAIN if v > 0 else LOSS for v in vals], width=.6, edgecolor=SURFACE, linewidth=2)
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xticks(x, labels)
    for i, v in enumerate(vals):
        t = f"${v:,.0f}" + (f"\nn={ns[i]}" if ns is not None else "")
        ax.annotate(t, (i, v), xytext=(0, 4 if v >= 0 else -4), textcoords="offset points",
                    ha="center", va="bottom" if v >= 0 else "top", fontsize=8.5, color=INK2)
    money_axis(ax)


def make_all(ep, ordered, daily, bt, grid, etf, panel):
    D.mkdir(parents=True, exist_ok=True)

    # 1 cumulative realized P&L + 4 drawdown
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    a1.plot(ordered.exit_time, ordered.cum, color=BLUE, label="全部期权")
    a1.axhline(0, color=AXIS, lw=1)
    a1.set_title("累计已实现净盈亏（全部期权，按平仓时间）")
    money_axis(a1)
    for sym, c in (("SPY/QQQ/IWM", AQUA),):
        e = ordered[ordered.etf]
        a1.plot(e.exit_time, e.pnl.cumsum(), color=c, lw=1.5, label="仅 SPY/QQQ/IWM")
    a1.legend(frameon=False, loc="lower left")
    a2.fill_between(ordered.exit_time, ordered.dd, 0, color=LOSS, alpha=.35, lw=0)
    a2.plot(ordered.exit_time, ordered.dd, color=LOSS, lw=1.2)
    a2.set_title("回撤（相对累计盈亏峰值）")
    money_axis(a2)
    save(fig, "01_cum_pnl_drawdown.png")

    # 2 daily pnl
    fig, ax = plt.subplots(figsize=(11, 3.8))
    d = daily.reset_index()
    d["day"] = pd.to_datetime(d.day)
    ax.bar(d.day, d.pnl, color=[GAIN if v > 0 else LOSS for v in d.pnl], width=1.2)
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_title(f"每日已实现盈亏（{len(d)} 个交易日；盈利日 {int((d.pnl > 0).sum())}，亏损日 {int((d.pnl <= 0).sum())}）")
    money_axis(ax)
    save(fig, "02_daily_pnl.png")

    # 3 return distribution
    fig, ax = plt.subplots(figsize=(9, 3.8))
    r = ep.ret.clip(-1, 3) * 100
    bins = np.arange(-100, 305, 10)
    ax.hist(r[r <= 0], bins=bins, color=LOSS, edgecolor=SURFACE, linewidth=1.5)
    ax.hist(r[r > 0], bins=bins, color=GAIN, edgecolor=SURFACE, linewidth=1.5)
    ax.axvline(ep.ret.median() * 100, color=INK2, ls="--", lw=1)
    ax.annotate(f"中位数 {ep.ret.median():.0%}", (ep.ret.median() * 100, ax.get_ylim()[1] * .9),
                xytext=(6, 0), textcoords="offset points", color=INK2)
    ax.set_title("单笔完整交易收益率分布（按开仓权利金+费用；>300% 并入最右）")
    ax.set_xlabel("收益率 %")
    ax.set_ylabel("交易笔数")
    save(fig, "03_return_distribution.png")

    # 5 DTE, call/put, tod, hold, delta panels
    def panel_bar(col, title, fname, df=ep):
        g = df.groupby(col, observed=True).agg(pnl=("pnl", "sum"), n=("pnl", "size"),
                                               exp=("pnl", "mean"), win=("win", "mean"))
        fig, (a, b) = plt.subplots(1, 2, figsize=(11, 3.8))
        signed_bars(a, [str(i) for i in g.index], g.pnl.values, g.n.values)
        a.set_title(f"{title}：净盈亏")
        signed_bars(b, [str(i) for i in g.index], g.exp.values)
        b.set_title(f"{title}：单笔期望")
        for x in (a, b):
            x.tick_params(axis="x", labelrotation=15 if len(g) > 4 else 0)
        save(fig, fname)

    panel_bar("dte_bucket", "到期周期 (DTE)", "05_dte.png")
    panel_bar("type", "Call / Put", "06_call_put.png")
    panel_bar("hold_bucket", "持仓时长", "07_hold.png")
    panel_bar("delta_bucket", "入场 Delta", "08_delta.png")
    panel_bar("add_type", "建仓方式", "09_add_type.png")

    # 7b hold vs return scatter
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.scatter(ep.hold_min.clip(upper=600), ep.ret * 100, s=22, c=[GAIN if w else LOSS for w in ep.win],
               edgecolor=SURFACE, linewidth=.8, alpha=.85)
    ax.set_xscale("symlog", linthresh=1)
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xlabel("持仓分钟（对数轴，>600 截断）")
    ax.set_ylabel("收益率 %")
    ax.set_title("持仓时长 vs 单笔收益率（蓝=盈利，橙=亏损）")
    save(fig, "07b_hold_vs_return.png")

    # 10 tod x DTE heatmap (expectancy)
    piv = ep.pivot_table(index="tod", columns="dte_bucket", values="pnl", aggfunc="mean", observed=True)
    cnt = ep.pivot_table(index="tod", columns="dte_bucket", values="pnl", aggfunc="size", observed=True)
    heat(piv, cnt, "交易时段 × 到期周期：单笔期望 $（格内 n=笔数）", "10_tod_dte_heatmap.png", fmt="${:,.0f}")

    # 11 size vs pnl
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.scatter(ep.cost, ep.pnl, s=22, c=[GAIN if w else LOSS for w in ep.win], edgecolor=SURFACE, lw=.8, alpha=.85)
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xscale("log")
    money_axis(ax)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.set_xlabel("开仓成本（对数轴）")
    ax.set_title("仓位（开仓权利金）vs 单笔盈亏")
    save(fig, "11_size_vs_pnl.png")

    # 12 MFE / MAE
    m = ep[ep.mfe.notna()]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.scatter(m.mae.clip(-1, 0) * 100, m.mfe.clip(0, 3) * 100, s=24, c=[GAIN if w else LOSS for w in m.win],
               edgecolor=SURFACE, lw=.8, alpha=.85)
    ax.set_xlabel("MAE：持仓期间最大浮亏 %")
    ax.set_ylabel("MFE：持仓期间最大浮盈 %（>300% 截断）")
    ax.set_title("MFE / MAE（蓝=最终盈利，橙=最终亏损）")
    ax.axhline(20, color=MUTED, ls=":", lw=1)
    ax.axvline(-30, color=MUTED, ls=":", lw=1)
    save(fig, "12_mfe_mae.png")

    # 13 TP/SL heatmaps
    for v, fname in (("actual/conservative", "13_tpsl_conservative.png"), ("actual/optimistic", "13b_tpsl_optimistic.png"),
                     ("eod/conservative", "13c_tpsl_hold_to_close.png"),
                     ("actual/conservative/strict3%", "13d_tpsl_strict.png")):
        sub = bt[(bt.rule == "tp_sl") & (bt.variant == v)]
        piv = sub.pivot_table(index=sub.tp.fillna(0), columns=sub.sl.fillna(0), values="total")
        piv.index = ["不设" if i == 0 else f"+{i:.0%}" for i in piv.index]
        piv.columns = ["不设" if i == 0 else f"-{i:.0%}" for i in piv.columns]
        base = sub[(sub.tp.isna()) & (sub.sl.isna())].total.iloc[0]
        heat(piv, None, f"首笔仓位 止盈(行)×止损(列) 回测总盈亏 — {v}\n同口径基准(不设止盈止损)=${base:,.0f}",
             fname, fmt="${:,.0f}", diverging=True, xlabel="止损", ylabel="止盈")

    # 14 trend x volume (control minutes) and my entries
    g = grid.pivot_table(index="mom_q", columns="rvol_q", values="cont15_bp", observed=True)
    n = grid.pivot_table(index="mom_q", columns="rvol_q", values="n", observed=True)
    heat(g, n, "全部分钟：前5分钟涨跌幅分位(行) × 5分钟RVOL分位(列)\n→ 之后15分钟沿原方向的平均延续 (bp)",
         "14_trend_rvol_all_minutes.png", fmt="{:.1f}", diverging=True, xlabel="RVOL 分位", ylabel="|前5分钟涨跌| 分位")
    e = etf.dropna(subset=["mom_q", "rvol_q"])
    g2 = e.pivot_table(index="mom_q", columns="rvol_q", values="pnl", aggfunc="mean", observed=True)
    n2 = e.pivot_table(index="mom_q", columns="rvol_q", values="pnl", aggfunc="size", observed=True)
    heat(g2, n2, "我的 SPY/QQQ/IWM 交易：入场时趋势强度 × RVOL → 单笔期望 $", "14b_trend_rvol_my_trades.png",
         fmt="${:,.0f}", diverging=True, xlabel="RVOL 分位", ylabel="|前5分钟涨跌| 分位")

    # 15 before vs after entry (chasing?)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(e.d_ret_15 * 1e4, e.d_fwd_15 * 1e4, s=24, c=[GAIN if w else LOSS for w in e.win],
               edgecolor=SURFACE, lw=.8, alpha=.85)
    ax.axhline(0, color=AXIS, lw=1)
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_xlabel("入场前15分钟 标的顺向变动 (bp)")
    ax.set_ylabel("入场后15分钟 标的顺向变动 (bp)")
    ax.set_title("入场前 vs 入场后 标的走势（顺向=对我有利的方向）")
    save(fig, "15_before_after_entry.png")


def heat(piv, cnt, title, fname, fmt="{:.1f}", diverging=True, xlabel="", ylabel=""):
    fig, ax = plt.subplots(figsize=(1.6 * piv.shape[1] + 3, .75 * piv.shape[0] + 2))
    v = piv.values.astype(float)
    lim = np.nanmax(np.abs(v)) if np.isfinite(v).any() else 1
    norm = TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim) if diverging and lim > 0 else None
    ax.imshow(np.ma.masked_invalid(v), cmap=DIV if diverging else SEQ, norm=norm, aspect="auto")
    ax.set_xticks(range(piv.shape[1]), [str(c) for c in piv.columns])
    ax.set_yticks(range(piv.shape[0]), [str(i) for i in piv.index])
    ax.grid(False)
    for i in range(v.shape[0]):
        for j in range(v.shape[1]):
            if np.isfinite(v[i, j]):
                t = fmt.format(v[i, j])
                if cnt is not None:
                    c = cnt.values[i, j]
                    t += f"\nn={int(c)}" if c == c else ""
                strong = abs(v[i, j]) > .6 * lim
                ax.text(j, i, t, ha="center", va="center", fontsize=8.5, color="#ffffff" if strong else INK)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    save(fig, fname)
