"""Portfolio: your positions with a broker-style P&L, the track record of your research calls, and a
portfolio lab (Markowitz) to see how the stocks you hold or follow combine."""
from __future__ import annotations

import base64
import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ai
import portfolio as P
import quant as Q
import sources as src
import state
import theme as T
import valuation as V
from views import search
from views.common import click, name_of


def render():
    T.show('<div class="amb-hero"><div><h1>Portfolio</h1><div class="sub">Your positions marked to market, the calls you '
           'saved from research notes, and the efficient frontier. Everything is saved in this browser.</div></div></div>')
    t1, t2, t3 = st.tabs(["Positions & P&L", "Research calls", "Portfolio lab"])
    with t1:
        _positions()
    with t2:
        _calls()
    with t3:
        _lab()
    T.footer("Quotes: Finnhub · history: Twelve Data · not investment advice")


def _closes(symbols: tuple[str, ...]) -> pd.DataFrame:
    """Daily closes, two years (each history is cached in sources, so a symbol that failed is retried next time)."""
    ser = {}
    for s in dict.fromkeys(symbols + ("SPY",)):
        h = src.try_history(s)
        if h is not None:
            ser[s] = h["close"]
    return Q.aligned(ser) if ser else pd.DataFrame()


def _m(x) -> str:
    """Dollars with cents, always (a broker statement never rounds)."""
    return "—" if not T.is_num(x) else f"{'-' if x < 0 else ''}${abs(x):,.2f}"


def _signed_money(x):
    if not T.is_num(x):
        return "—"
    return f'<span style="color:var(--{T.tone(x)})">{"+" if x > 0 else ""}{_m(x)}</span>'


# --------------------------------------------------------------------------- positions
def _example() -> dict:
    """$10,000 in each 2026 S&P 500 leader at the Dec 31, 2025 close."""
    pos = []
    for s in state.US_LEADERS:
        try:
            d, px = src.close_on(s, dt.date(2025, 12, 31))
        except Exception:
            continue
        pos.append({"sym": s, "shares": round(10000 / px, 4), "cost": round(px, 4), "date": d.isoformat()})
    return {"cash": 0.0, "positions": pos}


def _encode(pf: dict) -> str:
    raw = ";".join(f"{p['sym']},{p['shares']:g},{p['date']},{p['cost']:g}" for p in pf["positions"])
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode(code: str) -> dict:
    raw = base64.urlsafe_b64decode(code + "=" * (-len(code) % 4)).decode()
    pos = []
    for part in raw.split(";"):
        sym, sh, d, cost = part.split(",")
        pos.append({"sym": sym, "shares": float(sh), "date": d, "cost": float(cost)})
    return {"cash": 0.0, "positions": pos}


def _import_link():
    """Open a portfolio shared as a link (…/portfolio?pf=…) on this device."""
    code = st.query_params.get("pf")
    if not code:
        return
    try:
        state.set_portfolio(_decode(code))
        st.toast("Portfolio loaded on this device.")
    except Exception:
        st.toast("That portfolio link isn't valid.")
    del st.query_params["pf"]


def _add_form(pf: dict):
    T.section("Add a position", "the stock, the day you bought and how many shares · the price is that day's close")
    pick = search.picker("pf_pick", "Search the stock you bought")
    if pick:
        st.session_state["pf_new_sym"] = pick
    sym = st.session_state.get("pf_new_sym")
    c1, c2, c3 = st.columns([1.2, 1, 1], gap="medium", vertical_alignment="bottom")
    with c1:
        T.show(f'<div class="amb-picked">{("<b>" + T.esc(sym) + "</b> " + T.esc(name_of(sym)[:34])) if sym else "No stock selected yet"}</div>')
    with c2:
        day = st.date_input("Date bought", value=dt.date.today(), min_value=dt.date(2000, 1, 3), max_value=dt.date.today(),
                            key="pf_new_date", format="YYYY-MM-DD")
    with c3:
        shares = st.number_input("Shares", min_value=0.0, value=10.0, step=1.0, key="pf_new_shares", format="%.4g")
    b1, b2, b3 = st.columns([1.2, 1, 1], gap="medium")
    if b1.button("Add position", type="primary", width="stretch", key="pf_add", disabled=not sym or shares <= 0):
        try:
            with st.spinner(f"Finding {sym}'s close on {day:%b %d, %Y}..."):
                used, px = src.close_on(sym, day)
            state.set_portfolio({"cash": pf.get("cash", 0.0),
                                 "positions": pf["positions"] + [{"sym": sym, "shares": shares, "cost": px, "date": used.isoformat()}]})
            st.session_state["pf_msg"] = f"Added {shares:g} {sym} at ${px:,.2f}, the close of {used:%b %d, %Y}."
            st.session_state.pop("pf_new_sym", None)
            st.rerun()
        except Exception as e:
            st.error(f"Couldn't find {sym}'s price on that date ({e}).")
    if b2.button("Load an example", width="stretch", key="pf_example",
                 help="$10,000 in each of the five 2026 S&P 500 leaders, bought at the Dec 31, 2025 close."):
        with st.spinner("Loading year-end prices..."):
            state.set_portfolio(_example())
        st.rerun()
    if pf["positions"] and b3.button("Remove all", width="stretch", key="pf_clear"):
        state.set_portfolio({"cash": 0.0, "positions": []})
        st.rerun()
    msg = st.session_state.pop("pf_msg", None)
    if msg:
        st.success(msg)


def _lots(pos: list[dict], quotes: dict, spy_now: float | None) -> pd.DataFrame:
    """One row per purchase with the S&P 500 over the same holding period."""
    rows = []
    for i, p in enumerate(pos):
        q = quotes.get(p["sym"])
        last = q["price"] if q else np.nan
        prev = (q["price"] - q["change"]) if q and q.get("change") is not None else np.nan
        try:
            spy_then = src.close_on("SPY", dt.date.fromisoformat(p["date"]))[1] if p.get("date") else np.nan
        except Exception:
            spy_then = np.nan
        value = p["shares"] * last
        cost = p["shares"] * p["cost"]
        ret = last / p["cost"] - 1
        spy_ret = (spy_now / spy_then - 1) if spy_now and spy_then == spy_then else np.nan
        rows.append({"i": i, "sym": p["sym"], "date": p.get("date") or "", "shares": p["shares"], "buy": p["cost"], "last": last,
                     "chg": (q["pct"] / 100) if q else np.nan, "daily": p["shares"] * (last - prev), "value": value,
                     "cost": cost, "pnl": value - cost, "ret": ret, "spy": spy_ret, "excess": ret - spy_ret})
    return pd.DataFrame(rows)


def _facts(lots, nav, twr, spy_ret, risk, weights) -> str:
    lines = ["Positions (one row per purchase): " + "; ".join(
        f"{r.sym} {r.shares:g} sh bought {r.date} at {r.buy:.2f}, now {r.last:.2f}, P&L {r.pnl:+,.0f} ({r.ret:+.1%}), "
        f"S&P same period {r.spy:+.1%}" for r in lots.itertuples())]
    lines.append(f"Market value {nav:,.0f}; cost {lots['cost'].sum():,.0f}; unrealized P&L {lots['pnl'].sum():+,.0f} "
                 f"({lots['pnl'].sum() / lots['cost'].sum():+.1%}).")
    if len(twr):
        lines.append(f"Time-weighted return since first purchase {twr.iloc[-1]:+.1%}; S&P 500 same period "
                     f"{spy_ret:+.1%}" if spy_ret is not None else f"Time-weighted return {twr.iloc[-1]:+.1%}")
    lines.append("Weights: " + ", ".join(f"{s} {w:.0%}" for s, w in weights.sort_values(ascending=False).items()))
    contrib = lots.groupby("sym")["pnl"].sum().sort_values(ascending=False)
    lines.append("P&L contribution: " + ", ".join(f"{s} {v:+,.0f}" for s, v in contrib.items()))
    if risk:
        lines.append(f"Risk: beta {risk['beta']:.2f}, volatility {risk['vol']:.1%}, 1-day VaR 95% {risk['var']:.1%} "
                     f"(${risk['var'] * nav:,.0f}), expected shortfall {risk['cvar']:.1%}, effective positions {risk['effective_n']:.1f}"
                     if risk.get("beta") is not None else "")
    for s in weights.index:
        er = src.next_earnings(s)
        if er:
            lines.append(f"{s} next earnings {er['date']}")
    return "\n".join(x for x in lines if x)


def _portfolio_pdf(lots, nav, twr, spy_cum, risk, review, day) -> bytes:
    import pdf_report as R
    doc = R.Doc("Portfolio report", f"Portfolio report, {day}")
    pnl, cost = float(lots["pnl"].sum()), float(lots["cost"].sum())
    doc.title_block("Portfolio report", [f"{day} · {lots['sym'].nunique()} stocks, {len(lots)} purchases · prices at the last close"])
    figs = [("Market value", f"${nav:,.2f}"), ("Cost", f"${cost:,.2f}"), ("Unrealized P&L", f"{'+' if pnl >= 0 else '-'}${abs(pnl):,.2f}"),
            ("Return on cost", T.pct(pnl / cost if cost else None, 1))]
    if len(twr):
        figs.append(("Time-weighted return", T.pct(float(twr.iloc[-1]), 1)))
        if spy_cum is not None:
            figs.append(("S&P 500, same period", T.pct(float(spy_cum.iloc[-1]), 1)))
    doc.metrics(figs, 3)
    if review:
        doc.para(review.get("headline", ""), 11, bold=True)
    doc.h2("Positions")
    rows, colors = [], []
    for r in lots.itertuples():
        rows.append([r.sym, r.date, f"{r.shares:,.4g}", f"${r.buy:,.2f}", f"${r.last:,.2f}", f"${r.value:,.0f}",
                     f"{'+' if r.pnl >= 0 else '-'}${abs(r.pnl):,.0f}", T.pct(r.ret, 1), T.pct(r.spy, 1), T.pct(r.excess, 1)])
        colors.append([None] * 6 + [R.tone_color(r.pnl), R.tone_color(r.ret), None, R.tone_color(r.excess)])
    rows.append(["Total", "", "", "", "", f"${nav:,.0f}", f"{'+' if pnl >= 0 else '-'}${abs(pnl):,.0f}", T.pct(pnl / cost if cost else None, 1), "", ""])
    colors.append(None)
    doc.grid_table(["Stock", "Bought", "Shares", "Buy price", "Last", "Value", "P&L", "Return", "S&P 500", "vs S&P"],
                   rows, widths=[13, 20, 13, 16, 16, 18, 17, 14, 17, 14], bold_last=True, colors=colors)
    if len(twr) > 1:
        doc.h2("Performance vs the S&P 500", keep=78)
        series = {"Portfolio (time-weighted)": (twr.index, twr.values * 100)}
        if spy_cum is not None:
            series["S&P 500 (SPY)"] = (spy_cum.index, spy_cum.values * 100)
        doc.image_png(R.line_chart(series), 62)
    contrib = lots.groupby("sym")["pnl"].sum().sort_values(ascending=False)
    ch = max(28, 9 * len(contrib) + 10)
    doc.h2("Contribution to P&L", keep=ch + 14)
    doc.image_png(R.bar_chart(list(contrib.index), [float(v) for v in contrib.values]), ch)
    if risk and risk.get("beta") is not None:
        doc.h2("Risk of today's holdings")
        doc.metrics([("Beta vs S&P 500", f"{risk['beta']:.2f}"), ("Volatility", T.pct(risk["vol"], 1, False)),
                     ("1-day VaR 95%", f"-${risk['var'] * nav:,.0f}"), ("Expected shortfall", f"-${risk['cvar'] * nav:,.0f}"),
                     ("Effective positions", f"{risk['effective_n']:.1f}")], 3)
    if review:
        doc.h2("Review")
        for k, lbl in (("performance", "Performance"), ("drivers", "What drove it"), ("risk", "Risk"),
                       ("diversification", "Diversification")):
            if review.get(k):
                doc.para(f"{lbl}. {review[k]}")
        if review.get("watch"):
            doc.para("What to watch", bold=True)
            doc.bullets(review["watch"])
        if review.get("ideas"):
            doc.para("Ideas to consider", bold=True)
            doc.bullets(review["ideas"])
    doc.ln(2)
    doc.para("Prices: Finnhub (last) and Twelve Data (closes on purchase dates). Time-weighted return treats each purchase as "
             "new money. The review is written by a language model from these numbers. Not investment advice.", 8, R.MUTED)
    return doc.output_bytes()


def _positions():
    _import_link()
    pf = st.session_state.get("pf") or {"cash": 0.0, "positions": []}
    pos = pf["positions"]
    if not pos:
        T.show('<div class="amb-empty">No positions yet. Search the stock, pick the day you bought it and the number of shares: '
               'the app looks up that day\'s close as your buy price and tracks it against today\'s price and the S&amp;P 500.</div>')
        _add_form(pf)
        return
    syms = list(dict.fromkeys(p["sym"] for p in pos))
    with st.spinner("Marking positions to market..."):
        quotes = {s: src.try_quote(s) for s in syms}
        spy_q = src.try_quote("SPY")
        lots = _lots(pos, quotes, spy_q["price"] if spy_q else None)
    nav = float(lots["value"].sum(skipna=True))
    cost = float(lots["cost"].sum())
    pnl = nav - cost
    daily = float(lots["daily"].sum(skipna=True))
    prev_nav = nav - daily
    with st.spinner("Loading price history (free plan: 8 requests per minute)..."):
        closes = _closes(tuple(syms))
    twr = P.time_weighted(pos, closes) if not closes.empty else pd.Series(dtype=float)
    spy_cum, spy_ret = None, None
    if len(twr) > 1 and "SPY" in closes:
        spy = closes["SPY"].reindex(twr.index).ffill()
        spy_cum = spy / spy.iloc[0] - 1
        spy_ret = float(spy_cum.iloc[-1])

    T.show(T.kv([
        ("Market value", _m(nav), f"{len(syms)} stocks · {len(pos)} purchases"),
        ("Unrealized P&L", _signed_money(pnl), T.pct(pnl / cost if cost else None, 1) + f" on {_m(cost)} invested"),
        ("Today", _signed_money(daily), T.pct(daily / prev_nav if prev_nav else None, 2)),
        ("Return since first buy", f'<span style="color:var(--{T.tone(twr.iloc[-1] if len(twr) else None)})">'
         f'{T.pct(twr.iloc[-1] if len(twr) else None, 1)}</span>', "time-weighted"),
        ("S&P 500, same period", T.pct(spy_ret, 1), "SPY"),
        ("Beat the market by", f'<span style="color:var(--{T.tone((twr.iloc[-1] - spy_ret) if len(twr) and spy_ret is not None else None)})">'
         f'{T.pct((twr.iloc[-1] - spy_ret) if len(twr) and spy_ret is not None else None, 1)}</span>', "percentage points"),
    ]))

    # ---- holdings: one row per purchase, closing price that day vs today
    head = ("<th>Stock</th><th>Bought</th><th>Shares</th><th>Buy price</th><th>Last</th><th>Today</th><th>Value</th>"
            "<th>P&amp;L</th><th>Return</th><th>S&amp;P same period</th><th>vs S&amp;P</th><th></th>")
    body = ""
    for r in lots.sort_values("value", ascending=False).itertuples():
        body += (f'<tr><td><span{T.go_attr("t:" + r.sym)} style="cursor:pointer"><b style="color:var(--text)">{T.esc(r.sym)}</b>'
                 f'<span class="amb-sub-name">{T.esc(name_of(r.sym)[:24])}</span></span></td>'
                 f'<td>{T.esc(r.date)}</td><td>{r.shares:,.4g}</td><td>{_m(r.buy)}</td><td>{_m(r.last)}</td>'
                 f'<td style="color:var(--{T.tone(r.chg)})">{T.pct(r.chg, 2)}</td><td>{_m(r.value)}</td>'
                 f'<td>{_signed_money(r.pnl)}</td><td style="color:var(--{T.tone(r.ret)})">{T.pct(r.ret, 1)}</td>'
                 f'<td>{T.pct(r.spy, 1)}</td><td style="color:var(--{T.tone(r.excess)})">{T.pct(r.excess, 1)}</td>'
                 f'<td><span class="amb-x"{T.go_attr(f"rm:{r.i}")} title="Remove this purchase">✕</span></td></tr>')
    body += (f'<tr class="hl"><td>Total</td><td></td><td></td><td></td><td></td>'
             f'<td>{T.pct(daily / prev_nav if prev_nav else None, 2)}</td><td>{_m(nav)}</td><td>{_signed_money(pnl)}</td>'
             f'<td>{T.pct(pnl / cost if cost else None, 1)}</td><td></td><td></td><td></td></tr>')
    hit = T.clickable(f'<div class="amb-wrap"><table class="amb-table pnl"><thead><tr>{head}</tr></thead><tbody>{body}</tbody>'
                      f'</table></div>', "pnl_tbl")
    if hit and hit.startswith("rm:"):
        i = int(hit[3:])
        state.set_portfolio({"cash": 0.0, "positions": [p for j, p in enumerate(pos) if j != i]})
        st.rerun()
    elif hit:
        from views.common import route
        route(hit)
    T.show('<div class="amb-swipe">Swipe the table sideways for P&amp;L and the S&amp;P comparison →</div>')
    T.show('<div class="amb-note">Buy price = the closing price on the day you bought (the previous trading day\'s close for a '
           'weekend or holiday). "S&amp;P same period" is SPY from that same close to today, so "vs S&amp;P" tells you whether '
           'the purchase beat simply buying the index. ✕ removes a purchase.</div>')

    # ---- charts
    a, b = st.columns([1.5, 1], gap="large")
    with a:
        T.section("Performance vs the S&P 500", "time-weighted, since the first purchase")
        if len(twr) > 1:
            fig = go.Figure()
            fig.add_scatter(x=twr.index, y=twr.values * 100, name="Portfolio", mode="lines", line=dict(color=T.C["acc"], width=2.2))
            if spy_cum is not None:
                fig.add_scatter(x=spy_cum.index, y=spy_cum.values * 100, name="S&P 500 (SPY)", mode="lines",
                                line=dict(color=T.C["text2"], width=1.4, dash="dot"))
            fig.update_yaxes(ticksuffix="%")
            T.plot(fig, 300)
        else:
            T.show('<div class="amb-empty">The performance line appears from the day after your first purchase.</div>')
    with b:
        T.section("Contribution to P&L", "dollars gained or lost by each stock")
        contrib = lots.groupby("sym")["pnl"].sum().sort_values()
        fig = go.Figure(go.Bar(y=list(contrib.index), x=list(contrib.values), orientation="h",
                               marker_color=[T.C["up"] if v >= 0 else T.C["down"] for v in contrib.values],
                               text=[("+" if v >= 0 else "-") + f"${abs(v):,.0f}" for v in contrib.values], textposition="outside",
                               cliponaxis=False, hovertemplate="%{y}: %{x:$,.0f}<extra></extra>"))
        lo, hi = float(min(contrib.min(), 0)), float(max(contrib.max(), 0))
        span = (hi - lo) or 1
        fig.update_xaxes(tickprefix="$", range=[lo - span * (0.35 if lo < 0 else 0.02), hi + span * 0.35])
        fig.update_layout(hovermode="closest", margin=dict(l=8, r=20, t=10, b=8))
        T.plot(fig, 300)

    weights = lots.groupby("sym")["value"].sum()
    weights = weights / weights.sum()
    c1, c2 = st.columns([1, 1.5], gap="large")
    with c1:
        T.section("Allocation", "% of market value")
        al = weights.sort_values()
        fig = go.Figure(go.Bar(y=list(al.index), x=list(al.values * 100), orientation="h", marker_color=T.C["acc"],
                               text=[f"{v * 100:.1f}%" for v in al.values], textposition="outside", cliponaxis=False,
                               hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
        fig.update_xaxes(ticksuffix="%", range=[0, float(al.max()) * 125])
        fig.update_layout(hovermode="closest", margin=dict(l=8, r=30, t=10, b=8))
        T.plot(fig, 260)
    risk = None
    with c2:
        have = [s for s in syms if s in closes.columns]
        if have and "SPY" in closes and len(closes) > 120:
            rets = closes.pct_change().dropna()
            risk = P.holdings_risk(weights[have], rets[have], rets["SPY"])
            T.section("Risk of today's holdings", f"today's weights over the last {risk['days']} sessions")
            T.show(T.kv([
                ("Beta", f"{risk['beta']:.2f}" if risk["beta"] is not None else "—", "vs S&P 500, daily"),
                ("Volatility", T.pct(risk["vol"], 1, False), "annualized"),
                ("1-day VaR 95%", f'<span style="color:var(--down)">−{T.money(risk["var"] * nav, 0)}</span>', "historical"),
                ("Expected shortfall", f'<span style="color:var(--down)">−{T.money(risk["cvar"] * nav, 0)}</span>', "worst 5% of days"),
                ("Effective positions", f"{risk['effective_n']:.1f}", "1 / sum of squared weights"),
                ("Largest position", f"{weights.idxmax()} · {weights.max():.0%}", "of market value"),
            ]))

    # ---- analysis + downloads
    T.section("Portfolio review", "written from the numbers above")
    day = dt.date.today().isoformat()
    key = "pf_review_on"
    review = None
    if st.button("Write the review", type="primary", key="pf_review_btn") or st.session_state.get(key):
        try:
            with st.spinner("Reviewing the portfolio..."):
                review = ai.portfolio_review(_facts(lots, nav, twr, spy_ret, risk, weights), day)
            st.session_state[key] = True
        except Exception as e:
            st.info(f"The written review isn't available right now ({e}).")
    if review:
        T.show(f'<div class="amb-lead">{T.esc(review.get("headline", ""))}</div>')
        blocks = [("Performance", review.get("performance")), ("What drove it", review.get("drivers")),
                  ("Risk", review.get("risk")), ("Diversification", review.get("diversification"))]
        T.show('<div class="amb-grid g2 stack">' + "".join(
            f'<div class="amb-take"><div class="h">{k_}</div><p>{T.esc(v_ or "")}</p></div>' for k_, v_ in blocks) + "</div>")
        st.write("")
        lists = [("What to watch", review.get("watch")), ("Ideas to consider", review.get("ideas"))]
        T.show('<div class="amb-grid g2 stack">' + "".join(
            f'<div class="amb-take"><div class="h">{k_}</div><ul class="amb-ul">{"".join("<li>" + T.esc(str(x)) + "</li>" for x in (v_ or []))}</ul></div>'
            for k_, v_ in lists) + "</div>")
        T.show('<div class="amb-note"><span class="amb-tag ai">AI</span>Written by Gemini only from this portfolio\'s numbers. '
               'Educational, not personalized investment advice.</div>')
    d1, d2 = st.columns([1, 1], gap="medium")
    d1.download_button("Download PDF report", _portfolio_pdf(lots, nav, twr, spy_cum, risk, review, day),
                       file_name=f"portfolio_report_{day}.pdf", mime="application/pdf", width="stretch", key="pf_pdf",
                       help="Includes the review if you wrote it above.")
    with d2.popover("Open on another device", width="stretch"):
        base = (getattr(st.context, "url", None) or "https://alejandro-market-brief.streamlit.app/portfolio").split("?")[0]
        st.caption("Your positions are saved in this browser. Open this link on your phone (or any computer) to load them there.")
        st.code(f"{base}?pf={_encode(pf)}", language=None, wrap_lines=True)

    _add_form(pf)


# --------------------------------------------------------------------------- research calls
def _del_call(sym, date):
    state.delete_call(sym, date)


def _calls():
    calls = st.session_state.get("calls") or []
    T.section("Research calls", "saved from the Research note tab · measured against the S&P 500 since the call")
    if not calls:
        T.show('<div class="amb-empty">No calls yet. Open any stock, write its research note in the Research note tab and '
               'save your Buy / Hold / Sell call: it shows up here with its return against the S&P 500 since that day.</div>')
        return
    spy = src.try_quote("SPY")
    rows, hits, scored, ex_list = [], 0, 0, []
    for c in reversed(calls):
        q = src.try_quote(c["sym"])
        ret = (q["price"] / c["price"] - 1) if q and c.get("price") else None
        mkt = (spy["price"] / c["spy"] - 1) if spy and c.get("spy") else None
        excess = ret - mkt if ret is not None and mkt is not None else None
        # a call's result: long the stock for Buy, short it for Sell, both against the index
        call_alpha = None if excess is None else (excess if c["lean"] == "Buy" else -excess if c["lean"] == "Sell" else None)
        if call_alpha is not None:
            scored += 1
            hits += call_alpha > 0
            ex_list.append(call_alpha)
        tone = {"Buy": "up", "Sell": "down"}.get(c["lean"], "flat")
        upside = (c["value"] / c["price"] - 1) if c.get("value") and c.get("price") else None
        days = (dt.date.today() - dt.date.fromisoformat(c["date"])).days if c.get("date") else None
        rows.append(f'<tr><td><span{T.go_attr("t:" + c["sym"])} style="cursor:pointer"><b style="color:var(--text)">{T.esc(c["sym"])}</b></span></td>'
                    f'<td>{T.esc(c["date"])}</td><td>{days if days is not None else "—"}</td>'
                    f'<td><span class="amb-pill {tone}">{T.esc(c["lean"])}</span></td>'
                    f'<td>{T.money(c["price"])}</td><td>{T.money(q["price"]) if q else "—"}</td>'
                    f'<td style="color:var(--{T.tone(ret)})">{T.pct(ret)}</td><td>{T.pct(mkt)}</td>'
                    f'<td style="color:var(--{T.tone(call_alpha)})">{T.pct(call_alpha)}</td>'
                    f'<td>{T.money(c.get("value")) if c.get("value") else "—"}</td><td>{T.pct(upside, 0)}</td></tr>')
    T.show(T.kv([
        ("Calls", f"{len(calls)}", f"{scored} Buy / Sell, {len(calls) - scored} Hold"),
        ("Hit rate", f"{hits}/{scored}" if scored else "—", "Buy beat the S&P, or Sell lagged it"),
        ("Average call alpha", T.pct(float(np.mean(ex_list)), 1) if ex_list else "—", "vs the S&P 500 since each call"),
    ]))
    click('<div class="amb-wrap"><table class="amb-table"><thead><tr><th>Stock</th><th>Date</th><th>Days</th><th>Call</th>'
          '<th>Price then</th><th>Now</th><th>Stock return</th><th>S&amp;P 500</th><th>Call alpha</th><th>Your value</th>'
          f'<th>Upside then</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>', "calls_tbl")
    T.show('<div class="amb-note">Call alpha is the stock\'s return minus the S&amp;P 500\'s since the call, with the sign '
           'flipped for Sells (a Sell is right when the stock lags the index). Hold calls are tracked but not scored. '
           'Your value is the probability-weighted DCF value when you saved the call.</div>')
    with st.expander("Delete a call"):
        for c in calls:
            c1, c2 = st.columns([4, 1])
            c1.write(f"{c['sym']} · {c['lean']} · {c['date']}")
            c2.button("Delete", key=f"delcall_{c['sym']}_{c['date']}", on_click=_del_call, args=(c["sym"], c["date"]))


# --------------------------------------------------------------------------- portfolio lab
def _lab():
    pf = st.session_state.get("pf") or {"positions": []}
    held = list(dict.fromkeys(p["sym"] for p in pf["positions"]))
    pool = list(dict.fromkeys(held + state.all_symbols()))
    default = held[:10] if len(held) >= 2 else state.US_LEADERS
    T.section("Efficient frontier", "Markowitz mean-variance, long only")
    c1, c2, c3 = st.columns([3, 1, 1], gap="medium")
    with c1:
        picks = st.multiselect("Stocks", pool, default=[s for s in default if s in pool], key="pf_picks", max_selections=10)
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
    mu = pd.Series({s_: V.capm(rf, b_, erp) for s_, b_ in betas.items()})  # same CAPM as the DCF (beta held to 0.5-2.5)
    cov, delta = P.ledoit_wolf_cc(wk[have])
    cov = cov * P.PERIODS
    cap_used = P.effective_cap(cap, len(have))
    if cap_used > cap + 1e-9:
        st.caption(f"With {len(have)} stocks a {cap:.0%} cap would leave almost no choice, so up to {cap_used:.0%} per stock is "
                   f"allowed here. Add stocks to use a tighter cap.")
    cap = cap_used
    w_sh = P.optimize(mu, cov, rf, cap, "sharpe")
    w_mv = P.optimize(mu, cov, rf, cap, "minvar")
    w_eq = np.full(len(have), 1 / len(have))
    d_sh, d_mv, d_eq = (P.describe(w, mu, cov, rf) for w in (w_sh, w_mv, w_eq))
    fr = P.frontier(mu, cov, rf, cap)
    d_me = None
    if held and set(held) <= set(have):
        vals = pd.Series({s: sum(p["shares"] for p in pf["positions"] if p["sym"] == s) * (src.try_quote(s) or {}).get("price", np.nan)
                          for s in have}).fillna(0.0)
        if vals.sum() > 0:
            d_me = P.describe((vals / vals.sum()).to_numpy(), mu, cov, rf)

    fig = go.Figure()
    if len(have) == 2:  # the classic two-asset curve: every mix from 100% of one to 100% of the other
        ws = np.linspace(0, 1, 41)
        mix = [((w * mu.iloc[0] + (1 - w) * mu.iloc[1]) * 100,
                np.sqrt(max(w * w * cov[0, 0] + (1 - w) ** 2 * cov[1, 1] + 2 * w * (1 - w) * cov[0, 1], 0)) * 100) for w in ws]
        fig.add_scatter(x=[v for _, v in mix], y=[r for r, _ in mix], mode="lines", name="All mixes of the two",
                        line=dict(color=T.C["muted"], width=1.2, dash="dot"),
                        hovertemplate="risk %{x:.1f}%, return %{y:.1f}%<extra></extra>")
    eff, low = fr[fr["efficient"]], fr[~fr["efficient"]]
    if len(low) > 1:
        fig.add_scatter(x=low["vol"] * 100, y=low["ret"] * 100, mode="lines", name="Inefficient branch",
                        line=dict(color=T.C["acc"], width=1.2, dash="dot"), hoverinfo="skip")
    fig.add_scatter(x=eff["vol"] * 100, y=eff["ret"] * 100, mode="lines", name="Efficient frontier",
                    line=dict(color=T.C["acc"], width=2.4))
    vols = np.sqrt(np.diag(cov))
    fig.add_scatter(x=vols * 100, y=mu.values * 100, mode="markers+text", name="Single stocks", text=have,
                    textposition="top center", marker=dict(color=T.C["us"], size=8), textfont=dict(color=T.C["text2"], size=11),
                    hovertemplate="%{text}: risk %{x:.1f}%, return %{y:.1f}%<extra></extra>")
    marks = [("Maximum Sharpe (tangency)", d_sh, T.C["up"], "star"), ("Minimum variance", d_mv, T.C["mx"], "diamond"),
             ("Equal weight", d_eq, T.C["text2"], "circle-open")]
    if d_me:
        marks.append(("Your portfolio", d_me, T.C["ai"], "square"))
    for nm, d_, col, sym in marks:
        fig.add_scatter(x=[d_["vol"] * 100], y=[d_["ret"] * 100], mode="markers", name=nm,
                        marker=dict(color=col, size=14, symbol=sym, line=dict(width=1.5, color=col)),
                        hovertemplate=f"{nm}: risk %{{x:.1f}}%, return %{{y:.1f}}%<extra></extra>")
    x_max = float(max(vols.max(), fr["vol"].max()) * 100 * 1.05)
    fig.add_scatter(x=[0, x_max], y=[rf * 100, rf * 100 + d_sh["sharpe"] * x_max], mode="lines", name="Capital market line",
                    line=dict(color=T.C["muted"], width=1, dash="dot"), hoverinfo="skip")
    fig.update_xaxes(title="Risk: annual volatility", ticksuffix="%", rangemode="tozero")
    fig.update_yaxes(title="Expected return (CAPM)", ticksuffix="%")
    fig.update_layout(hovermode="closest", legend=dict(orientation="h", y=-0.22, x=0, yanchor="top"),
                      margin=dict(l=8, r=16, t=16, b=8))
    T.plot(fig, 480)

    head = "".join(f"<th>{T.esc(s)}</th>" for s in have)

    def row(nm, d_):
        cells = "".join(f"<td>{d_['weights'][s]:.0%}</td>" for s in have)
        return (f"<tr><td>{nm}</td>{cells}<td>{T.pct(d_['ret'], 1, False)}</td><td>{T.pct(d_['vol'], 1, False)}</td>"
                f"<td>{d_['sharpe']:.2f}</td><td>{d_['effective_n']:.1f}</td></tr>")
    rows = row("Maximum Sharpe", d_sh) + row("Minimum variance", d_mv) + row("Equal weight", d_eq) + (row("Your portfolio", d_me) if d_me else "")
    T.show(f'<div class="amb-wrap"><table class="amb-table"><thead><tr><th>Portfolio</th>{head}<th>Exp. return</th><th>Risk</th>'
           f'<th>Sharpe</th><th>Eff. N</th></tr></thead><tbody>{rows}</tbody></table></div>')

    a, b = st.columns([1, 1], gap="large")
    with a:
        T.section("Inputs", "what the optimizer sees")
        rows_in = "".join(f"<tr><td>{s}</td><td>{betas[s]:.2f}</td><td>{T.pct(mu[s], 1, False)}</td>"
                          f"<td>{T.pct(np.sqrt(cov[i, i]), 1, False)}</td></tr>" for i, s in enumerate(have))
        T.show(f'<div class="amb-wrap"><table class="amb-table"><thead><tr><th>Stock</th><th>Adj. beta</th><th>Exp. return</th>'
               f'<th>Volatility</th></tr></thead><tbody>{rows_in}</tbody></table></div>')
    with b:
        T.section("Correlation", "weekly returns, two years")
        corr = wk[have].corr()
        fig = go.Figure(go.Heatmap(z=corr.values, x=have, y=have, zmin=-1, zmax=1,
                                   colorscale=[[0, T.C["down"]], [0.5, T.C["card"]], [1, T.C["acc"]]],
                                   text=np.round(corr.values, 2), texttemplate="%{text}", showscale=False,
                                   hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>"))
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig.update_xaxes(showgrid=False)
        fig.update_layout(hovermode="closest")
        T.plot(fig, 300)
    T.show(f'<div class="amb-note"><b>Expected returns</b> come from CAPM ({rf:.2%} + adjusted beta × {erp:.2%}), the '
           f'equilibrium returns the model implies, rather than past returns, which are far too noisy to optimize on. '
           f'<b>Risk</b> is the covariance of two years of weekly returns, annualized (× 52) and shrunk with Ledoit-Wolf '
           f'toward a constant-correlation matrix ({delta:.0%} shrinkage), which keeps each stock\'s own volatility and '
           f'tames noisy correlations. <b>Frontier</b>: for each target return, the long-only, fully invested mix with the '
           f'lowest variance, at most {cap:.0%} per stock. <b>Capital market line</b>: from the risk-free rate through the '
           f'tangency (maximum-Sharpe) portfolio; any point on it mixes that portfolio with Treasuries. Points to the left of '
           f'the single stocks are the gain from diversification: what matters is how the stocks move together, not only '
           f'how volatile each one is.</div>')
