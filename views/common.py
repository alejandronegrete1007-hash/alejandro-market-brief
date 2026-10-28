"""Bits shared by several pages: routing from clickable cards, names, and stock cards."""
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
    if sym in src.ETFS:
        return f"{src.ETFS[sym]} ETF"
    return src.profile(sym)["name"]


def route(target: str | None):
    """Act on a clicked card: 't:MU' opens MU's analysis, 'p:mexico' opens a page."""
    if not target:
        return
    if target.startswith("t:"):
        state.focus(target[2:])
        st.session_state["an_other"] = ""
        st.switch_page(PAGES["analysis"])
    elif target.startswith("p:") and target[2:] in PAGES:
        st.switch_page(PAGES[target[2:]])


def click(markup: str, key: str):
    route(T.clickable(markup, key))


def mini_rows(symbols: list[str]) -> str:
    rows = []
    for s in symbols:
        q = src.try_quote(s)
        rows.append(
            f'<div class="amb-row"{T.go_attr("t:" + s)} style="grid-template-columns:1fr auto">'
            f'<div style="min-width:0"><div class="s">{T.esc(s)}</div><div class="n">{T.esc(name_of(s))}</div></div>'
            f'<div style="text-align:right"><div class="p" style="display:block">{T.money(q["price"]) if q else "—"}</div>'
            f'<div style="margin-top:3px">{T.pill(q["pct"]) if q else ""}</div></div></div>')
    return f'<div class="amb-rows">{"".join(rows)}</div>'


def stock_card(sym: str, market: str, is_open: bool) -> str:
    """Watchlist card from Finnhub only (quote + key metrics): fast and inside the free limits."""
    q = src.try_quote(sym)
    prof = src.profile(sym)
    try:
        km = src.key_metrics(sym)
    except Exception:
        km = {}
    er = src.next_earnings(sym)
    ytd = km.get("ytd")
    price = q["price"] if q else None
    return f"""
    <div class="amb-stock"{T.go_attr("t:" + sym)}>
      <div class="hd">
        <div style="display:flex;gap:10px;align-items:center;min-width:0">{T.logo(prof['logo'], sym)}
          <div style="min-width:0"><div class="sym">{T.esc(sym)} {T.chip(market, market)}</div>
          <div class="nm" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{T.esc(name_of(sym))}</div></div></div>
        <div><div class="px">{T.money(price)}</div><div style="text-align:right;margin-top:4px">{T.pill(q['pct']) if q else ''}</div></div>
      </div>
      {T.range_bar(km.get('lo52'), km.get('hi52'), price, '52-week range')}
      <div class="stats">
        <div class="st"><div class="k">YTD</div><div class="v" style="color:var(--{T.tone(ytd)})">{T.pct(ytd, 1, frac=False)}</div></div>
        <div class="st"><div class="k">1 year</div><div class="v">{T.pct(km.get('r52'), 1, frac=False)}</div></div>
        <div class="st"><div class="k">P/E</div><div class="v">{T.mult(km.get('pe'))}</div></div>
      </div>
      <div class="foot"><span>{('Earnings ' + er['date']) if er else T.status(q['time'] if q else None, is_open)}</span>
        <span class="go-hint">Analyze →</span></div>
    </div>"""
