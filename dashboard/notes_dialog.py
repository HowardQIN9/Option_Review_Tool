"""UI module: write the day note and/or the trade note in a dialog."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from .i18n import Lang, t, tag_label
from .notes import TAGS, Note, NoteStore


def _editor(note: Note, key: str, hint: str, lang: Lang) -> tuple[str, list[str]]:
    tags = st.pills(
        t("n_tags", lang),
        TAGS,
        selection_mode="multi",
        default=note.tags,
        format_func=lambda tag: tag_label(tag, lang),
        key=f"{key}_tags",
    )
    text = st.text_area(t("n_note_label", lang), value=note.text, placeholder=hint, height=180, key=f"{key}_text")
    if note.updated:
        st.caption(t("n_updated", lang, when=note.updated.replace("T", " ")))
    return text, list(tags or [])


def _body(store: NoteStore, day: date | None, trade: pd.Series | None, lang: Lang) -> None:
    sections: list[str] = []
    if trade is not None:
        sections.append("trade")
    if day is not None:
        sections.append("day")
    if not sections:
        st.info(t("n_no_trade", lang))
        return

    titles = {
        "trade": t("n_tab_trade", lang, trade_id=trade["trade_id"]) if trade is not None else "",
        "day": t("n_tab_day", lang, day=day) if day is not None else "",
    }
    for tab, section in zip(st.tabs([titles[s] for s in sections]), sections, strict=True):
        with tab:
            if section == "trade":
                key = str(trade["trade_key"])
                text, tags = _editor(store.trade(key), f"note_trade_{key}", t("n_trade_hint", lang), lang)
                if st.button(t("n_save", lang), type="primary", key="save_trade"):
                    store.set_trade(key, text, tags)
                    st.rerun()
            else:
                text, tags = _editor(store.day(day), f"note_day_{day}", t("n_day_hint", lang), lang)
                if st.button(t("n_save", lang), type="primary", key="save_day"):
                    store.set_day(day, text, tags)
                    st.rerun()
    if trade is None:
        st.caption(t("n_no_trade", lang))


def open_notes_dialog(store: NoteStore, day: date | None, trade: pd.Series | None, lang: Lang) -> None:
    """Open the notes dialog. Shows a trade tab if `trade` is given and a day tab if `day` is given."""
    st.dialog(t("n_title", lang), width="large")(_body)(store, day, trade, lang)
