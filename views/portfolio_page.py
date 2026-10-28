"""Portfolio: your positions with a broker-style P&L, the track record of your research calls, and a
portfolio lab (Markowitz) to see how the stocks you hold or follow combine."""
from __future__ import annotations

import datetime as dt

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
        h = src.try_history(s)
        if h is None:
            continue
        base = h["close"][h.index < pd.Timestamp("2026-01-01")]
        if len(base):
            px = float(base.iloc[-1])
            pos.append({"sym": s, "shares": round(10000 / px, 4), "cost": round(px, 4), "date": str(base.index[-1].date())})
    return {"cash": 0.0, "positions": pos}


def _editor(pf: dict):
    rows = pd.DataFrame(pf["positions"] or [], columns=["sym", "shares", "cost", "date"])
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    with st.expander("Edit positions", expanded=not pf["positions"]):
        st.caption("One row per purchase: ticker, shares, average cost per share and the date you bought. "
                   "Add rows at the bottom; select a row and press Delete to remove it.")
        ed = st.data_editor(rows, num_rows="dynamic", width="stretch", key="pf_editor", hide_index=True,
                            column_config={
                                "sym": st.column_config.TextColumn("Ticker", required=True, max_chars=8),
                                "shares": st.column_config.NumberColumn("Shares", min_value=0.0001, format="%.4f", required=True),
                                "cost": st.column_config.NumberColumn("Avg cost ($)", min_value=0.0001, format="$%.2f", required=True),
                                "date": st.column_config.DateColumn("Date bought", max_value=dt.date.today(), format="YYYY-MM-DD"),
                            })
        c1, c2, c3 = st.columns([1.2, 1, 1], gap="medium")
        cash = c1.number_input("Cash ($)", min_value=0.0, value=float(pf["cash"]), step=100.0, key="pf_cash")
        if c2.button("Save positions", type="primary", width="stretch", key="pf_save"):
            pos = []
            for _, r in ed.iterrows():
                if pd.isna(r.get("sym")) or pd.isna(r.get("shares")) or pd.isna(r.get("cost")):
                    continue
                d = r.get("date")
                pos.append({"sym": str(r["sym"]).upper().strip(), "shares": float(r["shares"]), "cost": float(r["cost"]),
                            "date": "" if pd.isna(d) else str(pd.Timestamp(d).date())})
            state.set_portfolio({"cash": cash, "positions": pos})
            st.session_state.pop("pf_editor", None)
            st.rerun()
        if c3.button("Load an example", width="stretch", key="pf_example",
                     help="$10,000 in each of the five 2026 S&P 500 leaders, bought at the Dec 31, 2025 close."):
            with st.spinner("Loading year-end prices..."):
                state.set_portfolio(_example())
            st.session_state.pop("pf_editor", None)
            st.rerun()


def _positions():
    pf = st.session_state.get("pf") or {"cash": 0.0, "positions": []}
    pos, cash = pf["positions"], float(pf["cash"])
    if not pos:
        T.show('<div class="amb-empty">No positions yet. Add what you own below (ticker, shares, average cost and date), or '
               'load the example portfolio to see how the page works. Nothing leaves this browser.</div>')
        _editor(pf)
        return
    syms = list(dict.fromkeys(p["sym"] for p in pos))
    with st.spinner("Marking positions to market..."):
        quotes = {s: src.try_quote(s) for s in syms}
    rows = P.pnl_rows(pos, quotes)
    # one line per ticker, like a broker: shares add up and the average cost is weighted
    g = rows.groupby("sym", sort=False).agg(shares=("shares", "sum"), basis=("basis", "sum"), value=("value", "sum"),
                                            daily=("daily", "sum"), last=("last", "first"), chg_pct=("chg_pct", "first"),
                                            date=("date", "min"))
    g["avg"] = g["basis"] / g["shares"]
    g["unrl"] = g["value"] - g["basis"]
    g["unrl_pct"] = g["unrl"] / g["basis"]
    mv = float(g["value"].sum(skipna=True))
    nav = mv + cash
    g["weight"] = g["value"] / nav if nav else np.nan
    daily = float(g["daily"].sum(skipna=True))
    basis = float(g["basis"].sum())
    unrl = mv - basis
    prev_nav = nav - daily

    with st.spinner("Loading price history (free plan: 8 requests per minute)..."):
        closes = _closes(tuple(syms))
    twr = P.time_weighted(pos, closes) if not closes.empty else pd.Series(dtype=float)
    spy_ret = None
    if len(twr) > 1 and "SPY" in closes:
        spy = closes["SPY"].reindex(twr.index).ffill()
        spy_cum = spy / spy.iloc[0] - 1
        spy_ret = float(spy_cum.iloc[-1])

    T.show(T.kv([
        ("Net liquidation value", _m(nav), f"positions {T.money(mv, 0)} + cash {T.money(cash, 0)}"),
        ("Daily P&L", _signed_money(daily), T.pct(daily / prev_nav if prev_nav else None, 2) + " today"),
        ("Unrealized P&L", _signed_money(unrl), T.pct(unrl / basis if basis else None, 1) + " on cost"),
        ("Cost basis", _m(basis), f"{len(g)} positions"),
        ("Return since first buy", f'<span style="color:var(--{T.tone(twr.iloc[-1] if len(twr) else None)})">'
         f'{T.pct(twr.iloc[-1] if len(twr) else None, 1)}</span>', "time-weighted"),
        ("S&P 500, same period", T.pct(spy_ret, 1), "SPY, price return"),
    ]))

    # ---- positions table
    head = ("<th>Instrument</th><th>Position</th><th>Last</th><th>Change</th><th>Daily P&amp;L</th><th>Avg price</th>"
            "<th>Cost basis</th><th>Market value</th><th>Unrealized P&amp;L</th><th>Unrl. %</th><th>% of NAV</th>")
    body = ""
    for sym, r in g.sort_values("value", ascending=False).iterrows():
        body += (f'<tr><td><span{T.go_attr("t:" + sym)} style="cursor:pointer"><b style="color:var(--text)">{T.esc(sym)}</b>'
                 f'<span class="amb-sub-name">{T.esc(name_of(sym)[:26])}</span></span></td>'
                 f'<td>{r["shares"]:,.4g}</td><td>{_m(r["last"])}</td>'
                 f'<td style="color:var(--{T.tone(r["chg_pct"])})">{T.pct(r["chg_pct"], 2)}</td>'
                 f'<td>{_signed_money(r["daily"])}</td><td>{_m(r["avg"])}</td><td>{_m(r["basis"])}</td>'
                 f'<td>{_m(r["value"])}</td><td>{_signed_money(r["unrl"])}</td>'
                 f'<td style="color:var(--{T.tone(r["unrl_pct"])})">{T.pct(r["unrl_pct"], 1)}</td><td>{T.pct(r["weight"], 1, False)}</td></tr>')
    body += (f'<tr class="sub"><td>Cash</td><td></td><td></td><td></td><td></td><td></td><td></td><td>{_m(cash)}</td>'
             f'<td></td><td></td><td>{T.pct(cash / nav if nav else None, 1, False)}</td></tr>')
    body += (f'<tr class="hl"><td>Total</td><td></td><td></td><td>{T.pct(daily / prev_nav if prev_nav else None, 2)}</td>'
             f'<td>{_signed_money(daily)}</td><td></td><td>{_m(basis)}</td><td>{_m(nav)}</td>'
             f'<td>{_signed_money(unrl)}</td><td>{T.pct(unrl / basis if basis else None, 1)}</td><td>100.0%</td></tr>')
    click(f'<div class="amb-wrap"><table class="amb-table pnl"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>',
          "pnl_tbl")
    T.show('<div class="amb-note">Daily P&amp;L = shares × today\'s change. Unrealized P&amp;L = market value − cost basis. '
           'Click a ticker to open its analysis.</div>')

    # ---- performance + allocation
    a, b = st.columns([1.5, 1], gap="large")
    with a:
        T.section("Performance vs the S&P 500", "time-weighted, since the first purchase")
        if len(twr) > 1:
            fig = go.Figure()
            fig.add_scatter(x=twr.index, y=twr.values * 100, name="Portfolio", mode="lines", line=dict(color=T.C["acc"], width=2.2))
            if spy_ret is not None:
                fig.add_scatter(x=spy_cum.index, y=spy_cum.values * 100, name="S&P 500 (SPY)", mode="lines",
                                line=dict(color=T.C["text2"], width=1.4, dash="dot"))
            fig.update_yaxes(ticksuffix="%")
            T.plot(fig, 300)
            T.show('<div class="amb-note">Time-weighted return treats each purchase as new money, so adding positions does not '
                   'count as performance and the line can be compared with the index. Uses daily closes.</div>')
        else:
            T.show('<div class="amb-empty">Price history isn\'t available right now (free plan limit). Refresh in a minute.</div>')
    with b:
        T.section("Allocation", "% of net liquidation value")
        al = g["weight"].dropna().sort_values()
        labels, vals = list(al.index), list(al.values * 100)
        if cash > 0:
            labels, vals = ["Cash"] + labels, [cash / nav * 100] + vals
        fig = go.Figure(go.Bar(y=labels, x=vals, orientation="h", marker_color=[T.C["us"] if l_ == "Cash" else T.C["acc"] for l_ in labels],
                               text=[f"{v:.1f}%" for v in vals], textposition="outside", cliponaxis=False,
                               hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
        fig.update_xaxes(ticksuffix="%", range=[0, max(vals) * 1.25 if vals else 1])
        fig.update_layout(hovermode="closest", margin=dict(l=8, r=30, t=10, b=8))
        T.plot(fig, 300)

    # ---- risk of today's holdings
    have = [s for s in syms if s in closes.columns]
    if len(have) >= 1 and "SPY" in closes and len(closes) > 120:
        rets = closes.pct_change().dropna()
        w = g.loc[have, "value"].astype(float)
        risk = P.holdings_risk(w, rets[have], rets["SPY"])
        T.section("Risk of today's holdings", f"today's weights over the last {risk['days']} sessions")
        T.show(T.kv([
            ("Beta", f"{risk['beta']:.2f}" if risk["beta"] is not None else "—", "vs S&P 500, daily"),
            ("Volatility", T.pct(risk["vol"], 1, False), "annualized"),
            ("1-day VaR 95%", f'<span style="color:var(--down)">−{T.money(risk["var"] * mv, 0)}</span>',
             f"{T.pct(-risk['var'], 1)} of the stocks, historical"),
            ("Expected shortfall", f'<span style="color:var(--down)">−{T.money(risk["cvar"] * mv, 0)}</span>',
             "average loss on the worst 5% of days"),
            ("Effective positions", f"{risk['effective_n']:.1f}", "1 / sum of squared weights"),
            ("Largest position", f"{g['weight'].idxmax()} · {T.pct(g['weight'].max(), 0, False)}", "of NAV"),
        ]))
    _editor(pf)


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
    fig.add_scatter(x=fr["vol"] * 100, y=fr["ret"] * 100, mode="lines", name="Efficient frontier",
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
    fig.update_layout(hovermode="closest")
    T.plot(fig, 440)

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
