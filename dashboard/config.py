"""Paths and display constants for the dashboard."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
DATA_DIR = ROOT / "data"
EXPORT_DIR = ROOT / "exports"

EPISODES_CSV = OUTPUT_DIR / "episodes.csv"
FILLS_CSV = OUTPUT_DIR / "fills_standardized.csv"
STOCK_MINUTE_DIR = DATA_DIR / "minute"
OPTION_MINUTE_DIR = DATA_DIR / "option_minute"

TZ = "America/New_York"

# Below this many trades, statistics are flagged as unreliable in the UI.
SMALL_SAMPLE = 30

# Display order for categorical columns produced by run_analysis.py.
CATEGORY_ORDER: dict[str, list[str]] = {
    "dte_bucket": ["0DTE", "1DTE", "2-5DTE", "6+DTE"],
    "hold_bucket": ["<1m", "1-5m", "5-15m", "15-30m", "30-60m", "60m+"],
    "tod": [
        "09:30前(盘前)",
        "09:30-10:00",
        "10:00-11:00",
        "11:00-14:00",
        "14:00-15:00",
        "15:00-16:00",
        "16:00后(收盘后)",
    ],
    "add_type": ["单次建仓", "加仓-价格更低(摊平)", "加仓-价格更高(加码)"],
    "type": ["Call", "Put"],
}
