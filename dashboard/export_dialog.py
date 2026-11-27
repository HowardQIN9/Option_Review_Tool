"""UI module: export the current selection as an analysis pack for an LLM coding agent.

Opened as a dialog from the sidebar, so it works from any view and always uses the current filter.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from .export import PROMPT_TEMPLATES, build_pack, write_pack
from .filters import TradeFilter
from .i18n import Lang, t
from .notes import NoteStore

PREVIEW_CHARS = 3000


def _preview(files: dict[str, str]) -> None:
    names = list(files)
    for tab, name in zip(st.tabs(names), names, strict=True):
        with tab:
            text = files[name]
            if name.endswith(".csv"):
                st.code(text[:PREVIEW_CHARS] + ("\n…" if len(text) > PREVIEW_CHARS else ""), language=None)
            else:
                st.markdown(text)


def _body(trades: pd.DataFrame, fills: pd.DataFrame, flt: TradeFilter, notes: NoteStore, lang: Lang) -> None:
    st.markdown(t("x_intro", lang, n=len(trades)))
    st.caption(t("filters_caption", lang) + t("list_sep", lang).join(flt.describe(lang)))

    include_amounts = st.toggle(t("x_amounts", lang), value=False, help=t("x_amounts_help", lang))
    if include_amounts:
        st.warning(t("x_amounts_on", lang), icon="🔓")
    else:
        st.success(t("x_amounts_off", lang), icon="🔒")
    include_notes = st.toggle(t("x_notes", lang), value=False, help=t("x_notes_help", lang))

    templates = PROMPT_TEMPLATES[lang]
    template = st.selectbox(t("x_template", lang), list(templates))
    prompt = st.text_area(t("x_question", lang), value=templates[template], height=120)

    pack = build_pack(trades, fills, flt, prompt, include_amounts, lang, notes=notes if include_notes else None)
    with st.expander(t("x_preview", lang)):
        _preview(pack.files)

    left, right = st.columns(2)
    if left.button(t("x_write", lang), type="primary", width="stretch"):
        st.session_state["last_pack"] = str(write_pack(pack))
    right.download_button(
        t("x_zip", lang),
        data=pack.zip_bytes(),
        file_name=f"{pack.folder.name}.zip",
        mime="application/zip",
        on_click="ignore",
        width="stretch",
    )

    if folder := st.session_state.get("last_pack"):
        st.success(t("x_done", lang, folder=folder))
        if os.name == "nt" and st.button(t("x_open", lang)):
            os.startfile(folder)  # local and user-initiated


def open_export_dialog(
    trades: pd.DataFrame, fills: pd.DataFrame, flt: TradeFilter, notes: NoteStore, lang: Lang
) -> None:
    """Open the export dialog; its title follows the current language, so it is built per call."""
    st.dialog(t("x_title", lang), width="large")(_body)(trades, fills, flt, notes, lang)
