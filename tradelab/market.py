"""Minute bars, entry-context features (no look-ahead), Black-Scholes IV / Greeks."""
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

from .config import OPT_MIN, RISK_FREE, STOCK_MIN, STOCK_MIN_EXT, TZ

MIN_PER_YEAR = 365 * 24 * 60


@lru_cache(maxsize=None)
def stock_day(sym, day, extended=False):
    """Regular-session bars (09:30-15:59); extended=True reads 04:00-19:59 bars from data/minute_ext/."""
    p = (STOCK_MIN_EXT if extended else STOCK_MIN) / sym / f"{day}.csv"
    if not p.exists():
        return None
    b = pd.read_csv(p)
    b["timestamp"] = pd.to_datetime(b["timestamp"], utc=True).dt.tz_convert(TZ)
    b = b.set_index("timestamp").sort_index()
    return b


@lru_cache(maxsize=None)
def option_day(o, day):
    p = OPT_MIN / o / f"{day}.csv"
    if not p.exists():
        return None
    b = pd.read_csv(p)
    b["timestamp"] = pd.to_datetime(b["timestamp"], utc=True).dt.tz_convert(TZ)
    return b.set_index("timestamp").sort_index()


def option_bars(o, start, end):
    parts = [option_day(o, str(d)) for d in pd.bdate_range(start.date(), end.date()).date]
    parts = [p for p in parts if p is not None]
    return pd.concat(parts) if parts else None


@lru_cache(maxsize=None)
def trading_days(sym):
    return sorted(p.stem for p in (STOCK_MIN / sym).glob("*.csv"))


@lru_cache(maxsize=None)
def minute_of_day_volume(sym):
    """volume by (day, minute-of-session) for RVOL baselines; only for symbols with continuous history."""
    rows = {}
    for d in trading_days(sym):
        b = stock_day(sym, d)
        mod = (b.index.hour * 60 + b.index.minute) - 570
        rows[d] = pd.Series(b["volume"].values, index=mod)
    return pd.DataFrame(rows).T.sort_index()     # index day, columns minute 0..389


def underlying_price(sym, t, before=True):
    """Close of the last completed minute before t (before=True), else close of the minute containing t.
    Outside 09:30-16:00 the extended-hours file is used when it exists (pre-market / after-hours fills)."""
    day = t.strftime("%Y-%m-%d")
    hm = t.hour * 60 + t.minute
    b = stock_day(sym, day, True) if (hm < 570 or hm > 960) else None
    if b is None:
        b = stock_day(sym, day)
    if b is None:
        return np.nan
    m = t.floor("min")
    s = b[b.index < m] if before else b[b.index <= m]
    if len(s) == 0:
        s = b[b.index <= m]
        return s["open"].iloc[-1] if len(s) else b["open"].iloc[0]
    return s["close"].iloc[-1]


def context(sym, t, continuous):
    """Features known strictly before minute t (no look-ahead) plus forward outcomes (labelled fwd_)."""
    day = t.strftime("%Y-%m-%d")
    b = stock_day(sym, day)
    if b is None:
        return {}
    m = t.floor("min")
    past = b[b.index < m]
    fut = b[b.index >= m]
    f = {}
    if len(past) == 0:
        f["minutes_since_open"] = 0
        return f
    c = past["close"].values
    c0 = c[-1]
    f["minutes_since_open"] = len(past)
    for k in (1, 3, 5, 15, 30, 60):
        f[f"ret_{k}"] = c0 / c[-1 - k] - 1 if len(c) > k else np.nan
    f["ret_open"] = c0 / past["open"].iloc[0] - 1
    if len(c) >= 7:
        f["accel_3"] = (c[-1] - c[-4]) / c[-4] - (c[-4] - c[-7]) / c[-7]
    r1 = np.diff(np.log(c[-31:])) if len(c) > 2 else np.array([])
    f["rv_30"] = r1.std() * np.sqrt(390 * 252) if len(r1) > 5 else np.nan
    vw = (past["vwap"] * past["volume"]).cumsum() / past["volume"].cumsum() if "vwap" in past else None
    if vw is not None:
        f["vwap_dist"] = c0 / vw.iloc[-1] - 1
    hi, lo = past["high"].max(), past["low"].min()
    f["range_pos"] = (c0 - lo) / (hi - lo) if hi > lo else np.nan
    f["day_range_pct"] = hi / lo - 1
    # breakout: last 3 bars exceed the prior 30-min extreme
    if len(past) >= 33:
        ph, pl = past["high"].iloc[-33:-3].max(), past["low"].iloc[-33:-3].min()
        f["break_up"] = past["high"].iloc[-3:].max() > ph
        f["break_dn"] = past["low"].iloc[-3:].min() < pl
        f["prior30_high"], f["prior30_low"] = ph, pl
    f["vol_5"] = past["volume"].iloc[-5:].sum()
    if continuous:
        mv = minute_of_day_volume(sym)
        prev = [d for d in mv.index if d < day][-20:]
        i1 = len(past)  # minute-of-session index of m
        if len(prev) >= 10 and i1 >= 5:
            base = mv.loc[prev].iloc[:, i1 - 5:i1].sum(axis=1).mean()
            f["rvol_5"] = f["vol_5"] / base if base else np.nan
            base15 = mv.loc[prev].iloc[:, max(0, i1 - 15):i1].sum(axis=1).mean()
            f["rvol_15"] = past["volume"].iloc[-15:].sum() / base15 if base15 else np.nan
    # forward outcomes (labels, never used as features)
    for k in (5, 15, 30):
        f[f"fwd_{k}"] = fut["close"].iloc[k - 1] / c0 - 1 if len(fut) >= k else np.nan
    f["u_price"] = c0
    return f


# ---------- Black-Scholes ----------
def bs_price(S, K, T, sigma, cp, r=RISK_FREE):
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K) if cp == "Call" else max(0.0, K - S)
    d1 = (np.log(S / K) + (r + sigma ** 2 / 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if cp == "Call":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def implied_vol(price, S, K, T, cp):
    if not (price > 0 and S > 0 and T > 0):
        return np.nan
    intrinsic = max(0.0, S - K) if cp == "Call" else max(0.0, K - S)
    if price <= intrinsic + 1e-4:
        return np.nan
    try:
        return brentq(lambda s: bs_price(S, K, T, s, cp) - price, 1e-4, 10.0, xtol=1e-6)
    except ValueError:
        return np.nan


def greeks(S, K, T, sigma, cp, r=RISK_FREE):
    if not (T > 0 and sigma > 0):
        return dict(delta=np.nan, gamma=np.nan, theta_min=np.nan, vega=np.nan)
    sq = np.sqrt(T)
    d1 = (np.log(S / K) + (r + sigma ** 2 / 2) * T) / (sigma * sq)
    d2 = d1 - sigma * sq
    pdf = norm.pdf(d1)
    delta = norm.cdf(d1) if cp == "Call" else norm.cdf(d1) - 1
    gamma = pdf / (S * sigma * sq)
    if cp == "Call":
        theta = -S * pdf * sigma / (2 * sq) - r * K * np.exp(-r * T) * norm.cdf(d2)
    else:
        theta = -S * pdf * sigma / (2 * sq) + r * K * np.exp(-r * T) * norm.cdf(-d2)
    return dict(delta=delta, gamma=gamma, theta_min=theta / MIN_PER_YEAR, vega=S * pdf * sq / 100)


def years_to_expiry(t, expiry):
    exp = pd.Timestamp(f"{expiry} 16:00", tz=TZ)
    return max((exp - t).total_seconds() / 60, 0) / MIN_PER_YEAR
