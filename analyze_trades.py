"""Round-trip analysis of SPY/QQQ/IWM option trades using exact fill times + 1-minute option bars.

Inputs : data/option_fills.csv (build_fills.py), data/option_minute/<occ>/<date>.csv (fetch_option_bars.py),
         data/minute/<sym>/<date>.csv (fetch_minute_bars.py), statement CSV (for OEXP = expired worthless)
Output : data/round_trips.csv, and a printed summary.

A round trip = one contract from flat -> position -> flat again (scaling in/out stays in the same trip).
Price-path metrics use option bars strictly after the entry minute and before the exit minute
(so the fill minute's own high/low, which may be before/after the fill, isn't counted).
  mfe_pct   : best high during the hold vs avg entry      (how much it was up at best)
  mae_pct   : worst low during the hold vs avg entry      (how much it was down at worst)
  capture   : realized gain / best possible gain (only when mfe > 0)
  post30_pct: best high in the 30 min after the exit vs avg exit  (did I sell too early)
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
DATA = ROOT / "data"
SYMS = ["SPY", "QQQ", "IWM"]
TZ = "America/New_York"

_bar_cache = {}


def bars(path):
    if path not in _bar_cache:
        if path.exists():
            b = pd.read_csv(path)
            b["timestamp"] = pd.to_datetime(b["timestamp"], utc=True).dt.tz_convert(TZ)
            _bar_cache[path] = b.set_index("timestamp").sort_index()
        else:
            _bar_cache[path] = None
    return _bar_cache[path]


def option_bars(occ, start, end):
    days = pd.bdate_range(start.date(), end.date()).date
    parts = [bars(DATA / "option_minute" / occ / f"{d}.csv") for d in days]
    parts = [p for p in parts if p is not None]
    return pd.concat(parts) if parts else pd.DataFrame(columns=["high", "low", "close"])


def underlying_px(sym, t):
    b = bars(DATA / "minute" / sym / f"{t.date()}.csv")
    if b is None:
        return np.nan
    b = b[b.index <= t.floor("min")]
    return b["close"].iloc[-1] if len(b) else np.nan


def load_fills():
    f = pd.read_csv(DATA / "option_fills.csv")
    f["exec_time"] = pd.to_datetime(f["exec_time"], utc=True, format="ISO8601").dt.tz_convert(TZ)
    f = f[f["underlying"].isin(SYMS)].copy()
    # expired-worthless positions: synthetic sell at 0 at 16:00 on expiry
    net = f.assign(s=f["qty"] * f["code"].map({"BTO": 1, "STC": -1})).groupby("occ")["s"].sum()
    exp = []
    for occ, q in net[net > 0].items():
        r = f[f["occ"] == occ].iloc[0]
        exp.append(dict(r, exec_time=pd.Timestamp(f"{r.expiry} 16:00", tz=TZ), date=r.expiry,
                        code="EXP", qty=q, price=0.0, amount=0.0, fees=0.0))
    return pd.concat([f, pd.DataFrame(exp)]).sort_values("exec_time").reset_index(drop=True)


def round_trips(f):
    out = []
    for occ, g in f.groupby("occ"):
        pos, cur = 0, []
        for r in g.itertuples():
            cur.append(r)
            pos += r.qty if r.code == "BTO" else -r.qty
            if pos == 0:
                out.append(summarize(occ, cur))
                cur = []
    return pd.DataFrame(out)


def summarize(occ, fills):
    buys = [x for x in fills if x.code == "BTO"]
    sells = [x for x in fills if x.code != "BTO"]
    q = sum(x.qty for x in buys)
    entry = sum(x.qty * x.price for x in buys) / q
    exit_ = sum(x.qty * x.price for x in sells) / q
    t0, t1 = buys[0].exec_time, sells[-1].exec_time
    cost = -sum(x.amount for x in buys)
    pnl = sum(x.amount for x in fills)
    b0 = buys[0]
    r = dict(occ=occ, underlying=b0.underlying, type=b0.type, strike=b0.strike, expiry=b0.expiry,
             entry_time=t0, exit_time=t1, hold_min=(t1 - t0).total_seconds() / 60,
             dte=(pd.Timestamp(b0.expiry).date() - t0.date()).days, contracts=q,
             n_buys=len(buys), n_sells=len(sells), expired=any(x.code == "EXP" for x in sells),
             avg_entry=entry, avg_exit=exit_, cost=cost, pnl=pnl, ret=pnl / cost)

    ob = option_bars(occ, t0, t1 + pd.Timedelta(hours=1))
    hold = ob[(ob.index > t0.floor("min")) & (ob.index < t1.floor("min"))]
    if len(hold):
        r["mfe_pct"] = hold["high"].max() / entry - 1
        r["mae_pct"] = hold["low"].min() / entry - 1
        r["mfe_min"] = (hold["high"].idxmax() - t0).total_seconds() / 60
    best = r.get("mfe_pct", np.nan)
    r["capture"] = (exit_ / entry - 1) / best if best and best > 0 else np.nan
    if not r["expired"]:
        for m in (5, 15, 30, 60):
            post = ob[(ob.index > t1.floor("min")) & (ob.index <= t1 + pd.Timedelta(minutes=m))
                      & (ob.index.date == t1.date())]
            r[f"post{m}_pct"] = post["high"].max() / exit_ - 1 if len(post) and exit_ > 0 else np.nan
            if m == 30:
                r["post30_low_pct"] = post["low"].min() / exit_ - 1 if len(post) and exit_ > 0 else np.nan
    u0, u1 = underlying_px(b0.underlying, t0), underlying_px(b0.underlying, min(t1, t1.normalize() + pd.Timedelta(hours=15, minutes=59)))
    r["und_move_pct"] = u1 / u0 - 1
    return r


def bucket_table(rt, by):
    g = rt.groupby(by, observed=True)
    t = pd.DataFrame({
        "trades": g.size(),
        "win%": g["pnl"].apply(lambda s: (s > 0).mean() * 100),
        "pnl": g["pnl"].sum(),
        "avg_pnl": g["pnl"].mean(),
        "avg_win": g["pnl"].apply(lambda s: s[s > 0].mean()),
        "avg_loss": g["pnl"].apply(lambda s: s[s <= 0].mean()),
        "avg_ret%": g["ret"].mean() * 100,
    })
    return t.round(1)


def main():
    rt = round_trips(load_fills()).sort_values("entry_time").reset_index(drop=True)
    rt.to_csv(DATA / "round_trips.csv", index=False)

    rt["result"] = np.where(rt["pnl"] > 0, "win", "loss")
    rt["hour"] = rt["entry_time"].dt.hour
    rt["tod"] = pd.cut(rt["entry_time"].dt.hour * 60 + rt["entry_time"].dt.minute,
                       [0, 600, 660, 780, 900, 1000], right=False,
                       labels=["09:30-10:00", "10:00-11:00", "11:00-13:00", "13:00-15:00", "15:00-16:00"])
    rt["hold"] = pd.cut(rt["hold_min"], [0, 5, 15, 30, 60, 240, 1e9], right=False,
                        labels=["<5m", "5-15m", "15-30m", "30-60m", "1-4h", "overnight+"])
    rt["dte_b"] = np.where(rt["dte"] == 0, "0DTE", "1+DTE")
    rt["month"] = rt["entry_time"].dt.strftime("%Y-%m")
    rt["scaled_in"] = np.where(rt["n_buys"] > 1, "added to position", "single entry")

    pd.set_option("display.width", 200)
    w, l = rt[rt.pnl > 0], rt[rt.pnl <= 0]
    print(f"Round trips: {len(rt)}  ({rt.entry_time.min():%Y-%m-%d} .. {rt.exit_time.max():%Y-%m-%d})")
    print(f"Net P&L (after fees): ${rt.pnl.sum():,.2f}   win rate {len(w)/len(rt):.1%}   "
          f"avg win ${w.pnl.mean():,.2f}   avg loss ${l.pnl.mean():,.2f}   "
          f"profit factor {w.pnl.sum()/-l.pnl.sum():.2f}   fees ${rt.cost.sum()*0 + load_fills().fees.sum():,.2f}")
    print(f"Median hold: winners {w.hold_min.median():.1f} min, losers {l.hold_min.median():.1f} min")
    for col in ["underlying", "type", "dte_b", "tod", "hold", "scaled_in", "month"]:
        print(f"\n== by {col}\n{bucket_table(rt, col).to_string()}")

    print("\n== price path (median)")
    print(rt.groupby("result")[["mfe_pct", "mae_pct", "capture", "post15_pct", "post30_pct"]].median().mul(100).round(1).to_string())
    print(f"\nLosers that were up >=20% at some point during the hold: "
          f"{(l.mfe_pct >= .2).sum()}/{l.mfe_pct.notna().sum()}  (lost ${l[l.mfe_pct >= .2].pnl.sum():,.0f})")
    print(f"Winners that first went down >=20%: {(w.mae_pct <= -.2).sum()}/{w.mae_pct.notna().sum()}")
    print(f"Exits where price rose >=20% above my exit within 30 min: "
          f"{(rt.post30_pct >= .2).sum()}/{rt.post30_pct.notna().sum()}")
    print(f"Exits where price fell >=20% below my exit within 30 min:  "
          f"{(rt.post30_low_pct <= -.2).sum()}/{rt.post30_low_pct.notna().sum()}")
    for th in (-.2, -.3, -.5):
        hit = rt[rt.mae_pct <= th]
        print(f"Trades that hit {th:.0%} drawdown: {len(hit)}, of which ended winners: {(hit.pnl > 0).sum()}, "
              f"P&L ${hit.pnl.sum():,.0f}")
    print("\nWorst 8 trades:")
    print(rt.nsmallest(8, "pnl")[["entry_time", "occ", "contracts", "avg_entry", "avg_exit", "hold_min",
                                    "pnl", "mfe_pct", "mae_pct", "n_buys"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
