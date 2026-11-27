"""Download 1-minute regular-session bars for the underlyings I trade options on.

Sources:
  - yfinance  : no key, but only the last ~30 days of 1m data.
  - alpaca    : free account key, stock bars back to 2016 (set ALPACA_API_KEY / ALPACA_API_SECRET).

Output: data/minute/{SYMBOL}/{YYYY-MM-DD}.csv  (timestamp in America/New_York, open/high/low/close/volume)
Only trading days on which I traded that underlying's options are fetched; existing files are skipped.

Usage:
  python fetch_minute_bars.py                      # SPY QQQ IWM, auto source
  python fetch_minute_bars.py --symbols SPY --source alpaca
"""
import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).parent
TRADES = next(ROOT.glob("*.csv"))
OUT = ROOT / "data" / "minute"
OUT_EXT = ROOT / "data" / "minute_ext"     # --extended: 04:00-19:59 ET (pre-market + regular + after-hours)
TZ = "America/New_York"


def get_with_retry(url, **kw):
    """GET that waits and retries on HTTP 429 (Alpaca free plan: 200 requests/min)."""
    import time
    for attempt in range(8):
        r = requests.get(url, **kw)
        if r.status_code != 429:
            r.raise_for_status()
            return r
        time.sleep(min(60, 5 * 2 ** attempt))
    r.raise_for_status()


def trade_days(symbols):
    df = pd.read_csv(TRADES, on_bad_lines="skip", usecols=range(9)).dropna(subset=["Activity Date"])
    o = df[df["Description"].str.contains(r" (?:Call|Put) \$", na=False) & df["Instrument"].isin(symbols)]
    o = o.assign(d=pd.to_datetime(o["Activity Date"]).dt.date)
    return {s: sorted(g["d"].unique()) for s, g in o.groupby("Instrument")}


def regular_session(df):
    df = df.tz_convert(TZ) if df.index.tz else df.tz_localize("UTC").tz_convert(TZ)
    return df.between_time("09:30", "15:59")


def fetch_yf(sym, day):
    import yfinance as yf
    d = yf.download(sym, start=day, end=day + timedelta(days=1), interval="1m",
                    progress=False, auto_adjust=False)
    if d.empty:
        return d
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    d = d.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    return regular_session(d)


def extended_session(df):
    df = df.tz_convert(TZ) if df.index.tz else df.tz_localize("UTC").tz_convert(TZ)
    return df.between_time("04:00", "19:59")


def fetch_alpaca(sym, day, extended=False):
    import requests
    key, sec = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_API_SECRET")
    if not key or not sec:
        raise RuntimeError("set ALPACA_API_KEY and ALPACA_API_SECRET")
    rows, token = [], None
    while True:
        start, end = (f"{day}T08:00:00Z", f"{day + timedelta(days=1)}T01:30:00Z") if extended             else (f"{day}T13:00:00Z", f"{day}T21:30:00Z")
        params = {"timeframe": "1Min", "start": start, "end": end,
                  "limit": 10000, "adjustment": "raw", "feed": os.environ.get("ALPACA_FEED", "sip")}
        if token:
            params["page_token"] = token
        r = get_with_retry(f"https://data.alpaca.markets/v2/stocks/{sym}/bars", params=params,
                           headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}, timeout=30)
        j = r.json()
        rows += j.get("bars") or []
        token = j.get("next_page_token")
        if not token:
            break
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows).rename(columns={"t": "timestamp", "o": "open", "h": "high", "l": "low",
                                           "c": "close", "v": "volume", "n": "trades", "vw": "vwap"})
    d = d.set_index(pd.to_datetime(d.pop("timestamp"), utc=True))
    d = d[["open", "high", "low", "close", "volume", "trades", "vwap"]]
    return extended_session(d) if extended else regular_session(d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["SPY", "QQQ", "IWM"])
    ap.add_argument("--source", choices=["auto", "yf", "alpaca"], default="auto")
    ap.add_argument("--range", nargs=2, metavar=("START", "END"),
                    help="fetch every weekday in this range instead of only my option-trade days")
    ap.add_argument("--extended", action="store_true",
                    help="Alpaca only: 04:00-19:59 ET bars into data/minute_ext/, for every day already in data/minute/")
    a = ap.parse_args()
    out = OUT_EXT if a.extended else OUT

    yf_cutoff = date.today() - timedelta(days=29)
    has_alpaca = bool(os.environ.get("ALPACA_API_KEY"))
    missing = []
    if a.extended:
        plan = {p.name: [date.fromisoformat(f.stem) for f in sorted(p.glob("*.csv"))]
                for p in sorted(OUT.iterdir()) if p.is_dir() and (p.name in a.symbols or a.symbols == ["ALL"])}
        a.source = "alpaca"
    elif a.range:
        wd = list(pd.bdate_range(*a.range).date)
        plan = {s: wd for s in a.symbols}
    else:
        plan = trade_days(a.symbols)
    for sym, days in plan.items():
        (out / sym).mkdir(parents=True, exist_ok=True)
        for day in days:
            f = out / sym / f"{day}.csv"
            if f.exists():
                continue
            src = a.source
            if src == "auto":
                src = "alpaca" if has_alpaca else ("yf" if day >= yf_cutoff else None)
            if src is None:
                missing.append((sym, day))
                continue
            try:
                d = fetch_alpaca(sym, day, a.extended) if src == "alpaca" else fetch_yf(sym, day)
            except Exception as e:
                print(f"{sym} {day} {src}: ERROR {e}", file=sys.stderr)
                missing.append((sym, day))
                continue
            if d.empty:
                print(f"{sym} {day} {src}: no data (holiday?)", file=sys.stderr)
                if not a.range:
                    missing.append((sym, day))
                continue
            d.index.name = "timestamp"
            d.to_csv(f)
            print(f"{sym} {day} {src}: {len(d)} bars")
    if missing:
        print(f"\n{len(missing)} symbol-days still missing (need Alpaca key):")
        for s, d in missing:
            print(f"  {s} {d}")


if __name__ == "__main__":
    main()
