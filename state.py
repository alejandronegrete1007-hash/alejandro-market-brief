"""Watchlists and navigation state.

- US leaders: the five S&P 500 stocks with the biggest 2026 gains. Always shown.
- Mexico leaders: the live YTD top 5 of the Mexican ADRs. Always shown.
- My stocks: any tickers you add, saved in this browser (localStorage), so they
  survive closing the page. No account or database needed.
"""
from __future__ import annotations

import json
import re

import streamlit as st

import mexico

# S&P 500 members with the biggest gains of 2026 as of Oct 27, 2026 (Chartrow / topstocksytd.com).
US_LEADERS = ["MRNA", "SNDK", "DELL", "MU", "MPC"]
US_LEADERS_ASOF = "Oct 27, 2026"
MY_MAX = 25
TICKER = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")

_STORE_JS = """
let lastSent;
export default function(component) {
  const { data, setStateValue } = component;
  const KEY = 'amb_my_stocks_v1';
  let stored = '[]';
  try {
    if (data && typeof data.write === 'string') { localStorage.setItem(KEY, data.write); lastSent = data.write; }
    stored = localStorage.getItem(KEY) || '[]';
  } catch (e) { stored = '[]'; }
  if (stored !== lastSent) { lastSent = stored; setStateValue('saved', stored); }
}
"""
_store = st.components.v2.component("amb_store", js=_STORE_JS)


def _clean(raw) -> list[str]:
    try:
        items = json.loads(raw) if isinstance(raw, str) else list(raw or [])
    except Exception:
        items = []
    out = []
    for t in items:
        t = str(t).upper().strip()
        if TICKER.match(t) and t not in out:
            out.append(t)
    return out[:MY_MAX]


def init():
    """Run once per page load, before any page renders."""
    ss = st.session_state
    ss.setdefault("my", [])
    ss.setdefault("my_loaded", False)
    if "focus" not in ss:
        ss.focus = (st.query_params.get("t") or "").upper() or None
    data = {"write": json.dumps(ss.my)} if ss.my_loaded else {}
    r = _store(data=data, key="amb_store", default={"saved": None}, on_saved_change=lambda: None)
    saved = getattr(r, "saved", None)
    if not ss.my_loaded and saved is not None:
        ss.my = _clean(saved)
        ss.my_loaded = True


def mx_leaders() -> tuple[list[str], bool]:
    return mexico.top5()


def my_list() -> list[str]:
    return st.session_state.get("my", [])


def all_symbols() -> list[str]:
    return list(dict.fromkeys(US_LEADERS + mx_leaders()[0] + my_list()))


def add(sym: str) -> str | None:
    sym = sym.upper().strip()
    if not TICKER.match(sym):
        return f"'{sym}' doesn't look like a US ticker."
    lst = st.session_state.my
    if sym in lst:
        return f"{sym} is already in My stocks."
    if len(lst) >= MY_MAX:
        return f"My stocks holds up to {MY_MAX}. Remove one first."
    st.session_state.my = lst + [sym]
    st.session_state.my_loaded = True
    return None


def remove(sym: str):
    st.session_state.my = [s for s in st.session_state.my if s != sym]
    st.session_state.my_loaded = True


def focus(sym: str):
    st.session_state.focus = sym.upper()
    st.query_params["t"] = sym.upper()


def market_of(sym: str) -> str:
    return "MX" if sym in mexico.UNIVERSE or sym == "EWW" else "US"
