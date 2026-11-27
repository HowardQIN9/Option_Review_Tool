from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "output"
RAW_CSV = next(p for p in ROOT.glob("*.csv"))           # Robinhood statement export (never modified here)
API_EXEC = DATA / "rh_option_executions.csv"            # export_rh_option_orders.py
STOCK_MIN_EXT = DATA / "minute_ext"                     # fetch_minute_bars.py --extended (04:00-19:59 ET)
STOCK_MIN = DATA / "minute"                             # fetch_minute_bars.py
OPT_MIN = DATA / "option_minute"                        # fetch_option_bars.py
TZ = "America/New_York"

# Rows of the statement that were typed in by hand (not from Robinhood's export); fees are estimates.
MANUAL_DATES = {"11/23/2026"}

INDEX_ETFS = ["SPY", "QQQ", "IWM"]   # continuous minute history -> RVOL and control group
RISK_FREE = 0.04                      # flat annual rate for Black-Scholes (approximation)

# backtest execution assumptions (option trade bars carry no bid/ask)
STOP_SLIPPAGE_PCT = 0.03              # stop / market exits fill this much below the trigger level
MIN_SLIPPAGE = 0.01                   # at least one tick
TP_TRADE_THROUGH = 0.01               # a take-profit limit only counts as filled if the bar high exceeds it by a tick
