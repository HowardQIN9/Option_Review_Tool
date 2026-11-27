"""Episode enrichment, performance metrics, exit analysis, TP/SL backtest, behavior, attribution, robustness,
and the trend/volume signal study with a control group of untraded minutes."""
import numpy as np
import pandas as pd

from . import market as mk
from .config import INDEX_ETFS, MIN_SLIPPAGE, STOP_SLIPPAGE_PCT, TP_TRADE_THROUGH, TZ

RNG = np.random.default_rng(7)


# ---------------------------------------------------------------- helpers
def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def day_block_bootstrap(df, stat=None, n=2000, day_col="day", col="pnl"):
    """Resample trading days with replacement (keeps within-day dependence).
    Returns the bootstrap distribution of the per-trade mean of `col`."""
    g = df.groupby(day_col)[col].agg(["sum", "size"])
    if len(g) < 3:
        return np.array([np.nan])
    idx = RNG.integers(0, len(g), (n, len(g)))
    return g["sum"].values[idx].sum(1) / g["size"].values[idx].sum(1)


def ci(a):
    a = a[~np.isnan(a)]
    return (np.percentile(a, 2.5), np.percentile(a, 97.5)) if len(a) else (np.nan, np.nan)


def streaks(sign):
    best = {True: 0, False: 0}
    cur, prev = 0, None
    for s in sign:
        cur = cur + 1 if s == prev else 1
        prev = s
        best[s] = max(best[s], cur)
    return best[True], best[False]


def slip(p):
    return max(MIN_SLIPPAGE, STOP_SLIPPAGE_PCT * p)


# ---------------------------------------------------------------- enrichment
def holidays():
    d = set(mk.trading_days("SPY"))
    wd = pd.bdate_range(min(d), max(d)).strftime("%Y-%m-%d")
    return [x for x in wd if x not in d]


def enrich(ep, matches):
    ep = ep[~ep.is_open].copy()
    hol = holidays()
    ep["day"] = ep.entry_time.dt.strftime("%Y-%m-%d")
    ep["exit_day"] = ep.exit_time.dt.strftime("%Y-%m-%d")
    ep["dir"] = np.where(ep.type == "Call", 1, -1)
    ep["dte"] = [np.busday_count(d, x, holidays=hol) for d, x in zip(ep.day, ep.expiry)]
    ep["dte_bucket"] = pd.cut(ep.dte, [-1, 0, 1, 5, 10_000], labels=["0DTE", "1DTE", "2-5DTE", "6+DTE"])
    ep["min_to_expiry"] = [mk.years_to_expiry(t, x) * mk.MIN_PER_YEAR for t, x in zip(ep.entry_time, ep.expiry)]
    ep["hold_min"] = (ep.exit_time - ep.entry_time).dt.total_seconds() / 60
    ep["overnight"] = ep.day != ep.exit_day
    ep["hold_bucket"] = pd.cut(ep.hold_min, [0, 1, 5, 15, 30, 60, 1e9], right=False,
                               labels=["<1m", "1-5m", "5-15m", "15-30m", "30-60m", "60m+"])
    mod = ep.entry_time.dt.hour * 60 + ep.entry_time.dt.minute
    ep["tod"] = pd.cut(mod, [0, 570, 600, 660, 840, 900, 960, 1440], right=False,
                       labels=["09:30前(盘前)", "09:30-10:00", "10:00-11:00", "11:00-14:00", "14:00-15:00", "15:00-16:00",
                               "16:00后(收盘后)"])
    ep["win"] = ep.pnl > 0
    ep["etf"] = ep.underlying.isin(INDEX_ETFS)

    rows = []
    for r in ep.itertuples():
        f = {"occ": r.occ, "entry_time": r.entry_time}
        ctx = mk.context(r.underlying, r.entry_time, continuous=r.underlying in INDEX_ETFS)
        f.update(ctx)
        S0 = mk.underlying_price(r.underlying, r.entry_time)
        S1 = mk.underlying_price(r.underlying, r.exit_time) if not r.expired else \
            mk.underlying_price(r.underlying, pd.Timestamp(f"{r.expiry} 15:59:59", tz=TZ))
        f["S0"], f["S1"] = S0, S1
        f["und_move"] = S1 / S0 - 1
        T0 = mk.years_to_expiry(r.entry_time, r.expiry)
        iv0 = mk.implied_vol(r.first_entry_price, S0, r.strike, T0, r.type)
        f["iv_entry"] = iv0
        f.update({f"{k}_entry": v for k, v in mk.greeks(S0, r.strike, T0, iv0, r.type).items()})
        if not r.expired:
            f["iv_exit"] = mk.implied_vol(r.avg_exit, S1, r.strike, mk.years_to_expiry(r.exit_time, r.expiry), r.type)
        f["otm_pct"] = (r.strike - S0) / S0 * (1 if r.type == "Call" else -1)
        intrinsic = max(0, (S0 - r.strike) * (1 if r.type == "Call" else -1))
        f["extrinsic_share"] = (r.first_entry_price - intrinsic) / r.first_entry_price
        f.update(path_metrics(r))
        rows.append(f)
    x = pd.DataFrame(rows)
    ep = ep.merge(x, on=["occ", "entry_time"], how="left")
    ep["d_ret_5"] = ep.dir * ep.ret_5
    ep["d_ret_15"] = ep.dir * ep.ret_15
    ep["d_ret_1"] = ep.dir * ep.ret_1
    ep["d_ret_3"] = ep.dir * ep.ret_3
    ep["d_vwap"] = ep.dir * ep.vwap_dist
    ep["d_accel"] = ep.dir * ep.accel_3
    ep["d_ret_60"] = ep.dir * ep.ret_60
    ep["d_fwd_5"], ep["d_fwd_15"], ep["d_fwd_30"] = ep.dir * ep.fwd_5, ep.dir * ep.fwd_15, ep.dir * ep.fwd_30
    ep["d_und_move"] = ep.dir * ep.und_move
    # range position measured in the trade direction (1 = at the day's extreme in my direction)
    ep["d_range_pos"] = np.where(ep.dir == 1, ep.range_pos, 1 - ep.range_pos)
    ep["trend_aligned"] = np.sign(ep.ret_5) == ep.dir
    ep["htf_aligned"] = np.sign(ep.ret_60) == np.sign(ep.ret_5)
    ep["abs_delta"] = ep.delta_entry.abs()
    ep["delta_bucket"] = pd.cut(ep.abs_delta, [0, .2, .4, .6, 1.01], right=False,
                                labels=["<0.20 深度价外", "0.20-0.40 价外", "0.40-0.60 平值", ">=0.60 价内"])
    ep["direction_class"] = np.select(
        [(ep.d_und_move > 0) & ep.win, (ep.d_und_move > 0) & ~ep.win, (ep.d_und_move <= 0) & ep.win,
         (ep.d_und_move <= 0) & ~ep.win],
        ["方向对·盈利", "方向对·亏损", "方向错·盈利", "方向错·亏损"], default="无行情")
    ep.loc[ep.d_und_move.isna(), "direction_class"] = "无行情"
    return ep


def path_metrics(r):
    """MFE/MAE inside the hold (bars strictly between entry and exit minute) and post-exit moves."""
    out = {}
    b = mk.option_bars(r.occ, r.entry_time, r.exit_time if pd.notna(r.exit_time) else r.entry_time)
    if b is None:
        return out
    t0, t1 = r.entry_time.floor("min"), r.exit_time.floor("min")
    hold = b[(b.index > t0) & (b.index < t1)]
    e = r.avg_entry
    if len(hold):
        out["mfe"] = hold.high.max() / e - 1
        out["mae"] = hold.low.min() / e - 1
        out["mfe_min"] = (hold.high.idxmax() - r.entry_time).total_seconds() / 60
        out["mae_min"] = (hold.low.idxmin() - r.entry_time).total_seconds() / 60
        out["mae_before_mfe"] = hold.low.idxmin() < hold.high.idxmax()
        out["hold_bar_minutes"] = len(hold)
    if r.expired or not (r.avg_exit > 0):
        return out
    x = r.avg_exit
    day = b[b.index.date == r.exit_time.date()]
    after = day[day.index > t1]
    for k in (1, 3, 5, 15, 30):
        w = after[after.index <= t1 + pd.Timedelta(minutes=k)]
        if len(w):
            out[f"post{k}_close"] = w.close.iloc[-1] / x - 1
            out[f"post{k}_high"] = w.high.max() / x - 1
            out[f"post{k}_low"] = w.low.min() / x - 1
    if len(after):
        out["post_eod_high"] = after.high.max() / x - 1
        out["post_back_above_entry_30"] = bool((after[after.index <= t1 + pd.Timedelta(minutes=30)].high > e).any())
    # liquidity proxy: option volume in the entry minute and the 5 minutes before
    pre = b[(b.index >= t0 - pd.Timedelta(minutes=5)) & (b.index <= t0)]
    out["opt_vol_entry_5m"] = pre.volume.sum()
    ent = b[b.index == t0]
    if len(ent):
        out["entry_vs_vwap"] = r.first_entry_price / ent.vwap.iloc[0] - 1
    ex = b[b.index == t1]
    if len(ex):
        out["exit_vs_vwap"] = x / ex.vwap.iloc[0] - 1
    return out


# ---------------------------------------------------------------- performance
def concurrent_exposure(matches):
    ev = []
    for r in matches.itertuples():
        c = r.qty * r.open_price * 100
        ev += [(r.open_time, c), (r.close_time, -c)]
    s = pd.DataFrame(ev, columns=["t", "c"]).sort_values(["t", "c"])
    s["open"] = s.c.cumsum()
    return s


def core_metrics(ep, fills, matches):
    w, l = ep[ep.win], ep[~ep.win]
    ordered = ep.sort_values("exit_time")
    cum = ordered.pnl.cumsum()
    dd = cum - cum.cummax().clip(lower=0)
    sw, sl = streaks(ordered.win.tolist())
    daily_prem = fills[fills.code == "BTO"].assign(d=lambda x: x.exec_time.dt.strftime("%Y-%m-%d")) \
        .groupby("d").amount.sum().abs()
    expo = concurrent_exposure(matches)
    k = int(ep.win.sum())
    lo, hi = wilson(k, len(ep))
    boot = day_block_bootstrap(ep)
    q = ep.ret.quantile([.05, .25, .5, .75, .95])
    m = {
        "累计已实现净盈亏 $": ep.pnl.sum(),
        "完整交易次数 (episodes)": len(ep),
        "成交笔数 (fills, 不含到期)": int(fills.code.isin(["BTO", "STC"]).sum()),
        "交易天数": ep.day.nunique(),
        "胜率": ep.win.mean(), "胜率 95% CI": f"{lo:.1%} – {hi:.1%}",
        "平均盈利 $": w.pnl.mean(), "平均盈利收益率": w.ret.mean(),
        "平均亏损 $": l.pnl.mean(), "平均亏损率": l.ret.mean(),
        "盈亏比 (avg win / avg loss)": w.pnl.mean() / -l.pnl.mean(),
        "Profit Factor": w.pnl.sum() / -l.pnl.sum(),
        "单笔期望 $": ep.pnl.mean(), "单笔期望 95% CI (按交易日分块 bootstrap)": "%.1f – %.1f" % ci(boot),
        "单笔期望收益率 (按开仓成本)": ep.ret.mean(),
        "收益率分位 5/25/50/75/95%": " / ".join(f"{v:.0%}" for v in q),
        "最大单笔盈利 $": ep.pnl.max(), "最大单笔亏损 $": ep.pnl.min(),
        "最大连续盈利 / 亏损 次数": f"{sw} / {sl}",
        "已实现盈亏最大回撤 $ (从峰值)": dd.min(),
        "累计投入权利金 $": ep.cost.sum(),
        "每日买入权利金 中位数 / 最大 $": f"{daily_prem.median():.0f} / {daily_prem.max():.0f}",
        "权利金效率 (净盈亏/累计权利金)": ep.pnl.sum() / ep.cost.sum(),
        "最大同时持仓权利金 $": expo.open.max(),
        "手续费合计 $": fills.fees.sum(),
    }
    return m, ordered.assign(cum=cum.values, dd=dd.values)


def group_table(ep, by, min_n=1):
    rows = []
    for k, g in ep.groupby(by, observed=True):
        if len(g) < min_n:
            continue
        w, l = g[g.win], g[~g.win]
        lo, hi = wilson(int(g.win.sum()), len(g))
        b = day_block_bootstrap(g, n=1000) if g.day.nunique() >= 3 else np.array([np.nan])
        c = ci(b)
        rows.append({by if isinstance(by, str) else "group": k, "n": len(g), "天数": g.day.nunique(),
                     "胜率": g.win.mean(), "胜率CI": f"{lo:.0%}-{hi:.0%}",
                     "净盈亏": g.pnl.sum(), "期望$": g.pnl.mean(), "期望CI": f"{c[0]:.0f}~{c[1]:.0f}",
                     "均盈": w.pnl.mean(), "均亏": l.pnl.mean(),
                     "盈亏比": w.pnl.mean() / -l.pnl.mean() if len(w) and len(l) else np.nan,
                     "PF": w.pnl.sum() / -l.pnl.sum() if len(l) and l.pnl.sum() < 0 else np.nan,
                     "收益率中位": g.ret.median(), "≤-50%占比": (g.ret <= -.5).mean(),
                     "权利金效率": g.pnl.sum() / g.cost.sum()})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- exits & backtest
def prepare_sim(r):
    """Numpy arrays of the option bars each horizon would walk through, plus the default exit price."""
    b = mk.option_bars(r.occ, r.entry_time, max(r.exit_time, r.entry_time))
    if b is None:
        return None
    t0, t1 = r.entry_time.floor("min"), r.exit_time.floor("min")
    out = {}
    act = b[(b.index > t0) & (b.index < t1)]
    out["actual"] = (act, r.avg_exit if not r.expired else 0.0)
    if not r.overnight:
        day = b[(b.index.date == r.entry_time.date()) & (b.index > t0)]
        d = (day.close.iloc[-1] - slip(day.close.iloc[-1])) if len(day) else r.avg_exit
        out["eod"] = (day, 0.0 if r.expired else d)
    else:
        out["eod"] = out["actual"]
    und = mk.stock_day(r.underlying, r.day)
    conv = {}
    for k, (bars, default) in out.items():
        mins = ((bars.index - r.entry_time).total_seconds() / 60).values
        u = np.full(len(bars), np.nan)
        if und is not None and r.S0 == r.S0 and len(bars):
            uc = und.close
            pos = np.searchsorted(uc.index.values, bars.index.values) - 1   # last completed underlying bar
            ok = pos >= 0
            u[ok] = r.dir * (uc.values[pos[ok]] / r.S0 - 1)
        conv[k] = (mins, bars.open.values, bars.high.values, bars.low.values, u, default)
    return conv


def simulate(e, arrs, tp=None, sl=None, trail=None, tstop=None, und_stop=None, order="conservative",
             tp_through_pct=0.0):
    """Exit price for the FIRST lot of an episode under a rule (entry = first fill price at the first-fill
    time, later add-ons are ignored, so a rule can't 'see' a cheaper average cost before it exists).
    If nothing triggers, the default exit applies (the trader's own average exit, or the last bar of the
    day for the 'eod' horizon)."""
    mins, O, H, L, U, default = arrs
    tp_lv = e * (1 + tp) if tp else None
    sl_lv = e * (1 - sl) if sl else None
    peak = e
    for i in range(len(O)):
        o, h, lo = O[i], H[i], L[i]
        if tstop and mins[i] >= tstop:
            return o - slip(o), "time"
        if und_stop and U[i] == U[i] and U[i] <= -und_stop:
            return o - slip(o), "und"
        stop = None
        if sl_lv and lo <= sl_lv:
            px = min(o, sl_lv)
            stop = px - slip(px)
        if trail and lo <= peak * (1 - trail):
            px = min(o, peak * (1 - trail))
            stop = min(stop, px - slip(px)) if stop is not None else px - slip(px)
        tp_hit = tp_lv is not None and h >= max(tp_lv + TP_TRADE_THROUGH, tp_lv * (1 + tp_through_pct))
        if tp_hit and o >= tp_lv:
            return o, "tp"                      # gapped through the limit: fills at the open
        if stop is not None and tp_hit:
            return (stop, "stop") if order == "conservative" else (tp_lv, "tp")
        if stop is not None:
            return stop, "stop"
        if tp_hit:
            return tp_lv, "tp"
        peak = max(peak, h)
    return default, "none"


def backtest(ep):
    cache = {r.Index: prepare_sim(r) for r in ep.itertuples()}
    tps = [None, .1, .2, .3, .5, 1.0]
    sls = [None, .1, .2, .3, .5]
    res = []

    def run(rule, label, horizon="actual", **kw):
        pnl = []
        for r in ep.itertuples():
            c = cache[r.Index]
            if c is None:
                q = r.first_qty
                pnl.append(((r.avg_exit if not r.expired else 0) - r.first_entry_price) * q * 100 - r.fees * q / r.contracts)
                continue
            px, _ = simulate(r.first_entry_price, c[horizon], **kw)
            q = r.first_qty
            pnl.append((px - r.first_entry_price) * q * 100 - r.fees * q / r.contracts)
        s = pd.Series(pnl, index=ep.index)
        res.append({"rule": rule, "variant": label, "horizon": horizon, **kw, "n": len(s),
                    "total": s.sum(), "expectancy": s.mean(), "win%": (s > 0).mean(), "pnl_series": s})

    for hz in ("actual", "eod"):
        for order in ("conservative", "optimistic"):
            for tp in tps:
                for sl in sls:
                    run("tp_sl", f"{hz}/{order}", horizon=hz, tp=tp, sl=sl, order=order)
    for tp in tps:
        for sl in sls:
            run("tp_sl", "actual/conservative/strict3%", tp=tp, sl=sl, order="conservative", tp_through_pct=.03)
    for tr in (.1, .2, .3, .5):
        run("trail", "actual", trail=tr)
    for ts in (5, 10, 15, 30):
        run("time", "actual", tstop=ts)
    for us in (.001, .002, .003):
        run("und", "actual", und_stop=us)
    return pd.DataFrame(res)


def oos_tp_sl(ep, bt):
    """Pick the best TP/SL cell (conservative fills, actual horizon) on the first half of trading days,
    evaluate on the second half."""
    days = sorted(ep.day.unique())
    cut = days[len(days) // 2]
    first = ep.day < cut
    sub = bt[(bt.rule == "tp_sl") & (bt.variant == "actual/conservative")].copy()
    sub["is_total"] = sub.pnl_series.apply(lambda s: s[first.values].sum())
    sub["oos_total"] = sub.pnl_series.apply(lambda s: s[~first.values].sum())
    best = sub.sort_values("is_total").iloc[-1]
    base = sub[(sub.tp.isna()) & (sub.sl.isna())].iloc[0]
    return dict(split_day=cut, n_is=int(first.sum()), n_oos=int((~first).sum()),
                best_tp=best.tp, best_sl=best.sl, is_total=best.is_total, oos_total=best.oos_total,
                actual_is=base.is_total, actual_oos=base.oos_total)


# ---------------------------------------------------------------- attribution (lot level)
def attribution(matches, fills):
    meta = fills.drop_duplicates("occ").set_index("occ")[["underlying", "type", "strike", "expiry"]]
    rows = []
    for r in matches.itertuples():
        m = meta.loc[r.occ]
        S0 = mk.underlying_price(m.underlying, r.open_time)
        t1 = r.close_time if r.close_code != "OEXP" else pd.Timestamp(f"{m.expiry} 15:59:59", tz=TZ)
        S1 = mk.underlying_price(m.underlying, t1)
        T0, T1 = mk.years_to_expiry(r.open_time, m.expiry), mk.years_to_expiry(r.close_time, m.expiry)
        if r.close_code == "OEXP":
            T1 = 0.0
        iv0 = mk.implied_vol(r.open_price, S0, m.strike, T0, m.type)
        mult = r.qty * 100
        d = dict(occ=r.occ, open_time=r.open_time, qty=r.qty, pnl=r.pnl, fees=r.fees, S0=S0, S1=S1, iv0=iv0)
        if iv0 == iv0 and S1 == S1:
            p0 = mk.bs_price(S0, m.strike, T0, iv0, m.type)
            pS = mk.bs_price(S1, m.strike, T0, iv0, m.type)
            pT = mk.bs_price(S1, m.strike, T1, iv0, m.type)
            d["underlying_$"] = (pS - p0) * mult
            d["time_$"] = (pT - pS) * mult
            iv1 = mk.implied_vol(r.close_price, S1, m.strike, T1, m.type) if T1 > 0 else np.nan
            d["iv1"] = iv1
            rest = (r.close_price - pT) * mult
            if iv1 == iv1:
                d["vol_$"] = rest
                d["residual_$"] = 0.0
            else:
                d["vol_$"] = np.nan
                d["residual_$"] = rest      # price below model value (intrinsic) / expiry
            g = mk.greeks(S0, m.strike, T0, iv0, m.type)
            dS, dt = S1 - S0, (T1 - T0) * mk.MIN_PER_YEAR * -1
            approx = g["delta"] * dS + .5 * g["gamma"] * dS ** 2 + g["theta_min"] * dt + \
                (g["vega"] * (iv1 - iv0) * 100 if iv1 == iv1 else 0)
            d["greek_approx_$"] = approx * mult
            d["greek_approx_err_$"] = (r.close_price - r.open_price) * mult - approx * mult
        rows.append(d)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- behavior
def behavior(ep, fills):
    ep = ep.sort_values("entry_time").copy()
    ep["seq_in_day"] = ep.groupby("day").cumcount() + 1
    ep["n_in_day"] = ep.groupby("day").occ.transform("size")
    ep["reentry_same_contract"] = ep.groupby(["day", "occ"]).cumcount() > 0
    ep["prev_win"] = ep.groupby("day").win.shift(1)
    ep["prev_pnl"] = ep.groupby("day").pnl.shift(1)
    prev_exit = ep.groupby("day").exit_time.shift(1)
    ep["gap_after_prev_min"] = (ep.entry_time - prev_exit).dt.total_seconds() / 60
    ep["cost_vs_median20"] = ep.cost / ep.cost.rolling(20, min_periods=5).median().shift(1)
    # averaging down / up
    tag = {}
    f = fills[fills.code == "BTO"]
    for r in ep[ep.n_buys > 1].itertuples():
        b = f[(f.occ == r.occ) & (f.exec_time >= r.entry_time) & (f.exec_time <= r.exit_time)].sort_values("exec_time")
        tag[r.Index] = "加仓-价格更低(摊平)" if b.price.iloc[1:].mean() < b.price.iloc[0] else "加仓-价格更高(加码)"
    ep["add_type"] = pd.Series(tag).reindex(ep.index).fillna("单次建仓")
    daily = ep.groupby("day").agg(n=("pnl", "size"), pnl=("pnl", "sum"), first=("pnl", "first"))
    daily["n_bucket"] = pd.cut(daily.n, [0, 2, 4, 7, 100], labels=["1-2", "3-4", "5-7", "8+"])
    ep["day_n_bucket"] = ep.day.map(daily.n_bucket)
    ep["cost_q"] = pd.qcut(ep.cost, 5, labels=["Q1 最小", "Q2", "Q3", "Q4", "Q5 最大"])
    return ep, daily


def loss_concentration(ep):
    l = ep[~ep.win].pnl.sort_values()
    w = ep[ep.win].pnl
    top10 = l.head(max(1, int(np.ceil(len(l) * .1))))
    return {"亏损笔数": len(l), "最大10%亏损笔数": len(top10), "其占总亏损比例": top10.sum() / l.sum(),
            "最大单笔亏损 / 盈利中位数": -l.min() / w.median(),
            "盈利中位数 $": w.median(), "亏损中位数 $": l.median()}


# ---------------------------------------------------------------- robustness
def robustness(ep):
    s = ep.sort_values("pnl", ascending=False)
    out = {f"剔除最大{k}笔盈利后净盈亏": s.pnl.iloc[k:].sum() for k in (1, 3, 5)}
    days = [g.sort_values("exit_time").pnl.values for _, g in ep.groupby("day")]
    sims, dds, streak = [], [], []
    for _ in range(5000):
        idx = RNG.integers(0, len(days), len(days))
        p = np.concatenate([days[i] for i in idx])
        c = p.cumsum()
        sims.append(c[-1])
        dds.append((c - np.maximum.accumulate(np.maximum(c, 0))).min())
        streak.append(streaks((p > 0).tolist())[1])
    sims, dds, streak = map(np.array, (sims, dds, streak))
    out.update({
        "按交易日重抽样(5000次, 与样本同长度) 净盈亏 中位数": np.median(sims),
        "  净盈亏 5%–95%": f"{np.percentile(sims, 5):.0f} ~ {np.percentile(sims, 95):.0f}",
        "  净盈亏>0 的概率": (sims > 0).mean(),
        "  最大回撤 中位数 / 5%分位(更差)": f"{np.median(dds):.0f} / {np.percentile(dds, 5):.0f}",
        "  最长连亏笔数 中位数 / 95%分位": f"{np.median(streak):.0f} / {np.percentile(streak, 95):.0f}",
    })
    return out, sims, dds


# ---------------------------------------------------------------- signal study / control group
def minute_panel(sym, start, end):
    """Vectorized features for every minute (features use bars before the minute; fwd_ are outcomes)."""
    days = [d for d in mk.trading_days(sym) if start <= d <= end]
    allv = mk.minute_of_day_volume(sym)
    frames = []
    for d in days:
        b = mk.stock_day(sym, d)
        if b is None or len(b) < 300:
            continue
        c = b.close
        f = pd.DataFrame(index=b.index)
        prev = c.shift(1)                        # last completed bar before this minute
        for k in (1, 3, 5, 15, 30, 60):
            f[f"ret_{k}"] = prev / c.shift(1 + k) - 1
        f["accel_3"] = (prev - c.shift(4)) / c.shift(4) - (c.shift(4) - c.shift(7)) / c.shift(7)
        pv = (b.vwap * b.volume).cumsum().shift(1) / b.volume.cumsum().shift(1)
        f["vwap_dist"] = prev / pv - 1
        hi, lo = b.high.cummax().shift(1), b.low.cummin().shift(1)
        f["range_pos"] = (prev - lo) / (hi - lo)
        v5 = b.volume.rolling(5).sum().shift(1)
        pdays = [x for x in allv.index if x < d][-20:]
        if len(pdays) >= 10:
            base = allv.loc[pdays].mean().rolling(5).sum().shift(1)
            mod = (b.index.hour * 60 + b.index.minute) - 570
            f["rvol_5"] = v5.values / base.reindex(mod).values
        for k in (5, 15, 30):
            f[f"fwd_{k}"] = c.shift(-(k - 1)) / prev - 1
        f["day"] = d
        f["sym"] = sym
        f["mod"] = (b.index.hour * 60 + b.index.minute) - 570
        frames.append(f)
    return pd.concat(frames)


def signal_study(ep):
    e = ep[ep.etf & ep.ret_5.notna()].copy()
    start, end = e.day.min(), e.day.max()
    panel = pd.concat([minute_panel(s, start, end) for s in INDEX_ETFS])
    panel = panel[(panel["mod"] >= 15) & (panel["mod"] <= 375)].dropna(subset=["ret_5", "fwd_15", "rvol_5"])
    panel["sdir"] = np.sign(panel.ret_5)
    for k in (5, 15, 30):
        panel[f"cont_{k}"] = panel.sdir * panel[f"fwd_{k}"]        # continuation in the direction of the last 5 min
    panel["abs_ret_5"] = panel.ret_5.abs()
    qs = panel.abs_ret_5.quantile([.5, .8, .9, .95]).values
    rq = panel.rvol_5.quantile([.5, .8, .9, .95]).values
    panel["mom_q"] = pd.cut(panel.abs_ret_5, [-1, *qs, 1], labels=["<P50", "P50-80", "P80-90", "P90-95", ">P95"])
    panel["rvol_q"] = pd.cut(panel.rvol_5, [-1, *rq, 1e9], labels=["<P50", "P50-80", "P80-90", "P90-95", ">P95"])
    grid = panel.groupby(["mom_q", "rvol_q"], observed=True).agg(
        n=("cont_15", "size"), cont15_bp=("cont_15", lambda s: s.mean() * 1e4),
        hit=("cont_15", lambda s: (s > 0).mean())).reset_index()
    # where do my entries sit in the distribution of all minutes?
    e["abs_ret_5"] = e.ret_5.abs()
    e["mom_pct"] = [(panel.abs_ret_5 < v).mean() for v in e.abs_ret_5]
    e["rvol_pct"] = [(panel.rvol_5 < v).mean() if v == v else np.nan for v in e.rvol_5]
    e["mom_q"] = pd.cut(e.abs_ret_5, [-1, *qs, 1], labels=["<P50", "P50-80", "P80-90", "P90-95", ">P95"])
    e["rvol_q"] = pd.cut(e.rvol_5, [-1, *rq, 1e9], labels=["<P50", "P50-80", "P80-90", "P90-95", ">P95"])
    # matched control: same symbol, same day, same momentum & rvol bucket, direction = my direction
    ctrl = []
    for r in e.itertuples():
        c = panel[(panel.sym == r.underlying) & (panel.day == r.day) & (panel.mom_q == r.mom_q) &
                  (panel.rvol_q == r.rvol_q) & (np.sign(panel.ret_5) == np.sign(r.ret_5))]
        c = c[(c.index < r.entry_time.floor("min") - pd.Timedelta(minutes=15)) |
              (c.index > r.entry_time.floor("min") + pd.Timedelta(minutes=15))]
        ctrl.append(dict(occ=r.occ, entry_time=r.entry_time, ctrl_n=len(c),
                         ctrl_dfwd_15=(r.dir * c.fwd_15).mean() if len(c) else np.nan))
    e = e.merge(pd.DataFrame(ctrl), on=["occ", "entry_time"])
    # objective rule, chosen in-sample, tested out-of-sample (non-overlapping signals: 15-min cooldown)
    days = sorted(panel.day.unique())
    cut = days[len(days) // 2]
    rules = []
    for mq in (.8, .9, .95):
        for rv in (1.0, 1.5, 2.0, 3.0):
            th = panel.abs_ret_5.quantile(mq)
            sig = panel[(panel.abs_ret_5 >= th) & (panel.rvol_5 >= rv)]
            sig = cooldown(sig, 15)
            for half, s in (("IS", sig[sig.day < cut]), ("OOS", sig[sig.day >= cut])):
                b = day_block_bootstrap(s, n=1000, col="cont_15")
                lo, hi = ci(b)
                rules.append(dict(mom_pctile=mq, rvol_min=rv, half=half, n=len(s), days=s.day.nunique(),
                                  cont15_bp=s.cont_15.mean() * 1e4, hit=(s.cont_15 > 0).mean(),
                                  ci_lo_bp=lo * 1e4, ci_hi_bp=hi * 1e4))
    rules = pd.DataFrame(rules)
    base = panel.groupby(panel.day < cut).cont_15.mean() * 1e4
    return panel, grid, e, rules, {"split_day": cut, "all_minutes_cont15_bp_IS": base.get(True),
                                   "all_minutes_cont15_bp_OOS": base.get(False)}


def cooldown(sig, minutes):
    keep, last = [], {}
    for t, s in zip(sig.index, sig.sym):
        if s not in last or (t - last[s]).total_seconds() / 60 >= minutes:
            keep.append(True)
            last[s] = t
        else:
            keep.append(False)
    return sig[np.array(keep)]
