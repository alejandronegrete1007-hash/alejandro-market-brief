"""Watchlist: two fixed leader lists plus your own list, saved in this browser."""
from __future__ import annotations

import streamlit as st

import sources as src
import state
import theme as T
from views.common import click, stock_card


def _add_cb(sym: str):
    st.session_state["_wl_msg"] = state.add(sym) or f"Added {sym}."


def _remove_cb():
    sym = st.session_state.get("wl_remove")
    if sym:
        state.remove(sym)
        st.session_state["_wl_msg"] = f"Removed {sym}."
    st.session_state["wl_remove"] = None


def _cards(symbols: list[str], key: str, is_open: bool):
    with st.spinner("Loading prices..."):
        cards = [stock_card(s, state.market_of(s), is_open) for s in symbols]
    click(T.grid(cards, "g3 stack"), key)


def render():
    T.show('<div class="amb-hero"><div><h1>What I follow</h1>'
           '<div class="sub">Click any card for the full analysis: chart, risk, DCF and the analyst view.</div></div></div>')
    is_open = src.us_market_status()["open"]

    T.section("S&P 500 leaders of 2026", f"biggest YTD gains as of {state.US_LEADERS_ASOF}", "United States · fixed")
    _cards(state.US_LEADERS, "wl_us", is_open)

    mx, live = state.mx_leaders()
    T.section("Mexico top 5", "live YTD ranking of NYSE-listed Mexican stocks" if live else "fallback list",
              "México · updates itself")
    _cards(mx, "wl_mx", is_open)

    mine = state.my_list()
    T.section("My stocks", f"{len(mine)}/{state.MY_MAX} · saved in this browser", "Yours")
    if mine:
        _cards(mine, "wl_my", is_open)
    else:
        T.show('<div class="amb-empty">Nothing here yet. Search a company below and add it. Your list stays saved in this '
               'browser even after you close the page.</div>')

    st.write("")
    a, b = st.columns([3, 2], gap="large")
    with a:
        q = st.text_input("Add a stock", placeholder="Company or ticker, e.g. Nvidia, COST, Walmart…", key="wl_q")
        if q:
            try:
                res = src.search(q)
            except Exception as e:
                res = []
                st.error(str(e))
            if not res and len(q) <= 5:
                res = [{"symbol": q.upper().strip(), "name": "Add by ticker"}]
            if not res:
                st.caption("No US-listed matches.")
            for r in res[:6]:
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"**{r['symbol']}** · {r['name']}")
                c2.button("Add", key=f"add_{r['symbol']}", on_click=_add_cb, args=(r["symbol"],), width="stretch")
    with b:
        if mine:
            st.pills("Tap to remove", mine, selection_mode="single", key="wl_remove", on_change=_remove_cb)
    msg = st.session_state.pop("_wl_msg", None)
    if msg:
        st.toast(msg)
    T.footer("Quotes and metrics: Finnhub · YTD and 1-year returns as of the last close")
