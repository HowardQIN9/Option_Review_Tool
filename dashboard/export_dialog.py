"""UI module: export the current selection as an analysis pack for an LLM coding agent.

Opened as a dialog from the sidebar, so it works from any view and always uses the current filter.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from .export import PROMPT_TEMPLATES, build_pack, write_pack
from .filters import TradeFilter

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


@st.dialog("导出给 LLM 分析", width="large")
def export_dialog(trades: pd.DataFrame, fills: pd.DataFrame, flt: TradeFilter) -> None:
    st.markdown(
        f"把当前筛选出的 **{len(trades)} 笔交易**导出成一个分析包文件夹，"
        "再用 **Claude Code** 或 **Codex** 打开这个文件夹，对它说：**“读 PROMPT.md，按要求开始分析。”**"
    )
    st.caption("筛选条件：" + "；".join(flt.describe()))

    include_amounts = st.toggle(
        "包含美元金额和仓位张数",
        value=False,
        help="关闭时，盈亏金额、成本、手续费、张数都会被移除，只保留收益率、比例和每股价格。",
    )
    if include_amounts:
        st.warning("分析包会包含你的真实盈亏金额。用 LLM 分析时，这些数据会发送给 Anthropic 或 OpenAI。", icon="🔓")
    else:
        st.success("不包含金额：只发送收益率、比例、价格和行情数据。", icon="🔒")

    template = st.selectbox("Prompt 模板", list(PROMPT_TEMPLATES))
    prompt = st.text_area("你的问题（可修改）", value=PROMPT_TEMPLATES[template], height=120)

    pack = build_pack(trades, fills, flt, prompt, include_amounts)
    with st.expander("预览将导出的内容"):
        _preview(pack.files)

    left, right = st.columns(2)
    if left.button("生成分析包文件夹", type="primary", width="stretch"):
        st.session_state["last_pack"] = str(write_pack(pack))
    right.download_button(
        "下载为 ZIP",
        data=pack.zip_bytes(),
        file_name=f"{pack.folder.name}.zip",
        mime="application/zip",
        on_click="ignore",
        width="stretch",
    )

    if folder := st.session_state.get("last_pack"):
        st.success(f"已生成：`{folder}`")
        if os.name == "nt" and st.button("在资源管理器中打开"):
            os.startfile(folder)  # local and user-initiated
