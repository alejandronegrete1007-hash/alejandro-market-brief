"""Bits shared by several pages."""
from __future__ import annotations

import streamlit as st

import mexico
import sources as src
import state
import theme as T
from views import PAGES


def name_of(sym: str) -> str:
    if sym in mexico.UNIVERSE:
        return mexico.UNIVERSE[sym][0]
    return src.profile(sym)["name"]


def open_analysis(sym: str):
    state.focus(sym)
    st.switch_page(PAGES["analysis"])


def _picked(key: str):
    v = st.session_state.get(key)
    if v:
        state.focus(v)
        st.session_state[key] = None
        st.session_state["_goto"] = "analysis"


def analyze_picker(options: list[str], key: str, label: str = "Open the analysis"):
    """Row of ticker pills; picking one jumps to the Analysis page (see app.py)."""
    if options:
        st.pills(label, options, selection_mode="single", key=key, on_change=_picked, args=(key,))


def mini_rows(symbols: list[str]) -> str:
    rows = []
    for s in symbols:
        q = src.try_quote(s)
        price = T.money(q["price"]) if q else "—"
        chg = T.pill(q["pct"]) if q else ""
        rows.append(f'<div class="amb-mini"><div><div class="s">{T.esc(s)}</div>'
                    f'<div class="n">{T.esc(name_of(s))}</div></div>'
                    f'<div><div class="p">{price}</div><div style="text-align:right;margin-top:3px">{chg}</div></div></div>')
    return f'<div class="amb-rail">{"".join(rows)}</div>'
