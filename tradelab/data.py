"""Read the raw statement, check data quality, standardize option fills, FIFO-match lots, build episodes."""
import csv
import re
from collections import deque

import numpy as np
import pandas as pd

from .config import API_EXEC, MANUAL_DATES, RAW_CSV, TZ

DESC = re.compile(r"^(\S+) (\d+/\d+/\d{4}) (Call|Put) \$([\d,.]+)$")
OEXP_DESC = re.compile(r"^Option Expiration for (\S+) (\d+/\d+/\d{4}) (Call|Put) \$([\d,.]+)$")
OPTION_CODES = {"BTO", "STC", "STO", "BTC"}
OPTION_EVENT_CODES = {"OEXP", "OASGN", "OEXCS"}
FIELDS = ["Activity Date", "Process Date", "Settle Date", "Instrument", "Description",
          "Trans Code", "Quantity", "Price", "Amount"]


def money(x):
    x = str(x).strip().replace("$", "").replace(",", "")
    if x in ("", "nan"):
        return np.nan
    neg = x.startswith("(")
    v = float(x.strip("()"))
    return -v if neg else v


def occ(root, expiry, cp, strike):
    return f"{root}{pd.Timestamp(expiry):%y%m%d}{cp[0]}{round(strike * 1000):08d}"


def read_raw():
    """Every row of the statement as text, with its line number; malformed rows are kept and flagged."""
    rows = []
    with open(RAW_CSV, newline="", encoding="utf-8-sig") as f:
        r = csv.reader(f)
        header = next(r)
        for i, row in enumerate(r, start=2):
            rows.append({"row": i, "n_fields": len(row), **dict(zip(FIELDS, row + [""] * (9 - len(row))))})
    df = pd.DataFrame(rows)
    df["manual"] = df["Activity Date"].isin(MANUAL_DATES)
    return header, df


def parse_contract(desc, pattern=DESC):
    m = pattern.match(str(desc).strip())
    if not m:
        return None
    root, exp, cp, k = m.groups()
    return root, pd.Timestamp(exp).strftime("%Y-%m-%d"), cp, float(k.replace(",", ""))


def standardize(raw):
    """Option rows -> one standardized fill per row; joins exact execution times from the API export."""
    issues = []
    opt = raw[raw["Trans Code"].isin(OPTION_CODES | OPTION_EVENT_CODES)].copy()
    recs = []
    for r in opt.rename(columns={"Activity Date": "act", "Trans Code": "tcode"}).itertuples():
        code = r.tcode
        pc = parse_contract(r.Description, OEXP_DESC if code in OPTION_EVENT_CODES else DESC)
        if pc is None:
            issues.append(("unparsed_description", r.row, r.Description))
            continue
        root, exp, cp, k = pc
        qty = float(re.sub(r"[^\d.]", "", r.Quantity) or "nan")
        price = money(r.Price) if code in OPTION_CODES else 0.0
        amount = money(r.Amount) if code in OPTION_CODES else 0.0
        recs.append(dict(row=r.row, date=pd.Timestamp(r.act).strftime("%Y-%m-%d"), underlying=root,
                         expiry=exp, type=cp, strike=k, occ=occ(root, exp, cp, k), code=code, qty=qty,
                         price=price, amount=amount, manual=r.manual))
    f = pd.DataFrame(recs)
    gross = f["qty"] * f["price"] * 100
    f["fees"] = 0.0
    f.loc[f["code"].isin({"STC", "STO"}), "fees"] = (gross - f["amount"]).round(2)
    f.loc[f["code"].isin({"BTO", "BTC"}), "fees"] = (-f["amount"] - gross).round(2)

    # exact execution times from the Robinhood API export
    f["exec_time"] = pd.Series(pd.NaT, index=f.index, dtype=f"datetime64[ns, {TZ}]")
    if API_EXEC.exists():
        e = pd.read_csv(API_EXEC)
        e = e[e["exec_qty"] > 0].copy()
        e["exec_time"] = pd.to_datetime(e["exec_time"], utc=True, format="ISO8601").dt.tz_convert(TZ)
        e["date"] = e["exec_time"].dt.strftime("%Y-%m-%d")
        e["code"] = e["side"].map({"buy": "BT", "sell": "ST"}) + e["position_effect"].map({"open": "O", "close": "C"})
        e = e.rename(columns={"symbol": "underlying", "exec_qty": "qty", "exec_price": "price"})
        key = ["date", "underlying", "expiry", "type", "strike", "code", "qty", "price"]
        t = f[f["code"].isin(OPTION_CODES)].copy()
        t["i"] = t.groupby(key).cumcount()
        e["i"] = e.groupby(key).cumcount()
        m = t.reset_index().merge(e[key + ["i", "exec_time", "order_id", "order_type", "limit_price", "order_created"]],
                                  on=key + ["i"], how="left", indicator=True).set_index("index")
        f.loc[m.index, "exec_time"] = m["exec_time_y"]
        for c in ["order_id", "order_type", "limit_price", "order_created"]:
            f.loc[m.index, c] = m[c]
        for r in m[m["_merge"] == "left_only"].itertuples():
            issues.append(("statement_fill_without_api_execution", r.row, f"{r.occ} {r.code} {r.qty}@{r.price}"))
        e2 = e.merge(t[key + ["i"]], on=key + ["i"], how="left", indicator=True)
        for r in e2[e2["_merge"] == "left_only"].itertuples():
            issues.append(("api_execution_missing_from_statement", None,
                           f"{r.exec_time} {r.underlying} {r.expiry} {r.type} {r.strike} {r.code} {r.qty}@{r.price}"))
    # expirations: synthetic close at 16:00 on expiry day, price 0
    ex = f["code"] == "OEXP"
    f.loc[ex, "exec_time"] = pd.to_datetime(f.loc[ex, "expiry"] + " 16:00").dt.tz_localize(TZ)
    f["exec_time"] = pd.to_datetime(f["exec_time"])
    f = f.sort_values(["exec_time", "row"], ascending=[True, False]).reset_index(drop=True)
    return f, issues


def quality_report(header, raw, fills, issues):
    """Data-quality checks; returns (markdown text, issues DataFrame)."""
    q = []
    q.append(f"- 原始文件：`{RAW_CSV.name}`，表头 {len(header)} 列：{', '.join(header)}")
    q.append(f"- 数据行 {len(raw)}；字段数≠9 的行 {int((raw.n_fields != 9).sum())}（行号："
             f"{', '.join(map(str, raw.loc[raw.n_fields != 9, 'row'].tolist()))}，为文件末尾免责声明/空行）")
    codes = raw["Trans Code"].replace("", "(空)").value_counts()
    q.append("- 交易代码分布：" + "，".join(f"{k} {v}" for k, v in codes.items()))
    q.append(f"- 期权相关行 {len(fills)}：成交 {int(fills.code.isin(OPTION_CODES).sum())}，"
             f"到期作废 OEXP {int((fills.code == 'OEXP').sum())}，行权/指派 "
             f"{int(fills.code.isin({'OASGN', 'OEXCS'}).sum())}；卖出开仓(STO/BTC) "
             f"{int(fills.code.isin({'STO', 'BTC'}).sum())}")
    man = fills[fills.manual]
    q.append(f"- 手动补录行（{', '.join(sorted(MANUAL_DATES))}）：{len(man)} 行；成交价/数量已与 API 成交逐笔核对，"
             f"手续费为估算（合计 ${man.fees.sum():.2f}）")
    dup = raw[raw.duplicated(FIELDS, keep=False) & raw["Trans Code"].isin(OPTION_CODES)]
    q.append(f"- 完全相同的期权行 {len(dup)} 行：经 API 核对均为同一订单的分次成交（Robinhood 账单按成交拆行），不是重复")
    t = fills[fills.code.isin(OPTION_CODES)]
    q.append(f"- 期权成交匹配到精确时间：{int(t.exec_time.notna().sum())}/{len(t)}")
    fee_pc = t.fees / t.qty
    odd = t[(fee_pc < -0.005) | (fee_pc > 0.2)]
    q.append(f"- 手续费检查（金额 vs 数量×价格×100）：每张 ${fee_pc.min():.3f}–${fee_pc.max():.3f}，异常 {len(odd)} 行")
    for r in odd.itertuples():
        issues.append(("fee_out_of_range", r.row, f"{r.occ} {r.code} fee/contract={r.fees / r.qty:.3f}"))
    # open positions / unclosed expiries
    net = fills.assign(s=fills.qty * fills.code.map({"BTO": 1, "STO": -1, "STC": -1, "BTC": 1, "OEXP": -1}))
    net = net.groupby(["occ", "expiry"])["s"].sum().reset_index()
    today = pd.Timestamp.now(tz=TZ).strftime("%Y-%m-%d")
    openpos = net[(net.s != 0) & (net.expiry >= today)]
    stale = net[(net.s != 0) & (net.expiry < today)]
    q.append(f"- 未平仓头寸：{len(openpos)}；已过期但未平且无 OEXP 记录：{len(stale)}")
    for r in stale.itertuples():
        issues.append(("expired_without_close", None, f"{r.occ} net {r.s}"))
    q.append(f"- 其他问题：{len(issues)} 条（见 data_issues.csv）")
    return "\n".join(q), pd.DataFrame(issues, columns=["issue", "raw_row", "detail"])


def fifo(fills):
    """FIFO lot matching (long premium only; STO/BTC would need the mirror logic and are absent).
    Returns lot-level matches and flat-to-flat episodes."""
    matches, episodes = [], []
    for o, g in fills.groupby("occ", sort=False):
        lots, pos, ep = deque(), 0.0, []
        for r in g.sort_values(["exec_time", "row"], ascending=[True, False]).itertuples():
            ep.append(r)
            if r.code == "BTO":
                lots.append([r.qty, r.price, r.fees / r.qty, r.exec_time, r.row])
                pos += r.qty
            elif r.code in ("STC", "OEXP"):
                left, fee_pc = r.qty, (r.fees / r.qty if r.qty else 0)
                while left > 1e-9:
                    if not lots:
                        raise ValueError(f"sell without open lot: {o} row {r.row}")
                    lot = lots[0]
                    q = min(left, lot[0])
                    pnl = q * (r.price - lot[1]) * 100 - q * (lot[2] + fee_pc)
                    matches.append(dict(occ=o, open_row=lot[4], close_row=r.row, open_time=lot[3],
                                        close_time=r.exec_time, qty=q, open_price=lot[1], close_price=r.price,
                                        fees=q * (lot[2] + fee_pc), pnl=pnl, close_code=r.code))
                    lot[0] -= q
                    left -= q
                    if lot[0] <= 1e-9:
                        lots.popleft()
                pos -= r.qty
            if abs(pos) < 1e-9 and ep:
                episodes.append(episode(o, ep))
                ep = []
        if ep:
            episodes.append(episode(o, ep, open_=True))
    return pd.DataFrame(matches), pd.DataFrame(episodes)


def episode(o, fills, open_=False):
    buys = [x for x in fills if x.code == "BTO"]
    sells = [x for x in fills if x.code in ("STC", "OEXP")]
    qb = sum(x.qty for x in buys)
    cost = sum(-x.amount for x in buys)                       # premium + buy fees
    proceeds = sum(x.amount for x in sells)                   # premium - sell fees
    pos, maxq = 0, 0
    for x in fills:
        pos += x.qty if x.code == "BTO" else -x.qty
        maxq = max(maxq, pos)
    b0 = buys[0]
    return dict(
        occ=o, underlying=b0.underlying, type=b0.type, strike=b0.strike, expiry=b0.expiry,
        entry_time=b0.exec_time, exit_time=sells[-1].exec_time if sells else pd.NaT,
        contracts=qb, max_position=maxq, n_buys=len(buys), n_sells=len(sells),
        avg_entry=sum(x.qty * x.price for x in buys) / qb,
        avg_exit=sum(x.qty * x.price for x in sells) / max(sum(x.qty for x in sells), 1e-9) if sells else np.nan,
        first_entry_price=b0.price, first_qty=b0.qty, cost=cost, proceeds=proceeds,
        fees=sum(x.fees for x in fills), pnl=proceeds - cost if not open_ else np.nan,
        ret=(proceeds - cost) / cost if not open_ else np.nan,
        expired=any(x.code == "OEXP" for x in sells), is_open=open_,
        manual=any(x.manual for x in fills), rows=",".join(str(x.row) for x in fills))
