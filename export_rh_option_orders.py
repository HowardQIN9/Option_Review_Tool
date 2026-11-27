"""Export my Robinhood option orders with exact execution timestamps (read-only).

Run it yourself in a terminal; it asks for username / password / 2FA (or app approval) interactively.
The login token is cached by robin_stocks in ~/.tokens so later runs don't need to log in again.
It only READS order history; it never places, changes or cancels anything.

Output:
  data/rh_option_orders_raw.json   full API response (for reference)
  data/rh_option_executions.csv    one row per execution, timestamps in America/New_York
"""
import json
from pathlib import Path

import pandas as pd
import robin_stocks.robinhood as rh

ROOT = Path(__file__).parent
OUT = ROOT / "data"
START = "2026-01-01"

_instr_cache = {}


def instrument(url):
    if url not in _instr_cache:
        _instr_cache[url] = rh.helper.request_get(url) or {}
    return _instr_cache[url]


def main():
    rh.login()  # prompts for credentials; reuses cached session if valid
    orders = rh.orders.get_all_option_orders(start_date=START)
    OUT.mkdir(exist_ok=True)
    (OUT / "rh_option_orders_raw.json").write_text(json.dumps(orders, indent=1, default=str))

    rows = []
    for o in orders:
        for leg in o.get("legs", []):
            ins = leg if leg.get("strike_price") else instrument(leg["option"])
            for ex in leg.get("executions", []):
                rows.append(dict(
                    order_id=o["id"],
                    symbol=o.get("chain_symbol"),
                    expiry=ins.get("expiration_date"),
                    type=(ins.get("option_type") or ins.get("type") or "").capitalize(),
                    strike=float(ins.get("strike_price") or "nan"),
                    side=leg.get("side"),
                    position_effect=leg.get("position_effect"),
                    exec_time=ex.get("timestamp"),
                    exec_price=float(ex.get("price")),
                    exec_qty=float(ex.get("quantity")),
                    order_created=o.get("created_at"),
                    order_type=o.get("type"),
                    limit_price=o.get("price"),
                    order_state=o.get("state"),
                ))
    df = pd.DataFrame(rows)
    if df.empty:
        print(f"{len(orders)} orders fetched, no executions found")
        return
    for c in ["exec_time", "order_created"]:
        df[c] = pd.to_datetime(df[c], utc=True, format="ISO8601").dt.tz_convert("America/New_York")
    df = df.sort_values("exec_time")
    df.to_csv(OUT / "rh_option_executions.csv", index=False)
    print(f"{len(orders)} orders, {len(df)} executions "
          f"({df.exec_time.min():%Y-%m-%d} .. {df.exec_time.max():%Y-%m-%d}) -> data/rh_option_executions.csv")


if __name__ == "__main__":
    main()
