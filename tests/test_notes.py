from datetime import date

import pandas as pd

from dashboard.notes import NoteStore, trade_key


def test_round_trip(tmp_path):
    path = tmp_path / "notes.json"
    store = NoteStore(path)
    store.set_day(date(2026, 3, 2), "  choppy open  ", ["planned"])
    store.set_trade("QQQ|t1", "chased the breakout", ["chased", "fomo"])

    reloaded = NoteStore(path)
    assert reloaded.day(date(2026, 3, 2)).text == "choppy open"
    assert reloaded.trade("QQQ|t1").tags == ["chased", "fomo"]
    assert reloaded.days_with_notes() == {date(2026, 3, 2)}


def test_unknown_tags_dropped_and_order_canonical(tmp_path):
    store = NoteStore(tmp_path / "notes.json")
    store.set_trade("k", "x", ["fomo", "not-a-tag", "planned"])
    assert store.trade("k").tags == ["planned", "fomo"]


def test_clearing_a_note_removes_it(tmp_path):
    store = NoteStore(tmp_path / "notes.json")
    store.set_day(date(2026, 3, 2), "x", [])
    store.set_day(date(2026, 3, 2), "   ", [])
    assert store.day(date(2026, 3, 2)).is_empty
    assert store.days_with_notes() == set()


def test_missing_note_is_empty(tmp_path):
    assert NoteStore(tmp_path / "none.json").trade("nope").is_empty


def test_trade_key_is_stable():
    ts = pd.Timestamp("2026-03-02 09:53:16.764", tz="America/New_York")
    assert trade_key("XOM260320C00160000", ts) == trade_key("XOM260320C00160000", ts)
    assert trade_key("XOM260320C00160000", ts).startswith("XOM260320C00160000|2026-03-02T09:53:16")


def test_trade_notes_aligned_to_keys(tmp_path):
    store = NoteStore(tmp_path / "notes.json")
    store.set_trade("b", "note b", ["planned"])
    out = store.trade_notes(pd.Series(["a", "b"], index=[10, 11]))
    assert out.loc[10, "note"] == ""
    assert out.loc[11, "note"] == "note b"
    assert out.loc[11, "note_tags"] == ["planned"]
