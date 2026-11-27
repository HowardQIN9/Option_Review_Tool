"""Trade filters, kept free of UI code so they can be unit-tested."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .i18n import DEFAULT_LANG, Lang, label, t

# Filter field name -> episodes column it applies to (multi-select fields only).
CATEGORICAL_COLUMNS: dict[str, str] = {
    "underlyings": "underlying",
    "option_types": "type",
    "dte_buckets": "dte_bucket",
    "times_of_day": "tod",
    "hold_buckets": "hold_bucket",
    "add_types": "add_type",
}

# Filter field name -> i18n key of its label.
FIELD_LABEL_KEYS: dict[str, str] = {
    "underlyings": "d_ticker",
    "option_types": "f_type",
    "dte_buckets": "f_dte",
    "times_of_day": "f_tod",
    "hold_buckets": "f_hold",
    "add_types": "f_add",
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

    def describe(self, lang: Lang = DEFAULT_LANG) -> list[str]:
        """Human-readable list of the active conditions (shown in the UI and in exports)."""
        out = []
        if self.start or self.end:
            start = self.start or t("d_earliest", lang)
            end = self.end or t("d_latest", lang)
            out.append(t("d_date", lang, start=start, end=end))
        for name, key in FIELD_LABEL_KEYS.items():
            selected = getattr(self, name)
            if selected:
                values = t("d_join", lang).join(label(v, lang) for v in selected)
                out.append(t("d_item", lang, name=t(key, lang), values=values))
        if self.outcome:
            out.append(t("d_item", lang, name=t("f_outcome", lang), values=t(self.outcome, lang)))
        if self.overnight is not None:
            value = t("yes" if self.overnight else "no", lang)
            out.append(t("d_item", lang, name=t("f_overnight", lang), values=value))
        return out or [t("d_none", lang)]
