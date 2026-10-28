"""Watchlists and navigation state.

- US leaders: the five S&P 500 stocks with the biggest 2026 gains. Always shown.
- Mexico leaders: the live YTD top 5 of the Mexican ADRs. Always shown.
- My stocks: any tickers you add, saved in this browser (localStorage), so they
  survive closing the page. No account or database needed.
- Research calls: the Buy / Hold / Sell calls you save from a research note, with the
  price and the S&P 500 level on that day, so the page can track how each call did.
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
  const KEYS = {my: 'amb_my_stocks_v1', calls: 'amb_calls_v1'};
  const out = {};
  for (const [name, key] of Object.entries(KEYS)) {
    try {
      if (data && typeof data[name] === 'string') localStorage.setItem(key, data[name]);
      out[name] = localStorage.getItem(key) || '[]';
    } catch (e) { out[name] = '[]'; }
  }
  const msg = JSON.stringify(out);
  if (msg !== lastSent) { lastSent = msg; setStateValue('saved', msg); }
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


CALL_FIELDS = ("sym", "date", "price", "spy", "lean", "value", "conviction")


def _clean_calls(raw) -> list[dict]:
    try:
        items = json.loads(raw) if isinstance(raw, str) else list(raw or [])
    except Exception:
        items = []
    out = []
    for c in items:
        if isinstance(c, dict) and TICKER.match(str(c.get("sym", ""))) and c.get("price"):
            out.append({k: c.get(k) for k in CALL_FIELDS})
    return out[-50:]


def init():
    """Run once per page load, before any page renders."""
    ss = st.session_state
    ss.setdefault("my", [])
    ss.setdefault("calls", [])
    ss.setdefault("my_loaded", False)
    if "focus" not in ss:
        ss.focus = (st.query_params.get("t") or "").upper() or None
    data = {"my": json.dumps(ss.my), "calls": json.dumps(ss.calls)} if ss.my_loaded else {}
    r = _store(data=data, key="amb_store", default={"saved": None}, on_saved_change=lambda: None)
    saved = getattr(r, "saved", None)
    if not ss.my_loaded and saved is not None:
        try:
            d = json.loads(saved)
        except Exception:
            d = {}
        ss.my = _clean(d.get("my", "[]"))
        ss.calls = _clean_calls(d.get("calls", "[]"))
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


def save_call(call: dict):
    """Record a research call (ticker, date, price, lean, value) so its result can be tracked."""
    st.session_state.calls = [c for c in st.session_state.calls
                              if not (c["sym"] == call["sym"] and c["date"] == call["date"])] + [call]
    st.session_state.my_loaded = True


def delete_call(sym: str, date: str):
    st.session_state.calls = [c for c in st.session_state.calls if not (c["sym"] == sym and c["date"] == date)]
    st.session_state.my_loaded = True


def remove(sym: str):
    st.session_state.my = [s for s in st.session_state.my if s != sym]
    st.session_state.my_loaded = True


def focus(sym: str):
    st.session_state.focus = sym.upper()
    st.query_params["t"] = sym.upper()


def market_of(sym: str) -> str:
    return "MX" if sym in mexico.UNIVERSE or sym == "EWW" else "US"
