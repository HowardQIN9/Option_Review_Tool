"""Small synthetic trades so tests never need real trading data."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest


@pytest.fixture
def trades() -> pd.DataFrame:
    entry = pd.to_datetime(
        ["2026-03-02 10:00", "2026-03-02 11:00", "2026-03-03 09:45", "2026-03-04 15:30"]
    ).tz_localize("America/New_York")
    return pd.DataFrame(
        {
            "trade_id": [1, 2, 3, 4],
            "day": [date(2026, 3, 2), date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4)],
            "entry_time": entry,
            "exit_time": entry + pd.Timedelta(minutes=20),
            "underlying": ["SPY", "QQQ", "QQQ", "TSLA"],
            "type": ["Call", "Put", "Call", "Call"],
            "strike": [600.0, 500.0, 510.0, 300.0],
            "expiry": [date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 3), date(2026, 3, 20)],
            "dte_bucket": ["0DTE", "1DTE", "0DTE", "6+DTE"],
            "tod": ["10:00-11:00", "11:00-14:00", "09:30-10:00", "15:00-16:00"],
            "hold_bucket": ["15-30m"] * 4,
            "add_type": ["单次建仓", "单次建仓", "加仓-价格更低(摊平)", "单次建仓"],
            "overnight": [False, False, False, True],
            "pnl": [100.0, -50.0, -30.0, 40.0],
            "ret": [0.5, -0.25, -0.3, 0.1],
            "win": [True, False, False, True],
            "contracts": [2.0, 1.0, 3.0, 1.0],
            "cost": [200.0, 200.0, 100.0, 400.0],
            "rows": ["1,2", "3,4", "5,6", "7,8"],
        }
    )


@pytest.fixture
def fills() -> pd.DataFrame:
    t = pd.Timestamp("2026-03-02 10:00", tz="America/New_York")
    return pd.DataFrame(
        {
            "row": list(range(1, 9)),
            "exec_time": [t + pd.Timedelta(minutes=i) for i in range(8)],
            "code": ["BTO", "STC"] * 4,
            "qty": [1.0] * 8,
            "price": [1.0, 1.5] * 4,
            "amount": [-100.0, 150.0] * 4,
            "order_type": ["limit"] * 8,
            "order_id": [f"secret-{i}" for i in range(8)],
        }
    )
