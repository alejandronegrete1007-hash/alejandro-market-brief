"""Watchlist: two fixed leader lists plus your own list (saved in this browser), the track record
of your research calls, and a portfolio lab that builds the efficient frontier for any of them."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import portfolio as P
import quant as Q
import sources as src
import state
import theme as T
import valuation as V
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
    _calls()
    _portfolio_lab()
    T.footer("Quotes and metrics: Finnhub · YTD and 1-year returns as of the last close")


# --------------------------------------------------------------------------- research calls
def _del_call(sym, date):
    state.delete_call(sym, date)


def _calls():
    calls = st.session_state.get("calls") or []
    T.section("My research calls", "saved from the Research note tab · measured against the S&P 500 since the call")
    if not calls:
        T.show('<div class="amb-empty">No calls yet. Open any stock, write its research note in the Research note tab and '
               'save your Buy / Hold / Sell call: it shows up here with its return against the S&P 500 since that day.</div>')
        return
    spy = src.try_quote("SPY")
    rows, hits, scored = [], 0, 0
    for c in reversed(calls):
        q = src.try_quote(c["sym"])
        ret = (q["price"] / c["price"] - 1) if q and c.get("price") else None
        mkt = (spy["price"] / c["spy"] - 1) if spy and c.get("spy") else None
        excess = ret - mkt if ret is not None and mkt is not None else None
        if excess is not None and c["lean"] in ("Buy", "Sell"):
            scored += 1
            hits += (excess > 0) if c["lean"] == "Buy" else (excess < 0)
        tone = {"Buy": "up", "Sell": "down"}.get(c["lean"], "flat")
        rows.append(f'<tr><td><span{T.go_attr("t:" + c["sym"])} style="cursor:pointer">{T.esc(c["sym"])}</span></td>'
                    f'<td>{T.esc(c["date"])}</td><td><span class="amb-pill {tone}">{T.esc(c["lean"])}</span></td>'
                    f'<td>{T.money(c["price"])}</td><td>{T.money(q["price"]) if q else "—"}</td>'
                    f'<td style="color:var(--{T.tone(ret)})">{T.pct(ret)}</td><td>{T.pct(mkt)}</td>'
                    f'<td style="color:var(--{T.tone(excess)})">{T.pct(excess)}</td>'
                    f'<td>{T.money(c.get("value")) if c.get("value") else "—"}</td></tr>')
    click('<div class="amb-wrap"><table class="amb-table"><thead><tr><th>Stock</th><th>Date</th><th>Call</th><th>Price then</th>'
           '<th>Now</th><th>Return</th><th>S&amp;P 500</th><th>vs S&amp;P</th><th>Your value</th></tr></thead>'
           f'<tbody>{"".join(rows)}</tbody></table></div>', "calls_tbl")
    if scored:
        T.show(f'<div class="amb-note">Hit rate: {hits} of {scored} Buy / Sell calls are right so far (a Buy is right when it beats '
               f'the S&amp;P 500, a Sell when it lags it). Calls are saved in this browser.</div>')
    with st.expander("Delete a call"):
        for c in calls:
            c1, c2 = st.columns([4, 1])
            c1.write(f"{c['sym']} · {c['lean']} · {c['date']}")
            c2.button("Delete", key=f"delcall_{c['sym']}_{c['date']}", on_click=_del_call, args=(c["sym"], c["date"]))


# --------------------------------------------------------------------------- portfolio lab
def _closes(symbols: tuple[str, ...]) -> pd.DataFrame:
    """Daily closes (each history is cached in sources, so a symbol that failed is retried next time)."""
    ser = {}
    for s in symbols + ("SPY",):
        h = src.try_history(s)
        if h is not None:
            ser[s] = h["close"]
    return Q.aligned(ser)


def _portfolio_lab():
    T.section("Portfolio lab", "Markowitz efficient frontier for the stocks you pick")
    pool = state.all_symbols()
    c1, c2, c3 = st.columns([3, 1, 1], gap="medium")
    with c1:
        picks = st.multiselect("Stocks", pool, default=state.US_LEADERS, key="pf_picks", max_selections=10)
    with c2:
        cap = st.slider("Max per stock", 10, 100, 35, 5, key="pf_cap", format="%d%%") / 100
    with c3:
        erp = st.slider("Equity risk premium", 3.0, 8.0, 5.0, 0.25, key="pf_erp", format="%.2f%%") / 100
    if len(picks) < 2:
        T.show('<div class="amb-empty">Pick at least two stocks.</div>')
        return
    with st.spinner("Loading two years of prices (free plan: 8 requests per minute)..."):
        df = _closes(tuple(picks))
    have = [s for s in picks if s in df.columns]
    missing = [s for s in picks if s not in have]
    if missing:
        st.caption(f"No price history right now for {', '.join(missing)} (free plan limit); they are left out. Refresh in a minute.")
    if "SPY" not in df.columns or len(have) < 2 or len(df) < 120:
        T.show('<div class="amb-empty">Not enough price history right now (Twelve Data limit). Try again in a minute.</div>')
        return
    rf, _ = src.risk_free()
    wk = df.resample("W-FRI").last().pct_change().dropna()
    betas = {s: V.adjusted_beta(Q.beta(df[s], df["SPY"])) for s in have}
    mu = P.capm_returns(betas, rf, erp)
    cov, delta = P.ledoit_wolf(wk[have])
    cov = cov * P.PERIODS
    w_sh = P.optimize(mu, cov, rf, cap, "sharpe")
    w_mv = P.optimize(mu, cov, rf, cap, "minvar")
    w_eq = np.full(len(have), 1 / len(have))
    d_sh, d_mv, d_eq = (P.describe(w, mu, cov, rf) for w in (w_sh, w_mv, w_eq))
    fr = P.frontier(mu, cov, rf, cap)

    fig = go.Figure()
    fig.add_scatter(x=fr["vol"] * 100, y=fr["ret"] * 100, mode="lines", name="Efficient frontier",
                    line=dict(color=T.C["acc"], width=2.4))
    vols = np.sqrt(np.diag(cov))
    fig.add_scatter(x=vols * 100, y=mu.values * 100, mode="markers+text", name="Single stocks", text=have,
                    textposition="top center", marker=dict(color=T.C["us"], size=8), textfont=dict(color=T.C["text2"], size=11))
    for nm, d_, col, sym in (("Maximum Sharpe", d_sh, T.C["up"], "star"), ("Minimum variance", d_mv, T.C["mx"], "diamond"),
                             ("Equal weight", d_eq, T.C["text2"], "circle-open")):
        fig.add_scatter(x=[d_["vol"] * 100], y=[d_["ret"] * 100], mode="markers", name=nm,
                        marker=dict(color=col, size=14, symbol=sym, line=dict(width=1.5, color=col)))
    x_max = float(max(vols.max(), fr["vol"].max()) * 100 * 1.05)
    fig.add_scatter(x=[0, x_max], y=[rf * 100, rf * 100 + d_sh["sharpe"] * x_max], mode="lines", name="Capital market line",
                    line=dict(color=T.C["muted"], width=1, dash="dot"))
    fig.update_xaxes(title="Risk: annual volatility", ticksuffix="%", rangemode="tozero")
    fig.update_yaxes(title="Expected return (CAPM)", ticksuffix="%")
    fig.update_layout(hovermode="closest")
    T.plot(fig, 420)

    head = "".join(f"<th>{T.esc(s)}</th>" for s in have)

    def row(nm, d_):
        cells = "".join(f"<td>{d_['weights'][s]:.0%}</td>" for s in have)
        return (f"<tr><td>{nm}</td>{cells}<td>{T.pct(d_['ret'], 1, False)}</td><td>{T.pct(d_['vol'], 1, False)}</td>"
                f"<td>{d_['sharpe']:.2f}</td></tr>")
    T.show(f'<div class="amb-wrap"><table class="amb-table"><thead><tr><th>Portfolio</th>{head}<th>Return</th><th>Risk</th>'
           f'<th>Sharpe</th></tr></thead><tbody>{row("Maximum Sharpe", d_sh)}{row("Minimum variance", d_mv)}'
           f'{row("Equal weight", d_eq)}</tbody></table></div>')
    T.show(f'<div class="amb-note">Expected returns come from CAPM ({rf:.2%} + adjusted beta × {erp:.2%}), not from past returns, '
           f'which are too noisy to optimize on. Risk uses two years of weekly returns with Ledoit-Wolf shrinkage '
           f'({delta:.0%} toward a constant-variance target). Long-only, fully invested, at most {cap:.0%} in one stock. '
           f'The maximum-Sharpe portfolio is where the capital market line touches the frontier. Diversification is what '
           f'pulls the frontier to the left of the single stocks.</div>')
