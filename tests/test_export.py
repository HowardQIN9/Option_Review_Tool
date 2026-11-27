import io
import zipfile
from datetime import datetime

import pandas as pd

from dashboard.export import FILL_COLUMNS, TRADE_COLUMNS, build_pack, export_columns
from dashboard.filters import TradeFilter

SENSITIVE_TRADE = {name for name, col in TRADE_COLUMNS.items() if col.sensitive}
SENSITIVE_FILL = {name for name, col in FILL_COLUMNS.items() if col.sensitive}


def _complete(trades):
    """Add any export column the fixture lacks, so build_pack can select it."""
    for col in TRADE_COLUMNS:
        if col not in trades:
            trades[col] = 0
    return trades


def _pack(trades, fills, include_amounts, lang="zh"):
    return build_pack(
        _complete(trades), fills, TradeFilter(), "测试问题", include_amounts, lang, now=datetime(2026, 1, 1, 12, 0, 0)
    )


def test_hidden_amounts_drop_sensitive_columns(trades, fills):
    pack = _pack(trades, fills, include_amounts=False)
    trade_cols = set(pd.read_csv(io.StringIO(pack.files["trades.csv"])).columns)
    fill_cols = set(pd.read_csv(io.StringIO(pack.files["fills.csv"])).columns)
    assert trade_cols.isdisjoint(SENSITIVE_TRADE)
    assert fill_cols.isdisjoint(SENSITIVE_FILL)
    assert "$" not in pack.files["summary.md"]
    assert "金额和仓位张数已被移除" in pack.files["PROMPT.md"]


def test_included_amounts_keep_pnl(trades, fills):
    pack = _pack(trades, fills, include_amounts=True)
    assert "pnl" in pd.read_csv(io.StringIO(pack.files["trades.csv"])).columns
    assert "$" in pack.files["summary.md"]


def test_order_ids_never_exported(trades, fills):
    for include in (True, False):
        assert "secret-" not in _pack(trades, fills, include).files["fills.csv"]


def test_fills_are_linked_to_trades(trades, fills):
    pack = _pack(trades, fills, include_amounts=False)
    exported = pd.read_csv(io.StringIO(pack.files["fills.csv"]))
    assert sorted(exported["trade_id"].unique()) == [1, 2, 3, 4]
    assert len(exported) == 8


def test_prompt_and_zip(trades, fills):
    pack = _pack(trades, fills, include_amounts=False)
    assert "测试问题" in pack.files["PROMPT.md"]
    assert pack.folder.name == "pack_20260101_120000"
    names = zipfile.ZipFile(io.BytesIO(pack.zip_bytes())).namelist()
    assert set(names) == set(pack.files)


def test_export_columns_respects_flag():
    assert set(export_columns(TRADE_COLUMNS, True)) == set(TRADE_COLUMNS)
    assert SENSITIVE_TRADE.isdisjoint(export_columns(TRADE_COLUMNS, False))


def test_english_pack_is_translated(trades, fills):
    pack = _pack(trades, fills, include_amounts=False, lang="en")
    assert "dollar amounts and position sizes have been removed" in pack.files["PROMPT.md"]
    assert "Headline statistics" in pack.files["summary.md"]
    assert "Data dictionary" in pack.files["DATA_DICTIONARY.md"]
    exported = pd.read_csv(io.StringIO(pack.files["trades.csv"]))
    assert "Added lower (averaging down)" in set(exported["add_type"])
    assert "加仓-价格更低(摊平)" not in set(exported["add_type"])


def test_every_column_has_both_languages():
    for spec in (TRADE_COLUMNS, FILL_COLUMNS):
        for col in spec.values():
            assert col.zh and col.en


def test_notes_included_only_when_requested(trades, fills, tmp_path):
    from datetime import date

    from dashboard.notes import NoteStore

    trades = _complete(trades)
    trades["trade_key"] = [f"k{i}" for i in trades["trade_id"]]
    store = NoteStore(tmp_path / "notes.json")
    store.set_trade("k1", "planned entry on the open", ["planned"])
    store.set_day(date(2026, 3, 2), "CPI day", [])

    without = build_pack(trades, fills, TradeFilter(), "", False, "en")
    assert "note" not in pd.read_csv(io.StringIO(without.files["trades.csv"])).columns
    assert "daily_notes.md" not in without.files

    with_notes = build_pack(trades, fills, TradeFilter(), "", False, "en", notes=store)
    exported = pd.read_csv(io.StringIO(with_notes.files["trades.csv"]))
    assert exported.loc[exported["trade_id"] == 1, "note"].item() == "planned entry on the open"
    assert exported.loc[exported["trade_id"] == 1, "note_tags"].item() == "Planned"
    assert "CPI day" in with_notes.files["daily_notes.md"]
    assert "daily_notes.md" in with_notes.files["PROMPT.md"]
