"""Two watchlists (US and Mexico), kept in the session and mirrored in the URL,
so a bookmarked link brings your lists back. No database needed."""
from __future__ import annotations

import streamlit as st

import mexico

MAX = 5
# S&P 500 members with the biggest gains of 2026 as of Oct 27, 2026 (Chartrow / topstocksytd.com).
US_DEFAULT = ["MRNA", "SNDK", "DELL", "MU", "MPC"]
US_DEFAULT_ASOF = "Oct 27, 2026"


def _parse(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    out = []
    for t in raw.upper().split(","):
        t = t.strip()
        if t and t not in out:
            out.append(t)
    return out[:MAX]


def init():
    ss = st.session_state
    if "wl_us" not in ss:
        ss.wl_us = _parse(st.query_params.get("us")) or list(US_DEFAULT)
    if "wl_mx" not in ss:
        ss.wl_mx = _parse(st.query_params.get("mx"))  # None = follow the live YTD leaders
    if "focus" not in ss:
        ss.focus = (st.query_params.get("t") or "").upper() or None
    sync()


def mx_list() -> tuple[list[str], bool]:
    """(tickers, follows_leaders)."""
    if st.session_state.wl_mx is not None:
        return st.session_state.wl_mx, False
    return mexico.top5()[0], True


def sync():
    qp = {"us": ",".join(st.session_state.wl_us)}
    if st.session_state.wl_mx is not None:
        qp["mx"] = ",".join(st.session_state.wl_mx)
    if st.session_state.get("focus"):
        qp["t"] = st.session_state.focus
    for k in ("us", "mx", "t"):
        if k in qp:
            if st.query_params.get(k) != qp[k]:
                st.query_params[k] = qp[k]
        elif k in st.query_params:
            del st.query_params[k]


def add(market: str, sym: str) -> str | None:
    sym = sym.upper().strip()
    if market == "US":
        lst = st.session_state.wl_us
    else:
        if st.session_state.wl_mx is None:
            st.session_state.wl_mx = list(mx_list()[0])
        lst = st.session_state.wl_mx
    if sym in lst:
        return f"{sym} is already on the list."
    if len(lst) >= MAX:
        return f"The list holds {MAX} stocks. Remove one first."
    lst.append(sym)
    sync()
    return None


def remove(market: str, sym: str):
    if market == "US":
        st.session_state.wl_us = [s for s in st.session_state.wl_us if s != sym]
    else:
        st.session_state.wl_mx = [s for s in mx_list()[0] if s != sym]
    sync()


def reset(market: str):
    if market == "US":
        st.session_state.wl_us = list(US_DEFAULT)
    else:
        st.session_state.wl_mx = None
    sync()


def focus(sym: str):
    st.session_state.focus = sym
    sync()


def market_of(sym: str) -> str:
    return "MX" if sym in mexico.UNIVERSE or sym in (st.session_state.wl_mx or []) or sym == "EWW" else "US"
