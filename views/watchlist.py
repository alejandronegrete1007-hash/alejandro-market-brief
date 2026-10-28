"""Watchlist: two editable lists of up to 5 stocks, US and Mexico."""
from __future__ import annotations

import streamlit as st

import mexico
import quant as Q
import sources as src
import state
import theme as T
from views.common import name_of, open_analysis


def _card(sym: str, market: str, is_open: bool) -> str:
    q = src.try_quote(sym)
    h = src.try_history(sym)
    prof = src.profile(sym)
    close = h["close"] if h is not None else None
    ytd = Q.ytd_return(close) if close is not None else None
    if q and close is not None and ytd is not None:  # use the live price against the year-end base
        base = close[close.index < f"{close.index[-1].year}-01-01"]
        ytd = q["price"] / base.iloc[-1] - 1 if len(base) else ytd
    r1y = Q.period_return(close, 365) if close is not None else None
    vol = Q.annual_volatility(close) if close is not None else None
    sp = T.spark(close.iloc[-252:], h=58) if close is not None else '<div class="amb-note">Chart unavailable</div>'
    hi52 = close.iloc[-252:].max() if close is not None else None
    lo52 = close.iloc[-252:].min() if close is not None else None
    er = src.next_earnings(sym)
    er_txt = f"Earnings {er['date']}" if er else "No earnings date yet"
    price = T.money(q["price"]) if q else "—"
    return f"""
    <div class="amb-stock">
      <div class="hd">
        <div style="display:flex;gap:10px;align-items:center">{T.logo(prof['logo'], sym)}
          <div><div class="sym">{T.esc(sym)} {T.chip(market, market)}</div><div class="nm">{T.esc(name_of(sym))}</div></div></div>
        <div><div class="px">{price}</div><div style="text-align:right;margin-top:4px">{T.pill(q['pct']) if q else ''}</div></div>
      </div>
      <div class="spark" style="margin:14px 0 2px">{sp}</div>
      {T.range_bar(lo52, hi52, q['price'] if q else None, '52w', '')}
      <div class="stats">
        <div class="st"><div class="k">YTD</div><div class="v" style="color:var(--{T.tone(ytd) if ytd is not None else 'text'})">{T.pct(ytd)}</div></div>
        <div class="st"><div class="k">1 year</div><div class="v">{T.pct(r1y)}</div></div>
        <div class="st"><div class="k">Volatility</div><div class="v">{T.pct(vol, 0, signed=False)}</div></div>
      </div>
      <div class="foot" style="display:flex;justify-content:space-between;margin-top:12px;font-family:var(--mono);font-size:.7rem;color:var(--muted)">
        <span>{er_txt}</span><span>{T.freshness(q['time'], is_open) if q else ''}</span></div>
    </div>"""


def _list(market: str):
    is_open = src.us_market_status()["open"]
    if market == "US":
        syms = st.session_state.wl_us
        T.show(f'<div class="amb-note" style="margin:0 0 14px">Starts with the five S&amp;P 500 stocks that gained the most in 2026 '
               f'(as of {state.US_DEFAULT_ASOF}). Change them whenever you like.</div>')
    else:
        syms, follows = state.mx_list()
        msg = ("Following the live top 5 Mexican ADRs by YTD return." if follows
               else "Custom list. Reset to go back to the live YTD top 5.")
        T.show(f'<div class="amb-note" style="margin:0 0 14px">{msg}</div>')

    if not syms:
        T.show('<div class="amb-empty">The list is empty. Add a stock below.</div>')
    with st.spinner("Loading prices and charts (the free plan paces history requests)..."):
        cols = st.columns(3, gap="medium")
        for i, s in enumerate(syms):
            with cols[i % 3]:
                T.show(_card(s, market, is_open))
                b1, b2 = st.columns([1.4, 1])
                if b1.button("Analyze →", key=f"an_{market}_{s}", use_container_width=True, type="primary"):
                    open_analysis(s)
                if b2.button("Remove", key=f"rm_{market}_{s}", use_container_width=True):
                    state.remove(market, s)
                    st.rerun()
                st.write("")

    st.divider()
    a, b = st.columns([3, 1], gap="medium")
    with a:
        if market == "MX":
            options = [s for s in mexico.UNIVERSE if s not in syms]
            pick = st.selectbox("Add a Mexican ADR", ["—"] + [f"{s} · {mexico.UNIVERSE[s][0]}" for s in options],
                                key="add_mx_pick")
            if pick != "—" and st.button("Add", key="add_mx_btn"):
                err = state.add("MX", pick.split(" · ")[0])
                st.error(err) if err else st.rerun()
        q = st.text_input("Search any US-listed stock by name or ticker", key=f"q_{market}",
                          placeholder="e.g. Nvidia, COST, Walmex…")
        if q:
            try:
                res = src.search(q)
            except Exception as e:
                res = []
                st.error(str(e))
            if not res:
                st.caption("No US-listed matches.")
            for r in res[:6]:
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"**{r['symbol']}** · {r['name']}")
                if c2.button("Add", key=f"add_{market}_{r['symbol']}"):
                    err = state.add(market, r["symbol"])
                    st.error(err) if err else st.rerun()
    with b:
        st.write("")
        st.write("")
        if st.button("Reset to defaults", key=f"reset_{market}", use_container_width=True):
            state.reset(market)
            st.rerun()
        st.caption(f"{len(syms)}/{state.MAX} stocks. Your lists live in the page link: bookmark it to keep them.")


def render():
    T.show('<div class="amb-hero"><div><div class="amb-kicker">Watchlist</div><h1>Ten stocks, two markets</h1>'
           '<div class="sub">Five on Wall Street, five from Mexico. Click Analyze for the full breakdown and the DCF.</div></div></div>')
    # One list at a time, so the free history quota isn't spent on the hidden one.
    choice = st.segmented_control("Market", ["🇺🇸  United States", "🇲🇽  México"], default="🇺🇸  United States",
                                  key="wl_market", label_visibility="collapsed")
    _list("MX" if choice and "México" in choice else "US")
    T.footer("Prices: Finnhub · history: Twelve Data")
