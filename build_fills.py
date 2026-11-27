"""Join the Robinhood statement CSV (option rows) with API executions to get exact fill times.

Inputs : the statement CSV in the project root, data/rh_option_executions.csv (export_rh_option_orders.py)
Output : data/option_fills.csv  - one row per statement option trade, with exec_time (America/New_York),
         OCC symbol (matches data/option_minute/<occ>/), statement amount (incl. fees), order details.
Matching is per execution on (date, contract, open/close side, qty, price); the statement splits
multi-execution orders into one row per execution, the same way.
"""
from pathlib import Path

import pandas as pd

from fetch_option_bars import DESC, occ

ROOT = Path(__file__).parent
KEY = ["date", "underlying", "expiry", "type", "strike", "code", "qty", "price"]


def money(s):
    s = s.astype(str).str.replace(r"[$,]", "", regex=True)
    neg = s.str.startswith("(")
    v = s.str.strip("()").astype(float)
    return v.where(~neg, -v)


def main():
    c = pd.read_csv(next(ROOT.glob("*.csv")), on_bad_lines="skip", usecols=range(9)).dropna(subset=["Activity Date"])
    c = c[c["Trans Code"].isin(["BTO", "STC", "BTC", "STO"])].copy()
    p = c["Description"].str.strip().str.extract(DESC.pattern)
    c["underlying"], c["type"] = p[0], p[2]
    c["expiry"] = pd.to_datetime(p[1]).dt.strftime("%Y-%m-%d")
    c["strike"] = p[3].str.replace(",", "").astype(float)
    c["date"] = pd.to_datetime(c["Activity Date"]).dt.strftime("%Y-%m-%d")
    c["code"], c["qty"] = c["Trans Code"], c["Quantity"].astype(float)
    c["price"], c["amount"] = money(c["Price"]), money(c["Amount"])

    e = pd.read_csv(ROOT / "data" / "rh_option_executions.csv")
    e["exec_time"] = pd.to_datetime(e["exec_time"], utc=True, format="ISO8601").dt.tz_convert("America/New_York")
    e["date"] = e["exec_time"].dt.strftime("%Y-%m-%d")
    e["code"] = e["side"].map({"buy": "BT", "sell": "ST"}) + e["position_effect"].map({"open": "O", "close": "C"})
    e = e.rename(columns={"symbol": "underlying", "exec_qty": "qty", "exec_price": "price"})

    c["i"] = c.groupby(KEY).cumcount()
    e["i"] = e.groupby(KEY).cumcount()
    m = c.merge(e, on=KEY + ["i"], how="outer", indicator=True)
    unmatched = m[m["_merge"] != "both"]
    m = m[m["_merge"] == "both"].copy()
    m["occ"] = [occ(u, pd.Timestamp(x).date(), t, k) for u, x, t, k in zip(m.underlying, m.expiry, m.type, m.strike)]
    m["fees"] = (m["amount"].abs() - m["qty"] * m["price"] * 100).abs().round(2)
    cols = ["exec_time", "date", "underlying", "occ", "expiry", "type", "strike", "code", "qty", "price",
            "amount", "fees", "order_id", "order_type", "limit_price", "order_created", "order_state"]
    m = m.sort_values("exec_time")[cols]
    m.to_csv(ROOT / "data" / "option_fills.csv", index=False)
    print(f"{len(m)} fills matched -> data/option_fills.csv; {len(unmatched)} unmatched")
    if len(unmatched):
        print(unmatched[KEY + ["_merge"]].to_string())


if __name__ == "__main__":
    main()
