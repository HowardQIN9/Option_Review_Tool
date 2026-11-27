"""Daily and per-trade journal notes, stored locally as JSON.

Notes are keyed by date ("2026-03-02") and by a stable trade key (contract + entry time), so they
survive re-running the analysis and can later be joined to other day-level views (e.g. a calendar).
The file lives in notes/ and is git-ignored: notes are personal.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from . import config

SCHEMA_VERSION = 1

# Tag id -> i18n key. Ids are stored; labels are translated for display.
TAGS: list[str] = [
    "planned",
    "impulsive",
    "chased",
    "fomo",
    "revenge",
    "followed_rules",
    "broke_rules",
    "cut_loss_in_time",
    "cut_loss_late",
    "took_profit_early",
]


@dataclass
class Note:
    text: str = ""
    tags: list[str] = field(default_factory=list)
    updated: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.text.strip() and not self.tags


def trade_key(occ: str, entry_time: pd.Timestamp) -> str:
    """Stable id for a trade: the contract plus its first fill time (independent of row order)."""
    return f"{occ}|{pd.Timestamp(entry_time).isoformat()}"


class NoteStore:
    """Read/write notes in a single JSON file."""

    def __init__(self, path: Path = config.NOTES_FILE) -> None:
        self.path = path
        self._days: dict[str, Note] = {}
        self._trades: dict[str, Note] = {}
        self._load()

    # ---------------------------------------------------------- persistence

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._days = {k: Note(**v) for k, v in raw.get("days", {}).items()}
        self._trades = {k: Note(**v) for k, v in raw.get("trades", {}).items()}

    def _save(self) -> None:
        payload = {
            "version": SCHEMA_VERSION,
            "days": {k: asdict(v) for k, v in sorted(self._days.items())},
            "trades": {k: asdict(v) for k, v in sorted(self._trades.items())},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file first so a crash never leaves a half-written notes file.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ---------------------------------------------------------- access

    def day(self, day: date) -> Note:
        return self._days.get(day.isoformat(), Note())

    def trade(self, key: str) -> Note:
        return self._trades.get(key, Note())

    def set_day(self, day: date, text: str, tags: list[str]) -> None:
        self._set(self._days, day.isoformat(), text, tags)

    def set_trade(self, key: str, text: str, tags: list[str]) -> None:
        self._set(self._trades, key, text, tags)

    def _set(self, bucket: dict[str, Note], key: str, text: str, tags: list[str]) -> None:
        note = Note(
            text=text.strip(), tags=[t for t in TAGS if t in tags], updated=datetime.now().isoformat(timespec="seconds")
        )
        if note.is_empty:
            bucket.pop(key, None)
        else:
            bucket[key] = note
        self._save()

    def days_with_notes(self) -> set[date]:
        return {date.fromisoformat(d) for d in self._days}

    def trade_notes(self, keys: pd.Series) -> pd.DataFrame:
        """Note text and tags aligned to a series of trade keys (empty strings / lists if none)."""
        notes = [self.trade(k) for k in keys]
        return pd.DataFrame(
            {"note": [n.text for n in notes], "note_tags": [n.tags for n in notes]},
            index=keys.index,
        )
