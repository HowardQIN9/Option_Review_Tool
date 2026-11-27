"""Summary statistics with confidence intervals for a set of trades."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Summary:
    n: int
    days: int
    win_rate: float
    win_rate_ci: tuple[float, float]
    total_pnl: float
    expectancy: float
    expectancy_ci: tuple[float, float]
    profit_factor: float
    payoff_ratio: float
    median_return: float


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (math.nan, math.nan)
    p = wins / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (centre - half, centre + half)


def day_block_bootstrap_ci(pnl: pd.Series, days: pd.Series, reps: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% CI of mean P&L per trade, resampling whole trading days.

    Trades on the same day are correlated (same market, same mood), so days rather
    than individual trades are the resampling unit.
    """
    by_day = pd.DataFrame({"pnl": pnl.to_numpy(), "day": days.to_numpy()}).groupby("day")["pnl"]
    sums, counts = by_day.sum().to_numpy(), by_day.count().to_numpy()
    if len(sums) < 2:
        return (math.nan, math.nan)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(sums), size=(reps, len(sums)))
    means = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return (float(lo), float(hi))


def summarize(trades: pd.DataFrame) -> Summary:
    """Compute the headline statistics shown in the dashboard and in exports."""
    n = len(trades)
    pnl = trades["pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    gross_loss = -losses.sum()
    return Summary(
        n=n,
        days=trades["day"].nunique(),
        win_rate=len(wins) / n if n else math.nan,
        win_rate_ci=wilson_ci(len(wins), n),
        total_pnl=float(pnl.sum()),
        expectancy=float(pnl.mean()) if n else math.nan,
        expectancy_ci=day_block_bootstrap_ci(pnl, trades["day"]) if n else (math.nan, math.nan),
        profit_factor=float(wins.sum() / gross_loss) if gross_loss > 0 else math.nan,
        payoff_ratio=(
            float(wins.mean() / -losses.mean()) if len(wins) and len(losses) and losses.mean() < 0 else math.nan
        ),
        median_return=float(trades["ret"].median()) if n else math.nan,
    )
