"""Load the analysis outputs (episodes, fills) and minute bars from disk."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from . import config


class MissingDataError(FileNotFoundError):
    """Raised when the analysis outputs the dashboard needs have not been generated yet."""


def _to_ny(series: pd.Series) -> pd.Series:
    """Parse timestamps with mixed UTC offsets (EST/EDT) into America/New_York."""
    return pd.to_datetime(series, utc=True, format="ISO8601").dt.tz_convert(config.TZ)


def load_episodes(path: Path = config.EPISODES_CSV) -> pd.DataFrame:
    """Load one row per round-trip trade, as written by run_analysis.py."""
    if not path.exists():
        raise MissingDataError(f"{path} not found. Run `python run_analysis.py` first.")
    df = pd.read_csv(path)
    df["entry_time"] = _to_ny(df["entry_time"])
    df["exit_time"] = _to_ny(df["exit_time"])
    df["day"] = pd.to_datetime(df["day"]).dt.date
    df["expiry"] = pd.to_datetime(df["expiry"]).dt.date
    df["trade_id"] = range(1, len(df) + 1)
    return df.sort_values("entry_time").reset_index(drop=True)


def load_fills(path: Path = config.FILLS_CSV) -> pd.DataFrame:
    """Load standardized option fills; `row` links them to episodes.rows."""
    if not path.exists():
        raise MissingDataError(f"{path} not found. Run `python run_analysis.py` first.")
    df = pd.read_csv(path)
    df["exec_time"] = _to_ny(df["exec_time"])
    return df


def fills_for(episode: pd.Series, fills: pd.DataFrame) -> pd.DataFrame:
    """Return the fills belonging to one episode, in execution order."""
    rows = {int(r) for r in str(episode["rows"]).split(",") if r.strip()}
    return fills[fills["row"].isin(rows)].sort_values("exec_time")


def _read_bars(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    bars = pd.read_csv(path)
    bars["timestamp"] = _to_ny(bars["timestamp"])
    return bars.set_index("timestamp").sort_index()


def minute_bars(directory: Path, days: list[date]) -> pd.DataFrame:
    """Concatenate the daily 1-minute bar files of one symbol/contract; missing days are skipped."""
    parts = [b for d in days if (b := _read_bars(directory / f"{d}.csv")) is not None]
    if not parts:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return pd.concat(parts)


def trade_days(episode: pd.Series) -> list[date]:
    """Business days spanned by an episode, from entry to exit."""
    return list(pd.bdate_range(episode["entry_time"].date(), episode["exit_time"].date()).date)


def option_bars(episode: pd.Series) -> pd.DataFrame:
    return minute_bars(config.OPTION_MINUTE_DIR / episode["occ"], trade_days(episode))


def underlying_bars(episode: pd.Series) -> pd.DataFrame:
    return minute_bars(config.STOCK_MINUTE_DIR / episode["underlying"], trade_days(episode))
