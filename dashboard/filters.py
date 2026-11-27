"""Trade filters, kept free of UI code so they can be unit-tested."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date

import pandas as pd

# Filter field name -> episodes column it applies to (multi-select fields only).
CATEGORICAL_COLUMNS: dict[str, str] = {
    "underlyings": "underlying",
    "option_types": "type",
    "dte_buckets": "dte_bucket",
    "times_of_day": "tod",
    "hold_buckets": "hold_bucket",
    "add_types": "add_type",
}


@dataclass(frozen=True)
class TradeFilter:
    """Selection of trades. An empty selection means "no restriction" for that field."""

    start: date | None = None
    end: date | None = None
    underlyings: tuple[str, ...] = field(default_factory=tuple)
    option_types: tuple[str, ...] = field(default_factory=tuple)
    dte_buckets: tuple[str, ...] = field(default_factory=tuple)
    times_of_day: tuple[str, ...] = field(default_factory=tuple)
    hold_buckets: tuple[str, ...] = field(default_factory=tuple)
    add_types: tuple[str, ...] = field(default_factory=tuple)
    outcome: str | None = None  # "win" | "loss" | None
    overnight: bool | None = None

    def apply(self, trades: pd.DataFrame) -> pd.DataFrame:
        """Return the subset of `trades` (an episodes frame) that matches this filter."""
        mask = pd.Series(True, index=trades.index)
        if self.start is not None:
            mask &= trades["day"] >= self.start
        if self.end is not None:
            mask &= trades["day"] <= self.end
        for name, column in CATEGORICAL_COLUMNS.items():
            selected = getattr(self, name)
            if selected:
                mask &= trades[column].isin(selected)
        if self.outcome == "win":
            mask &= trades["win"]
        elif self.outcome == "loss":
            mask &= ~trades["win"]
        if self.overnight is not None:
            mask &= trades["overnight"] == self.overnight
        return trades[mask]

    def describe(self) -> list[str]:
        """Human-readable list of the active conditions (for export metadata)."""
        labels = {
            "underlyings": "标的",
            "option_types": "Call/Put",
            "dte_buckets": "DTE",
            "times_of_day": "入场时段",
            "hold_buckets": "持仓时长",
            "add_types": "建仓方式",
        }
        out = []
        if self.start or self.end:
            out.append(f"日期：{self.start or '最早'} 至 {self.end or '最新'}")
        for f in fields(self):
            if f.name in labels and getattr(self, f.name):
                out.append(f"{labels[f.name]}：{'、'.join(getattr(self, f.name))}")
        if self.outcome:
            out.append(f"结果：{'盈利' if self.outcome == 'win' else '亏损'}")
        if self.overnight is not None:
            out.append(f"隔夜：{'是' if self.overnight else '否'}")
        return out or ["无筛选（全部交易）"]
