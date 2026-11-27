"""Download 1-minute bars for every option contract I traded (Alpaca, needs ALPACA_API_KEY / ALPACA_API_SECRET).

For each contract, fetches every trading day from its first fill to its last fill (capped at expiry),
so overnight holds are covered too. Option bars are sparse: minutes with no trades have no bar.

Output: data/option_minute/{OCC_SYMBOL}/{YYYY-MM-DD}.csv   (timestamp in America/New_York)
        data/option_minute/contracts.csv                     (contract -> underlying, expiry, type, strike)

Usage:
  python fetch_option_bars.py                 # SPY QQQ IWM
  python fetch_option_bars.py --symbols QQQ
"""
import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).parent
TRADES = next(ROOT.glob("*.csv"))
OUT = ROOT / "data" / "option_minute"
TZ = "America/New_York"
DESC = re.compile(r"^(\S+) (\d+/\d+/\d{4}) (Call|Put) \$([\d,.]+)$")


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


def occ(root, expiry, cp, strike):
    return f"{root}{expiry:%y%m%d}{cp[0]}{round(strike * 1000):08d}"


def load_contracts(symbols):
    df = pd.read_csv(TRADES, on_bad_lines="skip", usecols=range(9)).dropna(subset=["Activity Date"])
    df = df[df["Instrument"].isin(symbols) & df["Trans Code"].isin(["BTO", "STC", "STO", "BTC"])]
    rows = []
    for desc, day in zip(df["Description"], pd.to_datetime(df["Activity Date"]).dt.date):
        m = DESC.match(desc.strip())
        if not m:
            print(f"skip unparsed: {desc!r}", file=sys.stderr)
            continue
        root, exp, cp, k = m.groups()
        exp = pd.to_datetime(exp).date()
        k = float(k.replace(",", ""))
        rows.append(dict(symbol=occ(root, exp, cp, k), underlying=root, expiry=exp, type=cp,
                         strike=k, day=day))
    t = pd.DataFrame(rows)
    return t.groupby(["symbol", "underlying", "expiry", "type", "strike"]).day.agg(["min", "max"]).reset_index()


def fetch_day(symbols, day, headers):
    bars, token = defaultdict(list), None
    while True:
        p = {"symbols": ",".join(symbols), "timeframe": "1Min", "start": f"{day}T13:00:00Z",
             "end": f"{day}T21:30:00Z", "limit": 10000}
        if token:
            p["page_token"] = token
        r = get_with_retry("https://data.alpaca.markets/v1beta1/options/bars", params=p,
                           headers=headers, timeout=60)
        j = r.json()
        for s, b in (j.get("bars") or {}).items():
            bars[s] += b
        token = j.get("next_page_token")
        if not token:
            return bars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["SPY", "QQQ", "IWM"])
    a = ap.parse_args()
    key, sec = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_API_SECRET")
    if not key or not sec:
        sys.exit("set ALPACA_API_KEY and ALPACA_API_SECRET")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}

    c = load_contracts(a.symbols).rename(columns={"min": "first_trade", "max": "last_trade"})
    OUT.mkdir(parents=True, exist_ok=True)
    c.to_csv(OUT / "contracts.csv", index=False)

    todo = defaultdict(list)  # day -> contracts still missing a file
    for r in c.itertuples():
        for d in pd.bdate_range(r.first_trade, min(r.last_trade, r.expiry)).date:
            if not (OUT / r.symbol / f"{d}.csv").exists():
                todo[d].append(r.symbol)

    empty = []
    for day in sorted(todo):
        syms = todo[day]
        got = {}
        for i in range(0, len(syms), 100):
            got.update(fetch_day(syms[i:i + 100], day, headers))
        for s in syms:
            b = got.get(s)
            if not b:
                empty.append((s, day))
                continue
            d = pd.DataFrame(b).rename(columns={"t": "timestamp", "o": "open", "h": "high", "l": "low",
                                                "c": "close", "v": "volume", "n": "trades", "vw": "vwap"})
            d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True).dt.tz_convert(TZ)
            (OUT / s).mkdir(exist_ok=True)
            d[["timestamp", "open", "high", "low", "close", "volume", "trades", "vwap"]].to_csv(
                OUT / s / f"{day}.csv", index=False)
        print(f"{day}: {len(syms) - sum(1 for e in empty if e[1] == day)}/{len(syms)} contracts")
    print(f"\n{len(c)} contracts; {len(empty)} contract-days with no bars")
    for s, d in empty:
        print(f"  {s} {d}")


if __name__ == "__main__":
    main()
