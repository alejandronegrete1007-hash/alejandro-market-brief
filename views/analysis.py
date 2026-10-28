"""Analysis: one stock in depth - chart & risk, DCF (levered + unlevered), analysts & our take, news."""
from __future__ import annotations

import datetime as dt
from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import ai
import filings
import quant as Q
import sources as src
import state
import theme as T
import valuation as V
from views import compare, outlook
from views.common import name_of


# --------------------------------------------------------------------------- picker
def _on_select(key: str):
    v = st.session_state.get(key)
    if v:
        state.focus(v)
    st.session_state["an_other"] = ""


def _on_type():
    v = (st.session_state.get("an_other") or "").upper().strip()
    if v:
        state.focus(v)


def _pick() -> str | None:
    options = state.all_symbols()
    focus = st.session_state.get("focus") or (options[0] if options else None)
    if focus and focus not in options:
        options = [focus] + options
    if focus and not st.session_state.get("focus"):
        state.focus(focus)
    c1, c2 = st.columns([2, 1], gap="medium")
    key = f"an_sel_{focus}"
    with c1:
        st.selectbox("Stock", options, index=options.index(focus) if focus in options else 0,
                     format_func=lambda s: f"{s} · {name_of(s)}", key=key, on_change=_on_select, args=(key,))
    with c2:
        st.text_input("Or type any ticker", placeholder="e.g. NVDA, WMT, SPY", key="an_other", on_change=_on_type)
    return focus


def render():
    sym = _pick()
    if not sym:
        return
    market = state.market_of(sym)
    q = src.try_quote(sym)
    if not q:
        st.error(f"No quote for {sym}. Check the ticker (US-listed stocks, ADRs and ETFs).")
        return
    prof = src.profile(sym)
    is_open = src.us_market_status()["open"]
    er = src.next_earnings(sym)
    kind = "ETF" if src.is_etf(sym) else ("NYSE-listed Mexican ADR" if market == "MX" else "US-listed stock")

    T.show(f"""
    <div class="amb-hero" style="margin-top:6px">
      <div style="display:flex;gap:14px;align-items:center;min-width:0">{T.logo(prof['logo'], sym, 52)}
        <div style="min-width:0"><div class="amb-eyebrow">{(T.esc(prof['industry']) + ' · ') if prof['industry'] else ''}{kind}</div>
        <h1 style="font-size:clamp(1.6rem,3.4vw,2.5rem)">{T.esc(name_of(sym))} <span style="color:var(--muted);font-weight:500">{T.esc(sym)}</span></h1>
        <div class="sub">{T.chip(market, market)}<span>{T.status(q['time'], is_open)}</span>
        <span>{('Next earnings ' + er['date'] + (' · ' + er['when'] if er['when'] else '')) if er else 'No earnings date announced'}</span></div></div>
      </div>
      <div style="text-align:right"><div style="font-family:var(--mono);font-size:2.1rem;color:var(--text)">{T.money(q['price'])}</div>
        <div>{T.pill(q['pct'])}</div></div>
    </div>""")

    with st.spinner("Loading two years of prices (free plan: 8 requests per minute)..."):
        h = src.try_history(sym)
        spy = src.try_history("SPY")
    if h is None:
        st.warning("Price history isn't available right now (Twelve Data limit). Refresh in a minute.")
        return
    close = h["close"].copy()
    if close.index[-1].date() < q["time"].date():
        close.loc[pd.Timestamp(q["time"].date())] = q["price"]
    rf, rf_label = src.risk_free()
    vol = Q.annual_volatility(close)
    m = {"ytd": Q.ytd_return(close), "r1y": Q.period_return(close, 365), "vol": vol, "mdd": Q.max_drawdown(close),
         "beta": Q.beta(close, spy["close"]) if spy is not None else None, "sharpe": Q.sharpe(close, rf),
         "trend": Q.trend_label(close)}
    T.show(T.kv([
        ("YTD return", f'<span style="color:var(--{T.tone(m["ytd"])})">{T.pct(m["ytd"])}</span>', "since Dec 31 close"),
        ("1-year return", T.pct(m["r1y"]), ""),
        ("Volatility", T.pct(vol, 1, signed=False), "annualized"),
        ("Max drawdown", T.pct(m["mdd"]), "worst fall, 1 year"),
        ("Beta", f'{m["beta"]:.2f}' if m["beta"] is not None else "—", "vs S&P 500, 2y weekly"),
        ("Sharpe", f'{m["sharpe"]:.2f}' if m["sharpe"] is not None else "—", "1 year, vs 10Y"),
    ]))

    ctx = {"sym": sym, "q": q, "m": m, "rf": rf, "prof": prof, "er": er, "market": market}
    try:
        news = src.company_news(sym)
    except Exception:
        news = []
    ctx["news"] = news
    t_chart, t_val, t_out, t_cmp, t_take, t_news = st.tabs(
        ["Chart & risk", "Valuation", "Outlook", "Compare", "Analysts & our take", "News"])
    # Order matters: later tabs (and the AI take) use what earlier ones computed.
    with t_chart:
        _chart_tab(sym, h, close, q, m, vol, ctx)
    with t_val:
        _valuation_tab(sym, q, m, rf, rf_label, close, market, ctx)
    with t_out:
        outlook.render(sym, close, q, ctx)
    with t_cmp:
        compare.render(sym, close, prof, rf, market, ctx)
    with t_take:
        _take_tab(sym, ctx)
    with t_news:
        T.show(T.news_list(news, 12))
    T.footer("Not investment advice · statistics describe the past, they don't predict the future")


# --------------------------------------------------------------------------- chart & risk
def _chart_tab(sym, h, close, q, m, vol, ctx):
    span = st.segmented_control("Range", ["3M", "6M", "1Y", "2Y"], default="1Y", key="span", label_visibility="collapsed")
    days = {"3M": 92, "6M": 183, "1Y": 365, "2Y": 760}[span or "1Y"]
    s50, s200 = Q.sma(close, 50), Q.sma(close, 200)
    cut = close.index[-1] - pd.Timedelta(days=days)
    c, hh = close[close.index >= cut], h[h.index >= cut]
    up = c.iloc[-1] >= c.iloc[0]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.8, 0.2], vertical_spacing=0.03)
    fig.add_scatter(x=c.index, y=c.values, mode="lines", name=sym, line=dict(color=T.C["up"] if up else T.C["down"], width=2),
                    fill="tozeroy", fillcolor=("rgba(43,214,123,.06)" if up else "rgba(255,92,108,.06)"), row=1, col=1)
    fig.add_scatter(x=s50[s50.index >= cut].index, y=s50[s50.index >= cut].values, name="50-day avg",
                    line=dict(color=T.C["gold"], width=1.2, dash="dot"), row=1, col=1)
    fig.add_scatter(x=s200[s200.index >= cut].index, y=s200[s200.index >= cut].values, name="200-day avg",
                    line=dict(color=T.C["us"], width=1.2, dash="dot"), row=1, col=1)
    if "volume" in hh:
        fig.add_bar(x=hh.index, y=hh["volume"], marker_color=T.C["line2"], row=2, col=1, showlegend=False, name="Volume")
    fig.update_yaxes(range=[c.min() * 0.95, c.max() * 1.04], row=1, col=1)
    fig.update_yaxes(showticklabels=False, row=2, col=1)
    T.plot(fig, 420)
    T.show(f'<div class="amb-note"><span class="amb-tag calc">Calc</span>{T.esc(m["trend"])}.</div>')

    if vol:
        T.section("Statistical price ranges", "if the next months are as volatile as the last year", "Not a forecast")
        rows, ranges = [], {}
        for label, d in (("1 month", 21), ("3 months", 63), ("6 months", 126)):
            r = Q.statistical_range(q["price"], vol, d)
            ranges[label] = r
            rows.append(f'<tr><td>{label}</td><td>{T.money(r.low68)} – {T.money(r.high68)}</td>'
                        f'<td>{T.money(r.low95)} – {T.money(r.high95)}</td></tr>')
        ctx["ranges"] = ranges
        T.show(f'<div class="amb-wrap"><table class="amb-table"><thead><tr><th>Horizon</th><th>68% of the time</th>'
               f'<th>95% of the time</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
               f'<div class="amb-note">Zero-drift lognormal band using {T.pct(vol, 0, signed=False)} annual volatility.</div>')
    dd = Q.drawdown_series(close.iloc[-252:])
    fig = go.Figure(go.Scatter(x=dd.index, y=dd.values * 100, mode="lines", line=dict(color=T.C["down"], width=1.5),
                               fill="tozeroy", fillcolor="rgba(255,92,108,.1)", name="Drawdown"))
    fig.update_yaxes(ticksuffix="%")
    T.plot(fig, 220, "Drawdown from the previous high, 1 year")


# --------------------------------------------------------------------------- valuation
def _multiples(sym, ctx):
    try:
        km = src.key_metrics(sym)
    except Exception:
        km = {}
    ctx["multiples"] = {k: v for k, v in km.items() if k not in ("hi52", "lo52")}
    T.section("Multiples", "trailing twelve months · Finnhub", "Relative value")
    T.show(T.kv([
        ("P/E", T.mult(km.get("pe")), "price / earnings"),
        ("Forward P/E", T.mult(km.get("fwd_pe")), "on expected earnings"),
        ("EV/EBITDA", T.mult(km.get("ev_ebitda")), ""),
        ("P/S", T.mult(km.get("ps")), "price / sales"),
        ("EV/FCF", T.mult(km.get("ev_fcf")), ""),
        ("Net margin", T.pct(km.get("net_margin"), 1, False, frac=False), ""),
        ("ROE", T.pct(km.get("roe"), 1, False, frac=False), ""),
        ("Revenue growth", T.pct(km.get("rev_growth"), 1, True, frac=False), "year over year"),
    ]))


def _slider(label, key, lo, hi, default, step, help_=None, fmt="%.1f%%"):
    """Percent slider that stores whole percents in the UI and returns a fraction."""
    default = float(np.clip(default, lo, hi))
    return st.slider(label, lo, hi, round(default / step) * step, step, key=key, help=help_, format=fmt) / 100


def _valuation_tab(sym, q, m, rf, rf_label, close, market, ctx):
    price = q["price"]
    try:
        if src.is_etf(sym):
            raise filings.FilingsError("This is an ETF (a basket of securities), so it has no cash flows of its own to "
                                       "discount. Use the chart, risk and analyst tabs instead.")
        if market == "MX":
            raise filings.FilingsError("Mexican companies file a 20-F in IFRS and pesos, and one ADR equals several local "
                                       "shares, so the automatic DCF covers US filers. Multiples and the analyst view still work.")
        with st.spinner("Reading the 10-K data from the SEC..."):
            f = filings.build(src.sec_facts(sym))
        if not f["revenue0"] or f["ebitda_margin"] is None:
            raise filings.FilingsError("Revenue or operating income isn't tagged in the SEC data for this company.")
    except Exception as e:
        T.show(f'<div class="amb-empty">DCF not available for {T.esc(sym)}. {T.esc(str(e))}</div>')
        _multiples(sym, ctx)
        return

    shares, debt, cash = f["shares"], f["debt"], f["cash"]
    mcap = price * shares
    ebitda0 = f["revenue0"] * f["ebitda_margin"]
    ev_mkt = mcap + debt - cash
    cur_mult = ev_mkt / ebitda0 if ebitda0 > 0 else None
    beta = m["beta"] if m["beta"] is not None else 1.0
    ke0 = V.capm(rf, beta)
    kd0 = float(np.clip((f["interest"] / debt) if (f["interest"] and debt) else rf + 0.015, rf + 0.005, 0.12))
    tax0 = f["tax_rate"] if (f["tax_rate"] is not None and f["tax_rate"] >= 0.05) else 0.21
    wacc0 = V.wacc(ke0, kd0, tax0, mcap, debt)
    g0 = Q.cagr(f["revenue"]) if not f["revenue"].empty else None
    g0 = float(np.clip(g0 if g0 is not None else 0.06, -0.05, 0.25))
    m0 = f["ebitda_margin"]
    m3 = f["ebitda_margin_3y"]
    target0 = m0 if m0 > 0 else (m3 if m3 and m3 > 0 else 0.10)

    k = f"{sym}_"
    T.section("Assumptions", f"defaults from the 10-K (FY ending {f['fiscal_end']}) and market data", "Discounted cash flow")
    c = st.columns(5)
    with c[0]:
        tax = _slider("Tax rate", k + "tax", 0.0, 40.0, tax0 * 100, 0.5, "Default: effective tax rate in the last 10-K (21% if not meaningful).")
    with c[1]:
        g = _slider("Growth, yrs 1-5", k + "g", -10.0, 40.0, g0 * 100, 0.5,
                    "Revenue growth per year; earnings grow with it at the chosen margin. Default: 5-year revenue CAGR, capped at 25%.")
    with c[2]:
        wacc = _slider("Discount rate (WACC)", k + "wacc", 5.0, 16.0, wacc0 * 100, 0.1,
                       f"Default {wacc0:.1%}: equity at CAPM {ke0:.1%} and debt at {kd0:.1%} pre-tax, weighted by market value. {rf_label}")
    with c[3]:
        tg = _slider("Perpetual growth", k + "tg", 0.0, 5.0, 2.5, 0.1, "Growth forever after year 5. Keep it near long-run GDP / inflation.")
    with c[4]:
        mult = st.slider("EV/EBITDA exit multiple", 2.0, 40.0, float(np.clip(round(cur_mult or 12.0, 1), 2.0, 40.0)), 0.5,
                         key=k + "mult", help=f"Default: today's EV/EBITDA ({T.mult(cur_mult)}).", format="%.1fx")
    c = st.columns(5)
    with c[0]:
        ke = _slider("Cost of equity", k + "ke", 5.0, 20.0, ke0 * 100, 0.1, f"Discount rate for the levered DCF. Default CAPM: {rf:.2%} + {beta:.2f} × 5%.")
    with c[1]:
        mt = _slider("EBITDA margin, yr 5", k + "mt", -20.0, 80.0, target0 * 100, 0.5,
                     f"Today: {m0:.1%}. The margin moves in a straight line to this level by year 5.")
    with c[2]:
        capex = _slider("Capex, % revenue", k + "capex", 0.0, 50.0, (f["capex_pct"] or 0) * 100, 0.5, "Default: last fiscal year.")
    with c[3]:
        da = _slider("D&A, % revenue", k + "da", 0.0, 40.0, (f["da_pct"] or 0) * 100, 0.5, "Default: last fiscal year.")
    with c[4]:
        nwc = _slider("Working capital, % of new revenue", k + "nwc", 0.0, 40.0, 10.0, 1.0,
                      "Cash tied up in inventory and receivables for each extra dollar of sales.")
    if st.button("Reset to defaults", key=k + "reset"):
        for s in ("tax", "g", "wacc", "tg", "mult", "ke", "mt", "capex", "da", "nwc"):
            st.session_state.pop(k + s, None)
        st.rerun()

    if wacc <= tg + 0.005 or ke <= tg + 0.005:
        st.error("Both discount rates must be clearly above the perpetual growth rate.")
        _multiples(sym, ctx)
        return
    a = V.Inputs(revenue0=f["revenue0"], growth=g, margin0=m0, margin_target=mt, da_pct=da, capex_pct=capex, nwc_pct=nwc,
                 tax=tax, wacc=wacc, ke=ke, kd=kd0, tg=tg, exit_mult=mult, debt0=debt, cash0=cash, shares=shares)
    v = V.value(a)
    avg = v["average"]
    label, gap = V.verdict(avg, price)
    implied = V.implied_growth(a, price)
    cls = {"Undervalued": "under", "Overvalued": "over"}.get(label, "fair")
    u, l = v["unlevered"], v["levered"]
    ctx["dcf"] = {"avg": avg, "verdict": label, "gap": gap, "implied_g": implied, "g": g, "wacc": wacc, "ke": ke, "tg": tg,
                  "mult": mult, "u_perp": u["perpetuity"]["per_share"], "u_exit": u["exit"]["per_share"],
                  "l_perp": l["perpetuity"]["per_share"], "l_exit": l["exit"]["per_share"]}

    # ---- market vs intrinsic
    T.section("Market value vs intrinsic value", "intrinsic = average of the four DCF methods", "Result")
    T.show(f"""
    <div class="amb-verdict {cls}">
      <div><div class="amb-eyebrow" style="margin-bottom:6px">DCF verdict</div><div class="big">{label}</div>
        <div class="amb-note" style="margin-top:6px">Intrinsic value is {T.pct(gap, 0)} vs the market price</div></div>
      <div class="nums">
        <div><div class="k">Intrinsic / share</div><div class="v">{T.money(avg)}</div></div>
        <div><div class="k">Market price</div><div class="v">{T.money(price)}</div></div>
        <div><div class="k">Range of methods</div><div class="v">{T.money(v['low'])} – {T.money(v['high'])}</div></div>
        <div><div class="k">Price implies</div><div class="v">{(T.pct(implied, 1) + ' growth') if implied is not None else '—'}</div></div>
      </div>
    </div>""")

    def up(x):
        return f'<span style="color:var(--{T.tone(x / price - 1)})">{T.pct(x / price - 1, 0)}</span>'
    rows = [
        ("Market", T.big(mcap), T.big(ev_mkt), T.money(price), "—"),
        ("Unlevered · perpetuity", T.big(u["perpetuity"]["equity"]), T.big(u["perpetuity"]["ev"]), T.money(u["perpetuity"]["per_share"]), up(u["perpetuity"]["per_share"])),
        ("Unlevered · exit multiple", T.big(u["exit"]["equity"]), T.big(u["exit"]["ev"]), T.money(u["exit"]["per_share"]), up(u["exit"]["per_share"])),
        ("Levered · perpetuity", T.big(l["perpetuity"]["equity"]), "—", T.money(l["perpetuity"]["per_share"]), up(l["perpetuity"]["per_share"])),
        ("Levered · exit multiple", T.big(l["exit"]["equity"]), "—", T.money(l["exit"]["per_share"]), up(l["exit"]["per_share"])),
    ]
    body = "".join(f'<tr class="{"sub" if i == 0 else ""}"><td>{a_}</td><td>{b_}</td><td>{c_}</td><td>{d_}</td><td>{e_}</td></tr>'
                   for i, (a_, b_, c_, d_, e_) in enumerate(rows))
    T.show(f'<div class="amb-wrap" style="margin-top:12px"><table class="amb-table"><thead><tr><th>Method</th><th>Equity value</th>'
           f'<th>Enterprise value</th><th>Per share</th><th>vs price</th></tr></thead><tbody>{body}</tbody></table></div>')
    T.show(T.kv([
        ("Net debt", T.big(debt - cash), f"debt {T.big(debt)} − cash {T.big(cash)}"),
        ("EV/EBITDA today", T.mult(cur_mult), "market EV / last-year EBITDA"),
        ("Perpetuity implies", T.mult(v["implied_exit_mult"]), "exit EV/EBITDA"),
        ("Exit multiple implies", T.pct(v["implied_tg"], 1, False) if v["implied_tg"] is not None else "—", "perpetual growth"),
        ("Terminal value share", T.pct(u["perpetuity"]["tv_share"], 0, False), "of EV, perpetuity method"),
        ("Shares", f"{shares / 1e6:,.0f}M", f["shares_source"]),
    ]))
    T.show('<div class="amb-note"><span class="amb-tag calc">Calc</span><b>Unlevered</b>: free cash flow to the firm (before '
           'debt payments) discounted at the WACC, minus net debt. <b>Levered</b>: free cash flow to shareholders (after interest '
           'and new borrowing) discounted at the cost of equity. <b>Perpetuity</b> grows the last year forever; <b>exit multiple</b> '
           'sells the business at year 5 for EBITDA × multiple. When the four agree, the result is more robust.</div>')

    # ---- projection
    p = v["projection"]
    T.section("5-year projection", "US$ millions", "Model")
    lines = [("Revenue", "revenue"), ("EBITDA", "ebitda"), ("EBITDA margin", "margin"), ("− D&A", "da"), ("EBIT", "ebit"),
             ("− Taxes", "taxes"), ("− Capex", "capex"), ("− Working capital", "dnwc"), ("FCFF (unlevered)", "fcff"),
             ("− Interest after tax", None), ("+ Net borrowing", "net_borrow"), ("FCFE (levered)", "fcfe")]
    head = "".join(f"<th>Year {y}</th>" for y in p.index)
    trs = []
    for name, col in lines:
        if col == "margin":
            cells = "".join(f"<td>{x:.1%}</td>" for x in p[col])
        elif col is None:
            cells = "".join(f"<td>{x * (1 - tax) / 1e6:,.0f}</td>" for x in p["interest"])
        else:
            cells = "".join(f"<td>{x / 1e6:,.0f}</td>" for x in p[col])
        cls_ = "hl" if col in ("fcff", "fcfe") else ("sub" if name.startswith(("−", "+")) else "")
        trs.append(f'<tr class="{cls_}"><td>{name}</td>{cells}</tr>')
    T.show(f'<div class="amb-wrap"><table class="amb-table"><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>')
    if m0 <= 0:
        T.show(f'<div class="amb-note">This company lost money at the EBITDA level last year ({m0:.1%} margin). The value depends '
               f'almost entirely on the year-5 margin you set: try a few levels to see the range.</div>')

    # ---- football field + sensitivity
    a1, a2 = st.columns([1.3, 1], gap="large")
    with a1:
        T.section("Football field", "ranges vs today's price", "All methods")
        bars = []
        if len(close) > 200:
            bars.append(("52-week range", close.iloc[-252:].min(), close.iloc[-252:].max(), T.C["us"]))
        if m["vol"]:
            r = Q.statistical_range(price, m["vol"], 63)
            bars.append(("3-month stat. range", r.low95, r.high95, "#C792EA"))
        for nm, pick, field, delta in (
                ("Unlevered · perpetuity", lambda x: x["unlevered"]["perpetuity"]["per_share"], "tg", 0.005),
                ("Unlevered · exit", lambda x: x["unlevered"]["exit"]["per_share"], "exit_mult", 2.0),
                ("Levered · perpetuity", lambda x: x["levered"]["perpetuity"]["per_share"], "tg", 0.005),
                ("Levered · exit", lambda x: x["levered"]["exit"]["per_share"], "exit_mult", 2.0)):
            vals = []
            for dw in (-0.01, 0.01):
                for dc in (-delta, delta):
                    try:
                        vals.append(pick(V.value(replace(a, wacc=wacc + dw, ke=ke + dw, **{field: getattr(a, field) + dc}))))
                    except ValueError:
                        pass
            if vals:
                bars.append((nm, min(vals), max(vals), T.C["gold"] if "Unlevered" in nm else T.C["mx"]))
        fig = go.Figure()
        for lbl, lo, hi, colr in bars:
            fig.add_trace(go.Bar(y=[lbl], x=[hi - lo], base=[lo], orientation="h", marker=dict(color=colr, opacity=.75),
                                 hovertemplate=f"{lbl}<br>${lo:,.2f} – ${hi:,.2f}<extra></extra>", showlegend=False))
        fig.add_vline(x=price, line=dict(color=T.C["text"], width=1.5, dash="dash"),
                      annotation_text=f"Price {T.money(price)}", annotation_font_color=T.C["text"])
        fig.update_layout(bargap=0.45, hovermode="closest", margin=dict(l=8, r=16, t=30, b=8))
        fig.update_xaxes(tickprefix="$", gridcolor=T.C["line"])
        fig.update_yaxes(tickfont=dict(family="Inter", color=T.C["text2"]), autorange="reversed")
        T.plot(fig, 320)
        T.show('<div class="amb-note">DCF bars move WACC (and cost of equity) ±1 pt and perpetual growth ±0.5 pt or the exit multiple ±2x.</div>')
    with a2:
        T.section("Sensitivity", "unlevered value per share", "What-if")
        sens_kind = st.segmented_control("Terminal", ["Perpetual growth", "Exit multiple"], default="Perpetual growth",
                                         key=k + "sens", label_visibility="collapsed")
        waccs = [wacc - 0.01, wacc - 0.005, wacc, wacc + 0.005, wacc + 0.01]
        if sens_kind == "Exit multiple":
            cols = [max(mult - 4, 1), mult - 2 if mult > 3 else mult, mult, mult + 2, mult + 4]
            tbl = V.grid(a, waccs, cols, "exit_mult", lambda x: x["unlevered"]["exit"]["per_share"])
            tbl.columns = [f"{c_:.1f}x" for c_ in tbl.columns]
        else:
            cols = [tg - 0.01, tg - 0.005, tg, tg + 0.005, tg + 0.01]
            tbl = V.grid(a, waccs, cols, "tg", lambda x: x["unlevered"]["perpetuity"]["per_share"])
            tbl.columns = [f"g {c_ * 100:.1f}%" for c_ in tbl.columns]
        tbl.index = [f"WACC {w * 100:.1f}%" for w in tbl.index]

        def shade(x):
            if not T.is_num(x):
                return ""
            al = min(abs(x / price - 1) / 0.5, 1) * 0.45 + 0.08
            return f"background-color: rgba({'43,214,123' if x >= price else '255,92,108'},{al:.2f}); color: #ECEFF4"
        st.dataframe(tbl.style.format("${:,.0f}").map(shade), width="stretch")
        T.show(f'<div class="amb-note">Green above today\'s price ({T.money(price)}), red below.</div>')

    _history_chart(f)
    with st.expander("Data notes"):
        T.show(T.kv([("Revenue, last FY", T.big(f["revenue0"]), f["fiscal_end"] or ""),
                     ("EBITDA margin, last FY", T.pct(m0, 1, False), "EBIT + D&A"),
                     ("Cost of debt (pre-tax)", T.pct(kd0, 2, False), "interest / debt"),
                     ("Beta used", f"{beta:.2f}", "2 years of weekly returns")]))
        for n in f["notes"]:
            st.caption("• " + n)
    _multiples(sym, ctx)


def _history_chart(f):
    T.section("Revenue, EBITDA and free cash flow", "fiscal years · SEC 10-K", "History")
    fig = go.Figure()
    fig.add_bar(x=f["revenue"].index.year, y=f["revenue"].values / 1e9, name="Revenue", marker_color=T.C["line2"])
    if not f["ebitda"].empty:
        fig.add_bar(x=f["ebitda"].index.year, y=f["ebitda"].values / 1e9, name="EBITDA", marker_color=T.C["gold"])
    fig.add_bar(x=f["fcf"].index.year, y=f["fcf"].values / 1e9, name="Free cash flow",
                marker_color=[T.C["mx"] if x >= 0 else T.C["down"] for x in f["fcf"].values])
    fig.update_yaxes(ticksuffix="B", tickprefix="$")
    fig.update_layout(barmode="group")
    T.plot(fig, 280)


# --------------------------------------------------------------------------- analysts & AI take
CONSENSUS = [(4.5, "Strong Buy", "up"), (3.5, "Buy", "up"), (2.5, "Hold", "flat"), (1.5, "Sell", "down"), (0, "Strong Sell", "down")]


def _consensus(sym, ctx):
    try:
        recs = src.recommendations(sym)
    except Exception:
        recs = []
    T.section("Wall Street consensus", "Finnhub analyst recommendation trends", "What the experts say")
    if not recs:
        T.show('<div class="amb-empty">No analyst ratings available for this ticker.</div>')
        return
    r = recs[0]
    keys = [("strongBuy", "Strong Buy", "#1FAE68"), ("buy", "Buy", T.C["up"]), ("hold", "Hold", T.C["gold"]),
            ("sell", "Sell", "#FF8A80"), ("strongSell", "Strong Sell", T.C["down"])]
    counts = [int(r.get(k_) or 0) for k_, _, _ in keys]
    n = sum(counts)
    if not n:
        T.show('<div class="amb-empty">No analyst ratings available for this ticker.</div>')
        return
    score = sum(c_ * w for c_, w in zip(counts, (5, 4, 3, 2, 1))) / n
    lbl, tone = next((lb, tn) for th, lb, tn in CONSENSUS if score >= th)
    bars = "".join(f'<i style="width:{c_ / n * 100:.1f}%;background:{col}" title="{nm}: {c_}"></i>' for c_, (_, nm, col) in zip(counts, keys) if c_)
    legend = " · ".join(f"{nm} {c_}" for c_, (_, nm, _) in zip(counts, keys))
    trend = ""
    if len(recs) >= 4:
        old = recs[3]
        on = sum(int(old.get(k_) or 0) for k_, _, _ in keys)
        if on:
            os_ = sum(int(old.get(k_) or 0) * w for (k_, _, _), w in zip(keys, (5, 4, 3, 2, 1))) / on
            d = score - os_
            trend = f"{'more bullish' if d > 0.05 else 'more bearish' if d < -0.05 else 'unchanged'} vs {old.get('period', '')[:7]}"
    ctx["consensus"] = f"{lbl} (score {score:.2f}/5 from {n} analysts: {legend}; {trend or 'no trend data'})"
    T.show(f"""
    <div class="amb-take">
      <div style="display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap">
        <div><div class="amb-eyebrow" style="margin-bottom:6px">{n} analysts · {r.get('period', '')[:7]}</div>
          <div class="amb-verdict-big" style="font-family:var(--display);font-size:1.6rem;font-weight:700;color:var(--{tone if tone != 'flat' else 'gold'})">{lbl}</div></div>
        <div style="font-family:var(--mono);color:var(--text2);font-size:.85rem">{score:.2f} / 5 {('· ' + trend) if trend else ''}</div>
      </div>
      <div class="amb-bars">{bars}</div>
      <div class="amb-note" style="margin-top:0">{legend}</div>
    </div>""")
    T.show('<div class="amb-note">Ratings from the brokerage analysts that cover the stock, aggregated monthly by Finnhub. '
           'Price targets are not in the free plan.</div>')


def _facts(ctx) -> str:
    q, m, p = ctx["q"], ctx["m"], ctx["prof"]
    lines = [f"Company: {name_of(ctx['sym'])} ({ctx['sym']}), industry: {p['industry'] or 'n/a'}, "
             f"{'Mexican company, NYSE-listed ADR' if ctx['market'] == 'MX' else 'US-listed'}",
             f"Price: {q['price']:.2f} ({q['pct']:+.2f}% today)",
             f"YTD return: {T.pct(m['ytd'])}; 1-year: {T.pct(m['r1y'])}; annualized volatility: {T.pct(m['vol'], 1, False)}; "
             f"1-year max drawdown: {T.pct(m['mdd'])}; beta: {m['beta'] if m['beta'] is None else round(m['beta'], 2)}; "
             f"Sharpe: {m['sharpe'] if m['sharpe'] is None else round(m['sharpe'], 2)}",
             f"Trend: {m['trend']}"]
    if ctx.get("ranges"):
        r = ctx["ranges"]["3 months"]
        lines.append(f"3-month statistical range (68%): {r.low68:.2f}-{r.high68:.2f}; (95%): {r.low95:.2f}-{r.high95:.2f}")
    km = ctx.get("multiples") or {}
    if km:
        lines.append("Multiples: " + ", ".join(f"{k_}={v_:.2f}" for k_, v_ in km.items() if v_ is not None))
    d = ctx.get("dcf")
    if d:
        lines.append(f"DCF with the user's assumptions (growth {d['g']:.1%}, WACC {d['wacc']:.1%}, cost of equity {d['ke']:.1%}, "
                     f"perpetual growth {d['tg']:.1%}, exit {d['mult']:.1f}x EBITDA): unlevered perpetuity {d['u_perp']:.2f}, "
                     f"unlevered exit {d['u_exit']:.2f}, levered perpetuity {d['l_perp']:.2f}, levered exit {d['l_exit']:.2f}; "
                     f"average {d['avg']:.2f} -> {d['verdict']} ({d['gap']:+.0%} vs price). Reverse DCF: price implies "
                     f"{('%.1f%%' % (d['implied_g'] * 100)) if d['implied_g'] is not None else 'n/a'} annual growth for 5 years.")
    else:
        lines.append("DCF: not available for this security.")
    lines.append(f"Analyst consensus: {ctx.get('consensus') or 'not available'}")
    for k_, lbl in (("outlook", "Price simulation"), ("vs_market", "Versus the market"),
                    ("vs_sector", "Versus its sector"), ("vs_peers", "Relative valuation")):
        if ctx.get(k_):
            lines.append(f"{lbl}: {ctx[k_]}")
    if ctx.get("er"):
        lines.append(f"Next earnings date: {ctx['er']['date']} {ctx['er']['when']}")
    return "\n".join(lines)


LEAN = {"Buy": "up", "Hold": "flat", "Sell": "down"}


def _take_tab(sym, ctx):
    _consensus(sym, ctx)
    T.section("Our take", "Gemini reads the data on this page", "Model view")
    T.show('<div class="amb-note" style="margin:0 0 12px"><span class="amb-tag data">Data</span>fetched '
           '<span class="amb-tag calc">Calc</span>computed by the app <span class="amb-tag ai">AI</span>model opinion</div>')
    key = f"take_{sym}"
    if st.button("Write our take", type="primary", key=f"btn_{key}") or st.session_state.get(key):
        news = ctx.get("news") or []
        try:
            with st.spinner("Gemini is reading the numbers..."):
                t = ai.stock_take(sym, _facts(ctx),
                                  tuple(f"{n_['source']} | {n_['time']:%b %d} | {n_['title']} — {n_['summary'][:200]}"
                                        for n_ in news[:10] if n_.get("time")),
                                  dt.date.today().isoformat())
            st.session_state[key] = True
        except Exception as e:
            st.info(f"The AI take isn't available right now ({e}).")
            return
        lean = t.get("lean") if t.get("lean") in LEAN else "Hold"
        tone = LEAN[lean]
        col = {"up": "var(--up)", "down": "var(--down)", "flat": "var(--gold)"}[tone]
        T.show(f"""
        <div class="amb-verdict {'under' if tone == 'up' else 'over' if tone == 'down' else 'fair'}">
          <div><div class="amb-eyebrow" style="margin-bottom:6px">Model lean · {T.esc(t.get('conviction', 'Low'))} conviction</div>
            <div class="big" style="color:{col}">{lean}</div></div>
          <div style="flex:1;min-width:240px">
            <p style="margin:0 0 8px;color:var(--text);line-height:1.55">{T.esc(t.get('lean_why', ''))}</p>
            <p style="margin:0 0 4px;font-size:.88rem"><b style="color:var(--text)">What would change it:</b> {T.esc(t.get('changes_mind', ''))}</p>
            <p style="margin:0;font-size:.88rem"><b style="color:var(--text)">vs Wall Street:</b> {T.esc(t.get('vs_consensus', ''))}</p>
          </div>
        </div>""")
        st.write("")
        blocks = [("Situation", t.get("situation")), ("Momentum", t.get("momentum")), ("Valuation", t.get("valuation"))]
        T.show('<div class="amb-grid g3 stack">' + "".join(
            f'<div class="amb-take"><div class="h">{k_}</div><p>{T.esc(v_ or "")}</p></div>' for k_, v_ in blocks) + "</div>")
        st.write("")
        sc = [("Bull case", t.get("bull"), "up"), ("Base case", t.get("base"), "flat"), ("Bear case", t.get("bear"), "down")]
        T.show('<div class="amb-grid g3 stack">' + "".join(
            f'<div class="amb-story"><div class="top"><span class="amb-pill {c_}">{k_}</span></div>'
            f'<div class="row">{T.esc(v_ or "")}</div></div>' for k_, v_, c_ in sc) + "</div>")
        st.write("")
        lists = [("Risks", t.get("risks")), ("Catalysts", t.get("catalysts")), ("What the data can't tell us", t.get("unknowns"))]
        T.show('<div class="amb-grid g3 stack">' + "".join(
            f'<div class="amb-take"><div class="h">{k_}</div><p>{"<br>".join("• " + T.esc(str(x)) for x in (v_ or []))}</p></div>'
            for k_, v_ in lists) + "</div>")
        T.show(f'<div class="amb-lead" style="margin-top:20px;font-size:1.25rem"><span>›</span> {T.esc(t.get("bottom_line", ""))}</div>')
        T.show('<div class="amb-note">The lean is an AI reading of the numbers on this page and the analyst consensus, to guide your '
               'own research. It is not personalized investment advice.</div>')
    else:
        T.show('<div class="amb-empty">Click the button for a written take with a Buy / Hold / Sell lean, compared against the '
               'Wall Street consensus above, plus bull/base/bear cases, risks and catalysts. It uses the DCF with the '
               'assumptions you set in the Valuation tab.</div>')
